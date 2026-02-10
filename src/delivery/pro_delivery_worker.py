"""
Index & Digest Delivery Worker

Delivers GERI, EERI, Market Snapshot, and Daily AI Digest to ALL user plans via Email and Telegram.
Each plan tier receives content matching their dashboard features:

- Free: 24h delayed GERI (value + band + direction), basic EERI, executive snapshot
- Personal: Real-time GERI + 7d trends, EERI with drivers, multi-index digest
- Trader: Full GERI + regime + momentum, EERI + components, probability scoring
- Pro: GERI decomposition + AI narrative, EERI + contagion, scenario forecasts
- Enterprise: Full institutional package, multi-region spillover, strategic interpretation
"""

import os
import json
import logging
from datetime import datetime, timezone, timedelta, date
from typing import List, Dict, Optional, Tuple
from collections import defaultdict

from src.db.db import get_cursor, execute_one, execute_query
from src.alerts.channel_adapters import send_email_v2, send_telegram_v2

logger = logging.getLogger(__name__)

PLAN_TIERS = ['free', 'personal', 'trader', 'pro', 'enterprise']
PLAN_LEVELS = {"free": 0, "personal": 1, "trader": 2, "pro": 3, "enterprise": 4}
PLAN_LABELS = {
    "free": "Awareness",
    "personal": "Monitoring",
    "trader": "Decision Support",
    "pro": "Institutional Analytics",
    "enterprise": "Institutional Workspace"
}


def get_all_users_with_plans() -> List[Dict]:
    with get_cursor(commit=False) as cursor:
        cursor.execute("""
            SELECT u.id, u.email, u.telegram_chat_id,
                   COALESCE(up.plan, 'free') as plan
            FROM users u
            LEFT JOIN user_plans up ON u.id = up.user_id
            WHERE u.email_verified = true
        """)
        return [dict(row) for row in cursor.fetchall()]


def get_latest_geri(delayed: bool = False) -> Optional[Dict]:
    if delayed:
        sql = """
            SELECT date, value, band, trend_1d, trend_7d, components, interpretation, computed_at
            FROM intel_indices_daily
            WHERE index_id = 'global:geo_energy_risk'
              AND date < CURRENT_DATE
            ORDER BY date DESC
            LIMIT 1
        """
    else:
        sql = """
            SELECT date, value, band, trend_1d, trend_7d, components, interpretation, computed_at
            FROM intel_indices_daily
            WHERE index_id = 'global:geo_energy_risk'
            ORDER BY date DESC
            LIMIT 1
        """
    row = execute_one(sql)
    if row:
        result = dict(row)
        if result.get('components') and isinstance(result['components'], str):
            result['components'] = json.loads(result['components'])
        return result
    return None


def get_geri_history(days: int = 7) -> List[Dict]:
    rows = execute_query("""
        SELECT date, value, band, trend_1d
        FROM intel_indices_daily
        WHERE index_id = 'global:geo_energy_risk'
        ORDER BY date DESC
        LIMIT %s
    """, (days,))
    return [dict(r) for r in rows] if rows else []


def get_latest_eeri() -> Optional[Dict]:
    row = execute_one("""
        SELECT date, value, band, trend_1d, trend_7d, components, drivers, interpretation, computed_at
        FROM reri_indices_daily
        WHERE index_id = 'europe:eeri'
        ORDER BY date DESC
        LIMIT 1
    """)
    if row:
        result = dict(row)
        if result.get('components') and isinstance(result['components'], str):
            result['components'] = json.loads(result['components'])
        if result.get('drivers') and isinstance(result['drivers'], str):
            result['drivers'] = json.loads(result['drivers'])
        return result
    return None


def get_asset_snapshots() -> Dict:
    result = {}
    brent = execute_one("SELECT date, brent_price, brent_change_pct FROM oil_price_snapshots ORDER BY date DESC LIMIT 1")
    if brent:
        result['brent'] = dict(brent)
    ttf = execute_one("SELECT date, ttf_price FROM ttf_gas_snapshots ORDER BY date DESC LIMIT 1")
    if ttf:
        result['ttf'] = dict(ttf)
    storage = execute_one("SELECT date, eu_storage_percent, risk_band FROM gas_storage_snapshots ORDER BY date DESC LIMIT 1")
    if storage:
        result['storage'] = dict(storage)
    return result


