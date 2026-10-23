"""python -m src.risk.pipeline_v2_dry_run -- no writes and no paid API calls."""
from datetime import datetime
import json

from psycopg2 import connect
from psycopg2.extras import RealDictCursor
from src.db.db import get_database_url
from .pipeline_v2 import metrics, load_risk_rows, today_panel
from .pipeline_v2_core import plan, enabled, event_weight


def dry_run():
    from src.ai.ai_worker import build_input_text, SYSTEM_PROMPT, OPENAI_MODEL
    from src.ai.pipeline_v2_worker import request_bound
    if OPENAI_MODEL != "gpt-4.1-mini":
        raise RuntimeError("Update the approved V2 cost model before using another model")
    conn = connect(get_database_url(), connect_timeout=15,
                   options="-c default_transaction_read_only=on -c timezone=UTC -c statement_timeout=90000")
    try:
        conn.set_session(readonly=True, isolation_level="REPEATABLE READ")
        with conn.cursor(cursor_factory=RealDictCursor) as c:
            c.execute("SHOW transaction_read_only")
            if c.fetchone()["transaction_read_only"] != "on":
                raise RuntimeError("Dry run must be server-enforced read-only")
            now = datetime.utcnow()
            health = metrics(c, now)
            settings = plan(health)
            c.execute("""SELECT id,title,raw_text,inserted_at FROM events
                WHERE NOT processed AND ai_attempts<3 AND inserted_at<=%s
                AND (ai_impact_json->'_risk_pipeline_v2'->>'lease_until' IS NULL OR
                    (ai_impact_json->'_risk_pipeline_v2'->>'lease_until')::timestamp<%s)
                ORDER BY inserted_at DESC,id DESC LIMIT %s""", (now, now, settings["batch_size"]))
            selected = [dict(r) for r in c.fetchall()]
            reservation = 3*sum(request_bound(build_input_text(r["title"], r["raw_text"]), SYSTEM_PROMPT)
                                for r in selected)
            c.execute("""SELECT avg(octet_length(ai_impact_json::text)) AS mean_output_bytes
                FROM events WHERE processed AND ai_impact_json IS NOT NULL
                AND ai_model='gpt-4.1-mini' AND ai_processed_at>=NOW()-interval '30 days'""")
            output_bytes = c.fetchone()["mean_output_bytes"]
            expected_cost = None
            if output_bytes is not None:
                input_bytes = sum(len((SYSTEM_PROMPT+build_input_text(r["title"], r["raw_text"])).encode())+32
                                  for r in selected)
                expected_cost = (input_bytes/4*.4 + len(selected)*float(output_bytes)/4*1.6)/1e6
            c.execute("""SELECT COALESCE(sum((error::jsonb->>'charged_or_reserved_usd')::numeric),0) AS spent
                FROM job_runs WHERE job_name='risk_pipeline_v2_budget' AND index_date=%s""", (now.date(),))
            spent = float(c.fetchone()["spent"])
            risk = load_risk_rows(c, now)
            c.execute("""SELECT e.id AS event_id,e.inserted_at,e.region,e.category,
                e.severity_score AS base_severity,e.ai_impact_json
                FROM events e WHERE e.processed AND e.ai_impact_json IS NOT NULL
                AND e.inserted_at BETWEEN %s-interval '7 days' AND %s
                AND NOT EXISTS(SELECT 1 FROM risk_events r WHERE r.event_id=e.id)
                ORDER BY e.inserted_at DESC,e.id DESC""", (now, now))
            from .risk_engine import extract_avg_confidence
            ready = [dict(row) for row in c.fetchall()]
            for row in ready:
                row["ai_confidence"] = extract_avg_confidence(row["ai_impact_json"])
                row["weighted_score"] = event_weight(row, True)
                row["asset_impacts"] = row["ai_impact_json"].get("impact") or {}
            values = today_panel(risk+ready, now)
        return {"dry_run": True, "flag_currently_enabled": enabled(), "simulated_flag": True,
                "server_read_only": True, "writes": 0, "paid_calls": 0,
                "as_of_utc": now.isoformat(), "health": health, "plan": settings,
                "events_to_enrich": len(selected), "newest_first": [
                    {"id": row["id"], "inserted_at": row["inserted_at"].isoformat()} for row in selected],
                "maximum_admission_reservation_usd_including_two_retries": reservation,
                "estimated_next_batch_usd_one_call_per_event": expected_cost,
                "cost_estimate_assumptions": "1 token/4 UTF8 bytes; prior30d stored output size; no retries/markup/taxes",
                "daily_spend_or_reservations_usd": spent,
                "budget_can_admit_batch": spent+reservation <= settings["daily_budget_usd"],
                "already_enriched_fresh_events_to_score": len(ready),
                "known_inputs_only_regional_asset_output_today": values,
                "new_enrichment_effect": "UNKNOWN: exact post-enrichment values require AI outputs; no guesses or paid calls",
                "worst_case_risk_range_after_unknown_enrichment": [0, 100],
                "time_estimate_note": "Snapshot constant-capacity net estimate; oldest-first legacy backlog is not run"}
    finally:
        conn.rollback()
        conn.close()


if __name__ == "__main__":
    print(json.dumps(dry_run(), indent=2, default=str))
