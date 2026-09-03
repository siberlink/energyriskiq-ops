"""Interpretable historical-analogue forecasts for GERI Live price risk.

The model uses standardized market/risk features and distance-weighted nearest
neighbours. Forecasts are probabilistic and include sample/quality metadata;
they are not trading recommendations.
"""

import math
import logging
import time
from datetime import date, datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from src.db.db import execute_query


MODEL_NAME = "GERI Price-Risk Historical Analogue Model"
MODEL_VERSION = "1.0"
MIN_SAMPLES = 8
SIGNIFICANT_MOVE_THRESHOLD = 2.0
FORECAST_CACHE_SECONDS = 300
_forecast_cache: Dict[str, Any] = {"key": None, "expires_at": 0.0, "value": None}
logger = logging.getLogger(__name__)


def _number(value: Any) -> Optional[float]:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _date_key(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.date().isoformat() if isinstance(value, datetime) else value.isoformat()
    return str(value)[:10]


def _series(rows: Iterable[Dict[str, Any]], field: str) -> Dict[str, float]:
    output = {}
    for row in rows:
        value = _number(row.get(field))
        if value is not None:
            output[_date_key(row.get("date"))] = value
    return output


def _returns(values: Dict[str, float]) -> Dict[str, float]:
    dates = sorted(values)
    output = {}
    for index in range(1, len(dates)):
        previous = values[dates[index - 1]]
        current = values[dates[index]]
        if previous:
            output[dates[index]] = (current - previous) / previous * 100
    return output


def _band_index(value: float) -> int:
    if value >= 81:
        return 4
    if value >= 61:
        return 3
    if value >= 41:
        return 2
    if value >= 21:
        return 1
    return 0


def _mean(values: List[float]) -> Optional[float]:
    return sum(values) / len(values) if values else None


def _weighted_mean(pairs: List[Tuple[float, float]]) -> Optional[float]:
    total_weight = sum(weight for _, weight in pairs)
    if not pairs or not total_weight:
        return None
    return sum(value * weight for value, weight in pairs) / total_weight


def _weighted_spread(pairs: List[Tuple[float, float]], center: float) -> float:
    total_weight = sum(weight for _, weight in pairs)
    if not pairs or not total_weight:
        return 0.0
    variance = sum(weight * (value - center) ** 2 for value, weight in pairs) / total_weight
    return math.sqrt(max(variance, 0.0))


def _probability(pairs: List[Tuple[float, float]]) -> Optional[float]:
    if not pairs:
        return None
    total_weight = sum(weight for _, weight in pairs)
    successes = sum(value * weight for value, weight in pairs)
    # A weak Beta(1, 1) prior prevents false 0%/100% certainty while allowing
    # the historical analogues to dominate as their effective weight grows.
    return round((successes + 1.0) / (total_weight + 2.0) * 100, 1)


def _rounded(value: Optional[float], digits: int = 1) -> Optional[float]:
    return round(value, digits) if value is not None else None


def _confidence(sample_size: int, validation: Optional[Dict[str, Any]] = None) -> str:
    if sample_size < MIN_SAMPLES:
        return "insufficient"
    if validation:
        validated = [
            result for result in validation.values()
            if result.get("observations", 0) >= 20
            and result.get("accuracy_pct") is not None
            and result.get("baseline_accuracy_pct") is not None
        ]
        if validated:
            average_lift = sum(
                result["accuracy_pct"] - result["baseline_accuracy_pct"]
                for result in validated
            ) / len(validated)
            all_probability_improved = all(
                result.get("brier_score") is not None
                and result.get("baseline_brier_score") is not None
                and result["brier_score"] < result["baseline_brier_score"]
                for result in validated
            )
            if average_lift < 0 or not all_probability_improved:
                return "low"
            if sample_size >= 120 and all(
                result["accuracy_pct"] - result["baseline_accuracy_pct"] >= 5
                for result in validated
            ):
                return "high"
    if sample_size >= 45:
        return "medium"
    return "low"


def _latest_aligned_feature(
    oil_rows: List[Dict[str, Any]],
    ttf_rows: List[Dict[str, Any]],
    vix_rows: List[Dict[str, Any]],
    geri_rows: List[Dict[str, Any]],
) -> Tuple[Optional[List[float]], Optional[str]]:
    """Return the latest completed daily feature vector used by model training."""
    series = {
        "brent": _series(oil_rows, "brent_price"),
        "wti": _series(oil_rows, "wti_price"),
        "ttf": _series(ttf_rows, "ttf_price"),
        "vix": _series(vix_rows, "vix_close"),
        "geri": _series(geri_rows, "value"),
    }
    returns = {key: _returns(values) for key, values in series.items()}
    current_utc_date = datetime.now(timezone.utc).date().isoformat()
    common_dates = sorted(
        (
            value for value in set.intersection(*(set(values) for values in series.values()))
            if value < current_utc_date
        ),
        reverse=True,
    )
    for current_date in common_dates:
        if all(returns[key].get(current_date) is not None for key in series):
            return [
                series["geri"][current_date],
                returns["geri"][current_date],
                returns["brent"][current_date],
                returns["wti"][current_date],
                returns["ttf"][current_date],
                returns["vix"][current_date],
            ], current_date
    return None, None


def _training_states(
    oil_rows: List[Dict[str, Any]],
    ttf_rows: List[Dict[str, Any]],
    vix_rows: List[Dict[str, Any]],
    geri_rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    brent = _series(oil_rows, "brent_price")
    wti = _series(oil_rows, "wti_price")
    ttf = _series(ttf_rows, "ttf_price")
    vix = _series(vix_rows, "vix_close")
    geri = _series(geri_rows, "value")
    returns = {
        "brent": _returns(brent),
        "wti": _returns(wti),
        "ttf": _returns(ttf),
        "vix": _returns(vix),
        "geri": _returns(geri),
    }
    common_dates = sorted(set(brent) & set(wti) & set(ttf) & set(vix) & set(geri))
    states = []

    for index in range(1, len(common_dates) - 3):
        current_date = common_dates[index]
        future_dates = common_dates[index + 1:index + 4]
        feature_returns = [
            returns[key].get(current_date)
            for key in ("geri", "brent", "wti", "ttf", "vix")
        ]
        if len(future_dates) != 3 or any(value is None for value in feature_returns):
            continue

        features = [
            geri[current_date],
            returns["geri"][current_date],
            returns["brent"][current_date],
            returns["wti"][current_date],
            returns["ttf"][current_date],
            returns["vix"][current_date],
        ]
        brent_1d = returns["brent"].get(future_dates[0])
        brent_3d = (
            (brent[future_dates[-1]] - brent[current_date]) / brent[current_date] * 100
            if brent.get(current_date) and brent.get(future_dates[-1]) else None
        )

        future_ttf_dates = future_dates
        ttf_1d = returns["ttf"].get(future_ttf_dates[0])
        ttf_3d = (
            (ttf[future_ttf_dates[-1]] - ttf[current_date]) / ttf[current_date] * 100
            if current_date in ttf and future_ttf_dates and ttf[current_date] else None
        )
        future_geri = [geri[candidate] for candidate in future_dates]
        current_band = _band_index(geri[current_date])
        price_changes = [returns[key][current_date] for key in ("brent", "wti", "ttf")]
        average_price_change = _mean(price_changes) or 0.0
        geri_change = returns["geri"].get(current_date, 0.0)

        states.append({
            "date": current_date,
            "features": features,
            "outcomes": {
                "brent_up_3d": float(brent_3d > 0) if brent_3d is not None else None,
                "brent_up_1d": float(brent_1d > 0) if brent_1d is not None else None,
                "brent_1d": brent_1d,
                "brent_3d": brent_3d,
                "ttf_up_1d": float(ttf_1d > 0) if ttf_1d is not None else None,
                "ttf_1d": ttf_1d,
                "ttf_3d": ttf_3d,
                "elevated_1d": float(bool(future_geri and future_geri[0] >= 41)),
                "elevated_2d": float(any(value >= 41 for value in future_geri[:2])),
                "elevated_3d": float(any(value >= 41 for value in future_geri[:3])),
                "higher_band_3d": float(any(_band_index(value) > current_band for value in future_geri)),
                "significant_move_3d": float(
                    abs(brent_3d or 0.0) >= SIGNIFICANT_MOVE_THRESHOLD
                    or abs(ttf_3d or 0.0) >= SIGNIFICANT_MOVE_THRESHOLD
                ),
                "underpriced": float(abs(geri_change) > 5 and abs(average_price_change) < 1),
            },
        })
    return states


def _nearest(states: List[Dict[str, Any]], current: List[float]) -> List[Tuple[Dict[str, Any], float]]:
    if not states:
        return []
    columns = list(zip(*(state["features"] for state in states)))
    means = [sum(column) / len(column) for column in columns]
    spreads = [
        math.sqrt(sum((value - means[index]) ** 2 for value in column) / len(column)) or 1.0
        for index, column in enumerate(columns)
    ]
    ranked = []
    for state in states:
        distance = math.sqrt(sum(
            ((state["features"][index] - current[index]) / spreads[index]) ** 2
            for index in range(len(current))
        ))
        ranked.append((state, 1.0 / (0.25 + distance)))
    ranked.sort(key=lambda pair: pair[1], reverse=True)
    neighbour_count = min(25, max(8, int(math.sqrt(len(states)) * 2)))
    return ranked[:neighbour_count]


def _outcome_pairs(
    neighbours: List[Tuple[Dict[str, Any], float]],
    key: str,
) -> List[Tuple[float, float]]:
    return [
        (state["outcomes"][key], weight)
        for state, weight in neighbours
        if state["outcomes"].get(key) is not None
    ]


def _direction_forecast(
    neighbours: List[Tuple[Dict[str, Any], float]],
    return_key: str,
    direction_key: str,
) -> Dict[str, Any]:
    return_pairs = _outcome_pairs(neighbours, return_key)
    expected = _weighted_mean(return_pairs)
    probability_up = _probability(_outcome_pairs(neighbours, direction_key))
    if expected is None:
        return {
            "direction": "unavailable",
            "probability": None,
            "expected_change_pct": None,
            "range_low_pct": None,
            "range_high_pct": None,
        }
    spread = _weighted_spread(return_pairs, expected)
    direction = "higher" if expected > 0.1 else "lower" if expected < -0.1 else "range-bound"
    probability = probability_up
    if direction == "lower" and probability_up is not None:
        probability = round(100 - probability_up, 1)
    elif direction == "range-bound":
        probability = round(max(probability_up or 50, 100 - (probability_up or 50)), 1)
    return {
        "direction": direction,
        "probability": probability,
        "expected_change_pct": _rounded(expected),
        "range_low_pct": _rounded(expected - 1.28 * spread),
        "range_high_pct": _rounded(expected + 1.28 * spread),
    }


def _walk_forward_validation(states: List[Dict[str, Any]], target_key: str) -> Dict[str, Any]:
    """Validate classification forecasts using only observations available before each test date."""
    predictions = []
    first_test = max(MIN_SAMPLES, len(states) - 60)
    for index in range(first_test, len(states)):
        actual = states[index]["outcomes"].get(target_key)
        if actual is None:
            continue
        # Three-observation purge: no training label may overlap the test
        # forecast window or use an outcome unavailable at the test timestamp.
        training_end = index - 3
        if training_end < MIN_SAMPLES:
            continue
        neighbours = _nearest(states[:training_end], states[index]["features"])
        probability = _probability(_outcome_pairs(neighbours, target_key))
        if probability is not None:
            training_actuals = [
                state["outcomes"][target_key]
                for state in states[:training_end]
                if state["outcomes"].get(target_key) is not None
            ]
            if not training_actuals:
                continue
            baseline_probability = sum(training_actuals) / len(training_actuals)
            predictions.append((probability / 100, actual, baseline_probability))
    if not predictions:
        return {
            "observations": 0,
            "accuracy_pct": None,
            "brier_score": None,
            "baseline_accuracy_pct": None,
            "baseline_brier_score": None,
        }
    accuracy = sum((probability >= 0.5) == bool(actual) for probability, actual, _ in predictions) / len(predictions)
    brier = sum((probability - actual) ** 2 for probability, actual, _ in predictions) / len(predictions)
    baseline_correct = sum(
        (baseline_probability >= 0.5) == bool(actual)
        for _, actual, baseline_probability in predictions
    )
    baseline_brier = sum(
        (baseline_probability - actual) ** 2
        for _, actual, baseline_probability in predictions
    ) / len(predictions)
    return {
        "observations": len(predictions),
        "accuracy_pct": round(accuracy * 100, 1),
        "brier_score": round(brier, 3),
        "baseline_accuracy_pct": round(baseline_correct / len(predictions) * 100, 1),
        "baseline_brier_score": round(baseline_brier, 3),
    }


def _empty_forecast(
    sample_size: int,
    history_start: Optional[str],
    history_end: Optional[str],
    message: Optional[str] = None,
    status: str = "insufficient_data",
) -> Dict[str, Any]:
    return {
        "status": status,
        "model_name": MODEL_NAME,
        "model_version": MODEL_VERSION,
        "sample_size": sample_size,
        "confidence": "insufficient",
        "history_start": history_start,
        "history_end": history_end,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "message": message or f"At least {MIN_SAMPLES} aligned historical observations are required.",
    }


def build_price_risk_forecast(
    oil_rows: List[Dict[str, Any]],
    ttf_rows: List[Dict[str, Any]],
    vix_rows: List[Dict[str, Any]],
    geri_rows: List[Dict[str, Any]],
    current_signals: List[Dict[str, Any]],
    geri_value: float,
    geri_trend_pct: float,
) -> Dict[str, Any]:
    states = _training_states(oil_rows, ttf_rows, vix_rows, geri_rows)
    history_dates = [state["date"] for state in states]
    history_start = min(history_dates) if history_dates else None
    history_end = max(history_dates) if history_dates else None
    if len(states) < MIN_SAMPLES:
        return _empty_forecast(len(states), history_start, history_end)

    current_feature, forecast_as_of = _latest_aligned_feature(
        oil_rows, ttf_rows, vix_rows, geri_rows
    )
    if current_feature is None:
        return _empty_forecast(
            len(states),
            history_start,
            history_end,
            message="A completed daily observation for all model inputs is required.",
            status="unavailable_aligned_data",
        )
    model_geri_value = current_feature[0]
    model_geri_trend_pct = current_feature[1]
    neighbours = _nearest(states, current_feature)
    brent_rise = _probability(_outcome_pairs(neighbours, "brent_up_3d"))
    brent_fall = round(100 - brent_rise, 1) if brent_rise is not None else None
    brent_next = _direction_forecast(neighbours, "brent_1d", "brent_up_1d")
    ttf_next = _direction_forecast(neighbours, "ttf_1d", "ttf_up_1d")
    elevated = {
        "elevated_24h": 100.0 if model_geri_value >= 41 else _probability(_outcome_pairs(neighbours, "elevated_1d")),
        "elevated_48h": 100.0 if model_geri_value >= 41 else _probability(_outcome_pairs(neighbours, "elevated_2d")),
        "elevated_72h": 100.0 if model_geri_value >= 41 else _probability(_outcome_pairs(neighbours, "elevated_3d")),
    }
    significant = _probability(_outcome_pairs(neighbours, "significant_move_3d"))
    higher_band = _probability(_outcome_pairs(neighbours, "higher_band_3d"))
    underpriced = _probability(_outcome_pairs(neighbours, "underpriced"))

    major_states = [
        state for state in states
        if abs(state["features"][1]) >= 10
        and (model_geri_trend_pct == 0 or state["features"][1] * model_geri_trend_pct >= 0)
    ]
    major_brent = _mean([
        state["outcomes"]["brent_3d"] for state in major_states
        if state["outcomes"]["brent_3d"] is not None
    ])
    major_ttf = _mean([
        state["outcomes"]["ttf_3d"] for state in major_states
        if state["outcomes"]["ttf_3d"] is not None
    ])
    validation = {
        "brent_direction": _walk_forward_validation(states, "brent_up_3d"),
        "ttf_direction": _walk_forward_validation(states, "ttf_up_1d"),
    }
    confidence = _confidence(len(states), validation)
    validated_results = [
        result for result in validation.values()
        if result.get("observations", 0) >= 40
        and result.get("accuracy_pct") is not None
        and result.get("baseline_accuracy_pct") is not None
    ]
    average_validation_lift = (
        sum(
            result["accuracy_pct"] - result["baseline_accuracy_pct"]
            for result in validated_results
        ) / len(validated_results)
        if validated_results else None
    )
    every_target_validated = len(validated_results) == len(validation)
    every_target_positive = all(
        result["accuracy_pct"] > result["baseline_accuracy_pct"]
        and result["brier_score"] < result["baseline_brier_score"]
        for result in validated_results
    )
    validation_status = "validated_edge" if every_target_validated and every_target_positive else "underperforming_baseline"
    underpriced_label = (
        "elevated" if (underpriced or 0) >= 65
        else "watch" if (underpriced or 0) >= 45
        else "limited"
    )
    direction_phrase = (
        f"Brent is biased {brent_next['direction']} with an expected next-session move "
        f"of {brent_next['expected_change_pct']:+.1f}%."
        if brent_next["expected_change_pct"] is not None
        else "The Brent direction forecast is unavailable because aligned returns are sparse."
    )
    regime_probability = elevated["elevated_72h"]
    executive_summary = (
        f"The model identifies a {brent_rise:.1f}% probability of Brent finishing higher "
        f"over the next one to three sessions. {direction_phrase} "
        f"The probability of GERI reaching or remaining at ELEVATED or above within 72 hours "
        f"is {regime_probability:.1f}%."
    )
    market_interpretation = (
        f"Current conditions are closest to {len(neighbours)} historical analogues. "
        f"The model assigns a {significant:.1f}% probability to an oil or gas move of at least "
        f"{SIGNIFICANT_MOVE_THRESHOLD:.1f}% over the next three sessions, while the estimated "
        f"probability that current risk is underpriced is {underpriced:.1f}%."
    )
    trader_implications = (
        "Use these probabilities as a positioning and hedging input rather than a directional "
        "instruction. Compare the forecast with liquidity, curve structure, options-implied "
        "volatility, inventory data, and upcoming event risk before acting."
    )
    methodology = (
        "Distance-weighted nearest-neighbour forecasting on standardized daily GERI level/change, "
        "Brent, WTI, TTF and VIX changes. Outcomes are measured over the following one to three "
        "aligned trading observations. Probabilities use mild Bayesian shrinkage to avoid false "
        "certainty, and the displayed range is an 80% analogue outcome interval."
    )
    brent_validation = validation["brent_direction"]
    ttf_validation = validation["ttf_direction"]
    model_validation = (
        f"Walk-forward validation used {brent_validation['observations']} unseen Brent periods "
        f"and {ttf_validation['observations']} unseen TTF periods. Brent directional accuracy was "
        f"{brent_validation['accuracy_pct']}% versus a {brent_validation['baseline_accuracy_pct']}% "
        f"majority baseline; TTF directional accuracy was {ttf_validation['accuracy_pct']}% versus "
        f"a {ttf_validation['baseline_accuracy_pct']}% baseline. Brier scores were "
        f"{brent_validation['brier_score']} for Brent versus "
        f"{brent_validation['baseline_brier_score']}, and "
        f"{ttf_validation['brier_score']} for TTF versus "
        f"{ttf_validation['baseline_brier_score']} (lower is better)."
    )
    limitations = (
        "Forecasts are probabilistic, not guarantees. Results may be unstable when history is "
        "short, market structure changes, source dates are missing, or an unprecedented event "
        "has no comparable historical analogue. Correlation and analogue similarity do not prove causation. "
        "A low confidence rating means walk-forward accuracy did not consistently exceed the simple "
        "majority-direction baseline; treat those outputs as research context, not an actionable edge."
    )

    return {
        "status": "ready" if validation_status == "validated_edge" else "research_only",
        "model_name": MODEL_NAME,
        "model_version": MODEL_VERSION,
        "sample_size": len(states),
        "analogue_count": len(neighbours),
        "confidence": confidence,
        "validation_status": validation_status,
        "validation_lift_pct": _rounded(average_validation_lift),
        "history_start": history_start,
        "history_end": history_end,
        "forecast_as_of": forecast_as_of,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "brent_1_3d": {
            "rise_probability": brent_rise,
            "fall_probability": brent_fall,
        },
        "risk_regime": elevated,
        "brent_next_day": brent_next,
        "ttf_next_day": ttf_next,
        "significant_move": {
            "probability": significant,
            "threshold_pct": SIGNIFICANT_MOVE_THRESHOLD,
            "horizon_days": 3,
        },
        "higher_risk_band": {
            "probability": higher_band,
            "horizon_hours": 72,
        },
        "underpriced_risk": {
            "probability": underpriced,
            "classification": underpriced_label,
        },
        "major_geri_reaction": {
            "expected_brent_change_pct": _rounded(major_brent),
            "expected_ttf_change_pct": _rounded(major_ttf),
            "horizon_days": 3,
            "sample_size": len(major_states),
        },
        "validation": validation,
        "analysis": {
            "executive_summary": executive_summary,
            "market_interpretation": market_interpretation,
            "risk_regime_outlook": (
                f"ELEVATED-or-higher probability: {elevated['elevated_24h']:.1f}% at 24h, "
                f"{elevated['elevated_48h']:.1f}% at 48h, and "
                f"{elevated['elevated_72h']:.1f}% at 72h."
            ),
            "trader_implications": trader_implications,
            "methodology": methodology,
            "model_validation": model_validation,
            "limitations": limitations,
        },
    }


def get_price_risk_ml_analysis(
    current_signals: List[Dict[str, Any]],
    geri_value: float,
    geri_trend_pct: float,
) -> Dict[str, Any]:
    """Load aligned history and return a non-fatal forecast payload."""
    cache_key = "latest_completed_daily_observation"
    now = time.monotonic()
    if (
        _forecast_cache["key"] == cache_key
        and _forecast_cache["expires_at"] > now
        and _forecast_cache["value"] is not None
    ):
        return _forecast_cache["value"]

    try:
        oil_rows = execute_query(
            "SELECT date, brent_price, wti_price FROM oil_price_snapshots "
            "ORDER BY date DESC LIMIT 750"
        ) or []
        ttf_rows = execute_query(
            "SELECT date, ttf_price FROM ttf_gas_snapshots "
            "ORDER BY date DESC LIMIT 750"
        ) or []
        vix_rows = execute_query(
            "SELECT date, vix_close FROM vix_snapshots WHERE vix_close IS NOT NULL "
            "ORDER BY date DESC LIMIT 750"
        ) or []
        geri_rows = execute_query(
            """SELECT date, value FROM (
                SELECT DISTINCT ON (computed_at::date)
                    computed_at::date AS date, value
                FROM geri_live
                ORDER BY computed_at::date DESC, computed_at DESC
            ) daily
            ORDER BY date DESC LIMIT 750"""
        ) or []
        forecast = build_price_risk_forecast(
            oil_rows=oil_rows,
            ttf_rows=ttf_rows,
            vix_rows=vix_rows,
            geri_rows=geri_rows,
            current_signals=current_signals,
            geri_value=geri_value,
            geri_trend_pct=geri_trend_pct,
        )
        _forecast_cache.update({
            "key": cache_key,
            "expires_at": now + FORECAST_CACHE_SECONDS,
            "value": forecast,
        })
        return forecast
    except Exception as error:
        logger.exception("Price-risk forecast generation failed")
        return {
            "status": "unavailable",
            "model_name": MODEL_NAME,
            "model_version": MODEL_VERSION,
            "sample_size": 0,
            "confidence": "unavailable",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "message": "Forecast data is temporarily unavailable.",
        }