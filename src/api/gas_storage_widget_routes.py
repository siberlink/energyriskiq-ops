"""
Europe Gas Storage Widget — SEO landing page + embeddable iframe widget.

Routes:
  GET /widgets/europe-gas-storage-levels      → marketing landing page (SEO + funnel)
  GET /embed/europe-gas-storage-widget        → standalone iframe widget (free, branded)
  GET /embed/europe-gas-storage-widget-pro    → preview-only "pro" widget (visual demo)

Framed as a "Winter Readiness & Gas Risk Widget" per the free-widget blueprint.
Custom-algorithm wording (not "AI"). Fully mobile responsive.
Anti-copy text protection (does NOT block search engines).
"""
import logging
import asyncio
import html as _html
import json as _json
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter
from fastapi.responses import StreamingResponse, HTMLResponse

from src.db.db import execute_production_one, execute_production_query
from src.api.snapshot_routes import _PAGE_CSS, _LOADER_HTML, BAND_COLORS, _safe_float

router = APIRouter()
logger = logging.getLogger(__name__)

BASE_URL        = "https://energyriskiq.com"
WIDGET_PATH     = "/embed/europe-gas-storage-widget"
WIDGET_PATH_PRO = "/embed/europe-gas-storage-widget-pro"
LANDING_URL     = f"{BASE_URL}/widgets/europe-gas-storage-levels"
DATA_URL        = f"{BASE_URL}/gas-storage-levels-in-europe"
STORAGE_COLOR   = "#d4a017"

PRO_PRICE_EUR = "1.49"

EU_WINTER_TARGET = 90.0   # EU regulation storage target (% by Nov 1)

# Winter-readiness band colours
_GOOD_COLOR = "#22c55e"
_MOD_COLOR  = "#eab308"
_ELEV_COLOR = "#ef4444"

# Band severity scoring for risk composite
_BAND_LEVEL = {
    "LOW": 0, "MINIMAL": 0, "CALM": 0,
    "MODERATE": 1, "MEDIUM": 1, "NORMAL": 1, "BALANCED": 1,
    "ELEVATED": 2, "HIGH": 2,
    "SEVERE": 3, "CRITICAL": 3, "EXTREME": 3,
}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _flag(code):
    """Regional-indicator flag emoji from an ISO-2 country code."""
    code = (code or "").upper()[:2]
    if len(code) != 2 or not code.isalpha():
        return ""
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in code)


def _band_level(band):
    return _BAND_LEVEL.get(str(band or "").strip().upper(), 1)


# ─────────────────────────────────────────────────────────────────────────────
# Data
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_widget_data():
    """Lightweight fetch optimised for the gas-storage widget endpoint."""
    latest = execute_production_one(
        "SELECT date, eu_storage_percent, seasonal_norm, deviation_from_norm, "
        "refill_speed_7d, withdrawal_rate_7d, winter_deviation_risk, risk_score, risk_band "
        "FROM gas_storage_snapshots ORDER BY date DESC LIMIT 1"
    )

    # Storage value ~1 month ago for the trend line
    month_ago = None
    if latest and latest.get("date"):
        month_ago = execute_production_one(
            "SELECT eu_storage_percent FROM gas_storage_snapshots "
            "WHERE date <= %s ORDER BY date DESC LIMIT 1",
            (latest["date"] - timedelta(days=30),),
        )

    # 30-day history (for the Pro trend sparkline)
    storage_hist = execute_production_query(
        "SELECT date, eu_storage_percent FROM gas_storage_snapshots "
        "WHERE eu_storage_percent IS NOT NULL ORDER BY date DESC LIMIT 30"
    ) or []
    storage_hist = list(reversed(storage_hist))

    # Latest per-country snapshot
    countries = execute_production_query(
        "SELECT DISTINCT ON (country_code) "
        "country_code, country_name, storage_percent "
        "FROM gas_storage_country_snapshots "
        "WHERE level = 'country' AND storage_percent IS NOT NULL "
        "ORDER BY country_code, date DESC"
    ) or []

    eeri = execute_production_one(
        "SELECT value, band FROM reri_indices_daily "
        "WHERE index_id='europe:eeri' ORDER BY date DESC LIMIT 1"
    )
    egsi_m = execute_production_one(
        "SELECT index_value, band FROM egsi_m_daily "
        "WHERE region='Europe' ORDER BY index_date DESC LIMIT 1"
    )
    geri = execute_production_one(
        "SELECT value, band FROM geri_live ORDER BY id DESC LIMIT 1"
    )

    # Optional (Pro preview only) — guarded so a schema mismatch can't break the widget
    egsi_s = None
    try:
        egsi_s = execute_production_one(
            "SELECT index_value, band FROM egsi_s_daily "
            "ORDER BY index_date DESC LIMIT 1"
        )
    except Exception as exc:
        logger.warning(f"egsi_s fetch skipped: {exc}")

    return {
        "latest": latest,
        "month_ago": month_ago,
        "storage_hist": storage_hist,
        "countries": countries,
        "eeri": eeri,
        "egsi_m": egsi_m,
        "egsi_s": egsi_s,
        "geri": geri,
    }


def _compute_signals(data):
    """Deterministic Winter Readiness + Storage Risk + trend + insight."""
    latest = data.get("latest") or {}
    storage_pct = _safe_float(latest.get("eu_storage_percent"), 0.0)
    deviation   = _safe_float(latest.get("deviation_from_norm"), 0.0)
    seasonal    = _safe_float(latest.get("seasonal_norm"), 0.0)

    # ── Trend vs last month ──
    ma = data.get("month_ago") or {}
    prev_pct = _safe_float(ma.get("eu_storage_percent"), storage_pct)
    trend = storage_pct - prev_pct

    # ── Winter Readiness (0–100) ──
    # Blends absolute progress toward the 90% winter target with seasonal
    # positioning (how far above/below the seasonal norm we are).
    fill_score = _clamp(storage_pct / EU_WINTER_TARGET * 100.0, 0, 100)
    seasonal_score = _clamp(50.0 + deviation * 2.5, 0, 100)
    readiness = int(round(_clamp(0.6 * fill_score + 0.4 * seasonal_score, 0, 100)))
    if readiness >= 70:
        readiness_label, readiness_color = "GOOD", _GOOD_COLOR
    elif readiness >= 45:
        readiness_label, readiness_color = "MODERATE", _MOD_COLOR
    else:
        readiness_label, readiness_color = "ELEVATED", _ELEV_COLOR

    # ── Storage Risk signal (LOW / MOD / ELEVATED) ──
    # Composite of storage vs seasonal norm, absolute fill, EERI and EGSI-M.
    pts = 0
    if deviation <= -10:
        pts += 2
    elif deviation <= -3:
        pts += 1
    elif deviation >= 5:
        pts -= 1
    if storage_pct < 30:
        pts += 1
    eeri_lvl = _band_level((data.get("eeri") or {}).get("band"))
    egsi_lvl = _band_level((data.get("egsi_m") or {}).get("band"))
    if eeri_lvl >= 2:
        pts += 1
    if egsi_lvl >= 2:
        pts += 1
    if eeri_lvl >= 3 or egsi_lvl >= 3:
        pts += 1
    if pts <= 0:
        risk_label, risk_color = "LOW", _GOOD_COLOR
    elif pts <= 2:
        risk_label, risk_color = "MODERATE", _MOD_COLOR
    else:
        risk_label, risk_color = "ELEVATED", _ELEV_COLOR

    # ── Micro insight (one sentence, deterministic) ──
    if deviation >= 3:
        insight = ("Storage sits above seasonal norms, easing near-term "
                   "winter supply risk.")
    elif deviation <= -3:
        insight = ("Storage is tracking below seasonal norms, lifting "
                   "near-term winter supply risk.")
    else:
        insight = ("Storage is tracking close to seasonal norms, keeping "
                   "near-term winter supply risk balanced.")

    # ── Top 3 countries by fill ──
    cs = []
    for c in (data.get("countries") or []):
        p = _safe_float(c.get("storage_percent"), None) if c.get("storage_percent") is not None else None
        if p is None:
            continue
        cs.append((c.get("country_code") or "", c.get("country_name") or "", p))
    cs.sort(key=lambda x: x[2], reverse=True)
    top3 = cs[:3]

    return {
        "storage_pct": storage_pct,
        "seasonal": seasonal,
        "deviation": deviation,
        "trend": trend,
        "readiness": readiness,
        "readiness_label": readiness_label,
        "readiness_color": readiness_color,
        "risk_label": risk_label,
        "risk_color": risk_color,
        "insight": insight,
        "top3": top3,
        "all_countries": cs,
        "date": latest.get("date"),
    }