def get_risk_tone(geri_value: int, trend_1d: int) -> str:
    if geri_value >= 70:
        return "Escalating"
    elif geri_value >= 50:
        return "Elevated & Rising" if trend_1d and trend_1d > 0 else "Elevated"
    elif geri_value >= 30:
        return "Moderate"
    else:
        return "Stabilizing" if trend_1d and trend_1d < 0 else "Low"


def get_band_color(band: str) -> str:
    colors = {
        'LOW': '#22c55e',
        'MODERATE': '#f59e0b',
        'ELEVATED': '#f97316',
        'SEVERE': '#ef4444',
        'CRITICAL': '#dc2626',
    }
    return colors.get(band, '#64748b')


def trend_arrow(val) -> str:
    if val is None:
        return ""
    if val > 0:
        return f"+{val}"
    return str(val)


def build_geri_section_email(geri: Dict, plan: str) -> str:
    level = PLAN_LEVELS.get(plan, 0)
    value = geri.get('value', 0)
    band = geri.get('band', 'N/A')
    trend_1d = geri.get('trend_1d')
    trend_7d = geri.get('trend_7d')
    geri_date = geri.get('date', '')
    band_color = get_band_color(band)
    components = geri.get('components', {}) or {}
    interpretation = geri.get('interpretation') or components.get('interpretation', '')

    html = f"""
    <div style="background:#1e293b;border-radius:12px;padding:24px;margin-bottom:20px;border-left:4px solid {band_color};">
        <h2 style="color:#e2e8f0;margin:0 0 16px 0;font-size:20px;">Global Energy Risk Index (GERI)</h2>
        <div style="display:flex;align-items:baseline;gap:12px;margin-bottom:12px;">
            <span style="font-size:48px;font-weight:700;color:{band_color};">{value}</span>
            <span style="font-size:16px;color:#94a3b8;">/100</span>
            <span style="background:{band_color}20;color:{band_color};padding:4px 12px;border-radius:20px;font-size:13px;font-weight:600;">{band}</span>
        </div>
        <div style="color:#94a3b8;font-size:13px;margin-bottom:12px;">Date: {geri_date}</div>
    """

    if level >= 1 and trend_1d is not None:
        t1_color = '#ef4444' if trend_1d > 0 else '#22c55e' if trend_1d < 0 else '#94a3b8'
        html += f'<div style="margin-bottom:4px;"><span style="color:#94a3b8;">24h Change:</span> <span style="color:{t1_color};font-weight:600;">{trend_arrow(trend_1d)}</span></div>'

    if level >= 1 and trend_7d is not None:
        t7_color = '#ef4444' if trend_7d > 0 else '#22c55e' if trend_7d < 0 else '#94a3b8'
        html += f'<div style="margin-bottom:8px;"><span style="color:#94a3b8;">7-Day Change:</span> <span style="color:{t7_color};font-weight:600;">{trend_arrow(trend_7d)}</span></div>'

    if level == 0:
        html += '<div style="color:#64748b;font-size:12px;margin-top:8px;">24h delayed data (Free plan)</div>'

    if level >= 1 and components.get('top_regions'):
        html += '<div style="margin-top:12px;"><span style="color:#94a3b8;font-size:13px;font-weight:600;">Top Regions Under Pressure:</span>'
        for region_data in components.get('top_regions', [])[:3]:
            region_name = region_data.get('region', 'Unknown') if isinstance(region_data, dict) else str(region_data)
            html += f'<div style="color:#cbd5e1;font-size:13px;padding-left:8px;">- {region_name}</div>'
        html += '</div>'

    if level >= 2:
        risk_tone = get_risk_tone(value, trend_1d)
        html += f'<div style="margin-top:12px;"><span style="color:#94a3b8;font-size:13px;">Risk Tone:</span> <span style="color:#e2e8f0;font-weight:600;">{risk_tone}</span></div>'

    if level >= 2 and components:
        drivers_html = ""
        for key in ['high_impact_score', 'regional_spike_score', 'asset_risk_score']:
            val = components.get(key)
            if val is not None:
                label = key.replace('_', ' ').title()
                drivers_html += f'<div style="color:#cbd5e1;font-size:12px;padding-left:8px;">{label}: {val}</div>'
        if drivers_html:
            html += f'<div style="margin-top:12px;"><span style="color:#94a3b8;font-size:13px;font-weight:600;">Component Scores:</span>{drivers_html}</div>'

    if interpretation and level >= 1:
        max_len = 200 if level <= 1 else 500 if level <= 2 else 0
        display_text = interpretation[:max_len] + "..." if max_len and len(interpretation) > max_len else interpretation
        html += f'<div style="margin-top:16px;padding:12px;background:#0f172a;border-radius:8px;"><span style="color:#94a3b8;font-size:12px;font-weight:600;">AI Analysis</span><p style="color:#cbd5e1;font-size:13px;line-height:1.6;margin:8px 0 0 0;">{display_text}</p></div>'

    html += '</div>'
    return html


