"""
GERI Trader Intelligence Service

Computes tactical intelligence modules for Trader-tier GERI dashboard:
1. Lead/Lag Intelligence — cross-correlation timing between GERI and assets
2. Divergence Indicator — per-asset directional divergence vs GERI
3. Confirmation Score — cross-asset confirmation (0-100)
4. Storage Seasonal Context — EU gas storage vs seasonal average
5. Asset Reaction Summary — interpretive text about asset-risk dynamics
6. Regime Transition Indicator — transition direction from recent band changes
7. Alert Preview — 3 most recent alerts as upgrade teaser
"""
import logging
import math
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, Any, List, Optional, Tuple

from src.db.db import get_cursor, execute_production_query


def _to_float(v):
    if v is None:
        return None
    if isinstance(v, Decimal):
        return float(v)
    return float(v)

logger = logging.getLogger(__name__)


def compute_lead_lag(geri_series: List[Dict], asset_series: List[Dict], max_lag: int = 7) -> Dict[str, Any]:
    geri_by_date = {r['date']: _to_float(r['value']) for r in geri_series if r.get('value') is not None}
    asset_by_date = {r['date']: _to_float(r['value']) for r in asset_series if r.get('value') is not None}

    common_dates = sorted(set(geri_by_date.keys()) & set(asset_by_date.keys()))
    if len(common_dates) < 10:
        return {'lag': None, 'direction': None, 'sample_size': len(common_dates)}

    geri_vals = [geri_by_date[d] for d in common_dates]
    asset_vals = [asset_by_date[d] for d in common_dates]

    geri_changes = [geri_vals[i] - geri_vals[i-1] for i in range(1, len(geri_vals))]
    asset_changes = [asset_vals[i] - asset_vals[i-1] for i in range(1, len(asset_vals))]

    n = len(geri_changes)
    if n < 5:
        return {'lag': None, 'direction': None, 'sample_size': n}

    best_corr = -2
    best_lag = 0

    for lag in range(-max_lag, max_lag + 1):
        pairs = []
        for i in range(n):
            j = i + lag
            if 0 <= j < len(asset_changes):
                pairs.append((geri_changes[i], asset_changes[j]))
        if len(pairs) < 5:
            continue

        gx = [p[0] for p in pairs]
        ax = [p[1] for p in pairs]
        mg = sum(gx) / len(gx)
        ma = sum(ax) / len(ax)

        num = sum((g - mg) * (a - ma) for g, a in zip(gx, ax))
        dg = math.sqrt(sum((g - mg)**2 for g in gx)) or 1e-9
        da = math.sqrt(sum((a - ma)**2 for a in ax)) or 1e-9
        corr = num / (dg * da)

        if abs(corr) > abs(best_corr):
            best_corr = corr
            best_lag = lag

    if best_lag > 0:
        direction = 'Risk leads asset'
        lag_text = f"Risk leads by {best_lag} day{'s' if best_lag > 1 else ''}"
    elif best_lag < 0:
        direction = 'Asset leads risk'
        lag_text = f"Asset leads by {abs(best_lag)} day{'s' if abs(best_lag) > 1 else ''}"
    else:
        direction = 'Same-day'
        lag_text = "Moves same-day"

    return {
        'lag': best_lag,
        'lag_text': lag_text,
        'direction': direction,
        'correlation': round(best_corr, 3),
        'sample_size': n
    }


def compute_divergence(geri_series: List[Dict], asset_series: List[Dict], window: int = 7) -> str:
    geri_by_date = {r['date']: _to_float(r['value']) for r in geri_series if r.get('value') is not None}
    asset_by_date = {r['date']: _to_float(r['value']) for r in asset_series if r.get('value') is not None}

    common_dates = sorted(set(geri_by_date.keys()) & set(asset_by_date.keys()))
    if len(common_dates) < window:
        return 'insufficient data'

    recent = common_dates[-window:]
    geri_start = geri_by_date[recent[0]]
    geri_end = geri_by_date[recent[-1]]
    asset_start = asset_by_date[recent[0]]
    asset_end = asset_by_date[recent[-1]]

    geri_dir = 1 if geri_end > geri_start else (-1 if geri_end < geri_start else 0)
    asset_pct = ((asset_end - asset_start) / abs(asset_start)) * 100 if asset_start != 0 else 0
    asset_dir = 1 if asset_pct > 1 else (-1 if asset_pct < -1 else 0)

    if geri_dir == asset_dir or geri_dir == 0 or asset_dir == 0:
        return 'Aligned'

    geri_mag = abs(geri_end - geri_start)
    if geri_mag > 15 or abs(asset_pct) > 5:
        return 'Strong divergence'
    return 'Moderate divergence'


