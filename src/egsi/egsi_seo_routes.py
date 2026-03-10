"""
EGSI SEO Routes

Public-facing SEO-optimized pages for the Europe Gas Stress Index (EGSI-M & EGSI-S).
Mounted at /egsi for search engine visibility.
"""
import os
from datetime import datetime, date
from calendar import month_name

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse

from src.egsi.egsi_history_service import (
    get_latest_egsi_m_public,
    get_egsi_m_delayed,
    get_egsi_m_by_date,
    get_all_egsi_m_dates,
    get_egsi_m_available_months,
    get_egsi_m_monthly_data,
    get_egsi_m_adjacent_dates,
    get_egsi_m_monthly_stats,
)
from src.egsi.repo import get_egsi_s_delayed
from src.egsi.interpretation import generate_egsi_interpretation
from src.api.seo_routes import get_digest_dark_styles, render_digest_footer

router = APIRouter(tags=["egsi-seo"])

BASE_URL = os.environ.get('ALERTS_APP_BASE_URL', 'https://energyriskiq.com')


def get_common_styles():
    """Return common CSS styles for EGSI pages - GERI standard template."""
    return """
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        :root {
            --primary: #0066FF;
            --primary-dark: #0052CC;
            --secondary: #1A1A2E;
            --accent: #00D4AA;
            --text-primary: #1A1A2E;
            --text-secondary: #64748B;
            --bg-white: #FFFFFF;
            --bg-light: #F8FAFC;
            --border: #E2E8F0;
        }
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            color: var(--text-primary);
            line-height: 1.6;
            background: var(--bg-light);
        }
        .container { max-width: 900px; margin: 0 auto; padding: 0 1rem; }
        
        .nav {
            background: var(--bg-white);
            border-bottom: 1px solid var(--border);
            padding: 1rem 0;
            position: sticky;
            top: 0;
            z-index: 100;
        }
        .nav-inner { display: flex; justify-content: space-between; align-items: center; }
        .logo { font-weight: 700; font-size: 1.25rem; color: var(--secondary); text-decoration: none; display: flex; align-items: center; gap: 0.5rem; }
        .nav-links { display: flex; gap: 1.5rem; align-items: center; }
        .nav-links a { color: var(--text-secondary); text-decoration: none; font-weight: 500; }
        .nav-links a:hover { color: var(--primary); }
        .nav-links .cta-nav { background: var(--primary); color: white !important; padding: 0.5rem 1rem; border-radius: 0.5rem; }
        
        .index-hero { text-align: center; padding: 2rem 0; }
        .index-hero h1 { font-size: 2rem; margin-bottom: 0.5rem; }
        .index-hero p { color: #9ca3af; max-width: 600px; margin: 0 auto; }
        .index-hero .methodology-link { margin-top: 0.75rem; }
        .index-hero .methodology-link a { color: #60a5fa; text-decoration: none; font-size: 0.95rem; }
        .index-hero .methodology-link a:hover { color: #93c5fd; text-decoration: underline; }
        
        .index-metric-card {
            background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
            border: 1px solid #334155;
            border-radius: 1rem;
            padding: 2rem;
            text-align: center;
            max-width: 420px;
            margin: 2rem auto;
        }
        .index-header { display: flex; align-items: center; justify-content: center; gap: 0.75rem; margin-bottom: 0.5rem; }
        .index-icon { font-size: 1.5rem; }
        .index-title { font-size: 1.25rem; font-weight: 600; color: #f8fafc; }
        .index-value { font-size: 1.5rem; font-weight: bold; margin: 0.5rem 0; }
        .index-scale-ref { font-size: 0.8rem; color: #9ca3af; margin-bottom: 0.75rem; }
        .index-trend { font-size: 0.95rem; margin-bottom: 0.5rem; color: #f8fafc; }
        .index-date { color: #6b7280; font-size: 0.875rem; margin-top: 1rem; }
        
        .index-sections {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 1.5rem;
            margin: 2rem 0;
        }
        .index-section {
            background: #1e293b;
            border: 1px solid #334155;
            border-radius: 0.75rem;
            padding: 1.5rem;
        }
        .index-section h2 { font-size: 1.125rem; margin-bottom: 1rem; color: #f8fafc; }
        .section-header-blue { color: #60a5fa !important; font-size: 1rem; margin-bottom: 0.75rem; }
        
        .index-list { list-style: disc; padding-left: 1.25rem; color: #d1d5db; }
        .index-list li { margin-bottom: 0.75rem; line-height: 1.4; }
        .driver-tag { color: #4ecdc4; font-size: 0.8rem; font-weight: 500; }
        .driver-headline { font-weight: 500; color: #d1d5db; }
        .region-label { color: #9ca3af; font-size: 0.85rem; }
        
        .card {
            background: white;
            border-radius: 12px;
            padding: 30px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.05);
        }
        .card h3 { color: var(--primary); margin-bottom: 15px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 30px; }
        
        .assets-grid { display: flex; flex-wrap: wrap; gap: 0.5rem; }
        .asset-tag { background: rgba(96, 165, 250, 0.2); color: #60a5fa; padding: 0.5rem 1rem; border-radius: 8px; font-size: 0.9rem; font-weight: 500; }
        
        .index-interpretation { 
            color: #1f2937; 
            font-size: 1.05rem; 
            margin: 1.5rem 0 2rem 0; 
            line-height: 1.7; 
            background: rgba(96, 165, 250, 0.05);
            border-left: 3px solid #3b82f6;
            padding: 1.5rem;
            border-radius: 0 8px 8px 0;
        }
        .index-interpretation p { margin: 0 0 1rem 0; }
        .index-interpretation p:last-child { margin-bottom: 0; }
        
        .index-delay-badge {
            background: linear-gradient(135deg, #1e3a5f 0%, #0f172a 100%);
            border: 1px solid #3b82f6;
            border-radius: 2rem;
            padding: 0.5rem 1.5rem;
            text-align: center;
            color: #60a5fa;
            font-size: 0.9rem;
            margin-top: 1rem;
            display: inline-block;
        }
        
        .index-cta {
            background: linear-gradient(135deg, #1e3a5f 0%, #0f172a 100%);
            border: 1px solid #3b82f6;
            border-radius: 1rem;
            padding: 2rem;
            text-align: center;
            margin: 2rem 0;
        }
        .index-cta h3 { color: #60a5fa; margin-bottom: 0.5rem; }
        .index-cta p { color: #9ca3af; margin-bottom: 1.5rem; }
        .cta-button { display: inline-block; padding: 0.75rem 1.5rem; border-radius: 0.5rem; font-weight: 600; text-decoration: none; margin: 0.25rem; }
        .cta-button.primary { background: #3b82f6; color: white; }
        .cta-button.secondary { background: transparent; border: 1px solid #6b7280; color: #d1d5db; }
        
        .index-links { text-align: center; margin: 2rem 0; }
        .index-links a { color: #60a5fa; margin: 0 1rem; text-decoration: none; }
        .index-links a:hover { text-decoration: underline; }
        
        .footer { text-align: center; padding: 2rem 0; color: var(--text-secondary); font-size: 0.85rem; }
        .footer a { color: var(--primary); text-decoration: none; }
        
        .breadcrumb { padding: 15px 0; font-size: 0.9rem; color: var(--text-secondary); }
        .breadcrumb a { color: var(--primary); text-decoration: none; }
        
        table { width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; margin: 1rem 0; }
        th, td { padding: 12px 16px; text-align: left; border-bottom: 1px solid var(--border); }
        th { background: var(--bg-light); font-weight: 600; }
        
        @media (max-width: 640px) {
            .index-hero h1 { font-size: 1.5rem; }
            .index-value { font-size: 1.25rem; }
        }
    </style>
    """


def get_band_color(band: str) -> str:
    """Get CSS color for risk band."""
    colors = {
        'LOW': '#22c55e',
        'NORMAL': '#3b82f6',
        'ELEVATED': '#f97316',
        'HIGH': '#ef4444',
        'CRITICAL': '#dc2626',
    }
    return colors.get(band, '#6b7280')


def format_trend(trend_7d) -> tuple:
    """Format trend value for display. Returns (label, sign, color)."""
    if trend_7d is None:
        return ('N/A', '', '#6b7280')
    if abs(trend_7d) < 2:
        return ('Stable', '', '#6b7280')
    elif trend_7d >= 5:
        return ('Rising Sharply', '+', '#ef4444')
    elif trend_7d >= 2:
        return ('Rising', '+', '#f97316')
    elif trend_7d <= -5:
        return ('Falling Sharply', '', '#22c55e')
    else:
        return ('Falling', '', '#4ade80')


