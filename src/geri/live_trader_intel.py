"""
GERI Live — Energy Commodity Trader Intelligence Module

Five professional intelligence features for energy commodity traders:
1. Price-Risk Correlation Signal — GERI vs Brent/WTI/TTF divergence detection
2. Trading Risk Heatmap — Risk intensity across energy commodities
3. Position Risk Alert — Threshold-based commodity risk warnings
4. Intraday Risk Windows — Risk mapped to trading sessions (Asia/London/NY)
5. Flash Headline Feed — Highest-severity alerts that moved GERI
"""

import logging
import math
from datetime import date, datetime, timedelta, timezone
from typing import Dict, Any, List, Optional
from decimal import Decimal

from src.db.db import execute_query, execute_one

logger = logging.getLogger(__name__)

TRADING_SESSIONS = [
    {'name': 'Asia', 'start_hour': 1, 'end_hour': 8, 'color': '#3b82f6'},
    {'name': 'London', 'start_hour': 8, 'end_hour': 14, 'color': '#22c55e'},
    {'name': 'New York', 'start_hour': 14, 'end_hour': 21, 'color': '#f59e0b'},
    {'name': 'After Hours', 'start_hour': 21, 'end_hour': 1, 'color': '#64748b'},
]

OIL_KEYWORDS = ['oil', 'crude', 'brent', 'wti', 'opec', 'petroleum', 'barrel',
                'iran', 'iraq', 'saudi', 'refinery', 'tanker']
GAS_KEYWORDS = ['gas', 'ttf', 'lng', 'pipeline', 'gazprom', 'nord stream',
                'storage', 'methane']
FREIGHT_KEYWORDS = ['freight', 'shipping', 'tanker', 'strait', 'hormuz',
                    'chokepoint', 'suez', 'bosporus', 'maritime']
POWER_KEYWORDS = ['power', 'electric', 'grid', 'nuclear', 'renewable',
                  'wind', 'solar', 'interconnect']


def _sf(val, default=None):
    if val is None:
        return default
    try:
        if isinstance(val, Decimal):
            return float(val)
        return float(val)
    except (TypeError, ValueError):
        return default


def _pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs)) or 1e-9
    dy = math.sqrt(sum((y - my) ** 2 for y in ys)) or 1e-9
    return num / (dx * dy)


