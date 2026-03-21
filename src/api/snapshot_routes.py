"""
Energy Risk Snapshot Page
Route: /data/energy-risk-snapshot
SEO-optimized live page showing current global energy risk state.
"""
import os
import math
import json
import hashlib
import threading
import asyncio
import logging
import html as _html
from datetime import datetime, timezone
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, StreamingResponse

from src.db.db import execute_production_one, execute_production_query

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/api/hero-snapshot")
async def hero_snapshot_api():
    """Fast JSON endpoint powering the hero panel on the landing page."""
    from fastapi.responses import JSONResponse
    try:
        geri = execute_production_one(
            "SELECT value, band FROM intel_indices_daily "
            "WHERE index_id='global:geo_energy_risk' ORDER BY date DESC LIMIT 1"
        )
        eeri = execute_production_one(
            "SELECT value, band FROM reri_indices_daily "
            "WHERE index_id='europe:eeri' ORDER BY date DESC LIMIT 1"
        )
        egsi = execute_production_one(
            "SELECT index_value AS value, band FROM egsi_m_daily "
            "WHERE region='Europe' ORDER BY index_date DESC LIMIT 1"
        )
        brent = execute_production_one(
            "SELECT brent_price FROM oil_price_snapshots ORDER BY date DESC LIMIT 1"
        )
        ttf = execute_production_one(
            "SELECT ttf_price FROM ttf_gas_snapshots ORDER BY date DESC LIMIT 1"
        )
        storage = execute_production_one(
            "SELECT eu_storage_percent FROM gas_storage_snapshots ORDER BY date DESC LIMIT 1"
        )
        return JSONResponse({
            "geri":    {"value": float(geri["value"]),       "band": geri["band"]},
            "eeri":    {"value": float(eeri["value"]),       "band": eeri["band"]},
            "egsi":    {"value": float(egsi["value"]),       "band": egsi["band"]},
            "brent":   float(brent["brent_price"]),
            "ttf":     float(ttf["ttf_price"]),
            "storage": float(storage["eu_storage_percent"]),
        }, headers={"Cache-Control": "public, max-age=300"})
    except Exception as exc:
        logger.error("hero-snapshot API error: %s", exc)
        return JSONResponse({"error": str(exc)}, status_code=500)

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


def _fetch_infographic_watchlist(geri_val: float, storage_pct: float) -> list:
    """Fetch watchlist items using same logic as Daily Digest section 10."""
    from datetime import date, timedelta
    items = []
    try:
        start = date.today() - timedelta(days=1)
        end   = date.today() + timedelta(days=1)
        rows  = execute_production_query(
            """SELECT headline, scope_region, severity, category
               FROM alert_events
               WHERE created_at >= %s AND created_at < %s AND severity >= 7
               ORDER BY severity DESC, created_at DESC
               LIMIT 10""",
            (start, end)
        )
        seen = set()
        for r in (rows or []):
            headline = (r.get("headline") or "").strip()
            region   = r.get("scope_region") or "Global"
            sev      = r.get("severity", 7)
            cat      = r.get("category") or "general"
            key      = f"{cat}:{region}"
            if key in seen or not headline:
                continue
            seen.add(key)
            items.append({
                "title": headline[:52],
                "desc":  f"{region} — Severity {sev}/10. Monitor for energy supply disruption signals.",
            })
            if len(items) >= 4:
                break
    except Exception as ex:
        logger.warning(f"_fetch_infographic_watchlist error: {ex}")

    if geri_val > 60 and len(items) < 4:
        items.append({
            "title": "GERI Above 60 — Elevated Global Risk",
            "desc":  "Global risk index in elevated territory. Monitor supply chain disruptions.",
        })
    if storage_pct < 40 and len(items) < 4:
        items.append({
            "title": f"EU Gas Storage At {storage_pct:.1f}% — Below Norm",
            "desc":  "Storage below seasonal comfort level — supply cushion at risk.",
        })
    for w in WATCHLIST:
        if len(items) >= 5:
            break
        items.append({"title": w["title"], "desc": w["desc"]})
    return items[:5]