def _build_trend_sparkline(rows, color=STORAGE_COLOR, height=70, width=320):
    """Compact sparkline for the Pro storage-trend chart."""
    vals = [float(r["eu_storage_percent"]) for r in (rows or [])
            if r.get("eu_storage_percent") is not None]
    if len(vals) < 2:
        return (
            f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
            f'style="width:100%;height:auto;display:block;">'
            f'<text x="{width/2}" y="{height/2+4}" text-anchor="middle" font-size="11" '
            f'fill="#64748b" font-family="Inter,system-ui,sans-serif">Awaiting storage history</text>'
            f'</svg>'
        )
    PAD_L, PAD_R, PAD_T, PAD_B = 8, 8, 6, 6
    cw = width - PAD_L - PAD_R
    ch = height - PAD_T - PAD_B
    vmin, vmax = min(vals), max(vals)
    if vmin == vmax:
        vmax = vmin * 1.001 + 0.0001
    rng = vmax - vmin
    n = len(vals)
    pts = []
    for i, v in enumerate(vals):
        x = PAD_L + (i / max(n - 1, 1)) * cw
        y = PAD_T + ch - ((v - vmin) / rng) * ch
        pts.append((x, y))
    path_d = "M " + " L ".join(f"{p[0]:.1f} {p[1]:.1f}" for p in pts)
    area_d = path_d + f" L {pts[-1][0]:.1f} {PAD_T+ch:.1f} L {pts[0][0]:.1f} {PAD_T+ch:.1f} Z"
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
# /embed/europe-gas-storage-widget  — the actual iframe widget
# ─────────────────────────────────────────────────────────────────────────────

