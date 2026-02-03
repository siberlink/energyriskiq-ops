"""
EERI Pro API Routes

Pro-tier endpoints for real-time EERI data with full component transparency,
asset stress data, and historical intelligence.

Mounted under /api/v1/eeri-pro
"""
import logging
from datetime import date, datetime, timedelta
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Query, Depends, Header
import json

from src.reri import ENABLE_EERI
from src.reri.types import EERI_INDEX_ID
from src.reri.eeri_history_service import (
    get_latest_eeri_public,
    get_eeri_by_date,
    get_all_eeri_dates,
    get_eeri_available_months,
)
from src.db.db import get_cursor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/eeri-pro", tags=["EERI Pro"])

ASSET_CLASSES = ['gas', 'oil', 'freight', 'fx', 'power', 'lng', 'electricity']

ASSET_DISPLAY_NAMES = {
    'gas': 'Natural Gas',
    'oil': 'Crude Oil',
    'freight': 'Freight/Shipping',
    'fx': 'Currency/FX',
    'power': 'Power Grid',
    'lng': 'LNG',
    'electricity': 'Electricity',
}

RISK_BAND_COLORS = {
    'LOW': '#22c55e',
    'MODERATE': '#eab308',
    'ELEVATED': '#f97316',
    'CRITICAL': '#ef4444',
}


def check_enabled():
    """Raise 503 if EERI module is disabled."""
    if not ENABLE_EERI:
        raise HTTPException(
            status_code=503,
            detail="EERI module is disabled. Set ENABLE_EERI=true to enable."
        )


def verify_pro_access(authorization: Optional[str] = Header(None)):
    """
    Verify user has Pro-tier access.
    For now, returns True for authenticated users - plan verification handled by frontend.
    """
    return True


ASSET_KEYWORDS = {
    'gas': ['gas', 'pipeline', 'gazprom', 'ttf', 'lng terminal', 'natural gas', 'nord stream', 'turkstream'],
    'oil': ['oil', 'crude', 'brent', 'petroleum', 'refinery', 'opec', 'barrel'],
    'freight': ['freight', 'shipping', 'tanker', 'vessel', 'maritime', 'suez', 'red sea', 'houthi'],
    'fx': ['currency', 'euro', 'dollar', 'ruble', 'forex', 'exchange rate'],
    'power': ['power', 'electricity', 'grid', 'blackout', 'nuclear', 'renewable', 'solar', 'wind'],
    'lng': ['lng', 'liquefied', 'terminal', 'regasification', 'cargoes'],
    'electricity': ['electricity', 'power grid', 'megawatt', 'interconnector'],
}

def _infer_assets_from_text(headline: str, body: str) -> List[str]:
    """Infer asset classes from alert text content."""
    text = (headline + ' ' + body).lower()
    found_assets = []
    for asset, keywords in ASSET_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            found_assets.append(asset)
    return found_assets if found_assets else ['gas', 'oil']

