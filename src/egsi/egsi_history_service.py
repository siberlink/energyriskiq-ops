"""
EGSI History Service

Provides functions for retrieving historical EGSI-M data for SEO pages.
"""
import logging
from datetime import date, datetime, timedelta
from typing import Optional, List, Dict, Any
import json

from src.db.db import get_cursor
from src.egsi.types import EGSI_M_INDEX_ID

logger = logging.getLogger(__name__)


def get_all_egsi_m_dates() -> List[str]:
    """
    Get all dates that have EGSI-M snapshots.
    Returns list of ISO date strings in descending order.
    """
    query = """
        SELECT DISTINCT index_date
        FROM egsi_m_daily
        ORDER BY index_date DESC
    """
    try:
        with get_cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()
        return [row['index_date'].isoformat() if hasattr(row['index_date'], 'isoformat') else str(row['index_date']) for row in rows]
    except Exception as e:
        logger.error(f"Error fetching EGSI-M dates: {e}")
        return []


def get_egsi_m_available_months() -> List[Dict[str, Any]]:
    """
    Get all available months that have EGSI-M data.
    Returns list of {year, month, count, max_date} dicts.
    """
    query = """
        SELECT 
            EXTRACT(YEAR FROM index_date)::int as year,
            EXTRACT(MONTH FROM index_date)::int as month,
            COUNT(*) as count,
            MAX(index_date) as max_date
        FROM egsi_m_daily
        GROUP BY EXTRACT(YEAR FROM index_date), EXTRACT(MONTH FROM index_date)
        ORDER BY year DESC, month DESC
    """
    try:
        with get_cursor() as cursor:
            cursor.execute(query)
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
        logger.error(f"Error fetching EGSI-M months: {e}")
        return []


def get_egsi_m_by_date(target_date: date) -> Optional[Dict[str, Any]]:
    """
    Get EGSI-M snapshot for a specific date.
    Returns dict with value, band, trend, explanation, components.
    """
    query = """
        SELECT 
            index_date, index_value, band, trend_1d, trend_7d,
            explanation, computed_at
        FROM egsi_m_daily
        WHERE index_date = %s
    """
    try:
        with get_cursor() as cursor:
            cursor.execute(query, (target_date,))
            row = cursor.fetchone()
        
        if not row:
            return None
        
        components = get_egsi_m_components_for_date(target_date)
        drivers = get_egsi_m_drivers_for_date(target_date)
        
        return {
            'date': row['index_date'].isoformat() if hasattr(row['index_date'], 'isoformat') else str(row['index_date']),
            'value': float(row['index_value']) if row['index_value'] else 0,
            'band': row['band'],
            'trend_1d': float(row['trend_1d']) if row['trend_1d'] else None,
            'trend_7d': float(row['trend_7d']) if row['trend_7d'] else None,
            'explanation': row['explanation'],
            'components': components,
            'drivers': drivers,
        }
    except Exception as e:
        logger.error(f"Error fetching EGSI-M for {target_date}: {e}")
        return None


def get_egsi_m_components_for_date(target_date: date) -> Dict[str, Any]:
    """Get EGSI-M component breakdown for a date."""
    query = """
        SELECT component_key, raw_value, norm_value, weight, contribution, meta
        FROM egsi_components_daily
        WHERE index_date = %s AND index_family = 'EGSI_M'
    """
    try:
        with get_cursor() as cursor:
            cursor.execute(query, (target_date,))
            rows = cursor.fetchall()
        
        if not rows:
            return {}
        
        components = {}
        for row in rows:
            key = row['component_key']
            meta = row['meta']
            if isinstance(meta, str):
                meta = json.loads(meta)
            
            components[key] = {
                'raw_value': float(row['raw_value']) if row['raw_value'] else 0,
                'norm_value': float(row['norm_value']) if row['norm_value'] else 0,
                'weight': float(row['weight']) if row['weight'] else 0,
                'contribution': float(row['contribution']) if row['contribution'] else 0,
                'meta': meta if isinstance(meta, dict) else {},
            }
            
            # Extract chokepoint hits from the chokepoint_factor component meta
            if key == 'chokepoint_factor' and meta and 'hits' in meta:
                components[key]['hits'] = meta['hits']
        
        return components
    except Exception as e:
        logger.error(f"Error fetching EGSI-M components for {target_date}: {e}")
        return {}


