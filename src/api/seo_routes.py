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
from fastapi.responses import HTMLResponse, Response, PlainTextResponse
import time
import hashlib
from collections import defaultdict

from src.db.db import get_cursor, execute_one, execute_query
from src.seo.seo_generator import (
    get_daily_page,
    get_recent_daily_pages,
    get_monthly_pages,
    get_available_months,
    generate_sitemap_entries,
    get_yesterday_date,
    generate_daily_page_model,
    get_regional_daily_page,
    get_regional_available_dates,
    generate_regional_daily_page_model,
    REGION_DISPLAY_NAMES,
)
from src.geri.geri_service import get_geri_for_user, get_geri_delayed
from src.geri.interpretation import generate_interpretation as generate_geri_interpretation
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
from src.utils.contextual_linking import (
    ContextualLinkBuilder,
    get_risk_context_styles,
    extract_regions_from_alerts,
    extract_categories_from_alerts,
    extract_keywords_from_alerts,
)

router = APIRouter(tags=["seo"])

BASE_URL = os.environ.get('ALERTS_APP_BASE_URL', 'https://energyriskiq.com')

# Anti-scraping configuration
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX_REQUESTS = 30  # max requests per window for GERI pages
_request_counts = defaultdict(list)  # IP -> list of timestamps

BLOCKED_USER_AGENTS = [
    'scrapy', 'python-requests', 'httpclient', 'libwww',
    'crawler', 'spider', 'scraper', 'harvest', 'extractor',
    'dataminer', 'contentking', 'semrush', 'ahrefs', 'mj12bot',
    'dotbot', 'petalbot', 'bytespider', 'claudebot', 'gptbot'
]

ALLOWED_BOTS = ['googlebot', 'bingbot', 'slurp', 'duckduckbot', 'facebookexternalhit', 'twitterbot']

def get_client_fingerprint(request: Request) -> str:
    """Generate a fingerprint for rate limiting."""
    ip = request.client.host if request.client else "unknown"
    ua = request.headers.get("user-agent", "")[:100]
    return hashlib.md5(f"{ip}:{ua}".encode()).hexdigest()[:16]

def check_rate_limit(fingerprint: str) -> bool:
    """Check if request should be rate limited. Returns True if blocked."""
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW
    
    # Clean old entries
    _request_counts[fingerprint] = [t for t in _request_counts[fingerprint] if t > window_start]
    
    # Check limit
    if len(_request_counts[fingerprint]) >= RATE_LIMIT_MAX_REQUESTS:
        return True
    
    # Record this request
    _request_counts[fingerprint].append(now)
    return False

def is_blocked_scraper(request: Request) -> bool:
    """Check if the request appears to be from a blocked scraper."""
    ua = request.headers.get("user-agent", "").lower()
    
    # Allow legitimate search engine bots
    for allowed in ALLOWED_BOTS:
        if allowed in ua:
            return False
    
    # Block known scraper signatures
    for blocked in BLOCKED_USER_AGENTS:
        if blocked in ua:
            return True
    
    # Allow empty user agents - some legitimate proxies/iframes don't set them
    # Rate limiting handles abuse instead
    return False

def get_anti_scrape_headers() -> dict:
    """Return headers that discourage scraping/archiving."""
    return {
        "X-Robots-Tag": "noarchive, nosnippet",
        "Cache-Control": "private, no-store, max-age=0",
        "X-Content-Type-Options": "nosniff",
    }