def build_eeri_section_email(eeri: Dict, plan: str) -> str:
    level = PLAN_LEVELS.get(plan, 0)
    value = eeri.get('value', 0)
    band = eeri.get('band', 'N/A')
    trend_1d = eeri.get('trend_1d')
    trend_7d = eeri.get('trend_7d')
    eeri_date = eeri.get('date', '')
    band_color = get_band_color(band)
    components = eeri.get('components', {}) or {}
    drivers = eeri.get('drivers', []) or []
    interpretation = eeri.get('interpretation') or ''

    if isinstance(drivers, str):
        try:
            drivers = json.loads(drivers)
        except Exception:
            drivers = []

    html = f"""
    <div style="background:#1e293b;border-radius:12px;padding:24px;margin-bottom:20px;border-left:4px solid {band_color};">
        <h2 style="color:#e2e8f0;margin:0 0 16px 0;font-size:20px;">Europe Escalation Risk Index (EERI)</h2>
        <div style="display:flex;align-items:baseline;gap:12px;margin-bottom:12px;">
            <span style="font-size:48px;font-weight:700;color:{band_color};">{value}</span>
            <span style="font-size:16px;color:#94a3b8;">/100</span>
            <span style="background:{band_color}20;color:{band_color};padding:4px 12px;border-radius:20px;font-size:13px;font-weight:600;">{band}</span>
        </div>
        <div style="color:#94a3b8;font-size:13px;margin-bottom:12px;">Date: {eeri_date}</div>
    """

    if level >= 1 and trend_1d is not None:
        t1_color = '#ef4444' if trend_1d > 0 else '#22c55e' if trend_1d < 0 else '#94a3b8'
        html += f'<div style="margin-bottom:4px;"><span style="color:#94a3b8;">24h Change:</span> <span style="color:{t1_color};font-weight:600;">{trend_arrow(trend_1d)}</span></div>'

    if level >= 1 and trend_7d is not None:
        t7_color = '#ef4444' if trend_7d > 0 else '#22c55e' if trend_7d < 0 else '#94a3b8'
        html += f'<div style="margin-bottom:8px;"><span style="color:#94a3b8;">7-Day Change:</span> <span style="color:{t7_color};font-weight:600;">{trend_arrow(trend_7d)}</span></div>'

    if level >= 1 and drivers:
        html += '<div style="margin-top:12px;"><span style="color:#94a3b8;font-size:13px;font-weight:600;">Top Risk Drivers:</span>'
        driver_limit = 2 if level == 1 else 3 if level == 2 else 5
        for d in drivers[:driver_limit]:
            if isinstance(d, dict):
                headline = d.get('headline', d.get('title', str(d)))
                severity = d.get('severity', '')
                sev_str = f' [{severity}/5]' if severity else ''
                html += f'<div style="color:#cbd5e1;font-size:13px;padding-left:8px;">- {headline}{sev_str}</div>'
            else:
                html += f'<div style="color:#cbd5e1;font-size:13px;padding-left:8px;">- {d}</div>'
        html += '</div>'

    if level >= 2 and components:
        comp_html = ""
        reri_eu = components.get('reri_eu', {})
        if isinstance(reri_eu, dict) and reri_eu.get('value') is not None:
            comp_html += f'<div style="color:#cbd5e1;font-size:12px;padding-left:8px;">RERI-EU: {reri_eu["value"]}</div>'
        theme = components.get('theme_pressure', {})
        if isinstance(theme, dict) and theme.get('normalized') is not None:
            comp_html += f'<div style="color:#cbd5e1;font-size:12px;padding-left:8px;">Theme Pressure: {theme["normalized"]}</div>'
        asset_t = components.get('asset_transmission', {})
        if isinstance(asset_t, dict) and asset_t.get('normalized') is not None:
            comp_html += f'<div style="color:#cbd5e1;font-size:12px;padding-left:8px;">Asset Transmission: {asset_t["normalized"]}</div>'
        if comp_html:
            html += f'<div style="margin-top:12px;"><span style="color:#94a3b8;font-size:13px;font-weight:600;">Components:</span>{comp_html}</div>'

    if interpretation and level >= 1:
        max_len = 200 if level <= 1 else 500 if level <= 2 else 0
        display_text = interpretation[:max_len] + "..." if max_len and len(interpretation) > max_len else interpretation
        html += f'<div style="margin-top:16px;padding:12px;background:#0f172a;border-radius:8px;"><span style="color:#94a3b8;font-size:12px;font-weight:600;">AI Analysis</span><p style="color:#cbd5e1;font-size:13px;line-height:1.6;margin:8px 0 0 0;">{display_text}</p></div>'

    html += '</div>'
    return html


