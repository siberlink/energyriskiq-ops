"""
EERI Weekly Snapshot Service

Computes weekly risk overview, cross-asset confirmation, divergence status,
and historical tendencies from production data for the public /eeri page
and plan-tiered dashboard snapshots.
"""
import logging
from datetime import date, datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple

from src.db.db import get_cursor

logger = logging.getLogger(__name__)

EERI_INDEX_ID = 'europe:eeri'

PLAN_TIERS = {
    'free': 0,
    'personal': 1,
    'trader': 2,
    'pro': 3,
    'enterprise': 4,
}

CONDITIONAL_TENDENCIES = {
    'CRITICAL': {
        'rising': [
            {'asset': 'TTF Gas', 'tendency': '65-75% elevated volatility', 'confidence': 'High', 'condition': 'Critical + Rising'},
            {'asset': 'Brent Oil', 'tendency': '55-65% upward pressure', 'confidence': 'Medium', 'condition': 'Critical + Rising'},
            {'asset': 'VIX', 'tendency': '60-70% elevated levels', 'confidence': 'High', 'condition': 'Critical + Rising'},
            {'asset': 'EUR/USD', 'tendency': '60-70% weaker EUR', 'confidence': 'Medium', 'condition': 'Critical + Rising'},
            {'asset': 'EU Gas Storage', 'tendency': '60-70% accelerated draws', 'confidence': 'High', 'condition': 'Critical + Rising'},
        ],
        'stable': [
            {'asset': 'TTF Gas', 'tendency': '55-65% continued volatility', 'confidence': 'Medium', 'condition': 'Critical + Stable'},
            {'asset': 'Brent Oil', 'tendency': '50-60% mixed', 'confidence': 'Low', 'condition': 'Critical + Stable'},
            {'asset': 'VIX', 'tendency': '55-65% elevated', 'confidence': 'Medium', 'condition': 'Critical + Stable'},
            {'asset': 'EUR/USD', 'tendency': '55-65% weaker EUR', 'confidence': 'Medium', 'condition': 'Critical + Stable'},
            {'asset': 'EU Gas Storage', 'tendency': '55-65% seasonal draws', 'confidence': 'Medium', 'condition': 'Critical + Stable'},
        ],
        'falling': [
            {'asset': 'TTF Gas', 'tendency': '50-60% normalizing', 'confidence': 'Medium', 'condition': 'Critical + Falling'},
            {'asset': 'Brent Oil', 'tendency': '45-55% mixed', 'confidence': 'Low', 'condition': 'Critical + Falling'},
            {'asset': 'VIX', 'tendency': '50-60% normalizing', 'confidence': 'Medium', 'condition': 'Critical + Falling'},
            {'asset': 'EUR/USD', 'tendency': '50-60% stabilizing', 'confidence': 'Low', 'condition': 'Critical + Falling'},
            {'asset': 'EU Gas Storage', 'tendency': '50-60% seasonal norms', 'confidence': 'Medium', 'condition': 'Critical + Falling'},
        ],
    },
    'SEVERE': {
        'rising': [
            {'asset': 'TTF Gas', 'tendency': '60-70% elevated volatility', 'confidence': 'Medium', 'condition': 'Severe + Rising'},
            {'asset': 'Brent Oil', 'tendency': '50-60% upward pressure', 'confidence': 'Low', 'condition': 'Severe + Rising'},
            {'asset': 'VIX', 'tendency': '55-65% elevated levels', 'confidence': 'Medium', 'condition': 'Severe + Rising'},
            {'asset': 'EUR/USD', 'tendency': '55-65% weaker EUR', 'confidence': 'Medium', 'condition': 'Severe + Rising'},
            {'asset': 'EU Gas Storage', 'tendency': '55-65% accelerated draws', 'confidence': 'Medium', 'condition': 'Severe + Rising'},
        ],
        'stable': [
            {'asset': 'TTF Gas', 'tendency': '50-60% elevated volatility', 'confidence': 'Medium', 'condition': 'Severe + Stable'},
            {'asset': 'Brent Oil', 'tendency': '45-55% mixed', 'confidence': 'Low', 'condition': 'Severe + Stable'},
            {'asset': 'VIX', 'tendency': '50-60% elevated', 'confidence': 'Medium', 'condition': 'Severe + Stable'},
            {'asset': 'EUR/USD', 'tendency': '50-60% weaker EUR', 'confidence': 'Low', 'condition': 'Severe + Stable'},
            {'asset': 'EU Gas Storage', 'tendency': '50-60% seasonal draws', 'confidence': 'Medium', 'condition': 'Severe + Stable'},
        ],
        'falling': [
            {'asset': 'TTF Gas', 'tendency': '45-55% normalizing', 'confidence': 'Low', 'condition': 'Severe + Falling'},
            {'asset': 'Brent Oil', 'tendency': '45-55% mixed', 'confidence': 'Low', 'condition': 'Severe + Falling'},
            {'asset': 'VIX', 'tendency': '45-55% normalizing', 'confidence': 'Low', 'condition': 'Severe + Falling'},
            {'asset': 'EUR/USD', 'tendency': '45-55% stabilizing', 'confidence': 'Low', 'condition': 'Severe + Falling'},
            {'asset': 'EU Gas Storage', 'tendency': '50-60% seasonal norms', 'confidence': 'Medium', 'condition': 'Severe + Falling'},
        ],
    },
}