@router.get("/egsi", response_class=HTMLResponse)
async def egsi_public_page(request: Request):
    """
    EGSI Main Public Page - SEO anchor page for Europe Gas Stress Index.
    Shows 24h delayed EGSI-M and EGSI-S with charts.
    """
    egsi_m = get_egsi_m_delayed(delay_hours=24)
    if not egsi_m:
        egsi_m = get_latest_egsi_m_public()

    egsi_s = get_egsi_s_delayed(delay_days=1)

    if not egsi_m and not egsi_s:
        no_data_html = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Europe Gas Stress Index (EGSI) | EnergyRiskIQ</title>
            <meta name="description" content="Track Europe's gas market stress levels with EGSI. Monitor supply disruptions, pipeline issues, and infrastructure chokepoints.">
            <link rel="canonical" href="{BASE_URL}/egsi">
            <link rel="icon" type="image/png" href="/static/favicon.png">
            {get_digest_dark_styles()}
        </head>
        <body>
            <nav class="nav"><div class="nav-inner">
                <a href="/" class="logo"><img src="/static/logo.png" alt="EnergyRiskIQ" width="36" height="36" style="margin-right: 0.5rem;">EnergyRiskIQ</a>
                <button class="mobile-menu-btn" onclick="document.querySelector('.nav-links').classList.toggle('open')" aria-label="Menu">
                    <span></span><span></span><span></span>
                </button>
                <div class="nav-links">
                    <a href="/indices/global-energy-risk-index">GERI</a>
                    <a href="/indices/europe-energy-risk-index">EERI</a>
                    <a href="/egsi">EGSI</a>
                    <a href="/daily-geo-energy-intelligence-digest">Digest</a>
                    <a href="/daily-geo-energy-intelligence-digest/history">History</a>
                    <a href="/users" class="cta-btn-nav">Get FREE Access</a>
                </div>
            </div></nav>
            <main>
                <div class="container">
                    <div class="breadcrumbs"><a href="/">Home</a> / Europe Gas Stress Index</div>
                    <div style="text-align: center; padding: 2rem 0;">
                        <h1 style="font-size: 1.75rem; color: #f1f5f9; margin-bottom: 0.5rem;">Europe Gas Stress Index (EGSI)</h1>
                        <p style="color: #94a3b8;">A daily composite measure of gas market stress across European infrastructure.</p>
                    </div>
                    <div style="background: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 2rem; text-align: center; max-width: 500px; margin: 2rem auto;">
                        <h2 style="color: #f1f5f9; font-size: 1.25rem; margin-bottom: 0.5rem;">EGSI Data Coming Soon</h2>
                        <p style="color: #94a3b8;">The Europe Gas Stress Index is being computed. Check back shortly.</p>
                    </div>
                </div>
            </main>
            {render_digest_footer()}
        </body>
        </html>
        """
        return HTMLResponse(content=no_data_html)

    # --- EGSI-M data ---
    m_value = egsi_m.get('value', 0) if egsi_m else None
    m_band = egsi_m.get('band', 'LOW') if egsi_m else None
    m_trend_7d = egsi_m.get('trend_7d') if egsi_m else None
    m_date_str = egsi_m.get('date', 'N/A') if egsi_m else 'N/A'
    m_drivers = egsi_m.get('drivers', [])[:5] if egsi_m else []
    m_components = egsi_m.get('components', {}) if egsi_m else {}
    m_interpretation = (egsi_m.get('explanation') or egsi_m.get('interpretation') or '') if egsi_m else ''
    if egsi_m and not m_interpretation:
        m_interpretation = generate_egsi_interpretation(
            value=m_value, band=m_band, drivers=m_drivers,
            components=m_components, index_date=m_date_str, index_type="EGSI-M"
        )

    # --- EGSI-S data ---
    s_value = egsi_s.get('value', 0) if egsi_s else None
    s_band = egsi_s.get('band', 'LOW') if egsi_s else None
    s_trend_7d = egsi_s.get('trend_7d') if egsi_s else None
    s_date_str = egsi_s.get('date', 'N/A') if egsi_s else 'N/A'
    s_interpretation = (egsi_s.get('explanation') or '') if egsi_s else ''
    if egsi_s and not s_interpretation:
        s_components = egsi_s.get('components', {})
        s_interpretation = generate_egsi_interpretation(
            value=s_value, band=s_band, drivers=[],
            components=s_components, index_date=s_date_str, index_type="EGSI-S"
        )

    def _build_card(label, icon, value, band, trend_7d, date_str, computed_at, subtitle):
        if value is None:
            return f'''
            <div class="egsi-metric-card">
                <div class="egsi-card-header"><span>{icon}</span><span class="egsi-card-title">{label}</span></div>
                <p style="color: #94a3b8; margin: 1rem 0;">Data not yet available</p>
            </div>'''
        ca_str = str(computed_at)
        if len(ca_str) > 19:
            ca_str = ca_str[:19].replace('T', ', ') + ' UTC'
        bc = get_band_color(band)
        tl, ts, tc = format_trend(trend_7d)
        trend_html = ''
        if trend_7d is not None:
            sign = '+' if trend_7d > 0 else ''
            trend_html = f'<div class="egsi-trend" style="color: {tc};">7-Day Trend: {tl} ({sign}{trend_7d:.0f})</div>'
        return f'''
        <div class="egsi-metric-card">
            <div class="egsi-card-header"><span>{icon}</span><span class="egsi-card-title">{label}</span></div>
            <div class="egsi-card-subtitle">{subtitle}</div>
            <div class="egsi-card-value" style="color: {bc};">{value:.0f} / 100 ({band})</div>
            <div class="egsi-card-scale">0 = minimal stress · 100 = extreme stress</div>
            {trend_html}
            <div class="egsi-card-meta">
                <span>Index Date: <strong>{date_str}</strong></span>
                <span>Computed: <strong>{ca_str}</strong></span>
            </div>
            <div class="egsi-delay-badge">24h Delayed (Free Plan)</div>
        </div>'''

    m_card = _build_card(
        "EGSI-M · Market Stress", "⚡",
        m_value, m_band, m_trend_7d, m_date_str,
        egsi_m.get('computed_at', m_date_str) if egsi_m else 'N/A',
        "Transmission & infrastructure stress signals"
    )
    s_card = _build_card(
        "EGSI-S · System Stress", "🔋",
        s_value, s_band, s_trend_7d, s_date_str,
        egsi_s.get('computed_at', s_date_str) if egsi_s else 'N/A',
        "Storage, pricing & supply conditions"
    )

    # Drivers section (from EGSI-M)
    drivers_list_html = ""
    for driver in m_drivers:
        driver_name = driver.get('name', 'Unknown')
        driver_type = driver.get('type', 'N/A')
        contribution = driver.get('contribution', 0)
        drivers_list_html += f'<li><span class="driver-tag">{driver_type}</span> {driver_name} ({contribution:.1f}%)</li>'
    if not drivers_list_html:
        drivers_list_html = '<li>No significant drivers detected</li>'

    chokepoints = m_components.get('chokepoint_factor', {}).get('hits', []) if isinstance(m_components, dict) else []
    chokepoints_list_html = ""
    for cp in chokepoints[:5]:
        chokepoints_list_html += f'<li>{cp}</li>'
    if not chokepoints_list_html:
        chokepoints_list_html = '<li>No active chokepoint alerts</li>'

    # Interpretation
    interp_html = ""
    if m_interpretation:
        interp_html += f'<div class="egsi-interp-card"><div class="egsi-interp-header"><span>🧠</span><h3>EGSI-M Interpretation</h3></div><div class="egsi-interp-body"><p>{m_interpretation.replace(chr(10)+chr(10), "</p><p>")}</p></div></div>'
    if s_interpretation:
        interp_html += f'<div class="egsi-interp-card"><div class="egsi-interp-header"><span>📊</span><h3>EGSI-S Interpretation</h3></div><div class="egsi-interp-body"><p>{s_interpretation.replace(chr(10)+chr(10), "</p><p>")}</p></div></div>'

    meta_value = m_value if m_value is not None else (s_value or 0)
    meta_band = m_band or s_band or 'LOW'
    meta_interp = m_interpretation or s_interpretation or ''
    m_value_display = f"{m_value:.0f}" if m_value is not None else "N/A"
    m_band_display = m_band or 'N/A'

    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Europe Gas Stress Index (EGSI) - {meta_band} at {meta_value:.0f} | EnergyRiskIQ</title>
        <meta name="description" content="EGSI-M at {m_value_display} ({m_band_display}). Track European gas market and system stress.">
        <link rel="canonical" href="{BASE_URL}/egsi">
        <link rel="icon" type="image/png" href="/static/favicon.png">

        <meta property="og:title" content="Europe Gas Stress Index (EGSI) | EnergyRiskIQ">
        <meta property="og:description" content="EGSI at {meta_value:.0f} ({meta_band}). Track European gas market stress in real-time.">
        <meta property="og:type" content="website">
        <meta property="og:url" content="{BASE_URL}/egsi">

        <script type="application/ld+json">
        {{
            "@context": "https://schema.org",
            "@type": "Dataset",
            "name": "Europe Gas Stress Index (EGSI)",
            "description": "Daily index measuring gas market and system stress across European infrastructure",
            "url": "{BASE_URL}/egsi",
            "creator": {{"@type": "Organization", "name": "EnergyRiskIQ"}},
            "dateModified": "{m_date_str}"
        }}
        </script>

        {get_digest_dark_styles()}
        <style>
            .egsi-hero {{
                text-align: center;
                padding: 2rem 0 1rem 0;
            }}
            .egsi-hero h1 {{
                font-size: 1.75rem;
                margin-bottom: 0.5rem;
                color: #f1f5f9;
            }}
            .egsi-hero p {{
                color: #94a3b8;
                max-width: 600px;
                margin: 0 auto;
            }}
            .egsi-hero .methodology-link {{
                margin-top: 0.75rem;
            }}
            .egsi-hero .methodology-link a {{
                color: #60a5fa;
                text-decoration: none;
                font-size: 0.95rem;
            }}
            .egsi-hero .methodology-link a:hover {{
                color: #93c5fd;
                text-decoration: underline;
            }}
            .egsi-cards-row {{
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 1.5rem;
                margin: 1.5rem 0;
            }}
            .egsi-metric-card {{
                background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
                border: 1px solid #334155;
                border-radius: 12px;
                padding: 1.5rem;
                text-align: center;
            }}
            .egsi-card-header {{
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 0.5rem;
                margin-bottom: 0.25rem;
                font-size: 1.1rem;
            }}
            .egsi-card-title {{
                font-size: 1rem;
                font-weight: 600;
                color: #f1f5f9;
            }}
            .egsi-card-subtitle {{
                font-size: 0.8rem;
                color: #94a3b8;
                margin-bottom: 0.75rem;
            }}
            .egsi-card-value {{
                font-size: 2rem;
                font-weight: 700;
                margin: 0.5rem 0;
            }}
            .egsi-card-scale {{
                font-size: 0.75rem;
                color: #64748b;
                margin-bottom: 0.5rem;
            }}
            .egsi-trend {{
                font-size: 0.9rem;
                font-weight: 500;
                margin-bottom: 0.5rem;
            }}
            .egsi-card-meta {{
                display: flex;
                flex-direction: column;
                gap: 0.2rem;
                font-size: 0.8rem;
                color: #64748b;
                margin-top: 0.75rem;
                padding-top: 0.75rem;
                border-top: 1px solid #334155;
            }}
            .egsi-card-meta strong {{
                color: #cbd5e1;
            }}
            .egsi-delay-badge {{
                display: inline-block;
                background: rgba(251, 191, 36, 0.15);
                border: 1px solid rgba(251, 191, 36, 0.3);
                color: #fbbf24;
                padding: 4px 12px;
                border-radius: 16px;
                font-size: 0.75rem;
                font-weight: 600;
                margin-top: 0.75rem;
            }}
            .egsi-sections {{
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 1.5rem;
                margin: 1.5rem 0;
            }}
            .egsi-section {{
                background: #1e293b;
                border: 1px solid #334155;
                border-radius: 12px;
                padding: 1.25rem;
            }}
            .egsi-section h2 {{
                font-size: 1rem;
                font-weight: 600;
                color: #60a5fa;
                margin-bottom: 0.75rem;
            }}
            .egsi-list {{
                list-style: disc;
                padding-left: 1.25rem;
                color: #d1d5db;
                margin: 0;
            }}
            .egsi-list li {{
                margin-bottom: 0.5rem;
                line-height: 1.4;
                font-size: 0.9rem;
                overflow-wrap: break-word;
            }}
            .driver-tag {{
                color: #4ecdc4;
                font-size: 0.75rem;
                font-weight: 600;
            }}
            .source-attribution {{
                font-size: 0.8rem;
                color: #64748b;
                margin-top: 0.75rem;
                font-style: italic;
            }}
            .source-attribution a {{
                color: #60a5fa;
                text-decoration: none;
            }}
            .source-attribution a:hover {{
                text-decoration: underline;
            }}
            .egsi-interp-card {{
                background: #1e293b;
                border: 1px solid #334155;
                border-radius: 12px;
                margin-bottom: 1.25rem;
                overflow: hidden;
            }}
            .egsi-interp-header {{
                display: flex;
                align-items: center;
                gap: 0.5rem;
                padding: 1rem 1.25rem;
                border-bottom: 1px solid #334155;
            }}
            .egsi-interp-header h3 {{
                font-size: 1rem;
                font-weight: 600;
                color: #f1f5f9;
                margin: 0;
            }}
            .egsi-interp-body {{
                padding: 1.25rem;
            }}
            .egsi-interp-body p {{
                color: #cbd5e1;
                font-size: 0.9rem;
                line-height: 1.6;
                margin: 0 0 0.75rem 0;
                overflow-wrap: break-word;
            }}
            .egsi-interp-body p:last-child {{
                margin-bottom: 0;
            }}
            .egsi-chart-section {{
                background: #1e293b;
                border: 1px solid #334155;
                border-radius: 12px;
                padding: 1.25rem;
                margin-bottom: 1.25rem;
            }}
            .egsi-chart-section h3 {{
                font-size: 1rem;
                font-weight: 600;
                color: #f1f5f9;
                margin-bottom: 1rem;
            }}
            .egsi-chart-row {{
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 1.25rem;
                margin-bottom: 1.25rem;
            }}
            .egsi-chart-box {{
                background: rgba(15, 23, 42, 0.5);
                border: 1px solid #334155;
                border-radius: 10px;
                padding: 1rem;
            }}
            .egsi-chart-box h4 {{
                font-size: 0.85rem;
                font-weight: 600;
                color: #94a3b8;
                margin-bottom: 0.75rem;
                text-align: center;
            }}
            .egsi-chart-box canvas {{
                width: 100% !important;
                max-height: 200px;
            }}
            .egsi-cta {{
                background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
                border: 1px solid rgba(59, 130, 246, 0.3);
                border-radius: 12px;
                padding: 1.5rem;
                text-align: center;
                margin: 1.25rem 0;
            }}
            .egsi-cta h3 {{
                color: #60a5fa;
                margin-bottom: 0.5rem;
                font-size: 1.1rem;
            }}
            .egsi-cta p {{
                color: #94a3b8;
                margin-bottom: 1rem;
                font-size: 0.9rem;
            }}
            .cta-button {{
                display: inline-block;
                padding: 0.6rem 1.25rem;
                border-radius: 6px;
                font-weight: 600;
                text-decoration: none;
                font-size: 0.9rem;
            }}
            .cta-button.primary {{
                background: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%);
                color: white;
            }}
            .cta-button.primary:hover {{
                opacity: 0.9;
            }}
            .egsi-links {{
                text-align: center;
                margin: 1.5rem 0;
                display: flex;
                justify-content: center;
                gap: 1.5rem;
                flex-wrap: wrap;
            }}
            .egsi-links a {{
                color: #60a5fa;
                text-decoration: none;
                font-size: 0.9rem;
                font-weight: 500;
            }}
            .egsi-links a:hover {{
                text-decoration: underline;
            }}
            .breadcrumbs {{
                padding: 1rem 0 0.5rem 0;
                font-size: 0.85rem;
                color: #64748b;
            }}
            .breadcrumbs a {{
                color: #60a5fa;
                text-decoration: none;
            }}
            .breadcrumbs a:hover {{
                text-decoration: underline;
            }}
            .mobile-menu-btn {{
                display: none;
                background: none;
                border: none;
                cursor: pointer;
                padding: 0.5rem;
                color: #f1f5f9;
            }}
            .mobile-menu-btn span {{
                display: block;
                width: 22px;
                height: 2px;
                background: #f1f5f9;
                margin: 5px 0;
                border-radius: 2px;
                transition: all 0.3s;
            }}
            @media (max-width: 768px) {{
                .mobile-menu-btn {{ display: block; }}
                .nav-links {{
                    display: none;
                    position: absolute;
                    top: 100%;
                    left: 0;
                    right: 0;
                    background: #1e293b;
                    border-top: 1px solid #334155;
                    flex-direction: column;
                    padding: 1rem;
                    gap: 0;
                    z-index: 200;
                    box-shadow: 0 8px 24px rgba(0,0,0,0.3);
                }}
                .nav-links.open {{ display: flex; }}
                .nav-links a {{
                    padding: 0.75rem 1rem;
                    border-bottom: 1px solid #334155;
                    width: 100%;
                    text-align: left;
                }}
                .nav-links a:last-child {{ border-bottom: none; }}
                .nav-links .cta-btn-nav {{
                    margin-top: 0.5rem;
                    text-align: center;
                }}
                .nav {{ position: relative; }}
                .egsi-cards-row {{ grid-template-columns: 1fr; }}
                .egsi-sections {{ grid-template-columns: 1fr; }}
                .egsi-chart-row {{ grid-template-columns: 1fr; }}
                .egsi-hero h1 {{ font-size: 1.35rem; }}
                .egsi-card-value {{ font-size: 1.5rem; }}
                .container {{ padding: 0 0.75rem; }}
            }}
        </style>
    </head>
    <body>
        <nav class="nav">
            <div class="nav-inner">
                <a href="/" class="logo">
                    <img src="/static/logo.png" alt="EnergyRiskIQ" width="36" height="36" style="margin-right: 0.5rem;">
                    EnergyRiskIQ
                </a>
                <button class="mobile-menu-btn" onclick="document.querySelector('.nav-links').classList.toggle('open')" aria-label="Menu">
                    <span></span><span></span><span></span>
                </button>
                <div class="nav-links">
                    <a href="/indices/global-energy-risk-index">GERI</a>
                    <a href="/indices/europe-energy-risk-index">EERI</a>
                    <a href="/egsi">EGSI</a>
                    <a href="/daily-geo-energy-intelligence-digest">Digest</a>
                    <a href="/daily-geo-energy-intelligence-digest/history">History</a>
                    <a href="/users" class="cta-btn-nav">Get FREE Access</a>
                </div>
            </div>
        </nav>
        <main>
            <div class="container">
                <div class="breadcrumbs">
                    <a href="/">Home</a> / Europe Gas Stress Index
                </div>
                <div class="egsi-hero">
                    <h1>Europe Gas Stress Index (EGSI)</h1>
                    <p>A daily composite measure of gas market and system stress across European infrastructure.</p>
                    <p class="methodology-link"><a href="/egsi/methodology">(EGSI Methodology &amp; Construction)</a></p>
                </div>

                <div class="egsi-cards-row">
                    {m_card}
                    {s_card}
                </div>

                <div class="egsi-sections">
                    <div class="egsi-section">
                        <h2>Primary Risk Drivers:</h2>
                        <ul class="egsi-list">{drivers_list_html}</ul>
                        <p class="source-attribution">(Based on recent EnergyRiskIQ alerts) <a href="/alerts">View alerts &rarr;</a></p>
                    </div>
                    <div class="egsi-section">
                        <h2>Chokepoint Watch:</h2>
                        <ul class="egsi-list">{chokepoints_list_html}</ul>
                    </div>
                </div>

                {interp_html}

                <div class="egsi-chart-section">
                    <h3>📈 EGSI-M History</h3>
                    <div class="egsi-chart-row">
                        <div class="egsi-chart-box">
                            <h4>Last 7 Days</h4>
                            <canvas id="egsiM7"></canvas>
                        </div>
                        <div class="egsi-chart-box">
                            <h4>Last 30 Days</h4>
                            <canvas id="egsiM30"></canvas>
                        </div>
                    </div>
                </div>

                <div class="egsi-chart-section">
                    <h3>📈 EGSI-S History</h3>
                    <div class="egsi-chart-row">
                        <div class="egsi-chart-box">
                            <h4>Last 7 Days</h4>
                            <canvas id="egsiS7"></canvas>
                        </div>
                        <div class="egsi-chart-box">
                            <h4>Last 30 Days</h4>
                            <canvas id="egsiS30"></canvas>
                        </div>
                    </div>
                </div>

                <div class="egsi-chart-section">
                    <h3>📊 EGSI-M vs EGSI-S (30 Days)</h3>
                    <div class="egsi-chart-box" style="max-width: 100%;">
                        <canvas id="egsiCompare"></canvas>
                    </div>
                </div>

                <div class="egsi-cta">
                    <h3>Get Real-time Access</h3>
                    <p>Unlock instant EGSI updates with a Pro subscription.</p>
                    <a href="/users" class="cta-button primary">Unlock Real-time EGSI</a>
                </div>

                <div class="egsi-links">
                    <a href="/egsi/history">View History</a>
                    <a href="/egsi/methodology">Methodology</a>
                </div>
            </div>
        </main>
        {render_digest_footer()}

        <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"></script>
        <script>
        (async function() {{
            const chartDefaults = {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{ display: false }},
                    tooltip: {{
                        backgroundColor: '#1e293b',
                        borderColor: '#334155',
                        borderWidth: 1,
                        titleColor: '#f1f5f9',
                        bodyColor: '#cbd5e1',
                        padding: 10,
                        cornerRadius: 8,
                    }}
                }},
                scales: {{
                    x: {{
                        ticks: {{ color: '#64748b', maxRotation: 45, font: {{ size: 10 }} }},
                        grid: {{ color: 'rgba(51, 65, 85, 0.3)' }}
                    }},
                    y: {{
                        min: 0, max: 100,
                        ticks: {{ color: '#64748b', font: {{ size: 10 }} }},
                        grid: {{ color: 'rgba(51, 65, 85, 0.3)' }}
                    }}
                }}
            }};

            function bandColor(val) {{
                if (val >= 80) return '#dc2626';
                if (val >= 60) return '#ef4444';
                if (val >= 40) return '#f97316';
                if (val >= 20) return '#3b82f6';
                return '#22c55e';
            }}

            function buildLineChart(canvasId, labels, data, color) {{
                const ctx = document.getElementById(canvasId);
                if (!ctx) return;
                new Chart(ctx, {{
                    type: 'line',
                    data: {{
                        labels: labels,
                        datasets: [{{
                            data: data,
                            borderColor: color,
                            backgroundColor: color + '20',
                            borderWidth: 2,
                            pointRadius: 3,
                            pointBackgroundColor: color,
                            fill: true,
                            tension: 0.3
                        }}]
                    }},
                    options: chartDefaults
                }});
            }}

            // Fetch EGSI-M history
            let mData = [];
            try {{
                const resp = await fetch('/api/v1/indices/egsi-m/history?days=30');
                if (resp.ok) {{
                    const result = await resp.json();
                    mData = (result.data || []).sort((a, b) => a.date.localeCompare(b.date));
                }}
            }} catch(e) {{}}

            // Fetch EGSI-S history
            let sData = [];
            try {{
                const resp = await fetch('/api/v1/indices/egsi-s/history?days=30');
                if (resp.ok) {{
                    const result = await resp.json();
                    sData = (result.data || []).sort((a, b) => a.date.localeCompare(b.date));
                }}
            }} catch(e) {{}}

            // EGSI-M charts
            if (mData.length > 0) {{
                const m7 = mData.slice(-7);
                const m30 = mData;
                buildLineChart('egsiM7', m7.map(d => d.date.slice(5)), m7.map(d => d.value), '#3b82f6');
                buildLineChart('egsiM30', m30.map(d => d.date.slice(5)), m30.map(d => d.value), '#3b82f6');
            }}

            // EGSI-S charts
            if (sData.length > 0) {{
                const s7 = sData.slice(-7);
                const s30 = sData;
                buildLineChart('egsiS7', s7.map(d => d.date.slice(5)), s7.map(d => d.value), '#22c55e');
                buildLineChart('egsiS30', s30.map(d => d.date.slice(5)), s30.map(d => d.value), '#22c55e');
            }}

            // Combined chart
            if (mData.length > 0 || sData.length > 0) {{
                const allDates = [...new Set([...mData.map(d => d.date), ...sData.map(d => d.date)])].sort();
                const mMap = Object.fromEntries(mData.map(d => [d.date, d.value]));
                const sMap = Object.fromEntries(sData.map(d => [d.date, d.value]));
                const ctx = document.getElementById('egsiCompare');
                if (ctx) {{
                    new Chart(ctx, {{
                        type: 'line',
                        data: {{
                            labels: allDates.map(d => d.slice(5)),
                            datasets: [
                                {{
                                    label: 'EGSI-M',
                                    data: allDates.map(d => mMap[d] ?? null),
                                    borderColor: '#3b82f6',
                                    backgroundColor: '#3b82f620',
                                    borderWidth: 2,
                                    pointRadius: 2,
                                    tension: 0.3,
                                    spanGaps: true
                                }},
                                {{
                                    label: 'EGSI-S',
                                    data: allDates.map(d => sMap[d] ?? null),
                                    borderColor: '#22c55e',
                                    backgroundColor: '#22c55e20',
                                    borderWidth: 2,
                                    pointRadius: 2,
                                    tension: 0.3,
                                    spanGaps: true
                                }}
                            ]
                        }},
                        options: {{
                            ...chartDefaults,
                            plugins: {{
                                ...chartDefaults.plugins,
                                legend: {{
                                    display: true,
                                    labels: {{ color: '#94a3b8', font: {{ size: 11 }} }}
                                }}
                            }}
                        }}
                    }});
                }}
            }}
        }})();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html)


@router.get("/egsi/updates", response_class=HTMLResponse)
async def egsi_updates_page():
    """
    EGSI Updates Page - Shows changelog and updates to the EGSI index methodology.
    """
    updates = [
        {
            "date": "2026-01-31",
            "version": "1.1",
            "title": "Public Interpretation",
            "description": "Added daily interpretation to EGSI public pages. Each day's index now includes a unique, contextual analysis explaining current gas market stress levels and key indicators.",
            "type": "enhancement"
        },
        {
            "date": "2026-01-25",
            "version": "1.0",
            "title": "EGSI Launch",
            "description": "Initial release of the Europe Gas Stress Index with two index families: EGSI-M (Market/Transmission signal) measuring gas market stress, and EGSI-S (System stress) tracking storage and pricing conditions.",
            "type": "release"
        },
    ]
    
    updates_html = ""
    for update in updates:
        type_badge = {
            "release": '<span class="update-badge release">Release</span>',
            "enhancement": '<span class="update-badge enhancement">Enhancement</span>',
            "fix": '<span class="update-badge fix">Fix</span>',
            "breaking": '<span class="update-badge breaking">Breaking Change</span>',
        }.get(update["type"], '<span class="update-badge">Update</span>')
        
        updates_html += f"""
        <div class="update-card">
            <div class="update-header">
                <div class="update-meta">
                    <span class="update-date">{update["date"]}</span>
                    <span class="update-version">v{update["version"]}</span>
                    {type_badge}
                </div>
                <h3 class="update-title">{update["title"]}</h3>
            </div>
            <p class="update-description">{update["description"]}</p>
        </div>
        """
    
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>EGSI Updates & Changelog | EnergyRiskIQ</title>
        <meta name="description" content="Track updates, enhancements, and changes to the Europe Gas Stress Index (EGSI) methodology and calculation.">
        <link rel="canonical" href="{BASE_URL}/egsi/updates">
        <link rel="icon" type="image/png" href="/static/favicon.png">
        
        <meta property="og:title" content="EGSI Updates & Changelog | EnergyRiskIQ">
        <meta property="og:description" content="Stay informed about updates to the Europe Gas Stress Index methodology.">
        <meta property="og:type" content="website">
        <meta property="og:url" content="{BASE_URL}/egsi/updates">
        
        {get_common_styles()}
        <style>
            .updates-hero {{
                text-align: center;
                padding: 3rem 0 2rem;
            }}
            .updates-hero h1 {{
                font-size: 2rem;
                margin-bottom: 0.75rem;
                color: var(--text-primary);
            }}
            .updates-hero p {{
                color: var(--text-secondary);
                max-width: 600px;
                margin: 0 auto;
            }}
            .updates-container {{
                max-width: 800px;
                margin: 0 auto 3rem;
            }}
            .update-card {{
                background: white;
                border: 1px solid var(--border);
                border-radius: 12px;
                padding: 1.5rem;
                margin-bottom: 1rem;
                transition: box-shadow 0.2s ease;
            }}
            .update-card:hover {{
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
            }}
            .update-header {{
                margin-bottom: 0.75rem;
            }}
            .update-meta {{
                display: flex;
                align-items: center;
                gap: 0.75rem;
                margin-bottom: 0.5rem;
                flex-wrap: wrap;
            }}
            .update-date {{
                color: var(--text-secondary);
                font-size: 0.875rem;
            }}
            .update-version {{
                background: var(--bg-light);
                color: var(--text-secondary);
                padding: 0.25rem 0.5rem;
                border-radius: 4px;
                font-size: 0.8rem;
                font-weight: 500;
            }}
            .update-badge {{
                padding: 0.25rem 0.75rem;
                border-radius: 20px;
                font-size: 0.75rem;
                font-weight: 600;
                text-transform: uppercase;
            }}
            .update-badge.release {{
                background: linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%);
                color: white;
            }}
            .update-badge.enhancement {{
                background: linear-gradient(135deg, #10b981 0%, #059669 100%);
                color: white;
            }}
            .update-badge.fix {{
                background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
                color: white;
            }}
            .update-badge.breaking {{
                background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
                color: white;
            }}
            .update-title {{
                font-size: 1.125rem;
                font-weight: 600;
                color: var(--text-primary);
                margin: 0;
            }}
            .update-description {{
                color: var(--text-secondary);
                line-height: 1.6;
                margin: 0;
            }}
            .updates-nav {{
                display: flex;
                justify-content: center;
                gap: 1.5rem;
                margin-top: 2rem;
                padding-top: 2rem;
                border-top: 1px solid var(--border);
            }}
            .updates-nav a {{
                color: var(--primary);
                text-decoration: none;
                font-weight: 500;
            }}
            .updates-nav a:hover {{
                text-decoration: underline;
            }}
        </style>
    </head>
    <body>
        <nav class="nav"><div class="container nav-inner">
            <a href="/" class="logo"><img src="/static/logo.png" alt="EnergyRiskIQ" width="32" height="32" style="margin-right: 0.5rem; vertical-align: middle;">EnergyRiskIQ</a>
            <div class="nav-links">
                <a href="/indices/global-energy-risk-index">GERI</a>
                <a href="/indices/europe-energy-risk-index">EERI</a>
                <a href="/egsi">EGSI</a>
                <a href="/alerts">Alerts</a>
                <a href="/users" class="cta-nav">Get FREE Access</a>
            </div>
        </div></nav>
        
        <main>
            <div class="container">
                <div class="updates-hero">
                    <h1>EGSI Updates & Changelog</h1>
                    <p>Track the latest updates, enhancements, and changes to the Europe Gas Stress Index methodology and calculation.</p>
                </div>
                
                <div class="updates-container">
                    {updates_html}
                </div>
                
                <div class="updates-nav">
                    <a href="/egsi">Current EGSI</a>
                    <a href="/egsi/history">History</a>
                    <a href="/egsi/methodology">Methodology</a>
                </div>
            </div>
        </main>
        
        <footer class="footer">
            <div class="container">
                <p>&copy; {datetime.now().year} EnergyRiskIQ. All rights reserved.</p>
            </div>
        </footer>
    </body>
    </html>
    """
    return HTMLResponse(content=html)


