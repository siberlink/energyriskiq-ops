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
from src.geri.geri_history_service import (
    get_snapshot_by_date,
    list_snapshots,
    list_monthly,
    get_available_months as get_geri_available_months,
    get_monthly_stats,
    get_adjacent_dates,
    get_adjacent_months,
    get_all_snapshot_dates,
    get_latest_published_snapshot
)
from calendar import month_name as calendar_month_name

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


def get_geri_common_styles():
    """Return common styles for GERI history pages."""
    return """
    <style>
        .geri-table { width: 100%; border-collapse: collapse; margin: 1.5rem 0; }
        .geri-table th, .geri-table td { padding: 0.75rem 1rem; text-align: left; border-bottom: 1px solid #e2e8f0; }
        .geri-table th { background: #f8fafc; font-weight: 600; color: #475569; }
        .geri-table tr:hover { background: #f1f5f9; }
        .geri-table a { color: #3b82f6; text-decoration: none; }
        .geri-table a:hover { text-decoration: underline; }
        .band-low { color: #22c55e; }
        .band-moderate { color: #eab308; }
        .band-elevated { color: #f97316; }
        .band-critical, .band-severe { color: #ef4444; }
        .month-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 1rem; margin: 1.5rem 0; }
        .month-card { background: #1e293b; border: 1px solid #334155; border-radius: 0.5rem; padding: 1rem; text-align: center; }
        .month-card a { color: #f8fafc; text-decoration: none; font-weight: 600; }
        .month-card:hover { border-color: #3b82f6; }
        .breadcrumbs { margin-bottom: 1.5rem; color: #9ca3af; }
        .breadcrumbs a { color: #60a5fa; text-decoration: none; }
        .breadcrumbs a:hover { text-decoration: underline; }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 1rem; margin: 1.5rem 0; }
        .stat-card { background: #1e293b; border: 1px solid #334155; border-radius: 0.5rem; padding: 1rem; text-align: center; }
        .stat-value { font-size: 1.5rem; font-weight: 700; color: #f8fafc; }
        .stat-label { font-size: 0.875rem; color: #9ca3af; margin-top: 0.25rem; }
        .nav-arrows { display: flex; justify-content: space-between; margin: 1.5rem 0; }
        .nav-arrow { color: #60a5fa; text-decoration: none; }
        .nav-arrow:hover { text-decoration: underline; }
        .nav-arrow.disabled { color: #6b7280; pointer-events: none; }
    </style>
    """


@router.get("/geri/history", response_class=HTMLResponse)
async def geri_history_page():
    """
    GERI History Hub - Lists all available GERI snapshots.
    Public page showing the official published archive.
    """
    track_page_view("geri_history", "/geri/history")
    
    snapshots = list_snapshots(limit=90)
    months = get_geri_available_months()
    latest = get_latest_published_snapshot()
    
    latest_date = latest.date if latest else None
    
    rows_html = ""
    for s in snapshots:
        band_class = f"band-{s.band.lower()}"
        trend_display = f"{s.trend_7d:+.1f}" if s.trend_7d is not None else "-"
        rows_html += f"""
        <tr>
            <td><a href="/geri/{s.date}">{s.date}</a></td>
            <td>{s.value}</td>
            <td class="{band_class}">{s.band}</td>
            <td>{trend_display}</td>
        </tr>
        """
    
    if not rows_html:
        rows_html = '<tr><td colspan="4" style="text-align: center; color: #9ca3af;">No history available yet.</td></tr>'
    
    months_html = ""
    for m in months[:24]:
        month_display = f"{calendar_month_name[m['month']]} {m['year']}"
        months_html += f"""
        <div class="month-card">
            <a href="/geri/{m['year']}/{m['month']:02d}">{month_display}</a>
            <div style="color: #9ca3af; font-size: 0.875rem;">{m['snapshot_count']} days</div>
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
        <title>Global Energy Risk Index History | EnergyRiskIQ</title>
        <meta name="description" content="Complete history of the Global Energy Risk Index (GERI). Browse daily snapshots and monthly archives of energy market risk data.">
        <link rel="canonical" href="{BASE_URL}/geri/history">
        <link rel="icon" type="image/png" href="/favicon.png">
        {get_common_styles()}
        {get_geri_common_styles()}
    </head>
    <body>
        {render_nav()}
        <main>
            <div class="container">
                <div class="breadcrumbs">
                    <a href="/geri">GERI</a> &raquo; History
                </div>
                
                <h1>Global Energy Risk Index (GERI) History</h1>
                <p style="color: #9ca3af; margin-bottom: 2rem;">
                    The official published archive of daily GERI snapshots. 
                    Each snapshot represents the computed energy market risk for that day.
                </p>
                
                <h2>Monthly Archives</h2>
                <div class="month-grid">
                    {months_html}
                </div>
                
                <h2>Recent Snapshots</h2>
                <table class="geri-table">
                    <thead>
                        <tr>
                            <th>Date</th>
                            <th>Value</th>
                            <th>Band</th>
                            <th>7d Trend</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows_html}
                    </tbody>
                </table>
                
                <div style="text-align: center; margin-top: 2rem;">
                    <a href="/geri" style="color: #60a5fa;">Back to Today's GERI</a>
                </div>
            </div>
        </main>
        {render_footer()}
    </body>
    </html>
    """
    
    return HTMLResponse(content=html, headers={"Cache-Control": "public, max-age=3600"})


