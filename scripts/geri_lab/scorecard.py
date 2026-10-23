"""Standard-library descriptive diagnostics, explicitly not a forecasting test."""
from collections import Counter, defaultdict
from datetime import date
import json
import math
from statistics import mean, pstdev

from .replay import PILLARS


def metric(value, n):
    return {"value": value, "n": n}


def correlation(xs, ys):
    if len(xs) < 3:
        return None
    mx, my = mean(xs), mean(ys)
    xx = sum((x - mx) ** 2 for x in xs)
    yy = sum((y - my) ** 2 for y in ys)
    if xx == 0 or yy == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / math.sqrt(xx * yy)


def partial_correlation(xs, ys, controls):
    if len(xs) < 4:
        return None
    center = mean(controls)
    variance = sum((z - center) ** 2 for z in controls)
    if not variance:
        return None
    def residuals(values):
        average = mean(values)
        slope = sum((z - center) * (v - average)
                    for z, v in zip(controls, values)) / variance
        return [v - average - slope * (z - center)
                for z, v in zip(controls, values)]
    return correlation(residuals(xs), residuals(ys))


def clean_prices(rows):
    """Drop weekends and exact repeated closes; never interpolate missing prices."""
    daily = {}
    for row in rows:
        if row["value"] is not None:
            value = float(row["value"])
            if math.isfinite(value) and value > 0:
                day = row["date"]
                daily[date.fromisoformat(day) if isinstance(day, str) else day] = value
    kept, previous, weekends, repeats = [], None, 0, 0
    for day, value in sorted(daily.items()):
        if day.weekday() >= 5:
            weekends += 1
        elif previous == value:
            repeats += 1
        else:
            kept.append((day, value))
        previous = value
    return kept, {"input_dates": len(daily), "weekend_rows_dropped": weekends,
                  "repeat_rows_dropped": repeats, "retained_dates": len(kept),
                  "first_retained_date": kept[0][0].isoformat() if kept else None,
                  "last_retained_date": kept[-1][0].isoformat() if kept else None}


def diagnostic_bucket(value):
    if value <= 15:
        return "0–15"
    if value <= 25:
        return "16–25"
    if value <= 40:
        return "26–40"
    return "41+"


def market_metrics(series, market_rows, threshold):
    prices, cleaning = clean_prices(market_rows)
    geri = {row["date"]: row["geri"] for row in series}
    output = {"cleaning": cleaning, "horizons": {}}
    returns = [None] + [math.log(prices[i][1] / prices[i - 1][1])
                        for i in range(1, len(prices))]
    for horizon in (1, 3):
        observations = []
        for i, (day, price) in enumerate(prices):
            if day.isoformat() not in geri or i + horizon >= len(prices):
                continue
            forward = math.log(prices[i + horizon][1] / price)
            volatility = pstdev(returns[i - 9:i + 1]) if i >= 10 else None
            observations.append((geri[day.isoformat()], forward, volatility))
        xs = [x for x, _, _ in observations]
        ys = [y for _, y, _ in observations]
        controlled = [(x, y, z) for x, y, z in observations if z is not None]
        cx, cy, cz = ([row[i] for row in controlled] for i in range(3))
        buckets = {}
        for label in ("0–15", "16–25", "26–40", "41+"):
            moves = [y for x, y, _ in observations if diagnostic_bucket(x) == label]
            # Log returns for all return statistics; convert the stated simple
            # 5%/8% move threshold to simple returns for threshold membership.
            buckets[label] = {
                "mean_abs_log_return": metric(mean(map(abs, moves)) if moves else None, len(moves)),
                "share_large_moves": metric(
                    mean(abs(math.expm1(y)) > threshold for y in moves)
                    if moves and threshold is not None else None,
                    len(moves) if threshold is not None else 0,
                ),
                "share_up_moves": metric(mean(y > 0 for y in moves) if moves else None, len(moves)),
            }
        output["horizons"][str(horizon)] = {
            "corr_forward_return": metric(correlation(xs, ys), len(xs)),
            "corr_forward_abs_return": metric(correlation(xs, list(map(abs, ys))), len(xs)),
            "partial_corr_forward_return": metric(partial_correlation(cx, cy, cz), len(cx)),
            "partial_corr_forward_abs_return": metric(
                partial_correlation(cx, list(map(abs, cy)), cz), len(cx)),
            "buckets": buckets,
        }
    return output