def build_assets_section_email(assets: Dict, plan: str) -> str:
    level = PLAN_LEVELS.get(plan, 0)
    if not assets:
        return ''

    html = '<div style="background:#1e293b;border-radius:12px;padding:24px;margin-bottom:20px;">'
    html += '<h2 style="color:#e2e8f0;margin:0 0 16px 0;font-size:20px;">Market Snapshot</h2>'
    html += '<table style="width:100%;border-collapse:collapse;">'

    if assets.get('brent'):
        b = assets['brent']
        price = b.get('brent_price', 0)
        change = b.get('brent_change_pct', 0)
        c_color = '#ef4444' if change and float(change) > 0 else '#22c55e' if change and float(change) < 0 else '#94a3b8'
        change_str = f"{float(change):+.2f}%" if change else ""
        html += f'<tr><td style="color:#94a3b8;padding:6px 0;font-size:13px;">Brent Crude</td><td style="color:#e2e8f0;text-align:right;font-weight:600;padding:6px 0;">${price}</td><td style="color:{c_color};text-align:right;font-size:12px;padding:6px 0;">{change_str}</td></tr>'

    if assets.get('ttf'):
        t = assets['ttf']
        html += f'<tr><td style="color:#94a3b8;padding:6px 0;font-size:13px;">TTF Gas</td><td style="color:#e2e8f0;text-align:right;font-weight:600;padding:6px 0;">{t.get("ttf_price", 0)}</td><td style="color:#94a3b8;text-align:right;font-size:12px;padding:6px 0;"></td></tr>'

    if assets.get('storage') and level >= 1:
        s = assets['storage']
        storage_pct = s.get('eu_storage_percent', 0)
        risk = s.get('risk_band', '')
        html += f'<tr><td style="color:#94a3b8;padding:6px 0;font-size:13px;">EU Gas Storage</td><td style="color:#e2e8f0;text-align:right;font-weight:600;padding:6px 0;">{storage_pct}%</td><td style="color:#94a3b8;text-align:right;font-size:12px;padding:6px 0;">{risk}</td></tr>'

    html += '</table></div>'
    return html