def get_egsi_m_drivers_for_date(target_date: date) -> List[Dict[str, Any]]:
    """Get EGSI-M top drivers for a date."""
    query = """
        SELECT headline, driver_type, score, severity, confidence, driver_rank, meta
        FROM egsi_drivers_daily
        WHERE index_date = %s AND index_family = 'EGSI_M'
        ORDER BY driver_rank ASC, score DESC
        LIMIT 5
    """
    try:
        with get_cursor() as cursor:
            cursor.execute(query, (target_date,))
            rows = cursor.fetchall()
        
        result = []
        for row in rows:
            meta = row['meta']
            if isinstance(meta, str):
                meta = json.loads(meta)
            
            result.append({
                'name': row['headline'] or 'Unknown driver',
                'type': row['driver_type'] or 'general',
                'contribution': float(row['score']) if row['score'] else 0,
                'severity': float(row['severity']) if row['severity'] else 0,
                'confidence': float(row['confidence']) if row['confidence'] else 0,
                'details': meta if isinstance(meta, dict) else {},
            })
        return result
    except Exception as e:
        logger.error(f"Error fetching EGSI-M drivers for {target_date}: {e}")
        return []


def get_egsi_m_monthly_data(year: int, month: int) -> List[Dict[str, Any]]:
    """
    Get all EGSI-M data for a specific month.
    Returns list of dicts with date, value, band, trend.
    """
    query = """
        SELECT index_date, index_value, band, trend_1d, trend_7d, explanation
        FROM egsi_m_daily
        WHERE EXTRACT(YEAR FROM index_date) = %s
          AND EXTRACT(MONTH FROM index_date) = %s
        ORDER BY index_date DESC
    """
    try:
        with get_cursor() as cursor:
            cursor.execute(query, (year, month))
            rows = cursor.fetchall()
        
        result = []
        for row in rows:
            result.append({
                'date': row['index_date'].isoformat() if hasattr(row['index_date'], 'isoformat') else str(row['index_date']),
                'value': float(row['index_value']) if row['index_value'] else 0,
                'band': row['band'],
                'trend_1d': float(row['trend_1d']) if row['trend_1d'] else None,
                'trend_7d': float(row['trend_7d']) if row['trend_7d'] else None,
                'explanation': row['explanation'],
            })
        return result
    except Exception as e:
        logger.error(f"Error fetching EGSI-M monthly data for {year}-{month}: {e}")
        return []


def get_egsi_m_adjacent_dates(target_date: date) -> Dict[str, Optional[str]]:
    """
    Get previous and next dates with EGSI-M data relative to target_date.
    Returns dict with 'prev' and 'next' date strings.
    """
    prev_query = """
        SELECT MAX(index_date) as prev_date
        FROM egsi_m_daily
        WHERE index_date < %s
    """
    next_query = """
        SELECT MIN(index_date) as next_date
        FROM egsi_m_daily
        WHERE index_date > %s
    """
    result = {'prev': None, 'next': None}
    
    try:
        with get_cursor() as cursor:
            cursor.execute(prev_query, (target_date,))
            row = cursor.fetchone()
            if row and row['prev_date']:
                prev_date = row['prev_date']
                result['prev'] = prev_date.isoformat() if hasattr(prev_date, 'isoformat') else str(prev_date)
            
            cursor.execute(next_query, (target_date,))
            row = cursor.fetchone()
            if row and row['next_date']:
                next_date = row['next_date']
                result['next'] = next_date.isoformat() if hasattr(next_date, 'isoformat') else str(next_date)
    except Exception as e:
        logger.error(f"Error fetching EGSI-M adjacent dates: {e}")
    
    return result


