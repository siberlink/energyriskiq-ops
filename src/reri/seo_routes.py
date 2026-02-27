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

import json as json_module

from src.reri.interpretation import generate_eeri_interpretation
from src.api.seo_routes import get_digest_dark_styles, render_digest_footer
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
from src.reri.eeri_weekly_snapshot import get_weekly_snapshot, BAND_COLORS as WEEKLY_BAND_COLORS

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
        .index-meta { margin-top: 1rem; padding-top: 1rem; border-top: 1px solid rgba(107, 114, 128, 0.3); }
        .index-meta-row { display: flex; justify-content: space-between; align-items: center; padding: 0.25rem 0; font-size: 0.85rem; }
        .meta-label { color: #9ca3af; }
        .meta-value { color: #d1d5db; font-weight: 500; }
        
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
        
        .risk-bands-section { background: rgba(96, 165, 250, 0.03); border-radius: 12px; padding: 1.25rem 1.5rem; }
        .risk-bands-container { display: flex; flex-direction: column; gap: 0.5rem; margin: 1rem 0; }
        .risk-band-row { display: flex; align-items: center; gap: 0.75rem; padding: 0.5rem 0.75rem; border-radius: 8px; transition: all 0.2s ease; }
        .risk-band-row.active { background: rgba(255, 255, 255, 0.1); box-shadow: 0 0 0 2px rgba(96, 165, 250, 0.5); }
        .band-range { font-family: 'SF Mono', 'Consolas', monospace; font-size: 0.85rem; color: #6b7280; min-width: 50px; }
        .band-indicator { width: 24px; height: 24px; border-radius: 50%; flex-shrink: 0; }
        .band-indicator.low { background: linear-gradient(135deg, #22c55e 0%, #16a34a 100%); }
        .band-indicator.moderate { background: linear-gradient(135deg, #facc15 0%, #eab308 100%); }
        .band-indicator.elevated { background: linear-gradient(135deg, #f97316 0%, #ea580c 100%); }
        .band-indicator.severe { background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%); }
        .band-indicator.critical { background: linear-gradient(135deg, #991b1b 0%, #7f1d1d 100%); box-shadow: 0 0 8px rgba(239, 68, 68, 0.5); }
        .band-name { font-weight: 500; color: #374151; font-size: 0.95rem; }
        .risk-band-row.active .band-name { color: #1f2937; font-weight: 600; }
        .current-position { text-align: center; margin-top: 1rem; padding: 0.75rem; background: rgba(96, 165, 250, 0.1); border-radius: 8px; font-size: 0.95rem; color: #4b5563; }
        .current-position strong { font-weight: 700; }
        
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


def _build_weekly_snapshot_html(snapshot: dict) -> str:
    """Build the Weekly Snapshot HTML section for the /eeri page."""
    if not snapshot:
        return ''

    from datetime import datetime as dt
    ws = snapshot['week_start']
    we = snapshot['week_end']
    try:
        ws_dt = dt.strptime(ws, '%Y-%m-%d')
        we_dt = dt.strptime(we, '%Y-%m-%d')
        week_label = f"{ws_dt.strftime('%b %d')} – {we_dt.strftime('%b %d, %Y')}"
    except Exception:
        week_label = f"{ws} – {we}"

    ov = snapshot['overview']
    avg_val = ov['average']
    avg_band = ov['band']
    band_color = WEEKLY_BAND_COLORS.get(avg_band, '#6b7280')
    high_val = ov['high']['value']
    high_day = ov['high']['day']
    low_val = ov['low']['value']
    low_day = ov['low']['day']
    trend = ov['trend_vs_prior']
    trend_arrow = '↑' if trend == 'rising' else ('↓' if trend == 'falling' else '→')
    trend_label = trend.capitalize()
    trend_color = '#ef4444' if trend == 'rising' else ('#22c55e' if trend == 'falling' else '#6b7280')

    regime_html = ''
    for band_name, days in snapshot['regime_distribution']:
        bc = WEEKLY_BAND_COLORS.get(band_name, '#6b7280')
        day_word = 'day' if days == 1 else 'days'
        pct = round((days / snapshot['data_days']) * 100)
        regime_html += f'''
            <div class="ws-regime-row">
                <span class="ws-regime-badge" style="background: {bc};">{band_name}</span>
                <div class="ws-regime-bar-track">
                    <div class="ws-regime-bar-fill" style="width: {pct}%; background: {bc};"></div>
                </div>
                <span class="ws-regime-count">{days} {day_word}</span>
            </div>'''

    assets_html = ''
    for asset in snapshot['cross_asset']:
        move = asset['weekly_move_pct']
        if move is not None:
            sign = '+' if move > 0 else ''
            move_str = f"{sign}{move}%"
            move_color = '#ef4444' if move > 0 else ('#22c55e' if move < 0 else '#6b7280')
        else:
            move_str = 'N/A'
            move_color = '#6b7280'

        alignment = asset['alignment']
        if alignment == 'confirming':
            align_icon = '✅'
            align_label = 'Confirming'
            align_cls = 'ws-align-confirming'
        elif alignment == 'diverging':
            align_icon = '⚠'
            align_label = 'Diverging'
            align_cls = 'ws-align-diverging'
        else:
            align_icon = '🟡'
            align_label = 'Neutral'
            align_cls = 'ws-align-neutral'

        assets_html += f'''
            <div class="ws-asset-row">
                <div class="ws-asset-name">{asset['asset']}</div>
                <div class="ws-asset-move" style="color: {move_color};">{move_str}</div>
                <div class="ws-asset-align {align_cls}">{align_icon} {align_label}</div>
                <div class="ws-asset-context">{asset['context']}</div>
            </div>'''

    chart_data = snapshot.get('chart_data', {})
    chart_json = json_module.dumps(chart_data)

    asset_chart_configs = [
        ('ttf', 'TTF Gas', '#f97316'),
        ('brent', 'Brent Oil', '#3b82f6'),
        ('storage', 'EU Storage', '#22c55e'),
        ('vix', 'VIX', '#a855f7'),
        ('eurusd', 'EUR/USD', '#eab308'),
    ]
    charts_html = ''
    for key, name, color in asset_chart_configs:
        charts_html += f'''
            <div class="ws-mini-chart">
                <div class="ws-mini-chart-title">EERI vs {name}</div>
                <div class="ws-mini-chart-wrap">
                    <canvas id="ws-chart-{key}" width="200" height="120"></canvas>
                </div>
            </div>'''

    div_status = snapshot['divergence_status']
    div_narrative = snapshot['divergence_narrative']
    if div_status == 'confirming':
        div_icon = '✅'
        div_label = 'Markets Confirming Risk'
        div_cls = 'ws-div-confirming'
    elif div_status == 'diverging':
        div_icon = '⚠'
        div_label = 'Markets Diverging From Risk'
        div_cls = 'ws-div-diverging'
    else:
        div_icon = '🟡'
        div_label = 'Markets Mixed'
        div_cls = 'ws-div-mixed'

    hist_items = ''
    for item in snapshot['historical_context']:
        hist_items += f'<li>{item}</li>'

    tend_html = ''
    for t in snapshot['tendencies']:
        conf_cls = 'ws-conf-medium' if t['confidence'] == 'Medium' else 'ws-conf-low'
        tend_html += f'''
            <div class="ws-tend-row">
                <div class="ws-tend-asset">{t['asset']}</div>
                <div class="ws-tend-tendency">{t['tendency']}</div>
                <div class="ws-tend-conf {conf_cls}">{t['confidence']}</div>
            </div>'''

    chart_init_js = ''
    for key, name, color in asset_chart_configs:
        chart_init_js += f'''
        (function() {{
            var eeriPts = chartData.eeri || [];
            var assetPts = chartData['{key}'] || [];
            if (eeriPts.length < 2 || assetPts.length < 2) return;
            var eeriBase = Number(eeriPts[0].value) || 1;
            var assetBase = Number(assetPts[0].value) || 1;
            if (eeriBase === 0 || assetBase === 0) return;
            var labels = eeriPts.map(function(p) {{
                var d = new Date(p.date + 'T12:00:00');
                return ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][d.getDay() === 0 ? 6 : d.getDay()-1];
            }});
            var eeriIndexed = eeriPts.map(function(p) {{ return parseFloat(((Number(p.value) / eeriBase) * 100).toFixed(1)); }});
            var assetIndexed = assetPts.map(function(p) {{ return parseFloat(((Number(p.value) / assetBase) * 100).toFixed(1)); }});
            var maxLen = Math.min(labels.length, assetIndexed.length);
            labels = labels.slice(0, maxLen);
            eeriIndexed = eeriIndexed.slice(0, maxLen);
            assetIndexed = assetIndexed.slice(0, maxLen);
            var ctx = document.getElementById('ws-chart-{key}');
            if (!ctx) return;
            new Chart(ctx, {{
                type: 'line',
                data: {{
                    labels: labels,
                    datasets: [
                        {{ label: 'EERI', data: eeriIndexed, borderColor: '#0066FF', backgroundColor: 'transparent', borderWidth: 2, pointRadius: 0, tension: 0.3 }},
                        {{ label: '{name}', data: assetIndexed, borderColor: '{color}', backgroundColor: 'transparent', borderWidth: 2, pointRadius: 0, tension: 0.3 }}
                    ]
                }},
                options: {{
                    responsive: true, maintainAspectRatio: false, animation: false,
                    plugins: {{ legend: {{ display: true, position: 'bottom', labels: {{ font: {{ size: 10 }}, boxWidth: 12, padding: 6 }} }} }},
                    scales: {{
                        x: {{ grid: {{ display: false }}, ticks: {{ font: {{ size: 9 }} }} }},
                        y: {{ grid: {{ color: '#f1f5f9' }}, ticks: {{ font: {{ size: 9 }}, callback: function(v) {{ return v + ''; }} }} }}
                    }}
                }}
            }});
        }})();'''

    return f'''
        <div class="ws-section" style="margin: 2rem 0;">
            <style>
                .ws-section {{ font-family: 'Inter', -apple-system, sans-serif; }}
                .ws-header {{ text-align: center; margin-bottom: 1.5rem; }}
                .ws-header h2 {{ font-size: 1.4rem; color: var(--text-primary); margin-bottom: 0.3rem; }}
                .ws-header p {{ color: var(--text-secondary); font-size: 0.95rem; }}
                .ws-overview-card {{
                    background: linear-gradient(135deg, #1A1A2E 0%, #16213E 100%);
                    color: #fff; border-radius: 12px; padding: 1.5rem;
                    margin-bottom: 1.25rem;
                }}
                .ws-overview-title {{ font-size: 1.1rem; font-weight: 600; margin-bottom: 0.25rem; }}
                .ws-overview-week {{ font-size: 0.85rem; color: #94a3b8; margin-bottom: 1rem; }}
                .ws-overview-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; }}
                .ws-overview-stat {{ }}
                .ws-overview-label {{ font-size: 0.75rem; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em; }}
                .ws-overview-value {{ font-size: 1.25rem; font-weight: 700; }}
                .ws-overview-sub {{ font-size: 0.8rem; color: #94a3b8; }}
                .ws-panel {{
                    background: #fff; border: 1px solid var(--border); border-radius: 12px;
                    padding: 1.25rem; margin-bottom: 1.25rem;
                }}
                .ws-panel-title {{ font-size: 1rem; font-weight: 600; color: var(--text-primary); margin-bottom: 0.75rem; }}
                .ws-regime-row {{ display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.5rem; }}
                .ws-regime-badge {{
                    font-size: 0.7rem; font-weight: 600; color: #fff; padding: 2px 8px;
                    border-radius: 4px; min-width: 75px; text-align: center; text-transform: uppercase;
                }}
                .ws-regime-bar-track {{ flex: 1; background: #f1f5f9; border-radius: 4px; height: 8px; }}
                .ws-regime-bar-fill {{ height: 100%; border-radius: 4px; transition: width 0.5s; }}
                .ws-regime-count {{ font-size: 0.8rem; color: var(--text-secondary); min-width: 50px; text-align: right; }}
                .ws-asset-row {{
                    display: grid; grid-template-columns: 120px 70px 110px 1fr;
                    gap: 0.5rem; align-items: center; padding: 0.6rem 0;
                    border-bottom: 1px solid #f1f5f9;
                }}
                .ws-asset-row:last-child {{ border-bottom: none; }}
                .ws-asset-name {{ font-weight: 600; font-size: 0.9rem; }}
                .ws-asset-move {{ font-weight: 600; font-size: 0.9rem; text-align: center; }}
                .ws-asset-align {{ font-size: 0.8rem; font-weight: 500; }}
                .ws-align-confirming {{ color: #22c55e; }}
                .ws-align-diverging {{ color: #ef4444; }}
                .ws-align-neutral {{ color: #eab308; }}
                .ws-asset-context {{ font-size: 0.8rem; color: var(--text-secondary); }}
                .ws-charts-row {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 0.75rem; margin-bottom: 1.25rem; }}
                .ws-mini-chart {{ background: #fff; border: 1px solid var(--border); border-radius: 10px; padding: 0.75rem; height: 180px; position: relative; }}
                .ws-mini-chart-title {{ font-size: 0.75rem; font-weight: 600; color: var(--text-secondary); margin-bottom: 0.5rem; text-align: center; }}
                .ws-mini-chart-wrap {{ position: relative; height: 130px; }}
                .ws-mini-chart canvas {{ width: 100% !important; }}
                .ws-divergence-badge {{
                    border-radius: 12px; padding: 1rem 1.25rem;
                    margin-bottom: 1.25rem; font-size: 0.95rem;
                }}
                .ws-div-confirming {{ background: #f0fdf4; border: 1px solid #bbf7d0; color: #166534; }}
                .ws-div-mixed {{ background: #fefce8; border: 1px solid #fef08a; color: #854d0e; }}
                .ws-div-diverging {{ background: #fef2f2; border: 1px solid #fecaca; color: #991b1b; }}
                .ws-div-icon {{ font-size: 1.1rem; margin-right: 0.5rem; }}
                .ws-div-title {{ font-weight: 700; }}
                .ws-div-text {{ margin-top: 0.4rem; font-size: 0.9rem; line-height: 1.5; }}
                .ws-hist-box {{
                    background: #f8fafc; border: 1px solid var(--border); border-radius: 12px;
                    padding: 1.25rem; margin-bottom: 1.25rem;
                }}
                .ws-hist-box ul {{ margin: 0.5rem 0 0 1.25rem; color: var(--text-secondary); font-size: 0.9rem; line-height: 1.8; }}
                .ws-tend-row {{
                    display: grid; grid-template-columns: 120px 1fr 80px;
                    gap: 0.5rem; align-items: center; padding: 0.6rem 0;
                    border-bottom: 1px solid #f1f5f9;
                }}
                .ws-tend-row:last-child {{ border-bottom: none; }}
                .ws-tend-asset {{ font-weight: 600; font-size: 0.9rem; }}
                .ws-tend-tendency {{ font-size: 0.85rem; color: var(--text-secondary); }}
                .ws-tend-conf {{ font-size: 0.75rem; font-weight: 600; text-align: center; padding: 2px 8px; border-radius: 4px; }}
                .ws-conf-medium {{ background: #fef3c7; color: #92400e; }}
                .ws-conf-low {{ background: #f1f5f9; color: #64748b; }}
                @media (max-width: 768px) {{
                    .ws-charts-row {{ grid-template-columns: 1fr 1fr; }}
                    .ws-mini-chart {{ height: 150px; }}
                    .ws-mini-chart-wrap {{ height: 100px; }}
                    .ws-panel {{ padding: 1rem; }}
                }}
                @media (max-width: 640px) {{
                    .ws-asset-row {{ grid-template-columns: 1fr; gap: 0.25rem; }}
                    .ws-asset-context {{ padding-left: 0; }}
                    .ws-overview-grid {{ grid-template-columns: 1fr; }}
                    .ws-tend-row {{ grid-template-columns: 1fr; gap: 0.25rem; }}
                    .ws-charts-row {{ grid-template-columns: 1fr; }}
                    .ws-mini-chart {{ height: 180px; }}
                    .ws-mini-chart-wrap {{ height: 130px; }}
                }}
            </style>

            <div class="ws-header">
                <h2>📊 Weekly Risk Snapshot</h2>
                <p>How European energy risk evolved this week and how markets responded.</p>
            </div>

            <div class="ws-overview-card">
                <div class="ws-overview-title">⚡ Weekly EERI Overview</div>
                <div class="ws-overview-week">Week: {week_label}</div>
                <div class="ws-overview-grid">
                    <div class="ws-overview-stat">
                        <div class="ws-overview-label">Average Risk</div>
                        <div class="ws-overview-value" style="color: {band_color};">{avg_val} <span style="font-size: 0.8rem;">({avg_band})</span></div>
                    </div>
                    <div class="ws-overview-stat">
                        <div class="ws-overview-label">Trend vs Prior Week</div>
                        <div class="ws-overview-value" style="color: {trend_color};">{trend_arrow} {trend_label}</div>
                    </div>
                    <div class="ws-overview-stat">
                        <div class="ws-overview-label">Weekly High</div>
                        <div class="ws-overview-value">{high_val} <span class="ws-overview-sub">({high_day})</span></div>
                    </div>
                    <div class="ws-overview-stat">
                        <div class="ws-overview-label">Weekly Low</div>
                        <div class="ws-overview-value">{low_val} <span class="ws-overview-sub">({low_day})</span></div>
                    </div>
                </div>
            </div>

            <div class="ws-panel">
                <div class="ws-panel-title">Risk Regime Distribution</div>
                {regime_html}
            </div>

            <div class="ws-panel">
                <div class="ws-panel-title">Cross-Asset Risk Confirmation</div>
                <p style="font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 0.75rem;">Did markets validate the risk environment this week?</p>
                {assets_html}
            </div>

            <div class="ws-charts-row">
                {charts_html}
            </div>

            <div class="ws-divergence-badge {div_cls}">
                <span class="ws-div-icon">{div_icon}</span>
                <span class="ws-div-title">{div_label}</span>
                <div class="ws-div-text">{div_narrative}</div>
            </div>

            <div class="ws-hist-box">
                <div class="ws-panel-title">Historical Context</div>
                <p style="font-size: 0.9rem; color: var(--text-secondary);">Historically, weeks where EERI spends multiple days in <strong>{ov['band']}</strong> territory are associated with:</p>
                <ul>{hist_items}</ul>
            </div>

            <div class="ws-panel">
                <div class="ws-panel-title">Next-Week Historical Tendencies <span style="font-size: 0.75rem; color: var(--text-secondary); font-weight: 400;">(Not Forecasts)</span></div>
                {tend_html}
            </div>

            <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
            <script>
            (function() {{
                if (typeof Chart === 'undefined') return;
                try {{
                    var chartData = {chart_json};
                    {chart_init_js}
                }} catch(e) {{ console.error('Chart init error:', e); }}
            }})();
            </script>
        </div>'''


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
    - Weekly snapshot
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
            {get_digest_dark_styles()}
        </head>
        <body>
            <nav class="nav"><div class="nav-inner">
                <a href="/" class="logo"><img src="/static/logo.png" alt="EnergyRiskIQ" width="36" height="36" style="margin-right: 0.5rem;">EnergyRiskIQ</a>
                <button class="mobile-menu-btn" onclick="document.querySelector('.nav-links').classList.toggle('open')" aria-label="Menu">
                    <span></span><span></span><span></span>
                </button>
                <div class="nav-links">
                    <a href="/geri">GERI</a>
                    <a href="/eeri">EERI</a>
                    <a href="/egsi">EGSI</a>
                    <a href="/daily-geo-energy-intelligence-digest">Digest</a>
                    <a href="/daily-geo-energy-intelligence-digest/history">History</a>
                    <a href="/users" class="cta-btn-nav">Get FREE Access</a>
                </div>
            </div></nav>
            <main>
                <div class="container">
                    <div class="breadcrumbs">
                        <a href="/">Home</a> / European Energy Risk Index
                    </div>
                    <h1 style="font-size: 1.75rem; color: #f1f5f9; text-align: center; margin-bottom: 0.5rem;">European Energy Risk Index (EERI)</h1>
                    <p style="color: #94a3b8; text-align: center; margin-bottom: 2rem;">A daily composite measure of systemic geopolitical and supply-chain risk in European energy markets.</p>
                    <div style="text-align: center; padding: 3rem 1rem; color: #94a3b8;">
                        <h2 style="color: #f1f5f9; font-size: 1.25rem; margin-bottom: 0.5rem;">EERI Data Coming Soon</h2>
                        <p>EERI data is being computed. Check back shortly.</p>
                        <p style="margin-top: 1rem;"><a href="/users" class="cta-btn-nav" style="display: inline-block; padding: 12px 32px; font-size: 16px;">Sign up for alerts</a></p>
                    </div>
                </div>
            </main>
            {render_digest_footer()}
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
    
    top_drivers = eeri.get('top_drivers', [])
    components = eeri.get('components', {})
    index_date = eeri.get('date', date.today().isoformat())
    
    # Use stored interpretation (unique per day), fallback to generation only if missing
    interpretation = eeri.get('explanation') or eeri.get('interpretation')
    if not interpretation:
        interpretation = generate_eeri_interpretation(
            value=eeri['value'],
            band=eeri['band'],
            drivers=top_drivers[:5] if top_drivers else [],
            components=components,
            index_date=index_date
        )
    interpretation_html = ''.join(f'<p>{para}</p>' for para in interpretation.split('\n\n') if para.strip())
    
    current_band = eeri['band']
    band_classes = {
        'LOW': 'low',
        'MODERATE': 'moderate',
        'ELEVATED': 'elevated',
        'SEVERE': 'severe',
        'CRITICAL': 'critical',
    }
    
    def band_active(band_name):
        return 'active' if current_band == band_name else ''
    
    index_date = eeri.get('date', date.today().isoformat())
    # Format index date nicely (the date the index is FOR - 24h delayed)
    try:
        index_date_obj = datetime.fromisoformat(index_date) if isinstance(index_date, str) else index_date
        index_date_display = index_date_obj.strftime('%B %d, %Y')
    except:
        index_date_display = index_date
    
    computed_at = eeri.get('computed_at', '')
    if computed_at:
        try:
            computed_dt = datetime.fromisoformat(str(computed_at).replace('Z', '+00:00'))
            computed_display = computed_dt.strftime('%B %d, %Y') + ', 01:00 UTC'
        except:
            computed_display = str(computed_at).split('T')[0] if 'T' in str(computed_at) else str(computed_at)
    else:
        computed_display = 'Daily at 01:00 UTC'
    
    trend_display = ""
    if eeri.get('trend_7d') is not None:
        trend_val = eeri['trend_7d']
        trend_sign = "+" if trend_val > 0 else ""
        trend_display = f'<div class="index-trend" style="color: #4ade80;">7-Day Trend: {trend_label} ({trend_sign}{trend_val:.0f})</div>'
    
    delay_badge = '<div class="index-delay-badge">24h delayed • Real-time access with subscription</div>'
    
    weekly_snapshot = get_weekly_snapshot()
    weekly_snapshot_html = _build_weekly_snapshot_html(weekly_snapshot)
    
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
        {get_digest_dark_styles()}
        <style>
            .eeri-hero {{
                text-align: center;
                padding: 2rem 0 1rem 0;
            }}
            .eeri-hero h1 {{
                font-size: 1.75rem;
                margin-bottom: 0.5rem;
                color: #f1f5f9;
            }}
            .eeri-hero p {{
                color: #94a3b8;
                max-width: 600px;
                margin: 0 auto;
                font-size: 0.95rem;
            }}
            .eeri-hero .methodology-link {{
                margin-top: 0.75rem;
            }}
            .eeri-hero .methodology-link a {{
                color: #60a5fa;
                text-decoration: none;
                font-size: 0.9rem;
            }}
            .eeri-hero .methodology-link a:hover {{
                color: #93c5fd;
                text-decoration: underline;
            }}
            .index-metric-card {{
                background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
                border: 1px solid #334155;
                border-radius: 12px;
                padding: 1.5rem 2rem;
                text-align: center;
                max-width: 420px;
                margin: 1.5rem auto;
            }}
            .index-header {{
                display: flex;
                align-items: center;
                gap: 0.5rem;
                justify-content: center;
                margin-bottom: 0.5rem;
            }}
            .index-icon {{ font-size: 1.25rem; }}
            .index-title {{
                font-size: 1rem;
                font-weight: 600;
                color: #f1f5f9;
            }}
            .index-value {{
                font-size: 1.5rem;
                font-weight: 700;
                margin: 0.5rem 0;
            }}
            .index-scale-ref {{
                font-size: 0.75rem;
                color: #64748b;
                margin-bottom: 0.5rem;
            }}
            .index-trend {{
                font-size: 0.9rem;
                margin-bottom: 0.5rem;
            }}
            .index-meta {{
                margin-top: 0.75rem;
                padding-top: 0.75rem;
                border-top: 1px solid #334155;
            }}
            .index-meta-row {{
                display: flex;
                justify-content: space-between;
                padding: 0.25rem 0;
                font-size: 0.85rem;
            }}
            .meta-label {{ color: #64748b; }}
            .meta-value {{ color: #e2e8f0; font-weight: 500; }}
            .index-delay-badge {{
                background: rgba(251, 191, 36, 0.12);
                border: 1px solid rgba(251, 191, 36, 0.3);
                color: #fbbf24;
                border-radius: 20px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: 600;
                text-align: center;
                margin: 1.25rem 0;
            }}
            .index-sections {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
                gap: 1rem;
                margin: 1.25rem 0;
            }}
            .index-section {{
                background: #1e293b;
                border: 1px solid #334155;
                border-radius: 12px;
                padding: 1.25rem;
            }}
            .section-header-blue {{
                color: #60a5fa !important;
                font-size: 0.95rem;
                margin-bottom: 0.75rem;
                font-weight: 600;
            }}
            .index-list {{
                list-style: disc;
                padding-left: 1.25rem;
                color: #cbd5e1;
            }}
            .index-list li {{
                margin-bottom: 0.6rem;
                line-height: 1.4;
                font-size: 0.9rem;
            }}
            .driver-headline {{ color: #e2e8f0; }}
            .region-label {{
                color: #64748b;
                font-size: 0.8rem;
            }}
            .regions-list {{ list-style: disc; padding-left: 1.25rem; color: #cbd5e1; }}
            .regions-list li {{ margin-bottom: 0.5rem; font-size: 0.9rem; }}
            .assets-grid {{
                display: flex;
                flex-wrap: wrap;
                gap: 0.5rem;
            }}
            .asset-tag {{
                background: rgba(96, 165, 250, 0.12);
                color: #60a5fa;
                padding: 0.3rem 0.75rem;
                border-radius: 6px;
                font-size: 0.8rem;
                font-weight: 500;
            }}
            .risk-bands-section {{
                margin: 1.25rem 0;
            }}
            .risk-bands-container {{
                display: flex;
                flex-direction: column;
                gap: 0.4rem;
            }}
            .risk-band-row {{
                display: flex;
                align-items: center;
                gap: 0.75rem;
                padding: 0.4rem 0.75rem;
                border-radius: 6px;
                font-size: 0.85rem;
            }}
            .risk-band-row.active {{
                background: rgba(96, 165, 250, 0.1);
                border: 1px solid rgba(96, 165, 250, 0.3);
            }}
            .band-range {{ color: #64748b; font-size: 0.8rem; min-width: 40px; }}
            .band-indicator {{
                width: 12px;
                height: 12px;
                border-radius: 50%;
            }}
            .band-indicator.low {{ background: #22c55e; }}
            .band-indicator.moderate {{ background: #eab308; }}
            .band-indicator.elevated {{ background: #f97316; }}
            .band-indicator.severe {{ background: #ef4444; }}
            .band-indicator.critical {{ background: #dc2626; }}
            .band-name {{ color: #e2e8f0; }}
            .current-position {{
                margin-top: 0.75rem;
                font-size: 0.85rem;
                color: #94a3b8;
                text-align: center;
            }}
            .index-interpretation {{
                background: #1e293b;
                border: 1px solid #334155;
                border-radius: 12px;
                padding: 1.25rem;
                margin: 1.25rem 0;
            }}
            .index-interpretation p {{
                color: #cbd5e1;
                font-size: 0.92rem;
                line-height: 1.65;
                margin: 0 0 0.75rem 0;
            }}
            .index-interpretation p:last-child {{ margin-bottom: 0; }}
            .index-cta {{
                background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
                border: 1px solid rgba(59, 130, 246, 0.3);
                border-radius: 12px;
                padding: 1.5rem;
                text-align: center;
                margin: 1.25rem 0;
            }}
            .index-cta h3 {{
                color: #60a5fa;
                margin-bottom: 0.5rem;
                font-size: 1.1rem;
            }}
            .index-cta p {{
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
            .cta-button.primary:hover {{ opacity: 0.9; }}
            .index-links {{
                text-align: center;
                margin: 1.5rem 0;
                display: flex;
                justify-content: center;
                gap: 1.5rem;
                flex-wrap: wrap;
            }}
            .index-links a {{
                color: #60a5fa;
                text-decoration: none;
                font-size: 0.9rem;
                font-weight: 500;
            }}
            .index-links a:hover {{
                text-decoration: underline;
                color: #93c5fd;
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
            .source-attribution a:hover {{ text-decoration: underline; }}
            :root {{
                --text-primary: #f1f5f9;
                --text-secondary: #94a3b8;
                --border: #334155;
                --bg-white: #1e293b;
                --bg-light: #0f172a;
            }}
            .ws-panel {{
                background: #1e293b !important;
                border-color: #334155 !important;
            }}
            .ws-hist-box {{
                background: #1e293b !important;
                border-color: #334155 !important;
            }}
            .ws-mini-chart {{
                background: #1e293b !important;
                border-color: #334155 !important;
            }}
            .ws-regime-bar-track {{
                background: #334155 !important;
            }}
            .ws-asset-row {{
                border-bottom-color: #334155 !important;
            }}
            .ws-tend-row {{
                border-bottom-color: #334155 !important;
            }}
            .ws-div-confirming {{
                background: rgba(34, 197, 94, 0.1) !important;
                border-color: rgba(34, 197, 94, 0.3) !important;
                color: #4ade80 !important;
            }}
            .ws-div-mixed {{
                background: rgba(234, 179, 8, 0.1) !important;
                border-color: rgba(234, 179, 8, 0.3) !important;
                color: #fbbf24 !important;
            }}
            .ws-div-diverging {{
                background: rgba(239, 68, 68, 0.1) !important;
                border-color: rgba(239, 68, 68, 0.3) !important;
                color: #fca5a5 !important;
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
                .index-sections {{ grid-template-columns: 1fr; }}
                .eeri-hero h1 {{ font-size: 1.35rem; }}
                .container {{ padding: 0 0.75rem; }}
            }}
            @media (max-width: 600px) {{
                .index-sections {{ grid-template-columns: 1fr; }}
            }}
        </style>
    </head>
    <body>
        <nav class="nav"><div class="nav-inner">
            <a href="/" class="logo"><img src="/static/logo.png" alt="EnergyRiskIQ" width="36" height="36" style="margin-right: 0.5rem;">EnergyRiskIQ</a>
            <button class="mobile-menu-btn" onclick="document.querySelector('.nav-links').classList.toggle('open')" aria-label="Menu">
                <span></span><span></span><span></span>
            </button>
            <div class="nav-links">
                <a href="/geri">GERI</a>
                <a href="/eeri">EERI</a>
                <a href="/egsi">EGSI</a>
                <a href="/daily-geo-energy-intelligence-digest">Digest</a>
                <a href="/daily-geo-energy-intelligence-digest/history">History</a>
                <a href="/users" class="cta-btn-nav">Get FREE Access</a>
            </div>
        </div></nav>
        
        <main>
            <div class="container">
                <div class="breadcrumbs">
                    <a href="/">Home</a> / European Energy Risk Index
                </div>
                <div class="eeri-hero">
                    <h1>European Energy Risk Index (EERI)</h1>
                    <p>A daily composite measure of systemic geopolitical and supply-chain risk in European energy markets.</p>
                    <p class="methodology-link"><a href="/eeri/methodology">(EERI Methodology &amp; Construction)</a></p>
                </div>
                
                <div class="index-metric-card">
                    <div class="index-header">
                        <span class="index-icon">⚡</span>
                        <span class="index-title">European Energy Risk Index:</span>
                    </div>
                    <div class="index-value" style="color: {band_color};">{eeri['value']} / 100 ({eeri['band']})</div>
                    <div class="index-scale-ref">0 = minimal risk · 100 = extreme systemic stress</div>
                    {trend_display}
                    <div class="index-meta">
                        <div class="index-meta-row"><span class="meta-label">Index Date:</span> <span class="meta-value">{index_date_display}</span></div>
                        <div class="index-meta-row"><span class="meta-label">Computed At:</span> <span class="meta-value">{computed_display}</span></div>
                        <div class="index-meta-row"><span class="meta-label">Update Frequency:</span> <span class="meta-value">Daily</span></div>
                    </div>
                </div>
                
                <div class="index-sections">
                    <div class="index-section">
                        <h2 class="section-header-blue">Primary Risk Drivers:</h2>
                        <ul class="index-list">{drivers_html}</ul>
                        <p class="source-attribution" style="font-size: 0.8rem; color: #64748b; margin-top: 0.75rem; font-style: italic;">(Based on recent EnergyRiskIQ alerts) <a href="/alerts" style="color: #2563eb;">View alerts &rarr;</a></p>
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
                
                <div class="index-section risk-bands-section" style="margin: 1.5rem 0;">
                    <h2 class="section-header-blue">📈 Risk Level Bands:</h2>
                    <div class="risk-bands-container">
                        <div class="risk-band-row {'active' if eeri['band'] == 'LOW' else ''}">
                            <span class="band-range">0–20</span>
                            <span class="band-indicator low"></span>
                            <span class="band-name">Low</span>
                        </div>
                        <div class="risk-band-row {'active' if eeri['band'] == 'MODERATE' else ''}">
                            <span class="band-range">21–40</span>
                            <span class="band-indicator moderate"></span>
                            <span class="band-name">Moderate</span>
                        </div>
                        <div class="risk-band-row {'active' if eeri['band'] == 'ELEVATED' else ''}">
                            <span class="band-range">41–60</span>
                            <span class="band-indicator elevated"></span>
                            <span class="band-name">Elevated</span>
                        </div>
                        <div class="risk-band-row {'active' if eeri['band'] == 'SEVERE' else ''}">
                            <span class="band-range">61–80</span>
                            <span class="band-indicator severe"></span>
                            <span class="band-name">Severe</span>
                        </div>
                        <div class="risk-band-row {'active' if eeri['band'] == 'CRITICAL' else ''}">
                            <span class="band-range">81–100</span>
                            <span class="band-indicator critical"></span>
                            <span class="band-name">Critical</span>
                        </div>
                    </div>
                    <div class="current-position">
                        Current position: <strong style="color: {band_color};">{eeri['band']}</strong> ({eeri['value']})
                    </div>
                </div>
                
                {weekly_snapshot_html}
                
                <div class="index-interpretation">
                    {interpretation_html}
                </div>
                
                {delay_badge}
                
                <div class="index-cta">
                    <h3>Get Real-time Access</h3>
                    <p>Unlock instant EERI updates with a Pro subscription.</p>
                    <a href="/users" class="cta-button primary">Unlock Real-time EERI</a>
                </div>
                
                <div class="index-links">
                    <a href="/eeri/history">EERI History</a>
                    <a href="/eeri/methodology">Methodology</a>
                </div>
            </div>
        </main>
        
        {render_digest_footer()}
    </body>
    </html>
    """
    
    return HTMLResponse(content=html)


@router.get("/eeri/updates", response_class=HTMLResponse)
async def eeri_updates_page():
    """
    EERI Updates Page - Shows changelog and updates to the EERI index methodology.
    """
    updates = [
        {
            "date": "2026-01-31",
            "version": "1.1",
            "title": "Public Interpretation",
            "description": "Added daily interpretation to EERI public pages. Each day's index now includes a unique, contextual analysis explaining current European energy risk levels and contributing factors.",
            "type": "enhancement"
        },
        {
            "date": "2026-01-24",
            "version": "1.0",
            "title": "EERI Launch",
            "description": "Initial release of the Europe Energy Risk Index. The index provides a daily composite measure of European energy market stress using RERI, theme pressure, asset transmission, and contagion factors.",
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
        <title>EERI Updates & Changelog | EnergyRiskIQ</title>
        <meta name="description" content="Track updates, enhancements, and changes to the Europe Energy Risk Index (EERI) methodology and calculation.">
        <link rel="canonical" href="{BASE_URL}/eeri/updates">
        <link rel="icon" type="image/png" href="/static/favicon.png">
        
        <meta property="og:title" content="EERI Updates & Changelog | EnergyRiskIQ">
        <meta property="og:description" content="Stay informed about updates to the Europe Energy Risk Index methodology.">
        <meta property="og:type" content="website">
        <meta property="og:url" content="{BASE_URL}/eeri/updates">
        
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
                <a href="/users" class="cta-nav">Get FREE Access</a>
            </div>
        </div></nav>
        
        <main>
            <div class="container">
                <div class="updates-hero">
                    <h1>EERI Updates & Changelog</h1>
                    <p>Track the latest updates, enhancements, and changes to the Europe Energy Risk Index methodology and calculation.</p>
                </div>
                
                <div class="updates-container">
                    {updates_html}
                </div>
                
                <div class="updates-nav">
                    <a href="/eeri">Current EERI</a>
                    <a href="/eeri/history">History</a>
                    <a href="/eeri/methodology">Methodology</a>
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


@router.get("/eeri/methodology", response_class=HTMLResponse)
async def eeri_methodology_page():
    """
    EERI Methodology Page - Comprehensive SEO content explaining the European Energy Risk Index.
    """
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>EERI Methodology - European Energy Risk Index | EnergyRiskIQ</title>
        <meta name="description" content="Complete methodology for the European Energy Risk Index (EERI). Understand the four-pillar architecture, risk bands, source intelligence, normalisation strategy, and interpretation framework behind Europe's leading energy risk indicator.">
        <link rel="canonical" href="{BASE_URL}/eeri/methodology">

        <meta property="og:title" content="EERI Methodology — European Energy Risk Index | EnergyRiskIQ">
        <meta property="og:description" content="Full methodology for the European Energy Risk Index (EERI): four-pillar architecture, risk bands, computation cadence, interpretation framework, and model governance.">
        <meta property="og:url" content="{BASE_URL}/eeri/methodology">
        <meta property="og:type" content="article">

        <meta name="twitter:card" content="summary_large_image">
        <meta name="twitter:title" content="EERI Methodology — European Energy Risk Index">
        <meta name="twitter:description" content="How EnergyRiskIQ measures daily European energy disruption risk across geopolitical, supply, and market transmission forces.">

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
            .pillar-card.reserved {{
                border-style: dashed;
                opacity: 0.85;
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
        <nav class="nav"><div class="container nav-inner">
            <a href="/" class="logo"><img src="/static/logo.png" alt="EnergyRiskIQ" width="32" height="32" style="margin-right: 0.5rem; vertical-align: middle;">EnergyRiskIQ</a>
            <div class="nav-links">
                <a href="/alerts">Alerts</a>
                <a href="/geri">GERI</a>
                <a href="/eeri">EERI</a>
                <a href="/egsi">EGSI</a>
                <a href="/users" class="cta-nav">Get FREE Access</a>
            </div>
        </div></nav>

        <main class="container">

            <div class="meth-hero">
                <h1>EERI Methodology</h1>
                <p class="subtitle">A comprehensive overview of how the European Energy Risk Index measures daily exposure to energy disruption risk across geopolitical, supply, and market transmission forces.</p>
                <div class="version-badge">Model Version: v1 &nbsp;|&nbsp; Last Updated: February 2026</div>
            </div>

            <section class="meth-section">
                <h2><span class="section-num">1.</span> What Is EERI?</h2>
                <div class="meth-body">
                    <p>The <strong>European Energy Risk Index (EERI)</strong> is a proprietary composite index that measures Europe's daily exposure to energy disruption risk arising from geopolitical, supply, and market transmission forces. It answers one critical question:</p>
                    <div class="meth-blockquote">"How dangerous is the European energy environment today, and where is the stress coming from?"</div>
                    <p>EERI is the first regional index in the EnergyRiskIQ platform, built on top of the Regional Escalation Risk Index (RERI) framework. Where GERI provides a global risk temperature, EERI zooms into Europe specifically — the region most acutely sensitive to gas supply disruption, pipeline dependency, and geopolitical spillover from neighbouring conflict zones.</p>
                    <p>EERI is designed for energy traders, gas desk analysts, LNG procurement teams, European utility risk managers, freight planners, and institutional investors with European energy exposure. It translates complex, multi-source intelligence into an actionable daily signal that sits between raw news and formal market analysis.</p>
                </div>
            </section>

            <section class="meth-section">
                <h2><span class="section-num">2.</span> Index Architecture</h2>
                <div class="meth-body">
                    <h3>Scoring Range</h3>
                    <p>EERI produces a daily value on a <strong>0 to 100</strong> scale. A value of 0 represents a theoretical state of zero energy disruption risk for Europe, while 100 represents a theoretical state of maximum systemic energy crisis. The scale is normalised against a rolling historical baseline, ensuring the range remains calibrated to conditions actually observed in the European energy landscape.</p>

                    <h3>Risk Bands</h3>
                    <p>Each daily EERI value maps to one of five risk bands:</p>
                    <table class="meth-table">
                        <thead><tr><th>Risk Band</th><th>Range</th><th>Interpretation</th></tr></thead>
                        <tbody>
                            <tr><td><span class="band-dot" style="background:#22c55e;"></span><strong>LOW</strong></td><td>0 – 20</td><td>European energy environment is calm. No significant geopolitical or supply disruption signals are active. Standard operations can proceed without elevated monitoring.</td></tr>
                            <tr><td><span class="band-dot" style="background:#eab308;"></span><strong>MODERATE</strong></td><td>21 – 40</td><td>Background risk is present. Some supply concerns, regional tensions, or policy uncertainties exist, but systemic disruption is not indicated. Routine monitoring is appropriate.</td></tr>
                            <tr><td><span class="band-dot" style="background:#f97316;"></span><strong>ELEVATED</strong></td><td>41 – 60</td><td>Meaningful risk accumulation detected across European energy markets. Multiple stress vectors are contributing simultaneously. Active monitoring and hedging consideration are warranted.</td></tr>
                            <tr><td><span class="band-dot" style="background:#ef4444;"></span><strong>SEVERE</strong></td><td>61 – 80</td><td>Significant systemic stress affecting European energy security. Risk signals are converging across supply, transit, and market channels. Active hedging and contingency planning are strongly advised.</td></tr>
                            <tr><td><span class="band-dot" style="background:#991b1b;"></span><strong>CRITICAL</strong></td><td>81 – 100</td><td>Critical systemic stress. Risk signals have converged across all major channels. Historical precedent indicates imminent or active market disruption. Defensive positioning and emergency protocols are strongly indicated.</td></tr>
                        </tbody>
                    </table>

                    <h3>Trend Indicators</h3>
                    <p>Each daily EERI reading includes two trend signals:</p>
                    <ul>
                        <li><strong>1-Day Trend</strong> — Change from the previous day's value, showing immediate momentum</li>
                        <li><strong>7-Day Trend</strong> — Change from seven days prior, showing directional trajectory</li>
                    </ul>
                    <p>These trends are essential for distinguishing between an EERI of 70 that is rising sharply (escalation phase) and an EERI of 70 that is falling from a recent peak (stabilisation phase). The same number carries very different operational implications depending on its trajectory.</p>
                </div>
            </section>

            <section class="meth-section">
                <h2><span class="section-num">3.</span> The Four Pillars</h2>
                <div class="meth-body">
                    <p>EERI is constructed from four distinct pillars, each capturing a different dimension of European energy risk. This multi-pillar architecture ensures the index reflects the full spectrum of forces that can disrupt European energy markets.</p>
                </div>
                <div class="pillar-grid">
                    <div class="pillar-card">
                        <div class="pillar-icon">🏗️</div>
                        <div class="pillar-subtitle">Pillar 1</div>
                        <div class="pillar-name">Regional Risk Backbone</div>
                        <div class="pillar-desc">The structural foundation of EERI. Measures the underlying severity, intensity, and acceleration of geopolitical and energy events directly affecting Europe.</div>
                        <ul class="pillar-measures">
                            <li><strong>Severity Pressure</strong> — Cumulative severity of high-impact events affecting Europe</li>
                            <li><strong>High-Impact Concentration</strong> — Escalation stacking from simultaneous events</li>
                            <li><strong>Asset Overlap</strong> — Number of asset classes simultaneously under stress</li>
                            <li><strong>Escalation Velocity</strong> — Rate of change vs. recent historical average</li>
                        </ul>
                        <div class="pillar-why">Answers: "How dangerous is the European geopolitical and energy environment right now?"</div>
                    </div>
                    <div class="pillar-card">
                        <div class="pillar-icon">📊</div>
                        <div class="pillar-subtitle">Pillar 2</div>
                        <div class="pillar-name">Theme Pressure</div>
                        <div class="pillar-desc">Measures the nature and breadth of stress narratives dominating the European risk landscape — whether risk is concentrated in one narrative or spread across multiple themes simultaneously.</div>
                        <ul class="pillar-measures">
                            <li>Type of events driving risk (military, supply, sanctions, policy, logistics, diplomacy)</li>
                            <li>Breadth of thematic coverage across stress categories</li>
                            <li>Structural persistence of recurring narratives</li>
                        </ul>
                        <div class="pillar-why">Answers: "What kind of crisis is this?" — critical for choosing the right hedging strategy.</div>
                    </div>
                    <div class="pillar-card">
                        <div class="pillar-icon">🔗</div>
                        <div class="pillar-subtitle">Pillar 3</div>
                        <div class="pillar-name">Asset Transmission</div>
                        <div class="pillar-desc">Measures whether risk is actually propagating into European energy markets — bridging the gap between geopolitical headlines and financial reality.</div>
                        <ul class="pillar-measures">
                            <li>Number and breadth of energy asset classes showing stress</li>
                            <li>Cross-asset transmission patterns (Gas, Oil, Freight, FX, Power, LNG)</li>
                            <li>Alignment between risk events and market-observable stress</li>
                        </ul>
                        <div class="pillar-why">Answers: "Is this risk actually reaching markets?" — the bridge between headlines and money.</div>
                    </div>
                    <div class="pillar-card reserved">
                        <div class="pillar-icon">🌍</div>
                        <div class="pillar-subtitle">Pillar 4 — Reserved for v2</div>
                        <div class="pillar-name">Contagion</div>
                        <div class="pillar-desc">Will measure cross-regional spillover risk — the degree to which energy-relevant crises in neighbouring regions (Middle East, Black Sea / Caucasus) threaten to spread into Europe.</div>
                        <ul class="pillar-measures">
                            <li>Risk transmission from primary oil and LNG supply regions</li>
                            <li>Pipeline and shipping route vulnerability from adjacent conflict zones</li>
                            <li>Second-order effects from non-European disruptions</li>
                        </ul>
                        <div class="pillar-why">In v1, structurally present but set to zero. Will activate when mature regional indices are available.</div>
                    </div>
                </div>
            </section>

            <section class="meth-section">
                <h2><span class="section-num">4.</span> Source Intelligence</h2>
                <div class="meth-body">
                    <h3>Regional Focus</h3>
                    <p>EERI ingests events classified as affecting Europe, the European Union, or European energy infrastructure. Classification uses both explicit geographic tagging and entity recognition — events mentioning European pipelines, terminals, storage facilities, or regulatory bodies are included even if tagged to a broader region.</p>

                    <h3>Alert Types</h3>
                    <p>EERI consumes three categories of structured alerts from the EnergyRiskIQ intelligence pipeline:</p>
                    <ul>
                        <li><strong>High-Impact Events</strong> — Individual events with significant severity representing direct geopolitical or energy shocks (military escalations, infrastructure incidents, sanctions, policy shifts)</li>
                        <li><strong>Regional Risk Spikes</strong> — Synthesised alerts generated when a region's aggregate risk level rises meaningfully above its recent baseline, indicating clustering or escalation</li>
                        <li><strong>Asset Risk Alerts</strong> — Asset-specific alerts triggered when individual energy commodities or infrastructure show stress linked to European risk events</li>
                    </ul>

                    <h3>Event Categories</h3>
                    <p>Events are classified into thematic categories that determine their influence within the index:</p>
                    <table class="meth-table">
                        <thead><tr><th>Category</th><th>Disruption Profile</th></tr></thead>
                        <tbody>
                            <tr><td><strong>War / Military / Conflict</strong></td><td>Highest disruption potential — direct physical threat to energy infrastructure, supply routes, or producing regions</td></tr>
                            <tr><td><strong>Supply Disruption</strong></td><td>High disruption potential — production outages, pipeline stoppages, facility shutdowns, force majeure events</td></tr>
                            <tr><td><strong>Energy</strong></td><td>Significant — broad energy market developments with pricing or supply implications</td></tr>
                            <tr><td><strong>Sanctions</strong></td><td>Significant — trade restrictions affecting energy flows, often with delayed but persistent effects</td></tr>
                            <tr><td><strong>Political</strong></td><td>Moderate — government decisions, elections, or policy changes affecting energy policy</td></tr>
                            <tr><td><strong>Diplomacy</strong></td><td>Lower immediate impact — negotiations, agreements, or de-escalation signals that may reduce future risk</td></tr>
                        </tbody>
                    </table>
                </div>
            </section>

            <section class="meth-section">
                <h2><span class="section-num">5.</span> Normalisation Strategy</h2>
                <div class="meth-body">
                    <p>Raw risk metrics vary enormously depending on the global news cycle and event clustering. Without normalisation, the 0–100 scale would be meaningless — a quiet week could produce values near zero while a single crisis could push values far beyond 100.</p>
                    <p>EERI uses a <strong>multi-phase normalisation</strong> approach that adapts as the index matures:</p>
                    <ul>
                        <li><strong>Bootstrap Phase</strong> — During the initial period with insufficient historical data, EERI uses conservative fallback caps for each component, preventing extreme values while the system accumulates operational history.</li>
                        <li><strong>Rolling Baseline Phase</strong> — Once sufficient history has accumulated, EERI switches to a rolling baseline computed from recent component values. This dynamically adjusts the normalisation range using statistical percentiles of historical data.</li>
                    </ul>
                    <p>The rolling approach ensures the 0–100 scale remains meaningful as the risk environment evolves, prevents compression during prolonged calm or tension, properly reflects unusual conditions, and adapts to structural changes in the risk landscape over time.</p>
                </div>
            </section>

            <section class="meth-section">
                <h2><span class="section-num">6.</span> Computation Cadence</h2>
                <div class="meth-body">
                    <h3>Daily Computation</h3>
                    <p>EERI is computed once per day, producing a single authoritative daily value. The computation runs after all alerts for the previous day have been finalised, ensuring complete data coverage. Daily computation is triggered automatically at <strong>01:00 UTC</strong>.</p>

                    <h3>Publication Tiers</h3>
                    <div class="tier-grid">
                        <div class="tier-card">
                            <div class="tier-label">Paid Subscribers</div>
                            <div class="tier-title">Real-time on computation</div>
                            <ul>
                                <li>Full EERI value, band, and trend</li>
                                <li>Component breakdown and top drivers</li>
                                <li>Asset stress panel</li>
                                <li>AI-generated interpretation</li>
                            </ul>
                        </div>
                        <div class="tier-card">
                            <div class="tier-label">Free Users</div>
                            <div class="tier-title">24-hour delay</div>
                            <ul>
                                <li>EERI value and band</li>
                                <li>Limited context</li>
                            </ul>
                        </div>
                        <div class="tier-card">
                            <div class="tier-label">Public / SEO Pages</div>
                            <div class="tier-title">24-hour delay</div>
                            <ul>
                                <li>EERI value and band</li>
                                <li>Trend indicator</li>
                                <li>Top 2–3 risk driver headlines</li>
                            </ul>
                        </div>
                    </div>
                </div>
            </section>

            <section class="meth-section">
                <h2><span class="section-num">7.</span> Interpretation Framework</h2>
                <div class="meth-body">
                    <h3>EERI as a Regional Decision Layer</h3>
                    <p>EERI is not a price forecast or trading signal. It is a regional risk context layer that tells professionals where European energy stress is concentrated and how it is evolving:</p>
                    <ul>
                        <li><strong>EERI rising</strong> means European energy risk inputs are increasing — it does not guarantee energy prices will rise</li>
                        <li><strong>EERI falling</strong> means risk inputs are subsiding — it does not guarantee market calm</li>
                        <li><strong>EERI in CRITICAL</strong> means the concentration and severity of risk signals matches historical periods associated with significant energy market disruption</li>
                    </ul>

                    <h3>Asset Stress Patterns</h3>
                    <p>One of EERI's most valuable features is its ability to show which specific energy asset classes are absorbing geopolitical stress:</p>
                    <table class="meth-table">
                        <thead><tr><th>Asset</th><th>Role in European Energy Risk</th></tr></thead>
                        <tbody>
                            <tr><td><strong>Gas</strong></td><td>Europe's primary vulnerability indicator. First responder in European energy crises — reacts fastest and most severely to supply disruption signals.</td></tr>
                            <tr><td><strong>Oil</strong></td><td>Global benchmark reflecting broader supply concerns. Typically reacts when events have global implications such as Middle East spillover or sanctions on major producers.</td></tr>
                            <tr><td><strong>Freight</strong></td><td>Physical logistics and shipping route stress. Where geopolitical risk becomes physical reality — often the earliest confirmation signal of systemic disruption.</td></tr>
                            <tr><td><strong>FX (EUR/USD)</strong></td><td>European macro confidence indicator. Currency stress reflects capital positioning and investor confidence in European economic resilience.</td></tr>
                        </tbody>
                    </table>

                    <h3>Cross-Asset Patterns Professionals Watch</h3>
                    <table class="meth-table">
                        <thead><tr><th>Pattern</th><th>Interpretation</th></tr></thead>
                        <tbody>
                            <tr><td><strong>Gas + Freight elevated</strong></td><td>Physical supply chain stress — disruptions are real, not theoretical</td></tr>
                            <tr><td><strong>Oil + FX elevated</strong></td><td>Macro spillover — risk is affecting broader European economic outlook</td></tr>
                            <tr><td><strong>All four asset classes elevated</strong></td><td>Systemic shock — risk has permeated the entire European energy ecosystem</td></tr>
                            <tr><td><strong>Gas elevated, others calm</strong></td><td>Isolated supply concern — markets believe disruption is containable</td></tr>
                        </tbody>
                    </table>

                    <h3>Regime Recognition</h3>
                    <p>EERI's historical trajectory can be divided into recognisable risk regimes. Regime transitions are the most actionable signals in the index.</p>
                    <table class="meth-table">
                        <thead><tr><th>Regime</th><th>Characteristics</th><th>Typical Duration</th></tr></thead>
                        <tbody>
                            <tr><td><strong>Calm</strong></td><td>LOW/MODERATE bands, stable trend, minimal driver activity</td><td>Weeks to months</td></tr>
                            <tr><td><strong>Escalation</strong></td><td>EERI rising, crossing MODERATE to ELEVATED, increasing driver count</td><td>Days to weeks</td></tr>
                            <tr><td><strong>Crisis</strong></td><td>SEVERE/CRITICAL bands, multiple asset classes stressed, high driver concentration</td><td>Days to weeks</td></tr>
                            <tr><td><strong>De-escalation</strong></td><td>EERI falling from CRITICAL/SEVERE, driver intensity decreasing</td><td>Days to weeks</td></tr>
                            <tr><td><strong>Recovery</strong></td><td>Returning to LOW/MODERATE, normalisation of asset stress</td><td>Weeks</td></tr>
                        </tbody>
                    </table>
                </div>
            </section>

            <section class="meth-section">
                <h2><span class="section-num">8.</span> Relationship to Other Indices</h2>
                <div class="meth-body">
                    <h3>EERI and GERI</h3>
                    <p>GERI (Global Geo-Energy Risk Index) and EERI operate at different scales and serve different purposes:</p>
                    <table class="meth-table">
                        <thead><tr><th>Dimension</th><th>GERI</th><th>EERI</th></tr></thead>
                        <tbody>
                            <tr><td><strong>Scope</strong></td><td>Global</td><td>European</td></tr>
                            <tr><td><strong>Core Question</strong></td><td>"Is the world dangerous?"</td><td>"Is Europe's energy security threatened?"</td></tr>
                            <tr><td><strong>Audience</strong></td><td>CIOs, strategists, allocators</td><td>Energy traders, gas desks, European risk managers</td></tr>
                            <tr><td><strong>Decision Type</strong></td><td>Strategic portfolio allocation</td><td>Tactical hedging and procurement</td></tr>
                            <tr><td><strong>Sensitivity</strong></td><td>Broad geopolitical environment</td><td>Europe-specific supply, transit, and market stress</td></tr>
                        </tbody>
                    </table>

                    <h3>Reading Them Together</h3>
                    <ul>
                        <li><strong>GERI high + EERI high:</strong> Global risk is concentrated in or affecting Europe. Maximum concern for European energy exposure.</li>
                        <li><strong>GERI high + EERI moderate:</strong> Global risk exists but Europe is buffered (strong storage, diversified supply, or risk concentrated elsewhere).</li>
                        <li><strong>GERI moderate + EERI high:</strong> Europe-specific risk (internal policy, localised disruption, or transit issues) that hasn't reached global systemic levels.</li>
                    </ul>

                    <h3>Future Regional Indices</h3>
                    <p>EERI is the first implementation of the RERI framework. The same architecture is designed to support future regional indices for the Middle East and Black Sea / Caucasus corridor. When operational, these will activate the EERI Contagion pillar for cross-regional spillover measurement.</p>
                </div>
            </section>

            <section class="meth-section">
                <h2><span class="section-num">9.</span> What EERI Does Not Do</h2>
                <div class="meth-body">
                    <ul>
                        <li><strong>EERI is not a gas price forecast.</strong> It measures the risk environment, not the price outcome.</li>
                        <li><strong>EERI is not a trading signal.</strong> It provides risk context for decision-making, not buy/sell instructions.</li>
                        <li><strong>EERI does not cover non-energy European risks.</strong> Banking crises, public health emergencies, or sovereign debt concerns are outside its scope unless they directly affect energy markets.</li>
                        <li><strong>EERI is not intraday.</strong> It is a daily index. Events occurring during the day will be reflected in the following day's computation.</li>
                        <li><strong>EERI does not measure European energy demand.</strong> It focuses on supply disruption risk and geopolitical stress, not seasonal consumption patterns or economic growth dynamics.</li>
                        <li><strong>EERI is not a substitute for market analysis.</strong> It is a complementary intelligence layer designed to sit alongside traditional energy trading and risk management tools.</li>
                    </ul>
                </div>
            </section>

            <section class="meth-section">
                <h2><span class="section-num">10.</span> Model Governance</h2>
                <div class="meth-body">
                    <h3>Version Control</h3>
                    <p>EERI operates under strict version control. The current production model is <strong>v1</strong>, with the Contagion pillar reserved for v2 activation. All historical data is tagged with its model version, ensuring full auditability and reproducibility.</p>

                    <h3>Feature Flag</h3>
                    <p>EERI computation is controlled by a feature flag, allowing the index to be activated or deactivated without code changes. This ensures operational safety during maintenance or if data quality issues are detected.</p>

                    <h3>Planned Evolution</h3>
                    <ul>
                        <li><strong>v2 — Contagion Activation:</strong> Enable cross-regional spillover measurement from Middle East and Black Sea indices</li>
                        <li><strong>Velocity Normalisation:</strong> Transition escalation velocity to rolling baseline normalisation once sufficient historical data has accumulated</li>
                        <li><strong>Weekly Snapshot Intelligence:</strong> Structured weekly summary with plan-tiered depth, including cross-asset alignment analysis and scenario outlooks</li>
                    </ul>

                    <h3>Independence and Objectivity</h3>
                    <p>EERI is computed algorithmically from structured intelligence inputs. There is no editorial override, manual adjustment, or subjective intervention in the daily index value. The methodology is fixed for each model version, with changes implemented only through formal version upgrades.</p>
                </div>
            </section>

            <div class="meth-cta">
                <h3>Unlock the Full Power of EERI</h3>
                <p>Access real-time EERI values, component breakdowns, historical charts, asset stress panels, and AI-powered interpretations with EnergyRiskIQ Pro.</p>
                <a href="/users" class="cta-button">Get FREE Access</a>
            </div>

            <div class="disclaimer">
                <p>EERI is a proprietary index of EnergyRiskIQ. This methodology document is provided for transparency and educational purposes. It does not constitute financial advice.</p>
                <p>Model Version: v1 &nbsp;|&nbsp; Last Updated: February 2026</p>
            </div>

        </main>

        <footer class="footer">
            <div class="container">
                <p>&copy; 2026 EnergyRiskIQ</p>
                <p style="margin-top: 0.5rem;">
                    <a href="/eeri">EERI Index</a> · <a href="/eeri/history">History</a> · <a href="/geri">GERI</a> · <a href="/egsi">EGSI</a>
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
                <a href="/users" class="cta-nav">Get FREE Access</a>
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
                
                <div class="index-history-nav" style="text-align: center; margin-top: 2rem;">
                    <a href="/eeri" style="color: #60a5fa;">&larr; Back to Today's EERI</a>
                </div>
                
                <div class="data-sources-section" style="margin-top: 2rem; padding-top: 1.5rem; border-top: 1px solid #e2e8f0;">
                    <h4 style="font-size: 0.875rem; font-weight: 600; color: #64748b; margin-bottom: 0.5rem;">Data Sources</h4>
                    <p style="font-size: 0.875rem; color: #475569;">EERI values are computed from European energy risk alerts. <a href="/alerts" style="color: #2563eb;">View recent alerts</a></p>
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
    EERI Daily Snapshot Page - matches main EERI page design.
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
    
    # Snapshot date from 'date' column
    snapshot_date = eeri.get('date', date_str)
    try:
        if isinstance(snapshot_date, str):
            snapshot_dt = datetime.strptime(snapshot_date, '%Y-%m-%d').date()
        else:
            snapshot_dt = snapshot_date
        snapshot_display = snapshot_dt.strftime('%B %d, %Y')
    except:
        snapshot_display = snapshot_date
    
    # Computed date from 'computed_at' column
    computed_at = eeri.get('computed_at')
    if computed_at:
        try:
            if isinstance(computed_at, str):
                computed_dt = datetime.fromisoformat(computed_at.replace('Z', '+00:00'))
            else:
                computed_dt = computed_at
            computed_display = computed_dt.strftime('%B %d, %Y at %H:%M UTC')
        except:
            computed_display = str(computed_at)
    else:
        computed_display = 'N/A'
    
    drivers_html = ""
    for driver in eeri.get('top_drivers', [])[:3]:
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
    
    snapshot_drivers = eeri.get('top_drivers', [])
    snapshot_components = eeri.get('components', {})
    snapshot_index_date = eeri.get('date', date_str)
    
    # Use stored interpretation (unique per day), fallback to generation only if missing
    interpretation = eeri.get('explanation') or eeri.get('interpretation')
    if not interpretation:
        interpretation = generate_eeri_interpretation(
            value=eeri['value'],
            band=eeri['band'],
            drivers=snapshot_drivers[:5] if snapshot_drivers else [],
            components=snapshot_components,
            index_date=snapshot_index_date
        )
    interpretation_html = ''.join(f'<p>{para}</p>' for para in interpretation.split('\n\n') if para.strip())
    
    trend_display = ""
    if eeri.get('trend_7d') is not None:
        trend_val = eeri['trend_7d']
        trend_sign = "+" if trend_val > 0 else ""
        trend_color = "#4ade80" if trend_val <= 0 else "#f87171"
        trend_display = f'<div class="index-trend" style="color: {trend_color};">7-Day Trend: ({trend_sign}{trend_val:.0f})</div>'
    
    nav_html = '<div style="display: flex; justify-content: space-between; margin: 1.5rem 0; padding: 0 1rem;">'
    if adjacent.get('prev'):
        nav_html += f'<a href="/eeri/{adjacent["prev"]}" style="color: #60a5fa; text-decoration: none;">&larr; {adjacent["prev"]}</a>'
    else:
        nav_html += '<span></span>'
    if adjacent.get('next'):
        nav_html += f'<a href="/eeri/{adjacent["next"]}" style="color: #60a5fa; text-decoration: none;">{adjacent["next"]} &rarr;</a>'
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
        <meta name="description" content="European Energy Risk Index for {snapshot_display}. Value: {eeri['value']}, Band: {eeri['band']}. Historical EERI data.">
        <link rel="canonical" href="{BASE_URL}/eeri/{date_str}">
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
                <a href="/users" class="cta-nav">Get FREE Access</a>
            </div>
        </div></nav>
        
        <main>
            <div class="container">
                <div class="index-hero">
                    <h1>European Energy Risk Index (EERI)</h1>
                    <p>Historical snapshot for {snapshot_display}</p>
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
                    <div class="index-date">Date Computed: {computed_display}</div>
                </div>
                
                <div class="index-sections">
                    <div class="index-section">
                        <h2 class="section-header-blue">Primary Risk Drivers:</h2>
                        <ul class="index-list">{drivers_html}</ul>
                        <p class="source-attribution" style="font-size: 0.8rem; color: #64748b; margin-top: 0.75rem; font-style: italic;">(Based on recent EnergyRiskIQ alerts) <a href="/alerts" style="color: #2563eb;">View alerts &rarr;</a></p>
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
                    {interpretation_html}
                </div>
                
                {nav_html}
                
                <div class="index-cta">
                    <h3>Get Real-time Access</h3>
                    <p>Unlock instant EERI updates with a Pro subscription.</p>
                    <a href="/users" class="cta-button primary">Unlock Real-time EERI</a>
                </div>
                
                <div class="index-links">
                    <a href="/eeri/history">History</a> · 
                    <a href="/eeri/methodology">Methodology</a> · 
                    <a href="/eeri">Current EERI</a>
                </div>
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
