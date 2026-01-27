"""
EERI History Service

Provides functions for retrieving historical EERI data for SEO pages.
"""
import logging
from datetime import date, datetime, timedelta
from typing import Optional, List, Dict, Any

from src.db.db import get_cursor, execute_query
from src.reri.types import EERI_INDEX_ID, RERIResult, EERIComponents, RiskBand
import json

logger = logging.getLogger(__name__)


def get_all_eeri_dates() -> List[str]:
    """
    Get all dates that have EERI snapshots.
    Returns list of ISO date strings in descending order.
    """
    query = """
        SELECT DISTINCT date
        FROM reri_indices_daily
        WHERE index_id = %s
        ORDER BY date DESC
    """
    try:
        with get_cursor() as cursor:
            cursor.execute(query, (EERI_INDEX_ID,))
            rows = cursor.fetchall()
        return [row['date'].isoformat() if hasattr(row['date'], 'isoformat') else str(row['date']) for row in rows]
    except Exception as e:
        logger.error(f"Error fetching EERI dates: {e}")
        return []


def get_eeri_available_months() -> List[Dict[str, Any]]:
    """
    Get all available months that have EERI data.
    Returns list of {year, month, count, max_date} dicts.
    """
    query = """
        SELECT 
            EXTRACT(YEAR FROM date)::int as year,
            EXTRACT(MONTH FROM date)::int as month,
            COUNT(*) as count,
            MAX(date) as max_date
        FROM reri_indices_daily
        WHERE index_id = %s
        GROUP BY EXTRACT(YEAR FROM date), EXTRACT(MONTH FROM date)
        ORDER BY year DESC, month DESC
    """
    try:
        with get_cursor() as cursor:
            cursor.execute(query, (EERI_INDEX_ID,))
            rows = cursor.fetchall()
        result = []
        for row in rows:
            max_date = row['max_date']
            if hasattr(max_date, 'isoformat'):
                max_date = max_date.isoformat()
            result.append({
                'year': row['year'],
                'month': row['month'],
                'count': row['count'],
                'max_date': max_date,
            })
        return result
    except Exception as e:
        logger.error(f"Error fetching EERI months: {e}")
        return []


def get_eeri_by_date(target_date: date) -> Optional[Dict[str, Any]]:
    """
    Get EERI snapshot for a specific date.
    Returns dict with value, band, trend, drivers, interpretation.
    """
    query = """
        SELECT 
            date, value, band, trend_1d, trend_7d,
            components, drivers, computed_at, model_version
        FROM reri_indices_daily
        WHERE index_id = %s AND date = %s
    """
    try:
        with get_cursor() as cursor:
            cursor.execute(query, (EERI_INDEX_ID, target_date))
            row = cursor.fetchone()
        
        if not row:
            return None
        
        components = row['components'] if isinstance(row['components'], dict) else json.loads(row['components']) if row['components'] else {}
        drivers = row['drivers'] if isinstance(row['drivers'], list) else json.loads(row['drivers']) if row['drivers'] else []
        
        return {
            'date': row['date'].isoformat() if hasattr(row['date'], 'isoformat') else str(row['date']),
            'value': row['value'],
            'band': row['band'],
            'trend_1d': row['trend_1d'],
            'trend_7d': row['trend_7d'],
            'interpretation': components.get('interpretation', ''),
            'top_drivers': components.get('top_drivers', drivers[:3]),
            'affected_assets': _extract_affected_assets(components, drivers),
            'computed_at': row['computed_at'].isoformat() if row['computed_at'] else None,
            'model_version': row['model_version'],
        }
    except Exception as e:
        logger.error(f"Error fetching EERI for {target_date}: {e}")
        return None