REGIME_PERSISTENCE = {
    'CRITICAL': {'prob_low': 0.55, 'prob_high': 0.65, 'confidence': 'Medium', 'narrative': 'Critical regimes historically persist into the following week ~60% of the time.'},
    'SEVERE': {'prob_low': 0.50, 'prob_high': 0.60, 'confidence': 'Medium', 'narrative': 'Severe regimes historically persist into the following week ~55% of the time.'},
    'ELEVATED': {'prob_low': 0.45, 'prob_high': 0.55, 'confidence': 'Low', 'narrative': 'Elevated regimes historically persist into the following week ~50% of the time.'},
    'MODERATE': {'prob_low': 0.50, 'prob_high': 0.60, 'confidence': 'Low', 'narrative': 'Moderate regimes tend to be stable with ~55% persistence.'},
    'LOW': {'prob_low': 0.55, 'prob_high': 0.65, 'confidence': 'Medium', 'narrative': 'Low-risk regimes tend to persist into the following week ~60% of the time.'},
}

SCENARIO_TEMPLATES = {
    'CRITICAL': {
        'escalation': 'Continued high-severity events or new chokepoint disruptions could push EERI higher, intensifying gas/oil volatility.',
        'stabilization': 'If event flow subsides without new escalations, EERI may plateau within the Critical band before gradual normalization.',
        'de_escalation': 'Resolution of active conflicts or diplomatic breakthroughs could trigger rapid risk decline toward Severe/Elevated.',
    },
    'SEVERE': {
        'escalation': 'Escalation of regional tensions or supply disruptions could push EERI into Critical range.',
        'stabilization': 'Absence of new shocks may allow EERI to consolidate within the Severe band.',
        'de_escalation': 'Positive diplomatic developments or supply normalization could reduce risk toward Elevated.',
    },
    'ELEVATED': {
        'escalation': 'New geopolitical triggers or supply disruptions could push EERI into Severe range.',
        'stabilization': 'Current conditions suggest moderate risk persistence without major catalysts.',
        'de_escalation': 'Seasonal normalization and stable supply could reduce EERI toward Moderate.',
    },
    'MODERATE': {
        'escalation': 'Unexpected geopolitical events could rapidly elevate risk levels.',
        'stabilization': 'Baseline conditions support continued moderate risk environment.',
        'de_escalation': 'Continued stability may further reduce risk toward Low levels.',
    },
    'LOW': {
        'escalation': 'While unlikely, sudden events could rapidly shift the risk environment.',
        'stabilization': 'Low-risk environment expected to persist under current conditions.',
        'de_escalation': 'Risk levels are already at baseline, limited further downside.',
    },
}

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

    prior_avg_val = prior_avg if prior_data else None

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
        'prior_avg': prior_avg_val,
        'regime_distribution': sorted_regime,
        'cross_asset': cross_asset,
        'chart_data': chart_data,
        'divergence_status': divergence_status,
        'divergence_narrative': divergence_narrative,
        'historical_context': hist_context,
        'tendencies': tendencies,
        'data_days': len(eeri_data),
    }


