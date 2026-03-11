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
from typing import Optional, List
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
    generate_sitemap_core_entries,
    generate_sitemap_alerts_entries,
    generate_sitemap_indices_entries,
    generate_sitemap_digest_entries,
    get_yesterday_date,
    generate_daily_page_model,
    get_regional_daily_page,
    get_regional_available_dates,
    generate_regional_daily_page_model,
    REGION_DISPLAY_NAMES,
)
from src.seo.digest_page_generator import (
    get_public_digest_page,
    get_recent_public_digest_pages,
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
    get_latest_published_snapshot,
    get_weekly_snapshot
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
        .footer-links { display: flex; gap: 1.5rem; flex-wrap: wrap; justify-content: center; }
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
                <a href="/users" class="cta-btn">Get FREE Access</a>
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
                <strong>Get tomorrow's alerts before markets open.</strong> <a href="/users">Get FREE Access &rarr;</a>
            </div>
        </div>
        """
    elif position == "mid":
        return """
        <section class="cta-section cta-mid">
            <h3>These are public summaries.</h3>
            <p>Pro users receive <strong>full AI analysis</strong>, <strong>instant multi-channel delivery</strong>, and <strong>priority alerts</strong> before they appear here.</p>
            <a href="/users" class="cta-btn">Get FREE Access &rarr;</a>
        </section>
        """
    elif position == "bottom":
        return """
        <section class="cta-section">
            <h3>Don't Miss Tomorrow's Risk Signals</h3>
            <p>Get real-time alerts delivered via Email, Telegram, or SMS — before markets react.</p>
            <a href="/users" class="cta-btn">Get FREE Access &rarr;</a>
        </section>
        """
    else:
        return """
        <section class="cta-section">
            <h3>Stay Ahead of Market Risks</h3>
            <p>Subscribe for daily intelligence briefings and real-time risk signals.</p>
            <a href="/users" class="cta-btn">Get FREE Access &rarr;</a>
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
        """Compact card for collapsed alerts."""
        severity = card.get('severity', 3)
        severity_label = get_severity_label(severity)
        summary = card.get('public_summary', '')
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
Sitemap: {BASE_URL}/sitemap-index.xml
"""
    return PlainTextResponse(content=robots_content, headers={"Cache-Control": "public, max-age=86400"})


def _render_urlset_xml(entries: List[dict]) -> str:
    xml_entries = ""
    for e in entries:
        lastmod_tag = f"\n        <lastmod>{e['lastmod']}</lastmod>" if e.get('lastmod') else ""
        priority_tag = f"\n        <priority>{e['priority']}</priority>" if e.get('priority') else ""
        changefreq_tag = f"\n        <changefreq>{e['changefreq']}</changefreq>" if e.get('changefreq') else ""
        xml_entries += f"""
    <url>
        <loc>{BASE_URL}{e['loc']}</loc>{lastmod_tag}{priority_tag}{changefreq_tag}
    </url>"""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{xml_entries}
</urlset>"""


@router.get("/sitemap-index.xml", response_class=Response)
async def sitemap_index_xml():
    """Sitemap index file linking to individual sitemaps."""
    from datetime import date as _date
    today = _date.today().isoformat()

    sitemaps = [
        ('sitemap-core.xml', today),
        ('sitemap-alerts.xml', today),
        ('sitemap-indices.xml', today),
        ('sitemap-digest.xml', today),
    ]

    sitemap_entries = ""
    for name, lastmod in sitemaps:
        sitemap_entries += f"""
    <sitemap>
        <loc>{BASE_URL}/{name}</loc>
        <lastmod>{lastmod}</lastmod>
    </sitemap>"""

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{sitemap_entries}
</sitemapindex>"""
    return Response(content=xml, media_type="application/xml", headers={"Cache-Control": "public, max-age=3600"})


@router.get("/sitemap-core.xml", response_class=Response)
async def sitemap_core_xml():
    """Core authority pages sitemap (~10-30 URLs)."""
    entries = generate_sitemap_core_entries()
    return Response(content=_render_urlset_xml(entries), media_type="application/xml", headers={"Cache-Control": "public, max-age=3600"})


@router.get("/sitemap-alerts.xml", response_class=Response)
async def sitemap_alerts_xml():
    """Daily alert pages sitemap (last 60 days + monthly archives)."""
    entries = generate_sitemap_alerts_entries(limit=60)
    return Response(content=_render_urlset_xml(entries), media_type="application/xml", headers={"Cache-Control": "public, max-age=3600"})


@router.get("/sitemap-indices.xml", response_class=Response)
async def sitemap_indices_xml():
    """Index snapshot pages sitemap (GERI/EERI/EGSI, last 60 days + monthly archives)."""
    entries = generate_sitemap_indices_entries(limit=60)
    return Response(content=_render_urlset_xml(entries), media_type="application/xml", headers={"Cache-Control": "public, max-age=3600"})


@router.get("/sitemap-digest.xml", response_class=Response)
async def sitemap_digest_xml():
    """Daily digest pages sitemap (last 60 days)."""
    entries = generate_sitemap_digest_entries(limit=60)
    return Response(content=_render_urlset_xml(entries), media_type="application/xml", headers={"Cache-Control": "public, max-age=3600"})


@router.get("/sitemap.xml", response_class=Response)
async def sitemap_xml_redirect():
    """Legacy sitemap.xml redirects to sitemap-index.xml."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/sitemap-index.xml", status_code=301)


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
                    <li><a href="/indices/global-energy-risk-index">Global Energy Risk Index (GERI)</a></li>
                    <li><a href="/geri/methodology">GERI Methodology & Construction</a></li>
                    <li><a href="/geri/history">GERI History</a></li>
                    <li><a href="/indices/europe-energy-risk-index">European Energy Risk Index (EERI)</a></li>
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