def _compute_asset_stress_from_alerts() -> List[Dict[str, Any]]:
    """
    Compute asset stress levels from recent alert data.
    Returns normalized stress values for each asset class.
    """
    from src.db.db import get_connection
    
    asset_stress = []
    asset_scores = {asset: {'count': 0, 'severity_sum': 0, 'prev_count': 0} for asset in ASSET_CLASSES}
    
    try:
        with get_connection() as conn:
            cur = conn.cursor()
            
            cur.execute("""
                SELECT headline, body, scope_assets, severity
                FROM alert_events 
                WHERE scope_region = 'Europe'
                  AND created_at >= CURRENT_DATE - INTERVAL '7 days'
            """)
            current_rows = cur.fetchall()
            
            for row in current_rows:
                headline = row[0] or ''
                body = row[1] or ''
                scope_assets = row[2] or []
                severity = row[3] or 3
                
                assets = scope_assets if scope_assets else _infer_assets_from_text(headline, body)
                for asset in assets:
                    asset_lower = asset.lower()
                    if asset_lower in asset_scores:
                        asset_scores[asset_lower]['count'] += 1
                        asset_scores[asset_lower]['severity_sum'] += severity
            
            cur.execute("""
                SELECT headline, body, scope_assets
                FROM alert_events 
                WHERE scope_region = 'Europe'
                  AND created_at >= CURRENT_DATE - INTERVAL '14 days'
                  AND created_at < CURRENT_DATE - INTERVAL '7 days'
            """)
            prev_rows = cur.fetchall()
            
            for row in prev_rows:
                headline = row[0] or ''
                body = row[1] or ''
                scope_assets = row[2] or []
                
                assets = scope_assets if scope_assets else _infer_assets_from_text(headline, body)
                for asset in assets:
                    asset_lower = asset.lower()
                    if asset_lower in asset_scores:
                        asset_scores[asset_lower]['prev_count'] += 1
            
            cur.close()
        
    except Exception as e:
        logger.warning(f"Error fetching alert data for asset stress: {e}")
    
    max_count = max((d['count'] for d in asset_scores.values()), default=1) or 1
    max_severity = max((d['severity_sum'] for d in asset_scores.values()), default=1) or 1
    
    for asset in ASSET_CLASSES:
        data = asset_scores[asset]
        
        count_norm = min(100, (data['count'] / max_count) * 100) if max_count > 0 else 0
        severity_norm = min(100, (data['severity_sum'] / max_severity) * 100) if max_severity > 0 else 0
        score = round(0.4 * count_norm + 0.6 * severity_norm, 1)
        
        if score >= 80:
            status = 'CRITICAL'
            status_label = 'Severe'
        elif score >= 60:
            status = 'ELEVATED'
            status_label = 'High'
        elif score >= 40:
            status = 'MODERATE'
            status_label = 'Elevated'
        elif score >= 20:
            status = 'LOW'
            status_label = 'Moderate'
        else:
            status = 'MINIMAL'
            status_label = 'Low'
        
        if data['count'] > data['prev_count'] * 1.2:
            trend = '↑'
        elif data['count'] < data['prev_count'] * 0.8:
            trend = '↓'
        else:
            trend = '→'
        
        asset_stress.append({
            'asset': asset,
            'display_name': ASSET_DISPLAY_NAMES.get(asset, asset.title()),
            'score': score,
            'status': status,
            'status_label': status_label,
            'trend': trend,
            'color': RISK_BAND_COLORS.get(status, '#94a3b8'),
        })
    
    asset_stress.sort(key=lambda x: x['score'], reverse=True)
    return asset_stress


def _extract_component_breakdown(components: Dict[str, Any], eeri_value: float) -> Dict[str, Any]:
    """
    Extract EERI component breakdown for Pro transparency view.
    Shows normalized contribution values (never raw weights).
    """
    reri_eu = components.get('reri_eu', {})
    theme_pressure = components.get('theme_pressure', {})
    asset_transmission = components.get('asset_transmission', {})
    contagion = components.get('contagion', {})
    
    reri_contribution = (reri_eu.get('normalized', 0) * 0.45) if isinstance(reri_eu, dict) else 0
    theme_contribution = (theme_pressure.get('normalized', 0) * 0.25) if isinstance(theme_pressure, dict) else 0
    asset_contribution = (asset_transmission.get('normalized', 0) * 0.20) if isinstance(asset_transmission, dict) else 0
    contagion_contribution = (contagion.get('normalized', 0) * 0.10) if isinstance(contagion, dict) else 0
    
    total = reri_contribution + theme_contribution + asset_contribution + contagion_contribution
    
    return {
        'total_value': round(eeri_value, 1),
        'components': [
            {
                'name': 'Regional Risk (RERI_EU)',
                'short_name': 'RERI_EU',
                'contribution': round(reri_contribution, 1),
                'percentage': round((reri_contribution / total * 100) if total > 0 else 0, 1),
                'color': '#3b82f6',
                'description': 'Base regional escalation risk for Europe',
            },
            {
                'name': 'Theme Pressure',
                'short_name': 'Themes',
                'contribution': round(theme_contribution, 1),
                'percentage': round((theme_contribution / total * 100) if total > 0 else 0, 1),
                'color': '#8b5cf6',
                'description': 'Weighted severity by event category',
            },
            {
                'name': 'Asset Transmission',
                'short_name': 'Assets',
                'contribution': round(asset_contribution, 1),
                'percentage': round((asset_contribution / total * 100) if total > 0 else 0, 1),
                'color': '#f59e0b',
                'description': 'Risk transmission across energy asset classes',
            },
            {
                'name': 'Contagion Risk',
                'short_name': 'Contagion',
                'contribution': round(contagion_contribution, 1),
                'percentage': round((contagion_contribution / total * 100) if total > 0 else 0, 1),
                'color': '#ef4444',
                'description': 'Spillover risk from adjacent regions',
            },
        ],
    }


