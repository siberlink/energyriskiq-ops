"""
EERI SEO Routes

SEO-optimized public pages for European Energy Risk Index.
- /eeri - Main index page (24h delayed for public)
- /eeri/methodology - Methodology explanation
- /eeri/history - Historical overview
- /eeri/{date} - Daily snapshots
- /eeri/{year}/{month} - Monthly archives
"""

import os
from datetime import datetime, date
from calendar import month_name

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse

from src.reri.eeri_history_service import (
    get_latest_eeri_public,
    get_eeri_delayed,
    get_eeri_by_date,
    get_all_eeri_dates,
    get_eeri_available_months,
    get_eeri_monthly_data,
    get_eeri_adjacent_dates,
    get_eeri_monthly_stats,
)

router = APIRouter(tags=["eeri-seo"])

BASE_URL = os.environ.get('ALERTS_APP_BASE_URL', 'https://energyriskiq.com')


def get_common_styles():
    """Return common CSS styles for EERI pages - GERI standard template."""
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
        
        .assets-grid { display: flex; flex-wrap: wrap; gap: 0.5rem; }
        .asset-tag { background: rgba(96, 165, 250, 0.2); color: #60a5fa; padding: 0.5rem 1rem; border-radius: 8px; font-size: 0.9rem; font-weight: 500; }
        
        .index-interpretation { color: #1f2937; font-size: 1.05rem; font-style: italic; margin: 1.5rem 0; line-height: 1.6; }
        
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
        'MODERATE': '#eab308',
        'ELEVATED': '#f97316',
        'CRITICAL': '#ef4444',
        'SEVERE': '#dc2626',
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


@router.get("/eeri", response_class=HTMLResponse)
async def eeri_public_page(request: Request):
    """
    EERI Main Public Page - SEO anchor page.
    
    Shows 24h delayed EERI with:
    - Today's level, band, trend
    - Interpretation
    - Top 3 risk drivers
    - Affected assets
    - Risk band visualization
    - Methodology summary
    """
    eeri = get_eeri_delayed(delay_hours=24)
    
    if not eeri:
        eeri = get_latest_eeri_public()
    
    if not eeri:
        no_data_html = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>European Energy Risk Index (EERI) | EnergyRiskIQ</title>
            <meta name="description" content="The European Energy Risk Index (EERI) measures systemic geopolitical, supply-chain, and market disruption risks affecting European energy markets.">
            <link rel="canonical" href="{BASE_URL}/eeri">
            <link rel="icon" type="image/png" href="/static/favicon.png">
            {get_common_styles()}
        </head>
        <body>
            <nav class="nav"><div class="container nav-inner">
                <a href="/" class="logo"><img src="/static/logo.png" alt="EnergyRiskIQ" width="32" height="32" style="margin-right: 0.5rem; vertical-align: middle;">EnergyRiskIQ</a>
                <div class="nav-links">
                    <a href="/geri">GERI</a>
                    <a href="/eeri">EERI</a>
                    <a href="/egsi">EGSI</a>
                    <a href="/alerts">Alerts</a>
                    <a href="/users" class="cta-nav">Sign In</a>
                </div>
            </div></nav>
            <main>
                <div class="container">
                    <div class="index-hero">
                        <h1>European Energy Risk Index (EERI)</h1>
                        <p>A daily composite measure of systemic geopolitical and supply-chain risk in European energy markets.</p>
                    </div>
                    <div class="index-metric-card">
                        <p style="color: #9ca3af;">EERI data is being computed. Check back shortly.</p>
                        <p style="margin-top: 1rem;"><a href="/users" class="cta-button primary">Sign up for alerts</a></p>
                    </div>
                </div>
            </main>
            <footer class="footer"><div class="container">&copy; 2026 EnergyRiskIQ</div></footer>
        </body>
        </html>
        """
        return HTMLResponse(content=no_data_html)
    
    band_color = get_band_color(eeri['band'])
    trend_label, trend_sign, trend_color = format_trend(eeri.get('trend_7d'))
    
    trend_html = ""
    if eeri.get('trend_7d') is not None:
        trend_val = eeri['trend_7d']
        trend_html = f'<div class="index-trend" style="color: {trend_color};">7-Day Trend: {trend_label} ({trend_sign}{trend_val})</div>'
    
    drivers_html = ""
    top_drivers = eeri.get('top_drivers', [])[:3]
    for driver in top_drivers:
        if isinstance(driver, dict):
            headline = driver.get('headline', driver.get('title', ''))
        else:
            headline = str(driver)
        if headline:
            drivers_html += f'<li><span class="driver-headline">{headline}</span></li>'
    if not drivers_html:
        drivers_html = '<li><span class="driver-headline">No significant risk drivers detected</span></li>'
    
    assets_html = ""
    for asset in eeri.get('affected_assets', [])[:4]:
        assets_html += f'<span class="asset-tag">{asset}</span>'
    if not assets_html:
        assets_html = '<span class="asset-tag">Natural Gas</span><span class="asset-tag">Crude Oil</span>'
    
    interpretation = eeri.get('interpretation', '')
    if not interpretation:
        interpretation = f"Current EERI of {eeri['value']} indicates {eeri['band'].lower()} structural risk in European energy markets."
    
    current_band = eeri['band']
    band_classes = {
        'LOW': 'low',
        'MODERATE': 'elevated',
        'ELEVATED': 'high',
        'SEVERE': 'severe',
        'CRITICAL': 'critical',
    }
    
    def band_active(band_name):
        return 'active' if current_band == band_name else ''
    
    index_date = eeri.get('date', date.today().isoformat())
    computed_at = eeri.get('computed_at', '')
    if computed_at:
        try:
            computed_dt = datetime.fromisoformat(computed_at.replace('Z', '+00:00'))
            computed_display = computed_dt.strftime('%B %d, %Y, %H:%M UTC')
        except:
            computed_display = computed_at
    else:
        computed_display = 'Daily at 01:00 UTC'
    
    trend_display = ""
    if eeri.get('trend_7d') is not None:
        trend_val = eeri['trend_7d']
        trend_sign = "+" if trend_val > 0 else ""
        trend_display = f'<div class="index-trend" style="color: #4ade80;">7-Day Trend: {trend_label} ({trend_sign}{trend_val:.0f})</div>'
    
    delay_badge = '<div class="index-delay-badge">24h delayed • Real-time access with subscription</div>'
    
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>European Energy Risk Index (EERI) | EnergyRiskIQ</title>
        <meta name="description" content="Track the European Energy Risk Index (EERI) - a daily measure of geopolitical and supply-chain risks affecting European energy markets. Current level: {eeri['value']} ({eeri['band']}).">
        <link rel="canonical" href="{BASE_URL}/eeri">
        
        <meta property="og:title" content="European Energy Risk Index (EERI) | EnergyRiskIQ">
        <meta property="og:description" content="European Energy Risk Index: {eeri['value']} - {eeri['band']}. Track geopolitical and supply-chain risks affecting European energy markets.">
        <meta property="og:url" content="{BASE_URL}/eeri">
        <meta property="og:type" content="website">
        
        <link rel="icon" type="image/png" href="/static/favicon.png">
        {get_common_styles()}
    </head>
    <body>
        <nav class="nav"><div class="container nav-inner">
            <a href="/" class="logo"><img src="/static/logo.png" alt="EnergyRiskIQ" width="32" height="32" style="margin-right: 0.5rem; vertical-align: middle;">EnergyRiskIQ</a>
            <div class="nav-links">
                <a href="/geri">GERI</a>
                <a href="/eeri">EERI</a>
                <a href="/egsi">EGSI</a>
                <a href="/alerts">Alerts</a>
                <a href="/users" class="cta-nav">Sign In</a>
            </div>
        </div></nav>
        
        <main>
            <div class="container">
                <div class="index-hero">
                    <h1>European Energy Risk Index (EERI)</h1>
                    <p>A daily composite measure of systemic geopolitical and supply-chain risk in European energy markets.</p>
                    <p class="methodology-link"><a href="/eeri/methodology">(EERI Methodology & Construction)</a></p>
                </div>
                
                <div class="index-metric-card">
                    <div class="index-header">
                        <span class="index-icon">⚡</span>
                        <span class="index-title">European Energy Risk Index:</span>
                    </div>
                    <div class="index-value" style="color: {band_color};">{eeri['value']} / 100 ({eeri['band']})</div>
                    <div class="index-scale-ref">0 = minimal risk · 100 = extreme systemic stress</div>
                    {trend_display}
                    <div class="index-date">Date Computed: {index_date}</div>
                </div>
                
                <div class="index-sections">
                    <div class="index-section">
                        <h2 class="section-header-blue">Primary Risk Drivers:</h2>
                        <ul class="index-list">{drivers_html}</ul>
                    </div>
                    
                    <div class="index-section">
                        <h2 class="section-header-blue">Top Regions Under Pressure:</h2>
                        <ul class="index-list regions-list">
                            <li>Europe <span class="region-label">(Primary)</span></li>
                            <li>Black Sea <span class="region-label">(Secondary)</span></li>
                            <li>Middle East <span class="region-label">(Tertiary)</span></li>
                        </ul>
                    </div>
                </div>
                
                <div class="index-section" style="margin: 1.5rem 0;">
                    <h2 class="section-header-blue">Assets Most Affected:</h2>
                    <div class="assets-grid">
                        {assets_html}
                    </div>
                </div>
                
                <div class="index-interpretation">
                    <em>{interpretation}</em>
                </div>
                
                {delay_badge}
                
                <div class="index-cta">
                    <h3>Get Real-time Access</h3>
                    <p>Unlock instant EERI updates with a Pro subscription.</p>
                    <a href="/users" class="cta-button primary">Unlock Real-time EERI</a>
                    <a href="/alerts" class="cta-button secondary">See Alert Archive</a>
                </div>
                
                <div class="index-links">
                    <a href="/eeri/history">EERI History</a>
                    <a href="/eeri/methodology">Methodology</a>
                </div>
            </div>
        </main>
        
        <footer class="footer">
            <div class="container">
                <p>&copy; 2026 EnergyRiskIQ. All rights reserved.</p>
                <p style="margin-top: 0.5rem;">
                    <a href="/eeri/history">EERI History</a> · 
                    <a href="/eeri/methodology">Methodology</a> · 
                    <a href="/geri">GERI</a> · 
                    <a href="/alerts">Alerts</a>
                </p>
            </div>
        </footer>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html)


@router.get("/eeri/methodology", response_class=HTMLResponse)
async def eeri_methodology_page():
    """
    EERI Methodology Page - SEO content explaining the index.
    """
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>EERI Methodology - European Energy Risk Index | EnergyRiskIQ</title>
        <meta name="description" content="Learn how the European Energy Risk Index (EERI) is calculated. Understand the methodology behind measuring geopolitical and supply-chain risks in European energy markets.">
        <link rel="canonical" href="{BASE_URL}/eeri/methodology">
        
        <meta property="og:title" content="EERI Methodology | EnergyRiskIQ">
        <meta property="og:description" content="Methodology and calculation approach for the European Energy Risk Index (EERI).">
        <meta property="og:url" content="{BASE_URL}/eeri/methodology">
        
        <link rel="icon" type="image/png" href="/static/favicon.png">
        {get_common_styles()}
        <style>
            .methodology-content {{ line-height: 1.9; color: var(--text-secondary); }}
            .methodology-content h3 {{ color: var(--text-primary); margin-top: 1.5rem; margin-bottom: 0.75rem; }}
            .methodology-content p {{ margin-bottom: 1rem; }}
            .methodology-content ul {{ margin-left: 1.5rem; margin-bottom: 1rem; }}
            .methodology-content li {{ margin-bottom: 0.5rem; }}
            .component-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin: 1.5rem 0; }}
            .component-card {{ background: var(--bg-light); padding: 1rem; border-radius: 8px; text-align: center; }}
            .component-name {{ font-weight: 600; color: var(--text-primary); }}
            .component-desc {{ font-size: 0.85rem; color: var(--text-secondary); margin-top: 0.5rem; }}
        </style>
    </head>
    <body>
        <nav class="nav"><div class="container nav-inner">
            <a href="/" class="logo"><img src="/static/logo.png" alt="EnergyRiskIQ" width="32" height="32" style="margin-right: 0.5rem; vertical-align: middle;">EnergyRiskIQ</a>
            <div class="nav-links">
                <a href="/alerts">Alerts</a>
                <a href="/geri">GERI</a>
                <a href="/eeri">EERI</a>
            </div>
        </div></nav>
        
        <main class="container">
            <div class="hero">
                <h1>EERI Methodology</h1>
                <p class="subtitle">How the European Energy Risk Index is calculated</p>
            </div>
            
            <div class="section methodology-content">
                <h2>Overview</h2>
                <p>
                    The European Energy Risk Index (EERI) is a composite daily indicator measuring systemic risk exposure in European energy markets. It synthesizes multiple signal sources into a single 0-100 score, enabling institutional users to quickly assess market conditions.
                </p>
                
                <h3>Core Components</h3>
                <p>EERI aggregates four primary risk signal categories:</p>
                
                <div class="component-grid">
                    <div class="component-card">
                        <div class="component-name">Regional Risk</div>
                        <div class="component-desc">Base pressure from European-specific events</div>
                    </div>
                    <div class="component-card">
                        <div class="component-name">Thematic Pressure</div>
                        <div class="component-desc">Weighted severity by event category</div>
                    </div>
                    <div class="component-card">
                        <div class="component-name">Asset Transmission</div>
                        <div class="component-desc">Cross-asset risk propagation signals</div>
                    </div>
                    <div class="component-card">
                        <div class="component-name">Contagion Risk</div>
                        <div class="component-desc">Spillover from neighboring regions</div>
                    </div>
                </div>
                
                <h3>Risk Bands</h3>
                <p>The final index value maps to interpretable risk bands:</p>
                <ul>
                    <li><strong>0-25 (Normal):</strong> Markets operating within normal parameters</li>
                    <li><strong>26-50 (Elevated):</strong> Heightened vigilance recommended</li>
                    <li><strong>51-75 (High):</strong> Active risk management advised</li>
                    <li><strong>76-90 (Severe):</strong> Significant disruption risk present</li>
                    <li><strong>91-100 (Critical):</strong> Extreme systemic stress conditions</li>
                </ul>
                
                <h3>Data Sources</h3>
                <p>
                    EERI draws from EnergyRiskIQ's proprietary alert stream, which monitors geopolitical events, supply-chain disruptions, and market signals across European and adjacent regions. Events are classified, scored for severity and confidence, and aggregated into the daily index.
                </p>
                
                <h3>Update Schedule</h3>
                <p>
                    EERI is computed daily at 01:00 UTC, incorporating all alerts from the previous 24-hour period. Public access shows data with a 24-hour delay; real-time access is available to Pro subscribers.
                </p>
                
                <h3>Use Cases</h3>
                <ul>
                    <li>Portfolio risk monitoring for energy sector exposure</li>
                    <li>Trading desk situational awareness</li>
                    <li>Policy research and analysis</li>
                    <li>Supply chain risk management</li>
                    <li>Benchmark for risk reporting</li>
                </ul>
            </div>
            
            <div class="cta-section">
                <h3>Access Full Analysis</h3>
                <p>Get component-level breakdowns, historical data, and real-time updates with EnergyRiskIQ Pro.</p>
                <a href="/users" class="cta-btn">Explore Pro Features</a>
            </div>
        </main>
        
        <footer class="footer">
            <div class="container">
                <p>&copy; 2026 EnergyRiskIQ</p>
                <p style="margin-top: 0.5rem;">
                    <a href="/eeri">EERI Index</a> · <a href="/eeri/history">History</a> · <a href="/geri">GERI</a>
                </p>
            </div>
        </footer>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html)


@router.get("/eeri/history", response_class=HTMLResponse)
async def eeri_history_page():
    """
    EERI History Page - Overview of historical data with links to archives.
    Public page showing the official published archive (24h delayed).
    """
    dates = get_all_eeri_dates(public_only=True)
    months = get_eeri_available_months(public_only=True)
    
    rows_html = ""
    for d in dates[:90]:
        rows_html += f"""
        <tr>
            <td><a href="/eeri/{d}">{d}</a></td>
        </tr>
        """
    if not rows_html:
        rows_html = '<tr><td style="text-align: center; color: #9ca3af;">No history available yet.</td></tr>'
    
    months_html = ""
    for m in months[:24]:
        month_display = f"{month_name[m['month']]} {m['year']}"
        months_html += f"""
        <div class="month-card">
            <a href="/eeri/{m['year']}/{m['month']:02d}">{month_display}</a>
            <div style="color: #9ca3af; font-size: 0.875rem;">{m['count']} days</div>
        </div>
        """
    if not months_html:
        months_html = '<p style="color: #9ca3af;">No monthly archives available yet.</p>'
    
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>European Energy Risk Index History | EnergyRiskIQ</title>
        <meta name="description" content="Complete history of the European Energy Risk Index (EERI). Browse daily snapshots and monthly archives of European energy market risk data.">
        <link rel="canonical" href="{BASE_URL}/eeri/history">
        <link rel="icon" type="image/png" href="/static/favicon.png">
        {get_common_styles()}
        <style>
            .container {{ max-width: 1000px; margin: 0 auto; padding: 0 1rem; }}
            .breadcrumbs {{ margin: 1rem 0; color: #9ca3af; font-size: 0.875rem; }}
            .breadcrumbs a {{ color: #60a5fa; text-decoration: none; }}
            .breadcrumbs a:hover {{ text-decoration: underline; }}
            h1 {{ font-size: 2rem; color: #1a1a2e; margin-bottom: 0.5rem; }}
            h2 {{ font-size: 1.25rem; color: #1a1a2e; margin: 2rem 0 1rem; }}
            .month-grid {{ 
                display: grid; 
                grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); 
                gap: 1rem; 
                margin-bottom: 2rem;
            }}
            .month-card {{
                background: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 1rem;
                text-align: center;
            }}
            .month-card a {{
                color: #2563eb;
                text-decoration: none;
                font-weight: 500;
            }}
            .month-card a:hover {{ text-decoration: underline; }}
            .eeri-table {{
                width: 100%;
                border-collapse: collapse;
                margin-top: 1rem;
            }}
            .eeri-table th, .eeri-table td {{
                padding: 0.75rem 1rem;
                text-align: left;
                border-bottom: 1px solid #e2e8f0;
            }}
            .eeri-table th {{
                background: #f8fafc;
                font-weight: 600;
                color: #475569;
            }}
            .eeri-table a {{
                color: #2563eb;
                text-decoration: none;
            }}
            .eeri-table a:hover {{ text-decoration: underline; }}
        </style>
    </head>
    <body>
        <nav class="nav"><div class="container nav-inner">
            <a href="/" class="logo"><img src="/static/logo.png" alt="EnergyRiskIQ" width="32" height="32" style="margin-right: 0.5rem; vertical-align: middle;">EnergyRiskIQ</a>
            <div class="nav-links">
                <a href="/geri">GERI</a>
                <a href="/eeri">EERI</a>
                <a href="/egsi">EGSI</a>
                <a href="/alerts">Alerts</a>
                <a href="/users" class="cta-nav">Sign In</a>
            </div>
        </div></nav>
        <main>
            <div class="container">
                <div class="breadcrumbs">
                    <a href="/eeri">EERI</a> &raquo; History
                </div>
                
                <h1>European Energy Risk Index (EERI) History</h1>
                <p style="color: #9ca3af; margin-bottom: 2rem;">
                    The official published archive of daily EERI snapshots. 
                    Each snapshot represents the computed European energy market risk for that day.
                </p>
                
                <h2>Monthly Archives</h2>
                <div class="month-grid">
                    {months_html}
                </div>
                
                <h2>Recent Snapshots</h2>
                <table class="eeri-table">
                    <thead>
                        <tr>
                            <th>Date</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows_html}
                    </tbody>
                </table>
                
                <div style="text-align: center; margin-top: 2rem;">
                    <a href="/eeri" style="color: #60a5fa;">Back to Today's EERI</a>
                </div>
            </div>
        </main>
        <footer class="footer"><div class="container">&copy; 2026 EnergyRiskIQ</div></footer>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html, headers={"Cache-Control": "public, max-age=3600"})


@router.get("/eeri/{date_str}", response_class=HTMLResponse)
async def eeri_daily_snapshot(date_str: str):
    """
    EERI Daily Snapshot Page.
    """
    if '/' in date_str or len(date_str) < 8:
        raise HTTPException(status_code=404, detail="Invalid date format")
    
    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        raise HTTPException(status_code=404, detail="Invalid date format. Use YYYY-MM-DD.")
    
    eeri = get_eeri_by_date(target_date)
    if not eeri:
        raise HTTPException(status_code=404, detail=f"No EERI data for {date_str}")
    
    adjacent = get_eeri_adjacent_dates(target_date)
    
    band_color = get_band_color(eeri['band'])
    date_display = target_date.strftime('%B %d, %Y')
    
    drivers_html = ""
    for driver in eeri.get('top_drivers', [])[:3]:
        if isinstance(driver, dict):
            headline = driver.get('headline', driver.get('title', ''))
        else:
            headline = str(driver)
        if headline:
            drivers_html += f'<li><span class="driver-headline">{headline}</span></li>'
    if not drivers_html:
        drivers_html = '<li>No significant drivers</li>'
    
    nav_html = '<div style="display: flex; justify-content: space-between; margin: 1.5rem 0;">'
    if adjacent.get('prev'):
        nav_html += f'<a href="/eeri/{adjacent["prev"]}" style="color: var(--primary); text-decoration: none;">&larr; {adjacent["prev"]}</a>'
    else:
        nav_html += '<span></span>'
    if adjacent.get('next'):
        nav_html += f'<a href="/eeri/{adjacent["next"]}" style="color: var(--primary); text-decoration: none;">{adjacent["next"]} &rarr;</a>'
    else:
        nav_html += '<span></span>'
    nav_html += '</div>'
    
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>EERI {date_str} - European Energy Risk Index | EnergyRiskIQ</title>
        <meta name="description" content="European Energy Risk Index for {date_display}. Value: {eeri['value']}, Band: {eeri['band']}. Historical EERI data.">
        <link rel="canonical" href="{BASE_URL}/eeri/{date_str}">
        <link rel="icon" type="image/png" href="/static/favicon.png">
        {get_common_styles()}
    </head>
    <body>
        <nav class="nav"><div class="container nav-inner">
            <a href="/" class="logo"><img src="/static/logo.png" alt="EnergyRiskIQ" width="32" height="32" style="margin-right: 0.5rem; vertical-align: middle;">EnergyRiskIQ</a>
            <div class="nav-links">
                <a href="/alerts">Alerts</a>
                <a href="/geri">GERI</a>
                <a href="/eeri">EERI</a>
            </div>
        </div></nav>
        
        <main class="container">
            <div class="hero">
                <h1>EERI: {date_display}</h1>
                <p class="subtitle">European Energy Risk Index historical snapshot</p>
            </div>
            
            <div class="index-card">
                <div class="index-value" style="color: {band_color};">{eeri['value']}</div>
                <div class="index-band" style="color: {band_color};">{eeri['band']}</div>
                <div class="index-scale">0 = minimal risk · 100 = extreme systemic stress</div>
            </div>
            
            <div class="section">
                <h2>Risk Assessment</h2>
                <p class="interpretation">{eeri.get('interpretation', f"EERI of {eeri['value']} indicated {eeri['band'].lower()} risk conditions.")}</p>
            </div>
            
            <div class="section">
                <h2>Top Risk Drivers</h2>
                <ul class="drivers-list">{drivers_html}</ul>
            </div>
            
            {nav_html}
            
            <div style="text-align: center; margin: 1rem 0;">
                <a href="/eeri/history" style="color: var(--primary); text-decoration: none;">View Full History</a> · 
                <a href="/eeri" style="color: var(--primary); text-decoration: none;">Current EERI</a>
            </div>
        </main>
        
        <footer class="footer"><div class="container">&copy; 2026 EnergyRiskIQ</div></footer>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html)


@router.get("/eeri/{year}/{month}", response_class=HTMLResponse)
async def eeri_monthly_archive(year: int, month: int):
    """
    EERI Monthly Archive Page.
    """
    if month < 1 or month > 12:
        raise HTTPException(status_code=404, detail="Invalid month")
    if year < 2024 or year > 2030:
        raise HTTPException(status_code=404, detail="Invalid year")
    
    data = get_eeri_monthly_data(year, month)
    if not data:
        raise HTTPException(status_code=404, detail=f"No EERI data for {month_name[month]} {year}")
    
    month_label = f"{month_name[month]} {year}"
    
    avg_value = sum(d['value'] for d in data) / len(data) if data else 0
    max_val = max(d['value'] for d in data) if data else 0
    min_val = min(d['value'] for d in data) if data else 0
    
    days_html = ""
    for d in data:
        band_color = get_band_color(d['band'])
        days_html += f"""
        <tr>
            <td><a href="/eeri/{d['date']}" style="color: var(--primary); text-decoration: none;">{d['date']}</a></td>
            <td style="font-weight: 600; color: {band_color};">{d['value']}</td>
            <td style="color: {band_color};">{d['band']}</td>
        </tr>
        """
    
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>EERI {month_label} - European Energy Risk Index Archive | EnergyRiskIQ</title>
        <meta name="description" content="European Energy Risk Index data for {month_label}. {len(data)} days of EERI historical data with daily values and risk bands.">
        <link rel="canonical" href="{BASE_URL}/eeri/{year}/{month:02d}">
        <link rel="icon" type="image/png" href="/static/favicon.png">
        {get_common_styles()}
        <style>
            .data-table {{ width: 100%; border-collapse: collapse; }}
            .data-table th, .data-table td {{ padding: 0.75rem; text-align: left; border-bottom: 1px solid var(--border); }}
            .data-table th {{ background: var(--bg-light); font-weight: 600; color: var(--text-secondary); font-size: 0.85rem; text-transform: uppercase; }}
        </style>
    </head>
    <body>
        <nav class="nav"><div class="container nav-inner">
            <a href="/" class="logo"><img src="/static/logo.png" alt="EnergyRiskIQ" width="32" height="32" style="margin-right: 0.5rem; vertical-align: middle;">EnergyRiskIQ</a>
            <div class="nav-links">
                <a href="/alerts">Alerts</a>
                <a href="/geri">GERI</a>
                <a href="/eeri">EERI</a>
            </div>
        </div></nav>
        
        <main class="container">
            <div class="hero">
                <h1>EERI: {month_label}</h1>
                <p class="subtitle">Monthly archive of European Energy Risk Index</p>
            </div>
            
            <div class="section">
                <h2>Monthly Summary</h2>
                <div class="meta-info">
                    <div class="meta-item">
                        <div class="meta-label">Days Recorded</div>
                        <div class="meta-value">{len(data)}</div>
                    </div>
                    <div class="meta-item">
                        <div class="meta-label">Average Value</div>
                        <div class="meta-value">{avg_value:.0f}</div>
                    </div>
                    <div class="meta-item">
                        <div class="meta-label">Range</div>
                        <div class="meta-value">{min_val} - {max_val}</div>
                    </div>
                </div>
            </div>
            
            <div class="section">
                <h2>Daily Values</h2>
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>Date</th>
                            <th>Value</th>
                            <th>Band</th>
                        </tr>
                    </thead>
                    <tbody>
                        {days_html}
                    </tbody>
                </table>
            </div>
            
            <div style="text-align: center; margin: 2rem 0;">
                <a href="/eeri/history" style="color: var(--primary); text-decoration: none;">&larr; Back to History</a> · 
                <a href="/eeri" style="color: var(--primary); text-decoration: none;">Current EERI</a>
            </div>
        </main>
        
        <footer class="footer"><div class="container">&copy; 2026 EnergyRiskIQ</div></footer>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html)
