"""
EGSI Trader Intelligence Service

Computes tactical intelligence modules for Trader-tier EGSI dashboard:
1. Asset Overlay — aligned EGSI-M + asset time series for overlay charts
2. TTF vs EGSI Divergence — z-score spread for UNDERPRICED/OVERPRICED signals
3. Regime History — days spent in each band over last 12 months
4. Analog Event Finder — similar historical stress patterns
5. Risk Radar — bias indicators for next 30d (Up/Neutral/Down)
6. Alert Impact — scenario ranges if stress continues
7. Storage vs Seasonal — current vs seasonal average storage
8. Stress Momentum Gauge — RSI-like indicator
9. Biggest Risk Driver of the Week — top weekly driver headline
"""
import logging
import math
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, Any, List, Optional

from src.db.db import execute_production_query

logger = logging.getLogger(__name__)


def _to_float(v):
    if v is None:
        return None
    if isinstance(v, Decimal):
        return float(v)
    return float(v)


def _safe_date(d):
    if d is None:
        return None
    if hasattr(d, 'isoformat'):
        return d.isoformat()
    return str(d)


def _pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs)) or 1e-9
    dy = math.sqrt(sum((y - my) ** 2 for y in ys)) or 1e-9
    return num / (dx * dy)


def compute_asset_overlay(days: int = 90) -> Dict[str, Any]:
    egsi = execute_production_query("""
        SELECT index_date as date, index_value as value
        FROM egsi_m_daily
        WHERE index_date >= CURRENT_DATE - %s
        ORDER BY index_date ASC
    """, (days,))

    ttf = execute_production_query("""
        SELECT date, ttf_price as value
        FROM ttf_gas_snapshots
        WHERE date >= CURRENT_DATE - %s
        ORDER BY date ASC
    """, (days,))

    brent = execute_production_query("""
        SELECT date, brent_price as value
        FROM oil_price_snapshots
        WHERE date >= CURRENT_DATE - %s
        ORDER BY date ASC
    """, (days,))

    vix = execute_production_query("""
        SELECT date, vix_close as value
        FROM vix_snapshots
        WHERE date >= CURRENT_DATE - %s
        ORDER BY date ASC
    """, (days,))

    eurusd = execute_production_query("""
        SELECT date, rate as value
        FROM eurusd_snapshots
        WHERE date >= CURRENT_DATE - %s
        ORDER BY date ASC
    """, (days,))

    storage = execute_production_query("""
        SELECT date, eu_storage_percent as value
        FROM gas_storage_snapshots
        WHERE date >= CURRENT_DATE - %s
        ORDER BY date ASC
    """, (days,))

    def fmt(rows):
        return [{'date': _safe_date(r['date']), 'value': _to_float(r['value'])} for r in (rows or [])]

    return {
        'egsi_m': fmt(egsi),
        'ttf': fmt(ttf),
        'brent': fmt(brent),
        'vix': fmt(vix),
        'eurusd': fmt(eurusd),
        'storage': fmt(storage),
    }