@router.get("/geri")
async def geri_redirect(request: Request):
    """301 redirect from old /geri to new canonical URL."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/indices/global-energy-risk-index", status_code=301)


@router.get("/indices/global-energy-risk-index", response_class=HTMLResponse)
async def geri_page(request: Request):
    """
    GERI Index Page - Canonical public page at /indices/global-energy-risk-index.
    
    - Unauthenticated: Shows 24h delayed GERI
    - Authenticated: Shows real-time GERI
    
    Googlebot always sees delayed version (not logged in).
    Protected: Anti-scraping measures applied.
    """
    await apply_anti_scraping(request)
    
    track_page_view("geri", "/indices/global-energy-risk-index")
    
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
    
    score_card = ""
    change_stats = ""
    driver_cards = ""
    interp_card = ""
    chart_section = ""
    is_delayed = True
    
    if not geri:
        score_card = """
        <div class="geri-unavailable">
            <h2>GERI Data Coming Soon</h2>
            <p>The Global Energy Risk Index is being computed. Check back shortly.</p>
        </div>
        """
    else:
        is_delayed = geri.is_delayed
        
        band_colors = {
            'LOW': '#22c55e',
            'MODERATE': '#eab308',
            'ELEVATED': '#f97316',
            'CRITICAL': '#ef4444',
            'SEVERE': '#dc2626'
        }
        band_color = band_colors.get(geri.band, '#6b7280')
        
        delay_badge = '<div class="geri-delay-badge">Public value delay: 24 hours</div>' if is_delayed else '<div class="geri-realtime-badge">Real-time Data</div>'
        
        score_card = f"""
        <div class="geri-metric-card">
            <div class="geri-header">
                <span class="geri-flame">&#x1F525;</span>
                <span class="geri-title">Global Energy Risk Index</span>
            </div>
            <div style="font-size: 2.5rem; font-weight: 700; color: {band_color}; margin: 0.5rem 0; line-height: 1;">{geri.value}<span style="font-size: 1rem; color: #64748b;"> / 100</span></div>
            <div style="font-size: 1.1rem; font-weight: 600; color: {band_color}; margin-bottom: 0.25rem;">{geri.band}</div>
            <div class="geri-scale-ref">0 = minimal risk &middot; 100 = extreme systemic stress</div>
            <div class="geri-date">Last updated: {geri.computed_at}</div>
            {delay_badge}
        </div>
        """

        trend_1d_val = geri.trend_1d
        trend_7d_val = geri.trend_7d
        t1d_sign = "+" if trend_1d_val and trend_1d_val > 0 else ""
        t1d_display = f"{t1d_sign}{trend_1d_val:.0f}" if trend_1d_val is not None else "N/A"
        t1d_color = "#ef4444" if (trend_1d_val or 0) > 0 else "#22c55e" if (trend_1d_val or 0) < 0 else "#64748b"
        t7d_sign = "+" if trend_7d_val and trend_7d_val > 0 else ""
        t7d_display = f"{t7d_sign}{trend_7d_val:.0f}" if trend_7d_val is not None else "N/A"
        t7d_color = "#ef4444" if (trend_7d_val or 0) > 0 else "#22c55e" if (trend_7d_val or 0) < 0 else "#64748b"

        from src.db.db import execute_query
        from datetime import datetime, timedelta
        thirty_days_ago = (datetime.utcnow() - timedelta(days=30)).strftime('%Y-%m-%d')
        range_rows = execute_query(
            "SELECT MIN(value) as min_val, MAX(value) as max_val FROM intel_indices_daily WHERE index_id = 'geri' AND date >= %s",
            (thirty_days_ago,)
        )
        range_row = range_rows[0] if range_rows else {}
        if range_row and range_row.get('min_val') is not None:
            range_display = f"{range_row['min_val']}&ndash;{range_row['max_val']}"
        else:
            range_display = "N/A"

        change_stats = f"""
        <div class="geri-change-stats">
            <div class="geri-change-item">
                <span class="change-label">vs yesterday</span>
                <span class="change-value" style="color:{t1d_color};">{t1d_display}</span>
            </div>
            <div class="geri-change-item">
                <span class="change-label">7-day change</span>
                <span class="change-value" style="color:{t7d_color};">{t7d_display}</span>
            </div>
            <div class="geri-change-item">
                <span class="change-label">30-day range</span>
                <span class="change-value" style="color:#94a3b8;">{range_display}</span>
            </div>
        </div>
        """

        geo_cats = ['geopolitical', 'war', 'military', 'conflict', 'sanctions']
        energy_cats = ['energy', 'supply_chain', 'supply_disruption', 'strike']
        market_cats = ['political', 'diplomacy']
        geo_count = 0
        energy_count = 0
        market_count = 0
        for driver in (geri.top_drivers_detailed or []):
            cat = (driver.category or '').lower()
            sev = (getattr(driver, 'severity', '') or '').lower()
            if any(g in cat for g in geo_cats):
                geo_count += 1
            if any(e in cat for e in energy_cats):
                energy_count += 1
            if any(m in cat for m in market_cats) or sev == 'high':
                market_count += 1

        def _level_for(count):
            if count >= 3: return ('High', 'level-high')
            if count >= 1: return ('Medium', 'level-medium')
            return ('Low', 'level-low')

        geo_text, geo_cls = _level_for(geo_count)
        ene_text, ene_cls = _level_for(energy_count)
        mkt_text, mkt_cls = _level_for(market_count)

        driver_cards = f"""
        <div class="geri-simplified-drivers">
            <div class="geri-simplified-driver-card">
                <div class="driver-icon-pub">&#x2694;&#xFE0F;</div>
                <div class="driver-label-pub">Geopolitical Risk</div>
                <div class="driver-level-pub {geo_cls}">{geo_text}</div>
            </div>
            <div class="geri-simplified-driver-card">
                <div class="driver-icon-pub">&#x26FD;</div>
                <div class="driver-label-pub">Energy Supply</div>
                <div class="driver-level-pub {ene_cls}">{ene_text}</div>
            </div>
            <div class="geri-simplified-driver-card">
                <div class="driver-icon-pub">&#x1F4CA;</div>
                <div class="driver-label-pub">Market Stress</div>
                <div class="driver-level-pub {mkt_cls}">{mkt_text}</div>
            </div>
        </div>
        """

        top_drivers_list = [{'headline': d.headline, 'region': d.region, 'category': d.category} for d in geri.top_drivers_detailed[:5]] if geri.top_drivers_detailed else []
        interpretation = getattr(geri, 'interpretation', None) or getattr(geri, 'explanation', None)
        if not interpretation:
            interpretation = generate_geri_interpretation(
                value=geri.value,
                band=geri.band,
                top_drivers=top_drivers_list,
                top_regions=geri.top_regions[:3] if geri.top_regions else [],
                index_date=geri.computed_at
            )
        interp_paragraphs = [p.strip() for p in interpretation.split('\n') if p.strip()]
        summary_para = interp_paragraphs[0] if interp_paragraphs else ""
        full_paras = interp_paragraphs[1:] if len(interp_paragraphs) > 1 else []
        full_html = ''.join(f'<p>{p}</p>' for p in full_paras)
        expand_section = ""
        if full_html:
            expand_section = (
                '<div id="geriInterpFull" style="display:none; margin-top: 0.75rem;">'
                + full_html
                + '</div>'
                + "<button onclick=\"var el=document.getElementById('geriInterpFull');var btn=this;if(el.style.display==='none'){el.style.display='block';btn.textContent='Hide full interpretation';}else{el.style.display='none';btn.textContent='Read full interpretation';}\" style=\"background:none;border:none;color:#60a5fa;cursor:pointer;font-size:0.88rem;font-weight:600;padding:0.5rem 0 0 0;\">Read full interpretation</button>"
            )

        interp_card = f"""
        <div class="geri-interp-card">
            <div class="geri-interp-card-header">
                <span style="font-size: 16px;">&#x1F9E0;</span>
                <h3>GERI Interpretation</h3>
            </div>
            <div class="geri-interp-card-body">
                <p>{summary_para}</p>
                {expand_section}
            </div>
        </div>
        """

        chart_section = """
        <div class="geri-chart-section">
            <div class="digest-card">
                <div class="digest-card-header">
                    <span class="digest-section-icon">&#x1F4C8;</span>
                    <h3>GERI History (14 days)</h3>
                </div>
                <div style="padding: 16px;">
                    <div style="position:relative; height:220px;">
                        <canvas id="geriPublicChart"></canvas>
                    </div>
                    <p style="text-align:center; color:#64748b; font-size:0.8rem; margin-top:0.5rem;">Public 14-day GERI history (24h delayed)</p>
                </div>
            </div>
        </div>
        """
    
    # Weekly Snapshot Section
    weekly_section = ""
    weekly = get_weekly_snapshot()
    if weekly and weekly.get('snapshot_count', 0) >= 3:
        from datetime import datetime as dt
        start_display = dt.fromisoformat(weekly['start_date']).strftime('%b %d')
        end_display = dt.fromisoformat(weekly['end_date']).strftime('%b %d, %Y')
        
        weekly_drivers_html = ""
        for i, driver in enumerate(weekly.get('top_drivers', [])[:3], 1):
            weekly_drivers_html += f'<li><span class="driver-num">{i}.</span> {driver}</li>'
        if not weekly_drivers_html:
            weekly_drivers_html = '<li>No significant pressure points this week</li>'
        
        weekly_regions_html = ""
        for region in weekly.get('top_regions', [])[:2]:
            weekly_regions_html += f'<span class="region-tag">{region}</span>'
        if not weekly_regions_html:
            weekly_regions_html = '<span class="region-tag">Global</span>'
        
        weekly_assets_html = ""
        for asset in weekly.get('assets', [])[:4]:
            weekly_assets_html += f'<span class="asset-tag">{asset}</span>'
        if not weekly_assets_html:
            weekly_assets_html = '<span class="asset-tag">Energy</span>'
        
        band_color_map = {
            'LOW': '#22c55e', 'MODERATE': '#facc15', 'ELEVATED': '#f97316',
            'SEVERE': '#ef4444', 'CRITICAL': '#991b1b'
        }
        dominant_color = band_color_map.get(weekly['dominant_band'], '#60a5fa')
        
        chart_bars_html = ""
        for day in weekly.get('chart_data', []):
            day_color = band_color_map.get(day['band'], '#60a5fa')
            height_pct = max(10, min(100, day['value']))
            band_short = day['band'][:3].upper() if day['band'] else 'MOD'
            chart_bars_html += f'''
            <div class="weekly-bar-container">
                <span class="weekly-bar-elevation" style="color: {day_color};">{day['band']}</span>
                <div class="weekly-bar" style="height: {height_pct}%; background: {day_color};" title="{day['date']}: {day['value']}"></div>
                <span class="weekly-bar-label">{day['value']}</span>
            </div>'''
        
        weekly_section = f'''
        <div class="weekly-snapshot-section">
            <div class="weekly-header">
                <span class="weekly-icon">&#x1F4CA;</span>
                <h2>GERI Weekly Snapshot</h2>
                <span class="weekly-dates">{start_display} &ndash; {end_display}</span>
            </div>
            <p style="color:#94a3b8; font-size:0.85rem; margin:-0.75rem 0 1rem 0;">Public weekly summary of the Global Energy Risk Index.</p>
            
            <div class="weekly-card">
                <div class="weekly-chart-container">
                    <div class="weekly-chart-header">
                        <span class="chart-label">Weekly Risk Levels</span>
                        <span class="chart-elevation" style="color: {dominant_color};">{weekly['dominant_band']}</span>
                    </div>
                    <div class="weekly-chart">
                        {chart_bars_html}
                    </div>
                    <div class="weekly-stats">
                        <span>Avg: <strong>{weekly['avg_value']}</strong></span>
                        <span>Min: <strong>{weekly['min_value']}</strong></span>
                        <span>Max: <strong>{weekly['max_value']}</strong></span>
                    </div>
                </div>
                
                <div class="weekly-details">
                    <div class="weekly-detail-section">
                        <h3>Main Pressure Points</h3>
                        <ul class="weekly-drivers">{weekly_drivers_html}</ul>
                    </div>
                    
                    <div class="weekly-detail-row">
                        <div class="weekly-detail-section half">
                            <h3>Most Sensitive Regions</h3>
                            <div class="weekly-tags">{weekly_regions_html}</div>
                        </div>
                        <div class="weekly-detail-section half">
                            <h3>Assets Most Exposed</h3>
                            <div class="weekly-tags">{weekly_assets_html}</div>
                        </div>
                    </div>
                    
                    <div class="weekly-interpretation">
                        <p>{weekly['interpretation']}</p>
                    </div>
                </div>
            </div>
        </div>
        '''
    
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
        <meta name="description" content="Track the Global Energy Risk Index (GERI), a public 24-hour delayed measure of geopolitical and market stress across oil, gas, LNG, and global energy systems.">
        <link rel="canonical" href="{BASE_URL}/indices/global-energy-risk-index">
        
        <meta property="og:title" content="Global Energy Risk Index (GERI) | EnergyRiskIQ">
        <meta property="og:description" content="Track energy market risk with the Global Energy Risk Index. Daily updates on risk levels, drivers, and regional hotspots.">
        <meta property="og:url" content="{BASE_URL}/indices/global-energy-risk-index">
        <meta property="og:type" content="website">
        
        <link rel="icon" type="image/png" href="/static/favicon.png">
        {get_digest_dark_styles()}
        <style>
            .geri-hero {{
                text-align: center;
                padding: 2rem 0 1rem 0;
            }}
            .geri-hero h1 {{
                font-size: 1.75rem;
                margin-bottom: 0.5rem;
                color: #f1f5f9;
            }}
            .geri-hero p {{
                color: #94a3b8;
                max-width: 600px;
                margin: 0 auto;
                font-size: 0.95rem;
            }}
            .geri-hero .methodology-link {{
                margin-top: 0.75rem;
            }}
            .geri-hero .methodology-link a {{
                color: #60a5fa;
                text-decoration: none;
                font-size: 0.9rem;
            }}
            .geri-hero .methodology-link a:hover {{
                color: #93c5fd;
                text-decoration: underline;
            }}
            .geri-metric-card {{
                background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
                border: 1px solid #334155;
                border-radius: 12px;
                padding: 1.5rem 2rem;
                text-align: center;
                max-width: 420px;
                margin: 1.5rem auto;
            }}
            .geri-header {{
                display: flex;
                align-items: center;
                gap: 0.5rem;
                justify-content: center;
                margin-bottom: 0.5rem;
            }}
            .geri-flame {{ font-size: 1.25rem; }}
            .geri-title {{
                font-size: 1rem;
                font-weight: 600;
                color: #f1f5f9;
            }}
            .geri-scale-ref {{
                font-size: 0.75rem;
                color: #64748b;
                margin-bottom: 0.5rem;
            }}
            .geri-date {{
                color: #64748b;
                font-size: 0.8rem;
                margin-top: 0.75rem;
            }}
            .geri-trend {{
                font-size: 0.9rem;
                margin-bottom: 0.5rem;
            }}
            .geri-delay-badge {{
                background: rgba(251, 191, 36, 0.12);
                border: 1px solid rgba(251, 191, 36, 0.3);
                color: #fbbf24;
                border-radius: 20px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: 600;
                margin-top: 0.75rem;
                display: inline-block;
            }}
            .geri-realtime-badge {{
                background: rgba(34, 197, 94, 0.12);
                border: 1px solid rgba(34, 197, 94, 0.3);
                color: #4ade80;
                border-radius: 20px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: 600;
                margin-top: 0.75rem;
                display: inline-block;
            }}
            .geri-simplified-drivers {{
                display: flex;
                gap: 12px;
                margin: 1.25rem 0;
                justify-content: center;
            }}
            .geri-simplified-driver-card {{
                background: #1e293b;
                border: 1px solid #334155;
                border-radius: 10px;
                padding: 1rem 0.75rem;
                text-align: center;
                flex: 1;
                max-width: 160px;
            }}
            .driver-icon-pub {{ font-size: 1.25rem; margin-bottom: 0.4rem; }}
            .driver-label-pub {{ color: #e2e8f0; font-size: 0.8rem; font-weight: 600; margin-bottom: 0.4rem; }}
            .driver-level-pub {{ font-size: 0.8rem; font-weight: 700; padding: 0.2rem 0.6rem; border-radius: 6px; display: inline-block; }}
            .driver-level-pub.level-high {{ color: #fca5a5; background: rgba(239,68,68,0.15); }}
            .driver-level-pub.level-medium {{ color: #fcd34d; background: rgba(234,179,8,0.15); }}
            .driver-level-pub.level-low {{ color: #86efac; background: rgba(34,197,94,0.15); }}
            .geri-chart-section {{
                margin: 1.25rem 0;
            }}
            .geri-interp-card {{
                background: #1e293b;
                border: 1px solid #334155;
                border-radius: 12px;
                margin: 1.25rem 0;
                overflow: hidden;
            }}
            .geri-interp-card-header {{
                padding: 14px 20px;
                border-bottom: 1px solid #334155;
                display: flex;
                align-items: center;
                gap: 10px;
            }}
            .geri-interp-card-header h3 {{
                font-size: 15px;
                font-weight: 600;
                color: #f1f5f9;
                margin: 0;
            }}
            .geri-interp-card-body {{
                padding: 16px 20px;
            }}
            .geri-interp-card-body p {{
                color: #cbd5e1;
                font-size: 0.92rem;
                line-height: 1.65;
                margin: 0 0 0.75rem 0;
            }}
            .geri-interp-card-body p:last-child {{
                margin-bottom: 0;
            }}
            .geri-note-card {{
                background: rgba(251, 191, 36, 0.08);
                border: 1px solid rgba(251, 191, 36, 0.2);
                border-radius: 12px;
                padding: 1.25rem;
                margin: 1.25rem 0;
            }}
            .geri-note-card .note-header {{
                display: flex;
                align-items: center;
                gap: 0.5rem;
                margin-bottom: 0.75rem;
            }}
            .geri-note-card .note-label {{
                font-weight: 700;
                color: #fbbf24;
                font-size: 0.9rem;
            }}
            .geri-note-card .note-content {{
                color: #cbd5e1;
                font-size: 0.9rem;
                line-height: 1.6;
                margin: 0 0 0.5rem 0;
            }}
            .geri-note-card .note-content strong {{
                color: #fbbf24;
            }}
            .geri-note-card .note-cta {{
                color: #60a5fa;
                font-weight: 600;
                text-decoration: underline;
            }}
            .geri-note-card .note-cta:hover {{
                color: #93c5fd;
            }}
            .geri-note-card .note-tagline {{
                color: #94a3b8;
                font-size: 0.85rem;
                font-style: italic;
                margin: 0;
                padding-top: 0.5rem;
                border-top: 1px solid rgba(251, 191, 36, 0.15);
            }}
            .weekly-snapshot-section {{
                margin: 1.5rem 0;
                background: #1e293b;
                border: 1px solid #334155;
                border-radius: 12px;
                padding: 1.5rem;
                overflow: hidden;
                box-sizing: border-box;
                max-width: 100%;
            }}
            .weekly-header {{
                display: flex;
                align-items: center;
                gap: 0.75rem;
                margin-bottom: 1.25rem;
                flex-wrap: wrap;
            }}
            .weekly-icon {{ font-size: 1.25rem; }}
            .weekly-header h2 {{
                font-size: 1.1rem;
                font-weight: 600;
                color: #f1f5f9;
                margin: 0;
            }}
            .weekly-dates {{
                font-size: 0.85rem;
                color: #94a3b8;
                margin-left: auto;
            }}
            .weekly-card {{
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 1.5rem;
                overflow: hidden;
            }}
            .weekly-chart-container {{
                background: rgba(15, 23, 42, 0.5);
                border-radius: 10px;
                padding: 1rem;
                min-width: 0;
                overflow: hidden;
            }}
            .weekly-chart-header {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 0.75rem;
            }}
            .chart-label {{ color: #94a3b8; font-size: 0.8rem; }}
            .chart-elevation {{ font-weight: 600; font-size: 0.85rem; }}
            .weekly-chart {{
                display: flex;
                align-items: flex-end;
                justify-content: space-around;
                height: 140px;
                gap: 0.25rem;
                padding: 0.5rem 0;
            }}
            .weekly-bar-container {{
                display: flex;
                flex-direction: column;
                align-items: center;
                flex: 1;
                height: 100%;
                justify-content: flex-end;
            }}
            .weekly-bar-elevation {{
                transform: rotate(-30deg);
                font-size: 0.55rem;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.3px;
                margin-bottom: 0.5rem;
                white-space: nowrap;
                transform-origin: center bottom;
                max-width: 50px;
                overflow: hidden;
                text-overflow: ellipsis;
            }}
            .weekly-bar {{
                width: 100%;
                max-width: 20px;
                border-radius: 3px 3px 0 0;
                min-height: 8px;
            }}
            .weekly-bar-label {{
                font-size: 0.7rem;
                font-weight: 600;
                color: #d1d5db;
                margin-top: 0.3rem;
            }}
            .weekly-stats {{
                display: flex;
                justify-content: space-between;
                margin-top: 0.75rem;
                padding-top: 0.5rem;
                border-top: 1px solid rgba(107, 114, 128, 0.3);
                font-size: 0.75rem;
                color: #94a3b8;
            }}
            .weekly-stats strong {{ color: #d1d5db; }}
            .weekly-details {{ display: flex; flex-direction: column; gap: 0.75rem; min-width: 0; overflow: hidden; }}
            .weekly-detail-section h3 {{
                font-size: 0.8rem;
                font-weight: 600;
                color: #60a5fa;
                margin: 0 0 0.4rem 0;
            }}
            .weekly-drivers {{
                list-style: none;
                padding: 0;
                margin: 0;
            }}
            .weekly-drivers li {{
                font-size: 0.85rem;
                color: #e2e8f0;
                padding: 0.2rem 0;
                border-bottom: 1px solid rgba(107, 114, 128, 0.2);
                overflow-wrap: break-word;
                word-break: break-word;
            }}
            .weekly-drivers li:last-child {{ border-bottom: none; }}
            .driver-num {{ color: #60a5fa; font-weight: 600; margin-right: 0.5rem; }}
            .weekly-detail-row {{
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 0.75rem;
            }}
            .weekly-tags {{
                display: flex;
                flex-wrap: wrap;
                gap: 0.4rem;
            }}
            .region-tag, .asset-tag {{
                background: rgba(96, 165, 250, 0.12);
                color: #60a5fa;
                padding: 0.25rem 0.6rem;
                border-radius: 6px;
                font-size: 0.75rem;
                font-weight: 500;
            }}
            .weekly-interpretation {{
                margin-top: 0.4rem;
                padding: 0.6rem;
                background: rgba(96, 165, 250, 0.05);
                border-left: 3px solid #3b82f6;
                border-radius: 0 8px 8px 0;
            }}
            .weekly-interpretation p {{
                margin: 0;
                font-size: 0.85rem;
                color: #cbd5e1;
                line-height: 1.5;
                overflow-wrap: break-word;
                word-break: break-word;
            }}
            .geri-cta {{
                background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
                border: 1px solid rgba(59, 130, 246, 0.3);
                border-radius: 12px;
                padding: 1.5rem;
                text-align: center;
                margin: 1.25rem 0;
            }}
            .geri-cta h3 {{
                color: #60a5fa;
                margin-bottom: 0.5rem;
                font-size: 1.1rem;
            }}
            .geri-cta p {{
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
            .geri-links {{
                text-align: center;
                margin: 1.5rem 0;
                display: flex;
                justify-content: center;
                gap: 1.5rem;
                flex-wrap: wrap;
            }}
            .geri-links a {{
                color: #60a5fa;
                text-decoration: none;
                font-size: 0.9rem;
                font-weight: 500;
            }}
            .geri-links a:hover {{
                text-decoration: underline;
                color: #93c5fd;
            }}
            .geri-unavailable {{
                text-align: center;
                padding: 3rem 1rem;
                color: #94a3b8;
            }}
            .geri-unavailable h2 {{
                color: #f1f5f9;
                font-size: 1.25rem;
                margin-bottom: 0.5rem;
            }}
            .geri-change-stats {{
                display: flex;
                justify-content: center;
                gap: 1.5rem;
                margin: 1rem 0 1.25rem 0;
                flex-wrap: wrap;
            }}
            .geri-change-item {{
                text-align: center;
                background: #1e293b;
                border: 1px solid #334155;
                border-radius: 10px;
                padding: 0.65rem 1.25rem;
                min-width: 110px;
            }}
            .change-label {{
                display: block;
                font-size: 0.72rem;
                color: #64748b;
                text-transform: uppercase;
                letter-spacing: 0.5px;
                margin-bottom: 0.3rem;
            }}
            .change-value {{
                display: block;
                font-size: 1.1rem;
                font-weight: 700;
            }}
            .geri-what-measures {{
                background: #1e293b;
                border: 1px solid #334155;
                border-radius: 12px;
                padding: 1.25rem 1.5rem;
                margin: 1.25rem 0;
            }}
            .geri-what-measures h2 {{
                font-size: 1rem;
                font-weight: 600;
                color: #f1f5f9;
                margin: 0 0 0.6rem 0;
            }}
            .geri-what-measures p {{
                color: #94a3b8;
                font-size: 0.88rem;
                line-height: 1.65;
                margin: 0;
            }}
            .geri-related-indices {{
                margin: 1.5rem 0 0.5rem 0;
            }}
            .geri-related-indices h2 {{
                font-size: 1.05rem;
                color: #f1f5f9;
                margin-bottom: 0.75rem;
                text-align: center;
            }}
            .related-indices-grid {{
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 0.75rem;
            }}
            .related-index-card {{
                background: #1e293b;
                border: 1px solid #334155;
                border-radius: 10px;
                padding: 1rem;
                text-align: center;
                text-decoration: none;
                transition: border-color 0.2s;
            }}
            .related-index-card:hover {{
                border-color: #60a5fa;
            }}
            .related-index-card .ri-name {{
                color: #60a5fa;
                font-weight: 600;
                font-size: 0.9rem;
                margin-bottom: 0.25rem;
            }}
            .related-index-card .ri-desc {{
                color: #94a3b8;
                font-size: 0.78rem;
                line-height: 1.4;
            }}
            .geri-keyword-intro {{
                color: #94a3b8;
                font-size: 0.92rem;
                line-height: 1.6;
                max-width: 700px;
                margin: 0 auto 0.5rem auto;
                text-align: center;
            }}
            @media (max-width: 600px) {{
                .geri-change-stats {{ gap: 0.75rem; }}
                .geri-change-item {{ min-width: 85px; padding: 0.5rem 0.75rem; }}
                .related-indices-grid {{ grid-template-columns: 1fr; }}
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
                .weekly-card {{ grid-template-columns: 1fr; }}
                .weekly-detail-row {{ grid-template-columns: 1fr; }}
                .weekly-dates {{ margin-left: 0; width: 100%; margin-top: 0.5rem; }}
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
                .weekly-snapshot-section {{ padding: 1rem; }}
                .weekly-chart {{ height: 110px; }}
                .weekly-header {{ flex-direction: column; align-items: flex-start; gap: 0.25rem; }}
                .geri-hero h1 {{ font-size: 1.35rem; }}
                .geri-hero {{ padding: 1.5rem 0 0.75rem 0; }}
                .container {{ padding: 0 0.75rem; }}
                .weekly-interpretation {{ padding: 0.5rem; }}
                .weekly-interpretation p {{ font-size: 0.8rem; }}
                .weekly-drivers li {{ font-size: 0.8rem; }}
                .weekly-chart-container {{ padding: 0.75rem; }}
            }}
            @media (max-width: 600px) {{
                .geri-simplified-drivers {{ flex-direction: column; align-items: center; }}
                .geri-simplified-driver-card {{ max-width: 100%; width: 100%; }}
                .weekly-bar-elevation {{ font-size: 0.45rem; max-width: 35px; }}
                .weekly-bar {{ max-width: 14px; }}
                .weekly-stats {{ flex-direction: column; gap: 0.25rem; text-align: center; }}
                .weekly-detail-row {{ grid-template-columns: 1fr; }}
                .weekly-snapshot-section {{ padding: 0.75rem; }}
            }}
            @media (max-width: 400px) {{
                .weekly-chart {{ height: 90px; gap: 0.1rem; }}
                .weekly-bar-label {{ font-size: 0.55rem; }}
                .weekly-bar-elevation {{ display: none; }}
                .weekly-snapshot-section {{ padding: 0.5rem; }}
                .weekly-chart-container {{ padding: 0.5rem; }}
                .region-tag, .asset-tag {{ font-size: 0.65rem; padding: 0.2rem 0.4rem; }}
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
                    <a href="/">Home</a> / <a href="/indices">Indices</a> / Global Energy Risk Index
                </div>
                <div class="geri-hero">
                    <h1>Global Energy Risk Index (GERI)</h1>
                    <p class="geri-keyword-intro">The GERI tracks geopolitical risk, energy supply disruptions, and market stress across oil, gas, LNG, and power systems worldwide. Updated daily, it provides a single composite score from 0 to 100 measuring systemic risk in global energy markets.</p>
                    <p class="methodology-link"><a href="/geri/methodology">GERI Methodology &amp; Construction &rarr;</a></p>
                </div>
                
                {score_card}
                {change_stats}
                
                <div class="geri-what-measures">
                    <h2>What GERI Measures</h2>
                    <p>GERI aggregates alert severity, regional conflict concentration, and energy asset exposure into a single daily index. It captures geopolitical tensions, supply-chain disruptions, sanctions impacts, and market volatility affecting oil, gas, LNG, and power infrastructure globally.</p>
                </div>
                
                {driver_cards}
                
                {chart_section}
                
                {interp_card}
                
                {weekly_section}
                
                <div class="geri-links">
                    <a href="/geri/history">Full GERI History</a>
                    <a href="/geri/methodology">Methodology</a>
                    <a href="/why-geri">What GERI Actually Measures</a>
                </div>
                
                {cta_block}
                
                <div class="geri-related-indices">
                    <h2>Related EnergyRiskIQ Indices</h2>
                    <div class="related-indices-grid">
                        <a href="/indices/europe-energy-risk-index" class="related-index-card">
                            <div class="ri-name">EERI</div>
                            <div class="ri-desc">Europe Energy Escalation Risk Index</div>
                        </a>
                        <a href="/egsi" class="related-index-card">
                            <div class="ri-name">EGSI</div>
                            <div class="ri-desc">Europe Gas Stress Index</div>
                        </a>
                        <a href="/indices" class="related-index-card">
                            <div class="ri-name">All Indices</div>
                            <div class="ri-desc">Browse the full EnergyRiskIQ index suite</div>
                        </a>
                    </div>
                </div>
            </div>
        </main>
        {render_digest_footer()}
        <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"></script>
        <script>
        (async function() {{
            const canvas = document.getElementById('geriPublicChart');
            if (!canvas) return;
            try {{
                const yesterday = new Date();
                yesterday.setDate(yesterday.getDate() - 1);
                const toParam = yesterday.toISOString().split('T')[0];
                const resp = await fetch('/api/v1/indices/geri?from=2026-01-01&to=' + toParam);
                if (!resp.ok) return;
                const result = await resp.json();
                let allData = result.data || [];
                if (allData.length > 14) allData = allData.slice(-14);
                if (allData.length === 0) return;
                const labels = allData.map(d => d.date ? d.date.substring(5) : '');
                const values = allData.map(d => d.value);
                const bandColors = {{ 'LOW': '#22c55e', 'MODERATE': '#eab308', 'ELEVATED': '#f97316', 'SEVERE': '#ef4444', 'CRITICAL': '#dc2626' }};
                const pointColors = allData.map(d => bandColors[d.band] || '#6b7280');
                new Chart(canvas, {{
                    type: 'line',
                    data: {{
                        labels: labels,
                        datasets: [{{
                            label: 'GERI',
                            data: values,
                            borderColor: '#3b82f6',
                            backgroundColor: 'rgba(59,130,246,0.1)',
                            pointBackgroundColor: pointColors,
                            pointBorderColor: pointColors,
                            pointRadius: 4,
                            tension: 0.3,
                            fill: true,
                            yAxisID: 'y'
                        }}]
                    }},
                    options: {{
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {{ legend: {{ display: false }} }},
                        scales: {{
                            y: {{
                                min: 0, max: 100,
                                grid: {{ color: 'rgba(75,85,99,0.3)' }},
                                ticks: {{ color: '#9ca3af' }}
                            }},
                            x: {{
                                grid: {{ display: false }},
                                ticks: {{ color: '#9ca3af', maxRotation: 45 }}
                            }}
                        }}
                    }}
                }});
            }} catch(e) {{ console.error('Chart error:', e); }}
        }})();
        </script>
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
                    <a href="/indices/global-energy-risk-index">GERI</a> &raquo; History
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
                    <a href="/indices/global-energy-risk-index" class="back-link">&larr; Back to Today's GERI</a>
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
            "date": "2026-02-07",
            "version": "1.6",
            "title": "News Signal Quality Scoring",
            "description": "Introduced a comprehensive signal quality scoring algorithm for all ingested events. Each news item is now scored (0-100) based on source credibility, content freshness, entity specificity, energy relevance, and noise detection. Events are classified into quality bands (high/medium/low/noise) and automatically flagged as GERI drivers when signal strength and market relevance thresholds are met.",
            "type": "enhancement"
        },
        {
            "date": "2026-02-07",
            "version": "1.5",
            "title": "Expanded Ingestion Sources (24 Feeds)",
            "description": "Expanded the ingestion pipeline from 14 to 24 high-quality feeds. New sources address critical gaps in OPEC coverage, maritime security intelligence, China energy demand, Norwegian gas supply, and broader energy trade flows. Each source is assigned a credibility tier and quality weight for signal scoring.",
            "type": "enhancement"
        },
        {
            "date": "2026-02-07",
            "version": "1.5",
            "title": "Expanded Event Taxonomy",
            "description": "Broadened event classification beyond the original three categories (geopolitical, energy, supply_chain) to include thematic categories such as war, military, conflict, sanctions, strike, political, and diplomacy for more granular risk signal identification.",
            "type": "enhancement"
        },
        {
            "date": "2026-02-05",
            "version": "1.4",
            "title": "Dual Y-Axis Asset Overlays",
            "description": "GERI chart now supports dual Y-axis market data overlays with indexed asset prices (Brent crude, TTF gas, VIX, EUR/USD). Overlay data is aligned to GERI index dates and forward-filled across weekends and holidays for visual continuity.",
            "type": "enhancement"
        },
        {
            "date": "2026-02-03",
            "version": "1.3",
            "title": "Plan-Tiered Pro Dashboard",
            "description": "Launched the GERI Pro Dashboard module with progressive intelligence depth across subscription tiers. Includes real-time GERI display, component breakdown, asset stress panel, top risk drivers, historical intelligence, regime statistics, and daily AI-generated summaries.",
            "type": "release"
        },
        {
            "date": "2026-02-02",
            "version": "1.3",
            "title": "Daily Geo-Energy Intelligence Digest",
            "description": "Added an AI-powered daily briefing that synthesizes alerts, index movements, and market context into actionable intelligence. Tiered features range from executive snapshots (Free) through regime classification and probability scoring (Trader) to full institutional intelligence with scenario forecasts (Enterprise).",
            "type": "enhancement"
        },
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
            "description": "Initial release of the Global Energy Risk Index. The index provides a daily composite measure of energy market risk computed from alert severity, regional concentration, and asset exposure across seven weighted regions.",
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
                    <h1>GERI Updates & Changelog</h1>
                    <p>Track the latest updates, enhancements, and changes to the Global Energy Risk Index methodology and calculation.</p>
                </div>
                
                <div class="updates-container">
                    {updates_html}
                </div>
                
                <div class="updates-nav">
                    <a href="/indices/global-energy-risk-index">Current GERI</a>
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
    GERI Methodology Page - Comprehensive SEO content explaining the Global Geo-Energy Risk Index.
    """
    track_page_view("geri_methodology", "/geri/methodology")

    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>GERI Methodology - Global Geo-Energy Risk Index | EnergyRiskIQ</title>
        <meta name="description" content="Complete methodology for the Global Geo-Energy Risk Index (GERI). Understand the four-pillar architecture, regional weighting model, source intelligence, event processing pipeline, and interpretation framework behind the world's leading geo-energy risk indicator.">
        <link rel="canonical" href="{BASE_URL}/geri/methodology">

        <meta property="og:title" content="GERI Methodology — Global Geo-Energy Risk Index | EnergyRiskIQ">
        <meta property="og:description" content="Full methodology for the Global Geo-Energy Risk Index (GERI): four-pillar architecture, regional weighting, source intelligence, computation cadence, and interpretation framework.">
        <meta property="og:url" content="{BASE_URL}/geri/methodology">
        <meta property="og:type" content="article">

        <meta name="twitter:card" content="summary_large_image">
        <meta name="twitter:title" content="GERI Methodology — Global Geo-Energy Risk Index">
        <meta name="twitter:description" content="How EnergyRiskIQ measures daily global geopolitical and energy supply risk through structured intelligence and multi-pillar risk architecture.">

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
            @media (max-width: 640px) {{
                .meth-hero h1 {{ font-size: 1.6rem; }}
                .pillar-grid {{ grid-template-columns: 1fr; }}
                .tier-grid {{ grid-template-columns: 1fr; }}
                .meth-table {{ font-size: 0.8rem; }}
                .meth-table thead th, .meth-table tbody td {{ padding: 0.5rem 0.6rem; }}
            }}
        </style>
    </head>
    <body>
        {render_nav()}

        <main class="container">

            <div class="meth-hero">
                <h1>GERI Methodology</h1>
                <p class="subtitle">A comprehensive overview of how the Global Geo-Energy Risk Index measures daily geopolitical and energy supply risk affecting global energy markets through structured intelligence and multi-pillar risk architecture.</p>
                <div class="version-badge">Model Version: v1.1 &nbsp;|&nbsp; Last Updated: February 2026</div>
            </div>

            <section class="meth-section">
                <h2><span class="section-num">1.</span> What Is GERI?</h2>
                <div class="meth-body">
                    <p>The <strong>Global Geo-Energy Risk Index (GERI)</strong> is a proprietary composite index that measures the overall level of geopolitical and energy supply risk affecting global energy markets on any given day. It distills a complex, multi-source intelligence pipeline into a single, interpretable daily value that answers one question:</p>
                    <div class="meth-blockquote">"How dangerous is the global geopolitical and energy environment today?"</div>
                    <p>GERI functions as a macro-level risk thermometer — analogous to the VIX for financial volatility, but purpose-built for geopolitical and energy risk. It is designed for macro traders, risk committees, asset allocators, strategists, and energy professionals who need a reliable, quantitative signal to inform portfolio decisions, hedging strategies, and risk exposure management.</p>
                    <p>In a world where pipeline politics, military escalations, sanctions regimes, and supply chain disruptions can move energy prices faster than fundamentals, GERI provides the structured risk context that sits between raw news and formal market analysis — enabling professionals to act on intelligence rather than react to headlines.</p>
                </div>
            </section>

            <section class="meth-section">
                <h2><span class="section-num">2.</span> Index Architecture</h2>
                <div class="meth-body">
                    <h3>Scoring Range</h3>
                    <p>GERI produces a daily integer value on a <strong>0 to 100</strong> scale. A value of 0 represents a theoretical state of zero geopolitical or energy risk, while 100 represents a theoretical state of maximum systemic crisis. The scale is calibrated so that moderate, everyday risk environments cluster in the 30–50 range, while sustained readings above 75 indicate historically unusual stress.</p>

                    <h3>Risk Bands</h3>
                    <p>Each daily GERI value maps to one of five risk bands, providing an immediate qualitative interpretation:</p>
                    <table class="meth-table">
                        <thead><tr><th>Risk Band</th><th>Range</th><th>Interpretation</th></tr></thead>
                        <tbody>
                            <tr><td><span class="band-dot" style="background:#22c55e;"></span><strong>LOW</strong></td><td>0 – 20</td><td>Benign geopolitical environment. Energy supply risks are minimal. Markets are operating under normal conditions with no significant escalation signals.</td></tr>
                            <tr><td><span class="band-dot" style="background:#eab308;"></span><strong>MODERATE</strong></td><td>21 – 40</td><td>Background risk is present but manageable. Some regional tensions or supply concerns exist, but systemic contagion is not indicated. Standard monitoring posture.</td></tr>
                            <tr><td><span class="band-dot" style="background:#f97316;"></span><strong>ELEVATED</strong></td><td>41 – 60</td><td>Meaningful risk accumulation detected. Multiple regions or risk vectors are contributing to a heightened threat environment. Active monitoring and hedging consideration warranted.</td></tr>
                            <tr><td><span class="band-dot" style="background:#ef4444;"></span><strong>SEVERE</strong></td><td>61 – 80</td><td>Severe disruption pressure across multiple regions. Risk signals are converging with high probability of market dislocation. Active hedging and contingency planning strongly advised.</td></tr>
                            <tr><td><span class="band-dot" style="background:#991b1b;"></span><strong>CRITICAL</strong></td><td>81 – 100</td><td>Critical systemic stress. Risk signals have converged across regions and asset classes. Historical precedent indicates imminent or active market disruption and supply chain compromise. Defensive positioning and emergency protocols indicated.</td></tr>
                        </tbody>
                    </table>

                    <h3>Trend Indicators</h3>
                    <p>Each daily GERI reading is accompanied by two trend signals:</p>
                    <ul>
                        <li><strong>1-Day Trend</strong> — Change from the previous day's value, indicating immediate momentum</li>
                        <li><strong>7-Day Trend</strong> — Change from the value seven days prior, indicating directional trajectory</li>
                    </ul>
                    <p>These trends provide critical context: a GERI value of 60 that has risen 15 points in a week carries a very different implication than a GERI of 60 that has fallen 10 points over the same period. The same number tells a very different story depending on its trajectory.</p>
                </div>
            </section>

            <section class="meth-section">
                <h2><span class="section-num">3.</span> The Four Pillars</h2>
                <div class="meth-body">
                    <p>GERI is constructed from four distinct risk pillars, each capturing a different dimension of the global risk landscape. This multi-pillar architecture ensures the index is not dominated by any single event type and provides a balanced view of systemic conditions.</p>
                </div>
                <div class="pillar-grid">
                    <div class="pillar-card">
                        <div class="pillar-icon">⚡</div>
                        <div class="pillar-subtitle">Pillar 1</div>
                        <div class="pillar-name">High-Impact Events</div>
                        <div class="pillar-desc">The dominant pillar and primary driver of GERI movements. Captures events with the potential to cause significant, immediate disruption to global energy supply or pricing.</div>
                        <ul class="pillar-measures">
                            <li>Major geopolitical escalations (military conflicts, sanctions, diplomatic crises)</li>
                            <li>Critical infrastructure incidents (pipeline disruptions, refinery outages, port closures)</li>
                            <li>Supply shock events (production cuts, export bans, force majeure declarations)</li>
                            <li>Policy shifts with systemic implications (regulatory changes, trade restrictions)</li>
                        </ul>
                        <div class="pillar-why">Single high-severity events are the strongest predictors of near-term energy market dislocation.</div>
                    </div>
                    <div class="pillar-card">
                        <div class="pillar-icon">📈</div>
                        <div class="pillar-subtitle">Pillar 2</div>
                        <div class="pillar-name">Regional Risk Spikes</div>
                        <div class="pillar-desc">Detects concentrated risk build-up within specific geographic regions, even when individual events may not reach the high-impact threshold.</div>
                        <ul class="pillar-measures">
                            <li>Clusters of moderate-severity events in a single region</li>
                            <li>Accelerating event frequency within a region (escalation velocity)</li>
                            <li>Regional risk scores that deviate significantly from recent baselines</li>
                        </ul>
                        <div class="pillar-why">Energy supply disruptions are typically preceded by a period of regional risk accumulation — rising tensions, increasing event frequency, and building pressure.</div>
                    </div>
                    <div class="pillar-card">
                        <div class="pillar-icon">🛡️</div>
                        <div class="pillar-subtitle">Pillar 3</div>
                        <div class="pillar-name">Asset Risk</div>
                        <div class="pillar-desc">Captures risk signals emanating from direct asset-level stress — specific infrastructure, commodities, or supply chain elements under threat.</div>
                        <ul class="pillar-measures">
                            <li>Threats to specific energy assets (pipelines, terminals, shipping lanes)</li>
                            <li>Commodity-specific supply/demand imbalances flagged by intelligence</li>
                            <li>Critical infrastructure vulnerability alerts</li>
                        </ul>
                        <div class="pillar-why">Some risks are best understood at the asset level — a targeted attack on a key LNG terminal may not register as a major geopolitical event but has profound supply implications.</div>
                    </div>
                    <div class="pillar-card">
                        <div class="pillar-icon">🌍</div>
                        <div class="pillar-subtitle">Pillar 4</div>
                        <div class="pillar-name">Region Concentration</div>
                        <div class="pillar-desc">Measures the geographic diversity (or lack thereof) of the current risk environment, penalising concentrated risk by adding to the GERI score when geographic diversity is low.</div>
                        <ul class="pillar-measures">
                            <li>How concentrated risk is in a single region versus distributed globally</li>
                            <li>The dominance of any single region in the total risk picture</li>
                            <li>Geographic breadth of simultaneous risk signals</li>
                        </ul>
                        <div class="pillar-why">Concentrated risk implies higher disruption probability because a single escalation can trigger cascading effects. Distributed risk implies a more resilient but broadly stressed environment.</div>
                    </div>
                </div>
            </section>

            <section class="meth-section">
                <h2><span class="section-num">4.</span> Regional Weighting Model (v1.1)</h2>
                <div class="meth-body">
                    <h3>Philosophy</h3>
                    <p>Not all geopolitical events carry equal weight for global energy markets. A military escalation in the Strait of Hormuz has fundamentally different implications for energy pricing than an equivalent escalation in a region with no energy infrastructure. The Regional Weighting Model ensures that GERI reflects this reality by applying pre-aggregation multipliers based on the region-cluster from which the event originates.</p>

                    <h3>Region Clusters</h3>
                    <p>GERI groups the world into seven region clusters, each reflecting its structural importance to global energy markets:</p>
                    <table class="meth-table">
                        <thead><tr><th>Region Cluster</th><th>Rationale</th></tr></thead>
                        <tbody>
                            <tr><td><strong>Middle East</strong></td><td>Controls approximately 30%% of global oil production, key chokepoints (Strait of Hormuz), and is the primary source of swing production capacity. Geopolitical instability here directly impacts global crude benchmarks.</td></tr>
                            <tr><td><strong>Russia / Black Sea</strong></td><td>Major global oil and gas exporter, critical pipeline infrastructure to Europe, historically the single largest source of European gas supply. Sanctions, conflicts, and transit disruptions have outsized effects on European energy security.</td></tr>
                            <tr><td><strong>China</strong></td><td>The world's largest energy importer and a decisive demand-side force. Chinese economic activity, stockpiling behaviour, and trade policy directly influence LNG, crude oil, and commodity pricing globally.</td></tr>
                            <tr><td><strong>United States</strong></td><td>The world's largest oil and gas producer, a major LNG exporter, and the issuer of most energy-relevant sanctions. US policy, production shifts, and strategic reserve actions have global pricing implications.</td></tr>
                            <tr><td><strong>Europe Internal</strong></td><td>A major consuming region with limited domestic production. European regulatory decisions, storage policy, and demand patterns affect TTF gas pricing and broader energy security dynamics.</td></tr>
                            <tr><td><strong>LNG Exporters</strong></td><td>A dedicated cluster for Qatar, Australia, and Norway — the three largest LNG exporters outside the US. Disruptions to any major LNG export facility can rapidly tighten global gas markets.</td></tr>
                            <tr><td><strong>Emerging Supply Regions</strong></td><td>Covers North Africa, South America, and other developing energy supply regions. While individually less influential, emerging supply disruptions can exacerbate tight market conditions during periods of elevated stress.</td></tr>
                        </tbody>
                    </table>

                    <h3>Classification Logic</h3>
                    <p>Events are classified into region clusters through a hierarchical process. Keyword overrides ensure that events mentioning specific entities (e.g., Gazprom, Nord Stream, Kremlin for Russia; Qatar, Gorgon, Hammerfest for LNG Exporters) are classified correctly regardless of their generic geographic tagging. Events not caught by keyword overrides are mapped to their cluster based on their tagged region. Global or unattributed events receive a neutral weight, ensuring they contribute to the index without distortion.</p>

                    <h3>Scale Preservation</h3>
                    <p>The regional multipliers are scaled so that their average equals 1.0. This means the Regional Weighting Model reshapes the distribution of risk across regions without inflating or deflating the overall index level. A period with identical events occurring in every region simultaneously would produce the same GERI as a model without regional weighting.</p>
                </div>
            </section>

            <section class="meth-section">
                <h2><span class="section-num">5.</span> Source Intelligence Architecture</h2>
                <div class="meth-body">
                    <h3>Source Philosophy</h3>
                    <p>GERI's signal quality depends directly on the quality, credibility, and diversity of its intelligence sources. The platform follows a strict curation philosophy: institutional sources first, trade and industry sources second, regional sources third — and no noise sources. General news aggregators, opinion blogs, social media, and financial spam feeds are excluded by design.</p>

                    <h3>Source Credibility Tiers</h3>
                    <p>Each source is assigned a credibility tier that influences its contribution weight:</p>
                    <table class="meth-table">
                        <thead><tr><th>Tier</th><th>Description</th><th>Examples</th></tr></thead>
                        <tbody>
                            <tr><td><strong>Tier 0</strong></td><td>Primary institutional data</td><td>EIA, OPEC, government agencies</td></tr>
                            <tr><td><strong>Tier 1</strong></td><td>Professional market intelligence</td><td>Reuters, ICIS, Platts</td></tr>
                            <tr><td><strong>Tier 2</strong></td><td>Specialist trade publications</td><td>FreightWaves, Rigzone, Maritime Executive</td></tr>
                            <tr><td><strong>Tier 3</strong></td><td>Quality regional/general sources</td><td>Al Jazeera, Xinhua, EU Commission</td></tr>
                        </tbody>
                    </table>

                    <h3>Signal Domain Balance</h3>
                    <p>The source portfolio is designed to cover six core signal domains, ensuring comprehensive coverage of all forces that influence energy risk:</p>
                    <table class="meth-table">
                        <thead><tr><th>Signal Domain</th><th>What It Captures</th></tr></thead>
                        <tbody>
                            <tr><td><strong>Supply</strong></td><td>Production disruptions, capacity changes, reserves</td></tr>
                            <tr><td><strong>Transit</strong></td><td>Shipping routes, pipeline flows, chokepoint security</td></tr>
                            <tr><td><strong>Geopolitics</strong></td><td>Military conflicts, sanctions, diplomatic escalations</td></tr>
                            <tr><td><strong>Demand</strong></td><td>Consumption shifts, economic indicators, stockpiling</td></tr>
                            <tr><td><strong>Policy</strong></td><td>Regulatory changes, trade restrictions, energy policy</td></tr>
                            <tr><td><strong>Infrastructure</strong></td><td>Facility construction, maintenance, technical failures</td></tr>
                        </tbody>
                    </table>
                </div>
            </section>

            <section class="meth-section">
                <h2><span class="section-num">6.</span> Event Processing Pipeline</h2>
                <div class="meth-body">
                    <h3>Ingestion</h3>
                    <p>Events are ingested continuously from curated RSS feeds across the source portfolio. Each event undergoes:</p>
                    <ul>
                        <li><strong>Deduplication</strong> — Identical or near-identical events from multiple sources are consolidated</li>
                        <li><strong>Classification</strong> — Events are categorised by type (geopolitical, energy, supply chain, market, environmental) using keyword-based classification</li>
                        <li><strong>Region Tagging</strong> — Events are assigned to geographic regions based on content analysis</li>
                    </ul>

                    <h3>AI Enrichment</h3>
                    <p>Classified events are enriched using AI analysis to produce structured intelligence:</p>
                    <ul>
                        <li><strong>Impact Assessment</strong> — Structured evaluation of the event's potential effect on energy markets</li>
                        <li><strong>Severity Scoring</strong> — Quantitative severity assignment on a standardised scale</li>
                        <li><strong>Asset Linkage</strong> — Identification of specific energy assets, commodities, or infrastructure affected</li>
                        <li><strong>Contextual Summary</strong> — Concise narrative explaining why the event matters for energy risk</li>
                    </ul>

                    <h3>Alert Generation</h3>
                    <p>Enriched events that meet minimum severity and relevance thresholds are converted into structured alerts that feed directly into the GERI computation engine. Three alert types are generated:</p>
                    <ul>
                        <li><strong>HIGH_IMPACT_EVENT</strong> — Individual events with significant severity representing direct geopolitical or energy shocks</li>
                        <li><strong>REGIONAL_RISK_SPIKE</strong> — Regional risk accumulation alerts triggered when a region's aggregate score exceeds its recent baseline</li>
                        <li><strong>ASSET_RISK_ALERT</strong> — Asset-specific alerts triggered when individual infrastructure or commodity risk exceeds thresholds</li>
                    </ul>
                </div>
            </section>

            <section class="meth-section">
                <h2><span class="section-num">7.</span> Computation Cadence</h2>
                <div class="meth-body">
                    <h3>Daily Computation</h3>
                    <p>GERI is computed once per day, producing a single authoritative daily value. The computation window considers alerts generated within the trailing 24-hour period, ensuring the index reflects the most current intelligence.</p>

                    <h3>Publication Schedule</h3>
                    <div class="tier-grid">
                        <div class="tier-card">
                            <div class="tier-label">Paid Subscribers</div>
                            <div class="tier-title">Real-time on computation</div>
                            <ul>
                                <li>Full GERI value, band, and trend</li>
                                <li>Component breakdown and top drivers</li>
                                <li>AI-generated interpretation</li>
                                <li>Cross-asset context and historical comparison</li>
                            </ul>
                        </div>
                        <div class="tier-card">
                            <div class="tier-label">Free Users</div>
                            <div class="tier-title">24-hour delay</div>
                            <ul>
                                <li>GERI value and band</li>
                                <li>Limited historical context</li>
                            </ul>
                        </div>
                        <div class="tier-card">
                            <div class="tier-label">Public / SEO Pages</div>
                            <div class="tier-title">24-hour delay</div>
                            <ul>
                                <li>GERI value and band</li>
                                <li>Top-level trend indicator</li>
                            </ul>
                        </div>
                    </div>

                    <h3>Historical Baseline</h3>
                    <p>The index maintains a rolling historical baseline for normalisation purposes. This baseline tracks the minimum and maximum observed values for each pillar over a rolling window, ensuring that the 0–100 scale remains calibrated to the range of conditions actually observed in the data. This prevents the index from clustering at one end of the scale during prolonged periods of high or low risk.</p>
                </div>
            </section>

            <section class="meth-section">
                <h2><span class="section-num">8.</span> Interpretation Framework</h2>
                <div class="meth-body">
                    <h3>GERI as Risk Thermometer</h3>
                    <p>GERI is not an asset price prediction tool. It is a risk context layer that answers: "What is the current state of the geopolitical and energy risk environment?" The distinction is critical:</p>
                    <ul>
                        <li><strong>GERI rising</strong> means risk inputs are increasing — it does not guarantee asset prices will move in any specific direction</li>
                        <li><strong>GERI falling</strong> means risk inputs are subsiding — it does not guarantee market calm</li>
                        <li><strong>The relationship between GERI and asset prices</strong> is mediated by market positioning, liquidity, storage buffers, and participant expectations</li>
                    </ul>

                    <h3>Cross-Asset Context</h3>
                    <p>GERI is designed to be read alongside energy market data for maximum insight:</p>
                    <table class="meth-table">
                        <thead><tr><th>Cross-Reference</th><th>What It Reveals</th></tr></thead>
                        <tbody>
                            <tr><td><strong>GERI vs Brent Crude</strong></td><td>Whether supply disruption fear is priced into oil markets</td></tr>
                            <tr><td><strong>GERI vs TTF Gas</strong></td><td>European vulnerability to geopolitical gas risk</td></tr>
                            <tr><td><strong>GERI vs VIX</strong></td><td>Whether energy/geopolitical risk is spilling into broader financial markets</td></tr>
                            <tr><td><strong>GERI vs EUR/USD</strong></td><td>European macro vulnerability to energy shocks</td></tr>
                            <tr><td><strong>GERI vs EU Gas Storage</strong></td><td>Whether Europe's physical buffer is adequate for the current risk level</td></tr>
                        </tbody>
                    </table>

                    <h3>Regime Recognition</h3>
                    <p>GERI's historical trajectory can be divided into recognisable regimes. Regime transitions are the most actionable signals in the index:</p>
                    <table class="meth-table">
                        <thead><tr><th>Regime</th><th>Characteristics</th></tr></thead>
                        <tbody>
                            <tr><td><strong>Risk Accumulation</strong></td><td>GERI rising gradually, assets react slowly. Risk is building but markets are discounting. Early warning phase.</td></tr>
                            <tr><td><strong>Shock</strong></td><td>GERI spikes sharply, assets overshoot. A high-impact event has materialised. Maximum volatility phase.</td></tr>
                            <tr><td><strong>Stabilisation</strong></td><td>GERI begins to fall, but assets remain volatile. Markets are repricing and uncertainty is still elevated.</td></tr>
                            <tr><td><strong>Recovery</strong></td><td>GERI returns to low/moderate bands, assets normalise. Risk has dissipated and markets have found equilibrium.</td></tr>
                        </tbody>
                    </table>
                </div>
            </section>

            <section class="meth-section">
                <h2><span class="section-num">9.</span> What GERI Does Not Do</h2>
                <div class="meth-body">
                    <p>For transparency and proper use, it is important to understand the boundaries of the index:</p>
                    <ul>
                        <li><strong>GERI is not a trading signal.</strong> It is a risk context layer, not a buy/sell indicator.</li>
                        <li><strong>GERI does not predict asset prices.</strong> It measures risk inputs, not market outcomes.</li>
                        <li><strong>GERI does not cover all risk types.</strong> It focuses on geopolitical and energy supply risk. It does not measure financial systemic risk, credit risk, or natural disaster risk except insofar as they affect energy markets.</li>
                        <li><strong>GERI is not real-time intraday.</strong> It is a daily index. Intraday events will be reflected in the following day's computation.</li>
                        <li><strong>GERI is not a substitute for fundamental analysis.</strong> It is a complementary intelligence layer designed to sit alongside traditional energy market analysis.</li>
                    </ul>
                </div>
            </section>

            <section class="meth-section">
                <h2><span class="section-num">10.</span> Model Governance and Evolution</h2>
                <div class="meth-body">
                    <h3>Version Control</h3>
                    <p>GERI operates under strict version control. The current production model is <strong>v1.1</strong>, which introduced the Regional Weighting Model. All historical data is tagged with its computation model version, ensuring full reproducibility and auditability.</p>

                    <h3>Planned Enhancements</h3>
                    <ul>
                        <li><strong>Source Weighting Calibration</strong> — An adaptive system that will calibrate individual source weights based on measured contribution to predictive power, uniqueness, timeliness, and false-positive control</li>
                        <li><strong>Semantic Deduplication</strong> — Moving beyond title-based deduplication to AI-powered semantic clustering, reducing noise from multiple sources reporting the same underlying event</li>
                        <li><strong>Temporal Event Detection</strong> — Distinguishing between developing events and resolved events, preventing stale intelligence from inflating the index</li>
                    </ul>

                    <h3>Independence and Objectivity</h3>
                    <p>GERI is computed algorithmically from structured intelligence inputs. There is no editorial override, manual adjustment, or subjective intervention in the daily index value. The methodology is fixed for each model version, and changes are implemented only through formal version upgrades with documented rationale.</p>
                </div>
            </section>

            <div class="meth-cta">
                <h3>Access Full GERI Intelligence</h3>
                <p>Get real-time GERI values, component breakdowns, historical charts, cross-asset context, and AI-powered interpretations with EnergyRiskIQ.</p>
                <a href="/users" class="cta-button">Get FREE Access</a>
            </div>

            <div class="disclaimer">
                <p>Global Geo-Energy Risk Index (GERI) is a proprietary index of EnergyRiskIQ. This methodology document is provided for transparency and educational purposes. It does not constitute financial advice.</p>
                <p>Model Version: v1.1 &nbsp;|&nbsp; Last Updated: February 2026</p>
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
                    <a href="/indices/global-energy-risk-index">GERI</a> &raquo; 
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
                    <a href="/indices/global-energy-risk-index">GERI</a> &raquo; 
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


