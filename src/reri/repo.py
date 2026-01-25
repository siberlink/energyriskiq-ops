"""
RERI/EERI Repository Layer

Database operations for regional indices.
"""
import logging
from datetime import date, datetime, timedelta
from typing import Optional, List, Dict, Any
import json

from src.db.db import get_cursor
from src.reri.types import (
    AlertRecord,
    RERIResult,
    EERIComponents,
    RiskBand,
    get_band,
    EERI_INDEX_ID,
    MODEL_VERSION,
)

logger = logging.getLogger(__name__)


def fetch_alerts_for_date(
    target_date: date,
    region_filter: Optional[str] = None
) -> List[AlertRecord]:
    """
    Fetch all alerts for a specific date from alert_events.
    
    Args:
        target_date: Date to fetch alerts for
        region_filter: Optional region string to filter (e.g., 'Europe')
    
    Returns:
        List of AlertRecord objects
    """
    with get_cursor() as cursor:
        if region_filter:
            cursor.execute("""
                SELECT 
                    id, alert_type, severity, confidence,
                    scope_region, scope_assets, headline, body,
                    category, created_at
                FROM alert_events
                WHERE DATE(created_at) = %s
                  AND scope_region ILIKE %s
                ORDER BY created_at DESC
            """, (target_date, f'%{region_filter}%'))
        else:
            cursor.execute("""
                SELECT 
                    id, alert_type, severity, confidence,
                    scope_region, scope_assets, headline, body,
                    category, created_at
                FROM alert_events
                WHERE DATE(created_at) = %s
                ORDER BY created_at DESC
            """, (target_date,))
        
        rows = cursor.fetchall()
    
    alerts = []
    for row in rows:
        assets = row[5] if row[5] else []
        if isinstance(assets, str):
            assets = [assets]
        
        alerts.append(AlertRecord(
            id=row[0],
            alert_type=row[1],
            severity=row[2],
            confidence=float(row[3]) if row[3] else None,
            region=row[4],
            assets=assets,
            headline=row[6],
            body=row[7],
            category=row[8],
            created_at=row[9],
        ))
    
    return alerts


def fetch_historical_severity_values(
    region_id: str,
    before_date: date,
    days: int = 3
) -> List[float]:
    """
    Fetch historical severity pressure values for velocity calculation.
    
    Returns list of S values for the last N days before the target date.
    """
    start_date = before_date - timedelta(days=days)
    
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT date, (components->'reri_eu'->'components'->'severity_pressure'->>'raw')::float as s_value
            FROM reri_indices_daily
            WHERE region_id = %s
              AND date >= %s
              AND date < %s
            ORDER BY date ASC
        """, (region_id, start_date, before_date))
        
        rows = cursor.fetchall()
    
    return [row[1] for row in rows if row[1] is not None]


def fetch_historical_component_values(
    region_id: str,
    before_date: date,
    days: int = 90
) -> List[Dict[str, float]]:
    """
    Fetch historical component values for rolling normalization.
    
    Returns list of dicts with raw component values per day.
    """
    start_date = before_date - timedelta(days=days)
    
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT 
                date,
                (components->'reri_eu'->'components'->'severity_pressure'->>'raw')::float as severity_pressure,
                (components->'reri_eu'->'components'->'high_impact_count'->>'raw')::int as high_impact_count,
                (components->'reri_eu'->'components'->'asset_overlap'->>'raw')::int as asset_overlap,
                (components->'reri_eu'->'components'->'velocity'->>'raw')::float as velocity
            FROM reri_indices_daily
            WHERE region_id = %s
              AND date >= %s
              AND date < %s
            ORDER BY date ASC
        """, (region_id, start_date, before_date))
        
        rows = cursor.fetchall()
    
    return [
        {
            'date': row[0],
            'severity_pressure': row[1] or 0.0,
            'high_impact_count': row[2] or 0,
            'asset_overlap': row[3] or 0,
            'velocity': row[4] or 0.0,
        }
        for row in rows
    ]


