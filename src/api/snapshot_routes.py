"""
Energy Risk Snapshot Page
Route: /data/energy-risk-snapshot
SEO-optimized live page showing current global energy risk state.
"""
import math
import json
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from src.db.db import execute_production_one, execute_production_query

router = APIRouter()
logger = logging.getLogger(__name__)

BAND_COLORS = {
    'LOW':      '#22c55e',
    'MODERATE': '#eab308',
    'ELEVATED': '#f97316',
    'SEVERE':   '#ef4444',
    'CRITICAL': '#dc2626',
}

BAND_BG = {
    'LOW':      'rgba(34,197,94,0.12)',
    'MODERATE': 'rgba(234,179,8,0.12)',
    'ELEVATED': 'rgba(249,115,22,0.12)',
    'SEVERE':   'rgba(239,68,68,0.12)',
    'CRITICAL': 'rgba(220,38,38,0.15)',
}

WATCHLIST = [
    {
        "title": "Middle East Oil Infrastructure",
        "desc": "Monitor drone strike frequency and damage reports on UAE and Fujairah export facilities.",
        "slug": "middle-east-oil-infrastructure",
    },
    {
        "title": "Strait of Hormuz Traffic",
        "desc": "Vessel movements, tanker attack reports, and real-time chokepoint disruption signals.",
        "slug": "strait-of-hormuz-traffic",
    },
    {
        "title": "Ukraine Power Grid Attacks",
        "desc": "Frequency and scale of outages affecting European energy transmission and supply.",
        "slug": "ukraine-power-grid-attacks",
    },
    {
        "title": "Helium Supply Chains",
        "desc": "Semiconductor industry alerts on helium shortages, production cuts and price spikes.",
        "slug": "helium-supply-chains",
    },
    {
        "title": "European Gas Storage",
        "desc": "Weekly storage fill rates vs seasonal norms. Key indicator for winter supply cushion.",
        "slug": "european-gas-storage",
    },
    {
        "title": "Red Sea Shipping Corridor",
        "desc": "Houthi attack frequency and LNG/oil tanker rerouting around the Cape of Good Hope.",
        "slug": "red-sea-shipping-corridor",
    },
]


def _safe_float(val, default=0.0):
    try:
        return float(val) if val is not None else default
    except (TypeError, ValueError):
        return default


def _infographic_gauge_svg(value: int, band: str) -> str:
    """Infographic-sized speedometer gauge — viewBox 130×72, center (65,68), radius 56."""
    color = BAND_COLORS.get(band, '#f97316')

    def arc_pt(v, r=56):
        theta = math.pi - v * math.pi / 100
        return round(65 + r * math.cos(theta), 1), round(68 - r * math.sin(theta), 1)

    def needle_pt(v, r=46):
        theta = math.pi - v * math.pi / 100
        return round(65 + r * math.cos(theta), 1), round(68 - r * math.sin(theta), 1)

    p0   = arc_pt(0)
    p20  = arc_pt(20)
    p40  = arc_pt(40)
    p60  = arc_pt(60)
    p80  = arc_pt(80)
    p100 = arc_pt(100)
    npt  = needle_pt(value)

    return (
        f'<svg viewBox="0 0 130 72" xmlns="http://www.w3.org/2000/svg" style="width:130px;max-width:100%;display:block">'
        f'<path d="M{p0[0]},{p0[1]} A56,56 0 0,1 {p20[0]},{p20[1]}" fill="none" stroke="#22c55e" stroke-width="10" stroke-linecap="butt"/>'
        f'<path d="M{p20[0]},{p20[1]} A56,56 0 0,1 {p40[0]},{p40[1]}" fill="none" stroke="#eab308" stroke-width="10" stroke-linecap="butt"/>'
        f'<path d="M{p40[0]},{p40[1]} A56,56 0 0,1 {p60[0]},{p60[1]}" fill="none" stroke="#f97316" stroke-width="10" stroke-linecap="butt"/>'
        f'<path d="M{p60[0]},{p60[1]} A56,56 0 0,1 {p80[0]},{p80[1]}" fill="none" stroke="#ef4444" stroke-width="10" stroke-linecap="butt"/>'
        f'<path d="M{p80[0]},{p80[1]} A56,56 0 0,1 {p100[0]},{p100[1]}" fill="none" stroke="#dc2626" stroke-width="10" stroke-linecap="butt"/>'
        f'<line x1="65" y1="68" x2="{npt[0]}" y2="{npt[1]}" stroke="white" stroke-width="3" stroke-linecap="round"/>'
        f'<circle cx="65" cy="68" r="5.5" fill="{color}" stroke="rgba(255,255,255,0.85)" stroke-width="1.5"/>'
        f'<text x="5" y="71" fill="#6b7280" font-size="8" font-family="sans-serif">LOW</text>'
        f'<text x="109" y="71" fill="#6b7280" font-size="8" font-family="sans-serif">HIGH</text>'
        f'</svg>'
    )