def build_full_email(geri: Optional[Dict], eeri: Optional[Dict],
                     assets: Dict, plan: str, ai_digest: Optional[str] = None) -> Tuple[str, str]:
    level = PLAN_LEVELS.get(plan, 0)
    plan_label = PLAN_LABELS.get(plan, plan.title())

    geri_val = geri.get('value', 0) if geri else 0
    geri_band = geri.get('band', 'N/A') if geri else 'N/A'
    subject = f"[EnergyRiskIQ] Daily Intelligence: GERI {geri_val}/100 ({geri_band})"

    geri_section = build_geri_section_email(geri, plan) if geri else ''
    eeri_section = build_eeri_section_email(eeri, plan) if eeri else ''
    assets_section = build_assets_section_email(assets, plan)

    digest_section = ''
    if ai_digest and level >= 0:
        digest_section = f"""
        <div style="background:#1e293b;border-radius:12px;padding:24px;margin-bottom:20px;">
            <h2 style="color:#e2e8f0;margin:0 0 16px 0;font-size:20px;">Daily Intelligence Digest</h2>
            <div style="color:#cbd5e1;font-size:14px;line-height:1.7;white-space:pre-wrap;">{ai_digest}</div>
        </div>
        """

    upgrade_section = ''
    if level < 4:
        next_plan = PLAN_TIERS[min(level + 1, 4)]
        next_label = PLAN_LABELS.get(next_plan, next_plan.title())
        upgrade_section = f"""
        <div style="background:linear-gradient(135deg, #1e3a5f, #1e293b);border-radius:12px;padding:20px;margin-bottom:20px;border:1px solid #334155;">
            <p style="color:#94a3b8;font-size:13px;margin:0;">Upgrade to <span style="color:#3b82f6;font-weight:600;">{next_label}</span> for deeper analysis and more features.</p>
            <a href="https://energyriskiq.com/users/account" style="color:#3b82f6;font-size:13px;text-decoration:none;">View plans &rarr;</a>
        </div>
        """

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#0f172a;font-family:'Inter',-apple-system,BlinkMacSystemFont,sans-serif;">
<div style="max-width:640px;margin:0 auto;padding:20px;">
    <div style="text-align:center;padding:24px 0;margin-bottom:20px;">
        <h1 style="font-size:24px;font-weight:700;background:linear-gradient(135deg,#3b82f6,#8b5cf6);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;margin:0;">EnergyRiskIQ</h1>
        <p style="color:#64748b;font-size:13px;margin:8px 0 0 0;">Daily Energy Risk Intelligence | {plan_label}</p>
        <p style="color:#475569;font-size:12px;margin:4px 0 0 0;">{datetime.now(timezone.utc).strftime('%B %d, %Y')}</p>
    </div>

    {geri_section}
    {eeri_section}
    {assets_section}
    {digest_section}
    {upgrade_section}

    <div style="text-align:center;padding:24px 0;border-top:1px solid #334155;">
        <a href="https://energyriskiq.com/users/account" style="display:inline-block;background:linear-gradient(135deg,#3b82f6,#8b5cf6);color:#fff;padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:600;font-size:14px;">View Full Dashboard</a>
        <p style="color:#475569;font-size:11px;margin:16px 0 0 0;">EnergyRiskIQ - Energy Risk Intelligence<br>Informational only. Not financial advice.</p>
        <p style="color:#334155;font-size:11px;margin:8px 0 0 0;">
            <a href="https://energyriskiq.com/users/account" style="color:#475569;text-decoration:none;">Manage preferences</a>
        </p>
    </div>
