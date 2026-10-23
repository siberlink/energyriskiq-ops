"""Read-only production pipeline diagnosis; never invokes enrichment or scoring."""
from datetime import datetime
import hashlib
import json
from pathlib import Path

from .data import readonly_snapshot
from .step4_data import dump
from .step5_data import LAB, PROJECT, published_digest

OUT = LAB / "step6"


def hashes():
    return {str(p.relative_to(PROJECT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((PROJECT / "src").rglob("*.py"))}


def capture():
    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT / "pipeline_snapshot.json").exists():
        return
    dump(OUT / "source_hashes_before.json", hashes())
    with readonly_snapshot() as c:
        dump(OUT / "published_before.json", published_digest(c))
        c.execute("SELECT NOW() AT TIME ZONE 'UTC' AS captured_at")
        captured = c.fetchone()["captured_at"]
        c.execute("""SELECT table_name,column_name,data_type FROM information_schema.columns
            WHERE table_schema='public' AND (table_name IN ('events','risk_events','ingestion_runs','job_runs')
            OR table_name ILIKE '%%usage%%' OR table_name ILIKE '%%ai%%log%%'
            OR table_name ILIKE '%%token%%') ORDER BY table_name,ordinal_position""")
        schema = [dict(r) for r in c.fetchall()]
        c.execute("""SELECT inserted_at::date AS day,count(*) AS inserted,
            count(*) FILTER (WHERE processed AND ai_impact_json IS NOT NULL) AS currently_enriched,
            count(*) FILTER (WHERE NOT processed AND ai_attempts<3) AS waiting_retryable,
            count(*) FILTER (WHERE NOT processed AND ai_attempts>=3) AS attempts_exhausted
            FROM events GROUP BY inserted_at::date ORDER BY day""")
        insertions = [dict(r) for r in c.fetchall()]
        c.execute("""SELECT ai_processed_at::date AS day,count(*) AS completed,
            percentile_cont(.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM
                (ai_processed_at-inserted_at))/3600) AS median_delay_hours,
            percentile_cont(.95) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM
                (ai_processed_at-inserted_at))/3600) AS p95_delay_hours
            FROM events WHERE ai_processed_at IS NOT NULL GROUP BY ai_processed_at::date ORDER BY day""")
        enrichments = [dict(r) for r in c.fetchall()]
        c.execute("""SELECT r.created_at::date AS day,count(*) AS completed,
            percentile_cont(.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM
                (r.created_at-e.inserted_at))/3600) AS median_total_delay_hours,
            percentile_cont(.95) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM
                (r.created_at-e.inserted_at))/3600) AS p95_total_delay_hours,
            percentile_cont(.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM
                (r.created_at-e.ai_processed_at))/3600) AS median_after_enrichment_hours
            FROM risk_events r JOIN events e ON e.id=r.event_id
            GROUP BY r.created_at::date ORDER BY day""")
        scoring = [dict(r) for r in c.fetchall()]
        c.execute("""SELECT count(*) AS total,
            count(*) FILTER (WHERE NOT processed) AS waiting_all,
            count(*) FILTER (WHERE NOT processed AND ai_attempts<3) AS waiting_retryable,
            count(*) FILTER (WHERE NOT processed AND ai_attempts>=3) AS attempts_exhausted,
            count(*) FILTER (WHERE processed AND ai_impact_json IS NOT NULL) AS enriched,
            count(*) FILTER (WHERE processed AND ai_impact_json IS NULL) AS processed_without_impact,
            count(*) FILTER (WHERE ai_processed_at IS NULL AND processed) AS processed_without_timestamp,
            min(inserted_at) FILTER (WHERE NOT processed) AS oldest_waiting,
            min(inserted_at) FILTER (WHERE NOT processed AND ai_attempts<3) AS oldest_retryable,
            count(*) FILTER (WHERE NOT processed AND inserted_at >= %s-interval '7 days') AS waiting_last7d
            FROM events""", (captured,))
        backlog = dict(c.fetchone())
        c.execute("""SELECT ai_model,count(*) AS completed,
            avg(octet_length(COALESCE(title,'')||COALESCE(left(raw_text,6000),''))) AS mean_input_bytes,
            avg(octet_length(COALESCE(ai_impact_json::text,''))) AS mean_output_bytes
            FROM events WHERE ai_processed_at >= %s-interval '30 days'
            GROUP BY ai_model ORDER BY count(*) DESC""", (captured,))
        costs = [dict(r) for r in c.fetchall()]
        c.execute("""SELECT count(*) AS ready_unscored FROM events e WHERE processed
            AND ai_impact_json IS NOT NULL AND NOT EXISTS
            (SELECT 1 FROM risk_events r WHERE r.event_id=e.id)""")
        ready = dict(c.fetchone())
        c.execute("""SELECT id,job_name,index_date,status,started_at,finished_at,error
            FROM job_runs WHERE started_at >= %s-interval '30 days' ORDER BY started_at""", (captured,))
        jobs = [dict(r) for r in c.fetchall()]
        c.execute("""SELECT status,count(*) AS runs,min(started_at) AS first,max(started_at) AS last,
            sum(inserted_items) AS inserted FROM ingestion_runs GROUP BY status ORDER BY status""")
        runs = [dict(r) for r in c.fetchall()]
        c.execute("""SELECT r.event_id,e.inserted_at,e.ai_processed_at,r.created_at AS scored_at,
            r.region,r.category,r.base_severity,r.ai_confidence,r.weighted_score,
            e.ai_impact_json->'impact' AS asset_impacts FROM risk_events r
            JOIN events e ON e.id=r.event_id ORDER BY e.inserted_at,r.event_id""")
        risk = [dict(r) for r in c.fetchall()]
    dump(OUT / "schema_inventory.json", schema)
    dump(OUT / "pipeline_snapshot.json", {
        "captured_at": captured, "insertions": insertions, "enrichments": enrichments,
        "scoring": scoring, "backlog": backlog, "ready_unscored": ready, "cost_samples": costs,
        "job_runs": jobs, "ingestion_runs": runs})
    dump(OUT / "scored_event_snapshot.json", risk)
    print(json.dumps({"captured_at": str(captured), "backlog": backlog,
                      "ready_unscored": ready, "cost_samples": costs}, default=str), flush=True)


if __name__ == "__main__":
    capture()
