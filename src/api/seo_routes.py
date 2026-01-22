"""
SEO Routes for EnergyRiskIQ

Serves SEO-optimized pages:
- /alerts - Alerts hub
- /alerts/daily/YYYY-MM-DD - Daily pages
- /alerts/YYYY/MM - Monthly archives
- /sitemap.xml - XML sitemap
- /sitemap.html - HTML sitemap
"""

import os
import json
from datetime import datetime, date, timedelta, timezone
from typing import Optional
from calendar import month_name

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, Response

from src.db.db import get_cursor, execute_one, execute_query
from src.seo.seo_generator import (
    get_daily_page,
    get_recent_daily_pages,
    get_monthly_pages,
    get_available_months,
    generate_sitemap_entries,
    get_yesterday_date,
    generate_daily_page_model
)
from src.geri.geri_service import get_geri_for_user, get_geri_delayed

router = APIRouter(tags=["seo"])

BASE_URL = os.environ.get('ALERTS_APP_BASE_URL', 'https://energyriskiq.com')


def generate_why_matters_text(model: dict) -> str:
    """Generate contextual 'Why This Matters' text based on alert data."""
    stats = model.get('stats', {})
    total = stats.get('total_alerts', 0)
    critical = stats.get('critical_count', 0)
    high = stats.get('high_count', 0)
    regions = stats.get('regions', {})
    categories = stats.get('categories', {})
    
    if total == 0:
        return "No significant risk events were detected for this period. Energy markets operated within normal parameters, providing an opportunity for institutions to reassess exposures and prepare contingency strategies for future volatility."
    
    # Build dynamic text based on actual data
    top_regions = list(regions.keys())[:2]
    top_cats = list(categories.keys())[:2]
    
    region_str = " and ".join(top_regions) if top_regions else "global markets"
    
    # Build implications based on categories
    implications = []
    for cat in top_cats:
        if cat == 'Geopolitical':
            implications.append("geopolitical stability")
        elif cat == 'Commodities':
            implications.append("commodity pricing")
        elif cat == 'Energy':
            implications.append("energy supply chains")
        else:
            implications.append("market conditions")
    
    impl_str = ", ".join(implications) if implications else "market stability"
    
    if critical > 0:
        severity_phrase = f"Today's {critical} critical-severity alert(s) highlight"
    elif high > 0:
        severity_phrase = f"Today's {high} high-severity signal(s) indicate"
    else:
        severity_phrase = f"Today's {total} risk signal(s) suggest"
    
    return f"{severity_phrase} sustained pressure across {region_str}, with implications for {impl_str}. Monitoring these signals early helps institutions prepare before market reactions occur."


def track_page_view(page_type: str, page_path: str):
    """Track page view (privacy-safe, no cookies)."""
    try:
        with get_cursor() as cursor:
            cursor.execute("""
                INSERT INTO seo_page_views (page_type, page_path, view_count, last_viewed_at)
                VALUES (%s, %s, 1, NOW())
                ON CONFLICT (page_type, page_path) DO UPDATE SET
                    view_count = seo_page_views.view_count + 1,
                    last_viewed_at = NOW()
            """, (page_type, page_path))
    except Exception:
        pass