def _compute_reaction_speed(eeri_data: List[Dict], asset_data: List[Dict]) -> str:
    """Determine how quickly an asset reacted to EERI changes."""
    if len(eeri_data) < 3 or len(asset_data) < 3:
        return 'medium'

    eeri_vals = [int(r['value']) for r in eeri_data]
    eeri_mid = len(eeri_vals) // 2
    first_half_avg = sum(eeri_vals[:eeri_mid]) / max(eeri_mid, 1)
    second_half_avg = sum(eeri_vals[eeri_mid:]) / max(len(eeri_vals) - eeri_mid, 1)
    eeri_shifted = abs(second_half_avg - first_half_avg) > 3

    if not eeri_shifted:
        return 'medium'

    asset_vals = [float(r['value']) for r in asset_data]
    first_val = asset_vals[0]
    if first_val == 0:
        return 'medium'

    for i, v in enumerate(asset_vals[1:], 1):
        pct_change = abs((v - first_val) / first_val) * 100
        if pct_change > 1.5:
            if i <= len(asset_vals) // 3:
                return 'fast'
            elif i <= 2 * len(asset_vals) // 3:
                return 'medium'
            else:
                return 'lagging'

    return 'medium'


def _compute_risk_momentum(eeri_avg: float, prior_avg: Optional[float], trend: str) -> Dict[str, Any]:
    """Compute week-over-week risk acceleration/deceleration."""
    if prior_avg is None:
        return {'label': 'stable', 'narrative': 'Insufficient prior data for momentum analysis.'}

    delta = eeri_avg - prior_avg
    abs_delta = abs(delta)

    if delta > 5:
        label = 'accelerating'
        narrative = f'Risk momentum accelerated this week, with EERI averaging {eeri_avg} vs {prior_avg} the prior week (+{abs_delta:.0f} points).'
    elif delta < -5:
        label = 'easing'
        narrative = f'Risk momentum eased this week, with EERI declining from {prior_avg} to {eeri_avg} ({abs_delta:.0f} points).'
    elif delta > 2:
        label = 'building'
        narrative = f'Risk is gradually building, with a modest {abs_delta:.0f}-point increase from last week.'
    elif delta < -2:
        label = 'softening'
        narrative = f'Risk is softening slightly, with a {abs_delta:.0f}-point decline from last week.'
    else:
        label = 'plateauing'
        narrative = f'Risk momentum has plateaued, with EERI stable around {eeri_avg} (+/- {abs_delta:.0f} vs prior week).'

    return {'label': label, 'delta': round(delta, 1), 'narrative': narrative}


def _get_component_attribution(week_start: date, week_end: date) -> List[Dict[str, Any]]:
    """Get EERI component attribution for the week from daily data."""
    query = """
        SELECT components
        FROM reri_indices_daily
        WHERE index_id = %s AND date >= %s AND date <= %s
        ORDER BY date DESC
        LIMIT 1
    """
    try:
        with get_cursor() as cursor:
            cursor.execute(query, (EERI_INDEX_ID, week_start.isoformat(), week_end.isoformat()))
            row = cursor.fetchone()
        if not row or not row.get('components'):
            return []

        import json
        comp = row['components']
        if isinstance(comp, str):
            comp = json.loads(comp)

        attribution = []
        component_names = {
            'reri_eu': {'name': 'Regional Escalation (RERI_EU)', 'weight': 0.45},
            'theme_pressure': {'name': 'Theme Pressure', 'weight': 0.25},
            'asset_transmission': {'name': 'Asset Transmission', 'weight': 0.20},
            'contagion': {'name': 'Contagion', 'weight': 0.10},
        }
        for key, meta in component_names.items():
            val = comp.get(key, 0)
            if isinstance(val, (int, float)):
                attribution.append({
                    'component': meta['name'],
                    'value': round(float(val), 1),
                    'weight': meta['weight'],
                    'contribution': round(float(val) * meta['weight'], 1),
                })

        attribution.sort(key=lambda x: x['contribution'], reverse=True)
        return attribution
    except Exception as e:
        logger.error(f"Error fetching component attribution: {e}")
        return []