def _format_top_drivers(drivers: List[Any], limit: int = 5) -> List[Dict[str, Any]]:
    """Format top drivers with full Pro-tier details."""
    formatted = []
    
    for i, driver in enumerate(drivers[:limit]):
        if isinstance(driver, dict):
            formatted.append({
                'rank': i + 1,
                'headline': driver.get('headline', driver.get('title', 'Unknown')),
                'title': driver.get('title', driver.get('headline', 'Unknown')),
                'theme': driver.get('theme', driver.get('category', 'general')),
                'severity': driver.get('severity', driver.get('risk_score', 50)),
                'confidence': driver.get('confidence', 75),
                'assets_affected': driver.get('assets_affected', driver.get('affected_assets', [])),
                'region': driver.get('region', 'europe'),
                'driver_class': 'high_impact' if driver.get('severity', 50) >= 70 else 'moderate',
            })
        elif isinstance(driver, str):
            formatted.append({
                'rank': i + 1,
                'headline': driver,
                'title': driver,
                'theme': 'general',
                'severity': 50,
                'confidence': 50,
                'assets_affected': [],
                'region': 'europe',
                'driver_class': 'moderate',
            })
    
    return formatted


@router.get("/realtime")
async def get_eeri_realtime():
    """
    Get real-time EERI data for Pro subscribers.
    
    Returns the latest EERI with full component transparency.
    """
    check_enabled()
    
    result = get_latest_eeri_public()
    
    if not result:
        return {
            'success': False,
            'message': 'No EERI data available',
            'data': None,
        }
    
    components = result.get('components', {})
    eeri_value = result.get('value', 0)
    
    return {
        'success': True,
        'data': {
            'value': eeri_value,
            'band': result.get('band', 'LOW'),
            'band_color': RISK_BAND_COLORS.get(result.get('band', 'LOW'), '#22c55e'),
            'trend_1d': result.get('trend_1d', 0),
            'trend_7d': result.get('trend_7d', 0),
            'date': result.get('date'),
            'computed_at': result.get('computed_at'),
            'interpretation': result.get('interpretation', ''),
            'component_breakdown': _extract_component_breakdown(components, eeri_value),
            'asset_stress': _compute_asset_stress_from_alerts(),
            'top_drivers': _format_top_drivers(result.get('top_drivers', []), limit=5),
            'affected_assets': result.get('affected_assets', []),
            'is_realtime': True,
        },
    }


@router.get("/component-breakdown")
async def get_component_breakdown():
    """
    Get detailed EERI component breakdown.
    Shows how each component contributes to the final index value.
    """
    check_enabled()
    
    result = get_latest_eeri_public()
    
    if not result:
        return {
            'success': False,
            'message': 'No EERI data available',
            'data': None,
        }
    
    components = result.get('components', {})
    eeri_value = result.get('value', 0)
    
    return {
        'success': True,
        'data': _extract_component_breakdown(components, eeri_value),
    }


@router.get("/asset-stress")
async def get_asset_stress():
    """
    Get current asset stress levels across all energy asset classes.
    """
    check_enabled()
    
    result = get_latest_eeri_public()
    
    if not result:
        return {
            'success': False,
            'message': 'No EERI data available',
            'data': None,
        }
    
    components = result.get('components', {})
    
    return {
        'success': True,
        'date': result.get('date'),
        'data': _compute_asset_stress_from_alerts(),
    }


