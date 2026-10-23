"""Pure chronological replay using only the variant's own preceding raw history."""
from collections import Counter, defaultdict, deque
from datetime import timedelta
import csv
import json

from src.geri.compute import compute_components
from src.geri.normalize import normalize_components, calculate_geri_value
from src.geri.types import AlertRecord, HistoricalBaseline, get_band
from .relevance_filters import keep


RAW_FIELDS = (
    "high_impact_score", "regional_spike_score",
    "asset_risk_score", "region_concentration_score_raw",
)
NORMAL_FIELDS = (
    "norm_high_impact", "norm_regional_spike",
    "norm_asset_risk", "norm_region_concentration",
)
PREFIXES = ("high_impact", "regional_spike", "asset_risk", "region_concentration")
PILLARS = ("H", "R", "A", "C")
CSV_FIELDS = (
    "date", "geri", "band", "raw_H", "raw_R", "raw_A", "raw_C",
    "norm_H", "norm_R", "norm_A", "norm_C",
    "n_alerts", "n_by_type", "fallback_used", "flags",
    "data_quality", "alerts_ratio", "events_ratio",
    "active_pillar_ceiling", "baseline_active_pillars",
    "high_impact_available", "high_impact_kept",
)


def as_alert(row):
    raw = row.get("raw_input") or {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            raw = {}
    category = raw.get("category")
    if not category and raw.get("driver_events"):
        category = raw["driver_events"][0].get("category")
    return AlertRecord(
        id=row["id"], alert_type=row["alert_type"], severity=row["severity"],
        risk_score=float(row["risk_score"]) if row["risk_score"] is not None else None,
        region=row["region"], weight=float(row.get("weight") or 1.0),
        created_at=row["created_at"], headline=row["headline"],
        body=row.get("body"), category=category,
    )


def replay(alert_rows, start, end, variant, warmup=None, health=None, filter_context=None,
           diagnostics=False):
    variant.validate()
    if variant.pillar_mode in ("fixed_alerts", "fixed_alerts_sev4"):
        from .step5_pillars import prepare_alerts
        alert_rows = prepare_alerts(alert_rows, variant, filter_context or {})
    if variant.pillar_mode == "timely_alerts":
        alert_rows = [row for row in alert_rows if row["alert_type"] not in
                      ("REGIONAL_RISK_SPIKE", "ASSET_RISK_SPIKE", "ASSET_RISK_ALERT")]
        alert_rows += (filter_context or {})["timely_alerts"]
    warmup = warmup or start
    if end < start or warmup > start:
        raise ValueError("Invalid replay interval.")
    daily_alerts = defaultdict(list)
    available = Counter()
    kept_high = Counter()
    for row in alert_rows:
        if row["alert_type"] in variant.accepted_types:
            day = row["created_at"].date()
            if row["alert_type"] == "HIGH_IMPACT_EVENT":
                available[day] += 1
            if keep(row, variant, filter_context):
                daily_alerts[day].append(as_alert(row))
                if row["alert_type"] == "HIGH_IMPACT_EVENT":
                    kept_high[day] += 1
    history = deque()
    original_history=deque()
    smoothing_state=None
    transforms=bool(variant.weekday_adjust or variant.carryover_half_life_days
                    or variant.display_smoothing)
    output = []
    day = warmup
    while day <= end:
        cutoff = day - timedelta(days=variant.baseline_window_days)
        previous_window=[r for d,r in history if
                         day-timedelta(days=variant.baseline_window_days+1)<=d<day-timedelta(days=1)]
        expired=[r for d,r in history if d<cutoff]
        while history and history[0][0] < cutoff:
            history.popleft()
        components = compute_components(daily_alerts[day])
        if variant.pillar_mode in ("continuous", "timely_continuous"):
            from .step5_pillars import continuous_values
            regional, asset = continuous_values(day, filter_context or {})
            components.regional_spike_score = regional
            components.asset_risk_score = asset
        if variant.dedup_mode != "none":
            from .storyline import dedup_components
            context = filter_context or {}
            components = dedup_components(daily_alerts[day], components,
                                          context.get("assignments", {}),
                                          variant.dedup_mode, context.get("sources", {}))
        quality=(health or {}).get(day,{}).get("data_quality","OK")
        original_raw=tuple(getattr(components,key) for key in RAW_FIELDS)
        if transforms:
            from .smoothing import raw_transform
            while original_history and original_history[0][0]<day-timedelta(days=56):
                original_history.popleft()
            adjusted,smoothing_state=raw_transform(
                original_raw,day,quality,variant,original_history,smoothing_state)
            for field,v in zip(RAW_FIELDS,adjusted):
                setattr(components,field,v)
            original_history.append((day,original_raw,quality))
        baseline = HistoricalBaseline(days_count=len(history))
        varying = []
        for index, prefix in enumerate(PREFIXES):
            values = [raw[index] for _, raw in history]
            if values:
                setattr(baseline, prefix + "_min", min(values))
                setattr(baseline, prefix + "_max", max(values))
                if min(values) < max(values):
                    varying.append(PILLARS[index])
        raw = tuple(getattr(components, key) for key in RAW_FIELDS)
        normalize_components(components, baseline)
        value = calculate_geri_value(components)
        unsmoothed_value=value
        if transforms:
            from .smoothing import display_transform
            value=display_transform(value,variant,smoothing_state)
        flags = []
        if not daily_alerts[day]:
            flags.append("no_accepted_alerts_not_proof_of_outage")
        if day == warmup:
            flags.append("cold_start")
        if components.insufficient_history:
            flags.append("insufficient_history")
        row = {
            "date": day.isoformat(), "geri": value, "band": get_band(value).value,
            "n_alerts": len(daily_alerts[day]),
            "n_by_type": dict(Counter(a.alert_type for a in daily_alerts[day])),
            "fallback_used": components.insufficient_history, "flags": flags,
            "data_quality": (health or {}).get(day, {}).get("data_quality", "OK"),
            "alerts_ratio": (health or {}).get(day, {}).get("alerts_ratio"),
            "events_ratio": (health or {}).get(day, {}).get("events_ratio"),
            "active_pillar_ceiling": round(100 * sum(
                weight for pillar, weight in zip(PILLARS, variant.weights)
                if pillar in varying
            ), 10),
            "baseline_active_pillars": varying,
            "high_impact_available": available[day],
            "high_impact_kept": kept_high[day],
        }
        row.update({f"raw_{p}": v for p, v in zip(PILLARS, raw)})
        row.update({f"norm_{p}": getattr(components, field)
                    for p, field in zip(PILLARS, NORMAL_FIELDS)})
        if diagnostics:
            from copy import deepcopy
            def rescore(vectors):
                b=HistoricalBaseline(days_count=len(vectors))
                for i,prefix in enumerate(PREFIXES):
                    if vectors:
                        setattr(b,prefix+"_min",min(r[i] for r in vectors))
                        setattr(b,prefix+"_max",max(r[i] for r in vectors))
                trial=deepcopy(components)
                normalize_components(trial,b)
                return calculate_geri_value(trial)
            previous_value=rescore(previous_window)
            no_exit_value=rescore([r for _,r in history]+expired)
            row.update(original_raw=dict(zip(PILLARS,original_raw)),
                       smoothing_state=smoothing_state,
                       pre_display_value=unsmoothed_value,
                       previous_window_rescore=previous_value,
                       previous_window_delta=unsmoothed_value-previous_value,
                       isolated_exit_rescore=no_exit_value,
                       isolated_exit_delta=unsmoothed_value-no_exit_value,
                       expired_healthy_rows=len(expired))
        if day >= start:
            output.append(row)
        # Never seed from published component rows; every raw vector is replayed.
        # Production persists C to two decimals, then reads it into the next
        # baseline. Reproduce that serialization boundary using our OWN values.
        if not variant.degraded_alert_floor or row["data_quality"] == "OK":
            history.append((day, raw[:3] + (round(raw[3], 2),)))
        day += timedelta(days=1)
    return output


def write_series(path, rows):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            export = dict(row)
            for field in ("n_by_type", "flags", "baseline_active_pillars"):
                export[field] = json.dumps(export[field], sort_keys=True)
            writer.writerow(export)