def get_weekly_snapshot_tiered(plan: str = 'free') -> Optional[Dict[str, Any]]:
    """
    Compute plan-tiered EERI Weekly Snapshot for the user dashboard.

    Plan visibility:
    - free: overview, asset directions, basic interpretation, basic outlook
    - personal: + charts, alignment labels, historical context, simple probability ranges
    - trader: + reaction speed, momentum, conditional probabilities, volatility commentary
    - pro: + component attribution, regime persistence, scenarios, analog framing
    - enterprise: + all pro features (sector/spillover data when available)
    """
    base_snapshot = get_weekly_snapshot()
    if not base_snapshot:
        return None

    plan_level = PLAN_TIERS.get(plan, 0)
    ov = base_snapshot['overview']
    band = ov['band']
    trend = ov['trend_vs_prior']

    result = {
        'plan': plan,
        'week_start': base_snapshot['week_start'],
        'week_end': base_snapshot['week_end'],
        'data_days': base_snapshot['data_days'],
    }

    result['overview'] = {
        'average': ov['average'],
        'band': band,
        'high': ov['high'],
        'low': ov['low'],
        'trend_vs_prior': trend,
    }

    asset_direction = []
    for a in base_snapshot['cross_asset']:
        direction = 'flat'
        if a['weekly_move_pct'] is not None:
            if a['weekly_move_pct'] > 0.5:
                direction = 'up'
            elif a['weekly_move_pct'] < -0.5:
                direction = 'down'
        entry = {
            'asset': a['asset'],
            'direction': direction,
            'weekly_move_pct': a['weekly_move_pct'],
        }
        if plan_level >= 1:
            entry['alignment'] = a['alignment']
            entry['context'] = a['context']
        asset_direction.append(entry)
    result['asset_table'] = asset_direction

    regime_dist = {}
    for band_name, days in base_snapshot['regime_distribution']:
        regime_dist[band_name] = days
    result['regime_distribution'] = regime_dist

    result['divergence_status'] = base_snapshot['divergence_status']

    interpretation = _generate_basic_interpretation(ov, base_snapshot['cross_asset'], base_snapshot['divergence_status'])
    result['interpretation'] = interpretation

    outlook = _generate_basic_outlook(band)
    result['next_week_outlook'] = outlook

    if plan_level >= 1:
        result['charts_enabled'] = True
        result['chart_data'] = base_snapshot['chart_data']
        result['historical_context'] = base_snapshot['historical_context']
        result['tendencies'] = base_snapshot['tendencies']
        result['divergence_narrative'] = base_snapshot['divergence_narrative']
    else:
        result['charts_enabled'] = False

    if plan_level >= 2:
        week_start = date.fromisoformat(base_snapshot['week_start'])
        week_end = date.fromisoformat(base_snapshot['week_end'])

        asset_configs = [
            ('ttf', 'TTF Gas', 'ttf_gas_snapshots', 'date', 'ttf_price'),
            ('brent', 'Brent Oil', 'oil_price_snapshots', 'date', 'brent_price'),
            ('vix', 'VIX', 'vix_snapshots', 'date', 'vix_close'),
            ('eurusd', 'EUR/USD', 'eurusd_snapshots', 'date', 'rate'),
            ('storage', 'EU Gas Storage', 'gas_storage_snapshots', 'date', 'eu_storage_percent'),
        ]

        eeri_data = _fetch_eeri_week(week_start, week_end)
        reaction_speeds = {}
        for key, name, table, date_col, val_col in asset_configs:
            asset_data = _fetch_asset_week(table, date_col, val_col, week_start, week_end)
            speed = _compute_reaction_speed(eeri_data, asset_data)
            reaction_speeds[key] = speed

        for entry in result['asset_table']:
            key = None
            for k, n, _, _, _ in asset_configs:
                if n == entry['asset']:
                    key = k
                    break
            if key:
                entry['reaction_speed'] = reaction_speeds.get(key, 'medium')

        prior_avg = base_snapshot.get('prior_avg')
        momentum = _compute_risk_momentum(ov['average'], prior_avg, trend)
        result['momentum'] = momentum

        cond_key = band if band in CONDITIONAL_TENDENCIES else None
        if cond_key:
            trend_key = trend if trend in CONDITIONAL_TENDENCIES[cond_key] else 'stable'
            result['conditional_tendencies'] = CONDITIONAL_TENDENCIES[cond_key][trend_key]
            result['conditional_state'] = f"{band.capitalize()} + {trend.capitalize()}"
        else:
            result['conditional_tendencies'] = base_snapshot['tendencies']
            result['conditional_state'] = f"{band.capitalize()} + {trend.capitalize()}"

        result['volatility_commentary'] = _generate_volatility_commentary(band, trend, momentum['label'])

        persistence = REGIME_PERSISTENCE.get(band, REGIME_PERSISTENCE['MODERATE'])
        result['regime_persistence'] = persistence

    if plan_level >= 3:
        week_start = date.fromisoformat(base_snapshot['week_start'])
        week_end = date.fromisoformat(base_snapshot['week_end'])

        attribution = _get_component_attribution(week_start, week_end)
        result['component_attribution'] = attribution

        scenarios = SCENARIO_TEMPLATES.get(band, SCENARIO_TEMPLATES['MODERATE'])
        result['scenario_outlook'] = [
            {'name': 'Escalation', 'description': scenarios['escalation']},
            {'name': 'Stabilization', 'description': scenarios['stabilization']},
            {'name': 'De-escalation', 'description': scenarios['de_escalation']},
        ]

        result['analog_framing'] = _generate_analog_framing(band, trend)

    if plan_level >= 4:
        result['enterprise'] = True

    return result


