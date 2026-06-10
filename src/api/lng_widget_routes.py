"""
Global LNG Market Intelligence Widget — SEO landing page + embeddable iframe widget.

Routes:
  GET /widgets/jkm-lng-price       → marketing landing page (SEO + funnel)
  GET /embed/jkm-lng-widget        → standalone iframe widget (free, branded)
  GET /embed/jkm-lng-widget-pro    → preview-only "pro" widget (visual demo)

Custom-algorithm wording (not "AI"). Fully mobile responsive.
Anti-copy text protection (does NOT block search engines).
Mirrors the design of /widgets/wti-crude-oil-price and /widgets/europe-gas-storage-levels.
"""
import logging
import asyncio
import html as _html
import json as _json
from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import StreamingResponse, HTMLResponse

from src.db.db import execute_production_one, execute_production_query
from src.api.snapshot_routes import _LOADER_HTML, BAND_COLORS, _safe_float

router = APIRouter()
logger = logging.getLogger(__name__)

BASE_URL    = "https://energyriskiq.com"
WIDGET_PATH = "/embed/jkm-lng-widget"
LANDING_URL = f"{BASE_URL}/widgets/jkm-lng-price"
DATA_URL    = f"{BASE_URL}/data/jkm-lng-spot-price"
LNG_COLOR   = "#d4a017"
LNG_COLOR2  = "#f59e0b"

PRO_PRICE_EUR = "1.95"

# JKM is USD/MMBtu, TTF is EUR/MWh. Convert TTF → $/MMBtu for the spread.
_MMBTU_TO_MWH = 0.29307   # 1 MMBtu = 0.29307 MWh
_EUR_USD      = 1.09      # approximate FX for display comparisons


# ─────────────────────────────────────────────────────────────────────────────
# Data
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_widget_data():
    """Lightweight fetch optimised for the widget endpoint."""
    daily = execute_production_query(
        "SELECT date, jkm_price, jkm_change_24h, jkm_change_pct "
        "FROM lng_price_snapshots "
        "WHERE jkm_price IS NOT NULL "
        "ORDER BY date DESC LIMIT 30"
    ) or []
    # daily[0] = latest; reversed list for charts (oldest → newest)
    daily_hist = list(reversed(daily))

    geri_live = execute_production_one(
        "SELECT value, band, computed_at FROM geri_live ORDER BY id DESC LIMIT 1"
    )

    ttf = execute_production_one(
        "SELECT date, ttf_price FROM ttf_gas_snapshots "
        "WHERE ttf_price IS NOT NULL "
        "ORDER BY date DESC LIMIT 1"
    )

    return {
        'daily': daily,
        'daily_hist': daily_hist,
        'geri_live': geri_live,
        'ttf': ttf,
    }


def _lng_trend(daily_hist):
    """Deterministic Custom-Algorithm LNG market trend from the recent price path.

    Returns (label, color). Uses the last 7 available daily closes and compares the
    most recent close to the start of the window: >=+1% BULLISH, <=-1% BEARISH,
    otherwise NEUTRAL.
    """
    rows = [r for r in (daily_hist or []) if r.get('jkm_price') is not None]
    if len(rows) < 2:
        return ("NEUTRAL", "#eab308")
    window = rows[-7:]
    first = _safe_float(window[0]['jkm_price'])
    last = _safe_float(window[-1]['jkm_price'])
    pct = ((last - first) / first * 100.0) if first else 0.0
    if pct >= 1.0:
        return ("BULLISH", "#22c55e")
    if pct <= -1.0:
        return ("BEARISH", "#ef4444")
    return ("NEUTRAL", "#eab308")


def _ttf_spread_usd(jkm_price, ttf_row):
    """JKM − TTF spread in $/MMBtu (TTF €/MWh converted to $/MMBtu)."""
    if not ttf_row or ttf_row.get('ttf_price') is None or not jkm_price:
        return None
    ttf_usd_mmbtu = _safe_float(ttf_row['ttf_price']) * _MMBTU_TO_MWH * _EUR_USD
    return jkm_price - ttf_usd_mmbtu


def _build_mini_chart_svg(rows, color=LNG_COLOR, height=70, width=320,
                          price_key='jkm_price', empty_msg='Awaiting LNG data'):
    """Compact sparkline for the Pro widget daily charts."""
    pts_rows = [r for r in (rows or []) if r.get(price_key) is not None]
    if len(pts_rows) < 2:
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
    vals = [float(r[price_key]) for r in pts_rows]
    vmin, vmax = min(vals), max(vals)
    if vmin == vmax:
        vmax = vmin * 1.001 + 0.0001
    rng = vmax - vmin
    n = len(pts_rows)
    pts = []
    for i, r in enumerate(pts_rows):
        x = PAD_L + (i / max(n - 1, 1)) * cw
        y = PAD_T + ch - ((float(r[price_key]) - vmin) / rng) * ch
        pts.append((x, y))
    path_d = 'M ' + ' L '.join(f'{p[0]:.1f} {p[1]:.1f}' for p in pts)
    area_d = path_d + f' L {pts[-1][0]:.1f} {PAD_T+ch:.1f} L {pts[0][0]:.1f} {PAD_T+ch:.1f} Z'
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
# /embed/jkm-lng-widget — the actual iframe widget (free, branded)
# ─────────────────────────────────────────────────────────────────────────────

