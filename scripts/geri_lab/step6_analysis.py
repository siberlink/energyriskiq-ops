"""Frozen-cohort queue diagnosis, timely counterfactual, coverage-restricted validation."""
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import date, datetime, timedelta
import json
import csv
from statistics import mean

from src.risk.pipeline_v2_core import panels, plan
from src.ai.ai_worker import SYSTEM_PROMPT
from .bootstrap import compare_scorecards, markdown as bootstrap_markdown
from .replay import replay, write_series
from .scorecard import scorecard, write_scorecard, partial_correlation
from .step4_data import dump
from .step4_pairs import write_csv
from .step4_report import split_market
from .step5_data import START, END, LAB, cached_labels, PROJECT
from .step5_run import replay_inputs, pillar_exports
from .step6_data import OUT, capture
from .variants import get_variant

NAMES = ("integrity_v1", "pillars_continuous_timely", "pillars_alerts_timely",
         "pillars_continuous_timely_rel41")


def dates(end):
    return [START+timedelta(days=i) for i in range((end-START).days+1)]


def diagnosis():
    value = json.loads((OUT / "pipeline_snapshot.json").read_text())
    # Old operational error strings are not needed and may contain URLs: do not export them.
    for row in value["job_runs"]:
        row.pop("error", None)
        row.pop("has_error", None)
        row["error_detail_included"] = False
    dump(OUT / "pipeline_snapshot.json", value)
    captured = datetime.fromisoformat(value["captured_at"])
    inserted = {r["day"]: r for r in value["insertions"]}
    enriched = {r["day"]: r for r in value["enrichments"]}
    scored = {r["day"]: r for r in value["scoring"]}
    total_in = sum(r["inserted"] for r in value["insertions"] if r["day"] < START.isoformat())
    total_ai = sum(r["completed"] for r in value["enrichments"] if r["day"] < START.isoformat())
    total_risk = sum(r["completed"] for r in value["scoring"] if r["day"] < START.isoformat())
    rows = []
    for day in dates(captured.date()):
        key = day.isoformat()
        incoming, completed, risk = inserted.get(key, {}), enriched.get(key, {}), scored.get(key, {})
        n_in, n_ai, n_risk = incoming.get("inserted", 0), completed.get("completed", 0), risk.get("completed", 0)
        total_in += n_in
        total_ai += n_ai
        total_risk += n_risk
        rows.append({"date": key, "partial_current_day": day == captured.date(),
                     "events_inserted_completed": n_in, "enrichment_entered": n_in,
                     "processed_and_enrichment_completed": n_ai, "enrichment_queue_eod_reconstructed": total_in-total_ai,
                     "retryable_queue_historical": None,
                     "median_enrichment_delay_hours": completed.get("median_delay_hours"),
                     "p95_enrichment_delay_hours": completed.get("p95_delay_hours"),
                     "risk_scoring_entered": n_ai, "risk_scoring_completed": n_risk,
                     "risk_queue_eod_reconstructed": total_ai-total_risk,
                     "median_total_scoring_delay_hours": risk.get("median_total_delay_hours"),
                     "p95_total_scoring_delay_hours": risk.get("p95_total_delay_hours"),
                     "median_post_enrichment_scoring_hours": risk.get("median_after_enrichment_hours"),
                     "note": "Surviving-row cohort reconstruction; retry/exhaustion transitions were not timestamped"})
    write_csv(OUT / "daily_pipeline_queues_and_delays.csv", rows)
    full = [r for r in rows if not r["partial_current_day"]]
    first_short = next((r["date"] for r in full if r["processed_and_enrichment_completed"] < r["enrichment_entered"]), None)
    first_rolling = next((full[i]["date"] for i in range(6, len(full)) if
        sum(r["processed_and_enrichment_completed"] for r in full[i-6:i+1]) <
        sum(r["enrichment_entered"] for r in full[i-6:i+1])), None)
    last28 = full[-28:]
    avg_inflow = mean(r["enrichment_entered"] for r in last28)
    avg_throughput = mean(r["processed_and_enrichment_completed"] for r in last28)
    sample = value["cost_samples"][0]
    # No historical usage ledger exists. Explicit byte/token sensitivity, not invented token counts.
    cost_scenarios = []
    input_bytes = float(sample["mean_input_bytes"])+len(SYSTEM_PROMPT.encode())+32
    output_bytes = float(sample["mean_output_bytes"])
    for name, divisor in (("low_estimate", 5), ("central_estimate", 4), ("high_estimate", 3)):
        ip, op = input_bytes/divisor, output_bytes/divisor
        cost = (ip*.4+op*1.6)/1e6
        cost_scenarios.append({"scenario": name, "estimated_input_tokens_per_event": ip,
                              "estimated_output_tokens_per_event": op, "estimated_usd_per_event": cost,
                              "estimated_30d_at_inflow_usd": cost*avg_inflow*30,
                              "estimated_30d_at_120pct_capacity_usd": cost*avg_inflow*36,
                              "estimated_whole_retryable_backlog_usd": cost*value["backlog"]["waiting_retryable"]})
    result = {"captured_at": value["captured_at"], "backlog": value["backlog"],
              "ready_unscored": value["ready_unscored"]["ready_unscored"],
              "average_daily_inflow_28d": avg_inflow, "average_daily_enrichment_28d": avg_throughput,
              "first_single_day_below_inflow": first_short, "first_7day_below_inflow": first_rolling,
              "days_clear_with_no_new_inflow": value["backlog"]["waiting_retryable"]/avg_throughput,
              "days_clear_with_continued_inflow": (
                  value["backlog"]["waiting_retryable"]/(avg_throughput-avg_inflow)
                  if avg_throughput>avg_inflow else None),
              "measured_tokens_per_event": None, "measured_usd_per_event": None,
              "cost_estimate_scenarios": cost_scenarios,
              "cost_note": "Byte/token assumptions, OpenAI standard rates, no historical usage ledger; excludes retries/taxes/markup",
              "historical_queue_precision": "Surviving current rows; no deletion audit or attempt-state transition timestamps"}
    dump(OUT / "diagnosis.json", result)
    write_csv(OUT / "cost_estimate_sensitivity.csv", cost_scenarios)
    return result