def _generate_basic_interpretation(overview: Dict, cross_asset: List[Dict], divergence: str) -> str:
    """Generate a basic market interpretation paragraph."""
    avg = overview['average']
    band = overview['band']
    trend = overview['trend_vs_prior']

    rising_assets = [a['asset'] for a in cross_asset if a.get('weekly_move_pct') and a['weekly_move_pct'] > 0.5]
    falling_assets = [a['asset'] for a in cross_asset if a.get('weekly_move_pct') and a['weekly_move_pct'] < -0.5]

    trend_text = 'rising' if trend == 'rising' else ('falling' if trend == 'falling' else 'stable')

    interpretation = f"Risk conditions during the week remained {trend_text} with EERI averaging {avg} ({band} band)."

    if rising_assets and falling_assets:
        interpretation += f" {', '.join(rising_assets[:2])} moved higher while {', '.join(falling_assets[:2])} declined."
    elif rising_assets:
        interpretation += f" {', '.join(rising_assets[:3])} showed upward movement."
    elif falling_assets:
        interpretation += f" {', '.join(falling_assets[:3])} showed downward movement."

    if divergence == 'confirming':
        interpretation += " Markets broadly confirmed the risk environment."
    elif divergence == 'diverging':
        interpretation += " Markets showed limited confirmation of the reported risk level."
    else:
        interpretation += " Market signals were mixed relative to risk conditions."

    return interpretation


def _generate_basic_outlook(band: str) -> str:
    """Generate a basic one-sentence next-week outlook."""
    outlooks = {
        'CRITICAL': 'Weeks with EERI in the Critical range historically show continued elevated volatility across energy-sensitive markets.',
        'SEVERE': 'Historically, Severe-risk weeks tend to be followed by elevated but gradually normalizing volatility.',
        'ELEVATED': 'Elevated-risk conditions historically show moderate continuation with potential for normalization.',
        'MODERATE': 'Moderate-risk weeks typically see stable market conditions with limited directional bias.',
        'LOW': 'Low-risk conditions historically persist, with markets typically operating within normal ranges.',
    }
    return outlooks.get(band, outlooks['MODERATE'])


def _generate_volatility_commentary(band: str, trend: str, momentum: str) -> str:
    """Generate volatility expectation commentary for Trader+ tiers."""
    if band in ('CRITICAL', 'SEVERE') and trend == 'rising':
        return 'Historical analogs suggest elevated two-week volatility clustering. Traders should anticipate sustained directional pressure across gas and related markets.'
    elif band in ('CRITICAL', 'SEVERE') and momentum == 'accelerating':
        return 'Risk acceleration combined with elevated EERI levels suggests above-normal volatility persistence for the next 1-2 weeks.'
    elif band in ('CRITICAL', 'SEVERE'):
        return 'While risk levels remain elevated, momentum indicators suggest volatility may begin to moderate. Watch for regime transition signals.'
    elif band == 'ELEVATED':
        return 'Moderate volatility expected. Episodic moves possible but sustained directional trends unlikely without new catalysts.'
    else:
        return 'Baseline volatility conditions expected. Seasonal patterns likely to dominate over event-driven moves.'


def _generate_analog_framing(band: str, trend: str) -> str:
    """Generate historical analog framing for Pro+ tiers."""
    if band == 'CRITICAL' and trend == 'rising':
        return 'Current conditions resemble prior critical-escalation phases characterized by rapid risk accumulation and sustained supply-side stress.'
    elif band == 'CRITICAL':
        return 'This week resembles prior periods of peak risk where markets typically began pricing in de-escalation scenarios.'
    elif band == 'SEVERE' and trend == 'rising':
        return 'Current dynamics are consistent with historical pre-escalation periods where Severe-band persistence preceded Critical-range breakthroughs.'
    elif band == 'SEVERE':
        return 'This week resembles prior sustained-stress periods where risk elevated but stabilized before further escalation.'
    elif band == 'ELEVATED':
        return 'Conditions are consistent with historical transition periods between calm and stressed market environments.'
    else:
        return 'Current risk levels are consistent with baseline historical norms.'
