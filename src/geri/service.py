"""
GERI v1 Service Layer

Orchestrates compute and backfill operations.
"""
import logging
from datetime import date, timedelta
from typing import Optional, List, Dict, Any

from src.geri import ENABLE_GERI
from src.geri.types import GERIResult, INDEX_ID
from src.geri.repo import (
    get_alerts_for_date,
    get_index_for_date,
    get_previous_values,
    get_historical_baseline,
    save_index,
    get_date_range_with_alerts,
)
from src.geri.compute import compute_components
from src.geri.normalize import (
    normalize_components,
    calculate_geri_value,
    calculate_trends,
    build_result,
)

logger = logging.getLogger(__name__)


def compute_geri_for_date(target_date: date, force: bool = False) -> Optional[GERIResult]:
    """
    Compute GERI index for a specific date.
    
    Args:
        target_date: The UTC date to compute the index for
        force: If True, overwrite existing value; if False, skip if exists
    
    Returns:
        GERIResult if computed, None if skipped or error
    """
    if not ENABLE_GERI:
        logger.warning("GERI module is disabled (ENABLE_GERI=false)")
        return None
    
    existing = get_index_for_date(target_date)
    if existing and not force:
        logger.info(f"GERI for {target_date} already exists, skipping (use force=True to overwrite)")
        return None
    
    logger.info(f"Computing GERI for date: {target_date}")
    
    alerts = get_alerts_for_date(target_date)
    logger.info(f"Found {len(alerts)} alerts for {target_date}")
    
    components = compute_components(alerts)
    
    baseline = get_historical_baseline(target_date)
    logger.info(f"Historical baseline: {baseline.days_count} days of history")
    
    components = normalize_components(components, baseline)
    
    value = calculate_geri_value(components)
    
    previous_values = get_previous_values(target_date, days=7)
    trend_1d, trend_7d = calculate_trends(value, previous_values)
    
    result = build_result(target_date, value, components, trend_1d, trend_7d)
    
    saved = save_index(result, force=force)
    
    if saved:
        logger.info(f"GERI computed: date={target_date}, value={value}, band={result.band.value}")
    
    return result


def compute_yesterday() -> Optional[GERIResult]:
    """Compute GERI for yesterday (UTC). Used by scheduler."""
    yesterday = date.today() - timedelta(days=1)
    return compute_geri_for_date(yesterday, force=False)


def backfill(
    from_date: date,
    to_date: date,
    force: bool = False
) -> Dict[str, Any]:
    """
    Backfill GERI indices for a date range.
    
    Args:
        from_date: Start date (inclusive)
        to_date: End date (inclusive)
        force: If True, overwrite existing values
    
    Returns:
        Summary dict with counts
    """
    if not ENABLE_GERI:
        logger.warning("GERI module is disabled (ENABLE_GERI=false)")
        return {'error': 'GERI module disabled', 'computed': 0, 'skipped': 0}
    
    logger.info(f"Starting GERI backfill from {from_date} to {to_date} (force={force})")
    
    computed = 0
    skipped = 0
    failed = 0
    results = []
    
    current_date = from_date
    while current_date <= to_date:
        try:
            result = compute_geri_for_date(current_date, force=force)
            if result:
                computed += 1
                results.append({
                    'date': current_date.isoformat(),
                    'value': result.value,
                    'band': result.band.value,
                })
            else:
                skipped += 1
        except Exception as e:
            logger.error(f"Failed to compute GERI for {current_date}: {e}")
            failed += 1
        
        current_date += timedelta(days=1)
    
    summary = {
        'from_date': from_date.isoformat(),
        'to_date': to_date.isoformat(),
        'computed': computed,
        'skipped': skipped,
        'failed': failed,
        'total_days': (to_date - from_date).days + 1,
        'results': results,
    }
    
    logger.info(f"Backfill complete: computed={computed}, skipped={skipped}, failed={failed}")
    
    return summary


def auto_backfill(force: bool = False) -> Dict[str, Any]:
    """
    Automatically backfill all historical alerts.
    Determines date range from alert_events.
    """
    min_date, max_date = get_date_range_with_alerts()
    
    if not min_date or not max_date:
        return {
            'error': 'No alerts found in alert_events',
            'computed': 0,
            'skipped': 0,
        }
    
    yesterday = date.today() - timedelta(days=1)
    to_date = min(max_date, yesterday)
    
    logger.info(f"Auto-backfill: alert range is {min_date} to {max_date}, processing up to {to_date}")
    
    return backfill(min_date, to_date, force=force)
