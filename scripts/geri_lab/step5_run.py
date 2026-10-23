"""Cached-only restored-pillar replays and bootstrap decision tooling."""
import argparse
from collections import Counter, defaultdict
from dataclasses import asdict
import json
from statistics import mean

from .acceptance import replication
from .bootstrap import compare_scorecards, markdown as bootstrap_markdown
from .compare import compare
from .relevance_filters import context_for, sanity_lists
from .replay import replay, write_series
from .scorecard import scorecard, write_scorecard
from .step4_data import inputs as step4_inputs, labels_for
from .step4_pairs import write_csv
from .step4_report import split_market, stability
from .step5_data import OUT, LAB, START, END, capture, risk_inputs, population, cached_labels, dump, protections
from .step5_diagnosis import original_risk
from .step5_pillars import prepare_alerts
from .variants import get_variant

NAMES = ("integrity_v1", "rel_only", "rel41_only", "pillars_fixed_alerts",
         "pillars_fixed_alerts_sev4", "pillars_continuous", "pillars_continuous_rel41", "damp_log")
WEIGHTS = {"H": .4, "R": .25, "A": .2, "C": .15}


def replay_inputs():
    source = step4_inputs()
    risk = risk_inputs()
    existing = {r["id"] for r in source["alerts"]}
    source["alerts"] += [r for r in risk["alerts"] if r["id"] not in existing and
                         START <= r["created_at"].date() <= END]
    source["alerts"].sort(key=lambda r: (r["created_at"], r["id"]))
    return source


def pillar_exports(directory, series):
    rows = []
    for row in series:
        rows.append({
            "date": row["date"], "geri": row["geri"], "data_quality": row["data_quality"],
            **{f"raw_{p}": row[f"raw_{p}"] for p in WEIGHTS},
            **{f"norm_{p}": row[f"norm_{p}"] for p in WEIGHTS},
            **{f"weighted_{p}_points": row[f"norm_{p}"] * w for p, w in WEIGHTS.items()},
            "active_pillar_ceiling": row["active_pillar_ceiling"],
            "baseline_active_pillars": row["baseline_active_pillars"],
            "fallback_used": row["fallback_used"],
        })
    write_csv(directory / "pillar_daily_and_ceiling.csv", rows)
    monthly = []
    for month in sorted({r["date"][:7] for r in series}):
        group = [r for r in series if r["date"].startswith(month)]
        monthly.append({
            "month": month, "days": len(group),
            **{f"mean_weighted_{p}_points": mean(r[f"norm_{p}"] * w for r in group) for p, w in WEIGHTS.items()},
            **{f"raw_{p}_zero_days": sum(r[f"raw_{p}"] == 0 for r in group) for p in WEIGHTS},
            **{f"norm_{p}_zero_days": sum(r[f"norm_{p}"] == 0 for r in group) for p in WEIGHTS},
            "ceiling_min": min(r["active_pillar_ceiling"] for r in group),
            "ceiling_max": max(r["active_pillar_ceiling"] for r in group)})
    write_csv(directory / "pillar_monthly.csv", monthly)
    zeros = {p: {"raw_zero_days": sum(r[f"raw_{p}"] == 0 for r in series),
                 "normalized_zero_days": sum(r[f"norm_{p}"] == 0 for r in series)} for p in WEIGHTS}
    dump(directory / "pillar_zero_days.json", zeros)
    return monthly, zeros


def label_analysis():
    from .storyline import rule_pass
    rows = population()
    old, new = labels_for(rows), cached_labels(rows)
    from .step5_data import label_key, journal, CACHE
    records = {record["cache_key"]: record for record in journal(CACHE / "step5_relevance41.jsonl")}
    write_csv(OUT / "relevance41_alert_assignments.csv", [
        {"alert_id": row["alert_id"], "cache_key": label_key(row),
         "cached_source_alert_id": records[label_key(row)]["id"],
         "exact_input_reused_from_other_alert": records[label_key(row)]["id"] != row["alert_id"],
         **new[row["alert_id"]]} for row in rows])
    groups = defaultdict(list)
    for row in rows:
        groups[row["month"]].append(row)
    result = []
    for month, selected in [("overall", rows), *sorted(groups.items())]:
        mini = sum(rule_pass(old[r["alert_id"]], "r_material_events") for r in selected)
        strong = sum(rule_pass(new[r["alert_id"]], "r_material_events") for r in selected)
        result.append({"month": month, "n": len(selected), "mini_kept": mini, "gpt41_kept": strong,
                       "mini_share": mini / len(selected), "gpt41_share": strong / len(selected),
                       "pass_disagreements": sum(rule_pass(old[r["alert_id"]], "r_material_events") !=
                                                 rule_pass(new[r["alert_id"]], "r_material_events")
                                                 for r in selected)})
    write_csv(OUT / "relevance41_retention_monthly.csv", result)
    dump(OUT / "relevance41_retention.json", result)
    return result


