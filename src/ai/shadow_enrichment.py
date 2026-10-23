"""Shadow-approved enrichment: only retryable events in the trailing seven days."""
from datetime import datetime, timedelta
import json
import logging
import time

from src.db.db import get_cursor
from src.risk.pipeline_v2_core import mode, plan
from src.risk.pipeline_v2 import metrics, internal_alert
from .pipeline_v2_worker import rate_slot
from .shadow_budget import BudgetStopped, request

logger = logging.getLogger(__name__)


def run(batch_size=None):
    if mode() != "shadow":
        raise RuntimeError("Shadow enrichment requires explicit shadow mode")
    from . import ai_worker as legacy
    if legacy.OPENAI_MODEL != "gpt-4.1-mini":
        raise RuntimeError("Only approved enrichment model gpt-4.1-mini is allowed")
    now = datetime.utcnow()
    with get_cursor() as c:
        health = metrics(c, now)
    settings = plan(health)
    target = min(batch_size or settings["batch_size"], settings["retry_slot_capacity"])
    client = legacy.get_openai_client().with_options(timeout=60, max_retries=0)
    deadline = time.monotonic() + settings["runtime_seconds"]
    success = failed = 0
    internal_alert(health)
    for _ in range(target):
        if time.monotonic() + 65 > deadline:
            break
        with get_cursor() as c:
            c.execute("""SELECT id,title,raw_text,ai_attempts FROM events
                WHERE NOT processed AND ai_attempts<3
                AND inserted_at BETWEEN %s-interval '7 days' AND %s
                AND COALESCE(ai_impact_json->'_risk_pipeline_v2'->>'status','')<>'skipped_stale'
                AND (ai_impact_json->'_risk_pipeline_v2'->>'lease_until' IS NULL OR
                     (ai_impact_json->'_risk_pipeline_v2'->>'lease_until')::timestamp<%s)
                ORDER BY inserted_at DESC,id DESC LIMIT 1 FOR UPDATE SKIP LOCKED""",
                      (now, now, datetime.utcnow()))
            row = c.fetchone()
            if not row:
                break
            c.execute("""UPDATE events SET ai_impact_json=jsonb_set(
                COALESCE(ai_impact_json,'{}'::jsonb),'{_risk_pipeline_v2}',%s::jsonb,true)
                WHERE id=%s""",
                      (json.dumps({"lease_until": (datetime.utcnow()+timedelta(minutes=5)).isoformat(),
                                   "mode": "shadow", "status": "leased"}), row["id"]))
        try:
            rate_slot(settings["max_rpm"], deadline)
            raw, usage, cost, finish = request(
                client, "gpt-4.1-mini",
                [{"role": "system", "content": legacy.SYSTEM_PROMPT},
                 {"role": "user", "content": "Analyze this news event:\n\n" +
                  legacy.build_input_text(row["title"], row["raw_text"])}],
                2000, "enrichment", row["id"])
            with get_cursor() as c:
                c.execute("UPDATE events SET ai_attempts=ai_attempts+1 WHERE id=%s", (row["id"],))
            ok, result, error = legacy.parse_ai_response(raw)
            if not ok or finish != "stop":
                raise ValueError("Invalid or incomplete enrichment response")
            result["_risk_pipeline_v2"] = {
                "mode": "shadow", "status": "enriched", "usage": usage,
                "observed_or_upper_cost_usd": cost,
                "lease_until": datetime.utcnow().isoformat()}
            legacy.save_ai_result(row["id"], result["summary"], result, "gpt-4.1-mini")
            success += 1
        except BudgetStopped as exc:
            _release(row["id"], "budget_stopped")
            _admin_failure(str(exc))
            break
        except Exception as exc:
            # Count failed paid attempts once, including network/provider failures.
            with get_cursor() as c:
                c.execute("UPDATE events SET ai_attempts=GREATEST(ai_attempts,%s) WHERE id=%s",
                          (row["ai_attempts"]+1, row["id"]))
            _release(row["id"], "retryable_error")
            logger.warning("Shadow enrichment failed event_id=%s type=%s", row["id"], type(exc).__name__)
            failed += 1
    logger.info("Shadow enrichment completed success=%s failures=%s target=%s", success, failed, target)
    return success, failed


def _release(event_id, status):
    with get_cursor() as c:
        c.execute("""UPDATE events SET ai_impact_json=jsonb_set(
            COALESCE(ai_impact_json,'{}'::jsonb),'{_risk_pipeline_v2}',%s::jsonb,true)
            WHERE id=%s AND NOT processed""",
                  (json.dumps({"lease_until": datetime.utcnow().isoformat(), "mode": "shadow",
                               "status": status}), event_id))


def _admin_failure(message):
    from src.geri.job_health import start_run, finish_run
    now = datetime.utcnow()
    id_ = start_run(now.date(), "risk_pipeline_v2_admin_alert",
                    f"shadow-stop:{now:%Y-%m-%d-%H}")
    if id_:
        finish_run(id_, "error", message)


def mark_stale():
    """Monitoring flag only: do not delete events or touch exhausted attempts."""
    with get_cursor() as c:
        # jsonb_set cannot create a missing intermediate object: merge explicitly.
        c.execute("""UPDATE events SET ai_impact_json=
            COALESCE(ai_impact_json,'{}'::jsonb) || jsonb_build_object('_risk_pipeline_v2',
              COALESCE(ai_impact_json->'_risk_pipeline_v2','{}'::jsonb) ||
              '{"status":"skipped_stale","mode":"shadow"}'::jsonb)
            WHERE NOT processed AND ai_attempts<3 AND inserted_at<NOW()-interval '30 days'
            AND COALESCE(ai_impact_json->'_risk_pipeline_v2'->>'status','')<>'skipped_stale'""")
        return c.rowcount