@router.get("/egsi/methodology", response_class=HTMLResponse)
async def egsi_methodology_page():
    """
    EGSI Methodology Page - Comprehensive SEO content explaining the Europe Gas Stress Index.
    """
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>EGSI Methodology - Europe Gas Stress Index | EnergyRiskIQ</title>
        <meta name="description" content="Complete methodology for the Europe Gas Stress Index (EGSI). Understand the dual-layer architecture (EGSI-M and EGSI-S), risk bands, pillar design, data sources, normalisation strategy, and interpretation framework behind Europe's leading gas stress indicator.">
        <link rel="canonical" href="{BASE_URL}/egsi/methodology">

        <meta property="og:title" content="EGSI Methodology — Europe Gas Stress Index | EnergyRiskIQ">
        <meta property="og:description" content="Full methodology for the Europe Gas Stress Index (EGSI): dual-layer architecture, nine pillars, risk bands, computation cadence, interpretation framework, and model governance.">
        <meta property="og:url" content="{BASE_URL}/egsi/methodology">
        <meta property="og:type" content="article">

        <meta name="twitter:card" content="summary_large_image">
        <meta name="twitter:title" content="EGSI Methodology — Europe Gas Stress Index">
        <meta name="twitter:description" content="How EnergyRiskIQ measures daily European gas system stress across market transmission and structural fragility dimensions.">

        <link rel="icon" type="image/png" href="/static/favicon.png">
        {get_common_styles()}
        <style>
            .meth-hero {{
                text-align: center;
                padding: 3rem 0 2rem;
                border-bottom: 1px solid var(--border);
                margin-bottom: 2.5rem;
            }}
            .meth-hero h1 {{
                font-size: 2.25rem;
                font-weight: 800;
                color: var(--text-primary);
                margin-bottom: 0.5rem;
            }}
            .meth-hero .subtitle {{
                font-size: 1.1rem;
                color: var(--text-secondary);
                max-width: 640px;
                margin: 0 auto;
                line-height: 1.6;
            }}
            .meth-hero .version-badge {{
                display: inline-block;
                margin-top: 1rem;
                background: var(--bg-light);
                border: 1px solid var(--border);
                padding: 0.35rem 1rem;
                border-radius: 2rem;
                font-size: 0.8rem;
                color: var(--text-secondary);
                font-weight: 500;
            }}
            .meth-section {{
                margin-bottom: 3rem;
            }}
            .meth-section h2 {{
                font-size: 1.5rem;
                font-weight: 700;
                color: var(--text-primary);
                margin-bottom: 0.25rem;
                padding-bottom: 0.75rem;
                border-bottom: 2px solid var(--primary);
                display: inline-block;
            }}
            .meth-section .section-num {{
                color: var(--primary);
                font-weight: 800;
                margin-right: 0.25rem;
            }}
            .meth-section h3 {{
                font-size: 1.15rem;
                font-weight: 600;
                color: var(--text-primary);
                margin: 1.5rem 0 0.75rem;
            }}
            .meth-body {{
                color: var(--text-secondary);
                line-height: 1.85;
                font-size: 0.975rem;
            }}
            .meth-body p {{
                margin-bottom: 1rem;
            }}
            .meth-body ul {{
                margin: 0.75rem 0 1rem 1.5rem;
            }}
            .meth-body li {{
                margin-bottom: 0.6rem;
            }}
            .meth-body strong {{
                color: var(--text-primary);
            }}
            .meth-blockquote {{
                background: linear-gradient(135deg, #eff6ff 0%, #f0f9ff 100%);
                border-left: 4px solid var(--primary);
                padding: 1.25rem 1.5rem;
                border-radius: 0 8px 8px 0;
                margin: 1.25rem 0;
                font-size: 1.05rem;
                color: var(--text-primary);
                font-weight: 500;
                font-style: italic;
                line-height: 1.6;
            }}
            .meth-table {{
                width: 100%;
                border-collapse: collapse;
                margin: 1.25rem 0;
                font-size: 0.9rem;
                border-radius: 8px;
                overflow: hidden;
                border: 1px solid var(--border);
            }}
            .meth-table thead th {{
                background: var(--secondary);
                color: #fff;
                padding: 0.75rem 1rem;
                text-align: left;
                font-weight: 600;
                font-size: 0.85rem;
                text-transform: uppercase;
                letter-spacing: 0.03em;
            }}
            .meth-table tbody td {{
                padding: 0.75rem 1rem;
                border-bottom: 1px solid var(--border);
                color: var(--text-secondary);
                line-height: 1.5;
                vertical-align: top;
            }}
            .meth-table tbody tr:last-child td {{
                border-bottom: none;
            }}
            .meth-table tbody tr:nth-child(even) {{
                background: var(--bg-light);
            }}
            .meth-table .band-dot {{
                display: inline-block;
                width: 10px;
                height: 10px;
                border-radius: 50%;
                margin-right: 6px;
                vertical-align: middle;
            }}
            .pillar-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
                gap: 1.25rem;
                margin: 1.5rem 0;
            }}
            .pillar-card {{
                background: var(--bg-white);
                border: 1px solid var(--border);
                border-radius: 12px;
                padding: 1.5rem;
                transition: box-shadow 0.2s ease;
            }}
            .pillar-card:hover {{
                box-shadow: 0 4px 16px rgba(0,0,0,0.08);
            }}
            .pillar-card .pillar-icon {{
                font-size: 1.75rem;
                margin-bottom: 0.5rem;
            }}
            .pillar-card .pillar-name {{
                font-size: 1.1rem;
                font-weight: 700;
                color: var(--text-primary);
                margin-bottom: 0.5rem;
            }}
            .pillar-card .pillar-subtitle {{
                font-size: 0.8rem;
                font-weight: 600;
                color: var(--primary);
                text-transform: uppercase;
                letter-spacing: 0.05em;
                margin-bottom: 0.75rem;
            }}
            .pillar-card .pillar-desc {{
                font-size: 0.9rem;
                color: var(--text-secondary);
                line-height: 1.65;
            }}
            .pillar-card .pillar-measures {{
                margin-top: 0.75rem;
                padding-top: 0.75rem;
                border-top: 1px solid var(--border);
            }}
            .pillar-card .pillar-measures li {{
                font-size: 0.85rem;
                color: var(--text-secondary);
                margin-bottom: 0.4rem;
                line-height: 1.5;
            }}
            .pillar-card .pillar-why {{
                margin-top: 0.75rem;
                font-size: 0.85rem;
                color: var(--primary-dark);
                font-weight: 500;
                font-style: italic;
                line-height: 1.5;
            }}
            .tier-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
                gap: 1rem;
                margin: 1.25rem 0;
            }}
            .tier-card {{
                background: var(--bg-white);
                border: 1px solid var(--border);
                border-radius: 10px;
                padding: 1.25rem;
            }}
            .tier-card .tier-label {{
                font-size: 0.75rem;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 0.06em;
                color: var(--primary);
                margin-bottom: 0.5rem;
            }}
            .tier-card .tier-title {{
                font-weight: 600;
                color: var(--text-primary);
                margin-bottom: 0.5rem;
            }}
            .tier-card ul {{
                margin: 0 0 0 1.25rem;
                font-size: 0.85rem;
                color: var(--text-secondary);
            }}
            .tier-card ul li {{
                margin-bottom: 0.35rem;
            }}
            .meth-cta {{
                background: linear-gradient(135deg, var(--secondary) 0%, #16213E 100%);
                border-radius: 16px;
                padding: 3rem 2rem;
                text-align: center;
                margin: 3rem 0 2rem;
            }}
            .meth-cta h3 {{
                color: #fff;
                font-size: 1.5rem;
                margin-bottom: 0.5rem;
            }}
            .meth-cta p {{
                color: #94a3b8;
                margin-bottom: 1.5rem;
                max-width: 500px;
                margin-left: auto;
                margin-right: auto;
            }}
            .meth-cta .cta-button {{
                display: inline-block;
                padding: 0.85rem 2rem;
                background: var(--primary);
                color: #fff;
                font-weight: 700;
                border-radius: 8px;
                text-decoration: none;
                font-size: 1rem;
                transition: background 0.2s ease;
            }}
            .meth-cta .cta-button:hover {{
                background: var(--primary-dark);
            }}
            .disclaimer {{
                text-align: center;
                padding: 1.5rem;
                font-size: 0.8rem;
                color: var(--text-secondary);
                font-style: italic;
                line-height: 1.6;
                border-top: 1px solid var(--border);
                margin-top: 1rem;
            }}
            .dual-layer-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                gap: 1.5rem;
                margin: 1.5rem 0;
            }}
            @media (max-width: 640px) {{
                .meth-hero h1 {{ font-size: 1.6rem; }}
                .pillar-grid {{ grid-template-columns: 1fr; }}
                .tier-grid {{ grid-template-columns: 1fr; }}
                .dual-layer-grid {{ grid-template-columns: 1fr; }}
                .meth-table {{ font-size: 0.8rem; }}
                .meth-table thead th, .meth-table tbody td {{ padding: 0.5rem 0.6rem; }}
            }}
        </style>
    </head>
    <body>
        <nav class="nav"><div class="container nav-inner">
            <a href="/" class="logo"><img src="/static/logo.png" alt="EnergyRiskIQ" width="32" height="32" style="margin-right: 0.5rem; vertical-align: middle;">EnergyRiskIQ</a>
            <div class="nav-links">
                <a href="/alerts">Alerts</a>
                <a href="/indices/global-energy-risk-index">GERI</a>
                <a href="/indices/europe-energy-risk-index">EERI</a>
                <a href="/egsi">EGSI</a>
                <a href="/users" class="cta-nav">Get FREE Access</a>
            </div>
        </div></nav>

        <main class="container">

            <div class="meth-hero">
                <h1>EGSI Methodology</h1>
                <p class="subtitle">A comprehensive overview of how the Europe Gas Stress Index measures daily stress, fragility, and disruption exposure across the European natural gas system through its dual-layer architecture.</p>
                <div class="version-badge">Model Version: EGSI-M v1, EGSI-S v1 &nbsp;|&nbsp; Last Updated: February 2026</div>
            </div>

            <!-- Section 1: What Is EGSI? -->
            <section class="meth-section">
                <h2><span class="section-num">1.</span> What Is EGSI?</h2>
                <div class="meth-body">
                    <p>The <strong>Europe Gas Stress Index (EGSI)</strong> is a proprietary dual-layer index system that measures the stress, fragility, and disruption exposure of the European natural gas system. It answers two critical questions simultaneously:</p>
                    <div class="meth-blockquote">"How violently is risk transmitting through European gas markets right now?"</div>
                    <div class="meth-blockquote">"How structurally fragile is Europe's gas system today?"</div>
                    <p>EGSI is unique in the EnergyRiskIQ platform because it operates as two complementary indices &mdash; <strong>EGSI-M (Market/Transmission)</strong> and <strong>EGSI-S (System)</strong> &mdash; each measuring a different dimension of gas stress. Together, they provide the most complete picture available of European gas vulnerability.</p>
                    <p>EGSI is designed for gas traders, LNG procurement teams, utility risk managers, energy desk analysts, infrastructure operators, policymakers, and hedge funds with European gas exposure. It translates complex multi-source intelligence &mdash; spanning geopolitical events, infrastructure chokepoints, physical storage data, market pricing, and policy signals &mdash; into an actionable daily stress reading.</p>
                </div>
            </section>

            <!-- Section 2: The Two Layers -->
            <section class="meth-section">
                <h2><span class="section-num">2.</span> The Two Layers: EGSI-M and EGSI-S</h2>
                <div class="meth-body">
                    <h3>Why Two Indices?</h3>
                    <p>European gas stress manifests in two fundamentally different ways:</p>
                    <ul>
                        <li><strong>Market transmission stress</strong> &mdash; How violently geopolitical and supply risk is flowing through gas markets today. This is reactive, fast-moving, and driven by the alert stream.</li>
                        <li><strong>System structural stress</strong> &mdash; How fragile the underlying physical gas infrastructure is. This is slower-moving, driven by storage levels, refill rates, price volatility, and policy conditions.</li>
                    </ul>
                    <p>A single index cannot capture both dimensions without compromising clarity. EGSI solves this by providing both readings simultaneously.</p>
                </div>
                <div class="dual-layer-grid">
                    <div class="pillar-card">
                        <div class="pillar-icon">⚡</div>
                        <div class="pillar-subtitle">EGSI-M</div>
                        <div class="pillar-name">Market / Transmission</div>
                        <div class="pillar-desc">Measures how intensely geopolitical and supply risk is transmitting through European gas markets on any given day. Reactive, event-driven, fast-moving &mdash; responds to the daily intelligence stream.</div>
                        <div class="pillar-why">Analogy: If the European gas system were a building, EGSI-M measures how hard the building is shaking right now.</div>
                        <ul class="pillar-measures">
                            <li><strong>Primary audience:</strong> Gas traders, commodity desks, short-term risk managers</li>
                        </ul>
                    </div>
                    <div class="pillar-card">
                        <div class="pillar-icon">🏗️</div>
                        <div class="pillar-subtitle">EGSI-S</div>
                        <div class="pillar-name">System Stress</div>
                        <div class="pillar-desc">Measures how structurally fragile the European gas system is &mdash; its physical readiness, storage adequacy, price stability, and policy environment. Structural, data-driven, slower-moving.</div>
                        <div class="pillar-why">Analogy: If the European gas system were a building, EGSI-S measures how structurally sound the building is &mdash; regardless of whether it is currently shaking.</div>
                        <ul class="pillar-measures">
                            <li><strong>Primary audience:</strong> Utilities, LNG procurement teams, policymakers, infrastructure operators, institutional risk committees</li>
                        </ul>
                    </div>
                </div>
                <div class="meth-body">
                    <h3>Reading EGSI-M and EGSI-S Together</h3>
                    <p>The dual reading is one of EGSI's most powerful features &mdash; it separates headline noise from structural reality:</p>
                    <table class="meth-table">
                        <thead><tr><th>EGSI-M</th><th>EGSI-S</th><th>Interpretation</th></tr></thead>
                        <tbody>
                            <tr><td><strong>Low</strong></td><td><strong>Low</strong></td><td>Gas system is calm and structurally sound. Normal operations. Minimal risk.</td></tr>
                            <tr><td><strong>High</strong></td><td><strong>Low</strong></td><td>Market is reacting to headlines, but the physical system is resilient. Likely a transient shock &mdash; watch for escalation but system buffers are intact.</td></tr>
                            <tr><td><strong>Low</strong></td><td><strong>High</strong></td><td>No immediate headlines, but the physical system is under structural strain. Storage may be depleting, refill rates lagging, or prices volatile. This is the quiet danger &mdash; the building is weakening even though it is not shaking.</td></tr>
                            <tr><td><strong>High</strong></td><td><strong>High</strong></td><td>Maximum concern. Active market transmission stress AND structural fragility. The system is both shaking and weakened. Historically associated with crisis conditions. Defensive positioning and contingency planning strongly indicated.</td></tr>
                        </tbody>
                    </table>
                </div>
            </section>

            <!-- Section 3: Scoring Range -->
            <section class="meth-section">
                <h2><span class="section-num">3.</span> Scoring Range</h2>
                <div class="meth-body">
                    <p>Both EGSI-M and EGSI-S produce daily values on a <strong>0 to 100</strong> scale:</p>
                    <ul>
                        <li><strong>0</strong> represents a theoretical state of zero gas stress</li>
                        <li><strong>100</strong> represents a theoretical state of maximum systemic gas crisis</li>
                    </ul>
                    <p>The scale is calibrated so that normal operating conditions cluster in the lower ranges, while readings above 60 indicate historically unusual stress requiring active attention.</p>
                </div>
            </section>

            <!-- Section 4: Risk Bands -->
            <section class="meth-section">
                <h2><span class="section-num">4.</span> Risk Bands</h2>
                <div class="meth-body">
                    <p>EGSI uses a five-band classification system specifically designed for gas stress measurement. The band labels are intentionally distinct from GERI and EERI to reflect the different nature of gas system risk:</p>
                    <table class="meth-table">
                        <thead><tr><th>Risk Band</th><th>Range</th><th>Interpretation</th></tr></thead>
                        <tbody>
                            <tr><td><span class="band-dot" style="background:#22c55e;"></span><strong>LOW</strong></td><td>0 &ndash; 20</td><td>Minimal gas stress. The European gas system is operating under normal conditions with no significant supply, storage, or market disruption signals. Standard monitoring posture.</td></tr>
                            <tr><td><span class="band-dot" style="background:#3b82f6;"></span><strong>NORMAL</strong></td><td>21 &ndash; 40</td><td>Baseline market conditions. Some background stress may be present &mdash; routine maintenance, seasonal patterns, or minor supply variations &mdash; but nothing warrants elevated concern. Normal operational awareness.</td></tr>
                            <tr><td><span class="band-dot" style="background:#f59e0b;"></span><strong>ELEVATED</strong></td><td>41 &ndash; 60</td><td>Heightened stress detected across the gas system. Multiple stress vectors are contributing simultaneously. Active monitoring is warranted. Gas, freight, or power markets may be showing early sensitivity.</td></tr>
                            <tr><td><span class="band-dot" style="background:#ef4444;"></span><strong>HIGH</strong></td><td>61 &ndash; 80</td><td>Significant stress affecting the European gas system. Risk signals are converging across supply, storage, transit, and market channels. Active hedging and contingency planning are strongly advised.</td></tr>
                            <tr><td><span class="band-dot" style="background:#991b1b;"></span><strong>CRITICAL</strong></td><td>81 &ndash; 100</td><td>Severe systemic stress. The European gas system is under extreme pressure across multiple dimensions. Emergency protocols, defensive positioning, and immediate contingency activation are strongly indicated.</td></tr>
                        </tbody>
                    </table>

                    <h3>Why EGSI Uses Different Band Labels</h3>
                    <p>GERI and EERI use a five-band system with SEVERE as the fourth band. EGSI intentionally uses HIGH instead of SEVERE because gas system stress has a different operational character:</p>
                    <ul>
                        <li>Gas stress is more directly tied to physical infrastructure and commodity flows than geopolitical risk</li>
                        <li>The language of &ldquo;HIGH stress&rdquo; is more natural for physical systems, industrial operations, and commodity markets</li>
                        <li>It aligns with how gas traders, utilities, and procurement teams naturally describe system conditions</li>
                    </ul>

                    <h3>Trend Indicators</h3>
                    <p>Each daily EGSI reading includes two trend signals:</p>
                    <ul>
                        <li><strong>1-Day Trend</strong> &mdash; Change from the previous day's value, showing immediate momentum</li>
                        <li><strong>7-Day Trend</strong> &mdash; Change from seven days prior, showing directional trajectory</li>
                    </ul>
                    <p>These trends are critical for distinguishing between an EGSI of 55 that is rising sharply (stress is building) and an EGSI of 55 that is falling from a recent peak (stress is subsiding). The same number carries very different operational implications.</p>
                </div>
            </section>

            <!-- Section 5: EGSI-M Architecture -->
            <section class="meth-section">
                <h2><span class="section-num">5.</span> EGSI-M Architecture: The Four Pillars</h2>
                <div class="meth-body">
                    <p>EGSI-M is constructed from four distinct pillars, each capturing a different dimension of how risk transmits through European gas markets.</p>
                </div>
                <div class="pillar-grid">
                    <div class="pillar-card">
                        <div class="pillar-icon">🛡️</div>
                        <div class="pillar-subtitle">Pillar 1</div>
                        <div class="pillar-name">Regional Escalation Backbone</div>
                        <div class="pillar-desc">The structural foundation of EGSI-M. Measures the underlying severity and intensity of geopolitical and energy events directly affecting Europe's gas system.</div>
                        <ul class="pillar-measures">
                            <li>Cumulative impact of high-severity events affecting European energy security</li>
                            <li>Escalation patterns &mdash; rising event frequency, increasing severity, and building pressure</li>
                            <li>Overall temperature of the European geopolitical risk environment as it relates to gas</li>
                        </ul>
                        <div class="pillar-why">Answers: "How dangerous is the European geopolitical environment for gas right now?"</div>
                    </div>
                    <div class="pillar-card">
                        <div class="pillar-icon">📊</div>
                        <div class="pillar-subtitle">Pillar 2</div>
                        <div class="pillar-name">Theme Pressure</div>
                        <div class="pillar-desc">Measures the nature, breadth, and intensity of gas-specific stress narratives in the intelligence stream &mdash; whether stress is concentrated in one narrative or spread across multiple themes.</div>
                        <ul class="pillar-measures">
                            <li>Supply disruptions, pipeline issues, transit disputes, LNG congestion</li>
                            <li>Storage concerns, maintenance outages, policy interventions</li>
                            <li>Persistence of stress themes &mdash; repeated events signal deep structural pressure</li>
                        </ul>
                        <div class="pillar-why">Answers: "What kind of gas stress is this?" &mdash; critical for calibrating the right response.</div>
                    </div>
                    <div class="pillar-card">
                        <div class="pillar-icon">📡</div>
                        <div class="pillar-subtitle">Pillar 3</div>
                        <div class="pillar-name">Asset Transmission</div>
                        <div class="pillar-desc">Measures whether gas stress is actually propagating into energy markets &mdash; bridging the gap between intelligence signals and financial reality.</div>
                        <ul class="pillar-measures">
                            <li>Number and breadth of energy asset classes showing stress linked to gas events</li>
                            <li>Cross-asset transmission &mdash; whether stress is spreading to oil, freight, FX, and power</li>
                            <li>Strength of connection between intelligence signals and market-observable stress</li>
                        </ul>
                        <div class="pillar-why">Answers: "Is this stress real or theoretical?" &mdash; where headlines become money.</div>
                    </div>
                    <div class="pillar-card">
                        <div class="pillar-icon">🎯</div>
                        <div class="pillar-subtitle">Pillar 4</div>
                        <div class="pillar-name">Chokepoint Factor</div>
                        <div class="pillar-desc">Captures risk signals emanating from specific European gas infrastructure chokepoints &mdash; high-value, low-redundancy nodes where disruption has outsized consequences.</div>
                        <ul class="pillar-measures">
                            <li>Direct mentions of monitored chokepoint entities in the intelligence stream</li>
                            <li>Severity and frequency of alerts referencing specific infrastructure</li>
                            <li>Concentration of risk around critical gas transit and import facilities</li>
                        </ul>
                        <div class="pillar-why">Answers: "Is risk clustering around infrastructure single points of failure?"</div>
                    </div>
                </div>
            </section>

            <!-- Section 6: EGSI-S Architecture -->
            <section class="meth-section">
                <h2><span class="section-num">6.</span> EGSI-S Architecture: The Five Pillars</h2>
                <div class="meth-body">
                    <p>EGSI-S is constructed from five distinct pillars measuring the physical, market, and policy dimensions of European gas system fragility.</p>
                </div>
                <div class="pillar-grid">
                    <div class="pillar-card">
                        <div class="pillar-icon">🚚</div>
                        <div class="pillar-subtitle">Pillar 1</div>
                        <div class="pillar-name">Supply Pressure</div>
                        <div class="pillar-desc">Measures how fragile European gas supply is &mdash; the physical availability and reliability of gas flowing into the system.</div>
                        <ul class="pillar-measures">
                            <li>LNG terminal outages, maintenance events, and capacity constraints</li>
                            <li>Pipeline disruptions, compressor outages, and flow reductions</li>
                            <li>Force majeure events and export restrictions</li>
                            <li>Alignment between current supply capacity and seasonal demand requirements</li>
                        </ul>
                        <div class="pillar-why">Answers: "Can Europe get the gas it needs?"</div>
                    </div>
                    <div class="pillar-card">
                        <div class="pillar-icon">🌊</div>
                        <div class="pillar-subtitle">Pillar 2</div>
                        <div class="pillar-name">Transit Stress</div>
                        <div class="pillar-desc">Measures the physical flow dynamics of the European gas system &mdash; how gas is moving through the network and whether injection or withdrawal patterns indicate stress.</div>
                        <ul class="pillar-measures">
                            <li>Injection rates during refill season vs expected targets</li>
                            <li>Withdrawal rates during heating season vs sustainable depletion trajectories</li>
                            <li>Transit corridor disruptions and rerouting pressures</li>
                        </ul>
                        <div class="pillar-why">Answers: "Are flow dynamics normal?" &mdash; detects emerging problems before they become headlines.</div>
                    </div>
                    <div class="pillar-card">
                        <div class="pillar-icon">📦</div>
                        <div class="pillar-subtitle">Pillar 3</div>
                        <div class="pillar-name">Storage Stress</div>
                        <div class="pillar-desc">Measures the adequacy and trajectory of European gas storage &mdash; the physical buffer that determines Europe's resilience to supply shocks and demand surges.</div>
                        <ul class="pillar-measures">
                            <li>Current EU gas storage level as percentage of total capacity</li>
                            <li>Deviation from seasonal storage norms</li>
                            <li>Refill velocity and winter deviation risk</li>
                            <li><strong>Data source:</strong> GIE AGSI+ (Aggregated Gas Storage Inventory)</li>
                        </ul>
                        <div class="pillar-why">Answers: "Is Europe's insurance policy against supply disruption adequate?"</div>
                    </div>
                    <div class="pillar-card">
                        <div class="pillar-icon">💹</div>
                        <div class="pillar-subtitle">Pillar 4</div>
                        <div class="pillar-name">Market Stress</div>
                        <div class="pillar-desc">Measures financial market stress in European gas &mdash; the degree to which gas pricing and trading conditions indicate systemic concern.</div>
                        <ul class="pillar-measures">
                            <li>TTF spot price movements and volatility</li>
                            <li>Magnitude of daily price changes relative to historical norms</li>
                            <li>Price shock events &mdash; sudden, outsized moves indicating market dislocation</li>
                            <li><strong>Data source:</strong> OilPriceAPI (TTF gas benchmark pricing)</li>
                        </ul>
                        <div class="pillar-why">Answers: "Are markets signalling systemic concern?" &mdash; often an early warning signal.</div>
                    </div>
                    <div class="pillar-card">
                        <div class="pillar-icon">⚖️</div>
                        <div class="pillar-subtitle">Pillar 5</div>
                        <div class="pillar-name">Policy Risk</div>
                        <div class="pillar-desc">Measures the degree to which government and regulatory interventions signal systemic concern about European gas security.</div>
                        <ul class="pillar-measures">
                            <li>Emergency policy declarations and market intervention announcements</li>
                            <li>Price cap discussions, rationing proposals, and demand curtailment measures</li>
                            <li>Regulatory changes affecting gas storage mandates and market rules</li>
                            <li>Subsidy programmes, emergency procurement, and strategic reserve actions</li>
                        </ul>
                        <div class="pillar-why">Answers: "Do authorities believe conditions warrant extraordinary action?"</div>
                    </div>
                </div>
            </section>

            <!-- Section 7: Normalisation Strategy -->
            <section class="meth-section">
                <h2><span class="section-num">7.</span> Normalisation Strategy</h2>
                <div class="meth-body">
                    <p>Raw stress metrics vary enormously depending on the global news cycle, seasonal patterns, and market conditions. Without normalisation, the 0&ndash;100 scale would be meaningless. Both EGSI-M and EGSI-S use adaptive normalisation that evolves as the indices mature.</p>

                    <h3>Bootstrap Phase</h3>
                    <p>During the initial period when insufficient historical data exists, both indices use conservative cap-based fallback values for each component. These caps are set based on reasonable assumptions about the range of observable conditions, preventing extreme values while the system accumulates operational history.</p>

                    <h3>Rolling Baseline Phase</h3>
                    <p>Once sufficient history has accumulated, both indices transition to percentile-based normalisation using rolling historical baselines. This approach:</p>
                    <ul>
                        <li>Keeps the 0&ndash;100 scale meaningful as conditions evolve</li>
                        <li>Prevents prolonged periods of high or low stress from permanently compressing the scale</li>
                        <li>Adapts to structural changes in the risk landscape over time</li>
                        <li>Ensures new periods of unusual calm or stress are properly reflected</li>
                    </ul>
                </div>
            </section>

            <!-- Section 8: Data Sources -->
            <section class="meth-section">
                <h2><span class="section-num">8.</span> Data Sources</h2>
                <div class="meth-body">
                    <h3>Structured Data Sources</h3>
                    <table class="meth-table">
                        <thead><tr><th>Source</th><th>Data Provided</th><th>Used By</th></tr></thead>
                        <tbody>
                            <tr><td><strong>GIE AGSI+</strong></td><td>EU gas storage levels, injection/withdrawal rates, capacity data across 18 Member States</td><td>EGSI-S (Storage pillar)</td></tr>
                            <tr><td><strong>OilPriceAPI</strong></td><td>TTF spot/near-month gas prices, historical pricing</td><td>EGSI-S (Market pillar)</td></tr>
                        </tbody>
                    </table>

                    <h3>Intelligence Signal Sources</h3>
                    <p>Both EGSI-M and EGSI-S consume structured alerts from the EnergyRiskIQ intelligence pipeline:</p>
                    <ul>
                        <li><strong>High-Impact Events</strong> &mdash; Major geopolitical escalations, infrastructure incidents, supply shocks</li>
                        <li><strong>Regional Risk Spikes</strong> &mdash; Clustering of events indicating regional escalation</li>
                        <li><strong>Asset Risk Alerts</strong> &mdash; Asset-specific stress signals, including gas storage alerts generated by the EGSI storage monitoring system</li>
                    </ul>
                    <p>These alerts are ingested from a curated portfolio of institutional, trade, and regional intelligence sources spanning Reuters, ICIS, EU Commission feeds, maritime intelligence, and specialised energy publications.</p>
                </div>
            </section>

            <!-- Section 9: Computation Cadence -->
            <section class="meth-section">
                <h2><span class="section-num">9.</span> Computation Cadence</h2>
                <div class="meth-body">
                    <h3>Daily Computation</h3>
                    <p>Both EGSI-M and EGSI-S are computed daily, producing authoritative daily values. Computation runs after the day's intelligence has been processed and structured data has been updated.</p>

                    <h3>Scheduled Execution</h3>
                    <ul>
                        <li><strong>EGSI-M</strong> runs alongside GERI and EERI computation, after alert delivery</li>
                        <li><strong>EGSI-S</strong> runs on a higher-frequency schedule to incorporate the latest structured data as it becomes available</li>
                    </ul>

                    <h3>Publication Schedule</h3>
                    <table class="meth-table">
                        <thead><tr><th>Audience</th><th>Timing</th><th>Content</th></tr></thead>
                        <tbody>
                            <tr><td><strong>Paid subscribers</strong></td><td>Real-time on computation</td><td>Full EGSI-M and EGSI-S values, bands, trends, component breakdown, top drivers, chokepoint watch, and AI interpretation</td></tr>
                            <tr><td><strong>Free users</strong></td><td>24-hour delay</td><td>EGSI value and band with limited context</td></tr>
                            <tr><td><strong>Public / SEO pages</strong></td><td>24-hour delay</td><td>EGSI value, band, trend indicator, and top driver headlines</td></tr>
                        </tbody>
                    </table>
                </div>
            </section>

            <!-- Section 10: Chokepoint Monitoring -->
            <section class="meth-section">
                <h2><span class="section-num">10.</span> Chokepoint Monitoring</h2>
                <div class="meth-body">
                    <h3>Philosophy</h3>
                    <p>The European gas system has identifiable critical nodes &mdash; infrastructure where disruption has consequences far beyond the facility itself. These chokepoints represent low-redundancy, high-throughput points in the gas supply network. EGSI maintains a monitored chokepoint registry that feeds directly into the EGSI-M Chokepoint Factor pillar.</p>

                    <h3>Monitored Infrastructure</h3>
                    <p>EGSI tracks ten key European gas infrastructure chokepoints across three categories:</p>

                    <h3>Transit Corridors</h3>
                    <ul>
                        <li>Ukraine Transit System (Sudzha entry, Urengoy-Pomary-Uzhgorod pipeline)</li>
                        <li>TurkStream / Blue Stream (southern corridor)</li>
                        <li>Nord Stream infrastructure (northern corridor, currently compromised)</li>
                    </ul>

                    <h3>Pipeline Systems</h3>
                    <ul>
                        <li>Norway export pipelines (Langeled, Europipe, Troll infrastructure, Equinor network)</li>
                    </ul>

                    <h3>LNG Import Terminals</h3>
                    <ul>
                        <li>Gate Terminal (Rotterdam, Netherlands)</li>
                        <li>Zeebrugge LNG (Fluxys, Belgium)</li>
                        <li>Dunkerque LNG (France)</li>
                        <li>Montoir-de-Bretagne LNG (Elengy, France)</li>
                        <li>Swinoujscie LNG (Poland)</li>
                        <li>Revithoussa LNG (Greece)</li>
                    </ul>
                </div>
            </section>

            <!-- Section 11: Integration with Index Ecosystem -->
            <section class="meth-section">
                <h2><span class="section-num">11.</span> Integration with the EnergyRiskIQ Index Ecosystem</h2>
                <div class="meth-body">
                    <h3>Position in the Index Stack</h3>
                    <p>EGSI occupies the asset/system layer in EnergyRiskIQ's multi-level risk architecture:</p>
                    <table class="meth-table">
                        <thead><tr><th>Level</th><th>Index</th><th>Scope</th><th>Question Answered</th></tr></thead>
                        <tbody>
                            <tr><td><strong>Macro</strong></td><td>GERI</td><td>Global</td><td>"Is the world dangerous for energy markets?"</td></tr>
                            <tr><td><strong>Regional</strong></td><td>EERI</td><td>European</td><td>"Is Europe's energy security threatened?"</td></tr>
                            <tr><td><strong>Asset / System</strong></td><td>EGSI</td><td>European Gas</td><td>"How close is Europe to a gas shock?"</td></tr>
                        </tbody>
                    </table>
                    <p>This creates a complete risk stack: <strong>Macro &rarr; Regional &rarr; Asset System</strong>.</p>

                    <h3>Reading Alongside GERI</h3>
                    <p>GERI measures global geopolitical and energy risk. EGSI measures European gas-specific stress. Reading them together reveals whether global risk is concentrated in gas, or whether gas stress is a regional phenomenon disconnected from global conditions.</p>

                    <h3>Reading Alongside EERI</h3>
                    <p>EGSI feeds directly into EERI through the Asset Transmission component. When EGSI detects elevated gas stress, these signals contribute to EERI's composite reading. However, EGSI provides far more granular gas-specific intelligence than EERI alone.</p>
                    <table class="meth-table">
                        <thead><tr><th>Pattern</th><th>Interpretation</th></tr></thead>
                        <tbody>
                            <tr><td><strong>EERI high + EGSI high</strong></td><td>European energy stress is gas-led. Gas is the primary vulnerability vector.</td></tr>
                            <tr><td><strong>EERI high + EGSI moderate</strong></td><td>European stress is driven by non-gas factors (oil, geopolitics, broader energy policy). Gas system is relatively insulated.</td></tr>
                            <tr><td><strong>EERI moderate + EGSI high</strong></td><td>Gas-specific stress that hasn't yet reached broader European energy risk thresholds. A sectoral warning &mdash; critical for gas professionals, less urgent for broader energy risk managers.</td></tr>
                        </tbody>
                    </table>
                </div>
            </section>

            <!-- Section 12: Interpretation Framework -->
            <section class="meth-section">
                <h2><span class="section-num">12.</span> Interpretation Framework</h2>
                <div class="meth-body">
                    <h3>EGSI as Operational Intelligence</h3>
                    <p>EGSI is not a gas price forecast or trading signal. It is an operational stress intelligence layer that tells professionals where European gas system stress is concentrated, how it is evolving, and what dimensions are driving it:</p>
                    <ul>
                        <li><strong>EGSI rising</strong> means gas system stress inputs are increasing &mdash; it does not guarantee gas prices will rise</li>
                        <li><strong>EGSI falling</strong> means stress inputs are subsiding &mdash; it does not guarantee market calm</li>
                        <li><strong>EGSI in CRITICAL</strong> means the concentration and severity of stress signals matches historical periods associated with significant gas market disruption</li>
                        <li>The relationship between EGSI and gas prices is mediated by storage buffers, LNG availability, demand conditions, weather forecasts, and market positioning</li>
                    </ul>

                    <h3>Component Dominance &mdash; EGSI-M</h3>
                    <p>For paid subscribers, EGSI provides visibility into which pillars are driving the current reading:</p>
                    <ul>
                        <li><strong>Regional Escalation dominant:</strong> Geopolitical forces are the primary driver. The risk environment around Europe is deteriorating.</li>
                        <li><strong>Theme Pressure dominant:</strong> Gas-specific narratives are intensifying. Multiple stress themes are compounding.</li>
                        <li><strong>Asset Transmission dominant:</strong> Markets are actively pricing gas stress. This is the confirmation phase.</li>
                        <li><strong>Chokepoint Factor dominant:</strong> Risk is concentrated around specific infrastructure. High-consequence disruption probability is elevated.</li>
                    </ul>

                    <h3>Component Dominance &mdash; EGSI-S</h3>
                    <ul>
                        <li><strong>Supply Pressure dominant:</strong> Physical supply fragility is the primary concern. Outages, maintenance, or capacity constraints are driving stress.</li>
                        <li><strong>Transit Stress dominant:</strong> Flow dynamics are abnormal. Injection or withdrawal rates deviate significantly from expectations.</li>
                        <li><strong>Storage dominant:</strong> Storage levels are the primary vulnerability. The physical buffer is inadequate for current risk conditions.</li>
                        <li><strong>Market Stress dominant:</strong> Price volatility and trading conditions indicate systemic concern.</li>
                        <li><strong>Policy Risk dominant:</strong> Government interventions signal that authorities view conditions as beyond normal market management.</li>
                    </ul>

                    <h3>Regime Recognition</h3>
                    <p>EGSI's historical trajectory can be divided into recognisable stress regimes:</p>
                    <table class="meth-table">
                        <thead><tr><th>Regime</th><th>Characteristics</th><th>Typical Duration</th></tr></thead>
                        <tbody>
                            <tr><td><strong>Calm</strong></td><td>EGSI in LOW/NORMAL bands, stable trends, minimal driver activity. System operating well within safe parameters.</td><td>Weeks to months</td></tr>
                            <tr><td><strong>Stress Build-Up</strong></td><td>EGSI rising, crossing from NORMAL to ELEVATED. Storage may be lagging, supply concerns emerging, or market volatility increasing.</td><td>Days to weeks</td></tr>
                            <tr><td><strong>Active Stress</strong></td><td>EGSI in HIGH/CRITICAL range. Multiple pillars contributing. Markets volatile, storage under pressure, or supply disruptions active.</td><td>Days to weeks</td></tr>
                            <tr><td><strong>De-escalation</strong></td><td>EGSI falling from HIGH/CRITICAL. Stress drivers subsiding, storage improving, or supply normalising. Caution still warranted.</td><td>Days to weeks</td></tr>
                            <tr><td><strong>Recovery</strong></td><td>EGSI returning to LOW/NORMAL. System buffers rebuilding, market conditions normalising.</td><td>Weeks</td></tr>
                        </tbody>
                    </table>
                    <p>Regime transitions are the most actionable signals. The shift from Calm to Stress Build-Up is the early warning. The shift from Stress Build-Up to Active Stress is the confirmation. The shift from Active Stress to De-escalation is the turning point.</p>
                </div>
            </section>

            <!-- Section 13: Seasonal Context -->
            <section class="meth-section">
                <h2><span class="section-num">13.</span> Seasonal Context</h2>
                <div class="meth-body">
                    <p>European gas stress is inherently seasonal, and EGSI accounts for this in several ways.</p>

                    <h3>Storage Seasonality</h3>
                    <p>Gas storage follows a predictable annual cycle: drawdown during winter heating season (November through March), refill during injection season (April through October). EGSI-S measures storage relative to seasonal norms &mdash; not absolute levels &mdash; ensuring that a storage level of 50% in March (normal) is treated differently from 50% in September (concerning).</p>

                    <h3>Seasonal Benchmarks</h3>
                    <table class="meth-table">
                        <thead><tr><th>Period</th><th>Expected Storage</th><th>Significance</th></tr></thead>
                        <tbody>
                            <tr><td><strong>November 1</strong></td><td>90%</td><td>EU regulatory mandate for winter readiness</td></tr>
                            <tr><td><strong>Mid-winter (January)</strong></td><td>~65%</td><td>Normal mid-winter drawdown level</td></tr>
                            <tr><td><strong>Seasonal low (March)</strong></td><td>~40%</td><td>Expected post-winter minimum</td></tr>
                            <tr><td><strong>February 1</strong></td><td>45%</td><td>Winter security floor target</td></tr>
                            <tr><td><strong>Peak refill (August)</strong></td><td>~82%</td><td>Pre-autumn acceleration target</td></tr>
                        </tbody>
                    </table>

                    <h3>Winter Risk Amplification</h3>
                    <p>During winter months (November through March), all gas stress signals carry amplified significance because:</p>
                    <ul>
                        <li>Demand is at its highest (heating load)</li>
                        <li>Storage is being depleted rather than replenished</li>
                        <li>Supply disruptions cannot be compensated by accelerated injection</li>
                        <li>The consequences of miscalculation are immediate and severe</li>
                    </ul>
                    <p>EGSI-S incorporates this seasonal amplification directly into its stress calculations.</p>
                </div>
            </section>

            <!-- Section 14: What EGSI Does Not Do -->
            <section class="meth-section">
                <h2><span class="section-num">14.</span> What EGSI Does Not Do</h2>
                <div class="meth-body">
                    <p>For transparency and proper use, it is important to understand the boundaries of the index:</p>
                    <ul>
                        <li><strong>EGSI is not a gas price forecast.</strong> It measures the stress environment, not the price outcome.</li>
                        <li><strong>EGSI is not a trading signal.</strong> It provides stress context for decision-making, not buy/sell instructions.</li>
                        <li><strong>EGSI does not cover non-gas European energy risks.</strong> It focuses specifically on the natural gas system.</li>
                        <li><strong>EGSI is not intraday.</strong> It is a daily index. Events occurring during the day will be reflected in subsequent computations.</li>
                        <li><strong>EGSI does not model weather directly.</strong> It captures weather impact through downstream effects on storage deviation, withdrawal rates, and market volatility.</li>
                        <li><strong>EGSI does not replace fundamental gas market analysis.</strong> It is a complementary intelligence layer designed to sit alongside traditional gas trading and procurement tools.</li>
                    </ul>
                </div>
            </section>

            <!-- Section 15: Model Governance -->
            <section class="meth-section">
                <h2><span class="section-num">15.</span> Model Governance and Evolution</h2>
                <div class="meth-body">
                    <h3>Version Control</h3>
                    <p>EGSI operates under strict version control. The current production models are <strong>EGSI-M v1</strong> and <strong>EGSI-S v1</strong>. All historical data is tagged with its model version, ensuring full auditability and reproducibility.</p>

                    <h3>Feature Flag</h3>
                    <p>EGSI computation is controlled by a feature flag (<strong>ENABLE_EGSI</strong>), allowing both indices to be activated or deactivated without code changes. This ensures operational safety during maintenance or if data quality issues are detected.</p>

                    <h3>Planned Evolution</h3>
                    <ul>
                        <li><strong>EGSI-S v2 &mdash; Enhanced Pillar Architecture:</strong> Expansion of supply and transit pillars with additional structured data sources, including pipeline flow data and LNG terminal utilisation rates</li>
                        <li><strong>Country-Level Decomposition:</strong> Sub-national storage and stress analysis for major consuming countries (Germany, Italy, France, Netherlands)</li>
                        <li><strong>Weather Integration:</strong> Direct weather forecast anomaly data to enhance winter deviation risk modelling</li>
                        <li><strong>Cross-Index Contagion:</strong> When EERI activates its Contagion pillar (v2), EGSI will receive cross-regional spillover signals from Middle East and Black Sea gas-relevant developments</li>
                    </ul>

                    <h3>Independence and Objectivity</h3>
                    <p>EGSI is computed algorithmically from structured data inputs and intelligence signals. There is no editorial override, manual adjustment, or subjective intervention in the daily index values. The methodology is fixed for each model version, with changes implemented only through formal version upgrades with documented rationale.</p>
                </div>
            </section>

            <!-- CTA -->
            <div class="meth-cta">
                <h3>Access Full Gas Intelligence</h3>
                <p>Get real-time EGSI-M and EGSI-S readings, component breakdowns, chokepoint monitoring, and AI-powered interpretation delivered daily.</p>
                <a href="/users" class="cta-button">Get FREE Access</a>
            </div>

            <!-- Disclaimer -->
            <div class="disclaimer">
                Europe Gas Stress Index (EGSI) is a proprietary index of EnergyRiskIQ. This methodology document is provided for transparency and educational purposes. It does not constitute financial advice.
            </div>

        </main>

        <footer class="footer">
            <div class="container">
                <p>&copy; {datetime.now().year} EnergyRiskIQ. All rights reserved.</p>
                <p style="margin-top: 0.5rem;">
                    <a href="/egsi">EGSI</a> &middot;
                    <a href="/egsi/history">EGSI History</a> &middot;
                    <a href="/indices/global-energy-risk-index">GERI</a> &middot;
                    <a href="/indices/europe-energy-risk-index">EERI</a>
                </p>
            </div>
        </footer>
    </body>
    </html>
    """
    return HTMLResponse(content=html)


@router.get("/egsi/history", response_class=HTMLResponse)
async def egsi_history_page():
    """
    EGSI History Page - Overview of historical data with links to archives.
    """
    dates = get_all_egsi_m_dates()
    months = get_egsi_m_available_months()
    stats = get_egsi_m_monthly_stats()
    
    recent_dates_html = ""
    for d in dates[:14]:
        recent_dates_html += f'<li><a href="/egsi/{d}">{d}</a></li>'
    if not recent_dates_html:
        recent_dates_html = '<li>No historical data available yet</li>'
    
    months_html = ""
    for m in months[:12]:
        month_label = f"{month_name[m['month']]} {m['year']}"
        months_html += f'<li><a href="/egsi/{m["year"]}/{m["month"]:02d}">{month_label}</a> ({m["count"]} days)</li>'
    if not months_html:
        months_html = '<li>No monthly archives available yet</li>'
    
    stats_html = ""
    for s in stats[:6]:
        month_label = f"{month_name[s['month']]} {s['year']}"
        stats_html += f"""
        <tr>
            <td>{month_label}</td>
            <td>{s['count']}</td>
            <td>{s['avg_value']:.1f}</td>
            <td>{s['max_value']:.1f}</td>
            <td>{s['min_value']:.1f}</td>
        </tr>
        """
    
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>EGSI History - Europe Gas Stress Index Archive | EnergyRiskIQ</title>
        <meta name="description" content="Historical archive of Europe Gas Stress Index (EGSI) values. Browse daily snapshots and monthly trends.">
        <link rel="canonical" href="{BASE_URL}/egsi/history">
        <link rel="icon" type="image/png" href="/static/favicon.png">
        
        {get_common_styles()}
    </head>
    <body>
        <nav class="nav"><div class="container nav-inner">
            <a href="/" class="logo"><img src="/static/logo.png" alt="EnergyRiskIQ" width="32" height="32" style="margin-right: 0.5rem; vertical-align: middle;">EnergyRiskIQ</a>
            <div class="nav-links">
                <a href="/indices/global-energy-risk-index">GERI</a>
                <a href="/indices/europe-energy-risk-index">EERI</a>
                <a href="/egsi">EGSI</a>
                <a href="/alerts">Alerts</a>
                <a href="/users" class="cta-nav">Get FREE Access</a>
            </div>
        </div></nav>
        
        <main>
            <div class="container">
                <div class="breadcrumb">
                    <a href="/egsi">EGSI</a> &gt; History
                </div>
                
                <h1 style="margin: 40px 0 30px;">EGSI Historical Data</h1>
                
                <div class="index-sections">
                    <div class="index-section" style="background: white; border: 1px solid var(--border);">
                        <h2 style="color: var(--text-primary);">Recent Daily Snapshots</h2>
                        <ul style="margin-top: 15px; padding-left: 20px; color: var(--text-primary);">
                            {recent_dates_html}
                        </ul>
                    </div>
                    
                    <div class="index-section" style="background: white; border: 1px solid var(--border);">
                        <h2 style="color: var(--text-primary);">Monthly Archives</h2>
                        <ul style="margin-top: 15px; padding-left: 20px; color: var(--text-primary);">
                            {months_html}
                        </ul>
                    </div>
                </div>
                
                {"<div class='index-section' style='margin-top: 40px; background: white; border: 1px solid var(--border);'><h2 style='color: var(--text-primary);'>Monthly Statistics</h2><table><tr><th>Month</th><th>Days</th><th>Avg</th><th>Max</th><th>Min</th></tr>" + stats_html + "</table></div>" if stats_html else ""}
                
                <div class="index-links" style="margin-top: 40px;">
                    <a href="/egsi">&larr; Current EGSI</a>
                    <a href="/egsi/methodology">Methodology &rarr;</a>
                </div>
                
                <div class="data-sources-section" style="margin-top: 2rem; padding-top: 1.5rem; border-top: 1px solid #e2e8f0;">
                    <h4 style="font-size: 0.875rem; font-weight: 600; color: #64748b; margin-bottom: 0.5rem;">Data Sources</h4>
                    <p style="font-size: 0.875rem; color: #475569;">EGSI values are computed from gas-related energy risk alerts. <a href="/alerts" style="color: #2563eb;">View recent alerts</a></p>
                </div>
            </div>
        </main>
        
        <footer class="footer">
            <div class="container">
                <p>&copy; {datetime.now().year} EnergyRiskIQ</p>
            </div>
        </footer>
    </body>
    </html>
    """
    return HTMLResponse(content=html)