</div>
</body>
</html>"""

    return subject, html


def build_geri_telegram(geri: Dict, plan: str) -> str:
    level = PLAN_LEVELS.get(plan, 0)
    value = geri.get('value', 0)
    band = geri.get('band', 'N/A')
    trend_1d = geri.get('trend_1d')
    trend_7d = geri.get('trend_7d')
    geri_date = geri.get('date', '')
    components = geri.get('components', {}) or {}
    interpretation = geri.get('interpretation') or components.get('interpretation', '')

    parts = []
    parts.append("*GERI Daily Update*")
    parts.append(f"Date: {geri_date}")
    parts.append(f"Value: *{value}/100* ({band})")

    if level >= 1 and trend_1d is not None:
        parts.append(f"24h: {trend_arrow(trend_1d)}")
    if level >= 1 and trend_7d is not None:
        parts.append(f"7d: {trend_arrow(trend_7d)}")

    if level == 0:
        parts.append("_(24h delayed - Free plan)_")

    if level >= 2:
        risk_tone = get_risk_tone(value, trend_1d)
        parts.append(f"Risk Tone: {risk_tone}")

    if level >= 1 and components.get('top_regions'):
        parts.append("")
        parts.append("Top Regions:")
        for r in components.get('top_regions', [])[:3]:
            name = r.get('region', str(r)) if isinstance(r, dict) else str(r)
            parts.append(f"  - {name}")

    if interpretation and level >= 1:
        max_len = 150 if level <= 1 else 300 if level <= 2 else 500
        text = interpretation[:max_len] + "..." if len(interpretation) > max_len else interpretation
        parts.append("")
        parts.append(f"_{text}_")

    return "\n".join(parts)


def build_eeri_telegram(eeri: Dict, plan: str) -> str:
    level = PLAN_LEVELS.get(plan, 0)
    value = eeri.get('value', 0)
    band = eeri.get('band', 'N/A')
    trend_1d = eeri.get('trend_1d')
    drivers = eeri.get('drivers', []) or []
    interpretation = eeri.get('interpretation') or ''

    if isinstance(drivers, str):
        try:
            drivers = json.loads(drivers)
        except Exception:
            drivers = []

    parts = []
    parts.append("*EERI Update*")
    parts.append(f"Value: *{value}/100* ({band})")

    if level >= 1 and trend_1d is not None:
        parts.append(f"24h: {trend_arrow(trend_1d)}")

    if level >= 1 and drivers:
        driver_limit = 2 if level == 1 else 3
        parts.append("")
        parts.append("Drivers:")
        for d in drivers[:driver_limit]:
            if isinstance(d, dict):
                parts.append(f"  - {d.get('headline', d.get('title', str(d)))}")
            else:
                parts.append(f"  - {d}")

    if interpretation and level >= 1:
        max_len = 150 if level <= 1 else 300
        text = interpretation[:max_len] + "..." if len(interpretation) > max_len else interpretation
        parts.append("")
        parts.append(f"_{text}_")

    return "\n".join(parts)


def build_full_telegram(geri: Optional[Dict], eeri: Optional[Dict],
                        plan: str, ai_digest: Optional[str] = None) -> str:
    plan_label = PLAN_LABELS.get(plan, plan.title())
    parts = []
    parts.append(f"*EnergyRiskIQ Daily Intelligence*")
    parts.append(f"_{plan_label} | {datetime.now(timezone.utc).strftime('%b %d, %Y')}_")
    parts.append("")

    if geri:
        parts.append(build_geri_telegram(geri, plan))
        parts.append("")

    if eeri:
        parts.append(build_eeri_telegram(eeri, plan))
        parts.append("")

    if ai_digest:
        level = PLAN_LEVELS.get(plan, 0)
        max_len = 300 if level <= 1 else 600 if level <= 2 else 1000
        digest_text = ai_digest[:max_len] + "..." if len(ai_digest) > max_len else ai_digest
        parts.append("*Daily Digest*")
        parts.append(digest_text)
        parts.append("")

    parts.append("[View Dashboard](https://energyriskiq.com/users/account)")
    parts.append("_Informational only. Not financial advice._")

    return "\n".join(parts)


def generate_ai_digest_for_plan(plan: str, geri: Optional[Dict], eeri: Optional[Dict],
                                  assets: Dict) -> Optional[str]:
    try:
        import os
        from openai import OpenAI
        ai_api_key = os.environ.get('AI_INTEGRATIONS_OPENAI_API_KEY')
        ai_base_url = os.environ.get('AI_INTEGRATIONS_OPENAI_BASE_URL')
        if ai_api_key and ai_base_url:
            client = OpenAI(api_key=ai_api_key, base_url=ai_base_url)
        else:
            client = OpenAI()

        level = PLAN_LEVELS.get(plan, 0)

        geri_val = geri.get('value', 0) if geri else 0
        geri_band = geri.get('band', 'N/A') if geri else 'N/A'
        geri_trend = geri.get('trend_1d', 0) if geri else 0
        eeri_val = eeri.get('value', 0) if eeri else 0
        eeri_trend = eeri.get('trend_1d', 0) if eeri else 0

        risk_tone = get_risk_tone(geri_val, geri_trend)

        asset_text = ""
        if assets.get('brent'):
            b = assets['brent']
            asset_text += f"Brent Crude: ${b.get('brent_price', 0)} ({b.get('brent_change_pct', 0):+.2f}%)\n" if b.get('brent_change_pct') else f"Brent Crude: ${b.get('brent_price', 0)}\n"
        if assets.get('ttf'):
            asset_text += f"TTF Gas: {assets['ttf'].get('ttf_price', 0)}\n"
        if assets.get('storage'):
            asset_text += f"EU Gas Storage: {assets['storage'].get('eu_storage_percent', 0)}%\n"

        if level == 0:
            section_instructions = """OUTPUT (FREE PLAN - keep brief, max 200 words):
