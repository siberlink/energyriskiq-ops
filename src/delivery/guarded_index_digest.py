"""Closed-UTC-day index delivery. No provider refreshes and no correction sends.

Both repositories ship this module unchanged. Legacy rendering/plan preferences
stay in pro_delivery_worker; all delivery entry points use this boundary.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, datetime, timedelta, timezone
import html
import json
import math
import os
from pathlib import Path
import time
from uuid import uuid4

from src.db.db import get_cursor
from src.geri.model_selection import published_model

INDEX_NAMES = {"geri": "GERI", "eeri": "EERI", "egsi": "EGSI-M"}
_ORIGIN = ContextVar("index_digest_origin", default=None)


@contextmanager
def delivery_origin(caller):
    token = _ORIGIN.set(caller)
    try:
        yield
    finally:
        _ORIGIN.reset(token)


def closed_day():
    return datetime.now(timezone.utc).date() - timedelta(days=1)


def read_snapshot(target, methodology):
    """All three observations come from one read-only repeatable-read snapshot."""
    table = ("public.intel_indices_daily_v12" if methodology == "v1.2"
             else "public.intel_indices_daily")
    quality = (" AND smoothing_state->>'data_quality' <> 'UNAVAILABLE'"
               if methodology == "v1.2" else "")
    queries = {
        "geri": (
            "SELECT date,value,band,trend_1d,trend_7d,components,interpretation,model_version "
            f"FROM {table} WHERE index_id='global:geo_energy_risk' AND date=%s" + quality),
        "eeri": (
            "SELECT date,value,band,trend_1d,trend_7d,components,drivers,interpretation,model_version "
            "FROM reri_indices_daily WHERE index_id='europe:eeri' AND date=%s "
            "AND model_version='eeri_ttf_v3'"),
        "egsi": (
            "SELECT index_date AS date,index_value AS value,band,trend_1d,trend_7d,"
            "components_json AS components,interpretation FROM egsi_m_daily "
            "WHERE index_date=%s"),
    }
    observations = {}
    with get_cursor(commit=False) as cur:
        cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        for name, sql in queries.items():
            cur.execute(sql, (target,))
            raw = cur.fetchone()
            row = dict(raw) if raw else None
            if row:
                for field in ("components", "drivers"):
                    if isinstance(row.get(field), str):
                        row[field] = json.loads(row[field])
                valid = (str(row.get("date")) == str(target)
                         and row.get("value") is not None
                         and math.isfinite(float(row["value"]))
                         and not row.get("stale")
                         and not (row.get("components") or {}).get("stale"))
                if valid:
                    row["stale"] = False
                else:
                    row = None
            observations[name] = row
    return observations


def wait_for_snapshot(target, methodology, *, reader=None, sleep=None,
                      clock=None, timeout=120):
    """Fresh transactions per poll; never wait on an unchanged MVCC snapshot."""
    reader, sleep, clock = reader or read_snapshot, sleep or time.sleep, clock or time.monotonic
    deadline = clock() + timeout
    while True:
        snapshot = reader(target, methodology)
        if all(snapshot.get(name) is not None for name in INDEX_NAMES):
            return snapshot
        remaining = deadline - clock()
        if remaining <= 0:
            return snapshot
        sleep(min(10, remaining))


def provenance(caller):
    build = {}
    path = Path(__file__).parents[1] / "ingest" / "storage_build_info.json"
    if path.exists():
        build = json.loads(path.read_text())
    return {
        "caller": _ORIGIN.get() or caller,
        "job": os.getenv("CLOUD_RUN_JOB", "website"),
        "execution_id": os.getenv("CLOUD_RUN_EXECUTION", "unavailable"),
        "image": os.getenv("JOB_IMAGE") or build.get("image", "unavailable"),
        "commit": os.getenv("COMMIT_SHA") or build.get("commit", "unavailable"),
    }


def append_attempt(attempt_id, user_id, channel, outcome, metadata):
    """INSERT only. Missing audit migration fails closed before any transport."""
    with get_cursor(commit=True) as cur:
        cur.execute("""
            INSERT INTO index_digest_attempts
              (attempt_id,user_id,channel,outcome,target_date,metadata)
            VALUES (%s,%s,%s,%s,%s,%s::jsonb)
        """, (str(attempt_id), user_id, channel, outcome, metadata["target_date"],
              json.dumps(metadata, default=str, sort_keys=True)))


def send_reserved(user_id, channel, target):
    """An uncertain transport/ledger failure must not trigger a duplicate send."""
    with get_cursor(commit=False) as cur:
        cur.execute("""
            SELECT 1 FROM index_digest_attempts s
            WHERE s.user_id=%s AND s.channel=%s AND s.target_date=%s
              AND s.outcome='started' AND s.metadata->>'send'='true'
              AND NOT EXISTS (
                SELECT 1 FROM index_digest_attempts f
                WHERE f.attempt_id=s.attempt_id
                  AND f.metadata->>'delivered'='false'
                  AND f.outcome IN ('failed','skipped'))
            LIMIT 1
        """, (user_id, channel, target))
        return cur.fetchone() is not None


@contextmanager
def recipient_lock(user_id, channel, target):
    """Serialize overlapping website/worker attempts, including the sent check."""
    with get_cursor(commit=True) as cur:
        cur.execute("""
            SELECT pg_try_advisory_xact_lock(hashtext(%s),hashtext(%s)) AS acquired
        """, (f"index_digest:{user_id}:{channel}", str(target)))
        yield bool(cur.fetchone()["acquired"])


def snapshot_audit(snapshot, target, methodology, caller):
    observations = {
        ("egsi_m" if name == "egsi" else name): {"date": str(row["date"]) if row else None,
               "value": float(row["value"]) if row else None,
               "model": row.get("model_version") if row else None,
               "stale": row is None}
        for name, row in snapshot.items()
    }
    return {
        **provenance(caller), "run_id": str(uuid4()), "target_date": str(target),
        "methodology": methodology, "index_observations": observations,
        "snapshot_read_at": datetime.now(timezone.utc).isoformat(),
        "freshness_pending": any(snapshot.get(n) is None for n in INDEX_NAMES),
        "missing_indices": [n for n in INDEX_NAMES if snapshot.get(n) is None],
    }


def deterministic_text(snapshot, target):
    lines = [f"Stored observations for {target} (UTC closed day)."]
    for name, title in INDEX_NAMES.items():
        row = snapshot.get(name)
        lines.append(f"{title}: {row['value']} ({target})." if row else
                     f"{title}: pending — {target} observation not yet available.")
    return "\n".join(lines)


def render(worker, snapshot, target, methodology, plan, enabled, narrative=None, assets=None):
    """Never pass fabricated/older values to an existing renderer."""
    geri, eeri, egsi = (snapshot.get(k) for k in INDEX_NAMES)
    text = narrative if "daily_digest" in enabled else None
    subject, body = worker.build_full_email(
        geri, eeri, assets or {}, plan, text, egsi=egsi, enabled_indices=enabled)
    telegram = worker.build_full_telegram(
        geri, eeri, plan, text, egsi=egsi, enabled_indices=enabled)
    pending = [
        f"{title}: pending — {target} observation not yet available."
        for name, title in INDEX_NAMES.items()
        if snapshot.get(name) is None and (name in enabled or "daily_digest" in enabled)
    ]
    from src.geri.narrative_context import INACTIVE_NOTE
    note = f"Observation date: {target} UTC. GERI methodology {methodology}."
    if methodology == "v1.2":
        note += " " + INACTIVE_NOTE.replace(
            "Describe them as inactive, not as active risk drivers.",
            "These components are currently inactive, not active risk drivers.")
    additions = "\n".join([note] + pending)
    body = body.replace("</body>", "<p>" + html.escape(additions).replace(
        "\n", "<br>") + "</p></body>")
    telegram += "\n" + additions
    if not geri:
        subject = f"[EnergyRiskIQ] Daily Intelligence — {target}; GERI pending"
    return subject, body, telegram


def deliver(worker, *, send=False, caller="manual", ai_section_missing=False):
    """One digest per recipient/channel/UTC day; no correction/resend mechanism."""
    methodology, target = published_model(), closed_day()
    # Manual renders are immediate and deterministic: no wait, AI or sends.
    snapshot = (wait_for_snapshot(target, methodology) if send
                else read_snapshot(target, methodology))
    audit = snapshot_audit(snapshot, target, methodology, caller)
    stats = {"users_processed": 0, "emails_sent": 0, "emails_skipped": 0,
             "telegrams_sent": 0, "telegrams_skipped": 0, "errors": [],
             "ai_section_missing": bool(ai_section_missing),
             "freshness_pending": audit["freshness_pending"],
             "target_date": str(target), "methodology": methodology,
             "index_observations": audit["index_observations"], "renders": []}
    append_attempt(uuid4(), None, "run", "started", {**audit, "send": send})
    users = worker.get_all_users_with_plans()
    prefs = worker.get_user_delivery_preferences([u["id"] for u in users]) if users else {}
    assets = worker.get_asset_snapshots() if users else {}
    digest_cache = {}
    for user in users:
        uid, plan = user["id"], user.get("plan", "free")
        user_prefs = prefs.get(uid, {})
        stats["users_processed"] += 1
        opted_in = False
        for channel in ("email", "telegram"):
            enabled = [name for name in (*INDEX_NAMES, "daily_digest")
                       if user_prefs.get(name, {}).get(channel, False)]
            if not enabled:
                continue
            opted_in = True
            attempt = uuid4()
            metadata = {**audit, "plan": plan, "enabled_indices": enabled,
                        "ai_section_missing": bool(ai_section_missing)}
            prefix = "emails" if channel == "email" else "telegrams"

            def record(outcome, **details):
                append_attempt(attempt, uid, channel, outcome, {**metadata, **details})

            # The existing plan rule remains: free accounts have Telegram only.
            if channel == "email" and plan not in worker.PLAN_LEVELS:
                record("skipped", reason="unknown_plan")
                stats[prefix + "_skipped"] += 1
                continue
            if channel == "email" and plan == "free":
                record("skipped", reason="plan_not_entitled")
                stats[prefix + "_skipped"] += 1
                continue
            destination = user.get("email" if channel == "email" else "telegram_chat_id")
            if not destination:
                record("skipped", reason="missing_destination")
                stats[prefix + "_skipped"] += 1
                continue
            # Avoid AI work for a channel whose transport is deliberately paused.
            from src.alerts import channel_adapters
            if send and channel == "email" and not channel_adapters.ALERTS_EMAIL_ENABLED:
                record("skipped", reason="email_disabled")
                stats[prefix + "_skipped"] += 1
                continue
            try:
                with recipient_lock(uid, channel, target) if send else _render_lock() as acquired:
                    if not acquired:
                        record("skipped", reason="recipient_busy")
                        stats[prefix + "_skipped"] += 1
                        continue
                    if send and (worker.has_been_delivered_today(uid, channel, target)
                                 or send_reserved(uid, channel, target)):
                        record("skipped", reason="already_sent")
                        stats[prefix + "_skipped"] += 1
                        continue
                    narrative = None
                    if "daily_digest" in enabled:
                        if plan not in digest_cache:
                            text = None
                            if send and not audit["freshness_pending"]:
                                # Only the pinned exact-day rows enter the model.
                                text = worker.generate_ai_digest_for_plan(
                                    plan, snapshot["geri"], snapshot["eeri"], assets)
                            digest_cache[plan] = (text or deterministic_text(snapshot, target),
                                                  not bool(text))
                        narrative, fallback = digest_cache[plan]
                        metadata["ai_section_missing"] |= fallback
                    geri = snapshot.get("geri") or {}
                    metadata["ai_section_missing"] |= bool(
                        (geri.get("components") or {}).get("ai_section_missing"))
                    stats["ai_section_missing"] |= metadata["ai_section_missing"]
                    subject, body, telegram = render(
                        worker, snapshot, target, methodology, plan, enabled, narrative, assets)
                    if not send:
                        stats["renders"].append({"user_id": uid, "channel": channel,
                                                 "subject": subject,
                                                 "body": body if channel == "email" else telegram})
                        record("rendered", send=False)
                        continue
                    record("started", send=True)
                    result = (worker.send_email_v2(destination, subject, body)
                              if channel == "email" else
                              worker.send_telegram_v2(destination, telegram))
                    if result.success:
                        # Save sent state for pending content too: no later resend.
                        worker.record_index_delivery(
                            uid, channel, "sent", index_date=target,
                            ai_section_missing=metadata["ai_section_missing"],
                            geri_value=audit["index_observations"]["geri"]["value"],
                            methodology=methodology,
                            index_observations=audit["index_observations"])
                        record("pending" if audit["freshness_pending"] else "sent",
                               delivered=True)
                        stats[prefix + "_sent"] += 1
                    elif result.should_skip:
                        record("skipped", reason=result.skip_reason, delivered=False)
                        stats[prefix + "_skipped"] += 1
                    else:
                        record("failed", reason=result.error, delivered=False)
                        stats["errors"].append(f"{uid}:{channel}:transport_failed")
            except Exception as exc:
                # If auditing itself fails, let it fail rather than send unaudited.
                record("failed", reason=type(exc).__name__)
                raise
        if not opted_in:
            append_attempt(uuid4(), uid, "none", "skipped",
                           {**audit, "reason": "not_opted_in"})
    append_attempt(uuid4(), None, "run",
                   "failed" if stats["errors"] else "pending" if audit["freshness_pending"] else
                   "rendered" if not send else "completed",
                   {**audit, "send": send, "ai_section_missing": stats["ai_section_missing"]})
    return stats


@contextmanager
def _render_lock():
    yield True