def _build_infographic_html(
    today_str,
    geri_val, geri_band, geri_date, geri_delta,
    eeri_val, eeri_band, eeri_delta,
    egsi_val, egsi_band,
    brent_price, brent_chg, brent_chg_pct,
    ttf_price, ttf_chg,
    storage_pct,
) -> str:
    """Build the infographic section HTML. CSS uses plain string (no f-string brace issue)."""
    gc  = BAND_COLORS.get(geri_band,  '#f97316')
    ec  = BAND_COLORS.get(eeri_band,  '#f97316')
    mgc = BAND_COLORS.get(egsi_band,  '#f97316')

    geri_ig   = _infographic_gauge_svg(geri_val, geri_band)
    eeri_ig   = _infographic_gauge_svg(eeri_val, eeri_band)

    b_arrow  = '&#9650;' if brent_chg >= 0 else '&#9660;'
    b_color  = '#22c55e' if brent_chg >= 0 else '#ef4444'
    t_arrow  = '&#9650;' if ttf_chg >= 0   else '&#9660;'
    t_color  = '#22c55e' if ttf_chg >= 0   else '#ef4444'

    b_chg_str = ('+' if brent_chg >= 0 else '') + f'{brent_chg:.2f} | ' + ('+' if brent_chg_pct >= 0 else '') + f'{brent_chg_pct:.2f}% d/d'
    t_chg_str = ('+' if ttf_chg >= 0 else '') + f'{ttf_chg:.2f} d/d'

    g_delta = ('+' if geri_delta >= 0 else '') + str(geri_delta)
    e_delta = ('+' if eeri_delta >= 0 else '') + str(eeri_delta)

    eeri_change_note = 'unchanged' if eeri_delta == 0 else (f'+{eeri_delta}' if eeri_delta > 0 else str(eeri_delta))

    # Watchlist — 4 items to match image
    wl_items = ''
    for w in WATCHLIST[:4]:
        wl_items += (
            '<div class="ig-wl-item">'
            '<div class="ig-wl-check">&#10003;</div>'
            '<div class="ig-wl-body">'
            f'<div class="ig-wl-title">{w["title"]}</div>'
            f'<div class="ig-wl-desc">{w["desc"]}</div>'
            '</div></div>'
        )

    # Infographic footer interpretation
    price_action = 'mixed' if abs(brent_chg_pct) < 2.5 else ('falling' if brent_chg_pct < 0 else 'rising')
    footer_text = (
        f'So we have {price_action} price action, but a persistently tense risk regime and tight storage. '
        f'<strong>What to watch?</strong>'
    )

    # CSS as plain string (no brace doubling needed — not inside outer f-string)
    CSS = (
        '<style id="ig-styles">'
        '.ig-outer { margin-bottom: 44px; }'
        '.ig-topbar { display:flex; align-items:center; justify-content:space-between; margin-bottom:12px; }'
        '.ig-topbar-title { font-size:13px; font-weight:600; color:#94a3b8; }'
        '.ig-dl-btn { font-size:13px; font-weight:600; padding:9px 20px; border-radius:6px;'
        '  background:rgba(212,160,23,0.12); border:1px solid rgba(212,160,23,0.35);'
        '  color:#d4a017; cursor:pointer; transition:all 0.2s; }'
        '.ig-dl-btn:hover { background:rgba(212,160,23,0.22); color:#fbbf24; }'
        '.ig-root { background:#141926; border:1px solid rgba(255,255,255,0.08);'
        '  border-radius:12px; overflow:hidden; font-family:"Inter",sans-serif;'
        '  min-width:760px; }'
        '.ig-grid { display:grid;'
        '  grid-template:"prices clipboard" auto "indices clipboard" 1fr "footer footer" auto / 1fr 310px; }'
        '.ig-prices { grid-area:prices; display:flex; border-bottom:1px solid rgba(255,255,255,0.06); }'
        '.ig-price-card { flex:1; padding:22px 20px; position:relative; overflow:hidden; min-height:108px; }'
        '.ig-price-card + .ig-price-card { border-left:1px solid rgba(255,255,255,0.12); }'
        '.ig-brent-bg { background:#2d1a06; }'
        '.ig-ttf-bg   { background:#062030; }'
        '.ig-pc-img { position:absolute; top:0; left:0; width:100%; height:100%;'
        '  object-fit:cover; opacity:0.68; pointer-events:none; }'
        '.ig-pc-overlay { position:absolute; top:0; left:0; width:100%; height:100%; pointer-events:none;'
        '  background:linear-gradient(160deg,rgba(0,0,0,0.18) 0%,rgba(0,0,0,0.62) 100%); }'
        '.ig-pc-text { position:relative; z-index:2; }'
        '.ig-pc-label { font-size:11px; font-weight:700; letter-spacing:1.2px;'
        '  text-transform:uppercase; color:rgba(255,255,255,0.75); margin-bottom:7px;'
        '  text-shadow:0 1px 4px rgba(0,0,0,0.8); }'
        '.ig-pc-value { font-size:34px; font-weight:800; color:#fff; line-height:1; margin-bottom:7px;'
        '  text-shadow:0 2px 8px rgba(0,0,0,0.9); }'
        '.ig-pc-value sup { font-size:17px; vertical-align:top; margin-top:4px; }'
        '.ig-pc-unit { font-size:14px; font-weight:500; color:rgba(255,255,255,0.65); }'
        '.ig-pc-change { font-size:13px; font-weight:600; text-shadow:0 1px 4px rgba(0,0,0,0.8); }'
        '.ig-indices { grid-area:indices; padding:16px 18px;'
        '  border-right:1px solid rgba(255,255,255,0.06); background:#0f1522; }'
        '.ig-heading { font-size:16px; font-weight:700; color:#d4a017; margin-bottom:14px; }'
        '.ig-indices-body { display:grid; grid-template-columns:1fr 1fr; gap:0 20px; }'
        '.ig-left-col { }'
        '.ig-right-col { padding-left:16px; border-left:1px solid rgba(255,255,255,0.06);'
        '  grid-row:1/-1; }'
        '.ig-idx-label { font-size:11px; font-weight:700; color:#94a3b8; letter-spacing:0.5px;'
        '  margin-bottom:6px; }'
        '.ig-idx-row { display:flex; align-items:flex-start; gap:10px; margin-bottom:14px; }'
        '.ig-idx-row + .ig-idx-row { border-top:1px solid rgba(255,255,255,0.05); padding-top:12px; }'
        '.ig-idx-info { flex:1; }'
        '.ig-band-name { font-size:22px; font-weight:800; line-height:1.1; margin-bottom:5px; }'
        '.ig-band-note { font-size:11px; color:#94a3b8; line-height:1.45; }'
        '.ig-idx-subval { font-size:13px; color:#94a3b8; margin-top:4px; }'
        '.ig-egsi-title { font-size:12px; font-weight:700; color:#e2e8f0; margin-bottom:5px; }'
        '.ig-egsi-val { font-size:17px; font-weight:800; margin-bottom:5px; }'
        '.ig-egsi-note { font-size:10px; color:#94a3b8; line-height:1.4; padding-left:8px;'
        '  border-left:2px solid rgba(255,255,255,0.08); margin-bottom:4px; }'
        '.ig-storage-sep { margin:10px 0 8px; border:none; border-top:1px solid rgba(255,255,255,0.07); }'
        '.ig-storage-title { font-size:11px; font-weight:700; color:#d4a017; margin-bottom:4px; }'
        '.ig-storage-val { font-size:20px; font-weight:800; margin-bottom:4px; }'
        '.ig-storage-note { font-size:10px; color:#94a3b8; line-height:1.4;'
        '  padding-left:8px; border-left:2px solid rgba(212,160,23,0.3); }'
        '.ig-clipboard { grid-area:clipboard; position:relative;'
        '  border-left:1px solid rgba(255,255,255,0.06); display:flex; flex-direction:column; }'
        '.ig-clipboard-bg { position:absolute; top:0; left:0; width:100%; height:100%;'
        '  object-fit:cover; object-position:center top; opacity:0.55; pointer-events:none; }'
        '.ig-clipboard-inner { position:relative; z-index:1; display:flex; flex-direction:column;'
        '  height:100%; background:rgba(14,9,2,0.55); }'
        '.ig-clip-top { display:flex; align-items:center; justify-content:center;'
        '  padding:14px 10px 12px; background:rgba(0,0,0,0.45);'
        '  border-bottom:2px solid rgba(100,70,20,0.6); }'
        '.ig-clip-metal { width:68px; height:26px;'
        '  background:linear-gradient(135deg,#777 0%,#d0d0d0 35%,#bbb 55%,#888 80%,#666 100%);'
        '  border-radius:4px 4px 10px 10px; position:relative;'
        '  box-shadow:0 2px 8px rgba(0,0,0,0.7); }'
        '.ig-clip-metal::before { content:""; position:absolute; top:-11px; left:50%;'
        '  transform:translateX(-50%); width:36px; height:13px;'
        '  background:linear-gradient(135deg,#666,#b0b0b0,#888); border-radius:3px 3px 0 0;'
        '  box-shadow:0 -2px 4px rgba(0,0,0,0.5); }'
        '.ig-clip-header { padding:10px 14px 8px; font-size:11px; font-weight:800;'
        '  letter-spacing:1.8px; text-transform:uppercase; color:#d4a017;'
        '  border-bottom:1px solid rgba(255,255,255,0.07); background:rgba(0,0,0,0.35); }'
        '.ig-wl-item { display:flex; gap:9px; align-items:flex-start;'
        '  padding:11px 14px; border-bottom:1px solid rgba(255,255,255,0.04); }'
        '.ig-wl-item:last-child { border-bottom:none; }'
        '.ig-wl-check { width:17px; height:17px; border-radius:3px;'
        '  background:rgba(212,160,23,0.15); border:1px solid rgba(212,160,23,0.45);'
        '  color:#d4a017; font-size:10px; font-weight:800;'
        '  display:flex; align-items:center; justify-content:center;'
        '  flex-shrink:0; margin-top:1px; }'
        '.ig-wl-title { font-size:12px; font-weight:700; color:#e2e8f0; margin-bottom:3px; }'
        '.ig-wl-desc { font-size:10px; color:#94a3b8; line-height:1.35; }'
        '.ig-footer { grid-area:footer; padding:16px 22px; text-align:center;'
        '  background:#0f1522; border-top:1px solid rgba(255,255,255,0.06);'
        '  font-size:15px; color:#cbd5e1; font-style:italic; line-height:1.6; }'
        '.ig-footer strong { color:#ffffff; font-style:normal; }'
        '.ig-scroll { overflow-x:auto; }'
        '</style>'
    )

    HTML = f"""
<div class="ig-outer">
  <div class="ig-topbar">
    <span class="ig-topbar-title">&#128248;&nbsp; Current Energy Risk Environment &mdash; {today_str}</span>
    <button class="ig-dl-btn" id="igDlBtn" onclick="downloadInfographic('eriq-infographic','igDlBtn')">&#11015; Download PNG</button>
  </div>
  <div class="ig-scroll">
  <div id="eriq-infographic" class="ig-root">
    <div class="ig-grid">

      <!-- ── PRICE CARDS ── -->
      <div class="ig-prices">
        <div class="ig-price-card ig-brent-bg">
          <img class="ig-pc-img" src="/static/ig-brent-oilrig.png" alt="Oil rig" crossorigin="anonymous">
          <div class="ig-pc-overlay"></div>
          <div class="ig-pc-text">
            <div class="ig-pc-label">Brent Crude Oil</div>
            <div class="ig-pc-value"><sup>$</sup>{brent_price:.2f}</div>
            <div class="ig-pc-change" style="color:{b_color}">{b_arrow} {b_chg_str}</div>
          </div>
        </div>
        <div class="ig-price-card ig-ttf-bg">
          <img class="ig-pc-img" src="/static/ig-ttf-lngship.png" alt="LNG ship" crossorigin="anonymous">
          <div class="ig-pc-overlay"></div>
          <div class="ig-pc-text">
            <div class="ig-pc-label">TTF Natural Gas</div>
            <div class="ig-pc-value"><sup>&euro;</sup>{ttf_price:.2f}<span class="ig-pc-unit">/MWh</span></div>
            <div class="ig-pc-change" style="color:{t_color}">{t_arrow} {t_chg_str}</div>
          </div>
        </div>
      </div>

      <!-- ── INDICES PANEL ── -->
      <div class="ig-indices">
        <div class="ig-heading">EnergyRiskIQ&#8217;s Indices:</div>
        <div class="ig-indices-body">

          <!-- LEFT: GERI + EERI gauges -->
          <div class="ig-left-col">

            <!-- GERI -->
            <div class="ig-idx-label">GERI (Global Energy Risk Index): {geri_val}/100</div>
            <div class="ig-idx-row">
              <div>{geri_ig}
                <div style="text-align:center;font-size:10px;color:#6b7280;margin-top:2px">GERI: {geri_val}</div>
              </div>
              <div class="ig-idx-info">
                <div class="ig-band-name" style="color:{gc}">{geri_band}</div>
                <div class="ig-band-note">&#8211; Sharp increase driven by Middle East conflict escalation and infrastructure attacks</div>
                <div class="ig-idx-subval" style="color:{gc}">&#9660; {g_delta} from prev day</div>
              </div>
            </div>

            <!-- EERI -->
            <div class="ig-idx-label">EERI (European Energy Risk Index):</div>
            <div class="ig-idx-row">
              <div>{eeri_ig}
                <div style="text-align:center;font-size:10px;color:#6b7280;margin-top:2px">EERI: {eeri_val}</div>
              </div>
              <div class="ig-idx-info">
                <div class="ig-band-name" style="color:{ec}">{eeri_val} ({eeri_change_note})</div>
                <div class="ig-band-note">&#8211; Stability reflects ongoing but contained European risks, notably Ukraine power grid attacks.</div>
              </div>
            </div>

          </div>

          <!-- RIGHT: EGSI-M + EU Storage -->
          <div class="ig-right-col">
            <div class="ig-egsi-title">EGSI-M (Energy Geopolitical Stress Index): <span style="color:{mgc}">{egsi_val}</span></div>
            <div class="ig-egsi-val" style="color:{mgc}">{egsi_band}</div>
            <div class="ig-egsi-note">&#8211; High stress sustained due to repeated strikes on Gulf oil hubs and port disruptions.</div>
            <div class="ig-egsi-note">&#8211; EU gas storage sits at {storage_pct:.2f}% full.</div>
            <hr class="ig-storage-sep">
            <div class="ig-storage-title">EU Gas Storage Levels: <span style="color:{mgc}">{storage_pct:.2f}%</span> full</div>
            <div class="ig-storage-note">&#8226; Weekly changes to assess supply cushion ahead of summer.</div>
          </div>

        </div>
      </div>

      <!-- ── CLIPBOARD WATCHLIST ── -->
      <div class="ig-clipboard">
        <img class="ig-clipboard-bg" src="/static/ig-clipboard-bg.png" alt="" crossorigin="anonymous">
        <div class="ig-clipboard-inner">
          <div class="ig-clip-top"><div class="ig-clip-metal"></div></div>
          <div class="ig-clip-header">Custom Watchlist:</div>
          {wl_items}
        </div>
      </div>

      <!-- ── FOOTER TEXT ── -->
      <div class="ig-footer">{footer_text}</div>

    </div>
  </div>
  </div><!-- /ig-scroll -->
</div>
"""
    return CSS + HTML