def get_egsi_m_monthly_stats() -> List[Dict[str, Any]]:
    """
    Get monthly statistics for EGSI-M (avg, max, min values per month).
    """
    query = """
        SELECT 
            EXTRACT(YEAR FROM index_date)::int as year,
            EXTRACT(MONTH FROM index_date)::int as month,
            COUNT(*) as count,
            AVG(index_value)::numeric(5,2) as avg_value,
            MAX(index_value) as max_value,
            MIN(index_value) as min_value
        FROM egsi_m_daily
        GROUP BY EXTRACT(YEAR FROM index_date), EXTRACT(MONTH FROM index_date)
        ORDER BY year DESC, month DESC
    """
    try:
        with get_cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()
        
        result = []
        for row in rows:
            result.append({
                'year': row['year'],
                'month': row['month'],
                'count': row['count'],
                'avg_value': float(row['avg_value']) if row['avg_value'] else 0,
                'max_value': float(row['max_value']) if row['max_value'] else 0,
                'min_value': float(row['min_value']) if row['min_value'] else 0,
            })
        return result
    except Exception as e:
        logger.error(f"Error fetching EGSI-M monthly stats: {e}")
        return []


def get_egsi_m_delayed(delay_hours: int = 24) -> Optional[Dict[str, Any]]:
    """
    Get EGSI-M data with a delay for public display.
    
    Uses OFFSET 1 to get the second-most-recent record (true 24h delay).
    - Latest record (LIMIT 1) is for authenticated users (real-time)
    - Second-last record (OFFSET 1) is for public/unauthenticated (24h delayed)
    
    This matches GERI's delay logic for consistency.
    """
    query = """
        SELECT index_date, index_value, band, trend_1d, trend_7d, explanation, computed_at
        FROM egsi_m_daily
        ORDER BY computed_at DESC
        LIMIT 1 OFFSET 1
    """
    try:
        with get_cursor() as cursor:
            cursor.execute(query)
            row = cursor.fetchone()
        
        if not row:
            return None
        
        target_date = row['index_date']
        components = get_egsi_m_components_for_date(target_date)
        drivers = get_egsi_m_drivers_for_date(target_date)
        
        return {
            'date': row['index_date'].isoformat() if hasattr(row['index_date'], 'isoformat') else str(row['index_date']),
            'value': float(row['index_value']) if row['index_value'] else 0,
            'band': row['band'],
            'trend_1d': float(row['trend_1d']) if row['trend_1d'] else None,
            'trend_7d': float(row['trend_7d']) if row['trend_7d'] else None,
            'explanation': row['explanation'],
            'components': components,
            'drivers': drivers,
            'computed_at': row['computed_at'].isoformat() if row['computed_at'] else None,
        }
    except Exception as e:
        logger.error(f"Error fetching delayed EGSI-M: {e}")
        return None


def get_latest_egsi_m_public() -> Optional[Dict[str, Any]]:
    """
    Get the latest EGSI-M data for public display (fallback when no delayed data).
    """
    query = """
        SELECT index_date, index_value, band, trend_1d, trend_7d, explanation
        FROM egsi_m_daily
        ORDER BY index_date DESC
        LIMIT 1
    """
    try:
        with get_cursor() as cursor:
            cursor.execute(query)
            row = cursor.fetchone()
        
        if not row:
            return None
        
        target_date = row['index_date']
        components = get_egsi_m_components_for_date(target_date)
        drivers = get_egsi_m_drivers_for_date(target_date)
        
        return {
            'date': row['index_date'].isoformat() if hasattr(row['index_date'], 'isoformat') else str(row['index_date']),
            'value': float(row['index_value']) if row['index_value'] else 0,
            'band': row['band'],
            'trend_1d': float(row['trend_1d']) if row['trend_1d'] else None,
            'trend_7d': float(row['trend_7d']) if row['trend_7d'] else None,
            'explanation': row['explanation'],
            'components': components,
            'drivers': drivers,
        }
    except Exception as e:
        logger.error(f"Error fetching latest EGSI-M: {e}")
        return None
