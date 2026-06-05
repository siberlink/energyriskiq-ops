"""
Free-widget embed tracking.

Records the external pages where the free WTI and Europe Gas Storage widgets are
embedded. The free widgets are direct iframe embeds served from our own origin, so
a tiny in-iframe beacon reads ``document.referrer`` (the embedding page URL) and
POSTs it here. Results are aggregated per (widget_code, page_url) and surfaced in
the admin dashboard.
"""

import logging
from urllib.parse import urlparse
from typing import Optional

from fastapi import APIRouter, Form, Header, HTTPException, Request, Response

from src.db.db import get_cursor

logger = logging.getLogger(__name__)

router = APIRouter()

# Recognised free-widget codes -> human label for the admin UI.
WIDGET_LABELS = {
    "wti-free": "WTI Crude Oil — Free Widget",
    "gas-storage-free": "Europe Gas Storage — Free Widget",
}

# Hosts we never want to count as an external embed location.
_OWN_HOST_FRAGMENTS = (
    "energyriskiq.com",
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    ".replit.dev",
    ".replit.app",
    ".repl.co",
    ".kirk.replit",
)


def run_widget_embed_tracking_migration():
    """Create the embed-tracking table (idempotent)."""
    try:
        with get_cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS widget_embed_tracking (
                    id          SERIAL PRIMARY KEY,
                    widget_code VARCHAR(64)  NOT NULL,
                    page_url    TEXT         NOT NULL,
                    page_origin TEXT,
                    hit_count   INTEGER      NOT NULL DEFAULT 1,
                    user_agent  TEXT,
                    first_seen  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
                    last_seen   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
                    UNIQUE (widget_code, page_url)
                )
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_widget_embed_tracking_code "
                "ON widget_embed_tracking (widget_code)"
            )
    except Exception as e:
        logger.error(f"widget_embed_tracking migration error: {e}")
        raise


def _normalise_url(raw: str) -> Optional[tuple]:
    """Return (clean_url, origin) for a usable external referrer, else None."""
    if not raw:
        return None
    raw = raw.strip()
    if len(raw) > 2000:
        raw = raw[:2000]
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None
    host = parsed.netloc.lower()
    if any(frag in host for frag in _OWN_HOST_FRAGMENTS):
        return None
    # Strip query/fragment to aggregate per page, keep scheme/host/path.
    clean = f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/") or (
        f"{parsed.scheme}://{parsed.netloc}"
    )
    origin = f"{parsed.scheme}://{parsed.netloc}"
    return clean, origin


@router.post("/api/widget-embeds/track")
async def track_widget_embed(
    request: Request,
    widget: Optional[str] = Form(None),
    url: Optional[str] = Form(None),
):
    """Beacon endpoint hit from inside the free widget iframe (sendBeacon)."""
    resp_headers = {
        "Access-Control-Allow-Origin": "*",
        "Cache-Control": "no-store",
    }

    if widget not in WIDGET_LABELS:
        return Response(status_code=204, headers=resp_headers)

    # Prefer the JS-supplied referrer; fall back to the request Referer header.
    candidate = url or request.headers.get("referer") or ""
    normalised = _normalise_url(candidate)
    if not normalised:
        return Response(status_code=204, headers=resp_headers)

    clean_url, origin = normalised
    user_agent = (request.headers.get("user-agent") or "")[:500]

    try:
        with get_cursor() as cur:
            cur.execute(
                """
                INSERT INTO widget_embed_tracking
                    (widget_code, page_url, page_origin, user_agent, hit_count, first_seen, last_seen)
                VALUES (%s, %s, %s, %s, 1, NOW(), NOW())
                ON CONFLICT (widget_code, page_url) DO UPDATE
                    SET hit_count  = widget_embed_tracking.hit_count + 1,
                        last_seen   = NOW(),
                        page_origin = EXCLUDED.page_origin,
                        user_agent  = EXCLUDED.user_agent
                """,
                (widget, clean_url, origin, user_agent),
            )
    except Exception as e:
        logger.warning(f"widget embed track failed: {e}")

    return Response(status_code=204, headers=resp_headers)


@router.options("/api/widget-embeds/track")
async def track_widget_embed_options():
    return Response(
        status_code=204,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Max-Age": "86400",
        },
    )


@router.get("/admin/widget-embeds")
def admin_widget_embeds(x_admin_token: Optional[str] = Header(None)):
    """Admin-only listing of external pages embedding the free widgets."""
    from src.api.admin_routes import verify_admin_token

    verify_admin_token(x_admin_token)

    widgets = []
    total_pages = 0
    total_hits = 0
    try:
        with get_cursor(commit=False) as cur:
            for code, label in WIDGET_LABELS.items():
                cur.execute(
                    """
                    SELECT page_url, page_origin, hit_count,
                           first_seen, last_seen
                    FROM widget_embed_tracking
                    WHERE widget_code = %s
                    ORDER BY last_seen DESC
                    """,
                    (code,),
                )
                rows = cur.fetchall()
                pages = []
                widget_hits = 0
                for r in rows:
                    widget_hits += r["hit_count"] or 0
                    pages.append(
                        {
                            "page_url": r["page_url"],
                            "page_origin": r["page_origin"],
                            "hit_count": r["hit_count"],
                            "first_seen": r["first_seen"].isoformat()
                            if r["first_seen"]
                            else None,
                            "last_seen": r["last_seen"].isoformat()
                            if r["last_seen"]
                            else None,
                        }
                    )
                total_pages += len(pages)
                total_hits += widget_hits
                widgets.append(
                    {
                        "code": code,
                        "label": label,
                        "unique_pages": len(pages),
                        "total_hits": widget_hits,
                        "pages": pages,
                    }
                )
    except Exception as e:
        logger.error(f"admin widget-embeds query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "widgets": widgets,
        "summary": {
            "total_unique_pages": total_pages,
            "total_hits": total_hits,
        },
    }