def compute_ttf_divergence() -> Dict[str, Any]:
    rows = execute_production_query("""
        SELECT e.index_date as date, e.index_value as egsi_value, t.ttf_price
        FROM egsi_m_daily e
        JOIN ttf_gas_snapshots t ON e.index_date = t.date
        WHERE e.index_date >= CURRENT_DATE - 90
        ORDER BY e.index_date ASC
    """)

    if not rows or len(rows) < 5:
        return {'signal': 'INSUFFICIENT_DATA', 'z_score': None, 'description': 'Not enough aligned data points'}

    egsi_vals = [_to_float(r['egsi_value']) for r in rows]
    ttf_vals = [_to_float(r['ttf_price']) for r in rows]

    e_mean = sum(egsi_vals) / len(egsi_vals)
    e_std = math.sqrt(sum((v - e_mean) ** 2 for v in egsi_vals) / len(egsi_vals)) or 1e-9
    t_mean = sum(ttf_vals) / len(ttf_vals)
    t_std = math.sqrt(sum((v - t_mean) ** 2 for v in ttf_vals) / len(ttf_vals)) or 1e-9

    e_z = (egsi_vals[-1] - e_mean) / e_std
    t_z = (ttf_vals[-1] - t_mean) / t_std

    spread = t_z - e_z

    if spread > 1.5:
        signal = 'OVERPRICED'
        desc = f'TTF is {abs(spread):.1f}σ above EGSI-implied stress — market may be overpricing risk'
    elif spread < -1.5:
        signal = 'UNDERPRICED'
        desc = f'TTF is {abs(spread):.1f}σ below EGSI-implied stress — market may be underpricing risk'
    elif spread > 0.5:
        signal = 'SLIGHT_PREMIUM'
        desc = f'TTF carries a slight premium ({spread:.1f}σ) vs EGSI stress levels'
    elif spread < -0.5:
        signal = 'SLIGHT_DISCOUNT'
        desc = f'TTF at a slight discount ({abs(spread):.1f}σ) vs EGSI stress levels'
    else:
        signal = 'ALIGNED'
        desc = 'TTF pricing is broadly aligned with EGSI stress readings'

    return {
        'signal': signal,
        'z_score': round(spread, 2),
        'egsi_z': round(e_z, 2),
        'ttf_z': round(t_z, 2),
        'latest_egsi': round(egsi_vals[-1], 1),
        'latest_ttf': round(ttf_vals[-1], 2),
        'description': desc,
        'sample_size': len(rows),
    }


def compute_regime_history(days: int = 365) -> Dict[str, Any]:
    rows = execute_production_query("""
        SELECT band, COUNT(*) as days_count
        FROM egsi_m_daily
        WHERE index_date >= CURRENT_DATE - %s
        GROUP BY band
        ORDER BY days_count DESC
    """, (days,))

    band_map = {}
    total = 0
    for r in (rows or []):
        band = r['band'] or 'UNKNOWN'
        cnt = int(r['days_count'])
        band_map[band] = cnt
        total += cnt

    all_bands = ['LOW', 'NORMAL', 'ELEVATED', 'HIGH', 'CRITICAL']
    regime_data = []
    for b in all_bands:
        cnt = band_map.get(b, 0)
        regime_data.append({
            'band': b,
            'days': cnt,
            'pct': round((cnt / total * 100) if total > 0 else 0, 1),
        })

    transitions = execute_production_query("""
        WITH ordered AS (
            SELECT index_date, band, LAG(band) OVER (ORDER BY index_date) as prev_band
            FROM egsi_m_daily
            WHERE index_date >= CURRENT_DATE - %s
        )
        SELECT COUNT(*) as transitions
        FROM ordered
        WHERE band != prev_band AND prev_band IS NOT NULL
    """, (days,))

    return {
        'bands': regime_data,
        'total_days': total,
        'transitions': int(transitions[0]['transitions']) if transitions else 0,
        'period_days': days,
    }