def scorecard(series, markets, variant, sanity_headlines=None):
    n = len(series)
    values = [row["geri"] for row in series]
    changes = [b - a for a, b in zip(values, values[1:])]
    weekends = [row["geri"] for row in series
                if date.fromisoformat(row["date"]).weekday() >= 5]
    weekdays = [row["geri"] for row in series
                if date.fromisoformat(row["date"]).weekday() < 5]
    ratio = mean(weekends) / mean(weekdays) if weekends and weekdays and mean(weekdays) else None
    active = [p for p in PILLARS if any(row[f"raw_{p}"] != 0 for row in series)]
    monthly_rows = defaultdict(list)
    for row in series:
        monthly_rows[row["date"][:7]].append(row)
    monthly = {}
    for month, rows in monthly_rows.items():
        types = Counter()
        for row in rows:
            types.update(row["n_by_type"])
        monthly[month] = {
            "active_pillar_ceiling_min": metric(
                min(r.get("active_pillar_ceiling", 0) for r in rows), len(rows)),
            "active_pillar_ceiling_max": metric(
                max(r.get("active_pillar_ceiling", 0) for r in rows), len(rows)),
            "high_impact_kept_share": metric(
                sum(r.get("high_impact_kept", r["n_by_type"].get("HIGH_IMPACT_EVENT", 0)) for r in rows)
                / sum(r.get("high_impact_available", r["n_by_type"].get("HIGH_IMPACT_EVENT", 0)) for r in rows)
                if sum(r.get("high_impact_available", r["n_by_type"].get("HIGH_IMPACT_EVENT", 0)) for r in rows) else None,
                sum(r.get("high_impact_available", r["n_by_type"].get("HIGH_IMPACT_EVENT", 0)) for r in rows)),
            "weighted_contributions": {
                p: metric(mean(row[f"norm_{p}"] * weight for row in rows), len(rows))
                for p, weight in zip(PILLARS, variant.weights)
            },
            "alert_counts": {key: metric(types[key], len(rows))
                             for key in sorted(set(types) | set(variant.accepted_types))},
        }
    counts = Counter(row["band"] for row in series)
    result = {
        "variant": variant.name, "start": series[0]["date"], "end": series[-1]["date"],
        "stability": {
            "mean_absolute_daily_change": metric(mean(map(abs, changes)) if changes else None, len(changes)),
            "share_abs_change_ge_10": metric(mean(abs(x) >= 10 for x in changes) if changes else None, len(changes)),
            "share_abs_change_ge_15": metric(mean(abs(x) >= 15 for x in changes) if changes else None, len(changes)),
            "lag1_autocorr_daily_changes": metric(correlation(changes[:-1], changes[1:]), max(0, len(changes) - 1)),
            "weekend_weekday_mean_ratio": metric(ratio, len(weekends) + len(weekdays)),
            "weekend_mean": metric(mean(weekends) if weekends else None, len(weekends)),
            "weekday_mean": metric(mean(weekdays) if weekdays else None, len(weekdays)),
            "days_at_zero": metric(sum(v == 0 for v in values), n),
            "days_below_8_alerts": metric(sum(row["n_alerts"] < 8 for row in series), n),
        },
        "coverage": {
            "monthly": monthly,
            "band_distribution": {band: metric(counts[band], n)
                                  for band in ("LOW", "MODERATE", "ELEVATED", "SEVERE", "CRITICAL")},
            "maximum": metric(max(values), n),
            "active_pillars": active,
            "theoretical_maximum_active_pillars": metric(
                round(100 * sum(weight for p, weight in zip(PILLARS, variant.weights) if p in active), 10), n),
        },
        "market_link": {name: market_metrics(series, rows, {"Brent": .05, "TTF": .08}.get(name))
                        for name, rows in markets.items()},
        "sanity_headlines": sanity_headlines or {},
    }
    return result


def formatted(item, percent=False):
    value, n = item["value"], item["n"]
    if value is None:
        rendered = "N/A"
    elif isinstance(value, int) and not percent:
        rendered = str(value)
    else:
        rendered = f"{value * 100 if percent else value:.4f}"
    return f"{rendered}{'%' if percent and value is not None else ''} (n={n})"