def get_latest_eeri_public() -> Optional[Dict[str, Any]]:
    """
    Get the latest EERI snapshot for public display.
    """
    query = """
        SELECT 
            date, value, band, trend_1d, trend_7d,
            components, drivers, computed_at
        FROM reri_indices_daily
        WHERE index_id = %s
        ORDER BY date DESC
        LIMIT 1
    """
    try:
        with get_cursor() as cursor:
            cursor.execute(query, (EERI_INDEX_ID,))
            row = cursor.fetchone()
        
        if not row:
            return None
        
        components = row['components'] if isinstance(row['components'], dict) else json.loads(row['components']) if row['components'] else {}
        drivers = row['drivers'] if isinstance(row['drivers'], list) else json.loads(row['drivers']) if row['drivers'] else []
        
        return {
            'date': row['date'].isoformat() if hasattr(row['date'], 'isoformat') else str(row['date']),
            'value': row['value'],
            'band': row['band'],
            'trend_1d': row['trend_1d'],
            'trend_7d': row['trend_7d'],
            'interpretation': components.get('interpretation', ''),
            'top_drivers': components.get('top_drivers', drivers[:3]),
            'affected_assets': _extract_affected_assets(components, drivers),
            'computed_at': row['computed_at'].isoformat() if row['computed_at'] else None,
        }
    except Exception as e:
        logger.error(f"Error fetching latest EERI: {e}")
        return None


def get_eeri_delayed(delay_hours: int = 24) -> Optional[Dict[str, Any]]:
    """
    Get EERI data with a delay (for public/free tier access).
    Default 24-hour delay.
    """
    cutoff = datetime.utcnow() - timedelta(hours=delay_hours)
    
    query = """
        SELECT 
            date, value, band, trend_1d, trend_7d,
            components, drivers, computed_at
        FROM reri_indices_daily
        WHERE index_id = %s
          AND computed_at <= %s
        ORDER BY date DESC
        LIMIT 1
    """
    try:
        with get_cursor() as cursor:
            cursor.execute(query, (EERI_INDEX_ID, cutoff))
            row = cursor.fetchone()
        
        if not row:
            return None
        
        components = row['components'] if isinstance(row['components'], dict) else json.loads(row['components']) if row['components'] else {}
        drivers = row['drivers'] if isinstance(row['drivers'], list) else json.loads(row['drivers']) if row['drivers'] else []
        
        return {
            'date': row['date'].isoformat() if hasattr(row['date'], 'isoformat') else str(row['date']),
            'value': row['value'],
            'band': row['band'],
            'trend_1d': row['trend_1d'],
            'trend_7d': row['trend_7d'],
            'interpretation': components.get('interpretation', ''),
            'top_drivers': components.get('top_drivers', drivers[:3]),
            'affected_assets': _extract_affected_assets(components, drivers),
            'computed_at': row['computed_at'].isoformat() if row['computed_at'] else None,
            'is_delayed': True,
        }
    except Exception as e:
        logger.error(f"Error fetching delayed EERI: {e}")
        return None


def get_eeri_monthly_data(year: int, month: int) -> List[Dict[str, Any]]:
    """
    Get all EERI data for a specific month.
    """
    query = """
        SELECT 
            date, value, band, trend_1d, trend_7d,
            components, drivers, computed_at
        FROM reri_indices_daily
        WHERE index_id = %s
          AND EXTRACT(YEAR FROM date) = %s
          AND EXTRACT(MONTH FROM date) = %s
        ORDER BY date DESC
    """
    try:
        with get_cursor() as cursor:
            cursor.execute(query, (EERI_INDEX_ID, year, month))
            rows = cursor.fetchall()
        
        results = []
        for row in rows:
            components = row['components'] if isinstance(row['components'], dict) else json.loads(row['components']) if row['components'] else {}
            drivers = row['drivers'] if isinstance(row['drivers'], list) else json.loads(row['drivers']) if row['drivers'] else []
            
            results.append({
                'date': row['date'].isoformat() if hasattr(row['date'], 'isoformat') else str(row['date']),
                'value': row['value'],
                'band': row['band'],
                'trend_7d': row['trend_7d'],
                'interpretation': components.get('interpretation', ''),
                'top_drivers': components.get('top_drivers', drivers[:3])[:2],
            })
        return results
    except Exception as e:
        logger.error(f"Error fetching EERI for {year}-{month}: {e}")
        return []


