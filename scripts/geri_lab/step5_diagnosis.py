"""Daily end-of-day stored snapshots and causal upstream risk-engine diagnostics."""
from collections import Counter, defaultdict
from datetime import datetime, timedelta
import json
import math
from statistics import mean, median

from .step4_pairs import write_csv
from .step5_data import OUT, START, END, dump, risk_inputs

ASSETS = ("oil", "gas", "fx", "freight")
GENERATOR_REGIONS = ("Europe", "Middle East", "Black Sea", "Asia", "North Africa",
                     "South America", "Russia", "North America")


def days():
    day = START
    while day <= END:
        yield day
        day += timedelta(days=1)


def original_risk(row):
    raw = row.get("raw_input") or {}
    if isinstance(raw, str):
        raw = json.loads(raw)
    key = "risk_7d" if row["alert_type"] == "REGIONAL_RISK_SPIKE" else "risk_score"
    value = raw.get(key)
    if isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 100:
        return float(value)
    return None


def asof_grid(rows, fields):
    """Each grid value was persisted no later than that UTC day's end."""
    latest, position, output = {}, 0, {}
    for day in days():
        cutoff = datetime.combine(day + timedelta(days=1), datetime.min.time())
        while position < len(rows) and rows[position]["calculated_at"] < cutoff:
            item = rows[position]
            latest[tuple(item[k] for k in fields)] = item
            position += 1
        output[day] = dict(latest)
    return output


def window_stats(daily, day, window, lookback, denominator_window):
    cutoff = day - timedelta(days=window - 1)
    raw = sum(value for when, value in daily.items() if cutoff <= when <= day)
    first = day - timedelta(days=lookback - 1)
    candidates = [(when, value) for when, value in daily.items() if first <= when <= day]
    best, best_start, best_end = 1., None, None
    # Reproduce current risk_engine SQL: forward windows starting on observed days,
    # clipped to the current 180-day read boundary. Asset denominator_window=1.
    for when, _ in candidates:
        end = min(day, when + timedelta(days=denominator_window - 1))
        total = sum(value for other, value in candidates if when <= other <= end)
        if total > best:
            best, best_start, best_end = total, when, end
    return raw, best, best_start, best_end