def get_price_risk_correlation() -> Dict[str, Any]:
    oil_rows = execute_query(
        "SELECT date, brent_price, wti_price FROM oil_price_snapshots ORDER BY date DESC LIMIT 14"
    ) or []
    ttf_rows = execute_query(
        "SELECT date, ttf_price FROM ttf_gas_snapshots ORDER BY date DESC LIMIT 14"
    ) or []
    vix_rows = execute_query(
        "SELECT date, vix_close FROM vix_snapshots WHERE vix_close IS NOT NULL ORDER BY date DESC LIMIT 14"
    ) or []

    geri_latest = execute_one(
        "SELECT value, band FROM geri_live ORDER BY computed_at DESC LIMIT 1"
    )

    geri_daily = execute_query(
        """SELECT date, value FROM (
            SELECT DISTINCT ON (computed_at::date) computed_at::date as date, value
            FROM geri_live ORDER BY computed_at::date DESC, computed_at DESC
        ) sub ORDER BY date DESC LIMIT 14"""
    ) or []

    latest_oil = oil_rows[0] if oil_rows else None
    prev_oil = oil_rows[1] if len(oil_rows) > 1 else None
    latest_ttf = ttf_rows[0] if ttf_rows else None
    prev_ttf = ttf_rows[1] if len(ttf_rows) > 1 else None
    latest_vix = vix_rows[0] if vix_rows else None
    prev_vix = vix_rows[1] if len(vix_rows) > 1 else None
    geri_val = geri_latest['value'] if geri_latest else 0
    geri_band = geri_latest['band'] if geri_latest else 'LOW'

    signals = []

    if latest_oil and prev_oil:
        bn = _sf(latest_oil['brent_price'])
        bp = _sf(prev_oil['brent_price'])
        wn = _sf(latest_oil['wti_price'])
        wp = _sf(prev_oil['wti_price'])
        if bn and bp and bp > 0:
            signals.append({
                'commodity': 'Brent Crude', 'price': round(bn, 2),
                'change_pct': round(((bn - bp) / bp) * 100, 2),
                'unit': 'USD/bbl', 'color': '#3b82f6', 'key': 'brent',
            })
        if wn and wp and wp > 0:
            signals.append({
                'commodity': 'WTI Crude', 'price': round(wn, 2),
                'change_pct': round(((wn - wp) / wp) * 100, 2),
                'unit': 'USD/bbl', 'color': '#8b5cf6', 'key': 'wti',
            })

    if latest_ttf and prev_ttf:
        tn = _sf(latest_ttf['ttf_price'])
        tp = _sf(prev_ttf['ttf_price'])
        if tn and tp and tp > 0:
            signals.append({
                'commodity': 'TTF Gas', 'price': round(tn, 2),
                'change_pct': round(((tn - tp) / tp) * 100, 2),
                'unit': 'EUR/MWh', 'color': '#f59e0b', 'key': 'ttf',
            })

    if latest_vix and prev_vix:
        vn = _sf(latest_vix['vix_close'])
        vp = _sf(prev_vix['vix_close'])
        if vn and vp and vp > 0:
            signals.append({
                'commodity': 'VIX', 'price': round(vn, 2),
                'change_pct': round(((vn - vp) / vp) * 100, 2),
                'unit': '', 'color': '#ef4444', 'key': 'vix',
            })

    geri_daily_vals = [int(r['value']) for r in geri_daily]
    geri_trend_pct = 0
    if len(geri_daily_vals) >= 2 and geri_daily_vals[1] > 0:
        geri_trend_pct = round(((geri_daily_vals[0] - geri_daily_vals[1]) / geri_daily_vals[1]) * 100, 1)

    divergence = _detect_divergence(geri_trend_pct, signals)
    correlation_7d = _compute_7d_correlation(oil_rows, geri_daily)

    return {
        'geri_value': geri_val,
        'geri_band': geri_band,
        'geri_trend_pct': geri_trend_pct,
        'signals': signals,
        'divergence': divergence,
        'correlation_7d': correlation_7d,
    }


def _detect_divergence(geri_trend_pct, signals):
    if not signals:
        return None
    avg_price_chg = sum(s['change_pct'] for s in signals) / len(signals)
    if (geri_trend_pct > 5 and avg_price_chg < -0.5) or (geri_trend_pct < -5 and avg_price_chg > 0.5):
        return {
            'type': 'risk_price_divergence',
            'geri_direction': 'rising' if geri_trend_pct > 0 else 'falling',
            'price_direction': 'rising' if avg_price_chg > 0 else 'falling',
            'severity': 'high',
            'message': f"GERI {'rising' if geri_trend_pct > 0 else 'falling'} while prices {'rising' if avg_price_chg > 0 else 'falling'} — potential trading opportunity"
        }
    elif abs(geri_trend_pct) > 10 and abs(avg_price_chg) < 1:
        return {
            'type': 'risk_not_priced',
            'geri_direction': 'rising' if geri_trend_pct > 0 else 'falling',
            'price_direction': 'flat',
            'severity': 'medium',
            'message': f"Risk {'escalating' if geri_trend_pct > 0 else 'declining'} but prices stable — market may not have priced in risk shift"
        }
    return None