@router.get("/egsi/{date_str}", response_class=HTMLResponse)
async def egsi_daily_snapshot(date_str: str):
    """
    EGSI Daily Snapshot Page.
    """
    if '/' in date_str or len(date_str) < 8:
        raise HTTPException(status_code=404, detail="Invalid date format")
    
    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        raise HTTPException(status_code=404, detail="Invalid date format. Use YYYY-MM-DD.")
    
    egsi = get_egsi_m_by_date(target_date)
    if not egsi:
        date_display = target_date.strftime('%B %d, %Y')
        adjacent = get_egsi_m_adjacent_dates(target_date)
        
        nav_links = []
        if adjacent.get('prev'):
            nav_links.append(f'<a href="/egsi/{adjacent["prev"]}">&larr; {adjacent["prev"]}</a>')
        if adjacent.get('next'):
            nav_links.append(f'<a href="/egsi/{adjacent["next"]}">{adjacent["next"]} &rarr;</a>')
        nav_html = ' | '.join(nav_links) if nav_links else '<a href="/egsi/history">Browse History</a>'
        
        no_data_html = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>EGSI {date_str} - No Data Available | EnergyRiskIQ</title>
            <meta name="description" content="No Europe Gas Stress Index data available for {date_display}.">
            <link rel="canonical" href="{BASE_URL}/egsi/{date_str}">
            <link rel="icon" type="image/png" href="/static/favicon.png">
            {get_common_styles()}
        </head>
        <body>
            <header>
                <div class="container header-content">
                    <a href="/" class="logo">
                        <img src="/static/logo.png" alt="EnergyRiskIQ" style="height: 36px; vertical-align: middle; margin-right: 8px;">
                        EnergyRiskIQ
                    </a>
                    <nav>
                        <a href="/indices/europe-energy-risk-index">EERI</a>
                        <a href="/egsi">EGSI</a>
                        <a href="/alerts">Alerts</a>
                    </nav>
                </div>
            </header>
            
            <div class="container">
                <div class="breadcrumb">
                    <a href="/egsi">EGSI</a> &gt; <a href="/egsi/history">History</a> &gt; {date_str}
                </div>
                
                <div class="index-display" style="margin-top: 40px;">
                    <div style="font-size: 4rem; margin-bottom: 20px;">📊</div>
                    <h1 style="font-size: 1.8rem; margin-bottom: 15px;">No Data for {date_display}</h1>
                    <p class="interpretation">
                        The Europe Gas Stress Index was not computed for this date. 
                        This may be because:
                    </p>
                    <ul style="text-align: left; max-width: 400px; margin: 20px auto; line-height: 1.8;">
                        <li>The date is in the future</li>
                        <li>It falls before EGSI tracking began</li>
                        <li>No alerts were available for computation</li>
                    </ul>
                    <div style="margin-top: 30px;">
                        {nav_html}
                    </div>
                </div>
            </div>
            
            <footer>
                <div class="container">
                    <p>&copy; {datetime.now().year} EnergyRiskIQ</p>
                    <p style="margin-top: 10px;">
                        <a href="/egsi">Current EGSI</a> | 
                        <a href="/egsi/history">History</a> | 
                        <a href="/egsi/methodology">Methodology</a>
                    </p>
                </div>
            </footer>
        </body>
        </html>
        """
        return HTMLResponse(content=no_data_html)
    
    adjacent = get_egsi_m_adjacent_dates(target_date)
    
    value = egsi.get('value', 0)
    band = egsi.get('band', 'LOW')
    trend_7d = egsi.get('trend_7d')
    drivers = egsi.get('drivers', [])[:5]
    components = egsi.get('components', {})
    
    band_color = get_band_color(band)
    date_display = target_date.strftime('%B %d, %Y')
    
    interpretation = egsi.get('explanation') or egsi.get('interpretation')
    if not interpretation:
        interpretation = generate_egsi_interpretation(
            value=value,
            band=band,
            drivers=drivers,
            components=components,
            index_date=date_str,
            index_type="EGSI-M"
        )
    
    trend_label, trend_sign_val, trend_color = format_trend(trend_7d)
    trend_display = ""
    if trend_7d is not None:
        trend_sign = "+" if trend_7d > 0 else ""
        trend_display = f'<div class="index-trend" style="color: {trend_color};">7-Day Trend: {trend_label} ({trend_sign}{trend_7d:.0f})</div>'
    
    drivers_list_html = ""
    for driver in drivers:
        driver_name = driver.get('name', 'Unknown')
        driver_type = driver.get('type', 'N/A')
        contribution = driver.get('contribution', 0)
        drivers_list_html += f'<li><span class="driver-tag">{driver_type}</span><br>{driver_name} ({contribution:.1f}% contribution)</li>'
    if not drivers_list_html:
        drivers_list_html = '<li>No significant drivers detected</li>'
    
    chokepoints = components.get('chokepoint_factor', {}).get('hits', []) if isinstance(components, dict) else []
    chokepoints_list_html = ""
    for cp in chokepoints[:5]:
        chokepoints_list_html += f'<li>{cp}</li>'
    if not chokepoints_list_html:
        chokepoints_list_html = '<li>No active chokepoint alerts</li>'
    
    date_nav_html = '<div class="date-nav" style="display: flex; justify-content: space-between; margin: 2rem 0; font-size: 0.95rem;">'
    if adjacent.get('prev'):
        date_nav_html += f'<a href="/egsi/{adjacent["prev"]}" style="color: #60a5fa; text-decoration: none;">&larr; {adjacent["prev"]}</a>'
    else:
        date_nav_html += '<span></span>'
    if adjacent.get('next'):
        date_nav_html += f'<a href="/egsi/{adjacent["next"]}" style="color: #60a5fa; text-decoration: none;">{adjacent["next"]} &rarr;</a>'
    else:
        date_nav_html += '<span></span>'
    date_nav_html += '</div>'
    
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>EGSI {date_str} - {band} at {value:.0f} | EnergyRiskIQ</title>
        <meta name="description" content="Europe Gas Stress Index for {date_display}: {value:.0f} ({band}). {interpretation[:150] if interpretation else ''}">
        <link rel="canonical" href="{BASE_URL}/egsi/{date_str}">
        <link rel="icon" type="image/png" href="/static/favicon.png">
        
        <meta property="og:title" content="EGSI {date_str} - {band} at {value:.0f} | EnergyRiskIQ">
        <meta property="og:description" content="Europe Gas Stress Index for {date_display}: {value:.0f} ({band}).">
        <meta property="og:type" content="article">
        <meta property="og:url" content="{BASE_URL}/egsi/{date_str}">
        
        {get_common_styles()}
    </head>
    <body>
        <nav class="nav"><div class="container nav-inner">
            <a href="/" class="logo"><img src="/static/logo.png" alt="EnergyRiskIQ" width="32" height="32" style="margin-right: 0.5rem; vertical-align: middle;">EnergyRiskIQ</a>
            <div class="nav-links">
                <a href="/indices/global-energy-risk-index">GERI</a>
                <a href="/indices/europe-energy-risk-index">EERI</a>
                <a href="/egsi">EGSI</a>
                <a href="/alerts">Alerts</a>
                <a href="/users" class="cta-nav">Get FREE Access</a>
            </div>
        </div></nav>
        
        <main>
            <div class="container">
                <div class="index-hero">
                    <h1>Europe Gas Stress Index (EGSI)</h1>
                    <p>Historical snapshot for {date_display}</p>
                    <p class="methodology-link"><a href="/egsi/methodology">(EGSI Methodology & Construction)</a></p>
                </div>
                
                <div class="index-metric-card">
                    <div class="index-header">
                        <span class="index-icon">🔥</span>
                        <span class="index-title">Europe Gas Stress Index:</span>
                    </div>
                    <div class="index-value" style="color: {band_color};">{value:.0f} / 100 ({band})</div>
                    <div class="index-scale-ref">0 = minimal stress · 100 = extreme market stress</div>
                    {trend_display}
                    <div class="index-date">Date: {date_str}</div>
                </div>
                
                <div class="index-sections">
                    <div class="index-section">
                        <h2 class="section-header-blue">Primary Risk Drivers:</h2>
                        <ul class="index-list">{drivers_list_html}</ul>
                        <p class="source-attribution" style="font-size: 0.8rem; color: #64748b; margin-top: 0.75rem; font-style: italic;">(Based on recent EnergyRiskIQ alerts) <a href="/alerts" style="color: #2563eb;">View alerts &rarr;</a></p>
                    </div>
                    
                    <div class="index-section">
                        <h2 class="section-header-blue">Chokepoint Watch:</h2>
                        <ul class="index-list">{chokepoints_list_html}</ul>
                    </div>
                </div>
                
                <div class="index-interpretation">
                    <p>{interpretation.replace(chr(10)+chr(10), '</p><p>') if interpretation else 'No interpretation available for this date.'}</p>
                </div>
                
                {date_nav_html}
                
                <div class="index-links">
                    <a href="/egsi">Current EGSI</a>
                    <a href="/egsi/history">Full History</a>
                    <a href="/egsi/methodology">Methodology</a>
                </div>
            </div>
        </main>
        
        <footer class="footer">
            <div class="container">
                <p>&copy; {datetime.now().year} EnergyRiskIQ. <a href="/egsi/methodology">Methodology</a> | <a href="/egsi/history">History</a></p>
            </div>
        </footer>
    </body>
    </html>
    """
    return HTMLResponse(content=html)


