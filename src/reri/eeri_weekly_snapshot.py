"""
EERI Weekly Snapshot Service

Computes weekly risk overview, cross-asset confirmation, divergence status,
and historical tendencies from production data for the public /eeri page.
"""
import logging
from datetime import date, datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple

from src.db.db import get_cursor

logger = logging.getLogger(__name__)

EERI_INDEX_ID = 'europe:eeri'

DAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

BAND_ORDER = ['LOW', 'MODERATE', 'ELEVATED', 'SEVERE', 'CRITICAL']

BAND_COLORS = {
    'LOW': '#22c55e',
    'MODERATE': '#eab308',
    'ELEVATED': '#f97316',
    'SEVERE': '#dc2626',
    'CRITICAL': '#ef4444',
}

HISTORICAL_CONTEXT = {
    'CRITICAL': [
        'Significant gas price volatility often follows',
        'Freight and logistics disruption probability elevated',
        'European FX markets typically show stress',
        'Cross-market risk sentiment tends to remain elevated',
    ],
    'SEVERE': [
        'Gas markets may show sustained directional pressure',
        'Oil markets often display heightened sensitivity',
        'Risk sentiment tends toward gradual normalization',
        'Supply-chain indicators warrant close monitoring',
    ],
    'ELEVATED': [
        'Gas markets may show directional uncertainty',
        'Oil markets often display mixed signals',
        'Risk sentiment tends toward gradual normalization',
        'Supply-chain indicators warrant close monitoring',
    ],
    'MODERATE': [
        'Markets typically operate within normal ranges',
        'Gas price volatility remains subdued',
        'Risk sentiment broadly stable',
        'Seasonal patterns dominate over geopolitical signals',
    ],
    'LOW': [
        'Markets typically operate within normal ranges',
        'Gas price volatility remains subdued',
        'Risk sentiment broadly stable',
        'Seasonal patterns dominate over geopolitical signals',
    ],
}

TENDENCIES = {
    'CRITICAL': [
        {'asset': 'TTF Gas', 'tendency': '60–70% probability of continued volatility', 'confidence': 'Medium'},
        {'asset': 'Brent Oil', 'tendency': 'Mixed directional bias', 'confidence': 'Low'},
        {'asset': 'VIX', 'tendency': '55–65% probability of elevated levels', 'confidence': 'Medium'},
        {'asset': 'EUR/USD', 'tendency': '55–65% probability of weaker EUR', 'confidence': 'Medium'},
        {'asset': 'EU Gas Storage', 'tendency': '55–65% probability of accelerated draws', 'confidence': 'Medium'},
    ],
    'SEVERE': [
        {'asset': 'TTF Gas', 'tendency': '55–65% probability of elevated volatility', 'confidence': 'Medium'},
        {'asset': 'Brent Oil', 'tendency': '45–55% mixed directional bias', 'confidence': 'Low'},
        {'asset': 'VIX', 'tendency': '50–60% probability of elevated levels', 'confidence': 'Medium'},
        {'asset': 'EUR/USD', 'tendency': '50–60% probability of weaker EUR', 'confidence': 'Low'},
        {'asset': 'EU Gas Storage', 'tendency': '50–60% probability of seasonal draws', 'confidence': 'Medium'},
    ],
    'ELEVATED': [
        {'asset': 'TTF Gas', 'tendency': '50–60% probability of moderate volatility', 'confidence': 'Medium'},
        {'asset': 'Brent Oil', 'tendency': '45–55% mixed directional bias', 'confidence': 'Low'},
        {'asset': 'VIX', 'tendency': '45–55% normalizing tendency', 'confidence': 'Low'},
        {'asset': 'EUR/USD', 'tendency': '50–55% stable', 'confidence': 'Low'},
        {'asset': 'EU Gas Storage', 'tendency': '50–60% seasonal norms', 'confidence': 'Medium'},
    ],
    'MODERATE': [
        {'asset': 'TTF Gas', 'tendency': '40–50% stable', 'confidence': 'Low'},
        {'asset': 'Brent Oil', 'tendency': '45–55% stable', 'confidence': 'Low'},
        {'asset': 'VIX', 'tendency': '40–50% stable', 'confidence': 'Low'},
        {'asset': 'EUR/USD', 'tendency': '45–55% stable', 'confidence': 'Low'},
        {'asset': 'EU Gas Storage', 'tendency': '50–60% seasonal norms', 'confidence': 'Medium'},
    ],
    'LOW': [
        {'asset': 'TTF Gas', 'tendency': '40–50% stable', 'confidence': 'Low'},
        {'asset': 'Brent Oil', 'tendency': '45–55% stable', 'confidence': 'Low'},
        {'asset': 'VIX', 'tendency': '40–50% stable', 'confidence': 'Low'},
        {'asset': 'EUR/USD', 'tendency': '45–55% stable', 'confidence': 'Low'},
        {'asset': 'EU Gas Storage', 'tendency': '50–60% seasonal norms', 'confidence': 'Medium'},
    ],
}