def _compute_7d_correlation(oil_rows, geri_daily):
    if not oil_rows or not geri_daily or len(oil_rows) < 5 or len(geri_daily) < 5:
        return None
    oil_by_date = {str(r['date']): _sf(r['brent_price']) for r in oil_rows if _sf(r['brent_price'])}
    geri_by_date = {str(r['date']): int(r['value']) for r in geri_daily}
    common = sorted(set(oil_by_date) & set(geri_by_date))
    if len(common) < 5:
        return None
    common = common[-7:]
    corr = _pearson([oil_by_date[d] for d in common], [geri_by_date[d] for d in common])
    if corr is None:
        return None
    strength = 'Strong' if abs(corr) > 0.7 else 'Moderate' if abs(corr) > 0.4 else 'Weak'
    direction = 'positive' if corr > 0 else 'negative'
    return {
        'value': round(corr, 3), 'strength': strength, 'direction': direction,
        'label': f"{strength} {direction} ({round(corr, 2)})", 'days': len(common),
    }


def get_trading_risk_heatmap() -> Dict[str, Any]:
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    rows = execute_query("""
        SELECT id, scope_assets, scope_region, severity, category, headline, alert_type, created_at
        FROM alert_events
        WHERE created_at >= %s
          AND alert_type IN ('HIGH_IMPACT_EVENT','REGIONAL_RISK_SPIKE','ASSET_RISK_SPIKE')
        ORDER BY created_at DESC
    """, (today_start,)) or []

    commodities = {
        'oil': {'label': 'Oil (Brent/WTI)', 'color': '#3b82f6', 'alert_count': 0,
                'severity_sum': 0, 'max_severity': 0, 'regions': set(), 'keywords': OIL_KEYWORDS},
        'gas': {'label': 'Natural Gas (TTF)', 'color': '#f59e0b', 'alert_count': 0,
                'severity_sum': 0, 'max_severity': 0, 'regions': set(), 'keywords': GAS_KEYWORDS},
        'freight': {'label': 'Freight/Shipping', 'color': '#8b5cf6', 'alert_count': 0,
                    'severity_sum': 0, 'max_severity': 0, 'regions': set(), 'keywords': FREIGHT_KEYWORDS},
        'power': {'label': 'Power/Electricity', 'color': '#22c55e', 'alert_count': 0,
                  'severity_sum': 0, 'max_severity': 0, 'regions': set(), 'keywords': POWER_KEYWORDS},
    }

    for row in rows:
        scope_assets = row.get('scope_assets') or []
        headline_lower = (row.get('headline') or '').lower()
        severity = row.get('severity', 1)
        region = row.get('scope_region', 'Global')

        matched = set()
        if isinstance(scope_assets, list):
            for a in scope_assets:
                al = a.lower()
                if al in ('oil',): matched.add('oil')
                elif al in ('gas', 'lng'): matched.add('gas')
                elif al in ('freight',): matched.add('freight')

        for key, cfg in commodities.items():
            if any(kw in headline_lower for kw in cfg['keywords']):
                matched.add(key)

        if not matched:
            if any(kw in headline_lower for kw in ['iran', 'iraq', 'saudi', 'opec', 'russia', 'sanction']):
                matched.add('oil')
            if any(kw in headline_lower for kw in ['europe', 'ukraine', 'pipeline']):
                matched.add('gas')

        for key in matched:
            commodities[key]['alert_count'] += 1
            commodities[key]['severity_sum'] += severity
            commodities[key]['max_severity'] = max(commodities[key]['max_severity'], severity)
            commodities[key]['regions'].add(region)

    heatmap = []
    for key, cfg in commodities.items():
        risk_intensity = 0
        if cfg['alert_count'] > 0:
            avg_sev = cfg['severity_sum'] / cfg['alert_count']
            risk_intensity = min(100, int((avg_sev / 5) * 60 + (min(cfg['alert_count'], 10) / 10) * 40))
        risk_level = 'none'
        if risk_intensity > 75: risk_level = 'critical'
        elif risk_intensity > 50: risk_level = 'high'
        elif risk_intensity > 25: risk_level = 'moderate'
        elif risk_intensity > 0: risk_level = 'low'

        heatmap.append({
            'commodity': key, 'label': cfg['label'], 'color': cfg['color'],
            'alert_count': cfg['alert_count'], 'max_severity': cfg['max_severity'],
            'risk_intensity': risk_intensity, 'risk_level': risk_level,
            'regions': sorted(list(cfg['regions']))[:5],
        })
    heatmap.sort(key=lambda x: x['risk_intensity'], reverse=True)
    return {'heatmap': heatmap, 'total_alerts': len(rows), 'as_of': datetime.utcnow().strftime('%H:%M UTC')}


