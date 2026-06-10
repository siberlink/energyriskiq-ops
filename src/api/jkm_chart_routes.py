"""
JKM LNG Price Chart Page
Route: /data/jkm-lng-price-chart
SEO-optimised JKM LNG benchmark price chart with historical trends, risk intelligence, and market context.
"""
import os
import json
import math
import logging
import asyncio
import html as _html
from datetime import datetime, timezone, date as _date, timedelta

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from src.db.db import execute_production_one, execute_production_query
from src.api.snapshot_routes import (
    _PAGE_CSS, _LOADER_HTML, BAND_COLORS, _safe_float,
)

router = APIRouter()
logger = logging.getLogger(__name__)

BASE_URL = "https://energyriskiq.com"

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _sign(v): return "+" if v >= 0 else ""
def _arrow(v): return "&#9650;" if v >= 0 else "&#9660;"
def _chg_color(v): return "#22c55e" if v >= 0 else "#ef4444"

def _fmt_short(d):
    try:
        return d.strftime("%b %-d") if d else "—"
    except Exception:
        return str(d)

def _fmt_long(d):
    try:
        return d.strftime("%B %-d, %Y") if d else "—"
    except Exception:
        return str(d)

def _fmt_iso(d):
    try:
        return d.strftime("%Y-%m-%d") if d else ""
    except Exception:
        return str(d)


def _sentiment(chg_pct):
    if chg_pct >= 1.0:
        return "&#129001;", "Bullish", "#22c55e"
    elif chg_pct <= -1.0:
        return "&#128997;", "Bearish", "#ef4444"
    else:
        return "&#9898;", "Neutral", "#94a3b8"


# ─────────────────────────────────────────────────────────────────────────────
# SVG Chart Builder — full-width line+area
# ─────────────────────────────────────────────────────────────────────────────