def _gauge_svg(value: int, band: str) -> str:
    """Build SVG gauge for a 0-100 index value."""
    color = BAND_COLORS.get(band, '#f97316')
    # Arc band boundary points (r=45, center=50,50)
    # V=0:(5,50) V=20:(13.59,23.55) V=40:(36.09,7.2) V=60:(63.91,7.2) V=80:(86.41,23.55) V=100:(95,50)
    def arc_pt(v, r=45):
        theta = math.pi - v * math.pi / 100
        return round(50 + r * math.cos(theta), 2), round(50 - r * math.sin(theta), 2)

    def needle_pt(v, r=34):
        theta = math.pi - v * math.pi / 100
        return round(50 + r * math.cos(theta), 2), round(50 - r * math.sin(theta), 2)

    p0  = arc_pt(0)
    p20 = arc_pt(20)
    p40 = arc_pt(40)
    p60 = arc_pt(60)
    p80 = arc_pt(80)
    p100 = arc_pt(100)
    npt = needle_pt(value)

    svg = f"""<svg viewBox="0 0 100 58" xmlns="http://www.w3.org/2000/svg" class="gauge-svg">
  <path d="M{p0[0]},{p0[1]} A45,45 0 0,1 {p20[0]},{p20[1]}" fill="none" stroke="#22c55e" stroke-width="7" stroke-linecap="butt"/>
  <path d="M{p20[0]},{p20[1]} A45,45 0 0,1 {p40[0]},{p40[1]}" fill="none" stroke="#eab308" stroke-width="7" stroke-linecap="butt"/>
  <path d="M{p40[0]},{p40[1]} A45,45 0 0,1 {p60[0]},{p60[1]}" fill="none" stroke="#f97316" stroke-width="7" stroke-linecap="butt"/>
  <path d="M{p60[0]},{p60[1]} A45,45 0 0,1 {p80[0]},{p80[1]}" fill="none" stroke="#ef4444" stroke-width="7" stroke-linecap="butt"/>
  <path d="M{p80[0]},{p80[1]} A45,45 0 0,1 {p100[0]},{p100[1]}" fill="none" stroke="#dc2626" stroke-width="7" stroke-linecap="butt"/>
  <line x1="50" y1="50" x2="{npt[0]}" y2="{npt[1]}" stroke="white" stroke-width="2.5" stroke-linecap="round"/>
  <circle cx="50" cy="50" r="4" fill="{color}" stroke="white" stroke-width="1.5"/>
  <text x="50" y="56" text-anchor="middle" fill="white" font-size="9" font-weight="700">{value}</text>
  <text x="3" y="55" fill="#94a3b8" font-size="6">0</text>
  <text x="89" y="55" fill="#94a3b8" font-size="6">100</text>
</svg>"""
    return svg