def get_common_styles() -> str:
    """Return common CSS for SEO pages."""
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
            --severity-1: #22C55E;
            --severity-2: #84CC16;
            --severity-3: #EAB308;
            --severity-4: #F97316;
            --severity-5: #EF4444;
        }
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            color: var(--text-primary);
            line-height: 1.6;
            background: var(--bg-light);
        }
        .container { max-width: 1200px; margin: 0 auto; padding: 0 1rem; }
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
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }
        .logo-icon {
            width: 32px;
            height: 32px;
            background: linear-gradient(135deg, var(--primary), var(--accent));
            border-radius: 6px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-weight: 800;
            font-size: 0.875rem;
        }
        .nav-links { display: flex; gap: 1.5rem; align-items: center; }
        .nav-links a { color: var(--text-secondary); text-decoration: none; font-weight: 500; }
        .nav-links a:hover { color: var(--primary); }
        .nav-links a.cta-btn { color: white; }
        .nav-links a.cta-btn:hover { color: white; }
        .cta-btn {
            background: var(--primary);
            color: white;
            padding: 0.5rem 1rem;
            border-radius: 6px;
            text-decoration: none;
            font-weight: 600;
            transition: background 0.2s;
        }
        .cta-btn:hover { background: var(--primary-dark); }
        .hero-banner {
            background: linear-gradient(135deg, var(--primary) 0%, var(--accent) 100%);
            color: white;
            padding: 1rem 0;
            text-align: center;
        }
        .hero-banner a { color: white; font-weight: 600; }
        main { padding: 2rem 0; }
        h1 { font-size: 2rem; margin-bottom: 1rem; color: var(--secondary); }
        h2 { font-size: 1.5rem; margin: 1.5rem 0 1rem; color: var(--secondary); }
        .meta { color: var(--text-secondary); margin-bottom: 1.5rem; }
        .stats-row {
            display: flex;
            gap: 1rem;
            flex-wrap: wrap;
            margin-bottom: 1.5rem;
        }
        .stat-badge {
            background: var(--bg-white);
            border: 1px solid var(--border);
            border-radius: 6px;
            padding: 0.5rem 1rem;
            font-size: 0.875rem;
        }
        .stat-badge strong { color: var(--primary); }
        .risk-posture {
            background: var(--bg-white);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 1.5rem;
            margin-bottom: 1.5rem;
        }
        .risk-posture h3 { margin-bottom: 0.75rem; color: var(--secondary); }
        .drivers-list {
            list-style: none;
            margin: 1rem 0;
        }
        .drivers-list li {
            padding: 0.5rem 0;
            padding-left: 1.5rem;
            position: relative;
        }
        .drivers-list li::before {
            content: '>';
            position: absolute;
            left: 0;
            color: var(--primary);
            font-weight: bold;
        }
        .alert-cards {
            display: grid;
            gap: 1rem;
            margin: 1.5rem 0;
        }
        .alert-card {
            background: var(--bg-white);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 1.25rem;
            border-left: 4px solid var(--border);
        }
        .alert-card.severity-5 { border-left-color: var(--severity-5); }
        .alert-card.severity-4 { border-left-color: var(--severity-4); }
        .alert-card.severity-3 { border-left-color: var(--severity-3); }
        .alert-card.severity-2 { border-left-color: var(--severity-2); }
        .alert-card.severity-1 { border-left-color: var(--severity-1); }
        .alert-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 1rem;
            margin-bottom: 0.75rem;
            flex-wrap: wrap;
        }
        .alert-title { font-weight: 600; font-size: 1.1rem; }
        .alert-badges { display: flex; gap: 0.5rem; flex-wrap: wrap; }
        .badge {
            font-size: 0.75rem;
            padding: 0.25rem 0.5rem;
            border-radius: 4px;
            background: var(--bg-light);
            color: var(--text-secondary);
        }
        .badge.severity {
            background: var(--severity-3);
            color: white;
        }
        .badge.severity-5 { background: var(--severity-5); }
        .badge.severity-4 { background: var(--severity-4); }
        .badge.severity-3 { background: var(--severity-3); }
        .alert-summary {
            color: var(--text-secondary);
            margin-bottom: 0.5rem;
        }
        .alert-meta {
            font-size: 0.8rem;
            color: var(--text-secondary);
        }
        /* Why This Matters section */
        .why-matters {
            background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%);
            border: 1px solid #bae6fd;
            border-radius: 8px;
            padding: 1.5rem;
            margin: 1.5rem 0;
        }
        .why-matters h2 {
            color: var(--secondary);
            font-size: 1.25rem;
            margin-bottom: 0.75rem;
        }
        .why-matters p {
            color: var(--text-secondary);
            line-height: 1.7;
        }
        /* Compact card styles for collapsed alerts */
        .alert-card-compact {
            padding: 0.75rem 1rem;
        }
        .alert-header-compact {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            flex-wrap: wrap;
        }
        .alert-region-compact {
            font-size: 0.8rem;
            color: var(--text-secondary);
            font-weight: 500;
        }
        .alert-title-compact {
            font-weight: 600;
            font-size: 0.95rem;
            flex: 1;
        }
        .alert-summary-compact {
            font-size: 0.85rem;
            color: var(--text-secondary);
            margin: 0.25rem 0 0 0;
            line-height: 1.4;
        }
        .cta-section {
            background: linear-gradient(135deg, var(--secondary) 0%, #2D2D4A 100%);
            color: white;
            padding: 2rem;
            border-radius: 8px;
            text-align: center;
            margin: 2rem 0;
        }
        .cta-section h3 { margin-bottom: 0.75rem; }
        .cta-section p { margin-bottom: 1rem; opacity: 0.9; }
        .cta-section .cta-btn {
            display: inline-block;
            padding: 0.75rem 2rem;
            font-size: 1.1rem;
        }
        .nav-pagination {
            display: flex;
            justify-content: space-between;
            margin: 2rem 0;
            padding: 1rem 0;
            border-top: 1px solid var(--border);
        }
        .nav-pagination a {
            color: var(--primary);
            text-decoration: none;
            font-weight: 500;
        }
        .breadcrumbs {
            font-size: 0.875rem;
            color: var(--text-secondary);
            margin-bottom: 1rem;
        }
        .breadcrumbs a { color: var(--primary); text-decoration: none; }
        .page-list {
            list-style: none;
            display: grid;
            gap: 0.5rem;
        }
        .page-list li a {
            display: block;
            padding: 0.75rem 1rem;
            background: var(--bg-white);
            border: 1px solid var(--border);
            border-radius: 6px;
            text-decoration: none;
            color: var(--text-primary);
            transition: border-color 0.2s;
        }
        .page-list li a:hover { border-color: var(--primary); }
        .page-list .date { font-weight: 600; }
        .page-list .count { color: var(--text-secondary); font-size: 0.875rem; }
        footer {
            background: var(--secondary);
            color: white;
            padding: 2rem 0;
            margin-top: 3rem;
        }
        footer a { color: var(--accent); text-decoration: none; }
        .footer-inner {
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 1rem;
        }
        .footer-links { display: flex; gap: 1.5rem; }
        .disclaimer {
            font-size: 0.8rem;
            color: var(--text-secondary);
            margin-top: 1rem;
            padding: 1rem;
            background: var(--bg-light);
            border-radius: 6px;
        }
        .cta-mid {
            background: linear-gradient(135deg, #1E3A5F 0%, #2D5A87 100%);
        }
        .cta-mid h3 { color: #FFD700; }
        .risk-level {
            display: inline-block;
            padding: 0.25rem 0.75rem;
            border-radius: 4px;
            font-weight: 700;
            font-size: 0.875rem;
            text-transform: uppercase;
        }
        .risk-level.elevated { background: var(--severity-5); color: white; }
        .risk-level.moderate { background: var(--severity-4); color: white; }
        .risk-level.stable { background: var(--severity-1); color: white; }
        .alerts-collapsed { display: none; }
        .show-more-btn {
            display: block;
            width: 100%;
            padding: 1rem;
            background: var(--bg-white);
            border: 2px dashed var(--border);
            border-radius: 8px;
            color: var(--primary);
            font-weight: 600;
            cursor: pointer;
            margin-top: 1rem;
            transition: all 0.2s;
        }
        .show-more-btn:hover {
            background: var(--bg-light);
            border-color: var(--primary);
        }
        .driver-link {
            color: var(--primary);
            text-decoration: none;
            font-weight: 500;
        }
        .driver-link:hover { text-decoration: underline; }
        @media (max-width: 768px) {
            h1 { font-size: 1.5rem; }
            .nav-links { display: none; }
            .stats-row { flex-direction: column; }
            .alert-header { flex-direction: column; }
            .footer-inner { flex-direction: column; text-align: center; }
        }
    </style>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    """


def render_nav() -> str:
    """Render navigation bar."""
    return """
    <nav class="nav">
        <div class="container nav-inner">
            <a href="/" class="logo">
                <span class="logo-icon">E</span>
                EnergyRiskIQ
            </a>
            <div class="nav-links">
                <a href="/">Home</a>
                <a href="/alerts">Alerts</a>
                <a href="https://www.energyriskiq.com/users" class="cta-btn">Get Started</a>
            </div>
        </div>
    </nav>
    """


def render_footer() -> str:
    """Render footer."""
    return """
    <footer>
        <div class="container footer-inner">
            <div>&copy; 2026 EnergyRiskIQ. All rights reserved.</div>
            <div class="footer-links">
                <a href="/">Home</a>
                <a href="/alerts">Alerts</a>
                <a href="/sitemap.html">Sitemap</a>
                <a href="/privacy">Privacy</a>
                <a href="/terms">Terms</a>
            </div>
        </div>
    </footer>
    """


def render_cta_section(position: str = "mid") -> str:
    """Render conversion CTA section with varied anchor text for SEO."""
    if position == "top":
        return """
        <div class="hero-banner">
            <div class="container">
                <strong>Get tomorrow's alerts before markets open.</strong> <a href="https://www.energyriskiq.com/users">Start free &rarr;</a>
            </div>
        </div>
        """
    elif position == "mid":
        return """
        <section class="cta-section cta-mid">
            <h3>These are public summaries.</h3>
            <p>Pro users receive <strong>full AI analysis</strong>, <strong>instant multi-channel delivery</strong>, and <strong>priority alerts</strong> before they appear here.</p>
            <a href="https://www.energyriskiq.com/users" class="cta-btn">Unlock Full Analysis &rarr;</a>
        </section>
        """
    elif position == "bottom":
        return """
        <section class="cta-section">
            <h3>Don't Miss Tomorrow's Risk Signals</h3>
            <p>Get real-time alerts delivered via Email, Telegram, or SMS — before markets react.</p>
            <a href="https://www.energyriskiq.com/users" class="cta-btn">Get Alerts Now &rarr;</a>
        </section>
        """
    else:
        return """
        <section class="cta-section">
            <h3>Stay Ahead of Market Risks</h3>
            <p>Subscribe for daily intelligence briefings and real-time risk signals.</p>
            <a href="https://www.energyriskiq.com/users" class="cta-btn">Start Free Trial &rarr;</a>
        </section>
        """


@router.get("/alerts", response_class=HTMLResponse)
async def alerts_hub():
    """Alerts hub page - main entry point for SEO traffic."""
    track_page_view("hub", "/alerts")
    
    recent_pages = get_recent_daily_pages(limit=30)
    months = get_available_months()
    
    pages_html = ""
    for p in recent_pages[:15]:
        page_date = p['page_date']
        if isinstance(page_date, str):
            page_date = datetime.fromisoformat(page_date).date()
        date_display = page_date.strftime("%B %d, %Y")
        pages_html += f"""
        <li>
            <a href="/alerts/daily/{page_date.isoformat()}">
                <span class="date">{date_display}</span>
                <span class="count">{p['alert_count']} alerts</span>
            </a>
        </li>
        """
    
    months_html = ""
    for m in months[:12]:
        month_display = f"{month_name[m['month']]} {m['year']}"
        months_html += f"""
        <li>
            <a href="/alerts/{m['year']}/{m['month']:02d}">
                <span class="date">{month_display}</span>
                <span class="count">{m['page_count']} days, {m['total_alerts']} alerts</span>
            </a>
        </li>
        """
    
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Geopolitical & Energy Risk Alerts Archive | EnergyRiskIQ</title>
        <meta name="description" content="Browse daily geopolitical and energy risk alerts for Europe and global markets. Historical archive of energy supply disruption signals and risk intelligence.">
        <link rel="canonical" href="{BASE_URL}/alerts">
        {get_common_styles()}
    </head>
    <body>
        {render_nav()}
        {render_cta_section("top")}
        <main>
            <div class="container">
                <div class="breadcrumbs">
                    <a href="/">Home</a> / Alerts
                </div>
                <h1>Geopolitical & Energy Risk Alerts</h1>
                <p class="meta">Daily risk intelligence covering energy markets, supply chains, and geopolitical events affecting Europe and global markets.</p>
                
                <h2>Recent Daily Alerts</h2>
                <ul class="page-list">
                    {pages_html if pages_html else '<li>No daily pages generated yet.</li>'}
                </ul>
                
                {render_cta_section("mid")}
                
                <h2>Monthly Archives</h2>
                <ul class="page-list">
                    {months_html if months_html else '<li>No monthly archives available yet.</li>'}
                </ul>
                
                <div class="disclaimer">
                    <strong>Disclaimer:</strong> This information is provided for general informational purposes only and does not constitute financial, investment, or trading advice. Past alerts do not guarantee future accuracy.
                </div>
            </div>
        </main>
        {render_footer()}
    </body>
    </html>
    """
    
    return HTMLResponse(content=html, headers={"Cache-Control": "public, max-age=3600"})


@router.get("/alerts/region/{region_slug}", response_class=HTMLResponse)
async def alerts_by_region(region_slug: str):
    """
    Region-specific alerts page. Currently redirects to main alerts hub.
    In future, could filter alerts by region.
    """
    # Map slug back to display name for SEO
    region_display_map = {
        'middle-east': 'Middle East',
        'europe': 'Europe',
        'asia': 'Asia',
        'africa': 'Africa',
        'russia': 'Russia',
        'ukraine': 'Ukraine',
        'china': 'China',
        'iran': 'Iran',
        'global': 'Global',
    }
    
    region_name = region_display_map.get(region_slug, region_slug.replace('-', ' ').title())
    track_page_view("region", f"/alerts/region/{region_slug}")
    
    # Get recent daily pages for context
    recent_pages = get_recent_daily_pages(limit=10)
    pages_html = ""
    for page in recent_pages:
        page_date = page['page_date'].strftime('%Y-%m-%d')
        display_date = page['page_date'].strftime('%B %d, %Y')
        alert_count = page.get('alert_count', 0)
        pages_html += f'<li><a href="/alerts/daily/{page_date}">{display_date}</a> ({alert_count} alerts)</li>'
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{region_name} Risk Alerts | EnergyRiskIQ</title>
    <meta name="description" content="Geopolitical and energy risk alerts for {region_name}. Monitor supply disruption signals, market volatility, and risk intelligence for {region_name}.">
    <link rel="canonical" href="{BASE_URL}/alerts/region/{region_slug}">
    {get_common_styles()}
</head>
<body>
    {render_nav()}
    {render_cta_section("top")}
    <main>
        <div class="container">
            <div class="breadcrumbs">
                <a href="/">Home</a> / <a href="/alerts">Alerts</a> / {region_name}
            </div>
            <h1>{region_name} Risk Alerts</h1>
            <p class="meta">Geopolitical and energy risk intelligence for {region_name}. Track supply disruption signals, market volatility, and critical risk events.</p>
            
            <h2>Recent Alerts</h2>
            <p>Browse daily risk alerts that may include events affecting {region_name}:</p>
            <ul class="page-list">
                {pages_html if pages_html else '<li>No daily pages generated yet.</li>'}
            </ul>
            
            {render_cta_section("mid")}
            
            <p><a href="/alerts">&larr; Back to All Alerts</a></p>
            
            <div class="disclaimer">
                <strong>Disclaimer:</strong> This information is provided for general informational purposes only and does not constitute financial, investment, or trading advice.
            </div>
        </div>
    </main>
    {render_footer()}
</body>
</html>
"""
    
    return HTMLResponse(content=html, headers={"Cache-Control": "public, max-age=3600"})


@router.get("/alerts/category/{category_slug}", response_class=HTMLResponse)
async def alerts_by_category(category_slug: str):
    """
    Category-specific alerts page. Currently shows info page with links.
    In future, could filter alerts by category.
    """
    # Map slug back to display name
    category_display_map = {
        'geopolitical': 'Geopolitical',
        'infrastructure': 'Infrastructure',
        'supply-chain': 'Supply Chain',
        'market': 'Market',
        'energy': 'Energy',
        'conflict': 'Conflict',
    }
    
    category_name = category_display_map.get(category_slug, category_slug.replace('-', ' ').title())
    track_page_view("category", f"/alerts/category/{category_slug}")
    
    # Get recent daily pages for context
    recent_pages = get_recent_daily_pages(limit=10)
    pages_html = ""
    for page in recent_pages:
        page_date = page['page_date'].strftime('%Y-%m-%d')
        display_date = page['page_date'].strftime('%B %d, %Y')
        alert_count = page.get('alert_count', 0)
        pages_html += f'<li><a href="/alerts/daily/{page_date}">{display_date}</a> ({alert_count} alerts)</li>'
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{category_name} Risk Alerts | EnergyRiskIQ</title>
    <meta name="description" content="{category_name} risk alerts and intelligence. Monitor {category_name.lower()} events affecting energy markets, supply chains, and regional stability.">
    <link rel="canonical" href="{BASE_URL}/alerts/category/{category_slug}">
    {get_common_styles()}
</head>
<body>
    {render_nav()}
    {render_cta_section("top")}
    <main>
        <div class="container">
            <div class="breadcrumbs">
                <a href="/">Home</a> / <a href="/alerts">Alerts</a> / {category_name}
            </div>
            <h1>{category_name} Risk Alerts</h1>
            <p class="meta">{category_name} risk intelligence covering events affecting energy markets, supply chains, and regional stability.</p>
            
            <h2>Recent Alerts</h2>
            <p>Browse daily risk alerts that may include {category_name.lower()} events:</p>
            <ul class="page-list">
                {pages_html if pages_html else '<li>No daily pages generated yet.</li>'}
            </ul>
            
            {render_cta_section("mid")}
            
            <p><a href="/alerts">&larr; Back to All Alerts</a></p>
            
            <div class="disclaimer">
                <strong>Disclaimer:</strong> This information is provided for general informational purposes only and does not constitute financial, investment, or trading advice.
            </div>
        </div>
    </main>
    {render_footer()}
</body>
</html>
"""
    
    return HTMLResponse(content=html, headers={"Cache-Control": "public, max-age=3600"})


@router.get("/alerts/daily/{date_str}", response_class=HTMLResponse)
async def daily_alerts_page(date_str: str):
    """Daily alerts page for a specific date."""
    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        raise HTTPException(status_code=404, detail="Invalid date format")
    
    yesterday = get_yesterday_date()
    if target_date > yesterday:
        raise HTTPException(status_code=404, detail="Page not available yet (24h delay)")
    
    track_page_view("daily", f"/alerts/daily/{date_str}")
    
    page_data = get_daily_page(target_date)
    
    if page_data and page_data.get('model'):
        model = page_data['model']
    else:
        model = generate_daily_page_model(target_date)
    
    # Build alert cards with collapsible sections (top 10 expanded, rest collapsed)
    all_cards = model.get('alert_cards', [])
    visible_cards = all_cards[:10]
    collapsed_cards = all_cards[10:]
    
    def get_severity_label(severity):
        """Derive severity label from score for consistency."""
        if severity >= 5:
            return 'Critical'
        elif severity == 4:
            return 'High'
        elif severity == 3:
            return 'Moderate'
        return 'Low'
    
    def render_alert_card_full(card):
        """Full card for expanded/visible alerts."""
        severity = card.get('severity', 3)
        severity_label = get_severity_label(severity)
        return f"""
        <article class="alert-card severity-{severity}">
            <div class="alert-header">
                <h3 class="alert-title">{card['public_title']}</h3>
                <div class="alert-badges">
                    <span class="badge severity severity-{severity}">{severity_label} ({severity}/5)</span>
                    <span class="badge">{card['category']}</span>
                    <span class="badge">{card['region']}</span>
                </div>
            </div>
            <p class="alert-summary">{card['public_summary']}</p>
            <div class="alert-meta">{card['event_type']}</div>
        </article>
        """
    
    def render_alert_card_compact(card):
        """Compact card for collapsed alerts - reduces duplicate content blocks."""
        severity = card.get('severity', 3)
        severity_label = get_severity_label(severity)
        # Truncate summary to ~100 chars for compact view
        summary = card.get('public_summary', '')
        if len(summary) > 120:
            summary = summary[:117] + '...'
        return f"""
        <article class="alert-card alert-card-compact severity-{severity}">
            <div class="alert-header-compact">
                <span class="badge severity severity-{severity}">{severity_label}</span>
                <span class="alert-region-compact">{card['region']}</span>
                <span class="alert-title-compact">{card['public_title']}</span>
            </div>
            <p class="alert-summary-compact">{summary}</p>
        </article>
        """
    
    visible_cards_html = ''.join(render_alert_card_full(c) for c in visible_cards)
    collapsed_cards_html = ''.join(render_alert_card_compact(c) for c in collapsed_cards)
    
    # Build alert cards section with show more button
    if collapsed_cards:
        alert_cards_html = f"""
        {visible_cards_html}
        <button class="show-more-btn" onclick="document.getElementById('collapsed-alerts').classList.toggle('alerts-collapsed'); this.textContent = this.textContent.includes('Show') ? 'Hide {len(collapsed_cards)} alerts' : 'Show {len(collapsed_cards)} more alerts from this day';">
            Show {len(collapsed_cards)} more alerts from this day
        </button>
        <div id="collapsed-alerts" class="alerts-collapsed">
            {collapsed_cards_html}
        </div>
        """
    else:
        alert_cards_html = visible_cards_html
    
    # Build drivers with internal links to region/category pages
    drivers_html = ""
    top_drivers = model.get('top_drivers', [])
    for driver in top_drivers:
        if isinstance(driver, dict):
            text = driver.get('text', '')
            region = driver.get('region')
            region_slug = driver.get('region_slug')
            category = driver.get('category', '')
            category_slug = driver.get('category_slug', '')
            count = driver.get('count', 0)
            
            if region and region_slug:
                # Create links to both region and category filter pages
                region_link = f'<a href="/alerts/region/{region_slug}" class="driver-link">{region}</a>'
                if category and category_slug:
                    category_link = f'<a href="/alerts/category/{category_slug}" class="driver-link">{category.lower()}</a>'
                    drivers_html += f'<li>{region_link}: {count} {category_link} event(s) detected</li>'
                else:
                    drivers_html += f'<li>{region_link}: {count} geopolitical event(s) detected</li>'
            else:
                drivers_html += f"<li>{text}</li>"
        else:
            drivers_html += f"<li>{driver}</li>"
    
    # Handle risk_posture as dict or string (backward compatibility)
    risk_posture = model.get('risk_posture', {})
    if isinstance(risk_posture, dict):
        risk_level = risk_posture.get('level', 'STABLE')
        risk_summary = risk_posture.get('summary', '')
        risk_level_class = risk_level.lower()
    else:
        risk_level = 'STABLE'
        risk_summary = str(risk_posture)
        risk_level_class = 'stable'
    
    stats = model.get('stats', {})
    stats_html = f"""
    <div class="stats-row">
        <div class="stat-badge"><strong>{stats.get('total_alerts', 0)}</strong> Total Alerts</div>
        <div class="stat-badge"><strong>{stats.get('critical_count', 0)}</strong> Critical (5/5)</div>
        <div class="stat-badge"><strong>{stats.get('high_count', 0)}</strong> High (4/5)</div>
        <div class="stat-badge"><strong>{stats.get('moderate_count', 0)}</strong> Moderate (3/5)</div>
    </div>
    """
    
    prev_link = f'<a href="/alerts/daily/{model["prev_date"]}">&larr; Previous Day</a>' if model.get('prev_date') else '<span></span>'
    next_link = f'<a href="/alerts/daily/{model["next_date"]}">Next Day &rarr;</a>' if model.get('next_date') else '<span></span>'
    
    # BreadcrumbList JSON-LD schema
    breadcrumb_json_ld = json.dumps({
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{BASE_URL}/"},
            {"@type": "ListItem", "position": 2, "name": "Alerts", "item": f"{BASE_URL}/alerts"},
            {"@type": "ListItem", "position": 3, "name": model['date_display'], "item": f"{BASE_URL}/alerts/daily/{date_str}"}
        ]
    })
    
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{model['seo_title']}</title>
        <meta name="description" content="{model['seo_description']}">
        <link rel="canonical" href="{BASE_URL}/alerts/daily/{date_str}">
        <script type="application/ld+json">{breadcrumb_json_ld}</script>
        {get_common_styles()}
    </head>
    <body>
        {render_nav()}
        {render_cta_section("top")}
        <main>
            <div class="container">
                <div class="breadcrumbs">
                    <a href="/">Home</a> / <a href="/alerts">Alerts</a> / {model['date_display']}
                </div>
                <h1>{model['h1_title']}</h1>
                <p class="meta">Published {model['date_display']} (alerts from the previous 24 hours)</p>
                
                {stats_html}
                
                <section class="risk-posture">
                    <h2>Daily Risk Posture <span class="risk-level {risk_level_class}">{risk_level}</span></h2>
                    <p>{risk_summary}</p>
                </section>
                
                {render_cta_section("mid")}
                
                <h2>Top Risk Drivers</h2>
                <ul class="drivers-list">
                    {drivers_html}
                </ul>
                
                <section class="why-matters">
                    <h2>Why This Matters</h2>
                    <p>{generate_why_matters_text(model)}</p>
                </section>
                
                <h2>Alert Details</h2>
                <div class="alert-cards">
                    {alert_cards_html if alert_cards_html else '<p>No alerts detected for this day.</p>'}
                </div>
                
                {render_cta_section("bottom")}
                
                <nav class="nav-pagination">
                    {prev_link}
                    {next_link}
                </nav>
                
                <div class="disclaimer">
                    <strong>Disclaimer:</strong> This information is provided for general informational purposes only and does not constitute financial, investment, or trading advice.
                </div>
            </div>
        </main>
        {render_footer()}
    </body>
    </html>
    """
    
    return HTMLResponse(content=html, headers={"Cache-Control": "public, max-age=86400"})


@router.get("/alerts/{year}/{month}", response_class=HTMLResponse)
async def monthly_archive_page(year: int, month: int):
    """Monthly archive page."""
    if month < 1 or month > 12 or year < 2020 or year > 2030:
        raise HTTPException(status_code=404, detail="Invalid month/year")
    
    track_page_view("monthly", f"/alerts/{year}/{month:02d}")
    
    pages = get_monthly_pages(year, month)
    month_display = f"{month_name[month]} {year}"
    
    pages_html = ""
    total_alerts = 0
    for p in pages:
        page_date = p['page_date']
        if isinstance(page_date, str):
            page_date = datetime.fromisoformat(page_date).date()
        date_display = page_date.strftime("%B %d, %Y")
        total_alerts += p.get('alert_count', 0)
        pages_html += f"""
        <li>
            <a href="/alerts/daily/{page_date.isoformat()}">
                <span class="date">{date_display}</span>
                <span class="count">{p['alert_count']} alerts</span>
            </a>
        </li>
        """
    
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Risk Alerts - {month_display} | EnergyRiskIQ</title>
        <meta name="description" content="Geopolitical and energy risk alerts archive for {month_display}. {len(pages)} days of risk intelligence with {total_alerts} total alerts.">
        <link rel="canonical" href="{BASE_URL}/alerts/{year}/{month:02d}">
        {get_common_styles()}
    </head>
    <body>
        {render_nav()}
        {render_cta_section("top")}
        <main>
            <div class="container">
                <div class="breadcrumbs">
                    <a href="/">Home</a> / <a href="/alerts">Alerts</a> / {month_display}
                </div>
                <h1>Risk Alerts - {month_display}</h1>
                <p class="meta">{len(pages)} days of alerts | {total_alerts} total alerts</p>
                
                <h2>Daily Pages</h2>
                <ul class="page-list">
                    {pages_html if pages_html else '<li>No daily pages for this month.</li>'}
                </ul>
                
                {render_cta_section("mid")}
                
                <div class="disclaimer">
                    <strong>Disclaimer:</strong> This information is provided for general informational purposes only and does not constitute financial, investment, or trading advice.
                </div>
            </div>
        </main>
        {render_footer()}
    </body>
    </html>
    """
    
    return HTMLResponse(content=html, headers={"Cache-Control": "public, max-age=86400"})


@router.get("/sitemap.xml", response_class=Response)
async def sitemap_xml():
    """Generate XML sitemap with lastmod dates."""
    entries = generate_sitemap_entries()
    
    xml_entries = ""
    for e in entries:
        lastmod_tag = f"\n        <lastmod>{e['lastmod']}</lastmod>" if e.get('lastmod') else ""
        xml_entries += f"""
    <url>
        <loc>{BASE_URL}{e['loc']}</loc>{lastmod_tag}
        <priority>{e['priority']}</priority>
        <changefreq>{e['changefreq']}</changefreq>
    </url>"""
    
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{xml_entries}
</urlset>"""
    
    return Response(content=xml, media_type="application/xml")


@router.get("/sitemap.html", response_class=HTMLResponse)
async def sitemap_html():
    """Human-readable HTML sitemap."""
    track_page_view("sitemap", "/sitemap.html")
    
    recent_pages = get_recent_daily_pages(limit=90)
    months = get_available_months()
    
    daily_html = ""
    for p in recent_pages:
        page_date = p['page_date']
        if isinstance(page_date, str):
            page_date = datetime.fromisoformat(page_date).date()
        date_display = page_date.strftime("%B %d, %Y")
        daily_html += f'<li><a href="/alerts/daily/{page_date.isoformat()}">{date_display}</a> ({p["alert_count"]} alerts)</li>'
    
    monthly_html = ""
    for m in months:
        month_display = f"{month_name[m['month']]} {m['year']}"
        monthly_html += f'<li><a href="/alerts/{m["year"]}/{m["month"]:02d}">{month_display}</a> ({m["page_count"]} days)</li>'
    
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Sitemap | EnergyRiskIQ</title>
        <meta name="description" content="Complete sitemap for EnergyRiskIQ - navigate all pages including daily alerts, monthly archives, and more.">
        <link rel="canonical" href="{BASE_URL}/sitemap.html">
        {get_common_styles()}
    </head>
    <body>
        {render_nav()}
        <main>
            <div class="container">
                <h1>Sitemap</h1>
                
                <h2>Main Pages</h2>
                <ul class="page-list" style="list-style: disc; padding-left: 1.5rem;">
                    <li><a href="/">Homepage</a></li>
                    <li><a href="/geri">Global Energy Risk Index (GERI)</a></li>
                    <li><a href="/alerts">Alerts Hub</a></li>
                    <li><a href="/users">Sign Up / Login</a></li>
                    <li><a href="/privacy">Privacy Policy</a></li>
                    <li><a href="/terms">Terms of Service</a></li>
                </ul>
                
                <h2>Monthly Archives</h2>
                <ul class="page-list" style="list-style: disc; padding-left: 1.5rem;">
                    {monthly_html if monthly_html else '<li>No archives available yet.</li>'}
                </ul>
                
                <h2>Daily Alert Pages</h2>
                <ul class="page-list" style="list-style: disc; padding-left: 1.5rem; max-height: 400px; overflow-y: auto;">
                    {daily_html if daily_html else '<li>No daily pages available yet.</li>'}
                </ul>
            </div>
        </main>
        {render_footer()}
    </body>
    </html>
    """
    
    return HTMLResponse(content=html)


@router.get("/geri", response_class=HTMLResponse)
async def geri_page(request: Request):
    """
    GERI Index Page - Single canonical page with plan-based data.
    
    - Unauthenticated: Shows 24h delayed GERI
    - Authenticated: Shows real-time GERI
    
    Googlebot always sees delayed version (not logged in).
    """
    track_page_view("geri", "/geri")
    
    user_id = None
    x_user_token = request.headers.get('x-user-token')
    if x_user_token:
        try:
            from src.api.user_routes import verify_user_session
            session = verify_user_session(x_user_token)
            user_id = session.get('user_id')
        except:
            pass
    
    geri = get_geri_for_user(user_id)
    
    if not geri:
        geri_content = """
        <div class="geri-unavailable">
            <h2>GERI Data Coming Soon</h2>
            <p>The Global Energy Risk Index is being computed. Check back shortly.</p>
        </div>
        """
        is_delayed = True
        badge_label = "24h Delayed"
        badge_class = "delayed"
    else:
        is_delayed = geri.is_delayed
        badge_label = "24h Delayed" if is_delayed else "Real-time"
        badge_class = "delayed" if is_delayed else "realtime"
        
        band_colors = {
            'LOW': '#22c55e',
            'MODERATE': '#eab308',
            'ELEVATED': '#f97316',
            'CRITICAL': '#ef4444',
            'SEVERE': '#dc2626'
        }
        band_color = band_colors.get(geri.band, '#6b7280')
        
        trend_display = ""
        if geri.trend_7d is not None:
            trend_arrow = "+" if geri.trend_7d > 0 else ""
            trend_color = "#ef4444" if geri.trend_7d > 0 else "#22c55e" if geri.trend_7d < 0 else "#6b7280"
            trend_display = f'<span style="color: {trend_color}; font-size: 0.9rem;">{trend_arrow}{geri.trend_7d:.1f} vs 7-day avg</span>'
        
        drivers_html = ""
        for driver in geri.top_drivers[:5]:
            drivers_html += f'<li>{driver}</li>'
        if not drivers_html:
            drivers_html = '<li>No significant drivers detected</li>'
        
        regions_html = ""
        for region in geri.top_regions[:5]:
            regions_html += f'<li>{region}</li>'
        if not regions_html:
            regions_html = '<li>No regional hotspots</li>'
        
        geri_content = f"""
        <div class="geri-metric-card">
            <div class="geri-badge {badge_class}">{badge_label}</div>
            <div class="geri-value" style="color: {band_color};">{geri.value}</div>
            <div class="geri-band" style="color: {band_color};">{geri.band}</div>
            {trend_display}
            <div class="geri-date">As of {geri.date}</div>
        </div>
        
        <div class="geri-sections">
            <div class="geri-section">
                <h2>Top Drivers</h2>
                <ul class="geri-list">{drivers_html}</ul>
            </div>
            
            <div class="geri-section">
                <h2>Top Regions</h2>
                <ul class="geri-list">{regions_html}</ul>
            </div>
        </div>
        """
    
    cta_block = ""
    if is_delayed:
        cta_block = """
        <div class="geri-cta">
            <h3>Get Real-time Access</h3>
            <p>Unlock instant GERI updates with a Pro subscription.</p>
            <a href="/users" class="cta-button primary">Unlock Real-time GERI</a>
            <a href="/alerts" class="cta-button secondary">See Alert Archive</a>
        </div>
        """
    
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Global Energy Risk Index (GERI) | EnergyRiskIQ</title>
        <meta name="description" content="Track the Global Energy Risk Index (GERI) - a daily composite measure of energy market risk. Free 24h delayed access, real-time for Pro subscribers.">
        <link rel="canonical" href="{BASE_URL}/geri">
        
        <meta property="og:title" content="Global Energy Risk Index (GERI) | EnergyRiskIQ">
        <meta property="og:description" content="Track energy market risk with the Global Energy Risk Index. Daily updates on risk levels, drivers, and regional hotspots.">
        <meta property="og:url" content="{BASE_URL}/geri">
        <meta property="og:type" content="website">
        
        <link rel="icon" type="image/png" href="/favicon.png">
        {get_common_styles()}
        <style>
            .geri-hero {{
                text-align: center;
                padding: 2rem 0;
            }}
            .geri-hero h1 {{
                font-size: 2rem;
                margin-bottom: 0.5rem;
            }}
            .geri-hero p {{
                color: #9ca3af;
                max-width: 600px;
                margin: 0 auto;
            }}
            .geri-metric-card {{
                background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
                border: 1px solid #334155;
                border-radius: 1rem;
                padding: 2rem;
                text-align: center;
                max-width: 400px;
                margin: 2rem auto;
                position: relative;
            }}
            .geri-badge {{
                position: absolute;
                top: 1rem;
                right: 1rem;
                padding: 0.25rem 0.75rem;
                border-radius: 9999px;
                font-size: 0.75rem;
                font-weight: 600;
                text-transform: uppercase;
            }}
            .geri-badge.delayed {{
                background: #374151;
                color: #9ca3af;
            }}
            .geri-badge.realtime {{
                background: #22c55e;
                color: #052e16;
            }}
            .geri-value {{
                font-size: 4rem;
                font-weight: 700;
                line-height: 1;
            }}
            .geri-band {{
                font-size: 1.25rem;
                font-weight: 600;
                margin-top: 0.5rem;
            }}
            .geri-date {{
                color: #6b7280;
                font-size: 0.875rem;
                margin-top: 1rem;
            }}
            .geri-sections {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
                gap: 1.5rem;
                margin: 2rem 0;
            }}
            .geri-section {{
                background: #1e293b;
                border: 1px solid #334155;
                border-radius: 0.75rem;
                padding: 1.5rem;
            }}
            .geri-section h2 {{
                font-size: 1.125rem;
                margin-bottom: 1rem;
                color: #f8fafc;
            }}
            .geri-list {{
                list-style: disc;
                padding-left: 1.25rem;
                color: #d1d5db;
            }}
            .geri-list li {{
                margin-bottom: 0.5rem;
            }}
            .geri-cta {{
                background: linear-gradient(135deg, #1e3a5f 0%, #0f172a 100%);
                border: 1px solid #3b82f6;
                border-radius: 1rem;
                padding: 2rem;
                text-align: center;
                margin: 2rem 0;
            }}
            .geri-cta h3 {{
                color: #60a5fa;
                margin-bottom: 0.5rem;
            }}
            .geri-cta p {{
                color: #9ca3af;
                margin-bottom: 1.5rem;
            }}
            .cta-button {{
                display: inline-block;
                padding: 0.75rem 1.5rem;
                border-radius: 0.5rem;
                font-weight: 600;
                text-decoration: none;
                margin: 0.25rem;
            }}
            .cta-button.primary {{
                background: #3b82f6;
                color: white;
            }}
            .cta-button.secondary {{
                background: transparent;
                border: 1px solid #6b7280;
                color: #d1d5db;
            }}
            .geri-links {{
                text-align: center;
                margin: 2rem 0;
            }}
            .geri-links a {{
                color: #60a5fa;
                margin: 0 1rem;
            }}
            .geri-unavailable {{
                text-align: center;
                padding: 3rem;
                color: #9ca3af;
            }}
        </style>
    </head>
    <body>
        {render_nav()}
        <main>
            <div class="container">
                <div class="geri-hero">
                    <h1>Global Energy Risk Index (GERI)</h1>
                    <p>A daily composite measure of energy market risk, computed from alert severity, regional concentration, and asset exposure.</p>
                </div>
                
                {geri_content}
                
                {cta_block}
                
                <div class="geri-links">
                    <a href="/geri/history">View History</a>
                    <a href="/alerts">Alert Archive</a>
                </div>
            </div>
        </main>
        {render_footer()}
    </body>
    </html>
    """
    
    return HTMLResponse(content=html, headers={"Cache-Control": "public, max-age=300"})
