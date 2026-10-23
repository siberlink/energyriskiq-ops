"""GERI run records and watchdog. Internal ops only: no email/Telegram imports."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from src.db.db import get_cursor
from src.geri.health import utc_today

logger = logging.getLogger(__name__)


def start_run(day, name="geri_daily", key=None):
    with get_cursor() as cursor:
        cursor.execute(
            """INSERT INTO job_runs(job_name,index_date,status,run_key)
               VALUES (%s,%s,'running',%s) ON CONFLICT(run_key) DO NOTHING RETURNING id""",
            (name, day, key))
        row = cursor.fetchone()
        return row["id"] if row else None


def finish_run(run_id, status, error=None):
    if run_id:
        with get_cursor() as cursor:
            cursor.execute("UPDATE job_runs SET finished_at=NOW(),status=%s,error=%s WHERE id=%s",
                           (status, error, run_id))


def record_existing_skip(day):
    """Log an existing-publication job without recomputing its score."""
    run_id = start_run(day)
    try:
        from src.geri.health import record_health
        record_health(day)
        finish_run(run_id, "skipped")
    except Exception as error:
        finish_run(run_id, "error", str(error))
        raise


def watchdog(now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Watchdog requires a timezone-aware timestamp.")
    now = now.astimezone(timezone.utc)
    target = now.date() - timedelta(days=1)
    from src.geri.types import INDEX_ID
    with get_cursor() as cursor:
        cursor.execute("SELECT 1 FROM intel_indices_daily WHERE index_id=%s AND date=%s",
                       (INDEX_ID, target))
        if cursor.fetchone():
            return "present"
    if (now.hour, now.minute) < (2, 30):
        return "before_deadline"
    run_id = start_run(target, "geri_daily_watchdog_retry", f"geri-retry:{target}")
    if run_id:
        logger.error("GERI Daily missing at 02:30 UTC for %s; retrying once", target)
        try:
            from src.geri.service import compute_geri_for_date
            compute_geri_for_date(target)
            with get_cursor() as cursor:
                cursor.execute("SELECT 1 FROM intel_indices_daily WHERE index_id=%s AND date=%s",
                               (INDEX_ID, target))
                present = cursor.fetchone() is not None
            finish_run(run_id, "success" if present else "error",
                       None if present else "Retry produced no published row")
            if present:
                return "recovered"
        except Exception as error:
            logger.exception("GERI watchdog retry failed")
            finish_run(run_id, "error", str(error))
    if now.hour >= 4:
        alert = start_run(target, "geri_daily_admin_alert", f"geri-admin-alert:{target}")
        if alert:
            message = f"GERI Daily for {target} is still missing after 04:00 UTC."
            finish_run(alert, "error", message)
            # Existing operations channel: persisted operational state + app
            # error logs and /ops/status. No customer delivery is involved.
            logger.critical("INTERNAL ADMIN ALERT: %s", message)
        return "admin_alert"
    return "retry_checked"


async def periodic_watchdog():
    while True:
        try:
            await asyncio.to_thread(watchdog)
        except Exception:
            logger.exception("GERI watchdog failed")
        await asyncio.sleep(60)
