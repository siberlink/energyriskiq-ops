"""
EGSI SEO Routes

Public-facing SEO-optimized pages for the Europe Gas Stress Index (EGSI-M).
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
from src.egsi.interpretation import generate_egsi_interpretation

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
    
    Shows 24h delayed EGSI-M with:
    - Today's level, band, trend
    - Interpretation
    - Top drivers
    - Chokepoint watch
    - Risk band visualization
    """
    egsi = get_egsi_m_delayed(delay_hours=24)
    
    if not egsi:
        egsi = get_latest_egsi_m_public()
    
    if not egsi:
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
                        <h1>Europe Gas Stress Index (EGSI)</h1>
                        <p>A daily composite measure of gas market transmission stress across European infrastructure.</p>
                    </div>
                    <div class="index-metric-card">
                        <p style="color: #9ca3af;">EGSI data is being computed. Check back shortly.</p>
                        <p style="margin-top: 1rem;"><a href="/users" class="cta-button primary">Sign up for alerts</a></p>
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
        return HTMLResponse(content=no_data_html)
    
    value = egsi.get('value', 0)
    band = egsi.get('band', 'LOW')
    trend_7d = egsi.get('trend_7d')
    date_str = egsi.get('date', 'N/A')
    drivers = egsi.get('drivers', [])[:5]
    components = egsi.get('components', {})
    
    # Use stored interpretation (unique per day), fallback to generation only if missing
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
    
    band_color = get_band_color(band)
    trend_label, trend_sign, trend_color = format_trend(trend_7d)
    
    drivers_html = ""
    for driver in drivers:
        drivers_html += f"""
        <div class="card">
            <h3>{driver.get('name', 'Unknown')}</h3>
            <p>Type: {driver.get('type', 'N/A')}</p>
            <p>Contribution: {driver.get('contribution', 0):.1f}%</p>
        </div>
        """
    if not drivers_html:
        drivers_html = '<div class="card"><p>No significant drivers detected.</p></div>'
    
    chokepoints = components.get('chokepoint_factor', {}).get('hits', []) if isinstance(components, dict) else []
    chokepoints_html = ""
    for cp in chokepoints[:3]:
        chokepoints_html += f'<li>{cp}</li>'
    if not chokepoints_html:
        chokepoints_html = '<li>No active chokepoint alerts</li>'
    
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
    
    chokepoints_list_html = ""
    for cp in chokepoints[:5]:
        chokepoints_list_html += f'<li>{cp}</li>'
    if not chokepoints_list_html:
        chokepoints_list_html = '<li>No active chokepoint alerts</li>'
    
    delay_badge = '<div class="index-delay-badge">24h delayed • Real-time access with subscription</div>'
    
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Europe Gas Stress Index (EGSI) - {band} at {value:.0f} | EnergyRiskIQ</title>
        <meta name="description" content="EGSI at {value:.0f} ({band}). {interpretation[:150]}">
        <link rel="canonical" href="{BASE_URL}/egsi">
        <link rel="icon" type="image/png" href="/static/favicon.png">
        
        <meta property="og:title" content="Europe Gas Stress Index (EGSI) | EnergyRiskIQ">
        <meta property="og:description" content="EGSI at {value:.0f} ({band}). Track European gas market stress in real-time.">
        <meta property="og:type" content="website">
        <meta property="og:url" content="{BASE_URL}/egsi">
        
        <meta name="twitter:card" content="summary_large_image">
        <meta name="twitter:title" content="EGSI at {value:.0f} ({band})">
        <meta name="twitter:description" content="{interpretation[:200]}">
        
        <script type="application/ld+json">
        {{
            "@context": "https://schema.org",
            "@type": "Dataset",
            "name": "Europe Gas Stress Index (EGSI)",
            "description": "Daily index measuring gas market stress signals across European infrastructure",
            "url": "{BASE_URL}/egsi",
            "creator": {{
                "@type": "Organization",
                "name": "EnergyRiskIQ"
            }},
            "dateModified": "{date_str}",
            "variableMeasured": {{
                "@type": "PropertyValue",
                "name": "EGSI Value",
                "value": {value:.1f},
                "unitText": "index points (0-100)"
            }}
        }}
        </script>
        
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
                    <h1>Europe Gas Stress Index (EGSI)</h1>
                    <p>A daily composite measure of gas market transmission stress across European infrastructure.</p>
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
                    <div class="index-date">Date Computed: {date_str}</div>
                </div>
                
                <div class="index-sections">
                    <div class="index-section">
                        <h2 class="section-header-blue">Primary Risk Drivers:</h2>
                        <ul class="index-list">{drivers_list_html}</ul>
                    </div>
                    
                    <div class="index-section">
                        <h2 class="section-header-blue">Chokepoint Watch:</h2>
                        <ul class="index-list">{chokepoints_list_html}</ul>
                    </div>
                </div>
                
                <div class="index-interpretation">
                    <p>{interpretation.replace(chr(10)+chr(10), '</p><p>')}</p>
                </div>
                
                {delay_badge}
                
                <div class="index-cta">
                    <h3>Get Real-time Access</h3>
                    <p>Unlock instant EGSI updates with a Pro subscription.</p>
                    <a href="/users" class="cta-button primary">Unlock Real-time EGSI</a>
                    <a href="/alerts" class="cta-button secondary">See Alert Archive</a>
                </div>
                
                <div class="index-links">
                    <a href="/egsi/history">EGSI History</a>
                    <a href="/egsi/methodology">Methodology</a>
                </div>
            </div>
        </main>
        
        <footer class="footer">
            <div class="container">
                <p>&copy; {datetime.now().year} EnergyRiskIQ. All rights reserved.</p>
                <p style="margin-top: 0.5rem;">
                    <a href="/egsi/history">EGSI History</a> · 
                    <a href="/egsi/methodology">Methodology</a> · 
                    <a href="/eeri">EERI</a> · 
                    <a href="/geri">GERI</a>
                </p>
            </div>
        </footer>
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
                <a href="/geri">GERI</a>
                <a href="/eeri">EERI</a>
                <a href="/egsi">EGSI</a>
                <a href="/alerts">Alerts</a>
                <a href="/users" class="cta-nav">Sign In</a>
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
    EGSI Methodology Page - SEO content explaining the gas stress index.
    """
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>EGSI Methodology - Europe Gas Stress Index | EnergyRiskIQ</title>
        <meta name="description" content="Learn how the Europe Gas Stress Index (EGSI) is calculated. Understand the methodology behind measuring gas market transmission stress.">
        <link rel="canonical" href="{BASE_URL}/egsi/methodology">
        <link rel="icon" type="image/png" href="/static/favicon.png">
        
        <meta property="og:title" content="EGSI Methodology | EnergyRiskIQ">
        <meta property="og:description" content="Methodology behind the Europe Gas Stress Index calculation.">
        <meta property="og:url" content="{BASE_URL}/egsi/methodology">
        
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
                <div class="breadcrumb">
                    <a href="/egsi">EGSI</a> &gt; Methodology
                </div>
                
                <div class="index-section" style="margin: 40px 0; background: white; border: 1px solid var(--border);">
                    <h1 style="margin-bottom: 30px; color: var(--text-primary);">EGSI Methodology</h1>
                
                <h2 style="margin-top: 30px;">Overview</h2>
                <p>The Europe Gas Stress Index (EGSI-M) measures market transmission stress signals across European gas infrastructure. It combines regional risk assessments, theme-specific alert pressure, asset-level transmission, and infrastructure chokepoint monitoring.</p>
                
                <h2 style="margin-top: 30px;">Formula Components</h2>
                <p>EGSI-M is calculated using four weighted components:</p>
                
                <table style="margin: 20px 0;">
                    <tr>
                        <th>Component</th>
                        <th>Weight</th>
                        <th>Description</th>
                    </tr>
                    <tr>
                        <td>RERI_EU (Regional Risk)</td>
                        <td>35%</td>
                        <td>European regional escalation risk from EERI</td>
                    </tr>
                    <tr>
                        <td>Theme Pressure</td>
                        <td>35%</td>
                        <td>Gas-specific alert themes (supply disruption, pipeline issues, transit disputes)</td>
                    </tr>
                    <tr>
                        <td>Asset Transmission</td>
                        <td>20%</td>
                        <td>Risk transmission through gas infrastructure assets</td>
                    </tr>
                    <tr>
                        <td>Chokepoint Factor</td>
                        <td>10%</td>
                        <td>High-signal infrastructure chokepoint monitoring</td>
                    </tr>
                </table>
                
                <h2 style="margin-top: 30px;">Chokepoints v1</h2>
                <p>The index monitors 10 high-signal European gas infrastructure entities:</p>
                <ul style="margin: 15px 0; padding-left: 30px;">
                    <li>Ukraine Transit (Sudzha, Urengoy)</li>
                    <li>TurkStream / Blue Stream</li>
                    <li>Nord Stream</li>
                    <li>Norway Pipelines (Langeled, Europipe)</li>
                    <li>Gate LNG Terminal (Rotterdam)</li>
                    <li>Zeebrugge LNG (Fluxys)</li>
                    <li>Dunkerque LNG</li>
                    <li>Montoir LNG (Elengy)</li>
                    <li>Swinoujscie LNG (Poland)</li>
                    <li>Revithoussa LNG (Greece)</li>
                </ul>
                
                <h2 style="margin-top: 30px;">Risk Bands</h2>
                <table style="margin: 20px 0;">
                    <tr>
                        <th>Band</th>
                        <th>Range</th>
                        <th>Interpretation</th>
                    </tr>
                    <tr>
                        <td style="color: #22c55e; font-weight: 600;">LOW</td>
                        <td>0-20</td>
                        <td>Minimal gas market stress</td>
                    </tr>
                    <tr>
                        <td style="color: #3b82f6; font-weight: 600;">NORMAL</td>
                        <td>21-40</td>
                        <td>Baseline market conditions</td>
                    </tr>
                    <tr>
                        <td style="color: #f97316; font-weight: 600;">ELEVATED</td>
                        <td>41-60</td>
                        <td>Heightened stress, monitor closely</td>
                    </tr>
                    <tr>
                        <td style="color: #ef4444; font-weight: 600;">HIGH</td>
                        <td>61-80</td>
                        <td>Significant stress, supply concerns</td>
                    </tr>
                    <tr>
                        <td style="color: #dc2626; font-weight: 600;">CRITICAL</td>
                        <td>81-100</td>
                        <td>Severe stress, immediate impact</td>
                    </tr>
                </table>
                
                <h2 style="margin-top: 30px;">Update Schedule</h2>
                <p>EGSI is computed daily alongside GERI and EERI indices. Public data is displayed with a 24-hour delay. Pro subscribers receive real-time access.</p>
                
                <div class="index-links" style="margin-top: 2rem;">
                    <a href="/egsi">&larr; Back to EGSI</a>
                    <a href="/egsi/history">View History &rarr;</a>
                </div>
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
                <a href="/geri">GERI</a>
                <a href="/eeri">EERI</a>
                <a href="/egsi">EGSI</a>
                <a href="/alerts">Alerts</a>
                <a href="/users" class="cta-nav">Sign In</a>
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
                        <a href="/eeri">EERI</a>
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
                        <a href="/eeri">EERI</a>
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
                    <a href="/eeri">EERI</a>
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
