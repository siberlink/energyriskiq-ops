"""
EGSI Repository Layer

Database operations for EGSI indices.
"""
import logging
import json
from datetime import date, datetime, timedelta
from typing import Optional, List, Dict, Any

from src.db.db import get_cursor
from src.egsi.types import (
    EGSIMResult,
    EGSIMComponents,
    EGSISResult,
    EGSISComponents,
    EGSIBand,
    get_egsi_band,
    EGSI_M_INDEX_ID,
    EGSI_S_INDEX_ID,
    MODEL_VERSION,
    EGSI_S_MODEL_VERSION,
)

logger = logging.getLogger(__name__)


def save_egsi_m_result(result: EGSIMResult) -> bool:
    """
    Save EGSI-M result to database.
    Uses upsert to handle re-computation.
    """
    try:
        with get_cursor() as cursor:
            cursor.execute("""
                INSERT INTO egsi_m_daily (
                    index_date, region, index_value, band,
                    trend_1d, trend_7d, components_json, explanation, computed_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (index_date, region) DO UPDATE SET
                    index_value = EXCLUDED.index_value,
                    band = EXCLUDED.band,
                    trend_1d = EXCLUDED.trend_1d,
                    trend_7d = EXCLUDED.trend_7d,
                    components_json = EXCLUDED.components_json,
                    explanation = EXCLUDED.explanation,
                    computed_at = EXCLUDED.computed_at
            """, (
                result.index_date,
                result.region,
                result.value,
                result.band.value,
                result.trend_1d,
                result.trend_7d,
                json.dumps(result.components.to_dict()),
                result.components.interpretation,
                result.computed_at or datetime.utcnow(),
            ))
        
        logger.info(f"Saved EGSI-M for {result.index_date}: {result.value:.1f} ({result.band.value})")
        return True
    
    except Exception as e:
        logger.error(f"Failed to save EGSI-M result: {e}")
        return False


def save_egsi_components(
    index_family: str,
    index_date: date,
    region: str,
    components: Dict[str, Dict[str, Any]]
) -> bool:
    """Save individual component values for detailed analysis."""
    try:
        with get_cursor() as cursor:
            for component_key, values in components.items():
                if component_key in ['top_drivers', 'interpretation', 'weights', 'chokepoint_version']:
                    continue
                
                raw_value = values.get('raw', values.get('value', 0))
                norm_value = values.get('normalized', values.get('contribution', 0))
                weight = values.get('weight', 0)
                contribution = values.get('contribution', 0)
                
                meta = {k: v for k, v in values.items() 
                       if k not in ['raw', 'normalized', 'value', 'weight', 'contribution']}
                
                cursor.execute("""
                    INSERT INTO egsi_components_daily (
                        index_family, index_date, region, component_key,
                        raw_value, norm_value, weight, contribution, meta
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (index_family, index_date, region, component_key) DO UPDATE SET
                        raw_value = EXCLUDED.raw_value,
                        norm_value = EXCLUDED.norm_value,
                        weight = EXCLUDED.weight,
                        contribution = EXCLUDED.contribution,
                        meta = EXCLUDED.meta,
                        computed_at = NOW()
                """, (
                    index_family,
                    index_date,
                    region,
                    component_key,
                    raw_value,
                    norm_value,
                    weight,
                    contribution,
                    json.dumps(meta),
                ))
        
        return True
    except Exception as e:
        logger.error(f"Failed to save EGSI components: {e}")
        return False


def save_egsi_drivers(
    index_family: str,
    index_date: date,
    region: str,
    drivers: List[Dict[str, Any]]
) -> bool:
    """Save top drivers for the index."""
    try:
        with get_cursor() as cursor:
            cursor.execute("""
                DELETE FROM egsi_drivers_daily 
                WHERE index_family = %s AND index_date = %s AND region = %s
            """, (index_family, index_date, region))
            
            for rank, driver in enumerate(drivers, 1):
                cursor.execute("""
                    INSERT INTO egsi_drivers_daily (
                        index_family, index_date, region, driver_type, driver_rank,
                        component_key, alert_id, headline, severity, confidence, score, meta
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    index_family,
                    index_date,
                    region,
                    'ALERT',
                    rank,
                    'theme_pressure',
                    driver.get('alert_id'),
                    driver.get('headline'),
                    driver.get('severity'),
                    driver.get('confidence'),
                    driver.get('score'),
                    json.dumps({'region': driver.get('region'), 'category': driver.get('category')}),
                ))
        
        return True
    except Exception as e:
        logger.error(f"Failed to save EGSI drivers: {e}")
        return False


def get_egsi_m_for_date(index_date: date, region: str = 'Europe') -> Optional[Dict[str, Any]]:
    """Fetch EGSI-M result for a specific date."""
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT id, index_date, region, index_value, band,
                   trend_1d, trend_7d, components_json, explanation, computed_at
            FROM egsi_m_daily
            WHERE index_date = %s AND region = %s
        """, (index_date, region))
        
        row = cursor.fetchone()
    
    if not row:
        return None
    
    return {
        'id': row['id'],
        'date': row['index_date'],
        'region': row['region'],
        'value': float(row['index_value']),
        'band': row['band'],
        'trend_1d': float(row['trend_1d']) if row['trend_1d'] else None,
        'trend_7d': float(row['trend_7d']) if row['trend_7d'] else None,
        'components': row['components_json'],
        'explanation': row['explanation'],
        'computed_at': row['computed_at'],
    }


