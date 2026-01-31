"""
GERI v1 Repository Layer

READ from alert_events (INPUT ONLY)
WRITE to intel_indices_daily (OUTPUT ONLY)
"""
import logging
import json
from datetime import date, datetime, timedelta
from typing import List, Optional, Dict, Any

from src.db.db import get_cursor, execute_one
from src.geri.types import (
    AlertRecord,
    GERIResult,
    GERIComponents,
    RiskBand,
    get_band,
    INDEX_ID,
    MODEL_VERSION,
    VALID_ALERT_TYPES,
    HistoricalBaseline,
)

logger = logging.getLogger(__name__)


def get_alerts_for_date(target_date: date) -> List[AlertRecord]:
    """
    Read alerts from alert_events for a specific UTC day.
    INPUT ONLY - does not modify alert_events.
    Extracts event category from raw_input JSON (driver_events[0].category).
    """
    start_of_day = datetime.combine(target_date, datetime.min.time())
    end_of_day = datetime.combine(target_date + timedelta(days=1), datetime.min.time())
    
    sql = """
    SELECT 
        id,
        alert_type,
        severity,
        confidence as risk_score,
        scope_region as region,
        1.0 as weight,
        created_at,
        headline,
        body,
        raw_input
    FROM alert_events
    WHERE alert_type = ANY(%s)
      AND created_at >= %s
      AND created_at < %s
    ORDER BY created_at
    """
    
    alerts = []
    with get_cursor() as cursor:
        cursor.execute(sql, (VALID_ALERT_TYPES, start_of_day, end_of_day))
        rows = cursor.fetchall()
        
        for row in rows:
            risk_score_val = row['risk_score']
            if risk_score_val is not None:
                risk_score_val = float(risk_score_val)
            
            # Extract event category from raw_input JSON
            # For HIGH_IMPACT_EVENT: raw_input.category (flat)
            # For REGIONAL_RISK_SPIKE: raw_input.driver_events[0].category (nested)
            event_category = None
            raw_input = row.get('raw_input')
            if raw_input:
                if isinstance(raw_input, str):
                    try:
                        raw_input = json.loads(raw_input)
                    except:
                        raw_input = {}
                # Try flat category first (HIGH_IMPACT_EVENT)
                if raw_input.get('category'):
                    event_category = raw_input.get('category')
                # Fall back to driver_events (REGIONAL_RISK_SPIKE)
                elif raw_input.get('driver_events'):
                    driver_events = raw_input.get('driver_events', [])
                    if driver_events and len(driver_events) > 0:
                        event_category = driver_events[0].get('category')
            
            alerts.append(AlertRecord(
                id=row['id'],
                alert_type=row['alert_type'],
                severity=row['severity'],
                risk_score=risk_score_val,
                region=row['region'],
                weight=float(row['weight']) if row['weight'] else 1.0,
                created_at=row['created_at'],
                headline=row['headline'],
                body=row.get('body'),
                category=event_category,
            ))
    
    logger.info(f"Retrieved {len(alerts)} alerts for date {target_date}")
    return alerts


def get_index_for_date(target_date: date) -> Optional[Dict[str, Any]]:
    """Get stored index value for a specific date."""
    sql = """
    SELECT id, index_id, date, value, band, trend_1d, trend_7d, 
           components, model_version, computed_at
    FROM intel_indices_daily
    WHERE index_id = %s AND date = %s
    """
    
    with get_cursor() as cursor:
        cursor.execute(sql, (INDEX_ID, target_date))
        row = cursor.fetchone()
        
        if row:
            return dict(row)
    
    return None


def get_index_history(from_date: date, to_date: date) -> List[Dict[str, Any]]:
    """Get index history for a date range (ascending)."""
    sql = """
    SELECT id, index_id, date, value, band, trend_1d, trend_7d,
           components, model_version, computed_at
    FROM intel_indices_daily
    WHERE index_id = %s AND date >= %s AND date <= %s
    ORDER BY date ASC
    """
    
    results = []
    with get_cursor() as cursor:
        cursor.execute(sql, (INDEX_ID, from_date, to_date))
        rows = cursor.fetchall()
        for row in rows:
            results.append(dict(row))
    
    return results


def get_latest_index() -> Optional[Dict[str, Any]]:
    """Get the most recent index value.
    
    Orders by computed_at DESC to ensure we get the most recently computed record,
    which represents the latest available GERI data.
    """
    sql = """
    SELECT id, index_id, date, value, band, trend_1d, trend_7d,
           components, model_version, computed_at
    FROM intel_indices_daily
    WHERE index_id = %s
    ORDER BY computed_at DESC
    LIMIT 1
    """
    
    with get_cursor() as cursor:
        cursor.execute(sql, (INDEX_ID,))
        row = cursor.fetchone()
        if row:
            return dict(row)
    
    return None