@router.get("/top-drivers")
async def get_top_drivers(limit: int = Query(5, ge=1, le=10)):
    """
    Get full top drivers with Pro-tier details.
    """
    check_enabled()
    
    result = get_latest_eeri_public()
    
    if not result:
        return {
            'success': False,
            'message': 'No EERI data available',
            'data': None,
        }
    
    return {
        'success': True,
        'date': result.get('date'),
        'data': _format_top_drivers(result.get('top_drivers', []), limit=limit),
    }


@router.get("/history")
async def get_eeri_pro_history(
    days: int = Query(30, ge=7, le=365, description="Number of days of history"),
    smoothing: str = Query("raw", description="Smoothing: raw, ma3, ma7"),
):
    """
    Get EERI history with optional smoothing for Pro charts.
    """
    check_enabled()
    
    end_date = date.today()
    start_date = end_date - timedelta(days=days)
    
    query = """
        SELECT 
            date, value, band, trend_1d, trend_7d, components, computed_at
        FROM reri_indices_daily
        WHERE index_id = %s
          AND date >= %s
          AND date <= %s
        ORDER BY date ASC
    """
    
    try:
        with get_cursor() as cursor:
            cursor.execute(query, (EERI_INDEX_ID, start_date, end_date))
            rows = cursor.fetchall()
        
        data = []
        values = []
        
        for row in rows:
            value = float(row['value']) if row['value'] else 0
            values.append(value)
            
            data.append({
                'date': row['date'].isoformat() if hasattr(row['date'], 'isoformat') else str(row['date']),
                'value': value,
                'band': row['band'],
                'trend_1d': row['trend_1d'],
                'trend_7d': row['trend_7d'],
            })
        
        if smoothing == 'ma3' and len(values) >= 3:
            for i in range(2, len(data)):
                data[i]['smoothed'] = round(sum(values[i-2:i+1]) / 3, 1)
        elif smoothing == 'ma7' and len(values) >= 7:
            for i in range(6, len(data)):
                data[i]['smoothed'] = round(sum(values[i-6:i+1]) / 7, 1)
        
        band_distribution = {'LOW': 0, 'MODERATE': 0, 'ELEVATED': 0, 'CRITICAL': 0}
        for d in data:
            band = d.get('band', 'LOW')
            if band in band_distribution:
                band_distribution[band] += 1
        
        total = len(data) if data else 1
        band_percentages = {k: round(v / total * 100, 1) for k, v in band_distribution.items()}
        
        avg_value = round(sum(values) / len(values), 1) if values else 0
        max_value = max(values) if values else 0
        min_value = min(values) if values else 0
        
        return {
            'success': True,
            'period': {
                'days': days,
                'start': start_date.isoformat(),
                'end': end_date.isoformat(),
            },
            'statistics': {
                'average': avg_value,
                'max': max_value,
                'min': min_value,
                'band_distribution': band_distribution,
                'band_percentages': band_percentages,
            },
            'data': data,
            'count': len(data),
        }
    except Exception as e:
        logger.error(f"Error fetching EERI Pro history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/regime-stats")
async def get_regime_statistics():
    """
    Get EERI regime statistics for historical intelligence.
    Shows how often each risk band occurs and recent regime transitions.
    """
    check_enabled()
    
    query = """
        SELECT 
            date, value, band, trend_7d
        FROM reri_indices_daily
        WHERE index_id = %s
        ORDER BY date DESC
        LIMIT 90
    """
    
    try:
        with get_cursor() as cursor:
            cursor.execute(query, (EERI_INDEX_ID,))
            rows = cursor.fetchall()
        
        if not rows:
            return {
                'success': False,
                'message': 'Insufficient data for regime statistics',
                'data': None,
            }
        
        band_counts = {'LOW': 0, 'MODERATE': 0, 'ELEVATED': 0, 'CRITICAL': 0}
        values = []
        transitions = []
        prev_band = None
        
        for row in reversed(rows):
            band = row['band']
            value = float(row['value']) if row['value'] else 0
            values.append(value)
            
            if band in band_counts:
                band_counts[band] += 1
            
            if prev_band and prev_band != band:
                transitions.append({
                    'date': row['date'].isoformat() if hasattr(row['date'], 'isoformat') else str(row['date']),
                    'from_band': prev_band,
                    'to_band': band,
                    'value': value,
                })
            prev_band = band
        
        total = len(rows)
        band_percentages = {k: round(v / total * 100, 1) for k, v in band_counts.items()}
        
        current = rows[0] if rows else None
        
        return {
            'success': True,
            'period_days': total,
            'current': {
                'value': float(current['value']) if current and current['value'] else 0,
                'band': current['band'] if current else 'LOW',
                'date': current['date'].isoformat() if current and hasattr(current['date'], 'isoformat') else None,
            },
            'statistics': {
                'band_distribution': band_counts,
                'band_percentages': band_percentages,
                'average': round(sum(values) / len(values), 1) if values else 0,
                'max': max(values) if values else 0,
                'min': min(values) if values else 0,
                'volatility': round(max(values) - min(values), 1) if values else 0,
            },
            'recent_transitions': transitions[-5:],
        }
    except Exception as e:
        logger.error(f"Error fetching regime statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/daily-summary")