def get_digest_dark_styles() -> str:
    return """
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: #0f172a;
            color: #e2e8f0;
            min-height: 100vh;
            overflow-x: hidden;
        }
        .container { max-width: 900px; margin: 0 auto; padding: 0 1rem; }
        .nav {
            background: #1e293b;
            border-bottom: 1px solid #334155;
            padding: 1rem 0;
            position: sticky;
            top: 0;
            z-index: 100;
        }
        .nav-inner { display: flex; justify-content: space-between; align-items: center; max-width: 900px; margin: 0 auto; padding: 0 1rem; }
        .logo {
            font-weight: 700;
            font-size: 1.25rem;
            color: #f1f5f9;
            text-decoration: none;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }
        .nav-links { display: flex; gap: 1.5rem; align-items: center; }
        .nav-links a { color: #94a3b8; text-decoration: none; font-weight: 500; font-size: 14px; }
        .nav-links a:hover { color: #f1f5f9; }
        .cta-btn-nav {
            background: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%);
            color: white !important;
            padding: 0.5rem 1rem;
            border-radius: 6px;
            text-decoration: none;
            font-weight: 600;
            font-size: 13px;
        }
        .cta-btn-nav:hover { opacity: 0.9; }
        .breadcrumbs {
            font-size: 0.875rem;
            color: #64748b;
            margin-bottom: 1rem;
            padding-top: 1.5rem;
        }
        .breadcrumbs a { color: #60a5fa; text-decoration: none; }
        .breadcrumbs a:hover { text-decoration: underline; }
        .digest-header-bar {
            background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
            border: 1px solid #334155;
            border-radius: 12px;
            padding: 20px 24px;
            margin-bottom: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 16px;
        }
        .digest-header-bar .digest-date {
            color: #94a3b8;
            font-size: 13px;
        }
        .digest-header-bar .digest-date strong {
            color: #e2e8f0;
        }
        .digest-delayed-badge {
            background: rgba(251, 191, 36, 0.15);
            border: 1px solid rgba(251, 191, 36, 0.3);
            color: #fbbf24;
            padding: 6px 14px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
        }
        .digest-card {
            background: #1e293b;
            border: 1px solid #334155;
            border-radius: 12px;
            margin-bottom: 16px;
            overflow: hidden;
        }
        .digest-card-header {
            padding: 16px 20px;
            border-bottom: 1px solid #334155;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .digest-card-header h3 {
            font-size: 15px;
            font-weight: 600;
            color: #f1f5f9;
            margin: 0;
        }
        .digest-card-header .digest-section-icon {
            font-size: 16px;
        }
        .digest-card-body {
            padding: 20px;
        }
        .digest-risk-tone {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 16px 20px;
            border-radius: 10px;
            margin-bottom: 16px;
        }
        .digest-risk-tone.tone-red { background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.3); }
        .digest-risk-tone.tone-orange { background: rgba(249, 115, 22, 0.1); border: 1px solid rgba(249, 115, 22, 0.3); }
        .digest-risk-tone.tone-yellow { background: rgba(234, 179, 8, 0.1); border: 1px solid rgba(234, 179, 8, 0.3); }
        .digest-risk-tone.tone-green { background: rgba(34, 197, 94, 0.1); border: 1px solid rgba(34, 197, 94, 0.3); }
        .digest-risk-tone.tone-gray { background: rgba(148, 163, 184, 0.1); border: 1px solid rgba(148, 163, 184, 0.3); }
        .digest-risk-tone .tone-label {
            font-size: 18px;
            font-weight: 700;
        }
        .digest-risk-tone.tone-red .tone-label { color: #ef4444; }
        .digest-risk-tone.tone-orange .tone-label { color: #f97316; }
        .digest-risk-tone.tone-yellow .tone-label { color: #eab308; }
        .digest-risk-tone.tone-green .tone-label { color: #22c55e; }
        .digest-risk-tone.tone-gray .tone-label { color: #94a3b8; }
        .digest-index-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 12px;
            margin-bottom: 16px;
        }
        .digest-index-card {
            background: #0f172a;
            border: 1px solid #334155;
            border-radius: 10px;
            padding: 16px;
            text-align: center;
        }
        .digest-index-card .index-name {
            color: #94a3b8;
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 6px;
        }
        .digest-index-card .index-value {
            font-size: 28px;
            font-weight: 700;
            color: #f1f5f9;
        }
        .digest-index-card .index-band {
            font-size: 11px;
            font-weight: 600;
            padding: 2px 8px;
            border-radius: 4px;
            margin-top: 4px;
            display: inline-block;
        }
        .digest-index-card .index-trend {
            font-size: 12px;
            margin-top: 4px;
        }
        .digest-index-card .index-trend.up { color: #ef4444; }
        .digest-index-card .index-trend.down { color: #22c55e; }
        .digest-index-card .index-trend.flat { color: #94a3b8; }
        .digest-asset-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
            gap: 10px;
        }
        .digest-asset-item {
            background: #0f172a;
            border: 1px solid #334155;
            border-radius: 8px;
            padding: 14px;
            text-align: center;
        }
        .digest-asset-item .asset-label {
            color: #94a3b8;
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            margin-bottom: 4px;
        }
        .digest-asset-item .asset-value {
            font-size: 20px;
            font-weight: 700;
            color: #f1f5f9;
        }
        .digest-asset-item .asset-change {
            font-size: 13px;
            font-weight: 600;
            margin-top: 2px;
        }
        .digest-asset-item .asset-change.positive { color: #22c55e; }
        .digest-asset-item .asset-change.negative { color: #ef4444; }
        .digest-asset-item .asset-change.neutral { color: #94a3b8; }
        .digest-alert-item {
            background: #0f172a;
            border: 1px solid #334155;
            border-radius: 8px;
            padding: 14px 16px;
            margin-bottom: 10px;
        }
        .digest-alert-item .alert-headline {
            font-weight: 600;
            color: #f1f5f9;
            font-size: 14px;
            margin-bottom: 6px;
        }
        .digest-alert-item .alert-meta {
            display: flex;
            gap: 12px;
            flex-wrap: wrap;
            font-size: 12px;
            color: #94a3b8;
        }
        .digest-alert-item .alert-meta span {
            display: flex;
            align-items: center;
            gap: 4px;
        }
        .digest-severity-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            display: inline-block;
        }
        .digest-severity-dot.sev-5 { background: #ef4444; }
        .digest-severity-dot.sev-4 { background: #f97316; }
        .digest-severity-dot.sev-3 { background: #eab308; }
        .digest-severity-dot.sev-2 { background: #3b82f6; }
        .digest-severity-dot.sev-1 { background: #22c55e; }
        .digest-narrative {
            background: #0f172a;
            border: 1px solid #334155;
            border-radius: 10px;
            padding: 20px;
            line-height: 1.7;
            color: #cbd5e1;
            font-size: 14px;
        }
        .digest-narrative h2 {
            color: #f1f5f9;
            font-size: 16px;
            margin: 20px 0 10px 0;
            padding-bottom: 6px;
            border-bottom: 1px solid #334155;
        }
        .digest-narrative h2:first-child {
            margin-top: 0;
        }
        .digest-narrative strong {
            color: #e2e8f0;
        }
        .digest-narrative ul, .digest-narrative ol {
            padding-left: 20px;
            margin: 8px 0;
        }
        .digest-narrative li {
            margin-bottom: 4px;
        }
        .digest-locked-section {
            background: linear-gradient(135deg, rgba(59, 130, 246, 0.05) 0%, rgba(139, 92, 246, 0.05) 100%);
            border: 1px dashed rgba(59, 130, 246, 0.3);
            border-radius: 10px;
            padding: 20px;
            text-align: center;
            margin-bottom: 16px;
        }
        .digest-locked-section .lock-icon {
            font-size: 24px;
            margin-bottom: 8px;
        }
        .digest-locked-section .lock-title {
            color: #60a5fa;
            font-weight: 600;
            font-size: 14px;
            margin-bottom: 4px;
        }
        .digest-locked-section .lock-desc {
            color: #94a3b8;
            font-size: 12px;
            margin-bottom: 12px;
        }
        .digest-locked-section .lock-btn {
            background: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%);
            color: white;
            border: none;
            padding: 8px 20px;
            border-radius: 8px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            text-decoration: none;
            display: inline-block;
        }
        .digest-locked-section .lock-btn:hover {
            opacity: 0.9;
        }
        .digest-nav-pagination {
            display: flex;
            justify-content: space-between;
            margin: 2rem 0;
            padding: 1rem 0;
            border-top: 1px solid #334155;
        }
        .digest-nav-pagination a {
            color: #60a5fa;
            text-decoration: none;
            font-weight: 500;
            font-size: 14px;
        }
        .digest-nav-pagination a:hover { text-decoration: underline; }
        .page-list {
            list-style: none;
            display: grid;
            gap: 0.5rem;
        }
        .page-list li a {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0.75rem 1rem;
            background: #1e293b;
            border: 1px solid #334155;
            border-radius: 6px;
            text-decoration: none;
            color: #f1f5f9;
            transition: border-color 0.2s;
        }
        .page-list li a:hover { border-color: #60a5fa; }
        .page-list .date { font-weight: 600; }
        footer {
            background: #1e293b;
            border-top: 1px solid #334155;
            color: #94a3b8;
            padding: 2rem 0;
            margin-top: 3rem;
        }
        footer a { color: #60a5fa; text-decoration: none; }
        .footer-inner {
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 1rem;
            max-width: 900px;
            margin: 0 auto;
            padding: 0 1rem;
        }
        .footer-links { display: flex; gap: 1.5rem; flex-wrap: wrap; justify-content: center; }
        .mobile-menu-btn {
            display: none;
            background: none;
            border: none;
            cursor: pointer;
            padding: 0.5rem;
            color: #f1f5f9;
        }
        .mobile-menu-btn span {
            display: block;
            width: 22px;
            height: 2px;
            background: #f1f5f9;
            margin: 5px 0;
            border-radius: 2px;
            transition: all 0.3s;
        }
        @media (max-width: 768px) {
            .digest-header-bar {
                flex-direction: column;
                align-items: flex-start;
            }
            .digest-index-grid {
                grid-template-columns: repeat(2, 1fr);
            }
            .digest-asset-grid {
                grid-template-columns: repeat(2, 1fr);
            }
            .mobile-menu-btn { display: block; }
            .nav-links {
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
            }
            .nav-links.open { display: flex; }
            .nav-links a {
                padding: 0.75rem 1rem;
                border-bottom: 1px solid #334155;
                width: 100%;
                text-align: left;
            }
            .nav-links a:last-child { border-bottom: none; }
            .nav-links .cta-btn-nav {
                margin-top: 0.5rem;
                text-align: center;
            }
            .nav { position: relative; }
            .footer-inner { flex-direction: column; text-align: center; }
        }
    </style>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    """