def get_delayed_index(delay_days: int = 1) -> Optional[Dict[str, Any]]:
    """Get the second-last GERI index for public display (true 24h delay).
    
    Returns the second most recently computed GERI. This creates a true 24h delay:
    - Latest record (LIMIT 1) is for authenticated users (real-time)
    - Second-last record (OFFSET 1) is for public/unauthenticated (24h delayed)
    
    Orders by computed_at DESC to ensure proper chronological ordering.
    """
    sql = """
    SELECT id, index_id, date, value, band, trend_1d, trend_7d,
           components, model_version, computed_at
    FROM intel_indices_daily
    WHERE index_id = %s
    ORDER BY computed_at DESC
    LIMIT 1 OFFSET 1
    """
    
    with get_cursor() as cursor:
        cursor.execute(sql, (INDEX_ID,))
        row = cursor.fetchone()
        if row:
            return dict(row)
    
    return None


def get_previous_values(target_date: date, days: int = 7) -> List[int]:
    """Get previous N days of index values for trend calculation."""
    sql = """
    SELECT value
    FROM intel_indices_daily
    WHERE index_id = %s AND date < %s
    ORDER BY date DESC
    LIMIT %s
    """
    
    values = []
    with get_cursor() as cursor:
        cursor.execute(sql, (INDEX_ID, target_date, days))
        rows = cursor.fetchall()
        for row in rows:
            values.append(row['value'])
    
    return values


def get_historical_baseline(target_date: date, lookback_days: int = 90) -> HistoricalBaseline:
    """
    Get rolling baseline stats from past intel_indices_daily rows.
    Used for normalization.
    """
    start_date = target_date - timedelta(days=lookback_days)
    
    sql = """
    SELECT components
    FROM intel_indices_daily
    WHERE index_id = %s AND date >= %s AND date < %s
    ORDER BY date
    """
    
    baseline = HistoricalBaseline()
    
    high_impact_scores = []
    regional_spike_scores = []
    asset_risk_scores = []
    region_concentration_scores = []
    
    with get_cursor() as cursor:
        cursor.execute(sql, (INDEX_ID, start_date, target_date))
        rows = cursor.fetchall()
        
        for row in rows:
            components = row['components']
            if isinstance(components, str):
                components = json.loads(components)
            
            high_impact_scores.append(components.get('high_impact_score', 0))
            regional_spike_scores.append(components.get('regional_spike_score', 0))
            asset_risk_scores.append(components.get('asset_risk_score', 0))
            region_concentration_scores.append(components.get('region_concentration_score_raw', 0))
    
    baseline.days_count = len(high_impact_scores)
    
    if baseline.days_count > 0:
        baseline.high_impact_min = min(high_impact_scores)
        baseline.high_impact_max = max(high_impact_scores)
        baseline.regional_spike_min = min(regional_spike_scores)
        baseline.regional_spike_max = max(regional_spike_scores)
        baseline.asset_risk_min = min(asset_risk_scores)
        baseline.asset_risk_max = max(asset_risk_scores)
        baseline.region_concentration_min = min(region_concentration_scores)
        baseline.region_concentration_max = max(region_concentration_scores)
    
    return baseline


def save_index(result: GERIResult, force: bool = False) -> bool:
    """
    Save GERI result to intel_indices_daily.
    OUTPUT ONLY - writes only to intel_indices_daily.
    """
    components_json = json.dumps(result.components.to_dict())
    interpretation = getattr(result.components, 'interpretation', None) or ''
    
    if force:
        sql = """
        INSERT INTO intel_indices_daily 
            (index_id, date, value, band, trend_1d, trend_7d, components, interpretation, model_version, computed_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (index_id, date) 
        DO UPDATE SET 
            value = EXCLUDED.value,
            band = EXCLUDED.band,
            trend_1d = EXCLUDED.trend_1d,
            trend_7d = EXCLUDED.trend_7d,
            components = EXCLUDED.components,
            interpretation = EXCLUDED.interpretation,
            model_version = EXCLUDED.model_version,
            computed_at = NOW()
        RETURNING id
        """
    else:
        sql = """
        INSERT INTO intel_indices_daily 
            (index_id, date, value, band, trend_1d, trend_7d, components, interpretation, model_version, computed_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (index_id, date) DO NOTHING
        RETURNING id
        """
    
    with get_cursor() as cursor:
        cursor.execute(sql, (
            result.index_id,
            result.index_date,
            result.value,
            result.band.value,
            result.trend_1d,
            result.trend_7d,
            components_json,
            interpretation,
            result.model_version,
        ))
        row = cursor.fetchone()
        
        if row:
            logger.info(f"Saved GERI index for {result.index_date}: value={result.value}, band={result.band.value}")
            return True
        else:
            logger.info(f"GERI index for {result.index_date} already exists (skipped)")
            return False


def get_date_range_with_alerts() -> tuple:
    """Get the earliest and latest dates with alerts in alert_events."""
    sql = """
    SELECT 
        MIN(DATE(created_at)) as min_date,
        MAX(DATE(created_at)) as max_date
    FROM alert_events
    WHERE alert_type = ANY(%s)
    """
    
    with get_cursor() as cursor:
        cursor.execute(sql, (VALID_ALERT_TYPES,))
        row = cursor.fetchone()
        if row and row['min_date'] and row['max_date']:
            return row['min_date'], row['max_date']
    
    return None, None
