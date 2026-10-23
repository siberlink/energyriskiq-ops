"""Recorded historical proof for the fixed +40% GERI sales illustration."""
from datetime import date, timedelta
from math import isfinite


def _positive(value):
    return isinstance(value, (int, float)) and isfinite(value) and value > 0


def select_sales_analog(rows, episodes):
    """Rank completed same-direction episodes by similarity, then recency.

    Returns use calendar-day targets, never history-array offsets. For weekends
    and holidays, use the first recorded session on/after the target (max 4 days).
    """
    prices = {}
    for row in rows:
        if _positive(row.get("brent")):
            day = date.fromisoformat(str(row["date"])[:10])
            prices[day] = float(row["brent"])

    def observation(target):
        for offset in range(5):
            day = target + timedelta(days=offset)
            if day in prices:
                return day, prices[day]
        return None

    candidates = []
    for episode in episodes:
        shift = episode.get("geri_shift_pct")
        if not _positive(shift):
            continue
        difference = abs(shift - 40)
        score = min(97, max(0, int(round(100 - min(difference, 100) * .55))))
        if score < 55:
            continue
        start = date.fromisoformat(episode["start_date"])
        peak = date.fromisoformat(episode["peak_date"])
        before = observation(start)
        at_peak = observation(peak)
        week = observation(peak + timedelta(days=7))
        month = observation(peak + timedelta(days=30))
        if not all((before, at_peak, week, month)):
            continue
        if before[0] >= at_peak[0]:
            continue
        base_price, peak_price = before[1], at_peak[1]
        pct = lambda price, base: round((price / base - 1) * 100, 1)
        candidates.append({
            **episode,
            "match_pct": score,
            "brent_before": round(base_price, 2),
            "brent_at_peak": round(peak_price, 2),
            "move_to_peak_pct": pct(peak_price, base_price),
            "move_7d_pct": pct(week[1], peak_price),
            "move_30d_pct": pct(month[1], peak_price),
            "price_observation_dates": {
                "before": before[0].isoformat(), "peak": at_peak[0].isoformat(),
                "7d": week[0].isoformat(), "30d": month[0].isoformat(),
            },
            "similarity_explanation": (
                f"Illustrated GERI shift: +40%; recorded episode: +{shift}%. "
                "Match is a magnitude-similarity heuristic, not a prediction probability."
            ),
        })
    candidates.sort(key=lambda item: (item["match_pct"], item["peak_date"]), reverse=True)
    return candidates[0] if candidates else None


def load_sales_analog():
    # Reuse the engine's recorded-history cache; no model/API generation occurs.
    from src.api.brent_forecast_routes import _load_history, _mine_episodes
    rows = _load_history()
    if not rows:
        raise ValueError("Recorded GERI and Brent history is unavailable")
    analog = select_sales_analog(rows, _mine_episodes())
    return {
        "success": True, "analog": analog,
        "as_of": max(str(row["date"])[:10] for row in rows),
        "methodology": (
            "Recorded GERI and Brent daily history. Completed rising-GERI episodes "
            "ranked by similarity to the illustrated +40% GERI shift; newest wins ties. "
            "7D/30D moves are measured from the Brent quote at the GERI peak, using "
            "the first recorded session on/after the calendar-day target within 4 days. "
            "GERI peak is not necessarily the Brent price maximum. Similarity is a "
            "heuristic, not predictive validation."
        ),
    }
