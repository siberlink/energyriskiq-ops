"""
WTI Crude Oil Widget — SEO landing page + embeddable iframe widget.

Routes:
  GET /widgets/wti-crude-oil-price     → marketing landing page (SEO + funnel)
  GET /embed/wti-crude-oil-widget      → standalone iframe widget (free, branded)
  GET /embed/wti-crude-oil-widget-pro  → preview-only "pro" widget (visual demo)

Custom-algorithm wording (not "AI"). Fully mobile responsive.
Anti-copy text protection (does NOT block search engines).
"""
import logging
import asyncio
import html as _html
import json as _json
from datetime import datetime, timezone, date as _date

from fastapi import APIRouter
from fastapi.responses import StreamingResponse, HTMLResponse

from src.db.db import execute_production_one, execute_production_query
from src.api.snapshot_routes import _PAGE_CSS, _LOADER_HTML, BAND_COLORS, _safe_float

router = APIRouter()
logger = logging.getLogger(__name__)

BASE_URL    = "https://energyriskiq.com"
WIDGET_PATH = "/embed/wti-crude-oil-widget"
LANDING_URL = f"{BASE_URL}/widgets/wti-crude-oil-price"
DATA_URL    = f"{BASE_URL}/data/wti-crude-oil-price-today"
WTI_COLOR   = "#22d3ee"

PRO_PRICE_EUR = "1.49"


# ─────────────────────────────────────────────────────────────────────────────
# Data
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_widget_data():
    """Lightweight fetch optimised for the widget endpoint."""
    intraday = execute_production_query(
        "SELECT date, hour, price FROM intraday_wti "
        "WHERE price IS NOT NULL "
        "ORDER BY date DESC, hour DESC LIMIT 48"
    ) or []
    intraday = list(reversed(intraday))

    daily = execute_production_query(
        "SELECT date, wti_price, brent_price, brent_wti_spread "
        "FROM oil_price_snapshots "
        "WHERE wti_price IS NOT NULL "
        "ORDER BY date DESC LIMIT 2"
    ) or []

    geri_live = execute_production_one(
        "SELECT value, band, computed_at FROM geri_live ORDER BY id DESC LIMIT 1"
    )

    intraday_brent = execute_production_one(
        "SELECT date, hour, price FROM intraday_brent "
        "WHERE price IS NOT NULL "
        "ORDER BY date DESC, hour DESC LIMIT 1"
    )

    # Daily history (for Pro widget 7D / 30D charts)
    daily_hist = execute_production_query(
        "SELECT date, wti_price FROM oil_price_snapshots "
        "WHERE wti_price IS NOT NULL "
        "ORDER BY date DESC LIMIT 30"
    ) or []
    daily_hist = list(reversed(daily_hist))

    return {
        'intraday': intraday,
        'daily': daily,
        'geri_live': geri_live,
        'intraday_brent': intraday_brent,
        'daily_hist': daily_hist,
    }


def _build_mini_chart_svg(rows, color=WTI_COLOR, height=80, width=320, price_key='price', empty_msg='Awaiting intraday data'):
    """Compact sparkline for the widget. Works for intraday or daily rows."""
    if not rows or len(rows) < 2:
        return (
            f'<svg viewBox="0 0 {width} {height}" '
            f'xmlns="http://www.w3.org/2000/svg" style="width:100%;height:auto;display:block;">'
            f'<text x="{width/2}" y="{height/2+4}" text-anchor="middle" font-size="11" '
            f'fill="#64748b" font-family="Inter,system-ui,sans-serif">{empty_msg}</text>'
            f'</svg>'
        )
    PAD_L, PAD_R, PAD_T, PAD_B = 8, 8, 6, 6
    cw = width - PAD_L - PAD_R
    ch = height - PAD_T - PAD_B
    vals = [float(r[price_key]) for r in rows if r.get(price_key) is not None]
    vmin, vmax = min(vals), max(vals)
    if vmin == vmax:
        vmax = vmin * 1.001 + 0.0001
    rng = vmax - vmin
    n = len(rows)
    pts = []
    for i, r in enumerate(rows):
        x = PAD_L + (i / max(n - 1, 1)) * cw
        y = PAD_T + ch - ((float(r[price_key]) - vmin) / rng) * ch
        pts.append((x, y))
    path_d = 'M ' + ' L '.join(f'{p[0]:.1f} {p[1]:.1f}' for p in pts)
    area_d = path_d + f' L {pts[-1][0]:.1f} {PAD_T+ch:.1f} L {pts[0][0]:.1f} {PAD_T+ch:.1f} Z'
    # Axis labels: first & last values, low/high range hint
    label_first = f'${vals[0]:.2f}'
    label_last  = f'${vals[-1]:.2f}'
    return (
        f'<svg viewBox="0 0 {width} {height}" preserveAspectRatio="none" '
        f'xmlns="http://www.w3.org/2000/svg" style="width:100%;height:auto;display:block;">'
        f'<path d="{area_d}" fill="{color}" opacity="0.14"/>'
        f'<path d="{path_d}" fill="none" stroke="{color}" stroke-width="1.8" '
        f'stroke-linejoin="round" stroke-linecap="round"/>'
        f'<circle cx="{pts[-1][0]:.1f}" cy="{pts[-1][1]:.1f}" r="2.5" fill="{color}"/>'
        f'</svg>'
    )


# ─────────────────────────────────────────────────────────────────────────────
# /embed/wti-crude-oil-widget  — the actual iframe widget (free, branded)
# ─────────────────────────────────────────────────────────────────────────────