def _get_last_complete_week() -> Tuple[date, date]:
    """Return (monday, sunday) of the most recently completed ISO week."""
    today = date.today()
    days_since_monday = today.weekday()
    last_monday = today - timedelta(days=days_since_monday + 7)
    last_sunday = last_monday + timedelta(days=6)
    return last_monday, last_sunday


def _get_current_partial_week() -> Tuple[date, date]:
    """Return (monday, today) if we're mid-week, for fallback."""
    today = date.today()
    days_since_monday = today.weekday()
    this_monday = today - timedelta(days=days_since_monday)
    return this_monday, today


def _fetch_eeri_week(start: date, end: date) -> List[Dict[str, Any]]:
    """Fetch EERI daily values for a date range."""
    query = """
        SELECT date, value, band, trend_7d
        FROM reri_indices_daily
        WHERE index_id = %s AND date >= %s AND date <= %s
        ORDER BY date ASC
    """
    try:
        with get_cursor() as cursor:
            cursor.execute(query, (EERI_INDEX_ID, start.isoformat(), end.isoformat()))
            rows = cursor.fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"Error fetching EERI week data: {e}")
        return []


def _fetch_asset_week(table: str, date_col: str, value_col: str, start: date, end: date) -> List[Dict[str, Any]]:
    """Fetch asset daily values for a date range."""
    query = f"""
        SELECT {date_col} as date, {value_col} as value
        FROM {table}
        WHERE {date_col} >= %s AND {date_col} <= %s
        ORDER BY {date_col} ASC
    """
    try:
        with get_cursor() as cursor:
            cursor.execute(query, (start.isoformat(), end.isoformat()))
            rows = cursor.fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"Error fetching {table} week data: {e}")
        return []


def _compute_weekly_move_pct(data: List[Dict[str, Any]]) -> Optional[float]:
    """Compute % change from first to last value in the week."""
    if len(data) < 2:
        return None
    first_val = float(data[0]['value'])
    last_val = float(data[-1]['value'])
    if first_val == 0:
        return None
    return round(((last_val - first_val) / first_val) * 100, 2)


def _determine_alignment(asset_key: str, move_pct: Optional[float], eeri_avg: float, eeri_direction: str) -> str:
    """Determine risk alignment label for an asset.
    
    Uses both EERI average level (>=50 = elevated) and EERI direction
    (rising/falling/stable) to determine whether asset movement confirms risk.
    """
    if move_pct is None:
        return 'neutral'

    threshold = 1.5
    eeri_elevated = eeri_avg >= 50 or eeri_direction == 'rising'

    if asset_key == 'eurusd':
        if move_pct < -threshold:
            return 'confirming' if eeri_elevated else 'neutral'
        elif move_pct > threshold:
            return 'diverging' if eeri_elevated else 'neutral'
        return 'neutral'
    elif asset_key == 'storage':
        if move_pct < -threshold:
            return 'confirming' if eeri_elevated else 'neutral'
        elif move_pct > threshold:
            return 'diverging' if eeri_elevated else 'neutral'
        return 'neutral'
    else:
        if move_pct > threshold:
            return 'confirming' if eeri_elevated else 'neutral'
        elif move_pct < -threshold:
            return 'diverging' if eeri_elevated else 'neutral'
        return 'neutral'