def markdown(result):
    lines = [
        f"# GERI Lab scorecard — {result['variant']}",
        f"\n**CONFIDENTIAL — internal.** {result['start']} through {result['end']}.",
        "\nDiagnostic only; not a forecast or evidence of trading edge.",
        "\n`n` counts available days, adjacent-day changes, paired observations or "
        "market outcomes as appropriate. Undefined statistics are N/A, never zero-filled.",
        "\n## Stability", "\n| Metric | Value |", "|---|---|",
    ]
    for key, item in result["stability"].items():
        lines.append(f"| {key} | {formatted(item, key.startswith('share_'))} |")
    coverage = result["coverage"]
    lines += [
        "\n## Coverage",
        f"\nMaximum: {formatted(coverage['maximum'])}. Active-pillar theoretical ceiling: "
        f"{formatted(coverage['theoretical_maximum_active_pillars'])}.",
        "\nThe ceiling is a structural 100 × sum(active weights), not a claim that "
        "all pillar maxima can coincide or that fallback scaling reaches that value.",
        "\n| Band | Days |", "|---|---|",
    ]
    for band, item in coverage["band_distribution"].items():
        lines.append(f"| {band} | {formatted(item)} |")
    lines += [
        "\n### Monthly weighted contributions (index points)",
        "\n| Month | H | R | A | C |", "|---|---|---|---|---|",
    ]
    for month, details in coverage["monthly"].items():
        lines.append("| " + month + " | " + " | ".join(
            formatted(details["weighted_contributions"][p]) for p in PILLARS) + " |")
    lines += ["\n### Monthly alert counts", "\n| Month | Type | Count (n = days) |", "|---|---|---|"]
    for month, details in coverage["monthly"].items():
        for kind, item in details["alert_counts"].items():
            lines.append(f"| {month} | {kind} | {formatted(item)} |")
    lines += [
        "\n### Point-in-time active-pillar ceiling and HIGH_IMPACT retention",
        "\nThe daily ceiling uses only raw components that varied in that day's prior "
        "baseline window (health exclusions applied per variant). It is not a hard "
        "cap during insufficient-history fallback. The legacy full-period nonzero "
        "pillar ceiling above must not be mistaken for this rolling ceiling.",
        "\n| Month | Rolling ceiling min | Rolling ceiling max | High-impact kept |",
        "|---|---|---|---|",
    ]
    for month, details in coverage["monthly"].items():
        lines.append(f"| {month} | {formatted(details['active_pillar_ceiling_min'])} | "
                     f"{formatted(details['active_pillar_ceiling_max'])} | "
                     f"{formatted(details['high_impact_kept_share'], True)} |")
    for day, groups in result.get("sanity_headlines", {}).items():
        lines.append(f"\n### {day} headline sanity check")
        lines.append("\nRanked by the original single-alert raw H contribution, then alert ID.")
        for group, items in groups.items():
            lines += [f"\nTop {len(items)} {group}", "\n| Alert ID | Headline | Source | Confidence |",
                      "|---|---|---|---|"]
            for item in items:
                headline = item["headline"].replace("|", "/").replace("\n", " ")
                lines.append(f"| {item['alert_id']} | {headline} | {item.get('source') or 'N/A'} | {item['confidence']} |")
    lines += [
        "\n## Market link",
        "\nWeekends and exact repeated closes are removed, without price interpolation. "
        "Equal weekday closes can be genuine; the requested repeat filter cannot "
        "distinguish those from fills. Horizons count remaining observations, which "
        "can span more calendar days than their label suggests.",
        "\nReturns are natural logs. Partial correlations regress both variables on "
        "an intercept and trailing 10-return population volatility, using only data "
        "known on the signal date. GERI is aligned on the retained price date; its "
        "full-day alert set may postdate that market's close, so these diagnostics "
        "are not an executable close-time strategy. Current/future UTC-day price "
        "snapshots are excluded to avoid unfinished daily outcomes. Outcomes may overlap; no "
        "significance or causal claim is made. Missing or future-unavailable outcomes are dropped.",
        "\nBuckets below are the requested diagnostic bins, not production risk bands. "
        "Large-move shares use absolute simple returns >5% for Brent and >8% for TTF. "
        "There is no specified VIX threshold, so its large-move share is N/A.",
    ]
    for market, details in result["market_link"].items():
        lines += [f"\n### {market}", f"\nCleaning: `{json.dumps(details['cleaning'], sort_keys=True)}`",
                  "\n| Horizon (retained sessions) | Corr return | Corr abs return | Partial return | Partial abs return |",
                  "|---|---|---|---|---|"]
        for horizon, stats in details["horizons"].items():
            keys = ("corr_forward_return", "corr_forward_abs_return",
                    "partial_corr_forward_return", "partial_corr_forward_abs_return")
            lines.append(f"| {horizon} | " + " | ".join(formatted(stats[k]) for k in keys) + " |")
        lines += ["\n| Horizon | GERI bucket | Mean forward abs log return | Large-move share | Up share |",
                  "|---|---|---|---|---|"]
        for horizon, stats in details["horizons"].items():
            for bucket, items in stats["buckets"].items():
                lines.append(f"| {horizon} | {bucket} | " + " | ".join(
                    formatted(items[key], True) for key in
                    ("mean_abs_log_return", "share_large_moves", "share_up_moves")) + " |")
    return "\n".join(lines) + "\n"


def write_scorecard(directory, result):
    (directory / "scorecard.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    (directory / "scorecard.md").write_text(markdown(result))