def compute_analog_finder() -> Dict[str, Any]:
    rows = execute_production_query("""
        SELECT index_date as date, index_value as value, band
        FROM egsi_m_daily
        ORDER BY index_date ASC
    """)

    if not rows or len(rows) < 21:
        return {'analogs': [], 'message': 'Insufficient history for pattern matching'}

    values = [_to_float(r['value']) for r in rows]
    dates = [_safe_date(r['date']) for r in rows]
    bands = [r['band'] for r in rows]

    window = 14
    current = values[-window:]
    c_mean = sum(current) / len(current)
    c_std = math.sqrt(sum((v - c_mean) ** 2 for v in current) / len(current)) or 1e-9
    c_norm = [(v - c_mean) / c_std for v in current]

    analogs = []
    for i in range(len(values) - 2 * window):
        candidate = values[i:i + window]
        h_mean = sum(candidate) / len(candidate)
        h_std = math.sqrt(sum((v - h_mean) ** 2 for v in candidate) / len(candidate)) or 1e-9
        h_norm = [(v - h_mean) / h_std for v in candidate]

        corr = _pearson(c_norm, h_norm)

        if corr > 0.7:
            after = values[i + window:i + window + 7] if i + window + 7 <= len(values) else []
            outcome = None
            if after:
                delta = after[-1] - candidate[-1]
                outcome = 'rose' if delta > 2 else 'fell' if delta < -2 else 'stable'

            analogs.append({
                'start_date': dates[i],
                'end_date': dates[i + window - 1],
                'similarity': round(corr, 2),
                'avg_value': round(h_mean, 1),
                'band_at_time': bands[i + window - 1],
                'outcome_7d': outcome,
            })

    analogs.sort(key=lambda x: x['similarity'], reverse=True)

    return {
        'analogs': analogs[:5],
        'pattern_window': window,
        'current_avg': round(c_mean, 1),
    }


def compute_risk_radar() -> Dict[str, Any]:
    egsi = execute_production_query("""
        SELECT index_date as date, index_value as value, trend_1d, trend_7d, band
        FROM egsi_m_daily
        WHERE index_date >= CURRENT_DATE - 30
        ORDER BY index_date DESC
    """)

    if not egsi:
        return {'signals': [], 'overall_bias': 'NEUTRAL'}

    latest = egsi[0]
    t1d = _to_float(latest.get('trend_1d')) or 0
    t7d = _to_float(latest.get('trend_7d')) or 0
    band = (latest.get('band') or '').upper()
    val = _to_float(latest.get('value')) or 0

    signals = []

    if t1d > 3 and t7d > 2:
        signals.append({'factor': 'Stress Momentum', 'bias': 'UP', 'detail': 'Both short and medium-term trends rising'})
    elif t1d < -3 and t7d < -2:
        signals.append({'factor': 'Stress Momentum', 'bias': 'DOWN', 'detail': 'Both trends declining'})
    else:
        signals.append({'factor': 'Stress Momentum', 'bias': 'NEUTRAL', 'detail': 'Mixed or flat momentum signals'})

    storage = execute_production_query("""
        SELECT eu_storage_percent, seasonal_norm
        FROM gas_storage_snapshots
        ORDER BY date DESC LIMIT 1
    """)
    if storage:
        stor_pct = _to_float(storage[0].get('eu_storage_percent')) or 0
        norm = _to_float(storage[0].get('seasonal_norm')) or 0
        deficit = norm - stor_pct
        if deficit > 0.1:
            signals.append({'factor': 'Storage Draw Risk', 'bias': 'UP', 'detail': f'Storage {(deficit*100):.0f}% below seasonal norm'})
        elif stor_pct > norm + 0.05:
            signals.append({'factor': 'Storage Draw Risk', 'bias': 'DOWN', 'detail': 'Storage above seasonal norm'})
        else:
            signals.append({'factor': 'Storage Draw Risk', 'bias': 'NEUTRAL', 'detail': 'Storage near seasonal average'})

    ttf = execute_production_query("""
        SELECT ttf_price FROM ttf_gas_snapshots
        ORDER BY date DESC LIMIT 7
    """)
    if ttf and len(ttf) >= 3:
        prices = [_to_float(r['ttf_price']) for r in ttf]
        avg = sum(prices) / len(prices)
        vol = math.sqrt(sum((p - avg) ** 2 for p in prices) / len(prices))
        vol_pct = (vol / avg * 100) if avg > 0 else 0
        if vol_pct > 5:
            signals.append({'factor': 'Price Volatility', 'bias': 'UP', 'detail': f'TTF volatility elevated at {vol_pct:.1f}%'})
        elif vol_pct < 2:
            signals.append({'factor': 'Price Volatility', 'bias': 'DOWN', 'detail': 'TTF volatility compressed'})
        else:
            signals.append({'factor': 'Price Volatility', 'bias': 'NEUTRAL', 'detail': 'Normal TTF volatility'})

    if band in ('HIGH', 'CRITICAL'):
        signals.append({'factor': 'Supply Disruption', 'bias': 'UP', 'detail': f'Stress in {band} band signals elevated disruption risk'})
    elif band in ('LOW', 'NORMAL'):
        signals.append({'factor': 'Supply Disruption', 'bias': 'DOWN', 'detail': 'Low stress band suggests contained disruption risk'})
    else:
        signals.append({'factor': 'Supply Disruption', 'bias': 'NEUTRAL', 'detail': 'Elevated but not critical disruption risk'})

    up_count = sum(1 for s in signals if s['bias'] == 'UP')
    down_count = sum(1 for s in signals if s['bias'] == 'DOWN')

    if up_count >= 3:
        overall = 'RISK_ON'
    elif down_count >= 3:
        overall = 'RISK_OFF'
    elif up_count > down_count:
        overall = 'LEANING_UP'
    elif down_count > up_count:
        overall = 'LEANING_DOWN'
    else:
        overall = 'NEUTRAL'

    return {
        'signals': signals,
        'overall_bias': overall,
    }