def compute_confirmation_score(geri_series: List[Dict], assets: Dict[str, List[Dict]], window: int = 7) -> Dict[str, Any]:
    geri_by_date = {r['date']: _to_float(r['value']) for r in geri_series if r.get('value') is not None}
    geri_dates = sorted(geri_by_date.keys())
    if len(geri_dates) < window:
        return {'score': None, 'label': 'Insufficient data', 'details': []}

    recent_geri = geri_dates[-window:]
    geri_start = geri_by_date[recent_geri[0]]
    geri_end = geri_by_date[recent_geri[-1]]
    geri_dir = 1 if geri_end > geri_start else (-1 if geri_end < geri_start else 0)

    confirming = 0
    total = 0
    details = []

    expect_dir_map = {
        'brent': 1,
        'ttf': 1,
        'vix': 1,
        'eurusd': -1,
        'gas_storage': -1,
    }

    for asset_key, asset_data in assets.items():
        a_by_date = {r['date']: _to_float(r['value']) for r in asset_data if r.get('value') is not None}
        common = sorted(set(recent_geri) & set(a_by_date.keys()))
        if len(common) < 3:
            continue

        a_start = a_by_date[common[0]]
        a_end = a_by_date[common[-1]]
        a_pct = ((a_end - a_start) / abs(a_start)) * 100 if a_start != 0 else 0
        a_dir = 1 if a_pct > 0.5 else (-1 if a_pct < -0.5 else 0)

        expected = expect_dir_map.get(asset_key, 1)
        expected_actual = expected * geri_dir

        total += 1
        is_confirming = (a_dir == expected_actual) or a_dir == 0
        if is_confirming:
            confirming += 1

        details.append({
            'asset': asset_key,
            'status': 'confirming' if is_confirming else 'diverging',
            'move_pct': round(a_pct, 2)
        })

    if total == 0:
        return {'score': None, 'label': 'No data', 'details': []}

    score = int((confirming / total) * 100)
    if score >= 80:
        label = 'Strong'
    elif score >= 60:
        label = 'Moderate'
    elif score >= 40:
        label = 'Weak'
    else:
        label = 'Divergent'

    return {'score': score, 'label': label, 'details': details}


def compute_storage_context(storage_series: List[Dict]) -> Dict[str, Any]:
    if not storage_series:
        return {'current_pct': None, 'seasonal_avg': None, 'vs_seasonal': None, 'narrative': 'No storage data'}

    latest = storage_series[-1]
    current_pct = _to_float(latest.get('value'))
    if current_pct is None:
        return {'current_pct': None, 'seasonal_avg': None, 'vs_seasonal': None, 'narrative': 'No storage data'}

    current_date = latest.get('date')
    month = current_date.month if hasattr(current_date, 'month') else 2
    day = current_date.day if hasattr(current_date, 'day') else 14

    seasonal_averages = {
        1: {1: 72, 15: 65},
        2: {1: 55, 15: 45},
        3: {1: 38, 15: 33},
        4: {1: 32, 15: 35},
        5: {1: 40, 15: 48},
        6: {1: 55, 15: 62},
        7: {1: 68, 15: 74},
        8: {1: 78, 15: 83},
        9: {1: 86, 15: 90},
        10: {1: 92, 15: 90},
        11: {1: 85, 15: 78},
        12: {1: 72, 15: 68},
    }

    month_data = seasonal_averages.get(month, {1: 50, 15: 50})
    if day <= 7:
        seasonal_avg = month_data[1]
    elif day >= 22:
        next_month = month + 1 if month < 12 else 1
        seasonal_avg = seasonal_averages.get(next_month, {1: 50})[1]
    else:
        seasonal_avg = month_data[15]

    diff = round(current_pct - seasonal_avg, 1)
    sign = '+' if diff > 0 else ''

    if diff > 5:
        status = 'Above seasonal'
    elif diff < -5:
        status = 'Below seasonal'
    else:
        status = 'Near seasonal average'

    narrative = f"{current_pct:.1f}% — {status} ({sign}{diff}% vs ~{seasonal_avg}% typical)"

    return {
        'current_pct': round(current_pct, 1),
        'seasonal_avg': seasonal_avg,
        'vs_seasonal': diff,
        'status': status,
        'narrative': narrative
    }


