"""
RERI/EERI Normalization Logic

Handles rolling normalization and fallback caps for early days.
"""
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from src.reri.types import HistoricalBaseline, NORMALIZATION_CAPS


@dataclass
class NormalizationContext:
    """Context for normalization with history awareness."""
    days_of_history: int = 0
    use_rolling: bool = False
    baseline: Optional[HistoricalBaseline] = None


def get_fallback_caps() -> Dict[str, float]:
    """
    Get fallback normalization caps for early days (before rolling is available).
    These are conservative estimates based on expected data ranges.
    """
    return NORMALIZATION_CAPS.copy()


def compute_rolling_baseline(
    historical_values: List[Dict[str, float]],
    days: int = 90
) -> HistoricalBaseline:
    """
    Compute rolling baseline from historical component values.
    
    Args:
        historical_values: List of dicts with component values per day
        days: Rolling window size (default 90)
    
    Returns:
        HistoricalBaseline with min/max for each component
    """
    baseline = HistoricalBaseline()
    
    if not historical_values:
        baseline.days_count = 0
        return baseline
    
    recent = historical_values[-days:] if len(historical_values) > days else historical_values
    baseline.days_count = len(recent)
    
    if not recent:
        return baseline
    
    severity_vals = [d.get('severity_pressure', 0) for d in recent]
    high_impact_vals = [d.get('high_impact_count', 0) for d in recent]
    asset_vals = [d.get('asset_overlap', 0) for d in recent]
    velocity_vals = [d.get('velocity', 0) for d in recent]
    
    baseline.severity_min = min(severity_vals) if severity_vals else 0
    baseline.severity_max = max(severity_vals) if severity_vals else NORMALIZATION_CAPS['severity_pressure']
    
    baseline.high_impact_min = min(high_impact_vals) if high_impact_vals else 0
    baseline.high_impact_max = max(high_impact_vals) if high_impact_vals else NORMALIZATION_CAPS['high_impact_count']
    
    baseline.asset_overlap_min = min(asset_vals) if asset_vals else 0
    baseline.asset_overlap_max = max(asset_vals) if asset_vals else NORMALIZATION_CAPS['asset_overlap']
    
    baseline.velocity_min = min(velocity_vals) if velocity_vals else -10
    baseline.velocity_max = max(velocity_vals) if velocity_vals else 10
    
    return baseline


def normalize_with_baseline(
    value: float,
    baseline_min: float,
    baseline_max: float,
    fallback_cap: float
) -> float:
    """
    Normalize a value using rolling baseline or fallback cap.
    
    Args:
        value: Raw value to normalize
        baseline_min: Historical minimum
        baseline_max: Historical maximum
        fallback_cap: Fallback cap if baseline range is too small
    
    Returns:
        Normalized value between 0 and 1
    """
    range_val = baseline_max - baseline_min
    
    if range_val < 1.0:
        return min(1.0, max(0.0, value / fallback_cap))
    
    normalized = (value - baseline_min) / range_val
    return min(1.0, max(0.0, normalized))


def should_use_rolling_normalization(days_of_history: int) -> bool:
    """
    Determine if we should use rolling normalization based on history.
    
    - Days 1-14: Use fallback caps only
    - Days 15-29: Transitional (still use fallback for stability)
    - Days 30+: Use rolling normalization
    """
    return days_of_history >= 30


def get_normalization_context(days_of_history: int) -> NormalizationContext:
    """
    Get normalization context based on available history.
    """
    return NormalizationContext(
        days_of_history=days_of_history,
        use_rolling=should_use_rolling_normalization(days_of_history),
        baseline=None,
    )