def get_position_risk_alerts(geri_value: int, geri_band: str,
                             velocity: Optional[Dict] = None,
                             band_proximity: Optional[Dict] = None,
                             top_drivers: Optional[List] = None) -> Dict[str, Any]:
    alerts = []

    if band_proximity and band_proximity.get('direction') == 'up':
        pts = band_proximity.get('points_away', 99)
        target = band_proximity.get('target_band', '')
        if pts <= 5:
            sev = 'critical' if pts <= 2 else 'warning'
            alerts.append({
                'type': 'band_proximity', 'severity': sev,
                'title': f'{pts} pts from {target}',
                'message': f'GERI is {pts} points from escalating to {target} band. Heightened risk for all energy positions.',
                'action': f'Consider reducing exposure or hedging energy positions before {target} breach.',
            })

    if velocity:
        delta = velocity.get('delta', 0)
        if abs(delta) >= 3:
            direction = 'rising' if delta > 0 else 'falling'
            sev = 'critical' if abs(delta) >= 5 else 'warning'
            alerts.append({
                'type': 'velocity', 'severity': sev,
                'title': f'Rapid risk {direction}',
                'message': f'GERI moving at {velocity.get("label", "")}. {"Risk acceleration — markets may gap." if delta > 0 else "Risk easing — potential entry opportunity."}',
                'action': f'{"Monitor positions closely. Consider stop-loss tightening." if delta > 0 else "Watch for mean-reversion trades as risk normalizes."}',
            })

    for exp in _detect_commodity_exposure(top_drivers or []):
        alerts.append(exp)

    if geri_value >= 60 and geri_band in ('ELEVATED', 'SEVERE', 'CRITICAL'):
        alerts.append({
            'type': 'overall_risk',
            'severity': 'warning' if geri_value < 80 else 'critical',
            'title': f'GERI at {geri_value} ({geri_band})',
            'message': f'Overall energy risk is {geri_band.lower()}. All commodity positions carry elevated geopolitical risk premium.',
            'action': 'Review portfolio-wide energy exposure. Consider defensive positioning across all energy commodities.',
        })

    alerts.sort(key=lambda x: 0 if x['severity'] == 'critical' else 1)
    return {
        'alerts': alerts[:6],
        'risk_level': 'critical' if any(a['severity'] == 'critical' for a in alerts) else ('warning' if alerts else 'clear'),
        'alert_count': len(alerts),
    }


def _detect_commodity_exposure(top_drivers):
    oil_d, gas_d = [], []
    for d in top_drivers:
        hl = (d.get('headline', '') or '').lower()
        region = (d.get('region', '') or '').lower()
        if any(k in hl for k in OIL_KEYWORDS) or 'middle east' in region:
            oil_d.append(d)
        if any(k in hl for k in GAS_KEYWORDS) or region in ('europe', 'black sea'):
            gas_d.append(d)

    results = []
    if oil_d:
        mx = max(d.get('severity', 0) for d in oil_d)
        if mx >= 4:
            results.append({
                'type': 'commodity_exposure', 'severity': 'critical' if mx >= 5 else 'warning',
                'title': f'Oil exposure at risk — {oil_d[0].get("region", "Unknown")}',
                'message': f'{len(oil_d)} oil-related driver{"s" if len(oil_d) > 1 else ""} (max severity {mx}/5). {oil_d[0].get("headline", "")[:80]}',
                'action': 'Review Brent/WTI positions. Consider protective puts or reducing directional exposure.',
            })
    if gas_d:
        mx = max(d.get('severity', 0) for d in gas_d)
        if mx >= 4:
            results.append({
                'type': 'commodity_exposure', 'severity': 'critical' if mx >= 5 else 'warning',
                'title': f'Gas exposure at risk — {gas_d[0].get("region", "Unknown")}',
                'message': f'{len(gas_d)} gas-related driver{"s" if len(gas_d) > 1 else ""} (max severity {mx}/5). {gas_d[0].get("headline", "")[:80]}',
                'action': 'Review TTF/LNG positions. Consider hedging European gas exposure.',
            })
    return results