def _build_jkm_svg(data_points, color="#d4a017", height=180):
    if not data_points or len(data_points) < 2:
        return (
            "<div style='height:80px;display:flex;align-items:center;"
            "justify-content:center;color:#64748b;font-size:13px;'>"
            "Chart data loading…</div>"
        )
    vals = [p["val"] for p in data_points if p.get("val") is not None]
    if len(vals) < 2:
        return ""

    W, H = 680, height
    PL, PR, PT, PB = 52, 16, 16, 38

    cw = W - PL - PR
    ch = H - PT - PB

    vmin = min(vals) * 0.994
    vmax = max(vals) * 1.006
    rng = vmax - vmin or 1

    n = len(data_points)
    step = cw / max(n - 1, 1)

    pts = []
    for i, p in enumerate(data_points):
        v = p.get("val")
        if v is None:
            continue
        x = PL + i * step
        y = PT + ch - ((v - vmin) / rng) * ch
        pts.append((x, y, v))

    if len(pts) < 2:
        return ""

    path_d = f"M {pts[0][0]:.1f} {pts[0][1]:.1f}"
    for x, y, _ in pts[1:]:
        path_d += f" L {x:.1f} {y:.1f}"
    bot_y = PT + ch
    area_d = path_d + f" L {pts[-1][0]:.1f} {bot_y} L {pts[0][0]:.1f} {bot_y} Z"

    gid = f"jkmGrad{abs(hash(color)) % 9999}"
    defs = (
        f'<defs><linearGradient id="{gid}" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0%" stop-color="{color}" stop-opacity="0.25"/>'
        f'<stop offset="100%" stop-color="{color}" stop-opacity="0.02"/>'
        f'</linearGradient></defs>'
    )
    area_svg = (
        f'{defs}'
        f'<path d="{area_d}" fill="url(#{gid})"/>'
        f'<path d="{path_d}" fill="none" stroke="{color}" stroke-width="2.2" stroke-linejoin="round"/>'
    )

    # Y-axis — 3 labels
    y_top = PT
    y_bot = PT + ch
    mid_v = (vmin + vmax) / 2
    mid_y = PT + ch / 2
    ax_svg = (
        f'<line x1="{PL}" y1="{y_bot:.1f}" x2="{W - PR}" y2="{y_bot:.1f}" '
        f'stroke="rgba(255,255,255,0.08)" stroke-width="1"/>'
        f'<line x1="{PL}" y1="{mid_y:.1f}" x2="{W - PR}" y2="{mid_y:.1f}" '
        f'stroke="rgba(255,255,255,0.04)" stroke-width="1" stroke-dasharray="4 3"/>'
        f'<text x="{PL - 5}" y="{y_top + 5}" text-anchor="end" font-size="9" '
        f'fill="#94a3b8" font-family="Inter,sans-serif">${vmax:.1f}</text>'
        f'<text x="{PL - 5}" y="{mid_y + 3}" text-anchor="end" font-size="9" '
        f'fill="#94a3b8" font-family="Inter,sans-serif">${mid_v:.1f}</text>'
        f'<text x="{PL - 5}" y="{y_bot}" text-anchor="end" font-size="9" '
        f'fill="#94a3b8" font-family="Inter,sans-serif">${vmin:.1f}</text>'
    )

    # X-axis ticks — up to 8
    max_t = 8
    t_step = max(1, n // max_t)
    tick_svg = ""
    for i, p in enumerate(data_points):
        if i % t_step == 0 or i == n - 1:
            x = PL + i * step
            lbl = str(p.get("label", ""))
            tick_svg += (
                f'<text x="{x:.1f}" y="{y_bot + 22}" text-anchor="middle" '
                f'font-size="9" fill="#94a3b8" font-family="Inter,sans-serif">{lbl}</text>'
            )

    # Last-point dot + price label
    lx, ly, lv = pts[-1]
    dot_svg = (
        f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="5" fill="{color}" '
        f'stroke="#0f172a" stroke-width="2"/>'
        f'<text x="{lx:.1f}" y="{ly - 10:.1f}" text-anchor="middle" '
        f'font-size="10" fill="{color}" font-weight="700" '
        f'font-family="Inter,sans-serif">${lv:.2f}</text>'
    )

    return (
        f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" '
        f'style="width:100%;display:block;overflow:visible;">'
        f'{ax_svg}{area_svg}{tick_svg}{dot_svg}'
        f'</svg>'
    )


# ─────────────────────────────────────────────────────────────────────────────
# Loader HTML
# ─────────────────────────────────────────────────────────────────────────────

_JKM_LOADER_HTML = _LOADER_HTML.replace(
    "Global Energy Risk Snapshot | EnergyRiskIQ",
    "JKM LNG Price Chart (Live Daily Update) | Asia Gas Benchmark | EnergyRiskIQ",
).replace(
    'name="description" content="Live global energy risk snapshot. Current GERI, EERI and EGSI-M index values with Brent crude, TTF gas, VIX and LNG market prices."',
    'name="description" content="Track the JKM LNG price chart with daily updates, historical trends, and global LNG market insights. Monitor Asia\'s key gas benchmark and market drivers."',
).replace(
    'rel="canonical" href="https://energyriskiq.com/data/energy-risk-snapshot"',
    'rel="canonical" href="https://energyriskiq.com/data/jkm-lng-price-chart"',
).replace(
    "Fetching GERI\u00a0&\u00a0EERI indices\u2026",
    "Fetching JKM LNG price & risk data\u2026",
).replace(
    '<span class="ld-tag">GERI</span>\n    <span class="ld-tag">EERI</span>\n    <span class="ld-tag">EGSI&#8209;M</span>\n    <span class="ld-tag">Brent</span>\n    <span class="ld-tag">TTF</span>',
    '<span class="ld-tag">JKM</span>\n    <span class="ld-tag">LNG</span>\n    <span class="ld-tag">TTF</span>\n    <span class="ld-tag">GERI</span>\n    <span class="ld-tag">Brent</span>',
)


# ─────────────────────────────────────────────────────────────────────────────
# JKM Page CSS
# ─────────────────────────────────────────────────────────────────────────────

JKM_COLOR = "#d4a017"
JKM_COLOR_DIM = "rgba(212,160,23,0.18)"

_JKM_CSS = f"""
/* ── Anti-copy data protection ──────────────────────────────────────────── */
.jkm-protected {{
  user-select: none;
  -webkit-user-select: none;
  -moz-user-select: none;
  -ms-user-select: none;
}}
.jkm-watermark-attr {{
  font-size: 9px; color: rgba(148,163,184,0.25);
  position: absolute; bottom: 4px; right: 8px;
  pointer-events: none; letter-spacing: 0.05em;
}}

/* ── Hero Price Card ─────────────────────────────────────────────────────── */
.jkm-hero-card {{
  background: linear-gradient(135deg, #0e1708 0%, #14200a 50%, #0f172a 100%);
  border: 1px solid rgba(212,160,23,0.3);
  border-radius: 20px;
  padding: 32px 36px;
  margin-bottom: 40px;
  position: relative;
  overflow: hidden;
  max-width: 760px;
  margin-left: auto;
  margin-right: auto;
}}
.jkm-hero-card::before {{
  content: '';
  position: absolute; top: 0; left: 0; right: 0; height: 3px;
  background: linear-gradient(90deg, {JKM_COLOR}, rgba(212,160,23,0.2));
}}
.jkm-price-label {{
  font-size: 11px; font-weight: 700; letter-spacing: 2px;
  text-transform: uppercase; color: {JKM_COLOR}; margin-bottom: 8px;
}}
.jkm-price-main {{
  font-size: 54px; font-weight: 900; line-height: 1;
  color: {JKM_COLOR}; font-variant-numeric: tabular-nums; margin-bottom: 8px;
}}
.jkm-price-main sup {{ font-size: 28px; font-weight: 700; vertical-align: top; margin-top: 8px; }}
.jkm-price-change {{ font-size: 18px; font-weight: 700; margin-bottom: 12px; }}
.jkm-sentiment-badge {{
  display: inline-flex; align-items: center; gap: 6px;
  padding: 6px 16px; border-radius: 20px;
  font-size: 12px; font-weight: 700; letter-spacing: 0.06em;
  text-transform: uppercase;
}}
.jkm-trust-line {{
  font-size: 11px; color: #94a3b8; margin-top: 16px;
  display: flex; gap: 16px; flex-wrap: wrap; align-items: center;
}}
.jkm-trust-dot {{ color: #334155; }}
.jkm-hero-cta {{
  display: inline-flex; align-items: center; gap: 8px;
  margin-top: 20px; padding: 10px 22px; border-radius: 8px;
  background: rgba(212,160,23,0.1); border: 1px solid rgba(212,160,23,0.3);
  color: {JKM_COLOR}; font-size: 13px; font-weight: 700;
  text-decoration: none; transition: all 0.2s;
}}
.jkm-hero-cta:hover {{ background: rgba(212,160,23,0.2); }}

/* ── Sticky Bar ──────────────────────────────────────────────────────────── */
.jkm-sticky-bar {{
  position: fixed; bottom: 0; left: 0; right: 0; z-index: 900;
  background: rgba(15,23,42,0.96); backdrop-filter: blur(8px);
  border-top: 1px solid rgba(212,160,23,0.2);
  padding: 8px 20px;
  display: flex; align-items: center; justify-content: space-between;
  font-size: 13px;
}}
.jkm-sticky-label {{ color: #94a3b8; font-weight: 600; }}
.jkm-sticky-price {{ color: {JKM_COLOR}; font-weight: 800; font-size: 15px; margin: 0 8px; }}
.jkm-sticky-chg {{ font-weight: 600; }}
.jkm-sticky-time {{ color: #64748b; font-size: 11px; }}
.jkm-sticky-cta {{
  padding: 5px 14px; border-radius: 6px;
  background: rgba(212,160,23,0.12); border: 1px solid rgba(212,160,23,0.3);
  color: {JKM_COLOR}; font-size: 11px; font-weight: 700;
  text-decoration: none; letter-spacing: 0.04em; white-space: nowrap;
}}
@media (max-width: 640px) {{
  .jkm-sticky-bar {{ padding: 6px 10px; font-size: 11px; }}
  .jkm-sticky-label {{ display: none; }}
  .jkm-sticky-time {{ display: none; }}
  .jkm-sticky-price {{ font-size: 14px; margin: 0 4px; }}
}}

/* ── Chart Card ──────────────────────────────────────────────────────────── */
.jkm-chart-card {{
  background: var(--card); border: 1px solid var(--border);
  border-radius: 16px; padding: 24px; margin-bottom: 40px; overflow: hidden;
}}
.jkm-range-tabs {{
  display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 20px;
}}
.jkm-range-tab {{
  padding: 5px 14px; border-radius: 6px;
  font-size: 11px; font-weight: 700; letter-spacing: 0.06em;
  text-transform: uppercase; cursor: pointer; border: none;
  background: rgba(255,255,255,0.04); color: #64748b; transition: all 0.2s;
}}
.jkm-range-tab.active, .jkm-range-tab:hover {{
  background: rgba(212,160,23,0.15); color: {JKM_COLOR};
}}
.jkm-chart-wrap {{ width: 100%; overflow-x: hidden; }}
.jkm-chart-container {{ display: none; }}
.jkm-chart-container.active {{ display: block; }}
.jkm-chart-note {{
  font-size: 11px; color: #64748b; margin-top: 8px; text-align: right;
}}

/* ── Overlay Toggles ─────────────────────────────────────────────────────── */
.jkm-overlay-row {{
  display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px;
}}
.jkm-overlay-btn {{
  padding: 4px 12px; border-radius: 20px;
  font-size: 10px; font-weight: 700; letter-spacing: 0.08em;
  text-transform: uppercase; cursor: pointer; border: 1px solid rgba(255,255,255,0.08);
  background: rgba(255,255,255,0.03); color: #64748b; transition: all 0.2s;
}}
.jkm-overlay-btn:hover {{ border-color: rgba(212,160,23,0.3); color: {JKM_COLOR}; }}

/* ── Snapshot / Insight Cards ────────────────────────────────────────────── */
.jkm-snapshot-card {{
  background: linear-gradient(135deg, #0e1a0d 0%, #0f172a 100%);
  border: 1px solid rgba(212,160,23,0.18);
  border-radius: 14px; padding: 28px 32px; margin-bottom: 40px; position: relative;
}}
.jkm-snapshot-card::before {{
  content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px;
  background: linear-gradient(90deg, {JKM_COLOR}, transparent);
}}
.jkm-snapshot-para {{
  font-size: 16px; color: #cbd5e1; line-height: 1.85;
  margin-bottom: 1.1em; font-weight: 400;
}}
.jkm-snapshot-para:last-child {{ margin-bottom: 0; }}
.jkm-snapshot-para strong {{ color: #ffffff; font-weight: 600; }}

/* ── Section Grid Cards ──────────────────────────────────────────────────── */
.jkm-two-col {{
  display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 40px;
}}
@media (max-width: 700px) {{ .jkm-two-col {{ grid-template-columns: 1fr; }} }}
.jkm-three-col {{
  display: grid; grid-template-columns: repeat(3,1fr); gap: 14px; margin-bottom: 24px;
}}
@media (max-width: 700px) {{ .jkm-three-col {{ grid-template-columns: 1fr; }} }}
.jkm-four-col {{
  display: grid; grid-template-columns: repeat(4,1fr); gap: 12px; margin-bottom: 28px;
}}
@media (max-width: 700px) {{ .jkm-four-col {{ grid-template-columns: repeat(2,1fr); }} }}
@media (max-width: 420px) {{ .jkm-four-col {{ grid-template-columns: 1fr; }} }}

/* ── Context / Nav Cards ─────────────────────────────────────────────────── */
.jkm-nav-card {{
  display: flex; align-items: flex-start; gap: 14px;
  background: var(--card); border: 1px solid var(--border);
  border-radius: 12px; padding: 18px 20px;
  text-decoration: none; color: inherit; transition: all 0.2s;
}}
.jkm-nav-card:hover {{
  border-color: rgba(212,160,23,0.4);
  box-shadow: 0 0 16px rgba(212,160,23,0.07);
  transform: translateY(-1px);
}}
.jkm-nav-icon {{ font-size: 1.6rem; flex-shrink: 0; margin-top: 2px; }}
.jkm-nav-title {{ font-size: 13px; font-weight: 700; color: #e2e8f0; margin-bottom: 4px; }}
.jkm-nav-desc {{ font-size: 12px; color: #94a3b8; line-height: 1.5; }}
.jkm-nav-link {{ font-size: 11px; color: {JKM_COLOR}; font-weight: 600; margin-top: 6px;
  display: inline-flex; align-items: center; gap: 4px; }}

/* ── Driver Cards ────────────────────────────────────────────────────────── */
.jkm-driver-card {{
  background: var(--card); border: 1px solid var(--border);
  border-radius: 12px; padding: 20px 22px;
}}
.jkm-driver-num {{
  font-size: 11px; font-weight: 700; letter-spacing: 0.1em;
  text-transform: uppercase; color: {JKM_COLOR}; margin-bottom: 6px;
}}
.jkm-driver-title {{ font-size: 15px; font-weight: 700; color: #e2e8f0; margin-bottom: 8px; }}
.jkm-driver-desc {{ font-size: 13px; color: #94a3b8; line-height: 1.65; }}
.jkm-driver-desc a {{ color: {JKM_COLOR}; text-decoration: none; }}

/* ── Risk Cards ──────────────────────────────────────────────────────────── */
.jkm-risk-card {{
  background: var(--card); border: 1px solid var(--border);
  border-radius: 12px; padding: 18px 20px; text-align: center;
}}
.jkm-risk-name {{
  font-size: 10px; font-weight: 700; letter-spacing: 1.5px;
  text-transform: uppercase; color: #94a3b8; margin-bottom: 6px;
}}
.jkm-risk-value {{ font-size: 36px; font-weight: 900; line-height: 1; margin-bottom: 4px; }}
.jkm-risk-band {{
  font-size: 11px; font-weight: 700; letter-spacing: 0.08em;
  text-transform: uppercase; margin-bottom: 4px;
}}
.jkm-risk-desc {{ font-size: 11px; color: #94a3b8; line-height: 1.5; }}
.jkm-risk-interp-card {{
  background: linear-gradient(135deg, rgba(212,160,23,0.06) 0%, rgba(15,23,42,0) 100%);
  border: 1px solid rgba(212,160,23,0.15);
  border-radius: 12px; padding: 22px 26px; margin-bottom: 40px;
}}

/* ── Spread / Historical Cards ───────────────────────────────────────────── */
.jkm-spread-card {{
  background: var(--card); border: 1px solid var(--border);
  border-radius: 12px; padding: 22px 26px; margin-bottom: 14px;
}}
.jkm-spread-title {{
  font-size: 14px; font-weight: 700; color: #e2e8f0; margin-bottom: 8px;
  display: flex; align-items: center; gap: 8px;
}}
.jkm-spread-desc {{ font-size: 13px; color: #94a3b8; line-height: 1.65; }}
.jkm-spread-desc a {{ color: {JKM_COLOR}; text-decoration: none; }}
.jkm-hist-card {{
  background: var(--card); border: 1px solid var(--border);
  border-radius: 10px; padding: 14px 16px; text-align: center;
}}
.jkm-hist-label {{
  font-size: 10px; font-weight: 700; letter-spacing: 1.2px;
  text-transform: uppercase; color: #94a3b8; margin-bottom: 6px;
}}
.jkm-hist-value {{ font-size: 22px; font-weight: 800; color: #e2e8f0; }}
.jkm-hist-date {{ font-size: 10px; color: #94a3b8; margin-top: 3px; }}

/* ── Insight Card ────────────────────────────────────────────────────────── */
.jkm-insight-card {{
  background: linear-gradient(135deg, #0e1708 0%, #0f172a 100%);
  border: 1px solid rgba(212,160,23,0.2); border-radius: 14px;
  padding: 28px 32px; margin-bottom: 40px; position: relative;
}}
.jkm-insight-card::before {{
  content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px;
  background: linear-gradient(90deg, {JKM_COLOR}, transparent);
}}
.jkm-insight-label {{
  font-size: 11px; font-weight: 700; letter-spacing: 0.1em;
  text-transform: uppercase; color: {JKM_COLOR}; margin-bottom: 16px;
}}
.jkm-insight-item {{ margin-bottom: 16px; }}
.jkm-insight-section-title {{
  font-size: 11px; font-weight: 700; letter-spacing: 0.08em;
  text-transform: uppercase; color: #94a3b8; margin-bottom: 4px;
}}
.jkm-insight-body {{
  font-size: 15px; color: #cbd5e1; line-height: 1.75;
}}
.jkm-insight-body strong {{ color: #ffffff; font-weight: 600; }}

/* ── CTA Card ────────────────────────────────────────────────────────────── */
.jkm-cta-card {{
  background: linear-gradient(135deg, #0e1708 0%, #14200a 50%, #0f172a 100%);
  border: 1px solid rgba(212,160,23,0.25); border-radius: 20px;
  padding: 40px 36px; text-align: center; margin-bottom: 40px;
  position: relative; overflow: hidden;
}}
.jkm-cta-card::before {{
  content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px;
  background: linear-gradient(90deg, {JKM_COLOR}, rgba(212,160,23,0.3), transparent);
}}
.jkm-cta-label {{
  font-size: 10px; font-weight: 700; letter-spacing: 2px;
  text-transform: uppercase; color: {JKM_COLOR}; margin-bottom: 12px;
}}
.jkm-cta-h2 {{
  font-size: 26px; font-weight: 800; color: #e2e8f0;
  margin-bottom: 12px; line-height: 1.3;
}}
.jkm-cta-sub {{
  font-size: 14px; color: #94a3b8; margin-bottom: 24px; max-width: 500px;
  margin-left: auto; margin-right: auto; line-height: 1.7;
}}
.jkm-cta-benefits {{
  display: flex; justify-content: center; gap: 22px; flex-wrap: wrap; margin-bottom: 28px;
}}
.jkm-cta-benefit {{
  font-size: 12px; color: #94a3b8; display: flex; align-items: center; gap: 6px;
}}
.jkm-cta-benefit::before {{ content: '✓'; color: #22c55e; font-weight: 700; }}
.jkm-cta-btn {{
  display: inline-block; padding: 14px 36px;
  background: linear-gradient(135deg, {JKM_COLOR}, #b8880f);
  color: #0f172a; font-size: 15px; font-weight: 800;
  border-radius: 10px; text-decoration: none; letter-spacing: 0.03em;
  box-shadow: 0 4px 20px rgba(212,160,23,0.3); transition: all 0.2s;
}}
.jkm-cta-btn:hover {{ box-shadow: 0 6px 28px rgba(212,160,23,0.45); transform: translateY(-1px); }}
.jkm-cta-credits {{ font-size: 11px; color: #64748b; margin-top: 10px; }}

/* ── FAQ ─────────────────────────────────────────────────────────────────── */
.jkm-faq-card {{
  background: var(--card); border: 1px solid var(--border);
  border-radius: 12px; margin-bottom: 10px; overflow: hidden;
}}
.jkm-faq-q {{
  padding: 16px 20px; font-size: 14px; font-weight: 600; color: #e2e8f0;
  cursor: pointer; display: flex; justify-content: space-between; align-items: center;
  user-select: none;
}}
.jkm-faq-q:hover {{ color: {JKM_COLOR}; }}
.jkm-faq-chevron {{ font-size: 12px; color: #64748b; transition: transform 0.2s; }}
.jkm-faq-a {{
  display: none; padding: 0 20px 16px; font-size: 13px;
  color: #94a3b8; line-height: 1.7;
}}
.jkm-faq-card.open .jkm-faq-chevron {{ transform: rotate(180deg); }}
.jkm-faq-card.open .jkm-faq-a {{ display: block; }}

/* ── Link Footer ─────────────────────────────────────────────────────────── */
.jkm-link-footer {{
  background: var(--card); border: 1px solid var(--border);
  border-radius: 14px; padding: 28px 30px; margin-bottom: 40px;
}}
.jkm-link-section {{ margin-bottom: 22px; }}
.jkm-link-section:last-child {{ margin-bottom: 0; }}
.jkm-link-section-title {{
  font-size: 10px; font-weight: 700; letter-spacing: 1.5px;
  text-transform: uppercase; color: #94a3b8; margin-bottom: 12px;
}}
.jkm-link-grid {{ display: flex; gap: 10px; flex-wrap: wrap; }}
.jkm-link-pill {{
  display: inline-flex; align-items: center; gap: 6px;
  padding: 6px 14px; border-radius: 20px;
  background: rgba(255,255,255,0.03); border: 1px solid var(--border);
  font-size: 12px; font-weight: 600; color: #94a3b8;
  text-decoration: none; transition: all 0.2s;
}}
.jkm-link-pill:hover {{ border-color: rgba(212,160,23,0.3); color: {JKM_COLOR}; }}

/* ── Cite Card ───────────────────────────────────────────────────────────── */
.jkm-cite-card {{
  background: var(--card); border: 1px solid var(--border);
  border-radius: 12px; padding: 22px 24px; margin-bottom: 40px;
}}
.jkm-cite-desc {{ font-size: 13px; color: #94a3b8; margin-bottom: 12px; }}
.jkm-cite-code {{
  font-size: 12px; font-family: "JetBrains Mono","Courier New",monospace;
  color: #94a3b8; line-height: 1.7; margin: 0; white-space: pre-wrap;
  overflow-wrap: break-word; word-break: break-word;
}}
.jkm-cite-code em {{ color: {JKM_COLOR}; font-style: normal; }}
.jkm-cite-code a {{ color: #3b82f6; }}

/* ── Mobile ──────────────────────────────────────────────────────────────── */
@media (max-width: 640px) {{
  .jkm-hero-card {{ padding: 22px 16px; margin-bottom: 28px; }}
  .jkm-price-main {{ font-size: 38px; }}
  .jkm-price-change {{ font-size: 15px; }}
  .jkm-chart-card {{ padding: 16px 14px; }}
  .jkm-snapshot-card, .jkm-insight-card {{ padding: 20px 16px; }}
  .jkm-cta-card {{ padding: 24px 16px; }}
  .jkm-cta-h2 {{ font-size: 20px; }}
  .jkm-link-footer {{ padding: 20px 16px; }}
  .jkm-risk-interp-card {{ padding: 18px 16px; }}
  .jkm-spread-card {{ padding: 16px; }}
  body {{ padding-bottom: 60px; }}
  .jkm-range-tab {{ padding: 5px 9px; font-size: 10px; }}
  .jkm-trust-line {{ gap: 10px; font-size: 10px; }}
}}
@media (max-width: 600px) {{
  .nav-inner > div > a:not(.cta-btn-nav) {{ display: none; }}
}}
"""


# ─────────────────────────────────────────────────────────────────────────────
# Data Fetch
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_jkm_data() -> dict:
    today = _date.today()
    ytd_start = today.replace(month=1, day=1)
    one_year_ago = today - timedelta(days=365)

    # JKM latest
    jkm_latest = execute_production_one(
        "SELECT date, jkm_price, jkm_change_24h, jkm_change_pct "
        "FROM lng_price_snapshots ORDER BY date DESC LIMIT 1"
    )
    # JKM full history (all rows available)
    jkm_all = execute_production_query(
        "SELECT date, jkm_price FROM lng_price_snapshots ORDER BY date ASC"
    ) or []
    # YTD
    jkm_ytd = execute_production_query(
        "SELECT date, jkm_price FROM lng_price_snapshots WHERE date >= %s ORDER BY date ASC",
        (ytd_start,)
    ) or []
    # 1Y
    jkm_1y = execute_production_query(
        "SELECT date, jkm_price FROM lng_price_snapshots WHERE date >= %s ORDER BY date ASC",
        (one_year_ago,)
    ) or []

    # TTF
    ttf_latest = execute_production_one(
        "SELECT date, ttf_price FROM ttf_gas_snapshots ORDER BY date DESC LIMIT 1"
    )
    ttf_prev = execute_production_one(
        "SELECT ttf_price FROM ttf_gas_snapshots ORDER BY date DESC LIMIT 1 OFFSET 1"
    )
    # TTF history for overlay
    ttf_all = execute_production_query(
        "SELECT date, ttf_price FROM ttf_gas_snapshots ORDER BY date ASC"
    ) or []

    # Brent
    brent_latest = execute_production_one(
        "SELECT date, brent_price, brent_change_24h, brent_change_pct "
        "FROM oil_price_snapshots ORDER BY date DESC LIMIT 1"
    )
    # Brent history for overlay
    brent_all = execute_production_query(
        "SELECT date, brent_price FROM oil_price_snapshots ORDER BY date ASC"
    ) or []

    # VIX
    vix_latest = execute_production_one(
        "SELECT date, vix_close FROM vix_snapshots ORDER BY date DESC LIMIT 1"
    )
    vix_prev = execute_production_one(
        "SELECT vix_close FROM vix_snapshots ORDER BY date DESC LIMIT 1 OFFSET 1"
    )

    # Gas storage
    storage_latest = execute_production_one(
        "SELECT date, eu_storage_percent, seasonal_norm, deviation_from_norm, risk_band "
        "FROM gas_storage_snapshots ORDER BY date DESC LIMIT 1"
    )

    # GERI
    geri_row = execute_production_one(
        "SELECT date, value, band, trend_7d FROM intel_indices_daily "
        "WHERE index_id='global:geo_energy_risk' ORDER BY date DESC LIMIT 1"
    )
    geri_prev = execute_production_one(
        "SELECT value FROM intel_indices_daily "
        "WHERE index_id='global:geo_energy_risk' ORDER BY date DESC LIMIT 1 OFFSET 1"
    )
    # EERI
    eeri_row = execute_production_one(
        "SELECT date, value, band FROM reri_indices_daily "
        "WHERE index_id='europe:eeri' ORDER BY date DESC LIMIT 1"
    )
    eeri_prev = execute_production_one(
        "SELECT value FROM reri_indices_daily "
        "WHERE index_id='europe:eeri' ORDER BY date DESC LIMIT 1 OFFSET 1"
    )
    # EGSI-M
    egsi_m_row = execute_production_one(
        "SELECT index_date, index_value, band FROM egsi_m_daily "
        "WHERE region='Europe' ORDER BY index_date DESC LIMIT 1"
    )
    # EGSI-S
    egsi_s_row = execute_production_one(
        "SELECT index_date, index_value, band FROM egsi_s_daily "
        "WHERE region='Europe' ORDER BY index_date DESC LIMIT 1"
    )

    # Historical high/low YTD
    hist_ytd = execute_production_query(
        "SELECT date, jkm_price FROM lng_price_snapshots "
        "WHERE date >= %s ORDER BY jkm_price", (ytd_start,)
    ) or []
    # Historical high/low 30D
    hist_30d = execute_production_query(
        "SELECT date, jkm_price FROM "
        "(SELECT date, jkm_price FROM lng_price_snapshots ORDER BY date DESC LIMIT 30) t "
        "ORDER BY jkm_price"
    ) or []

    # Alert context
    alert_cats = execute_production_query(
        "SELECT category, COUNT(*) as cnt FROM alert_events "
        "WHERE created_at >= NOW() - INTERVAL '72 hours' "
        "GROUP BY category ORDER BY cnt DESC LIMIT 6"
    ) or []
    alert_context = "Alert categories (last 72h): " + ", ".join(
        f"{r['category']}={r['cnt']}" for r in alert_cats
    ) if alert_cats else "No recent alerts."

    return {
        "jkm_latest": jkm_latest,
        "jkm_all": jkm_all,
        "jkm_ytd": jkm_ytd,
        "jkm_1y": jkm_1y,
        "ttf_latest": ttf_latest,
        "ttf_prev": ttf_prev,
        "ttf_all": ttf_all,
        "brent_latest": brent_latest,
        "brent_all": brent_all,
        "vix_latest": vix_latest,
        "vix_prev": vix_prev,
        "storage_latest": storage_latest,
        "geri_row": geri_row,
        "geri_prev": geri_prev,
        "eeri_row": eeri_row,
        "eeri_prev": eeri_prev,
        "egsi_m_row": egsi_m_row,
        "egsi_s_row": egsi_s_row,
        "hist_ytd": hist_ytd,
        "hist_30d": hist_30d,
        "alert_context": alert_context,
    }


# ─────────────────────────────────────────────────────────────────────────────
# AI Insight Engine (Custom Algorithms)
# ─────────────────────────────────────────────────────────────────────────────

_JKM_INSIGHT_CACHE: dict = {}


def _run_jkm_insight(today_str, jkm_price, jkm_chg, jkm_chg_pct,
                     ttf_price, brent_price, vix_close, storage_pct,
                     geri_val, geri_band, eeri_val, eeri_band,
                     alert_context) -> dict:
    cache_key = f"jkm:{today_str}:{round(jkm_price, 1)}:{geri_val}"
    if cache_key in _JKM_INSIGHT_CACHE:
        return _JKM_INSIGHT_CACHE[cache_key]

    chg_dir = "up" if jkm_chg >= 0 else "down"
    trend_desc = "rising" if jkm_chg_pct > 0.5 else ("falling" if jkm_chg_pct < -0.5 else "flat")
    jkm_ttf_spread = round(jkm_price - (ttf_price / 3.412), 2) if ttf_price else 0.0

    fallback = {
        "what_happened": (
            f"JKM LNG traded at ${jkm_price:.2f}/MMBtu today, moving "
            f"{chg_dir} {abs(jkm_chg_pct):.1f}% on the day. "
            f"Asian demand patterns and European cargo competition continue "
            f"to shape near-term pricing dynamics."
        ),
        "why_matters": (
            f"With GERI at {geri_val}/100 ({geri_band}) and EERI at "
            f"{eeri_val}/100 ({eeri_band}), supply chain stress across "
            f"key LNG corridors remains a pricing factor. "
            f"TTF at €{ttf_price:.2f}/MWh sets the arbitrage threshold "
            f"for Atlantic-to-Pacific cargo rerouting."
        ),
        "what_to_watch": (
            f"Monitor Asian winter demand commitments, European gas storage "
            f"at {storage_pct:.1f}%, and Red Sea/Panama Canal shipping constraints. "
            f"Any GERI escalation above 60 would signal heightened supply risk "
            f"for JKM — watch Brent at ${brent_price:.2f}/bbl for oil-indexed LNG contract signals."
        ),
    }

    try:
        from openai import OpenAI
        ai_key = os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY")
        ai_url = os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL")
        client = OpenAI(api_key=ai_key, base_url=ai_url) if ai_key and ai_url else OpenAI()

        prompt = f"""You are EnergyRiskIQ's senior LNG market analyst. Today is {today_str}.

LIVE DATA:
JKM LNG Price: ${jkm_price:.2f}/MMBtu  change={_sign(jkm_chg)}{jkm_chg:.2f} ({jkm_chg_pct:+.2f}%) trend={trend_desc}
TTF Natural Gas: €{ttf_price:.2f}/MWh  JKM-TTF arbitrage spread: ~${jkm_ttf_spread:.2f}/MMBtu
Brent Crude: ${brent_price:.2f}/bbl (oil-linked LNG contracts reference)
VIX: {vix_close:.2f}
EU Gas Storage: {storage_pct:.1f}%
GERI (Global Energy Risk Index): {geri_val}/100  band={geri_band}
EERI (European Energy Risk Index): {eeri_val}/100  band={eeri_band}
{alert_context}

Return ONLY a valid JSON object with exactly these 3 keys. No markdown. No AI mentions. Write as proprietary analysis.

1. "what_happened" (≤220 chars): 2 sentences on what drove JKM price today. Reference specific prices.
2. "why_matters" (≤220 chars): 2 sentences on why today's move matters for LNG markets globally. Reference risk indices.
3. "what_to_watch" (≤220 chars): 2 sentences on forward-looking signals for JKM prices.

Authoritative, factual, no bullets, no AI references."""

        resp = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=420,
            response_format={"type": "json_object"},
            timeout=18,
        )
        data = json.loads(resp.choices[0].message.content)
        result = {k: str(data.get(k, fallback[k])).strip() for k in fallback}
        _JKM_INSIGHT_CACHE[cache_key] = result
        return result
    except Exception as exc:
        logger.warning(f"JKM insight engine failed: {exc}")
        return fallback