def get_eeri_adjacent_dates(target_date: date) -> Dict[str, Optional[str]]:
    """
    Get previous and next dates that have EERI data relative to target date.
    """
    prev_query = """
        SELECT date FROM reri_indices_daily
        WHERE index_id = %s AND date < %s
        ORDER BY date DESC LIMIT 1
    """
    next_query = """
        SELECT date FROM reri_indices_daily
        WHERE index_id = %s AND date > %s
        ORDER BY date ASC LIMIT 1
    """
    try:
        with get_cursor() as cursor:
            cursor.execute(prev_query, (EERI_INDEX_ID, target_date))
            prev_row = cursor.fetchone()
            cursor.execute(next_query, (EERI_INDEX_ID, target_date))
            next_row = cursor.fetchone()
        
        prev_date = None
        next_date = None
        if prev_row:
            prev_date = prev_row['date'].isoformat() if hasattr(prev_row['date'], 'isoformat') else str(prev_row['date'])
        if next_row:
            next_date = next_row['date'].isoformat() if hasattr(next_row['date'], 'isoformat') else str(next_row['date'])
        
        return {'prev': prev_date, 'next': next_date}
    except Exception as e:
        logger.error(f"Error fetching adjacent EERI dates: {e}")
        return {'prev': None, 'next': None}


def get_eeri_monthly_stats() -> Dict[str, Any]:
    """
    Get aggregate statistics across all EERI history.
    """
    query = """
        SELECT 
            COUNT(*) as total_days,
            AVG(value) as avg_value,
            MAX(value) as max_value,
            MIN(value) as min_value,
            MIN(date) as first_date,
            MAX(date) as last_date
        FROM reri_indices_daily
        WHERE index_id = %s
    """
    try:
        with get_cursor() as cursor:
            cursor.execute(query, (EERI_INDEX_ID,))
            row = cursor.fetchone()
        
        if not row or row['total_days'] == 0:
            return {}
        
        return {
            'total_days': row['total_days'],
            'avg_value': round(float(row['avg_value']), 1) if row['avg_value'] else 0,
            'max_value': row['max_value'],
            'min_value': row['min_value'],
            'first_date': row['first_date'].isoformat() if hasattr(row['first_date'], 'isoformat') else str(row['first_date']),
            'last_date': row['last_date'].isoformat() if hasattr(row['last_date'], 'isoformat') else str(row['last_date']),
        }
    except Exception as e:
        logger.error(f"Error fetching EERI stats: {e}")
        return {}


def _extract_affected_assets(components: Dict, drivers: List) -> List[str]:
    """
    Extract affected asset classes from components/drivers.
    Returns cleaned list of asset names.
    """
    assets = set()
    
    reri_eu = components.get('reri_eu', {})
    if reri_eu.get('components', {}).get('asset_overlap', {}).get('assets'):
        for a in reri_eu['components']['asset_overlap']['assets']:
            assets.add(a.lower())
    
    for driver in drivers[:5]:
        if isinstance(driver, dict) and driver.get('assets'):
            for a in driver['assets']:
                if a:
                    assets.add(a.lower())
    
    ASSET_DISPLAY = {
        'gas': 'Natural Gas',
        'oil': 'Crude Oil',
        'lng': 'LNG',
        'power': 'Power & Electricity',
        'electricity': 'Power & Electricity',
        'freight': 'Freight & Shipping',
        'shipping': 'Freight & Shipping',
        'fx': 'Foreign Exchange',
        'forex': 'Foreign Exchange',
    }
    
    result = []
    seen = set()
    for asset in assets:
        display = ASSET_DISPLAY.get(asset, asset.title())
        if display not in seen:
            result.append(display)
            seen.add(display)
    
    return result[:4]