def run():
    from src.geri.types import get_region_cluster, get_regional_weight
    source = risk_inputs()
    regional_grid = asof_grid(source["risk_indices"], ("region", "window_days"))
    asset_grid = asof_grid(source["asset_risk"], ("region", "asset", "window_days"))
    regional_daily, asset_daily = defaultdict(lambda: defaultdict(float)), defaultdict(lambda: defaultdict(float))
    for event in source["risk_events"]:
        day, weight, region = event["created_at"].date(), float(event["weighted_score"]), event["region"]
        regional_daily[region][day] += weight
        for asset, impact in event["asset_impacts"].items():
            confidence = impact.get("confidence")
            confidence = .5 if confidence is None else float(confidence)
            asset_daily[(region, asset)][day] += weight * confidence
    regions = sorted({r["region"] for r in source["risk_indices"]} | set(GENERATOR_REGIONS))
    stored_regions = sorted({r["region"] for r in source["risk_indices"]})
    regional_rows, asset_rows = [], []
    actual_alerts = defaultdict(list)
    for alert in source["alerts"]:
        if START <= alert["created_at"].date() <= END:
            actual_alerts[(alert["created_at"].date(), alert["region"], alert["alert_type"])].append(alert)
    for day in days():
        for region in regions:
            for window in (7, 30):
                item = regional_grid[day].get((region, window))
                raw, maximum, peak_start, peak_end = window_stats(
                    regional_daily[region], day, window, 180, window)
                value = float(item["risk_score"]) if item else None
                age = ((datetime.combine(day + timedelta(days=1), datetime.min.time()) -
                        item["calculated_at"]).total_seconds() / 3600) if item else None
                events = actual_alerts[(day, region, "REGIONAL_RISK_SPIKE")]
                regional_rows.append({
                    "date": day.isoformat(), "region": region, "window_days": window,
                    "stored_risk": value, "stored_snapshot_id": item["id"] if item else None,
                    "stored_calculated_at": item["calculated_at"].isoformat() if item else None,
                    "snapshot_age_hours_at_eod": age, "fresh_within_24h": age <= 24 if age is not None else False,
                    "raw_window_sum": raw, "comparison_max_180d": maximum,
                    "comparison_peak_start": str(peak_start) if peak_start else None,
                    "comparison_peak_end": str(peak_end) if peak_end else None,
                    "reconstructed_normalized_current_formula": min(100, 100 * raw / maximum),
                    "candidate_ge70": value >= 70 if value is not None else None,
                    "severity_ge4_at80": value >= 80 if value is not None else None,
                    "severity5_at90": value >= 90 if value is not None else None,
                    "actual_alerts_that_day": len(events) if window == 7 else None,
                    "note": "stored normalized risk is point-in-time; comparison maximum replays current formula"})
        for asset in ASSETS:
            for window in (7, 30):
                item = asset_grid[day].get(("Europe", asset, window))
                raw, max90, peak_start, peak_end = window_stats(
                    asset_daily[("Europe", asset)], day, window, 90, 1)
                _, max180, _, _ = window_stats(asset_daily[("Europe", asset)], day, window, 180, window)
                value = float(item["risk_score"]) if item else None
                events = [r for r in actual_alerts[(day, "Europe", "ASSET_RISK_SPIKE")]
                          if ((r.get("raw_input") or {}).get("asset") or
                              (r.get("scope_assets") or [None])[0]) == asset]
                asset_rows.append({
                    "date": day.isoformat(), "region": "Europe", "asset": asset, "window_days": window,
                    "stored_risk": value, "stored_snapshot_id": item["id"] if item else None,
                    "stored_calculated_at": item["calculated_at"].isoformat() if item else None,
                    "snapshot_age_hours_at_eod": (
                        (datetime.combine(day + timedelta(days=1), datetime.min.time()) -
                         item["calculated_at"]).total_seconds() / 3600 if item else None),
                    "raw_window_sum": raw, "actual_comparison_max_90d_single_day": max90,
                    "requested_180d_window_max_diagnostic_only": max180,
                    "comparison_peak_day": str(peak_start) if peak_start else None,
                    "reconstructed_normalized_current_formula": min(100, 100 * raw / max90),
                    "candidate_ge70": value >= 70 if value is not None else None,
                    "severity_ge4_at80": value >= 80 if value is not None else None,
                    "severity5_at90": value >= 90 if value is not None else None,
                    "actual_alerts_that_day": len(events) if window == 7 else None,
                    "note": "asset formula uses 90d max SINGLE DAY, not 180d rolling-window maximum"})
    write_csv(OUT / "regional_daily_thresholds.csv", regional_rows)
    write_csv(OUT / "asset_daily_thresholds.csv", asset_rows)
    monthly, type_months = [], Counter()
    for row in source["alerts"]:
        if START <= row["created_at"].date() <= END:
            type_months[(row["created_at"].strftime("%Y-%m"), row["alert_type"])] += 1
    for kind, rows in (("regional", regional_rows), ("asset", asset_rows)):
        for month in sorted({r["date"][:7] for r in rows}):
            selected = [r for r in rows if r["date"].startswith(month) and r["window_days"] == 7
                        and (kind != "regional" or r["region"] in GENERATOR_REGIONS)]
            available = [r for r in selected if r["stored_risk"] is not None]
            monthly.append({"kind": kind, "month": month, "entity_days": len(selected),
                            "available": len(available), "missing": len(selected) - len(available),
                            "max_stored_7d": max((r["stored_risk"] for r in available), default=None),
                            "days_below70": sum(r["stored_risk"] < 70 for r in available),
                            "days_70_to80": sum(70 <= r["stored_risk"] < 80 for r in available),
                            "days_80_to90": sum(80 <= r["stored_risk"] < 90 for r in available),
                            "days_ge90": sum(r["stored_risk"] >= 90 for r in available),
                            "actual_alerts": sum(r["actual_alerts_that_day"] or 0 for r in available)})
    write_csv(OUT / "monthly_threshold_diagnosis.csv", monthly)
    asset_alerts = [r for r in source["alerts"] if r["alert_type"] == "ASSET_RISK_SPIKE"
                    and START <= r["created_at"].date() <= END]
    type_counts = [{"month": month, "asset_risk_spike": type_months[(month, "ASSET_RISK_SPIKE")],
                    "regional_risk_spike": type_months[(month, "REGIONAL_RISK_SPIKE")],
                    "asset_risk_alert": type_months[(month, "ASSET_RISK_ALERT")],
                    "share_accepted_by_original_type_filter": (
                        0. if type_months[(month, "ASSET_RISK_SPIKE")] else None),
                    "share_accepted_by_corrected_type_filter": (
                        1. if type_months[(month, "ASSET_RISK_SPIKE")] else None)}
                   for month in sorted({d.strftime("%Y-%m") for d in days()})]
    write_csv(OUT / "alert_type_counts_monthly.csv", type_counts)
    threshold_anomalies = [r for r in regional_rows + asset_rows
                           if r["window_days"] == 7 and r["date"] >= "2026-08-01"
                           and r["severity5_at90"] and not r["actual_alerts_that_day"]]
    write_csv(OUT / "late_period_ge90_without_alert.csv", threshold_anomalies)
    result = {"stored_regions": stored_regions,
              "continuous_regional_multipliers": {
                  region: {"cluster": get_region_cluster(region, "", ""),
                           "multiplier": get_regional_weight(get_region_cluster(region, "", ""))}
                  for region in stored_regions},
              "regions_without_any_history": sorted(set(GENERATOR_REGIONS) - set(stored_regions)),
              "regional_rows": len(regional_rows), "asset_rows": len(asset_rows), "monthly": monthly,
              "asset_alerts_total": len(asset_alerts),
              "asset_alerts_with_original_risk": sum(original_risk(r) is not None for r in asset_alerts),
              "regional_alerts_with_original_risk": sum(
                  original_risk(r) is not None for r in source["alerts"] if r["alert_type"] == "REGIONAL_RISK_SPIKE"),
              "late_ge90_without_alert_rows": len(threshold_anomalies),
              "current_formula_asset_denominator": "90-day maximum single-day asset score",
              "current_formula_regional_denominator": "180-day maximum rolling window score",
              "pit_reconstruction_limit": (
                  "risk_events created_at and stored weighted_score are causal; asset confidence metadata are "
                  "current event JSON without version history. Stored normalized snapshots, not reconstructed "
                  "values, are used for continuous scoring. Current formulas are not proven historical versions.")}
    dump(OUT / "diagnosis.json", result)
    timing_path = OUT / "risk_event_timing.json"
    if timing_path.exists():
        timing = json.loads(timing_path.read_text())
        timing_groups = defaultdict(list)
        for item in timing:
            timing_groups[item["scored_at"][:7]].append(item)
        delay_rows = []
        for month, items in sorted(timing_groups.items()):
            delays = sorted(float(r["scoring_delay_days"]) for r in items)
            delay_rows.append({
                "month": month, "n": len(items), "mean_scoring_delay_days": mean(delays),
                "median_scoring_delay_days": median(delays), "max_scoring_delay_days": max(delays),
                "share_delay_over30d": mean(value > 30 for value in delays),
                "mean_weighted_score": mean(float(r["weighted_score"]) for r in items),
                "latest_source_inserted_at": max(r["inserted_at"] for r in items),
                "mean_decay_factor_at_scoring": mean(math.exp(-value / 14) for value in delays)})
        write_csv(OUT / "risk_scoring_delay_monthly.csv", delay_rows)
        result["scoring_delay_monthly"] = delay_rows
        dump(OUT / "diagnosis.json", result)
    dump(OUT / "asof_pillars.json", {
        day.isoformat(): {
            "regional": {region: {"risk": float(regional_grid[day][(region, 7)]["risk_score"]),
                                  "snapshot_id": regional_grid[day][(region, 7)]["id"]}
                         for region in stored_regions if (region, 7) in regional_grid[day]},
            "asset": {asset: {"risk": float(asset_grid[day][("Europe", asset, 7)]["risk_score"]),
                              "snapshot_id": asset_grid[day][("Europe", asset, 7)]["id"]}
                      for asset in ASSETS if ("Europe", asset, 7) in asset_grid[day]}}
        for day in days()})
    print(f"Daily threshold evidence: {len(regional_rows)} regional rows, {len(asset_rows)} asset rows", flush=True)
    return result


if __name__ == "__main__":
    run()
