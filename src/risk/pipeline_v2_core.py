"""Pure pipeline planning and point-in-time risk panels. No database/API side effects."""
from collections import defaultdict
from datetime import date, datetime, timedelta
import math
import os

REGIONS = ("Europe", "Middle East", "Asia", "North America", "Black Sea", "North Africa", "global")
ASSETS = ("oil", "gas", "fx", "freight")
WEIGHTS = {"geopolitical": 1.2, "energy": 1.5, "supply_chain": 1.0}


def mode():
    """Explicit mode wins; the deprecated boolean means LIVE, never shadow."""
    value = os.environ.get("RISK_PIPELINE_V2_MODE")
    if value is None:
        value = "live" if os.environ.get("RISK_PIPELINE_V2_ENABLED", "false").lower() == "true" else "off"
    value = value.strip().lower()
    if value not in {"off", "shadow", "live"}:
        raise ValueError("RISK_PIPELINE_V2_MODE must be off, shadow or live")
    return value


def enabled():
    return mode() != "off"


def plan(metrics):
    inflow = float(metrics["average_daily_inflow_28d"])
    required = max(1, math.ceil(1.2 * inflow / 24))
    configured_rpm = float(os.environ.get("RISK_PIPELINE_V2_MAX_RPM", "20"))
    rpm = min(60 / max(.5, float(os.environ.get("AI_SLEEP_BETWEEN_CALLS", ".5"))), configured_rpm)
    seconds = float(os.environ.get("RISK_PIPELINE_V2_RUN_SECONDS", "1200"))
    budget = min(5., float(os.environ.get("RISK_PIPELINE_V2_DAILY_BUDGET_USD", "5")))
    if not all(math.isfinite(x) and x > 0 for x in (configured_rpm, rpm, seconds, budget)):
        raise ValueError("Positive request rate and runtime required")
    # Three request slots per event allow both retries; normal one-call capacity is higher.
    slot_capacity = math.floor(rpm * seconds / 60 / 3)
    if required > slot_capacity:
        raise RuntimeError(f"Insufficient configured capacity: {required} events/run required, "
                           f"{slot_capacity} fit retry-reserved rate slots")
    daily_capacity = required * 24
    net = daily_capacity - inflow
    return {"batch_size": required, "runs_per_day": 24, "planned_daily_capacity": daily_capacity,
            "capacity_ratio": daily_capacity / inflow if inflow else None,
            "max_rpm": rpm, "runtime_seconds": seconds, "retry_slot_capacity": slot_capacity,
            "catch_up_last7d_days_at_net_capacity": (
                metrics.get("waiting_last7d_retryable", metrics["waiting_last7d"]) / net if net > 0 else None),
            "daily_budget_usd": budget,
            "guarantee_scope": "configured hourly capacity; outages, budget exhaustion and failures raise shortfall"}


def event_weight(row, zero_age):
    if not zero_age:
        return float(row["weighted_score"])
    return float(row["base_severity"]) * float(row["ai_confidence"]) * WEIGHTS.get(row["category"], 1.)


def panels(rows, dates, zero_age=True):
    """Causal daily EOD panels. Later-known AI values make zero_age a counterfactual."""
    region_days, asset_days = defaultdict(lambda: defaultdict(float)), defaultdict(lambda: defaultdict(float))
    for row in rows:
        inserted = row["inserted_at"]
        day = inserted.date() if isinstance(inserted, datetime) else date.fromisoformat(inserted[:10])
        weight = event_weight(row, zero_age)
        region_days[row["region"]][day] += weight
        if row["region"] == "Europe":
            for asset, value in (row.get("asset_impacts") or {}).items():
                if asset in ASSETS and isinstance(value, dict):
                    confidence = value.get("confidence")
                    asset_days[asset][day] += weight * (.5 if confidence is None else float(confidence))
    all_days = sorted({day for value in region_days.values() for day in value} | set(dates))
    first, last = min(all_days), max(all_days)
    calendar = [first + timedelta(days=i) for i in range((last-first).days+1)]

    def series(values):
        daily = [values.get(day, 0.) for day in calendar]
        prefix = [0.]
        for value in daily:
            prefix.append(prefix[-1]+value)
        return daily, prefix

    regional = {region: series(region_days[region]) for region in REGIONS}
    assets = {asset: series(asset_days[asset]) for asset in ASSETS}
    result = {}
    for day in dates:
        i = (day-first).days
        output = {"regional": {}, "asset": {}, "denominators": {}}
        for region, (_, prefix) in regional.items():
            output["regional"][region] = {}
            for window in (7, 30):
                left = max(0, i-179)
                # For non-negative scores the maximum full window dominates boundary partials.
                ends = range(min(i, left+window-1), i+1)
                maximum = max(1., max(prefix[end+1]-prefix[max(left, end-window+1)] for end in ends))
                raw = prefix[i+1]-prefix[max(0, i-window+1)]
                output["regional"][region][str(window)] = min(100., 100*max(0., raw)/maximum)
                output["denominators"][f"{region}_{window}"] = maximum
        for asset, (daily, prefix) in assets.items():
            maximum = max(1., max(daily[max(0, i-89):i+1]))
            output["asset"][asset] = {
                str(window): min(100., 100*max(0., prefix[i+1]-prefix[max(0, i-window+1)])/maximum)
                for window in (7, 30)}
            output["denominators"][asset] = maximum
        result[day.isoformat()] = output
    return result