@router.get("/egsi/{year}/{month}", response_class=HTMLResponse)
async def egsi_monthly_archive(year: int, month: int):
    """
    EGSI Monthly Archive Page.
    """
    if month < 1 or month > 12:
        raise HTTPException(status_code=404, detail="Invalid month")
    if year < 2024 or year > 2030:
        raise HTTPException(status_code=404, detail="Invalid year")
    
    data = get_egsi_m_monthly_data(year, month)
    if not data:
        month_label = f"{month_name[month]} {year}"
        no_data_html = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>EGSI {month_label} - No Data Available | EnergyRiskIQ</title>
            <meta name="description" content="No Europe Gas Stress Index data available for {month_label}.">
            <link rel="canonical" href="{BASE_URL}/egsi/{year}/{month:02d}">
            <link rel="icon" type="image/png" href="/static/favicon.png">
            {get_common_styles()}
        </head>
        <body>
            <header>
                <div class="container header-content">
                    <a href="/" class="logo">
                        <img src="/static/logo.png" alt="EnergyRiskIQ" style="height: 36px; vertical-align: middle; margin-right: 8px;">
                        EnergyRiskIQ
                    </a>
                    <nav>
                        <a href="/indices/europe-energy-risk-index">EERI</a>
                        <a href="/egsi">EGSI</a>
                        <a href="/alerts">Alerts</a>
                    </nav>
                </div>
            </header>
            
            <div class="container">
                <div class="breadcrumb">
                    <a href="/egsi">EGSI</a> &gt; <a href="/egsi/history">History</a> &gt; {month_label}
                </div>
                
                <div class="index-display" style="margin-top: 40px;">
                    <div style="font-size: 4rem; margin-bottom: 20px;">📅</div>
                    <h1 style="font-size: 1.8rem; margin-bottom: 15px;">No Data for {month_label}</h1>
                    <p class="interpretation">
                        No Europe Gas Stress Index data was recorded for this month.
                        This may be because the month is in the future or before EGSI tracking began.
                    </p>
                    <div style="margin-top: 30px;">
                        <a href="/egsi/history">Browse Available History</a>
                    </div>
                </div>
            </div>
            
            <footer>
                <div class="container">
                    <p>&copy; {datetime.now().year} EnergyRiskIQ</p>
                    <p style="margin-top: 10px;">
                        <a href="/egsi">Current EGSI</a> | 
                        <a href="/egsi/history">History</a> | 
                        <a href="/egsi/methodology">Methodology</a>
                    </p>
                </div>
            </footer>
        </body>
        </html>
        """
        return HTMLResponse(content=no_data_html)
    
    month_label = f"{month_name[month]} {year}"
    
    avg_value = sum(d['value'] for d in data) / len(data) if data else 0
    max_val = max(d['value'] for d in data) if data else 0
    min_val = min(d['value'] for d in data) if data else 0
    
    days_html = ""
    for d in data:
        band_color = get_band_color(d['band'])
        days_html += f"""
        <tr>
            <td><a href="/egsi/{d['date']}">{d['date']}</a></td>
            <td style="color: {band_color}; font-weight: 600;">{d['value']:.0f}</td>
            <td><span class="index-band band-{d['band']}" style="padding: 4px 12px; font-size: 0.8rem;">{d['band']}</span></td>
        </tr>
        """
    
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>EGSI {month_label} - Monthly Archive | EnergyRiskIQ</title>
        <meta name="description" content="Europe Gas Stress Index archive for {month_label}. {len(data)} days of data with average value {avg_value:.1f}.">
        <link rel="canonical" href="{BASE_URL}/egsi/{year}/{month:02d}">
        <link rel="icon" type="image/png" href="/static/favicon.png">
        
        {get_common_styles()}
    </head>
    <body>
        <header>
            <div class="container header-content">
                <a href="/" class="logo">
                    <img src="/static/logo.png" alt="EnergyRiskIQ" style="height: 36px; vertical-align: middle; margin-right: 8px;">
                    EnergyRiskIQ
                </a>
                <nav>
                    <a href="/indices/europe-energy-risk-index">EERI</a>
                    <a href="/egsi">EGSI</a>
                    <a href="/alerts">Alerts</a>
                </nav>
            </div>
        </header>
        
        <div class="container">
            <div class="breadcrumb">
                <a href="/egsi">EGSI</a> &gt; <a href="/egsi/history">History</a> &gt; {month_label}
            </div>
            
            <h1 style="margin: 40px 0 20px;">EGSI - {month_label}</h1>
            
            <div class="grid" style="margin-bottom: 40px;">
                <div class="card">
                    <h3>Days Recorded</h3>
                    <p style="font-size: 2rem; font-weight: 700;">{len(data)}</p>
                </div>
                <div class="card">
                    <h3>Average</h3>
                    <p style="font-size: 2rem; font-weight: 700;">{avg_value:.1f}</p>
                </div>
                <div class="card">
                    <h3>Range</h3>
                    <p style="font-size: 2rem; font-weight: 700;">{min_val:.0f} - {max_val:.0f}</p>
                </div>
            </div>
            
            <div class="card">
                <h2>Daily Values</h2>
                <table>
                    <tr>
                        <th>Date</th>
                        <th>Value</th>
                        <th>Band</th>
                    </tr>
                    {days_html}
                </table>
            </div>
            
            <div class="nav-links" style="margin-top: 40px;">
                <a href="/egsi/history">&larr; Back to History</a>
                <a href="/egsi">Current EGSI &rarr;</a>
            </div>
        </div>
        
        <footer>
            <div class="container">
                <p>&copy; {datetime.now().year} EnergyRiskIQ</p>
            </div>
        </footer>
    </body>
    </html>
    """
    return HTMLResponse(content=html)