def fetch_previous_values(
    index_id: str,
    before_date: date,
    days: int = 7
) -> List[Dict[str, Any]]:
    """
    Fetch previous index values for trend calculation.
    """
    start_date = before_date - timedelta(days=days)
    
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT date, value
            FROM reri_indices_daily
            WHERE index_id = %s
              AND date >= %s
              AND date < %s
            ORDER BY date DESC
        """, (index_id, start_date, before_date))
        
        rows = cursor.fetchall()
    
    return [{'date': row[0], 'value': row[1]} for row in rows]


def compute_trends(
    current_value: int,
    previous_values: List[Dict[str, Any]]
) -> tuple[Optional[int], Optional[int]]:
    """
    Compute 1-day and 7-day trends.
    
    Returns:
        (trend_1d, trend_7d) where each is current - previous
    """
    trend_1d = None
    trend_7d = None
    
    if previous_values:
        yesterday = previous_values[0]['value'] if previous_values else None
        if yesterday is not None:
            trend_1d = current_value - yesterday
        
        if len(previous_values) >= 7:
            week_ago = previous_values[6]['value']
            if week_ago is not None:
                trend_7d = current_value - week_ago
        elif len(previous_values) >= 3:
            avg_value = sum(v['value'] for v in previous_values) / len(previous_values)
            trend_7d = current_value - int(avg_value)
    
    return trend_1d, trend_7d


def save_reri_result(result: RERIResult) -> int:
    """
    Save RERI/EERI result to database.
    Uses upsert to handle re-computation.
    
    Returns:
        Row ID of the saved record
    """
    with get_cursor() as cursor:
        cursor.execute("""
            INSERT INTO reri_indices_daily (
                index_id, region_id, date, value, band,
                trend_1d, trend_7d, components, drivers,
                model_version, computed_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT (index_id, date) DO UPDATE SET
                value = EXCLUDED.value,
                band = EXCLUDED.band,
                trend_1d = EXCLUDED.trend_1d,
                trend_7d = EXCLUDED.trend_7d,
                components = EXCLUDED.components,
                drivers = EXCLUDED.drivers,
                model_version = EXCLUDED.model_version,
                computed_at = EXCLUDED.computed_at
            RETURNING id
        """, (
            result.index_id,
            result.region_id,
            result.index_date,
            result.value,
            result.band.value,
            result.trend_1d,
            result.trend_7d,
            json.dumps(result.components.to_dict()),
            json.dumps(result.drivers),
            result.model_version,
            result.computed_at or datetime.utcnow(),
        ))
        
        row = cursor.fetchone()
        row_id = row[0] if row else 0
    
    logger.info(f"Saved RERI result: {result.index_id} = {result.value} ({result.band.value})")
    return row_id


def get_latest_reri(index_id: str) -> Optional[RERIResult]:
    """
    Get the latest RERI/EERI result for an index.
    """
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT 
                index_id, region_id, date, value, band,
                trend_1d, trend_7d, components, drivers,
                model_version, computed_at
            FROM reri_indices_daily
            WHERE index_id = %s
            ORDER BY date DESC
            LIMIT 1
        """, (index_id,))
        
        row = cursor.fetchone()
    
    if not row:
        return None
    
    components_data = row[7] if isinstance(row[7], dict) else json.loads(row[7])
    drivers_data = row[8] if isinstance(row[8], (dict, list)) else json.loads(row[8]) if row[8] else []
    
    eeri_components = EERIComponents()
    if 'reri_eu' in components_data:
        eeri_components.reri_eu_value = components_data['reri_eu'].get('value', 0)
    if 'theme_pressure' in components_data:
        eeri_components.theme_pressure_raw = components_data['theme_pressure'].get('raw', 0)
        eeri_components.theme_pressure_norm = components_data['theme_pressure'].get('normalized', 0)
    if 'asset_transmission' in components_data:
        eeri_components.asset_transmission_raw = components_data['asset_transmission'].get('raw', 0)
        eeri_components.asset_transmission_norm = components_data['asset_transmission'].get('normalized', 0)
    if 'top_drivers' in components_data:
        eeri_components.top_drivers = components_data['top_drivers']
    if 'interpretation' in components_data:
        eeri_components.interpretation = components_data['interpretation']
    
    return RERIResult(
        index_id=row[0],
        region_id=row[1],
        index_date=row[2],
        value=row[3],
        band=RiskBand(row[4]),
        trend_1d=row[5],
        trend_7d=row[6],
        components=eeri_components,
        drivers=drivers_data,
        model_version=row[9],
        computed_at=row[10],
    )


def get_reri_for_date(index_id: str, target_date: date) -> Optional[RERIResult]:
    """
    Get RERI/EERI result for a specific date.
    """
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT 
                index_id, region_id, date, value, band,
                trend_1d, trend_7d, components, drivers,
                model_version, computed_at
            FROM reri_indices_daily
            WHERE index_id = %s AND date = %s
        """, (index_id, target_date))
        
        row = cursor.fetchone()
    
    if not row:
        return None
    
    components_data = row[7] if isinstance(row[7], dict) else json.loads(row[7])
    drivers_data = row[8] if isinstance(row[8], (dict, list)) else json.loads(row[8]) if row[8] else []
    
    eeri_components = EERIComponents()
    
    return RERIResult(
        index_id=row[0],
        region_id=row[1],
        index_date=row[2],
        value=row[3],
        band=RiskBand(row[4]),
        trend_1d=row[5],
        trend_7d=row[6],
        components=eeri_components,
        drivers=drivers_data,
        model_version=row[9],
        computed_at=row[10],
    )


def count_days_of_history(index_id: str) -> int:
    """
    Count how many days of history exist for an index.
    """
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT COUNT(DISTINCT date)
            FROM reri_indices_daily
            WHERE index_id = %s
        """, (index_id,))
        
        result = cursor.fetchone()
    
    return result[0] if result else 0


def get_canonical_regions() -> List[Dict[str, Any]]:
    """
    Fetch all canonical regions from database.
    """
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT region_id, region_name, region_type, aliases, core_assets, is_active
            FROM reri_canonical_regions
            WHERE is_active = TRUE
        """)
        
        rows = cursor.fetchall()
    
    return [
        {
            'region_id': row[0],
            'region_name': row[1],
            'region_type': row[2],
            'aliases': row[3],
            'core_assets': row[4],
            'is_active': row[5],
        }
        for row in rows
    ]