def render_digest_nav() -> str:
    return """
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
                <a href="/">Home</a>
                <a href="/indices/global-energy-risk-index">GERI</a>
                <a href="/alerts">Alerts</a>
                <a href="/daily-geo-energy-intelligence-digest">Digest</a>
                <a href="/daily-geo-energy-intelligence-digest/history">History</a>
                <a href="/users" class="cta-btn-nav">Get FREE Access</a>
            </div>
        </div>
    </nav>
    """


def _get_indices_latest_values() -> dict:
    from datetime import datetime, timedelta
    result = {"geri": None, "eeri": None, "egsi": None}
    yesterday = (datetime.utcnow() - timedelta(days=1)).date()
    day30 = (datetime.utcnow() - timedelta(days=31)).date()
    try:
        with get_cursor(commit=False) as cursor:
            cursor.execute("""
                SELECT value, band, date FROM intel_indices_daily
                WHERE index_id = 'global:geo_energy_risk' AND date <= %s AND date >= %s
                ORDER BY date ASC
            """, (yesterday, day30))
            rows = cursor.fetchall()
            if rows:
                latest = rows[-1]
                change = (rows[-1]["value"] - rows[-2]["value"]) if len(rows) > 1 else None
                sparkline = [r["value"] for r in rows]
                result["geri"] = {"value": latest["value"], "band": latest["band"], "date": str(latest["date"]), "change": change, "sparkline": sparkline}
            else:
                cursor.execute("""
                    SELECT value, band, computed_at::date as date FROM geri_live
                    WHERE computed_at::date <= %s AND value > 0
                    ORDER BY computed_at DESC LIMIT 1
                """, (yesterday,))
                row = cursor.fetchone()
                if row:
                    result["geri"] = {"value": row["value"], "band": row["band"], "date": str(row["date"]), "change": None, "sparkline": []}
    except Exception:
        pass
    try:
        with get_cursor(commit=False) as cursor:
            cursor.execute("""
                SELECT value, band, date FROM reri_indices_daily
                WHERE index_id = 'europe:eeri' AND date <= %s AND date >= %s
                ORDER BY date ASC
            """, (yesterday, day30))
            rows = cursor.fetchall()
            if rows:
                latest = rows[-1]
                change = (rows[-1]["value"] - rows[-2]["value"]) if len(rows) > 1 else None
                sparkline = [r["value"] for r in rows]
                result["eeri"] = {"value": latest["value"], "band": latest["band"], "date": str(latest["date"]), "change": change, "sparkline": sparkline}
    except Exception:
        pass
    try:
        with get_cursor(commit=False) as cursor:
            cursor.execute("""
                SELECT index_value as value, band, index_date as date FROM egsi_m_daily
                WHERE region = 'Europe' AND index_date <= %s AND index_date >= %s
                ORDER BY index_date ASC
            """, (yesterday, day30))
            rows = cursor.fetchall()
            if rows:
                latest = rows[-1]
                raw = float(latest["value"])
                display_val = int(raw) if raw == int(raw) else round(raw, 1)
                prev_raw = float(rows[-2]["value"]) if len(rows) > 1 else None
                change = round(raw - prev_raw, 1) if prev_raw is not None else None
                sparkline = [float(r["value"]) for r in rows]
                result["egsi"] = {"value": display_val, "band": latest["band"], "date": str(latest["date"]), "change": change, "sparkline": sparkline}
    except Exception:
        pass
    return result