def _render_widget_html(data, *, pro=False):
    s = _compute_signals(data)
    storage_pct = s["storage_pct"]
    trend = s["trend"]
    ts_str = s["date"].isoformat() if s.get("date") else ""

    trend_color = "#22c55e" if trend > 0 else "#ef4444" if trend < 0 else "#94a3b8"
    trend_arrow = "&#9650;" if trend > 0 else "&#9660;" if trend < 0 else "&#9644;"

    # Top countries rows
    country_rows = ""
    for code, name, pct in s["top3"]:
        country_rows += (
            f'<div class="erq-ctry-row">'
            f'<span class="erq-ctry-name">{_flag(code)} {_html.escape(code)}</span>'
            f'<span class="erq-ctry-val">{pct:.0f}%</span>'
            f'</div>'
        )
    if not country_rows:
        country_rows = '<div class="erq-ctry-row"><span class="erq-ctry-name">Awaiting country data</span></div>'

    # Pro-only extras
    if pro:
        spark = _build_trend_sparkline(data.get("storage_hist") or [])
        egsi_m = data.get("egsi_m") or {}
        egsi_s = data.get("egsi_s") or {}
        egsi_m_val = int(round(_safe_float(egsi_m.get("index_value"), 0)))
        egsi_s_val = int(round(_safe_float(egsi_s.get("index_value"), 0))) if egsi_s else None
        # extra countries (4th & 5th)
        extra_rows = ""
        for code, name, pct in s["all_countries"][3:5]:
            extra_rows += (
                f'<div class="erq-ctry-row">'
                f'<span class="erq-ctry-name">{_flag(code)} {_html.escape(code)}</span>'
                f'<span class="erq-ctry-val">{pct:.0f}%</span>'
                f'</div>'
            )
    else:
        spark = ""
        egsi_m_val = egsi_s_val = None
        extra_rows = ""

    # Pro styling vs Free styling
    if pro:
        bg = "transparent"
        card_bg = "linear-gradient(135deg,#020617 0%,#0a0f1d 50%,#0d1525 100%)"
        border = f"1px solid {STORAGE_COLOR}59"
        brand_block = ""
        cite_block = ""
        accent = STORAGE_COLOR
    else:
        bg = "#0b0f1a"
        card_bg = "linear-gradient(135deg,#0c1322 0%,#15110a 50%,#0c1322 100%)"
        border = f"1px solid {STORAGE_COLOR}38"
        brand_block = (
            f'<a href="{DATA_URL}" target="_blank" rel="noopener" class="erq-brand">'
            f'<span class="erq-brand-dot"></span>Powered by EnergyRiskIQ'
            f'</a>'
        )
        cite_block = (
            f'<a href="{DATA_URL}" target="_blank" rel="noopener" class="erq-cite">'
            f'View Full Storage Analysis &rarr;</a>'
        )
        accent = STORAGE_COLOR

    label_pro = '<span class="erq-pro-tag">PRO</span>' if pro else ''

    pro_block = ""
    if pro:
        egsi_s_html = (f'<span class="erq-idx"><b>EGSI&#8209;S</b> {egsi_s_val}</span>'
                       if egsi_s_val is not None else '')
        pro_block = f"""
  <div class="erq-pro-panel">
    <div class="erq-pro-label">30-Day Storage Trend</div>
    <div class="erq-spark">{spark}</div>
    <div class="erq-idx-row">
      <span class="erq-idx"><b>EGSI&#8209;M</b> {egsi_m_val}</span>
      {egsi_s_html}
    </div>
    {('<div class="erq-ctry-extra">' + extra_rows + '</div>') if extra_rows else ''}
  </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,follow">
<title>Europe Gas Storage Widget &middot; EnergyRiskIQ</title>
<style>
  *{{box-sizing:border-box;}}
  html,body{{margin:0;padding:0;background:{bg};font-family:Inter,system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:#e2e8f0;-webkit-font-smoothing:antialiased;}}
  .erq-widget{{
    width:100%; max-width:400px; margin:0 auto;
    background:{card_bg};
    border:{border}; border-radius:14px;
    padding:15px 17px 13px;
    position:relative; overflow:hidden;
    user-select:none; -webkit-user-select:none;
  }}
  .erq-widget::before{{
    content:''; position:absolute; top:0; left:0; right:0; height:2px;
    background:linear-gradient(90deg,{accent},rgba(212,160,23,0.12));
  }}
  .erq-head{{display:flex; align-items:flex-start; justify-content:space-between; gap:8px; margin-bottom:6px;}}
  .erq-title{{font-size:12px; font-weight:800; color:#f1f5f9; letter-spacing:0.4px;}}
  .erq-sub{{font-size:9.5px; font-weight:700; letter-spacing:1.2px; text-transform:uppercase; color:#64748b;}}
  .erq-sub-dot{{display:inline-block; width:6px; height:6px; border-radius:50%; background:{accent}; box-shadow:0 0 6px {accent}; margin-right:5px; vertical-align:middle;}}
  .erq-unit{{font-size:9.5px; font-weight:700; letter-spacing:1px; text-transform:uppercase; color:{accent}; text-align:right;}}
  .erq-metric{{text-align:center; margin:6px 0 4px;}}
  .erq-pct{{font-size:40px; font-weight:800; color:#fff; line-height:1; font-variant-numeric:tabular-nums;}}
  .erq-pct sup{{font-size:18px; font-weight:700; vertical-align:top; margin-left:2px;}}
  .erq-metric-label{{font-size:11px; color:#94a3b8; margin-top:3px; letter-spacing:0.3px;}}
  .erq-trend{{text-align:center; font-size:12.5px; font-weight:700; color:{trend_color}; margin:2px 0 10px; font-variant-numeric:tabular-nums;}}
  .erq-signals{{display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-bottom:10px;}}
  .erq-sig{{background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.06); border-radius:10px; padding:8px 10px;}}
  .erq-sig-label{{font-size:8.5px; font-weight:800; letter-spacing:1px; text-transform:uppercase; color:#64748b; margin-bottom:3px;}}
  .erq-sig-val{{font-size:14px; font-weight:800; letter-spacing:0.3px;}}
  .erq-sig-sub{{font-size:10px; color:#94a3b8; font-weight:700; margin-top:1px;}}
  .erq-ctry{{border-top:1px dashed rgba(255,255,255,0.08); padding-top:9px; margin-bottom:9px;}}
  .erq-ctry-head{{font-size:9px; font-weight:800; letter-spacing:1.1px; text-transform:uppercase; color:#64748b; margin-bottom:6px;}}
  .erq-ctry-row{{display:flex; justify-content:space-between; align-items:center; font-size:12px; padding:2px 0;}}
  .erq-ctry-name{{color:#cbd5e1; font-weight:600;}}
  .erq-ctry-val{{color:#fff; font-weight:800; font-variant-numeric:tabular-nums;}}
  .erq-insight{{font-size:11px; color:#94a3b8; line-height:1.55; background:rgba(212,160,23,0.05); border-left:2px solid {accent}; padding:7px 10px; border-radius:0 6px 6px 0; margin-bottom:10px;}}
  .erq-pro-panel{{border-top:1px dashed rgba(255,255,255,0.08); padding-top:9px; margin-bottom:9px;}}
  .erq-pro-label{{font-size:9px; font-weight:800; letter-spacing:1.1px; text-transform:uppercase; color:#94a3b8; margin-bottom:4px;}}
  .erq-spark{{margin-bottom:6px;}}
  .erq-idx-row{{display:flex; gap:14px; font-size:11px; color:#94a3b8;}}
  .erq-idx b{{color:#cbd5e1; font-weight:700;}}
  .erq-ctry-extra{{margin-top:6px;}}
  .erq-cite{{display:block; text-align:center; margin-top:2px; font-size:11.5px; font-weight:800; color:{accent}; text-decoration:none; padding:9px 0; letter-spacing:0.3px; background:rgba(212,160,23,0.08); border-radius:9px;}}
  .erq-cite:hover{{background:rgba(212,160,23,0.16); color:#fff;}}
  .erq-brand{{display:block; text-align:center; margin-top:7px; font-size:9.5px; color:#475569; text-decoration:none; letter-spacing:0.5px;}}
  .erq-brand-dot{{display:inline-block; width:5px; height:5px; border-radius:50%; background:{accent}; margin-right:5px; vertical-align:middle;}}
  .erq-brand:hover{{color:#94a3b8;}}
  .erq-pro-tag{{font-size:9px; font-weight:800; letter-spacing:1px; background:linear-gradient(135deg,{STORAGE_COLOR},#f59e0b); color:#0a0f1e; padding:2px 8px; border-radius:10px;}}
  @media (max-width:340px){{.erq-pct{{font-size:32px;}} .erq-widget{{padding:12px 13px;}}}}
</style>
</head>
<body>
<div class="erq-widget" role="region" aria-label="Europe Gas Storage Widget by EnergyRiskIQ">
  <div class="erq-head">
    <div>
      <div class="erq-title">Europe Gas Storage &middot; Today {label_pro}</div>
      <div class="erq-sub"><span class="erq-sub-dot"></span>Updated Daily</div>
    </div>
    <div class="erq-unit">% Full</div>
  </div>

  <div class="erq-metric">
    <div class="erq-pct">{storage_pct:.1f}<sup>%</sup></div>
    <div class="erq-metric-label">EU Storage Filled</div>
  </div>
  <div class="erq-trend">{trend_arrow} {trend:+.1f}% vs Last Month</div>

  <div class="erq-signals">
    <div class="erq-sig">
      <div class="erq-sig-label">Winter Readiness</div>
      <div class="erq-sig-val" style="color:{s['readiness_color']};">{s['readiness_label']}</div>
      <div class="erq-sig-sub">{s['readiness']} / 100</div>
    </div>
    <div class="erq-sig">
      <div class="erq-sig-label">Storage Risk</div>
      <div class="erq-sig-val" style="color:{s['risk_color']};">{s['risk_label']}</div>
      <div class="erq-sig-sub">Composite signal</div>
    </div>
  </div>

  <div class="erq-ctry">
    <div class="erq-ctry-head">Top Storage Countries</div>
    {country_rows}
  </div>

  <div class="erq-insight">{_html.escape(s['insight'])}</div>
{pro_block}
  {cite_block}
  {brand_block}
</div>
<script>
  document.addEventListener('contextmenu',function(e){{e.preventDefault();}});
</script>
</body>
</html>"""


def _empty_data():
    return {
        "latest": None, "month_ago": None, "storage_hist": [], "countries": [],
        "eeri": None, "egsi_m": None, "egsi_s": None, "geri": None,
    }