def reconstruct():
    source = json.loads((OUT / "scored_event_snapshot.json").read_text())
    captured = datetime.fromisoformat(json.loads((OUT / "pipeline_snapshot.json").read_text())["captured_at"])
    grid = panels(source, dates(captured.date()), zero_age=True)
    dump(OUT / "timely_risk_panels.json", grid)
    stored_lookup = {}
    for kind, filename in (("regional", "regional_daily_thresholds.csv"), ("asset", "asset_daily_thresholds.csv")):
        with (LAB / "step5" / filename).open() as stream:
            for item in csv.DictReader(stream):
                name = item["region"] if kind == "regional" else item["asset"]
                stored_lookup[(item["date"], kind, name, item["window_days"])] = (
                    float(item["stored_risk"]) if item["stored_risk"] else None)
    snapshot = json.loads((OUT / "pipeline_snapshot.json").read_text())
    incoming = {r["day"]: r["inserted"] for r in snapshot["insertions"]}
    scored = Counter(row["inserted_at"][:10] for row in source)
    coverage = [{"date": day.isoformat(), "inserted": incoming.get(day.isoformat(), 0),
                 "have_risk_score_at_snapshot": scored[day.isoformat()],
                 "coverage": scored[day.isoformat()]/incoming[day.isoformat()] if incoming.get(day.isoformat()) else None,
                 "reliable": bool(incoming.get(day.isoformat())) and scored[day.isoformat()]/incoming[day.isoformat()] >= .5,
                 "counterfactual_later_known_ai": True} for day in dates(captured.date())]
    write_csv(OUT / "daily_counterfactual_coverage.csv", coverage)
    comparisons, asof, alerts = [], {}, []
    serial = -2000000
    generator_regions = ("Europe", "Middle East", "Black Sea", "Asia", "North Africa", "North America")
    for day, panel in grid.items():
        asof[day] = {"regional": {region: {"risk": values["7"]} for region, values in panel["regional"].items()},
                      "asset": {asset: {"risk": values["7"]} for asset, values in panel["asset"].items()}}
        for kind in ("regional", "asset"):
            for name, windows in panel[kind].items():
                for window in ("7", "30"):
                    stored = stored_lookup.get((day, kind, name, window))
                    comparisons.append({"date": day, "kind": kind, "name": name, "window_days": int(window),
                                        "counterfactual_timely_risk": windows[window], "stored_risk": stored,
                                        "candidate_ge70": windows[window] >= 70,
                                        "passes_severity5_gate_at90": windows[window] >= 90,
                                        "generator_uses_this_scope_window": window == "7" and (
                                            kind == "asset" or name in generator_regions),
                                        "coverage": next(r["coverage"] for r in coverage if r["date"] == day)})
                if windows["7"] >= 90 and (kind == "asset" or name in generator_regions):
                    serial -= 1
                    alerts.append({"id": serial, "alert_type": "REGIONAL_RISK_SPIKE" if kind == "regional" else "ASSET_RISK_ALERT",
                                   "lab_source_alert_type": "REGIONAL_RISK_SPIKE" if kind == "regional" else "ASSET_RISK_SPIKE",
                                   "region": name if kind == "regional" else "Europe",
                                   "created_at": datetime.fromisoformat(day)+timedelta(days=1, microseconds=-1),
                                   "severity": 5, "risk_score": windows["7"], "weight": 1.,
                                   "headline": f"Counterfactual timely {kind} {name}", "body": "", "raw_input": {}})
    write_csv(OUT / "timely_vs_stored_risk_daily.csv", comparisons)
    write_csv(OUT / "timely_severity5_candidates.csv", alerts)
    return asof, alerts, coverage