# ─────────────────────────────────────────────────────────────────────────────
# HTML Builder
# ─────────────────────────────────────────────────────────────────────────────

def _build_jkm_html(data: dict) -> str:
    today_str = datetime.now(timezone.utc).strftime("%B %-d, %Y")
    today_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # ── JKM price ──
    jr = data["jkm_latest"] or {}
    jkm_price = _safe_float(jr.get("jkm_price", 0))
    jkm_chg = _safe_float(jr.get("jkm_change_24h", 0))
    jkm_chg_pct = _safe_float(jr.get("jkm_change_pct", 0))
    jkm_date = jr.get("date", today_date)

    # ── TTF ──
    tr = data["ttf_latest"] or {}
    ttf_price = _safe_float(tr.get("ttf_price", 0))
    ttf_prev_price = _safe_float((data["ttf_prev"] or {}).get("ttf_price", ttf_price))
    ttf_chg = ttf_price - ttf_prev_price

    # ── Brent ──
    br = data["brent_latest"] or {}
    brent_price = _safe_float(br.get("brent_price", 0))
    brent_chg = _safe_float(br.get("brent_change_24h", 0))

    # ── VIX ──
    vr = data["vix_latest"] or {}
    vix_close = _safe_float(vr.get("vix_close", 20))
    vix_prev = _safe_float((data["vix_prev"] or {}).get("vix_close", vix_close))
    vix_chg = vix_close - vix_prev

    # ── Storage ──
    sr = data["storage_latest"] or {}
    storage_pct = _safe_float(sr.get("eu_storage_percent", 45))
    storage_norm = _safe_float(sr.get("seasonal_norm", 50))
    storage_dev = _safe_float(sr.get("deviation_from_norm", 0))

    # ── Indices ──
    geri_r = data["geri_row"] or {}
    geri_val = int(round(_safe_float(geri_r.get("value", 0))))
    geri_band = str(geri_r.get("band", "MODERATE"))
    geri_prev_val = int(round(_safe_float((data["geri_prev"] or {}).get("value", geri_val))))
    geri_delta = geri_val - geri_prev_val

    eeri_r = data["eeri_row"] or {}
    eeri_val = int(round(_safe_float(eeri_r.get("value", 0))))
    eeri_band = str(eeri_r.get("band", "ELEVATED"))
    eeri_prev_val = int(round(_safe_float((data["eeri_prev"] or {}).get("value", eeri_val))))
    eeri_delta = eeri_val - eeri_prev_val

    egsi_mr = data["egsi_m_row"] or {}
    egsi_m_val = round(_safe_float(egsi_mr.get("index_value", 0)), 1)
    egsi_m_band = str(egsi_mr.get("band", "MODERATE"))

    egsi_sr = data["egsi_s_row"] or {}
    egsi_s_val = round(_safe_float(egsi_sr.get("index_value", 0)), 1)
    egsi_s_band = str(egsi_sr.get("band", "MODERATE"))

    gc = BAND_COLORS.get(geri_band, "#f97316")
    ec = BAND_COLORS.get(eeri_band, "#ef4444")
    mgc = BAND_COLORS.get(egsi_m_band, "#f97316")
    sgc = BAND_COLORS.get(egsi_s_band, "#f97316")

    # ── Sentiment & arrows ──
    s_emoji, s_label, s_color = _sentiment(jkm_chg_pct)
    j_arrow = _arrow(jkm_chg)
    j_color = _chg_color(jkm_chg)
    t_arrow = _arrow(ttf_chg)
    t_color = _chg_color(ttf_chg)
    b_arrow = _arrow(brent_chg)
    b_color = _chg_color(brent_chg)
    v_arrow = _arrow(vix_chg)
    v_color = _chg_color(vix_chg)

    # ── Pre-computed strings ──
    trend_word = "rising" if jkm_chg_pct > 0.5 else ("falling" if jkm_chg_pct < -0.5 else "flat")
    storage_above_below = "above" if storage_dev >= 0 else "below"
    vix_desc = "elevated" if vix_close > 20 else "moderate"
    geri_risk_word = {"LOW": "low", "MODERATE": "moderate", "ELEVATED": "elevated",
                      "SEVERE": "severe", "CRITICAL": "critical"}.get(geri_band, "moderate")
    jkm_ttf_spread = round(jkm_price - (ttf_price / 3.412), 2) if ttf_price else 0.0
    arb_direction = "positive (JKM premium)" if jkm_ttf_spread > 0 else "negative (TTF premium)"
    pct_sign = "+" if jkm_chg_pct >= 0 else ""
    abs_chg_sign = "+" if jkm_chg >= 0 else ""

    geri_interp = (
        f"JKM LNG price movements today reflect {geri_risk_word} geopolitical supply risk. "
        f"GERI at {geri_val}/100 ({geri_band}) and EERI at {eeri_val}/100 ({eeri_band}) "
        f"signal {'heightened' if geri_val > 50 else 'contained'} stress across LNG supply corridors, "
        f"including Middle East shipping lanes and Russian supply disruption risk."
    )

    # ── Build charts ──
    jkm_all = data["jkm_all"]
    jkm_ytd = data["jkm_ytd"]
    jkm_1y = data["jkm_1y"]

    def _slice(rows, n):
        subset = rows[-n:] if len(rows) >= n else rows
        return [{"label": _fmt_short(r["date"]), "val": _safe_float(r["jkm_price"])} for r in subset]

    pts_7d = _slice(jkm_all, 7)
    pts_30d = _slice(jkm_all, 30)
    pts_90d = _slice(jkm_all, 90)
    pts_ytd = [{"label": _fmt_short(r["date"]), "val": _safe_float(r["jkm_price"])} for r in jkm_ytd]
    pts_1y = [{"label": _fmt_short(r["date"]), "val": _safe_float(r["jkm_price"])} for r in jkm_1y]
    pts_all = [{"label": _fmt_short(r["date"]), "val": _safe_float(r["jkm_price"])} for r in jkm_all]

    svg_7d = _build_jkm_svg(pts_7d)
    svg_30d = _build_jkm_svg(pts_30d)
    svg_90d = _build_jkm_svg(pts_90d)
    svg_ytd = _build_jkm_svg(pts_ytd)
    svg_1y = _build_jkm_svg(pts_1y if len(pts_1y) > 1 else pts_all)
    svg_all = _build_jkm_svg(pts_all)

    # ── Historical high/low ──
    h30 = data["hist_30d"]
    hytd = data["hist_ytd"]
    low30 = h30[0] if h30 else None
    high30 = h30[-1] if h30 else None
    low_ytd = hytd[0] if hytd else None
    high_ytd = hytd[-1] if hytd else None

    low30_val = _safe_float((low30 or {}).get("jkm_price", 0))
    high30_val = _safe_float((high30 or {}).get("jkm_price", 0))
    low_ytd_val = _safe_float((low_ytd or {}).get("jkm_price", 0))
    high_ytd_val = _safe_float((high_ytd or {}).get("jkm_price", 0))
    low30_date = _fmt_short((low30 or {}).get("date"))
    high30_date = _fmt_short((high30 or {}).get("date"))
    low_ytd_date = _fmt_short((low_ytd or {}).get("date"))
    high_ytd_date = _fmt_short((high_ytd or {}).get("date"))

    dist_ytd_high = round(high_ytd_val - jkm_price, 2) if high_ytd_val else 0.0
    dist_ytd_high_pct = round((dist_ytd_high / jkm_price) * 100, 1) if jkm_price else 0.0

    # ── Market insight (custom algorithms) ──
    insight = _run_jkm_insight(
        today_str, jkm_price, jkm_chg, jkm_chg_pct,
        ttf_price, brent_price, vix_close, storage_pct,
        geri_val, geri_band, eeri_val, eeri_band,
        data["alert_context"],
    )

    # ── Snapshot prose ──
    snap_para1 = (
        f"The JKM LNG price today stands at <strong>${jkm_price:.2f}/MMBtu</strong>, "
        f"moving <strong>{abs_chg_sign}{jkm_chg:.2f} ({pct_sign}{jkm_chg_pct:.2f}%)</strong> "
        f"over the last 24 hours as of {today_str}. "
        f"Market sentiment for Asia&rsquo;s key LNG benchmark reads <strong>{s_label}</strong>, "
        f"with price action reflecting current supply-demand dynamics across Pacific and Atlantic basins."
    )
    snap_para2 = (
        f"JKM prices have been <strong>{trend_word}</strong> over recent sessions, "
        f"influenced by Asian winter/summer demand cycles, European competition for LNG cargoes, "
        f"and geopolitical risk signals captured in EnergyRiskIQ&rsquo;s proprietary indices. "
        f"GERI at <strong>{geri_val}/100 ({geri_band})</strong> and EERI at "
        f"<strong>{eeri_val}/100 ({eeri_band})</strong> are key context indicators."
    )
    snap_para3 = (
        f"The JKM-TTF arbitrage spread currently stands at approximately "
        f"<strong>${jkm_ttf_spread:.2f}/MMBtu</strong> ({arb_direction}), "
        f"a key signal for cargo redirection between Asia and Europe. "
        f"EU gas storage at <strong>{storage_pct:.1f}%</strong> ({storage_above_below} the "
        f"{storage_norm:.1f}% seasonal norm) shapes European buyers&rsquo; willingness to bid "
        f"for Pacific cargoes, directly affecting JKM price levels."
    )

    # ── FAQ ──
    faq_entries = [
        ("What is JKM LNG?",
         "JKM (Japan Korea Marker) is Asia's primary LNG spot price benchmark, published by S&P Global Platts. It reflects the price of LNG delivered to Japan and Korea — the world's two largest LNG importers — and is used as the pricing reference for LNG spot cargoes across the Asia Pacific region."),
        ("How is JKM LNG priced?",
         "JKM is assessed daily by S&P Global Platts in US dollars per million British thermal units ($/MMBtu). It reflects competitive bids, offers, and transactions for LNG cargoes delivered within a 2-6 week window to Northeast Asia. EnergyRiskIQ tracks JKM daily from verified market data sources and enriches it with proprietary risk signals."),
        ("Why is JKM important for global energy markets?",
         "JKM is the world's leading Asian LNG benchmark and directly influences approximately one-third of global LNG trade. As Japan, Korea, and China account for over 50% of global LNG imports, JKM movements signal shifts in Asian energy demand, shipping logistics, and the global LNG supply-demand balance."),
        ("What is the difference between JKM and TTF?",
         "JKM reflects LNG prices in Asia (Japan Korea Marker), while TTF (Title Transfer Facility) is Europe's dominant natural gas benchmark. The JKM-TTF spread is a key indicator of global LNG arbitrage — when JKM trades at a premium to TTF, LNG cargoes flow towards Asia; when TTF is higher, Europe attracts more LNG shipments. EnergyRiskIQ tracks this spread as part of its LNG risk intelligence."),
        ("What factors affect JKM LNG prices?",
         "JKM is driven by: Asian demand (particularly from Japan, Korea, and China), European competition for LNG cargoes (TTF dynamics), shipping and freight constraints (Panama Canal, Red Sea disruptions), seasonal weather patterns (winter heating, summer cooling), oil-indexed long-term contract pricing linked to Brent crude, and geopolitical events affecting LNG supply routes."),
        ("Why do JKM LNG prices spike?",
         "JKM price spikes occur when Asian demand surges (extreme cold winter or hot summer), European gas storage is low and European buyers compete aggressively for LNG cargoes, LNG shipping is constrained (canal disruptions, weather events), or supply outages hit major LNG export facilities in Australia, Qatar, or the US Gulf Coast. EnergyRiskIQ's GERI and EERI indices provide early warning signals for such events."),
    ]

    faq_ld = json.dumps({
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": q,
                "acceptedAnswer": {"@type": "Answer", "text": a}
            }
            for q, a in faq_entries
        ]
    }, indent=2)

    dataset_ld = json.dumps({
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "WebPage",
                "name": "JKM LNG Price Chart (Live Daily Update) | Asia Gas Benchmark",
                "url": f"{BASE_URL}/data/jkm-lng-price-chart",
                "description": "Track the JKM LNG price chart with daily updates, historical trends, and global LNG market insights. Monitor Asia's key gas benchmark and market drivers.",
                "publisher": {"@type": "Organization", "name": "EnergyRiskIQ", "url": BASE_URL},
                "about": [
                    {"@type": "Thing", "name": "JKM LNG"},
                    {"@type": "Thing", "name": "LNG Price"},
                    {"@type": "Thing", "name": "Asia Natural Gas"},
                    {"@type": "Thing", "name": "Global LNG Market"},
                ]
            },
            {
                "@type": "Dataset",
                "name": "JKM LNG Daily Prices",
                "description": "Daily Japan Korea Marker (JKM) LNG spot prices, 24-hour changes, and historical data updated daily by EnergyRiskIQ.",
                "url": f"{BASE_URL}/data/jkm-lng-price-chart",
                "creator": {"@type": "Organization", "name": "EnergyRiskIQ", "url": BASE_URL},
                "publisher": {"@type": "Organization", "name": "EnergyRiskIQ", "url": BASE_URL},
                "license": f"{BASE_URL}/data-license",
                "isAccessibleForFree": True,
                "temporalCoverage": f"2024-01-01/{today_date}",
                "spatialCoverage": "Asia Pacific",
                "variableMeasured": [
                    {"@type": "PropertyValue", "name": "JKM LNG Price", "unitCode": "USD/MMBTU"},
                    {"@type": "PropertyValue", "name": "JKM 24h Change", "unitCode": "USD"},
                    {"@type": "PropertyValue", "name": "JKM-TTF Spread", "unitCode": "USD/MMBTU"},
                ],
                "measurementTechnique": "OilPriceAPI daily spot data; EnergyRiskIQ proprietary LNG data pipeline",
                "dateModified": today_date,
                "keywords": ["jkm lng price", "lng price chart", "japan korea marker", "asia lng benchmark", "jkm spot price"],
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Home", "item": BASE_URL},
                    {"@type": "ListItem", "position": 2, "name": "Data", "item": f"{BASE_URL}/data"},
                    {"@type": "ListItem", "position": 3, "name": "JKM LNG Price Chart",
                     "item": f"{BASE_URL}/data/jkm-lng-price-chart"},
                ]
            },
            {
                "@type": "FinancialProduct",
                "name": "JKM LNG (Japan Korea Marker)",
                "description": "The Japan Korea Marker (JKM) is Asia's primary LNG spot price benchmark, reflecting delivered LNG prices to Northeast Asia and used as the pricing standard for approximately one-third of global LNG trade.",
                "url": f"{BASE_URL}/data/jkm-lng-price-chart",
                "provider": {"@type": "Organization", "name": "EnergyRiskIQ", "url": BASE_URL},
            },
        ]
    }, indent=2)

    # ── FAQ HTML ──
    faq_html = ""
    for i, (q, a) in enumerate(faq_entries):
        faq_html += f"""<div class="jkm-faq-card" id="jkm-faq-{i}">
  <div class="jkm-faq-q" onclick="(function(el){{el.closest('.jkm-faq-card').classList.toggle('open')}})(this)">
    <span>{_html.escape(q)}</span><span class="jkm-faq-chevron">&#9660;</span>
  </div>
  <div class="jkm-faq-a">{_html.escape(a)}</div>
</div>"""

    # ── Assemble full HTML ──
    return f"""<script>
var l=document.getElementById('snap-loader');
if(l){{l.style.display='none';}}
document.body.style.overflow='';
</script>
<script type="application/ld+json">
{dataset_ld}
</script>
<script type="application/ld+json">
{faq_ld}
</script>
<style>
{_JKM_CSS}
</style>

<!-- ── ANTI-COPY PROTECTION ─────────────────────────────────────────── -->
<script>
(function(){{
  document.addEventListener('copy', function(e) {{
    var sel = window.getSelection ? window.getSelection().toString() : '';
    if (sel.length > 0) {{
      var attr = '\\n\\n[Data source: EnergyRiskIQ.com | CC BY-NC 4.0 — non-commercial use only]';
      e.clipboardData.setData('text/plain', sel + attr);
      e.preventDefault();
    }}
  }});
  document.addEventListener('contextmenu', function(e) {{
    var t = e.target;
    if (t && (t.classList.contains('jkm-protected') || t.closest('.jkm-protected'))) {{
      e.preventDefault();
    }}
  }});
}})();
</script>

<!-- ── STICKY PRICE BAR ──────────────────────────────────────────────── -->
<div class="jkm-sticky-bar">
  <span class="jkm-sticky-label">&#9875; JKM Today</span>
  <span class="jkm-sticky-price jkm-protected">${jkm_price:.2f}</span>
  <span class="jkm-sticky-chg" style="color:{j_color};">{j_arrow} {jkm_chg:+.2f} ({jkm_chg_pct:+.2f}%)</span>
  <span class="jkm-sticky-time">Updated: {today_str}</span>
  <a href="/users" class="jkm-sticky-cta">Free Alerts &rarr;</a>
</div>

<!-- ── NAV ───────────────────────────────────────────────────────────── -->
<nav class="nav">
  <div class="nav-inner">
    <a href="/" class="logo">
      <img src="/static/logo.png" alt="EnergyRiskIQ" style="height:28px">
      <span>EnergyRiskIQ</span>
    </a>
    <div style="display:flex;align-items:center;gap:1.5rem;">
      <a href="/indices/global-energy-risk-index" style="font-size:13px;color:#94a3b8;text-decoration:none;">GERI</a>
      <a href="/indices/europe-energy-risk-index" style="font-size:13px;color:#94a3b8;text-decoration:none;">EERI</a>
      <a href="/indices/europe-gas-stress-index" style="font-size:13px;color:#94a3b8;text-decoration:none;">EGSI</a>
      <a href="/data/energy-risk-snapshot" style="font-size:13px;color:#94a3b8;text-decoration:none;">Snapshot</a>
      <a href="/users" class="cta-btn-nav">Get Free Access</a>
    </div>
  </div>
</nav>

<!-- ── SECTION 1: HERO ───────────────────────────────────────────────── -->
<header class="hero">
  <div class="hero-date">&#128337; Updated Daily &nbsp;&bull;&nbsp; {today_str} &nbsp;&bull;&nbsp; Benchmark: Japan Korea Marker (JKM)</div>
  <h1>JKM LNG Price Chart</h1>
  <p class="hero-sub">
    Track the JKM LNG price chart with daily updates, historical trends, and global LNG market insights.
    Monitor Asia&rsquo;s key gas benchmark and its impact on global energy markets.
  </p>

  <!-- PRICE CARD -->
  <div class="jkm-hero-card">
    <div class="jkm-price-label">&#9875; Japan Korea Marker &mdash; JKM LNG &mdash; USD/MMBtu</div>
    <div class="jkm-price-main jkm-protected"><sup>$</sup>{jkm_price:.2f}</div>
    <div class="jkm-price-change jkm-protected" style="color:{j_color};">
      {j_arrow} {jkm_chg:+.2f} &nbsp;&bull;&nbsp; {jkm_chg_pct:+.2f}% day-over-day
    </div>
    <div>
      <span class="jkm-sentiment-badge"
        style="background:rgba(255,255,255,0.04);border:1px solid {s_color}33;color:{s_color};">
        {s_emoji} {s_label} Bias
      </span>
    </div>
    <div class="jkm-trust-line">
      <span>Benchmark: Japan Korea Marker (JKM)</span>
      <span class="jkm-trust-dot">&#9679;</span>
      <span>Data updated daily</span>
      <span class="jkm-trust-dot">&#9679;</span>
      <span>Source: OilPriceAPI &bull; {jkm_date}</span>
      <span class="jkm-trust-dot">&#9679;</span>
      <span>Asia&rsquo;s primary LNG benchmark</span>
    </div>
    <a href="/users" class="jkm-hero-cta">
      &#128276; Get LNG price alerts &amp; risk signals &rarr; Free Account
    </a>
    <span class="jkm-watermark-attr">EnergyRiskIQ.com</span>
  </div>

  <!-- Index badges -->
  <div style="display:flex;justify-content:center;gap:1rem;flex-wrap:wrap;margin-top:0.5rem;">
    <a href="/indices/global-energy-risk-index"
      style="font-size:12px;font-weight:600;color:{gc};border:1px solid {gc}33;border-radius:20px;padding:4px 14px;text-decoration:none;">
      GERI {geri_val}/100 &bull; {geri_band}
    </a>
    <a href="/indices/europe-energy-risk-index"
      style="font-size:12px;font-weight:600;color:{ec};border:1px solid {ec}33;border-radius:20px;padding:4px 14px;text-decoration:none;">
      EERI {eeri_val}/100 &bull; {eeri_band}
    </a>
    <span style="font-size:12px;font-weight:600;color:#94a3b8;border:1px solid rgba(148,163,184,0.2);border-radius:20px;padding:4px 14px;">
      VIX {vix_close:.1f} &bull; {vix_desc.title()} Volatility
    </span>
  </div>
</header>

<main class="page-body">

<!-- ── WIDGET ADVERTISE BANNER ─────────────────────────────────────────────── -->
<style>
.jkm-w-banner {{
  display: flex; align-items: center; justify-content: space-between; gap: 24px;
  background: linear-gradient(135deg, #15110a 0%, #1c1608 45%, #0f172a 100%);
  border: 1px solid rgba(212,160,23,0.35);
  border-radius: 16px; padding: 22px 26px; margin-bottom: 32px;
  position: relative; overflow: hidden;
}}
.jkm-w-banner::before {{
  content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px;
  background: linear-gradient(90deg, #d4a017, #f59e0b);
}}
.jkm-w-banner-glow {{
  position: absolute; top: -40%; right: -10%; width: 320px; height: 320px;
  background: radial-gradient(circle, rgba(212,160,23,0.16) 0%, transparent 70%);
  pointer-events: none;
}}
.jkm-w-banner-text {{ position: relative; z-index: 1; flex: 1 1 auto; min-width: 0; }}
.jkm-w-banner-tag {{
  display: inline-block; font-size: 10px; font-weight: 800; letter-spacing: 1.4px;
  text-transform: uppercase; color: #0a0f1e;
  background: linear-gradient(135deg, #d4a017, #f59e0b);
  padding: 3px 10px; border-radius: 20px; margin-bottom: 10px;
}}
.jkm-w-banner-title {{ font-size: 19px; font-weight: 800; color: #f8fafc; line-height: 1.3; margin: 0 0 6px; }}
.jkm-w-banner-title span {{ color: #d4a017; }}
.jkm-w-banner-desc {{ font-size: 13.5px; color: #94a3b8; line-height: 1.6; margin: 0; max-width: 640px; }}
.jkm-w-banner-desc strong {{ color: #cbd5e1; font-weight: 700; }}
.jkm-w-banner-cta {{
  position: relative; z-index: 1; flex: 0 0 auto;
  display: inline-flex; align-items: center; gap: 8px;
  background: linear-gradient(135deg, #d4a017, #f59e0b); color: #0a0f1e !important;
  text-decoration: none; font-weight: 800; font-size: 14px; white-space: nowrap;
  padding: 13px 24px; border-radius: 10px;
  box-shadow: 0 6px 22px rgba(212,160,23,0.22);
  transition: transform .15s ease, box-shadow .15s ease;
}}
.jkm-w-banner-cta:hover {{ transform: translateY(-2px); box-shadow: 0 10px 28px rgba(212,160,23,0.32); }}
@media (max-width: 720px) {{
  .jkm-w-banner {{ flex-direction: column; align-items: flex-start; gap: 16px; padding: 20px; }}
  .jkm-w-banner-cta {{ width: 100%; justify-content: center; }}
}}
</style>
<aside class="jkm-w-banner" aria-label="Free JKM LNG price widget for websites">
  <div class="jkm-w-banner-glow"></div>
  <div class="jkm-w-banner-text">
    <span class="jkm-w-banner-tag">&#9889; Free Embeddable Widget</span>
    <h2 class="jkm-w-banner-title">Put the <span>JKM LNG Price Widget</span> on Your Own Website &mdash; Free</h2>
    <p class="jkm-w-banner-desc">
      Embed a <strong>live JKM LNG price widget</strong> on your blog, app or dashboard in one line of code.
      Show real-time Asian LNG spot prices, <strong>market trend signals</strong>, energy-risk levels and the
      JKM&ndash;TTF spread &mdash; updated daily, mobile-responsive and free for commercial use.
    </p>
  </div>
  <a href="/widgets/jkm-lng-price" class="jkm-w-banner-cta">
    Get the Free Widget &rarr;
  </a>
</aside>

<!-- ── SECTION 2: MAIN CHART ─────────────────────────────────────────── -->
<div class="section-label" style="margin-bottom:20px;">&#128200; JKM LNG Price Chart</div>
<div class="jkm-chart-card">
  <h2 style="font-size:16px;font-weight:700;color:#e2e8f0;margin-bottom:14px;">
    JKM LNG Price Chart &mdash; Historical Daily Benchmark
  </h2>

  <!-- Time range tabs -->
  <div class="jkm-range-tabs">
    <button class="jkm-range-tab" onclick="switchJKM('7d')">7D</button>
    <button class="jkm-range-tab active" onclick="switchJKM('30d')">30D</button>
    <button class="jkm-range-tab" onclick="switchJKM('90d')">90D</button>
    <button class="jkm-range-tab" onclick="switchJKM('ytd')">YTD</button>
    <button class="jkm-range-tab" onclick="switchJKM('1y')">1Y</button>
    <button class="jkm-range-tab" onclick="switchJKM('all')">Since Launch</button>
  </div>

  <!-- Overlay toggles -->
  <div class="jkm-overlay-row">
    <span class="jkm-overlay-btn" title="TTF Gas overlay — unlock with free account">&#127470;&#127489; TTF Gas</span>
    <span class="jkm-overlay-btn" title="Brent Oil overlay — unlock with free account">&#128137; Brent Oil</span>
    <span class="jkm-overlay-btn" title="EU Gas Storage overlay — unlock with free account">&#128201; EU Storage</span>
    <span class="jkm-overlay-btn" title="VIX overlay — unlock with free account">&#128200; VIX</span>
    <a href="/users" style="font-size:10px;font-weight:700;color:#d4a017;text-decoration:none;
      padding:4px 12px;border-radius:20px;border:1px solid rgba(212,160,23,0.3);
      background:rgba(212,160,23,0.06);display:inline-flex;align-items:center;gap:5px;">
      &#128275; Pro: Spread View &amp; Correlation Toggle
    </a>
  </div>

  <!-- Charts -->
  <div class="jkm-chart-wrap">
    <div id="jkm-chart-7d"  class="jkm-chart-container">{svg_7d}</div>
    <div id="jkm-chart-30d" class="jkm-chart-container active">{svg_30d}</div>
    <div id="jkm-chart-90d" class="jkm-chart-container">{svg_90d}</div>
    <div id="jkm-chart-ytd" class="jkm-chart-container">{svg_ytd}</div>
    <div id="jkm-chart-1y"  class="jkm-chart-container">{svg_1y}</div>
    <div id="jkm-chart-all" class="jkm-chart-container">{svg_all}</div>
  </div>
  <div class="jkm-chart-note">
    Source: OilPriceAPI (daily closes) &bull; EnergyRiskIQ data pipeline &bull; $/MMBtu
  </div>

  <!-- Market context strip -->
  <div style="margin-top:20px;padding:16px 18px;background:rgba(255,255,255,0.02);
    border:1px solid rgba(255,255,255,0.06);border-radius:10px;">
    <div style="font-size:10px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;
      color:#94a3b8;margin-bottom:10px;">Cross-Market Context</div>
    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;" class="jkm-corr-grid">
      <div>
        <div style="font-size:10px;color:#94a3b8;font-weight:600;margin-bottom:3px;">TTF NAT GAS</div>
        <div class="jkm-protected" style="font-size:15px;font-weight:700;color:#e2e8f0;">&euro;{ttf_price:.2f}</div>
        <div style="font-size:11px;color:{t_color};">{t_arrow} {ttf_chg:+.2f} d/d</div>
      </div>
      <div>
        <div style="font-size:10px;color:#94a3b8;font-weight:600;margin-bottom:3px;">BRENT CRUDE</div>
        <div class="jkm-protected" style="font-size:15px;font-weight:700;color:#e2e8f0;">${brent_price:.2f}</div>
        <div style="font-size:11px;color:{b_color};">{b_arrow} {brent_chg:+.2f} d/d</div>
      </div>
      <div>
        <div style="font-size:10px;color:#94a3b8;font-weight:600;margin-bottom:3px;">VIX FEAR INDEX</div>
        <div class="jkm-protected" style="font-size:15px;font-weight:700;color:#e2e8f0;">{vix_close:.2f}</div>
        <div style="font-size:11px;color:{v_color};">{v_arrow} {vix_chg:+.2f} d/d</div>
      </div>
    </div>
  </div>

  <!-- CTA under chart -->
  <div style="margin-top:18px;text-align:center;">
    <a href="/users" style="font-size:13px;font-weight:700;color:{JKM_COLOR};
      border:1px solid rgba(212,160,23,0.3);border-radius:8px;padding:8px 22px;
      text-decoration:none;display:inline-block;">
      &#128275; Unlock LNG spreads &amp; correlations &rarr; Free account
    </a>
  </div>
</div>

<script>
function switchJKM(range) {{
  var charts = document.querySelectorAll('.jkm-chart-container');
  charts.forEach(function(c) {{ c.classList.remove('active'); }});
  var tabs = document.querySelectorAll('.jkm-range-tab');
  tabs.forEach(function(t) {{ t.classList.remove('active'); }});
  var el = document.getElementById('jkm-chart-' + range);
  if (el) el.classList.add('active');
  var btns = document.querySelectorAll('.jkm-range-tab');
  var rangeMap = {{'7d':0,'30d':1,'90d':2,'ytd':3,'1y':4,'all':5}};
  if (btns[rangeMap[range]]) btns[rangeMap[range]].classList.add('active');
}}
</script>

<!-- ── SECTION 3: DAILY MARKET SNAPSHOT ─────────────────────────────── -->
<div class="section-label" style="margin-bottom:20px;">&#128203; JKM LNG Market Snapshot &mdash; Today</div>
<div class="jkm-snapshot-card">
  <h2 style="font-size:18px;font-weight:700;color:#e2e8f0;margin-bottom:18px;">
    JKM LNG Market Snapshot &mdash; {today_str}
  </h2>
  <p class="jkm-snapshot-para">{snap_para1}</p>
  <p class="jkm-snapshot-para">{snap_para2}</p>
  <p class="jkm-snapshot-para">{snap_para3}</p>
  <div style="margin-top:18px;padding:14px 18px;background:rgba(212,160,23,0.06);
    border:1px solid rgba(212,160,23,0.12);border-radius:10px;font-size:13px;color:#94a3b8;">
    &#128204; JKM-TTF Spread: <strong style="color:#e2e8f0;" class="jkm-protected">${jkm_ttf_spread:.2f}/MMBtu</strong>
    &nbsp;&bull;&nbsp; EU Storage: <strong style="color:#e2e8f0;">{storage_pct:.1f}%</strong>
    &nbsp;&bull;&nbsp; Brent: <strong style="color:#e2e8f0;" class="jkm-protected">${brent_price:.2f}/bbl</strong>
  </div>
</div>

<!-- ── SECTION 4: GLOBAL LNG CONTEXT ────────────────────────────────── -->
<div class="section-label" style="margin-bottom:20px;">&#127758; Global LNG Market Overview</div>
<h2 style="font-size:20px;font-weight:700;color:#e2e8f0;margin-bottom:16px;">
  Global LNG Market Overview
</h2>
<div class="jkm-snapshot-card" style="margin-bottom:40px;">
  <p class="jkm-snapshot-para">
    <strong>Japan and Korea</strong> are the world&rsquo;s largest LNG importers, accounting for
    approximately 35% of global LNG demand. Japan relies on LNG for over 35% of its electricity
    generation following the post-Fukushima nuclear phase-down, while Korea uses LNG intensively
    for both power generation and industrial heating. Demand from these two nations anchors the JKM
    benchmark year-round, with pronounced seasonal spikes in winter (December–February) and
    summer cooling season (July–August).
  </p>
  <p class="jkm-snapshot-para">
    <strong>China</strong> has become the world&rsquo;s largest LNG importer and is the most
    volatile demand source. Rapid industrial growth, urban heating programmes, and coal-to-gas
    switching policies have made Chinese LNG import demand highly price-sensitive. When Chinese
    buyers enter the spot market aggressively, JKM prices spike rapidly — the 2021 energy crisis
    saw JKM reach record levels above $56/MMBtu.
  </p>
  <p class="jkm-snapshot-para">
    <strong>European competition</strong> fundamentally reshapes JKM pricing dynamics. As Europe
    shifted from Russian pipeline gas to LNG post-2022, European buyers began competing directly
    for Pacific cargoes. The JKM-TTF spread (currently <strong>${jkm_ttf_spread:.2f}/MMBtu</strong>)
    determines which market attracts flexible LNG cargoes. EU gas storage at
    <strong>{storage_pct:.1f}%</strong> vs the {storage_norm:.1f}% seasonal norm is a key variable
    in this arbitrage equation.
    &rarr; <a href="/data/europe-lng-supply-demand" style="color:{JKM_COLOR};">View Europe LNG Supply-Demand &rarr;</a>
  </p>
</div>

<!-- ── SECTION 5: CROSS-ASSET NAVIGATION ────────────────────────────── -->
<div class="section-label" style="margin-bottom:20px;">&#128279; Related Energy Market Indicators</div>
<h3 style="font-size:16px;font-weight:700;color:#e2e8f0;margin-bottom:16px;">
  Related Energy Market Indicators
</h3>
<div class="jkm-two-col">
  <a href="/data/ttf-gas-price-today" class="jkm-nav-card">
    <span class="jkm-nav-icon">&#127470;&#127489;</span>
    <div>
      <div class="jkm-nav-title">TTF Gas Price Today</div>
      <div class="jkm-nav-desc">Dutch TTF European gas benchmark &mdash; the key arbitrage reference for Atlantic vs Pacific LNG cargo flows. Currently &euro;{ttf_price:.2f}/MWh.</div>
      <div class="jkm-nav-link">View TTF Data &rarr;</div>
    </div>
  </a>
  <a href="/data/brent-crude-oil-price-today" class="jkm-nav-card">
    <span class="jkm-nav-icon">&#128137;</span>
    <div>
      <div class="jkm-nav-title">Brent Crude Oil Price Today</div>
      <div class="jkm-nav-desc">Brent crude is the reference for oil-indexed LNG long-term contracts. Currently ${brent_price:.2f}/bbl — key for JKM-Brent ratio analysis.</div>
      <div class="jkm-nav-link">View Brent Data &rarr;</div>
    </div>
  </a>
  <a href="/gas-storage-levels-in-europe" class="jkm-nav-card">
    <span class="jkm-nav-icon">&#128201;</span>
    <div>
      <div class="jkm-nav-title">Europe Gas Storage Levels</div>
      <div class="jkm-nav-desc">EU gas storage at {storage_pct:.1f}% ({storage_above_below} seasonal norm) directly shapes European LNG demand and JKM-TTF arbitrage flows.</div>
      <div class="jkm-nav-link">View Gas Storage &rarr;</div>
    </div>
  </a>
  <a href="/data/global-energy-risk-forecast" class="jkm-nav-card">
    <span class="jkm-nav-icon">&#127760;</span>
    <div>
      <div class="jkm-nav-title">Global Energy Risk Forecast</div>
      <div class="jkm-nav-desc">24-hour Brent &amp; TTF forecasts powered by EnergyRiskIQ&rsquo;s proprietary risk pipeline. Provides forward-looking context for JKM market positioning.</div>
      <div class="jkm-nav-link">View Forecast &rarr;</div>
    </div>
  </a>
</div>

<!-- ── SECTION 6: WHAT DRIVES JKM ───────────────────────────────────── -->
<div class="section-label" style="margin-bottom:20px;">&#129504; What Drives JKM LNG Prices?</div>
<h2 style="font-size:20px;font-weight:700;color:#e2e8f0;margin-bottom:20px;">
  What Drives JKM LNG Prices?
</h2>
<div class="jkm-two-col" style="margin-bottom:0;">
  <div class="jkm-driver-card">
    <div class="jkm-driver-num">01 / ASIAN DEMAND</div>
    <div class="jkm-driver-title">&#127758; Japan, Korea &amp; China LNG Imports</div>
    <div class="jkm-driver-desc">
      Japan and Korea provide the baseline JKM demand floor — Japan alone imports ~75 million tonnes
      per year (mtpa) of LNG. China is the swing demand factor: aggressive Chinese spot buying
      has driven the most violent JKM price spikes. Seasonal patterns are strong — winter
      heating demand (Dec–Feb) and summer cooling (Jul–Aug) are consistently price-positive.
    </div>
  </div>
  <div class="jkm-driver-card">
    <div class="jkm-driver-num">02 / EUROPEAN COMPETITION</div>
    <div class="jkm-driver-title">&#127482;&#127466; Europe vs Asia LNG Cargo Competition</div>
    <div class="jkm-driver-desc">
      Since 2022, Europe has competed directly with Asia for LNG cargoes. When TTF is high
      relative to JKM, Atlantic cargoes divert to Europe, reducing Pacific supply and
      lifting JKM. Current TTF at &euro;{ttf_price:.2f}/MWh vs JKM at ${jkm_price:.2f}/MMBtu
      creates a spread of ~${jkm_ttf_spread:.2f}/MMBtu favouring {'Asia' if jkm_ttf_spread > 0 else 'Europe'}.
      &rarr; <a href="/data/ttf-gas-price-today">TTF Gas Price Today</a>
    </div>
  </div>
  <div class="jkm-driver-card">
    <div class="jkm-driver-num">03 / SHIPPING &amp; FREIGHT</div>
    <div class="jkm-driver-title">&#9875; Shipping Constraints &amp; Canal Disruptions</div>
    <div class="jkm-driver-desc">
      LNG shipping economics are critical to JKM-TTF arbitrage viability. Panama Canal
      draught restrictions (particularly during La Niña drought years) add 15–20 days
      to US-to-Asia cargo routes, effectively tightening Pacific supply. Red Sea disruptions
      similarly impact Middle East and European LNG flows. GERI at {geri_val}/100 ({geri_band})
      captures current geopolitical shipping risk.
    </div>
  </div>
  <div class="jkm-driver-card">
    <div class="jkm-driver-num">04 / WEATHER</div>
    <div class="jkm-driver-title">&#10052; Seasonal Demand &mdash; Winter &amp; Summer</div>
    <div class="jkm-driver-desc">
      JKM is acutely weather-sensitive. Colder-than-expected winters in Japan, Korea, and
      China directly trigger emergency LNG procurement, sending spot prices sharply higher.
      Summer heat waves driving power demand for air conditioning in China and Korea are a
      growing JKM demand driver. La Niña/El Niño cycles create multi-year seasonal demand
      patterns that skilled traders monitor closely.
    </div>
  </div>
  <div class="jkm-driver-card" style="grid-column:1/-1;">
    <div class="jkm-driver-num">05 / OIL-LINKED CONTRACTS</div>
    <div class="jkm-driver-title">&#128137; Oil-Indexed LNG Contracts &amp; Brent Linkage</div>
    <div class="jkm-driver-desc">
      A significant portion of long-term LNG contracts in Asia are indexed to crude oil prices
      at a formula of approximately 13–14% of Brent. With Brent at ${brent_price:.2f}/bbl,
      the theoretical oil-linked LNG price is approximately
      <strong>${round(brent_price * 0.135, 2):.2f}/MMBtu</strong>.
      When JKM spot trades significantly above this level, buyers seek to renegotiate contracts.
      When below, LNG project economics for new supply come under pressure.
      &rarr; <a href="/data/brent-crude-oil-price-today">Brent Crude Oil Price Today</a>
    </div>
  </div>
</div>
<div style="margin-bottom:40px;"></div>

<!-- ── SECTION 7: ENERGY RISK INTELLIGENCE ──────────────────────────── -->
<div class="section-label" style="margin-bottom:20px;">&#9888; Energy Risk Signals Behind LNG Prices</div>
<h2 style="font-size:20px;font-weight:700;color:#e2e8f0;margin-bottom:20px;">
  Energy Risk Signals Behind LNG Prices
</h2>
<div class="jkm-three-col">
  <div class="jkm-risk-card">
    <a href="/indices/global-energy-risk-index" style="text-decoration:none;color:inherit;">
      <div class="jkm-risk-name">Global Energy Risk Index</div>
      <div class="jkm-risk-value jkm-protected" style="color:{gc};">{geri_val}</div>
      <div class="jkm-risk-band" style="color:{gc};">{geri_band}</div>
      <div class="jkm-risk-desc">{_sign(geri_delta)}{geri_delta}pt vs yesterday &bull; 0&ndash;100 scale</div>
    </a>
  </div>
  <div class="jkm-risk-card">
    <a href="/indices/europe-energy-risk-index" style="text-decoration:none;color:inherit;">
      <div class="jkm-risk-name">European Energy Risk Index</div>
      <div class="jkm-risk-value jkm-protected" style="color:{ec};">{eeri_val}</div>
      <div class="jkm-risk-band" style="color:{ec};">{eeri_band}</div>
      <div class="jkm-risk-desc">{_sign(eeri_delta)}{eeri_delta}pt vs yesterday &bull; Europe focus</div>
    </a>
  </div>
  <div class="jkm-risk-card">
    <a href="/indices/europe-gas-stress-index" style="text-decoration:none;color:inherit;">
      <div class="jkm-risk-name">Energy Geopolitical Stress</div>
      <div class="jkm-risk-value jkm-protected" style="color:{mgc};">{egsi_m_val:.1f}</div>
      <div class="jkm-risk-band" style="color:{mgc};">{egsi_m_band}</div>
      <div class="jkm-risk-desc">EGSI-M: geopolitical supply stress signal</div>
    </a>
  </div>
</div>
<div class="jkm-risk-interp-card">
  <div style="font-size:10px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;
    color:{JKM_COLOR};margin-bottom:12px;">&#128204; Risk Interpretation</div>
  <p style="font-size:15px;color:#cbd5e1;line-height:1.8;margin-bottom:12px;">
    {_html.escape(geri_interp)}
  </p>
  <p style="font-size:14px;color:#94a3b8;line-height:1.75;margin-bottom:16px;">
    EGSI-S (Shipping &amp; Supply Stress): <strong style="color:{sgc};">{egsi_s_val:.1f} &mdash; {egsi_s_band}</strong> &bull;
    EnergyRiskIQ&rsquo;s proprietary indicators suggest
    {'supply chain pressures are elevating LNG price risk — early warning signals are active.' if geri_val > 60 else 'current risk levels are being priced in without unusual supply stress.'}
  </p>
  <a href="/users" style="font-size:13px;font-weight:700;color:{JKM_COLOR};
    border:1px solid rgba(212,160,23,0.3);border-radius:8px;padding:8px 22px;
    text-decoration:none;display:inline-block;">
    &#128275; Access full risk dashboard &rarr; Free account
  </a>
</div>

<!-- ── SECTION 8: JKM vs TTF ─────────────────────────────────────────── -->
<div class="section-label" style="margin-bottom:20px;">&#128200; JKM vs TTF Gas Price Spread</div>
<h2 style="font-size:20px;font-weight:700;color:#e2e8f0;margin-bottom:20px;">
  JKM vs TTF Gas Price Spread &mdash; Arbitrage Dynamics
</h2>
<div class="jkm-spread-card">
  <div class="jkm-spread-title">&#128200; JKM-TTF Arbitrage &mdash; What the Spread Signals</div>
  <div class="jkm-spread-desc">
    The JKM-TTF spread is the world&rsquo;s most important LNG arbitrage signal. When JKM
    (currently <strong style="color:{JKM_COLOR};">${jkm_price:.2f}/MMBtu</strong>) trades at a premium to
    TTF (<strong style="color:#60a5fa;">&euro;{ttf_price:.2f}/MWh</strong>, ~${round(ttf_price/3.412,2):.2f}/MMBtu equivalent),
    flexible LNG cargoes are directed to Asia. When TTF is higher, Europe outbids Asia.
    The current spread of approximately <strong class="jkm-protected">${jkm_ttf_spread:.2f}/MMBtu</strong>
    signals <strong>{arb_direction}</strong> — meaning flexible cargoes are currently more
    attracted to {'Asian buyers' if jkm_ttf_spread > 0 else 'European buyers'}.
    <br><br>
    This dynamic means European gas storage levels (currently {storage_pct:.1f}%, {storage_above_below}
    seasonal norm) directly set the floor for JKM prices. Low European storage creates urgent
    European LNG buying, diverting cargoes from Asia and lifting JKM.
    <br><br>
    <a href="/data/ttf-gas-price-today">View TTF Gas Price Today &rarr;</a>
  </div>
</div>
<div class="jkm-spread-card">
  <div class="jkm-spread-title">&#9875; Cargo Redirection &mdash; Atlantic to Pacific</div>
  <div class="jkm-spread-desc">
    US Gulf Coast LNG (Sabine Pass, Freeport, Sabine) is the primary source of flexible global
    supply — these cargoes can be directed to either Europe or Asia based on the JKM-TTF spread.
    Middle East LNG (Qatar, UAE) has contractual obligations but also places spot volumes.
    Australian LNG is predominantly contracted to Japan/Korea but spot cargoes influence JKM.
    When shipping costs are ~$1.50–2.00/MMBtu for a US-to-Asia cargo, a spread above this
    threshold makes Atlantic-to-Pacific flows economically viable, supporting JKM at or above
    those levels.
  </div>
</div>
<div class="jkm-spread-card" style="margin-bottom:40px;">
  <div class="jkm-spread-title">&#128307; Market Imbalance Signals</div>
  <div class="jkm-spread-desc">
    Sustained JKM premiums above $3–4/MMBtu vs TTF (after freight) signal structural Asian supply
    tightness — a potential medium-term price floor. Sustained TTF premiums indicate European
    supply stress, which historically also eventually lifts JKM as storage draw-downs end.
    EnergyRiskIQ&rsquo;s EERI at {eeri_val}/100 ({eeri_band}) reflects current European gas supply
    stress, a leading indicator for JKM arbitrage pressure.
    <br><br>
    <a href="/data/europe-lng-supply-demand">View Europe LNG Supply-Demand &rarr;</a>
  </div>
</div>

<!-- ── SECTION 9: HISTORICAL ANALYSIS ───────────────────────────────── -->
<div class="section-label" style="margin-bottom:20px;">&#128199; JKM LNG Price History &amp; Key Levels</div>
<h2 style="font-size:20px;font-weight:700;color:#e2e8f0;margin-bottom:20px;">
  JKM LNG Price History &amp; Key Levels
</h2>
<div class="jkm-four-col">
  <div class="jkm-hist-card">
    <div class="jkm-hist-label">30D Low</div>
    <div class="jkm-hist-value jkm-protected" style="color:#ef4444;">${low30_val:.2f}</div>
    <div class="jkm-hist-date">{low30_date}</div>
  </div>
  <div class="jkm-hist-card">
    <div class="jkm-hist-label">30D High</div>
    <div class="jkm-hist-value jkm-protected" style="color:#22c55e;">${high30_val:.2f}</div>
    <div class="jkm-hist-date">{high30_date}</div>
  </div>
  <div class="jkm-hist-card">
    <div class="jkm-hist-label">YTD Low</div>
    <div class="jkm-hist-value jkm-protected" style="color:#ef4444;">${low_ytd_val:.2f}</div>
    <div class="jkm-hist-date">{low_ytd_date}</div>
  </div>
  <div class="jkm-hist-card">
    <div class="jkm-hist-label">YTD High</div>
    <div class="jkm-hist-value jkm-protected" style="color:#22c55e;">${high_ytd_val:.2f}</div>
    <div class="jkm-hist-date">{high_ytd_date}</div>
  </div>
</div>
<div style="background:var(--card);border:1px solid var(--border);border-radius:12px;
  padding:20px 24px;margin-bottom:24px;">
  <div style="font-size:11px;font-weight:700;letter-spacing:1px;text-transform:uppercase;
    color:#94a3b8;margin-bottom:14px;">Key Level Analysis</div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
    <div>
      <div style="font-size:12px;color:#94a3b8;margin-bottom:3px;">30D Range</div>
      <div class="jkm-protected" style="font-size:14px;font-weight:700;color:#e2e8f0;">${low30_val:.2f} &ndash; ${high30_val:.2f}/MMBtu</div>
    </div>
    <div>
      <div style="font-size:12px;color:#94a3b8;margin-bottom:3px;">30D Range Width</div>
      <div class="jkm-protected" style="font-size:14px;font-weight:700;color:#e2e8f0;">${(high30_val - low30_val):.2f} ({round((high30_val - low30_val) / low30_val * 100, 1) if low30_val else 0:.1f}%)</div>
    </div>
    <div>
      <div style="font-size:12px;color:#94a3b8;margin-bottom:3px;">Distance from YTD High</div>
      <div class="jkm-protected" style="font-size:14px;font-weight:700;color:{'#ef4444' if dist_ytd_high > 0 else '#22c55e'};">
        {'${:.2f} ({:.1f}%) below YTD high'.format(abs(dist_ytd_high), abs(dist_ytd_high_pct)) if dist_ytd_high > 0 else 'At or above YTD high'}
      </div>
    </div>
    <div>
      <div style="font-size:12px;color:#94a3b8;margin-bottom:3px;">Oil-Indexed Reference</div>
      <div class="jkm-protected" style="font-size:14px;font-weight:700;color:#e2e8f0;">${round(brent_price * 0.135, 2):.2f}/MMBtu (13.5% Brent)</div>
    </div>
  </div>
  <div style="margin-top:14px;font-size:12px;color:#64748b;">
    &#8594; <a href="/research/global-energy-risk-timeline" style="color:{JKM_COLOR};text-decoration:none;">
      Global Energy Risk Timeline &mdash; LNG price history &amp; key market events
    </a>
  </div>
</div>

<!-- Historical context paragraphs -->
<div style="background:var(--card);border:1px solid var(--border);border-radius:12px;
  padding:20px 24px;margin-bottom:40px;">
  <div style="font-size:11px;font-weight:700;letter-spacing:1px;text-transform:uppercase;
    color:#94a3b8;margin-bottom:14px;">Seasonal &amp; Cyclical Trends</div>
  <p style="font-size:14px;color:#94a3b8;line-height:1.75;margin-bottom:0;">
    JKM historically peaks in winter (December–February, driven by heating demand in Japan and Korea)
    and in early summer (June–August, driven by Chinese cooling demand). The shoulder seasons
    (March–May and September–November) typically see lower JKM as storage injections and mild
    weather reduce demand urgency. The all-time JKM high was $56.33/MMBtu (December 2021),
    driven by the European gas crisis and simultaneous Asian demand surge.
    Current YTD JKM has ranged ${low_ytd_val:.2f}–${high_ytd_val:.2f}/MMBtu ({low_ytd_date}–{high_ytd_date}),
    with the benchmark currently trading at <strong style="color:#e2e8f0;">${jkm_price:.2f}/MMBtu</strong>
    — {'above' if jkm_price > (low_ytd_val + high_ytd_val) / 2 else 'below'} the YTD midpoint.
  </p>
</div>

<!-- ── SECTION 10: TODAY'S LNG MARKET INSIGHT ────────────────────────── -->
<div class="section-label" style="margin-bottom:20px;">&#128161; Today&rsquo;s LNG Market Insight</div>
<div class="jkm-insight-card">
  <h2 style="font-size:18px;font-weight:700;color:#e2e8f0;margin-bottom:20px;">
    Today&rsquo;s LNG Market Insight
  </h2>
  <div class="jkm-insight-item">
    <div class="jkm-insight-section-title">What happened today</div>
    <div class="jkm-insight-body">{_html.escape(insight['what_happened'])}</div>
  </div>
  <div class="jkm-insight-item">
    <div class="jkm-insight-section-title">Why it matters</div>
    <div class="jkm-insight-body">{_html.escape(insight['why_matters'])}</div>
  </div>
  <div class="jkm-insight-item" style="margin-bottom:0;">
    <div class="jkm-insight-section-title">What to watch next</div>
    <div class="jkm-insight-body">{_html.escape(insight['what_to_watch'])}</div>
  </div>
  <div style="margin-top:18px;font-size:10px;color:#64748b;">
    Analysis generated by EnergyRiskIQ&rsquo;s proprietary LNG market intelligence engine (Custom Algorithms)
    &bull; {today_str} &bull; Not financial advice.
  </div>
</div>

<!-- ── SECTION 11: CONVERSION BLOCK ──────────────────────────────────── -->
<div class="jkm-cta-card">
  <div class="jkm-cta-label">Daily LNG Market Intelligence</div>
  <h2 class="jkm-cta-h2">Get Ahead of LNG Market Moves</h2>
  <p class="jkm-cta-sub">
    Get daily JKM LNG alerts, spread monitoring, energy risk signals, and market interpretation
    from EnergyRiskIQ&rsquo;s proprietary analysis pipeline.
  </p>
  <div class="jkm-cta-benefits">
    <span class="jkm-cta-benefit">JKM LNG daily price alerts</span>
    <span class="jkm-cta-benefit">JKM-TTF spread monitoring</span>
    <span class="jkm-cta-benefit">GERI &amp; EERI risk signals</span>
    <span class="jkm-cta-benefit">Daily market interpretation</span>
  </div>
  <a href="/users" class="jkm-cta-btn">&#128275; Create Free Account</a>
  <div class="jkm-cta-credits">No credit card required &bull; Free plan available</div>
</div>

<!-- ── SECTION 12: FAQ ────────────────────────────────────────────────── -->
<div class="section-label" style="margin-bottom:20px;">&#128218; JKM LNG Price &mdash; FAQs</div>
<h2 style="font-size:20px;font-weight:700;color:#e2e8f0;margin-bottom:20px;">
  JKM LNG Price &mdash; Frequently Asked Questions
</h2>
{faq_html}
<div style="margin-bottom:40px;"></div>

<!-- ── SECTION 13: INTERNAL LINKING FOOTER ───────────────────────────── -->
<div class="jkm-link-footer">
  <div class="jkm-link-section">
    <div class="jkm-link-section-title">&#128201; Data</div>
    <div class="jkm-link-grid">
      <a href="/data/europe-lng-supply-demand" class="jkm-link-pill">&#128168; LNG Supply-Demand</a>
      <a href="/data/ttf-gas-price-today" class="jkm-link-pill">&#127470;&#127489; TTF Gas Price</a>
      <a href="/data/brent-crude-oil-price-today" class="jkm-link-pill">&#128137; Brent Oil Price</a>
      <a href="/gas-storage-levels-in-europe" class="jkm-link-pill">&#128201; Gas Storage</a>
      <a href="/data/energy-risk-snapshot" class="jkm-link-pill">&#128248; Risk Snapshot</a>
      <a href="/data/global-energy-risk-forecast" class="jkm-link-pill">&#127760; Energy Forecast</a>
    </div>
  </div>
  <div class="jkm-link-section">
    <div class="jkm-link-section-title">&#128200; Indices</div>
    <div class="jkm-link-grid">
      <a href="/indices/global-energy-risk-index" class="jkm-link-pill">&#127760; Global Energy Risk Index</a>
      <a href="/indices/europe-energy-risk-index" class="jkm-link-pill">&#127482;&#127466; Europe Energy Risk Index</a>
      <a href="/indices/europe-gas-stress-index" class="jkm-link-pill">&#9889; Europe Gas Stress Index</a>
    </div>
  </div>
  <div class="jkm-link-section">
    <div class="jkm-link-section-title">&#128218; Research</div>
    <div class="jkm-link-grid">
      <a href="/research/global-energy-risk-timeline" class="jkm-link-pill">&#128337; Global Energy Risk Timeline</a>
      <a href="/research/global-energy-risk-index" class="jkm-link-pill">&#128202; GERI Research</a>
      <a href="/research/europe-energy-risk-index" class="jkm-link-pill">&#128202; EERI Research</a>
    </div>
  </div>
  <div class="jkm-link-section">
    <div class="jkm-link-section-title">&#128275; License</div>
    <div class="jkm-link-grid">
      <a href="/data-license" class="jkm-link-pill">&#128221; Data License &amp; Usage Terms</a>
    </div>
  </div>
</div>

<!-- ── CITATION & REFERENCE ──────────────────────────────────────────── -->
<div class="jkm-cite-card">
  <div style="font-size:13px;font-weight:700;color:#e2e8f0;margin-bottom:10px;">
    &#128221; Citation &amp; Attribution
  </div>
  <div class="jkm-cite-desc">
    EnergyRiskIQ publishes JKM LNG price data for informational purposes. If referencing this data,
    please attribute as follows. All data is subject to the
    <a href="/data-license" style="color:{JKM_COLOR};">EnergyRiskIQ Data License</a>.
    Not for commercial redistribution without prior written consent.
  </div>
  <pre class="jkm-cite-code">EnergyRiskIQ. <em>"JKM LNG Price Chart (Japan Korea Marker – Daily Benchmark)."</em>
EnergyRiskIQ, <em>{today_str}</em>.
<a href="{BASE_URL}/data/jkm-lng-price-chart">{BASE_URL}/data/jkm-lng-price-chart</a>

Data sources: OilPriceAPI (JKM spot), EnergyRiskIQ proprietary risk pipeline.
License: <a href="{BASE_URL}/data-license">{BASE_URL}/data-license</a>
</pre>
</div>

</main>
"""


# ─────────────────────────────────────────────────────────────────────────────
# Route
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/data/jkm-lng-price-chart")
async def jkm_price_chart_page():
    """JKM LNG Price Chart — daily Japan Korea Marker benchmark with full market context."""

    async def _stream():
        yield _JKM_LOADER_HTML
        try:
            data = await asyncio.get_event_loop().run_in_executor(None, _fetch_jkm_data)
            html_body = await asyncio.get_event_loop().run_in_executor(None, _build_jkm_html, data)
            yield html_body
        except Exception as exc:
            logger.error(f"JKM chart page error: {exc}", exc_info=True)
            yield (
                "<script>document.getElementById('snap-loader') && "
                "(document.getElementById('snap-loader').innerHTML = "
                "'<p style=\"color:#ef4444;text-align:center;padding:2rem;\">Data temporarily unavailable. Please try again.</p>');"
                "</script>"
            )

    return StreamingResponse(_stream(), media_type="text/html")
