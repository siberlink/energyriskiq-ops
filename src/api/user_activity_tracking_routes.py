"""
Internal first-party user-behavior tracking.

Records how authenticated users behave on the platform — logins, page views,
account-section views, engaged time-on-page, and key CTA clicks — into an
append-only ``user_activity_events`` table. The data powers the LIVE "User
Activity" section of the admin portal.

Design notes:
- The browser tracker uses ``navigator.sendBeacon`` for the final time-on-page
  beacon, and ``sendBeacon`` cannot set custom headers. So the session token is
  carried inside the JSON body (``token``) rather than the ``X-User-Token``
  header. Events are attributed to a user only when that token maps to a live
  session; otherwise they are silently dropped (204) so a tracking failure can
  never break a user page.
- The ingestion endpoint always returns 204 and never raises, by design.
"""

import csv
import hashlib
import io
import json
import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response
from fastapi.concurrency import run_in_threadpool

from src.db.db import get_cursor

logger = logging.getLogger(__name__)

router = APIRouter()


def _hash_token(token: Optional[str]) -> Optional[str]:
    """Non-reversible session fingerprint so raw bearer tokens are never stored
    in analytics rows, while still distinguishing distinct sessions."""
    if not token:
        return None
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _date_bounds(date_from: Optional[str], date_to: Optional[str], default_days: int = 30):
    """Return tz-aware UTC (start, end) bounds. Dates are 'YYYY-MM-DD'; `end` is
    exclusive (the day after `date_to`). Falls back to the last `default_days`."""
    start = end = None
    try:
        if date_from:
            start = datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        start = None
    try:
        if date_to:
            end = (datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)).replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        end = None
    now = datetime.now(timezone.utc)
    if end is None:
        end = now + timedelta(days=1)
    if start is None:
        start = now - timedelta(days=default_days)
    return start, end

# Event types we accept from the browser tracker. Server-side events (login) are
# recorded directly via record_activity_event().
_CLIENT_EVENT_TYPES = {
    "page_view",
    "section_view",
    "page_time",
    "cta_click",
    "heartbeat",
}

_MAX_EVENTS_PER_BATCH = 25
_ACTIVE_WINDOW_MINUTES = 5


def run_user_activity_migration():
    """Create the user-activity-events table (idempotent)."""
    try:
        with get_cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS user_activity_events (
                    id            BIGSERIAL PRIMARY KEY,
                    user_id       INTEGER,
                    email         TEXT,
                    session_token TEXT,
                    event_type    TEXT        NOT NULL,
                    page_path     TEXT,
                    section       TEXT,
                    duration_ms   BIGINT,
                    metadata      JSONB,
                    user_agent    TEXT,
                    device        TEXT,
                    browser       TEXT,
                    ip            TEXT,
                    referrer      TEXT,
                    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_uae_created_at "
                "ON user_activity_events (created_at DESC)"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_uae_user_created "
                "ON user_activity_events (user_id, created_at DESC)"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_uae_event_type "
                "ON user_activity_events (event_type)"
            )
    except Exception as e:
        logger.error(f"user_activity migration error: {e}")
        raise


def _parse_device(ua: str) -> str:
    if not ua:
        return "Unknown"
    u = ua.lower()
    if any(t in u for t in ("ipad", "tablet", "kindle", "playbook", "silk")):
        return "Tablet"
    if any(t in u for t in ("mobi", "iphone", "android", "phone", "ipod")):
        return "Mobile"
    return "Desktop"


def _parse_browser(ua: str) -> str:
    if not ua:
        return "Unknown"
    u = ua.lower()
    if "edg/" in u or "edga" in u or "edgios" in u:
        return "Edge"
    if "opr/" in u or "opera" in u:
        return "Opera"
    if "chrome" in u or "crios" in u:
        return "Chrome"
    if "firefox" in u or "fxios" in u:
        return "Firefox"
    if "safari" in u:
        return "Safari"
    return "Other"


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()[:64]
    if request.client and request.client.host:
        return request.client.host[:64]
    return ""


