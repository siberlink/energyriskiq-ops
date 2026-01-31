"""
EERI Service Layer

Orchestrates EERI computation workflow.
"""
import logging
from datetime import date, datetime
from typing import Optional

from src.reri import ENABLE_EERI
from src.reri.types import (
    EERI_INDEX_ID,
    MODEL_VERSION,
    RERIResult,
    EERIComponents,
    RERIComponents,
    get_band,
)
from src.reri.compute import (
    filter_alerts_by_region,
    compute_reri_components,
    compute_reri_value,
    compute_eeri_components,
    compute_eeri_value,
    extract_top_drivers,
    generate_interpretation,
)
from src.reri.repo import (
    fetch_alerts_for_date,
    fetch_historical_severity_values,
    fetch_previous_values,
    compute_trends,
    save_reri_result,
    get_latest_reri,
    count_days_of_history,
    fetch_historical_component_values,
)
from src.reri.normalize import (
    should_use_rolling_normalization,
    compute_rolling_baseline,
)

logger = logging.getLogger(__name__)


def compute_eeri_for_date(
    target_date: date,
    save: bool = True,
    force: bool = False
) -> Optional[RERIResult]:
    """
    Compute EERI (Europe Energy Risk Index) for a specific date.
    
    Args:
        target_date: Date to compute EERI for
        save: Whether to save result to database
        force: Whether to overwrite existing result
    
    Returns:
        RERIResult or None if feature is disabled or already exists (and not force)
    """
    if not ENABLE_EERI:
        logger.info("EERI is disabled (ENABLE_EERI=false)")
        return None
    
    from src.reri.repo import get_reri_for_date
    existing = get_reri_for_date(EERI_INDEX_ID, target_date)
    if existing and not force:
        logger.info(f"EERI for {target_date} already exists (skipped). Use force=True to overwrite.")
        return None
    
    logger.info(f"Computing EERI for {target_date} (force={force})")
    
    all_alerts = fetch_alerts_for_date(target_date)
    logger.info(f"Fetched {len(all_alerts)} total alerts for {target_date}")
    
    europe_alerts = filter_alerts_by_region(all_alerts, 'europe')
    logger.info(f"Filtered to {len(europe_alerts)} Europe alerts")
    
    historical_s = fetch_historical_severity_values('europe', target_date, days=3)
    
    days_history = count_days_of_history(EERI_INDEX_ID)
    use_rolling = should_use_rolling_normalization(days_history)
    baseline_caps = None
    
    if use_rolling:
        historical_components = fetch_historical_component_values('europe', target_date, days=90)
        if historical_components:
            baseline = compute_rolling_baseline(historical_components, days=90)
            baseline_caps = {
                'severity_max': baseline.severity_max,
                'high_impact_max': baseline.high_impact_max,
                'asset_overlap_max': baseline.asset_overlap_max,
                'velocity_range': baseline.velocity_max - baseline.velocity_min,
            }
            logger.info(f"Using rolling normalization (days={days_history})")
    else:
        logger.info(f"Using fallback caps (days={days_history})")
    
    reri_components = compute_reri_components(
        europe_alerts, 
        historical_s,
        use_rolling_normalization=use_rolling,
        baseline_caps=baseline_caps,
    )
    reri_eu_value = compute_reri_value(reri_components)
    logger.info(f"Computed RERI_EU = {reri_eu_value}")
    
    neighbor_reri_values = {}
    
    me_alerts = filter_alerts_by_region(all_alerts, 'middle-east')
    if me_alerts:
        me_historical_s = fetch_historical_severity_values('middle-east', target_date, days=3)
        me_components = compute_reri_components(me_alerts, me_historical_s)
        neighbor_reri_values['middle-east'] = compute_reri_value(me_components)
        logger.info(f"Computed RERI Middle East = {neighbor_reri_values['middle-east']} ({len(me_alerts)} alerts)")
    
    bs_alerts = filter_alerts_by_region(all_alerts, 'black-sea')
    if bs_alerts:
        bs_historical_s = fetch_historical_severity_values('black-sea', target_date, days=3)
        bs_components = compute_reri_components(bs_alerts, bs_historical_s)
        neighbor_reri_values['black-sea'] = compute_reri_value(bs_components)
        logger.info(f"Computed RERI Black Sea = {neighbor_reri_values['black-sea']} ({len(bs_alerts)} alerts)")
    
    eeri_components = compute_eeri_components(
        europe_alerts,
        reri_eu_value,
        reri_components,
        neighbor_reri_values=neighbor_reri_values,
    )
    
    eeri_value = compute_eeri_value(eeri_components)
    band = get_band(eeri_value)
    logger.info(f"Computed EERI = {eeri_value} ({band.value})")
    
    drivers = extract_top_drivers(europe_alerts, limit=5)
    eeri_components.top_drivers = drivers
    
    # Generate AI-powered interpretation (unique per day)
    from src.reri.interpretation import generate_eeri_interpretation
    ai_interpretation = generate_eeri_interpretation(
        value=eeri_value,
        band=band.value,
        drivers=drivers,
        components={
            'reri_eu': eeri_components.reri_eu,
            'theme_pressure': eeri_components.theme_pressure_norm,
            'asset_transmission': eeri_components.asset_transmission_norm,
            'contagion': eeri_components.contagion_factor,
        },
        index_date=target_date.isoformat()
    )
    eeri_components.interpretation = ai_interpretation
    
    previous_values = fetch_previous_values(EERI_INDEX_ID, target_date, days=7)
    trend_1d, trend_7d = compute_trends(eeri_value, previous_values)
    
    result = RERIResult(
        index_id=EERI_INDEX_ID,
        region_id='europe',
        index_date=target_date,
        value=eeri_value,
        band=band,
        trend_1d=trend_1d,
        trend_7d=trend_7d,
        components=eeri_components,
        drivers=drivers,
        model_version=MODEL_VERSION,
        computed_at=datetime.utcnow(),
    )
    
    if save:
        save_reri_result(result)
        logger.info(f"Saved EERI result for {target_date}")
    
    return result


def get_latest_eeri() -> Optional[RERIResult]:
    """
    Get the most recent EERI result.
    
    Returns:
        RERIResult or None if no data exists
    """
    return get_latest_reri(EERI_INDEX_ID)


def get_eeri_status() -> dict:
    """
    Get EERI module status and configuration.
    """
    days_history = count_days_of_history(EERI_INDEX_ID)
    latest = get_latest_eeri()
    
    return {
        'enabled': ENABLE_EERI,
        'index_id': EERI_INDEX_ID,
        'model_version': MODEL_VERSION,
        'days_of_history': days_history,
        'normalization_mode': 'rolling' if days_history >= 30 else 'fallback_caps',
        'latest': {
            'date': latest.index_date.isoformat() if latest else None,
            'value': latest.value if latest else None,
            'band': latest.band.value if latest else None,
        } if latest else None,
        'contagion_enabled': True,
        'contagion_neighbors': {'middle-east': 0.6, 'black-sea': 0.4},
    }


def run_daily_eeri_computation() -> Optional[RERIResult]:
    """
    Run daily EERI computation for today.
    This is the main entry point for scheduled runs.
    
    Returns:
        RERIResult or None if disabled
    """
    today = date.today()
    logger.info(f"Running daily EERI computation for {today}")
    
    try:
        result = compute_eeri_for_date(today, save=True)
        if result:
            logger.info(f"Daily EERI: {result.value} ({result.band.value})")
        return result
    except Exception as e:
        logger.error(f"Error computing daily EERI: {e}", exc_info=True)
        raise