def compute_alert_impact() -> Dict[str, Any]:
    latest = execute_production_query("""
        SELECT index_value as value, band, trend_1d, trend_7d
        FROM egsi_m_daily
        ORDER BY index_date DESC LIMIT 1
    """)

    if not latest:
        return {'scenarios': []}

    val = _to_float(latest[0]['value']) or 0
    t1d = _to_float(latest[0].get('trend_1d')) or 0
    t7d = _to_float(latest[0].get('trend_7d')) or 0
    band = latest[0].get('band', 'LOW')

    momentum = (t1d * 0.6 + t7d * 0.4)

    low_2w = max(0, val + momentum * 14 * 0.3)
    high_2w = min(100, val + momentum * 14 * 1.2)
    mid_2w = val + momentum * 14 * 0.7

    if high_2w < low_2w:
        low_2w, high_2w = high_2w, low_2w

    def band_for(v):
        if v >= 80:
            return 'CRITICAL'
        if v >= 60:
            return 'HIGH'
        if v >= 40:
            return 'ELEVATED'
        if v >= 20:
            return 'NORMAL'
        return 'LOW'

    return {
        'current_value': round(val, 1),
        'current_band': band,
        'momentum': round(momentum, 2),
        'scenarios': [
            {
                'label': 'If stress accelerates',
                'egsi_range': f'{round(max(val, high_2w - 5), 1)} – {round(high_2w, 1)}',
                'implied_band': band_for(high_2w),
                'ttf_impact': 'Higher' if high_2w > 50 else 'Moderate',
            },
            {
                'label': 'Base case (trend continues)',
                'egsi_range': f'{round(min(low_2w + 3, mid_2w - 3), 1)} – {round(mid_2w + 3, 1)}',
                'implied_band': band_for(mid_2w),
                'ttf_impact': 'Stable to higher' if mid_2w > val else 'Easing',
            },
            {
                'label': 'If stress reverses',
                'egsi_range': f'{round(low_2w, 1)} – {round(min(val, low_2w + 8), 1)}',
                'implied_band': band_for(low_2w),
                'ttf_impact': 'Lower' if low_2w < val - 5 else 'Contained',
            },
        ],
    }