def get_egsi_m_latest(region: str = 'Europe') -> Optional[Dict[str, Any]]:
    """Fetch most recent EGSI-M result."""
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT id, index_date, region, index_value, band,
                   trend_1d, trend_7d, components_json, explanation, computed_at
            FROM egsi_m_daily
            WHERE region = %s
            ORDER BY index_date DESC
            LIMIT 1
        """, (region,))
        
        row = cursor.fetchone()
    
    if not row:
        return None
    
    return {
        'id': row['id'],
        'date': row['index_date'],
        'region': row['region'],
        'value': float(row['index_value']),
        'band': row['band'],
        'trend_1d': float(row['trend_1d']) if row['trend_1d'] else None,
        'trend_7d': float(row['trend_7d']) if row['trend_7d'] else None,
        'components': row['components_json'],
        'explanation': row['explanation'],
        'computed_at': row['computed_at'],
    }


def get_egsi_m_delayed(delay_days: int = 1, region: str = 'Europe') -> Optional[Dict[str, Any]]:
    """Fetch EGSI-M result with delay for public access."""
    target_date = date.today() - timedelta(days=delay_days)
    
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT id, index_date, region, index_value, band,
                   trend_1d, trend_7d, components_json, explanation, computed_at
            FROM egsi_m_daily
            WHERE region = %s AND index_date <= %s
            ORDER BY index_date DESC
            LIMIT 1
        """, (region, target_date))
        
        row = cursor.fetchone()
    
    if not row:
        return None
    
    return {
        'id': row['id'],
        'date': row['index_date'],
        'region': row['region'],
        'value': float(row['index_value']),
        'band': row['band'],
        'trend_1d': float(row['trend_1d']) if row['trend_1d'] else None,
        'trend_7d': float(row['trend_7d']) if row['trend_7d'] else None,
        'components': row['components_json'],
        'explanation': row['explanation'],
        'computed_at': row['computed_at'],
    }


def get_egsi_m_history(
    days: int = 30,
    region: str = 'Europe'
) -> List[Dict[str, Any]]:
    """Fetch EGSI-M history for trend analysis."""
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT index_date, index_value, band, trend_1d, trend_7d
            FROM egsi_m_daily
            WHERE region = %s
            ORDER BY index_date DESC
            LIMIT %s
        """, (region, days))
        
        rows = cursor.fetchall()
    
    return [
        {
            'date': row['index_date'],
            'value': float(row['index_value']),
            'band': row['band'],
            'trend_1d': float(row['trend_1d']) if row['trend_1d'] else None,
            'trend_7d': float(row['trend_7d']) if row['trend_7d'] else None,
        }
        for row in rows
    ]


def compute_trends(
    current_value: float,
    region: str = 'Europe'
) -> tuple:
    """Compute 1-day and 7-day trends."""
    history = get_egsi_m_history(days=7, region=region)
    
    trend_1d = None
    trend_7d = None
    
    if len(history) >= 1:
        trend_1d = current_value - history[0]['value']
    
    if len(history) >= 7:
        avg_7d = sum(h['value'] for h in history) / len(history)
        trend_7d = current_value - avg_7d
    elif len(history) >= 1:
        avg = sum(h['value'] for h in history) / len(history)
        trend_7d = current_value - avg
    
    return trend_1d, trend_7d


def ensure_egsi_s_tables():
    """Ensure EGSI-S database tables exist."""
    try:
        with get_cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS egsi_s_daily (
                    id SERIAL PRIMARY KEY,
                    index_date DATE NOT NULL,
                    region VARCHAR(100) NOT NULL DEFAULT 'Europe',
                    index_value NUMERIC(10,2) NOT NULL,
                    band VARCHAR(20) NOT NULL,
                    trend_1d NUMERIC(10,2),
                    trend_7d NUMERIC(10,2),
                    components_json JSONB,
                    explanation TEXT,
                    data_sources TEXT[],
                    model_version VARCHAR(50) DEFAULT 'egsi_s_v1',
                    computed_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE(index_date, region)
                )
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_egsi_s_daily_date 
                ON egsi_s_daily(index_date DESC)
            """)
        logger.info("EGSI-S tables ensured")
        return True
    except Exception as e:
        logger.error(f"Error ensuring EGSI-S tables: {e}")
        return False