def _resolve_user(token: Optional[str]):
    """Return (user_id, email) for a live session token, else (None, None)."""
    if not token:
        return None, None
    try:
        with get_cursor(commit=False) as cur:
            cur.execute(
                """
                SELECT u.id AS user_id, u.email AS email
                FROM sessions s
                JOIN users u ON u.id = s.user_id
                WHERE s.token = %s AND s.expires_at > (NOW() AT TIME ZONE 'UTC')
                """,
                (token,),
            )
            row = cur.fetchone()
            if row:
                return row["user_id"], row["email"]
    except Exception as e:
        logger.debug(f"activity token resolve failed: {e}")
    return None, None


def record_activity_event(
    user_id: Optional[int],
    email: Optional[str],
    event_type: str,
    *,
    page_path: Optional[str] = None,
    section: Optional[str] = None,
    duration_ms: Optional[int] = None,
    metadata: Optional[dict] = None,
    request: Optional[Request] = None,
    session_token: Optional[str] = None,
):
    """Insert one activity event. Never raises (best-effort)."""
    ua = ""
    ip = ""
    referrer = ""
    if request is not None:
        ua = (request.headers.get("user-agent") or "")[:500]
        ip = _client_ip(request)
        referrer = (request.headers.get("referer") or "")[:500]
    try:
        with get_cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_activity_events
                    (user_id, email, session_token, event_type, page_path,
                     section, duration_ms, metadata, user_agent, device,
                     browser, ip, referrer)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    user_id,
                    email,
                    _hash_token(session_token),
                    event_type,
                    page_path,
                    section,
                    duration_ms,
                    json.dumps(metadata) if metadata else None,
                    ua,
                    _parse_device(ua),
                    _parse_browser(ua),
                    ip,
                    referrer,
                ),
            )
    except Exception as e:
        logger.warning(f"record_activity_event failed: {e}")