def _build_infographic_html(
    today_str,
    geri_val, geri_band, geri_date, geri_delta,
    eeri_val, eeri_band, eeri_delta,
    egsi_val, egsi_band,
    brent_price, brent_chg, brent_chg_pct,
    ttf_price, ttf_chg,
    storage_pct,
    ai_texts=None,
    watchlist_items=None,
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

    # AI-generated daily texts (with fallback)
    _at = ai_texts or {}
    ai_geri_desc    = _html.escape(_at.get('geri_desc',    'Sharp increase driven by Middle East conflict escalation and infrastructure attacks.'))
    ai_eeri_desc    = _html.escape(_at.get('eeri_desc',    'Stability reflects ongoing but contained European risks, notably Ukraine power grid attacks.'))
    ai_egsi_bullet1 = _html.escape(_at.get('egsi_bullet1', 'High stress sustained due to repeated strikes on Gulf oil hubs and port disruptions.'))
    ai_egsi_bullet2 = _html.escape(_at.get('egsi_bullet2', f'EU gas storage sits at {storage_pct:.2f}% full.'))
    ai_storage_note = _html.escape(_at.get('storage_note', 'Weekly changes to assess supply cushion ahead of summer.'))

    # Watchlist — live items from digest data, fallback to static WATCHLIST
    _wl_source = watchlist_items if watchlist_items else WATCHLIST
    _wl_list   = _wl_source[:5]
    wl_count   = len(_wl_list)
    wl_items   = ''
    for w in _wl_list:
        wl_items += (
            '<div class="ig-wl-item">'
            '<div class="ig-wl-check">&#10003;</div>'
            '<div class="ig-wl-body">'
            f'<div class="ig-wl-title">{_html.escape(w["title"])}</div>'
            f'<div class="ig-wl-desc">{_html.escape(w["desc"])}</div>'
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
        '.ig-heading { font-size:16px; font-weight:800; color:#d4a017; margin-bottom:13px;'
        '  border-bottom:1px solid rgba(212,160,23,0.25); padding-bottom:8px; }'
        '.ig-indices-body { display:grid; grid-template-columns:54% 46%; gap:0; height:100%; }'
        '.ig-left-col { padding-right:14px; }'
        '.ig-right-col { padding-left:14px; border-left:1px solid rgba(255,255,255,0.10); }'
        '.ig-idx-label { font-size:11px; font-weight:700; color:#94a3b8; letter-spacing:0.4px;'
        '  margin-bottom:7px; }'
        '.ig-idx-row { display:flex; align-items:flex-start; gap:10px; margin-bottom:12px; }'
        '.ig-idx-sep { border:none; border-top:1px solid rgba(255,255,255,0.07);'
        '  margin:8px 0 10px; }'
        '.ig-gauge-block { flex-shrink:0; text-align:center; }'
        '.ig-gauge-sub { font-size:13px; color:#d4a017; font-weight:800; margin-top:4px; }'
        '.ig-idx-info { flex:1; min-width:0; }'
        '.ig-band-name { font-size:25px; font-weight:900; line-height:1.1; margin-bottom:5px; }'
        '.ig-band-val  { font-size:20px; font-weight:800; line-height:1.1; margin-bottom:5px; }'
        '.ig-band-note { font-size:10.5px; color:#94a3b8; line-height:1.5; }'
        '.ig-rc-title { font-size:13px; font-weight:700; color:#e2e8f0; margin-bottom:9px;'
        '  line-height:1.45; }'
        '.ig-rc-bullet { font-size:10.5px; color:#94a3b8; line-height:1.45; margin-bottom:5px; }'
        '.ig-storage-sep { margin:9px 0 8px; border:none;'
        '  border-top:2px solid rgba(255,255,255,0.10); }'
        '.ig-storage-title { font-size:13px; font-weight:700; color:#d4a017;'
        '  margin-bottom:7px; line-height:1.45; }'
        '.ig-storage-note { font-size:10.5px; color:#94a3b8; line-height:1.45; }'
        '.ig-clipboard { grid-area:clipboard; position:relative;'
        '  display:flex; flex-direction:column;'
        '  background:#131d31; border-left:1px solid #1e3050; }'
        '.ig-clipboard-inner { display:flex; flex-direction:column;'
        '  height:100%; padding:18px 16px 14px; }'
        '.ig-clip-top { display:none; }'
        '.ig-clip-metal { display:none; }'
        '.ig-clip-header { font-size:11px; font-weight:900;'
        '  letter-spacing:1.8px; text-transform:uppercase; color:#d4a017;'
        '  margin-bottom:4px; }'
        '.ig-clip-subcount { font-size:10px; color:#64748b; margin-bottom:10px;'
        '  padding-bottom:10px; border-bottom:1px solid rgba(51,65,85,0.8); }'
        '.ig-wl-item { display:flex; gap:10px; align-items:flex-start;'
        '  padding:10px 0; border-bottom:1px solid rgba(51,65,85,0.5); }'
        '.ig-wl-item:last-child { border-bottom:none; }'
        '.ig-wl-check { width:18px; height:18px; border-radius:3px; flex-shrink:0;'
        '  background:rgba(212,160,23,0.18); border:1.5px solid #d4a017;'
        '  color:#d4a017; font-size:11px; font-weight:900;'
        '  display:flex; align-items:center; justify-content:center; margin-top:1px; }'
        '.ig-wl-title { font-size:11.5px; font-weight:700; color:#f1f5f9; margin-bottom:3px; }'
        '.ig-wl-desc { font-size:9.5px; color:#64748b; line-height:1.4; }'
        '.ig-footer { grid-area:footer; padding:16px 22px; text-align:center;'
        '  background:#0f1522; border-top:1px solid rgba(255,255,255,0.06);'
        '  font-size:15px; color:#cbd5e1; font-style:italic; line-height:1.6; }'
        '.ig-footer strong { color:#ffffff; font-style:normal; }'
        '.ig-scroll { overflow-x:auto; }'
        '@media (max-width:640px) {'
        '  .ig-root { min-width:0 !important; }'
        '  .ig-scroll { overflow-x:visible; }'
        '  .ig-grid { display:block; }'
        '  .ig-prices { flex-wrap:wrap; }'
        '  .ig-price-card { flex:0 0 50%; box-sizing:border-box; min-height:80px; }'
        '  .ig-price-card + .ig-price-card { border-left:none; }'
        '  .ig-price-card:nth-child(n+3) { border-top:1px solid rgba(255,255,255,0.12); }'
        '  .ig-indices-body { display:block; }'
        '  .ig-right-col { padding-left:0; border-left:none; padding-top:12px; margin-top:10px;'
        '    border-top:1px solid rgba(255,255,255,0.10); }'
        '  .ig-clipboard { border-left:none; border-top:1px solid #1e3050; }'
        '  .ig-topbar { flex-direction:column; gap:8px; align-items:flex-start; }'
        '  .ig-pc-value { font-size:26px; }'
        '}'
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

          <!-- LEFT: GERI + EERI -->
          <div class="ig-left-col">

            <!-- GERI row -->
            <div class="ig-idx-label">GERI (Global Energy Risk Index): {geri_val}/100</div>
            <div class="ig-idx-row">
              <div class="ig-gauge-block">
                {geri_ig}
                <div class="ig-gauge-sub">GERI: {geri_val}</div>
              </div>
              <div class="ig-idx-info">
                <div class="ig-band-name" style="color:{gc}">{geri_band}</div>
                <div class="ig-band-note">&#8211; {ai_geri_desc}</div>
              </div>
            </div>

            <hr class="ig-idx-sep">

            <!-- EERI row -->
            <div class="ig-idx-label">EERI (European Energy Risk Index):</div>
            <div class="ig-idx-row">
              <div class="ig-gauge-block">
                {eeri_ig}
                <div class="ig-gauge-sub">EERI: {eeri_val}</div>
              </div>
              <div class="ig-idx-info">
                <div class="ig-band-val" style="color:{ec}">{eeri_val} ({eeri_change_note})</div>
                <div class="ig-band-note">&#8211; {ai_eeri_desc}</div>
              </div>
            </div>

          </div>

          <!-- RIGHT: EGSI-M + EU Storage -->
          <div class="ig-right-col">
            <div class="ig-rc-title">
              EGSI-M (Energy Geopolitical Stress Index &#8211; Middle East:
              <span style="color:{mgc};font-weight:900"> {egsi_val:.1f}</span>)
            </div>
            <div class="ig-rc-bullet">&#8211; {ai_egsi_bullet1}</div>
            <div class="ig-rc-bullet">&#8211; {ai_egsi_bullet2}</div>
            <hr class="ig-storage-sep">
            <div class="ig-storage-title">
              EU Gas Storage Levels:
              <span style="color:{mgc};font-weight:900"> {storage_pct:.2f}%</span> full
            </div>
            <div class="ig-storage-note">&#8226; {ai_storage_note}</div>
          </div>

        </div>
      </div>

      <!-- ── CLIPBOARD WATCHLIST ── -->
      <div class="ig-clipboard">
        <div class="ig-clipboard-inner">
          <div class="ig-clip-header">&#128203; Custom Watchlist</div>
          <div class="ig-clip-subcount">{wl_count} active risk vectors being monitored</div>
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


# ── Snapshot Engine ─────────────────────────────────────────────────────────
# Single shared cache keyed by data fingerprint (not UTC date).
# AI texts regenerate automatically whenever live data changes.
_SNAPSHOT_CACHE: dict = {}
_SNAPSHOT_LOCK = threading.Lock()


def _compute_fingerprint(
    geri_val, geri_date, eeri_val, eeri_date,
    egsi_val, egsi_date, brent_price, brent_hour,
    ttf_price, ttf_date, vix_close, lng_price, storage_pct,
) -> str:
    raw = (
        f"{geri_date}:{geri_val}|{eeri_date}:{eeri_val}|{egsi_date}:{round(egsi_val,1)}"
        f"|{round(brent_price,1)}h{brent_hour}|{ttf_date}:{round(ttf_price,2)}"
        f"|{round(vix_close,2)}|{round(lng_price,2)}|{round(storage_pct,1)}"
    )
    return hashlib.md5(raw.encode()).hexdigest()[:14]


def _run_snapshot_engine(
    fingerprint,
    geri_val, geri_band, geri_delta, geri_date,
    eeri_val, eeri_band, eeri_delta,
    egsi_val, egsi_band,
    brent_price, ttf_price, vix_close, lng_price,
    storage_pct, storage_band, storage_norm, storage_dev,
    watchlist_items,
    today_str,
) -> dict:
    """Dedicated snapshot engine.
    Generates AI panel captions + expert daily assessment in one call.
    Result is cached by data fingerprint — regenerates only when live data changes."""

    with _SNAPSHOT_LOCK:
        if fingerprint in _SNAPSHOT_CACHE:
            logger.debug(f"Snapshot engine: cache hit for fingerprint={fingerprint}")
            return _SNAPSHOT_CACHE[fingerprint]

    fallback_texts = {
        'geri_desc':    'Elevated global risk driven by Middle East escalation and persistent supply chain stress.',
        'eeri_desc':    'European risk remains structurally high, supported by ongoing Ukraine infrastructure attacks.',
        'egsi_bullet1': 'Geopolitical stress sustained by Gulf chokepoint tensions and tanker traffic disruptions.',
        'egsi_bullet2': f'EU gas storage at {storage_pct:.2f}% — {abs(storage_dev):.1f}% below seasonal norm of {storage_norm:.1f}% — constrains the summer supply buffer.',
        'storage_note': f'Storage deviation of {storage_dev:+.1f}% from the {storage_norm:.1f}% seasonal norm raises refill risk through the injection season.',
    }
    fallback_assessment = _build_short_interpretation(
        geri_val, eeri_val, egsi_val, storage_pct, geri_band, eeri_band, None
    )

    try:
        from openai import OpenAI
        ai_key = os.environ.get('AI_INTEGRATIONS_OPENAI_API_KEY')
        ai_url = os.environ.get('AI_INTEGRATIONS_OPENAI_BASE_URL')
        client = OpenAI(api_key=ai_key, base_url=ai_url) if ai_key and ai_url else OpenAI()

        wl_context = ""
        if watchlist_items:
            wl_context = "\nActive risk vectors being monitored:\n" + "\n".join(
                f"  - {w['title']}: {w['desc']}" for w in watchlist_items[:5]
            )

        sign = lambda v: '+' if v >= 0 else ''

        prompt = (
            f"Today is {today_str}. You are EnergyRiskIQ's senior energy risk analyst.\n\n"
            f"LIVE DATA (all from production pipeline, just updated):\n"
            f"  GERI  (Global Energy Risk Index):       {geri_val}/100  band={geri_band}  delta={sign(geri_delta)}{geri_delta:d}pt vs yesterday\n"
            f"  EERI  (European Energy Risk Index):     {eeri_val}/100  band={eeri_band}  delta={sign(eeri_delta)}{eeri_delta:d}pt vs yesterday\n"
            f"  EGSI-M (Geopolitical Stress, Mid-East): {egsi_val:.1f}    band={egsi_band}\n"
            f"  EU Gas Storage:  {storage_pct:.2f}% full  seasonal_norm={storage_norm:.1f}%  deviation={'+' if storage_dev >= 0 else ''}{storage_dev:.1f}%  band={storage_band}\n"
            f"  Brent Crude Oil: ${brent_price:.2f}/bbl\n"
            f"  TTF Natural Gas: €{ttf_price:.2f}/MWh\n"
            f"  VIX Volatility:  {vix_close:.2f}\n"
            f"  LNG JKM (Asia):  ${lng_price:.2f}/MMBtu\n"
            f"{wl_context}\n\n"
            "Return ONLY a valid JSON object with exactly these 6 keys. No markdown. No extra keys.\n\n"
            "1. 'geri_desc'    (≤130 chars): 1 sentence explaining the primary driver of the current GERI level.\n"
            "2. 'eeri_desc'    (≤130 chars): 1 sentence explaining the primary driver of the current EERI level.\n"
            "3. 'egsi_bullet1' (≤130 chars): 1 sentence on the primary geopolitical stress factor behind EGSI-M.\n"
            "4. 'egsi_bullet2' (≤130 chars): 1 sentence linking EGSI-M stress to the current gas storage or supply outlook.\n"
            "5. 'storage_note' (≤130 chars): 1 sentence on what the EU storage level implies for seasonal supply risk.\n"
            "6. 'assessment'   (≤520 chars): 3–4 sentence expert daily assessment paragraph. "
            "Reference specific numbers (GERI, EERI, EGSI values, Brent, TTF, VIX, LNG, storage %). "
            "Connect the data points analytically. Authoritative, fact-dense, flowing prose. No bullets. No markdown."
        )

        resp = client.chat.completions.create(
            model='gpt-4.1-mini',
            messages=[{'role': 'user', 'content': prompt}],
            temperature=0.35,
            max_tokens=650,
            response_format={'type': 'json_object'},
            timeout=18,
        )
        data = json.loads(resp.choices[0].message.content)

        ai_texts = {}
        for k in fallback_texts:
            val = str(data.get(k, '')).strip().rstrip('.')
            ai_texts[k] = (val[:170] + '.') if val else fallback_texts[k]

        assessment = str(data.get('assessment', '')).strip()
        if not assessment:
            assessment = fallback_assessment

        engine_result = {'ai_texts': ai_texts, 'assessment': assessment}

        with _SNAPSHOT_LOCK:
            if len(_SNAPSHOT_CACHE) >= 6:
                oldest_key = next(iter(_SNAPSHOT_CACHE))
                del _SNAPSHOT_CACHE[oldest_key]
            _SNAPSHOT_CACHE[fingerprint] = engine_result

        logger.info(f"Snapshot engine: generated AI output for fingerprint={fingerprint}")
        return engine_result

    except Exception as exc:
        logger.warning(f"Snapshot engine AI call failed: {exc}")
        return {'ai_texts': fallback_texts, 'assessment': fallback_assessment}


_PAGE_CSS = """
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    :root {
      --bg: #0f172a;
      --card: #1e293b;
      --card2: #162032;
      --border: #334155;
      --text: #e2e8f0;
      --muted: #94a3b8;
      --gold: #d4a017;
      --gold2: #fbbf24;
    }
    body {
      background: var(--bg);
      color: var(--text);
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      min-height: 100vh;
      line-height: 1.6;
      overflow-x: hidden;
    }
    .nav {
      background: #1e293b;
      border-bottom: 1px solid #334155;
      padding: 1rem 0;
      position: sticky;
      top: 0;
      z-index: 100;
    }
    .nav-inner {
      display: flex; justify-content: space-between; align-items: center;
      max-width: 1160px; margin: 0 auto; padding: 0 1.5rem;
    }
    .logo {
      font-weight: 700; font-size: 1.2rem; color: #f1f5f9;
      text-decoration: none; display: flex; align-items: center; gap: 0.5rem;
    }
    .cta-btn-nav {
      background: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%);
      color: white !important; padding: 0.5rem 1rem; border-radius: 6px;
      text-decoration: none; font-weight: 600; font-size: 13px;
    }
    .cta-btn-nav:hover { opacity: 0.9; }
    .hero {
      padding: 52px 24px 40px;
      text-align: center;
      border-bottom: 1px solid var(--border);
      background: linear-gradient(180deg, rgba(212,160,23,0.04) 0%, transparent 100%);
    }
    .hero-date {
      font-size: 13px; font-weight: 600; letter-spacing: 1.5px;
      color: var(--gold); text-transform: uppercase; margin-bottom: 14px;
    }
    .hero h1 {
      font-family: 'DM Serif Display', serif;
      font-size: clamp(28px, 5vw, 48px);
      font-weight: 400;
      color: #ffffff;
      line-height: 1.2;
      max-width: 700px;
      margin: 0 auto 16px;
    }
    .hero-sub {
      font-size: 15px; color: var(--muted);
      max-width: 560px; margin: 0 auto;
    }
    .page-body {
      max-width: 1160px;
      margin: 0 auto;
      padding: 40px 20px 60px;
    }
    .section-label {
      font-size: 11px; font-weight: 700; letter-spacing: 2px;
      color: var(--gold); text-transform: uppercase;
      margin-bottom: 20px; display: flex; align-items: center; gap: 10px;
    }
    .section-label::after {
      content: '';
      flex: 1; height: 1px;
      background: linear-gradient(90deg, rgba(212,160,23,0.4) 0%, transparent 100%);
    }
    .price-grid {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 16px;
      margin-bottom: 44px;
    }
    @media (max-width: 768px) { .price-grid { grid-template-columns: repeat(2, 1fr); } }
    @media (max-width: 420px) { .price-grid { grid-template-columns: 1fr; } }
    .price-card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 22px 20px;
      position: relative;
      overflow: hidden;
      transition: border-color 0.2s, transform 0.2s;
    }
    .price-card:hover { border-color: rgba(212,160,23,0.35); transform: translateY(-2px); }
    .price-card::before {
      content: '';
      position: absolute; inset: 0;
      background: linear-gradient(135deg, rgba(255,255,255,0.02) 0%, transparent 60%);
      pointer-events: none;
    }
    .price-commodity {
      font-size: 11px; font-weight: 700; letter-spacing: 1.5px;
      text-transform: uppercase; color: var(--muted); margin-bottom: 10px;
    }
    .price-value {
      font-size: 30px; font-weight: 800;
      color: #ffffff; line-height: 1; margin-bottom: 8px;
      font-variant-numeric: tabular-nums;
    }
    .price-value sup { font-size: 16px; font-weight: 600; vertical-align: top; margin-top: 4px; }
    .price-change {
      font-size: 13px; font-weight: 600;
    }
    .price-source {
      font-size: 10px; color: var(--muted);
      margin-top: 8px; opacity: 0.7;
    }
    .main-grid {
      display: grid;
      grid-template-columns: 1fr 340px;
      gap: 28px;
      margin-bottom: 36px;
    }
    @media (max-width: 900px) { .main-grid { grid-template-columns: 1fr; } }
    .indices-col { display: flex; flex-direction: column; gap: 16px; }
    .index-card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 22px 24px;
      display: flex;
      gap: 20px;
      align-items: flex-start;
      transition: border-color 0.2s;
    }
    .index-card:hover { border-color: rgba(212,160,23,0.3); }
    .gauge-wrap {
      flex-shrink: 0;
      width: 100px;
    }
    .gauge-svg { width: 100%; height: auto; display: block; }
    .index-detail { flex: 1; }
    .index-name {
      font-size: 12px; font-weight: 700; letter-spacing: 1.2px;
      text-transform: uppercase; color: var(--muted); margin-bottom: 4px;
    }
    .index-fullname {
      font-size: 13px; color: #64748b; margin-bottom: 8px; font-weight: 400;
    }
    .index-value-row {
      display: flex; align-items: baseline; gap: 10px; margin-bottom: 6px;
    }
    .index-number {
      font-size: 40px; font-weight: 800; line-height: 1;
      font-variant-numeric: tabular-nums;
    }
    .index-denom { font-size: 18px; color: var(--muted); font-weight: 400; }
    .band-pill {
      display: inline-block;
      font-size: 11px; font-weight: 700; letter-spacing: 1px;
      text-transform: uppercase; padding: 3px 10px; border-radius: 20px;
      border: 1px solid currentColor; margin-bottom: 8px;
    }
    .delta { font-size: 13px; font-weight: 600; }
    .index-note {
      font-size: 12px; color: var(--muted); line-height: 1.5;
      border-left: 2px solid rgba(255,255,255,0.08);
      padding-left: 10px; margin-top: 6px;
    }
    .index-date { font-size: 11px; color: #475569; margin-top: 6px; }
    .watchlist-card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 14px;
      overflow: hidden;
    }
    .wl-header {
      padding: 18px 20px 14px;
      border-bottom: 1px solid var(--border);
      background: linear-gradient(135deg, rgba(212,160,23,0.06) 0%, transparent 100%);
    }
    .wl-header-title {
      font-size: 13px; font-weight: 700; letter-spacing: 1px;
      text-transform: uppercase; color: var(--gold2);
    }
    .wl-header-sub {
      font-size: 11px; color: var(--muted); margin-top: 3px;
    }
    .wl-item {
      display: flex; gap: 12px; align-items: flex-start;
      padding: 14px 20px;
      border-bottom: 1px solid rgba(255,255,255,0.04);
      text-decoration: none;
      color: inherit;
      transition: background 0.15s;
    }
    .wl-item:last-child { border-bottom: none; }
    .wl-item:hover { background: rgba(255,255,255,0.03); }
    .wl-check {
      width: 20px; height: 20px; border-radius: 4px;
      background: rgba(212,160,23,0.15);
      border: 1px solid rgba(212,160,23,0.4);
      color: var(--gold2);
      font-size: 12px; font-weight: 700;
      display: flex; align-items: center; justify-content: center;
      flex-shrink: 0; margin-top: 1px;
    }
    .wl-body { flex: 1; }
    .wl-title { font-size: 13px; font-weight: 600; color: #e2e8f0; margin-bottom: 3px; }
    .wl-desc { font-size: 11px; color: var(--muted); line-height: 1.4; }
    .interp-block {
      background: linear-gradient(135deg, #111827 0%, #0f172a 100%);
      border: 1px solid rgba(212,160,23,0.2);
      border-radius: 14px;
      padding: 32px 36px;
      margin-bottom: 28px;
      position: relative;
      overflow: hidden;
    }
    .interp-block::before {
      content: '';
      position: absolute;
      top: 0; left: 0; right: 0; height: 3px;
      background: linear-gradient(90deg, var(--gold), transparent);
    }
    .interp-label {
      font-size: 10px; font-weight: 700; letter-spacing: 2px;
      text-transform: uppercase; color: var(--gold);
      margin-bottom: 14px; display: flex; align-items: center; gap: 8px;
    }
    .interp-label::before { content: '\25B6'; font-size: 8px; }
    .interp-text {
      font-size: 17px;
      color: #cbd5e1;
      line-height: 1.75;
      font-weight: 400;
    }
    .interp-text strong { color: #ffffff; font-weight: 600; }
    .storage-row {
      display: flex; align-items: center; gap: 16px;
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 18px 24px;
      margin-bottom: 28px;
    }
    .storage-icon { font-size: 28px; flex-shrink: 0; }
    .storage-label { font-size: 12px; color: var(--muted); font-weight: 500; }
    .storage-value { font-size: 24px; font-weight: 800; }
    .storage-note { font-size: 12px; color: var(--muted); margin-top: 2px; }
    .storage-bar-wrap { flex: 1; }
    .storage-bar {
      height: 8px; background: rgba(255,255,255,0.08);
      border-radius: 4px; overflow: hidden;
    }
    .storage-bar-fill {
      height: 100%; border-radius: 4px;
      transition: width 0.5s;
    }
    .snap-cite-card {
      background: #1e293b;
      border: 1px solid #334155;
      border-radius: 12px;
      padding: 24px 28px;
      margin-bottom: 32px;
    }
    .snap-cite-card h3 {
      font-size: 1.05rem; font-weight: 700; color: #f1f5f9;
      margin-bottom: 10px;
    }
    .snap-cite-desc {
      font-size: 14px; color: #94a3b8; margin-bottom: 18px; line-height: 1.6;
    }
    .snap-cite-code-wrap {
      background: #0f172a; border: 1px solid #334155;
      border-radius: 8px; padding: 16px 20px; position: relative;
    }
    .snap-cite-code {
      font-family: 'Courier New', Courier, monospace;
      font-size: 13px; color: #e2e8f0; line-height: 1.8;
    }
    .snap-cite-code a { color: #60a5fa; text-decoration: none; }
    .snap-cite-copy-btn {
      position: absolute; top: 12px; right: 12px;
      background: rgba(30,41,59,0.9); border: 1px solid #475569;
      color: #94a3b8; padding: 5px 14px; font-size: 12px; font-weight: 600;
      border-radius: 6px; cursor: pointer; font-family: inherit;
    }
    .snap-cite-copy-btn:hover { color: #f1f5f9; border-color: #94a3b8; }
    .snap-cite-footer {
      margin-top: 14px; font-size: 12px; color: #64748b;
    }
    .snap-cite-footer a { color: #60a5fa; text-decoration: none; }
    .snap-cite-footer a:hover { text-decoration: underline; }
    .citation-block {
      background: rgba(255,255,255,0.02);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 16px 20px;
      font-size: 12px;
      color: var(--muted);
      line-height: 1.6;
      margin-bottom: 36px;
    }
    .citation-block a { color: var(--gold2); text-decoration: none; }
    .citation-block a:hover { text-decoration: underline; }
    .cta-section {
      text-align: center;
      padding: 52px 24px;
      background: linear-gradient(135deg, rgba(212,160,23,0.06) 0%, rgba(11,15,26,0) 60%);
      border-top: 1px solid var(--border);
      border-radius: 16px;
    }
    .cta-label {
      font-size: 11px; font-weight: 700; letter-spacing: 2px;
      text-transform: uppercase; color: var(--gold); margin-bottom: 16px;
    }
    .cta-headline {
      font-family: 'DM Serif Display', serif;
      font-size: clamp(24px, 4vw, 36px);
      font-weight: 400; color: #ffffff;
      margin-bottom: 12px; line-height: 1.25;
    }
    .cta-sub {
      font-size: 15px; color: var(--muted);
      max-width: 480px; margin: 0 auto 28px;
    }
    .cta-btn {
      display: inline-block;
      background: linear-gradient(135deg, #d4a017, #fbbf24);
      color: #0b0f1a;
      font-size: 15px; font-weight: 700;
      padding: 14px 36px; border-radius: 8px;
      text-decoration: none; letter-spacing: 0.3px;
      transition: transform 0.2s, box-shadow 0.2s;
      box-shadow: 0 4px 20px rgba(212,160,23,0.3);
    }
    .cta-btn:hover { transform: translateY(-2px); box-shadow: 0 8px 28px rgba(212,160,23,0.45); }
    .cta-secondary {
      display: block; margin-top: 14px;
      font-size: 13px; color: var(--muted); text-decoration: none;
    }
    .cta-secondary:hover { color: var(--text); }
    .page-footer {
      border-top: 1px solid var(--border);
      padding: 24px;
      text-align: center;
      font-size: 12px; color: #475569;
    }
    .page-footer a { color: var(--muted); text-decoration: none; margin: 0 8px; }
    .page-footer a:hover { color: var(--text); }
"""

_LOADER_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Global Energy Risk Snapshot | EnergyRiskIQ</title>
<meta name="description" content="Live global energy risk snapshot. Current GERI, EERI and EGSI-M index values with Brent crude, TTF gas, VIX and LNG market prices.">
<meta name="robots" content="index, follow">
<link rel="canonical" href="https://energyriskiq.com/data/energy-risk-snapshot">
<link rel="icon" type="image/png" href="/static/favicon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=DM+Serif+Display&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js"></script>
<style>
""" + _PAGE_CSS + """
/* ── LOADER ── */
#snap-loader{
  position:fixed;inset:0;background:#0f172a;
  display:flex;flex-direction:column;align-items:center;justify-content:center;
  z-index:9999;
}
.ld-logo{margin-bottom:36px;opacity:.95}
.ld-logo img{height:34px;vertical-align:middle;margin-right:10px}
.ld-logo span{font-size:1.25rem;font-weight:800;color:#e2e8f0;letter-spacing:-.3px;vertical-align:middle}
.ld-ring-wrap{position:relative;width:84px;height:84px}
.ld-ring-bg{
  position:absolute;inset:0;border-radius:50%;
  border:3px solid rgba(255,255,255,.05);
}
.ld-arc1{
  position:absolute;inset:0;border-radius:50%;
  border:3px solid transparent;
  border-top-color:#d4a017;border-right-color:#d4a017;
  animation:spin-cw 1.4s cubic-bezier(.6,.2,.4,.8) infinite;
}
.ld-arc2{
  position:absolute;inset:8px;border-radius:50%;
  border:2.5px solid transparent;
  border-bottom-color:#3b82f6;border-left-color:#3b82f6;
  animation:spin-ccw 1.1s cubic-bezier(.6,.2,.4,.8) infinite;
}
.ld-arc3{
  position:absolute;inset:18px;border-radius:50%;
  border:2px solid transparent;
  border-top-color:rgba(251,191,36,.6);
  animation:spin-cw .8s linear infinite;
}
.ld-dot{
  position:absolute;top:50%;left:50%;width:8px;height:8px;
  background:#d4a017;border-radius:50%;
  transform:translate(-50%,-50%);
  animation:pulse-dot 1.4s ease-in-out infinite;
  box-shadow:0 0 10px rgba(212,160,23,.8);
}
@keyframes spin-cw{to{transform:rotate(360deg)}}
@keyframes spin-ccw{to{transform:rotate(-360deg)}}
@keyframes pulse-dot{0%,100%{transform:translate(-50%,-50%) scale(1);opacity:1}50%{transform:translate(-50%,-50%) scale(.5);opacity:.4}}
.ld-label{margin-top:28px;text-align:center}
.ld-label-main{font-size:15px;font-weight:600;color:#e2e8f0;letter-spacing:.3px;margin-bottom:8px}
.ld-label-sub{font-size:12px;color:#475569;min-height:18px;transition:opacity .3s}
.ld-bar-wrap{width:240px;height:2px;background:rgba(255,255,255,.06);border-radius:2px;margin-top:22px;overflow:hidden}
.ld-bar-fill{height:100%;border-radius:2px;background:linear-gradient(90deg,#d4a017,#fbbf24);animation:bar-progress 12s ease-in-out forwards}
@keyframes bar-progress{0%{width:2%}15%{width:28%}35%{width:52%}55%{width:68%}72%{width:80%}88%{width:90%}100%{width:94%}}
.ld-tags{display:flex;gap:8px;margin-top:28px;flex-wrap:wrap;justify-content:center;max-width:300px}
.ld-tag{font-size:10px;font-weight:700;letter-spacing:1.2px;text-transform:uppercase;color:#334155;border:1px solid #1e293b;padding:4px 10px;border-radius:20px;animation:tag-pop .4s ease both}
.ld-tag:nth-child(1){animation-delay:.1s;color:#d4a017;border-color:rgba(212,160,23,.25)}
.ld-tag:nth-child(2){animation-delay:.2s;color:#3b82f6;border-color:rgba(59,130,246,.25)}
.ld-tag:nth-child(3){animation-delay:.3s}
.ld-tag:nth-child(4){animation-delay:.4s}
.ld-tag:nth-child(5){animation-delay:.5s}
@keyframes tag-pop{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}
.ld-footer{position:absolute;bottom:28px;font-size:10px;font-weight:700;letter-spacing:2px;color:#1e293b;text-transform:uppercase}
</style>
</head>
<body style="overflow:hidden">
<div id="snap-loader">
  <div class="ld-logo">
    <img src="/static/logo.png" alt="EnergyRiskIQ">
    <span>EnergyRiskIQ</span>
  </div>
  <div class="ld-ring-wrap">
    <div class="ld-ring-bg"></div>
    <div class="ld-arc1"></div>
    <div class="ld-arc2"></div>
    <div class="ld-arc3"></div>
    <div class="ld-dot"></div>
  </div>
  <div class="ld-label">
    <div class="ld-label-main">Loading latest data</div>
    <div class="ld-label-sub" id="ld-status">Connecting to production pipeline&hellip;</div>
  </div>
  <div class="ld-bar-wrap"><div class="ld-bar-fill"></div></div>
  <div class="ld-tags">
    <span class="ld-tag">GERI</span>
    <span class="ld-tag">EERI</span>
    <span class="ld-tag">EGSI&#8209;M</span>
    <span class="ld-tag">Brent</span>
    <span class="ld-tag">TTF</span>
  </div>
  <div class="ld-footer">Live Data Engine &mdash; EnergyRiskIQ</div>
</div>
<script>
(function(){
  var msgs=['Connecting to production pipeline\u2026',
            'Fetching GERI\u00a0&\u00a0EERI indices\u2026',
            'Loading commodity prices\u2026',
            'Querying EU gas storage\u2026',
            'Analysing risk environment\u2026',
            'Generating AI assessment\u2026',
            'Building infographic\u2026'];
  var i=0,el=document.getElementById('ld-status');
  setInterval(function(){i=(i+1)%msgs.length;if(el){el.style.opacity='0';setTimeout(function(){el.textContent=msgs[i];el.style.opacity='1';},200);}},2200);
})();
</script>
"""


def _compute_snapshot_html() -> str:
    """Synchronous worker: fetch all production data, run snapshot engine, return full page HTML."""
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
            "SELECT date, eu_storage_percent, seasonal_norm, deviation_from_norm, risk_band FROM gas_storage_snapshots ORDER BY date DESC LIMIT 1"
        )
        return ('ok', geri_row, geri_prev, eeri_row, eeri_prev, egsi_row, egsi_prev,
                brent_row, brent_intra, ttf_row, ttf_prev, vix_row, vix_prev,
                lng_row, storage_row)
    except Exception as e:
        return ('error', str(e))


@router.get("/data/energy-risk-snapshot")
async def energy_risk_snapshot(request: Request):
    async def generate():
        yield _LOADER_HTML

        try:
            rows = await asyncio.to_thread(_compute_snapshot_html)
        except Exception as exc:
            logger.error(f"Snapshot data fetch failed: {exc}", exc_info=True)
            yield f"""<script>
var l=document.getElementById('snap-loader');
if(l){{l.style.display='none';}}
document.body.style.overflow='';
document.title='Error | EnergyRiskIQ';
</script>
<div style="color:#ef4444;padding:40px;font-family:sans-serif;background:#0b0f1a">
  <h2>Error loading snapshot</h2><p>{exc}</p>
</div></body></html>"""
            return

        if rows[0] == 'error':
            yield f"""<script>
var l=document.getElementById('snap-loader');if(l)l.style.display='none';
document.body.style.overflow='';
</script>
<div style="color:#ef4444;padding:40px;font-family:sans-serif;background:#0b0f1a">
  <h2>Error loading snapshot</h2><p>{rows[1]}</p>
</div></body></html>"""
            return

        (_, geri_row, geri_prev, eeri_row, eeri_prev, egsi_row, egsi_prev,
         brent_row, brent_intra, ttf_row, ttf_prev, vix_row, vix_prev,
         lng_row, storage_row) = rows

        try:
            yield await asyncio.to_thread(
                _build_snapshot_html,
                geri_row, geri_prev, eeri_row, eeri_prev, egsi_row, egsi_prev,
                brent_row, brent_intra, ttf_row, ttf_prev, vix_row, vix_prev,
                lng_row, storage_row,
            )
        except Exception as exc:
            logger.error(f"Snapshot HTML build failed: {exc}", exc_info=True)
            yield f"""<script>
var l=document.getElementById('snap-loader');if(l)l.style.display='none';
document.body.style.overflow='';
</script>
<div style="color:#ef4444;padding:40px;font-family:sans-serif;background:#0b0f1a">
  <h2>Error building snapshot</h2><p>{exc}</p>
</div></body></html>"""

    return StreamingResponse(generate(), media_type="text/html")


def _build_snapshot_html(
    geri_row, geri_prev, eeri_row, eeri_prev, egsi_row, egsi_prev,
    brent_row, brent_intra, ttf_row, ttf_prev, vix_row, vix_prev,
    lng_row, storage_row,
) -> str:
    """Build the full page HTML string from pre-fetched DB rows."""
    try:
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

        storage_pct      = _safe_float(storage_row['eu_storage_percent'])   if storage_row else 0.0
        storage_band     = str(storage_row['risk_band'])                     if storage_row else 'ELEVATED'
        storage_norm     = _safe_float(storage_row['seasonal_norm'])         if storage_row else 40.0
        storage_dev      = _safe_float(storage_row['deviation_from_norm'])   if storage_row else 0.0

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

        storage_color = BAND_COLORS.get(storage_band, '#f97316')

        # --- Watchlist (live alert events — fetched before AI call so events inform the assessment) ---
        ig_watchlist = _fetch_infographic_watchlist(geri_val=geri_val, storage_pct=storage_pct)

        # --- Data fingerprint: changes whenever any live value changes ---
        brent_hour_val = int(brent_intra['hour'])    if brent_intra else 0
        ttf_date_val   = str(ttf_row['date'])        if ttf_row    else ''
        vix_date_val   = str(vix_row['date'])        if vix_row    else ''
        lng_date_val   = str(lng_row['date'])        if lng_row    else ''
        eeri_date_val  = str(eeri_row['date'])       if eeri_row   else ''
        egsi_date_val  = str(egsi_row['index_date']) if egsi_row   else ''
        fingerprint = _compute_fingerprint(
            geri_val=geri_val, geri_date=geri_date,
            eeri_val=eeri_val, eeri_date=eeri_date_val,
            egsi_val=egsi_val, egsi_date=egsi_date_val,
            brent_price=brent_price, brent_hour=brent_hour_val,
            ttf_price=ttf_price, ttf_date=ttf_date_val,
            vix_close=vix_close, lng_price=lng_price, storage_pct=storage_pct,
        )

        # --- Run dedicated snapshot engine (AI captions + daily assessment) ---
        engine_result = _run_snapshot_engine(
            fingerprint=fingerprint,
            geri_val=geri_val, geri_band=geri_band, geri_delta=geri_delta, geri_date=geri_date,
            eeri_val=eeri_val, eeri_band=eeri_band, eeri_delta=eeri_delta,
            egsi_val=egsi_val, egsi_band=egsi_band,
            brent_price=brent_price, ttf_price=ttf_price,
            vix_close=vix_close, lng_price=lng_price,
            storage_pct=storage_pct, storage_band=storage_band,
            storage_norm=storage_norm, storage_dev=storage_dev,
            watchlist_items=ig_watchlist,
            today_str=today_str,
        )
        ig_ai_texts  = engine_result['ai_texts']
        interpretation = engine_result['assessment']

        # --- Index delta badge HTML ---
        def delta_badge(delta_str, color):
            return f'<span class="delta" style="color:{color}">{delta_str}</span>'

        geri_delta_badge  = delta_badge(geri_delta_str,  gc if geri_delta  != 0 else '#94a3b8')
        eeri_delta_badge  = delta_badge(eeri_delta_str,  ec if eeri_delta  != 0 else '#94a3b8')
        egsi_delta_badge  = delta_badge(egsi_delta_str,  mgc if egsi_delta != 0 else '#94a3b8')

        # --- Infographic section ---
        infographic_section = _build_infographic_html(
            today_str=today_str,
            geri_val=geri_val, geri_band=geri_band, geri_date=geri_date, geri_delta=geri_delta,
            eeri_val=eeri_val, eeri_band=eeri_band, eeri_delta=eeri_delta,
            egsi_val=egsi_val, egsi_band=egsi_band,
            brent_price=brent_price, brent_chg=brent_chg, brent_chg_pct=brent_chg_pct,
            ttf_price=ttf_price, ttf_chg=ttf_chg,
            storage_pct=storage_pct,
            ai_texts=ig_ai_texts,
            watchlist_items=ig_watchlist,
        )

        html = f"""<script>
(function(){{
  document.title='Global Energy Risk Snapshot \u2014 {today_str} | EnergyRiskIQ';
  var m;
  m=document.querySelector('meta[name="description"]');
  if(m)m.setAttribute('content','Live global energy risk snapshot for {today_str}. GERI {geri_val}/100 ({geri_band}), EERI {eeri_val}/100 ({eeri_band}), EGSI-M {egsi_val} ({egsi_band}). Brent ${{brent_price:.2f}}, TTF \u20ac{{ttf_price:.2f}}/MWh. Powered by EnergyRiskIQ.');
  m=document.querySelector('meta[property="og:title"]');
  if(m)m.setAttribute('content','Global Energy Risk Snapshot \u2014 {today_str}');
  m=document.querySelector('meta[property="og:description"]');
  if(m)m.setAttribute('content','GERI {geri_val}/100 ({geri_band}) | EERI {eeri_val}/100 ({eeri_band}) | Brent ${{brent_price:.2f}} | TTF \u20ac{{ttf_price:.2f}}/MWh');
  m=document.querySelector('meta[name="twitter:title"]');
  if(m)m.setAttribute('content','Global Energy Risk Snapshot \u2014 {today_str}');
  m=document.querySelector('meta[name="twitter:description"]');
  if(m)m.setAttribute('content','GERI {geri_val} ({geri_band}) | EERI {eeri_val} ({eeri_band}) | Brent ${{brent_price:.2f}} | TTF \u20ac{{ttf_price:.2f}}');
  var l=document.getElementById('snap-loader');
  if(l){{
    l.style.transition='opacity 0.65s ease, visibility 0.65s ease';
    l.style.opacity='0';
    l.style.visibility='hidden';
    setTimeout(function(){{if(l.parentNode)l.parentNode.removeChild(l);}},700);
  }}
  document.body.style.overflow='';
}})();
</script>

<nav class="nav">
  <div class="nav-inner">
    <a href="/" class="logo">
      <img src="/static/logo.png" alt="EnergyRiskIQ" width="36" height="36">
      EnergyRiskIQ
    </a>
    <a href="/users" class="cta-btn-nav">Get FREE Access</a>
  </div>
</nav>

<div class="hero">
  <div class="hero-date">&#128197; {today_str}</div>
  <h1>Global Energy Risk Snapshot</h1>
  <p class="hero-sub">Live risk indices, commodity prices and geopolitical watchlist — updated daily from the EnergyRiskIQ intelligence pipeline.</p>
</div>

<div class="page-body">

  <!-- ── INFOGRAPHIC ── -->
  <div class="section-label">Current Energy Risk Environment</div>
  {infographic_section}

  <!-- ── CITATION CARD ── -->
  <div class="snap-cite-card">
    <h3>Citation &amp; Reference</h3>
    <p class="snap-cite-desc">When referencing the Global Energy Risk Snapshot in research or publications, please use the following citation:</p>
    <div class="snap-cite-code-wrap">
      <div class="snap-cite-code">
        EnergyRiskIQ ({datetime.now().year}).<br>
        Global Energy Risk Snapshot &mdash; GERI, EERI, EGSI-M. {today_str}.<br>
        <a href="https://energyriskiq.com/data/energy-risk-snapshot">https://energyriskiq.com/data/energy-risk-snapshot</a>
      </div>
      <button class="snap-cite-copy-btn" onclick="(function(b){{
        navigator.clipboard.writeText('EnergyRiskIQ ({datetime.now().year}). Global Energy Risk Snapshot \u2014 GERI, EERI, EGSI-M. {today_str}. https://energyriskiq.com/data/energy-risk-snapshot').then(function(){{
          b.textContent='\u2713 Copied!'; b.style.color='#22c55e';
          setTimeout(function(){{b.textContent='Copy'; b.style.color='';}},2000);
        }});
      }})(this)">Copy</button>
    </div>
    <p class="snap-cite-footer">For BibTeX, APA, or other citation formats, see the full <a href="/research/global-energy-risk-index">Methodology section</a>.</p>
  </div>

  <!-- ── EU GAS STORAGE ── -->
  <div class="storage-row">
    <div class="storage-icon">&#9651;</div>
    <div>
      <div class="storage-label">EU Gas Storage</div>
      <div class="storage-value" style="color:{storage_color}">{storage_pct:.2f}% full</div>
      <div class="storage-note">Seasonal norm: <strong style="color:#94a3b8">{storage_norm:.1f}%</strong> &nbsp;&bull;&nbsp; Deviation: <strong style="color:{storage_color}">{'+' if storage_dev >= 0 else ''}{storage_dev:.1f}%</strong> &nbsp;&bull;&nbsp; Risk band: <strong style="color:{storage_color}">{storage_band}</strong></div>
    </div>
    <div class="storage-bar-wrap">
      <div style="font-size:10px;color:var(--muted);margin-bottom:5px;text-align:right">{storage_pct:.1f}% full &nbsp;|&nbsp; norm {storage_norm:.1f}%</div>
      <div class="storage-bar" style="position:relative">
        <div class="storage-bar-fill" style="width:{min(storage_pct, 100):.1f}%; background:{storage_color}"></div>
        <div style="position:absolute;top:0;bottom:0;left:{min(storage_norm, 100):.1f}%;width:2px;background:#64748b;opacity:0.8" title="Seasonal norm {storage_norm:.1f}%"></div>
      </div>
      <div style="font-size:10px;color:var(--muted);margin-top:4px;text-align:right">Seasonal norm {storage_norm:.1f}% &nbsp;&#9474;&nbsp; Current {storage_pct:.1f}%</div>
    </div>
  </div>

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
      <div class="price-source">Daily Close — {ttf_date_val}</div>
    </div>

    <!-- VIX -->
    <div class="price-card">
      <div class="price-commodity">VIX Volatility Index</div>
      <div class="price-value">{vix_close:.2f}</div>
      <div class="price-change" style="color:{vix_color}">{vix_arrow} {vix_chg_str}</div>
      <div class="price-source">CBOE — {vix_date_val}</div>
    </div>

    <!-- LNG -->
    <div class="price-card">
      <div class="price-commodity">LNG JKM (Asia)</div>
      <div class="price-value"><sup>$</sup>{lng_price:.2f}<span style="font-size:14px;font-weight:500;color:var(--muted)">/MMBtu</span></div>
      <div class="price-change" style="color:{lng_color}">{lng_arrow} {lng_chg_str}</div>
      <div class="price-source">Platts JKM — {lng_date_val}</div>
    </div>

  </div>

  <!-- ── INTERPRETATION BLOCK ── -->
  <div class="section-label">Risk Intelligence Interpretation</div>
  <div class="interp-block">
    <div class="interp-label">EnergyRiskIQ Daily Assessment</div>
    <p class="interp-text">{_html.escape(interpretation)}</p>
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

  <!-- ── CTA BUTTON ── -->
  <div style="text-align:center; padding:36px 0 24px;">
    <a href="/users" class="cta-btn-nav" style="font-size:15px; padding:14px 36px; border-radius:8px; display:inline-block; font-weight:700; letter-spacing:0.2px; box-shadow:0 4px 20px rgba(59,130,246,0.3);">Get FREE Access To Intelligence</a>
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
        return html

    except Exception as e:
        logger.error(f"Snapshot HTML build failed: {e}", exc_info=True)
        raise
