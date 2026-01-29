"""
EGSI-S Service Layer

Orchestrates EGSI-S (System Stress) computation.
"""
import logging
from datetime import date, datetime
from typing import Optional, List, Dict, Any

from src.egsi.types import (
    ENABLE_EGSI,
    EGSI_S_INDEX_ID,
    EGSISResult,
    EGSI_S_MODEL_VERSION,
    get_egsi_band,
)
from src.egsi.compute_egsi_s import (
    compute_egsi_s_components,
    compute_egsi_s_value,
)
from src.egsi.data_sources import get_market_data_provider
from src.egsi.repo import (
    save_egsi_s_result,
    get_egsi_s_for_date,
    get_egsi_s_latest,
    get_egsi_s_history,
    compute_egsi_s_trends,
)
from src.reri.repo import fetch_alerts_for_date

logger = logging.getLogger(__name__)


def compute_egsi_s_for_date(
    target_date: date,
    save: bool = True,
    force: bool = False
) -> Optional[EGSISResult]:
    """
    Compute EGSI-S (Europe Gas Stress Index - System) for a specific date.
    
    Args:
        target_date: Date to compute EGSI-S for
        save: Whether to save result to database
        force: Whether to overwrite existing result
    
    Returns:
        EGSISResult or None if feature is disabled or already exists (and not force)
    """
    if not ENABLE_EGSI:
        logger.info("EGSI is disabled (ENABLE_EGSI=false)")
        return None
    
    existing = get_egsi_s_for_date(target_date)
    if existing and not force:
        logger.info(f"EGSI-S for {target_date} already exists (skipped). Use force=True to recompute.")
        return None
    
    logger.info(f"Computing EGSI-S for {target_date}...")
    
    provider = get_market_data_provider()
    market_data = provider.get_snapshot(target_date)
    
    if not market_data:
        logger.warning(f"No market data available for {target_date}")
        return None
    
    logger.info(f"Using market data from source: {market_data.source}")
    
    alerts = fetch_alerts_for_date(target_date, region_filter='Europe')
    supply_alerts = [
        a for a in alerts 
        if any(kw in f"{getattr(a, 'title', '') or ''} {getattr(a, 'summary', '') or ''}".lower() 
               for kw in ['gas', 'supply', 'pipeline', 'lng', 'storage'])
    ]
    logger.info(f"Found {len(supply_alerts)} supply-related alerts for {target_date}")
    
    components = compute_egsi_s_components(market_data, supply_alerts)
    value = compute_egsi_s_value(components)
    band = get_egsi_band(value)
    
    components.interpretation = components.interpretation.replace(
        "EGSI-S value",
        f"EGSI-S value of {value:.0f}"
    )
    
    trend_1d, trend_7d = compute_egsi_s_trends(value)
    
    result = EGSISResult(
        index_id=EGSI_S_INDEX_ID,
        region='Europe',
        index_date=target_date,
        value=value,
        band=band,
        trend_1d=trend_1d,
        trend_7d=trend_7d,
        components=components,
        model_version=EGSI_S_MODEL_VERSION,
        computed_at=datetime.utcnow(),
    )
    
    logger.info(
        f"EGSI-S computed: {value:.1f} ({band.value}) | "
        f"Storage={components.storage_level_pct*100:.1f}% (target: {components.storage_target_pct*100:.1f}%) | "
        f"TTF={components.ttf_price:.2f} EUR/MWh | "
        f"Source: {market_data.source}"
    )
    
    if save:
        save_egsi_s_result(result)
    
    return result


def get_egsi_s_status() -> dict:
    """Get current EGSI-S computation status for health checks."""
    latest = get_egsi_s_latest()
    history = get_egsi_s_history(days=7)
    
    provider = get_market_data_provider()
    
    return {
        'enabled': ENABLE_EGSI,
        'data_source': provider.source_name,
        'latest': {
            'date': latest['date'].isoformat() if latest else None,
            'value': latest['value'] if latest else None,
            'band': latest['band'] if latest else None,
        } if latest else None,
        'history_days': len(history),
        'model_version': EGSI_S_MODEL_VERSION,
    }
