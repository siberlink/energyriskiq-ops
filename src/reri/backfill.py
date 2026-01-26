"""
EERI Backfill Module

Backfills EERI indices from historical alert_events data.
"""
import logging
from datetime import date, timedelta
from typing import Optional, Dict, Any

from src.db.db import get_cursor
from src.reri.service import compute_eeri_for_date

logger = logging.getLogger(__name__)


def get_alert_date_range() -> tuple[Optional[date], Optional[date]]:
    """
    Get the date range of alerts in alert_events table.
    
    Returns:
        Tuple of (earliest_date, latest_date) or (None, None) if no alerts
    """
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT 
                MIN(created_at::date) as earliest,
                MAX(created_at::date) as latest
            FROM alert_events
        """)
        row = cursor.fetchone()
    
    if not row or not row['earliest']:
        return None, None
    
    return row['earliest'], row['latest']


def get_dates_with_alerts(start_date: date, end_date: date) -> list[date]:
    """
    Get list of dates that have alerts in the range.
    
    Returns:
        List of dates with at least one alert
    """
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT DISTINCT created_at::date as alert_date
            FROM alert_events
            WHERE created_at::date BETWEEN %s AND %s
            ORDER BY alert_date ASC
        """, (start_date, end_date))
        rows = cursor.fetchall()
    
    return [row['alert_date'] for row in rows]


def run_eeri_backfill(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """
    Backfill EERI indices from historical alert_events.
    
    Args:
        start_date: Start date (auto-detect from earliest alert if not specified)
        end_date: End date (yesterday if not specified)
        force: Whether to overwrite existing values
    
    Returns:
        Dict with backfill statistics
    """
    logger.info("Starting EERI backfill...")
    
    if not start_date or not end_date:
        earliest, latest = get_alert_date_range()
        
        if not earliest:
            logger.warning("No alerts found in alert_events table")
            return {
                'total_days': 0,
                'computed': 0,
                'skipped': 0,
                'errors': 0,
                'message': 'No alerts found in alert_events table',
            }
        
        if not start_date:
            start_date = earliest
        if not end_date:
            yesterday = date.today() - timedelta(days=1)
            end_date = min(latest, yesterday) if latest else yesterday
    
    if end_date >= date.today():
        end_date = date.today() - timedelta(days=1)
    
    logger.info(f"Backfill range: {start_date} to {end_date}")
    
    dates_with_alerts = get_dates_with_alerts(start_date, end_date)
    
    if not dates_with_alerts:
        logger.warning(f"No alerts found between {start_date} and {end_date}")
        return {
            'total_days': 0,
            'computed': 0,
            'skipped': 0,
            'errors': 0,
            'message': f'No alerts found between {start_date} and {end_date}',
        }
    
    total_days = len(dates_with_alerts)
    computed = 0
    skipped = 0
    errors = 0
    results = []
    
    logger.info(f"Found {total_days} days with alerts to process")
    
    for i, target_date in enumerate(dates_with_alerts, 1):
        try:
            logger.info(f"[{i}/{total_days}] Computing EERI for {target_date}...")
            
            result = compute_eeri_for_date(target_date, save=True, force=force)
            
            if result:
                computed += 1
                results.append({
                    'date': target_date.isoformat(),
                    'value': result.value,
                    'band': result.band.value,
                })
                logger.info(f"  -> EERI = {result.value} ({result.band.value})")
            else:
                skipped += 1
                logger.info(f"  -> Skipped (already exists)")
                
        except Exception as e:
            errors += 1
            logger.error(f"  -> Error: {e}")
    
    logger.info(f"Backfill complete: {computed} computed, {skipped} skipped, {errors} errors")
    
    return {
        'total_days': total_days,
        'computed': computed,
        'skipped': skipped,
        'errors': errors,
        'start_date': start_date.isoformat(),
        'end_date': end_date.isoformat(),
        'results': results,
    }