async def get_daily_intelligence_summary():
    """
    Get the daily EERI intelligence summary.
    AI-generated brief tied to current index value.
    """
    check_enabled()
    
    result = get_latest_eeri_public()
    
    if not result:
        return {
            'success': False,
            'message': 'No EERI data available',
            'data': None,
        }
    
    components = result.get('components', {})
    eeri_value = result.get('value', 0)
    band = result.get('band', 'LOW')
    trend_7d = result.get('trend_7d', 0)
    
    drivers = result.get('top_drivers', [])
    driver_headlines = []
    for d in drivers[:3]:
        if isinstance(d, dict):
            driver_headlines.append(d.get('headline', d.get('title', '')))
        elif isinstance(d, str):
            driver_headlines.append(d)
    
    assets = result.get('affected_assets', [])
    
    if trend_7d > 5:
        trend_text = "Risk is accelerating"
        trend_icon = "↑"
    elif trend_7d < -5:
        trend_text = "Risk is declining"
        trend_icon = "↓"
    else:
        trend_text = "Risk remains stable"
        trend_icon = "→"
    
    drivers_text = " and ".join(driver_headlines[:2]) if driver_headlines else "multiple factors"
    assets_text = ", ".join(assets[:3]) if assets else "energy assets"
    
    interpretation = result.get('interpretation', '')
    
    if not interpretation:
        interpretation = f"EERI closed at {eeri_value} ({band}), driven by {drivers_text}. {assets_text.title()} remain the most exposed assets. {trend_text} compared to the 7-day baseline."
    
    return {
        'success': True,
        'data': {
            'date': result.get('date'),
            'value': eeri_value,
            'band': band,
            'trend_icon': trend_icon,
            'trend_text': trend_text,
            'interpretation': interpretation,
            'key_drivers': driver_headlines,
            'exposed_assets': assets[:5],
            'computed_at': result.get('computed_at'),
        },
    }


@router.get("/comparison/{date1}/{date2}")
async def compare_eeri_dates(date1: str, date2: str):
    """
    Compare EERI between two dates for delta analysis.
    """
    check_enabled()
    
    try:
        d1 = datetime.strptime(date1, "%Y-%m-%d").date()
        d2 = datetime.strptime(date2, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")
    
    result1 = get_eeri_by_date(d1)
    result2 = get_eeri_by_date(d2)
    
    if not result1 or not result2:
        return {
            'success': False,
            'message': 'Data not available for one or both dates',
            'data': None,
        }
    
    delta_value = result1.get('value', 0) - result2.get('value', 0)
    
    return {
        'success': True,
        'comparison': {
            'date1': {
                'date': date1,
                'value': result1.get('value', 0),
                'band': result1.get('band', 'LOW'),
            },
            'date2': {
                'date': date2,
                'value': result2.get('value', 0),
                'band': result2.get('band', 'LOW'),
            },
            'delta': {
                'value': round(delta_value, 1),
                'direction': 'up' if delta_value > 0 else 'down' if delta_value < 0 else 'unchanged',
                'percentage': round((delta_value / result2.get('value', 1)) * 100, 1) if result2.get('value', 0) > 0 else 0,
            },
        },
    }