@router.get("/indices", response_class=HTMLResponse)
async def indices_hub_page(request: Request):
    await apply_anti_scraping(request)
    track_page_view("indices", "/indices")

    data = _get_indices_latest_values()

    band_colors = {
        'LOW': '#22c55e', 'MODERATE': '#eab308', 'ELEVATED': '#f97316',
        'SEVERE': '#ef4444', 'CRITICAL': '#dc2626'
    }

    def _format_change(change):
        if change is None:
            return '<span style="color: #475569;">—</span>'
        c = int(change) if change == int(change) else round(change, 1)
        if c > 0:
            return f'<span style="color: #ef4444; font-weight: 600;">&uarr;{c}</span>'
        elif c < 0:
            return f'<span style="color: #22c55e; font-weight: 600;">&darr;{abs(c)}</span>'
        return '<span style="color: #64748b;">&#x2192;0</span>'

    def _render_sparkline_svg(values, color, width=200, height=40):
        if not values or len(values) < 2:
            return ''
        mn = min(values)
        mx = max(values)
        rng = mx - mn if mx != mn else 1
        pad = 2
        usable_h = height - pad * 2
        usable_w = width - pad * 2
        step = usable_w / (len(values) - 1)
        points = []
        for i, v in enumerate(values):
            x = round(pad + i * step, 1)
            y = round(pad + usable_h - ((v - mn) / rng) * usable_h, 1)
            points.append(f"{x},{y}")
        polyline = " ".join(points)
        fill_points = f"{pad},{height - pad} " + polyline + f" {round(pad + (len(values)-1)*step, 1)},{height - pad}"
        return f'''<div class="idx-sparkline">
            <svg viewBox="0 0 {width} {height}" preserveAspectRatio="none" width="100%" height="{height}">
                <polyline points="{fill_points}" fill="{color}" fill-opacity="0.1" stroke="none"/>
                <polyline points="{polyline}" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                <circle cx="{points[-1].split(',')[0]}" cy="{points[-1].split(',')[1]}" r="2.5" fill="{color}"/>
            </svg>
            <div class="idx-sparkline-label">30-day trend</div>
        </div>'''

    def _render_index_card(idx_key, title, abbrev, description, seo_line, href, icon, data_entry):
        if data_entry:
            val = data_entry["value"]
            band = data_entry["band"]
            b_color = band_colors.get(band, '#6b7280')
            date_str = data_entry["date"]
            change_html = _format_change(data_entry.get("change"))
            sparkline_html = _render_sparkline_svg(data_entry.get("sparkline", []), b_color)
            value_html = f'''
                <div class="idx-card-value" style="color: {b_color};">{val}<span class="idx-card-max"> / 100</span></div>
                <div class="idx-card-band" style="color: {b_color};">{band} {change_html}</div>
                {sparkline_html}
                <div class="idx-card-date">{date_str} &middot; 24h Delayed</div>
            '''
        else:
            value_html = '<div class="idx-card-no-data">Awaiting data</div>'

        return f'''
        <div class="idx-card">
            <div class="idx-card-icon">{icon}</div>
            <h2><a href="{href}">{title} ({abbrev})</a></h2>
            <p class="idx-card-desc">{description}</p>
            <p class="idx-card-seo">{seo_line}</p>
            {value_html}
            <a href="{href}" class="idx-card-cta">View Index &rarr;</a>
        </div>
        '''

    cards_html = _render_index_card(
        "geri", "Global Energy Risk Index", "GERI",
        "Measures escalation risk across global energy markets including oil, LNG logistics, and geopolitical tensions.",
        "The Global Energy Risk Index measures escalation risk across global oil, LNG, and geopolitical energy systems.",
        "/indices/global-energy-risk-index", "&#x1F525;", data.get("geri")
    ) + _render_index_card(
        "eeri", "European Energy Risk Index", "EERI",
        "Tracks escalation risk specific to Europe's energy system including gas flows, storage stress, sanctions, and infrastructure risk.",
        "The European Energy Risk Index tracks gas flows, sanctions impact, and infrastructure risk across European energy markets.",
        "/indices/europe-energy-risk-index", "&#x26A1;", data.get("eeri")
    ) + _render_index_card(
        "egsi", "Europe Gas Stress Index", "EGSI",
        "Quantifies stress in the European gas market using storage levels, LNG flows, weather risk, and supply disruptions.",
        "The Europe Gas Stress Index quantifies gas market stress using storage, LNG flows, and supply disruption signals.",
        "/egsi", "&#x1F4A8;", data.get("egsi")
    )

    readings_rows = ""
    for label, abbrev, entry in [("Global Energy Risk Index", "GERI", data.get("geri")),
                                  ("European Energy Risk Index", "EERI", data.get("eeri")),
                                  ("Europe Gas Stress Index", "EGSI", data.get("egsi"))]:
        if entry:
            b_color = band_colors.get(entry["band"], '#6b7280')
            change_html = _format_change(entry.get("change"))
            readings_rows += f'''
            <tr>
                <td><strong>{abbrev}</strong></td>
                <td style="color: {b_color}; font-weight: 700;">{entry["value"]}</td>
                <td>{change_html}</td>
                <td style="color: {b_color};">{entry["band"]}</td>
                <td style="color: #64748b; font-size: 0.85rem;">{entry["date"]}</td>
            </tr>'''
        else:
            readings_rows += f'''
            <tr>
                <td><strong>{abbrev}</strong></td>
                <td style="color: #475569;">—</td>
                <td style="color: #475569;">—</td>
                <td style="color: #475569;">—</td>
                <td style="color: #64748b; font-size: 0.85rem;">—</td>
            </tr>'''

    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Energy Risk Indices for Global Energy Markets | EnergyRiskIQ</title>
        <meta name="description" content="EnergyRiskIQ energy risk indices translate geopolitical events, supply chain disruptions, and policy developments into measurable energy risk signals. Track GERI, EERI, and EGSI.">
        <link rel="canonical" href="{BASE_URL}/indices">

        <meta property="og:title" content="Energy Risk Indices for Global Energy Markets | EnergyRiskIQ">
        <meta property="og:description" content="Track energy risk with GERI, EERI, and EGSI indices. Daily updates on geopolitical risk, European energy stress, and gas market conditions.">
        <meta property="og:url" content="{BASE_URL}/indices">
        <meta property="og:type" content="website">

        <link rel="icon" type="image/png" href="/static/favicon.png">
        {get_digest_dark_styles()}
        <style>
            .container {{ max-width: 1000px; }}

            .indices-hero {{
                text-align: center;
                padding: 2.5rem 0 1.5rem 0;
            }}
            .indices-hero h1 {{
                font-size: 2rem;
                margin-bottom: 0.75rem;
                color: #f1f5f9;
                font-weight: 800;
            }}
            .indices-hero p {{
                color: #94a3b8;
                max-width: 680px;
                margin: 0 auto 0.5rem auto;
                font-size: 1rem;
                line-height: 1.7;
            }}

            .idx-grid {{
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 1.25rem;
                margin: 1.5rem 0 2.5rem 0;
            }}
            .idx-card {{
                background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
                border: 1px solid #334155;
                border-radius: 14px;
                padding: 1.75rem 1.5rem;
                text-align: center;
                transition: border-color 0.2s, transform 0.2s;
                display: flex;
                flex-direction: column;
                align-items: center;
            }}
            .idx-card:hover {{
                border-color: #60a5fa;
                transform: translateY(-3px);
            }}
            .idx-card-icon {{
                font-size: 2rem;
                margin-bottom: 0.75rem;
            }}
            .idx-card h2 {{
                font-size: 1.05rem;
                margin: 0 0 0.5rem 0;
                line-height: 1.4;
            }}
            .idx-card h2 a {{
                color: #f1f5f9;
                text-decoration: none;
            }}
            .idx-card h2 a:hover {{
                color: #60a5fa;
                text-decoration: underline;
            }}
            .idx-card-desc {{
                color: #94a3b8;
                font-size: 0.875rem;
                line-height: 1.6;
                margin-bottom: 1rem;
                flex-grow: 1;
            }}
            .idx-card-value {{
                font-size: 2.25rem;
                font-weight: 700;
                line-height: 1;
                margin-bottom: 0.25rem;
            }}
            .idx-card-max {{
                font-size: 0.85rem;
                color: #64748b;
            }}
            .idx-card-band {{
                font-size: 0.95rem;
                font-weight: 600;
                margin-bottom: 0.25rem;
            }}
            .idx-card-date {{
                font-size: 0.75rem;
                color: #64748b;
                margin-bottom: 1rem;
            }}
            .idx-card-seo {{
                color: #64748b;
                font-size: 0.775rem;
                line-height: 1.5;
                margin-bottom: 0.75rem;
                font-style: italic;
            }}
            .idx-sparkline {{
                width: 100%;
                margin: 0.5rem 0;
                padding: 0 0.5rem;
            }}
            .idx-sparkline svg {{
                display: block;
            }}
            .idx-sparkline-label {{
                font-size: 0.65rem;
                color: #475569;
                text-align: center;
                margin-top: 0.15rem;
            }}
            .idx-card-no-data {{
                color: #475569;
                font-size: 0.9rem;
                margin-bottom: 1rem;
                padding: 0.75rem 0;
            }}
            .idx-card-cta {{
                display: inline-block;
                background: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%);
                color: white;
                padding: 0.5rem 1.25rem;
                border-radius: 8px;
                text-decoration: none;
                font-weight: 600;
                font-size: 0.85rem;
                transition: opacity 0.2s;
            }}
            .idx-card-cta:hover {{ opacity: 0.85; }}

            .idx-section {{
                background: #1e293b;
                border: 1px solid #334155;
                border-radius: 14px;
                padding: 2rem 2.5rem;
                margin-bottom: 2rem;
            }}
            .idx-section h2 {{
                font-size: 1.35rem;
                color: #f1f5f9;
                margin: 0 0 1rem 0;
                font-weight: 700;
            }}
            .idx-section p {{
                color: #94a3b8;
                font-size: 0.95rem;
                line-height: 1.7;
                margin-bottom: 0.75rem;
            }}
            .idx-section p:last-child {{ margin-bottom: 0; }}

            .idx-components {{
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 1rem;
                margin-top: 1.25rem;
            }}
            .idx-component {{
                background: rgba(15, 23, 42, 0.6);
                border: 1px solid #334155;
                border-radius: 10px;
                padding: 1.25rem;
            }}
            .idx-component-icon {{
                font-size: 1.5rem;
                margin-bottom: 0.5rem;
            }}
            .idx-component h3 {{
                font-size: 0.95rem;
                color: #e2e8f0;
                margin: 0 0 0.5rem 0;
                font-weight: 600;
            }}
            .idx-component p {{
                color: #94a3b8;
                font-size: 0.825rem;
                line-height: 1.55;
                margin: 0;
            }}

            .idx-readings {{
                width: 100%;
                border-collapse: collapse;
                margin-top: 1rem;
            }}
            .idx-readings th {{
                text-align: left;
                color: #64748b;
                font-size: 0.8rem;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.05em;
                padding: 0.5rem 0.75rem;
                border-bottom: 1px solid #334155;
            }}
            .idx-readings td {{
                padding: 0.65rem 0.75rem;
                color: #e2e8f0;
                font-size: 0.9rem;
                border-bottom: 1px solid rgba(51, 65, 85, 0.5);
            }}

            .idx-cta-section {{
                text-align: center;
                padding: 2.5rem 2rem;
                background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
                border: 1px solid #334155;
                border-radius: 14px;
                margin-bottom: 2rem;
            }}
            .idx-cta-section h2 {{
                font-size: 1.35rem;
                color: #f1f5f9;
                margin: 0 0 0.5rem 0;
            }}
            .idx-cta-section p {{
                color: #94a3b8;
                max-width: 520px;
                margin: 0 auto 1.25rem auto;
                font-size: 0.95rem;
            }}
            .idx-cta-btn {{
                display: inline-block;
                background: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%);
                color: white;
                padding: 0.75rem 2rem;
                border-radius: 10px;
                text-decoration: none;
                font-weight: 700;
                font-size: 1rem;
                transition: opacity 0.2s;
            }}
            .idx-cta-btn:hover {{ opacity: 0.85; }}

            .idx-bands-visual {{
                display: flex;
                flex-direction: column;
                gap: 0;
                border-radius: 12px;
                overflow: hidden;
                border: 1px solid rgba(255,255,255,0.06);
            }}
            .idx-band-row {{
                display: grid;
                grid-template-columns: 80px 120px 1fr;
                align-items: center;
                padding: 0.75rem 1.25rem;
                border-bottom: 1px solid rgba(255,255,255,0.04);
            }}
            .idx-band-row:last-child {{ border-bottom: none; }}
            .idx-band-range {{
                font-size: 0.85rem;
                font-weight: 700;
                font-family: 'Courier New', monospace;
            }}
            .idx-band-name {{
                font-size: 0.8rem;
                font-weight: 700;
                letter-spacing: 0.5px;
            }}
            .idx-band-desc {{
                font-size: 0.8rem;
                color: #94a3b8;
            }}
            .idx-band-low {{
                background: rgba(34, 197, 94, 0.08);
            }}
            .idx-band-low .idx-band-range,
            .idx-band-low .idx-band-name {{
                color: #22c55e;
            }}
            .idx-band-moderate {{
                background: rgba(234, 179, 8, 0.08);
            }}
            .idx-band-moderate .idx-band-range,
            .idx-band-moderate .idx-band-name {{
                color: #eab308;
            }}
            .idx-band-elevated {{
                background: rgba(249, 115, 22, 0.08);
            }}
            .idx-band-elevated .idx-band-range,
            .idx-band-elevated .idx-band-name {{
                color: #f97316;
            }}
            .idx-band-severe {{
                background: rgba(239, 68, 68, 0.08);
            }}
            .idx-band-severe .idx-band-range,
            .idx-band-severe .idx-band-name {{
                color: #ef4444;
            }}
            .idx-band-critical {{
                background: rgba(168, 85, 247, 0.08);
            }}
            .idx-band-critical .idx-band-range,
            .idx-band-critical .idx-band-name {{
                color: #a855f7;
            }}
            @media (max-width: 600px) {{
                .idx-band-row {{
                    grid-template-columns: 65px 90px 1fr;
                    padding: 0.6rem 0.75rem;
                }}
                .idx-band-range {{ font-size: 0.75rem; }}
                .idx-band-name {{ font-size: 0.7rem; }}
                .idx-band-desc {{ font-size: 0.7rem; }}
            }}

            .idx-analysis-links {{
                list-style: none;
                padding: 0;
                margin: 1rem 0 0 0;
            }}
            .idx-analysis-links li {{
                padding: 0.5rem 0;
                border-bottom: 1px solid rgba(51, 65, 85, 0.4);
            }}
            .idx-analysis-links li:last-child {{ border-bottom: none; }}
            .idx-analysis-links a {{
                color: #60a5fa;
                text-decoration: none;
                font-size: 0.9rem;
            }}
            .idx-analysis-links a:hover {{
                color: #93c5fd;
                text-decoration: underline;
            }}
            .idx-scale-note {{
                color: #94a3b8;
                font-size: 0.9rem;
                text-align: center;
                margin-bottom: 0.5rem;
                line-height: 1.6;
            }}

            @media (max-width: 768px) {{
                .idx-grid {{
                    grid-template-columns: 1fr;
                    gap: 1rem;
                }}
                .idx-components {{
                    grid-template-columns: 1fr;
                }}
                .idx-section {{
                    padding: 1.25rem 1rem;
                }}
                .indices-hero h1 {{
                    font-size: 1.5rem;
                }}
                .idx-card-value {{
                    font-size: 1.75rem;
                }}
            }}
        </style>
    </head>
    <body>
        <nav class="nav">
            <div class="container nav-inner">
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
                    <a href="/">Home</a> / Energy Risk Indices
                </div>

                <div class="indices-hero">
                    <h1>Energy Risk Indices for Global Energy Markets</h1>
                    <p>EnergyRiskIQ indices translate geopolitical events, supply chain disruptions, and policy developments into measurable energy risk signals.</p>
                    <p>Each index aggregates thousands of events and market indicators to quantify escalation risk in global and regional energy systems.</p>
                </div>

                <p class="idx-scale-note">All indices use a 0&ndash;100 escalation scale, where higher values indicate abnormal energy system stress compared to typical market conditions.</p>

                <div class="idx-grid">
                    {cards_html}
                </div>

                <div class="idx-section">
                    <h2>Risk Level Bands Classification</h2>
                    <div class="idx-bands-visual">
                        <div class="idx-band-row idx-band-low">
                            <div class="idx-band-range">0 &ndash; 20</div>
                            <div class="idx-band-name">LOW</div>
                            <div class="idx-band-desc">Normal conditions &mdash; no significant stress detected</div>
                        </div>
                        <div class="idx-band-row idx-band-moderate">
                            <div class="idx-band-range">21 &ndash; 40</div>
                            <div class="idx-band-name">MODERATE</div>
                            <div class="idx-band-desc">Emerging pressure &mdash; early signals of structural stress</div>
                        </div>
                        <div class="idx-band-row idx-band-elevated">
                            <div class="idx-band-range">41 &ndash; 60</div>
                            <div class="idx-band-name">ELEVATED</div>
                            <div class="idx-band-desc">Active disruption risk &mdash; multiple stress vectors converging</div>
                        </div>
                        <div class="idx-band-row idx-band-severe">
                            <div class="idx-band-range">61 &ndash; 80</div>
                            <div class="idx-band-name">SEVERE</div>
                            <div class="idx-band-desc">High disruption pressure &mdash; significant market impact likely</div>
                        </div>
                        <div class="idx-band-row idx-band-critical">
                            <div class="idx-band-range">81 &ndash; 100</div>
                            <div class="idx-band-name">CRITICAL</div>
                            <div class="idx-band-desc">Extreme stress &mdash; systemic disruption in progress</div>
                        </div>
                    </div>
                </div>

                <div class="idx-section">
                    <h2>Latest Index Readings</h2>
                    <table class="idx-readings">
                        <thead>
                            <tr>
                                <th>Index</th>
                                <th>Value</th>
                                <th>Change</th>
                                <th>Band</th>
                                <th>Date</th>
                            </tr>
                        </thead>
                        <tbody>
                            {readings_rows}
                        </tbody>
                    </table>
                </div>

                <div class="idx-section">
                    <h2>Methodology Overview: How EnergyRiskIQ Risk Indices Work</h2>
                    <p>EnergyRiskIQ indices transform complex energy market signals into structured daily indicators.</p>
                    <p>Each index is built from three core components:</p>
                    <div class="idx-components">
                        <div class="idx-component">
                            <div class="idx-component-icon">&#x2694;&#xFE0F;</div>
                            <h3>Geopolitical Events</h3>
                            <p>Conflicts, sanctions, policy shifts and infrastructure incidents that disrupt energy supply chains.</p>
                        </div>
                        <div class="idx-component">
                            <div class="idx-component-icon">&#x1F4CA;</div>
                            <h3>Market Signals</h3>
                            <p>Price volatility, freight disruptions, and derivative market stress indicators.</p>
                        </div>
                        <div class="idx-component">
                            <div class="idx-component-icon">&#x26FD;</div>
                            <h3>Structural Indicators</h3>
                            <p>Storage levels, supply flows, seasonal demand pressure and logistics capacity constraints.</p>
                        </div>
                    </div>
                    <p style="margin-top: 1.25rem;">These signals are normalized into a 0&ndash;100 risk scale, where higher values indicate elevated escalation risk compared to normal market conditions.</p>
                </div>

                <div class="idx-section">
                    <h2>Latest Energy Risk Analysis</h2>
                    <p>Explore our latest intelligence and analysis on energy market risk.</p>
                    <ul class="idx-analysis-links">
                        <li><a href="/daily-geo-energy-intelligence-digest">Daily Geo-Energy Intelligence Digest</a></li>
                        <li><a href="/geri/methodology">GERI Methodology &amp; Construction</a></li>
                        <li><a href="/eeri/methodology">EERI Methodology &amp; Construction</a></li>
                        <li><a href="/egsi/methodology">EGSI Methodology &amp; Construction</a></li>
                        <li><a href="/alerts">Latest Energy Risk Alerts</a></li>
                        <li><a href="/blog">Energy Risk Blog &amp; Analysis</a></li>
                    </ul>
                </div>

                <div class="idx-cta-section">
                    <h2>Monitor Energy Risk in Real Time</h2>
                    <p>Professional dashboards provide live charts, correlation analysis, and escalation signals across all indices.</p>
                    <a href="/users" class="idx-cta-btn">Get FREE Access</a>
                </div>
            </div>
        </main>
        {render_digest_footer()}
    </body>
    </html>
    """
    return HTMLResponse(content=html, headers={"Cache-Control": "public, max-age=3600"})


def render_digest_footer() -> str:
    return """
    <footer>
        <div class="footer-inner">
            <div>&copy; 2026 EnergyRiskIQ. All rights reserved.</div>
            <div class="footer-links">
                <a href="/">Home</a>
                <a href="/indices">Indices</a>
                <a href="/alerts">Alerts</a>
                <a href="/daily-geo-energy-intelligence-digest">Digest</a>
                <a href="/sitemap.html">Sitemap</a>
                <a href="/privacy">Privacy</a>
                <a href="/terms">Terms</a>
            </div>
        </div>
    </footer>
    """


def render_digest_html(d: dict) -> str:
    import re as _re
    tone = d.get('risk_tone', {})
    tone_color = tone.get('color', 'gray')
    tone_icons = {'red': '&#x1F534;', 'orange': '&#x1F7E0;', 'yellow': '&#x1F7E1;', 'green': '&#x1F7E2;', 'gray': '&#x26AA;'}
    tone_icon = tone_icons.get(tone_color, '&#x26AA;')

    delay_badge = '<span class="digest-delayed-badge">24h Delayed (Free Plan)</span>' if d.get('is_delayed') else ''

    header_bar = f"""
    <div class="digest-header-bar">
        <div class="digest-date">
            <strong>Digest Date:</strong> {d.get('digest_date', '')} &nbsp;|&nbsp;
            <strong>Based on Alerts From:</strong> {d.get('alerts_date', '')} &nbsp;|&nbsp;
            <strong>Total Alerts:</strong> {d.get('total_alerts_yesterday', 0)}
        </div>
        {delay_badge}
    </div>
    """

    risk_tone_html = f"""
    <div class="digest-risk-tone tone-{tone_color}">
        <span style="font-size: 28px;">{tone_icon}</span>
        <div>
            <div class="tone-label">Global Risk Tone: {tone.get('tone', 'Unknown')}</div>
            <div style="color: #94a3b8; font-size: 12px; margin-top: 2px;">Based on {d.get('total_alerts_yesterday', 0)} alerts analyzed from {d.get('alerts_date', '')}</div>
        </div>
    </div>
    """

    geri = d.get('geri')
    index_cards = ''
    if geri:
        band_colors = {'CRITICAL': '#dc2626', 'SEVERE': '#ef4444', 'ELEVATED': '#f97316', 'MODERATE': '#eab308', 'LOW': '#22c55e'}
        color = band_colors.get(str(geri.get('band', '')), '#94a3b8')
        trend = geri.get('trend_1d', 0) or 0
        trend_class = 'up' if trend > 0 else 'down' if trend < 0 else 'flat'
        trend_arrow = '&#x2191;' if trend > 0 else '&#x2193;' if trend < 0 else '&#x2192;'
        trend_7d = geri.get('trend_7d', 0) or 0
        index_cards += f"""
        <div class="digest-index-card">
            <div class="index-name">GERI</div>
            <div class="index-value">{geri.get('value', 'N/A')}</div>
            <div class="index-band" style="background: {color}20; color: {color};">{geri.get('band', 'N/A')}</div>
            <div class="index-trend {trend_class}">{trend_arrow} {'+' if trend > 0 else ''}{trend} (1d) | {'+' if trend_7d > 0 else ''}{trend_7d} (7d)</div>
        </div>
        """

    index_cards += """
    <div class="digest-index-card" style="opacity: 0.5; position: relative;">
        <div class="index-name">EERI</div>
        <div class="index-value" style="filter: blur(4px);">--</div>
        <div style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); background: rgba(0,0,0,0.7); padding: 4px 10px; border-radius: 6px; font-size: 11px; color: #60a5fa;">Personal+</div>
    </div>
    <div class="digest-index-card" style="opacity: 0.5; position: relative;">
        <div class="index-name">EGSI-M</div>
        <div class="index-value" style="filter: blur(4px);">--</div>
        <div style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); background: rgba(0,0,0,0.7); padding: 4px 10px; border-radius: 6px; font-size: 11px; color: #60a5fa;">Personal+</div>
    </div>
    """

    index_summary = f"""
    <div class="digest-card">
        <div class="digest-card-header">
            <span class="digest-section-icon">&#x1F4CA;</span>
            <h3>Index Movement Summary</h3>
        </div>
        <div class="digest-card-body">
            <div class="digest-index-grid">{index_cards}</div>
        </div>
    </div>
    """

    asset_changes = d.get('asset_changes', {})
    asset_items = ''
    for key, data in asset_changes.items():
        label = data.get('label', key)
        value = data.get('current', 0)
        change_text = ''
        change_class = 'neutral'
        if 'change_pct' in data:
            pct = data['change_pct']
            change_text = f"{'+'if pct > 0 else ''}{pct:.2f}%"
            if key in ('vix', 'storage'):
                change_class = 'negative' if pct > 0 else 'positive' if pct < 0 else 'neutral'
            else:
                change_class = 'positive' if pct > 0 else 'negative' if pct < 0 else 'neutral'
        elif 'change_delta' in data:
            delta = data['change_delta']
            change_text = f"{'+'if delta > 0 else ''}{delta}"
            if key == 'vix':
                change_class = 'negative' if delta > 0 else 'positive' if delta < 0 else 'neutral'
            elif key == 'storage':
                change_class = 'negative' if delta < 0 else 'positive' if delta > 0 else 'neutral'
            else:
                change_class = 'positive' if delta > 0 else 'negative' if delta < 0 else 'neutral'

        if key == 'eurusd':
            display_val = f"{value:.4f}"
        elif key == 'storage':
            display_val = f"{value}%"
        elif key in ('brent', 'ttf'):
            display_val = f"${value:.2f}"
        else:
            display_val = f"{value:.2f}" if isinstance(value, float) else str(value)

        asset_items += f"""
        <div class="digest-asset-item">
            <div class="asset-label">{label}</div>
            <div class="asset-value">{display_val}</div>
            <div class="asset-change {change_class}">{change_text}</div>
        </div>
        """

    asset_section = ''
    if asset_items:
        asset_section = f"""
        <div class="digest-card">
            <div class="digest-card-header">
                <span class="digest-section-icon">&#x1F4B9;</span>
                <h3>Market Reaction (24h)</h3>
            </div>
            <div class="digest-card-body">
                <div class="digest-asset-grid">{asset_items}</div>
            </div>
        </div>
        """

    alerts_list = d.get('alerts', [])
    alerts_items = ''
    for a in alerts_list:
        sev = a.get('severity', 0)
        conf = a.get('confidence', 0)
        conf_str = f"{conf * 100:.0f}%" if conf else ''
        alerts_items += f"""
        <div class="digest-alert-item">
            <div class="alert-headline">
                <span class="digest-severity-dot sev-{sev}"></span>
                {a.get('headline', '')}
            </div>
            <div class="alert-meta">
                <span>Region: {a.get('region', 'N/A')}</span>
                <span>Severity: {sev}/5</span>
                <span>Category: {a.get('category', 'N/A')}</span>
                {'<span>Confidence: ' + conf_str + '</span>' if conf_str else ''}
            </div>
        </div>
        """

    more_note = ''

    alerts_section = ''
    if alerts_items:
        alerts_section = f"""
        <div class="digest-card">
            <div class="digest-card-header">
                <span class="digest-section-icon">&#x26A0;&#xFE0F;</span>
                <h3>Top Risk Events ({len(alerts_list)})</h3>
            </div>
            <div class="digest-card-body">
                {alerts_items}
                {more_note}
            </div>
        </div>
        """

    narrative = d.get('ai_narrative', '')
    narrative_html = ''
    if narrative:
        rendered = narrative
        rendered = _re.sub(r'## (.*)', r'<h2>\1</h2>', rendered)
        rendered = _re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', rendered)
        rendered = _re.sub(r'^- (.*)', r'<li>\1</li>', rendered, flags=_re.MULTILINE)
        rendered = _re.sub(r'^\* (.*)', r'<li>\1</li>', rendered, flags=_re.MULTILINE)
        rendered = _re.sub(r'(<li>.*?</li>)', lambda m: '<ul>' + m.group(0) + '</ul>', rendered, flags=_re.DOTALL)
        rendered = rendered.replace('</ul>\n<ul>', '\n')
        rendered = rendered.replace('\n\n', '<br><br>')
        rendered = rendered.replace('\n', '<br>')

        narrative_html = f"""
        <div class="digest-card">
            <div class="digest-card-header">
                <span class="digest-section-icon">&#x1F9E0;</span>
                <h3>Executive Intelligence Brief</h3>
                <span style="background: rgba(59,130,246,0.2); color: #60a5fa; font-size: 10px; padding: 2px 8px; border-radius: 4px; margin-left: auto;">AI-Generated</span>
            </div>
            <div class="digest-card-body">
                <div class="digest-narrative">{rendered}</div>
            </div>
        </div>
        """

    disclaimer = """
    <div style="text-align: center; padding: 12px; color: #64748b; font-size: 11px; margin-top: 8px;">
        Informational only. Not financial advice. | EnergyRiskIQ Intelligence Engine
    </div>
    """

    return header_bar + risk_tone_html + index_summary + asset_section + alerts_section + narrative_html + disclaimer


@router.get("/daily-geo-energy-intelligence-digest/history", response_class=HTMLResponse)
async def digest_history_page():
    pages = get_recent_public_digest_pages(limit=90)

    pages_html = ""
    for p in pages:
        page_date = p['page_date']
        if isinstance(page_date, str):
            page_date_obj = datetime.fromisoformat(page_date).date()
        else:
            page_date_obj = page_date
        date_display = page_date_obj.strftime("%B %d, %Y")
        pages_html += f"""
        <li>
            <a href="/daily-geo-energy-intelligence-digest/{page_date_obj.isoformat()}">
                <span class="date">{date_display}</span>
            </a>
        </li>
        """

    if not pages_html:
        pages_html = '<li style="color: #94a3b8; padding: 1rem;">No digest pages available yet.</li>'

    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Daily Geo-Energy Intelligence Digest - History | EnergyRiskIQ</title>
        <meta name="description" content="Browse the archive of daily geo-energy risk intelligence digests from EnergyRiskIQ. Free GERI index data, market reactions, and AI risk analysis.">
        <link rel="canonical" href="{BASE_URL}/daily-geo-energy-intelligence-digest/history">
        <meta property="og:title" content="Daily Geo-Energy Intelligence Digest - History | EnergyRiskIQ">
        <meta property="og:description" content="Browse the archive of daily geo-energy risk intelligence digests.">
        <meta property="og:type" content="website">
        <meta property="og:url" content="{BASE_URL}/daily-geo-energy-intelligence-digest/history">
        <link rel="icon" type="image/png" href="/static/favicon.png">
        {get_digest_dark_styles()}
    </head>
    <body>
        {render_digest_nav()}
        <main>
            <div class="container">
                <div class="breadcrumbs">
                    <a href="/">Home</a> / <a href="/daily-geo-energy-intelligence-digest">Digest</a> / History
                </div>
                <h1 style="font-size: 1.75rem; margin-bottom: 0.5rem; color: #f1f5f9;">Daily Geo-Energy Intelligence Digest Archive</h1>
                <p style="color: #94a3b8; margin-bottom: 2rem;">Browse past daily intelligence digests with GERI index movements, market reactions, and AI-generated risk analysis.</p>
                <ul class="page-list">
                    {pages_html}
                </ul>
            </div>
        </main>
        {render_digest_footer()}
    </body>
    </html>
    """

    return HTMLResponse(content=html, headers={"Cache-Control": "no-cache"})