def _build_short_interpretation(geri_val, eeri_val, egsi_val, storage_pct, geri_band, eeri_band, geri_components):
    """Build the interpretation block text from production data."""
    top_driver = ""
    try:
        if geri_components:
            comp = json.loads(geri_components) if isinstance(geri_components, str) else geri_components
            drivers = comp.get("top_drivers", [])
            if drivers:
                top_driver = drivers[0].get("headline", "")
    except Exception:
        pass

    geri_desc = {
        'LOW': 'subdued with limited supply disruption risk',
        'MODERATE': 'moderate with some supply chain pressure',
        'ELEVATED': 'elevated with significant supply chain stress',
        'SEVERE': 'severe with acute disruption risk across key corridors',
        'CRITICAL': 'critical — extreme disruption risk and market stress',
    }.get(geri_band, 'elevated')

    eeri_desc = {
        'LOW': 'calm with contained European risk',
        'MODERATE': 'moderate with manageable European exposure',
        'ELEVATED': 'structurally high, with storage below seasonal norms',
        'SEVERE': 'severe — European supply chains under acute stress',
        'CRITICAL': 'critical — European energy security at serious risk',
    }.get(eeri_band, 'elevated')

    storage_note = ""
    if storage_pct:
        sp = _safe_float(storage_pct)
        storage_note = f" EU gas storage sits at {sp:.2f}% full"
        if sp < 35:
            storage_note += " — well below seasonal average"
        elif sp < 50:
            storage_note += " — below seasonal average"
        storage_note += "."

    driver_note = f' Key driver: "{top_driver[:80]}..."' if top_driver else ""

    return (
        f"Global energy risk remains {geri_desc}, driven by Middle East escalation and persistent supply chain disruptions."
        f"{driver_note} European risk {eeri_desc}.{storage_note}"
    )