def _persist_events(token, events, ua, ip):
    """Resolve the user and bulk-insert events. Runs in a worker thread so the
    blocking DB I/O never stalls the async event loop. Never raises."""
    user_id, email = _resolve_user(token)
    if not user_id:
        # Only attributed (authenticated) behavior is tracked.
        return

    device = _parse_device(ua)
    browser = _parse_browser(ua)

    token_hash = _hash_token(token)
    rows = []
    for ev in events[:_MAX_EVENTS_PER_BATCH]:
        if not isinstance(ev, dict):
            continue
        etype = str(ev.get("type") or "")[:40]
        if etype not in _CLIENT_EVENT_TYPES:
            continue
        path = (str(ev.get("path")) if ev.get("path") is not None else None)
        section = (str(ev.get("section")) if ev.get("section") is not None else None)
        if path:
            path = path[:300]
        if section:
            section = section[:120]
        duration = ev.get("duration_ms")
        try:
            duration = int(duration) if duration is not None else None
            if duration is not None and (duration < 0 or duration > 86_400_000):
                duration = None
        except (TypeError, ValueError):
            duration = None
        meta = ev.get("meta")
        meta_json = json.dumps(meta)[:2000] if isinstance(meta, dict) else None
        referrer = (str(ev.get("referrer")) if ev.get("referrer") else "")[:500]
        rows.append(
            (
                user_id, email, token_hash, etype, path, section, duration,
                meta_json, ua, device, browser, ip, referrer,
            )
        )

    if not rows:
        return
    try:
        with get_cursor() as cur:
            cur.executemany(
                """
                INSERT INTO user_activity_events
                    (user_id, email, session_token, event_type, page_path,
                     section, duration_ms, metadata, user_agent, device,
                     browser, ip, referrer)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                rows,
            )
            # Opportunistic, low-frequency retention: keep the table lean by
            # pruning high-volume heartbeats older than 14 days. Indexed on
            # created_at so this stays cheap; runs on ~0.5% of requests.
            if random.random() < 0.005:
                cur.execute(
                    "DELETE FROM user_activity_events "
                    "WHERE event_type='heartbeat' "
                    "AND created_at < NOW() - INTERVAL '14 days'"
                )
    except Exception as e:
        logger.warning(f"track_activity insert failed: {e}")


@router.post("/api/activity/track")
async def track_activity(request: Request):
    """Batched beacon endpoint from the browser tracker. Always returns 204."""
    headers = {"Cache-Control": "no-store"}
    try:
        raw = await request.body()
        if not raw:
            return Response(status_code=204, headers=headers)
        payload = json.loads(raw.decode("utf-8", "ignore"))
    except Exception:
        return Response(status_code=204, headers=headers)

    token = None
    events = []
    if isinstance(payload, dict):
        token = payload.get("token")
        events = payload.get("events") or []
    if not isinstance(events, list) or not events:
        return Response(status_code=204, headers=headers)

    ua = (request.headers.get("user-agent") or "")[:500]
    ip = _client_ip(request)

    try:
        await run_in_threadpool(_persist_events, token, events, ua, ip)
    except Exception as e:
        logger.warning(f"track_activity threadpool failed: {e}")

    return Response(status_code=204, headers=headers)


@router.options("/api/activity/track")
async def track_activity_options():
    return Response(
        status_code=204,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Max-Age": "86400",
        },
    )


# ───────────────────────────── Admin analytics ─────────────────────────────


def _require_admin(token: Optional[str]):
    from src.api.admin_routes import verify_admin_token

    verify_admin_token(token)


@router.get("/admin/activity/overview")
def admin_activity_overview(x_admin_token: Optional[str] = Header(None)):
    _require_admin(x_admin_token)
    try:
        with get_cursor(commit=False) as cur:
            cur.execute(
                f"""
                SELECT COUNT(DISTINCT user_id) AS n
                FROM user_activity_events
                WHERE created_at > NOW() - INTERVAL '{_ACTIVE_WINDOW_MINUTES} minutes'
                """
            )
            active_now = cur.fetchone()["n"] or 0

            cur.execute(
                "SELECT COUNT(DISTINCT user_id) AS n FROM user_activity_events "
                "WHERE created_at::date = NOW()::date"
            )
            active_today = cur.fetchone()["n"] or 0

            cur.execute(
                "SELECT COUNT(*) AS n FROM user_activity_events "
                "WHERE event_type='login' AND created_at::date = NOW()::date"
            )
            logins_today = cur.fetchone()["n"] or 0

            cur.execute(
                "SELECT COUNT(*) AS n FROM user_activity_events "
                "WHERE event_type='login' AND created_at > NOW() - INTERVAL '7 days'"
            )
            logins_7d = cur.fetchone()["n"] or 0

            cur.execute(
                "SELECT COUNT(*) AS n FROM user_activity_events "
                "WHERE event_type='page_view' AND created_at::date = NOW()::date"
            )
            page_views_today = cur.fetchone()["n"] or 0

            cur.execute(
                "SELECT COALESCE(SUM(duration_ms),0) AS ms FROM user_activity_events "
                "WHERE event_type='page_time' AND created_at::date = NOW()::date"
            )
            engaged_ms_today = int(cur.fetchone()["ms"] or 0)

            # Returning vs one-time (by total login count over all time)
            cur.execute(
                """
                SELECT
                    COUNT(*) FILTER (WHERE logins >= 2) AS returning,
                    COUNT(*) FILTER (WHERE logins = 1) AS one_time
                FROM (
                    SELECT user_id, COUNT(*) AS logins
                    FROM user_activity_events
                    WHERE event_type='login' AND user_id IS NOT NULL
                    GROUP BY user_id
                ) t
                """
            )
            rv = cur.fetchone()
            returning_users = rv["returning"] or 0
            one_time_users = rv["one_time"] or 0

            cur.execute(
                """
                SELECT COALESCE(device,'Unknown') AS device, COUNT(*) AS n
                FROM user_activity_events
                WHERE created_at > NOW() - INTERVAL '30 days'
                GROUP BY device ORDER BY n DESC
                """
            )
            devices = [{"device": r["device"], "count": r["n"]} for r in cur.fetchall()]

            cur.execute(
                """
                SELECT COALESCE(browser,'Unknown') AS browser, COUNT(*) AS n
                FROM user_activity_events
                WHERE created_at > NOW() - INTERVAL '30 days'
                GROUP BY browser ORDER BY n DESC
                """
            )
            browsers = [{"browser": r["browser"], "count": r["n"]} for r in cur.fetchall()]

        return {
            "active_now": active_now,
            "active_today": active_today,
            "logins_today": logins_today,
            "logins_7d": logins_7d,
            "page_views_today": page_views_today,
            "engaged_ms_today": engaged_ms_today,
            "returning_users": returning_users,
            "one_time_users": one_time_users,
            "devices": devices,
            "browsers": browsers,
            "active_window_minutes": _ACTIVE_WINDOW_MINUTES,
        }
    except Exception as e:
        logger.error(f"activity overview failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/activity/live")
def admin_activity_live(
    x_admin_token: Optional[str] = Header(None),
    limit: int = 60,
):
    _require_admin(x_admin_token)
    limit = max(1, min(limit, 200))
    try:
        with get_cursor(commit=False) as cur:
            cur.execute(
                """
                SELECT id, user_id, email, event_type, page_path, section,
                       duration_ms, device, browser, created_at
                FROM user_activity_events
                ORDER BY id DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()
        events = [
            {
                "id": r["id"],
                "user_id": r["user_id"],
                "email": r["email"],
                "event_type": r["event_type"],
                "page_path": r["page_path"],
                "section": r["section"],
                "duration_ms": int(r["duration_ms"]) if r["duration_ms"] is not None else None,
                "device": r["device"],
                "browser": r["browser"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ]
        return {"events": events}
    except Exception as e:
        logger.error(f"activity live failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/activity/logins")
def admin_activity_logins(x_admin_token: Optional[str] = Header(None)):
    _require_admin(x_admin_token)
    try:
        with get_cursor(commit=False) as cur:
            cur.execute(
                """
                SELECT user_id, MAX(email) AS email, COUNT(*) AS login_count,
                       MAX(created_at) AS last_login
                FROM user_activity_events
                WHERE event_type='login' AND user_id IS NOT NULL
                GROUP BY user_id
                ORDER BY login_count DESC, last_login DESC
                LIMIT 50
                """
            )
            rows = cur.fetchall()
        leaders = [
            {
                "user_id": r["user_id"],
                "email": r["email"],
                "login_count": r["login_count"],
                "last_login": r["last_login"].isoformat() if r["last_login"] else None,
            }
            for r in rows
        ]
        return {"leaders": leaders}
    except Exception as e:
        logger.error(f"activity logins failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/activity/pages")
def admin_activity_pages(
    x_admin_token: Optional[str] = Header(None),
    date_from: Optional[str] = Query(None, alias="from"),
    date_to: Optional[str] = Query(None, alias="to"),
):
    _require_admin(x_admin_token)
    start, end = _date_bounds(date_from, date_to)
    rng = (start, end)
    try:
        with get_cursor(commit=False) as cur:
            cur.execute(
                """
                SELECT page_path, COUNT(*) AS views
                FROM user_activity_events
                WHERE event_type='page_view' AND page_path IS NOT NULL
                  AND created_at >= %s AND created_at < %s
                GROUP BY page_path ORDER BY views DESC LIMIT 20
                """,
                rng,
            )
            top_pages = [{"page_path": r["page_path"], "views": r["views"]} for r in cur.fetchall()]

            cur.execute(
                """
                SELECT page_path,
                       COUNT(*) AS samples,
                       ROUND(AVG(duration_ms)) AS avg_ms
                FROM user_activity_events
                WHERE event_type='page_time' AND duration_ms IS NOT NULL
                  AND page_path IS NOT NULL
                  AND created_at >= %s AND created_at < %s
                GROUP BY page_path ORDER BY avg_ms DESC LIMIT 20
                """,
                rng,
            )
            time_pages = [
                {
                    "page_path": r["page_path"],
                    "samples": r["samples"],
                    "avg_ms": int(r["avg_ms"]) if r["avg_ms"] is not None else 0,
                }
                for r in cur.fetchall()
            ]

            cur.execute(
                """
                SELECT section,
                       COUNT(*) AS opens,
                       ROUND(AVG(NULLIF(duration_ms,0))) AS avg_ms
                FROM user_activity_events
                WHERE event_type='section_view' AND section IS NOT NULL
                  AND created_at >= %s AND created_at < %s
                GROUP BY section ORDER BY opens DESC LIMIT 30
                """,
                rng,
            )
            sections = [
                {
                    "section": r["section"],
                    "opens": r["opens"],
                    "avg_ms": int(r["avg_ms"]) if r["avg_ms"] is not None else 0,
                }
                for r in cur.fetchall()
            ]

            cur.execute(
                """
                SELECT COALESCE(section, page_path) AS label, COUNT(*) AS clicks
                FROM user_activity_events
                WHERE event_type='cta_click'
                  AND created_at >= %s AND created_at < %s
                GROUP BY label ORDER BY clicks DESC LIMIT 20
                """,
                rng,
            )
            ctas = [{"label": r["label"], "clicks": r["clicks"]} for r in cur.fetchall()]

        return {
            "top_pages": top_pages,
            "time_pages": time_pages,
            "sections": sections,
            "ctas": ctas,
        }
    except Exception as e:
        logger.error(f"activity pages failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/activity/users")
def admin_activity_users(
    x_admin_token: Optional[str] = Header(None),
    search: Optional[str] = None,
    limit: int = 50,
    date_from: Optional[str] = Query(None, alias="from"),
    date_to: Optional[str] = Query(None, alias="to"),
):
    _require_admin(x_admin_token)
    limit = max(1, min(limit, 200))
    start, end = _date_bounds(date_from, date_to)
    params = [start, end]
    where = "WHERE user_id IS NOT NULL AND created_at >= %s AND created_at < %s"
    if search:
        where += " AND LOWER(email) LIKE %s"
        params.append(f"%{search.lower()}%")
    params.append(limit)
    try:
        with get_cursor(commit=False) as cur:
            cur.execute(
                f"""
                SELECT user_id,
                       MAX(email) AS email,
                       COUNT(*) FILTER (WHERE event_type='login') AS logins,
                       COUNT(*) FILTER (WHERE event_type='page_view') AS page_views,
                       COUNT(DISTINCT section) FILTER (WHERE event_type='section_view') AS sections_used,
                       COALESCE(SUM(duration_ms) FILTER (WHERE event_type='page_time'),0) AS engaged_ms,
                       MAX(created_at) AS last_seen
                FROM user_activity_events
                {where}
                GROUP BY user_id
                ORDER BY last_seen DESC
                LIMIT %s
                """,
                tuple(params),
            )
            rows = cur.fetchall()
        users = [
            {
                "user_id": r["user_id"],
                "email": r["email"],
                "logins": r["logins"],
                "page_views": r["page_views"],
                "sections_used": r["sections_used"],
                "engaged_ms": int(r["engaged_ms"] or 0),
                "last_seen": r["last_seen"].isoformat() if r["last_seen"] else None,
            }
            for r in rows
        ]
        return {"users": users}
    except Exception as e:
        logger.error(f"activity users failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/activity/user/{user_id}")
def admin_activity_user_detail(
    user_id: int,
    x_admin_token: Optional[str] = Header(None),
):
    _require_admin(x_admin_token)
    try:
        with get_cursor(commit=False) as cur:
            cur.execute(
                """
                SELECT MAX(email) AS email,
                       COUNT(*) FILTER (WHERE event_type='login') AS logins,
                       COUNT(*) FILTER (WHERE event_type='page_view') AS page_views,
                       COALESCE(SUM(duration_ms) FILTER (WHERE event_type='page_time'),0) AS engaged_ms,
                       MIN(created_at) AS first_seen,
                       MAX(created_at) AS last_seen
                FROM user_activity_events
                WHERE user_id = %s
                """,
                (user_id,),
            )
            summary = cur.fetchone() or {}

            cur.execute(
                """
                SELECT section, COUNT(*) AS opens,
                       ROUND(AVG(NULLIF(duration_ms,0))) AS avg_ms
                FROM user_activity_events
                WHERE user_id = %s AND event_type='section_view' AND section IS NOT NULL
                GROUP BY section ORDER BY opens DESC LIMIT 30
                """,
                (user_id,),
            )
            sections = [
                {
                    "section": r["section"],
                    "opens": r["opens"],
                    "avg_ms": int(r["avg_ms"]) if r["avg_ms"] is not None else 0,
                }
                for r in cur.fetchall()
            ]

            cur.execute(
                """
                SELECT created_at FROM user_activity_events
                WHERE user_id = %s AND event_type='login'
                ORDER BY created_at DESC LIMIT 20
                """,
                (user_id,),
            )
            login_history = [
                r["created_at"].isoformat() for r in cur.fetchall() if r["created_at"]
            ]

            cur.execute(
                """
                SELECT event_type, page_path, section, duration_ms,
                       device, browser, created_at
                FROM user_activity_events
                WHERE user_id = %s
                ORDER BY id DESC LIMIT 100
                """,
                (user_id,),
            )
            timeline = [
                {
                    "event_type": r["event_type"],
                    "page_path": r["page_path"],
                    "section": r["section"],
                    "duration_ms": int(r["duration_ms"]) if r["duration_ms"] is not None else None,
                    "device": r["device"],
                    "browser": r["browser"],
                    "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                }
                for r in cur.fetchall()
            ]

        return {
            "user_id": user_id,
            "email": summary.get("email"),
            "logins": summary.get("logins") or 0,
            "page_views": summary.get("page_views") or 0,
            "engaged_ms": int(summary.get("engaged_ms") or 0),
            "first_seen": summary["first_seen"].isoformat() if summary.get("first_seen") else None,
            "last_seen": summary["last_seen"].isoformat() if summary.get("last_seen") else None,
            "sections": sections,
            "login_history": login_history,
            "timeline": timeline,
        }
    except Exception as e:
        logger.error(f"activity user detail failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


_CSV_MAX_ROWS = 50_000


@router.get("/admin/activity/export.csv")
def admin_activity_export_csv(
    x_admin_token: Optional[str] = Header(None),
    date_from: Optional[str] = Query(None, alias="from"),
    date_to: Optional[str] = Query(None, alias="to"),
):
    """Export raw activity events within a date range as CSV (admin only).
    Capped at _CSV_MAX_ROWS most-recent rows. Session tokens are never exported."""
    _require_admin(x_admin_token)
    start, end = _date_bounds(date_from, date_to)
    try:
        with get_cursor(commit=False) as cur:
            cur.execute(
                """
                SELECT created_at, user_id, email, event_type, page_path,
                       section, duration_ms, device, browser, referrer
                FROM user_activity_events
                WHERE created_at >= %s AND created_at < %s
                ORDER BY id DESC
                LIMIT %s
                """,
                (start, end, _CSV_MAX_ROWS),
            )
            rows = cur.fetchall()

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([
            "created_at", "user_id", "email", "event_type", "page_path",
            "section", "duration_ms", "device", "browser", "referrer",
        ])
        for r in rows:
            writer.writerow([
                r["created_at"].isoformat() if r["created_at"] else "",
                r["user_id"] if r["user_id"] is not None else "",
                r["email"] or "",
                r["event_type"] or "",
                r["page_path"] or "",
                r["section"] or "",
                r["duration_ms"] if r["duration_ms"] is not None else "",
                r["device"] or "",
                r["browser"] or "",
                r["referrer"] or "",
            ])

        fname = f"user-activity_{start.strftime('%Y%m%d')}_{(end - timedelta(days=1)).strftime('%Y%m%d')}.csv"
        return Response(
            content=buf.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{fname}"'},
        )
    except Exception as e:
        logger.error(f"activity export failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