@router.get("/daily-geo-energy-intelligence-digest/{date_str}", response_class=HTMLResponse)
async def digest_date_page(date_str: str):
    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        raise HTTPException(status_code=404, detail="Invalid date format")

    page = get_public_digest_page(target_date)
    if not page or not page.get('model'):
        raise HTTPException(status_code=404, detail="Digest page not found for this date")

    d = page['model']
    formatted_date = target_date.strftime("%B %d, %Y")
    seo_title = d.get('seo_title', f"Daily Geo-Energy Intelligence Digest - {formatted_date} | EnergyRiskIQ")
    seo_desc = d.get('seo_description', f"Free daily geo-energy risk intelligence digest for {formatted_date}.")

    prev_date = (target_date - timedelta(days=1)).isoformat()
    next_date = (target_date + timedelta(days=1))
    today = date.today()
    next_link = ''
    if next_date < today:
        next_link = f'<a href="/daily-geo-energy-intelligence-digest/{next_date.isoformat()}">Next Day &rarr;</a>'
    prev_link = f'<a href="/daily-geo-energy-intelligence-digest/{prev_date}">&larr; Previous Day</a>'

    digest_body = render_digest_html(d)

    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{seo_title}</title>
        <meta name="description" content="{seo_desc}">
        <link rel="canonical" href="{BASE_URL}/daily-geo-energy-intelligence-digest/{date_str}">
        <meta property="og:title" content="{seo_title}">
        <meta property="og:description" content="{seo_desc}">
        <meta property="og:type" content="article">
        <meta property="og:url" content="{BASE_URL}/daily-geo-energy-intelligence-digest/{date_str}">
        <link rel="icon" type="image/png" href="/static/favicon.png">
        {get_digest_dark_styles()}
    </head>
    <body>
        {render_digest_nav()}
        <main>
            <div class="container">
                <div class="breadcrumbs">
                    <a href="/">Home</a> / <a href="/daily-geo-energy-intelligence-digest">Digest</a> / {formatted_date}
                </div>
                <h1 style="font-size: 1.5rem; margin-bottom: 1rem; color: #f1f5f9;">Daily Geo-Energy Intelligence Digest - {formatted_date}</h1>
                {digest_body}
                <div class="digest-nav-pagination">
                    {prev_link}
                    {next_link}
                </div>
            </div>
        </main>
        {render_digest_footer()}
    </body>
    </html>
    """

    return HTMLResponse(content=html, headers={"Cache-Control": "no-cache"})


@router.get("/daily-geo-energy-intelligence-digest", response_class=HTMLResponse)
async def digest_latest_page():
    pages = get_recent_public_digest_pages(limit=1)
    if pages:
        page_date = pages[0]['page_date']
        if isinstance(page_date, str):
            date_str = page_date[:10]
        else:
            date_str = page_date.isoformat()
        return await digest_date_page(date_str)

    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Daily Geo-Energy Intelligence Digest | EnergyRiskIQ</title>
        <meta name="description" content="Daily geo-energy risk intelligence digest with GERI index, market reactions, and AI analysis. Free from EnergyRiskIQ.">
        <link rel="canonical" href="{BASE_URL}/daily-geo-energy-intelligence-digest">
        <link rel="icon" type="image/png" href="/static/favicon.png">
        {get_digest_dark_styles()}
    </head>
    <body>
        {render_digest_nav()}
        <main>
            <div class="container" style="text-align: center; padding: 4rem 1rem;">
                <h1 style="font-size: 1.75rem; color: #f1f5f9; margin-bottom: 1rem;">Daily Geo-Energy Intelligence Digest</h1>
                <p style="color: #94a3b8; margin-bottom: 2rem;">No digest pages have been generated yet. Check back soon.</p>
                <a href="/users" class="cta-btn-nav" style="display: inline-block; padding: 12px 32px; font-size: 16px;">Get Real-Time Alerts</a>
            </div>
        </main>
        {render_digest_footer()}
    </body>
    </html>
    """

    return HTMLResponse(content=html, headers={"Cache-Control": "no-cache"})