def compute_storage_seasonal() -> Dict[str, Any]:
    storage = execute_production_query("""
        SELECT date, eu_storage_percent, seasonal_norm
        FROM gas_storage_snapshots
        ORDER BY date ASC
    """)

    if not storage:
        return {'current': [], 'seasonal_avg': [], 'message': 'No storage data available'}

    current = [{'date': _safe_date(r['date']), 'value': round(_to_float(r['eu_storage_percent']) * 100, 1) if r.get('eu_storage_percent') else None} for r in storage]
    seasonal = [{'date': _safe_date(r['date']), 'value': round(_to_float(r['seasonal_norm']) * 100, 1) if r.get('seasonal_norm') else None} for r in storage]

    latest = storage[-1] if storage else None
    deficit = None
    if latest and latest.get('eu_storage_percent') and latest.get('seasonal_norm'):
        deficit = round((_to_float(latest['seasonal_norm']) - _to_float(latest['eu_storage_percent'])) * 100, 1)

    return {
        'current': current,
        'seasonal_avg': seasonal,
        'latest_pct': round(_to_float(latest['eu_storage_percent']) * 100, 1) if latest and latest.get('eu_storage_percent') else None,
        'seasonal_norm_pct': round(_to_float(latest['seasonal_norm']) * 100, 1) if latest and latest.get('seasonal_norm') else None,
        'deficit': deficit,
    }


def compute_stress_momentum(window: int = 14) -> Dict[str, Any]:
    rows = execute_production_query("""
        SELECT index_date as date, index_value as value
        FROM egsi_m_daily
        ORDER BY index_date DESC
        LIMIT %s
    """, (window + 1,))

    if not rows or len(rows) < window:
        return {'rsi': None, 'label': 'INSUFFICIENT_DATA'}

    rows = list(reversed(rows))
    values = [_to_float(r['value']) for r in rows]

    gains = []
    losses = []
    for i in range(1, len(values)):
        delta = values[i] - values[i - 1]
        if delta > 0:
            gains.append(delta)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(delta))

    avg_gain = sum(gains) / len(gains) if gains else 0
    avg_loss = sum(losses) / len(losses) if losses else 0

    if avg_loss == 0:
        rsi = 100.0
    elif avg_gain == 0:
        rsi = 0.0
    else:
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

    if rsi >= 70:
        label = 'OVERBOUGHT'
        desc = 'Stress momentum is stretched — potential for relief'
    elif rsi >= 55:
        label = 'BUILDING'
        desc = 'Stress is building with moderate momentum'
    elif rsi <= 30:
        label = 'OVERSOLD'
        desc = 'Stress momentum is exhausted — potential for rebound'
    elif rsi <= 45:
        label = 'EASING'
        desc = 'Stress is easing with downward momentum'
    else:
        label = 'NEUTRAL'
        desc = 'Stress momentum is balanced'

    return {
        'rsi': round(rsi, 1),
        'label': label,
        'description': desc,
        'window': window,
    }


def compute_weekly_driver() -> Dict[str, Any]:
    rows = execute_production_query("""
        SELECT headline, severity, confidence, score, driver_type, component_key, source
        FROM egsi_drivers_daily
        WHERE index_date >= CURRENT_DATE - 7
          AND index_family = 'egsi_m'
        ORDER BY score DESC NULLS LAST, severity DESC NULLS LAST
        LIMIT 1
    """)

    if not rows:
        return {'headline': None, 'message': 'No driver data for this week'}

    driver = rows[0]
    return {
        'headline': driver.get('headline', 'Unknown driver'),
        'severity': driver.get('severity'),
        'confidence': driver.get('confidence'),
        'score': _to_float(driver.get('score')),
        'type': driver.get('driver_type'),
        'component': driver.get('component_key'),
        'source': driver.get('source'),
    }


