"""
Brent Crude Oil Price Today Page
Route: /data/brent-crude-oil-price-today
SEO-optimized live Brent crude oil price page with charts, risk intelligence, and market context.
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
    _build_infographic_html, _fetch_infographic_watchlist,
    _run_snapshot_engine, _compute_fingerprint,
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


def _fmt_date(d):
    try:
        return d.strftime("%b %-d") if d else "—"
    except Exception:
        return str(d)


def _sentiment_label(chg_pct: float) -> tuple:
    """Return (emoji, label, color) for price sentiment."""
    if chg_pct >= 1.0:
        return "&#129001;", "Bullish", "#22c55e"
    elif chg_pct <= -1.0:
        return "&#128997;", "Bearish", "#ef4444"
    else:
        return "&#9898;", "Neutral", "#94a3b8"


def _build_brent_svg_chart(data_points, color="#f97316", height=160):
    """Build a server-side SVG line+area chart from a list of {label, val} dicts."""
    if not data_points or len(data_points) < 2:
        return "<div style='height:80px;display:flex;align-items:center;justify-content:center;color:#475569;font-size:12px;'>Chart data loading…</div>"

    vals = [p["val"] for p in data_points if p.get("val") is not None]
    if len(vals) < 2:
        return ""

    W, H = 560, height
    PL, PR, PT, PB = 44, 12, 14, 34
    cw = W - PL - PR
    ch = H - PT - PB

    vmin = min(vals) * 0.997
    vmax = max(vals) * 1.003
    rng = vmax - vmin or 1

    n = len(data_points)
    step = cw / (n - 1)

    pts = []
    for i, pt in enumerate(data_points):
        v = pt.get("val")
        if v is None:
            continue
        x = PL + i * step
        y = PT + ch - ((v - vmin) / rng) * ch
        pts.append((x, y, v))

    # Area path
    path_d = f"M {pts[0][0]:.1f} {pts[0][1]:.1f}"
    for x, y, _ in pts[1:]:
        path_d += f" L {x:.1f} {y:.1f}"
    bot_y = PT + ch
    area_d = path_d + f" L {pts[-1][0]:.1f} {bot_y} L {pts[0][0]:.1f} {bot_y} Z"

    gid = "brentGrad"
    area_svg = (
        f'<defs><linearGradient id="{gid}" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0%" stop-color="{color}" stop-opacity="0.22"/>'
        f'<stop offset="100%" stop-color="{color}" stop-opacity="0.02"/>'
        f'</linearGradient></defs>'
        f'<path d="{area_d}" fill="url(#{gid})"/>'
        f'<path d="{path_d}" fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round"/>'
    )

    # Y-axis labels
    y_top = PT
    y_bot = PT + ch
    mid_v = (vmin + vmax) / 2
    mid_y = PT + ch / 2
    ax_svg = (
        f'<line x1="{PL}" y1="{y_bot:.1f}" x2="{W-PR}" y2="{y_bot:.1f}" stroke="rgba(255,255,255,0.08)" stroke-width="1"/>'
        f'<line x1="{PL}" y1="{mid_y:.1f}" x2="{W-PR}" y2="{mid_y:.1f}" stroke="rgba(255,255,255,0.05)" stroke-width="1" stroke-dasharray="3 3"/>'
        f'<text x="{PL-4}" y="{y_top+5}" text-anchor="end" font-size="9" fill="#94a3b8" font-family="Inter,sans-serif">${vmax:.0f}</text>'
        f'<text x="{PL-4}" y="{mid_y+3}" text-anchor="end" font-size="9" fill="#94a3b8" font-family="Inter,sans-serif">${mid_v:.0f}</text>'
        f'<text x="{PL-4}" y="{y_bot}" text-anchor="end" font-size="9" fill="#94a3b8" font-family="Inter,sans-serif">${vmin:.0f}</text>'
    )

    # X-axis labels — show at most 8 ticks
    max_ticks = 8
    tick_step = max(1, n // max_ticks)
    tick_svg = ""
    for i, pt in enumerate(data_points):
        if i % tick_step == 0 or i == n - 1:
            x = PL + i * step
            lbl = str(pt.get("label", ""))
            tick_svg += (
                f'<text x="{x:.1f}" y="{y_bot + 20}" text-anchor="middle" '
                f'font-size="9" fill="#94a3b8" font-family="Inter,sans-serif">{lbl}</text>'
            )

    # Current price dot
    last_x, last_y, last_v = pts[-1]
    dot_svg = (
        f'<circle cx="{last_x:.1f}" cy="{last_y:.1f}" r="4" fill="{color}" stroke="#0f172a" stroke-width="2"/>'
        f'<text x="{last_x:.1f}" y="{last_y-8:.1f}" text-anchor="middle" font-size="9" fill="{color}" font-weight="700" font-family="Inter,sans-serif">${last_v:.2f}</text>'
    )

    return (
        f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" '
        f'style="width:100%;display:block;overflow:visible">'
        f'{ax_svg}{area_svg}{tick_svg}{dot_svg}'
        f'</svg>'
    )


# ─────────────────────────────────────────────────────────────────────────────
# Loader HTML
# ─────────────────────────────────────────────────────────────────────────────

_BRENT_LOADER_HTML = _LOADER_HTML.replace(
    "Global Energy Risk Snapshot | EnergyRiskIQ",
    "Brent Crude Oil Price Today (Live Daily Update) | EnergyRiskIQ",
).replace(
    'name="description" content="Live global energy risk snapshot. Current GERI, EERI and EGSI-M index values with Brent crude, TTF gas, VIX and LNG market prices."',
    'name="description" content="Track the Brent crude oil price today with daily updates, charts, and market insights. Monitor global oil trends and energy risk signals."',
).replace(
    'rel="canonical" href="https://energyriskiq.com/data/energy-risk-snapshot"',
    'rel="canonical" href="https://energyriskiq.com/data/brent-crude-oil-price-today"',
).replace(
    "Fetching GERI\u00a0&\u00a0EERI indices\u2026",
    "Fetching Brent price & risk data\u2026",
).replace(
    '<span class="ld-tag">GERI</span>\n    <span class="ld-tag">EERI</span>\n    <span class="ld-tag">EGSI&#8209;M</span>\n    <span class="ld-tag">Brent</span>\n    <span class="ld-tag">TTF</span>',
    '<span class="ld-tag">Brent</span>\n    <span class="ld-tag">WTI</span>\n    <span class="ld-tag">GERI</span>\n    <span class="ld-tag">EERI</span>\n    <span class="ld-tag">VIX</span>',
)


# ─────────────────────────────────────────────────────────────────────────────
# Additional CSS
# ─────────────────────────────────────────────────────────────────────────────

_BRENT_CSS = """
/* ── Brent Page Specific ─────────────────────────────────────────────── */
.brent-hero-price-card {
  background: linear-gradient(135deg, #1a0e03 0%, #1e1108 50%, #0f172a 100%);
  border: 1px solid rgba(249,115,22,0.3);
  border-radius: 20px;
  padding: 32px 36px;
  margin-bottom: 40px;
  position: relative;
  overflow: hidden;
  max-width: 760px;
  margin-left: auto;
  margin-right: auto;
}
.brent-hero-price-card::before {
  content: '';
  position: absolute; top: 0; left: 0; right: 0; height: 3px;
  background: linear-gradient(90deg, #f97316, rgba(249,115,22,0.2));
}
.brent-price-label {
  font-size: 11px; font-weight: 700; letter-spacing: 2px;
  text-transform: uppercase; color: #f97316; margin-bottom: 8px;
}
.brent-price-main {
  font-size: 52px; font-weight: 900; line-height: 1;
  color: #f97316; font-variant-numeric: tabular-nums;
  margin-bottom: 8px;
}
.brent-price-main sup { font-size: 28px; font-weight: 700; vertical-align: top; margin-top: 6px; }
.brent-price-unit { font-size: 15px; font-weight: 500; color: #94a3b8; }
.brent-price-change {
  font-size: 18px; font-weight: 700; margin-bottom: 12px;
}
.brent-sentiment-badge {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 6px 16px; border-radius: 20px;
  font-size: 12px; font-weight: 700; letter-spacing: 0.06em;
  text-transform: uppercase;
}
.brent-trust-line {
  font-size: 11px; color: #94a3b8; margin-top: 16px;
  display: flex; gap: 16px; flex-wrap: wrap; align-items: center;
}
.brent-trust-dot { color: #334155; }
.brent-hero-cta {
  display: inline-flex; align-items: center; gap: 8px;
  margin-top: 20px;
  padding: 10px 22px; border-radius: 8px;
  background: rgba(249,115,22,0.12); border: 1px solid rgba(249,115,22,0.35);
  color: #f97316; font-size: 13px; font-weight: 700;
  text-decoration: none; transition: all 0.2s;
}
.brent-hero-cta:hover { background: rgba(249,115,22,0.22); }

/* ── Sticky Price Bar ─────────────────────────────────────────────────── */
.brent-sticky-bar {
  position: fixed; bottom: 0; left: 0; right: 0; z-index: 900;
  background: rgba(15,23,42,0.95); backdrop-filter: blur(8px);
  border-top: 1px solid rgba(249,115,22,0.2);
  padding: 8px 20px;
  display: flex; align-items: center; justify-content: space-between;
  font-size: 13px;
}
.brent-sticky-label { color: #94a3b8; font-weight: 600; letter-spacing: 0.05em; }
.brent-sticky-price { color: #f97316; font-weight: 800; font-size: 15px; margin: 0 8px; }
.brent-sticky-chg { font-weight: 600; }
.brent-sticky-time { color: #64748b; font-size: 11px; }
.brent-sticky-cta {
  padding: 5px 14px; border-radius: 6px;
  background: rgba(249,115,22,0.15); border: 1px solid rgba(249,115,22,0.3);
  color: #f97316; font-size: 11px; font-weight: 700;
  text-decoration: none; letter-spacing: 0.05em; white-space: nowrap;
}
@media (max-width: 640px) {
  .brent-sticky-bar { padding: 6px 10px; font-size: 11px; flex-wrap: wrap; gap: 4px; }
  .brent-sticky-time { display: none; }
  .brent-sticky-label { display: none; }
  .brent-sticky-price { font-size: 14px; margin: 0 4px; }
}

/* ── Chart Section ────────────────────────────────────────────────────── */
.brent-chart-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 24px;
  margin-bottom: 40px;
  overflow: hidden;
}
.brent-range-tabs {
  display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 20px;
}
.brent-range-tab {
  padding: 5px 14px; border-radius: 6px;
  font-size: 11px; font-weight: 700; letter-spacing: 0.06em;
  text-transform: uppercase; cursor: pointer; border: none;
  background: rgba(255,255,255,0.04);
  color: #64748b; transition: all 0.2s;
}
.brent-range-tab.active, .brent-range-tab:hover {
  background: rgba(249,115,22,0.15);
  color: #f97316;
}
.brent-overlay-toggles {
  display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 16px;
}
.brent-overlay-btn {
  padding: 4px 12px; border-radius: 20px;
  font-size: 10px; font-weight: 700; letter-spacing: 0.08em;
  text-transform: uppercase; cursor: pointer; border: none;
  background: rgba(255,255,255,0.04); color: #64748b;
  transition: all 0.2s;
}
.brent-overlay-btn.on { background: rgba(96,165,250,0.15); color: #60a5fa; }
.brent-chart-wrap {
  width: 100%; overflow-x: hidden;
}
.brent-chart-container { display: none; }
.brent-chart-container.active { display: block; }
.brent-chart-note {
  font-size: 11px; color: #64748b; margin-top: 8px; text-align: right;
}

/* ── Market Snapshot Prose ────────────────────────────────────────────── */
.brent-snapshot-card {
  background: linear-gradient(135deg, #111827 0%, #0f172a 100%);
  border: 1px solid rgba(249,115,22,0.18);
  border-radius: 14px;
  padding: 28px 32px;
  margin-bottom: 40px;
  position: relative;
}
.brent-snapshot-card::before {
  content: '';
  position: absolute; top: 0; left: 0; right: 0; height: 2px;
  background: linear-gradient(90deg, #f97316, transparent);
}
.brent-snapshot-para {
  font-size: 16px; color: #cbd5e1; line-height: 1.85;
  margin-bottom: 1.2em; font-weight: 400;
}
.brent-snapshot-para:last-child { margin-bottom: 0; }
.brent-snapshot-para strong { color: #ffffff; font-weight: 600; }

/* ── Context Hub ──────────────────────────────────────────────────────── */
.brent-context-grid {
  display: grid; grid-template-columns: repeat(2, 1fr); gap: 14px;
  margin-bottom: 40px;
}
@media (max-width: 600px) { .brent-context-grid { grid-template-columns: 1fr; } }
.brent-context-card {
  display: flex; align-items: flex-start; gap: 14px;
  background: var(--card); border: 1px solid var(--border);
  border-radius: 12px; padding: 18px 20px;
  text-decoration: none; color: inherit; transition: all 0.2s;
}
.brent-context-card:hover {
  border-color: rgba(249,115,22,0.35);
  box-shadow: 0 0 16px rgba(249,115,22,0.07);
  transform: translateY(-1px);
}
.brent-context-icon { font-size: 1.6rem; flex-shrink: 0; margin-top: 2px; }
.brent-context-title {
  font-size: 13px; font-weight: 700; color: #e2e8f0; margin-bottom: 4px;
}
.brent-context-desc { font-size: 12px; color: #94a3b8; line-height: 1.5; }
.brent-context-link {
  font-size: 11px; color: #f97316; font-weight: 600; margin-top: 6px;
  display: inline-flex; align-items: center; gap: 4px;
}

/* ── Driver Blocks ────────────────────────────────────────────────────── */
.brent-drivers-grid {
  display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 40px;
}
@media (max-width: 700px) { .brent-drivers-grid { grid-template-columns: 1fr; } }
.brent-driver-card {
  background: var(--card); border: 1px solid var(--border);
  border-radius: 12px; padding: 20px 22px;
}
.brent-driver-num {
  font-size: 11px; font-weight: 700; letter-spacing: 0.1em;
  text-transform: uppercase; color: #f97316; margin-bottom: 6px;
}
.brent-driver-title {
  font-size: 15px; font-weight: 700; color: #e2e8f0; margin-bottom: 8px;
}
.brent-driver-desc { font-size: 13px; color: #94a3b8; line-height: 1.65; }
.brent-driver-desc a { color: #f97316; text-decoration: none; }

/* ── Risk Intelligence Panel ──────────────────────────────────────────── */
.brent-risk-grid {
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px;
  margin-bottom: 24px;
}
@media (max-width: 700px) { .brent-risk-grid { grid-template-columns: 1fr; } }
.brent-risk-card {
  background: var(--card); border: 1px solid var(--border);
  border-radius: 12px; padding: 18px 20px; text-align: center;
}
.brent-risk-idx-name {
  font-size: 10px; font-weight: 700; letter-spacing: 1.5px;
  text-transform: uppercase; color: #94a3b8; margin-bottom: 6px;
}
.brent-risk-value { font-size: 36px; font-weight: 900; line-height: 1; margin-bottom: 4px; }
.brent-risk-band {
  font-size: 11px; font-weight: 700; letter-spacing: 0.08em;
  text-transform: uppercase; margin-bottom: 4px;
}
.brent-risk-desc { font-size: 11px; color: #94a3b8; line-height: 1.5; }
.brent-risk-interp-card {
  background: linear-gradient(135deg, rgba(249,115,22,0.06) 0%, rgba(15,23,42,0) 100%);
  border: 1px solid rgba(249,115,22,0.15);
  border-radius: 12px; padding: 22px 26px; margin-bottom: 40px;
}

/* ── Historical Context ───────────────────────────────────────────────── */
.brent-hist-grid {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px;
  margin-bottom: 40px;
}
@media (max-width: 700px) { .brent-hist-grid { grid-template-columns: repeat(2, 1fr); } }
.brent-hist-card {
  background: var(--card); border: 1px solid var(--border);
  border-radius: 10px; padding: 14px 16px; text-align: center;
}
.brent-hist-label {
  font-size: 10px; font-weight: 700; letter-spacing: 1.2px;
  text-transform: uppercase; color: #94a3b8; margin-bottom: 6px;
}
.brent-hist-value { font-size: 22px; font-weight: 800; color: #e2e8f0; }
.brent-hist-date { font-size: 10px; color: #94a3b8; margin-top: 3px; }

/* ── Cross-Market Section ─────────────────────────────────────────────── */
.brent-cross-card {
  background: var(--card); border: 1px solid var(--border);
  border-radius: 12px; padding: 22px 26px; margin-bottom: 14px;
}
.brent-cross-title {
  font-size: 14px; font-weight: 700; color: #e2e8f0; margin-bottom: 8px;
  display: flex; align-items: center; gap: 8px;
}
.brent-cross-desc { font-size: 13px; color: #94a3b8; line-height: 1.65; }
.brent-cross-desc a { color: #f97316; text-decoration: none; }

/* ── Insight / Freshness Section ──────────────────────────────────────── */
.brent-insight-card {
  background: linear-gradient(135deg, #111827 0%, #0f172a 100%);
  border: 1px solid rgba(212,160,23,0.2); border-radius: 14px;
  padding: 28px 32px; margin-bottom: 40px; position: relative;
}
.brent-insight-card::before {
  content: '';
  position: absolute; top: 0; left: 0; right: 0; height: 2px;
  background: linear-gradient(90deg, var(--gold), transparent);
}
.brent-insight-h3 {
  font-size: 13px; font-weight: 700; letter-spacing: 0.1em;
  text-transform: uppercase; color: var(--gold); margin-bottom: 16px;
}
.brent-insight-item { margin-bottom: 16px; }
.brent-insight-item-title {
  font-size: 11px; font-weight: 700; letter-spacing: 0.08em;
  text-transform: uppercase; color: #94a3b8; margin-bottom: 4px;
}
.brent-insight-item-body {
  font-size: 15px; color: #cbd5e1; line-height: 1.75;
}
.brent-insight-item-body strong { color: #ffffff; font-weight: 600; }

/* ── FAQ ──────────────────────────────────────────────────────────────── */
.brent-faq-card {
  background: var(--card); border: 1px solid var(--border);
  border-radius: 12px; margin-bottom: 10px; overflow: hidden;
}
.brent-faq-q {
  padding: 16px 20px; font-size: 14px; font-weight: 600; color: #e2e8f0;
  cursor: pointer; display: flex; justify-content: space-between; align-items: center;
  user-select: none;
}
.brent-faq-q:hover { color: #f97316; }
.brent-faq-chevron { font-size: 12px; color: #475569; transition: transform 0.2s; }
.brent-faq-a {
  display: none; padding: 0 20px 16px; font-size: 13px;
  color: #94a3b8; line-height: 1.7;
}
.brent-faq-card.open .brent-faq-chevron { transform: rotate(180deg); }
.brent-faq-card.open .brent-faq-a { display: block; }

/* ── CTA Section ──────────────────────────────────────────────────────── */
.brent-cta-card {
  background: linear-gradient(135deg, #1a0e03 0%, #1e1108 50%, #0f172a 100%);
  border: 1px solid rgba(249,115,22,0.25); border-radius: 20px;
  padding: 40px 36px; text-align: center; margin-bottom: 40px;
  position: relative; overflow: hidden;
}
.brent-cta-card::before {
  content: '';
  position: absolute; top: 0; left: 0; right: 0; height: 3px;
  background: linear-gradient(90deg, #f97316, rgba(249,115,22,0.3), transparent);
}
.brent-cta-label {
  font-size: 10px; font-weight: 700; letter-spacing: 2px;
  text-transform: uppercase; color: #f97316; margin-bottom: 12px;
}
.brent-cta-h2 {
  font-size: 26px; font-weight: 800; color: #e2e8f0;
  margin-bottom: 12px; line-height: 1.3;
}
.brent-cta-sub {
  font-size: 14px; color: #94a3b8; margin-bottom: 24px; max-width: 500px;
  margin-left: auto; margin-right: auto; line-height: 1.7;
}
.brent-cta-benefits {
  display: flex; justify-content: center; gap: 24px; flex-wrap: wrap;
  margin-bottom: 28px;
}
.brent-cta-benefit {
  font-size: 12px; color: #94a3b8; display: flex; align-items: center; gap: 6px;
}
.brent-cta-benefit::before { content: '✓'; color: #22c55e; font-weight: 700; }
.brent-cta-btn-primary {
  display: inline-block; padding: 14px 36px;
  background: linear-gradient(135deg, #f97316, #ea6e0a);
  color: #fff; font-size: 15px; font-weight: 700;
  border-radius: 10px; text-decoration: none; letter-spacing: 0.03em;
  box-shadow: 0 4px 20px rgba(249,115,22,0.3);
  transition: all 0.2s;
}
.brent-cta-btn-primary:hover { box-shadow: 0 6px 28px rgba(249,115,22,0.45); transform: translateY(-1px); }
.brent-cta-credits { font-size: 11px; color: #64748b; margin-top: 10px; }

/* ── Link Footer ──────────────────────────────────────────────────────── */
.brent-link-footer {
  background: var(--card); border: 1px solid var(--border);
  border-radius: 14px; padding: 28px 30px; margin-bottom: 40px;
}
.brent-link-footer-section { margin-bottom: 22px; }
.brent-link-footer-section:last-child { margin-bottom: 0; }
.brent-link-footer-title {
  font-size: 10px; font-weight: 700; letter-spacing: 1.5px;
  text-transform: uppercase; color: #94a3b8; margin-bottom: 12px;
}
.brent-link-footer-grid {
  display: flex; gap: 10px; flex-wrap: wrap;
}
.brent-link-footer-pill {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 6px 14px; border-radius: 20px;
  background: rgba(255,255,255,0.03); border: 1px solid var(--border);
  font-size: 12px; font-weight: 600; color: #94a3b8;
  text-decoration: none; transition: all 0.2s;
}
.brent-link-footer-pill:hover { border-color: rgba(249,115,22,0.3); color: #f97316; }

/* ── Cite Card ────────────────────────────────────────────────────────── */
.brent-cite-card {
  background: var(--card); border: 1px solid var(--border);
  border-radius: 12px; padding: 22px 24px; margin-bottom: 40px;
}
.brent-cite-desc { font-size: 13px; color: #94a3b8; margin-bottom: 12px; }
.brent-cite-code {
  font-size: 12px; font-family: "JetBrains Mono", "Courier New", monospace;
  color: #94a3b8; line-height: 1.7; margin: 0; white-space: pre-wrap;
  overflow-wrap: break-word; word-break: break-word;
}
.brent-cite-code em { color: #d4a017; font-style: normal; }
.brent-cite-code a { color: #3b82f6; }

/* ── Mobile polishes ──────────────────────────────────────────────────── */
@media (max-width: 640px) {
  .brent-hero-price-card { padding: 22px 16px; margin-bottom: 28px; }
  .brent-price-main { font-size: 38px; }
  .brent-price-change { font-size: 15px; }
  .brent-snapshot-card { padding: 20px 16px; }
  .brent-insight-card { padding: 20px 16px; }
  .brent-cta-card { padding: 24px 16px; }
  .brent-cta-h2 { font-size: 20px; }
  .brent-cta-benefits { gap: 12px; }
  .brent-link-footer { padding: 20px 16px; }
  .brent-chart-card { padding: 16px 14px; }
  .brent-risk-interp-card { padding: 18px 16px; }
  .brent-cross-card { padding: 16px 16px; }
  body { padding-bottom: 60px; }
  .brent-range-tab { padding: 5px 10px; font-size: 10px; }
  .brent-hist-grid { grid-template-columns: repeat(2, 1fr); }
  .brent-trust-line { gap: 10px; font-size: 10px; }
}
/* ── Correlation context grid mobile ─────────────────────────────────── */
@media (max-width: 500px) {
  .brent-corr-grid { grid-template-columns: 1fr !important; gap: 8px; }
  .brent-price-main { font-size: 34px; }
}
/* ── Nav mobile ───────────────────────────────────────────────────────── */
@media (max-width: 600px) {
  .nav-inner > div > a:not(.cta-btn-nav) { display: none; }
}
"""


# ─────────────────────────────────────────────────────────────────────────────
# Data Fetch
# ─────────────────────────────────────────────────────────────────────────────

def _compute_brent_data() -> dict:
    """Fetch all production data needed for the Brent crude oil page."""
    today = _date.today()
    ytd_start = today.replace(month=1, day=1)

    # Brent latest (daily)
    brent_latest_row = execute_production_one(
        "SELECT date, brent_price, brent_change_24h, brent_change_pct, wti_price, wti_change_24h, brent_wti_spread "
        "FROM oil_price_snapshots ORDER BY date DESC LIMIT 1"
    )

    # Brent 90-day history
    brent_90d = execute_production_query(
        "SELECT date, brent_price FROM "
        "(SELECT date, brent_price FROM oil_price_snapshots ORDER BY date DESC LIMIT 90) t "
        "ORDER BY date ASC"
    ) or []

    # Brent intraday
    brent_intraday = execute_production_query(
        "SELECT hour, price FROM intraday_brent WHERE date = %s ORDER BY hour ASC",
        (today,)
    ) or []

    # WTI latest
    wti_row = execute_production_one(
        "SELECT date, wti_price, wti_change_24h, wti_change_pct FROM oil_price_snapshots ORDER BY date DESC LIMIT 1"
    )

    # VIX
    vix_row = execute_production_one(
        "SELECT date, vix_close, vix_open, vix_high, vix_low FROM vix_snapshots ORDER BY date DESC LIMIT 1"
    )
    vix_prev = execute_production_one(
        "SELECT vix_close FROM vix_snapshots ORDER BY date DESC LIMIT 1 OFFSET 1"
    )

    # TTF
    ttf_row = execute_production_one(
        "SELECT date, ttf_price FROM ttf_gas_snapshots ORDER BY date DESC LIMIT 1"
    )
    ttf_prev_row = execute_production_one(
        "SELECT ttf_price FROM ttf_gas_snapshots ORDER BY date DESC LIMIT 1 OFFSET 1"
    )

    # LNG
    lng_row = execute_production_one(
        "SELECT date, jkm_price, jkm_change_pct FROM lng_price_snapshots ORDER BY date DESC LIMIT 1"
    )

    # Storage
    storage_row = execute_production_one(
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
        "SELECT date, value, band, trend_7d FROM reri_indices_daily "
        "WHERE index_id='europe:eeri' ORDER BY date DESC LIMIT 1"
    )
    eeri_prev = execute_production_one(
        "SELECT value FROM reri_indices_daily "
        "WHERE index_id='europe:eeri' ORDER BY date DESC LIMIT 1 OFFSET 1"
    )

    # EGSI-M
    egsi_row = execute_production_one(
        "SELECT index_date, index_value, band FROM egsi_m_daily "
        "WHERE region='Europe' ORDER BY index_date DESC LIMIT 1"
    )

    # Historical stats: 30-day
    hist_30d = execute_production_query(
        "SELECT date, brent_price FROM "
        "(SELECT date, brent_price FROM oil_price_snapshots ORDER BY date DESC LIMIT 30) t "
        "ORDER BY brent_price"
    ) or []

    # Historical stats: YTD
    hist_ytd = execute_production_query(
        "SELECT date, brent_price FROM oil_price_snapshots "
        "WHERE date >= %s ORDER BY brent_price",
        (ytd_start,)
    ) or []

    # Alert context for AI insight
    alert_cats = execute_production_query(
        "SELECT category, COUNT(*) as cnt FROM alert_events "
        "WHERE created_at >= NOW() - INTERVAL '72 hours' "
        "GROUP BY category ORDER BY cnt DESC LIMIT 6"
    ) or []
    alert_context = "Alert categories (last 72h): " + ", ".join(
        f"{r['category']}={r['cnt']}" for r in alert_cats
    ) if alert_cats else "No recent alerts."

    return {
        "brent_latest_row": brent_latest_row,
        "brent_90d": brent_90d,
        "brent_intraday": brent_intraday,
        "wti_row": wti_row,
        "vix_row": vix_row,
        "vix_prev": vix_prev,
        "ttf_row": ttf_row,
        "ttf_prev_row": ttf_prev_row,
        "lng_row": lng_row,
        "storage_row": storage_row,
        "geri_row": geri_row,
        "geri_prev": geri_prev,
        "eeri_row": eeri_row,
        "eeri_prev": eeri_prev,
        "egsi_row": egsi_row,
        "hist_30d": hist_30d,
        "hist_ytd": hist_ytd,
        "alert_context": alert_context,
    }


# ─────────────────────────────────────────────────────────────────────────────
# AI Insight Engine
# ─────────────────────────────────────────────────────────────────────────────

_BRENT_INSIGHT_CACHE: dict = {}


def _run_brent_insight_engine(
    today_str, brent_price, brent_chg, brent_chg_pct,
    wti_price, ttf_price, vix_close, lng_price,
    storage_pct, geri_val, geri_band, eeri_val, eeri_band,
    alert_context,
) -> dict:
    """Generate a daily Brent market insight (3 structured sections)."""
    cache_key = f"brent:{today_str}:{round(brent_price,1)}:{geri_val}"
    if cache_key in _BRENT_INSIGHT_CACHE:
        return _BRENT_INSIGHT_CACHE[cache_key]

    chg_dir = "up" if brent_chg >= 0 else "down"
    trend_desc = "rising" if brent_chg_pct > 0.5 else ("falling" if brent_chg_pct < -0.5 else "flat")
    wti_spread = round(brent_price - wti_price, 2) if wti_price else 0.0

    fallback = {
        "what_moved": (
            f"Brent crude traded at ${brent_price:.2f}/bbl today, moving {chg_dir} {abs(brent_chg_pct):.1f}% "
            f"on the day. The Brent-WTI spread stands at ${wti_spread:.2f}, "
            f"reflecting current global demand dynamics and shipping cost differentials."
        ),
        "why_matters": (
            f"With GERI at {geri_val}/100 ({geri_band}) and EERI at {eeri_val}/100 ({eeri_band}), "
            f"geopolitical risk remains a key pricing factor. VIX at {vix_close:.2f} signals "
            f"{'elevated' if vix_close > 20 else 'moderate'} market uncertainty, "
            f"which historically correlates with oil price volatility."
        ),
        "what_to_watch": (
            f"Monitor OPEC+ production signals, Middle East supply corridor stability, "
            f"and EU gas storage progression. TTF at €{ttf_price:.2f}/MWh and "
            f"gas storage at {storage_pct:.1f}% shape energy switching dynamics that "
            f"feed back into oil demand. Any shift in GERI trend is an early warning signal."
        ),
    }

    try:
        from openai import OpenAI
        ai_key = os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY")
        ai_url = os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL")
        client = OpenAI(api_key=ai_key, base_url=ai_url) if ai_key and ai_url else OpenAI()

        prompt = f"""You are EnergyRiskIQ's senior oil market analyst. Today is {today_str}.

LIVE DATA:
Brent Crude: ${brent_price:.2f}/bbl  change={_sign(brent_chg)}{brent_chg:.2f} ({brent_chg_pct:+.2f}%) trend={trend_desc}
WTI: ${wti_price:.2f}/bbl  Brent-WTI spread: ${wti_spread:.2f}
TTF Natural Gas: €{ttf_price:.2f}/MWh
VIX: {vix_close:.2f}
JKM LNG: ${lng_price:.2f}/MMBtu
EU Gas Storage: {storage_pct:.1f}%
GERI (Global Energy Risk Index): {geri_val}/100  band={geri_band}
EERI (European Energy Risk Index): {eeri_val}/100  band={eeri_band}
{alert_context}

Return ONLY a valid JSON object with exactly these 3 keys. No markdown. No AI mentions. Write as proprietary analysis.

1. "what_moved" (≤200 chars): 2 sentences explaining what drove Brent's price action today. Reference specific prices.
2. "why_matters" (≤200 chars): 2 sentences on why today's move matters for energy markets. Reference risk indices.
3. "what_to_watch" (≤200 chars): 2 sentences on forward-looking signals and key levels to monitor.

Keep it authoritative, factual, no bullet points, no AI mentions."""

        resp = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=400,
            response_format={"type": "json_object"},
            timeout=18,
        )
        data = json.loads(resp.choices[0].message.content)
        result = {k: str(data.get(k, fallback[k])).strip() for k in fallback}
        _BRENT_INSIGHT_CACHE[cache_key] = result
        logger.info("Brent insight engine: generated successfully")
        return result
    except Exception as exc:
        logger.warning(f"Brent insight engine failed: {exc}")
        return fallback


# ─────────────────────────────────────────────────────────────────────────────
# HTML Builder
# ─────────────────────────────────────────────────────────────────────────────

def _build_brent_html(data: dict) -> str:
    today_str  = datetime.now(timezone.utc).strftime("%B %-d, %Y")
    today_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    brent_row = data["brent_latest_row"] or {}
    brent_price  = _safe_float(brent_row.get("brent_price", 0))
    brent_chg    = _safe_float(brent_row.get("brent_change_24h", 0))
    brent_chg_pct = _safe_float(brent_row.get("brent_change_pct", 0))
    brent_date   = brent_row.get("date", today_date)

    wti_row   = data["wti_row"] or {}
    wti_price  = _safe_float(wti_row.get("wti_price", 0))
    wti_chg    = _safe_float(wti_row.get("wti_change_24h", 0))
    brent_wti_spread = _safe_float(brent_row.get("brent_wti_spread") or (brent_price - wti_price))

    vix_row   = data["vix_row"] or {}
    vix_close = _safe_float(vix_row.get("vix_close", 20))
    vix_prev_close = _safe_float((data["vix_prev"] or {}).get("vix_close", vix_close))
    vix_chg = vix_close - vix_prev_close

    ttf_row   = data["ttf_row"] or {}
    ttf_price = _safe_float(ttf_row.get("ttf_price", 0))
    ttf_prev_price = _safe_float((data["ttf_prev_row"] or {}).get("ttf_price", ttf_price))
    ttf_chg = ttf_price - ttf_prev_price

    lng_row   = data["lng_row"] or {}
    lng_price = _safe_float(lng_row.get("jkm_price", 0))

    storage_row   = data["storage_row"] or {}
    storage_pct   = _safe_float(storage_row.get("eu_storage_percent", 45))
    storage_norm  = _safe_float(storage_row.get("seasonal_norm", 50))
    storage_dev   = _safe_float(storage_row.get("deviation_from_norm", 0))
    storage_band  = str(storage_row.get("risk_band", "MODERATE"))

    geri_row  = data["geri_row"] or {}
    geri_val  = int(round(_safe_float(geri_row.get("value", 0))))
    geri_band = str(geri_row.get("band", "MODERATE"))
    geri_prev_val = int(round(_safe_float((data["geri_prev"] or {}).get("value", geri_val))))
    geri_delta = geri_val - geri_prev_val

    eeri_row  = data["eeri_row"] or {}
    eeri_val  = int(round(_safe_float(eeri_row.get("value", 0))))
    eeri_band = str(eeri_row.get("band", "ELEVATED"))
    eeri_prev_val = int(round(_safe_float((data["eeri_prev"] or {}).get("value", eeri_val))))
    eeri_delta = eeri_val - eeri_prev_val

    egsi_row  = data["egsi_row"] or {}
    egsi_val  = round(_safe_float(egsi_row.get("index_value", 0)), 1)
    egsi_band = str(egsi_row.get("band", "ELEVATED"))

    gc = BAND_COLORS.get(geri_band, "#f97316")
    ec = BAND_COLORS.get(eeri_band, "#ef4444")
    mgc = BAND_COLORS.get(egsi_band, "#f97316")

    # Sentiment
    s_emoji, s_label, s_color = _sentiment_label(brent_chg_pct)
    b_arrow = _arrow(brent_chg)
    b_color = _chg_color(brent_chg)
    t_arrow = _arrow(ttf_chg)
    t_color = _chg_color(ttf_chg)
    w_arrow = _arrow(wti_chg)
    w_color = _chg_color(wti_chg)
    v_arrow = _arrow(vix_chg)
    v_color = _chg_color(vix_chg)

    # Pre-computed strings (no backslash in f-string expressions)
    brent_above_below   = "above" if brent_chg >= 0 else "below"
    trend_word          = "rising" if brent_chg_pct > 0.5 else ("falling" if brent_chg_pct < -0.5 else "flat")
    vix_desc            = "elevated" if vix_close > 20 else "moderate"
    storage_health      = "above" if storage_dev >= 0 else "below"
    geri_risk_word      = {"LOW": "low", "MODERATE": "moderate", "ELEVATED": "elevated", "SEVERE": "severe", "CRITICAL": "critical"}.get(geri_band, "moderate")
    storage_signal_word = "positive" if storage_dev >= 0 else "negative"
    geri_interp         = (
        f"Today's Brent price movement reflects {geri_risk_word} geopolitical escalation risk. "
        f"GERI at {geri_val}/100 ({geri_band}) and EERI at {eeri_val}/100 ({eeri_band}) indicate "
        f"{'contained' if geri_val < 50 else 'significant'} supply chain stress across global energy corridors."
    )

    # ── Build chart SVGs ──────────────────────────────────────────────────────
    brent_90d = data["brent_90d"]

    def _slice_chart(rows, n):
        subset = rows[-n:] if len(rows) >= n else rows
        return [{"label": _fmt_date(r["date"]), "val": _safe_float(r["brent_price"])} for r in subset]

    pts_7d  = _slice_chart(brent_90d, 7)
    pts_30d = _slice_chart(brent_90d, 30)
    pts_90d = _slice_chart(brent_90d, 90)

    # Build intraday
    intra_pts = data["brent_intraday"]
    pts_1d = [{"label": f"{r['hour']:02d}:00", "val": _safe_float(r["price"])} for r in intra_pts]

    svg_1d  = _build_brent_svg_chart(pts_1d)  if pts_1d  else "<div style='height:80px;display:flex;align-items:center;justify-content:center;color:#475569;font-size:12px;'>Intraday data not yet available today</div>"
    svg_7d  = _build_brent_svg_chart(pts_7d)
    svg_30d = _build_brent_svg_chart(pts_30d)
    svg_90d = _build_brent_svg_chart(pts_90d)

    # ── Historical highs/lows ─────────────────────────────────────────────────
    hist_30d = data["hist_30d"]
    hist_ytd = data["hist_ytd"]

    low30_row  = hist_30d[0]  if hist_30d  else None
    high30_row = hist_30d[-1] if hist_30d  else None
    low_ytd    = hist_ytd[0]  if hist_ytd  else None
    high_ytd   = hist_ytd[-1] if hist_ytd  else None

    low30_val  = _safe_float((low30_row  or {}).get("brent_price", 0))
    high30_val = _safe_float((high30_row or {}).get("brent_price", 0))
    low_ytd_val  = _safe_float((low_ytd  or {}).get("brent_price", 0))
    high_ytd_val = _safe_float((high_ytd or {}).get("brent_price", 0))
    low30_date   = _fmt_date((low30_row  or {}).get("date"))
    high30_date  = _fmt_date((high30_row or {}).get("date"))
    low_ytd_date  = _fmt_date((low_ytd  or {}).get("date"))
    high_ytd_date = _fmt_date((high_ytd or {}).get("date"))

    # Spread to YTD high
    dist_to_ytd_high = round(high_ytd_val - brent_price, 2) if high_ytd_val else 0.0
    dist_to_ytd_high_pct = round((dist_to_ytd_high / brent_price) * 100, 1) if brent_price else 0.0

    # ── Market insight AI ──────────────────────────────────────────────────────
    insight = _run_brent_insight_engine(
        today_str, brent_price, brent_chg, brent_chg_pct,
        wti_price, ttf_price, vix_close, lng_price,
        storage_pct, geri_val, geri_band, eeri_val, eeri_band,
        data["alert_context"],
    )

    # ── Market snapshot auto-generated prose ──────────────────────────────────
    pct_sign = "+" if brent_chg_pct >= 0 else ""
    abs_chg_sign = "+" if brent_chg >= 0 else ""
    snap_para1 = (
        f"The Brent crude oil price today stands at <strong>${brent_price:.2f} per barrel</strong>, "
        f"moving <strong>{abs_chg_sign}{brent_chg:.2f} ({pct_sign}{brent_chg_pct:.2f}%)</strong> "
        f"over the last 24 hours as of {today_str}. "
        f"The benchmark is trading {brent_above_below} the prior day close, "
        f"with market sentiment reading <strong>{s_label}</strong> based on daily price action."
    )
    snap_para2 = (
        f"Over the past week, Brent prices have been <strong>{trend_word}</strong>, "
        f"influenced by global supply dynamics, OPEC+ production posture, and geopolitical "
        f"risk signals captured in EnergyRiskIQ's proprietary indices. "
        f"The Global Energy Risk Index (GERI) currently stands at <strong>{geri_val}/100 "
        f"({geri_band})</strong>, while the European Energy Risk Index (EERI) is at "
        f"<strong>{eeri_val}/100 ({eeri_band})</strong>."
    )
    snap_para3 = (
        f"Brent-WTI spread is at <strong>${brent_wti_spread:.2f}/bbl</strong>, "
        f"reflecting differential demand patterns between Atlantic Basin and domestic US markets. "
        f"VIX volatility at <strong>{vix_close:.2f}</strong> signals "
        f"{vix_desc} market uncertainty, a factor historically correlated with crude oil price moves. "
        f"EU gas storage at {storage_pct:.1f}% is {storage_health} the {storage_norm:.1f}% seasonal norm "
        f"— a {storage_signal_word} signal for energy switching demand."
    )

    # ── JSON-LD Schemas ───────────────────────────────────────────────────────
    faq_entries = [
        ("What is Brent crude oil?",
         "Brent crude is a major oil benchmark that represents about two-thirds of all globally traded oil contracts. It is extracted from the North Sea and is used as the international pricing standard for crude oil exports from Europe, Africa, and the Middle East."),
        ("Why is Brent crude important for energy markets?",
         "Brent crude serves as the primary pricing benchmark for approximately 78% of the world's traded oil. Changes in Brent prices directly affect fuel costs, petrochemical production, airline costs, and broader economic indicators including inflation."),
        ("How often is Brent crude price updated?",
         "EnergyRiskIQ updates Brent crude prices daily from verified market data sources. Intraday price data is also tracked via futures market feeds. Our proprietary analysis engine contextualises every price reading with global risk index data."),
        ("What factors affect the Brent crude oil price?",
         "The Brent price is driven by multiple factors: OPEC+ production decisions, US shale output, global demand from China and emerging markets, geopolitical events in the Middle East and Russia, US dollar strength, VIX market volatility, and energy substitution between oil and gas."),
        ("What is the difference between Brent and WTI crude oil?",
         "WTI (West Texas Intermediate) is the US domestic benchmark traded on NYMEX, while Brent is the global benchmark traded on ICE. Brent typically trades at a premium to WTI due to higher international shipping costs and global demand dynamics. The Brent-WTI spread is a key indicator of market conditions."),
        ("Why is Brent crude oil price volatile?",
         "Brent oil prices are volatile because they respond to a complex mix of supply disruptions, geopolitical conflicts, demand forecasts, currency movements, and speculative trading. Events such as OPEC+ output changes, Middle East conflicts, or sanctions can cause significant price swings within hours."),
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
                "name": "Brent Crude Oil Price Today (Live Daily Update & Market Insights)",
                "url": f"{BASE_URL}/data/brent-crude-oil-price-today",
                "description": "Track the Brent crude oil price today with daily updates, charts, and market insights. Monitor global oil trends and energy risk signals.",
                "publisher": {"@type": "Organization", "name": "EnergyRiskIQ", "url": BASE_URL},
                "about": [
                    {"@type": "Thing", "name": "Brent Crude Oil"},
                    {"@type": "Thing", "name": "Oil Price"},
                    {"@type": "Thing", "name": "Energy Markets"},
                    {"@type": "Thing", "name": "Global Energy Risk"},
                ]
            },
            {
                "@type": "Dataset",
                "name": "Brent Crude Oil Daily Prices",
                "description": "Daily Brent crude oil benchmark prices, 24-hour changes, and historical data updated daily by EnergyRiskIQ.",
                "url": f"{BASE_URL}/data/brent-crude-oil-price-today",
                "creator":   {"@type": "Organization", "name": "EnergyRiskIQ", "url": BASE_URL},
                "publisher": {"@type": "Organization", "name": "EnergyRiskIQ", "url": BASE_URL},
                "license": f"{BASE_URL}/data-license",
                "isAccessibleForFree": True,
                "temporalCoverage": f"2024-01-01/{today_date}",
                "spatialCoverage": "Global",
                "variableMeasured": [
                    {"@type": "PropertyValue", "name": "Brent Crude Price", "unitCode": "USD/BBL"},
                    {"@type": "PropertyValue", "name": "Brent 24h Change", "unitCode": "USD"},
                    {"@type": "PropertyValue", "name": "WTI Crude Price", "unitCode": "USD/BBL"},
                    {"@type": "PropertyValue", "name": "Brent-WTI Spread", "unitCode": "USD"},
                ],
                "measurementTechnique": "OilPriceAPI daily spot data; yfinance BZ=F futures for intraday; EnergyRiskIQ proprietary risk pipeline",
                "dateModified": today_date,
                "keywords": ["brent crude oil price", "oil price today", "brent oil chart", "energy market", "oil benchmark"],
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Home", "item": BASE_URL},
                    {"@type": "ListItem", "position": 2, "name": "Data", "item": f"{BASE_URL}/data"},
                    {"@type": "ListItem", "position": 3, "name": "Brent Crude Oil Price Today",
                     "item": f"{BASE_URL}/data/brent-crude-oil-price-today"},
                ]
            },
            {
                "@type": "FinancialProduct",
                "name": "Brent Crude Oil",
                "description": "Brent crude oil is the leading global price benchmark for Atlantic basin crude oils. It represents approximately 78% of globally traded crude oil contracts.",
                "url": f"{BASE_URL}/data/brent-crude-oil-price-today",
                "provider": {"@type": "Organization", "name": "EnergyRiskIQ", "url": BASE_URL},
            },
        ]
    }, indent=2)

    # ── FAQ HTML ──────────────────────────────────────────────────────────────
    faq_html = ""
    for i, (q, a) in enumerate(faq_entries):
        faq_html += f"""<div class="brent-faq-card" id="brent-faq-{i}">
  <div class="brent-faq-q" onclick="(function(el){{el.closest('.brent-faq-card').classList.toggle('open')}})(this)">
    <span>{_html.escape(q)}</span><span class="brent-faq-chevron">&#9660;</span>
  </div>
  <div class="brent-faq-a">{_html.escape(a)}</div>
</div>"""

    # ── Assemble HTML ─────────────────────────────────────────────────────────
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
{_BRENT_CSS}
</style>

<!-- ── STICKY PRICE BAR ────────────────────────────────────────────── -->
<div class="brent-sticky-bar">
  <span class="brent-sticky-label">&#128137; Brent Today</span>
  <span class="brent-sticky-price">${brent_price:.2f}</span>
  <span class="brent-sticky-chg" style="color:{b_color}">{b_arrow} {brent_chg:+.2f} ({brent_chg_pct:+.2f}%)</span>
  <span class="brent-sticky-time">Updated: {today_str}</span>
  <a href="/users" class="brent-sticky-cta">Free Alerts &rarr;</a>
</div>

<!-- ── NAV ────────────────────────────────────────────────────────── -->
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
      <a href="/users" class="cta-btn-nav">Unlock Deeper Intelligence</a>
    </div>
  </div>
</nav>

<!-- ── HERO ───────────────────────────────────────────────────────── -->
<header class="hero">
  <div class="hero-date">&#128337; Updated Daily &nbsp;&bull;&nbsp; {today_str} &nbsp;&bull;&nbsp; Benchmark: ICE Brent</div>
  <h1>Brent Crude Oil Price Today</h1>
  <p class="hero-sub">
    Track today&rsquo;s Brent crude oil price, daily changes, and global energy market trends.
    Updated daily with risk signals, macro context, and price drivers.
  </p>

  <!-- PRIMARY PRICE CARD -->
  <div class="brent-hero-price-card">
    <div class="brent-price-label">&#128137; Brent Crude Oil &mdash; USD per Barrel</div>
    <div class="brent-price-main"><sup>$</sup>{brent_price:.2f}</div>
    <div class="brent-price-change" style="color:{b_color}">
      {b_arrow} {brent_chg:+.2f} &nbsp;&bull;&nbsp; {brent_chg_pct:+.2f}% day-over-day
    </div>
    <div>
      <span class="brent-sentiment-badge" style="background:rgba(255,255,255,0.04);border:1px solid {s_color}33;color:{s_color};">
        {s_emoji} {s_label} Bias
      </span>
    </div>
    <div class="brent-trust-line">
      <span>Benchmark: Brent Crude Oil (ICE)</span>
      <span class="brent-trust-dot">&#9679;</span>
      <span>Data updated daily</span>
      <span class="brent-trust-dot">&#9679;</span>
      <span>Used by traders, analysts &amp; risk managers</span>
      <span class="brent-trust-dot">&#9679;</span>
      <span>Source: OilPriceAPI &bull; {brent_date}</span>
    </div>
    <a href="/users" class="brent-hero-cta">
      &#128276; Get real-time oil price alerts &amp; risk signals &rarr; Free Account
    </a>
  </div>

  <!-- Hero index badges -->
  <div style="display:flex;justify-content:center;gap:1rem;flex-wrap:wrap;margin-top:0.5rem;">
    <a href="/indices/global-energy-risk-index" style="font-size:12px;font-weight:600;color:{gc};
      border:1px solid {gc}33;border-radius:20px;padding:4px 14px;text-decoration:none;">
      GERI {geri_val}/100 &bull; {geri_band}
    </a>
    <a href="/indices/europe-energy-risk-index" style="font-size:12px;font-weight:600;color:{ec};
      border:1px solid {ec}33;border-radius:20px;padding:4px 14px;text-decoration:none;">
      EERI {eeri_val}/100 &bull; {eeri_band}
    </a>
    <span style="font-size:12px;font-weight:600;color:#94a3b8;
      border:1px solid rgba(148,163,184,0.2);border-radius:20px;padding:4px 14px;">
      VIX {vix_close:.1f} &bull; {vix_desc.title()} Volatility
    </span>
  </div>
</header>

<main class="page-body">

<!-- ── SECTION 2: BRENT CHART ───────────────────────────────────────── -->
<div class="section-label" style="margin-bottom:20px;">&#128200; Brent Crude Oil Price Chart</div>
<div class="brent-chart-card">
  <h2 style="font-size:16px;font-weight:700;color:#e2e8f0;margin-bottom:14px;">
    Brent Crude Oil Price Chart &mdash; Historical & Intraday
  </h2>

  <!-- Time range tabs -->
  <div class="brent-range-tabs">
    <button class="brent-range-tab" onclick="switchRange('1d')">1D</button>
    <button class="brent-range-tab active" onclick="switchRange('7d')">7D</button>
    <button class="brent-range-tab" onclick="switchRange('30d')">30D</button>
    <button class="brent-range-tab" onclick="switchRange('90d')">90D</button>
  </div>

  <!-- Charts -->
  <div class="brent-chart-wrap">
    <div id="chart-1d" class="brent-chart-container">{svg_1d}</div>
    <div id="chart-7d" class="brent-chart-container active">{svg_7d}</div>
    <div id="chart-30d" class="brent-chart-container">{svg_30d}</div>
    <div id="chart-90d" class="brent-chart-container">{svg_90d}</div>
  </div>
  <div class="brent-chart-note">
    Source: OilPriceAPI (daily closes) &bull; yfinance BZ=F (intraday) &bull; EnergyRiskIQ data pipeline
  </div>

  <!-- Market Correlations note -->
  <div style="margin-top:20px;padding:16px 18px;background:rgba(255,255,255,0.02);
    border:1px solid rgba(255,255,255,0.06);border-radius:10px;">
    <div style="font-size:10px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;
      color:#94a3b8;margin-bottom:10px;">Market Correlation Context</div>
    <div class="brent-corr-grid" style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;">
      <div>
        <div style="font-size:10px;color:#94a3b8;font-weight:600;margin-bottom:3px;">WTI CRUDE</div>
        <div style="font-size:15px;font-weight:700;color:#e2e8f0;">${wti_price:.2f}</div>
        <div style="font-size:11px;color:{w_color};">{w_arrow} {wti_chg:+.2f} d/d</div>
      </div>
      <div>
        <div style="font-size:10px;color:#94a3b8;font-weight:600;margin-bottom:3px;">TTF NATURAL GAS</div>
        <div style="font-size:15px;font-weight:700;color:#e2e8f0;">&euro;{ttf_price:.2f}</div>
        <div style="font-size:11px;color:{t_color};">{t_arrow} {ttf_chg:+.2f} d/d</div>
      </div>
      <div>
        <div style="font-size:10px;color:#94a3b8;font-weight:600;margin-bottom:3px;">VIX (FEAR GAUGE)</div>
        <div style="font-size:15px;font-weight:700;color:#e2e8f0;">{vix_close:.2f}</div>
        <div style="font-size:11px;color:{v_color};">{v_arrow} {vix_chg:+.2f} d/d</div>
      </div>
    </div>
  </div>

  <!-- CTA under chart -->
  <div style="margin-top:18px;text-align:center;">
    <a href="/users" style="font-size:13px;font-weight:700;color:#f97316;
      border:1px solid rgba(249,115,22,0.3);border-radius:8px;padding:8px 22px;
      text-decoration:none;display:inline-block;">
      &#128275; Unlock full risk correlation overlays &rarr; Free account
    </a>
  </div>
</div>

<!-- ── SECTION 3: DAILY MARKET SNAPSHOT (SEO CORE) ──────────────────── -->
<div class="section-label" style="margin-bottom:20px;">&#128203; Brent Oil Market Snapshot &mdash; Today</div>
<div class="brent-snapshot-card" style="margin-bottom:40px;">
  <h2 style="font-size:18px;font-weight:700;color:#e2e8f0;margin-bottom:18px;">
    Brent Oil Market Snapshot &mdash; {today_str}
  </h2>
  <p class="brent-snapshot-para">{snap_para1}</p>
  <p class="brent-snapshot-para">{snap_para2}</p>
  <p class="brent-snapshot-para">{snap_para3}</p>
  <div style="margin-top:18px;padding:14px 18px;background:rgba(249,115,22,0.06);
    border:1px solid rgba(249,115,22,0.12);border-radius:10px;
    font-size:13px;color:#94a3b8;">
    &#128204; Brent-WTI Spread: <strong style="color:#e2e8f0;">${brent_wti_spread:.2f}/bbl</strong>
    &nbsp;&bull;&nbsp;
    JKM LNG: <strong style="color:#e2e8f0;">${lng_price:.2f}/MMBtu</strong>
    &nbsp;&bull;&nbsp;
    EU Gas Storage: <strong style="color:#e2e8f0;">{storage_pct:.1f}%</strong>
  </div>
</div>

<!-- ── SECTION 4: CONTEXT HUB ────────────────────────────────────────── -->
<div class="section-label" style="margin-bottom:20px;">&#128279; What&rsquo;s Driving Oil Markets Right Now</div>
<h3 style="font-size:16px;font-weight:700;color:#e2e8f0;margin-bottom:16px;">
  What&rsquo;s Driving Oil Markets Right Now
</h3>
<div class="brent-context-grid">
  <a href="/data/ttf-gas-price-today" class="brent-context-card">
    <span class="brent-context-icon">&#127470;&#127489;</span>
    <div>
      <div class="brent-context-title">TTF Gas Price Today</div>
      <div class="brent-context-desc">Dutch TTF European natural gas benchmark — energy switching signal for oil demand.</div>
      <div class="brent-context-link">View TTF Gas Data &rarr;</div>
    </div>
  </a>
  <a href="/data/europe-lng-supply-demand" class="brent-context-card">
    <span class="brent-context-icon">&#128168;</span>
    <div>
      <div class="brent-context-title">LNG Supply &amp; Demand</div>
      <div class="brent-context-desc">Europe LNG supply-demand balance — a key driver of gas-to-oil substitution dynamics.</div>
      <div class="brent-context-link">View LNG Data &rarr;</div>
    </div>
  </a>
  <a href="/gas-storage-levels-in-europe" class="brent-context-card">
    <span class="brent-context-icon">&#128201;</span>
    <div>
      <div class="brent-context-title">Europe Gas Storage Levels</div>
      <div class="brent-context-desc">EU gas storage fill rates and seasonal risk — directly feeds into energy switching pressure on oil.</div>
      <div class="brent-context-link">View Gas Storage &rarr;</div>
    </div>
  </a>
  <a href="/data/jkm-lng-spot-price" class="brent-context-card">
    <span class="brent-context-icon">&#9875;</span>
    <div>
      <div class="brent-context-title">JKM LNG Spot Price</div>
      <div class="brent-context-desc">Japan Korea Marker — Asia spot LNG price with oil-indexation ties and demand signals.</div>
      <div class="brent-context-link">View JKM Data &rarr;</div>
    </div>
  </a>
</div>

<!-- ── SECTION 5: WHAT MOVES BRENT ──────────────────────────────────── -->
<div class="section-label" style="margin-bottom:20px;">&#129504; What Drives Brent Crude Oil Prices?</div>
<h2 style="font-size:20px;font-weight:700;color:#e2e8f0;margin-bottom:20px;">
  What Drives Brent Crude Oil Prices?
</h2>
<div class="brent-drivers-grid">
  <div class="brent-driver-card">
    <div class="brent-driver-num">01 / SUPPLY</div>
    <div class="brent-driver-title">&#128101; Global Supply &mdash; OPEC+ &amp; Outages</div>
    <div class="brent-driver-desc">
      OPEC+ production decisions are the single largest controllable factor in Brent pricing.
      When OPEC+ cuts output, supply tightens and Brent rises. Unplanned outages — from
      pipeline attacks, sanctions, or extreme weather — create immediate supply shocks.
      Today&rsquo;s GERI at {geri_val}/100 reflects current geopolitical supply risk levels.
      <br><br>
      <a href="/indices/global-energy-risk-index">&#8594; View Global Energy Risk Index</a>
    </div>
  </div>
  <div class="brent-driver-card">
    <div class="brent-driver-num">02 / DEMAND</div>
    <div class="brent-driver-title">&#127758; Demand &mdash; China, US &amp; Global Economy</div>
    <div class="brent-driver-desc">
      China accounts for approximately 16% of global oil consumption. US economic data —
      particularly manufacturing PMI, jobs reports, and GDP — drives near-term demand forecasts.
      A global recession typically reduces oil demand by 1–3 mb/d, creating significant
      downward pressure on Brent. Watch IEA monthly demand revisions as leading indicators.
    </div>
  </div>
  <div class="brent-driver-card">
    <div class="brent-driver-num">03 / GEOPOLITICS</div>
    <div class="brent-driver-title">&#9889; Geopolitics &mdash; Middle East, Russia &amp; Shipping</div>
    <div class="brent-driver-desc">
      Middle East tensions, Ukraine conflict escalation, and Red Sea shipping disruptions
      are among the fastest-moving Brent price catalysts. The Strait of Hormuz handles
      21% of global oil trade — any closure risk creates an immediate geopolitical premium.
      EERI at {eeri_val}/100 ({eeri_band}) captures current European geopolitical risk exposure.
      <br><br>
      <a href="/indices/global-energy-risk-index">&#8594; Global Energy Risk Index</a>
    </div>
  </div>
  <div class="brent-driver-card">
    <div class="brent-driver-num">04 / MACRO</div>
    <div class="brent-driver-title">&#128185; Financial Markets &mdash; Dollar &amp; Risk Sentiment</div>
    <div class="brent-driver-desc">
      Oil is priced in USD globally. A stronger dollar makes oil more expensive in local
      currencies, reducing international demand. VIX at {vix_close:.2f} currently signals
      {vix_desc} market uncertainty — periods of high VIX often coincide with oil sell-offs
      as risk-off sentiment dominates. Fed rate decisions and DXY strength are key macro inputs.
    </div>
  </div>
  <div class="brent-driver-card" style="grid-column:1/-1;">
    <div class="brent-driver-num">05 / SUBSTITUTION</div>
    <div class="brent-driver-title">&#9889; Substitution Effects &mdash; Gas vs Oil Switching</div>
    <div class="brent-driver-desc">
      When natural gas prices rise sharply, industrial users and power generators switch from
      gas to oil, increasing oil demand. TTF at &euro;{ttf_price:.2f}/MWh and EU gas storage at
      {storage_pct:.1f}% (vs {storage_norm:.1f}% seasonal norm) directly influence switching pressure.
      High TTF with low storage is bullish for oil demand. This energy interconnection is a key
      analytical edge that most oil-only data providers miss.
      <br><br>
      <a href="/data/ttf-gas-price-today">&#8594; TTF Gas Price Today &rarr;</a>
    </div>
  </div>
</div>

<!-- ── SECTION 6: ENERGY RISK INTELLIGENCE ───────────────────────────── -->
<div class="section-label" style="margin-bottom:20px;">&#9888; Energy Risk Signals Behind Today&rsquo;s Oil Price</div>
<h2 style="font-size:20px;font-weight:700;color:#e2e8f0;margin-bottom:20px;">
  Energy Risk Signals Behind Today&rsquo;s Oil Price
</h2>
<div class="brent-risk-grid">
  <div class="brent-risk-card">
    <a href="/indices/global-energy-risk-index" style="text-decoration:none;color:inherit;">
      <div class="brent-risk-idx-name">Global Energy Risk Index</div>
      <div class="brent-risk-value" style="color:{gc};">{geri_val}</div>
      <div class="brent-risk-band" style="color:{gc};">{geri_band}</div>
      <div class="brent-risk-desc">
        {_sign(geri_delta)}{geri_delta}pt vs yesterday &bull; 0–100 scale
      </div>
    </a>
  </div>
  <div class="brent-risk-card">
    <a href="/indices/europe-energy-risk-index" style="text-decoration:none;color:inherit;">
      <div class="brent-risk-idx-name">European Energy Risk Index</div>
      <div class="brent-risk-value" style="color:{ec};">{eeri_val}</div>
      <div class="brent-risk-band" style="color:{ec};">{eeri_band}</div>
      <div class="brent-risk-desc">
        {_sign(eeri_delta)}{eeri_delta}pt vs yesterday &bull; Europe focus
      </div>
    </a>
  </div>
  <div class="brent-risk-card">
    <a href="/indices/europe-gas-stress-index" style="text-decoration:none;color:inherit;">
      <div class="brent-risk-idx-name">Energy Geopolitical Stress Index</div>
      <div class="brent-risk-value" style="color:{mgc};">{egsi_val:.1f}</div>
      <div class="brent-risk-band" style="color:{mgc};">{egsi_band}</div>
      <div class="brent-risk-desc">Middle East geopolitical stress signal</div>
    </a>
  </div>
</div>
<div class="brent-risk-interp-card">
  <div style="font-size:10px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;
    color:#f97316;margin-bottom:12px;">&#128204; Risk Interpretation</div>
  <p style="font-size:15px;color:#cbd5e1;line-height:1.8;margin-bottom:12px;">
    {_html.escape(geri_interp)}
  </p>
  <p style="font-size:14px;color:#94a3b8;line-height:1.75;margin-bottom:16px;">
    EnergyRiskIQ&rsquo;s proprietary indices suggest
    {'early warning signals warrant monitoring.' if geri_val > 60 else 'markets are pricing in current risk levels without significant premium compression.'}
    EERI at {eeri_val}/100 indicates European supply chain exposure
    {'at acute levels.' if eeri_val > 60 else 'is being managed within historical norms.'}
  </p>
  <a href="/users" style="font-size:13px;font-weight:700;color:#f97316;
    border:1px solid rgba(249,115,22,0.3);border-radius:8px;padding:8px 22px;
    text-decoration:none;display:inline-block;">
    &#128275; Access full risk intelligence &rarr; Free account
  </a>
</div>

<!-- ── SECTION 7: BRENT vs GAS & LNG ────────────────────────────────── -->
<div class="section-label" style="margin-bottom:20px;">&#128101; Brent vs Gas &amp; LNG &mdash; Market Interconnections</div>
<h2 style="font-size:20px;font-weight:700;color:#e2e8f0;margin-bottom:20px;">
  Brent vs Gas &amp; LNG &mdash; Market Interconnections
</h2>
<div class="brent-cross-card">
  <div class="brent-cross-title">&#9889; Oil vs Gas Substitution Dynamics</div>
  <div class="brent-cross-desc">
    When TTF natural gas prices rise sharply, industrial users and utilities switch from gas to oil.
    Currently TTF is at <strong style="color:#60a5fa;">&euro;{ttf_price:.2f}/MWh</strong> and Brent
    at <strong style="color:#f97316;">${brent_price:.2f}/bbl</strong> — this spread determines
    whether substitution pressure is adding to oil demand. With EU gas storage at {storage_pct:.1f}%
    ({storage_health} the {storage_norm:.1f}% seasonal norm), the switching incentive is
    {'moderate, as adequate storage reduces urgent switching need' if storage_dev >= 0 else 'elevated, as low storage creates urgency for alternative energy sourcing'}.
    <br><br>
    <a href="/data/ttf-gas-price-today">View TTF Gas Price Today &rarr;</a>
  </div>
</div>
<div class="brent-cross-card">
  <div class="brent-cross-title">&#9875; LNG vs Oil Price Linkage &amp; JKM Dynamics</div>
  <div class="brent-cross-desc">
    Long-term LNG contracts have historically been indexed to crude oil prices (typically 12–14%
    of Brent). JKM (Japan Korea Marker) at <strong style="color:#22c55e;">${lng_price:.2f}/MMBtu</strong>
    reflects current Asia Pacific LNG spot demand. High LNG prices reduce Asian buyers&rsquo; budgets
    for oil, while low LNG prices signal risk-off in energy markets broadly. The JKM-Brent price
    relationship is a leading indicator of Asian energy demand strength.
    <br><br>
    <a href="/data/jkm-lng-spot-price">View JKM LNG Spot Price &rarr;</a>
  </div>
</div>
<div class="brent-cross-card" style="margin-bottom:40px;">
  <div class="brent-cross-title">&#127956; Seasonal Effects on Brent Crude Oil Price</div>
  <div class="brent-cross-desc">
    Crude oil demand follows predictable seasonal patterns: peak demand periods (summer driving
    season in the US, winter heating in Europe) typically support higher prices. Europe&rsquo;s gas
    storage injection season (April–October) reduces immediate gas demand but can sustain oil
    demand as industrial producers shift sourcing. EU storage at {storage_pct:.1f}% ({storage_health}
    seasonal norm) is a {storage_signal_word} demand signal for oil over the coming quarter.
    <br><br>
    <a href="/gas-storage-levels-in-europe">View Europe Gas Storage Levels &rarr;</a>
  </div>
</div>

<!-- ── SECTION 8: HISTORICAL CONTEXT ────────────────────────────────── -->
<div class="section-label" style="margin-bottom:20px;">&#128199; Brent Oil Price History &amp; Key Levels</div>
<h2 style="font-size:20px;font-weight:700;color:#e2e8f0;margin-bottom:20px;">
  Brent Oil Price History &amp; Key Levels
</h2>
<div class="brent-hist-grid">
  <div class="brent-hist-card">
    <div class="brent-hist-label">30D Low</div>
    <div class="brent-hist-value" style="color:#ef4444;">${low30_val:.2f}</div>
    <div class="brent-hist-date">{low30_date}</div>
  </div>
  <div class="brent-hist-card">
    <div class="brent-hist-label">30D High</div>
    <div class="brent-hist-value" style="color:#22c55e;">${high30_val:.2f}</div>
    <div class="brent-hist-date">{high30_date}</div>
  </div>
  <div class="brent-hist-card">
    <div class="brent-hist-label">YTD Low</div>
    <div class="brent-hist-value" style="color:#ef4444;">${low_ytd_val:.2f}</div>
    <div class="brent-hist-date">{low_ytd_date}</div>
  </div>
  <div class="brent-hist-card">
    <div class="brent-hist-label">YTD High</div>
    <div class="brent-hist-value" style="color:#22c55e;">${high_ytd_val:.2f}</div>
    <div class="brent-hist-date">{high_ytd_date}</div>
  </div>
</div>
<div style="background:var(--card);border:1px solid var(--border);border-radius:12px;
  padding:20px 24px;margin-bottom:40px;">
  <div style="font-size:11px;font-weight:700;letter-spacing:1px;text-transform:uppercase;
    color:#94a3b8;margin-bottom:14px;">Key Level Analysis</div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
    <div>
      <div style="font-size:12px;color:#94a3b8;margin-bottom:3px;">30D Range</div>
      <div style="font-size:14px;font-weight:700;color:#e2e8f0;">${low30_val:.2f} &ndash; ${high30_val:.2f}</div>
    </div>
    <div>
      <div style="font-size:12px;color:#94a3b8;margin-bottom:3px;">30D Range Width</div>
      <div style="font-size:14px;font-weight:700;color:#e2e8f0;">${(high30_val - low30_val):.2f}/bbl ({round((high30_val - low30_val) / low30_val * 100, 1) if low30_val else 0:.1f}%)</div>
    </div>
    <div>
      <div style="font-size:12px;color:#94a3b8;margin-bottom:3px;">Distance from YTD High</div>
      <div style="font-size:14px;font-weight:700;color:{'#ef4444' if dist_to_ytd_high > 0 else '#22c55e'};">
        {'$' + str(abs(dist_to_ytd_high)) + ' (' + str(abs(dist_to_ytd_high_pct)) + '%) below YTD high' if dist_to_ytd_high > 0 else 'At or above YTD high'}
      </div>
    </div>
    <div>
      <div style="font-size:12px;color:#94a3b8;margin-bottom:3px;">Brent-WTI Spread</div>
      <div style="font-size:14px;font-weight:700;color:#e2e8f0;">${brent_wti_spread:.2f}/bbl</div>
    </div>
  </div>
  <div style="margin-top:14px;font-size:12px;color:#64748b;">
    &#8594; <a href="/research/global-energy-risk-timeline" style="color:#f97316;text-decoration:none;">Global Energy Risk Timeline — historical events and price correlations</a>
  </div>
</div>

<!-- ── SECTION 9: TODAY'S OIL MARKET INSIGHT (RETURN ENGINE) ─────────── -->
<div class="section-label" style="margin-bottom:20px;">&#128161; Today&rsquo;s Oil Market Insight</div>
<div class="brent-insight-card">
  <h2 style="font-size:18px;font-weight:700;color:#e2e8f0;margin-bottom:20px;">
    Today&rsquo;s Oil Market Insight
  </h2>
  <div class="brent-insight-item">
    <div class="brent-insight-item-title">What moved oil today</div>
    <div class="brent-insight-item-body">{_html.escape(insight['what_moved'])}</div>
  </div>
  <div class="brent-insight-item">
    <div class="brent-insight-item-title">Why it matters</div>
    <div class="brent-insight-item-body">{_html.escape(insight['why_matters'])}</div>
  </div>
  <div class="brent-insight-item" style="margin-bottom:0;">
    <div class="brent-insight-item-title">What to watch next</div>
    <div class="brent-insight-item-body">{_html.escape(insight['what_to_watch'])}</div>
  </div>
  <div style="margin-top:18px;font-size:10px;color:#64748b;">
    Analysis generated by EnergyRiskIQ&rsquo;s proprietary market intelligence engine &bull; {today_str} &bull; Not financial advice.
  </div>
</div>

<!-- ── SECTION 10: CONVERSION BLOCK ─────────────────────────────────── -->
<div class="brent-cta-card">
  <div class="brent-cta-label">Daily Oil Market Intelligence</div>
  <h2 class="brent-cta-h2">Stay Ahead of Oil Market Moves</h2>
  <p class="brent-cta-sub">
    Get daily Brent crude price alerts, energy risk signals, and market interpretation
    from EnergyRiskIQ&rsquo;s proprietary analysis engine.
  </p>
  <div class="brent-cta-benefits">
    <span class="brent-cta-benefit">Real-time oil price alerts</span>
    <span class="brent-cta-benefit">GERI &amp; EERI risk signals</span>
    <span class="brent-cta-benefit">Daily market interpretation</span>
    <span class="brent-cta-benefit">Brent-WTI spread tracking</span>
  </div>
  <a href="/users" class="brent-cta-btn-primary">
    Create Free Account &rarr;
  </a>
  <div class="brent-cta-credits">No credit card required &bull; Free plan always available</div>
</div>

<!-- ── SECTION 11: FAQ ────────────────────────────────────────────────── -->
<div class="section-label" style="margin-bottom:20px;">&#10067; Brent Oil Price &mdash; FAQs</div>
<h2 style="font-size:20px;font-weight:700;color:#e2e8f0;margin-bottom:20px;">
  Brent Crude Oil Price &mdash; Frequently Asked Questions
</h2>
{faq_html}

<div style="margin-bottom:40px;"></div>

<!-- ── SECTION 12: INTERNAL LINK FOOTER ─────────────────────────────── -->
<div class="brent-link-footer">
  <div class="brent-link-footer-section">
    <div class="brent-link-footer-title">Data</div>
    <div class="brent-link-footer-grid">
      <a href="/data/ttf-gas-price-today" class="brent-link-footer-pill">&#127470;&#127489; TTF Gas Price</a>
      <a href="/data/jkm-lng-spot-price" class="brent-link-footer-pill">&#9875; JKM LNG Price</a>
      <a href="/data/europe-lng-supply-demand" class="brent-link-footer-pill">&#128168; LNG Supply-Demand</a>
      <a href="/gas-storage-levels-in-europe" class="brent-link-footer-pill">&#128201; Gas Storage</a>
      <a href="/data/energy-risk-snapshot" class="brent-link-footer-pill">&#128248; Risk Snapshot</a>
    </div>
  </div>
  <div class="brent-link-footer-section">
    <div class="brent-link-footer-title">Indices</div>
    <div class="brent-link-footer-grid">
      <a href="/indices/global-energy-risk-index" class="brent-link-footer-pill">&#127758; Global Energy Risk Index</a>
      <a href="/indices/europe-energy-risk-index" class="brent-link-footer-pill">&#127482;&#127466; Europe Energy Risk Index</a>
      <a href="/indices/europe-gas-stress-index" class="brent-link-footer-pill">&#128137; Europe Gas Stress Index</a>
    </div>
  </div>
  <div class="brent-link-footer-section">
    <div class="brent-link-footer-title">Research</div>
    <div class="brent-link-footer-grid">
      <a href="/research/global-energy-risk-timeline" class="brent-link-footer-pill">&#128337; Global Energy Risk Timeline</a>
      <a href="/data/global-energy-risk-forecast" class="brent-link-footer-pill">&#128202; Energy Risk Forecast</a>
    </div>
  </div>
  <div class="brent-link-footer-section" style="margin-bottom:0;">
    <div class="brent-link-footer-title">License</div>
    <div class="brent-link-footer-grid">
      <a href="/data-license" class="brent-link-footer-pill">&#128196; Data License &amp; Usage Terms</a>
    </div>
  </div>
</div>

<!-- ── CITATION & REFERENCE ──────────────────────────────────────────── -->
<div class="section-label" style="margin-bottom:20px;">&#128196; Citation &amp; Reference</div>
<div class="brent-cite-card">
  <h3 style="font-size:15px;font-weight:700;color:#e2e8f0;margin-bottom:8px;">How to Cite This Data</h3>
  <p class="brent-cite-desc">
    This page is updated daily with fresh Brent crude oil price data and proprietary risk analysis.
    To reference this data in research, journalism, or professional reports, use the citation below.
  </p>
  <div style="position:relative;background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.06);
    border-radius:8px;padding:16px 16px 40px;">
    <pre class="brent-cite-code">EnergyRiskIQ. ({today_date[:4]}). <em>Brent Crude Oil Price Today &mdash; {today_str}</em>.
Retrieved from <a href="{BASE_URL}/data/brent-crude-oil-price-today">{BASE_URL}/data/brent-crude-oil-price-today</a>
Data sources: OilPriceAPI (Brent daily), yfinance BZ=F (intraday), EnergyRiskIQ risk pipeline (GERI, EERI, EGSI-M).</pre>
    <button style="position:absolute;bottom:12px;right:12px;font-size:11px;font-weight:700;
      padding:5px 14px;border-radius:5px;background:rgba(212,160,23,0.12);
      border:1px solid rgba(212,160,23,0.35);color:#d4a017;cursor:pointer;"
      onclick="this.textContent='Copied!';setTimeout(()=>this.textContent='Copy',2000);
        navigator.clipboard&&navigator.clipboard.writeText('EnergyRiskIQ. ({today_date[:4]}). Brent Crude Oil Price Today — {today_str}. Retrieved from {BASE_URL}/data/brent-crude-oil-price-today')">
      Copy
    </button>
  </div>
  <div style="margin-top:12px;font-size:11px;color:#334155;line-height:1.7;">
    Data sourced from: OilPriceAPI (Brent spot price), yfinance BZ=F futures (intraday),
    EnergyRiskIQ internal risk scoring pipeline (GERI, EERI, EGSI-M).
    See <a href="{BASE_URL}/data-license" style="color:#64748b;">/data-license</a> for full usage terms.
    <strong>Not financial advice.</strong>
  </div>
</div>

</main>

<footer class="page-footer">
  <div>
    &copy; {today_date[:4]} EnergyRiskIQ &bull;
    <a href="/">Home</a>
    <a href="/indices">Indices</a>
    <a href="/data/energy-risk-snapshot">Risk Snapshot</a>
    <a href="/data/brent-crude-oil-price-today">Brent Price</a>
    <a href="/data/global-energy-risk-forecast">Forecast</a>
    <a href="/sitemap-index.xml">Sitemap</a>
    &bull; Not financial advice.
  </div>
</footer>

<!-- Chart toggle JS -->
<script>
function switchRange(range) {{
  var charts = document.querySelectorAll('.brent-chart-container');
  charts.forEach(function(c) {{ c.classList.remove('active'); }});
  var tabs = document.querySelectorAll('.brent-range-tab');
  tabs.forEach(function(t) {{ t.classList.remove('active'); }});
  var el = document.getElementById('chart-' + range);
  if (el) el.classList.add('active');
  var clicked = event.target;
  if (clicked) clicked.classList.add('active');
}}
</script>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────────────
# Route Handler
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/data/brent-crude-oil-price-today")
async def brent_crude_oil_price():
    async def generate():
        yield _BRENT_LOADER_HTML

        try:
            data = await asyncio.to_thread(_compute_brent_data)
        except Exception as exc:
            logger.error(f"Brent data fetch failed: {exc}", exc_info=True)
            yield f"""<script>var l=document.getElementById('snap-loader');if(l)l.style.display='none';
document.body.style.overflow='';</script>
<div style="color:#ef4444;padding:40px;font-family:sans-serif;background:#0b0f1a">
<h2>Error loading Brent price data</h2><p>{_html.escape(str(exc))}</p></div></body></html>"""
            return

        try:
            html_body = await asyncio.to_thread(_build_brent_html, data)
            yield html_body
        except Exception as exc:
            logger.error(f"Brent HTML build failed: {exc}", exc_info=True)
            yield f"""<script>var l=document.getElementById('snap-loader');if(l)l.style.display='none';
document.body.style.overflow='';</script>
<div style="color:#ef4444;padding:40px;font-family:sans-serif;background:#0b0f1a">
<h2>Error building page</h2><p>{_html.escape(str(exc))}</p></div></body></html>"""

    return StreamingResponse(generate(), media_type="text/html")