def _naive(dt):
    if dt is None:
        return dt
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


def get_intraday_risk_windows() -> Dict[str, Any]:
    now_utc = datetime.utcnow()
    today_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)

    timeline_rows = execute_query("""
        SELECT value, band, alert_count, computed_at
        FROM geri_live WHERE computed_at >= %s ORDER BY computed_at ASC
    """, (today_start,)) or []

    alert_rows = execute_query("""
        SELECT id, severity, scope_region, headline, created_at
        FROM alert_events
        WHERE created_at >= %s
          AND alert_type IN ('HIGH_IMPACT_EVENT','REGIONAL_RISK_SPIKE','ASSET_RISK_SPIKE')
        ORDER BY created_at ASC
    """, (today_start,)) or []

    now_h = now_utc.hour
    sessions = []
    for sess in TRADING_SESSIONS:
        sh, eh = sess['start_hour'], sess['end_hour']
        wraps = sh >= eh

        if wraps:
            sess_start = today_start.replace(hour=sh) if now_h >= sh else (today_start - timedelta(days=1)).replace(hour=sh)
            sess_end = (today_start + timedelta(days=1)).replace(hour=eh) if now_h >= sh else today_start.replace(hour=eh)
        else:
            sess_start = today_start.replace(hour=sh)
            sess_end = today_start.replace(hour=eh)

        s_alerts = [a for a in alert_rows if sess_start <= _naive(a['created_at']) < sess_end]
        s_tl = [t for t in timeline_rows if sess_start <= _naive(t['computed_at']) < sess_end]
        vals = [t['value'] for t in s_tl]
        avg_v = round(sum(vals) / len(vals)) if vals else None
        gs, ge = (vals[0] if vals else None), (vals[-1] if vals else None)
        delta = (ge - gs) if gs is not None and ge is not None else None
        mx_sev = max((a['severity'] for a in s_alerts), default=0)

        is_active = False
        if wraps:
            is_active = now_h >= sh or now_h < eh
        else:
            is_active = sh <= now_h < eh

        risk_level = 'none'
        if avg_v is not None:
            if avg_v >= 61: risk_level = 'critical'
            elif avg_v >= 41: risk_level = 'high'
            elif avg_v >= 21: risk_level = 'moderate'
            else: risk_level = 'low'

        top_headline = None
        if s_alerts:
            top_alert = max(s_alerts, key=lambda a: a['severity'])
            top_headline = top_alert.get('headline', '')[:100]

        sessions.append({
            'name': sess['name'], 'start_hour': sh, 'end_hour': eh, 'color': sess['color'],
            'is_active': is_active, 'alert_count': len(s_alerts), 'max_severity': mx_sev,
            'geri_avg': avg_v, 'geri_start': gs, 'geri_end': ge, 'geri_delta': delta,
            'risk_level': risk_level,
            'direction': 'up' if delta and delta > 0 else ('down' if delta and delta < 0 else 'flat'),
            'top_headline': top_headline,
            'time_label': f"{sh:02d}:00\u2013{eh:02d}:00 UTC",
        })

    return {'sessions': sessions, 'current_utc': now_utc.strftime('%H:%M UTC')}