ASSET_CONTEXT_TEMPLATES = {
    'ttf': {
        'confirming': 'Gas markets strengthened alongside elevated risk, reflecting supply sensitivity.',
        'neutral': 'Gas prices showed limited reaction to risk conditions.',
        'diverging': 'Gas markets moved against risk direction, suggesting isolated supply dynamics.',
    },
    'brent': {
        'confirming': 'Oil markets reacted to energy stress with upward price pressure.',
        'neutral': 'Oil moved modestly, suggesting mixed global supply-demand interpretation.',
        'diverging': 'Oil markets showed resilience despite elevated European risk.',
    },
    'vix': {
        'confirming': 'Broader risk sentiment reacted to energy stress.',
        'neutral': 'Volatility markets showed limited reaction to energy-specific risk.',
        'diverging': 'Volatility markets remained calm despite elevated energy risk signals.',
    },
    'eurusd': {
        'confirming': 'Currency markets reflect European risk premium with weaker EUR.',
        'neutral': 'EUR/USD remained stable despite energy market stress.',
        'diverging': 'EUR strengthened despite elevated European energy risk.',
    },
    'storage': {
        'confirming': 'Accelerated withdrawal validates supply concern.',
        'neutral': 'Storage levels followed seasonal norms.',
        'diverging': 'Storage levels held steady despite elevated risk signals.',
    },
}


def _get_divergence_status(cross_asset: List[Dict[str, Any]]) -> Tuple[str, str]:
    """Determine overall divergence status and narrative from cross-asset data."""
    conf_assets = [a['asset'] for a in cross_asset if a['alignment'] == 'confirming']
    div_assets = [a['asset'] for a in cross_asset if a['alignment'] == 'diverging']
    confirming_count = len(conf_assets)

    if confirming_count >= 4:
        status = 'confirming'
        narrative = f"Markets broadly validated elevated risk conditions, with {', '.join(conf_assets)} confirming the risk environment."
    elif confirming_count >= 2:
        status = 'mixed'
        parts = []
        if conf_assets:
            parts.append(f"{', '.join(conf_assets)} confirmed elevated risk")
        if div_assets:
            parts.append(f"while {', '.join(div_assets)} showed partial divergence")
        narrative = 'Markets Mixed \u2014 ' + ', '.join(parts) + '.'
    else:
        status = 'diverging'
        narrative = 'Markets showed limited confirmation of elevated risk, suggesting potential underpricing of geopolitical stress.'

    return status, narrative