def save_egsi_s_result(result: EGSISResult) -> bool:
    """Save EGSI-S result to database."""
    try:
        ensure_egsi_s_tables()
        
        with get_cursor() as cursor:
            cursor.execute("""
                INSERT INTO egsi_s_daily (
                    index_date, region, index_value, band,
                    trend_1d, trend_7d, components_json, explanation,
                    data_sources, model_version, computed_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (index_date, region) DO UPDATE SET
                    index_value = EXCLUDED.index_value,
                    band = EXCLUDED.band,
                    trend_1d = EXCLUDED.trend_1d,
                    trend_7d = EXCLUDED.trend_7d,
                    components_json = EXCLUDED.components_json,
                    explanation = EXCLUDED.explanation,
                    data_sources = EXCLUDED.data_sources,
                    model_version = EXCLUDED.model_version,
                    computed_at = EXCLUDED.computed_at
            """, (
                result.index_date,
                result.region,
                result.value,
                result.band.value,
                result.trend_1d,
                result.trend_7d,
                json.dumps(result.components.to_dict()),
                result.components.interpretation,
                result.components.data_sources,
                result.model_version,
                result.computed_at or datetime.utcnow(),
            ))
        logger.info(f"Saved EGSI-S result for {result.index_date}: {result.value:.1f} ({result.band.value})")
        return True
    except Exception as e:
        logger.error(f"Error saving EGSI-S result: {e}")
        return False


def get_egsi_s_for_date(target_date: date, region: str = 'Europe') -> Optional[Dict[str, Any]]:
    """Fetch EGSI-S for a specific date."""
    try:
        with get_cursor() as cursor:
            cursor.execute("""
                SELECT index_date, region, index_value, band, trend_1d, trend_7d,
                       components_json, explanation, data_sources, model_version, computed_at
                FROM egsi_s_daily
                WHERE index_date = %s AND region = %s
            """, (target_date, region))
            row = cursor.fetchone()
        
        if not row:
            return None
        
        components = row['components_json']
        if isinstance(components, str):
            components = json.loads(components)
        
        return {
            'date': row['index_date'],
            'region': row['region'],
            'value': float(row['index_value']),
            'band': row['band'],
            'trend_1d': float(row['trend_1d']) if row['trend_1d'] else None,
            'trend_7d': float(row['trend_7d']) if row['trend_7d'] else None,
            'components': components,
            'explanation': row['explanation'],
            'data_sources': row['data_sources'] or [],
            'model_version': row['model_version'],
            'computed_at': row['computed_at'],
        }
    except Exception as e:
        logger.error(f"Error fetching EGSI-S for {target_date}: {e}")
        return None


def get_egsi_s_latest(region: str = 'Europe') -> Optional[Dict[str, Any]]:
    """Get the latest EGSI-S result."""
    try:
        with get_cursor() as cursor:
            cursor.execute("""
                SELECT index_date, region, index_value, band, trend_1d, trend_7d,
                       components_json, explanation, data_sources, model_version, computed_at
                FROM egsi_s_daily
                WHERE region = %s
                ORDER BY index_date DESC
                LIMIT 1
            """, (region,))
            row = cursor.fetchone()
        
        if not row:
            return None
        
        components = row['components_json']
        if isinstance(components, str):
            components = json.loads(components)
        
        return {
            'date': row['index_date'],
            'region': row['region'],
            'value': float(row['index_value']),
            'band': row['band'],
            'trend_1d': float(row['trend_1d']) if row['trend_1d'] else None,
            'trend_7d': float(row['trend_7d']) if row['trend_7d'] else None,
            'components': components,
            'explanation': row['explanation'],
            'data_sources': row['data_sources'] or [],
            'model_version': row['model_version'],
            'computed_at': row['computed_at'],
        }
    except Exception as e:
        logger.error(f"Error fetching latest EGSI-S: {e}")
        return None


def get_egsi_s_history(days: int = 30, region: str = 'Europe') -> List[Dict[str, Any]]:
    """Fetch EGSI-S history."""
    try:
        with get_cursor() as cursor:
            cursor.execute("""
                SELECT index_date, index_value, band, trend_1d, trend_7d
                FROM egsi_s_daily
                WHERE region = %s
                ORDER BY index_date DESC
                LIMIT %s
            """, (region, days))
            rows = cursor.fetchall()
        
        return [
            {
                'date': row['index_date'],
                'value': float(row['index_value']),
                'band': row['band'],
                'trend_1d': float(row['trend_1d']) if row['trend_1d'] else None,
                'trend_7d': float(row['trend_7d']) if row['trend_7d'] else None,
            }
            for row in rows
        ]
    except Exception as e:
        logger.error(f"Error fetching EGSI-S history: {e}")
        return []


def compute_egsi_s_trends(current_value: float, region: str = 'Europe') -> tuple:
    """Compute 1-day and 7-day trends for EGSI-S."""
    history = get_egsi_s_history(days=7, region=region)
    
    trend_1d = None
    trend_7d = None
    
    if len(history) >= 1:
        trend_1d = current_value - history[0]['value']
    
    if len(history) >= 7:
        avg_7d = sum(h['value'] for h in history) / len(history)
        trend_7d = current_value - avg_7d
    elif len(history) >= 1:
        avg = sum(h['value'] for h in history) / len(history)
        trend_7d = current_value - avg
    
    return trend_1d, trend_7d