async def apply_anti_scraping(request: Request) -> None:
    """Apply anti-scraping checks. Raises HTTPException if blocked."""
    # Check for blocked scrapers
    if is_blocked_scraper(request):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Check rate limit
    fingerprint = get_client_fingerprint(request)
    if check_rate_limit(fingerprint):
        raise HTTPException(status_code=429, detail="Too many requests")


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
                <img src="/static/logo.png" alt="EnergyRiskIQ" width="36" height="36" style="margin-right: 0.5rem;">
                EnergyRiskIQ
            </a>
            <div class="nav-links">
                <a href="/">Home</a>
                <a href="/alerts">Alerts</a>
                <a href="/users" class="cta-btn">Get Started</a>
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
                <strong>Get tomorrow's alerts before markets open.</strong> <a href="/users">Start free &rarr;</a>
            </div>
        </div>
        """
    elif position == "mid":
        return """
        <section class="cta-section cta-mid">
            <h3>These are public summaries.</h3>
            <p>Pro users receive <strong>full AI analysis</strong>, <strong>instant multi-channel delivery</strong>, and <strong>priority alerts</strong> before they appear here.</p>
            <a href="/users" class="cta-btn">Unlock Full Analysis &rarr;</a>
        </section>
        """
    elif position == "bottom":
        return """
        <section class="cta-section">
            <h3>Don't Miss Tomorrow's Risk Signals</h3>
            <p>Get real-time alerts delivered via Email, Telegram, or SMS — before markets react.</p>
            <a href="/users" class="cta-btn">Get Alerts Now &rarr;</a>
        </section>
        """
    else:
        return """
        <section class="cta-section">
            <h3>Stay Ahead of Market Risks</h3>
            <p>Subscribe for daily intelligence briefings and real-time risk signals.</p>
            <a href="/users" class="cta-btn">Start Free Trial &rarr;</a>
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
        <link rel="icon" type="image/png" href="/static/favicon.png">
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
    Region-specific alerts hub page. Shows daily regional alert pages.
    """
    region_name = REGION_DISPLAY_NAMES.get(region_slug, region_slug.replace('-', ' ').title())
    track_page_view("region", f"/alerts/region/{region_slug}")
    
    regional_pages = get_regional_available_dates(region_slug, limit=30)
    
    if regional_pages:
        pages_html = ""
        for page in regional_pages:
            page_date = page['page_date']
            if isinstance(page_date, str):
                page_date_str = page_date
                display_date = datetime.fromisoformat(page_date).strftime('%B %d, %Y')
            else:
                page_date_str = page_date.strftime('%Y-%m-%d')
                display_date = page_date.strftime('%B %d, %Y')
            alert_count = page.get('alert_count', 0)
            pages_html += f'<li><a href="/alerts/region/{region_slug}/{page_date_str}">{display_date}</a> ({alert_count} alerts)</li>'
    else:
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
    <title>{region_name} Risk Alerts Archive | EnergyRiskIQ</title>
    <meta name="description" content="Daily archive of geopolitical and energy risk alerts for {region_name}. Monitor supply disruption signals, market volatility, and risk intelligence.">
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
            <p class="meta">Daily archive of geopolitical and energy risk intelligence for {region_name}. Track supply disruption signals, market volatility, and critical risk events.</p>
            
            <h2>Daily Alert Archives</h2>
            <p>Browse daily risk alerts for {region_name}:</p>
            <ul class="page-list">
                {pages_html if pages_html else '<li>No regional pages generated yet. Check back soon.</li>'}
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


@router.get("/alerts/region/{region_slug}/{date_str}", response_class=HTMLResponse)
async def regional_daily_alerts_page(region_slug: str, date_str: str, request: Request):
    """Regional daily alerts page for a specific date and region."""
    await apply_anti_scraping(request)
    
    region_name = REGION_DISPLAY_NAMES.get(region_slug, region_slug.replace('-', ' ').title())
    
    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        raise HTTPException(status_code=404, detail="Invalid date format")
    
    yesterday = get_yesterday_date()
    if target_date > yesterday:
        raise HTTPException(status_code=404, detail="Page not available yet (24h delay)")
    
    track_page_view("regional_daily", f"/alerts/region/{region_slug}/{date_str}")
    
    page_data = get_regional_daily_page(target_date, region_slug)
    
    if page_data and page_data.get('model'):
        model = page_data['model']
    else:
        model = generate_regional_daily_page_model(target_date, region_slug)
    
    all_cards = model.get('alert_cards', [])
    visible_cards = all_cards[:10]
    collapsed_cards = all_cards[10:]
    
    def get_severity_label(severity):
        if severity >= 5:
            return 'Critical'
        elif severity == 4:
            return 'High'
        elif severity == 3:
            return 'Moderate'
        else:
            return 'Low'
    
    def render_alert_card(card, collapsed=False):
        severity = card.get('severity', 3)
        severity_label = card.get('severity_label') or get_severity_label(severity)
        category = card.get('category', 'General')
        region = card.get('region', 'Global')
        
        title = card.get('public_title', 'Risk Alert')
        summary = card.get('public_summary', '')
        
        card_class = f"alert-card severity-{severity}" + (" collapsed" if collapsed else "")
        
        return f'''
        <article class="{card_class}">
            <h3>{title}</h3>
            <div class="alert-meta">
                <span class="severity-badge severity-{severity}">{severity_label} ({severity}/5)</span>
                <span class="category">{category}</span>
                <span class="region">{region}</span>
            </div>
            <p class="summary">{summary}</p>
        </article>
        '''
    
    cards_html = ""
    for card in visible_cards:
        cards_html += render_alert_card(card, collapsed=False)
    
    if collapsed_cards:
        cards_html += f'''
        <div class="collapsed-section">
            <button class="expand-btn" onclick="this.parentElement.classList.toggle('expanded'); this.textContent = this.parentElement.classList.contains('expanded') ? 'Show Less' : 'Show {len(collapsed_cards)} More Alerts';">
                Show {len(collapsed_cards)} More Alerts
            </button>
            <div class="collapsed-content">
        '''
        for card in collapsed_cards:
            cards_html += render_alert_card(card, collapsed=True)
        cards_html += '</div></div>'
    
    stats = model.get('stats', {})
    stats_html = f"""
    <div class="stats-row">
        <div class="stat-badge"><strong>{stats.get('total_alerts', 0)}</strong> Total Alerts</div>
        <div class="stat-badge"><strong>{stats.get('critical_count', 0)}</strong> Critical (5/5)</div>
        <div class="stat-badge"><strong>{stats.get('high_count', 0)}</strong> High (4/5)</div>
        <div class="stat-badge"><strong>{stats.get('moderate_count', 0)}</strong> Moderate (3/5)</div>
    </div>
    """
    
    risk_posture = model.get('risk_posture', {})
    posture_level = risk_posture.get('level', 'stable').lower()
    posture_description = risk_posture.get('description', 'Risk levels are within normal parameters.')
    posture_html = f"""
    <section class="risk-posture">
        <h2>Daily Risk Posture <span class="risk-level {posture_level}">{posture_level.upper()}</span></h2>
        <p>{posture_description}</p>
    </section>
    """
    
    prev_link = f'<a href="/alerts/region/{region_slug}/{model["prev_date"]}">&larr; Previous Day</a>' if model.get('prev_date') else '<span></span>'
    next_link = f'<a href="/alerts/region/{region_slug}/{model["next_date"]}">Next Day &rarr;</a>' if model.get('next_date') else '<span></span>'
    
    link_builder = ContextualLinkBuilder()
    categories = [c.get('category', '').lower() for c in all_cards]
    keywords = extract_keywords_from_alerts(all_cards)
    relevant_indices = link_builder.determine_relevant_indices(
        regions=[region_slug],
        categories=categories,
        keywords=keywords,
        max_links=3
    )
    period_text = model.get('date_display', 'this day')
    risk_context_html = link_builder.render_risk_context_block(relevant_indices, period_text)
    
    breadcrumb_json_ld = json.dumps({
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{BASE_URL}/"},
            {"@type": "ListItem", "position": 2, "name": "Alerts", "item": f"{BASE_URL}/alerts"},
            {"@type": "ListItem", "position": 3, "name": region_name, "item": f"{BASE_URL}/alerts/region/{region_slug}"},
            {"@type": "ListItem", "position": 4, "name": model['date_display'], "item": f"{BASE_URL}/alerts/region/{region_slug}/{date_str}"}
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
        <link rel="canonical" href="{BASE_URL}/alerts/region/{region_slug}/{date_str}">
        <link rel="icon" type="image/png" href="/static/favicon.png">
        <script type="application/ld+json">{breadcrumb_json_ld}</script>
        {get_common_styles()}
        {get_risk_context_styles()}
    </head>
    <body>
        {render_nav()}
        {render_cta_section("top")}
        <main>
            <div class="container">
                <div class="breadcrumbs">
                    <a href="/">Home</a> / <a href="/alerts">Alerts</a> / <a href="/alerts/region/{region_slug}">{region_name}</a> / {model['date_display']}
                </div>
                <h1>{model['h1_title']}</h1>
                <p class="meta">Published {model['date_display']} (alerts from the previous 24 hours)</p>
                
                {risk_context_html}
                
                {stats_html}

                {posture_html}
                
                <section class="alerts-list">
                    <h2>{region_name} Alerts</h2>
                    {cards_html if cards_html else '<p class="no-alerts">No significant risk alerts detected for this date in {region_name}.</p>'}
                </section>
                
                {render_cta_section("mid")}
                
                <nav class="pagination">
                    {prev_link}
                    {next_link}
                </nav>
                
                <div class="disclaimer">
                    <strong>Disclaimer:</strong> This information is provided for general informational purposes only and does not constitute financial, investment, or trading advice. Past alerts do not guarantee future accuracy.
                </div>
            </div>
        </main>
        {render_footer()}
    </body>
    </html>
    """
    
    return HTMLResponse(content=html, headers={"Cache-Control": "public, max-age=300"})


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
async def daily_alerts_page(date_str: str, request: Request):
    """Daily alerts page for a specific date."""
    # Anti-scraping protection: allow search engines, block scrapers
    await apply_anti_scraping(request)
    
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
    
    # Build Risk Context block with contextual links to indices
    link_builder = ContextualLinkBuilder()
    regions = extract_regions_from_alerts(all_cards)
    categories = extract_categories_from_alerts(all_cards)
    keywords = extract_keywords_from_alerts(all_cards)
    relevant_indices = link_builder.determine_relevant_indices(
        regions=regions,
        categories=categories,
        keywords=keywords,
        max_links=3
    )
    period_text = model.get('date_display', 'this day')
    risk_context_html = link_builder.render_risk_context_block(relevant_indices, period_text)
    
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
        <link rel="icon" type="image/png" href="/static/favicon.png">
        <script type="application/ld+json">{breadcrumb_json_ld}</script>
        {get_common_styles()}
        {get_risk_context_styles()}
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
                
                {risk_context_html}
                
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
    
    # Anti-scrape headers: allow indexing but discourage archiving/extraction
    headers = {
        "Cache-Control": "public, max-age=86400",
        "X-Robots-Tag": "index, follow, noarchive",
        "X-Content-Type-Options": "nosniff",
    }
    return HTMLResponse(content=html, headers=headers)


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
    
    # Build Risk Context block for monthly archive
    link_builder = ContextualLinkBuilder()
    relevant_indices = ['geri', 'eeri', 'egsi']
    risk_context_html = link_builder.render_risk_context_block(relevant_indices, month_display)
    
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Risk Alerts - {month_display} | EnergyRiskIQ</title>
        <meta name="description" content="Geopolitical and energy risk alerts archive for {month_display}. {len(pages)} days of risk intelligence with {total_alerts} total alerts.">
        <link rel="canonical" href="{BASE_URL}/alerts/{year}/{month:02d}">
        <link rel="icon" type="image/png" href="/static/favicon.png">
        {get_common_styles()}
        {get_risk_context_styles()}
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
                
                {risk_context_html}
                
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