def compute_regime_transition(geri_series: List[Dict]) -> Dict[str, Any]:
    bands_map = {'LOW': 0, 'MODERATE': 1, 'ELEVATED': 2, 'SEVERE': 3, 'CRITICAL': 4}
    reverse_map = {0: 'LOW', 1: 'MODERATE', 2: 'ELEVATED', 3: 'SEVERE', 4: 'CRITICAL'}

    if len(geri_series) < 3:
        return {'current_band': None, 'transition': None, 'text': 'Insufficient data'}

    recent = geri_series[-7:] if len(geri_series) >= 7 else geri_series[-3:]

    current_band = recent[-1].get('band', 'MODERATE')
    bands_seen = [r.get('band', 'MODERATE') for r in recent]
    band_levels = [bands_map.get(b, 1) for b in bands_seen]

    current_level = band_levels[-1]
    avg_prior = sum(band_levels[:-1]) / len(band_levels[:-1]) if len(band_levels) > 1 else current_level

    if current_level > avg_prior + 0.3:
        transition = 'escalating'
        arrow = '↑'
    elif current_level < avg_prior - 0.3:
        transition = 'de-escalating'
        arrow = '↓'
    else:
        transition = 'stable'
        arrow = '→'

    unique_bands = list(dict.fromkeys(bands_seen))
    if len(unique_bands) >= 3:
        transition_text = f"Volatile — {' → '.join(unique_bands[-3:])}"
    elif transition == 'escalating':
        prev_band = reverse_map.get(max(0, current_level - 1), 'LOW')
        transition_text = f"Transitioning {prev_band} → {current_band} {arrow}"
    elif transition == 'de-escalating':
        prev_band = reverse_map.get(min(4, current_level + 1), 'CRITICAL')
        transition_text = f"Transitioning {prev_band} → {current_band} {arrow}"
    else:
        transition_text = f"{current_band} — Stable {arrow}"

    return {
        'current_band': current_band,
        'transition': transition,
        'text': transition_text
    }


def generate_reaction_summary(geri_series: List[Dict], divergences: Dict[str, str], confirmation: Dict[str, Any]) -> str:
    if not geri_series:
        return ''

    latest = geri_series[-1]
    value = _to_float(latest.get('value')) or 0
    band = latest.get('band', 'MODERATE')
    trend_7d = _to_float(latest.get('trend_7d')) or 0

    score = confirmation.get('score')
    score_label = confirmation.get('label', '')

    diverging_assets = [k for k, v in divergences.items() if 'divergence' in v.lower()]

    if trend_7d > 10:
        trend_word = 'surging'
    elif trend_7d > 3:
        trend_word = 'rising'
    elif trend_7d < -10:
        trend_word = 'falling sharply'
    elif trend_7d < -3:
        trend_word = 'easing'
    else:
        trend_word = 'stable'

    if score is not None and score >= 80:
        if len(diverging_assets) == 0:
            return f"GERI {trend_word} at {value} ({band}) with strong cross-asset confirmation — markets are pricing risk consistently."
        else:
            div_list = ', '.join(a.replace('_', ' ').title() for a in diverging_assets[:2])
            return f"GERI {trend_word} at {value} ({band}) — {div_list} diverging despite broad confirmation."
    elif score is not None and score >= 40:
        if diverging_assets:
            div_list = ', '.join(a.replace('_', ' ').title() for a in diverging_assets[:2])
            return f"GERI {trend_word} at {value} ({band}) — mixed signals. {div_list} showing divergence, possible delayed repricing."
        return f"GERI {trend_word} at {value} ({band}) — moderate cross-asset alignment. Watch for directional conviction."
    else:
        return f"GERI {trend_word} at {value} ({band}) — weak cross-asset confirmation. Markets may not be pricing risk adequately."