def _render_widget_html(data, *, pro=False):
    daily      = data['daily']
    daily_hist = data.get('daily_hist') or []
    geri       = data['geri_live']
    ttf        = data['ttf']

    # Latest price + change (prefer stored daily change fields)
    if daily:
        latest = daily[0]
        price = _safe_float(latest['jkm_price'])
        ts_str = latest['date'].isoformat() if latest.get('date') else ''
        chg = _safe_float(latest.get('jkm_change_24h')) if latest.get('jkm_change_24h') is not None else 0.0
        chg_pct = _safe_float(latest.get('jkm_change_pct')) if latest.get('jkm_change_pct') is not None else 0.0
        # Fallback: derive from previous row if change fields missing
        if (latest.get('jkm_change_24h') is None) and len(daily) >= 2:
            prev = _safe_float(daily[1]['jkm_price'])
            chg = price - prev
            chg_pct = (chg / prev * 100.0) if prev else 0.0
    else:
        price, ts_str, chg, chg_pct = 0.0, '', 0.0, 0.0

    chg_color = '#22c55e' if chg > 0 else '#ef4444' if chg < 0 else '#eab308'
    arrow = '&#9650;' if chg > 0 else '&#9660;' if chg < 0 else '&#9644;'

    # Custom-Algorithm LNG market trend
    trend_label, trend_color = _lng_trend(daily_hist)

    # GERI energy-risk band
    geri_band = _html.escape(str((geri or {}).get('band') or 'MODERATE')).upper()
    geri_val  = int(round(_safe_float((geri or {}).get('value', 0))))
    geri_color = BAND_COLORS.get(geri_band, BAND_COLORS.get(geri_band.title(), '#f97316'))

    # JKM − TTF spread ($/MMBtu)
    spread = _ttf_spread_usd(price, ttf)
    spread_str = f"{spread:+.2f}" if spread is not None else "—"
    spread_color = ('#22c55e' if spread > 0 else '#ef4444' if spread < 0 else '#94a3b8') if spread is not None else '#94a3b8'

    # Pro-only daily charts
    if pro:
        hist_30 = daily_hist[-30:] if daily_hist else []
        hist_7  = daily_hist[-7:]  if daily_hist else []
        chart_30_svg = _build_mini_chart_svg(hist_30, color=LNG_COLOR, height=70)
        chart_7_svg  = _build_mini_chart_svg(hist_7,  color=LNG_COLOR, height=70)

        def _range_meta(rows):
            v = [float(r['jkm_price']) for r in rows if r.get('jkm_price') is not None]
            if not v:
                return ('—', '—', '—')
            lo, hi = min(v), max(v)
            chg_p = ((v[-1] - v[0]) / v[0] * 100.0) if v[0] else 0.0
            return (f'${lo:.2f}', f'${hi:.2f}', f'{chg_p:+.2f}%')
        lo7, hi7, ch7 = _range_meta(hist_7)
        lo30, hi30, ch30 = _range_meta(hist_30)

        # Deterministic market intelligence sentence
        spread_phrase = (
            "a JKM premium to European TTF that incentivises cargo diversion toward Asia"
            if (spread is not None and spread > 0)
            else "a discount to European TTF that favours Atlantic-basin deliveries into Europe"
            if (spread is not None and spread < 0)
            else "a JKM–TTF spread near parity"
        )
        trend_phrase = {
            "BULLISH": "firming Asian demand and tighter cargo availability",
            "BEARISH": "softer Asian demand and ample cargo supply",
            "NEUTRAL": "balanced Asia–Europe demand",
        }[trend_label]
        intel_text = (
            f"JKM LNG is showing a {trend_label.lower()} trend on {trend_phrase}, with "
            f"{spread_phrase}. Energy-risk conditions read {geri_band.lower()} on the GERI engine."
        )
    else:
        chart_30_svg = chart_7_svg = ''
        lo7 = hi7 = ch7 = lo30 = hi30 = ch30 = '—'
        intel_text = ''

    # Pro styling vs Free styling
    if pro:
        bg = "transparent"
        card_bg = "linear-gradient(135deg,#020617 0%,#0a0f1d 50%,#0d1525 100%)"
        border = f"1px solid rgba(212,160,23,0.35)"
        brand_block = ""
        cite_block = ""
        accent = LNG_COLOR
        title_color = "#f1f5f9"
    else:
        bg = "#0b0f1a"
        card_bg = "linear-gradient(135deg,#0c1322 0%,#15110a 50%,#0c1322 100%)"
        border = f"1px solid rgba(212,160,23,0.22)"
        brand_block = (
            f'<a href="{LANDING_URL}" target="_blank" rel="noopener" class="erq-brand">'
            f'<span class="erq-brand-dot"></span>Powered by EnergyRiskIQ'
            f'</a>'
        )
        cite_block = (
            f'<a href="{DATA_URL}" target="_blank" rel="noopener" class="erq-cite">'
            f'View Full LNG Analysis &rarr;</a>'
        )
        accent = LNG_COLOR
        title_color = "#f1f5f9"

    label_pro = '<span class="erq-pro-tag">PRO</span>' if pro else ''

    pro_panel = ('''
  <div class="erq-daily-panel">
    <div class="erq-daily-head">
      <span class="erq-daily-label">LNG Price Chart</span>
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
    <div class="erq-intel">
      <div class="erq-intel-label">Market Intelligence</div>
      <div class="erq-intel-body">{_html.escape(intel_text)}</div>
    </div>
  </div>
  ''') if pro else ''

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,follow">
<title>Global LNG Market Widget &middot; EnergyRiskIQ</title>
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
    background:linear-gradient(90deg,{accent},rgba(212,160,23,0.12));
  }}
  .erq-head{{display:flex; align-items:center; justify-content:space-between; margin-bottom:8px; gap:8px;}}
  .erq-title{{font-size:12px; font-weight:800; color:{title_color}; letter-spacing:0.4px;}}
  .erq-sub{{font-size:9.5px; font-weight:700; letter-spacing:1.2px; text-transform:uppercase; color:#64748b;}}
  .erq-sub-dot{{display:inline-block; width:6px; height:6px; border-radius:50%; background:{accent}; box-shadow:0 0 6px {accent}; margin-right:5px; vertical-align:middle;}}
  .erq-price-row{{display:flex; align-items:baseline; gap:8px; flex-wrap:wrap; margin-top:2px;}}
  .erq-price{{font-size:30px; font-weight:800; color:#fff; line-height:1.05; font-variant-numeric:tabular-nums;}}
  .erq-price sup{{font-size:14px; font-weight:600; vertical-align:top; margin-top:4px;}}
  .erq-unit{{font-size:10.5px; color:#94a3b8;}}
  .erq-chg{{font-size:12.5px; font-weight:700; color:{chg_color}; margin-top:2px; font-variant-numeric:tabular-nums;}}
  .erq-stats{{margin:12px 0 4px; display:flex; flex-direction:column; gap:7px;}}
  .erq-stat{{display:flex; align-items:center; justify-content:space-between; gap:10px;}}
  .erq-stat-k{{font-size:10.5px; font-weight:700; letter-spacing:0.6px; text-transform:uppercase; color:#94a3b8;}}
  .erq-stat-v{{font-size:12px; font-weight:800; font-variant-numeric:tabular-nums;}}
  .erq-badge{{font-size:10px; font-weight:800; letter-spacing:1px; padding:3px 9px; border-radius:14px; text-transform:uppercase; display:inline-flex; align-items:center; gap:5px;}}
  .erq-badge::before{{content:''; width:6px; height:6px; border-radius:50%; background:currentColor;}}
  .erq-cite{{display:block; text-align:center; margin-top:12px; font-size:11px; font-weight:700; color:{accent}; text-decoration:none; padding:6px 0; letter-spacing:0.3px;}}
  .erq-cite:hover{{color:#fff;}}
  .erq-brand{{display:block; text-align:center; margin-top:6px; font-size:9.5px; color:#475569; text-decoration:none; letter-spacing:0.5px;}}
  .erq-brand-dot{{display:inline-block; width:5px; height:5px; border-radius:50%; background:{accent}; margin-right:5px; vertical-align:middle;}}
  .erq-brand:hover{{color:#94a3b8;}}
  .erq-pro-tag{{font-size:9px; font-weight:800; letter-spacing:1px; background:linear-gradient(135deg,{LNG_COLOR},{LNG_COLOR2}); color:#0a0f1e; padding:2px 8px; border-radius:10px;}}
  .erq-ts{{font-size:9.5px; color:#64748b; margin-top:8px;}}
  .erq-daily-panel{{margin-top:12px; padding-top:10px; border-top:1px dashed rgba(255,255,255,0.08);}}
  .erq-daily-head{{display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;}}
  .erq-daily-label{{font-size:9.5px; font-weight:800; letter-spacing:1.2px; text-transform:uppercase; color:#94a3b8;}}
  .erq-range-toggle{{display:inline-flex; gap:0;}}
  .erq-range-toggle button{{background:rgba(255,255,255,0.04); color:#64748b; border:1px solid rgba(255,255,255,0.08); font-size:9.5px; font-weight:700; padding:3px 9px; cursor:pointer; font-family:inherit; letter-spacing:0.5px;}}
  .erq-range-toggle button:first-child{{border-radius:5px 0 0 5px;}}
  .erq-range-toggle button:last-child{{border-radius:0 5px 5px 0; border-left:none;}}
  .erq-range-toggle button.active{{background:{accent}22; color:{accent}; border-color:{accent}55;}}
  .erq-daily-stats{{display:flex; justify-content:space-between; gap:10px; font-size:10px; color:#94a3b8; margin-top:4px; font-variant-numeric:tabular-nums;}}
  .erq-daily-stats b{{color:#cbd5e1; font-weight:700;}}
  .erq-chart-pane{{display:none;}}
  .erq-chart-pane.active{{display:block;}}
  .erq-intel{{margin-top:10px; padding-top:10px; border-top:1px dashed rgba(255,255,255,0.08);}}
  .erq-intel-label{{font-size:9.5px; font-weight:800; letter-spacing:1.2px; text-transform:uppercase; color:{accent}; margin-bottom:4px;}}
  .erq-intel-body{{font-size:11px; color:#cbd5e1; line-height:1.55;}}
  @media (max-width:340px){{.erq-price{{font-size:24px;}} .erq-widget{{padding:12px 14px;}}}}
</style>
</head>
<body>
<div class="erq-widget" role="region" aria-label="Global LNG Market Widget by EnergyRiskIQ">
  <div class="erq-head">
    <div>
      <div class="erq-title">JKM LNG &middot; Today {label_pro}</div>
      <div class="erq-sub"><span class="erq-sub-dot"></span>Global LNG Market</div>
    </div>
    <div style="text-align:right;">
      <div class="erq-sub" style="color:{accent};">$/MMBtu</div>
    </div>
  </div>

  <div class="erq-price-row">
    <div class="erq-price"><sup>$</sup>{price:.2f}</div>
    <div class="erq-unit">/MMBtu</div>
  </div>
  <div class="erq-chg">{arrow} {chg:+.2f} ({chg_pct:+.2f}%)</div>

  <div class="erq-stats">
    <div class="erq-stat">
      <span class="erq-stat-k">LNG Market Trend</span>
      <span class="erq-badge" style="color:{trend_color};border:1px solid {trend_color}33;background:rgba(255,255,255,0.04);">{trend_label}</span>
    </div>
    <div class="erq-stat">
      <span class="erq-stat-k">Energy Risk</span>
      <span class="erq-badge" style="color:{geri_color};border:1px solid {geri_color}33;background:rgba(255,255,255,0.04);">{geri_band}</span>
    </div>
    <div class="erq-stat">
      <span class="erq-stat-k">JKM&ndash;TTF Spread</span>
      <span class="erq-stat-v" style="color:{spread_color};">{spread_str}</span>
    </div>
  </div>

  <div class="erq-ts">Snapshot: {ts_str} &middot; GERI {geri_val}</div>

  {pro_panel}

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


_EMBED_TRACK_BEACON = (
    "<script>(function(){try{var r=document.referrer||'';if(!r)return;"
    "var d=new URLSearchParams();d.set('widget','jkm-lng-free');d.set('url',r);"
    "navigator.sendBeacon('/api/widget-embeds/track',d);}catch(e){}})();</script>"
)


@router.get("/embed/jkm-lng-widget")
async def lng_widget_embed():
    try:
        data = await asyncio.to_thread(_fetch_widget_data)
    except Exception as exc:
        logger.error(f"LNG widget data fetch failed: {exc}", exc_info=True)
        data = {'daily': [], 'daily_hist': [], 'geri_live': None, 'ttf': None}
    html = _render_widget_html(data, pro=False)
    html = html.replace("</body>", _EMBED_TRACK_BEACON + "</body>", 1)
    return HTMLResponse(content=html, headers={"Cache-Control": "public, max-age=120"})


@router.get("/embed/jkm-lng-widget-pro")
async def lng_widget_embed_pro():
    try:
        data = await asyncio.to_thread(_fetch_widget_data)
    except Exception as exc:
        logger.error(f"LNG widget data fetch failed: {exc}", exc_info=True)
        data = {'daily': [], 'daily_hist': [], 'geri_live': None, 'ttf': None}
    html = _render_widget_html(data, pro=True)
    return HTMLResponse(content=html, headers={"Cache-Control": "public, max-age=120"})


# ─────────────────────────────────────────────────────────────────────────────
# /widgets/jkm-lng-price — SEO landing page + funnel
# ─────────────────────────────────────────────────────────────────────────────

_LANDING_CSS = f"""
.lng-w-protected {{ user-select:none; -webkit-user-select:none; }}

/* Hero */
.lng-w-hero{{text-align:center; padding:60px 20px 40px; background:linear-gradient(180deg,#0b0f1a 0%,#0e1422 100%);}}
.lng-w-hero h1{{font-family:'DM Serif Display',Georgia,serif; font-size:clamp(32px,5vw,52px); line-height:1.15; margin:0 0 18px; color:#fff;}}
.lng-w-hero h1 span{{color:{LNG_COLOR};}}
.lng-w-hero p{{font-size:clamp(14px,1.6vw,17px); color:#94a3b8; max-width:680px; margin:0 auto 26px; line-height:1.65;}}
.lng-w-cta-row{{display:flex; gap:12px; justify-content:center; flex-wrap:wrap; margin-bottom:24px;}}
.lng-w-cta-primary{{background:linear-gradient(135deg,{LNG_COLOR},{LNG_COLOR2}); color:#0a0f1e !important; text-decoration:none; font-weight:800; font-size:14.5px; padding:13px 26px; border-radius:10px; box-shadow:0 6px 24px rgba(212,160,23,0.18);}}
.lng-w-cta-secondary{{background:transparent; color:#cbd5e1 !important; border:1px solid rgba(255,255,255,0.18); text-decoration:none; font-weight:600; font-size:14px; padding:13px 26px; border-radius:10px;}}
.lng-w-cta-secondary:hover{{border-color:rgba(212,160,23,0.5); color:#fff !important;}}

/* Trust micro-bar */
.lng-w-trust{{display:flex; gap:18px; justify-content:center; flex-wrap:wrap; font-size:11.5px; color:#94a3b8; max-width:880px; margin:0 auto;}}
.lng-w-trust span{{display:inline-flex; align-items:center; gap:6px;}}
.lng-w-trust span::before{{content:'\u2713'; color:#22c55e; font-weight:800;}}

/* Section common */
.lng-w-section{{padding:48px 22px; max-width:1100px; margin:0 auto;}}
.lng-w-section h2{{font-family:'DM Serif Display',Georgia,serif; font-size:clamp(24px,3.5vw,34px); color:#fff; text-align:center; margin:0 0 14px;}}
.lng-w-section h2 + p{{text-align:center; color:#94a3b8; max-width:660px; margin:0 auto 32px; font-size:14px; line-height:1.65;}}

/* Widget preview frame */
.lng-w-preview-wrap{{display:flex; gap:24px; justify-content:center; align-items:flex-start; flex-wrap:wrap;}}
.lng-w-preview-col{{flex:1 1 360px; max-width:420px; background:#0e1422; border:1px solid var(--border); border-radius:16px; padding:22px;}}
.lng-w-preview-col h3{{font-size:13px; font-weight:800; color:#cbd5e1; margin:0 0 14px; letter-spacing:0.5px; text-align:center;}}
.lng-w-iframe-shell{{background:linear-gradient(135deg,#020617,#0a0f1d); border-radius:12px; padding:14px;}}
.lng-w-preview-note{{font-size:11px; color:#64748b; margin-top:12px; text-align:center;}}
.lng-w-preview-pro{{position:relative; background:linear-gradient(135deg,{LNG_COLOR} 0%,{LNG_COLOR2} 100%); padding:1px; border-radius:17px;}}
.lng-w-preview-pro .lng-w-preview-col{{margin:0; border:none;}}

/* Embed code box */
.lng-w-embed-box{{background:#020617; border:1px solid rgba(212,160,23,0.25); border-radius:12px; padding:0; max-width:780px; margin:0 auto 14px; overflow:hidden;}}
.lng-w-embed-head{{display:flex; justify-content:space-between; align-items:center; padding:10px 16px; border-bottom:1px solid rgba(255,255,255,0.06); font-size:11px; font-weight:700; color:#64748b; letter-spacing:1px; text-transform:uppercase;}}
.lng-w-embed-copy{{background:rgba(212,160,23,0.15); color:{LNG_COLOR}; border:1px solid rgba(212,160,23,0.35); border-radius:6px; font-size:11px; font-weight:700; padding:5px 14px; cursor:pointer; letter-spacing:0.3px;}}
.lng-w-embed-copy:hover{{background:rgba(212,160,23,0.25);}}
.lng-w-embed-code{{font-family:'JetBrains Mono',ui-monospace,monospace; font-size:12.5px; color:#94a3b8; line-height:1.7; padding:16px 18px; margin:0; white-space:pre-wrap; word-break:break-word; overflow-x:auto;}}
.lng-w-embed-code .tk{{color:{LNG_COLOR};}}
.lng-w-embed-micro{{text-align:center; font-size:11.5px; color:#64748b; max-width:680px; margin:0 auto;}}

/* Why cards */
.lng-w-why-grid{{display:grid; grid-template-columns:repeat(4,1fr); gap:14px;}}
@media (max-width:920px){{.lng-w-why-grid{{grid-template-columns:1fr 1fr;}}}}
@media (max-width:500px){{.lng-w-why-grid{{grid-template-columns:1fr;}}}}
.lng-w-why-card{{background:var(--card); border:1px solid var(--border); border-radius:14px; padding:20px;}}
.lng-w-why-icon{{font-size:1.7rem; margin-bottom:8px;}}
.lng-w-why-title{{font-size:14px; font-weight:800; color:#f1f5f9; margin-bottom:6px;}}
.lng-w-why-body{{font-size:12.5px; color:#94a3b8; line-height:1.6;}}

/* Comparison table */
.lng-w-compare-wrap{{overflow-x:auto;}}
.lng-w-compare{{width:100%; border-collapse:collapse; min-width:520px; background:var(--card); border:1px solid var(--border); border-radius:14px; overflow:hidden;}}
.lng-w-compare th, .lng-w-compare td{{padding:12px 16px; text-align:center; font-size:13px; border-bottom:1px solid rgba(255,255,255,0.04);}}
.lng-w-compare th{{background:rgba(255,255,255,0.02); font-size:11px; font-weight:800; letter-spacing:1.2px; text-transform:uppercase; color:#64748b;}}
.lng-w-compare th.col-pro{{color:{LNG_COLOR};}}
.lng-w-compare td:first-child{{text-align:left; color:#cbd5e1; font-weight:600;}}
.lng-w-compare tr:last-child td{{border-bottom:none;}}
.tick{{color:#22c55e; font-weight:800;}}
.cross{{color:#475569;}}

/* Use cases */
.lng-w-uses-grid{{display:grid; grid-template-columns:repeat(3,1fr); gap:12px;}}
@media (max-width:780px){{.lng-w-uses-grid{{grid-template-columns:1fr 1fr;}}}}
@media (max-width:460px){{.lng-w-uses-grid{{grid-template-columns:1fr;}}}}
.lng-w-use-card{{background:var(--card); border:1px solid var(--border); border-radius:12px; padding:16px 18px; display:flex; align-items:center; gap:10px; font-size:13px; color:#cbd5e1; font-weight:600;}}
.lng-w-use-card::before{{content:'\u2713'; color:#22c55e; font-weight:800;}}

/* SEO content */
.lng-w-seo-block{{background:var(--card); border:1px solid var(--border); border-radius:14px; padding:26px 28px;}}
.lng-w-seo-block h3{{font-size:16px; font-weight:700; color:#f1f5f9; margin:18px 0 8px;}}
.lng-w-seo-block h3:first-child{{margin-top:0;}}
.lng-w-seo-block p{{font-size:13.5px; color:#94a3b8; line-height:1.75; margin:0 0 10px;}}
.lng-w-seo-block a{{color:{LNG_COLOR}; text-decoration:none; font-weight:700;}}
.lng-w-seo-block a:hover{{text-decoration:underline;}}

/* Insight */
.lng-w-insight{{background:linear-gradient(135deg,#0c1322 0%,#15110a 50%,#0c1322 100%); border:1px solid rgba(212,160,23,0.25); border-radius:16px; padding:28px 30px; max-width:880px; margin:0 auto;}}
.lng-w-insight h3{{font-size:15px; color:{LNG_COLOR}; margin:0 0 12px; letter-spacing:0.5px; text-transform:uppercase; font-weight:800;}}
.lng-w-insight p{{font-size:14px; color:#cbd5e1; line-height:1.8; margin:0 0 12px;}}
.lng-w-insight p:last-child{{margin-bottom:0;}}
.lng-w-insight .lng-w-insight-tag{{font-size:11px; color:#64748b; margin-top:14px; font-style:italic;}}

/* Internal links */
.lng-w-links-tier{{margin-bottom:22px;}}
.lng-w-links-tier h3{{font-size:12px; font-weight:800; letter-spacing:1.2px; text-transform:uppercase; color:#64748b; margin:0 0 12px; text-align:center;}}
.lng-w-links-grid{{display:flex; flex-wrap:wrap; gap:10px; justify-content:center;}}
.lng-w-link-pill{{background:var(--card); border:1px solid var(--border); border-radius:999px; padding:9px 18px; font-size:13px; color:#cbd5e1; text-decoration:none; font-weight:600;}}
.lng-w-link-pill:hover{{border-color:rgba(212,160,23,0.5); color:#fff;}}

/* FAQ */
.lng-w-faq details{{background:var(--card); border:1px solid var(--border); border-radius:10px; margin-bottom:10px; overflow:hidden;}}
.lng-w-faq summary{{list-style:none; cursor:pointer; padding:16px 50px 16px 20px; font-size:14px; font-weight:700; color:#f1f5f9; position:relative;}}
.lng-w-faq summary::-webkit-details-marker{{display:none;}}
.lng-w-faq summary::after{{content:'+'; position:absolute; right:18px; top:50%; transform:translateY(-50%); font-size:22px; color:{LNG_COLOR};}}
.lng-w-faq details[open] summary::after{{content:'\u2212';}}
.lng-w-faq details > div{{padding:0 20px 18px; font-size:13.5px; color:#94a3b8; line-height:1.7;}}

/* Conversion */
.lng-w-conv{{background:linear-gradient(135deg,#0c1322 0%,#1c1608 50%,#0f172a 100%); border:1px solid rgba(212,160,23,0.3); border-radius:18px; padding:38px 28px; text-align:center; max-width:780px; margin:0 auto;}}
.lng-w-conv h2{{font-family:'DM Serif Display',serif; font-size:clamp(22px,3.5vw,30px); color:#fff; margin:0 0 12px;}}
.lng-w-conv p{{color:#94a3b8; max-width:560px; margin:0 auto 22px; font-size:14px;}}

/* Cite */
.lng-w-cite-card{{background:var(--card); border:1px solid var(--border); border-radius:14px; padding:24px 26px; max-width:880px; margin:0 auto 40px; position:relative;}}
.lng-w-cite-card h3{{font-size:16px; color:#f1f5f9; margin-bottom:6px;}}
.lng-w-cite-card .lng-w-cite-desc{{font-size:13px; color:#94a3b8; margin-bottom:14px;}}
.lng-w-cite-code-wrap{{background:rgba(0,0,0,0.25); border-radius:10px; padding:16px 18px; position:relative;}}
.lng-w-cite-code{{font-family:'JetBrains Mono',ui-monospace,monospace; font-size:12px; color:#cbd5e1; line-height:1.7; margin:0; white-space:pre-wrap; word-break:break-word;}}
.lng-w-cite-code a{{color:{LNG_COLOR}; text-decoration:none;}}
.lng-w-cite-btn{{position:absolute; top:12px; right:12px; background:rgba(212,160,23,0.15); color:{LNG_COLOR}; border:1px solid rgba(212,160,23,0.35); border-radius:6px; font-size:11px; font-weight:700; padding:5px 12px; cursor:pointer;}}
@media (max-width:560px){{.lng-w-cite-btn{{position:static; display:block; width:100%; margin-top:12px;}}}}

/* Footer license */
.lng-w-license{{max-width:880px; margin:0 auto 30px; background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.06); border-radius:10px; padding:18px 20px; font-size:12px; color:#94a3b8;}}
.lng-w-license a{{color:{LNG_COLOR}; text-decoration:none; font-weight:700;}}
"""


def _build_landing_html(today_str):
    embed_code = (
        '&lt;<span class="tk">iframe</span>\n'
        f'  src=&quot;{BASE_URL}{WIDGET_PATH}&quot;\n'
        '  width=&quot;100%&quot;\n'
        '  height=&quot;300&quot;\n'
        '  frameborder=&quot;0&quot;\n'
        '  loading=&quot;lazy&quot;&gt;\n'
        '&lt;/<span class="tk">iframe</span>&gt;'
    )
    embed_code_plain = (
        f'<iframe src="{BASE_URL}{WIDGET_PATH}" '
        'width="100%" height="300" frameborder="0" loading="lazy"></iframe>'
    )

    faqs = [
        ("What is JKM LNG?",
         "JKM (Japan Korea Marker) is the leading spot price benchmark for liquefied natural gas (LNG) "
         "delivered into Northeast Asia &mdash; principally Japan, South Korea, China and Taiwan. It is the "
         "reference price for Asian LNG cargoes and one of the most important indicators in the global gas "
         "market, quoted in US dollars per million British thermal units ($/MMBtu)."),
        ("How often is the LNG widget updated?",
         "The widget reflects EnergyRiskIQ&rsquo;s daily JKM LNG assessment from the production data pipeline, "
         "alongside live GERI energy-risk signals from the geri_live engine. JKM is a daily-assessed benchmark, "
         "so the widget refreshes each trading day as new LNG market data is published."),
        ("Is the LNG widget free?",
         "Yes &mdash; the standard Global LNG Market widget is free for personal and commercial use, provided the "
         "EnergyRiskIQ attribution remains visible. For an unbranded, white-label version with 7-day and 30-day "
         f"charts and spread analysis, the Pro widget is available from &euro;{PRO_PRICE_EUR}/month."),
        ("Can I use it commercially?",
         "Yes &mdash; commercial use is permitted on the free widget under the EnergyRiskIQ data licence "
         "(CC BY-NC 4.0), so long as the EnergyRiskIQ attribution is preserved and visible. For commercial "
         "redistribution without attribution, the Pro widget removes branding entirely."),
        ("Can I remove EnergyRiskIQ branding?",
         "Branding removal is only available on the Pro widget. The free widget requires the EnergyRiskIQ "
         "attribution link to remain visible &mdash; this funds the data pipeline that keeps the widget free."),
        ("What is the difference between JKM and TTF?",
         "JKM is the Asian LNG spot benchmark (USD/MMBtu), while TTF (Dutch Title Transfer Facility) is the "
         "European natural gas benchmark (EUR/MWh). The JKM&ndash;TTF spread signals whether Europe or Asia is "
         "paying more for gas &mdash; when JKM trades at a premium, Atlantic-basin LNG cargoes are pulled toward "
         "Asia, tightening European supply."),
    ]
    faq_html = ''
    for q, a in faqs:
        faq_html += (
            f'<details><summary>{_html.escape(q)}</summary>'
            f'<div>{a}</div></details>'
        )
    faqpage_schema = _json.dumps({
        "@context": "https://schema.org", "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": q,
             "acceptedAnswer": {"@type": "Answer", "text": _html.unescape(a)}}
            for q, a in faqs
        ],
    })

    webpage_schema = _json.dumps({
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": "Free JKM LNG Price Widget for Websites",
        "url": LANDING_URL,
        "description": "Embed a free JKM LNG price widget on your website. Live LNG prices, market signals, LNG supply trends, and energy risk intelligence from EnergyRiskIQ.",
        "isAccessibleForFree": True,
        "publisher": {"@type": "Organization", "name": "EnergyRiskIQ", "url": BASE_URL},
        "license": f"{BASE_URL}/data-license",
    })

    sw_schema = _json.dumps({
        "@context": "https://schema.org",
        "@type": "SoftwareApplication",
        "name": "EnergyRiskIQ Global LNG Market Widget",
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
            {"@type": "ListItem", "position": 2, "name": "Widgets", "item": LANDING_URL},
            {"@type": "ListItem", "position": 3, "name": "Global LNG Market Widget", "item": LANDING_URL},
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
      var attr = '\\n\\n[Source: EnergyRiskIQ.com — Global LNG Market Widget | CC BY-NC 4.0]';
      e.clipboardData.setData('text/plain', sel + attr);
      e.preventDefault();
    }}
  }});
  document.addEventListener('contextmenu', function(e) {{
    var t = e.target;
    if (t && (t.classList && t.classList.contains('lng-w-protected') || (t.closest && t.closest('.lng-w-protected')))) {{
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
      <a href="/data/jkm-lng-spot-price" style="font-size:13px;color:#94a3b8;text-decoration:none;">JKM LNG</a>
      <a href="/data/ttf-gas-price-today" style="font-size:13px;color:#94a3b8;text-decoration:none;">TTF</a>
      <a href="/indices/global-energy-risk-index" style="font-size:13px;color:#94a3b8;text-decoration:none;">GERI</a>
      <a href="/users" class="cta-btn-nav">Get Free Access</a>
    </div>
  </div>
</nav>

<!-- ── 1. HERO ───────────────────────────────────────────────────── -->
<header class="lng-w-hero">
  <h1>Free <span>JKM LNG Price Widget</span><br>for Websites</h1>
  <p>
    Embed live LNG market intelligence on your website, newsletter, dashboard, or research portal.
    Track JKM LNG prices, market trends, and energy risk signals with a free embeddable widget &mdash;
    powered by Custom Algorithms.
  </p>
  <div class="lng-w-cta-row">
    <a href="#embed" class="lng-w-cta-primary">Get Free Widget Code &darr;</a>
    <a href="#pro" class="lng-w-cta-secondary">Unlock Pro LNG Widget (&euro;{PRO_PRICE_EUR}/mo)</a>
  </div>
  <div class="lng-w-trust">
    <span>LNG market data</span>
    <span>Daily updates</span>
    <span>Energy risk signals</span>
    <span>Mobile responsive</span>
    <span>Free commercial use</span>
  </div>
</header>

<!-- ── 2. LIVE WIDGET PREVIEW ────────────────────────────────────── -->
<section class="lng-w-section" id="preview">
  <h2>Live LNG Widget Preview</h2>
  <p>Real-time render of the free embeddable widget. This is exactly what your visitors will see &mdash; LNG price, market trend, energy risk and the JKM&ndash;TTF spread.</p>
  <div class="lng-w-preview-wrap">
    <div class="lng-w-preview-col">
      <h3>FREE WIDGET &middot; LIVE RENDER</h3>
      <div class="lng-w-iframe-shell">
        <iframe src="{WIDGET_PATH}" width="100%" height="320" frameborder="0"
                style="border:0;display:block;border-radius:10px;background:transparent;"
                loading="lazy" title="Global LNG Market Widget"></iframe>
      </div>
      <div class="lng-w-preview-note">Branded &middot; required attribution &middot; CC BY-NC 4.0</div>
    </div>
  </div>
</section>

<!-- ── 3. EMBED SECTION ──────────────────────────────────────────── -->
<section class="lng-w-section" id="embed">
  <h2>Copy &amp; Paste This Widget Into Your Website</h2>
  <p>One-line iframe embed. Works in any HTML page, blog editor, CMS, or dashboard.</p>
  <div class="lng-w-embed-box">
    <div class="lng-w-embed-head">
      <span>HTML &middot; iframe embed</span>
      <button class="lng-w-embed-copy" id="copyEmbedBtn">Copy Code</button>
    </div>
    <pre class="lng-w-embed-code" id="embedCode">{embed_code}</pre>
  </div>
  <p class="lng-w-embed-micro">Free to use with EnergyRiskIQ attribution &middot; loads in &lt;200ms &middot; mobile-responsive.</p>
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

<!-- ── 4. WHY PUBLISHERS USE THIS WIDGET ─────────────────────────── -->
<section class="lng-w-section">
  <h2>Why Publishers Use This LNG Widget</h2>
  <div class="lng-w-why-grid">
    <div class="lng-w-why-card">
      <div class="lng-w-why-icon">&#127760;</div>
      <div class="lng-w-why-title">LNG Market Intelligence</div>
      <div class="lng-w-why-body">Goes beyond price &mdash; shows the LNG market trend and energy-risk regime so your visitors see context, not just a number.</div>
    </div>
    <div class="lng-w-why-card">
      <div class="lng-w-why-icon">&#9875;</div>
      <div class="lng-w-why-title">Asia&ndash;Europe LNG Monitoring</div>
      <div class="lng-w-why-body">Tracks the JKM Asian LNG benchmark and the JKM&ndash;TTF spread that governs cargo competition between Europe and Asia.</div>
    </div>
    <div class="lng-w-why-card">
      <div class="lng-w-why-icon">&#9888;&#65039;</div>
      <div class="lng-w-why-title">Energy Risk Signals</div>
      <div class="lng-w-why-body">Links LNG prices with EnergyRiskIQ&rsquo;s live GERI risk signal &mdash; instant insight into the global energy risk backdrop.</div>
    </div>
    <div class="lng-w-why-card">
      <div class="lng-w-why-icon">&#9889;</div>
      <div class="lng-w-why-title">Fast Lightweight Embed</div>
      <div class="lng-w-why-body">Perfect for blogs, dashboards and research portals &mdash; under 200ms render, zero JS dependencies, fully responsive.</div>
    </div>
  </div>
</section>

<!-- ── 5. FREE VS PRO COMPARISON ─────────────────────────────────── -->
<section class="lng-w-section" id="compare">
  <h2>Free vs Professional LNG Widget</h2>
  <p>Both widgets carry the same live LNG data &mdash; Pro removes branding and unlocks charts, spread analysis and intelligence.</p>
  <div class="lng-w-compare-wrap">
    <table class="lng-w-compare">
      <thead>
        <tr>
          <th style="text-align:left;">Feature</th>
          <th>Free Widget</th>
          <th class="col-pro">Pro Widget (&euro;{PRO_PRICE_EUR}/mo)</th>
        </tr>
      </thead>
      <tbody>
        <tr><td>JKM LNG Price</td><td><span class="tick">&#10003;</span></td><td><span class="tick">&#10003;</span></td></tr>
        <tr><td>Daily Trend</td><td><span class="tick">&#10003;</span></td><td><span class="tick">&#10003;</span></td></tr>
        <tr><td>LNG Market Signal</td><td><span class="tick">&#10003;</span></td><td><span class="tick">&#10003;</span></td></tr>
        <tr><td>EnergyRiskIQ Branding</td><td>Required</td><td><span class="cross">Removed</span></td></tr>
        <tr><td>Citation Required</td><td>Required</td><td><span class="cross">Not Required</span></td></tr>
        <tr><td>7-Day LNG Chart</td><td><span class="cross">&#10005;</span></td><td><span class="tick">&#10003;</span></td></tr>
        <tr><td>30-Day LNG Chart</td><td><span class="cross">&#10005;</span></td><td><span class="tick">&#10003;</span></td></tr>
        <tr><td>JKM vs TTF Spread</td><td><span class="tick">&#10003;</span></td><td><span class="tick">&#10003;</span></td></tr>
        <tr><td>LNG Intelligence Analysis</td><td><span class="cross">&#10005;</span></td><td><span class="tick">&#10003;</span></td></tr>
        <tr><td>LNG Supply Context</td><td><span class="cross">&#10005;</span></td><td><span class="tick">&#10003;</span></td></tr>
        <tr><td>Energy Risk Overlay</td><td><span class="cross">&#10005;</span></td><td><span class="tick">&#10003;</span></td></tr>
        <tr><td>White Label Usage</td><td><span class="cross">&#10005;</span></td><td><span class="tick">&#10003;</span></td></tr>
        <tr><td>Transparent Background</td><td><span class="cross">&#10005;</span></td><td><span class="tick">&#10003;</span></td></tr>
      </tbody>
    </table>
  </div>
  <div style="text-align:center;margin-top:24px;">
    <a href="/users" class="lng-w-cta-primary">Create Free Account &amp; Unlock Pro LNG Widget &rarr;</a>
  </div>
</section>

<!-- ── 6. PRO WIDGET PREVIEW ─────────────────────────────────────── -->
<section class="lng-w-section" id="pro">
  <h2>Professional LNG Market Widget</h2>
  <p>Significantly more value &mdash; 7-day and 30-day LNG charts, the JKM&ndash;TTF spread, and a daily LNG market intelligence read, fully unbranded with a transparent background.</p>
  <div class="lng-w-preview-wrap">
    <div class="lng-w-preview-pro">
      <div class="lng-w-preview-col" style="background:transparent;">
        <h3 style="color:#fff;">PRO WIDGET &middot; UNBRANDED PREVIEW</h3>
        <div class="lng-w-iframe-shell" style="background:#020617;">
          <iframe src="/embed/jkm-lng-widget-pro" width="100%" height="420" frameborder="0"
                  style="border:0;display:block;border-radius:10px;background:transparent;"
                  loading="lazy" title="Pro LNG Widget Preview"></iframe>
        </div>
        <div class="lng-w-preview-note" style="color:#94a3b8;">
          No branding &middot; transparent background &middot; white-label ready
        </div>
      </div>
    </div>
  </div>
  <div style="text-align:center;margin-top:24px;">
    <a href="/users" class="lng-w-cta-primary">Upgrade for &euro;{PRO_PRICE_EUR}/month &rarr;</a>
  </div>
</section>

<!-- ── 7. SEO CONTENT ────────────────────────────────────────────── -->
<section class="lng-w-section">
  <h2>JKM LNG Price Today</h2>
  <div class="lng-w-seo-block">
    <h3>What Is JKM LNG?</h3>
    <p>
      JKM (Japan Korea Marker) is the benchmark spot price for liquefied natural gas (LNG) delivered into
      Northeast Asia &mdash; the world&rsquo;s largest LNG-importing region, led by Japan, South Korea, China
      and Taiwan. Quoted in US dollars per MMBtu, JKM is the reference price for Asian LNG cargoes and the
      single most-watched indicator of global LNG market tightness. As the world increasingly trades gas as
      seaborne LNG rather than via pipeline, JKM has become a global energy benchmark in its own right.
    </p>
    <h3>Why LNG Prices Matter</h3>
    <p>
      LNG sits at the centre of European gas markets and global energy security. Europe replaced lost Russian
      pipeline gas with seaborne LNG imports, putting the continent in direct competition with Asia for every
      flexible cargo. When JKM rises, cargoes are pulled toward Asia and away from Europe &mdash; tightening
      <a href="/gas-storage-levels-in-europe">European gas storage</a> and lifting
      <a href="/data/ttf-gas-price-today">TTF prices</a>. LNG flows therefore shape inflation, industrial
      competitiveness and winter supply risk across the entire Atlantic basin.
    </p>
    <h3>What Drives LNG Prices?</h3>
    <p>
      LNG prices are driven by Asian weather and power demand, European gas storage needs, shipping and
      freight availability, geopolitical risk, oil-indexed contract pricing, and the JKM&ndash;TTF arbitrage
      that routes cargoes between basins. For a full breakdown of every driver, see our research guide:
      &rarr; <a href="/research/what-drives-lng-prices">What Drives LNG Prices</a>.
    </p>
  </div>
</section>

<!-- ── 8. LNG MARKET INSIGHT ─────────────────────────────────────── -->
<section class="lng-w-section">
  <h2>Today&rsquo;s LNG Market Analysis</h2>
  <div class="lng-w-insight lng-w-protected">
    <h3>Global LNG Market Read</h3>
    <p>
      LNG markets remain shaped by the constant competition for flexible cargoes between Europe and Asia.
      The JKM&ndash;TTF spread is the decisive signal: when Asian JKM trades at a premium to European TTF,
      Atlantic-basin LNG is diverted eastward, tightening European supply; when the spread narrows or
      inverts, more cargoes stay in Europe to refill storage.
    </p>
    <p>
      Steady Asian demand &mdash; from Japanese and South Korean power utilities and Chinese industrial
      buyers &mdash; continues to underpin the global LNG balance, while European storage targets and
      seasonal injection needs set the floor for how aggressively the continent must bid for supply.
      The widget&rsquo;s live LNG market trend and energy-risk signals summarise this backdrop at a glance.
    </p>
    <div class="lng-w-insight-tag">Generated daily by EnergyRiskIQ Custom Algorithms &middot; not financial advice.</div>
  </div>
</section>

<!-- ── 9. USE CASES ──────────────────────────────────────────────── -->
<section class="lng-w-section">
  <h2>Perfect For</h2>
  <div class="lng-w-uses-grid">
    <div class="lng-w-use-card">LNG news sites</div>
    <div class="lng-w-use-card">Energy blogs</div>
    <div class="lng-w-use-card">Commodity research</div>
    <div class="lng-w-use-card">Trading communities</div>
    <div class="lng-w-use-card">LNG shipping portals</div>
    <div class="lng-w-use-card">Energy consultancies</div>
  </div>
</section>

<!-- ── 10. INTERNAL LINKING ──────────────────────────────────────── -->
<section class="lng-w-section">
  <h2>Explore the EnergyRiskIQ LNG &amp; Gas Network</h2>
  <p>Go deeper with our LNG, gas, and energy-risk intelligence pages.</p>

  <div class="lng-w-links-tier">
    <h3>LNG Cluster</h3>
    <div class="lng-w-links-grid">
      <a href="/data/jkm-lng-spot-price" class="lng-w-link-pill">&#9875; JKM LNG Spot Price</a>
      <a href="/data/europe-lng-supply-demand" class="lng-w-link-pill">&#127757; Europe LNG Supply &amp; Demand</a>
    </div>
  </div>

  <div class="lng-w-links-tier">
    <h3>Gas Storage Cluster</h3>
    <div class="lng-w-links-grid">
      <a href="/gas-storage-levels-in-europe" class="lng-w-link-pill">&#128202; Gas Storage Levels in Europe</a>
      <a href="/gas-storage-levels-germany" class="lng-w-link-pill">&#127465;&#127466; Germany Gas Storage Levels</a>
    </div>
  </div>

  <div class="lng-w-links-tier">
    <h3>Gas Price Cluster</h3>
    <div class="lng-w-links-grid">
      <a href="/data/natural-gas-price-today-europe" class="lng-w-link-pill">&#128293; Natural Gas Price Today Europe</a>
      <a href="/data/ttf-gas-price-today" class="lng-w-link-pill">&#128176; TTF Gas Price Today</a>
    </div>
  </div>

  <div class="lng-w-links-tier">
    <h3>Risk Cluster</h3>
    <div class="lng-w-links-grid">
      <a href="/indices/europe-energy-risk-index" class="lng-w-link-pill">&#127466;&#127482; Europe Energy Risk Index</a>
      <a href="/indices/europe-gas-stress-index" class="lng-w-link-pill">&#128137; Europe Gas Stress Index</a>
      <a href="/indices/global-energy-risk-index" class="lng-w-link-pill">&#127758; Global Energy Risk Index</a>
    </div>
  </div>

  <div class="lng-w-links-tier">
    <h3>Research</h3>
    <div class="lng-w-links-grid">
      <a href="/research/what-drives-lng-prices" class="lng-w-link-pill">&#128218; What Drives LNG Prices</a>
      <a href="/research/global-energy-risk-timeline" class="lng-w-link-pill">&#128337; Global Energy Risk Timeline</a>
    </div>
  </div>
</section>

<!-- ── 11. WIDGET ECOSYSTEM ──────────────────────────────────────── -->
<section class="lng-w-section">
  <h2>Related Energy Widgets</h2>
  <p>Build a complete energy intelligence layer on your site with the full EnergyRiskIQ widget network.</p>
  <div class="lng-w-links-grid">
    <a href="/widgets/wti-crude-oil-price" class="lng-w-link-pill">&#128738; WTI Crude Oil Widget</a>
    <a href="/widgets/europe-gas-storage-levels" class="lng-w-link-pill">&#128202; Europe Gas Storage Widget</a>
  </div>
</section>

<!-- ── 12. FAQ ───────────────────────────────────────────────────── -->
<section class="lng-w-section">
  <h2>Frequently Asked Questions</h2>
  <div class="lng-w-faq">{faq_html}</div>
</section>

<!-- ── CITATION & REFERENCE ──────────────────────────────────────── -->
<section class="lng-w-section">
  <h2>Citation &amp; Reference</h2>
  <div class="lng-w-cite-card">
    <h3>How to Cite This Widget</h3>
    <div class="lng-w-cite-desc">
      When using the LNG widget in research, journalism, dashboards or professional reports, please cite the source as follows.
    </div>
    <div class="lng-w-cite-code-wrap">
      <pre class="lng-w-cite-code">EnergyRiskIQ. (2026). <em>Global LNG Market Widget &mdash; JKM LNG Price, {today_str}</em>.
Retrieved from <a href="{LANDING_URL}">{LANDING_URL}</a>
Live data: <a href="{DATA_URL}">{DATA_URL}</a>
Custom Algorithm interpretation. Data sources: JKM LNG daily assessment, TTF gas benchmark, GERI live risk engine.</pre>
      <button class="lng-w-cite-btn" onclick="this.textContent='Copied!';setTimeout(()=>this.textContent='Copy',2000);navigator.clipboard&amp;&amp;navigator.clipboard.writeText('EnergyRiskIQ. (2026). Global LNG Market Widget — JKM LNG Price, {today_str}. Retrieved from {LANDING_URL}')">Copy</button>
    </div>
  </div>
</section>

<!-- ── 13. FINAL CONVERSION ──────────────────────────────────────── -->
<section class="lng-w-section">
  <div class="lng-w-conv">
    <h2>Upgrade to the Professional LNG Market Widget</h2>
    <p>
      Unlock 7-day and 30-day LNG charts, JKM&ndash;TTF spread analysis, LNG intelligence signals, and
      white-label usage for your website or application &mdash; for less than the price of a coffee per month.
    </p>
    <div class="lng-w-cta-row" style="margin-bottom:0;">
      <a href="/users" class="lng-w-cta-primary">Create Free Account &rarr;</a>
      <a href="#compare" class="lng-w-cta-secondary">Compare Free vs Pro</a>
    </div>
  </div>
</section>

<!-- ── FOOTER LICENSE ────────────────────────────────────────────── -->
<div class="lng-w-license">
  <strong>Data disclaimer:</strong> LNG prices shown in the widget are provided for informational purposes only and
  do not constitute financial advice. Data is delivered under the EnergyRiskIQ
  <a href="/data-license">data licence (CC BY-NC 4.0)</a>. Commercial redistribution without attribution
  is not permitted on the free widget &mdash; the Pro plan grants full white-label rights.
</div>

<footer class="page-footer">
  <div>
    &copy; 2026 EnergyRiskIQ &bull;
    <a href="/">Home</a>
    <a href="/data/jkm-lng-spot-price">JKM LNG</a>
    <a href="/data/ttf-gas-price-today">TTF Gas</a>
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
    'JKM LNG Price Today Widget | Free LNG Market Widget'
).replace(
    'name="description" content="Live global energy risk snapshot. Current GERI, EERI and EGSI-M index values with Brent crude, TTF gas, VIX and LNG market prices."',
    'name="description" content="Embed a free JKM LNG price widget on your website. Live LNG prices, market signals, LNG supply trends, and energy risk intelligence from EnergyRiskIQ."'
).replace(
    'rel="canonical" href="https://energyriskiq.com/data/energy-risk-snapshot"',
    f'rel="canonical" href="{LANDING_URL}"'
).replace(
    'Fetching GERI\u00a0&\u00a0EERI indices\u2026',
    'Loading LNG widget preview\u2026',
).replace(
    '<span class="ld-tag">GERI</span>\n    <span class="ld-tag">EERI</span>\n    <span class="ld-tag">EGSI&#8209;M</span>\n    <span class="ld-tag">Brent</span>\n    <span class="ld-tag">TTF</span>',
    '<span class="ld-tag">JKM LNG</span>\n    <span class="ld-tag">Widget</span>\n    <span class="ld-tag">Embed</span>\n    <span class="ld-tag">GERI</span>',
)


@router.get("/widgets/jkm-lng-price")
async def lng_widget_landing():
    async def generate():
        yield _WIDGET_LOADER_HTML
        try:
            today_str = datetime.now(timezone.utc).strftime('%B %-d, %Y')
            html = await asyncio.to_thread(_build_landing_html, today_str)
            yield html
        except Exception as exc:
            logger.error(f"LNG widget landing render failed: {exc}", exc_info=True)
            yield (
                "<script>var l=document.getElementById('snap-loader');"
                "if(l)l.style.display='none';document.body.style.overflow='';</script>"
                f"<div style='color:#ef4444;padding:40px;font-family:sans-serif;background:#0b0f1a;'>"
                f"<h2>Error loading widget page</h2><p>{_html.escape(str(exc))}</p></div></body></html>"
            )

    return StreamingResponse(generate(), media_type="text/html")
