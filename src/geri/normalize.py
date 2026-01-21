"""
GERI v1 Normalization Functions (Pure Functions)

Normalizes raw scores to 0-100 scale using rolling baselines.
"""
from src.geri.types import (
    GERIComponents,
    GERIResult,
    HistoricalBaseline,
    RiskBand,
    get_band,
    INDEX_ID,
    MODEL_VERSION,
    GERI_WEIGHTS,
)
from datetime import date
from typing import Optional, List


FALLBACK_HIGH_IMPACT_MAX = 25.0
FALLBACK_REGIONAL_SPIKE_MAX = 500.0
FALLBACK_ASSET_RISK_MAX = 500.0
FALLBACK_REGION_CONCENTRATION_MAX = 100.0

MIN_HISTORY_DAYS = 14


def normalize_value(raw: float, min_val: float, max_val: float) -> float:
    """
    Normalize a raw value to 0-100 using min/max.
    Handles edge cases per spec.
    """
    if max_val == min_val:
        if raw == 0:
            return 0.0
        else:
            return 50.0
    
    normalized = ((raw - min_val) / (max_val - min_val)) * 100
    return max(0.0, min(100.0, normalized))


def normalize_components(
    components: GERIComponents,
    baseline: HistoricalBaseline
) -> GERIComponents:
    """
    Apply normalization to component scores.
    Uses baseline if sufficient history, else fallback values.
    """
    if baseline.days_count < MIN_HISTORY_DAYS:
        components.insufficient_history = True
        hi_min, hi_max = 0, max(FALLBACK_HIGH_IMPACT_MAX, components.high_impact_score * 1.5 or FALLBACK_HIGH_IMPACT_MAX)
        rs_min, rs_max = 0, max(FALLBACK_REGIONAL_SPIKE_MAX, components.regional_spike_score * 1.5 or FALLBACK_REGIONAL_SPIKE_MAX)
        ar_min, ar_max = 0, max(FALLBACK_ASSET_RISK_MAX, components.asset_risk_score * 1.5 or FALLBACK_ASSET_RISK_MAX)
        rc_min, rc_max = 0, FALLBACK_REGION_CONCENTRATION_MAX
    else:
        components.insufficient_history = False
        hi_min, hi_max = baseline.high_impact_min, baseline.high_impact_max
        rs_min, rs_max = baseline.regional_spike_min, baseline.regional_spike_max
        ar_min, ar_max = baseline.asset_risk_min, baseline.asset_risk_max
        rc_min, rc_max = baseline.region_concentration_min, baseline.region_concentration_max
    
    components.norm_high_impact = normalize_value(
        components.high_impact_score, hi_min, hi_max
    )
    components.norm_regional_spike = normalize_value(
        components.regional_spike_score, rs_min, rs_max
    )
    components.norm_asset_risk = normalize_value(
        components.asset_risk_score, ar_min, ar_max
    )
    components.norm_region_concentration = normalize_value(
        components.region_concentration_score_raw, rc_min, rc_max
    )
    
    return components


def calculate_geri_value(components: GERIComponents) -> int:
    """
    Calculate final GERI index value (0-100) from normalized components.
    
    GERI = 0.40 * norm_high_impact
         + 0.25 * norm_regional_spike
         + 0.20 * norm_asset_risk
         + 0.15 * norm_region_concentration
    """
    weighted_sum = (
        GERI_WEIGHTS['high_impact'] * components.norm_high_impact +
        GERI_WEIGHTS['regional_spike'] * components.norm_regional_spike +
        GERI_WEIGHTS['asset_risk'] * components.norm_asset_risk +
        GERI_WEIGHTS['region_concentration'] * components.norm_region_concentration
    )
    
    value = int(round(weighted_sum))
    return max(0, min(100, value))


def calculate_trends(
    current_value: int,
    previous_values: List[int]
) -> tuple:
    """
    Calculate trend_1d and trend_7d.
    
    trend_1d = value - previous day value
    trend_7d = value - avg(previous 7 days)
    """
    trend_1d = None
    trend_7d = None
    
    if len(previous_values) >= 1:
        trend_1d = current_value - previous_values[0]
    
    if len(previous_values) >= 7:
        avg_7d = sum(previous_values[:7]) / 7
        trend_7d = int(round(current_value - avg_7d))
    
    return trend_1d, trend_7d


def build_result(
    index_date: date,
    value: int,
    components: GERIComponents,
    trend_1d: Optional[int],
    trend_7d: Optional[int]
) -> GERIResult:
    """Build the final GERI result object."""
    return GERIResult(
        index_id=INDEX_ID,
        index_date=index_date,
        value=value,
        band=get_band(value),
        trend_1d=trend_1d,
        trend_7d=trend_7d,
        components=components,
        model_version=MODEL_VERSION,
    )