def _bisect_timeline(timeline_times, target_time):
    lo, hi = 0, len(timeline_times) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if timeline_times[mid] < target_time:
            lo = mid + 1
        else:
            hi = mid - 1
    return lo


def get_flash_headline_feed() -> Dict[str, Any]:
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    rows = execute_query("""
        SELECT id, alert_type, severity, scope_region, scope_assets,
               headline, category, created_at
        FROM alert_events
        WHERE created_at >= %s
          AND alert_type IN ('HIGH_IMPACT_EVENT','REGIONAL_RISK_SPIKE','ASSET_RISK_SPIKE')
          AND severity >= 4
        ORDER BY created_at DESC LIMIT 20
    """, (today_start,)) or []

    timeline = execute_query("""
        SELECT value, computed_at FROM geri_live
        WHERE computed_at >= %s ORDER BY computed_at ASC
    """, (today_start,)) or []

    tl_times = [t['computed_at'] for t in timeline]
    tl_vals = [t['value'] for t in timeline]

    feed = []
    for row in rows:
        alert_time = row['created_at']
        geri_before, geri_after = None, None
        if timeline:
            idx = _bisect_timeline(tl_times, alert_time)
            if idx < len(timeline):
                geri_after = tl_vals[idx]
                geri_before = tl_vals[idx - 1] if idx > 0 else tl_vals[0]
            else:
                geri_after = tl_vals[-1]
                geri_before = tl_vals[-2] if len(tl_vals) > 1 else tl_vals[-1]

        impact = None
        if geri_before is not None and geri_after is not None:
            d = geri_after - geri_before
            impact = {
                'delta': d,
                'direction': 'up' if d > 0 else ('down' if d < 0 else 'neutral'),
                'label': f"+{d}" if d > 0 else (str(d) if d != 0 else "\u2014"),
            }

        sev_labels = {5: 'CRITICAL', 4: 'HIGH', 3: 'MEDIUM', 2: 'LOW', 1: 'MINIMAL'}
        time_str = alert_time.strftime('%H:%M') if hasattr(alert_time, 'strftime') else str(alert_time)[-8:-3]

        assets_affected = []
        headline_lower = (row['headline'] or '').lower()
        if any(k in headline_lower for k in OIL_KEYWORDS): assets_affected.append('Oil')
        if any(k in headline_lower for k in GAS_KEYWORDS): assets_affected.append('Gas')
        if any(k in headline_lower for k in FREIGHT_KEYWORDS): assets_affected.append('Freight')

        feed.append({
            'id': row['id'], 'headline': row['headline'], 'severity': row['severity'],
            'severity_label': sev_labels.get(row['severity'], 'UNKNOWN'),
            'region': row['scope_region'] or 'Global',
            'category': (row['category'] or 'unknown').replace('_', ' ').title(),
            'time': time_str, 'impact': impact,
            'alert_type': row['alert_type'],
            'assets_affected': assets_affected,
        })

    return {
        'feed': feed,
        'total_high_severity': len(feed),
        'as_of': datetime.utcnow().strftime('%H:%M UTC'),
    }


def get_full_trader_intelligence(geri_value: int = 0, geri_band: str = 'LOW',
                                 velocity: Optional[Dict] = None,
                                 band_proximity: Optional[Dict] = None,
                                 top_drivers: Optional[List] = None) -> Dict[str, Any]:
    return {
        'price_risk_correlation': get_price_risk_correlation(),
        'trading_risk_heatmap': get_trading_risk_heatmap(),
        'position_risk_alerts': get_position_risk_alerts(
            geri_value=geri_value, geri_band=geri_band,
            velocity=velocity, band_proximity=band_proximity,
            top_drivers=top_drivers,
        ),
        'intraday_risk_windows': get_intraday_risk_windows(),
        'flash_headline_feed': get_flash_headline_feed(),
    }
