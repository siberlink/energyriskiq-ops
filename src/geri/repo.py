"""
GERI v1 Repository Layer

READ from alert_events (INPUT ONLY)
WRITE to intel_indices_daily (OUTPUT ONLY)
"""
import logging
import json
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional, Dict, Any

from src.db.db import get_cursor, execute_one, get_production_cursor, execute_production_one
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
    from src.geri.health import utc_bounds
    start_of_day, end_of_day = utc_bounds(target_date)
    
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
      AND created_at >= (%s AT TIME ZONE 'UTC')
      AND created_at < (%s AT TIME ZONE 'UTC')
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


def _recalc_band(row_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Recalculate band from value to prevent stale label mismatches."""
    if row_dict and row_dict.get("data_quality") == "UNAVAILABLE":
        row_dict["stored_value"] = row_dict.get("value")
        row_dict.update(value=None, band="UNAVAILABLE", trend_1d=None, trend_7d=None)
    elif row_dict and row_dict.get('value') is not None:
        row_dict['band'] = get_band(int(row_dict['value'])).value
    return row_dict


def attach_health(rows, start, end, include_missing=True):
    """Read-time overlay: never rewrite historical scores."""
    with get_production_cursor() as cursor:
        cursor.execute("SELECT * FROM geri_daily_health WHERE index_date BETWEEN %s AND %s",
                       (start, end))
        health = {r["index_date"]: dict(r) for r in cursor.fetchall()}
    seen = set()
    output = []
    for original in rows:
        row = dict(original)
        day = row["date"]
        seen.add(day)
        h = health.get(day, {})
        row["data_quality"] = h.get("data_quality", "OK")
        row["data_health"] = h
        output.append(_recalc_band(row))
    if include_missing:
        for day, h in health.items():
            if day not in seen and h["data_quality"] == "UNAVAILABLE":
                output.append({
                    "index_id": INDEX_ID, "date": day, "value": None, "band": "UNAVAILABLE",
                    "data_quality": "UNAVAILABLE", "data_health": h, "components": {},
                    "trend_1d": None, "trend_7d": None, "computed_at": None,
                })
    return sorted(output, key=lambda r: r["date"])


def get_index_for_date(target_date: date) -> Optional[Dict[str, Any]]:
    """Get stored index value for a specific date."""
    sql = """
    SELECT id, index_id, date, value, band, trend_1d, trend_7d, 
           components, model_version, computed_at
    FROM intel_indices_daily
    WHERE index_id = %s AND date = %s
    """
    
    with get_production_cursor() as cursor:
        cursor.execute(sql, (INDEX_ID, target_date))
        row = cursor.fetchone()
        
        if row:
            return attach_health([dict(row)], target_date, target_date)[0]
    
    rows = attach_health([], target_date, target_date)
    return rows[0] if rows else None


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
    with get_production_cursor() as cursor:
        cursor.execute(sql, (INDEX_ID, from_date, to_date))
        rows = cursor.fetchall()
        for row in rows:
            results.append(_recalc_band(dict(row)))
    
    return attach_health(results, from_date, to_date)


def get_latest_index() -> Optional[Dict[str, Any]]:
    """Get the most recent index value.
    
    Orders by observation date; rebuilding an old date cannot make it latest.
    """
    sql = """
    SELECT id, index_id, date, value, band, trend_1d, trend_7d,
           components, model_version, computed_at
    FROM intel_indices_daily
    WHERE index_id = %s
    ORDER BY date DESC
    LIMIT 1
    """
    
    with get_production_cursor() as cursor:
        cursor.execute(sql, (INDEX_ID,))
        row = cursor.fetchone()
        if row:
            end = max(row["date"], datetime.now(timezone.utc).date() - timedelta(days=1))
            return attach_health([dict(row)], row["date"], end)[-1]
    
    return None


def get_delayed_index(delay_days: int = 1) -> Optional[Dict[str, Any]]:
    """Get the second-last GERI index for public display (true 24h delay).
    
    Returns the second most recently computed GERI. This creates a true 24h delay:
    - Latest record (LIMIT 1) is for authenticated users (real-time)
    - Second-last record (OFFSET 1) is for public/unauthenticated (24h delayed)
    
    Orders by computed_at DESC to ensure proper chronological ordering.
    """
    latest = get_latest_index()
    return get_index_for_date(latest["date"] - timedelta(days=delay_days)) if latest else None


def get_previous_values(target_date: date, days: int = 7) -> List[int]:
    """Get previous N days of index values for trend calculation."""
    sql = """
    SELECT value
    FROM intel_indices_daily
    WHERE index_id = %s AND date < %s
      AND NOT EXISTS (SELECT 1 FROM geri_daily_health h WHERE h.index_date=date
                      AND h.data_quality = ANY(%s::text[]))
    ORDER BY date DESC
    LIMIT %s
    """
    
    values = []
    with get_cursor() as cursor:
        from src.geri.health import excluded_history_statuses
        cursor.execute(sql, (INDEX_ID, target_date, excluded_history_statuses(), days))
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
    SELECT date, components
    FROM intel_indices_daily
    WHERE index_id = %s AND date >= %s AND date < %s
      AND NOT EXISTS (SELECT 1 FROM geri_daily_health h WHERE h.index_date=date
                      AND h.data_quality = ANY(%s::text[]))
    ORDER BY date
    """
    
    baseline = HistoricalBaseline()
    baseline.source_dates = []
    
    high_impact_scores = []
    regional_spike_scores = []
    asset_risk_scores = []
    region_concentration_scores = []
    
    with get_cursor() as cursor:
        from src.geri.health import excluded_history_statuses
        cursor.execute(sql, (INDEX_ID, start_date, target_date, excluded_history_statuses()))
        rows = cursor.fetchall()
        
        for row in rows:
            baseline.source_dates.append(row["date"].isoformat())
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


def save_index(result: GERIResult, force: bool = False, reason=None, apply_revision=False) -> bool:
    """
    Save GERI result to intel_indices_daily.
    OUTPUT ONLY - writes only to intel_indices_daily.
    """
    from src.geri.publication import publish
    return publish(result, force=force, reason=reason, apply_revision=apply_revision)


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