@router.get("/robots.txt", response_class=PlainTextResponse)
async def robots_txt():
    """
    Robots.txt - Allow search engines, block scrapers.
    """
    robots_content = f"""# EnergyRiskIQ Robots.txt

# Allow major search engines to crawl everything (for SEO)
User-agent: Googlebot
Allow: /

User-agent: Bingbot
Allow: /

User-agent: Slurp
Allow: /

User-agent: DuckDuckBot
Allow: /

User-agent: Baiduspider
Allow: /

User-agent: YandexBot
Allow: /

User-agent: facebookexternalhit
Allow: /

User-agent: Twitterbot
Allow: /

User-agent: LinkedInBot
Allow: /

# Block known scrapers and data miners
User-agent: Scrapy
Disallow: /

User-agent: python-requests
Disallow: /

User-agent: curl
Disallow: /

User-agent: wget
Disallow: /

User-agent: HTTrack
Disallow: /

User-agent: SemrushBot
Disallow: /geri

User-agent: AhrefsBot
Disallow: /geri

User-agent: MJ12bot
Disallow: /geri

User-agent: DotBot
Disallow: /geri

User-agent: PetalBot
Disallow: /geri

User-agent: GPTBot
Disallow: /geri

User-agent: ClaudeBot
Disallow: /geri

User-agent: CCBot
Disallow: /geri

User-agent: ByteSpider
Disallow: /geri

# Default: Allow all other bots with crawl-delay
User-agent: *
Allow: /
Crawl-delay: 5

# Sitemap location
Sitemap: {BASE_URL}/sitemap.xml
"""
    return PlainTextResponse(content=robots_content, headers={"Cache-Control": "public, max-age=86400"})


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
                    <li><a href="/geri/methodology">GERI Methodology & Construction</a></li>
                    <li><a href="/geri/history">GERI History</a></li>
                    <li><a href="/eeri">European Energy Risk Index (EERI)</a></li>
                    <li><a href="/eeri/methodology">EERI Methodology</a></li>
                    <li><a href="/eeri/history">EERI History</a></li>
                    <li><a href="/egsi">Europe Gas Stress Index (EGSI)</a></li>
                    <li><a href="/egsi/methodology">EGSI Methodology</a></li>
                    <li><a href="/egsi/history">EGSI History</a></li>
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
    Protected: Anti-scraping measures applied.
    """
    # Apply anti-scraping protection
    await apply_anti_scraping(request)
    
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
            trend_val = geri.trend_7d
            if abs(trend_val) < 2:
                trend_label = "Stable"
                trend_color = "#6b7280"
            elif trend_val >= 5:
                trend_label = "Rising Sharply"
                trend_color = "#ef4444"
            elif trend_val >= 2:
                trend_label = "Rising"
                trend_color = "#f97316"
            elif trend_val <= -5:
                trend_label = "Falling Sharply"
                trend_color = "#22c55e"
            else:
                trend_label = "Falling"
                trend_color = "#4ade80"
            trend_sign = "+" if trend_val > 0 else ""
            trend_display = f'<div class="geri-trend" style="color: #4ade80;">7-Day Trend: {trend_label} ({trend_sign}{trend_val:.0f})</div>'
        
        drivers_html = ""
        for driver in geri.top_drivers_detailed[:5]:
            tag_parts = []
            if driver.region:
                tag_parts.append(driver.region)
            if driver.category:
                cat_formatted = driver.category.replace('_', ' ').title()
                tag_parts.append(cat_formatted)
            tag_line = ' · '.join(tag_parts)
            if tag_line:
                drivers_html += f'<li><span class="driver-tag">{tag_line}</span><br>{driver.headline}</li>'
            else:
                drivers_html += f'<li>{driver.headline}</li>'
        if not drivers_html:
            drivers_html = '<li>No significant drivers detected</li>'
        
        regions_html = ""
        region_labels = ["Primary", "Secondary", "Tertiary"]
        for i, region in enumerate(geri.top_regions[:3]):
            label = region_labels[i] if i < len(region_labels) else ""
            regions_html += f'<li>{region} <span class="region-label">({label})</span></li>'
        if not regions_html:
            regions_html = '<li>No regional hotspots</li>'
        
        top_drivers_list = [{'headline': d.headline, 'region': d.region, 'category': d.category} for d in geri.top_drivers_detailed[:5]] if geri.top_drivers_detailed else []
        # Use stored interpretation (unique per day), fallback to generation only if missing
        interpretation = getattr(geri, 'interpretation', None) or getattr(geri, 'explanation', None)
        if not interpretation:
            interpretation = generate_geri_interpretation(
                value=geri.value,
                band=geri.band,
                top_drivers=top_drivers_list,
                top_regions=geri.top_regions[:3] if geri.top_regions else [],
                index_date=geri.computed_at
            )
        interpretation_html = ''.join(f'<p>{para}</p>' for para in interpretation.split('\n\n') if para.strip())
        
        delay_badge = '<div class="geri-delay-badge">24h delayed • Real-time access with subscription</div>' if is_delayed else '<div class="geri-realtime-badge">Real-time data</div>'
        
        geri_content = f"""
        <div class="geri-metric-card">
            <div class="geri-header">
                <span class="geri-flame">🔥</span>
                <span class="geri-title">Global Energy Risk Index:</span>
            </div>
            <div class="geri-value" style="font-size: 1.5rem; font-weight: bold; color: {band_color}; margin: 0.5rem 0;">{geri.value} / 100 ({geri.band})</div>
            <div class="geri-scale-ref">0 = minimal risk · 100 = extreme systemic stress</div>
            {trend_display}
            <div class="geri-date">Date Computed: {geri.computed_at}</div>
        </div>
        
        <div class="geri-sections">
            <div class="geri-section">
                <h2 class="section-header-blue">Primary Risk Drivers:</h2>
                <ul class="geri-list">{drivers_html}</ul>
                <p class="source-attribution">(Based on recent EnergyRiskIQ alerts) <a href="/alerts">View alerts &rarr;</a></p>
            </div>
            
            <div class="geri-section">
                <h2 class="section-header-blue">Top Regions Under Pressure:</h2>
                <ul class="geri-list regions-list">{regions_html}</ul>
            </div>
        </div>
        
        <div class="geri-interpretation">
            {interpretation_html}
        </div>
        
        {delay_badge}
        """
    
    cta_block = ""
    if is_delayed:
        cta_block = """
        <div class="geri-cta">
            <h3>Get Real-time Access</h3>
            <p>Unlock instant GERI updates with a Pro subscription.</p>
            <a href="/users" class="cta-button primary">Unlock Real-time GERI</a>
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
        
        <link rel="icon" type="image/png" href="/static/favicon.png">
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
            .geri-hero .methodology-link {{
                margin-top: 0.75rem;
            }}
            .geri-hero .methodology-link a {{
                color: #60a5fa;
                text-decoration: none;
                font-size: 0.95rem;
                transition: color 0.2s;
            }}
            .geri-hero .methodology-link a:hover {{
                color: #93c5fd;
                text-decoration: underline;
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
                margin-bottom: 0.75rem;
                line-height: 1.4;
            }}
            .driver-tag {{
                color: #4ecdc4;
                font-size: 0.8rem;
                font-weight: 500;
            }}
            .geri-header {{
                display: flex;
                align-items: center;
                gap: 0.75rem;
                margin-bottom: 0.5rem;
            }}
            .geri-flame {{
                font-size: 1.5rem;
            }}
            .geri-title {{
                font-size: 1.25rem;
                font-weight: 600;
                color: #f8fafc;
            }}
            .geri-scale-ref {{
                font-size: 0.8rem;
                color: #9ca3af;
                margin-bottom: 0.75rem;
            }}
            .geri-trend {{
                font-size: 0.95rem;
                margin-bottom: 0.5rem;
                color: #f8fafc;
            }}
            .section-header-blue {{
                color: #60a5fa !important;
                font-size: 1rem;
                margin-bottom: 0.75rem;
            }}
            .region-label {{
                color: #9ca3af;
                font-size: 0.85rem;
            }}
            .geri-interpretation {{ 
                color: #1f2937; 
                font-size: 1.05rem; 
                margin: 1.5rem 0 2rem 0; 
                line-height: 1.7; 
                background: rgba(96, 165, 250, 0.05);
                border-left: 3px solid #3b82f6;
                padding: 1.5rem;
                border-radius: 0 8px 8px 0;
            }}
            .geri-interpretation p {{ margin: 0 0 1rem 0; }}
            .geri-interpretation p:last-child {{ margin-bottom: 0; }}
            .geri-delay-badge {{
                background: linear-gradient(135deg, #1e3a5f 0%, #0f172a 100%);
                border: 1px solid #3b82f6;
                border-radius: 2rem;
                padding: 0.5rem 1.5rem;
                text-align: center;
                color: #60a5fa;
                font-size: 0.9rem;
                margin-top: 1rem;
            }}
            .geri-realtime-badge {{
                background: linear-gradient(135deg, #064e3b 0%, #0f172a 100%);
                border: 1px solid #22c55e;
                border-radius: 2rem;
                padding: 0.5rem 1.5rem;
                text-align: center;
                color: #4ade80;
                font-size: 0.9rem;
                margin-top: 1rem;
            }}
            .regions-list {{
                list-style: disc;
            }}
            .source-attribution {{
                font-size: 0.8rem;
                color: #9ca3af;
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
            .data-sources-section {{
                margin-top: 2rem;
                padding-top: 1.5rem;
                border-top: 1px solid #334155;
            }}
            .data-sources-section h4 {{
                font-size: 0.875rem;
                font-weight: 600;
                color: #9ca3af;
                margin-bottom: 0.5rem;
            }}
            .data-sources-section p {{
                font-size: 0.875rem;
                color: #d1d5db;
            }}
            .data-sources-section a {{
                color: #60a5fa;
                text-decoration: none;
            }}
            .data-sources-section a:hover {{
                text-decoration: underline;
            }}
            .index-history-nav {{
                text-align: center;
                margin-top: 2rem;
            }}
            .index-history-nav .back-link {{
                color: #60a5fa;
                text-decoration: none;
            }}
            .index-history-nav .back-link:hover {{
                text-decoration: underline;
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
                    <p class="methodology-link"><a href="/geri/methodology">(GERI Methodology & Construction)</a></p>
                </div>
                
                {geri_content}
                
                {cta_block}
                
                <div class="geri-links">
                    <a href="/geri/history">View History</a>
                    <a href="/geri/methodology">Methodology</a>
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
async def geri_history_page(request: Request):
    """
    GERI History Hub - Lists all available GERI snapshots.
    Public page showing the official published archive.
    Protected: Anti-scraping measures applied.
    """
    # Apply anti-scraping protection
    await apply_anti_scraping(request)
    
    track_page_view("geri_history", "/geri/history")
    
    yesterday = get_yesterday_date().isoformat()
    snapshots = list_snapshots(to_date=yesterday, limit=90)
    months = get_geri_available_months(public_only=True)
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
        <link rel="icon" type="image/png" href="/static/favicon.png">
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
                
                <div class="index-history-nav">
                    <a href="/geri" class="back-link">&larr; Back to Today's GERI</a>
                </div>
                
                <div class="data-sources-section">
                    <h4>Data Sources</h4>
                    <p>GERI values are computed from daily energy risk alerts. <a href="/alerts">View recent alerts</a></p>
                </div>
            </div>
        </main>
        {render_footer()}
    </body>
    </html>
    """
    
    return HTMLResponse(content=html, headers={"Cache-Control": "public, max-age=3600"})


@router.get("/geri/updates", response_class=HTMLResponse)
async def geri_updates_page():
    """
    GERI Updates Page - Shows changelog and updates to the GERI index methodology.
    """
    track_page_view("geri_updates", "/geri/updates")
    
    updates = [
        {
            "date": "2026-01-31",
            "version": "1.2",
            "title": "Public Interpretation",
            "description": "Added daily interpretation to GERI public pages. Each day's index now includes a unique, contextual analysis explaining current risk levels and key drivers.",
            "type": "enhancement"
        },
        {
            "date": "2026-01-14",
            "version": "1.0",
            "title": "GERI Launch",
            "description": "Initial release of the Global Energy Risk Index. The index provides a daily composite measure of energy market risk computed from alert severity, regional concentration, and asset exposure.",
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
        <title>GERI Updates & Changelog | EnergyRiskIQ</title>
        <meta name="description" content="Track updates, enhancements, and changes to the Global Energy Risk Index (GERI) methodology and calculation.">
        <link rel="canonical" href="{BASE_URL}/geri/updates">
        <link rel="icon" type="image/png" href="/static/favicon.png">
        
        <meta property="og:title" content="GERI Updates & Changelog | EnergyRiskIQ">
        <meta property="og:description" content="Stay informed about updates to the Global Energy Risk Index methodology.">
        <meta property="og:type" content="website">
        <meta property="og:url" content="{BASE_URL}/geri/updates">
        
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
                    <h1>GERI Updates & Changelog</h1>
                    <p>Track the latest updates, enhancements, and changes to the Global Energy Risk Index methodology and calculation.</p>
                </div>
                
                <div class="updates-container">
                    {updates_html}
                </div>
                
                <div class="updates-nav">
                    <a href="/geri">Current GERI</a>
                    <a href="/geri/history">History</a>
                    <a href="/geri/methodology">Methodology</a>
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
        
        <link rel="icon" type="image/png" href="/static/favicon.png">
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
            .warning-list {{
                list-style: none;
                padding-left: 0;
                margin: 1rem 0;
                display: flex;
                flex-wrap: wrap;
                gap: 0.5rem;
            }}
            .warning-list li {{
                background: #fee2e2;
                color: #991b1b;
                padding: 0.5rem 1rem;
                border-radius: 2rem;
                font-weight: 500;
                font-size: 0.95rem;
                display: flex;
                align-items: center;
                gap: 0.35rem;
            }}
            .warning-list li::before {{
                content: "✕";
                font-size: 0.8rem;
                font-weight: 700;
            }}
            .definition-block {{
                background: linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%);
                border-left: 4px solid #2563eb;
                border-radius: 0.5rem;
                padding: 1.25rem 1.5rem;
                margin: 1.5rem 0;
            }}
            .definition-block p {{
                margin: 0;
                color: #1e40af;
            }}
            .definition-block p:first-child {{
                margin-bottom: 0.5rem;
            }}
            .emphasis-text {{
                font-size: 1.1rem;
                font-weight: 600;
                color: #0f172a;
                font-style: italic;
                margin-top: 1rem;
            }}
            .layer-card {{
                border-radius: 0.75rem;
                padding: 1.5rem;
                margin: 1.25rem 0;
                border: 1px solid;
            }}
            .layer-1 {{
                background: linear-gradient(135deg, #fef3c7 0%, #fde68a 50%);
                border-color: #f59e0b;
            }}
            .layer-2 {{
                background: linear-gradient(135deg, #dbeafe 0%, #bfdbfe 50%);
                border-color: #3b82f6;
            }}
            .layer-3 {{
                background: linear-gradient(135deg, #d1fae5 0%, #a7f3d0 50%);
                border-color: #10b981;
            }}
            .layer-header {{
                display: flex;
                align-items: center;
                gap: 0.75rem;
                margin-bottom: 1rem;
            }}
            .layer-number {{
                width: 2rem;
                height: 2rem;
                border-radius: 50%;
                background: rgba(0,0,0,0.15);
                display: flex;
                align-items: center;
                justify-content: center;
                font-weight: 700;
                font-size: 1rem;
                color: #1e293b;
            }}
            .layer-header h4 {{
                margin: 0;
                font-size: 1.1rem;
                font-weight: 600;
                color: #1e293b;
            }}
            .layer-list {{
                list-style: none;
                padding-left: 0;
                margin: 0.75rem 0;
            }}
            .layer-list li {{
                padding: 0.3rem 0 0.3rem 1.25rem;
                position: relative;
                color: #334155;
                font-size: 0.95rem;
            }}
            .layer-list li::before {{
                content: "→";
                position: absolute;
                left: 0;
                color: #64748b;
            }}
            .layer-note {{
                font-style: italic;
                color: #64748b;
                font-size: 0.9rem;
                margin: 0.5rem 0;
            }}
            .layer-summary {{
                font-weight: 600;
                color: #0f172a;
                margin-top: 0.75rem;
                padding-top: 0.75rem;
                border-top: 1px dashed rgba(0,0,0,0.2);
            }}
            .timestamp-concepts {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                gap: 1.5rem;
                margin: 1.5rem 0;
            }}
            .timestamp-card {{
                background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%);
                border: 1px solid #0ea5e9;
                border-radius: 0.75rem;
                padding: 1.5rem;
            }}
            .timestamp-card h4 {{
                color: #0369a1;
                margin: 0 0 0.75rem 0;
                font-size: 1.1rem;
            }}
            .timestamp-card p {{
                margin: 0.5rem 0;
                color: #334155;
            }}
            .timestamp-example {{
                background: rgba(255,255,255,0.7);
                border-radius: 0.5rem;
                padding: 0.75rem;
                margin: 1rem 0;
                font-family: monospace;
                font-size: 0.9rem;
                color: #1e40af;
            }}
            .governance-box {{
                background: linear-gradient(135deg, #fefce8 0%, #fef9c3 100%);
                border: 1px solid #eab308;
                border-radius: 0.75rem;
                padding: 1.5rem;
                margin: 1.5rem 0;
            }}
            .governance-box h4 {{
                color: #a16207;
                margin: 0 0 0.75rem 0;
                font-size: 1.1rem;
            }}
            .governance-box p {{
                color: #334155;
                margin: 0.5rem 0;
            }}
            .governance-note {{
                font-style: italic;
                color: #92400e;
                margin-top: 1rem;
                padding-top: 0.75rem;
                border-top: 1px dashed rgba(0,0,0,0.15);
            }}
            .why-matters-box {{
                background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%);
                border: 1px solid #22c55e;
                border-radius: 0.75rem;
                padding: 1.5rem;
                margin: 1.5rem 0;
            }}
            .why-matters-box h4 {{
                color: #15803d;
                margin: 0 0 0.75rem 0;
                font-size: 1.1rem;
            }}
            .why-matters-box p {{
                color: #334155;
                margin: 0.5rem 0;
            }}
            .simple-list.compact {{
                margin: 0.5rem 0;
                gap: 0.5rem;
            }}
            .simple-list.compact li {{
                padding: 0.35rem 0.75rem;
                font-size: 0.85rem;
            }}
            .aggregation-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 0.75rem;
                margin: 1rem 0;
            }}
            .aggregation-item {{
                background: rgba(255,255,255,0.6);
                border-radius: 0.5rem;
                padding: 0.75rem;
                display: flex;
                flex-direction: column;
                gap: 0.25rem;
            }}
            .agg-icon {{
                font-size: 1.25rem;
            }}
            .agg-label {{
                font-weight: 600;
                color: #1e293b;
                font-size: 0.9rem;
            }}
            .agg-detail {{
                font-size: 0.8rem;
                color: #64748b;
            }}
            .result-showcase {{
                display: flex;
                justify-content: center;
                gap: 1.5rem;
                margin: 1.25rem 0;
                flex-wrap: wrap;
            }}
            .result-item {{
                background: rgba(255,255,255,0.7);
                border-radius: 0.5rem;
                padding: 1rem 1.5rem;
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: 0.35rem;
                min-width: 100px;
            }}
            .result-icon {{
                font-size: 1.5rem;
            }}
            .result-text {{
                font-weight: 600;
                color: #1e293b;
                font-size: 0.95rem;
            }}
            .risk-bands {{
                display: flex;
                flex-direction: column;
                gap: 0.75rem;
                margin: 1.5rem 0;
            }}
            .risk-band {{
                display: flex;
                align-items: center;
                gap: 1rem;
                padding: 1rem 1.25rem;
                border-radius: 0.5rem;
                border-left: 4px solid;
            }}
            .band-low {{
                background: #ecfdf5;
                border-color: #10b981;
            }}
            .band-moderate {{
                background: #fefce8;
                border-color: #eab308;
            }}
            .band-elevated {{
                background: #fff7ed;
                border-color: #f97316;
            }}
            .band-severe {{
                background: #fef2f2;
                border-color: #ef4444;
            }}
            .band-indicator {{
                font-size: 1.5rem;
                flex-shrink: 0;
            }}
            .band-content {{
                display: flex;
                flex-direction: column;
                gap: 0.25rem;
            }}
            .band-label {{
                font-weight: 700;
                font-size: 1rem;
                color: #1e293b;
            }}
            .band-desc {{
                font-size: 0.9rem;
                color: #475569;
            }}
            .publish-list {{
                list-style: none;
                padding-left: 0;
                margin: 1rem 0;
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 0.5rem;
            }}
            .publish-list li {{
                display: flex;
                align-items: center;
                gap: 0.5rem;
                padding: 0.5rem 0.75rem;
                background: #f1f5f9;
                border-radius: 0.375rem;
                font-size: 0.9rem;
                color: #334155;
            }}
            .pub-icon {{
                font-size: 1.1rem;
            }}
            .check-list {{
                list-style: none;
                padding-left: 0;
                margin: 1rem 0;
            }}
            .check-list li {{
                padding: 0.4rem 0 0.4rem 1.75rem;
                position: relative;
                color: #334155;
                font-size: 0.95rem;
            }}
            .check-list li::before {{
                content: "✓";
                position: absolute;
                left: 0.25rem;
                color: #10b981;
                font-weight: 700;
            }}
            .code-block {{
                background: #1e293b;
                border-radius: 0.5rem;
                padding: 1rem 1.5rem;
                margin: 1rem 0;
                overflow-x: auto;
            }}
            .code-block code {{
                color: #38bdf8;
                font-family: 'Monaco', 'Consolas', monospace;
                font-size: 1rem;
            }}
            .archive-benefits {{
                display: flex;
                flex-wrap: wrap;
                gap: 0.75rem;
                margin: 1rem 0;
            }}
            .benefit-item {{
                background: #f0f9ff;
                border: 1px solid #bae6fd;
                border-radius: 0.5rem;
                padding: 0.75rem 1rem;
                display: flex;
                align-items: center;
                gap: 0.5rem;
                flex: 1;
                min-width: 180px;
            }}
            .benefit-icon {{
                font-size: 1.25rem;
            }}
            .use-case-list {{
                list-style: none;
                padding-left: 0;
                margin: 1rem 0;
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
                gap: 0.5rem;
            }}
            .use-case-list li {{
                display: flex;
                align-items: center;
                gap: 0.5rem;
                padding: 0.5rem 0.75rem;
                background: #faf5ff;
                border: 1px solid #e9d5ff;
                border-radius: 0.375rem;
                font-size: 0.9rem;
                color: #6b21a8;
            }}
            .use-icon {{
                font-size: 1rem;
            }}
            .governance-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
                gap: 1rem;
                margin: 1.5rem 0;
            }}
            .governance-card {{
                border-radius: 0.75rem;
                padding: 1.25rem;
                border: 1px solid;
            }}
            .governance-card.integrity {{
                background: linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%);
                border-color: #10b981;
            }}
            .governance-card.stability {{
                background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
                border-color: #3b82f6;
            }}
            .governance-card h4 {{
                margin: 0 0 0.75rem 0;
                font-size: 1.05rem;
                font-weight: 600;
                color: #1e293b;
                display: flex;
                align-items: center;
                gap: 0.5rem;
            }}
            .gov-icon {{
                font-size: 1.1rem;
            }}
            .gov-list {{
                list-style: none;
                padding-left: 0;
                margin: 0;
            }}
            .gov-list li {{
                padding: 0.3rem 0 0.3rem 1.25rem;
                position: relative;
                color: #334155;
                font-size: 0.9rem;
            }}
            .gov-list li::before {{
                content: "•";
                position: absolute;
                left: 0.25rem;
                color: #64748b;
            }}
            .ensure-grid {{
                display: flex;
                flex-wrap: wrap;
                gap: 0.75rem;
                margin: 1rem 0;
            }}
            .ensure-item {{
                background: #f0fdf4;
                border: 1px solid #86efac;
                border-radius: 2rem;
                padding: 0.5rem 1rem;
                display: flex;
                align-items: center;
                gap: 0.35rem;
                font-weight: 500;
                font-size: 0.9rem;
                color: #166534;
            }}
            .ensure-icon {{
                font-size: 0.9rem;
            }}
            .audience-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 0.75rem;
                margin: 1.5rem 0;
            }}
            .audience-item {{
                background: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 0.5rem;
                padding: 0.75rem 1rem;
                display: flex;
                align-items: center;
                gap: 0.5rem;
                font-size: 0.95rem;
                color: #334155;
                transition: all 0.2s ease;
            }}
            .audience-item:hover {{
                background: #f1f5f9;
                border-color: #cbd5e1;
            }}
            .aud-icon {{
                font-size: 1.1rem;
            }}
            .exposure-list {{
                list-style: none;
                padding-left: 0;
                margin: 1rem 0;
                display: flex;
                flex-wrap: wrap;
                gap: 0.75rem;
            }}
            .exposure-list li {{
                background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
                border: 1px solid #f59e0b;
                border-radius: 0.5rem;
                padding: 0.75rem 1.25rem;
                display: flex;
                align-items: center;
                gap: 0.5rem;
                font-weight: 500;
                color: #92400e;
            }}
            .exp-icon {{
                font-size: 1.1rem;
            }}
            .final-section {{
                border-top: 2px solid #e2e8f0;
                padding-top: 2rem;
                margin-top: 1rem;
            }}
            .trend-grid {{
                display: flex;
                flex-wrap: wrap;
                gap: 0.75rem;
                margin: 1.25rem 0;
                justify-content: center;
            }}
            .trend-item {{
                background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%);
                border: 1px solid #fca5a5;
                border-radius: 0.5rem;
                padding: 0.75rem 1.25rem;
                display: flex;
                align-items: center;
                gap: 0.5rem;
                font-weight: 500;
                color: #991b1b;
            }}
            .trend-icon {{
                font-size: 1.1rem;
            }}
            .contrast-block {{
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 1.5rem;
                margin: 2rem 0;
                flex-wrap: wrap;
            }}
            .contrast-old, .contrast-new {{
                display: flex;
                flex-direction: column;
                align-items: center;
                padding: 1.25rem 1.5rem;
                border-radius: 0.75rem;
                text-align: center;
                min-width: 180px;
            }}
            .contrast-old {{
                background: #f1f5f9;
                border: 1px solid #cbd5e1;
            }}
            .contrast-new {{
                background: linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%);
                border: 2px solid #10b981;
            }}
            .contrast-label {{
                font-size: 0.85rem;
                color: #64748b;
                margin-bottom: 0.35rem;
            }}
            .contrast-value {{
                font-size: 1.1rem;
                font-weight: 700;
                color: #1e293b;
            }}
            .contrast-new .contrast-value {{
                color: #065f46;
            }}
            .contrast-arrow {{
                font-size: 1.75rem;
                color: #10b981;
                font-weight: 700;
            }}
            .mission-list {{
                list-style: none;
                padding-left: 0;
                margin: 1rem 0;
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 0.75rem;
            }}
            .mission-list li {{
                background: #f0f9ff;
                border: 1px solid #bae6fd;
                border-radius: 0.5rem;
                padding: 0.75rem 1rem;
                display: flex;
                align-items: center;
                gap: 0.5rem;
                font-size: 0.95rem;
                color: #0369a1;
            }}
            .mission-icon {{
                font-size: 1.1rem;
            }}
            .closing-statement {{
                background: linear-gradient(135deg, #1e3a5f 0%, #0f172a 100%);
                border-radius: 0.75rem;
                padding: 1.5rem 2rem;
                margin-top: 1.5rem;
                text-align: center;
            }}
            .closing-statement p {{
                margin: 0;
                color: #e2e8f0;
                font-size: 1.1rem;
                font-weight: 500;
            }}
            .disclaimer-section {{
                background: #fffbeb;
                border: 2px solid #f59e0b;
                border-radius: 0.75rem;
                padding: 1.5rem;
                margin-top: 1.5rem;
            }}
            .important-notice {{
                display: flex;
                align-items: center;
                gap: 0.5rem;
                background: #fef3c7;
                border-radius: 0.5rem;
                padding: 0.75rem 1rem;
                margin-bottom: 1rem;
            }}
            .notice-icon {{
                font-size: 1.25rem;
            }}
            .notice-text {{
                font-weight: 600;
                color: #92400e;
                font-size: 0.95rem;
            }}
            .disclaimer-list {{
                list-style: none;
                padding-left: 0;
                margin: 1rem 0;
            }}
            .disclaimer-list li {{
                padding: 0.4rem 0;
                display: flex;
                align-items: center;
                gap: 0.5rem;
                color: #991b1b;
                font-size: 0.95rem;
            }}
            .dis-icon {{
                color: #dc2626;
                font-weight: 700;
                font-size: 0.9rem;
            }}
            .responsibility-list, .warranty-list {{
                list-style: none;
                padding-left: 0;
                margin: 0.75rem 0 1rem 0;
                display: flex;
                flex-wrap: wrap;
                gap: 0.5rem;
            }}
            .responsibility-list li, .warranty-list li {{
                background: #fef3c7;
                border: 1px solid #fcd34d;
                border-radius: 0.375rem;
                padding: 0.4rem 0.75rem;
                font-size: 0.9rem;
                color: #92400e;
            }}
            .final-disclaimer {{
                background: #fef2f2;
                border: 1px solid #fca5a5;
                border-radius: 0.5rem;
                padding: 1rem 1.25rem;
                margin-top: 1rem;
                text-align: center;
            }}
            .final-disclaimer p {{
                margin: 0;
                color: #991b1b;
                font-size: 1rem;
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
                .warning-list {{
                    justify-content: center;
                }}
                .warning-list li {{
                    font-size: 0.85rem;
                    padding: 0.4rem 0.75rem;
                }}
                .definition-block {{
                    padding: 1rem 1.25rem;
                }}
                .emphasis-text {{
                    font-size: 1rem;
                }}
                .layer-card {{
                    padding: 1.25rem;
                }}
                .layer-header h4 {{
                    font-size: 1rem;
                }}
                .layer-list li {{
                    font-size: 0.9rem;
                }}
                .aggregation-grid {{
                    grid-template-columns: 1fr;
                }}
                .result-showcase {{
                    gap: 1rem;
                }}
                .result-item {{
                    padding: 0.75rem 1rem;
                    min-width: 80px;
                }}
                .risk-band {{
                    padding: 0.75rem 1rem;
                    gap: 0.75rem;
                }}
                .band-label {{
                    font-size: 0.9rem;
                }}
                .band-desc {{
                    font-size: 0.85rem;
                }}
                .publish-list {{
                    grid-template-columns: 1fr;
                }}
                .archive-benefits {{
                    flex-direction: column;
                }}
                .benefit-item {{
                    min-width: auto;
                }}
                .use-case-list {{
                    grid-template-columns: repeat(2, 1fr);
                }}
                .code-block {{
                    padding: 0.75rem 1rem;
                }}
                .code-block code {{
                    font-size: 0.9rem;
                }}
                .governance-grid {{
                    grid-template-columns: 1fr;
                }}
                .governance-card {{
                    padding: 1rem;
                }}
                .governance-card h4 {{
                    font-size: 1rem;
                }}
                .ensure-grid {{
                    justify-content: center;
                }}
                .ensure-item {{
                    font-size: 0.85rem;
                    padding: 0.4rem 0.75rem;
                }}
                .audience-grid {{
                    grid-template-columns: repeat(2, 1fr);
                }}
                .audience-item {{
                    font-size: 0.9rem;
                    padding: 0.6rem 0.75rem;
                }}
                .exposure-list {{
                    justify-content: center;
                }}
                .exposure-list li {{
                    padding: 0.6rem 1rem;
                    font-size: 0.9rem;
                }}
                .trend-grid {{
                    gap: 0.5rem;
                }}
                .trend-item {{
                    padding: 0.6rem 1rem;
                    font-size: 0.9rem;
                }}
                .contrast-block {{
                    gap: 1rem;
                }}
                .contrast-old, .contrast-new {{
                    min-width: 150px;
                    padding: 1rem;
                }}
                .contrast-arrow {{
                    font-size: 1.25rem;
                }}
                .mission-list {{
                    grid-template-columns: 1fr;
                }}
                .closing-statement {{
                    padding: 1.25rem 1.5rem;
                }}
                .closing-statement p {{
                    font-size: 1rem;
                }}
                .disclaimer-section {{
                    padding: 1.25rem;
                }}
                .disclaimer-list li {{
                    font-size: 0.9rem;
                }}
                .responsibility-list, .warranty-list {{
                    gap: 0.4rem;
                }}
                .responsibility-list li, .warranty-list li {{
                    font-size: 0.85rem;
                    padding: 0.35rem 0.6rem;
                }}
                .final-disclaimer {{
                    padding: 0.75rem 1rem;
                }}
                .final-disclaimer p {{
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
                    
                    <div class="methodology-section">
                        <h3><span class="section-icon">🚫</span> What GERI Does Not Measure</h3>
                        <p>To avoid ambiguity:</p>
                        <p><strong>GERI does not measure:</strong></p>
                        <ul class="warning-list">
                            <li>Prices</li>
                            <li>Returns</li>
                            <li>Forecasts</li>
                            <li>Trading signals</li>
                            <li>Market recommendations</li>
                        </ul>
                        <div class="definition-block">
                            <p><strong>GERI is:</strong></p>
                            <p>A systemic risk indicator designed to describe stress in the energy system — not to predict prices or guide trades.</p>
                        </div>
                        <p class="emphasis-text">This distinction is fundamental to its credibility.</p>
                    </div>
                    
                    <div class="methodology-section">
                        <h3><span class="section-icon">🧩</span> How GERI Is Constructed — Conceptual Architecture</h3>
                        <p>GERI is built using a multi-layer analytical framework designed to transform complex global events into a structured daily risk indicator.</p>
                        
                        <div class="layer-card layer-1">
                            <div class="layer-header">
                                <span class="layer-number">1</span>
                                <h4>Event Layer — What is happening in the world</h4>
                            </div>
                            <p>EnergyRiskIQ continuously monitors high-impact events related to:</p>
                            <ul class="layer-list">
                                <li>Geopolitics</li>
                                <li>Energy production</li>
                                <li>Transport and shipping</li>
                                <li>Sanctions and trade</li>
                                <li>Infrastructure incidents</li>
                                <li>Regulatory and policy decisions</li>
                            </ul>
                            <p class="layer-note">Only events with material relevance to energy systems are included.</p>
                            <p>Each event is classified by:</p>
                            <ul class="simple-list compact">
                                <li>📍 Region</li>
                                <li>📂 Category</li>
                                <li>⚠️ Severity</li>
                                <li>🔗 Relevance</li>
                            </ul>
                            <p class="layer-summary">This layer captures <strong>what is happening</strong>.</p>
                        </div>
                        
                        <div class="layer-card layer-2">
                            <div class="layer-header">
                                <span class="layer-number">2</span>
                                <h4>Risk Signal Layer — What these events mean for risk</h4>
                            </div>
                            <p>Raw events are not yet risk. They are translated into structured risk signals, such as:</p>
                            <ul class="layer-list">
                                <li>Probability of supply disruption</li>
                                <li>Escalation risk</li>
                                <li>Transport vulnerability</li>
                                <li>Regulatory instability</li>
                                <li>Regional exposure</li>
                            </ul>
                            <p>Signals are aggregated across:</p>
                            <div class="aggregation-grid">
                                <div class="aggregation-item">
                                    <span class="agg-icon">🌍</span>
                                    <span class="agg-label">Regions</span>
                                    <span class="agg-detail">Europe, Middle East, Asia, Americas, etc.</span>
                                </div>
                                <div class="aggregation-item">
                                    <span class="agg-icon">📊</span>
                                    <span class="agg-label">Asset Classes</span>
                                    <span class="agg-detail">Oil, gas, power, freight, FX, etc.</span>
                                </div>
                                <div class="aggregation-item">
                                    <span class="agg-icon">🔄</span>
                                    <span class="agg-label">Systemic Channels</span>
                                    <span class="agg-detail">Supply, policy, logistics, demand</span>
                                </div>
                            </div>
                            <p class="layer-summary">This layer captures <strong>how events affect the system</strong>.</p>
                        </div>
                        
                        <div class="layer-card layer-3">
                            <div class="layer-header">
                                <span class="layer-number">3</span>
                                <h4>Index Layer — Converting risk into a single indicator</h4>
                            </div>
                            <p>Aggregated risk signals are then transformed into:</p>
                            <ul class="layer-list">
                                <li>A daily numerical index value (0–100 scale)</li>
                                <li>A qualitative risk band</li>
                                <li>Short-term and medium-term trend indicators</li>
                            </ul>
                            <div class="result-showcase">
                                <div class="result-item">
                                    <span class="result-icon">🔢</span>
                                    <span class="result-text">One number</span>
                                </div>
                                <div class="result-item">
                                    <span class="result-icon">🎚️</span>
                                    <span class="result-text">One band</span>
                                </div>
                                <div class="result-item">
                                    <span class="result-icon">📅</span>
                                    <span class="result-text">One daily snapshot</span>
                                </div>
                            </div>
                            <p class="layer-summary">Representing the overall stress level of the global energy system.</p>
                        </div>
                    </div>
                    
                    <div class="methodology-section">
                        <h3><span class="section-icon">📅</span> Index Date vs. Computation Timestamp</h3>
                        <p>GERI is published as a daily reference index representing systemic risk conditions for a specific calendar day.</p>
                        <p>For accuracy, completeness, and audit integrity, the index follows a <strong>two-step publication process</strong>:</p>
                        
                        <div class="timestamp-concepts">
                            <div class="timestamp-card">
                                <h4>Index Date (Publication Date)</h4>
                                <p>The Index Date identifies the calendar day whose risk conditions are being measured.</p>
                                <p class="timestamp-example"><strong>Example:</strong> GERI — January 21, 2026 represents systemic energy risk conditions observed throughout January 21, 2026.</p>
                                <p>This date is the official historical reference used in:</p>
                                <ul class="layer-list">
                                    <li>Archive pages</li>
                                    <li>Charts</li>
                                    <li>Research</li>
                                    <li>Licensing and reporting</li>
                                </ul>
                            </div>
                            
                            <div class="timestamp-card">
                                <h4>Computed Date (Computation Timestamp)</h4>
                                <p>The Computed Date records the exact timestamp when the index was calculated and published.</p>
                                <p>Because GERI incorporates all alerts and signals generated during the full calendar day, the index is computed after the close of the observation period, typically in the early hours of the following day.</p>
                                <p class="timestamp-example"><strong>Example:</strong><br/>Index Date: January 21, 2026<br/>Computed At: January 22, 2026, 06:10 UTC</p>
                                <p>This ensures that:</p>
                                <ul class="layer-list">
                                    <li>All relevant events for the day are included</li>
                                    <li>Late-day developments are captured</li>
                                    <li>Daily snapshots are complete and reproducible</li>
                                </ul>
                            </div>
                        </div>
                        
                        <div class="governance-box">
                            <h4>Publication & Governance Principles</h4>
                            <p>This methodology follows standard benchmark and index publication practices used by institutional data providers:</p>
                            <ul class="layer-list">
                                <li>Each index value reflects a full-day observation window</li>
                                <li>Computation occurs after the day closes</li>
                                <li>Each daily snapshot is: <strong>published once</strong>, <strong>immutable</strong>, <strong>auditable</strong>, and <strong>permanently archived</strong></li>
                            </ul>
                            <p class="governance-note">Once published, a GERI value is not revised or backfilled and represents the official historical record for that date.</p>
                        </div>
                        
                        <div class="why-matters-box">
                            <h4>Why This Matters</h4>
                            <p>Separating the Index Date from the Computation Timestamp ensures:</p>
                            <ul class="layer-list">
                                <li>Full coverage of daily events and alerts</li>
                                <li>Methodological consistency</li>
                                <li>Stable historical time series</li>
                                <li>Transparency for professional and institutional users</li>
                            </ul>
                            <p class="layer-summary">This approach guarantees that every published GERI value reflects a complete, final, and reproducible measure of systemic energy risk for the stated date.</p>
                        </div>
                    </div>
                    
                    <div class="methodology-section">
                        <h3><span class="section-icon">📊</span> How to Interpret GERI</h3>
                        <p>GERI ranges from 0 to 100, divided into four qualitative bands:</p>
                        
                        <div class="risk-bands">
                            <div class="risk-band band-low">
                                <div class="band-indicator">🟢</div>
                                <div class="band-content">
                                    <span class="band-label">LOW</span>
                                    <span class="band-desc">Stable energy environment with minimal systemic stress</span>
                                </div>
                            </div>
                            <div class="risk-band band-moderate">
                                <div class="band-indicator">🟡</div>
                                <div class="band-content">
                                    <span class="band-label">MODERATE</span>
                                    <span class="band-desc">Normal structural risk typical of balanced markets</span>
                                </div>
                            </div>
                            <div class="risk-band band-elevated">
                                <div class="band-indicator">🟠</div>
                                <div class="band-content">
                                    <span class="band-label">ELEVATED</span>
                                    <span class="band-desc">Rising geopolitical or supply stress with increasing fragility</span>
                                </div>
                            </div>
                            <div class="risk-band band-severe">
                                <div class="band-indicator">🔴</div>
                                <div class="band-content">
                                    <span class="band-label">SEVERE</span>
                                    <span class="band-desc">Systemic disruption risk affecting multiple regions and assets</span>
                                </div>
                            </div>
                        </div>
                        
                        <p>In addition to the level, GERI publishes:</p>
                        <ul class="publish-list">
                            <li><span class="pub-icon">📈</span> Daily change (1-day)</li>
                            <li><span class="pub-icon">📉</span> Medium-term trend (7-day)</li>
                            <li><span class="pub-icon">⚠️</span> Main risk drivers</li>
                            <li><span class="pub-icon">🌍</span> Regions under pressure</li>
                            <li><span class="pub-icon">🛢️</span> Assets likely affected</li>
                        </ul>
                        <p class="section-summary">This allows users to understand not only <strong>how risky</strong>, but also <strong>where</strong> and <strong>why</strong>.</p>
                    </div>
                    
                    <div class="methodology-section">
                        <h3><span class="section-icon">🕰️</span> Daily Publication & Permanent Historical Archive</h3>
                        <p>GERI is:</p>
                        <ul class="check-list">
                            <li>Computed once per day</li>
                            <li>Published at a fixed schedule</li>
                            <li>Stored permanently</li>
                            <li>Never rewritten after publication</li>
                        </ul>
                        
                        <p>Each day becomes an official historical record, accessible at:</p>
                        <div class="code-block">
                            <code>/geri/YYYY-MM-DD</code>
                        </div>
                        
                        <p>This creates:</p>
                        <div class="archive-benefits">
                            <div class="benefit-item">
                                <span class="benefit-icon">📚</span>
                                <span>A transparent time-series archive</span>
                            </div>
                            <div class="benefit-item">
                                <span class="benefit-icon">🔄</span>
                                <span>Reproducible history</span>
                            </div>
                            <div class="benefit-item">
                                <span class="benefit-icon">🏛️</span>
                                <span>Institutional accountability</span>
                            </div>
                        </div>
                        
                        <p>Every published value remains:</p>
                        <ul class="simple-list">
                            <li>🌐 Public</li>
                            <li>♾️ Permanent</li>
                            <li>🔒 Immutable</li>
                        </ul>
                        
                        <p>This historical integrity is essential for:</p>
                        <ul class="use-case-list">
                            <li><span class="use-icon">🔬</span> Research</li>
                            <li><span class="use-icon">📋</span> Audits</li>
                            <li><span class="use-icon">📜</span> Licensing</li>
                            <li><span class="use-icon">🏢</span> Institutional use</li>
                        </ul>
                    </div>
                    
                    <div class="methodology-section">
                        <h3><span class="section-icon">🔐</span> Governance, Integrity & Methodology Stability</h3>
                        <p>GERI follows strict governance principles:</p>
                        
                        <div class="governance-grid">
                            <div class="governance-card integrity">
                                <h4><span class="gov-icon">🧾</span> Integrity Principles</h4>
                                <ul class="gov-list">
                                    <li>Automated computation</li>
                                    <li>Reproducible methodology</li>
                                    <li>Immutable historical records</li>
                                    <li>Auditable publication process</li>
                                    <li>Versioned models</li>
                                </ul>
                            </div>
                            <div class="governance-card stability">
                                <h4><span class="gov-icon">🏛️</span> Stability Principles</h4>
                                <ul class="gov-list">
                                    <li>Consistent methodology over time</li>
                                    <li>Controlled updates</li>
                                    <li>Documented model versions</li>
                                    <li>Transparent publication rules</li>
                                </ul>
                            </div>
                        </div>
                        
                        <p>These principles ensure:</p>
                        <div class="ensure-grid">
                            <div class="ensure-item"><span class="ensure-icon">✅</span> Reliability</div>
                            <div class="ensure-item"><span class="ensure-icon">✅</span> Continuity</div>
                            <div class="ensure-item"><span class="ensure-icon">✅</span> Regulatory compatibility</div>
                            <div class="ensure-item"><span class="ensure-icon">✅</span> Long-term credibility</div>
                        </div>
                    </div>
                    
                    <div class="methodology-section">
                        <h3><span class="section-icon">🏢</span> Who GERI Is Designed For</h3>
                        <p>GERI is built for professionals exposed to energy risk, including:</p>
                        
                        <div class="audience-grid">
                            <div class="audience-item"><span class="aud-icon">📈</span> Energy traders & analysts</div>
                            <div class="audience-item"><span class="aud-icon">💹</span> Commodity desks</div>
                            <div class="audience-item"><span class="aud-icon">⚡</span> Producers & utilities</div>
                            <div class="audience-item"><span class="aud-icon">🚢</span> Shipping & logistics firms</div>
                            <div class="audience-item"><span class="aud-icon">🔗</span> Supply-chain managers</div>
                            <div class="audience-item"><span class="aud-icon">🛡️</span> Risk managers</div>
                            <div class="audience-item"><span class="aud-icon">🏛️</span> Policymakers & regulators</div>
                            <div class="audience-item"><span class="aud-icon">🔬</span> Institutional researchers</div>
                        </div>
                        
                        <p>Any organization exposed to:</p>
                        <ul class="exposure-list">
                            <li><span class="exp-icon">⚡</span> Energy availability</li>
                            <li><span class="exp-icon">💰</span> Energy prices</li>
                            <li><span class="exp-icon">🌍</span> Geopolitical instability</li>
                        </ul>
                        
                        <p class="section-summary">can use GERI as a <strong>systemic risk compass</strong>.</p>
                    </div>
                    
                    <div class="methodology-section final-section">
                        <h3><span class="section-icon">🌐</span> Why EnergyRiskIQ Created GERI</h3>
                        <p>Energy systems are becoming:</p>
                        
                        <div class="trend-grid">
                            <div class="trend-item"><span class="trend-icon">⚔️</span> More geopolitical</div>
                            <div class="trend-item"><span class="trend-icon">🧩</span> More fragmented</div>
                            <div class="trend-item"><span class="trend-icon">📜</span> More regulated</div>
                            <div class="trend-item"><span class="trend-icon">⚠️</span> More fragile</div>
                        </div>
                        
                        <div class="contrast-block">
                            <div class="contrast-old">
                                <span class="contrast-label">Traditional indicators focus on</span>
                                <span class="contrast-value">what happened</span>
                            </div>
                            <div class="contrast-arrow">→</div>
                            <div class="contrast-new">
                                <span class="contrast-label">GERI focuses on</span>
                                <span class="contrast-value">what is building</span>
                            </div>
                        </div>
                        
                        <p>Its mission is to provide:</p>
                        <ul class="mission-list">
                            <li><span class="mission-icon">🚨</span> Early warning signals</li>
                            <li><span class="mission-icon">👁️</span> Systemic visibility</li>
                            <li><span class="mission-icon">📊</span> Structured risk intelligence</li>
                            <li><span class="mission-icon">📚</span> Historical accountability</li>
                        </ul>
                        
                        <div class="closing-statement">
                            <p>GERI is designed to support better decisions in increasingly complex energy markets.</p>
                        </div>
                    </div>
                    
                    <div class="methodology-section disclaimer-section">
                        <h3><span class="section-icon">⚠️</span> Transparency, Limitations & Disclaimer</h3>
                        <div class="important-notice">
                            <span class="notice-icon">ℹ️</span>
                            <span class="notice-text">Important notice</span>
                        </div>
                        
                        <p>GERI is provided for <strong>informational and analytical purposes only</strong>.</p>
                        
                        <p>It:</p>
                        <ul class="disclaimer-list">
                            <li><span class="dis-icon">✕</span> Does not constitute investment advice</li>
                            <li><span class="dis-icon">✕</span> Does not constitute trading advice</li>
                            <li><span class="dis-icon">✕</span> Does not constitute a forecast</li>
                        </ul>
                        
                        <p>Users remain <strong>solely responsible</strong> for:</p>
                        <ul class="responsibility-list">
                            <li>Investment decisions</li>
                            <li>Trading strategies</li>
                            <li>Risk management actions</li>
                        </ul>
                        
                        <p>EnergyRiskIQ makes no representations or warranties regarding:</p>
                        <ul class="warranty-list">
                            <li>Future performance</li>
                            <li>Market outcomes</li>
                            <li>Financial results</li>
                        </ul>
                        
                        <div class="final-disclaimer">
                            <p>GERI is a <strong>descriptive risk indicator</strong>, not a recommendation engine.</p>
                        </div>
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
async def geri_daily_page(request: Request, date: str):
    """
    GERI Daily Snapshot Page - Shows a specific day's GERI data.
    Returns 404 if the date doesn't exist in the archive.
    Protected: Anti-scraping measures applied.
    """
    # Apply anti-scraping protection
    await apply_anti_scraping(request)
    
    import re
    
    month_match = re.match(r'^(\d{4})/(\d{2})$', date)
    if month_match:
        year = int(month_match.group(1))
        month = int(month_match.group(2))
        return await geri_monthly_page(request, year, month)
    
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
            <link rel="icon" type="image/png" href="/static/favicon.png">
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
        trend_val = snapshot.trend_7d
        if abs(trend_val) < 2:
            trend_label = "Stable"
            trend_color = "#6b7280"
        elif trend_val >= 5:
            trend_label = "Rising Sharply"
            trend_color = "#ef4444"
        elif trend_val >= 2:
            trend_label = "Rising"
            trend_color = "#f97316"
        elif trend_val <= -5:
            trend_label = "Falling Sharply"
            trend_color = "#22c55e"
        else:
            trend_label = "Falling"
            trend_color = "#4ade80"
        trend_sign = "+" if trend_val > 0 else ""
        trend_display = f'<div class="geri-trend" style="color: #4ade80;">7-Day Trend: {trend_label} ({trend_sign}{trend_val:.0f})</div>'
    
    drivers_html = ""
    for driver in snapshot.top_drivers_detailed[:5]:
        tag_parts = []
        if driver.get('region'):
            tag_parts.append(driver['region'])
        if driver.get('category'):
            cat_formatted = driver['category'].replace('_', ' ').title()
            tag_parts.append(cat_formatted)
        tag_line = ' · '.join(tag_parts)
        if tag_line:
            drivers_html += f'<li><span class="driver-tag">{tag_line}</span><br>{driver["headline"]}</li>'
        else:
            drivers_html += f'<li>{driver["headline"]}</li>'
    if not drivers_html:
        drivers_html = '<li style="color: #9ca3af;">No significant drivers</li>'
    
    regions_html = ""
    region_labels = ["Primary", "Secondary", "Tertiary"]
    for i, region in enumerate(snapshot.top_regions[:3]):
        label = region_labels[i] if i < len(region_labels) else ""
        regions_html += f'<li>{region} <span class="region-label">({label})</span></li>'
    if not regions_html:
        regions_html = '<li style="color: #9ca3af;">No regional hotspots</li>'
    
    snapshot_drivers_list = [{'headline': d.get('headline', ''), 'region': d.get('region', ''), 'category': d.get('category', '')} for d in snapshot.top_drivers_detailed[:5]] if snapshot.top_drivers_detailed else []
    # Use stored interpretation (unique per day), fallback to generation only if missing
    interpretation = getattr(snapshot, 'interpretation', None) or getattr(snapshot, 'explanation', None)
    if not interpretation:
        interpretation = generate_geri_interpretation(
            value=snapshot.value,
            band=snapshot.band,
            top_drivers=snapshot_drivers_list,
            top_regions=snapshot.top_regions[:3] if snapshot.top_regions else [],
            index_date=snapshot.computed_at
        )
    interpretation_html = ''.join(f'<p>{para}</p>' for para in interpretation.split('\n\n') if para.strip())
    
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
        <link rel="icon" type="image/png" href="/static/favicon.png">
        {get_common_styles()}
        {get_geri_common_styles()}
        <style>
            .snapshot-card {{
                background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
                border: 1px solid #334155;
                border-radius: 1rem;
                padding: 2rem;
                max-width: 600px;
                margin: 2rem auto;
            }}
            .geri-header {{
                display: flex;
                align-items: center;
                gap: 0.75rem;
                margin-bottom: 0.5rem;
            }}
            .geri-flame {{
                font-size: 1.5rem;
            }}
            .geri-title {{
                font-size: 1.25rem;
                font-weight: 600;
                color: #f8fafc;
            }}
            .geri-scale-ref {{
                font-size: 0.8rem;
                color: #9ca3af;
                margin-bottom: 0.75rem;
            }}
            .geri-trend {{
                font-size: 0.95rem;
                margin-bottom: 0.5rem;
                color: #f8fafc;
            }}
            .geri-date {{
                color: #9ca3af;
                margin-top: 0.5rem;
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
            .section-header-blue {{
                color: #60a5fa !important;
                font-size: 1rem;
                margin-bottom: 0.75rem;
            }}
            .geri-list {{
                list-style: disc;
                padding-left: 1.25rem;
                color: #d1d5db;
            }}
            .geri-list li {{
                margin-bottom: 0.75rem;
                line-height: 1.4;
            }}
            .driver-tag {{
                color: #4ecdc4;
                font-size: 0.8rem;
                font-weight: 500;
            }}
            .region-label {{
                color: #9ca3af;
                font-size: 0.85rem;
            }}
            .geri-interpretation {{ 
                color: #1f2937; 
                font-size: 1.05rem; 
                margin: 1.5rem 0 2rem 0; 
                line-height: 1.7; 
                background: rgba(96, 165, 250, 0.05);
                border-left: 3px solid #3b82f6;
                padding: 1.5rem;
                border-radius: 0 8px 8px 0;
            }}
            .geri-interpretation p {{ margin: 0 0 1rem 0; }}
            .geri-interpretation p:last-child {{ margin-bottom: 0; }}
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
                
                <div class="snapshot-card" style="text-align: center;">
                    <div class="geri-header" style="justify-content: center;">
                        <span class="geri-flame">🔥</span>
                        <span class="geri-title">Global Energy Risk Index:</span>
                    </div>
                    <div class="geri-value" style="font-size: 1.5rem; font-weight: bold; color: {band_color}; margin: 0.5rem 0;">{snapshot.value} / 100 ({snapshot.band})</div>
                    <div class="geri-scale-ref">0 = minimal risk · 100 = extreme systemic stress</div>
                    {trend_display}
                    <div class="geri-date">Date Computed: {snapshot.computed_at_formatted}</div>
                </div>
                
                <div class="drivers-regions">
                    <div class="section-card">
                        <h2 class="section-header-blue">Primary Risk Drivers:</h2>
                        <ul class="geri-list">{drivers_html}</ul>
                    </div>
                    <div class="section-card">
                        <h2 class="section-header-blue">Top Regions Under Pressure:</h2>
                        <ul class="geri-list">{regions_html}</ul>
                    </div>
                </div>
                
                <div class="geri-interpretation">
                    {interpretation_html}
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


async def geri_monthly_page(request: Request, year: int, month: int):
    """
    GERI Monthly Archive Hub - Shows all snapshots for a specific month.
    Protected: Anti-scraping already applied by parent route.
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
            <link rel="icon" type="image/png" href="/static/favicon.png">
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
        <link rel="icon" type="image/png" href="/static/favicon.png">
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
