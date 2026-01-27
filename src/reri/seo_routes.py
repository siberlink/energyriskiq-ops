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
    """Return common CSS styles for EERI pages."""
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
            --band-low: #22C55E;
            --band-moderate: #EAB308;
            --band-elevated: #F97316;
            --band-critical: #EF4444;
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
        .logo {
            font-weight: 700;
            font-size: 1.25rem;
            color: var(--secondary);
            text-decoration: none;
        }
        .nav-links { display: flex; gap: 1.5rem; }
        .nav-links a { color: var(--text-secondary); text-decoration: none; font-size: 0.95rem; }
        .nav-links a:hover { color: var(--primary); }
        
        .hero { text-align: center; padding: 2rem 0 1rem; }
        .hero h1 { font-size: 2rem; margin-bottom: 0.5rem; color: var(--secondary); }
        .hero .subtitle { color: var(--text-secondary); max-width: 600px; margin: 0 auto; }
        
        .index-card {
            background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
            border-radius: 12px;
            padding: 2rem;
            margin: 1.5rem 0;
            color: white;
            text-align: center;
        }
        .index-value { font-size: 4rem; font-weight: 800; line-height: 1; }
        .index-band { font-size: 1.5rem; font-weight: 600; margin-top: 0.5rem; }
        .index-trend { font-size: 1rem; color: #94a3b8; margin-top: 0.5rem; }
        .index-scale { font-size: 0.85rem; color: #64748b; margin-top: 1rem; }
        .index-date { font-size: 0.85rem; color: #94a3b8; margin-top: 0.5rem; }
        .delay-badge {
            display: inline-block;
            background: rgba(234, 179, 8, 0.2);
            color: #fbbf24;
            font-size: 0.75rem;
            padding: 0.25rem 0.75rem;
            border-radius: 999px;
            margin-top: 1rem;
        }
        
        .section { background: white; border-radius: 12px; padding: 1.5rem; margin: 1.5rem 0; border: 1px solid var(--border); }
        .section h2 { font-size: 1.25rem; color: var(--secondary); margin-bottom: 1rem; border-bottom: 2px solid var(--primary); padding-bottom: 0.5rem; }
        .section h3 { font-size: 1.1rem; color: var(--secondary); margin-bottom: 0.75rem; }
        
        .interpretation { font-style: italic; color: var(--text-secondary); line-height: 1.7; font-size: 1.05rem; }
        
        .risk-bands { display: grid; grid-template-columns: repeat(5, 1fr); gap: 0.5rem; margin: 1rem 0; }
        .band-item { text-align: center; padding: 0.75rem 0.5rem; border-radius: 8px; font-size: 0.8rem; }
        .band-item.low { background: rgba(34, 197, 94, 0.15); color: #16a34a; }
        .band-item.elevated { background: rgba(234, 179, 8, 0.15); color: #ca8a04; }
        .band-item.high { background: rgba(249, 115, 22, 0.15); color: #ea580c; }
        .band-item.severe { background: rgba(239, 68, 68, 0.15); color: #dc2626; }
        .band-item.critical { background: rgba(220, 38, 38, 0.2); color: #b91c1c; }
        .band-item.active { border: 2px solid currentColor; font-weight: 700; }
        .band-range { font-size: 0.7rem; opacity: 0.8; margin-top: 0.25rem; }
        
        .drivers-list { list-style: none; }
        .drivers-list li { padding: 0.75rem 0; border-bottom: 1px solid var(--border); }
        .drivers-list li:last-child { border-bottom: none; }
        .driver-headline { font-weight: 500; color: var(--text-primary); }
        
        .assets-grid { display: flex; flex-wrap: wrap; gap: 0.5rem; }
        .asset-tag { background: rgba(0, 102, 255, 0.1); color: var(--primary); padding: 0.5rem 1rem; border-radius: 8px; font-size: 0.9rem; font-weight: 500; }
        
        .meta-info { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; }
        .meta-item { }
        .meta-label { font-size: 0.8rem; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.05em; }
        .meta-value { font-weight: 600; color: var(--text-primary); margin-top: 0.25rem; }
        
        .cta-section { background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%); color: white; border-radius: 12px; padding: 2rem; text-align: center; margin: 2rem 0; }
        .cta-section h3 { font-size: 1.25rem; margin-bottom: 0.5rem; }
        .cta-section p { opacity: 0.9; margin-bottom: 1rem; }
        .cta-btn { display: inline-block; background: white; color: var(--primary); padding: 0.75rem 1.5rem; border-radius: 8px; text-decoration: none; font-weight: 600; }
        .cta-btn:hover { background: #f1f5f9; }
        
        .footer { text-align: center; padding: 2rem 0; color: var(--text-secondary); font-size: 0.85rem; }
        .footer a { color: var(--primary); text-decoration: none; }
        
        @media (max-width: 640px) {
            .hero h1 { font-size: 1.5rem; }
            .index-value { font-size: 3rem; }
            .risk-bands { grid-template-columns: repeat(3, 1fr); }
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
                <a href="/" class="logo">EnergyRiskIQ</a>
                <div class="nav-links">
                    <a href="/alerts">Alerts</a>
                    <a href="/geri">GERI</a>
                    <a href="/eeri">EERI</a>
                </div>
            </div></nav>
            <main class="container">
                <div class="hero">
                    <h1>European Energy Risk Index (EERI)</h1>
                    <p class="subtitle">EERI data is being computed. Check back shortly.</p>
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
            <a href="/" class="logo">EnergyRiskIQ</a>
            <div class="nav-links">
                <a href="/alerts">Alerts</a>
                <a href="/geri">GERI</a>
                <a href="/eeri">EERI</a>
            </div>
        </div></nav>
        
        <main class="container">
            <div class="hero">
                <h1>European Energy Risk Index (EERI)</h1>
                <p class="subtitle">Daily measure of systemic disruption risk in European energy markets</p>
            </div>
            
            <!-- Block 1: Today's Index -->
            <div class="index-card">
                <div class="index-value" style="color: {band_color};">{eeri['value']}</div>
                <div class="index-band" style="color: {band_color};">{eeri['band']}</div>
                {trend_html}
                <div class="index-scale">0 = minimal risk · 100 = extreme systemic stress</div>
                <div class="index-date">Index Date: {index_date}</div>
                <span class="delay-badge">24h Delayed</span>
            </div>
            
            <!-- Block: Interpretation -->
            <div class="section">
                <h2>Risk Assessment</h2>
                <p class="interpretation">{interpretation}</p>
            </div>
            
            <!-- Block 2: Risk Band Visualization -->
            <div class="section">
                <h2>Risk Level Bands</h2>
                <div class="risk-bands">
                    <div class="band-item low {band_active('LOW')}">
                        <div>Normal</div>
                        <div class="band-range">0-25</div>
                    </div>
                    <div class="band-item elevated {band_active('MODERATE')}">
                        <div>Elevated</div>
                        <div class="band-range">26-50</div>
                    </div>
                    <div class="band-item high {band_active('ELEVATED')}">
                        <div>High</div>
                        <div class="band-range">51-75</div>
                    </div>
                    <div class="band-item severe {band_active('SEVERE')}">
                        <div>Severe</div>
                        <div class="band-range">76-90</div>
                    </div>
                    <div class="band-item critical {band_active('CRITICAL')}">
                        <div>Critical</div>
                        <div class="band-range">91-100</div>
                    </div>
                </div>
                <p style="text-align: center; color: var(--text-secondary); font-size: 0.9rem; margin-top: 1rem;">
                    Current position: <strong style="color: {band_color};">{eeri['band']} ({eeri['value']})</strong>
                </p>
            </div>
            
            <!-- Block 3: Top Risk Drivers -->
            <div class="section">
                <h2>Top Risk Drivers Today</h2>
                <ul class="drivers-list">
                    {drivers_html}
                </ul>
            </div>
            
            <!-- Block 4: Assets Affected -->
            <div class="section">
                <h2>Assets Most Affected Today</h2>
                <div class="assets-grid">
                    {assets_html}
                </div>
            </div>
            
            <!-- Block 5: Update Metadata -->
            <div class="section">
                <h2>Index Information</h2>
                <div class="meta-info">
                    <div class="meta-item">
                        <div class="meta-label">Index Date</div>
                        <div class="meta-value">{index_date}</div>
                    </div>
                    <div class="meta-item">
                        <div class="meta-label">Computed At</div>
                        <div class="meta-value">{computed_display}</div>
                    </div>
                    <div class="meta-item">
                        <div class="meta-label">Update Frequency</div>
                        <div class="meta-value">Daily</div>
                    </div>
                </div>
            </div>
            
            <!-- Block 6: What is EERI -->
            <div class="section">
                <h2>What is the European Energy Risk Index (EERI)?</h2>
                <p style="color: var(--text-secondary); line-height: 1.8;">
                    The European Energy Risk Index (EERI) measures systemic geopolitical, supply-chain, and market disruption risks affecting European energy markets. It aggregates high-impact events, asset transmission signals, and thematic pressures into a daily risk score designed for analysts, traders, and policy professionals.
                </p>
                <p style="margin-top: 1rem;">
                    <a href="/eeri/methodology" style="color: var(--primary); text-decoration: none;">Learn more about EERI methodology &rarr;</a>
                </p>
            </div>
            
            <!-- Block 7: CTA -->
            <div class="cta-section">
                <h3>Access Full EERI Components</h3>
                <p>Unlock real-time data, historical charts, and detailed component analysis with EnergyRiskIQ Pro.</p>
                <a href="/users" class="cta-btn">Unlock Real-time Access</a>
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
            <a href="/" class="logo">EnergyRiskIQ</a>
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
    """
    dates = get_all_eeri_dates()
    months = get_eeri_available_months()
    stats = get_eeri_monthly_stats()
    
    recent_dates_html = ""
    for d in dates[:14]:
        recent_dates_html += f'<li><a href="/eeri/{d}">{d}</a></li>'
    if not recent_dates_html:
        recent_dates_html = '<li>No historical data available yet</li>'
    
    months_html = ""
    for m in months[:12]:
        month_label = f"{month_name[m['month']]} {m['year']}"
        months_html += f'<li><a href="/eeri/{m["year"]}/{m["month"]:02d}">{month_label}</a> ({m["count"]} days)</li>'
    if not months_html:
        months_html = '<li>No monthly archives available yet</li>'
    
    stats_html = ""
    if stats:
        stats_html = f"""
        <div class="section">
            <h2>Historical Statistics</h2>
            <div class="meta-info">
                <div class="meta-item">
                    <div class="meta-label">Total Days</div>
                    <div class="meta-value">{stats.get('total_days', 0)}</div>
                </div>
                <div class="meta-item">
                    <div class="meta-label">Average Value</div>
                    <div class="meta-value">{stats.get('avg_value', 0)}</div>
                </div>
                <div class="meta-item">
                    <div class="meta-label">Range</div>
                    <div class="meta-value">{stats.get('min_value', 0)} - {stats.get('max_value', 0)}</div>
                </div>
                <div class="meta-item">
                    <div class="meta-label">First Record</div>
                    <div class="meta-value">{stats.get('first_date', 'N/A')}</div>
                </div>
            </div>
        </div>
        """
    
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>EERI History - European Energy Risk Index Archive | EnergyRiskIQ</title>
        <meta name="description" content="Historical archive of the European Energy Risk Index (EERI). Browse daily snapshots and monthly summaries of European energy market risk levels.">
        <link rel="canonical" href="{BASE_URL}/eeri/history">
        <link rel="icon" type="image/png" href="/static/favicon.png">
        {get_common_styles()}
        <style>
            .history-list {{ list-style: none; }}
            .history-list li {{ padding: 0.5rem 0; border-bottom: 1px solid var(--border); }}
            .history-list li:last-child {{ border-bottom: none; }}
            .history-list a {{ color: var(--primary); text-decoration: none; }}
            .history-list a:hover {{ text-decoration: underline; }}
            .two-column {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; }}
            @media (max-width: 640px) {{ .two-column {{ grid-template-columns: 1fr; }} }}
        </style>
    </head>
    <body>
        <nav class="nav"><div class="container nav-inner">
            <a href="/" class="logo">EnergyRiskIQ</a>
            <div class="nav-links">
                <a href="/alerts">Alerts</a>
                <a href="/geri">GERI</a>
                <a href="/eeri">EERI</a>
            </div>
        </div></nav>
        
        <main class="container">
            <div class="hero">
                <h1>EERI History</h1>
                <p class="subtitle">Historical archive of European Energy Risk Index data</p>
            </div>
            
            {stats_html}
            
            <div class="two-column">
                <div class="section">
                    <h2>Recent Daily Snapshots</h2>
                    <ul class="history-list">
                        {recent_dates_html}
                    </ul>
                </div>
                
                <div class="section">
                    <h2>Monthly Archives</h2>
                    <ul class="history-list">
                        {months_html}
                    </ul>
                </div>
            </div>
            
            <div style="text-align: center; margin: 2rem 0;">
                <a href="/eeri" style="color: var(--primary); text-decoration: none;">&larr; Back to Current EERI</a>
            </div>
        </main>
        
        <footer class="footer">
            <div class="container">
                <p>&copy; 2026 EnergyRiskIQ</p>
            </div>
        </footer>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html)


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
            <a href="/" class="logo">EnergyRiskIQ</a>
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
            <a href="/" class="logo">EnergyRiskIQ</a>
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
