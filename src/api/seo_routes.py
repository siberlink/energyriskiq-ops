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

router = APIRouter(tags=["seo"])

BASE_URL = os.environ.get('ALERTS_APP_BASE_URL', 'https://energyriskiq.com')


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
    """Render conversion CTA section."""
    if position == "top":
        return """
        <div class="hero-banner">
            <div class="container">
                Get real-time alerts delivered to your inbox. <a href="/users">Sign up free</a>
            </div>
        </div>
        """
    return """
    <section class="cta-section">
        <h3>Unlock Full Risk Intelligence</h3>
        <p>Get real-time alerts, detailed analysis, and multi-channel delivery (Email, Telegram, SMS).</p>
        <a href="/users" class="cta-btn">Start Free Trial</a>
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
    
    alert_cards_html = ""
    for card in model.get('alert_cards', []):
        severity = card.get('severity', 3)
        alert_cards_html += f"""
        <article class="alert-card severity-{severity}">
            <div class="alert-header">
                <h3 class="alert-title">{card['public_title']}</h3>
                <div class="alert-badges">
                    <span class="badge severity severity-{severity}">Severity {severity}/5</span>
                    <span class="badge">{card['category']}</span>
                    <span class="badge">{card['region']}</span>
                </div>
            </div>
            <p class="alert-summary">{card['public_summary']}</p>
            <div class="alert-meta">
                {card['event_type']}
                {f" | Source: {card['source_domain']}" if card.get('source_domain') else ""}
            </div>
        </article>
        """
    
    drivers_html = ""
    for driver in model.get('top_drivers', []):
        drivers_html += f"<li>{driver}</li>"
    
    stats = model.get('stats', {})
    stats_html = f"""
    <div class="stats-row">
        <div class="stat-badge"><strong>{stats.get('total_alerts', 0)}</strong> Total Alerts</div>
        <div class="stat-badge"><strong>{stats.get('critical_count', 0)}</strong> Critical</div>
        <div class="stat-badge"><strong>{stats.get('high_count', 0)}</strong> High Severity</div>
    </div>
    """
    
    prev_link = f'<a href="/alerts/daily/{model["prev_date"]}">&larr; Previous Day</a>' if model.get('prev_date') else '<span></span>'
    next_link = f'<a href="/alerts/daily/{model["next_date"]}">Next Day &rarr;</a>' if model.get('next_date') else '<span></span>'
    
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{model['seo_title']}</title>
        <meta name="description" content="{model['seo_description']}">
        <link rel="canonical" href="{BASE_URL}/alerts/daily/{date_str}">
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
                <p class="meta">Published {model['date_display']} | Updated daily with 24-hour delayed alerts</p>
                
                {stats_html}
                
                <section class="risk-posture">
                    <h3>Daily Risk Posture</h3>
                    <p>{model['risk_posture']}</p>
                </section>
                
                <h2>Top Risk Drivers</h2>
                <ul class="drivers-list">
                    {drivers_html}
                </ul>
                
                <h2>Alert Details</h2>
                <div class="alert-cards">
                    {alert_cards_html if alert_cards_html else '<p>No alerts detected for this day.</p>'}
                </div>
                
                {render_cta_section("mid")}
                
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
    """Generate XML sitemap."""
    entries = generate_sitemap_entries()
    
    xml_entries = ""
    for e in entries:
        xml_entries += f"""
    <url>
        <loc>{BASE_URL}{e['loc']}</loc>
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