@router.get("/data/energy-risk-snapshot", response_class=HTMLResponse)
async def energy_risk_snapshot(request: Request):
    try:
        # --- Fetch all production data ---
        geri_row = execute_production_one(
            "SELECT date, value, band, components FROM intel_indices_daily WHERE index_id='global:geo_energy_risk' ORDER BY date DESC LIMIT 1"
        )
        geri_prev = execute_production_one(
            "SELECT value FROM intel_indices_daily WHERE index_id='global:geo_energy_risk' ORDER BY date DESC LIMIT 1 OFFSET 1"
        )
        eeri_row = execute_production_one(
            "SELECT date, value, band FROM reri_indices_daily WHERE index_id='europe:eeri' ORDER BY date DESC LIMIT 1"
        )
        eeri_prev = execute_production_one(
            "SELECT value FROM reri_indices_daily WHERE index_id='europe:eeri' ORDER BY date DESC LIMIT 1 OFFSET 1"
        )
        egsi_row = execute_production_one(
            "SELECT index_date, index_value, band FROM egsi_m_daily ORDER BY index_date DESC LIMIT 1"
        )
        egsi_prev = execute_production_one(
            "SELECT index_value FROM egsi_m_daily ORDER BY index_date DESC LIMIT 1 OFFSET 1"
        )
        brent_row = execute_production_one(
            "SELECT date, brent_price, brent_change_pct FROM oil_price_snapshots ORDER BY date DESC LIMIT 1"
        )
        brent_intra = execute_production_one(
            "SELECT date, hour, price, change_24h, change_pct FROM intraday_brent ORDER BY captured_at DESC LIMIT 1"
        )
        ttf_row = execute_production_one(
            "SELECT date, ttf_price FROM ttf_gas_snapshots ORDER BY date DESC LIMIT 1"
        )
        ttf_prev = execute_production_one(
            "SELECT ttf_price FROM ttf_gas_snapshots ORDER BY date DESC LIMIT 1 OFFSET 1"
        )
        vix_row = execute_production_one(
            "SELECT date, vix_close, vix_open, vix_high, vix_low FROM vix_snapshots ORDER BY date DESC LIMIT 1"
        )
        vix_prev = execute_production_one(
            "SELECT vix_close FROM vix_snapshots ORDER BY date DESC LIMIT 1 OFFSET 1"
        )
        lng_row = execute_production_one(
            "SELECT date, jkm_price, jkm_change_pct FROM lng_price_snapshots ORDER BY date DESC LIMIT 1"
        )
        storage_row = execute_production_one(
            "SELECT date, eu_storage_percent, risk_band FROM gas_storage_snapshots ORDER BY date DESC LIMIT 1"
        )

        # --- Extract values ---
        geri_val  = int(geri_row['value'])  if geri_row  else 0
        geri_band = str(geri_row['band'])   if geri_row  else 'ELEVATED'
        geri_date = str(geri_row['date'])   if geri_row  else ''
        geri_comp = geri_row.get('components') if geri_row else None
        geri_delta = geri_val - int(geri_prev['value']) if geri_prev else 0

        eeri_val  = int(eeri_row['value'])  if eeri_row  else 0
        eeri_band = str(eeri_row['band'])   if eeri_row  else 'ELEVATED'
        eeri_date = str(eeri_row['date'])   if eeri_row  else ''
        eeri_delta = eeri_val - int(eeri_prev['value']) if eeri_prev else 0

        egsi_val  = round(_safe_float(egsi_row['index_value']) if egsi_row else 0, 1)
        egsi_band = str(egsi_row['band'])   if egsi_row  else 'ELEVATED'
        egsi_date = str(egsi_row['index_date']) if egsi_row else ''
        egsi_delta = round(_safe_float(egsi_row['index_value']) - _safe_float(egsi_prev['index_value']), 2) if (egsi_row and egsi_prev) else 0.0

        # Brent: prefer intraday (most current)
        if brent_intra:
            brent_price = _safe_float(brent_intra['price'])
            brent_chg   = _safe_float(brent_intra['change_24h'])
            brent_chg_pct = _safe_float(brent_intra['change_pct'])
            brent_label = f"Intraday {brent_intra['hour']}:00 UTC"
        elif brent_row:
            brent_price = _safe_float(brent_row['brent_price'])
            brent_chg_pct = _safe_float(brent_row['brent_change_pct'])
            brent_chg = 0.0
            brent_label = "Daily Close"
        else:
            brent_price, brent_chg, brent_chg_pct, brent_label = 0.0, 0.0, 0.0, ''

        ttf_price = _safe_float(ttf_row['ttf_price']) if ttf_row else 0.0
        ttf_chg   = round(ttf_price - _safe_float(ttf_prev['ttf_price']), 2) if ttf_prev else 0.0

        vix_close = _safe_float(vix_row['vix_close']) if vix_row else 0.0
        vix_chg   = round(vix_close - _safe_float(vix_prev['vix_close']), 2) if vix_prev else 0.0

        lng_price = _safe_float(lng_row['jkm_price']) if lng_row else 0.0
        lng_chg_pct = _safe_float(lng_row['jkm_change_pct']) if lng_row else 0.0

        storage_pct  = _safe_float(storage_row['eu_storage_percent']) if storage_row else 0.0
        storage_band = str(storage_row['risk_band']) if storage_row else 'ELEVATED'

        # --- Formatted strings ---
        today_str = datetime.now(timezone.utc).strftime('%B %-d, %Y')
        data_date = geri_date  # e.g. 2026-03-16

        def sign(v):
            return '+' if v >= 0 else ''

        geri_delta_str  = f"{sign(geri_delta)}{geri_delta}"
        eeri_delta_str  = f"{sign(eeri_delta)}{eeri_delta}"
        egsi_delta_str  = f"{sign(egsi_delta)}{egsi_delta:.2f}"
        brent_chg_str   = f"{sign(brent_chg)}{brent_chg:.2f} | {sign(brent_chg_pct)}{brent_chg_pct:.2f}% d/d"
        ttf_chg_str     = f"{sign(ttf_chg)}{ttf_chg:.2f} d/d"
        vix_chg_str     = f"{sign(vix_chg)}{vix_chg:.2f} d/d"
        lng_chg_str     = f"{sign(lng_chg_pct)}{lng_chg_pct:.2f}% d/d"

        brent_color  = '#22c55e' if brent_chg >= 0 else '#ef4444'
        ttf_color    = '#22c55e' if ttf_chg >= 0   else '#ef4444'
        vix_color    = '#22c55e' if vix_chg <= 0   else '#ef4444'  # lower VIX = calmer
        lng_color    = '#22c55e' if lng_chg_pct >= 0 else '#ef4444'

        brent_arrow  = '▲' if brent_chg >= 0 else '▼'
        ttf_arrow    = '▲' if ttf_chg >= 0   else '▼'
        vix_arrow    = '▲' if vix_chg >= 0   else '▼'
        lng_arrow    = '▲' if lng_chg_pct >= 0 else '▼'

        # --- Gauges ---
        geri_gauge  = _gauge_svg(geri_val, geri_band)
        eeri_gauge  = _gauge_svg(eeri_val, eeri_band)
        egsi_gauge  = _gauge_svg(int(round(egsi_val)), egsi_band)

        # --- Band colors ---
        gc  = BAND_COLORS.get(geri_band,  '#f97316')
        ec  = BAND_COLORS.get(eeri_band,  '#f97316')
        mgc = BAND_COLORS.get(egsi_band,  '#f97316')
        gbg = BAND_BG.get(geri_band,  'rgba(249,115,22,0.10)')
        ebg = BAND_BG.get(eeri_band,  'rgba(249,115,22,0.10)')
        mgbg = BAND_BG.get(egsi_band, 'rgba(249,115,22,0.10)')

        # --- Interpretation ---
        interpretation = _build_short_interpretation(
            geri_val, eeri_val, egsi_val, storage_pct, geri_band, eeri_band, geri_comp
        )

        # --- Watchlist HTML ---
        wl_items = []
        for w in WATCHLIST:
            wl_items.append(f"""
              <a href="/research/watchlist/{w['slug']}" class="wl-item">
                <div class="wl-check">&#10003;</div>
                <div class="wl-body">
                  <div class="wl-title">{w['title']}</div>
                  <div class="wl-desc">{w['desc']}</div>
                </div>
              </a>""")
        watchlist_html = "\n".join(wl_items)

        # --- Index delta badge HTML ---
        def delta_badge(delta_str, color):
            return f'<span class="delta" style="color:{color}">{delta_str}</span>'

        geri_delta_badge  = delta_badge(geri_delta_str,  gc if geri_delta  != 0 else '#94a3b8')
        eeri_delta_badge  = delta_badge(eeri_delta_str,  ec if eeri_delta  != 0 else '#94a3b8')
        egsi_delta_badge  = delta_badge(egsi_delta_str,  mgc if egsi_delta != 0 else '#94a3b8')

        storage_color = BAND_COLORS.get(storage_band, '#f97316')

        # --- Infographic section ---
        infographic_section = _build_infographic_html(
            today_str=today_str,
            geri_val=geri_val, geri_band=geri_band, geri_date=geri_date, geri_delta=geri_delta,
            eeri_val=eeri_val, eeri_band=eeri_band, eeri_delta=eeri_delta,
            egsi_val=egsi_val, egsi_band=egsi_band,
            brent_price=brent_price, brent_chg=brent_chg, brent_chg_pct=brent_chg_pct,
            ttf_price=ttf_price, ttf_chg=ttf_chg,
            storage_pct=storage_pct,
        )

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Global Energy Risk Snapshot — {today_str} | EnergyRiskIQ</title>
  <meta name="description" content="Live global energy risk snapshot for {today_str}. Current GERI, EERI and EGSI-M index values with Brent crude, TTF gas, VIX and LNG market prices. Powered by EnergyRiskIQ.">
  <meta name="robots" content="index, follow">
  <link rel="canonical" href="https://energyriskiq.com/data/energy-risk-snapshot">
  <meta property="og:title" content="Global Energy Risk Snapshot — {today_str}">
  <meta property="og:description" content="Live energy risk indices (GERI {geri_val}/100 {geri_band}, EERI {eeri_val}/100 {eeri_band}) plus Brent ${brent_price:.2f}, TTF €{ttf_price:.2f}/MWh, VIX {vix_close:.2f}.">
  <meta property="og:type" content="article">
  <meta property="og:url" content="https://energyriskiq.com/data/energy-risk-snapshot">
  <meta property="og:site_name" content="EnergyRiskIQ">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="Global Energy Risk Snapshot — {today_str}">
  <meta name="twitter:description" content="GERI {geri_val} ({geri_band}) | EERI {eeri_val} ({eeri_band}) | Brent ${brent_price:.2f} | TTF €{ttf_price:.2f}">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=DM+Serif+Display&display=swap" rel="stylesheet">
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    :root {{
      --bg: #0b0f1a;
      --card: #111827;
      --card2: #151c2c;
      --border: rgba(255,255,255,0.07);
      --text: #e2e8f0;
      --muted: #94a3b8;
      --gold: #d4a017;
      --gold2: #fbbf24;
    }}
    body {{
      background: var(--bg);
      color: var(--text);
      font-family: 'Inter', sans-serif;
      min-height: 100vh;
      line-height: 1.6;
    }}

    /* ── HEADER ── */
    .site-header {{
      background: rgba(11,15,26,0.96);
      border-bottom: 1px solid var(--border);
      padding: 14px 24px;
      display: flex; align-items: center; justify-content: space-between;
    }}
    .site-logo {{ font-size: 15px; font-weight: 700; color: var(--gold2); letter-spacing: 0.5px; text-decoration: none; }}
    .site-logo span {{ color: var(--muted); font-weight: 400; }}
    .header-badge {{
      font-size: 11px; font-weight: 600; padding: 4px 10px;
      border-radius: 20px; border: 1px solid rgba(251,191,36,0.4);
      color: var(--gold2); background: rgba(251,191,36,0.08);
      letter-spacing: 0.5px;
    }}

    /* ── HERO ── */
    .hero {{
      padding: 52px 24px 40px;
      text-align: center;
      border-bottom: 1px solid var(--border);
      background: linear-gradient(180deg, rgba(212,160,23,0.04) 0%, transparent 100%);
    }}
    .hero-date {{
      font-size: 13px; font-weight: 600; letter-spacing: 1.5px;
      color: var(--gold); text-transform: uppercase; margin-bottom: 14px;
    }}
    .hero h1 {{
      font-family: 'DM Serif Display', serif;
      font-size: clamp(28px, 5vw, 48px);
      font-weight: 400;
      color: #ffffff;
      line-height: 1.2;
      max-width: 700px;
      margin: 0 auto 16px;
    }}
    .hero-sub {{
      font-size: 15px; color: var(--muted);
      max-width: 560px; margin: 0 auto;
    }}

    /* ── LAYOUT ── */
    .page-body {{
      max-width: 1160px;
      margin: 0 auto;
      padding: 40px 20px 60px;
    }}

    /* ── SECTION TITLES ── */
    .section-label {{
      font-size: 11px; font-weight: 700; letter-spacing: 2px;
      color: var(--gold); text-transform: uppercase;
      margin-bottom: 20px; display: flex; align-items: center; gap: 10px;
    }}
    .section-label::after {{
      content: '';
      flex: 1; height: 1px;
      background: linear-gradient(90deg, rgba(212,160,23,0.4) 0%, transparent 100%);
    }}

    /* ── PRICE STRIP ── */
    .price-grid {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 16px;
      margin-bottom: 44px;
    }}
    @media (max-width: 768px) {{ .price-grid {{ grid-template-columns: repeat(2, 1fr); }} }}
    @media (max-width: 420px) {{ .price-grid {{ grid-template-columns: 1fr; }} }}

    .price-card {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 22px 20px;
      position: relative;
      overflow: hidden;
      transition: border-color 0.2s, transform 0.2s;
    }}
    .price-card:hover {{ border-color: rgba(212,160,23,0.35); transform: translateY(-2px); }}
    .price-card::before {{
      content: '';
      position: absolute; inset: 0;
      background: linear-gradient(135deg, rgba(255,255,255,0.02) 0%, transparent 60%);
      pointer-events: none;
    }}
    .price-commodity {{
      font-size: 11px; font-weight: 700; letter-spacing: 1.5px;
      text-transform: uppercase; color: var(--muted); margin-bottom: 10px;
    }}
    .price-value {{
      font-size: 30px; font-weight: 800;
      color: #ffffff; line-height: 1; margin-bottom: 8px;
      font-variant-numeric: tabular-nums;
    }}
    .price-value sup {{ font-size: 16px; font-weight: 600; vertical-align: top; margin-top: 4px; }}
    .price-change {{
      font-size: 13px; font-weight: 600;
    }}
    .price-source {{
      font-size: 10px; color: var(--muted);
      margin-top: 8px; opacity: 0.7;
    }}

    /* ── MAIN GRID ── */
    .main-grid {{
      display: grid;
      grid-template-columns: 1fr 340px;
      gap: 28px;
      margin-bottom: 36px;
    }}
    @media (max-width: 900px) {{ .main-grid {{ grid-template-columns: 1fr; }} }}

    /* ── INDEX CARDS ── */
    .indices-col {{ display: flex; flex-direction: column; gap: 16px; }}
    .index-card {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 22px 24px;
      display: flex;
      gap: 20px;
      align-items: flex-start;
      transition: border-color 0.2s;
    }}
    .index-card:hover {{ border-color: rgba(212,160,23,0.3); }}
    .gauge-wrap {{
      flex-shrink: 0;
      width: 100px;
    }}
    .gauge-svg {{ width: 100%; height: auto; display: block; }}
    .index-detail {{ flex: 1; }}
    .index-name {{
      font-size: 12px; font-weight: 700; letter-spacing: 1.2px;
      text-transform: uppercase; color: var(--muted); margin-bottom: 4px;
    }}
    .index-fullname {{
      font-size: 13px; color: #64748b; margin-bottom: 8px; font-weight: 400;
    }}
    .index-value-row {{
      display: flex; align-items: baseline; gap: 10px; margin-bottom: 6px;
    }}
    .index-number {{
      font-size: 40px; font-weight: 800; line-height: 1;
      font-variant-numeric: tabular-nums;
    }}
    .index-denom {{ font-size: 18px; color: var(--muted); font-weight: 400; }}
    .band-pill {{
      display: inline-block;
      font-size: 11px; font-weight: 700; letter-spacing: 1px;
      text-transform: uppercase; padding: 3px 10px; border-radius: 20px;
      border: 1px solid currentColor; margin-bottom: 8px;
    }}
    .delta {{ font-size: 13px; font-weight: 600; }}
    .index-note {{
      font-size: 12px; color: var(--muted); line-height: 1.5;
      border-left: 2px solid rgba(255,255,255,0.08);
      padding-left: 10px; margin-top: 6px;
    }}
    .index-date {{ font-size: 11px; color: #475569; margin-top: 6px; }}

    /* ── WATCHLIST ── */
    .watchlist-card {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 14px;
      overflow: hidden;
    }}
    .wl-header {{
      padding: 18px 20px 14px;
      border-bottom: 1px solid var(--border);
      background: linear-gradient(135deg, rgba(212,160,23,0.06) 0%, transparent 100%);
    }}
    .wl-header-title {{
      font-size: 13px; font-weight: 700; letter-spacing: 1px;
      text-transform: uppercase; color: var(--gold2);
    }}
    .wl-header-sub {{
      font-size: 11px; color: var(--muted); margin-top: 3px;
    }}
    .wl-item {{
      display: flex; gap: 12px; align-items: flex-start;
      padding: 14px 20px;
      border-bottom: 1px solid rgba(255,255,255,0.04);
      text-decoration: none;
      color: inherit;
      transition: background 0.15s;
    }}
    .wl-item:last-child {{ border-bottom: none; }}
    .wl-item:hover {{ background: rgba(255,255,255,0.03); }}
    .wl-check {{
      width: 20px; height: 20px; border-radius: 4px;
      background: rgba(212,160,23,0.15);
      border: 1px solid rgba(212,160,23,0.4);
      color: var(--gold2);
      font-size: 12px; font-weight: 700;
      display: flex; align-items: center; justify-content: center;
      flex-shrink: 0; margin-top: 1px;
    }}
    .wl-body {{ flex: 1; }}
    .wl-title {{ font-size: 13px; font-weight: 600; color: #e2e8f0; margin-bottom: 3px; }}
    .wl-desc {{ font-size: 11px; color: var(--muted); line-height: 1.4; }}

    /* ── INTERPRETATION BLOCK ── */
    .interp-block {{
      background: linear-gradient(135deg, #111827 0%, #0f172a 100%);
      border: 1px solid rgba(212,160,23,0.2);
      border-radius: 14px;
      padding: 32px 36px;
      margin-bottom: 28px;
      position: relative;
      overflow: hidden;
    }}
    .interp-block::before {{
      content: '';
      position: absolute;
      top: 0; left: 0; right: 0; height: 3px;
      background: linear-gradient(90deg, var(--gold), transparent);
    }}
    .interp-label {{
      font-size: 10px; font-weight: 700; letter-spacing: 2px;
      text-transform: uppercase; color: var(--gold);
      margin-bottom: 14px; display: flex; align-items: center; gap: 8px;
    }}
    .interp-label::before {{ content: '\\25B6'; font-size: 8px; }}
    .interp-text {{
      font-size: 17px;
      color: #cbd5e1;
      line-height: 1.75;
      font-weight: 400;
    }}
    .interp-text strong {{ color: #ffffff; font-weight: 600; }}

    /* ── STORAGE CALLOUT ── */
    .storage-row {{
      display: flex; align-items: center; gap: 16px;
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 18px 24px;
      margin-bottom: 28px;
    }}
    .storage-icon {{ font-size: 28px; flex-shrink: 0; }}
    .storage-label {{ font-size: 12px; color: var(--muted); font-weight: 500; }}
    .storage-value {{ font-size: 24px; font-weight: 800; }}
    .storage-note {{ font-size: 12px; color: var(--muted); margin-top: 2px; }}
    .storage-bar-wrap {{ flex: 1; }}
    .storage-bar {{
      height: 8px; background: rgba(255,255,255,0.08);
      border-radius: 4px; overflow: hidden;
    }}
    .storage-bar-fill {{
      height: 100%; border-radius: 4px;
      transition: width 0.5s;
    }}

    /* ── CITATION ── */
    .citation-block {{
      background: rgba(255,255,255,0.02);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 16px 20px;
      font-size: 12px;
      color: var(--muted);
      line-height: 1.6;
      margin-bottom: 36px;
    }}
    .citation-block a {{ color: var(--gold2); text-decoration: none; }}
    .citation-block a:hover {{ text-decoration: underline; }}

    /* ── CTA ── */
    .cta-section {{
      text-align: center;
      padding: 52px 24px;
      background: linear-gradient(135deg, rgba(212,160,23,0.06) 0%, rgba(11,15,26,0) 60%);
      border-top: 1px solid var(--border);
      border-radius: 16px;
    }}
    .cta-label {{
      font-size: 11px; font-weight: 700; letter-spacing: 2px;
      text-transform: uppercase; color: var(--gold); margin-bottom: 16px;
    }}
    .cta-headline {{
      font-family: 'DM Serif Display', serif;
      font-size: clamp(24px, 4vw, 36px);
      font-weight: 400; color: #ffffff;
      margin-bottom: 12px; line-height: 1.25;
    }}
    .cta-sub {{
      font-size: 15px; color: var(--muted);
      max-width: 480px; margin: 0 auto 28px;
    }}
    .cta-btn {{
      display: inline-block;
      background: linear-gradient(135deg, #d4a017, #fbbf24);
      color: #0b0f1a;
      font-size: 15px; font-weight: 700;
      padding: 14px 36px; border-radius: 8px;
      text-decoration: none; letter-spacing: 0.3px;
      transition: transform 0.2s, box-shadow 0.2s;
      box-shadow: 0 4px 20px rgba(212,160,23,0.3);
    }}
    .cta-btn:hover {{ transform: translateY(-2px); box-shadow: 0 8px 28px rgba(212,160,23,0.45); }}
    .cta-secondary {{
      display: block; margin-top: 14px;
      font-size: 13px; color: var(--muted); text-decoration: none;
    }}
    .cta-secondary:hover {{ color: var(--text); }}

    /* ── FOOTER ── */
    .page-footer {{
      border-top: 1px solid var(--border);
      padding: 24px;
      text-align: center;
      font-size: 12px; color: #475569;
    }}
    .page-footer a {{ color: var(--muted); text-decoration: none; margin: 0 8px; }}
    .page-footer a:hover {{ color: var(--text); }}
  </style>

  <script type="application/ld+json">
  {{
    "@context": "https://schema.org",
    "@type": "Dataset",
    "name": "Global Energy Risk Snapshot — {today_str}",
    "description": "Live energy risk indices and commodity prices from EnergyRiskIQ. GERI: {geri_val}/100 ({geri_band}), EERI: {eeri_val}/100 ({eeri_band}), EGSI-M: {egsi_val} ({egsi_band}).",
    "url": "https://energyriskiq.com/data/energy-risk-snapshot",
    "publisher": {{ "@type": "Organization", "name": "EnergyRiskIQ", "url": "https://energyriskiq.com" }},
    "dateModified": "{data_date}",
    "keywords": ["energy risk", "GERI", "EERI", "EGSI", "Brent crude", "TTF gas", "VIX", "LNG", "geopolitical risk"],
    "license": "https://energyriskiq.com/terms"
  }}
  </script>
  <script src="https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js"></script>
</head>
<body>

<header class="site-header">
  <a href="/" class="site-logo">EnergyRisk<span>IQ</span></a>
  <span class="header-badge">LIVE DATA</span>
</header>

<div class="hero">
  <div class="hero-date">&#128197; {today_str}</div>
  <h1>Global Energy Risk Snapshot</h1>
  <p class="hero-sub">Live risk indices, commodity prices and geopolitical watchlist — updated daily from the EnergyRiskIQ intelligence pipeline.</p>
</div>

<div class="page-body">

  <!-- ── KEY MARKET PRICES ── -->
  <div class="section-label">Key Market Prices</div>
  <div class="price-grid">

    <!-- Brent -->
    <div class="price-card">
      <div class="price-commodity">Brent Crude Oil</div>
      <div class="price-value"><sup>$</sup>{brent_price:.2f}</div>
      <div class="price-change" style="color:{brent_color}">{brent_arrow} {brent_chg_str}</div>
      <div class="price-source">{brent_label}</div>
    </div>

    <!-- TTF Gas -->
    <div class="price-card">
      <div class="price-commodity">TTF Natural Gas</div>
      <div class="price-value"><sup>&#8364;</sup>{ttf_price:.2f}<span style="font-size:14px;font-weight:500;color:var(--muted)">/MWh</span></div>
      <div class="price-change" style="color:{ttf_color}">{ttf_arrow} {ttf_chg_str}</div>
      <div class="price-source">Daily Close — Mar 16, 2026</div>
    </div>

    <!-- VIX -->
    <div class="price-card">
      <div class="price-commodity">VIX Volatility Index</div>
      <div class="price-value">{vix_close:.2f}</div>
      <div class="price-change" style="color:{vix_color}">{vix_arrow} {vix_chg_str}</div>
      <div class="price-source">CBOE — Daily Close</div>
    </div>

    <!-- LNG -->
    <div class="price-card">
      <div class="price-commodity">LNG JKM (Asia)</div>
      <div class="price-value"><sup>$</sup>{lng_price:.2f}<span style="font-size:14px;font-weight:500;color:var(--muted)">/MMBtu</span></div>
      <div class="price-change" style="color:{lng_color}">{lng_arrow} {lng_chg_str}</div>
      <div class="price-source">Platts JKM — Daily Close</div>
    </div>

  </div>

  <!-- ── INFOGRAPHIC ── -->
  <div class="section-label">Current Energy Risk Environment</div>
  {infographic_section}

  <!-- ── INDICES + WATCHLIST ── -->
  <div class="section-label">EnergyRiskIQ Indices</div>
  <div class="main-grid">

    <!-- INDICES COL -->
    <div class="indices-col">

      <!-- GERI -->
      <article class="index-card" style="border-left:3px solid {gc}; background:linear-gradient(135deg,{gbg} 0%,var(--card) 40%)">
        <div class="gauge-wrap">{geri_gauge}</div>
        <div class="index-detail">
          <div class="index-name">GERI</div>
          <div class="index-fullname">Global Energy Risk Index</div>
          <div class="index-value-row">
            <span class="index-number" style="color:{gc}">{geri_val}</span>
            <span class="index-denom">/100</span>
            {geri_delta_badge}
          </div>
          <span class="band-pill" style="color:{gc}; border-color:{gc}; background:rgba(0,0,0,0.2)">{geri_band}</span>
          <div class="index-note">Middle East escalation and infrastructure attacks driving sustained supply-chain pressure across key export corridors.</div>
          <div class="index-date">&#128338; Data as of {geri_date} &nbsp;&bull;&nbsp; <a href="/indices/global-energy-risk-index" style="color:var(--gold2);text-decoration:none;font-size:11px">Full Analysis &#8594;</a></div>
        </div>
      </article>

      <!-- EERI -->
      <article class="index-card" style="border-left:3px solid {ec}; background:linear-gradient(135deg,{ebg} 0%,var(--card) 40%)">
        <div class="gauge-wrap">{eeri_gauge}</div>
        <div class="index-detail">
          <div class="index-name">EERI</div>
          <div class="index-fullname">Europe Energy Risk Index</div>
          <div class="index-value-row">
            <span class="index-number" style="color:{ec}">{eeri_val}</span>
            <span class="index-denom">/100</span>
            {eeri_delta_badge}
          </div>
          <span class="band-pill" style="color:{ec}; border-color:{ec}; background:rgba(0,0,0,0.2)">{eeri_band}</span>
          <div class="index-note">Stability reflects ongoing but contained European risks — notably Ukraine power grid attacks and Black Sea shipping disruptions.</div>
          <div class="index-date">&#128338; Data as of {eeri_date} &nbsp;&bull;&nbsp; <a href="/indices/europe-energy-risk-index" style="color:var(--gold2);text-decoration:none;font-size:11px">Full Analysis &#8594;</a></div>
        </div>
      </article>

      <!-- EGSI-M -->
      <article class="index-card" style="border-left:3px solid {mgc}; background:linear-gradient(135deg,{mgbg} 0%,var(--card) 40%)">
        <div class="gauge-wrap">{egsi_gauge}</div>
        <div class="index-detail">
          <div class="index-name">EGSI-M</div>
          <div class="index-fullname">Europe Gas Stress Index — Market</div>
          <div class="index-value-row">
            <span class="index-number" style="color:{mgc}">{egsi_val}</span>
            <span class="index-denom">/100</span>
            {egsi_delta_badge}
          </div>
          <span class="band-pill" style="color:{mgc}; border-color:{mgc}; background:rgba(0,0,0,0.2)">{egsi_band}</span>
          <div class="index-note">High market-side gas stress sustained due to repeated strikes on Gulf oil hubs and port disruptions impacting LNG re-exports.</div>
          <div class="index-date">&#128338; Data as of {egsi_date} &nbsp;&bull;&nbsp; <a href="/indices/europe-gas-stress-index" style="color:var(--gold2);text-decoration:none;font-size:11px">Full Analysis &#8594;</a></div>
        </div>
      </article>

    </div>

    <!-- WATCHLIST COL -->
    <aside class="watchlist-card">
      <div class="wl-header">
        <div class="wl-header-title">&#128203; Custom Watchlist</div>
        <div class="wl-header-sub">6 active risk vectors being monitored</div>
      </div>
      {watchlist_html}
    </aside>

  </div>

  <!-- ── EU GAS STORAGE ── -->
  <div class="storage-row">
    <div class="storage-icon">&#9651;</div>
    <div>
      <div class="storage-label">EU Gas Storage</div>
      <div class="storage-value" style="color:{storage_color}">{storage_pct:.2f}% full</div>
      <div class="storage-note">Weekly changes assessed to track supply cushion ahead of summer. Risk band: <strong style="color:{storage_color}">{storage_band}</strong></div>
    </div>
    <div class="storage-bar-wrap">
      <div style="font-size:10px;color:var(--muted);margin-bottom:5px;text-align:right">{storage_pct:.1f}% / 100%</div>
      <div class="storage-bar">
        <div class="storage-bar-fill" style="width:{min(storage_pct, 100):.1f}%; background:{storage_color}"></div>
      </div>
      <div style="font-size:10px;color:var(--muted);margin-top:4px;text-align:right">Seasonal avg ~40%</div>
    </div>
  </div>

  <!-- ── INTERPRETATION BLOCK ── -->
  <div class="section-label">Risk Intelligence Interpretation</div>
  <div class="interp-block">
    <div class="interp-label">EnergyRiskIQ Daily Assessment</div>
    <p class="interp-text">{interpretation}</p>
    <div style="margin-top:16px;font-size:12px;color:#475569">
      Indices powered by EnergyRiskIQ's proprietary GERI, EERI and EGSI methodology. Data as of {data_date}.
    </div>
  </div>

  <!-- ── CITATION ── -->
  <div class="citation-block">
    <strong style="color:var(--text)">Data Sources &amp; Methodology:</strong> Index values (GERI, EERI, EGSI-M) are proprietary EnergyRiskIQ calculations updated daily from live alert pipelines. Commodity prices sourced from OilPrice API (Brent, WTI, US Natural Gas) and market data providers (TTF, LNG JKM, VIX, EUR/USD).
    Indices represent risk scoring on a 0–100 scale: LOW (0–20), MODERATE (21–40), ELEVATED (41–60), SEVERE (61–80), CRITICAL (81–100).
    Full methodology available at <a href="/indices/global-energy-risk-index#methodology">GERI Methodology</a> &#8226;
    <a href="/indices/europe-energy-risk-index#methodology">EERI Methodology</a> &#8226;
    <a href="/indices/europe-gas-stress-index#methodology">EGSI Methodology</a>.
  </div>

  <!-- ── CTA ── -->
  <div class="cta-section">
    <div class="cta-label">Real-Time Intelligence</div>
    <h2 class="cta-headline">Monitor Risk in Real-Time</h2>
    <p class="cta-sub">Get live index alerts, daily AI-powered briefings, and full dashboard access across all EnergyRiskIQ risk indices.</p>
    <a href="/register" class="cta-btn">Start Free — No Card Required</a>
    <a href="/indices" class="cta-secondary">Explore all indices &#8594;</a>
  </div>

</div>

<footer class="page-footer">
  &#169; {datetime.now().year} EnergyRiskIQ &nbsp;&bull;&nbsp;
  <a href="/">Home</a>
  <a href="/indices">Indices</a>
  <a href="/research">Research</a>
  <a href="/alerts">Alerts</a>
  <a href="/privacy">Privacy</a>
  <a href="/terms">Terms</a>
</footer>

<script>
window.downloadInfographic = function(elId, btnId) {{
  var el  = document.getElementById(elId);
  var btn = document.getElementById(btnId);
  if (!el || typeof html2canvas === 'undefined') {{
    alert('Export library not loaded yet — please wait a moment and try again.');
    return;
  }}
  if (btn) {{ btn.textContent = 'Generating\u2026'; btn.style.color = '#facc15'; }}
  var SCALE   = 2;
  var PAD     = 40 * SCALE;
  var TITLE_H = 80;
  html2canvas(el, {{
    scale: SCALE,
    backgroundColor: '#141926',
    logging: false,
    useCORS: true,
    allowTaint: true
  }}).then(function(captured) {{
    var CW = captured.width + PAD * 2;
    var CH = captured.height + TITLE_H + 14;
    var canvas = document.createElement('canvas');
    canvas.width  = CW;
    canvas.height = CH;
    var ctx = canvas.getContext('2d');

    ctx.fillStyle = '#0b0f1a';
    ctx.fillRect(0, 0, CW, CH);
    ctx.fillStyle = '#111827';
    ctx.fillRect(0, 0, CW, TITLE_H);
    ctx.fillStyle = '#d4a017';
    ctx.fillRect(0, 0, 6, TITLE_H);

    ctx.font = 'bold 28px sans-serif';
    ctx.fillStyle = '#f1f5f9';
    ctx.fillText('Current Energy Risk Environment \u2014 {today_str}', PAD, 36);

    ctx.font = '18px sans-serif';
    ctx.fillStyle = '#d4a017';
    ctx.fillText('EnergyRiskIQ  \u00B7  energyriskiq.com', PAD, 62);

    ctx.fillStyle = '#1e3a5f';
    ctx.fillRect(0, TITLE_H, CW, 2);

    ctx.drawImage(captured, PAD, TITLE_H + 10);

    ctx.font = '16px sans-serif';
    ctx.fillStyle = '#1e3a5f';
    var wm = 'EnergyRiskIQ \u00B7 energyriskiq.com \u00B7 {data_date}';
    ctx.fillText(wm, CW - ctx.measureText(wm).width - PAD / 2, CH - 6);

    var a = document.createElement('a');
    a.download = 'energy-risk-environment-{data_date}-energyriskiq.png';
    a.href = canvas.toDataURL('image/png');
    a.click();

    if (btn) {{
      btn.textContent = '\u2713 Downloaded!';
      btn.style.color = '#22c55e';
      setTimeout(function() {{
        btn.textContent = '\u2B07 Download PNG';
        btn.style.color = '';
      }}, 2800);
    }}
  }}).catch(function(err) {{
    console.error('Download failed:', err);
    if (btn) {{ btn.textContent = '\u2B07 Download PNG'; btn.style.color = ''; }}
  }});
}};
</script>

</body>
</html>"""
        return HTMLResponse(content=html)

    except Exception as e:
        logger.error(f"Energy risk snapshot failed: {e}", exc_info=True)
        return HTMLResponse(content=f"<h1>Error loading snapshot</h1><p>{e}</p>", status_code=500)