def get_weekly_snapshot() -> Optional[Dict[str, Any]]:
    """
    Compute the full EERI Weekly Snapshot for the public /eeri page.
    Returns None if insufficient data.
    """
    week_start, week_end = _get_last_complete_week()

    eeri_data = _fetch_eeri_week(week_start, week_end)

    if len(eeri_data) < 3:
        week_start, week_end = _get_current_partial_week()
        eeri_data = _fetch_eeri_week(week_start, week_end)
        if len(eeri_data) < 3:
            logger.info("Insufficient EERI data for weekly snapshot")
            return None

    eeri_values = [int(r['value']) for r in eeri_data]
    eeri_bands = [r['band'] for r in eeri_data]
    eeri_avg = round(sum(eeri_values) / len(eeri_values))

    high_val = max(eeri_values)
    low_val = min(eeri_values)
    high_idx = eeri_values.index(high_val)
    low_idx = eeri_values.index(low_val)

    high_date = eeri_data[high_idx]['date']
    low_date = eeri_data[low_idx]['date']

    if hasattr(high_date, 'weekday'):
        high_day = DAY_NAMES[high_date.weekday()]
        low_day = DAY_NAMES[low_date.weekday()]
    else:
        high_day = ''
        low_day = ''

    def _get_band(val):
        if val <= 20: return 'LOW'
        if val <= 40: return 'MODERATE'
        if val <= 60: return 'ELEVATED'
        if val <= 80: return 'SEVERE'
        return 'CRITICAL'

    avg_band = _get_band(eeri_avg)

    prior_start = week_start - timedelta(days=7)
    prior_end = week_start - timedelta(days=1)
    prior_data = _fetch_eeri_week(prior_start, prior_end)
    if prior_data:
        prior_avg = round(sum(int(r['value']) for r in prior_data) / len(prior_data))
        diff = eeri_avg - prior_avg
        if diff > 3:
            trend_vs_prior = 'rising'
        elif diff < -3:
            trend_vs_prior = 'falling'
        else:
            trend_vs_prior = 'stable'
    else:
        trend_vs_prior = 'stable'

    regime_dist = {}
    for b in eeri_bands:
        regime_dist[b] = regime_dist.get(b, 0) + 1

    sorted_regime = sorted(regime_dist.items(), key=lambda x: BAND_ORDER.index(x[0]) if x[0] in BAND_ORDER else 0, reverse=True)

    asset_configs = [
        ('ttf', 'TTF Gas', 'ttf_gas_snapshots', 'date', 'ttf_price'),
        ('brent', 'Brent Oil', 'oil_price_snapshots', 'date', 'brent_price'),
        ('vix', 'VIX', 'vix_snapshots', 'date', 'vix_close'),
        ('eurusd', 'EUR/USD', 'eurusd_snapshots', 'date', 'rate'),
        ('storage', 'EU Gas Storage', 'gas_storage_snapshots', 'date', 'eu_storage_percent'),
    ]

    cross_asset = []
    chart_data = {}

    for key, name, table, date_col, val_col in asset_configs:
        asset_data = _fetch_asset_week(table, date_col, val_col, week_start, week_end)
        move_pct = _compute_weekly_move_pct(asset_data)
        alignment = _determine_alignment(key, move_pct, eeri_avg, trend_vs_prior)
        context = ASSET_CONTEXT_TEMPLATES.get(key, {}).get(alignment, '')

        cross_asset.append({
            'asset': name,
            'key': key,
            'weekly_move_pct': move_pct,
            'alignment': alignment,
            'context': context,
        })

        asset_chart_points = []
        for row in asset_data:
            d = row['date']
            if hasattr(d, 'isoformat'):
                d = d.isoformat()
            asset_chart_points.append({'date': d, 'value': float(row['value'])})

        chart_data[key] = asset_chart_points

    eeri_chart_points = []
    for row in eeri_data:
        d = row['date']
        if hasattr(d, 'isoformat'):
            d = d.isoformat()
        eeri_chart_points.append({'date': d, 'value': int(row['value'])})
    chart_data['eeri'] = eeri_chart_points

    divergence_status, divergence_narrative = _get_divergence_status(cross_asset)

    dominant_band = max(regime_dist, key=regime_dist.get) if regime_dist else avg_band
    hist_context = HISTORICAL_CONTEXT.get(dominant_band, HISTORICAL_CONTEXT['MODERATE'])
    tendencies = TENDENCIES.get(dominant_band, TENDENCIES['MODERATE'])

    ws = week_start.isoformat() if hasattr(week_start, 'isoformat') else str(week_start)
    we = week_end.isoformat() if hasattr(week_end, 'isoformat') else str(week_end)

    return {
        'week_start': ws,
        'week_end': we,
        'overview': {
            'average': eeri_avg,
            'band': avg_band,
            'high': {'value': high_val, 'day': high_day},
            'low': {'value': low_val, 'day': low_day},
            'trend_vs_prior': trend_vs_prior,
        },
        'regime_distribution': sorted_regime,
        'cross_asset': cross_asset,
        'chart_data': chart_data,
        'divergence_status': divergence_status,
        'divergence_narrative': divergence_narrative,
        'historical_context': hist_context,
        'tendencies': tendencies,
        'data_days': len(eeri_data),
    }
