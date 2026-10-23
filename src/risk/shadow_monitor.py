"""Read-only operational snapshots plus durable 24h/72h checkpoints."""
from datetime import datetime, timezone
import json

from src.db.db import get_cursor


def snapshot():
    with get_cursor(commit=False) as c:
        c.execute("SELECT to_regclass('public.risk_pipeline_v2_control') AS installed")
        if not c.fetchone()["installed"]:
            return {"installed": False}
        c.execute("SELECT * FROM risk_pipeline_v2_control WHERE singleton")
        row = c.fetchone()
        if not row:
            return {"installed": True, "activated": False}
        control = dict(row)
        c.execute("""SELECT
            count(*) FILTER(WHERE NOT processed AND ai_attempts<3 AND inserted_at>=NOW()-interval '7 days') AS fresh_queue,
            count(*) FILTER(WHERE NOT processed AND ai_attempts<3 AND
              COALESCE(ai_impact_json->'_risk_pipeline_v2'->>'status','')<>'skipped_stale') AS total_queue,
            count(*) FILTER(WHERE NOT processed AND ai_attempts<3 AND
              ai_impact_json->'_risk_pipeline_v2'->>'status'='skipped_stale') AS skipped_stale,
            count(*) FILTER(WHERE NOT processed AND ai_attempts>=3) AS attempts_exhausted,
            EXTRACT(EPOCH FROM (NOW()-min(inserted_at) FILTER(WHERE NOT processed AND ai_attempts<3
              AND inserted_at>=NOW()-interval '7 days')))/3600 AS oldest_fresh_waiting_hours,
            percentile_cont(.5) WITHIN GROUP(ORDER BY EXTRACT(EPOCH FROM(ai_processed_at-inserted_at))/3600)
              FILTER(WHERE ai_processed_at>=%s AND inserted_at>=%s) AS median_new_event_delay_hours,
            count(*) FILTER(WHERE ai_processed_at>=%s AND ai_model='gpt-4.1-mini'
              AND ai_impact_json->'_risk_pipeline_v2'->>'mode'='shadow') AS enriched_since_activation
            FROM events""", (control["activated_at"], control["activated_at"], control["activated_at"]))
        queue = dict(c.fetchone())
        c.execute("""SELECT budget_date,purpose,count(*) AS requests,
            count(*) FILTER(WHERE status='error') AS failed_requests,
            COALESCE(sum(charged_usd),0) AS charged_or_upper_usd,
            COALESCE(sum(reserved_usd) FILTER(WHERE status='reserved'),0) AS reserved_usd,
            COALESCE(sum((usage->>'prompt_tokens')::bigint),0) AS prompt_tokens,
            COALESCE(sum((usage->>'completion_tokens')::bigint),0) AS completion_tokens,
            COALESCE(sum(charged_usd) FILTER(WHERE usage IS NOT NULL),0) AS actual_usage_usd,
            count(*) FILTER(WHERE usage IS NULL AND charged_usd>0) AS ambiguous_charges
            FROM risk_pipeline_v2_usage GROUP BY budget_date,purpose ORDER BY budget_date,purpose""")
        usage = [dict(r) for r in c.fetchall()]
        c.execute("""SELECT date_trunc('hour',requested_at) AS hour,
            count(*) AS requests,count(*) FILTER(WHERE status='completed') AS completed_requests,
            count(*) FILTER(WHERE status='error') AS failures
            FROM risk_pipeline_v2_usage WHERE purpose='enrichment'
            GROUP BY 1 ORDER BY 1""")
        hourly = [dict(r) for r in c.fetchall()]
        c.execute("""SELECT payload FROM risk_pipeline_v2_monitor
            WHERE checkpoint='risk_panel' ORDER BY observed_at DESC LIMIT 1""")
        latest = c.fetchone()
        c.execute("""SELECT index_date,variant,value,computed_at FROM geri_shadow_daily
            WHERE COALESCE((inputs->>'seed')::boolean,false)=false
            AND index_date=(SELECT max(index_date) FROM geri_shadow_daily
                WHERE COALESCE((inputs->>'seed')::boolean,false)=false)
            ORDER BY variant""")
        values = [dict(r) for r in c.fetchall()]
    now = datetime.now(timezone.utc)
    elapsed = max((now-control["activated_at"]).total_seconds()/3600, 1e-8)
    today = str(now.date())
    from src.ai.shadow_budget import limit
    today_committed = sum(float(r["charged_or_upper_usd"])+float(r["reserved_usd"])
                          for r in usage if str(r["budget_date"]) == today)
    return {"installed": True, "activated": True, "mode": control["mode"],
            "activated_at": control["activated_at"], "start_date": control["start_date"],
            "runner": control["runner"], "elapsed_hours": elapsed,
            **queue, "enriched_per_hour": queue["enriched_since_activation"]/elapsed,
            "usage": usage, "hourly": hourly,
            "today_committed_usd": today_committed, "daily_budget_usd": limit(),
            "latest_saturation": latest["payload"]["saturation"] if latest else None,
            "latest_shadow_geri": values,
            "checkpoint_24h": "due" if elapsed >= 24 else "not_due",
            "checkpoint_72h": "due" if elapsed >= 72 else "not_due"}


def capture():
    value = snapshot()
    if not value.get("activated"):
        return value
    with get_cursor() as c:
        for checkpoint, hours in (("24h", 24), ("72h", 72)):
            if value["elapsed_hours"] < hours:
                continue
            # First observation after the due time is immutable; not an invented
            # exactly-on-the-hour measurement. observed_at records the real time.
            c.execute("""INSERT INTO risk_pipeline_v2_monitor(checkpoint,payload)
                SELECT %s,%s::jsonb WHERE NOT EXISTS
                (SELECT 1 FROM risk_pipeline_v2_monitor WHERE checkpoint=%s)""",
                      (checkpoint, json.dumps(value, default=str), checkpoint))
    return value