1) EXECUTIVE RISK SNAPSHOT: Global risk tone, 2 key drivers, 1 interpretation paragraph
2) GERI DIRECTION: Current value, direction
3) SHORT WATCHLIST: 1-2 forward signals"""
        elif level == 1:
            section_instructions = """OUTPUT (PERSONAL PLAN - max 400 words):
1) EXECUTIVE RISK SNAPSHOT: Global risk tone, 3 key drivers, interpretation
2) INDEX MOVEMENT SUMMARY: GERI + EERI with interpretations
3) ASSET IMPACT: Directional impacts on key commodities
4) 7-DAY RISK TREND"""
        elif level == 2:
            section_instructions = """OUTPUT (TRADER PLAN - max 600 words):
1) EXECUTIVE RISK SNAPSHOT with risk tone analysis
2) INDEX MOVEMENT SUMMARY: GERI + EERI with WHY each moved
3) CROSS-ASSET IMPACT: Each asset with directional impact + magnitude
4) PROBABILITY-BASED OUTLOOK: Spike/breakout probabilities
5) FORWARD WATCHLIST with probability and confidence"""
        elif level == 3:
            section_instructions = """OUTPUT (PRO PLAN - max 800 words):
1) EXECUTIVE RISK SNAPSHOT with regime classification
2) INDEX DECOMPOSITION: GERI component drivers
3) CROSS-ASSET SENSITIVITY TABLE
4) REGIME CLASSIFICATION + shift detection
5) SCENARIO OUTLOOK: Base case, Escalation, De-escalation
6) FORWARD WATCHLIST with triggers"""
        else:
            section_instructions = """OUTPUT (ENTERPRISE PLAN - max 1000 words):
1) EXECUTIVE RISK SNAPSHOT with regime + contagion status
2) FULL INDEX DECOMPOSITION with component attribution
3) MULTI-REGION SPILLOVER ANALYSIS
4) CROSS-ASSET SENSITIVITY DASHBOARD
5) REGIME CLASSIFICATION + transition probability
6) SECTOR IMPACT FORECAST: Power, Industrial, LNG, Storage
7) SCENARIO FORECASTS: 3 scenarios with portfolio implications
8) STRATEGIC INTERPRETATION: Analyst Note"""

        system_prompt = """You are EnergyRiskIQ Intelligence Engine.
Interpret today's risk indices and real market data.
Be concise, trader-oriented, quantify relationships when data is provided.
Separate: Facts / Interpretation / Watchlist.
Professional, analytical tone. No promotional language.
Use clear section headers. Use bullet points for lists.
End with: "Informational only. Not financial advice."
"""

        user_prompt = f"""DATE: {date.today().isoformat()}
RISK TONE: {risk_tone}

INDEX SNAPSHOT:
GERI: {geri_val}/100 ({geri_band}, change: {geri_trend:+d})
EERI: {eeri_val}/100 (change: {eeri_trend:+d})

ASSET MOVES:
{asset_text}

{section_instructions}
"""

        max_tokens = 400 if level == 0 else 700 if level == 1 else 1000 if level == 2 else 1300
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.4,
            max_tokens=max_tokens
        )

        return response.choices[0].message.content

    except Exception as e:
        logger.error(f"AI digest generation failed for plan {plan}: {e}")
        return None


def ensure_index_digest_unique_index():
    try:
        with get_cursor(commit=True) as cursor:
            cursor.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_index_digest_delivery_unique
                ON user_alert_deliveries (user_id, channel, geri_date)
                WHERE delivery_kind = 'index_digest' AND geri_date IS NOT NULL
            """)
    except Exception as e:
        logger.warning(f"Could not create index_digest unique index (may already exist): {e}")


