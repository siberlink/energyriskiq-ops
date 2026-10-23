"""Complete stage-unit accounting; distinguish absent instrumentation from zero delay."""
from collections import defaultdict
import csv
from datetime import datetime
import json
import math

from .data import readonly_snapshot
from .step4_data import dump
from .step4_pairs import write_csv
from .step6_data import OUT


def percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered)-1)*fraction
    lower, upper = math.floor(index), math.ceil(index)
    return ordered[lower]+(ordered[upper]-ordered[lower])*(index-lower)


def build():
    snapshot = json.loads((OUT / "pipeline_snapshot.json").read_text())
    captured = datetime.fromisoformat(snapshot["captured_at"])
    path = OUT / "index_stage_daily_counts.json"
    if not path.exists():
        aggregate = {}
        with readonly_snapshot() as c:
            for table in ("risk_indices", "asset_risk"):
                c.execute(f"""SELECT calculated_at::date AS day,count(*) AS completed_snapshot_rows
                    FROM {table} WHERE calculated_at >= '2026-01-14' AND calculated_at<=%s
                    GROUP BY 1 ORDER BY 1""", (captured,))
                aggregate[table] = [dict(row) for row in c.fetchall()]
        dump(path, aggregate)
    aggregate = json.loads(path.read_text())
    counts = {table: {r["day"]: r["completed_snapshot_rows"] for r in values}
              for table, values in aggregate.items()}
    scoring_delays = defaultdict(list)
    for event in json.loads((OUT / "scored_event_snapshot.json").read_text()):
        scored_at = event.get("scored_at", event.get("created_at"))
        ai_at = event.get("ai_processed_at")
        if scored_at and ai_at:
            scoring_delays[scored_at[:10]].append(
                (datetime.fromisoformat(scored_at)-datetime.fromisoformat(ai_at)).total_seconds()/3600)
    with (OUT / "daily_pipeline_queues_and_delays.csv").open() as stream:
        daily = list(csv.DictReader(stream))
    long = []
    for row in daily:
        day = row["date"]
        post = scoring_delays[day]
        row["p95_post_enrichment_scoring_hours"] = percentile(post, .95)
        for stage, incoming, completed, queue, median, p95, input_unit, output_unit, note in (
            ("raw_event_ingestion", row["events_inserted_completed"], row["events_inserted_completed"], 0,
             None, None, "visible inserted events", "persisted events",
             "Only committed inserts observable; external fetch entry time/queue not instrumented"),
            ("processed_flag_and_AI_enrichment", row["enrichment_entered"], row["processed_and_enrichment_completed"],
             row["enrichment_queue_eod_reconstructed"], row["median_enrichment_delay_hours"],
             row["p95_enrichment_delay_hours"], "events", "events",
             "processed=true is the same atomic AI completion, not a separate stage"),
            ("risk_event_scoring", row["risk_scoring_entered"], row["risk_scoring_completed"],
             row["risk_queue_eod_reconstructed"], percentile(post, .5), percentile(post, .95),
             "AI-enriched events", "risk_events",
             "Delay is scoring minus AI completion; total insertion-to-scoring separately reported"),
            ("regional_index_aggregation", row["risk_scoring_completed"], counts["risk_indices"].get(day, 0),
             None, None, None, "new risk events", "regional snapshot rows",
             "Many-to-many rolling aggregate; no per-snapshot stage-entry/start timestamp or event queue audit"),
            ("Europe_asset_aggregation", row["risk_scoring_completed"], counts["asset_risk"].get(day, 0),
             None, None, None, "new risk events (all regions; Europe subset consumed)", "asset snapshot rows",
             "Many-to-many rolling aggregate; no per-snapshot processing-start/queue audit"),
        ):
            long.append({"date": day, "stage": stage, "items_entering": incoming,
                         "items_completed": completed, "input_unit": input_unit, "output_unit": output_unit,
                         "queue_eod": queue, "median_stage_delay_hours": median, "p95_stage_delay_hours": p95,
                         "partial_current_day": row["partial_current_day"], "instrumentation_limit": note})
    write_csv(OUT / "daily_pipeline_queues_and_delays.csv", daily)
    write_csv(OUT / "daily_pipeline_all_stages.csv", long)
    assert len(long) == len(daily)*5
    assert sum(int(r["risk_scoring_completed"]) for r in daily) > 0
    return len(long)
