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

router = APIRouter(tags=["egsi-seo"])

BASE_URL = os.environ.get('ALERTS_APP_BASE_URL', 'https://energyriskiq.com')


def get_common_styles():
    """Return common CSS styles for EGSI pages."""
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
            --band-normal: #3B82F6;
            --band-elevated: #F97316;
            --band-high: #EF4444;
            --band-critical: #DC2626;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            color: var(--text-primary);
            background: var(--bg-light);
        }
        .container { max-width: 1200px; margin: 0 auto; padding: 0 20px; }
        header {
            background: linear-gradient(135deg, var(--secondary) 0%, #2D2D4A 100%);
            color: white;
            padding: 20px 0;
        }
        .header-content {
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .logo {
            font-size: 1.5rem;
            font-weight: 700;
            text-decoration: none;
            color: white;
        }
        nav a {
            color: rgba(255,255,255,0.8);
            text-decoration: none;
            margin-left: 30px;
            transition: color 0.2s;
        }
        nav a:hover { color: white; }
        .hero {
            background: linear-gradient(135deg, var(--secondary) 0%, #2D2D4A 100%);
            color: white;
            padding: 60px 0;
            text-align: center;
        }
        .hero h1 { font-size: 2.5rem; margin-bottom: 10px; }
        .hero p { font-size: 1.2rem; opacity: 0.9; max-width: 600px; margin: 0 auto; }
        .index-display {
            background: white;
            border-radius: 16px;
            padding: 40px;
            margin: -40px auto 40px;
            max-width: 800px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
            text-align: center;
        }
        .index-value {
            font-size: 5rem;
            font-weight: 700;
            line-height: 1;
            margin-bottom: 10px;
        }
        .index-band {
            display: inline-block;
            padding: 8px 24px;
            border-radius: 20px;
            font-weight: 600;
            font-size: 1.1rem;
            margin-bottom: 20px;
        }
        .band-LOW { background: var(--band-low); color: white; }
        .band-NORMAL { background: var(--band-normal); color: white; }
        .band-ELEVATED { background: var(--band-elevated); color: white; }
        .band-HIGH { background: var(--band-high); color: white; }
        .band-CRITICAL { background: var(--band-critical); color: white; }
        .interpretation {
            font-size: 1.1rem;
            color: var(--text-secondary);
            max-width: 600px;
            margin: 20px auto;
        }
        .section { padding: 60px 0; }
        .section h2 { font-size: 1.8rem; margin-bottom: 30px; text-align: center; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 30px; }
        .card {
            background: white;
            border-radius: 12px;
            padding: 30px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.05);
        }
        .card h3 { color: var(--primary); margin-bottom: 15px; }
        .trend { font-size: 0.9rem; margin-top: 10px; }
        .trend-up { color: var(--band-high); }
        .trend-down { color: var(--band-low); }
        .trend-stable { color: var(--text-secondary); }
        footer {
            background: var(--secondary);
            color: white;
            padding: 40px 0;
            text-align: center;
        }
        footer a { color: var(--accent); text-decoration: none; }
        .breadcrumb {
            padding: 15px 0;
            font-size: 0.9rem;
            color: var(--text-secondary);
        }
        .breadcrumb a { color: var(--primary); text-decoration: none; }
        .nav-links { display: flex; justify-content: space-between; margin-top: 30px; }
        .nav-links a {
            color: var(--primary);
            text-decoration: none;
            padding: 10px 20px;
            background: var(--bg-light);
            border-radius: 8px;
        }
        table { width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; }
        th, td { padding: 12px 16px; text-align: left; border-bottom: 1px solid var(--border); }
        th { background: var(--bg-light); font-weight: 600; }
        @media (max-width: 768px) {
            .hero h1 { font-size: 1.8rem; }
            .index-value { font-size: 3rem; }
            .header-content { flex-direction: column; gap: 15px; }
            nav a { margin: 0 15px; }
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
            <div class="hero">
                <div class="container">
                    <h1>Europe Gas Stress Index (EGSI)</h1>
                    <p>Real-time intelligence on European gas market stress</p>
                </div>
            </div>
            <div class="container">
                <div class="index-display">
                    <p>No EGSI data available yet. The index is computed daily.</p>
                    <p style="margin-top: 20px;">Check back soon or <a href="/signup">sign up for alerts</a>.</p>
                </div>
            </div>
            <footer>
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
    explanation = egsi.get('explanation', 'Europe gas market stress assessment based on regional risk, supply disruptions, and infrastructure factors.')
    drivers = egsi.get('drivers', [])[:3]
    components = egsi.get('components', {})
    
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
    
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Europe Gas Stress Index (EGSI) - {band} at {value:.0f} | EnergyRiskIQ</title>
        <meta name="description" content="EGSI at {value:.0f} ({band}). {explanation[:150]}">
        <link rel="canonical" href="{BASE_URL}/egsi">
        <link rel="icon" type="image/png" href="/static/favicon.png">
        
        <meta property="og:title" content="Europe Gas Stress Index (EGSI) | EnergyRiskIQ">
        <meta property="og:description" content="EGSI at {value:.0f} ({band}). Track European gas market stress in real-time.">
        <meta property="og:type" content="website">
        <meta property="og:url" content="{BASE_URL}/egsi">
        
        <meta name="twitter:card" content="summary_large_image">
        <meta name="twitter:title" content="EGSI at {value:.0f} ({band})">
        <meta name="twitter:description" content="{explanation[:200]}">
        
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
        
        <div class="hero">
            <div class="container">
                <h1>Europe Gas Stress Index</h1>
                <p>Real-time intelligence on European gas market transmission stress</p>
            </div>
        </div>
        
        <div class="container">
            <div class="index-display">
                <div class="index-value" style="color: {band_color}">{value:.0f}</div>
                <div class="index-band band-{band}">{band}</div>
                <p class="trend" style="color: {trend_color}">7-Day Trend: {trend_label} {f'{trend_sign}{abs(trend_7d):.1f}' if trend_7d else ''}</p>
                <p class="interpretation">{explanation}</p>
                <p style="font-size: 0.9rem; color: var(--text-secondary); margin-top: 20px;">
                    Data as of {date_str} (24-hour delay for public display)
                </p>
            </div>
            
            <section class="section">
                <h2>Top Risk Drivers</h2>
                <div class="grid">
                    {drivers_html}
                </div>
            </section>
            
            <section class="section">
                <h2>Chokepoint Watch</h2>
                <div class="card">
                    <p>Infrastructure entities under monitoring:</p>
                    <ul style="margin-top: 15px; padding-left: 20px;">
                        {chokepoints_html}
                    </ul>
                </div>
            </section>
            
            <section class="section">
                <h2>Understanding EGSI Bands</h2>
                <div class="grid">
                    <div class="card">
                        <h3 style="color: var(--band-low)">LOW (0-20)</h3>
                        <p>Minimal gas market stress. Stable supply conditions.</p>
                    </div>
                    <div class="card">
                        <h3 style="color: var(--band-normal)">NORMAL (21-40)</h3>
                        <p>Baseline market conditions. Standard operations.</p>
                    </div>
                    <div class="card">
                        <h3 style="color: var(--band-elevated)">ELEVATED (41-60)</h3>
                        <p>Heightened stress. Monitor supply flows closely.</p>
                    </div>
                    <div class="card">
                        <h3 style="color: var(--band-high)">HIGH (61-80)</h3>
                        <p>Significant stress. Potential supply concerns.</p>
                    </div>
                    <div class="card">
                        <h3 style="color: var(--band-critical)">CRITICAL (81-100)</h3>
                        <p>Severe stress. Immediate market impact likely.</p>
                    </div>
                </div>
            </section>
        </div>
        
        <footer>
            <div class="container">
                <p>&copy; {datetime.now().year} EnergyRiskIQ. All rights reserved.</p>
                <p style="margin-top: 10px;">
                    <a href="/egsi/methodology">Methodology</a> | 
                    <a href="/egsi/history">History</a> | 
                    <a href="/eeri">EERI Index</a>
                </p>
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
                <a href="/egsi">EGSI</a> &gt; Methodology
            </div>
            
            <div class="card" style="margin: 40px 0;">
                <h1 style="margin-bottom: 30px;">EGSI Methodology</h1>
                
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
                
                <div class="nav-links">
                    <a href="/egsi">&larr; Back to EGSI</a>
                    <a href="/egsi/history">View History &rarr;</a>
                </div>
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
                <a href="/egsi">EGSI</a> &gt; History
            </div>
            
            <h1 style="margin: 40px 0 30px;">EGSI Historical Data</h1>
            
            <div class="grid">
                <div class="card">
                    <h2>Recent Daily Snapshots</h2>
                    <ul style="margin-top: 15px; padding-left: 20px;">
                        {recent_dates_html}
                    </ul>
                </div>
                
                <div class="card">
                    <h2>Monthly Archives</h2>
                    <ul style="margin-top: 15px; padding-left: 20px;">
                        {months_html}
                    </ul>
                </div>
            </div>
            
            {"<div class='card' style='margin-top: 40px;'><h2>Monthly Statistics</h2><table><tr><th>Month</th><th>Days</th><th>Avg</th><th>Max</th><th>Min</th></tr>" + stats_html + "</table></div>" if stats_html else ""}
            
            <div class="nav-links" style="margin-top: 40px;">
                <a href="/egsi">&larr; Current EGSI</a>
                <a href="/egsi/methodology">Methodology &rarr;</a>
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
    
    band_color = get_band_color(egsi['band'])
    date_display = target_date.strftime('%B %d, %Y')
    
    drivers_html = ""
    for driver in egsi.get('drivers', [])[:3]:
        drivers_html += f"""
        <div class="card">
            <h3>{driver.get('name', 'Unknown')}</h3>
            <p>Contribution: {driver.get('contribution', 0):.1f}%</p>
        </div>
        """
    
    nav_html = '<div class="nav-links">'
    if adjacent.get('prev'):
        nav_html += f'<a href="/egsi/{adjacent["prev"]}">&larr; {adjacent["prev"]}</a>'
    else:
        nav_html += '<span></span>'
    if adjacent.get('next'):
        nav_html += f'<a href="/egsi/{adjacent["next"]}">{adjacent["next"]} &rarr;</a>'
    else:
        nav_html += '<span></span>'
    nav_html += '</div>'
    
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>EGSI {date_str} - {egsi['band']} at {egsi['value']:.0f} | EnergyRiskIQ</title>
        <meta name="description" content="Europe Gas Stress Index for {date_display}: {egsi['value']:.0f} ({egsi['band']}). {egsi.get('explanation', '')[:150]}">
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
                <h1 style="font-size: 1.5rem; margin-bottom: 20px;">EGSI for {date_display}</h1>
                <div class="index-value" style="color: {band_color}">{egsi['value']:.0f}</div>
                <div class="index-band band-{egsi['band']}">{egsi['band']}</div>
                <p class="interpretation">{egsi.get('explanation', '')}</p>
            </div>
            
            {"<section class='section'><h2>Risk Drivers</h2><div class='grid'>" + drivers_html + "</div></section>" if drivers_html else ""}
            
            {nav_html}
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