def execute(names):
    capture()
    data = replay_inputs()
    base_dir = OUT / "variants"
    base_dir.mkdir(exist_ok=True)
    # Reconfirm the original baseline from the same frozen high-impact corpus.
    baseline = replay(data["alerts"], START, END, get_variant("baseline"), data["warmup"], data["health"])
    check = replication(baseline, data["published"])
    dump(OUT / "baseline_replication.json", check)
    if not check["replication_passed"] or not check["known_values_passed"]:
        raise ValueError("Baseline replication protection failed")
    risk_rows = [r for r in data["alerts"] if r["alert_type"] in
                 ("REGIONAL_RISK_SPIKE", "ASSET_RISK_SPIKE", "ASSET_RISK_ALERT")]
    exclusions = [{"alert_id": r["id"], "date": r["created_at"].date().isoformat(),
                   "alert_type": r["alert_type"], "headline": r["headline"],
                   "reason": "Original 0–100 score missing from raw_input; excluded, never confidence-imputed"}
                  for r in risk_rows if original_risk(r) is None]
    write_csv(OUT / "fixed_alerts_missing_original_risk.csv", exclusions)
    coverage = {"source_regional": sum(r["alert_type"] == "REGIONAL_RISK_SPIKE" for r in risk_rows),
                "source_asset_spike": sum(r["alert_type"] == "ASSET_RISK_SPIKE" for r in risk_rows),
                "original_score_missing_excluded": len(exclusions)}
    dump(OUT / "fixed_alert_input_coverage.json", coverage)
    for name in names:
        variant = get_variant(name)
        context = context_for(variant, data["alerts"])
        series = replay(data["alerts"], START, END, variant, data["warmup"], data["health"], context)
        directory = base_dir / name
        directory.mkdir(exist_ok=True)
        result = scorecard(series, data["markets"], variant, sanity_lists(data["alerts"], variant, context))
        result["market_splits_step4"] = split_market(series, data["markets"])
        monthly, zeros = pillar_exports(directory, series)
        result["pillar_zero_days"] = zeros
        result["pillar_monthly_step5"] = monthly
        write_series(directory / "series.csv", series)
        write_scorecard(directory, result)
        dump(directory / "variant.json", asdict(variant))
        if variant.pillar_mode == "fixed_alerts_sev4":
            prepared = prepare_alerts(data["alerts"], variant, context)
            reconstructed = [r for r in prepared if r.get("lab_reconstructed")]
            write_csv(directory / "reconstructed_candidates.csv", reconstructed)
        print(f"{name}: {len(series)} days replayed", flush=True)
    # Every comparison uses identical dated outcomes/controls and paired weeks.
    reference = json.loads((base_dir / "integrity_v1/scorecard.json").read_text())
    for name in names:
        directory = base_dir / name
        result = json.loads((directory / "scorecard.json").read_text())
        bootstrap, draws = compare_scorecards(reference, result)
        dump(directory / "bootstrap_vs_integrity_v1.json", bootstrap)
        dump(directory / "bootstrap_draws.json", draws)
        result["bootstrap_vs_integrity_v1"] = bootstrap
        dump(directory / "scorecard.json", result)
        (directory / "scorecard.md").write_text(
            (directory / "scorecard.md").read_text() + "\n\n" + bootstrap_markdown(bootstrap))
        # New output tree does not overwrite archived Step 4 files.
        left_series = json.loads((base_dir / "integrity_v1/scorecard.json").read_text())
        text = "# Comparison against integrity_v1\n\n" + bootstrap_markdown(bootstrap)
        from .step4_report import table
        text += "\n## Stability\n\n" + table(
            ["Metric", "integrity_v1", name],
            [[key, left_series["stability"][key]["value"], result["stability"][key]["value"]]
             for key in ("mean_absolute_daily_change", "share_abs_change_ge_10", "weekend_weekday_mean_ratio")])
        (directory / "compare_integrity_v1.md").write_text(text + "\n")
    return protections()


def finalize():
    summary = []
    for name in NAMES:
        directory = OUT / "variants" / name
        if not (directory / "scorecard.json").exists():
            continue
        result = json.loads((directory / "scorecard.json").read_text())
        guard = result["bootstrap_vs_integrity_v1"]
        row = {"variant": name,
               "mean_abs_daily_change": result["stability"]["mean_absolute_daily_change"]["value"],
               "share_change_ge10": result["stability"]["share_abs_change_ge_10"]["value"],
               "weekend_weekday_ratio": result["stability"]["weekend_weekday_mean_ratio"]["value"],
               "maximum": result["coverage"]["maximum"]["value"],
               "acceptable": guard["acceptable"], "improvement": guard["improvement"]}
        for market, horizon in (("Brent", 3), ("TTF", 1)):
            for split in ("full", "H1", "H2"):
                metric = next(c for c in guard["cells"] if (c["market"], c["horizon_sessions"], c["split"]) ==
                              (market, horizon, split))
                prefix = f"{market}_{horizon}d_{split}"
                row[prefix + "_partial"] = metric["candidate_partial"]
                row[prefix + "_difference"] = metric["point_difference"]
                row[prefix + "_low90"] = metric["ci90_low"]
                row[prefix + "_high90"] = metric["ci90_high"]
        summary.append(row)
    dump(OUT / "summary_table.json", summary)
    write_csv(OUT / "summary_table.csv", summary)
    if (OUT / "variants/rel41_only/scorecard.json").exists():
        label_analysis()
    from .step5_report import build
    build(summary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--without-llm", action="store_true", help="Run independent completed-input variants first")
    parser.add_argument("--finalize-only", action="store_true")
    args = parser.parse_args()
    if not args.finalize_only:
        names = [name for name in NAMES if not args.without_llm or "rel41" not in name]
        execute(names)
    finalize()


if __name__ == "__main__":
    main()