def _normalize_row(row):
    d = dict(row)
    for k, v in d.items():
        if isinstance(v, Decimal):
            d[k] = float(v)
    return d


def get_geri_trader_intel() -> Dict[str, Any]:
    geri_rows = [_normalize_row(r) for r in execute_production_query("""
        SELECT date, value, band, trend_1d, trend_7d
        FROM intel_indices_daily
        ORDER BY date ASC
    """)]

    brent_rows = [_normalize_row(r) for r in execute_production_query("""
        SELECT date, brent_price as value FROM oil_price_snapshots
        WHERE brent_price IS NOT NULL ORDER BY date ASC
    """)]

    ttf_rows = [_normalize_row(r) for r in execute_production_query("""
        SELECT date, ttf_price as value FROM ttf_gas_snapshots
        WHERE ttf_price IS NOT NULL ORDER BY date ASC
    """)]

    vix_rows = [_normalize_row(r) for r in execute_production_query("""
        SELECT date, vix_close as value FROM vix_snapshots
        WHERE vix_close IS NOT NULL ORDER BY date ASC
    """)]

    eurusd_rows = [_normalize_row(r) for r in execute_production_query("""
        SELECT date, rate as value FROM eurusd_snapshots
        WHERE rate IS NOT NULL ORDER BY date ASC
    """)]

    storage_rows = [_normalize_row(r) for r in execute_production_query("""
        SELECT date, eu_storage_percent as value FROM gas_storage_snapshots
        WHERE eu_storage_percent IS NOT NULL ORDER BY date ASC
    """)]

    recent_alerts = [_normalize_row(r) for r in execute_production_query("""
        SELECT headline, severity, scope_region, created_at
        FROM alert_events
        ORDER BY created_at DESC
        LIMIT 5
    """)]

    asset_map = {
        'brent': brent_rows,
        'ttf': ttf_rows,
        'vix': vix_rows,
        'eurusd': eurusd_rows,
        'gas_storage': storage_rows,
    }
    asset_labels = {
        'brent': 'Brent Oil',
        'ttf': 'TTF Gas',
        'vix': 'VIX',
        'eurusd': 'EUR/USD',
        'gas_storage': 'EU Gas Storage',
    }

    lead_lag = {}
    for key, series in asset_map.items():
        if key == 'gas_storage':
            continue
        ll = compute_lead_lag(geri_rows, series)
        lead_lag[key] = {
            'asset': asset_labels[key],
            **ll
        }

    divergences = {}
    for key, series in asset_map.items():
        div = compute_divergence(geri_rows, series)
        divergences[key] = div

    divergence_display = []
    for key in ['ttf', 'brent', 'vix', 'eurusd', 'gas_storage']:
        divergence_display.append({
            'asset': asset_labels[key],
            'status': divergences.get(key, 'insufficient data'),
        })

    confirmation = compute_confirmation_score(geri_rows, asset_map)

    storage_ctx = compute_storage_context(storage_rows)

    regime = compute_regime_transition(geri_rows)

    reaction_summary = generate_reaction_summary(geri_rows, divergences, confirmation)

    alerts_preview = []
    for a in recent_alerts:
        ca = a.get('created_at')
        alerts_preview.append({
            'headline': a.get('headline', ''),
            'severity': a.get('severity', ''),
            'region': a.get('scope_region', ''),
            'date': ca.strftime('%Y-%m-%d %H:%M') if hasattr(ca, 'strftime') else str(ca)[:16] if ca else '',
        })

    latest_geri = geri_rows[-1] if geri_rows else {}
    geri_date = latest_geri.get('date')

    return {
        'lead_lag': lead_lag,
        'divergence': divergence_display,
        'confirmation': confirmation,
        'storage_context': storage_ctx,
        'regime_transition': regime,
        'reaction_summary': reaction_summary,
        'alert_preview': alerts_preview,
        'geri_current': {
            'value': _to_float(latest_geri.get('value')),
            'band': latest_geri.get('band'),
            'trend_7d': _to_float(latest_geri.get('trend_7d')),
            'date': geri_date.isoformat() if hasattr(geri_date, 'isoformat') else str(geri_date) if geri_date else None,
        },
        'last_updated': geri_date.isoformat() if hasattr(geri_date, 'isoformat') else str(geri_date) if geri_date else None,
    }