def mask_market(result, valid):
    for market in result.values():
        for horizons in market["splits"].values():
            for item in horizons.values():
                item["observations"] = [r for r in item["observations"] if r["date"] in valid]
                obs = item["observations"]
                xs, ys, zs = [[r[key] for r in obs] for key in ("signal", "forward_log_return", "realised_vol_10")]
                item.update(n=len(obs), partial_abs=partial_correlation(xs, list(map(abs, ys)), zs),
                            partial_signed=partial_correlation(xs, ys, zs))
    return result


def run():
    capture()
    diagnosis()
    asof, alerts, coverage = reconstruct()
    valid = {r["date"] for r in coverage if r["reliable"] and r["date"]<=END.isoformat()}
    data = replay_inputs()
    scores, summary = {}, []
    for name in NAMES:
        variant = get_variant(name)
        context = {"asof_pillars": asof, "timely_alerts": alerts,
                   "labels": cached_labels() if variant.label_model == "gpt41" else {}}
        series = replay(data["alerts"], START, END, variant, data["warmup"], data["health"], context)
        for row in series:
            if row["date"] not in valid:
                row["flags"].append("unreliable_timely_coverage_below_50pct")
        directory = OUT / "variants" / name
        directory.mkdir(parents=True, exist_ok=True)
        result = scorecard(series, data["markets"], variant)
        # Do not leave unrestricted market statistics labelled as evaluated evidence.
        result["market_link"] = {}  # unrestricted generic metrics must not appear as evaluated evidence
        result["market_splits_step4"] = mask_market(split_market(series, data["markets"]), valid)
        result["coverage_restriction"] = {"reliable_calendar_days": len(valid), "all_days": len(series),
                                           "signal_date_requires_coverage_at_least": .5}
        scores[name] = result
        write_series(directory / "series.csv", series)
        pillar_exports(directory, series)
        dump(directory / "variant.json", asdict(variant))
        write_scorecard(directory, result)
    for name, result in scores.items():
        guard, draws = compare_scorecards(scores["integrity_v1"], result)
        guard["decision_assessable"] = all(c["ci90_low"] is not None for c in guard["cells"]
            if c["split"] != "full" and (c["market"], c["horizon_sessions"]) in (("Brent", 3), ("TTF", 1)))
        result["bootstrap_vs_integrity_v1"] = guard
        directory = OUT / "variants" / name
        dump(directory / "scorecard.json", result)
        dump(directory / "bootstrap_vs_integrity_v1.json", guard)
        dump(directory / "bootstrap_draws.json", draws)
        (directory / "bootstrap.md").write_text(bootstrap_markdown(guard))
        # The generic scorecard renderer needs its original market section, so write a clear restricted report.
        (directory / "scorecard.md").write_text(
            f"# {name}\n\nMarket evaluation: reliable signal-date coverage >=50%; {len(valid)}/282 calendar days.\n\n"
            + bootstrap_markdown(guard))
        summary.append({"variant": name, "reliable_calendar_days": len(valid), "acceptable": guard["acceptable"],
                        "improvement": guard["improvement"],
                        "decision_status": "assessable" if guard["decision_assessable"] else "insufficient_coverage",
                        **{key: result["stability"][key]["value"] for key in
                           ("mean_absolute_daily_change", "share_abs_change_ge_10", "weekend_weekday_mean_ratio")},
                        "deciding_cells": [r for r in guard["cells"] if r["split"] != "full" and
                                            (r["market"], r["horizon_sessions"]) in (("Brent", 3), ("TTF", 1))]})
    dump(OUT / "summary_table.json", summary)
    write_csv(OUT / "summary_table.csv", summary)
    from .step6_report import build
    build()
    print("Step 6 frozen-input diagnosis and counterfactual replays complete", flush=True)


if __name__ == "__main__":
    run()