def record_index_delivery(user_id: int, channel: str, status: str,
                           delivery_kind: str = 'index_digest',
                           index_date: Optional[date] = None,
                           error: Optional[str] = None):
    with get_cursor(commit=True) as cursor:
        cursor.execute("""
            INSERT INTO user_alert_deliveries
                (user_id, channel, status, delivery_kind,
                 created_at, sent_at, geri_date, last_error)
            VALUES (%s, %s, %s, %s, NOW(), NOW(), %s, %s)
            ON CONFLICT (user_id, channel, geri_date)
                WHERE delivery_kind = 'index_digest' AND geri_date IS NOT NULL
            DO UPDATE SET status = EXCLUDED.status, sent_at = NOW(),
                         last_error = EXCLUDED.last_error
        """, (user_id, channel, status, delivery_kind, index_date, error))


def has_been_delivered_today(user_id: int, channel: str, index_date: date) -> bool:
    row = execute_one("""
        SELECT 1 FROM user_alert_deliveries
        WHERE user_id = %s
          AND channel = %s
          AND geri_date = %s
          AND delivery_kind IN ('index_digest', 'geri')
          AND status = 'sent'
        LIMIT 1
    """, (user_id, channel, index_date))
    return row is not None


def run_index_delivery() -> Dict:
    logger.info("Starting Index & Digest delivery for all plans")

    ensure_index_digest_unique_index()

    stats = {
        "users_processed": 0,
        "emails_sent": 0,
        "emails_skipped": 0,
        "telegrams_sent": 0,
        "telegrams_skipped": 0,
        "errors": [],
        "plans": defaultdict(int),
    }

    users = get_all_users_with_plans()
    if not users:
        logger.info("No verified users found")
        return dict(stats)

    logger.info(f"Found {len(users)} verified users")

    geri_realtime = get_latest_geri(delayed=False)
    geri_delayed = get_latest_geri(delayed=True)
    eeri = get_latest_eeri()
    assets = get_asset_snapshots()

    if not geri_realtime:
        logger.warning("No GERI data available, skipping delivery")
        return dict(stats)

    geri_date = geri_realtime.get('date')
    if not geri_date:
        logger.warning("GERI missing date field")
        return dict(stats)

    digest_cache = {}

    for user in users:
        user_id = user['id']
        email = user['email']
        chat_id = user.get('telegram_chat_id')
        plan = user.get('plan', 'free')
        level = PLAN_LEVELS.get(plan, 0)

        stats["plans"][plan] = stats["plans"].get(plan, 0) + 1

        geri = (geri_delayed or geri_realtime) if level == 0 else geri_realtime
        effective_date = geri.get('date') if geri else geri_date

        try:
            if plan not in digest_cache:
                digest_cache[plan] = generate_ai_digest_for_plan(plan, geri, eeri, assets)
            ai_digest = digest_cache[plan]

            if email and not has_been_delivered_today(user_id, 'email', effective_date):
                subject, html_body = build_full_email(geri, eeri, assets, plan, ai_digest)
                result = send_email_v2(email, subject, html_body)

                if result.success:
                    stats["emails_sent"] += 1
                    record_index_delivery(user_id, 'email', 'sent', index_date=effective_date)
                elif result.should_skip:
                    stats["emails_skipped"] += 1
                    record_index_delivery(user_id, 'email', 'skipped', index_date=effective_date, error=result.skip_reason)
                else:
                    stats["errors"].append(f"Email to {email}: {result.error}")
                    record_index_delivery(user_id, 'email', 'failed', index_date=effective_date, error=result.error)
            else:
                stats["emails_skipped"] += 1

            if chat_id and not has_been_delivered_today(user_id, 'telegram', effective_date):
                telegram_msg = build_full_telegram(geri, eeri, plan, ai_digest)
                result = send_telegram_v2(chat_id, telegram_msg)

                if result.success:
                    stats["telegrams_sent"] += 1
                    record_index_delivery(user_id, 'telegram', 'sent', index_date=effective_date)
                elif result.should_skip:
                    stats["telegrams_skipped"] += 1
                else:
                    stats["errors"].append(f"Telegram to {chat_id}: {result.error}")
                    record_index_delivery(user_id, 'telegram', 'failed', index_date=effective_date, error=result.error)
            else:
                stats["telegrams_skipped"] += 1

            stats["users_processed"] += 1

        except Exception as e:
            logger.error(f"Error processing user {user_id}: {e}")
            stats["errors"].append(f"User {user_id}: {str(e)}")

    stats["plans"] = dict(stats["plans"])
    logger.info(f"Index & Digest delivery complete: {stats}")
    return dict(stats)