@router.get("/research/global-energy-risk-index", response_class=HTMLResponse)
async def geri_research_page(request: Request):
    """
    GERI Research Page - Deep-dive asset page for the Global Energy Risk Index.
    Built incrementally section by section.
    """
    import json as _json
    from datetime import date as _date

    # ── GERI Live: daily max per day for case study window ────────────────────
    _geri_rows = execute_query("""
        SELECT computed_at::date AS d, MAX(value) AS v
        FROM geri_live
        WHERE computed_at::date BETWEEN '2026-02-25' AND '2026-03-04'
        GROUP BY computed_at::date
        ORDER BY computed_at::date
    """)
    _geri_by_date = {str(r['d']): float(r['v']) for r in _geri_rows} if _geri_rows else {}

    # ── Brent: daily close for case study window ───────────────────────────────
    _brent_rows = execute_query("""
        SELECT date, brent_price
        FROM oil_price_snapshots
        WHERE date BETWEEN '2026-02-25' AND '2026-03-04'
        ORDER BY date
    """)
    _brent_by_date = {str(r['date']): float(r['brent_price']) for r in _brent_rows} if _brent_rows else {}

    # ── VIX: market-day close for case study window ───────────────────────────
    _vix_rows = execute_query("""
        SELECT date, vix_close
        FROM vix_snapshots
        WHERE date BETWEEN '2026-02-25' AND '2026-03-04'
        ORDER BY date
    """)
    _vix_by_date = {str(r['date']): float(r['vix_close']) for r in _vix_rows} if _vix_rows else {}

    # ── Build GERI chart arrays (all 8 dates, null for missing) ───────────────
    _all_dates = ['2026-02-25','2026-02-26','2026-02-27','2026-02-28',
                  '2026-03-01','2026-03-02','2026-03-03','2026-03-04']
    _event_date = '2026-02-28'
    _geri_labels_py = []
    _geri_data_py   = []
    for _d in _all_dates:
        _mo, _dy = _d[5:7], _d[8:]
        _lbl_base = f"Feb {int(_dy)}" if _mo == '02' else f"Mar {int(_dy)}"
        _lbl = _lbl_base + ' ★' if _d == _event_date else _lbl_base
        _geri_labels_py.append(_lbl)
        _geri_data_py.append(_geri_by_date.get(_d))  # None → JS null

    _geri_event_idx = _all_dates.index(_event_date)

    # ── Build Brent chart arrays (dates that exist in DB) ─────────────────────
    _brent_labels_py = []
    _brent_data_py   = []
    _brent_surge_idx = 0
    for _i, _d in enumerate(_all_dates):
        if _d in _brent_by_date:
            _mo, _dy = _d[5:7], _d[8:]
            _lbl_base = f"Feb {int(_dy)}" if _mo == '02' else f"Mar {int(_dy)}"
            _lbl = _lbl_base + ' ★' if _d == _event_date else _lbl_base
            _brent_labels_py.append(_lbl)
            _brent_data_py.append(_brent_by_date[_d])
    # Surge point = highest Brent value
    if _brent_data_py:
        _brent_surge_idx = _brent_data_py.index(max(_brent_data_py))

    # ── Build VIX chart arrays (market days only) ──────────────────────────────
    _vix_labels_py = []
    _vix_data_py   = []
    for _d in _all_dates:
        if _d in _vix_by_date:
            _mo, _dy = _d[5:7], _d[8:]
            _lbl_base = f"Feb {int(_dy)}" if _mo == '02' else f"Mar {int(_dy)}"
            _vix_labels_py.append(_lbl_base)
            _vix_data_py.append(_vix_by_date[_d])
    _vix_surge_idx = len(_vix_data_py) - 1 if _vix_data_py else 0

    # ── Serialise to JSON for embedding ───────────────────────────────────────
    _geri_labels_js = _json.dumps(_geri_labels_py)
    _geri_data_js   = _json.dumps(_geri_data_py)
    _brent_labels_js = _json.dumps(_brent_labels_py)
    _brent_data_js   = _json.dumps(_brent_data_py)
    _vix_labels_js   = _json.dumps(_vix_labels_py)
    _vix_data_js     = _json.dumps(_vix_data_py)

    # ── Y-axis ranges (calculated from real data) ──────────────────────────────
    _brent_min = int(min(_brent_data_py) - 1) if _brent_data_py else 68
    _brent_max = int(max(_brent_data_py) + 2) if _brent_data_py else 80
    _vix_min   = int(min(_vix_data_py) - 1) if _vix_data_py else 16
    _vix_max   = int(max(_vix_data_py) + 2) if _vix_data_py else 24

    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Global Energy Risk Index (GERI) Research | EnergyRiskIQ</title>
        <meta name="description" content="The Global Energy Risk Index (GERI) is a quantitative framework measuring abnormal geopolitical and systemic risk in global energy markets. Research methodology, construction, and interpretation.">
        <link rel="canonical" href="{BASE_URL}/research/global-energy-risk-index">

        <meta property="og:title" content="Global Energy Risk Index (GERI) Research | EnergyRiskIQ">
        <meta property="og:description" content="A quantitative framework measuring abnormal geopolitical and systemic risk in global energy markets.">
        <meta property="og:url" content="{BASE_URL}/research/global-energy-risk-index">
        <meta property="og:type" content="article">

        <link rel="icon" type="image/png" href="/static/favicon.png">
        <script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
        {get_digest_dark_styles()}
        <style>
            .research-hero {{
                text-align: center;
                padding: 2.5rem 0 1.5rem 0;
            }}
            .research-hero h1 {{
                font-size: 1.85rem;
                margin-bottom: 0.75rem;
                color: #f1f5f9;
                font-weight: 700;
                letter-spacing: -0.01em;
            }}
            .research-hero .subtitle {{
                color: #94a3b8;
                max-width: 640px;
                margin: 0 auto;
                font-size: 1rem;
                line-height: 1.65;
                font-style: italic;
            }}
            .research-section {{
                background: #1e293b;
                border: 1px solid #334155;
                border-radius: 12px;
                padding: 1.5rem 1.75rem;
                margin: 1.5rem 0;
            }}
            .research-section h2 {{
                font-size: 1.1rem;
                font-weight: 600;
                color: #f1f5f9;
                margin: 0 0 1rem 0;
            }}
            .research-section p {{
                color: #cbd5e1;
                font-size: 0.92rem;
                line-height: 1.7;
                margin: 0 0 1rem 0;
            }}
            .research-section p:last-child {{
                margin-bottom: 0;
            }}
            .pipeline-visual {{
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 0;
                margin: 1.75rem 0 1rem 0;
                flex-wrap: wrap;
            }}
            .pipeline-step {{
                display: flex;
                flex-direction: column;
                align-items: center;
                text-align: center;
                padding: 1rem 1.25rem;
                background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
                border: 1px solid #334155;
                border-radius: 10px;
                min-width: 145px;
                max-width: 180px;
                flex: 1;
            }}
            .pipeline-step .step-icon {{
                font-size: 1.5rem;
                margin-bottom: 0.5rem;
            }}
            .pipeline-step .step-label {{
                color: #f1f5f9;
                font-weight: 600;
                font-size: 0.88rem;
                margin-bottom: 0.3rem;
            }}
            .pipeline-step .step-desc {{
                color: #64748b;
                font-size: 0.75rem;
                line-height: 1.4;
            }}
            .pipeline-arrow {{
                color: #3b82f6;
                font-size: 1.35rem;
                padding: 0 0.5rem;
                flex-shrink: 0;
            }}
            .measures-subsection {{
                margin: 1.5rem 0;
                padding: 1.25rem;
                background: #0f172a;
                border: 1px solid #1e293b;
                border-radius: 10px;
            }}
            .measures-subsection h3 {{
                font-size: 0.95rem;
                font-weight: 600;
                color: #e2e8f0;
                margin: 0 0 0.75rem 0;
            }}
            .measures-subsection p {{
                color: #94a3b8;
                font-size: 0.88rem;
                line-height: 1.65;
                margin: 0 0 0.75rem 0;
            }}
            .measures-subsection p:last-child {{
                margin-bottom: 0;
            }}
            .measures-examples {{
                display: flex;
                flex-wrap: wrap;
                gap: 0.45rem;
                margin: 0.75rem 0;
            }}
            .measure-tag {{
                background: #1e293b;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 0.4rem 0.7rem;
                font-size: 0.78rem;
                color: #cbd5e1;
                white-space: nowrap;
            }}
            .four-pillars-visual {{
                display: grid;
                grid-template-columns: repeat(4, 1fr);
                gap: 0.75rem;
                margin: 1.75rem 0 0.5rem 0;
            }}
            .pillar-card {{
                background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
                border: 1px solid #334155;
                border-radius: 10px;
                padding: 1rem;
                text-align: center;
            }}
            .pillar-weight {{
                font-size: 1.5rem;
                font-weight: 700;
                color: #f1f5f9;
                margin-bottom: 0.3rem;
            }}
            .pillar-name {{
                color: #e2e8f0;
                font-weight: 600;
                font-size: 0.82rem;
                margin-bottom: 0.35rem;
            }}
            .pillar-desc {{
                color: #64748b;
                font-size: 0.7rem;
                line-height: 1.4;
            }}
            .method-step {{
                display: flex;
                gap: 1rem;
                margin: 1.25rem 0;
                padding: 1.25rem;
                background: #0f172a;
                border: 1px solid #1e293b;
                border-radius: 10px;
            }}
            .method-step-num {{
                flex-shrink: 0;
                width: 36px;
                height: 36px;
                background: linear-gradient(135deg, #1e3a5f 0%, #0f172a 100%);
                border: 1px solid #3b82f6;
                border-radius: 8px;
                display: flex;
                align-items: center;
                justify-content: center;
                color: #60a5fa;
                font-weight: 700;
                font-size: 0.85rem;
            }}
            .method-step-content h3 {{
                font-size: 0.95rem;
                font-weight: 600;
                color: #e2e8f0;
                margin: 0 0 0.6rem 0;
            }}
            .method-step-content p {{
                color: #94a3b8;
                font-size: 0.88rem;
                line-height: 1.65;
                margin: 0 0 0.6rem 0;
            }}
            .method-step-content p:last-child {{
                margin-bottom: 0;
            }}
            .regime-table {{
                width: 100%;
                border-collapse: collapse;
                margin: 1rem 0;
            }}
            .regime-table th {{
                text-align: left;
                padding: 0.6rem 0.75rem;
                font-size: 0.78rem;
                color: #94a3b8;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.05em;
                border-bottom: 2px solid #334155;
            }}
            .regime-table td {{
                padding: 0.6rem 0.75rem;
                font-size: 0.85rem;
                border-bottom: 1px solid #1e293b;
            }}
            .regime-table tr:last-child td {{
                border-bottom: none;
            }}
            .regime-table td:first-child {{
                font-weight: 600;
                white-space: nowrap;
            }}
            .regime-table td:nth-child(2) {{
                color: #e2e8f0;
                font-weight: 600;
            }}
            .regime-table td:nth-child(3) {{
                color: #94a3b8;
            }}
            .regime-band-dot {{
                display: inline-block;
                width: 10px;
                height: 10px;
                border-radius: 50%;
                margin-right: 0.4rem;
                vertical-align: middle;
            }}
            .source-tiers {{
                display: grid;
                grid-template-columns: repeat(2, 1fr);
                gap: 0.5rem;
                margin: 0.75rem 0;
            }}
            .source-tier {{
                background: #1e293b;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 0.5rem 0.7rem;
                font-size: 0.78rem;
            }}
            .source-tier .tier-label {{
                color: #60a5fa;
                font-weight: 600;
                font-size: 0.72rem;
                text-transform: uppercase;
                margin-bottom: 0.2rem;
            }}
            .source-tier .tier-desc {{
                color: #cbd5e1;
            }}
            .use-cases-grid {{
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 0.75rem;
                margin: 1.25rem 0;
            }}
            .use-case-card {{
                background: #0f172a;
                border: 1px solid #1e293b;
                border-radius: 10px;
                padding: 1.1rem;
            }}
            .use-case-card .uc-icon {{
                font-size: 1.3rem;
                margin-bottom: 0.5rem;
            }}
            .use-case-card .uc-title {{
                color: #e2e8f0;
                font-weight: 600;
                font-size: 0.88rem;
                margin-bottom: 0.5rem;
            }}
            .use-case-card .uc-list {{
                list-style: none;
                padding: 0;
                margin: 0;
            }}
            .use-case-card .uc-list li {{
                color: #94a3b8;
                font-size: 0.8rem;
                line-height: 1.5;
                padding: 0.2rem 0;
                padding-left: 0.9rem;
                position: relative;
            }}
            .use-case-card .uc-list li::before {{
                content: "—";
                position: absolute;
                left: 0;
                color: #475569;
            }}
            .callout-box {{
                background: rgba(59,130,246,0.08);
                border-left: 3px solid #3b82f6;
                padding: 0.85rem 1rem;
                border-radius: 0 8px 8px 0;
                margin: 1.25rem 0;
            }}
            .callout-box p {{
                color: #e2e8f0;
                font-size: 0.9rem;
                line-height: 1.65;
                margin: 0;
                font-weight: 500;
            }}
            .cross-ref-grid {{
                display: grid;
                grid-template-columns: repeat(2, 1fr);
                gap: 0.5rem;
                margin: 1rem 0;
            }}
            .cross-ref-item {{
                background: #1e293b;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 0.55rem 0.75rem;
            }}
            .cross-ref-item .cr-pair {{
                color: #60a5fa;
                font-weight: 600;
                font-size: 0.78rem;
                margin-bottom: 0.15rem;
            }}
            .cross-ref-item .cr-desc {{
                color: #94a3b8;
                font-size: 0.73rem;
                line-height: 1.4;
            }}
            .case-study {{
                background: #0f172a;
                border: 1px solid #1e293b;
                border-radius: 12px;
                padding: 1.5rem;
                margin: 1.5rem 0;
            }}
            .case-study-header {{
                display: flex;
                align-items: flex-start;
                gap: 1rem;
                margin-bottom: 1rem;
            }}
            .case-study-badge {{
                flex-shrink: 0;
                background: #1e293b;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 0.5rem 0.75rem;
                text-align: center;
                min-width: 64px;
            }}
            .case-study-badge .badge-icon {{
                font-size: 1.1rem;
            }}
            .case-study-badge .badge-label {{
                font-size: 0.62rem;
                color: #64748b;
                text-transform: uppercase;
                letter-spacing: 0.05em;
                margin-top: 0.15rem;
            }}
            .case-study-title {{
                flex: 1;
            }}
            .case-study-title h3 {{
                font-size: 1rem;
                font-weight: 600;
                color: #f1f5f9;
                margin: 0 0 0.25rem 0;
            }}
            .case-study-title .cs-date {{
                color: #64748b;
                font-size: 0.78rem;
            }}
            .case-study-body p {{
                color: #94a3b8;
                font-size: 0.87rem;
                line-height: 1.7;
                margin: 0 0 1rem 0;
            }}
            .case-study-body p:last-child {{
                margin-bottom: 0;
            }}
            .cs-metrics-row {{
                display: flex;
                gap: 0.6rem;
                margin: 1rem 0;
                flex-wrap: wrap;
            }}
            .cs-metric {{
                background: #1e293b;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 0.6rem 0.85rem;
                flex: 1;
                min-width: 120px;
                text-align: center;
            }}
            .cs-metric .cm-label {{
                color: #64748b;
                font-size: 0.68rem;
                text-transform: uppercase;
                letter-spacing: 0.04em;
                margin-bottom: 0.25rem;
            }}
            .cs-metric .cm-value {{
                color: #f1f5f9;
                font-size: 1.05rem;
                font-weight: 700;
            }}
            .cs-metric .cm-sub {{
                color: #94a3b8;
                font-size: 0.68rem;
                margin-top: 0.15rem;
            }}
            .cs-bar-chart {{
                margin: 1rem 0;
            }}
            .cs-bar-chart .bar-title {{
                color: #64748b;
                font-size: 0.72rem;
                text-transform: uppercase;
                letter-spacing: 0.04em;
                margin-bottom: 0.6rem;
            }}
            .cs-bar-row {{
                display: flex;
                align-items: center;
                gap: 0.6rem;
                margin-bottom: 0.45rem;
            }}
            .cs-bar-label {{
                color: #94a3b8;
                font-size: 0.72rem;
                white-space: nowrap;
                width: 70px;
                text-align: right;
                flex-shrink: 0;
            }}
            .cs-bar-track {{
                flex: 1;
                background: #1e293b;
                border-radius: 3px;
                height: 14px;
                position: relative;
                overflow: hidden;
            }}
            .cs-bar-fill {{
                height: 100%;
                border-radius: 3px;
                transition: width 0.3s ease;
            }}
            .cs-bar-val {{
                color: #e2e8f0;
                font-size: 0.72rem;
                font-weight: 600;
                width: 55px;
                flex-shrink: 0;
            }}
            .cs-events-list {{
                margin: 1rem 0;
            }}
            .cs-events-list .ev-item {{
                display: flex;
                align-items: flex-start;
                gap: 0.6rem;
                padding: 0.4rem 0;
                border-bottom: 1px solid #1e293b;
                font-size: 0.78rem;
            }}
            .cs-events-list .ev-item:last-child {{ border-bottom: none; }}
            .cs-events-list .ev-sev {{
                flex-shrink: 0;
                background: #ef4444;
                color: white;
                font-size: 0.65rem;
                font-weight: 700;
                border-radius: 4px;
                padding: 0.15rem 0.35rem;
                margin-top: 0.1rem;
            }}
            .cs-events-list .ev-text {{ color: #cbd5e1; line-height: 1.4; }}
            @media (max-width: 768px) {{
                .four-pillars-visual {{ grid-template-columns: repeat(2, 1fr); }}
                .measure-tag {{ font-size: 0.74rem; }}
                .method-step {{ flex-direction: column; gap: 0.5rem; }}
                .source-tiers {{ grid-template-columns: 1fr; }}
                .use-cases-grid {{ grid-template-columns: 1fr; }}
                .cross-ref-grid {{ grid-template-columns: 1fr; }}
                .cs-metrics-row {{ gap: 0.4rem; }}
                .cs-metric {{ min-width: 90px; }}
            }}
            .risk-drivers-grid {{
                display: flex;
                flex-wrap: wrap;
                gap: 0.5rem;
                margin: 1.25rem 0;
                justify-content: center;
            }}
            .risk-driver-tag {{
                background: #0f172a;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 0.5rem 0.85rem;
                font-size: 0.82rem;
                color: #e2e8f0;
                font-weight: 500;
                white-space: nowrap;
            }}
            .risk-lag-visual {{
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 0;
                margin: 1.75rem 0 0.75rem 0;
                flex-wrap: wrap;
            }}
            .lag-phase {{
                text-align: center;
                padding: 1.1rem 1.25rem;
                border-radius: 10px;
                min-width: 160px;
                max-width: 210px;
                flex: 1;
            }}
            .lag-buildup {{
                background: linear-gradient(135deg, #1e3a5f 0%, #0f172a 100%);
                border: 1px solid #3b82f6;
            }}
            .lag-reaction {{
                background: linear-gradient(135deg, #3b1a1a 0%, #0f172a 100%);
                border: 1px solid #ef4444;
            }}
            .lag-icon {{
                font-size: 1.4rem;
                margin-bottom: 0.4rem;
            }}
            .lag-label {{
                color: #f1f5f9;
                font-weight: 600;
                font-size: 0.88rem;
                margin-bottom: 0.3rem;
            }}
            .lag-desc {{
                color: #94a3b8;
                font-size: 0.73rem;
                line-height: 1.4;
            }}
            .lag-connector {{
                display: flex;
                align-items: center;
                gap: 0.4rem;
                padding: 0 0.6rem;
                flex-shrink: 0;
            }}
            .lag-connector-line {{
                width: 28px;
                height: 2px;
                background: repeating-linear-gradient(90deg, #475569 0px, #475569 4px, transparent 4px, transparent 8px);
            }}
            .lag-connector-text {{
                color: #94a3b8;
                font-size: 0.7rem;
                font-style: italic;
                white-space: nowrap;
            }}
            @media (max-width: 768px) {{
                .lag-connector {{ display: none; }}
                .lag-phase {{ min-width: 100%; max-width: 100%; margin-bottom: 0.5rem; }}
                .risk-lag-visual {{ gap: 0.5rem; }}
            }}
            .quick-facts {{
                background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
                border: 1px solid #334155;
                border-radius: 12px;
                padding: 1.5rem 1.75rem;
                margin: 1.5rem 0;
            }}
            .quick-facts h2 {{
                font-size: 1.1rem;
                font-weight: 600;
                color: #f1f5f9;
                margin: 0 0 1rem 0;
                display: flex;
                align-items: center;
                gap: 0.5rem;
            }}
            .quick-facts table {{
                width: 100%;
                border-collapse: collapse;
            }}
            .quick-facts tr {{
                border-bottom: 1px solid #334155;
            }}
            .quick-facts tr:last-child {{
                border-bottom: none;
            }}
            .quick-facts td {{
                padding: 0.6rem 0.5rem;
                font-size: 0.88rem;
                vertical-align: middle;
            }}
            .quick-facts td:first-child {{
                color: #94a3b8;
                font-weight: 500;
                white-space: nowrap;
                width: 40%;
            }}
            .quick-facts td:last-child {{
                color: #f1f5f9;
                font-weight: 600;
            }}
            @media (max-width: 768px) {{
                .research-hero h1 {{ font-size: 1.4rem; }}
                .research-hero .subtitle {{ font-size: 0.9rem; }}
                .research-section {{ padding: 1.25rem 1rem; }}
                .quick-facts {{ padding: 1.25rem 1rem; }}
                .pipeline-visual {{ gap: 0.5rem; }}
                .pipeline-arrow {{ display: none; }}
                .pipeline-step {{ min-width: 100%; max-width: 100%; }}
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
                    <a href="/">Home</a> / <a href="/indices">Indices</a> / <a href="/indices/global-energy-risk-index">GERI</a> / Research
                </div>

                <div class="research-hero">
                    <h1>Global Energy Risk Index (GERI)</h1>
                    <p class="subtitle">&ldquo;A quantitative framework measuring abnormal geopolitical and systemic risk in global energy markets.&rdquo;</p>
                </div>

                <div class="research-section">
                    <h2>Introduction</h2>

                    <p>The Global Energy Risk Index (GERI) is a daily indicator developed by EnergyRiskIQ to measure abnormal geopolitical and systemic stress in global energy markets.</p>

                    <p>The index converts complex energy events &mdash; including supply disruptions, geopolitical escalation, market volatility, and policy shocks &mdash; into a normalized 0&ndash;100 risk score.</p>

                    <p>GERI helps traders, analysts, and policymakers understand when energy markets are operating in a normal environment versus a high-risk regime.</p>

                    <div class="pipeline-visual">
                        <div class="pipeline-step">
                            <div class="step-icon">&#x1F4E1;</div>
                            <div class="step-label">Energy Events</div>
                            <div class="step-desc">Supply disruptions, geopolitical escalation, policy shocks</div>
                        </div>
                        <div class="pipeline-arrow">&#x27A1;&#xFE0F;</div>
                        <div class="pipeline-step">
                            <div class="step-icon">&#x26A0;&#xFE0F;</div>
                            <div class="step-label">Risk Environment</div>
                            <div class="step-desc">AI classification, severity scoring, regional mapping</div>
                        </div>
                        <div class="pipeline-arrow">&#x27A1;&#xFE0F;</div>
                        <div class="pipeline-step">
                            <div class="step-icon">&#x1F4C8;</div>
                            <div class="step-label">Market Reaction</div>
                            <div class="step-desc">Normalized 0&ndash;100 risk score for energy markets</div>
                        </div>
                    </div>
                </div>

                <div class="quick-facts">
                    <h2>&#x1F4CB; GERI Quick Facts</h2>
                    <table>
                        <tr><td>Index Type</td><td>Global Energy Risk Indicator</td></tr>
                        <tr><td>Frequency</td><td>Daily</td></tr>
                        <tr><td>Scale</td><td>0 &ndash; 100</td></tr>
                        <tr><td>Coverage</td><td>Oil, LNG, gas flows, geopolitics</td></tr>
                        <tr><td>Developed by</td><td>EnergyRiskIQ</td></tr>
                        <tr><td>First Published</td><td>January 2025</td></tr>
                    </table>
                </div>

                <div class="research-section">
                    <h2>Why Prices Alone Cannot Measure Energy Risk</h2>

                    <p>Energy markets are not driven by supply and demand alone. Beneath every price movement lies a web of interconnected risk factors that traditional market data struggles to capture:</p>

                    <div class="risk-drivers-grid">
                        <div class="risk-driver-tag">&#x1F30D; Geopolitics</div>
                        <div class="risk-driver-tag">&#x1F6E2;&#xFE0F; Supply Chains</div>
                        <div class="risk-driver-tag">&#x1F3ED; Infrastructure Vulnerabilities</div>
                        <div class="risk-driver-tag">&#x1F6AB; Sanctions</div>
                        <div class="risk-driver-tag">&#x2693; Maritime Risks</div>
                        <div class="risk-driver-tag">&#x1F4E6; Storage Levels</div>
                        <div class="risk-driver-tag">&#x1F4B1; Currency Dynamics</div>
                    </div>

                    <p>These forces shape the risk environment continuously &mdash; but prices only react <em>after</em> risk materializes. By the time a supply disruption or geopolitical escalation is priced in, the opportunity to anticipate it has already passed.</p>

                    <p>A risk index aims to measure the environment <strong>before</strong> markets fully adjust &mdash; capturing the buildup of stress that precedes price moves.</p>

                    <div class="risk-lag-visual">
                        <div class="lag-phase lag-buildup">
                            <div class="lag-icon">&#x1F50D;</div>
                            <div class="lag-label">Risk Buildup</div>
                            <div class="lag-desc">Geopolitical tensions, supply threats, sanctions &mdash; stress accumulates</div>
                        </div>
                        <div class="lag-connector">
                            <div class="lag-connector-line"></div>
                            <div class="lag-connector-text">Time lag</div>
                            <div class="lag-connector-line"></div>
                        </div>
                        <div class="lag-phase lag-reaction">
                            <div class="lag-icon">&#x1F4C9;</div>
                            <div class="lag-label">Price Reaction</div>
                            <div class="lag-desc">Markets adjust only after risk events materialize</div>
                        </div>
                    </div>

                    <p style="text-align: center; color: #64748b; font-size: 0.82rem; margin-top: 0.25rem;">GERI measures the buildup phase &mdash; giving you the signal before markets move.</p>
                </div>

                <div class="research-section">
                    <h2>What the Global Energy Risk Index Measures</h2>

                    <p>GERI distills a multi-source intelligence pipeline into a single daily value by measuring four distinct dimensions of global energy risk. Each dimension captures a different layer of the threat landscape &mdash; from individual high-severity events to the geographic breadth of simultaneous stress.</p>

                    <div class="measures-subsection">
                        <h3>3.1 &nbsp;Geopolitical Risk Signals</h3>
                        <p>The dominant driver of GERI movements. This dimension captures events with the potential to cause significant, immediate disruption to global energy supply or pricing.</p>
                        <div class="measures-examples">
                            <span class="measure-tag">&#x2694;&#xFE0F; Military escalation &amp; armed conflict</span>
                            <span class="measure-tag">&#x1F6AB; Sanctions &amp; export restrictions</span>
                            <span class="measure-tag">&#x2693; Maritime &amp; chokepoint disruptions</span>
                            <span class="measure-tag">&#x1F4A5; Pipeline sabotage &amp; infrastructure attacks</span>
                            <span class="measure-tag">&#x1F30D; Conflict in producing regions</span>
                            <span class="measure-tag">&#x1F4DC; Policy shifts with systemic implications</span>
                        </div>
                        <p>Events are scored on a 1&ndash;5 severity scale and weighted by regional influence. A military escalation near the Strait of Hormuz carries fundamentally different weight than an equivalent event in a region with no energy infrastructure.</p>
                    </div>

                    <div class="measures-subsection">
                        <h3>3.2 &nbsp;Supply Chain &amp; Transit Stress</h3>
                        <p>Energy supply disruptions rarely occur without warning. This dimension detects the buildup of stress across global energy transit routes and logistics networks.</p>
                        <div class="measures-examples">
                            <span class="measure-tag">&#x1F6A2; Shipping &amp; LNG cargo disruptions</span>
                            <span class="measure-tag">&#x26F5; Chokepoint stress (Hormuz, Bab el-Mandeb, Suez)</span>
                            <span class="measure-tag">&#x1F6E2;&#xFE0F; Pipeline flow interruptions</span>
                            <span class="measure-tag">&#x1F4E6; Port closures &amp; logistics bottlenecks</span>
                            <span class="measure-tag">&#x1F4B1; LNG cargo competition (Europe vs. Asia)</span>
                        </div>
                        <p>GERI monitors accelerating event frequency within regions &mdash; what we call <em>escalation velocity</em>. A cluster of moderate-severity supply events in a single corridor often precedes a major disruption.</p>
                    </div>

                    <div class="measures-subsection">
                        <h3>3.3 &nbsp;Market Stress Signals</h3>
                        <p>Risk signals emanating from direct asset-level stress &mdash; specific commodities, instruments, and financial indicators under threat.</p>
                        <div class="measures-examples">
                            <span class="measure-tag">&#x1F4C9; Brent &amp; WTI crude volatility</span>
                            <span class="measure-tag">&#x1F525; TTF natural gas price spikes</span>
                            <span class="measure-tag">&#x1F4C8; VIX financial contagion</span>
                            <span class="measure-tag">&#x1F4B1; EUR/USD risk-off signals</span>
                            <span class="measure-tag">&#x1F6A2; Freight cost anomalies</span>
                            <span class="measure-tag">&#x1F4CA; Abnormal Brent-WTI spread widening</span>
                        </div>
                        <p>AI-derived directional assessments for oil, gas, FX, and freight are generated for each event &mdash; capturing how intelligence translates into observable market stress before traditional price data reflects it.</p>
                    </div>

                    <div class="measures-subsection">
                        <h3>3.4 &nbsp;Structural Risk Indicators</h3>
                        <p>Persistent, slower-moving risk factors that define the baseline vulnerability of the global energy system.</p>
                        <div class="measures-examples">
                            <span class="measure-tag">&#x1F4E6; EU gas storage levels vs. seasonal norms</span>
                            <span class="measure-tag">&#x1F3ED; Refinery &amp; terminal outages</span>
                            <span class="measure-tag">&#x26A1; Production disruptions &amp; force majeure</span>
                            <span class="measure-tag">&#x1F6E0;&#xFE0F; Critical infrastructure vulnerability</span>
                            <span class="measure-tag">&#x2744;&#xFE0F; Winter readiness &amp; injection rates</span>
                            <span class="measure-tag">&#x1F30D; Geographic risk concentration</span>
                        </div>
                        <p>A world where risk is concentrated in a single region (e.g., 80% emanating from the Middle East) is qualitatively different from one where the same total risk is distributed across four regions. GERI penalises concentrated risk because a single escalation in a dominant region can trigger cascading effects.</p>
                    </div>

                    <div class="four-pillars-visual">
                        <div class="pillar-card" style="border-top: 3px solid #ef4444;">
                            <div class="pillar-weight">40%</div>
                            <div class="pillar-name">High-Impact Events</div>
                            <div class="pillar-desc">Geopolitical escalations, supply shocks, policy shifts</div>
                        </div>
                        <div class="pillar-card" style="border-top: 3px solid #f97316;">
                            <div class="pillar-weight">25%</div>
                            <div class="pillar-name">Regional Risk Spikes</div>
                            <div class="pillar-desc">Cluster detection, escalation velocity, baseline deviation</div>
                        </div>
                        <div class="pillar-card" style="border-top: 3px solid #3b82f6;">
                            <div class="pillar-weight">20%</div>
                            <div class="pillar-name">Asset Risk</div>
                            <div class="pillar-desc">Oil, gas, FX, freight &mdash; asset-level stress signals</div>
                        </div>
                        <div class="pillar-card" style="border-top: 3px solid #8b5cf6;">
                            <div class="pillar-weight">15%</div>
                            <div class="pillar-name">Region Concentration</div>
                            <div class="pillar-desc">Geographic diversity of simultaneous risk</div>
                        </div>
                    </div>
                    <p style="text-align: center; color: #64748b; font-size: 0.82rem; margin-top: 0.5rem;">The Four Pillars of GERI &mdash; weighted composite architecture</p>
                </div>

                <div class="research-section">
                    <h2>How GERI Is Calculated (Methodology)</h2>

                    <p>GERI is computed algorithmically from structured intelligence inputs. There is no editorial override, manual adjustment, or subjective intervention in the daily index value. The methodology is fixed for each model version, and changes are implemented only through formal version upgrades.</p>

                    <div class="method-step">
                        <div class="method-step-num">4.1</div>
                        <div class="method-step-content">
                            <h3>Event Collection</h3>
                            <p>Events are ingested continuously from a curated portfolio of institutional, trade, and specialist intelligence sources. The source architecture follows a strict credibility hierarchy:</p>
                            <div class="source-tiers">
                                <div class="source-tier">
                                    <div class="tier-label">Tier 0 &mdash; Institutional</div>
                                    <div class="tier-desc">EIA, OPEC, government agencies</div>
                                </div>
                                <div class="source-tier">
                                    <div class="tier-label">Tier 1 &mdash; Market Intelligence</div>
                                    <div class="tier-desc">Reuters, ICIS, Platts</div>
                                </div>
                                <div class="source-tier">
                                    <div class="tier-label">Tier 2 &mdash; Trade Specialist</div>
                                    <div class="tier-desc">FreightWaves, Rigzone, Maritime Executive</div>
                                </div>
                                <div class="source-tier">
                                    <div class="tier-label">Tier 3 &mdash; Regional / General</div>
                                    <div class="tier-desc">Al Jazeera, Xinhua, EU Commission</div>
                                </div>
                            </div>
                            <p style="background: rgba(59,130,246,0.08); border-left: 3px solid #3b82f6; padding: 0.6rem 0.85rem; border-radius: 0 6px 6px 0; color: #e2e8f0; font-weight: 500;">General news aggregators, opinion blogs, social media, and financial spam feeds are excluded by design. Signal quality depends directly on source credibility and diversity.</p>
                        </div>
                    </div>

                    <div class="method-step">
                        <div class="method-step-num">4.2</div>
                        <div class="method-step-content">
                            <h3>Event Classification</h3>
                            <p>Each ingested event undergoes deduplication, classification, and region tagging. Events are categorized by primary type and thematic sub-category, with a priority hierarchy that ensures the most operationally significant interpretation is selected:</p>
                            <div class="measures-examples">
                                <span class="measure-tag">&#x2694;&#xFE0F; War &amp; Armed Conflict</span>
                                <span class="measure-tag">&#x1F6E1;&#xFE0F; Military Posturing</span>
                                <span class="measure-tag">&#x1F4A5; Active Conflict</span>
                                <span class="measure-tag">&#x1F6E0;&#xFE0F; Industrial Strikes</span>
                                <span class="measure-tag">&#x1F6AB; Sanctions &amp; Embargoes</span>
                                <span class="measure-tag">&#x26A1; Supply Disruption</span>
                                <span class="measure-tag">&#x1F6E2;&#xFE0F; Energy Market Events</span>
                                <span class="measure-tag">&#x1F3DB;&#xFE0F; Policy &amp; Regulation</span>
                                <span class="measure-tag">&#x1F91D; Diplomacy &amp; De-escalation</span>
                            </div>
                            <p>Events are then enriched using Algorithms to produce structured impact assessments, severity scoring, asset linkage, and contextual summaries explaining why the event matters for energy risk.</p>
                        </div>
                    </div>

                    <div class="method-step">
                        <div class="method-step-num">4.3</div>
                        <div class="method-step-content">
                            <h3>Scoring Framework</h3>
                            <p>Each qualifying event receives a multi-dimensional risk assessment based on:</p>
                            <div class="measures-examples">
                                <span class="measure-tag">&#x1F4CA; Severity (1&ndash;5 scale)</span>
                                <span class="measure-tag">&#x1F30D; Regional influence weight</span>
                                <span class="measure-tag">&#x1F4F0; Source credibility tier</span>
                                <span class="measure-tag">&#x1F4C8; Market relevance</span>
                            </div>
                            <p>Events originating from regions with higher structural influence on global energy flows receive proportionally greater weight. The seven region clusters &mdash; Middle East, Russia/Black Sea, China, United States, Europe Internal, LNG Exporters, and Emerging Supply Regions &mdash; each carry a calibrated influence weight reflecting their importance to global energy markets.</p>
                            <p>Scored events are then converted into three alert types that feed the index: <strong>High-Impact Events</strong> for individual severe occurrences, <strong>Regional Risk Spikes</strong> for concentrated regional buildup, and <strong>Asset Risk Alerts</strong> for infrastructure and commodity-specific threats.</p>
                        </div>
                    </div>

                    <div class="method-step">
                        <div class="method-step-num">4.4</div>
                        <div class="method-step-content">
                            <h3>Normalization &amp; Risk Bands</h3>
                            <p>The index maintains a rolling historical baseline for normalization purposes. This baseline tracks observed values over a rolling window, ensuring the 0&ndash;100 scale remains calibrated to the range of conditions actually observed. This prevents the index from clustering at one end during prolonged periods of high or low risk.</p>
                            <p>Each daily GERI value maps to one of five risk bands, accompanied by 1-day and 7-day trend indicators:</p>
                            <table class="regime-table">
                                <thead>
                                    <tr>
                                        <th>Score</th>
                                        <th>Risk Band</th>
                                        <th>Interpretation</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    <tr>
                                        <td><span class="regime-band-dot" style="background:#22c55e;"></span>0 &ndash; 20</td>
                                        <td>LOW</td>
                                        <td>Benign geopolitical environment. Energy supply risks minimal. Normal market conditions.</td>
                                    </tr>
                                    <tr>
                                        <td><span class="regime-band-dot" style="background:#eab308;"></span>21 &ndash; 40</td>
                                        <td>MODERATE</td>
                                        <td>Background risk present but manageable. Some regional tensions. Standard monitoring posture.</td>
                                    </tr>
                                    <tr>
                                        <td><span class="regime-band-dot" style="background:#f97316;"></span>41 &ndash; 60</td>
                                        <td>ELEVATED</td>
                                        <td>Meaningful risk accumulation. Multiple regions contributing. Active monitoring and hedging warranted.</td>
                                    </tr>
                                    <tr>
                                        <td><span class="regime-band-dot" style="background:#ef4444;"></span>61 &ndash; 80</td>
                                        <td>SEVERE</td>
                                        <td>Severe disruption pressure. Risk signals converging. Active hedging and contingency planning advised.</td>
                                    </tr>
                                    <tr>
                                        <td><span class="regime-band-dot" style="background:#dc2626;"></span>81 &ndash; 100</td>
                                        <td>CRITICAL</td>
                                        <td>Systemic stress. Risk converged across regions and assets. Defensive positioning indicated.</td>
                                    </tr>
                                </tbody>
                            </table>
                            <p>Trend context matters: a GERI of 60 that has risen 15 points in a week carries a very different implication than a GERI of 60 that has fallen 10 points over the same period.</p>
                        </div>
                    </div>
                </div>

                <div class="research-section">
                    <h2>Interpreting the Index</h2>

                    <p>GERI is not an asset price prediction tool. It is a <strong>risk context layer</strong> that answers: &ldquo;What is the current state of the geopolitical and energy risk environment?&rdquo; The distinction is critical &mdash; GERI measures risk inputs, not market outcomes.</p>

                    <div class="callout-box">
                        <p>A rising GERI indicates that the global energy system is experiencing increasing structural stress, even if prices have not yet reacted. The relationship between GERI and asset prices is mediated by market positioning, liquidity, storage buffers, and participant expectations.</p>
                    </div>

                    <h3 style="font-size: 0.95rem; font-weight: 600; color: #e2e8f0; margin: 1.5rem 0 0.75rem 0;">How Analysts Use GERI</h3>

                    <div class="use-cases-grid">
                        <div class="use-case-card">
                            <div class="uc-icon">&#x1F4C8;</div>
                            <div class="uc-title">Trading</div>
                            <ul class="uc-list">
                                <li>Identifying abnormal risk regimes</li>
                                <li>Confirming volatility environments</li>
                                <li>Timing hedging decisions</li>
                                <li>Detecting risk build-up before price moves</li>
                            </ul>
                        </div>
                        <div class="use-case-card">
                            <div class="uc-icon">&#x1F3AF;</div>
                            <div class="uc-title">Strategic Planning</div>
                            <ul class="uc-list">
                                <li>Assessing geopolitical risk exposure</li>
                                <li>Informing portfolio allocation</li>
                                <li>Activating contingency protocols</li>
                                <li>Evaluating energy procurement timing</li>
                            </ul>
                        </div>
                        <div class="use-case-card">
                            <div class="uc-icon">&#x1F50D;</div>
                            <div class="uc-title">Market Analysis</div>
                            <ul class="uc-list">
                                <li>Understanding price-risk divergence</li>
                                <li>Cross-asset risk correlation</li>
                                <li>Regime recognition and cycle analysis</li>
                                <li>Contextualising commodity moves</li>
                            </ul>
                        </div>
                    </div>

                    <h3 style="font-size: 0.95rem; font-weight: 600; color: #e2e8f0; margin: 1.5rem 0 0.75rem 0;">Cross-Asset Context</h3>

                    <p style="color: #94a3b8; font-size: 0.88rem; line-height: 1.65;">GERI is designed to be read alongside energy market data for maximum insight. These cross-references reveal whether risk is being priced in &mdash; or ignored:</p>

                    <div class="cross-ref-grid">
                        <div class="cross-ref-item">
                            <div class="cr-pair">GERI vs. Brent Crude</div>
                            <div class="cr-desc">Whether supply disruption fear is priced into oil markets</div>
                        </div>
                        <div class="cross-ref-item">
                            <div class="cr-pair">GERI vs. TTF Gas</div>
                            <div class="cr-desc">European vulnerability to geopolitical gas risk</div>
                        </div>
                        <div class="cross-ref-item">
                            <div class="cr-pair">GERI vs. VIX</div>
                            <div class="cr-desc">Whether energy risk is spilling into broader financial markets</div>
                        </div>
                        <div class="cross-ref-item">
                            <div class="cr-pair">GERI vs. EUR/USD</div>
                            <div class="cr-desc">European macro vulnerability to energy shocks</div>
                        </div>
                    </div>

                    <h3 style="font-size: 0.95rem; font-weight: 600; color: #e2e8f0; margin: 1.5rem 0 0.75rem 0;">Recognising Risk Regimes</h3>

                    <p style="color: #94a3b8; font-size: 0.88rem; line-height: 1.65; margin-bottom: 0.75rem;">GERI&rsquo;s historical trajectory can be divided into four recognisable regimes:</p>

                    <table class="regime-table">
                        <thead>
                            <tr>
                                <th>Regime</th>
                                <th>GERI Behaviour</th>
                                <th>Market Characteristics</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr>
                                <td><span class="regime-band-dot" style="background:#eab308;"></span>Accumulation</td>
                                <td>Rising gradually</td>
                                <td>Risk building, assets react slowly. Markets are discounting. Early warning phase.</td>
                            </tr>
                            <tr>
                                <td><span class="regime-band-dot" style="background:#ef4444;"></span>Shock</td>
                                <td>Sharp spike</td>
                                <td>High-impact event materialised. Assets overshoot. Maximum volatility phase.</td>
                            </tr>
                            <tr>
                                <td><span class="regime-band-dot" style="background:#f97316;"></span>Stabilisation</td>
                                <td>Begins to fall</td>
                                <td>Markets repricing, uncertainty still elevated. Assets remain volatile.</td>
                            </tr>
                            <tr>
                                <td><span class="regime-band-dot" style="background:#22c55e;"></span>Recovery</td>
                                <td>Returns to low/moderate</td>
                                <td>Risk dissipated, markets found equilibrium. Normal conditions resume.</td>
                            </tr>
                        </tbody>
                    </table>
                </div>

                <div class="research-section">
                    <h2>Historical Examples of Energy Risk Spikes</h2>

                    <p>The following case studies are drawn from EnergyRiskIQ live production data. They illustrate how the platform captures real-world energy risk events, scores their severity, and reflects them in the index before markets fully absorb the implications.</p>

                    <div class="case-study">
                        <div class="case-study-header">
                            <div class="case-study-badge">
                                <div class="badge-icon">&#x1F4A5;</div>
                                <div class="badge-label">Geopolitical</div>
                            </div>
                            <div class="case-study-title">
                                <h3>US-Israel Strikes on Iran &amp; Strait of Hormuz Risk</h3>
                                <div class="cs-date">28 February 2026 &mdash; GERI Live Event</div>
                            </div>
                        </div>
                        <div class="case-study-body">
                            <p>On 28 February 2026, US and Israeli forces launched coordinated strikes on Iranian targets. Iran responded by striking the US military base in Bahrain. The platform registered 13 severity-5 HIGH_IMPACT_EVENT alerts within a single intraday processing window spanning the Middle East, Asia, and Russia clusters &mdash; the maximum alert severity the system can generate.</p>

                            <div class="cs-metrics-row">
                                <div class="cs-metric">
                                    <div class="cm-label">GERI Live</div>
                                    <div class="cm-value" style="color:#eab308;">31</div>
                                    <div class="cm-sub">MODERATE band</div>
                                </div>
                                <div class="cs-metric">
                                    <div class="cm-label">Alerts triggered</div>
                                    <div class="cm-value" style="color:#ef4444;">19</div>
                                    <div class="cm-sub">13 at severity 5</div>
                                </div>
                                <div class="cs-metric">
                                    <div class="cm-label">Brent next day</div>
                                    <div class="cm-value" style="color:#22c55e;">+7.2%</div>
                                    <div class="cm-sub">$72.48 → $77.70</div>
                                </div>
                                <div class="cs-metric">
                                    <div class="cm-label">Hormuz exposure</div>
                                    <div class="cm-value" style="color:#f97316;">50%</div>
                                    <div class="cm-sub">India oil imports at risk</div>
                                </div>
                            </div>

                            <div style="margin: 1.25rem 0;">
                                <div style="font-size:0.72rem;color:#64748b;text-transform:uppercase;letter-spacing:0.04em;margin-bottom:0.75rem;">GERI Live &mdash; Feb 25 to Mar 4, 2026 (0&ndash;100 scale)</div>
                                <div style="position:relative;height:140px;"><canvas id="geriChart"></canvas></div>
                                <div style="font-size:0.72rem;color:#64748b;text-transform:uppercase;letter-spacing:0.04em;margin:1.25rem 0 0.75rem 0;">Brent Crude (USD/bbl) &mdash; same period</div>
                                <div style="position:relative;height:120px;"><canvas id="brentChart"></canvas></div>
                                <div style="font-size:0.72rem;color:#64748b;text-transform:uppercase;letter-spacing:0.04em;margin:1.25rem 0 0.75rem 0;">VIX (market days only &mdash; Feb 28 &amp; Mar 1 were weekend)</div>
                                <div style="position:relative;height:110px;"><canvas id="vixChart"></canvas></div>
                                <div style="font-size:0.7rem;color:#475569;margin-top:0.5rem;">&#9733; = Strike date (28 Feb). Sources: EnergyRiskIQ GERI Live, OilPriceAPI, CBOE via Yahoo Finance / FRED.</div>
                            </div>

                            <div class="cs-events-list">
                                <div class="ev-item"><span class="ev-sev">SEV 5</span><span class="ev-text">Oil Markets Brace for Volatility As U.S.-Israel Launch Strikes Across Iran</span></div>
                                <div class="ev-item"><span class="ev-sev">SEV 5</span><span class="ev-text">Iran strikes US military base in Bahrain as explosions heard across Gulf</span></div>
                                <div class="ev-item"><span class="ev-sev">SEV 5</span><span class="ev-text">US-Israel strike on Iran: Attack puts 50% of India&rsquo;s oil imports at risk via Hormuz</span></div>
                                <div class="ev-item"><span class="ev-sev">SEV 5</span><span class="ev-text">Russia Oil Exports to China &amp; India Surge Amid Sanctions &mdash; shifting global supply flows</span></div>
                            </div>

                            <p>The GERI reading of 31 (MODERATE) at the time reflected intraday alert accumulation before the full market reaction was priced in. Brent crude, which closed at $72.48 on the day of the strikes, moved to $77.70 the following session &mdash; a 7.2% single-day move confirming the risk environment GERI had flagged. VIX also rose from 19.86 to 21.21, indicating broader financial market contagion from the energy shock.</p>
                        </div>
                    </div>
                </div>
            </div>
        </main>

        {render_digest_footer()}
        <script>
        (function() {{
            const GRID = {{ color: 'rgba(51,65,85,0.5)' }};
            const TICK = {{ color: '#64748b', font: {{ size: 10 }} }};
            const FONT = 'Inter, system-ui, sans-serif';
            Chart.defaults.font.family = FONT;

            const geriLabels = {_geri_labels_js};
            const geriData   = {_geri_data_js};

            new Chart(document.getElementById('geriChart'), {{
                type: 'line',
                data: {{
                    labels: geriLabels,
                    datasets: [{{
                        label: 'GERI Live',
                        data: geriData,
                        borderColor: '#f97316',
                        backgroundColor: 'rgba(249,115,22,0.12)',
                        borderWidth: 2.5,
                        pointRadius: geriData.map((v, i) => i === {_geri_event_idx} ? 7 : (v !== null ? 4 : 0)),
                        pointBackgroundColor: geriData.map((v, i) => i === {_geri_event_idx} ? '#ef4444' : '#f97316'),
                        pointBorderColor: '#0f172a',
                        pointBorderWidth: 2,
                        fill: true,
                        tension: 0.35,
                        spanGaps: false
                    }}]
                }},
                options: {{
                    responsive: true, maintainAspectRatio: false,
                    plugins: {{
                        legend: {{ display: false }},
                        tooltip: {{
                            backgroundColor: '#1e293b',
                            titleColor: '#f1f5f9',
                            bodyColor: '#94a3b8',
                            borderColor: '#334155',
                            borderWidth: 1,
                            callbacks: {{
                                label: ctx => ctx.parsed.y !== null ? 'GERI: ' + ctx.parsed.y : 'No data'
                            }}
                        }}
                    }},
                    scales: {{
                        x: {{ grid: GRID, ticks: TICK, border: {{ color: '#334155' }} }},
                        y: {{
                            min: 0, max: 50,
                            grid: GRID, ticks: {{ ...TICK, stepSize: 10 }},
                            border: {{ color: '#334155' }}
                        }}
                    }}
                }}
            }});

            const brentLabels = {_brent_labels_js};
            const brentData   = {_brent_data_js};

            new Chart(document.getElementById('brentChart'), {{
                type: 'line',
                data: {{
                    labels: brentLabels,
                    datasets: [{{
                        label: 'Brent (USD/bbl)',
                        data: brentData,
                        borderColor: '#3b82f6',
                        backgroundColor: 'rgba(59,130,246,0.1)',
                        borderWidth: 2.5,
                        pointRadius: brentData.map((v, i) => i === {_brent_surge_idx} ? 7 : 4),
                        pointBackgroundColor: brentData.map((v, i) => i === {_brent_surge_idx} ? '#22c55e' : '#3b82f6'),
                        pointBorderColor: '#0f172a',
                        pointBorderWidth: 2,
                        fill: true,
                        tension: 0.3
                    }}]
                }},
                options: {{
                    responsive: true, maintainAspectRatio: false,
                    plugins: {{
                        legend: {{ display: false }},
                        tooltip: {{
                            backgroundColor: '#1e293b',
                            titleColor: '#f1f5f9',
                            bodyColor: '#94a3b8',
                            borderColor: '#334155',
                            borderWidth: 1,
                            callbacks: {{
                                label: ctx => '$' + ctx.parsed.y.toFixed(2) + ' / bbl'
                            }}
                        }}
                    }},
                    scales: {{
                        x: {{ grid: GRID, ticks: TICK, border: {{ color: '#334155' }} }},
                        y: {{
                            min: {_brent_min}, max: {_brent_max},
                            grid: GRID, ticks: {{ ...TICK, callback: v => '$' + v }},
                            border: {{ color: '#334155' }}
                        }}
                    }}
                }}
            }});

            const vixLabels = {_vix_labels_js};
            const vixData   = {_vix_data_js};

            new Chart(document.getElementById('vixChart'), {{
                type: 'line',
                data: {{
                    labels: vixLabels,
                    datasets: [{{
                        label: 'VIX',
                        data: vixData,
                        borderColor: '#a78bfa',
                        backgroundColor: 'rgba(167,139,250,0.1)',
                        borderWidth: 2.5,
                        pointRadius: vixData.map((v, i) => i === {_vix_surge_idx} ? 7 : 4),
                        pointBackgroundColor: vixData.map((v, i) => i === {_vix_surge_idx} ? '#ef4444' : '#a78bfa'),
                        pointBorderColor: '#0f172a',
                        pointBorderWidth: 2,
                        fill: true,
                        tension: 0.3
                    }}]
                }},
                options: {{
                    responsive: true, maintainAspectRatio: false,
                    plugins: {{
                        legend: {{ display: false }},
                        tooltip: {{
                            backgroundColor: '#1e293b',
                            titleColor: '#f1f5f9',
                            bodyColor: '#94a3b8',
                            borderColor: '#334155',
                            borderWidth: 1,
                            callbacks: {{
                                label: ctx => 'VIX: ' + ctx.parsed.y.toFixed(2)
                            }}
                        }}
                    }},
                    scales: {{
                        x: {{ grid: GRID, ticks: TICK, border: {{ color: '#334155' }} }},
                        y: {{
                            min: {_vix_min}, max: {_vix_max},
                            grid: GRID, ticks: TICK,
                            border: {{ color: '#334155' }}
                        }}
                    }}
                }}
            }});
        }})();
        </script>
    </body>
    </html>
    """

    return HTMLResponse(content=html)