@router.get("/geri/methodology", response_class=HTMLResponse)
async def geri_methodology_page():
    """
    GERI Methodology Page - Static page explaining the index construction.
    """
    track_page_view("geri_methodology", "/geri/methodology")
    
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Global Energy Risk Index (GERI) — Methodology & Construction | EnergyRiskIQ</title>
        <meta name="description" content="Learn how the Global Energy Risk Index (GERI) measures systemic geopolitical and supply risk in global energy markets through daily event analysis and structured risk signals.">
        <link rel="canonical" href="{BASE_URL}/geri/methodology">
        
        <meta property="og:title" content="Global Energy Risk Index (GERI) — Methodology & Construction | EnergyRiskIQ">
        <meta property="og:description" content="Learn how GERI measures systemic geopolitical and supply risk in global energy markets through daily event analysis.">
        <meta property="og:url" content="{BASE_URL}/geri/methodology">
        <meta property="og:type" content="article">
        
        <link rel="icon" type="image/png" href="/favicon.png">
        {get_common_styles()}
        <style>
            .methodology-hero {{
                text-align: center;
                padding: 4rem 0 2rem;
                max-width: 800px;
                margin: 0 auto;
            }}
            .methodology-hero h1 {{
                font-size: 2.5rem;
                font-weight: 700;
                color: #1a1a2e;
                margin-bottom: 0.5rem;
                line-height: 1.2;
            }}
            .methodology-hero .subtitle {{
                font-size: 1.5rem;
                font-weight: 600;
                color: #0066FF;
                margin-bottom: 1.5rem;
            }}
            .methodology-hero h2 {{
                font-size: 1.25rem;
                font-weight: 400;
                color: #64748b;
                font-style: italic;
                max-width: 700px;
                margin: 0 auto;
                line-height: 1.6;
            }}
            .methodology-content {{
                max-width: 800px;
                margin: 3rem auto;
                padding: 0 1rem;
            }}
            .methodology-section {{
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 1rem;
                padding: 2rem;
                margin-bottom: 2rem;
                box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
            }}
            .methodology-section h3 {{
                font-size: 1.25rem;
                font-weight: 600;
                color: #1a1a2e;
                margin-bottom: 1rem;
                display: flex;
                align-items: center;
                gap: 0.75rem;
            }}
            .methodology-section h3 .icon {{
                width: 32px;
                height: 32px;
                background: linear-gradient(135deg, #0066FF 0%, #0052CC 100%);
                border-radius: 8px;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 1rem;
            }}
            .methodology-section p {{
                color: #475569;
                line-height: 1.8;
                margin-bottom: 1rem;
            }}
            .methodology-section ul {{
                color: #475569;
                line-height: 1.8;
                padding-left: 1.5rem;
            }}
            .methodology-section li {{
                margin-bottom: 0.5rem;
            }}
            .section-icon {{
                font-size: 1.25rem;
                margin-right: 0.5rem;
            }}
            .feature-list {{
                list-style: none;
                padding-left: 0;
                margin: 1.5rem 0;
            }}
            .feature-list li {{
                display: flex;
                align-items: center;
                padding: 0.75rem 1rem;
                background: #f1f5f9;
                border-radius: 0.5rem;
                margin-bottom: 0.5rem;
                font-weight: 500;
                color: #334155;
            }}
            .list-icon {{
                font-size: 1.25rem;
                margin-right: 0.75rem;
            }}
            .simple-list {{
                list-style: none;
                padding-left: 0;
                margin: 1rem 0;
                display: flex;
                flex-wrap: wrap;
                gap: 0.75rem;
            }}
            .simple-list li {{
                background: #e0f2fe;
                color: #0369a1;
                padding: 0.5rem 1rem;
                border-radius: 2rem;
                font-weight: 500;
                font-size: 0.95rem;
            }}
            .highlight-block {{
                background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
                border-left: 4px solid #f59e0b;
                border-radius: 0.5rem;
                padding: 1.5rem;
                margin: 1.5rem 0;
                text-align: center;
            }}
            .highlight-text {{
                font-size: 1.1rem;
                color: #92400e;
                line-height: 1.8;
                margin: 0;
            }}
            .highlight-text strong {{
                color: #78350f;
                font-size: 1.25rem;
            }}
            .quote-block {{
                background: linear-gradient(135deg, #ede9fe 0%, #ddd6fe 100%);
                border-left: 4px solid #7c3aed;
                border-radius: 0.5rem;
                padding: 1.5rem 2rem;
                margin: 1.5rem 0;
            }}
            .quote-block p {{
                font-size: 1.15rem;
                font-style: italic;
                color: #5b21b6;
                margin: 0;
                font-weight: 500;
            }}
            .risk-category {{
                background: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 0.75rem;
                padding: 1.25rem 1.5rem;
                margin: 1rem 0;
            }}
            .risk-category h4 {{
                font-size: 1.1rem;
                font-weight: 600;
                color: #1e293b;
                margin: 0 0 0.75rem 0;
                display: flex;
                align-items: center;
                gap: 0.5rem;
            }}
            .category-icon {{
                font-size: 1.25rem;
            }}
            .category-list {{
                list-style: none;
                padding-left: 0;
                margin: 0;
            }}
            .category-list li {{
                padding: 0.35rem 0 0.35rem 1.5rem;
                position: relative;
                color: #475569;
                font-size: 0.95rem;
            }}
            .category-list li::before {{
                content: "•";
                position: absolute;
                left: 0.5rem;
                color: #94a3b8;
            }}
            .section-summary {{
                background: linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%);
                border-left: 4px solid #10b981;
                border-radius: 0.5rem;
                padding: 1.25rem 1.5rem;
                margin-top: 1.5rem;
                font-weight: 500;
                color: #065f46;
            }}
            .methodology-nav {{
                display: flex;
                justify-content: center;
                gap: 1rem;
                margin: 3rem 0;
                flex-wrap: wrap;
            }}
            .methodology-nav a {{
                padding: 0.75rem 1.5rem;
                border-radius: 0.5rem;
                text-decoration: none;
                font-weight: 500;
                transition: all 0.2s ease;
            }}
            .methodology-nav a.primary {{
                background: #0066FF;
                color: white;
            }}
            .methodology-nav a.primary:hover {{
                background: #0052CC;
            }}
            .methodology-nav a.secondary {{
                background: #e2e8f0;
                color: #1a1a2e;
            }}
            .methodology-nav a.secondary:hover {{
                background: #cbd5e1;
            }}
            .breadcrumbs {{
                color: #64748b;
                margin-bottom: 1rem;
                font-size: 0.875rem;
            }}
            .breadcrumbs a {{
                color: #0066FF;
                text-decoration: none;
            }}
            .breadcrumbs a:hover {{
                text-decoration: underline;
            }}
            @media (max-width: 768px) {{
                .methodology-hero {{
                    padding: 2rem 0 1rem;
                }}
                .methodology-hero h1 {{
                    font-size: 1.5rem;
                }}
                .methodology-hero .subtitle {{
                    font-size: 1.1rem;
                }}
                .methodology-hero h2 {{
                    font-size: 0.95rem;
                    padding: 0 0.5rem;
                }}
                .methodology-content {{
                    padding: 0 0.5rem;
                    margin: 2rem auto;
                }}
                .methodology-section {{
                    padding: 1.25rem;
                    border-radius: 0.75rem;
                }}
                .methodology-section h3 {{
                    font-size: 1.1rem;
                    flex-wrap: wrap;
                }}
                .methodology-section p {{
                    font-size: 0.95rem;
                    line-height: 1.7;
                }}
                .feature-list li {{
                    padding: 0.6rem 0.75rem;
                    font-size: 0.9rem;
                }}
                .list-icon {{
                    font-size: 1.1rem;
                    margin-right: 0.5rem;
                }}
                .methodology-nav {{
                    flex-direction: column;
                    align-items: center;
                    gap: 0.75rem;
                    margin: 2rem 0;
                }}
                .methodology-nav a {{
                    width: 100%;
                    max-width: 280px;
                    text-align: center;
                }}
                .breadcrumbs {{
                    font-size: 0.8rem;
                    padding: 0 0.5rem;
                }}
                .simple-list {{
                    justify-content: center;
                }}
                .simple-list li {{
                    font-size: 0.85rem;
                    padding: 0.4rem 0.75rem;
                }}
                .highlight-block {{
                    padding: 1rem;
                }}
                .highlight-text {{
                    font-size: 1rem;
                }}
                .highlight-text strong {{
                    font-size: 1.1rem;
                }}
                .quote-block {{
                    padding: 1rem 1.25rem;
                }}
                .quote-block p {{
                    font-size: 1rem;
                }}
                .risk-category {{
                    padding: 1rem 1.25rem;
                }}
                .risk-category h4 {{
                    font-size: 1rem;
                }}
                .category-list li {{
                    font-size: 0.9rem;
                }}
                .section-summary {{
                    padding: 1rem 1.25rem;
                    font-size: 0.95rem;
                }}
            }}
            @media (max-width: 480px) {{
                .methodology-hero h1 {{
                    font-size: 1.25rem;
                }}
                .methodology-hero .subtitle {{
                    font-size: 1rem;
                }}
                .methodology-hero h2 {{
                    font-size: 0.875rem;
                }}
                .methodology-section {{
                    padding: 1rem;
                }}
                .methodology-section h3 {{
                    font-size: 1rem;
                }}
            }}
        </style>
    </head>
    <body>
        {render_nav()}
        <main style="background: #f8fafc; min-height: 100vh; padding-bottom: 4rem;">
            <div class="container">
                <div class="breadcrumbs">
                    <a href="/geri">GERI</a> &raquo; Methodology
                </div>
                
                <div class="methodology-hero">
                    <h1>Global Energy Risk Index (GERI)</h1>
                    <div class="subtitle">Methodology & Construction</div>
                    <h2>"Measuring systemic risk in global energy markets — daily, transparent, and institutional-grade."</h2>
                </div>
                
                <div class="methodology-nav">
                    <a href="/geri" class="primary">View Current GERI</a>
                    <a href="/geri/history" class="secondary">Browse History</a>
                </div>
                
                <div class="methodology-content">
                    <div class="methodology-section">
                        <h3><span class="section-icon">🔹</span> Introduction — What is GERI?</h3>
                        <p>The Global Energy Risk Index (GERI) is a daily indicator designed to measure the level of systemic risk affecting global energy markets.</p>
                        <p>It captures how geopolitical tensions, supply disruptions, regulatory changes, and structural stresses influence the stability of:</p>
                        <ul class="feature-list">
                            <li><span class="list-icon">🛢️</span> Oil markets</li>
                            <li><span class="list-icon">🔥</span> Natural gas markets</li>
                            <li><span class="list-icon">⚡</span> Electricity systems</li>
                            <li><span class="list-icon">🚢</span> Energy trade routes</li>
                            <li><span class="list-icon">🔗</span> Energy-dependent supply chains</li>
                        </ul>
                        <p>GERI provides a single, interpretable number that reflects the current risk environment of the global energy system.</p>
                        <p>It is published daily, archived permanently, and built for professionals who need to understand risk before it becomes price.</p>
                    </div>
                    
                    <div class="methodology-section">
                        <h3><span class="section-icon">🎯</span> Why GERI Exists — The Problem It Solves</h3>
                        <p>Energy markets are no longer driven by fundamentals alone.</p>
                        <p>They are increasingly shaped by:</p>
                        <ul class="feature-list">
                            <li><span class="list-icon">⚔️</span> Geopolitical conflicts</li>
                            <li><span class="list-icon">🚫</span> Sanctions and trade restrictions</li>
                            <li><span class="list-icon">🔧</span> Production outages</li>
                            <li><span class="list-icon">🚢</span> Shipping disruptions</li>
                            <li><span class="list-icon">📜</span> Regulatory interventions</li>
                            <li><span class="list-icon">🏗️</span> Infrastructure fragility</li>
                            <li><span class="list-icon">🌪️</span> Extreme weather</li>
                        </ul>
                        <div class="highlight-block">
                            <p class="highlight-text">Prices react late.<br>Volatility reacts late.<br><strong>Risk builds early.</strong></p>
                        </div>
                        <p>Traditional indicators focus on:</p>
                        <ul class="simple-list">
                            <li>📈 Prices</li>
                            <li>📊 Returns</li>
                            <li>📉 Volatility</li>
                        </ul>
                        <p>They rarely capture the structural stress building inside the system.</p>
                        <div class="quote-block">
                            <p>"How risky is the global energy system today compared to normal?"</p>
                        </div>
                        <p>GERI was created to answer this question. By focusing on systemic risk rather than price, GERI provides early visibility into pressures that often emerge before markets move.</p>
                    </div>
                    
                    <div class="methodology-section">
                        <h3><span class="section-icon">🔍</span> What GERI Measures</h3>
                        <p>GERI measures <strong>risk pressure</strong>, not performance.</p>
                        <p>Specifically, it monitors:</p>
                        
                        <div class="risk-category">
                            <h4><span class="category-icon">⚔️</span> Geopolitical Risk</h4>
                            <ul class="category-list">
                                <li>Conflicts in energy-producing regions</li>
                                <li>International tensions</li>
                                <li>Military escalations affecting supply routes</li>
                            </ul>
                        </div>
                        
                        <div class="risk-category">
                            <h4><span class="category-icon">🛢️</span> Production & Infrastructure Risk</h4>
                            <ul class="category-list">
                                <li>Outages and unplanned shutdowns</li>
                                <li>Refinery and terminal disruptions</li>
                                <li>Pipeline and grid incidents</li>
                            </ul>
                        </div>
                        
                        <div class="risk-category">
                            <h4><span class="category-icon">🚢</span> Transport & Logistics Risk</h4>
                            <ul class="category-list">
                                <li>Shipping bottlenecks</li>
                                <li>Chokepoint disruptions</li>
                                <li>Freight and port instability</li>
                            </ul>
                        </div>
                        
                        <div class="risk-category">
                            <h4><span class="category-icon">🏛️</span> Policy & Regulatory Risk</h4>
                            <ul class="category-list">
                                <li>Sanctions</li>
                                <li>Export restrictions</li>
                                <li>Regulatory interventions</li>
                                <li>Strategic reserve actions</li>
                            </ul>
                        </div>
                        
                        <div class="risk-category">
                            <h4><span class="category-icon">🌪️</span> Environmental & Structural Risk</h4>
                            <ul class="category-list">
                                <li>Extreme weather events</li>
                                <li>Climate-related infrastructure stress</li>
                                <li>Long-term system fragility</li>
                            </ul>
                        </div>
                        
                        <p class="section-summary">GERI reflects how these forces combine to shape the structural stability of the global energy system.</p>
                    </div>
                </div>
                
                <div class="methodology-nav">
                    <a href="/geri" class="primary">View Current GERI</a>
                    <a href="/geri/history" class="secondary">Browse History</a>
                </div>
            </div>
        </main>
        {render_footer()}
    </body>
    </html>
    """
    
    return HTMLResponse(content=html, headers={"Cache-Control": "public, max-age=86400"})


@router.get("/geri/{date:path}", response_class=HTMLResponse)
async def geri_daily_page(date: str):
    """
    GERI Daily Snapshot Page - Shows a specific day's GERI data.
    Returns 404 if the date doesn't exist in the archive.
    """
    import re
    
    month_match = re.match(r'^(\d{4})/(\d{2})$', date)
    if month_match:
        year = int(month_match.group(1))
        month = int(month_match.group(2))
        return await geri_monthly_page(year, month)
    
    date_match = re.match(r'^(\d{4})-(\d{2})-(\d{2})$', date)
    if not date_match:
        raise HTTPException(status_code=404, detail="Invalid date format. Use YYYY-MM-DD.")
    
    track_page_view("geri_daily", f"/geri/{date}")
    
    snapshot = get_snapshot_by_date(date)
    
    if not snapshot:
        html = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>GERI {date} Not Found | EnergyRiskIQ</title>
            <link rel="icon" type="image/png" href="/favicon.png">
            {get_common_styles()}
        </head>
        <body>
            {render_nav()}
            <main>
                <div class="container" style="text-align: center; padding: 4rem 0;">
                    <h1>Snapshot Not Found</h1>
                    <p style="color: #9ca3af;">No GERI data available for {date}.</p>
                    <p><a href="/geri/history" style="color: #60a5fa;">Browse History</a></p>
                </div>
            </main>
            {render_footer()}
        </body>
        </html>
        """
        return HTMLResponse(content=html, status_code=404)
    
    adjacent = get_adjacent_dates(date)
    
    year = int(date[:4])
    month = int(date[5:7])
    
    band_colors = {
        'LOW': '#22c55e',
        'MODERATE': '#eab308',
        'ELEVATED': '#f97316',
        'CRITICAL': '#ef4444',
        'SEVERE': '#dc2626'
    }
    band_color = band_colors.get(snapshot.band, '#6b7280')
    
    trend_display = ""
    if snapshot.trend_7d is not None:
        trend_arrow = "+" if snapshot.trend_7d > 0 else ""
        trend_color = "#ef4444" if snapshot.trend_7d > 0 else "#22c55e" if snapshot.trend_7d < 0 else "#6b7280"
        trend_display = f'<p style="color: {trend_color};">{trend_arrow}{snapshot.trend_7d:.1f} vs 7-day average</p>'
    
    drivers_html = ""
    for driver in snapshot.top_drivers[:5]:
        drivers_html += f'<li>{driver}</li>'
    if not drivers_html:
        drivers_html = '<li style="color: #9ca3af;">No significant drivers</li>'
    
    regions_html = ""
    for region in snapshot.top_regions[:5]:
        regions_html += f'<li>{region}</li>'
    if not regions_html:
        regions_html = '<li style="color: #9ca3af;">No regional hotspots</li>'
    
    prev_link = f'<a class="nav-arrow" href="/geri/{adjacent["prev"]}">&larr; {adjacent["prev"]}</a>' if adjacent['prev'] else '<span class="nav-arrow disabled">&larr; No earlier</span>'
    next_link = f'<a class="nav-arrow" href="/geri/{adjacent["next"]}">{adjacent["next"]} &rarr;</a>' if adjacent['next'] else '<span class="nav-arrow disabled">No later &rarr;</span>'
    
    from datetime import datetime
    human_date = datetime.strptime(date, "%Y-%m-%d").strftime("%B %d, %Y")
    
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Global Energy Risk Index {date} | EnergyRiskIQ</title>
        <meta name="description" content="GERI snapshot for {human_date}. Value: {snapshot.value}, Band: {snapshot.band}. View historical energy market risk data.">
        <link rel="canonical" href="{BASE_URL}/geri/{date}">
        <link rel="icon" type="image/png" href="/favicon.png">
        {get_common_styles()}
        {get_geri_common_styles()}
        <style>
            .snapshot-card {{
                background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
                border: 1px solid #334155;
                border-radius: 1rem;
                padding: 2rem;
                text-align: center;
                max-width: 400px;
                margin: 2rem auto;
            }}
            .snapshot-value {{
                font-size: 4rem;
                font-weight: 700;
                line-height: 1;
            }}
            .snapshot-band {{
                font-size: 1.25rem;
                font-weight: 600;
                margin-top: 0.5rem;
            }}
            .snapshot-date {{
                color: #9ca3af;
                margin-top: 1rem;
            }}
            .drivers-regions {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
                gap: 1.5rem;
                margin: 2rem 0;
            }}
            .section-card {{
                background: #1e293b;
                border: 1px solid #334155;
                border-radius: 0.75rem;
                padding: 1.5rem;
            }}
            .section-card h2 {{
                font-size: 1.125rem;
                margin-bottom: 1rem;
                color: #f8fafc;
            }}
            .section-card ul {{
                list-style: disc;
                padding-left: 1.25rem;
                color: #d1d5db;
            }}
            .section-card li {{
                margin-bottom: 0.5rem;
            }}
        </style>
    </head>
    <body>
        {render_nav()}
        <main>
            <div class="container">
                <div class="breadcrumbs">
                    <a href="/geri">GERI</a> &raquo; 
                    <a href="/geri/history">History</a> &raquo; 
                    <a href="/geri/{year}/{month:02d}">{calendar_month_name[month]} {year}</a> &raquo;
                    {date}
                </div>
                
                <h1>Global Energy Risk Index - {human_date}</h1>
                
                <div class="snapshot-card">
                    <div class="snapshot-value" style="color: {band_color};">{snapshot.value}</div>
                    <div class="snapshot-band" style="color: {band_color};">{snapshot.band}</div>
                    {trend_display}
                    <div class="snapshot-date">Published: {date}</div>
                </div>
                
                <div class="drivers-regions">
                    <div class="section-card">
                        <h2>Top Drivers</h2>
                        <ul>{drivers_html}</ul>
                    </div>
                    <div class="section-card">
                        <h2>Top Regions</h2>
                        <ul>{regions_html}</ul>
                    </div>
                </div>
                
                <div class="nav-arrows">
                    {prev_link}
                    {next_link}
                </div>
                
                <div style="text-align: center; margin-top: 2rem;">
                    <a href="/geri/history" style="color: #60a5fa;">View Full History</a>
                </div>
            </div>
        </main>
        {render_footer()}
    </body>
    </html>
    """
    
    return HTMLResponse(content=html, headers={"Cache-Control": "public, max-age=86400"})


async def geri_monthly_page(year: int, month: int):
    """
    GERI Monthly Archive Hub - Shows all snapshots for a specific month.
    """
    if month < 1 or month > 12:
        raise HTTPException(status_code=404, detail="Invalid month.")
    
    track_page_view("geri_monthly", f"/geri/{year}/{month:02d}")
    
    snapshots = list_monthly(year, month)
    stats = get_monthly_stats(year, month)
    
    if not snapshots:
        html = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>GERI {calendar_month_name[month]} {year} Not Found | EnergyRiskIQ</title>
            <link rel="icon" type="image/png" href="/favicon.png">
            {get_common_styles()}
        </head>
        <body>
            {render_nav()}
            <main>
                <div class="container" style="text-align: center; padding: 4rem 0;">
                    <h1>No Data Available</h1>
                    <p style="color: #9ca3af;">No GERI data available for {calendar_month_name[month]} {year}.</p>
                    <p><a href="/geri/history" style="color: #60a5fa;">Browse History</a></p>
                </div>
            </main>
            {render_footer()}
        </body>
        </html>
        """
        return HTMLResponse(content=html, status_code=404)
    
    adjacent = get_adjacent_months(year, month)
    
    rows_html = ""
    for s in snapshots:
        band_class = f"band-{s.band.lower()}"
        trend_display = f"{s.trend_7d:+.1f}" if s.trend_7d is not None else "-"
        rows_html += f"""
        <tr>
            <td><a href="/geri/{s.date}">{s.date}</a></td>
            <td>{s.value}</td>
            <td class="{band_class}">{s.band}</td>
            <td>{trend_display}</td>
        </tr>
        """
    
    stats_html = ""
    if stats:
        stats_html = f"""
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-value">{stats.get('avg_value', 0):.0f}</div>
                <div class="stat-label">Monthly Avg</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{stats.get('min_value', 0)}</div>
                <div class="stat-label">Min</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{stats.get('max_value', 0)}</div>
                <div class="stat-label">Max</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{stats.get('snapshot_count', 0)}</div>
                <div class="stat-label">Days</div>
            </div>
        </div>
        """
    
    prev_link = ""
    if adjacent['prev']:
        p = adjacent['prev']
        prev_link = f'<a class="nav-arrow" href="/geri/{p["year"]}/{p["month"]:02d}">&larr; {calendar_month_name[p["month"]]} {p["year"]}</a>'
    else:
        prev_link = '<span class="nav-arrow disabled">&larr; No earlier</span>'
    
    next_link = ""
    if adjacent['next']:
        n = adjacent['next']
        next_link = f'<a class="nav-arrow" href="/geri/{n["year"]}/{n["month"]:02d}">{calendar_month_name[n["month"]]} {n["year"]} &rarr;</a>'
    else:
        next_link = '<span class="nav-arrow disabled">No later &rarr;</span>'
    
    month_display = f"{calendar_month_name[month]} {year}"
    
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Global Energy Risk Index {month_display} | EnergyRiskIQ</title>
        <meta name="description" content="GERI archive for {month_display}. View all daily energy risk index snapshots for this month.">
        <link rel="canonical" href="{BASE_URL}/geri/{year}/{month:02d}">
        <link rel="icon" type="image/png" href="/favicon.png">
        {get_common_styles()}
        {get_geri_common_styles()}
    </head>
    <body>
        {render_nav()}
        <main>
            <div class="container">
                <div class="breadcrumbs">
                    <a href="/geri">GERI</a> &raquo; 
                    <a href="/geri/history">History</a> &raquo;
                    {month_display}
                </div>
                
                <h1>Global Energy Risk Index - {month_display}</h1>
                
                {stats_html}
                
                <h2>Daily Snapshots</h2>
                <table class="geri-table">
                    <thead>
                        <tr>
                            <th>Date</th>
                            <th>Value</th>
                            <th>Band</th>
                            <th>7d Trend</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows_html}
                    </tbody>
                </table>
                
                <div class="nav-arrows">
                    {prev_link}
                    {next_link}
                </div>
                
                <div style="text-align: center; margin-top: 2rem;">
                    <a href="/geri/history" style="color: #60a5fa;">View Full History</a>
                </div>
            </div>
        </main>
        {render_footer()}
    </body>
    </html>
    """
    
    return HTMLResponse(content=html, headers={"Cache-Control": "public, max-age=3600"})