@router.get("/embed/europe-gas-storage-widget")
async def gas_storage_widget_embed():
    try:
        data = await asyncio.to_thread(_fetch_widget_data)
    except Exception as exc:
        logger.error(f"Gas storage widget data fetch failed: {exc}", exc_info=True)
        data = _empty_data()
    html = _render_widget_html(data, pro=False)
    return HTMLResponse(
        content=html,
        headers={
            "Cache-Control": "public, max-age=120",
            "Content-Security-Policy": "frame-ancestors *;",
        },
    )


@router.get("/embed/europe-gas-storage-widget-pro")
async def gas_storage_widget_embed_pro():
    try:
        data = await asyncio.to_thread(_fetch_widget_data)
    except Exception as exc:
        logger.error(f"Gas storage widget data fetch failed: {exc}", exc_info=True)
        data = _empty_data()
    html = _render_widget_html(data, pro=True)
    return HTMLResponse(
        content=html,
        headers={
            "Cache-Control": "public, max-age=120",
            "Content-Security-Policy": "frame-ancestors *;",
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# /widgets/europe-gas-storage-levels — SEO landing page + funnel
# ─────────────────────────────────────────────────────────────────────────────

_LANDING_CSS = f"""
.gs-w-protected {{ user-select:none; -webkit-user-select:none; }}

/* Hero */
.gs-w-hero{{
  text-align:center; padding:60px 20px 40px;
  background:linear-gradient(180deg,#0b0f1a 0%,#0e1422 100%);
}}
.gs-w-hero h1{{
  font-family:'DM Serif Display',Georgia,serif;
  font-size:clamp(32px,5vw,52px); line-height:1.15;
  margin:0 0 18px; color:#fff;
}}
.gs-w-hero h1 span{{color:{STORAGE_COLOR};}}
.gs-w-hero p{{
  font-size:clamp(14px,1.6vw,17px); color:#94a3b8;
  max-width:680px; margin:0 auto 26px; line-height:1.65;
}}
.gs-w-cta-row{{display:flex; gap:12px; justify-content:center; flex-wrap:wrap; margin-bottom:24px;}}
.gs-w-cta-primary{{
  background:linear-gradient(135deg,{STORAGE_COLOR},#f59e0b); color:#0a0f1e !important;
  text-decoration:none; font-weight:700; font-size:14.5px;
  padding:13px 26px; border-radius:10px;
  box-shadow:0 6px 24px rgba(212,160,23,0.18);
}}
.gs-w-cta-secondary{{
  background:transparent; color:#cbd5e1 !important;
  border:1px solid rgba(255,255,255,0.18);
  text-decoration:none; font-weight:600; font-size:14px;
  padding:13px 26px; border-radius:10px;
}}
.gs-w-cta-secondary:hover{{border-color:rgba(212,160,23,0.5); color:#fff !important;}}

/* Trust micro-bar */
.gs-w-trust{{
  display:flex; gap:18px; justify-content:center; flex-wrap:wrap;
  font-size:11.5px; color:#94a3b8; max-width:880px; margin:0 auto;
}}
.gs-w-trust span{{display:inline-flex; align-items:center; gap:6px;}}
.gs-w-trust span::before{{content:'\u2713'; color:#22c55e; font-weight:800;}}

/* Section common */
.gs-w-section{{padding:48px 22px; max-width:1100px; margin:0 auto;}}
.gs-w-section h2{{
  font-family:'DM Serif Display',Georgia,serif;
  font-size:clamp(24px,3.5vw,34px); color:#fff; text-align:center; margin:0 0 14px;
}}
.gs-w-section h2 + p{{
  text-align:center; color:#94a3b8; max-width:660px; margin:0 auto 32px;
  font-size:14px; line-height:1.65;
}}

/* Widget preview frame */
.gs-w-preview-wrap{{display:flex; gap:24px; justify-content:center; align-items:flex-start; flex-wrap:wrap;}}
.gs-w-preview-col{{
  flex:1 1 360px; max-width:440px;
  background:#0e1422; border:1px solid var(--border);
  border-radius:16px; padding:22px;
}}
.gs-w-preview-col h3{{font-size:13px; font-weight:800; color:#cbd5e1; margin:0 0 14px; letter-spacing:0.5px; text-align:center;}}
.gs-w-iframe-shell{{background:linear-gradient(135deg,#020617,#0a0f1d); border-radius:12px; padding:14px;}}
.gs-w-preview-note{{font-size:11px; color:#64748b; margin-top:12px; text-align:center;}}
.gs-w-preview-pro{{position:relative; background:linear-gradient(135deg,{STORAGE_COLOR} 0%,#f59e0b 100%); padding:1px; border-radius:17px;}}
.gs-w-preview-pro .gs-w-preview-col{{margin:0; border:none;}}

/* Embed code box */
.gs-w-embed-box{{
  background:#020617; border:1px solid rgba(212,160,23,0.25);
  border-radius:12px; padding:0; max-width:780px; margin:0 auto 14px; overflow:hidden;
}}
.gs-w-embed-head{{
  display:flex; justify-content:space-between; align-items:center;
  padding:10px 16px; border-bottom:1px solid rgba(255,255,255,0.06);
  font-size:11px; font-weight:700; color:#64748b; letter-spacing:1px; text-transform:uppercase;
}}
.gs-w-embed-copy{{
  background:rgba(212,160,23,0.15); color:{STORAGE_COLOR};
  border:1px solid rgba(212,160,23,0.35); border-radius:6px;
  font-size:11px; font-weight:700; padding:5px 14px; cursor:pointer; letter-spacing:0.3px;
}}
.gs-w-embed-copy:hover{{background:rgba(212,160,23,0.25);}}
.gs-w-embed-code{{
  font-family:'JetBrains Mono',ui-monospace,monospace;
  font-size:12.5px; color:#94a3b8; line-height:1.7;
  padding:16px 18px; margin:0; white-space:pre-wrap; word-break:break-word; overflow-x:auto;
}}
.gs-w-embed-code .tk{{color:{STORAGE_COLOR};}}
.gs-w-embed-micro{{text-align:center; font-size:11.5px; color:#64748b; max-width:680px; margin:0 auto;}}

/* Why cards */
.gs-w-why-grid{{display:grid; grid-template-columns:repeat(4,1fr); gap:14px;}}
@media (max-width:920px){{.gs-w-why-grid{{grid-template-columns:1fr 1fr;}}}}
@media (max-width:500px){{.gs-w-why-grid{{grid-template-columns:1fr;}}}}
.gs-w-why-card{{background:var(--card); border:1px solid var(--border); border-radius:14px; padding:20px;}}
.gs-w-why-icon{{font-size:1.7rem; margin-bottom:8px;}}
.gs-w-why-title{{font-size:14px; font-weight:800; color:#f1f5f9; margin-bottom:6px;}}
.gs-w-why-body{{font-size:12.5px; color:#94a3b8; line-height:1.6;}}

/* Comparison table */
.gs-w-compare-wrap{{overflow-x:auto;}}
.gs-w-compare{{
  width:100%; border-collapse:collapse; min-width:520px;
  background:var(--card); border:1px solid var(--border); border-radius:14px; overflow:hidden;
}}
.gs-w-compare th, .gs-w-compare td{{padding:12px 16px; text-align:center; font-size:13px; border-bottom:1px solid rgba(255,255,255,0.04);}}
.gs-w-compare th{{background:rgba(255,255,255,0.02); font-size:11px; font-weight:800; letter-spacing:1.2px; text-transform:uppercase; color:#64748b;}}
.gs-w-compare th.col-pro{{color:{STORAGE_COLOR};}}
.gs-w-compare td:first-child{{text-align:left; color:#cbd5e1; font-weight:600;}}
.gs-w-compare tr:last-child td{{border-bottom:none;}}
.tick{{color:#22c55e; font-weight:800;}}
.cross{{color:#475569;}}

/* Use cases */
.gs-w-uses-grid{{display:grid; grid-template-columns:repeat(3,1fr); gap:12px;}}
@media (max-width:780px){{.gs-w-uses-grid{{grid-template-columns:1fr 1fr;}}}}
@media (max-width:460px){{.gs-w-uses-grid{{grid-template-columns:1fr;}}}}
.gs-w-use-card{{
  background:var(--card); border:1px solid var(--border); border-radius:12px; padding:16px 18px;
  display:flex; align-items:center; gap:10px; font-size:13px; color:#cbd5e1; font-weight:600;
}}
.gs-w-use-card::before{{content:'\u2713'; color:#22c55e; font-weight:800;}}

/* SEO content */
.gs-w-seo-block{{background:var(--card); border:1px solid var(--border); border-radius:14px; padding:26px 28px;}}
.gs-w-seo-block h3{{font-size:16px; font-weight:700; color:#f1f5f9; margin:18px 0 8px;}}
.gs-w-seo-block h3:first-child{{margin-top:0;}}
.gs-w-seo-block p{{font-size:13.5px; color:#94a3b8; line-height:1.75; margin:0 0 10px;}}
.gs-w-seo-block a{{color:{STORAGE_COLOR}; text-decoration:none; font-weight:700;}}
.gs-w-seo-block a:hover{{text-decoration:underline;}}

/* Cross-link hub */
.gs-w-links-grid{{display:grid; grid-template-columns:repeat(3,1fr); gap:12px;}}
@media (max-width:780px){{.gs-w-links-grid{{grid-template-columns:1fr 1fr;}}}}
@media (max-width:460px){{.gs-w-links-grid{{grid-template-columns:1fr;}}}}
.gs-w-link-card{{
  background:var(--card); border:1px solid var(--border); border-radius:12px; padding:16px 18px;
  text-decoration:none; display:block; transition:border-color .15s;
}}
.gs-w-link-card:hover{{border-color:rgba(212,160,23,0.45);}}
.gs-w-link-title{{font-size:13.5px; font-weight:800; color:#f1f5f9; margin-bottom:4px;}}
.gs-w-link-desc{{font-size:11.5px; color:#94a3b8; line-height:1.5;}}

/* FAQ */
.gs-w-faq details{{background:var(--card); border:1px solid var(--border); border-radius:10px; margin-bottom:10px; overflow:hidden;}}
.gs-w-faq summary{{list-style:none; cursor:pointer; padding:16px 50px 16px 20px; font-size:14px; font-weight:700; color:#f1f5f9; position:relative;}}
.gs-w-faq summary::-webkit-details-marker{{display:none;}}
.gs-w-faq summary::after{{content:'+'; position:absolute; right:18px; top:50%; transform:translateY(-50%); font-size:22px; color:{STORAGE_COLOR};}}
.gs-w-faq details[open] summary::after{{content:'\u2212';}}
.gs-w-faq details > div{{padding:0 20px 18px; font-size:13.5px; color:#94a3b8; line-height:1.7;}}

/* Conversion */
.gs-w-conv{{
  background:linear-gradient(135deg,#0c1322 0%,#1c1608 50%,#0f172a 100%);
  border:1px solid rgba(212,160,23,0.3); border-radius:18px; padding:38px 28px; text-align:center;
  max-width:780px; margin:0 auto;
}}
.gs-w-conv h2{{font-family:'DM Serif Display',serif; font-size:clamp(22px,3.5vw,30px); color:#fff; margin:0 0 12px;}}
.gs-w-conv p{{color:#94a3b8; max-width:560px; margin:0 auto 22px; font-size:14px;}}

/* Cite */
.gs-w-cite-card{{background:var(--card); border:1px solid var(--border); border-radius:14px; padding:24px 26px; max-width:880px; margin:0 auto 40px; position:relative;}}
.gs-w-cite-card h3{{font-size:16px; color:#f1f5f9; margin-bottom:6px;}}
.gs-w-cite-card .gs-w-cite-desc{{font-size:13px; color:#94a3b8; margin-bottom:14px;}}
.gs-w-cite-code-wrap{{background:rgba(0,0,0,0.25); border-radius:10px; padding:16px 18px; position:relative;}}
.gs-w-cite-code{{font-family:'JetBrains Mono',ui-monospace,monospace; font-size:12px; color:#cbd5e1; line-height:1.7; margin:0; white-space:pre-wrap; word-break:break-word;}}
.gs-w-cite-code a{{color:{STORAGE_COLOR}; text-decoration:none;}}
.gs-w-cite-btn{{position:absolute; top:12px; right:12px; background:rgba(212,160,23,0.15); color:{STORAGE_COLOR}; border:1px solid rgba(212,160,23,0.35); border-radius:6px; font-size:11px; font-weight:700; padding:5px 12px; cursor:pointer;}}
@media (max-width:560px){{.gs-w-cite-btn{{position:static; display:block; width:100%; margin-top:12px;}}}}

/* Footer license */
.gs-w-license{{
  max-width:880px; margin:0 auto 30px;
  background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.06);
  border-radius:10px; padding:18px 20px; font-size:12px; color:#94a3b8;
}}
.gs-w-license a{{color:{STORAGE_COLOR}; text-decoration:none; font-weight:700;}}
"""


def _build_landing_html(today_str):
    embed_code = (
        '&lt;<span class="tk">iframe</span>\n'
        f'  src=&quot;{BASE_URL}{WIDGET_PATH}&quot;\n'
        '  width=&quot;100%&quot;\n'
        '  height=&quot;420&quot;\n'
        '  frameborder=&quot;0&quot;\n'
        '  loading=&quot;lazy&quot;&gt;\n'
        '&lt;/<span class="tk">iframe</span>&gt;'
    )
    embed_code_plain = (
        f'<iframe src="{BASE_URL}{WIDGET_PATH}" '
        'width="100%" height="420" frameborder="0" loading="lazy"></iframe>'
    )

    faqs = [
        ("How do I embed the Europe gas storage widget?",
         "Copy the iframe code from the embed section above and paste it into your website&rsquo;s HTML, "
         "blog editor, dashboard, or CMS. The widget loads instantly and is fully responsive on mobile."),
        ("What is the Winter Readiness score?",
         "Winter Readiness is a 0&ndash;100 score computed by Custom Algorithms that blends Europe&rsquo;s "
         "absolute gas storage fill against the EU&rsquo;s 90% winter target with how far storage sits above "
         "or below the seasonal norm. It is colour-coded GOOD, MODERATE or ELEVATED for instant reading."),
        ("How often is the storage data updated?",
         "The widget pulls EU gas storage levels from EnergyRiskIQ&rsquo;s production pipeline, sourced daily "
         "from AGSI+ / GIE. Storage percentage, country data and risk signals refresh every day."),
        ("Is the widget free?",
         "Yes &mdash; the standard Europe gas storage widget is free for personal and commercial use, provided "
         "the EnergyRiskIQ attribution remains visible. For an unbranded, white-label version, the Pro widget "
         f"is available from &euro;{PRO_PRICE_EUR}/month."),
        ("Can I use the widget commercially?",
         "Yes &mdash; commercial use is permitted on the free widget under the EnergyRiskIQ data licence "
         "(CC BY-NC 4.0), so long as EnergyRiskIQ attribution is preserved and visible."),
        ("Can I remove EnergyRiskIQ branding?",
         "Branding removal is only available on the Pro widget. The free widget requires the EnergyRiskIQ "
         "attribution link to remain visible &mdash; this funds the data pipeline that keeps the widget free."),
    ]
    faq_html = ''
    for q, a in faqs:
        faq_html += (
            f'<details><summary>{q}</summary>'
            f'<div>{a}</div></details>'
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
        "name": "Free Europe Gas Storage Levels Widget for Websites",
        "url": LANDING_URL,
        "description": "Embed a live Europe gas storage levels widget on your website with daily updates, winter readiness score and gas market risk signals.",
        "isAccessibleForFree": True,
        "publisher": {"@type": "Organization", "name": "EnergyRiskIQ", "url": BASE_URL},
        "license": f"{BASE_URL}/data-license",
    })

    sw_schema = _json.dumps({
        "@context": "https://schema.org",
        "@type": "SoftwareApplication",
        "name": "EnergyRiskIQ Europe Gas Storage Widget",
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
             "item": f"{BASE_URL}/widgets/europe-gas-storage-levels"},
            {"@type": "ListItem", "position": 3, "name": "Europe Gas Storage Widget", "item": LANDING_URL},
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
      var attr = '\\n\\n[Source: EnergyRiskIQ.com — Europe Gas Storage Widget | CC BY-NC 4.0]';
      e.clipboardData.setData('text/plain', sel + attr);
      e.preventDefault();
    }}
  }});
  document.addEventListener('contextmenu', function(e) {{
    var t = e.target;
    if (t && (t.classList && t.classList.contains('gs-w-protected') || (t.closest && t.closest('.gs-w-protected')))) {{
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
      <a href="/gas-storage-levels-in-europe" style="font-size:13px;color:#94a3b8;text-decoration:none;">Storage</a>
      <a href="/data/ttf-gas-price-today" style="font-size:13px;color:#94a3b8;text-decoration:none;">TTF</a>
      <a href="/indices/europe-gas-stress-index" style="font-size:13px;color:#94a3b8;text-decoration:none;">EGSI</a>
      <a href="/users" class="cta-btn-nav">Get Free Access</a>
    </div>
  </div>
</nav>

<!-- ── 1. HERO ───────────────────────────────────────────────────── -->
<header class="gs-w-hero">
  <h1>Free <span>Europe Gas Storage Widget</span><br>for Websites</h1>
  <p>
    Embed a live Europe gas storage levels widget on your website, app, dashboard, or energy blog.
    Track EU storage %, winter readiness, country storage data and gas market risk signals &mdash;
    updated daily and powered by Custom Algorithms.
  </p>
  <div class="gs-w-cta-row">
    <a href="#embed" class="gs-w-cta-primary">Get Free Widget Code &darr;</a>
    <a href="#pro" class="gs-w-cta-secondary">Unlock Pro Widget (&euro;{PRO_PRICE_EUR}/mo)</a>
  </div>
  <div class="gs-w-trust">
    <span>Daily AGSI+ updates</span>
    <span>Winter readiness score</span>
    <span>Free commercial use</span>
    <span>Mobile responsive</span>
    <span>Gas risk signals</span>
  </div>
</header>

<!-- ── 2. LIVE WIDGET PREVIEW ────────────────────────────────────── -->
<section class="gs-w-section" id="preview">
  <h2>Live Gas Storage Widget Preview</h2>
  <p>Real-time render of the free embeddable widget. This is exactly what your visitors will see.</p>
  <div class="gs-w-preview-wrap">
    <div class="gs-w-preview-col">
      <h3>FREE WIDGET &middot; LIVE RENDER</h3>
      <div class="gs-w-iframe-shell">
        <iframe src="{WIDGET_PATH}" width="100%" height="440" frameborder="0"
                style="border:0;display:block;border-radius:10px;background:transparent;"
                loading="lazy" title="Europe Gas Storage Widget"></iframe>
      </div>
      <div class="gs-w-preview-note">Branded &middot; required attribution &middot; CC BY-NC 4.0</div>
    </div>
  </div>
</section>

<!-- ── 3. EMBED SECTION ──────────────────────────────────────────── -->
<section class="gs-w-section" id="embed">
  <h2>Copy &amp; Paste This Widget Into Your Site</h2>
  <p>One-line iframe embed. Works in any HTML page, blog editor, CMS, or dashboard.</p>
  <div class="gs-w-embed-box">
    <div class="gs-w-embed-head">
      <span>HTML &middot; iframe embed</span>
      <button class="gs-w-embed-copy" id="copyEmbedBtn">Copy Code</button>
    </div>
    <pre class="gs-w-embed-code" id="embedCode">{embed_code}</pre>
  </div>
  <p class="gs-w-embed-micro">Free to use with EnergyRiskIQ attribution &middot; loads in &lt;200ms &middot; mobile-responsive.</p>
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
<section class="gs-w-section">
  <h2>Why Publishers &amp; Analysts Use This Storage Widget</h2>
  <div class="gs-w-why-grid">
    <div class="gs-w-why-card">
      <div class="gs-w-why-icon">&#127777;&#65039;</div>
      <div class="gs-w-why-title">Winter Readiness Signal</div>
      <div class="gs-w-why-body">A single colour-coded score visitors actually remember &mdash; far more memorable than a raw storage percentage.</div>
    </div>
    <div class="gs-w-why-card">
      <div class="gs-w-why-icon">&#128205;</div>
      <div class="gs-w-why-title">Country Storage Data</div>
      <div class="gs-w-why-body">Top EU storage countries at a glance, drawn from per-country AGSI+ data across the continent.</div>
    </div>
    <div class="gs-w-why-card">
      <div class="gs-w-why-icon">&#9889;</div>
      <div class="gs-w-why-title">Fast Lightweight Embed</div>
      <div class="gs-w-why-body">Optimised for blogs, dashboards and energy apps &mdash; under 200ms render, zero JS dependencies.</div>
    </div>
    <div class="gs-w-why-card">
      <div class="gs-w-why-icon">&#128241;</div>
      <div class="gs-w-why-title">Mobile Responsive</div>
      <div class="gs-w-why-body">Adapts cleanly to desktop, tablet and mobile &mdash; renders perfectly inside any iframe container.</div>
    </div>
  </div>
</section>

<!-- ── 5. FREE VS PRO COMPARISON ─────────────────────────────────── -->
<section class="gs-w-section" id="compare">
  <h2>Free vs Professional Widget</h2>
  <p>Both widgets carry the same live storage data &mdash; Pro removes branding and unlocks customisation.</p>
  <div class="gs-w-compare-wrap">
    <table class="gs-w-compare">
      <thead>
        <tr>
          <th style="text-align:left;">Feature</th>
          <th>Free Widget</th>
          <th class="col-pro">Pro Widget (&euro;{PRO_PRICE_EUR}/mo)</th>
        </tr>
      </thead>
      <tbody>
        <tr><td>EU Storage %</td><td><span class="tick">&#10003;</span></td><td><span class="tick">&#10003;</span></td></tr>
        <tr><td>Winter Readiness Score</td><td><span class="tick">&#10003;</span></td><td><span class="tick">&#10003;</span></td></tr>
        <tr><td>Top 3 Country Storage</td><td><span class="tick">&#10003;</span></td><td><span class="tick">&#10003;</span></td></tr>
        <tr><td>30-Day Storage Trend Chart</td><td><span class="cross">&#10005;</span></td><td><span class="tick">&#10003;</span></td></tr>
        <tr><td>EGSI-M &amp; EGSI-S Stress Index</td><td><span class="cross">&#10005;</span></td><td><span class="tick">&#10003;</span></td></tr>
        <tr><td>Extended Country Breakdown</td><td><span class="cross">&#10005;</span></td><td><span class="tick">&#10003;</span></td></tr>
        <tr><td>EnergyRiskIQ Branding</td><td>Required</td><td><span class="cross">Removed</span></td></tr>
        <tr><td>Citation Required</td><td>Required</td><td><span class="cross">Not Required</span></td></tr>
        <tr><td>Custom Colours &amp; Themes</td><td><span class="cross">&#10005;</span></td><td><span class="tick">&#10003;</span></td></tr>
        <tr><td>Transparent Background</td><td><span class="cross">&#10005;</span></td><td><span class="tick">&#10003;</span></td></tr>
        <tr><td>White-label Usage</td><td><span class="cross">&#10005;</span></td><td><span class="tick">&#10003;</span></td></tr>
      </tbody>
    </table>
  </div>
  <div style="text-align:center;margin-top:24px;">
    <a href="/users" class="gs-w-cta-primary">Create Free Account &amp; Unlock Pro Widget &rarr;</a>
  </div>
</section>

<!-- ── 6. PROFESSIONAL WIDGET PREVIEW ────────────────────────────── -->
<section class="gs-w-section" id="pro">
  <h2>Professional Unbranded Storage Widget</h2>
  <p>Cleaner, white-label, transparent background &mdash; with a 30-day storage trend, gas stress indices and an extended country breakdown for premium dashboards.</p>
  <div class="gs-w-preview-wrap">
    <div class="gs-w-preview-pro">
      <div class="gs-w-preview-col" style="background:transparent;">
        <h3 style="color:#fff;">PRO WIDGET &middot; UNBRANDED PREVIEW</h3>
        <div class="gs-w-iframe-shell" style="background:#020617;">
          <iframe src="{WIDGET_PATH_PRO}" width="100%" height="520" frameborder="0"
                  style="border:0;display:block;border-radius:10px;background:transparent;"
                  loading="lazy" title="Pro Europe Gas Storage Widget Preview"></iframe>
        </div>
        <div class="gs-w-preview-note" style="color:#94a3b8;">
          No branding &middot; transparent background &middot; white-label ready
        </div>
      </div>
    </div>
  </div>
  <div style="text-align:center;margin-top:24px;">
    <a href="/users" class="gs-w-cta-primary">Upgrade for &euro;{PRO_PRICE_EUR}/month &rarr;</a>
  </div>
</section>

<!-- ── 7. SEO CONTENT ────────────────────────────────────────────── -->
<section class="gs-w-section">
  <h2>Europe Gas Storage Levels Today</h2>
  <div class="gs-w-seo-block">
    <h3>What Are Europe&rsquo;s Gas Storage Levels?</h3>
    <p>
      Europe&rsquo;s gas storage levels measure how full the continent&rsquo;s underground gas storage sites are,
      expressed as a percentage of total working capacity. Storage is injected through spring and summer and
      drawn down through winter, making the seasonal fill curve one of the most-watched indicators in European
      energy markets. The EU targets <strong>90% storage by 1 November</strong> each year to secure winter supply.
    </p>
    <h3>Why Gas Storage Matters for Prices</h3>
    <p>
      Storage is inseparable from gas prices. When storage runs below the seasonal norm, the market must compete
      harder for LNG cargoes and pipeline flows, pushing up <a href="/data/ttf-gas-price-today">TTF gas prices</a>.
      Healthy storage cushions winter demand shocks and dampens price volatility. This is why our widget leads with
      <strong>Winter Readiness</strong> &mdash; the signal that actually drives the market.
    </p>
    <h3>What Moves Europe&rsquo;s Storage Levels?</h3>
    <p>
      Storage is driven by weather and heating demand, LNG import availability, pipeline supply, the seasonal
      injection/withdrawal cycle, and gas-market risk. EnergyRiskIQ&rsquo;s
      <a href="/indices/europe-gas-stress-index">Europe Gas Stress Index (EGSI)</a> and
      <a href="/indices/europe-energy-risk-index">Europe Energy Risk Index (EERI)</a> capture the risk layer in real time.
    </p>
  </div>
</section>

<!-- ── 8. USE CASES ──────────────────────────────────────────────── -->
<section class="gs-w-section">
  <h2>Perfect For</h2>
  <div class="gs-w-uses-grid">
    <div class="gs-w-use-card">Energy blogs</div>
    <div class="gs-w-use-card">Trading communities</div>
    <div class="gs-w-use-card">Market dashboards</div>
    <div class="gs-w-use-card">Utility &amp; industrial sites</div>
    <div class="gs-w-use-card">Investment newsletters</div>
    <div class="gs-w-use-card">Economic research websites</div>
  </div>
</section>

<!-- ── 9. CROSS-LINK HUB ─────────────────────────────────────────── -->
<section class="gs-w-section">
  <h2>Explore More Gas, LNG &amp; Risk Data</h2>
  <p>Storage directly impacts gas and LNG prices &mdash; explore the full EnergyRiskIQ data network.</p>
  <div class="gs-w-links-grid">
    <a class="gs-w-link-card" href="/gas-storage-levels-in-europe">
      <div class="gs-w-link-title">Gas Storage Levels in Europe</div>
      <div class="gs-w-link-desc">Full storage dashboard, trend charts and risk scoring.</div>
    </a>
    <a class="gs-w-link-card" href="/data/ttf-gas-price-today">
      <div class="gs-w-link-title">TTF Gas Price Today</div>
      <div class="gs-w-link-desc">The European natural gas benchmark, updated daily.</div>
    </a>
    <a class="gs-w-link-card" href="/data/natural-gas-price-today-europe">
      <div class="gs-w-link-title">Natural Gas Price Today Europe</div>
      <div class="gs-w-link-desc">Live European gas pricing with charts and drivers.</div>
    </a>
    <a class="gs-w-link-card" href="/data/europe-lng-supply-demand">
      <div class="gs-w-link-title">Europe LNG Supply &amp; Demand</div>
      <div class="gs-w-link-desc">LNG flows that refill Europe&rsquo;s storage.</div>
    </a>
    <a class="gs-w-link-card" href="/data/jkm-lng-spot-price">
      <div class="gs-w-link-title">JKM LNG Spot Price</div>
      <div class="gs-w-link-desc">Asian LNG benchmark competing for cargoes.</div>
    </a>
    <a class="gs-w-link-card" href="/research/what-drives-lng-prices">
      <div class="gs-w-link-title">What Drives LNG Prices?</div>
      <div class="gs-w-link-desc">The research behind global LNG pricing.</div>
    </a>
    <a class="gs-w-link-card" href="/indices/europe-energy-risk-index">
      <div class="gs-w-link-title">Europe Energy Risk Index (EERI)</div>
      <div class="gs-w-link-desc">Daily European energy risk regime.</div>
    </a>
    <a class="gs-w-link-card" href="/indices/europe-gas-stress-index">
      <div class="gs-w-link-title">Europe Gas Stress Index (EGSI)</div>
      <div class="gs-w-link-desc">Gas-specific market and supply stress.</div>
    </a>
    <a class="gs-w-link-card" href="/data/global-energy-risk-forecast">
      <div class="gs-w-link-title">Global Energy Risk Forecast</div>
      <div class="gs-w-link-desc">24-hour Brent &amp; TTF risk-driven forecast.</div>
    </a>
  </div>
</section>

<!-- ── 10. FAQ ───────────────────────────────────────────────────── -->
<section class="gs-w-section">
  <h2>Frequently Asked Questions</h2>
  <div class="gs-w-faq">{faq_html}</div>
</section>

<!-- ── CITATION & REFERENCE ──────────────────────────────────────── -->
<section class="gs-w-section">
  <h2>Citation &amp; Reference</h2>
  <div class="gs-w-cite-card">
    <h3>How to Cite This Widget</h3>
    <div class="gs-w-cite-desc">
      When using the Europe gas storage widget in research, journalism, dashboards or professional reports, please cite the source as follows.
    </div>
    <div class="gs-w-cite-code-wrap">
      <pre class="gs-w-cite-code">EnergyRiskIQ. (2026). <em>Europe Gas Storage Levels Widget &mdash; {today_str}</em>.
Retrieved from <a href="{LANDING_URL}">{LANDING_URL}</a>
Live data: <a href="{DATA_URL}">{DATA_URL}</a>
Custom Algorithm interpretation. Data sources: AGSI+ / GIE gas storage, per-country storage captures, EERI &amp; EGSI risk engines.</pre>
      <button class="gs-w-cite-btn" onclick="this.textContent='Copied!';setTimeout(()=>this.textContent='Copy',2000);navigator.clipboard&amp;&amp;navigator.clipboard.writeText('EnergyRiskIQ. (2026). Europe Gas Storage Levels Widget — {today_str}. Retrieved from {LANDING_URL}')">Copy</button>
    </div>
  </div>
</section>

<!-- ── 11. FINAL CONVERSION ──────────────────────────────────────── -->
<section class="gs-w-section">
  <div class="gs-w-conv">
    <h2>Upgrade to the Professional Storage Widget</h2>
    <p>
      Remove branding, customise appearance, and integrate a premium gas storage widget with trend charts and
      stress indices into your website, app, or trading dashboard &mdash; for less than the price of a coffee per month.
    </p>
    <div class="gs-w-cta-row" style="margin-bottom:0;">
      <a href="/users" class="gs-w-cta-primary">Create Free Account &rarr;</a>
      <a href="#compare" class="gs-w-cta-secondary">Compare Free vs Pro</a>
    </div>
  </div>
</section>

<!-- ── 12. FOOTER LICENSE ────────────────────────────────────────── -->
<div class="gs-w-license">
  <strong>Data disclaimer:</strong> Gas storage figures shown in the widget are provided for informational purposes
  only and do not constitute financial advice. Data is delivered under the EnergyRiskIQ
  <a href="/data-license">data licence (CC BY-NC 4.0)</a>. Commercial redistribution without attribution
  is not permitted on the free widget &mdash; the Pro plan grants full white-label rights.
</div>

<footer class="page-footer">
  <div>
    &copy; 2026 EnergyRiskIQ &bull;
    <a href="/">Home</a>
    <a href="/gas-storage-levels-in-europe">Gas Storage</a>
    <a href="/data/ttf-gas-price-today">TTF</a>
    <a href="/indices/europe-gas-stress-index">EGSI</a>
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
    'Europe Gas Storage Levels Today (%) | Live Widget & Risk Signals'
).replace(
    'name="description" content="Live global energy risk snapshot. Current GERI, EERI and EGSI-M index values with Brent crude, TTF gas, VIX and LNG market prices."',
    'name="description" content="Track Europe gas storage levels today with a free live widget. Monitor EU storage %, winter readiness, country storage data, and gas market risk signals."'
).replace(
    'rel="canonical" href="https://energyriskiq.com/data/energy-risk-snapshot"',
    f'rel="canonical" href="{LANDING_URL}"'
).replace(
    'Fetching GERI\u00a0&\u00a0EERI indices\u2026',
    'Loading gas storage widget preview\u2026',
).replace(
    '<span class="ld-tag">GERI</span>\n    <span class="ld-tag">EERI</span>\n    <span class="ld-tag">EGSI&#8209;M</span>\n    <span class="ld-tag">Brent</span>\n    <span class="ld-tag">TTF</span>',
    '<span class="ld-tag">Storage</span>\n    <span class="ld-tag">Widget</span>\n    <span class="ld-tag">Embed</span>\n    <span class="ld-tag">EGSI</span>',
)


@router.get("/widgets/europe-gas-storage-levels")
async def gas_storage_widget_landing():
    async def generate():
        yield _WIDGET_LOADER_HTML
        try:
            today_str = datetime.now(timezone.utc).strftime('%B %-d, %Y')
            html = await asyncio.to_thread(_build_landing_html, today_str)
            yield html
        except Exception as exc:
            logger.error(f"Gas storage widget landing render failed: {exc}", exc_info=True)
            yield (
                "<script>var l=document.getElementById('snap-loader');"
                "if(l)l.style.display='none';document.body.style.overflow='';</script>"
                f"<div style='color:#ef4444;padding:40px;font-family:sans-serif;background:#0b0f1a;'>"
                f"<h2>Error loading widget page</h2><p>{_html.escape(str(exc))}</p></div></body></html>"
            )

    return StreamingResponse(generate(), media_type="text/html")