def compute_rolling_correlations(days: int = 90) -> List[Dict[str, Any]]:
    egsi = execute_production_query("""
        SELECT index_date as date, index_value as value
        FROM egsi_m_daily
        WHERE index_date >= CURRENT_DATE - %s
        ORDER BY index_date ASC
    """, (days,))

    if not egsi or len(egsi) < 30:
        return []

    asset_queries = {
        'TTF': ("SELECT date, ttf_price as value FROM ttf_gas_snapshots WHERE date >= CURRENT_DATE - %s ORDER BY date ASC", (days,)),
        'Brent': ("SELECT date, brent_price as value FROM oil_price_snapshots WHERE date >= CURRENT_DATE - %s ORDER BY date ASC", (days,)),
        'VIX': ("SELECT date, vix_close as value FROM vix_snapshots WHERE date >= CURRENT_DATE - %s ORDER BY date ASC", (days,)),
        'EUR/USD': ("SELECT date, rate as value FROM eurusd_snapshots WHERE date >= CURRENT_DATE - %s ORDER BY date ASC", (days,)),
        'Storage': ("SELECT date, eu_storage_percent as value FROM gas_storage_snapshots WHERE date >= CURRENT_DATE - %s ORDER BY date ASC", (days,)),
    }

    egsi_map = {_safe_date(r['date']): _to_float(r['value']) for r in egsi}
    egsi_dates = [_safe_date(r['date']) for r in egsi]

    results = []
    for asset_name, (query, params) in asset_queries.items():
        rows = execute_production_query(query, params)
        if not rows:
            continue
        asset_map = {_safe_date(r['date']): _to_float(r['value']) for r in rows}
        aligned_egsi = []
        aligned_asset = []
        for d in egsi_dates:
            if d in asset_map and egsi_map.get(d) is not None and asset_map[d] is not None:
                aligned_egsi.append(egsi_map[d])
                aligned_asset.append(asset_map[d])

        if len(aligned_egsi) < 10:
            continue

        window = 30
        correlations = []
        step = max(1, len(aligned_egsi) // 20)
        for i in range(window, len(aligned_egsi), step):
            seg_e = aligned_egsi[i - window:i]
            seg_a = aligned_asset[i - window:i]
            corr = _pearson(seg_e, seg_a)
            correlations.append(round(corr, 3))

        full_corr = _pearson(aligned_egsi, aligned_asset)
        latest_corr = _pearson(aligned_egsi[-window:], aligned_asset[-window:]) if len(aligned_egsi) >= window else full_corr

        results.append({
            'asset': asset_name,
            'correlation': round(latest_corr, 3),
            'full_period': round(full_corr, 3),
            'rolling': correlations,
            'sample_size': len(aligned_egsi),
        })

    results.sort(key=lambda x: abs(x['correlation']), reverse=True)
    return results


def compute_component_decomposition() -> Dict[str, Any]:
    rows = execute_production_query("""
        SELECT component_key, driver_type,
               COUNT(*) as count,
               AVG(score) as avg_score,
               MAX(score) as max_score,
               AVG(severity) as avg_severity
        FROM egsi_drivers_daily
        WHERE index_family = 'egsi_m'
          AND index_date >= CURRENT_DATE - 30
        GROUP BY component_key, driver_type
        ORDER BY avg_score DESC NULLS LAST
    """)

    if not rows:
        return {'components': [], 'total_drivers': 0}

    total_score = sum(_to_float(r['avg_score']) or 0 for r in rows)
    components = []
    for r in rows:
        avg_s = _to_float(r['avg_score']) or 0
        weight = round((avg_s / total_score * 100) if total_score > 0 else 0, 1)
        components.append({
            'component': r['component_key'] or 'unknown',
            'type': r['driver_type'] or 'unknown',
            'avg_score': round(avg_s, 2),
            'max_score': round(_to_float(r['max_score']) or 0, 2),
            'avg_severity': round(_to_float(r['avg_severity']) or 0, 1),
            'count': int(r['count']),
            'weight_pct': weight,
        })

    return {
        'components': components[:10],
        'total_drivers': sum(int(r['count']) for r in rows),
        'period_days': 30,
    }


def compute_regime_transition_probability() -> Dict[str, Any]:
    rows = execute_production_query("""
        WITH ordered AS (
            SELECT index_date, band,
                   LAG(band) OVER (ORDER BY index_date) as prev_band
            FROM egsi_m_daily
        )
        SELECT prev_band, band as next_band, COUNT(*) as transitions
        FROM ordered
        WHERE prev_band IS NOT NULL
        GROUP BY prev_band, band
        ORDER BY prev_band, transitions DESC
    """)

    if not rows:
        return {'transitions': {}, 'current_band': None}

    transition_counts = {}
    for r in rows:
        prev = r['prev_band']
        nxt = r['next_band']
        cnt = int(r['transitions'])
        if prev not in transition_counts:
            transition_counts[prev] = {}
        transition_counts[prev][nxt] = cnt

    probabilities = {}
    for band, targets in transition_counts.items():
        total = sum(targets.values())
        probabilities[band] = {}
        for target, cnt in targets.items():
            probabilities[band][target] = round(cnt / total * 100, 1) if total > 0 else 0

    latest = execute_production_query("""
        SELECT band FROM egsi_m_daily ORDER BY index_date DESC LIMIT 1
    """)
    current_band = latest[0]['band'] if latest else None

    current_probs = probabilities.get(current_band, {})
    all_bands = ['LOW', 'NORMAL', 'ELEVATED', 'HIGH', 'CRITICAL']
    next_probs = []
    for b in all_bands:
        next_probs.append({
            'band': b,
            'probability': current_probs.get(b, 0),
            'is_current': b == current_band,
        })

    return {
        'current_band': current_band,
        'next_day_probabilities': next_probs,
        'full_matrix': probabilities,
    }


def compute_cross_index_spillover(days: int = 90) -> List[Dict[str, Any]]:
    egsi = execute_production_query("""
        SELECT index_date as date, index_value as value
        FROM egsi_m_daily
        WHERE index_date >= CURRENT_DATE - %s
        ORDER BY index_date ASC
    """, (days,))

    if not egsi or len(egsi) < 14:
        return []

    egsi_map = {_safe_date(r['date']): _to_float(r['value']) for r in egsi}
    egsi_dates = [_safe_date(r['date']) for r in egsi]

    index_queries = {
        'GERI': "SELECT calculated_at::date as date, risk_score as value FROM risk_indices WHERE region = 'global' AND window_days = 7 AND calculated_at::date >= CURRENT_DATE - %s ORDER BY calculated_at::date ASC",
        'EERI': "SELECT calculated_at::date as date, risk_score as value FROM risk_indices WHERE region = 'europe' AND window_days = 7 AND calculated_at::date >= CURRENT_DATE - %s ORDER BY calculated_at::date ASC",
    }

    results = []
    for idx_name, query in index_queries.items():
        try:
            rows = execute_production_query(query, (days,))
            if not rows:
                continue

            idx_map = {}
            for r in rows:
                d = _safe_date(r['date'])
                idx_map[d] = _to_float(r['value'])

            aligned_egsi = []
            aligned_idx = []
            for d in egsi_dates:
                if d in idx_map and egsi_map.get(d) is not None and idx_map[d] is not None:
                    aligned_egsi.append(egsi_map[d])
                    aligned_idx.append(idx_map[d])

            if len(aligned_egsi) < 10:
                continue

            corr = _pearson(aligned_egsi, aligned_idx)

            egsi_changes = [aligned_egsi[i] - aligned_egsi[i-1] for i in range(1, len(aligned_egsi))]
            idx_changes = [aligned_idx[i] - aligned_idx[i-1] for i in range(1, len(aligned_idx))]

            lead_corr = 0
            lag_corr = 0
            if len(egsi_changes) >= 5 and len(idx_changes) >= 5:
                lead_corr = _pearson(egsi_changes[:-1], idx_changes[1:])
                lag_corr = _pearson(egsi_changes[1:], idx_changes[:-1])

            if abs(lead_corr) > abs(lag_corr) and abs(lead_corr) > 0.2:
                lead_lag = f'EGSI leads {idx_name} by ~1 day'
            elif abs(lag_corr) > abs(lead_corr) and abs(lag_corr) > 0.2:
                lead_lag = f'{idx_name} leads EGSI by ~1 day'
            else:
                lead_lag = 'Contemporaneous movement'

            results.append({
                'index': idx_name,
                'correlation': round(corr, 3),
                'lead_correlation': round(lead_corr, 3),
                'lag_correlation': round(lag_corr, 3),
                'lead_lag_insight': lead_lag,
                'sample_size': len(aligned_egsi),
            })
        except Exception as e:
            logger.warning(f"Cross-index spillover error for {idx_name}: {e}")
            continue

    return results


def get_egsi_trader_intel(plan_level: int = 2) -> Dict[str, Any]:
    result = {}

    try:
        result['asset_overlay'] = compute_asset_overlay(days=90 if plan_level == 2 else 365)
    except Exception as e:
        logger.error(f"Asset overlay error: {e}")
        result['asset_overlay'] = {'egsi_m': [], 'ttf': [], 'brent': [], 'vix': [], 'eurusd': [], 'storage': []}

    try:
        result['ttf_divergence'] = compute_ttf_divergence()
    except Exception as e:
        logger.error(f"TTF divergence error: {e}")
        result['ttf_divergence'] = {'signal': 'ERROR', 'z_score': None}

    try:
        result['regime_history'] = compute_regime_history(days=365)
    except Exception as e:
        logger.error(f"Regime history error: {e}")
        result['regime_history'] = {'bands': [], 'total_days': 0}

    try:
        result['analog_finder'] = compute_analog_finder()
    except Exception as e:
        logger.error(f"Analog finder error: {e}")
        result['analog_finder'] = {'analogs': []}

    try:
        result['risk_radar'] = compute_risk_radar()
    except Exception as e:
        logger.error(f"Risk radar error: {e}")
        result['risk_radar'] = {'signals': [], 'overall_bias': 'NEUTRAL'}

    try:
        result['alert_impact'] = compute_alert_impact()
    except Exception as e:
        logger.error(f"Alert impact error: {e}")
        result['alert_impact'] = {'scenarios': []}

    try:
        result['storage_seasonal'] = compute_storage_seasonal()
    except Exception as e:
        logger.error(f"Storage seasonal error: {e}")
        result['storage_seasonal'] = {'current': [], 'seasonal_avg': []}

    try:
        result['stress_momentum'] = compute_stress_momentum()
    except Exception as e:
        logger.error(f"Stress momentum error: {e}")
        result['stress_momentum'] = {'rsi': None, 'label': 'ERROR'}

    try:
        result['weekly_driver'] = compute_weekly_driver()
    except Exception as e:
        logger.error(f"Weekly driver error: {e}")
        result['weekly_driver'] = {'headline': None}

    result['plan_level'] = plan_level

    if plan_level >= 3:
        try:
            result['rolling_correlations'] = compute_rolling_correlations(days=90)
        except Exception as e:
            logger.error(f"Rolling correlations error: {e}")
            result['rolling_correlations'] = []

        try:
            result['component_decomposition'] = compute_component_decomposition()
        except Exception as e:
            logger.error(f"Component decomposition error: {e}")
            result['component_decomposition'] = {'components': [], 'total_drivers': 0}

        try:
            result['regime_transition_probability'] = compute_regime_transition_probability()
        except Exception as e:
            logger.error(f"Regime transition probability error: {e}")
            result['regime_transition_probability'] = {'transitions': {}, 'current_band': None}

    if plan_level >= 4:
        try:
            result['cross_index_spillover'] = compute_cross_index_spillover(days=90)
        except Exception as e:
            logger.error(f"Cross-index spillover error: {e}")
            result['cross_index_spillover'] = []

    return result
