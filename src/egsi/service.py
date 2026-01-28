"""
EGSI Service Layer

Orchestrates EGSI-M computation, integrating with RERI data and alert streams.
"""
import logging
from datetime import date, datetime
from typing import Optional

from src.egsi.types import (
    ENABLE_EGSI,
    EGSI_M_INDEX_ID,
    EGSIMResult,
    EGSIMComponents,
    get_egsi_band,
    MODEL_VERSION,
)
from src.egsi.compute import (
    compute_egsi_m_components,
    compute_egsi_m_value,
)
from src.egsi.repo import (
    save_egsi_m_result,
    save_egsi_components,
    save_egsi_drivers,
    get_egsi_m_for_date,
    compute_trends,
)
from src.reri.repo import fetch_alerts_for_date, get_reri_for_date
from src.reri.types import EERI_INDEX_ID

logger = logging.getLogger(__name__)


def compute_egsi_m_for_date(
    target_date: date,
    save: bool = True,
    force: bool = False
) -> Optional[EGSIMResult]:
    """
    Compute EGSI-M (Europe Gas Stress Index - Market) for a specific date.
    
    Args:
        target_date: Date to compute EGSI-M for
        save: Whether to save result to database
        force: Whether to overwrite existing result
    
    Returns:
        EGSIMResult or None if feature is disabled or already exists (and not force)
    """
    if not ENABLE_EGSI:
        logger.info("EGSI is disabled (ENABLE_EGSI=false)")
        return None
    
    existing = get_egsi_m_for_date(target_date)
    if existing and not force:
        logger.info(f"EGSI-M for {target_date} already exists (skipped). Use force=True to recompute.")
        return None
    
    logger.info(f"Computing EGSI-M for {target_date}...")
    
    eeri_result = get_reri_for_date(EERI_INDEX_ID, target_date)
    
    if not eeri_result:
        logger.warning(f"No EERI/RERI data for {target_date}, cannot compute EGSI-M")
        return None
    
    reri_eu_value = eeri_result.value
    logger.info(f"Using RERI_EU value: {reri_eu_value}")
    
    alerts = fetch_alerts_for_date(target_date, region_filter='Europe')
    logger.info(f"Fetched {len(alerts)} Europe alerts for {target_date}")
    
    components = compute_egsi_m_components(
        alerts=alerts,
        reri_eu_value=reri_eu_value,
        use_percentile_norm=False,
    )
    
    value = compute_egsi_m_value(components)
    band = get_egsi_band(value)
    
    trend_1d, trend_7d = compute_trends(value)
    
    result = EGSIMResult(
        index_id=EGSI_M_INDEX_ID,
        region='Europe',
        index_date=target_date,
        value=value,
        band=band,
        trend_1d=trend_1d,
        trend_7d=trend_7d,
        components=components,
        model_version=MODEL_VERSION,
        computed_at=datetime.utcnow(),
    )
    
    logger.info(
        f"EGSI-M computed: {value:.1f} ({band.value}) | "
        f"RERI_EU={reri_eu_value} | "
        f"ThemePressure={components.theme_pressure_raw:.1f} ({components.theme_alert_count} alerts) | "
        f"AssetTrans={components.asset_transmission_raw:.1f} ({components.asset_count} assets) | "
        f"Chokepoint={components.chokepoint_factor_raw:.1f} ({len(components.chokepoint_hits)} hits)"
    )
    
    if save:
        save_egsi_m_result(result)
        
        save_egsi_components(
            index_family='EGSI_M',
            index_date=target_date,
            region='Europe',
            components=components.to_dict(),
        )
        
        if components.top_drivers:
            save_egsi_drivers(
                index_family='EGSI_M',
                index_date=target_date,
                region='Europe',
                drivers=components.top_drivers,
            )
    
    return result


def get_egsi_m_status() -> dict:
    """Get current EGSI-M computation status for health checks."""
    from src.egsi.repo import get_egsi_m_latest, get_egsi_m_history
    
    latest = get_egsi_m_latest()
    history = get_egsi_m_history(days=7)
    
    return {
        'enabled': ENABLE_EGSI,
        'latest': {
            'date': latest['date'].isoformat() if latest else None,
            'value': latest['value'] if latest else None,
            'band': latest['band'] if latest else None,
        } if latest else None,
        'history_days': len(history),
        'model_version': MODEL_VERSION,
    }