def _render_widget_html(data, *, pro=False):
    intraday = data['intraday']
    daily    = data['daily']
    geri     = data['geri_live']
    brent    = data['intraday_brent']
    daily_hist = data.get('daily_hist') or []

    # Price: prefer intraday, fall back to daily
    if intraday:
        price = _safe_float(intraday[-1]['price'])
        ts_date = intraday[-1]['date']
        ts_hour = int(intraday[-1]['hour']) if intraday[-1].get('hour') is not None else None
        ts_str = f"{ts_date.isoformat()} {ts_hour:02d}:00 UTC" if ts_hour is not None else ts_date.isoformat()
    elif daily:
        price = _safe_float(daily[0]['wti_price'])
        ts_str = daily[0]['date'].isoformat() if daily[0].get('date') else ''
    else:
        price, ts_str = 0.0, ''

    # Day-over-day change from daily snapshots
    if len(daily) >= 2:
        prev = _safe_float(daily[1]['wti_price'])
        latest_daily = _safe_float(daily[0]['wti_price'])
        chg = latest_daily - prev
        chg_pct = (chg / prev * 100) if prev else 0.0
    else:
        chg, chg_pct = 0.0, 0.0
    chg_color = '#22c55e' if chg > 0 else '#ef4444' if chg < 0 else '#eab308'
    arrow = '&#9650;' if chg > 0 else '&#9660;' if chg < 0 else '&#9644;'

    # Brent-WTI spread
    spread = None
    if daily:
        s_db = daily[0].get('brent_wti_spread')
        if s_db is not None:
            spread = _safe_float(s_db)
        elif brent and daily[0].get('wti_price'):
            spread = _safe_float(brent['price']) - _safe_float(daily[0]['wti_price'])
    spread_str = f"{spread:+.2f}" if spread is not None else "—"

    # GERI live
    geri_val  = int(round(_safe_float((geri or {}).get('value', 0))))
    geri_band = _html.escape(str((geri or {}).get('band') or 'MODERATE'))
    geri_color = BAND_COLORS.get(geri_band, '#f97316')

    mini = _build_mini_chart_svg(intraday)

    # Pro-only: 7D and 30D daily charts from oil_price_snapshots
    if pro:
        hist_30 = daily_hist[-30:] if daily_hist else []
        hist_7  = daily_hist[-7:]  if daily_hist else []
        chart_30_svg = _build_mini_chart_svg(hist_30, color=WTI_COLOR, height=70, price_key='wti_price', empty_msg='Awaiting daily data')
        chart_7_svg  = _build_mini_chart_svg(hist_7,  color=WTI_COLOR, height=70, price_key='wti_price', empty_msg='Awaiting daily data')
        def _range_meta(rows):
            if not rows: return ('—','—','—')
            vals = [float(r['wti_price']) for r in rows]
            lo, hi = min(vals), max(vals)
            first, last = vals[0], vals[-1]
            chg_p = ((last - first) / first * 100) if first else 0.0
            return (f'${lo:.2f}', f'${hi:.2f}', f'{chg_p:+.2f}%')
        lo7, hi7, ch7 = _range_meta(hist_7)
        lo30, hi30, ch30 = _range_meta(hist_30)
    else:
        chart_30_svg = chart_7_svg = ''
        lo7=hi7=ch7=lo30=hi30=ch30='—'

    # Pro styling vs Free styling
    if pro:
        bg = "transparent"
        card_bg = "linear-gradient(135deg,#020617 0%,#0a0f1d 50%,#0d1525 100%)"
        border = "1px solid rgba(34,211,238,0.35)"
        brand_block = ""
        cite_block = ""
        accent = "#22d3ee"
        title_color = "#f1f5f9"
    else:
        bg = "#0b0f1a"
        card_bg = "linear-gradient(135deg,#0c1322 0%,#0f1a2e 50%,#0c1322 100%)"
        border = "1px solid rgba(34,211,238,0.22)"
        brand_block = (
            f'<a href="{LANDING_URL}" target="_blank" rel="noopener" class="erq-brand">'
            f'<span class="erq-brand-dot"></span>Powered by EnergyRiskIQ'
            f'</a>'
        )
        cite_block = (
            f'<a href="{DATA_URL}" target="_blank" rel="noopener" class="erq-cite">'
            f'View Full Oil Analysis &rarr;</a>'
        )
        accent = WTI_COLOR
        title_color = "#f1f5f9"

    label_pro = '<span class="erq-pro-tag">PRO</span>' if pro else ''

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,follow">
<title>WTI Crude Oil Widget &middot; EnergyRiskIQ</title>
<style>
  *{{box-sizing:border-box;}}
  html,body{{margin:0;padding:0;background:{bg};font-family:Inter,system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:#e2e8f0;-webkit-font-smoothing:antialiased;}}
  .erq-widget{{
    width:100%; max-width:380px; margin:0 auto;
    background:{card_bg};
    border:{border}; border-radius:14px;
    padding:16px 18px 14px;
    position:relative; overflow:hidden;
    user-select:none; -webkit-user-select:none;
  }}
  .erq-widget::before{{
    content:''; position:absolute; top:0; left:0; right:0; height:2px;
    background:linear-gradient(90deg,{accent},rgba(34,211,238,0.15));
  }}
  .erq-head{{
    display:flex; align-items:center; justify-content:space-between;
    margin-bottom:8px; gap:8px;
  }}
  .erq-title{{
    font-size:12px; font-weight:800; color:{title_color};
    letter-spacing:0.4px;
  }}
  .erq-sub{{
    font-size:9.5px; font-weight:700; letter-spacing:1.2px;
    text-transform:uppercase; color:#64748b;
  }}
  .erq-sub-dot{{
    display:inline-block; width:6px; height:6px; border-radius:50%;
    background:{accent}; box-shadow:0 0 6px {accent};
    margin-right:5px; vertical-align:middle;
  }}
  .erq-price-row{{
    display:flex; align-items:baseline; gap:8px; flex-wrap:wrap;
    margin-top:2px;
  }}
  .erq-price{{
    font-size:30px; font-weight:800; color:#fff; line-height:1.05;
    font-variant-numeric:tabular-nums;
  }}
  .erq-price sup{{font-size:14px; font-weight:600; vertical-align:top; margin-top:4px;}}
  .erq-unit{{font-size:10.5px; color:#94a3b8;}}
  .erq-chg{{
    font-size:12.5px; font-weight:700; color:{chg_color};
    margin-top:2px; font-variant-numeric:tabular-nums;
  }}
  .erq-chart{{margin:10px 0 6px;}}
  .erq-meta{{
    display:flex; justify-content:space-between; align-items:center;
    gap:10px; margin-top:6px; flex-wrap:wrap;
  }}
  .erq-risk-pill{{
    font-size:10px; font-weight:800; letter-spacing:1px;
    padding:3px 9px; border-radius:14px; text-transform:uppercase;
    background:rgba(255,255,255,0.04); color:{geri_color};
    border:1px solid {geri_color}33;
    display:inline-flex; align-items:center; gap:5px;
  }}
  .erq-risk-pill::before{{
    content:''; width:6px; height:6px; border-radius:50%;
    background:{geri_color};
  }}
  .erq-spread{{
    font-size:11px; color:#94a3b8; font-variant-numeric:tabular-nums;
  }}
  .erq-spread b{{color:#cbd5e1;}}
  .erq-cite{{
    display:block; text-align:center; margin-top:10px;
    font-size:11px; font-weight:700; color:{accent};
    text-decoration:none; padding:6px 0; letter-spacing:0.3px;
  }}
  .erq-cite:hover{{color:#fff;}}
  .erq-brand{{
    display:block; text-align:center; margin-top:6px;
    font-size:9.5px; color:#475569; text-decoration:none;
    letter-spacing:0.5px;
  }}
  .erq-brand-dot{{
    display:inline-block; width:5px; height:5px; border-radius:50%;
    background:{accent}; margin-right:5px; vertical-align:middle;
  }}
  .erq-brand:hover{{color:#94a3b8;}}
  .erq-pro-tag{{
    font-size:9px; font-weight:800; letter-spacing:1px;
    background:linear-gradient(135deg,#06b6d4,#3b82f6); color:#fff;
    padding:2px 8px; border-radius:10px;
  }}
  .erq-ts{{font-size:9.5px; color:#64748b; margin-top:2px;}}
  .erq-daily-panel{{
    margin-top:12px; padding-top:10px;
    border-top:1px dashed rgba(255,255,255,0.08);
  }}
  .erq-daily-head{{
    display:flex; justify-content:space-between; align-items:center;
    margin-bottom:6px;
  }}
  .erq-daily-label{{
    font-size:9.5px; font-weight:800; letter-spacing:1.2px;
    text-transform:uppercase; color:#94a3b8;
  }}
  .erq-range-toggle{{display:inline-flex; gap:0;}}
  .erq-range-toggle button{{
    background:rgba(255,255,255,0.04); color:#64748b;
    border:1px solid rgba(255,255,255,0.08);
    font-size:9.5px; font-weight:700; padding:3px 9px;
    cursor:pointer; font-family:inherit; letter-spacing:0.5px;
  }}
  .erq-range-toggle button:first-child{{border-radius:5px 0 0 5px;}}
  .erq-range-toggle button:last-child{{border-radius:0 5px 5px 0; border-left:none;}}
  .erq-range-toggle button.active{{
    background:{accent}22; color:{accent};
    border-color:{accent}55;
  }}
  .erq-daily-stats{{
    display:flex; justify-content:space-between; gap:10px;
    font-size:10px; color:#94a3b8; margin-top:4px;
    font-variant-numeric:tabular-nums;
  }}
  .erq-daily-stats b{{color:#cbd5e1; font-weight:700;}}
  .erq-chart-pane{{display:none;}}
  .erq-chart-pane.active{{display:block;}}
  @media (max-width:340px){{
    .erq-price{{font-size:24px;}}
    .erq-widget{{padding:12px 14px;}}
  }}
</style>
</head>
<body>
<div class="erq-widget" role="region" aria-label="WTI Crude Oil Price Widget by EnergyRiskIQ">
  <div class="erq-head">
    <div>
      <div class="erq-title">WTI Crude Oil &middot; Today {label_pro}</div>
      <div class="erq-sub"><span class="erq-sub-dot"></span>Updated Live</div>
    </div>
    <div style="text-align:right;">
      <div class="erq-sub" style="color:{accent};">{'$/' if True else ''}BBL</div>
    </div>
  </div>

  <div class="erq-price-row">
    <div class="erq-price"><sup>$</sup>{price:.2f}</div>
    <div class="erq-unit">/bbl</div>
  </div>
  <div class="erq-chg">{arrow} {chg:+.2f} ({chg_pct:+.2f}%)</div>

  <div class="erq-chart">{mini}</div>

  <div class="erq-meta">
    <span class="erq-risk-pill">GERI {geri_val} &middot; {geri_band}</span>
    <span class="erq-spread"><b>Brent Spread</b> {spread_str}</span>
  </div>

  <div class="erq-ts">Snapshot: {ts_str}</div>

  {('''
  <div class="erq-daily-panel">
    <div class="erq-daily-head">
      <span class="erq-daily-label">Daily Price Chart</span>
      <span class="erq-range-toggle">
        <button type="button" data-range="7"  class="active" id="erqR7">7D</button>
        <button type="button" data-range="30"                id="erqR30">30D</button>
      </span>
    </div>
    <div class="erq-chart-pane active" id="erqPane7">''' + chart_7_svg + f'''
      <div class="erq-daily-stats">
        <span><b>Low</b> {lo7}</span>
        <span><b>High</b> {hi7}</span>
        <span><b>7D Chg</b> {ch7}</span>
      </div>
    </div>
    <div class="erq-chart-pane" id="erqPane30">''' + chart_30_svg + f'''
      <div class="erq-daily-stats">
        <span><b>Low</b> {lo30}</span>
        <span><b>High</b> {hi30}</span>
        <span><b>30D Chg</b> {ch30}</span>
      </div>
    </div>
  </div>
  ''') if pro else ''}

  {cite_block}
  {brand_block}
</div>
<script>
  document.addEventListener('contextmenu',function(e){{e.preventDefault();}});
  (function(){{
    var b7=document.getElementById('erqR7'),b30=document.getElementById('erqR30');
    var p7=document.getElementById('erqPane7'),p30=document.getElementById('erqPane30');
    if(b7&&b30&&p7&&p30){{
      b7.addEventListener('click',function(){{b7.classList.add('active');b30.classList.remove('active');p7.classList.add('active');p30.classList.remove('active');}});
      b30.addEventListener('click',function(){{b30.classList.add('active');b7.classList.remove('active');p30.classList.add('active');p7.classList.remove('active');}});
    }}
  }})();
</script>
</body>
</html>"""


@router.get("/embed/wti-crude-oil-widget")
async def wti_widget_embed():
    try:
        data = await asyncio.to_thread(_fetch_widget_data)
    except Exception as exc:
        logger.error(f"Widget data fetch failed: {exc}", exc_info=True)
        data = {'intraday': [], 'daily': [], 'geri_live': None, 'intraday_brent': None}
    html = _render_widget_html(data, pro=False)
    return HTMLResponse(
        content=html,
        headers={
            "Cache-Control": "public, max-age=120",
            "X-Frame-Options": "ALLOWALL",
            "Content-Security-Policy": "frame-ancestors *;",
        },
    )


@router.get("/embed/wti-crude-oil-widget-pro")
async def wti_widget_embed_pro():
    try:
        data = await asyncio.to_thread(_fetch_widget_data)
    except Exception as exc:
        logger.error(f"Widget data fetch failed: {exc}", exc_info=True)
        data = {'intraday': [], 'daily': [], 'geri_live': None, 'intraday_brent': None}
    html = _render_widget_html(data, pro=True)
    return HTMLResponse(
        content=html,
        headers={
            "Cache-Control": "public, max-age=120",
            "X-Frame-Options": "ALLOWALL",
            "Content-Security-Policy": "frame-ancestors *;",
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# /widgets/wti-crude-oil-price — SEO landing page + funnel
# ─────────────────────────────────────────────────────────────────────────────

_LANDING_CSS = f"""
.wti-w-protected {{ user-select:none; -webkit-user-select:none; }}

/* Hero */
.wti-w-hero{{
  text-align:center; padding:60px 20px 40px;
  background:linear-gradient(180deg,#0b0f1a 0%,#0e1422 100%);
}}
.wti-w-hero h1{{
  font-family:'DM Serif Display',Georgia,serif;
  font-size:clamp(32px,5vw,52px); line-height:1.15;
  margin:0 0 18px; color:#fff;
}}
.wti-w-hero h1 span{{color:{WTI_COLOR};}}
.wti-w-hero p{{
  font-size:clamp(14px,1.6vw,17px); color:#94a3b8;
  max-width:680px; margin:0 auto 26px; line-height:1.65;
}}
.wti-w-cta-row{{
  display:flex; gap:12px; justify-content:center; flex-wrap:wrap; margin-bottom:24px;
}}
.wti-w-cta-primary{{
  background:linear-gradient(135deg,#06b6d4,#3b82f6); color:#fff !important;
  text-decoration:none; font-weight:700; font-size:14.5px;
  padding:13px 26px; border-radius:10px;
  box-shadow:0 6px 24px rgba(34,211,238,0.18);
}}
.wti-w-cta-secondary{{
  background:transparent; color:#cbd5e1 !important;
  border:1px solid rgba(255,255,255,0.18);
  text-decoration:none; font-weight:600; font-size:14px;
  padding:13px 26px; border-radius:10px;
}}
.wti-w-cta-secondary:hover{{border-color:rgba(34,211,238,0.5); color:#fff !important;}}

/* Trust micro-bar */
.wti-w-trust{{
  display:flex; gap:18px; justify-content:center; flex-wrap:wrap;
  font-size:11.5px; color:#94a3b8; max-width:880px; margin:0 auto;
}}
.wti-w-trust span{{display:inline-flex; align-items:center; gap:6px;}}
.wti-w-trust span::before{{
  content:'\u2713'; color:#22c55e; font-weight:800;
}}

/* Section common */
.wti-w-section{{padding:48px 22px; max-width:1100px; margin:0 auto;}}
.wti-w-section h2{{
  font-family:'DM Serif Display',Georgia,serif;
  font-size:clamp(24px,3.5vw,34px); color:#fff; text-align:center;
  margin:0 0 14px;
}}
.wti-w-section h2 + p{{
  text-align:center; color:#94a3b8; max-width:660px; margin:0 auto 32px;
  font-size:14px; line-height:1.65;
}}

/* Widget preview frame */
.wti-w-preview-wrap{{
  display:flex; gap:24px; justify-content:center; align-items:flex-start;
  flex-wrap:wrap;
}}
.wti-w-preview-col{{
  flex:1 1 360px; max-width:420px;
  background:#0e1422; border:1px solid var(--border);
  border-radius:16px; padding:22px;
}}
.wti-w-preview-col h3{{
  font-size:13px; font-weight:800; color:#cbd5e1;
  margin:0 0 14px; letter-spacing:0.5px; text-align:center;
}}
.wti-w-iframe-shell{{
  background:linear-gradient(135deg,#020617,#0a0f1d);
  border-radius:12px; padding:14px;
}}
.wti-w-preview-note{{
  font-size:11px; color:#64748b; margin-top:12px; text-align:center;
}}
.wti-w-preview-pro{{
  position:relative; background:linear-gradient(135deg,#06b6d4 0%,#3b82f6 100%);
  padding:1px; border-radius:17px;
}}
.wti-w-preview-pro .wti-w-preview-col{{margin:0; border:none;}}

/* Embed code box */
.wti-w-embed-box{{
  background:#020617; border:1px solid rgba(34,211,238,0.25);
  border-radius:12px; padding:0;
  max-width:780px; margin:0 auto 14px; overflow:hidden;
}}
.wti-w-embed-head{{
  display:flex; justify-content:space-between; align-items:center;
  padding:10px 16px; border-bottom:1px solid rgba(255,255,255,0.06);
  font-size:11px; font-weight:700; color:#64748b;
  letter-spacing:1px; text-transform:uppercase;
}}
.wti-w-embed-copy{{
  background:rgba(34,211,238,0.15); color:{WTI_COLOR};
  border:1px solid rgba(34,211,238,0.35); border-radius:6px;
  font-size:11px; font-weight:700; padding:5px 14px; cursor:pointer;
  letter-spacing:0.3px;
}}
.wti-w-embed-copy:hover{{background:rgba(34,211,238,0.25);}}
.wti-w-embed-code{{
  font-family:'JetBrains Mono',ui-monospace,monospace;
  font-size:12.5px; color:#94a3b8; line-height:1.7;
  padding:16px 18px; margin:0; white-space:pre-wrap; word-break:break-word;
  overflow-x:auto;
}}
.wti-w-embed-code .tk{{color:{WTI_COLOR};}}
.wti-w-embed-micro{{
  text-align:center; font-size:11.5px; color:#64748b; max-width:680px;
  margin:0 auto;
}}

/* Why cards */
.wti-w-why-grid{{
  display:grid; grid-template-columns:repeat(4,1fr); gap:14px;
}}
@media (max-width:920px){{.wti-w-why-grid{{grid-template-columns:1fr 1fr;}}}}
@media (max-width:500px){{.wti-w-why-grid{{grid-template-columns:1fr;}}}}
.wti-w-why-card{{
  background:var(--card); border:1px solid var(--border);
  border-radius:14px; padding:20px;
}}
.wti-w-why-icon{{font-size:1.7rem; margin-bottom:8px;}}
.wti-w-why-title{{font-size:14px; font-weight:800; color:#f1f5f9; margin-bottom:6px;}}
.wti-w-why-body{{font-size:12.5px; color:#94a3b8; line-height:1.6;}}

/* Comparison table */
.wti-w-compare-wrap{{overflow-x:auto;}}
.wti-w-compare{{
  width:100%; border-collapse:collapse; min-width:520px;
  background:var(--card); border:1px solid var(--border); border-radius:14px;
  overflow:hidden;
}}
.wti-w-compare th, .wti-w-compare td{{
  padding:12px 16px; text-align:center; font-size:13px;
  border-bottom:1px solid rgba(255,255,255,0.04);
}}
.wti-w-compare th{{
  background:rgba(255,255,255,0.02); font-size:11px; font-weight:800;
  letter-spacing:1.2px; text-transform:uppercase; color:#64748b;
}}
.wti-w-compare th.col-pro{{color:{WTI_COLOR};}}
.wti-w-compare td:first-child{{text-align:left; color:#cbd5e1; font-weight:600;}}
.wti-w-compare tr:last-child td{{border-bottom:none;}}
.tick{{color:#22c55e; font-weight:800;}}
.cross{{color:#475569;}}

/* Use cases */
.wti-w-uses-grid{{
  display:grid; grid-template-columns:repeat(3,1fr); gap:12px;
}}
@media (max-width:780px){{.wti-w-uses-grid{{grid-template-columns:1fr 1fr;}}}}
@media (max-width:460px){{.wti-w-uses-grid{{grid-template-columns:1fr;}}}}
.wti-w-use-card{{
  background:var(--card); border:1px solid var(--border);
  border-radius:12px; padding:16px 18px;
  display:flex; align-items:center; gap:10px;
  font-size:13px; color:#cbd5e1; font-weight:600;
}}
.wti-w-use-card::before{{content:'\u2713'; color:#22c55e; font-weight:800;}}

/* SEO content */
.wti-w-seo-block{{
  background:var(--card); border:1px solid var(--border);
  border-radius:14px; padding:26px 28px;
}}
.wti-w-seo-block h3{{
  font-size:16px; font-weight:700; color:#f1f5f9;
  margin:18px 0 8px;
}}
.wti-w-seo-block h3:first-child{{margin-top:0;}}
.wti-w-seo-block p{{
  font-size:13.5px; color:#94a3b8; line-height:1.75; margin:0 0 10px;
}}
.wti-w-seo-block a{{color:{WTI_COLOR}; text-decoration:none; font-weight:700;}}
.wti-w-seo-block a:hover{{text-decoration:underline;}}

/* FAQ */
.wti-w-faq details{{
  background:var(--card); border:1px solid var(--border); border-radius:10px;
  margin-bottom:10px; overflow:hidden;
}}
.wti-w-faq summary{{
  list-style:none; cursor:pointer; padding:16px 50px 16px 20px;
  font-size:14px; font-weight:700; color:#f1f5f9; position:relative;
}}
.wti-w-faq summary::-webkit-details-marker{{display:none;}}
.wti-w-faq summary::after{{
  content:'+'; position:absolute; right:18px; top:50%;
  transform:translateY(-50%); font-size:22px; color:{WTI_COLOR};
}}
.wti-w-faq details[open] summary::after{{content:'\u2212';}}
.wti-w-faq details > div{{
  padding:0 20px 18px; font-size:13.5px; color:#94a3b8; line-height:1.7;
}}

/* Conversion */
.wti-w-conv{{
  background:linear-gradient(135deg,#0c1322 0%,#14233a 50%,#0f172a 100%);
  border:1px solid rgba(34,211,238,0.3);
  border-radius:18px; padding:38px 28px; text-align:center;
  max-width:780px; margin:0 auto;
}}
.wti-w-conv h2{{
  font-family:'DM Serif Display',serif;
  font-size:clamp(22px,3.5vw,30px); color:#fff; margin:0 0 12px;
}}
.wti-w-conv p{{color:#94a3b8; max-width:560px; margin:0 auto 22px; font-size:14px;}}

/* Cite */
.wti-w-cite-card{{
  background:var(--card); border:1px solid var(--border);
  border-radius:14px; padding:24px 26px;
  max-width:880px; margin:0 auto 40px;
  position:relative;
}}
.wti-w-cite-card h3{{font-size:16px; color:#f1f5f9; margin-bottom:6px;}}
.wti-w-cite-card .wti-w-cite-desc{{font-size:13px; color:#94a3b8; margin-bottom:14px;}}
.wti-w-cite-code-wrap{{background:rgba(0,0,0,0.25); border-radius:10px; padding:16px 18px; position:relative;}}
.wti-w-cite-code{{
  font-family:'JetBrains Mono',ui-monospace,monospace;
  font-size:12px; color:#cbd5e1; line-height:1.7;
  margin:0; white-space:pre-wrap; word-break:break-word;
}}
.wti-w-cite-code a{{color:{WTI_COLOR}; text-decoration:none;}}
.wti-w-cite-btn{{
  position:absolute; top:12px; right:12px;
  background:rgba(34,211,238,0.15); color:{WTI_COLOR};
  border:1px solid rgba(34,211,238,0.35); border-radius:6px;
  font-size:11px; font-weight:700; padding:5px 12px; cursor:pointer;
}}
@media (max-width:560px){{
  .wti-w-cite-btn{{position:static; display:block; width:100%; margin-top:12px;}}
}}

/* Footer license */
.wti-w-license{{
  max-width:880px; margin:0 auto 30px;
  background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.06);
  border-radius:10px; padding:18px 20px;
  font-size:12px; color:#94a3b8;
}}
.wti-w-license a{{color:{WTI_COLOR}; text-decoration:none; font-weight:700;}}
"""


def _build_landing_html(today_str):
    embed_code = (
        '&lt;<span class="tk">iframe</span>\n'
        f'  src=&quot;{BASE_URL}{WIDGET_PATH}&quot;\n'
        '  width=&quot;100%&quot;\n'
        '  height=&quot;320&quot;\n'
        '  frameborder=&quot;0&quot;\n'
        '  loading=&quot;lazy&quot;&gt;\n'
        '&lt;/<span class="tk">iframe</span>&gt;'
    )
    embed_code_plain = (
        f'<iframe src="{BASE_URL}{WIDGET_PATH}" '
        'width="100%" height="320" frameborder="0" loading="lazy"></iframe>'
    )

    faqs = [
        ("How do I embed the WTI oil widget?",
         "Copy the iframe code from the embed section above and paste it into your website&rsquo;s HTML, "
         "blog editor, dashboard, or CMS. The widget loads instantly and is fully responsive on mobile."),
        ("Is the widget free?",
         "Yes &mdash; the standard WTI crude oil widget is free for personal and commercial use, provided "
         "the EnergyRiskIQ attribution remains visible. For an unbranded, white-label version, the Pro "
         f"widget is available from &euro;{PRO_PRICE_EUR}/month."),
        ("How often is WTI data updated?",
         "The widget pulls intraday WTI crude oil prices from EnergyRiskIQ&rsquo;s production data pipeline. "
         "Prices refresh continuously throughout the trading session, alongside live GERI risk signals "
         "from the geri_live engine."),
        ("Can I use the widget commercially?",
         "Yes &mdash; commercial use is permitted on the free widget under the EnergyRiskIQ data licence "
         "(CC BY-NC 4.0), so long as EnergyRiskIQ attribution is preserved and visible. For commercial "
         "redistribution without attribution, the Pro widget removes branding entirely."),
        ("Can I remove EnergyRiskIQ branding?",
         "Branding removal is only available on the Pro widget. The free widget requires the EnergyRiskIQ "
         "attribution link to remain visible &mdash; this funds the data pipeline that keeps the widget free."),
        ("Is there an unbranded version?",
         f"Yes. The Pro widget (&euro;{PRO_PRICE_EUR}/month) is fully unbranded, supports custom colours, "
         "transparent backgrounds, premium themes, overlay options and full white-label commercial use."),
    ]
    faq_html = ''
    for q, a in faqs:
        faq_html += (
            f'<details><summary>{_html.escape(q)}</summary>'
            f'<div>{_html.escape(a)}</div></details>'
        )
    faqpage_schema = _json.dumps({
        "@context": "https://schema.org", "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": q,
             "acceptedAnswer": {"@type": "Answer", "text": a}}
            for q, a in faqs
        ],
    })

    webpage_schema = _json.dumps({
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": "Free WTI Crude Oil Price Widget for Websites",
        "url": LANDING_URL,
        "description": "Embed a live WTI crude oil price widget on your website with intraday updates and energy risk signals.",
        "isAccessibleForFree": True,
        "publisher": {"@type": "Organization", "name": "EnergyRiskIQ", "url": BASE_URL},
        "license": f"{BASE_URL}/data-license",
    })

    sw_schema = _json.dumps({
        "@context": "https://schema.org",
        "@type": "SoftwareApplication",
        "name": "EnergyRiskIQ WTI Crude Oil Widget",
        "applicationCategory": "FinanceApplication",
        "operatingSystem": "Web (iframe embed)",
        "url": LANDING_URL,
        "offers": [
            {"@type": "Offer", "name": "Free Widget", "price": "0", "priceCurrency": "EUR"},
            {"@type": "Offer", "name": "Pro Widget (unbranded)", "price": PRO_PRICE_EUR, "priceCurrency": "EUR"},
        ],
        "publisher": {"@type": "Organization", "name": "EnergyRiskIQ", "url": BASE_URL},
    })

    breadcrumb_schema = _json.dumps({
        "@context": "https://schema.org", "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": BASE_URL},
            {"@type": "ListItem", "position": 2, "name": "Widgets",
             "item": f"{BASE_URL}/widgets/wti-crude-oil-price"},
            {"@type": "ListItem", "position": 3, "name": "WTI Crude Oil Widget", "item": LANDING_URL},
        ],
    })

    return f"""<script>
var l=document.getElementById('snap-loader');
if(l){{l.style.display='none';}}
document.body.style.overflow='';
</script>
<script type="application/ld+json">{webpage_schema}</script>
<script type="application/ld+json">{sw_schema}</script>
<script type="application/ld+json">{breadcrumb_schema}</script>
<script type="application/ld+json">{faqpage_schema}</script>
<style>{_LANDING_CSS}</style>

<script>
(function(){{
  document.addEventListener('copy', function(e) {{
    var sel = window.getSelection ? window.getSelection().toString() : '';
    if (sel.length > 0) {{
      var attr = '\\n\\n[Source: EnergyRiskIQ.com — WTI Crude Oil Widget | CC BY-NC 4.0]';
      e.clipboardData.setData('text/plain', sel + attr);
      e.preventDefault();
    }}
  }});
  document.addEventListener('contextmenu', function(e) {{
    var t = e.target;
    if (t && (t.classList && t.classList.contains('wti-w-protected') || (t.closest && t.closest('.wti-w-protected')))) {{
      e.preventDefault();
    }}
  }});
}})();
</script>

<!-- ── NAV ───────────────────────────────────────────────────────── -->
<nav class="nav">
  <div class="nav-inner">
    <a href="/" class="logo">
      <img src="/static/logo.png" alt="EnergyRiskIQ" style="height:28px">
      <span>EnergyRiskIQ</span>
    </a>
    <div style="display:flex;align-items:center;gap:1.5rem;">
      <a href="/data/wti-crude-oil-price-today" style="font-size:13px;color:#94a3b8;text-decoration:none;">WTI</a>
      <a href="/data/brent-crude-oil-price-today" style="font-size:13px;color:#94a3b8;text-decoration:none;">Brent</a>
      <a href="/indices/global-energy-risk-index" style="font-size:13px;color:#94a3b8;text-decoration:none;">GERI</a>
      <a href="/users" class="cta-btn-nav">Get Free Access</a>
    </div>
  </div>
</nav>

<!-- ── 1. HERO ───────────────────────────────────────────────────── -->
<header class="wti-w-hero">
  <h1>Free <span>WTI Crude Oil Price Widget</span><br>for Websites</h1>
  <p>
    Embed a live WTI crude oil price widget on your website, app, dashboard, or financial blog.
    Automatically updated with intraday oil market data and EnergyRiskIQ signals &mdash;
    powered by Custom Algorithms.
  </p>
  <div class="wti-w-cta-row">
    <a href="#embed" class="wti-w-cta-primary">Get Free Widget Code &darr;</a>
    <a href="#pro" class="wti-w-cta-secondary">Unlock Pro Widget (&euro;{PRO_PRICE_EUR}/mo)</a>
  </div>
  <div class="wti-w-trust">
    <span>Intraday WTI updates</span>
    <span>Free commercial use</span>
    <span>Mobile responsive</span>
    <span>Fast lightweight embed</span>
    <span>Energy market signals</span>
  </div>
</header>

<!-- ── 2. LIVE WIDGET PREVIEW ────────────────────────────────────── -->
<section class="wti-w-section" id="preview">
  <h2>Live WTI Oil Widget Preview</h2>
  <p>Real-time render of the free embeddable widget. This is exactly what your visitors will see.</p>
  <div class="wti-w-preview-wrap">
    <div class="wti-w-preview-col">
      <h3>FREE WIDGET &middot; LIVE RENDER</h3>
      <div class="wti-w-iframe-shell">
        <iframe src="{WIDGET_PATH}" width="100%" height="340" frameborder="0"
                style="border:0;display:block;border-radius:10px;background:transparent;"
                loading="lazy" title="WTI Crude Oil Widget"></iframe>
      </div>
      <div class="wti-w-preview-note">Branded &middot; required attribution &middot; CC BY-NC 4.0</div>
    </div>
  </div>
</section>

<!-- ── 3. EMBED SECTION ──────────────────────────────────────────── -->
<section class="wti-w-section" id="embed">
  <h2>Copy &amp; Paste This Widget Into Your Site</h2>
  <p>One-line iframe embed. Works in any HTML page, blog editor, CMS, or dashboard.</p>
  <div class="wti-w-embed-box">
    <div class="wti-w-embed-head">
      <span>HTML &middot; iframe embed</span>
      <button class="wti-w-embed-copy" id="copyEmbedBtn">Copy Code</button>
    </div>
    <pre class="wti-w-embed-code" id="embedCode">{embed_code}</pre>
  </div>
  <p class="wti-w-embed-micro">Free to use with EnergyRiskIQ attribution &middot; loads in &lt;200ms &middot; mobile-responsive.</p>
  <script>
  (function(){{
    var btn=document.getElementById('copyEmbedBtn');
    if(!btn) return;
    btn.addEventListener('click',function(){{
      var code={_json.dumps(embed_code_plain)};
      if(navigator.clipboard){{navigator.clipboard.writeText(code);}}
      btn.textContent='Copied!'; setTimeout(function(){{btn.textContent='Copy Code';}},2000);
    }});
  }})();
  </script>
</section>

<!-- ── 4. WHY THIS WIDGET ────────────────────────────────────────── -->
<section class="wti-w-section">
  <h2>Why Publishers &amp; Analysts Use This WTI Widget</h2>
  <div class="wti-w-why-grid">
    <div class="wti-w-why-card">
      <div class="wti-w-why-icon">&#128200;</div>
      <div class="wti-w-why-title">Live Intraday Oil Data</div>
      <div class="wti-w-why-body">Continuously updated WTI market prices sourced from the EnergyRiskIQ production pipeline.</div>
    </div>
    <div class="wti-w-why-card">
      <div class="wti-w-why-icon">&#9888;&#65039;</div>
      <div class="wti-w-why-title">Energy Risk Context</div>
      <div class="wti-w-why-body">Real-time GERI risk signal embedded in the widget &mdash; visitors see the risk regime instantly.</div>
    </div>
    <div class="wti-w-why-card">
      <div class="wti-w-why-icon">&#9889;</div>
      <div class="wti-w-why-title">Fast Lightweight Embed</div>
      <div class="wti-w-why-body">Optimised for blogs, dashboards and finance apps &mdash; under 200ms render, zero JS deps.</div>
    </div>
    <div class="wti-w-why-card">
      <div class="wti-w-why-icon">&#128241;</div>
      <div class="wti-w-why-title">Mobile Responsive</div>
      <div class="wti-w-why-body">Adapts cleanly to desktop, tablet and mobile &mdash; renders perfectly inside any iframe container.</div>
    </div>
  </div>
</section>

<!-- ── 5. FREE VS PRO COMPARISON ─────────────────────────────────── -->
<section class="wti-w-section" id="compare">
  <h2>Free vs Professional Widget</h2>
  <p>Both widgets carry the same live WTI data &mdash; Pro removes branding and unlocks customisation.</p>
  <div class="wti-w-compare-wrap">
    <table class="wti-w-compare">
      <thead>
        <tr>
          <th style="text-align:left;">Feature</th>
          <th>Free Widget</th>
          <th class="col-pro">Pro Widget (&euro;{PRO_PRICE_EUR}/mo)</th>
        </tr>
      </thead>
      <tbody>
        <tr><td>Live WTI Price</td><td><span class="tick">&#10003;</span></td><td><span class="tick">&#10003;</span></td></tr>
        <tr><td>Intraday Chart</td><td><span class="tick">&#10003;</span></td><td><span class="tick">&#10003;</span></td></tr>
        <tr><td>7-Day &amp; 30-Day Daily Price Chart</td><td><span class="cross">&#10005;</span></td><td><span class="tick">&#10003;</span></td></tr>
        <tr><td>EnergyRiskIQ Branding</td><td>Required</td><td><span class="cross">Removed</span></td></tr>
        <tr><td>Citation Required</td><td>Required</td><td><span class="cross">Not Required</span></td></tr>
        <tr><td>Premium Themes</td><td><span class="cross">&#10005;</span></td><td><span class="tick">&#10003;</span></td></tr>
        <tr><td>Custom Colours</td><td><span class="cross">&#10005;</span></td><td><span class="tick">&#10003;</span></td></tr>
        <tr><td>Transparent Background</td><td><span class="cross">&#10005;</span></td><td><span class="tick">&#10003;</span></td></tr>
        <tr><td>Overlay Options (Brent / VIX / GERI)</td><td><span class="cross">&#10005;</span></td><td><span class="tick">&#10003;</span></td></tr>
        <tr><td>Advanced Layouts</td><td><span class="cross">&#10005;</span></td><td><span class="tick">&#10003;</span></td></tr>
        <tr><td>White-label Usage</td><td><span class="cross">&#10005;</span></td><td><span class="tick">&#10003;</span></td></tr>
      </tbody>
    </table>
  </div>
  <div style="text-align:center;margin-top:24px;">
    <a href="/users" class="wti-w-cta-primary">Create Free Account &amp; Unlock Pro Widget &rarr;</a>
  </div>
</section>

<!-- ── 6. PROFESSIONAL WIDGET PREVIEW ────────────────────────────── -->
<section class="wti-w-section" id="pro">
  <h2>Professional Unbranded Oil Widget</h2>
  <p>Cleaner, white-label, transparent background &mdash; designed to blend seamlessly into premium dashboards and trading platforms.</p>
  <div class="wti-w-preview-wrap">
    <div class="wti-w-preview-pro">
      <div class="wti-w-preview-col" style="background:transparent;">
        <h3 style="color:#fff;">PRO WIDGET &middot; UNBRANDED PREVIEW</h3>
        <div class="wti-w-iframe-shell" style="background:#020617;">
          <iframe src="/embed/wti-crude-oil-widget-pro" width="100%" height="320" frameborder="0"
                  style="border:0;display:block;border-radius:10px;background:transparent;"
                  loading="lazy" title="Pro WTI Widget Preview"></iframe>
        </div>
        <div class="wti-w-preview-note" style="color:#94a3b8;">
          No branding &middot; transparent background &middot; white-label ready
        </div>
      </div>
    </div>
  </div>
  <div style="text-align:center;margin-top:24px;">
    <a href="/users" class="wti-w-cta-primary">Upgrade for &euro;{PRO_PRICE_EUR}/month &rarr;</a>
  </div>
</section>

<!-- ── 7. SEO CONTENT ────────────────────────────────────────────── -->
<section class="wti-w-section">
  <h2>WTI Crude Oil Price Today</h2>
  <div class="wti-w-seo-block">
    <h3>What is WTI Crude Oil?</h3>
    <p>
      WTI (West Texas Intermediate) is the leading United States oil benchmark, priced at the Cushing,
      Oklahoma delivery hub and traded on NYMEX. It is a light, sweet crude grade used as the marginal
      price for US refiners and as the reference for North American crude oil contracts. WTI is one of
      the two most important global oil benchmarks alongside Brent.
    </p>
    <h3>Why Oil Prices Matter</h3>
    <p>
      WTI prices directly affect US inflation, gasoline and diesel pump prices, jet-fuel costs, freight
      and logistics rates, and the broader global economy. A sustained move in WTI feeds through into
      consumer prices within weeks and reshapes corporate margins across every fuel-intensive industry.
    </p>
    <h3>What Moves WTI Prices?</h3>
    <p>
      WTI is driven by OPEC+ production decisions, weekly US EIA inventory data, geopolitical risk
      (Middle East, Russia, sanctions, Red Sea shipping), Chinese industrial demand, US dollar strength,
      macro volatility (VIX), and gas-to-oil switching dynamics. EnergyRiskIQ&rsquo;s
      <a href="/indices/global-energy-risk-index">GERI index</a> captures the geopolitical layer in real time.
    </p>
    <h3>Related Pages</h3>
    <p>
      &rarr; <a href="/data/wti-crude-oil-price-today">WTI Crude Oil Price Today (full data page)</a><br>
      &rarr; <a href="/data/brent-crude-oil-price-today">Brent Crude Oil Price Today</a><br>
      &rarr; <a href="/data/natural-gas-price-today-europe">Natural Gas Price Today Europe</a><br>
      &rarr; <a href="/indices/global-energy-risk-index">Global Energy Risk Index (GERI)</a><br>
      &rarr; <a href="/research/global-energy-risk-timeline">Global Energy Risk Timeline</a>
    </p>
  </div>
</section>

<!-- ── 8. USE CASES ──────────────────────────────────────────────── -->
<section class="wti-w-section">
  <h2>Perfect For</h2>
  <div class="wti-w-uses-grid">
    <div class="wti-w-use-card">Financial blogs</div>
    <div class="wti-w-use-card">Trading communities</div>
    <div class="wti-w-use-card">Market dashboards</div>
    <div class="wti-w-use-card">Investment newsletters</div>
    <div class="wti-w-use-card">Energy companies</div>
    <div class="wti-w-use-card">Economic research websites</div>
  </div>
</section>

<!-- ── 9. BACKLINK ENGINE ────────────────────────────────────────── -->
<section class="wti-w-section">
  <h2>Powered by EnergyRiskIQ</h2>
  <p>
    The free widget is available for any website under the EnergyRiskIQ
    <a href="/data-license" style="color:{WTI_COLOR};text-decoration:none;font-weight:700;">data licence (CC BY-NC 4.0)</a>.
    Use requires that the &ldquo;Powered by EnergyRiskIQ&rdquo; branding remains visible and links back to
    <a href="{DATA_URL}" style="color:{WTI_COLOR};text-decoration:none;font-weight:700;">{DATA_URL}</a>.
    This attribution gives your visitors direct access to deeper WTI analysis, charts and risk intelligence.
  </p>
</section>

<!-- ── 10. FAQ ───────────────────────────────────────────────────── -->
<section class="wti-w-section">
  <h2>Frequently Asked Questions</h2>
  <div class="wti-w-faq">{faq_html}</div>
</section>

<!-- ── CITATION & REFERENCE ──────────────────────────────────────── -->
<section class="wti-w-section">
  <h2>Citation &amp; Reference</h2>
  <div class="wti-w-cite-card">
    <h3>How to Cite This Widget</h3>
    <div class="wti-w-cite-desc">
      When using the WTI widget in research, journalism, dashboards or professional reports, please cite the source as follows.
    </div>
    <div class="wti-w-cite-code-wrap">
      <pre class="wti-w-cite-code">EnergyRiskIQ. (2026). <em>WTI Crude Oil Price Widget &mdash; {today_str}</em>.
Retrieved from <a href="{LANDING_URL}">{LANDING_URL}</a>
Live data: <a href="{DATA_URL}">{DATA_URL}</a>
Custom Algorithm interpretation. Data sources: NYMEX WTI settlement, intraday WTI captures, GERI live risk engine, intraday Brent for spread calculation.</pre>
      <button class="wti-w-cite-btn" onclick="this.textContent='Copied!';setTimeout(()=>this.textContent='Copy',2000);navigator.clipboard&amp;&amp;navigator.clipboard.writeText('EnergyRiskIQ. (2026). WTI Crude Oil Price Widget — {today_str}. Retrieved from {LANDING_URL}')">Copy</button>
    </div>
  </div>
</section>

<!-- ── 11. FINAL CONVERSION ──────────────────────────────────────── -->
<section class="wti-w-section">
  <div class="wti-w-conv">
    <h2>Upgrade to the Professional Oil Widget</h2>
    <p>
      Remove branding, customise appearance, and integrate a premium oil market widget into your website,
      app, or trading dashboard &mdash; for less than the price of a coffee per month.
    </p>
    <div class="wti-w-cta-row" style="margin-bottom:0;">
      <a href="/users" class="wti-w-cta-primary">Create Free Account &rarr;</a>
      <a href="#compare" class="wti-w-cta-secondary">Compare Free vs Pro</a>
    </div>
  </div>
</section>

<!-- ── 12. FOOTER LICENSE ────────────────────────────────────────── -->
<div class="wti-w-license">
  <strong>Data disclaimer:</strong> Oil prices shown in the widget are provided for informational purposes only and
  do not constitute financial advice. Data is delivered under the EnergyRiskIQ
  <a href="/data-license">data licence (CC BY-NC 4.0)</a>. Commercial redistribution without attribution
  is not permitted on the free widget &mdash; the Pro plan grants full white-label rights.
</div>

<footer class="page-footer">
  <div>
    &copy; 2026 EnergyRiskIQ &bull;
    <a href="/">Home</a>
    <a href="/data/wti-crude-oil-price-today">WTI Data</a>
    <a href="/data/brent-crude-oil-price-today">Brent</a>
    <a href="/indices/global-energy-risk-index">GERI</a>
    <a href="/data-license">Data Licence</a>
    <a href="/sitemap-index.xml">Sitemap</a>
    &bull; Not financial advice.
  </div>
</footer>
</body>
</html>"""


# Custom loader for the landing page
_WIDGET_LOADER_HTML = _LOADER_HTML.replace(
    'Global Energy Risk Snapshot | EnergyRiskIQ',
    'Free WTI Crude Oil Price Widget for Websites | EnergyRiskIQ'
).replace(
    'name="description" content="Live global energy risk snapshot. Current GERI, EERI and EGSI-M index values with Brent crude, TTF gas, VIX and LNG market prices."',
    'name="description" content="Embed a live WTI crude oil price widget on your website or app. Free oil price widget with intraday updates, charts, and energy risk signals."'
).replace(
    'rel="canonical" href="https://energyriskiq.com/data/energy-risk-snapshot"',
    f'rel="canonical" href="{LANDING_URL}"'
).replace(
    'Fetching GERI\u00a0&\u00a0EERI indices\u2026',
    'Loading WTI widget preview\u2026',
).replace(
    '<span class="ld-tag">GERI</span>\n    <span class="ld-tag">EERI</span>\n    <span class="ld-tag">EGSI&#8209;M</span>\n    <span class="ld-tag">Brent</span>\n    <span class="ld-tag">TTF</span>',
    '<span class="ld-tag">WTI</span>\n    <span class="ld-tag">Widget</span>\n    <span class="ld-tag">Embed</span>\n    <span class="ld-tag">GERI</span>',
)


@router.get("/widgets/wti-crude-oil-price")
async def wti_widget_landing():
    async def generate():
        yield _WIDGET_LOADER_HTML
        try:
            today_str = datetime.now(timezone.utc).strftime('%B %-d, %Y')
            html = await asyncio.to_thread(_build_landing_html, today_str)
            yield html
        except Exception as exc:
            logger.error(f"WTI widget landing render failed: {exc}", exc_info=True)
            yield (
                "<script>var l=document.getElementById('snap-loader');"
                "if(l)l.style.display='none';document.body.style.overflow='';</script>"
                f"<div style='color:#ef4444;padding:40px;font-family:sans-serif;background:#0b0f1a;'>"
                f"<h2>Error loading widget page</h2><p>{_html.escape(str(exc))}</p></div></body></html>"
            )

    return StreamingResponse(generate(), media_type="text/html")
