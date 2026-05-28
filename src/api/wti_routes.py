"""
WTI Crude Oil Price Today (West Texas Intermediate) Page
Route: /data/wti-crude-oil-price-today

SEO-optimised live WTI crude oil price page with intraday status,
multi-range chart with overlays (Brent / VIX / GERI / TTF / NatGas),
Brent-WTI spread, risk context, drivers, FAQ, citation block.

Custom-algorithm wording (not "AI"). Fully mobile responsive.
Anti-copy text protection (does NOT block search engines).
"""
import logging
import asyncio
import html as _html
import json as _json
from datetime import datetime, timezone, date as _date, timedelta

from fastapi import APIRouter
from fastapi.responses import StreamingResponse, Response

from src.db.db import execute_production_one, execute_production_query
from src.api.snapshot_routes import (
    _PAGE_CSS, _LOADER_HTML, BAND_COLORS, _safe_float,
)
from src.api.forecast_routes import (
    _arrow, _chg_color, _fmt_date,
)

router = APIRouter()
logger = logging.getLogger(__name__)

BASE_URL = "https://energyriskiq.com"
WTI_COLOR = "#22d3ee"          # cyan — distinct vs Brent's orange
WTI_COLOR_DIM = "rgba(34,211,238,0.18)"


# ─────────────────────────────────────────────────────────────────────────────
# Loader skin
# ─────────────────────────────────────────────────────────────────────────────

_WTI_LOADER_HTML = _LOADER_HTML.replace(
    'Global Energy Risk Snapshot | EnergyRiskIQ',
    'WTI Crude Oil Price Today (West Texas Intermediate) | Live Chart &amp; Market Analysis | EnergyRiskIQ'
).replace(
    'name="description" content="Live global energy risk snapshot. Current GERI, EERI and EGSI-M index values with Brent crude, TTF gas, VIX and LNG market prices."',
    'name="description" content="Live WTI crude oil price today (West Texas Intermediate). Track intraday moves, charts, volatility, Brent-WTI spread, and global energy risk signals."'
).replace(
    'rel="canonical" href="https://energyriskiq.com/data/energy-risk-snapshot"',
    'rel="canonical" href="https://energyriskiq.com/data/wti-crude-oil-price-today"'
).replace(
    'Fetching GERI\u00a0&\u00a0EERI indices\u2026',
    'Fetching WTI crude oil prices\u2026',
).replace(
    '<span class="ld-tag">GERI</span>\n    <span class="ld-tag">EERI</span>\n    <span class="ld-tag">EGSI&#8209;M</span>\n    <span class="ld-tag">Brent</span>\n    <span class="ld-tag">TTF</span>',
    '<span class="ld-tag">WTI</span>\n    <span class="ld-tag">Brent</span>\n    <span class="ld-tag">VIX</span>\n    <span class="ld-tag">GERI</span>\n    <span class="ld-tag">Spread</span>',
)


# ─────────────────────────────────────────────────────────────────────────────
# Page-specific CSS
# ─────────────────────────────────────────────────────────────────────────────

_WTI_CSS = f"""
.wti-protected {{
  user-select: none;
  -webkit-user-select: none;
  -moz-user-select: none;
  -ms-user-select: none;
}}

/* Sticky price bar */
.wti-sticky-bar {{
  position: sticky; top: 0; z-index: 99;
  display: flex; align-items: center; flex-wrap: wrap; gap: 14px;
  background: linear-gradient(90deg, #0e1422 0%, #111a2c 100%);
  border-bottom: 1px solid rgba(34,211,238,0.25);
  padding: 10px 18px; font-size: 13px;
}}
.wti-sticky-label {{ font-weight: 800; color: {WTI_COLOR}; letter-spacing: 1px; font-size: 11px; text-transform: uppercase; }}
.wti-sticky-price {{ font-weight: 800; color: #f1f5f9; font-variant-numeric: tabular-nums; font-size: 15px; }}
.wti-sticky-chg {{ font-weight: 700; font-variant-numeric: tabular-nums; }}
.wti-sticky-time {{ color: #64748b; font-size: 11px; margin-left: auto; }}
.wti-sticky-cta {{
  background: linear-gradient(135deg,#06b6d4,#3b82f6); color:#fff !important;
  text-decoration: none; font-weight: 700; font-size: 12px;
  padding: 6px 14px; border-radius: 6px;
}}
@media (max-width: 640px) {{
  .wti-sticky-time {{ display: none; }}
  .wti-sticky-bar {{ padding: 8px 12px; gap: 10px; font-size: 12px; }}
}}

/* Hero card */
.wti-hero-card {{
  background: linear-gradient(135deg, #0c1322 0%, #0e2433 50%, #0f172a 100%);
  border: 1px solid rgba(34,211,238,0.3);
  border-radius: 20px;
  padding: 32px 36px;
  margin: 28px auto 36px;
  position: relative;
  overflow: hidden;
  max-width: 760px;
}}
.wti-hero-card::before {{
  content: '';
  position: absolute; top: 0; left: 0; right: 0; height: 3px;
  background: linear-gradient(90deg, {WTI_COLOR}, rgba(34,211,238,0.2));
}}
.wti-hero-bench {{
  font-size: 11px; font-weight: 700; letter-spacing: 2px; text-transform: uppercase;
  color: {WTI_COLOR}; margin-bottom: 8px;
}}
.wti-hero-price-row {{ display: flex; align-items: baseline; gap: 14px; flex-wrap: wrap; }}
.wti-hero-price {{
  font-size: 56px; font-weight: 800; line-height: 1; color: #fff;
  font-variant-numeric: tabular-nums;
}}
.wti-hero-price sup {{ font-size: 24px; font-weight: 600; vertical-align: top; margin-top: 8px; }}
.wti-hero-unit {{ font-size: 16px; color: #94a3b8; }}
.wti-hero-chg {{ font-size: 16px; font-weight: 700; margin-top: 10px; }}
.wti-hero-meta {{
  margin-top: 14px; display: flex; flex-wrap: wrap; gap: 14px;
  font-size: 12px; color: #94a3b8;
}}
.wti-hero-meta b {{ color: #cbd5e1; }}
.wti-hero-cta-row {{ margin-top: 22px; display: flex; gap: 12px; flex-wrap: wrap; }}
.wti-intraday-tag {{
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 11px; font-weight: 700; padding: 3px 10px;
  border-radius: 20px; background: rgba(34,211,238,0.12);
  color: {WTI_COLOR}; margin-left: 8px;
}}
.wti-intraday-tag::before {{
  content: ''; width: 6px; height: 6px; border-radius: 50%;
  background: {WTI_COLOR}; box-shadow: 0 0 8px {WTI_COLOR};
}}
.wti-cta-primary {{
  background: linear-gradient(135deg,#06b6d4,#3b82f6); color:#fff !important;
  text-decoration: none; font-weight: 700; font-size: 14px;
  padding: 12px 22px; border-radius: 10px;
}}
.wti-cta-secondary {{
  background: transparent; color: #cbd5e1 !important;
  border: 1px solid rgba(255,255,255,0.18);
  text-decoration: none; font-weight: 600; font-size: 14px;
  padding: 12px 22px; border-radius: 10px;
}}
.wti-cta-secondary:hover {{ border-color: rgba(34,211,238,0.5); color:#fff !important; }}
@media (max-width: 540px) {{
  .wti-hero-card {{ padding: 22px 18px; border-radius: 14px; }}
  .wti-hero-price {{ font-size: 40px; }}
  .wti-hero-price sup {{ font-size: 18px; margin-top: 5px; }}
}}

/* Sentiment badges */
.wti-sentiment {{
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 11px; font-weight: 800; letter-spacing: 1.2px;
  text-transform: uppercase; padding: 4px 12px; border-radius: 20px;
}}

/* Chart card */
.wti-chart-card {{
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 24px 26px;
  margin-bottom: 44px;
}}
.wti-chart-toolbar {{
  display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
  margin: 16px 0 12px;
}}
.wti-chart-toolbar .wti-tb-group {{ display: flex; flex-wrap: wrap; gap: 6px; }}
.wti-tb-btn {{
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.08);
  color: #cbd5e1;
  font-size: 11px; font-weight: 700;
  padding: 5px 12px; border-radius: 8px; cursor: pointer;
  user-select: none; letter-spacing: 0.5px;
  transition: all 0.15s;
}}
.wti-tb-btn:hover {{ border-color: rgba(34,211,238,0.4); color: #fff; }}
.wti-tb-btn.active {{
  background: rgba(34,211,238,0.18);
  border-color: rgba(34,211,238,0.6);
  color: {WTI_COLOR};
}}
.wti-tb-divider {{
  width: 1px; height: 18px; background: rgba(255,255,255,0.1);
  margin: 0 6px;
}}
.wti-tb-label {{
  font-size: 10px; font-weight: 700; color: #64748b;
  letter-spacing: 1.2px; text-transform: uppercase; margin-right: 2px;
}}
.wti-chart-panel {{ display: none; }}
.wti-chart-panel.active {{ display: block; }}
.wti-chart-legend {{
  display: flex; flex-wrap: wrap; gap: 14px; margin-top: 10px;
  font-size: 11px; color: #94a3b8;
}}
.wti-chart-legend .lg-dot {{
  display: inline-block; width: 10px; height: 10px;
  border-radius: 2px; margin-right: 6px; vertical-align: middle;
}}

/* Snapshot grid */
.wti-snap-grid {{
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
  margin-bottom: 40px;
}}
@media (max-width: 780px) {{ .wti-snap-grid {{ grid-template-columns: 1fr 1fr; }} }}
@media (max-width: 460px) {{ .wti-snap-grid {{ grid-template-columns: 1fr; }} }}
.wti-snap-cell {{
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 16px 18px;
}}
.wti-snap-label {{
  font-size: 10px; font-weight: 700; letter-spacing: 1.4px;
  text-transform: uppercase; color: #64748b; margin-bottom: 6px;
}}
.wti-snap-val {{
  font-size: 22px; font-weight: 800; color: #f1f5f9;
  font-variant-numeric: tabular-nums; margin-bottom: 4px;
}}
.wti-snap-sub {{ font-size: 11px; color: #94a3b8; }}

/* Driver / risk / link grids */
.wti-grid-2 {{
  display: grid; grid-template-columns: 1fr 1fr;
  gap: 16px; margin-bottom: 36px;
}}
@media (max-width: 780px) {{ .wti-grid-2 {{ grid-template-columns: 1fr; }} }}
.wti-driver-grid {{
  display: grid; grid-template-columns: repeat(3, 1fr);
  gap: 16px; margin-bottom: 40px;
}}
@media (max-width: 880px) {{ .wti-driver-grid {{ grid-template-columns: 1fr 1fr; }} }}
@media (max-width: 540px) {{ .wti-driver-grid {{ grid-template-columns: 1fr; }} }}
.wti-driver-card {{
  background: var(--card); border: 1px solid var(--border);
  border-radius: 12px; padding: 18px 20px;
  transition: border-color 0.2s, transform 0.2s;
}}
.wti-driver-card:hover {{ border-color: rgba(34,211,238,0.35); transform: translateY(-2px); }}
.wti-driver-icon {{ font-size: 1.6rem; margin-bottom: 6px; }}
.wti-driver-title {{
  font-size: 13px; font-weight: 800; color: #f1f5f9; margin-bottom: 6px;
}}
.wti-driver-body {{ font-size: 12.5px; color: #94a3b8; line-height: 1.55; margin-bottom: 10px; }}
.wti-driver-link {{
  font-size: 11px; font-weight: 700; color: {WTI_COLOR};
  text-decoration: none; letter-spacing: 0.5px;
}}
.wti-driver-link:hover {{ text-decoration: underline; }}

/* Risk panel */
.wti-risk-grid {{
  display: grid; grid-template-columns: repeat(4, 1fr);
  gap: 14px; margin-bottom: 32px;
}}
@media (max-width: 780px) {{ .wti-risk-grid {{ grid-template-columns: 1fr 1fr; }} }}
@media (max-width: 440px) {{ .wti-risk-grid {{ grid-template-columns: 1fr; }} }}
.wti-risk-card {{
  background: var(--card); border: 1px solid var(--border);
  border-radius: 14px; padding: 18px;
  text-decoration: none; color: inherit;
  display: block;
  transition: border-color 0.2s, transform 0.2s;
}}
.wti-risk-card:hover {{ transform: translateY(-2px); }}
.wti-risk-name {{ font-size: 10px; font-weight: 700; letter-spacing: 1.2px; text-transform: uppercase; color: #64748b; }}
.wti-risk-val {{ font-size: 28px; font-weight: 800; color: #f1f5f9; font-variant-numeric: tabular-nums; margin: 4px 0 2px; }}
.wti-risk-band {{ font-size: 11px; font-weight: 700; letter-spacing: 1px; text-transform: uppercase; }}
.wti-risk-desc {{ font-size: 11px; color: #94a3b8; margin-top: 6px; }}

/* Brent-WTI spread card */
.wti-spread-card {{
  background: linear-gradient(135deg, #0c1322 0%, #14233a 50%, #0f172a 100%);
  border: 1px solid rgba(34,211,238,0.25);
  border-radius: 16px; padding: 28px 32px;
  margin-bottom: 40px;
}}
.wti-spread-grid {{
  display: grid; grid-template-columns: 1fr 1fr 1fr;
  gap: 22px; align-items: start;
}}
@media (max-width: 720px) {{ .wti-spread-grid {{ grid-template-columns: 1fr; gap: 18px; }} }}
.wti-spread-cell {{ text-align: center; }}
.wti-spread-cell-label {{ font-size: 10px; font-weight: 700; letter-spacing: 1.4px; text-transform: uppercase; color: #64748b; margin-bottom: 6px; }}
.wti-spread-cell-val {{ font-size: 30px; font-weight: 800; color: #fff; font-variant-numeric: tabular-nums; }}
.wti-spread-cell-sub {{ font-size: 11px; color: #94a3b8; margin-top: 4px; }}
.wti-spread-note {{
  margin-top: 22px; font-size: 13px; color: #94a3b8; line-height: 1.7;
  padding-top: 18px; border-top: 1px solid rgba(255,255,255,0.06);
}}
.wti-spread-note strong {{ color: #cbd5e1; }}

/* Commentary card */
.wti-commentary {{
  background: linear-gradient(135deg, #111827 0%, #0f172a 100%);
  border: 1px solid rgba(212,160,23,0.2);
  border-radius: 14px;
  padding: 26px 28px;
  margin-bottom: 40px;
  position: relative;
  overflow: hidden;
}}
.wti-commentary::before {{
  content: '';
  position: absolute; top: 0; left: 0; right: 0; height: 3px;
  background: linear-gradient(90deg, var(--gold), transparent);
}}
.wti-commentary p {{ font-size: 15px; color: #cbd5e1; line-height: 1.75; margin-bottom: 1em; }}
.wti-commentary p:last-child {{ margin-bottom: 0; }}
.wti-commentary p strong {{ color: #fff; }}
.wti-bias-badge {{
  display: inline-block; font-size: 11px; font-weight: 800;
  letter-spacing: 1.2px; text-transform: uppercase;
  padding: 5px 14px; border-radius: 20px; margin-bottom: 14px;
}}
.wti-engine-tag {{
  font-size: 10px; font-weight: 700; color: #64748b;
  letter-spacing: 1.2px; text-transform: uppercase; margin-top: 14px;
}}

/* Historical data table */
.wti-table-wrap {{
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 14px;
  overflow: hidden;
  margin-bottom: 40px;
}}
.wti-table-head {{
  display: flex; justify-content: space-between; align-items: center;
  padding: 16px 20px; border-bottom: 1px solid var(--border);
  flex-wrap: wrap; gap: 10px;
}}
.wti-table-head h3 {{ font-size: 16px; font-weight: 700; color: #f1f5f9; margin: 0; }}
.wti-table-csv {{
  font-size: 12px; font-weight: 700; color: {WTI_COLOR};
  text-decoration: none; padding: 6px 14px; border-radius: 8px;
  border: 1px solid rgba(34,211,238,0.3); background: rgba(34,211,238,0.06);
}}
.wti-table-scroll {{ overflow-x: auto; }}
.wti-table {{ width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }}
.wti-table th, .wti-table td {{
  padding: 10px 16px; text-align: left; font-size: 13px;
  border-bottom: 1px solid rgba(255,255,255,0.04);
}}
.wti-table th {{
  background: rgba(255,255,255,0.02);
  font-size: 10px; font-weight: 700; letter-spacing: 1.2px;
  text-transform: uppercase; color: #64748b;
}}
.wti-table td {{ color: #cbd5e1; }}
.wti-table tr:last-child td {{ border-bottom: none; }}

/* Related intelligence wheel grid */
.wheel-grid {{
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
  margin-bottom: 40px;
}}
@media (max-width: 980px) {{ .wheel-grid {{ grid-template-columns: repeat(3, 1fr); }} }}
@media (max-width: 720px) {{ .wheel-grid {{ grid-template-columns: 1fr 1fr; }} }}
@media (max-width: 420px) {{ .wheel-grid {{ grid-template-columns: 1fr; }} }}
.wheel-link {{
  display: flex; flex-direction: column; align-items: center; justify-content: flex-start;
  text-align: center; gap: 8px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 20px 14px 18px;
  text-decoration: none !important;
  color: inherit;
  transition: border-color 0.2s, box-shadow 0.2s, transform 0.2s;
  min-height: 130px;
}}
.wheel-link:hover {{
  border-color: rgba(34,211,238,0.45);
  box-shadow: 0 4px 22px rgba(34,211,238,0.10);
  transform: translateY(-2px);
}}
.wheel-link-icon {{ font-size: 1.7rem; line-height: 1; }}
.wheel-link-label {{
  font-size: 11px; font-weight: 800; letter-spacing: 1.2px;
  text-transform: uppercase; color: {WTI_COLOR};
}}
.wheel-link-desc {{ font-size: 11.5px; color: #94a3b8; line-height: 1.45; }}

/* FAQ accordion */
.wti-faq {{ margin-bottom: 40px; }}
.wti-faq details {{
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 0;
  margin-bottom: 10px;
  overflow: hidden;
}}
.wti-faq summary {{
  list-style: none; cursor: pointer;
  font-size: 14px; font-weight: 700; color: #f1f5f9;
  padding: 16px 50px 16px 20px;
  position: relative;
}}
.wti-faq summary::-webkit-details-marker {{ display: none; }}
.wti-faq summary::after {{
  content: '+'; position: absolute; right: 18px; top: 50%;
  transform: translateY(-50%); font-size: 22px;
  color: {WTI_COLOR}; transition: transform 0.2s; font-weight: 400;
}}
.wti-faq details[open] summary::after {{ content: '\u2212'; }}
.wti-faq details > div {{
  padding: 0 20px 18px; font-size: 13.5px; color: #94a3b8; line-height: 1.7;
}}

/* License block */
.wti-license {{
  background: rgba(255,255,255,0.02);
  border: 1px solid rgba(255,255,255,0.06);
  border-radius: 10px; padding: 18px 20px;
  margin-bottom: 40px; font-size: 12px; color: #94a3b8;
}}
.wti-license a {{ color: {WTI_COLOR}; text-decoration: none; font-weight: 700; }}
.wti-license a:hover {{ text-decoration: underline; }}

/* Conversion */
.wti-conv {{
  background: linear-gradient(135deg, #0c1322 0%, #14233a 50%, #0f172a 100%);
  border: 1px solid rgba(34,211,238,0.3);
  border-radius: 18px; padding: 32px;
  text-align: center; margin-bottom: 40px;
}}
.wti-conv h2 {{
  font-family: 'DM Serif Display', serif;
  font-size: clamp(22px, 4vw, 32px); font-weight: 400;
  color: #fff; line-height: 1.25; margin-bottom: 12px;
}}
.wti-conv p {{ font-size: 14px; color: #94a3b8; max-width: 560px; margin: 0 auto 22px; }}
.wti-conv .wti-cta-primary, .wti-conv .wti-cta-secondary {{ margin: 4px; }}

/* Citation */
.wti-cite-card {{
  background: var(--card); border: 1px solid var(--border);
  border-radius: 14px; padding: 24px 26px; margin-bottom: 36px;
  position: relative;
}}
.wti-cite-card h3 {{ font-size: 16px; font-weight: 700; color: #f1f5f9; margin-bottom: 8px; }}
.wti-cite-desc {{ font-size: 13px; color: #94a3b8; margin-bottom: 14px; }}
.wti-cite-code-wrap {{ position: relative; background: rgba(0,0,0,0.25); border-radius: 10px; padding: 16px 18px; }}
.wti-cite-code {{
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 12px; color: #cbd5e1; line-height: 1.7;
  margin: 0; white-space: pre-wrap; word-break: break-word;
}}
.wti-cite-code a {{ color: {WTI_COLOR}; text-decoration: none; }}
.wti-cite-copy-btn {{
  position: absolute; top: 12px; right: 12px;
  background: rgba(34,211,238,0.15); color: {WTI_COLOR};
  border: 1px solid rgba(34,211,238,0.35); border-radius: 6px;
  font-size: 11px; font-weight: 700; padding: 5px 12px; cursor: pointer;
}}
.wti-cite-footer {{ font-size: 11px; color: #64748b; margin-top: 12px; line-height: 1.6; }}
@media (max-width: 600px) {{
  .wti-cite-copy-btn {{ position: static; display: block; width: 100%; margin-top: 12px; }}
}}
"""


# ─────────────────────────────────────────────────────────────────────────────
# Multi-series chart (WTI + Brent / VIX / GERI / TTF / NatGas overlays)
# ─────────────────────────────────────────────────────────────────────────────

def _build_wti_chart_svg(rows, brent_rows, vix_rows, geri_rows, ttf_rows, ng_rows,
                         label="3M", height=300):
    """Multi-series SVG chart for one time range.

    Primary: WTI ($/bbl) — labelled on left axis.
    Overlays (toggleable, date-aligned to WTI x-axis): Brent, VIX, GERI, TTF, NatGas (Henry Hub).
    """
    if not rows:
        return (
            f'<div style="padding:40px;color:#64748b;text-align:center;font-size:12px">'
            f'No data available for {label}.</div>'
        )

    W, H = 900, height
    PAD_L, PAD_R, PAD_T, PAD_B = 56, 56, 22, 44
    cw = W - PAD_L - PAD_R
    ch = H - PAD_T - PAD_B

    n_wti = len(rows)
    wti_dates = [r.get('date') for r in rows]
    x_for_idx = lambda i: PAD_L + (i / max(n_wti - 1, 1)) * cw

    def _wti_series():
        vals = [float(r['wti_price']) for r in rows if r.get('wti_price') is not None]
        if len(vals) < 2:
            return '', None, None
        vmin, vmax = min(vals), max(vals)
        if vmin == vmax:
            vmax = vmin * 1.01 + 0.0001
        rng = vmax - vmin
        pts = []
        for i, r in enumerate(rows):
            v = r.get('wti_price')
            if v is None:
                continue
            x = x_for_idx(i)
            y = PAD_T + ch - ((float(v) - vmin) / rng) * ch
            pts.append((x, y))
        if not pts:
            return '', None, None
        path_d = 'M ' + ' L '.join(f'{p[0]:.1f} {p[1]:.1f}' for p in pts)
        area_d = path_d + f' L {pts[-1][0]:.1f} {PAD_T+ch:.1f} L {pts[0][0]:.1f} {PAD_T+ch:.1f} Z'
        svg = (
            f'<g class="wti-series-wti">'
            f'<path d="{area_d}" fill="{WTI_COLOR}" opacity="0.10"/>'
            f'<path d="{path_d}" fill="none" stroke="{WTI_COLOR}" stroke-width="2" '
            f'stroke-linejoin="round" stroke-linecap="round"/>'
            f'</g>'
        )
        return svg, vmin, vmax

    def _overlay(data, val_key, color, klass):
        if not data:
            return ''
        lookup = {r['date']: r[val_key] for r in data if r.get('date') and r.get(val_key) is not None}
        window_vals = [float(lookup[d]) for d in wti_dates if d in lookup]
        if len(window_vals) < 2:
            return ''
        vmin, vmax = min(window_vals), max(window_vals)
        if vmin == vmax:
            vmax = vmin * 1.01 + 0.0001
        rng = vmax - vmin
        segments, cur = [], []
        for i, d in enumerate(wti_dates):
            if d in lookup:
                x = x_for_idx(i)
                y = PAD_T + ch - ((float(lookup[d]) - vmin) / rng) * ch
                cur.append((x, y))
            else:
                if len(cur) >= 2:
                    segments.append(cur)
                cur = []
        if len(cur) >= 2:
            segments.append(cur)
        if not segments:
            return ''
        paths = []
        for seg in segments:
            d_attr = 'M ' + ' L '.join(f'{p[0]:.1f} {p[1]:.1f}' for p in seg)
            paths.append(
                f'<path d="{d_attr}" fill="none" stroke="{color}" stroke-width="1.8" '
                f'stroke-linejoin="round" stroke-linecap="round" opacity="0.85"/>'
            )
        return f'<g class="{klass}">{"".join(paths)}</g>'

    wti_svg, wti_min, wti_max = _wti_series()
    brent_svg = _overlay(brent_rows, 'brent_price', '#f97316', 'wti-series-brent')
    vix_svg   = _overlay(vix_rows,   'vix_close',   '#a78bfa', 'wti-series-vix')
    geri_svg  = _overlay(geri_rows,  'value',       '#ef4444', 'wti-series-geri')
    ttf_svg   = _overlay(ttf_rows,   'ttf_price',   '#60a5fa', 'wti-series-ttf')
    ng_svg    = _overlay(ng_rows,    'price',       '#22c55e', 'wti-series-ng')

    # Y-axis ticks (WTI $/bbl)
    grid_svg = ''
    if wti_min is not None and wti_max is not None:
        ticks = 5
        rng = wti_max - wti_min
        for t in range(ticks + 1):
            frac = t / ticks
            y = PAD_T + ch - frac * ch
            v = wti_min + frac * rng
            grid_svg += (
                f'<line x1="{PAD_L}" y1="{y:.1f}" x2="{W-PAD_R}" y2="{y:.1f}" '
                f'stroke="rgba(255,255,255,0.05)" stroke-width="1"/>'
                f'<text x="{PAD_L-8}" y="{y+3:.1f}" text-anchor="end" '
                f'font-size="10" fill="#64748b" font-family="Inter,sans-serif">'
                f'${v:.1f}</text>'
            )

    # X-axis date labels
    x_label_svg = ''
    if rows:
        n = len(rows)
        label_count = min(6, n)
        for k in range(label_count):
            idx = int(round(k * (n - 1) / max(label_count - 1, 1))) if label_count > 1 else 0
            x = x_for_idx(idx)
            d = rows[idx].get('date')
            txt = _fmt_date(d) if d else ''
            anchor = 'middle' if 0 < k < label_count - 1 else ('start' if k == 0 else 'end')
            x_label_svg += (
                f'<text x="{x:.1f}" y="{PAD_T+ch+22}" text-anchor="{anchor}" '
                f'font-size="10" fill="#64748b" font-family="Inter,sans-serif">{txt}</text>'
            )

    watermark = (
        f'<text x="{W-PAD_R-6}" y="{PAD_T+16}" text-anchor="end" font-size="10" '
        f'fill="rgba(148,163,184,0.18)" font-family="Inter,sans-serif" '
        f'font-style="italic">EnergyRiskIQ.com</text>'
    )

    return (
        f'<svg viewBox="0 0 {W} {H}" preserveAspectRatio="xMidYMid meet" '
        f'xmlns="http://www.w3.org/2000/svg" '
        f'style="width:100%;height:auto;display:block;max-width:100%;" '
        f'class="wti-protected">'
        f'{grid_svg}{x_label_svg}{watermark}'
        f'{ng_svg}{ttf_svg}{geri_svg}{vix_svg}{brent_svg}{wti_svg}'
        f'</svg>'
    )


def _build_intraday_chart_svg(rows, height=240):
    """Simple intraday WTI line chart from intraday_wti rows.

    rows expected: [{date, hour, price}] ascending.
    """
    if not rows or len(rows) < 2:
        return (
            '<div style="padding:30px;color:#64748b;text-align:center;font-size:12px">'
            'Intraday data not yet available for today.</div>'
        )
    W, H = 900, height
    PAD_L, PAD_R, PAD_T, PAD_B = 56, 56, 22, 36
    cw = W - PAD_L - PAD_R
    ch = H - PAD_T - PAD_B

    vals = [float(r['price']) for r in rows if r.get('price') is not None]
    vmin, vmax = min(vals), max(vals)
    if vmin == vmax:
        vmax = vmin * 1.001 + 0.0001
    rng = vmax - vmin
    n = len(rows)
    pts = []
    for i, r in enumerate(rows):
        x = PAD_L + (i / max(n - 1, 1)) * cw
        y = PAD_T + ch - ((float(r['price']) - vmin) / rng) * ch
        pts.append((x, y))

    path_d = 'M ' + ' L '.join(f'{p[0]:.1f} {p[1]:.1f}' for p in pts)
    area_d = path_d + f' L {pts[-1][0]:.1f} {PAD_T+ch:.1f} L {pts[0][0]:.1f} {PAD_T+ch:.1f} Z'

    # y ticks
    grid_svg = ''
    for t in range(5):
        frac = t / 4
        y = PAD_T + ch - frac * ch
        v = vmin + frac * rng
        grid_svg += (
            f'<line x1="{PAD_L}" y1="{y:.1f}" x2="{W-PAD_R}" y2="{y:.1f}" '
            f'stroke="rgba(255,255,255,0.05)" stroke-width="1"/>'
            f'<text x="{PAD_L-8}" y="{y+3:.1f}" text-anchor="end" font-size="10" '
            f'fill="#64748b" font-family="Inter,sans-serif">${v:.1f}</text>'
        )

    # x hour labels (every ~4)
    x_label_svg = ''
    step = max(n // 6, 1)
    for i in range(0, n, step):
        r = rows[i]
        x = PAD_L + (i / max(n - 1, 1)) * cw
        h = r.get('hour')
        txt = f'{int(h):02d}:00' if h is not None else ''
        x_label_svg += (
            f'<text x="{x:.1f}" y="{PAD_T+ch+18}" text-anchor="middle" font-size="10" '
            f'fill="#64748b" font-family="Inter,sans-serif">{txt}</text>'
        )

    return (
        f'<svg viewBox="0 0 {W} {H}" preserveAspectRatio="xMidYMid meet" '
        f'xmlns="http://www.w3.org/2000/svg" '
        f'style="width:100%;height:auto;display:block;max-width:100%;" '
        f'class="wti-protected">'
        f'{grid_svg}{x_label_svg}'
        f'<path d="{area_d}" fill="{WTI_COLOR}" opacity="0.10"/>'
        f'<path d="{path_d}" fill="none" stroke="{WTI_COLOR}" stroke-width="2" '
        f'stroke-linejoin="round" stroke-linecap="round"/>'
        f'</svg>'
    )


# ─────────────────────────────────────────────────────────────────────────────
# Custom-algorithm commentary
# ─────────────────────────────────────────────────────────────────────────────

def _wti_commentary(wti_latest, wti_chg_pct, wti_30d_chg_pct, spread,
                    vix_close, geri_val, geri_band, eeri_val, brent_latest):
    """Deterministic 3-paragraph commentary with directional-bias badge."""
    bull, bear = 0, 0
    if wti_chg_pct > 1:   bull += 1
    if wti_chg_pct < -1:  bear += 1
    if wti_30d_chg_pct > 3:  bull += 1
    if wti_30d_chg_pct < -3: bear += 1
    if geri_val >= 65:    bull += 1
    if geri_val <= 40:    bear += 1
    if eeri_val >= 65:    bull += 1
    if vix_close >= 25:   bull += 1  # risk premium into oil
    if vix_close < 15:    bear += 1
    if spread is not None:
        if spread > 5:  bull += 1   # tight Atlantic basin → WTI catch-up risk
        if spread < 1:  bear += 1

    if bull - bear >= 2:
        bias = ('BULLISH BIAS', '#22c55e', 'rgba(34,197,94,0.12)')
    elif bear - bull >= 2:
        bias = ('BEARISH BIAS', '#ef4444', 'rgba(239,68,68,0.12)')
    else:
        bias = ('NEUTRAL / RANGE-BOUND', '#eab308', 'rgba(234,179,8,0.12)')

    trend_word = "moved higher" if wti_chg_pct > 0 else "softened" if wti_chg_pct < 0 else "held flat"
    p1 = (
        f"<strong>WTI crude oil is trading near ${wti_latest:.2f}/bbl.</strong> "
        f"On the session WTI has {trend_word} by {wti_chg_pct:+.2f}%, with a "
        f"{wti_30d_chg_pct:+.1f}% move across the trailing 30 trading days. "
        "WTI is the leading US oil benchmark and the marginal price input for North American "
        "refiners, gasoline, jet fuel and downstream fuel inflation."
    )

    spread_txt = f"${spread:+.2f}/bbl" if spread is not None else "n/a"
    geri_word = (geri_band or 'elevated').lower()
    p2 = (
        f"The Brent\u2013WTI spread sits at <strong>{spread_txt}</strong>, "
        f"reflecting the relative tightness of the Atlantic basin versus US Gulf Coast supply. "
        f"GERI &mdash; EnergyRiskIQ&rsquo;s global energy risk index &mdash; reads "
        f"<strong>{geri_val}/100 ({geri_word})</strong>, while EERI is at "
        f"<strong>{eeri_val}/100</strong>. VIX sits at {vix_close:.2f}, "
        "shaping the macro risk-premium that flows into oil."
    )

    if bias[0].startswith('BULL'):
        outlook = (
            "Risk skew currently favours <strong>upside in WTI</strong> on a combination of supportive "
            "macro risk premia, firmer geopolitical signals and a wider Brent\u2013WTI spread. "
            "Custom Algorithm flags continued sensitivity to OPEC+ guidance, US inventory data and "
            "any escalation in Middle East shipping risk."
        )
    elif bias[0].startswith('BEAR'):
        outlook = (
            "Risk skew currently favours <strong>downside in WTI</strong> as softer risk-index signals, "
            "compressed Brent\u2013WTI spread and contained volatility weigh on oil pricing. "
            "Custom Algorithm flags downside protection from demand softness and OPEC+ supply discipline."
        )
    else:
        outlook = (
            "Risk balance is currently <strong>range-bound</strong>, with offsetting bullish risk-index "
            "signals and softer macro volatility. Custom Algorithm flags OPEC+ commentary, EIA inventories, "
            "China demand prints and Middle East risk as the most likely directional triggers."
        )

    return bias, p1, p2, outlook


def _sentiment_badge(chg_pct):
    if chg_pct > 1:
        return '<span class="wti-sentiment" style="background:rgba(34,197,94,0.14);color:#22c55e;">&#9650; BULLISH</span>'
    if chg_pct < -1:
        return '<span class="wti-sentiment" style="background:rgba(239,68,68,0.14);color:#ef4444;">&#9660; BEARISH</span>'
    return '<span class="wti-sentiment" style="background:rgba(234,179,8,0.14);color:#eab308;">&#9644; NEUTRAL</span>'


# ─────────────────────────────────────────────────────────────────────────────
# Data fetcher
# ─────────────────────────────────────────────────────────────────────────────

def _compute_wti_data():
    """Fetch all required data. DESC LIMIT + reverse to guarantee latest rows."""
    wti_rows = list(reversed(execute_production_query(
        "SELECT date, wti_price, brent_price, brent_wti_spread "
        "FROM oil_price_snapshots "
        "WHERE wti_price IS NOT NULL "
        "ORDER BY date DESC LIMIT 2000"
    ) or []))

    brent_rows = list(reversed(execute_production_query(
        "SELECT date, brent_price FROM oil_price_snapshots "
        "WHERE brent_price IS NOT NULL "
        "ORDER BY date DESC LIMIT 2000"
    ) or []))

    vix_rows = list(reversed(execute_production_query(
        "SELECT date, vix_close FROM vix_snapshots "
        "WHERE vix_close IS NOT NULL "
        "ORDER BY date DESC LIMIT 2000"
    ) or []))

    ttf_rows = list(reversed(execute_production_query(
        "SELECT date, ttf_price FROM ttf_gas_snapshots "
        "WHERE ttf_price IS NOT NULL "
        "ORDER BY date DESC LIMIT 2000"
    ) or []))

    geri_rows = list(reversed(execute_production_query(
        "SELECT date, value FROM intel_indices_daily "
        "WHERE index_id='global:geo_energy_risk' AND value IS NOT NULL "
        "ORDER BY date DESC LIMIT 2000"
    ) or []))

    # NatGas — try a daily proxy via intraday_natgas (group by date avg)
    ng_rows = list(reversed(execute_production_query(
        "SELECT date, AVG(price) AS price FROM intraday_natgas "
        "WHERE price IS NOT NULL "
        "GROUP BY date "
        "ORDER BY date DESC LIMIT 600"
    ) or []))

    # Intraday WTI for today's session view (latest 36 hours)
    intraday_rows = execute_production_query(
        "SELECT date, hour, price FROM intraday_wti "
        "WHERE price IS NOT NULL "
        "ORDER BY date DESC, hour DESC LIMIT 48"
    ) or []
    # reverse ascending for plot
    intraday_rows = list(reversed(intraday_rows))

    # Latest index/risk values
    eeri_row = execute_production_one(
        "SELECT date, value, band FROM reri_indices_daily "
        "WHERE index_id='europe:eeri' ORDER BY date DESC LIMIT 1"
    )
    egsi_m_row = execute_production_one(
        "SELECT index_date, index_value, band FROM egsi_m_daily "
        "WHERE region='Europe' ORDER BY index_date DESC LIMIT 1"
    )
    egsi_s_row = execute_production_one(
        "SELECT index_date, index_value, band FROM egsi_s_daily "
        "WHERE region='Europe' ORDER BY index_date DESC LIMIT 1"
    )
    geri_latest_row = execute_production_one(
        "SELECT date, value, band FROM intel_indices_daily "
        "WHERE index_id='global:geo_energy_risk' ORDER BY date DESC LIMIT 1"
    )

    return {
        'wti_rows': wti_rows,
        'brent_rows': brent_rows,
        'vix_rows': vix_rows,
        'ttf_rows': ttf_rows,
        'geri_rows': geri_rows,
        'ng_rows': ng_rows,
        'intraday_rows': intraday_rows,
        'eeri_row': eeri_row,
        'egsi_m_row': egsi_m_row,
        'egsi_s_row': egsi_s_row,
        'geri_row': geri_latest_row,
    }


def _filter_range(rows, days, date_key='date'):
    if not rows or days is None:
        return rows
    if not rows:
        return []
    # cutoff relative to the latest date in series, not today (handles stale data gracefully)
    latest = rows[-1].get(date_key)
    if not latest:
        return rows
    cutoff = latest - timedelta(days=days)
    return [r for r in rows if r.get(date_key) and r[date_key] >= cutoff]


def _filter_ytd(rows, date_key='date'):
    if not rows:
        return []
    latest = rows[-1].get(date_key)
    year = latest.year if latest else _date.today().year
    start = _date(year, 1, 1)
    return [r for r in rows if r.get(date_key) and r[date_key] >= start]


# ─────────────────────────────────────────────────────────────────────────────
# HTML builder
# ─────────────────────────────────────────────────────────────────────────────

def _build_wti_html(data, today_str, today_date):
    wti_rows      = data['wti_rows']
    brent_rows    = data['brent_rows']
    vix_rows      = data['vix_rows']
    ttf_rows      = data['ttf_rows']
    geri_rows     = data['geri_rows']
    ng_rows       = data['ng_rows']
    intraday_rows = data['intraday_rows']
    eeri_row      = data['eeri_row']
    egsi_m_row    = data['egsi_m_row']
    egsi_s_row    = data['egsi_s_row']
    geri_row      = data['geri_row']

    # Latest values — prefer intraday for the live hero price
    if intraday_rows:
        latest_intra = intraday_rows[-1]
        wti_latest = _safe_float(latest_intra['price'])
        wti_latest_hour = int(latest_intra['hour']) if latest_intra.get('hour') is not None else None
        wti_latest_date = latest_intra['date']
        intraday_available = True
    else:
        wti_latest = _safe_float(wti_rows[-1]['wti_price']) if wti_rows else 0.0
        wti_latest_hour = None
        wti_latest_date = wti_rows[-1]['date'] if wti_rows else _date.today()
        intraday_available = False

    # Daily snapshot for day-over-day change (always from oil_price_snapshots)
    daily_latest = _safe_float(wti_rows[-1]['wti_price']) if wti_rows else wti_latest
    daily_prev   = _safe_float(wti_rows[-2]['wti_price']) if len(wti_rows) >= 2 else daily_latest
    wti_chg      = daily_latest - daily_prev
    wti_chg_pct  = (wti_chg / daily_prev * 100) if daily_prev else 0.0
    daily_date   = wti_rows[-1]['date'] if wti_rows else _date.today()

    def _pct_chg_from(idx_back):
        if len(wti_rows) <= idx_back:
            return 0.0
        ref = _safe_float(wti_rows[-idx_back-1]['wti_price'])
        return ((daily_latest - ref) / ref * 100) if ref else 0.0
    wti_7d_chg_pct  = _pct_chg_from(7)
    wti_30d_chg_pct = _pct_chg_from(30)

    # Brent / spread / VIX
    brent_latest = _safe_float(wti_rows[-1].get('brent_price', 0)) if wti_rows else 0.0
    spread       = _safe_float(wti_rows[-1].get('brent_wti_spread', 0)) if wti_rows else None
    if not spread and brent_latest and daily_latest:
        spread = brent_latest - daily_latest
    vix_close = _safe_float(vix_rows[-1]['vix_close']) if vix_rows else 0.0

    # Risk indices
    eeri_val  = int(round(_safe_float((eeri_row or {}).get('value', 0))))
    eeri_band = _html.escape(str((eeri_row or {}).get('band') or 'ELEVATED'))
    egsi_m_val = round(_safe_float((egsi_m_row or {}).get('index_value', 0)), 1)
    egsi_m_band = _html.escape(str((egsi_m_row or {}).get('band') or 'ELEVATED'))
    egsi_s_val = round(_safe_float((egsi_s_row or {}).get('index_value', 0)), 1)
    egsi_s_band = _html.escape(str((egsi_s_row or {}).get('band') or 'ELEVATED'))
    geri_val   = int(round(_safe_float((geri_row or {}).get('value', 0))))
    geri_band  = _html.escape(str((geri_row or {}).get('band') or 'MODERATE'))

    arrow = _arrow(wti_chg)
    color = _chg_color(wti_chg)
    sentiment = _sentiment_badge(wti_chg_pct)

    def _trend(v): return '&#9650;' if v > 0.2 else '&#9660;' if v < -0.2 else '&#9644;'
    def _trend_color(v): return '#22c55e' if v > 0.2 else '#ef4444' if v < -0.2 else '#eab308'

    if vix_close >= 25:
        vol_label, vol_color = 'ELEVATED', '#ef4444'
    elif vix_close >= 18:
        vol_label, vol_color = 'MODERATE', '#eab308'
    else:
        vol_label, vol_color = 'CALM', '#22c55e'

    # Regime
    if geri_val >= 65 and wti_30d_chg_pct > 2:
        regime_label, regime_color = 'RISK-ON / BULLISH', '#22c55e'
    elif geri_val >= 65 and wti_30d_chg_pct <= 0:
        regime_label, regime_color = 'RISK-OFF / DEFENSIVE', '#ef4444'
    elif wti_30d_chg_pct > 2:
        regime_label, regime_color = 'BULLISH', '#22c55e'
    elif wti_30d_chg_pct < -2:
        regime_label, regime_color = 'BEARISH', '#ef4444'
    else:
        regime_label, regime_color = 'NEUTRAL', '#eab308'

    # Spread label
    if spread is None:
        spread_label, spread_color = 'n/a', '#94a3b8'
    elif spread >= 5:
        spread_label, spread_color = 'WIDE', '#ef4444'
    elif spread >= 2:
        spread_label, spread_color = 'NORMAL', '#eab308'
    else:
        spread_label, spread_color = 'TIGHT', '#22c55e'

    # Time-range slices for the chart (date-aligned overlays inside the chart builder)
    w_1m  = _filter_range(wti_rows, 30)
    w_3m  = _filter_range(wti_rows, 90)
    w_ytd = _filter_ytd(wti_rows)
    w_1y  = _filter_range(wti_rows, 365)
    w_max = wti_rows

    chart_intraday = _build_intraday_chart_svg(intraday_rows)
    chart_1m  = _build_wti_chart_svg(w_1m,  brent_rows, vix_rows, geri_rows, ttf_rows, ng_rows, '1M')
    chart_3m  = _build_wti_chart_svg(w_3m,  brent_rows, vix_rows, geri_rows, ttf_rows, ng_rows, '3M')
    chart_ytd = _build_wti_chart_svg(w_ytd, brent_rows, vix_rows, geri_rows, ttf_rows, ng_rows, 'YTD')
    chart_1y  = _build_wti_chart_svg(w_1y,  brent_rows, vix_rows, geri_rows, ttf_rows, ng_rows, '1Y')
    chart_max = _build_wti_chart_svg(w_max, brent_rows, vix_rows, geri_rows, ttf_rows, ng_rows, 'MAX')

    (bias_label, bias_color, bias_bg), p1, p2, outlook = _wti_commentary(
        wti_latest, wti_chg_pct, wti_30d_chg_pct, spread,
        vix_close, geri_val, geri_band, eeri_val, brent_latest
    )

    # Historical table (last 30 daily rows)
    hist = list(reversed(wti_rows[-30:]))
    table_rows_html = ''
    for i, r in enumerate(hist):
        p = _safe_float(r['wti_price'])
        if i + 1 < len(hist):
            prev = _safe_float(hist[i+1]['wti_price'])
        else:
            prev = p
        chg = p - prev
        chg_pct = (chg / prev * 100) if prev else 0.0
        ccol = _chg_color(chg)
        table_rows_html += (
            f'<tr>'
            f'<td>{r["date"].isoformat() if r.get("date") else ""}</td>'
            f'<td class="wti-protected">${p:.2f}</td>'
            f'<td class="wti-protected" style="color:{ccol}">{chg:+.2f}</td>'
            f'<td class="wti-protected" style="color:{ccol}">{chg_pct:+.2f}%</td>'
            f'</tr>'
        )

    # Risk band colours
    eeri_c    = BAND_COLORS.get(eeri_band, '#f97316')
    egsi_m_c  = BAND_COLORS.get(egsi_m_band, '#f97316')
    egsi_s_c  = BAND_COLORS.get(egsi_s_band, '#f97316')
    geri_c    = BAND_COLORS.get(geri_band, '#f97316')

    # FAQ
    faqs = [
        ("What is WTI crude oil?",
         "WTI (West Texas Intermediate) is a light, sweet crude oil benchmark produced primarily in the "
         "United States, priced at the Cushing, Oklahoma delivery hub. WTI is the underlying for NYMEX "
         "crude oil futures and the leading US oil benchmark, used to price North American crude streams "
         "and refined-product margins."),
        ("Why is WTI oil important?",
         "WTI sets the marginal price for US refiners and is the most-watched US oil-market signal. "
         "Because WTI is highly liquid and traded around the clock on NYMEX, it acts as the global "
         "real-time pulse of US oil supply, demand and macro risk &mdash; with direct pass-through to "
         "gasoline, diesel, jet fuel and broader US inflation."),
        ("What affects oil prices today?",
         "Oil prices today are driven by OPEC+ production decisions, US weekly EIA inventory data, "
         "geopolitical risk (Middle East, Russia, sanctions), Chinese industrial demand, the US dollar "
         "and VIX (macro risk premium), and natural-gas/LNG arbitrage. EnergyRiskIQ&rsquo;s GERI index "
         "captures the geopolitical layer in real time."),
        ("What is the difference between Brent and WTI?",
         "Brent is the European/global crude benchmark priced from North Sea grades; WTI is the US "
         "benchmark priced at Cushing, Oklahoma. Brent typically trades at a small premium to WTI "
         "(the Brent\u2013WTI spread) reflecting Atlantic-basin tightness, US shale supply, transport "
         "costs and quality differentials."),
        ("Will oil prices go up?",
         "Forward oil prices depend on OPEC+ supply discipline, US shale growth, China demand, "
         "geopolitical disruption risk and macro volatility. EnergyRiskIQ uses Custom Algorithms across "
         "GERI, EERI and EGSI risk indices to flag directional risk before price reacts."),
        ("Why is WTI cheaper than Brent?",
         "WTI usually trades at a discount to Brent because US shale crude is landlocked at Cushing with "
         "limited export infrastructure relative to globally-tradable seaborne Brent. The discount "
         "widens when US supply is abundant, and narrows when Atlantic-basin supply tightens."),
    ]
    faq_html = ''
    for q, a in faqs:
        faq_html += (
            f'<details><summary>{_html.escape(q)}</summary>'
            f'<div>{_html.escape(a)}</div></details>'
        )
    faq_schema_items = [
        {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
        for q, a in faqs
    ]
    faqpage_schema = _json.dumps({
        "@context": "https://schema.org", "@type": "FAQPage", "mainEntity": faq_schema_items,
    })

    dataset_schema = _json.dumps({
        "@context": "https://schema.org",
        "@type": "Dataset",
        "name": "WTI Crude Oil Price (West Texas Intermediate) — Daily History",
        "description": (
            "Daily closing price of WTI (West Texas Intermediate) crude oil in USD/barrel, with "
            "risk-context overlays for Brent, VIX, GERI, TTF gas and Henry Hub natural gas."
        ),
        "url": f"{BASE_URL}/data/wti-crude-oil-price-today",
        "creator":   {"@type": "Organization", "name": "EnergyRiskIQ", "url": BASE_URL},
        "publisher": {"@type": "Organization", "name": "EnergyRiskIQ", "url": BASE_URL},
        "license": f"{BASE_URL}/data-license",
        "isAccessibleForFree": True,
        "dateModified": today_date,
        "variableMeasured": [
            {"@type": "PropertyValue", "name": "WTI crude oil price", "unitText": "USD/barrel"},
            {"@type": "PropertyValue", "name": "Brent crude price (overlay)", "unitText": "USD/barrel"},
            {"@type": "PropertyValue", "name": "Brent-WTI spread", "unitText": "USD/barrel"},
            {"@type": "PropertyValue", "name": "VIX volatility (overlay)", "unitText": "index"},
            {"@type": "PropertyValue", "name": "GERI risk index (overlay)", "unitText": "score 0-100"},
        ],
        "measurementTechnique": "Custom Algorithm aggregation of WTI settlement prices, intraday WTI captures, and reference market data.",
        "keywords": ["wti crude oil price today", "wti oil price", "crude oil price today", "oil price chart", "wti price live"],
        "spatialCoverage": "United States",
    })

    breadcrumb_schema = _json.dumps({
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": BASE_URL},
            {"@type": "ListItem", "position": 2, "name": "Data", "item": f"{BASE_URL}/data/energy-risk-snapshot"},
            {"@type": "ListItem", "position": 3, "name": "WTI Crude Oil Price Today",
             "item": f"{BASE_URL}/data/wti-crude-oil-price-today"},
        ],
    })

    webpage_schema = _json.dumps({
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": "WTI Crude Oil Price Today (West Texas Intermediate)",
        "url": f"{BASE_URL}/data/wti-crude-oil-price-today",
        "description": "Live WTI crude oil price, intraday chart, Brent-WTI spread, risk signals and market drivers.",
        "isAccessibleForFree": True,
        "publisher": {"@type": "Organization", "name": "EnergyRiskIQ", "url": BASE_URL},
        "license": f"{BASE_URL}/data-license",
        "dateModified": today_date,
    })

    finprod_schema = _json.dumps({
        "@context": "https://schema.org",
        "@type": "FinancialProduct",
        "name": "WTI Crude Oil",
        "description": "West Texas Intermediate (WTI) is the US crude oil benchmark, priced at Cushing OK and quoted in USD/barrel.",
        "category": "Commodity / Crude Oil",
        "provider": {"@type": "Organization", "name": "EnergyRiskIQ", "url": BASE_URL},
    })

    intraday_status = ''
    if intraday_available and wti_latest_hour is not None:
        intraday_status = (
            f'<span class="wti-intraday-tag">INTRADAY '
            f'&middot; {wti_latest_date.isoformat()} {wti_latest_hour:02d}:00 UTC</span>'
        )

    return f"""<script>
var l=document.getElementById('snap-loader');
if(l){{l.style.display='none';}}
document.body.style.overflow='';
</script>
<script type="application/ld+json">{webpage_schema}</script>
<script type="application/ld+json">{dataset_schema}</script>
<script type="application/ld+json">{finprod_schema}</script>
<script type="application/ld+json">{breadcrumb_schema}</script>
<script type="application/ld+json">{faqpage_schema}</script>
<style>{_WTI_CSS}</style>

<!-- ── ANTI-COPY PROTECTION ───────────────────────────────────────── -->
<script>
(function(){{
  document.addEventListener('copy', function(e) {{
    var sel = window.getSelection ? window.getSelection().toString() : '';
    if (sel.length > 0) {{
      var attr = '\\n\\n[Source: EnergyRiskIQ.com — WTI Crude Oil Price Today | CC BY-NC 4.0 — non-commercial use only]';
      e.clipboardData.setData('text/plain', sel + attr);
      e.preventDefault();
    }}
  }});
  document.addEventListener('contextmenu', function(e) {{
    var t = e.target;
    if (t && (t.classList && t.classList.contains('wti-protected') || (t.closest && t.closest('.wti-protected')))) {{
      e.preventDefault();
    }}
  }});
}})();
</script>

<!-- ── STICKY PRICE BAR ───────────────────────────────────────────── -->
<div class="wti-sticky-bar">
  <span class="wti-sticky-label">&#9954; WTI Today</span>
  <span class="wti-sticky-price wti-protected">${wti_latest:.2f}/bbl</span>
  <span class="wti-sticky-chg" style="color:{color};">{arrow} {wti_chg:+.2f} ({wti_chg_pct:+.2f}%)</span>
  <span class="wti-sticky-time">Updated: {today_str}</span>
  <a href="/users" class="wti-sticky-cta">Free Alerts &rarr;</a>
</div>

<!-- ── NAV ───────────────────────────────────────────────────────── -->
<nav class="nav">
  <div class="nav-inner">
    <a href="/" class="logo">
      <img src="/static/logo.png" alt="EnergyRiskIQ" style="height:28px">
      <span>EnergyRiskIQ</span>
    </a>
    <div style="display:flex;align-items:center;gap:1.5rem;">
      <a href="/data/brent-crude-oil-price-today" style="font-size:13px;color:#94a3b8;text-decoration:none;">Brent</a>
      <a href="/indices/global-energy-risk-index" style="font-size:13px;color:#94a3b8;text-decoration:none;">GERI</a>
      <a href="/indices/europe-energy-risk-index" style="font-size:13px;color:#94a3b8;text-decoration:none;">EERI</a>
      <a href="/data/global-energy-risk-forecast" style="font-size:13px;color:#94a3b8;text-decoration:none;">Forecast</a>
      <a href="/users" class="cta-btn-nav">Get Free Access</a>
    </div>
  </div>
</nav>

<!-- ── HERO ───────────────────────────────────────────────────────── -->
<header class="hero">
  <div class="hero-date">&#128337; Updated Daily &nbsp;&bull;&nbsp; {today_str}</div>
  <h1>WTI Crude Oil Price Today<br><span style="font-size:0.65em;color:#94a3b8;font-style:italic;">(West Texas Intermediate)</span></h1>
  <p class="hero-sub">
    Track the latest WTI crude oil price, intraday market moves, volatility, and global energy risk signals.
    Updated continuously with market context and analysis &mdash; powered by EnergyRiskIQ Custom Algorithms.
  </p>
</header>

<main class="page-body">

  <!-- ── 1. LIVE PRICE CARD ─────────────────────────────────────── -->
  <div class="wti-hero-card">
    <div class="wti-hero-bench">&#127482;&#127480; WTI Cushing &bull; US Benchmark{intraday_status}</div>
    <div class="wti-hero-price-row">
      <div class="wti-hero-price wti-protected"><sup>$</sup>{wti_latest:.2f}</div>
      <div class="wti-hero-unit">/barrel</div>
      <div style="margin-left:auto;">{sentiment}</div>
    </div>
    <div class="wti-hero-chg wti-protected" style="color:{color};">
      {arrow} {wti_chg:+.2f} $/bbl &bull; {wti_chg_pct:+.2f}% day-over-day
    </div>
    <div class="wti-hero-meta">
      <div><b>7D:</b> <span style="color:{_trend_color(wti_7d_chg_pct)};">{_trend(wti_7d_chg_pct)} {wti_7d_chg_pct:+.1f}%</span></div>
      <div><b>30D:</b> <span style="color:{_trend_color(wti_30d_chg_pct)};">{_trend(wti_30d_chg_pct)} {wti_30d_chg_pct:+.1f}%</span></div>
      <div><b>Last close:</b> {daily_date.isoformat() if daily_date else '—'}</div>
      <div><b>Source:</b> EnergyRiskIQ Pipeline (NYMEX settlement)</div>
    </div>
    <div class="wti-hero-cta-row">
      <a href="/users" class="wti-cta-primary">Get Free Daily Oil &amp; Energy Risk Alerts &rarr;</a>
      <a href="/users/account" class="wti-cta-secondary">Unlock Real-Time Market Signals (Pro)</a>
    </div>
  </div>

  <!-- ── 2. INTRADAY CHART (TODAY'S SESSION) ────────────────────── -->
  <div class="section-label" style="margin-bottom:20px;">&#128293; WTI Intraday &mdash; Today&rsquo;s Session</div>
  <div class="wti-chart-card">
    <div style="font-size:14px;color:#94a3b8;margin-bottom:12px;">
      Hourly WTI captures &mdash; latest {len(intraday_rows)} data points.
    </div>
    {chart_intraday}
  </div>

  <!-- ── 3. MAIN CHART WITH OVERLAYS ────────────────────────────── -->
  <div class="section-label" style="margin-bottom:20px;">&#128200; WTI Crude Oil Price Chart</div>
  <div class="wti-chart-card">
    <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:12px;">
      <div>
        <div style="font-size:15px;font-weight:700;color:#f1f5f9;">WTI Crude Oil &mdash; Daily Closing Price</div>
        <div style="font-size:12px;color:#94a3b8;margin-top:4px;">$/barrel &bull; with optional overlays for Brent, VIX, GERI, TTF and NatGas</div>
      </div>
      <div>{sentiment}</div>
    </div>

    <div class="wti-chart-toolbar">
      <div class="wti-tb-group">
        <span class="wti-tb-label">Range</span>
        <button class="wti-tb-btn" data-range="1m">1M</button>
        <button class="wti-tb-btn active" data-range="3m">3M</button>
        <button class="wti-tb-btn" data-range="ytd">YTD</button>
        <button class="wti-tb-btn" data-range="1y">1Y</button>
        <button class="wti-tb-btn" data-range="max">MAX</button>
      </div>
      <span class="wti-tb-divider"></span>
      <div class="wti-tb-group">
        <span class="wti-tb-label">Overlay</span>
        <button class="wti-tb-btn" data-overlay="brent">Brent</button>
        <button class="wti-tb-btn" data-overlay="vix">VIX</button>
        <button class="wti-tb-btn" data-overlay="geri">GERI</button>
        <button class="wti-tb-btn" data-overlay="ttf">TTF Gas</button>
        <button class="wti-tb-btn" data-overlay="ng">NatGas</button>
      </div>
    </div>

    <div class="wti-chart-panel" data-panel="1m">{chart_1m}</div>
    <div class="wti-chart-panel active" data-panel="3m">{chart_3m}</div>
    <div class="wti-chart-panel" data-panel="ytd">{chart_ytd}</div>
    <div class="wti-chart-panel" data-panel="1y">{chart_1y}</div>
    <div class="wti-chart-panel" data-panel="max">{chart_max}</div>

    <div class="wti-chart-legend">
      <span><span class="lg-dot" style="background:{WTI_COLOR};"></span>WTI ($/bbl)</span>
      <span><span class="lg-dot" style="background:#f97316;"></span>Brent &mdash; overlay</span>
      <span><span class="lg-dot" style="background:#a78bfa;"></span>VIX &mdash; overlay</span>
      <span><span class="lg-dot" style="background:#ef4444;"></span>GERI &mdash; overlay</span>
      <span><span class="lg-dot" style="background:#60a5fa;"></span>TTF &mdash; overlay</span>
      <span><span class="lg-dot" style="background:#22c55e;"></span>NatGas &mdash; overlay</span>
    </div>
    <div style="font-size:10px;color:#475569;margin-top:8px;">
      Overlays normalised to the chart area and date-aligned to the WTI x-axis &mdash; toggle on/off to compare directional movement.
    </div>
  </div>

  <script>
  (function(){{
    var panels = document.querySelectorAll('.wti-chart-panel');
    var rangeBtns = document.querySelectorAll('.wti-tb-btn[data-range]');
    rangeBtns.forEach(function(btn){{
      btn.addEventListener('click', function(){{
        rangeBtns.forEach(function(b){{ b.classList.remove('active'); }});
        btn.classList.add('active');
        var r = btn.getAttribute('data-range');
        panels.forEach(function(p){{
          p.classList.toggle('active', p.getAttribute('data-panel') === r);
        }});
      }});
    }});
    var overlayMap = {{
      brent: '.wti-series-brent',
      vix:   '.wti-series-vix',
      geri:  '.wti-series-geri',
      ttf:   '.wti-series-ttf',
      ng:    '.wti-series-ng'
    }};
    Object.keys(overlayMap).forEach(function(k){{
      document.querySelectorAll(overlayMap[k]).forEach(function(el){{ el.style.display = 'none'; }});
    }});
    document.querySelectorAll('.wti-tb-btn[data-overlay]').forEach(function(btn){{
      btn.addEventListener('click', function(){{
        var k = btn.getAttribute('data-overlay');
        var on = !btn.classList.contains('active');
        btn.classList.toggle('active', on);
        document.querySelectorAll(overlayMap[k]).forEach(function(el){{
          el.style.display = on ? '' : 'none';
        }});
      }});
    }});
  }})();
  </script>

  <!-- ── 4. MARKET SNAPSHOT ─────────────────────────────────────── -->
  <div class="section-label" style="margin-bottom:20px;">&#9889; Oil Market Snapshot (Today)</div>
  <div class="wti-snap-grid">
    <div class="wti-snap-cell">
      <div class="wti-snap-label">WTI Price</div>
      <div class="wti-snap-val wti-protected">${wti_latest:.2f}</div>
      <div class="wti-snap-sub">per barrel &bull; {daily_date.isoformat() if daily_date else '—'}</div>
    </div>
    <div class="wti-snap-cell">
      <div class="wti-snap-label">7-Day Trend</div>
      <div class="wti-snap-val" style="color:{_trend_color(wti_7d_chg_pct)};">{_trend(wti_7d_chg_pct)} {wti_7d_chg_pct:+.1f}%</div>
      <div class="wti-snap-sub">Weekly directional move</div>
    </div>
    <div class="wti-snap-cell">
      <div class="wti-snap-label">30-Day Trend</div>
      <div class="wti-snap-val" style="color:{_trend_color(wti_30d_chg_pct)};">{_trend(wti_30d_chg_pct)} {wti_30d_chg_pct:+.1f}%</div>
      <div class="wti-snap-sub">Monthly directional move</div>
    </div>
    <div class="wti-snap-cell">
      <div class="wti-snap-label">Brent-WTI Spread</div>
      <div class="wti-snap-val wti-protected" style="color:{spread_color};">{('${:+.2f}'.format(spread)) if spread is not None else 'n/a'}</div>
      <div class="wti-snap-sub">{spread_label}</div>
    </div>
    <div class="wti-snap-cell">
      <div class="wti-snap-label">VIX (Macro Risk)</div>
      <div class="wti-snap-val" style="color:{vol_color};">{vol_label}</div>
      <div class="wti-snap-sub">VIX {vix_close:.2f}</div>
    </div>
    <div class="wti-snap-cell">
      <div class="wti-snap-label">GERI Risk Level</div>
      <div class="wti-snap-val" style="color:{geri_c};">{geri_val}<span style="font-size:12px;color:#64748b;font-weight:600;">/100</span></div>
      <div class="wti-snap-sub">{geri_band}</div>
    </div>
  </div>
  <div style="text-align:center;margin:-16px 0 12px;">
    <span class="wti-sentiment" style="background:rgba(255,255,255,0.04);color:{regime_color};border:1px solid {regime_color}55;">
      Risk Regime: {regime_label}
    </span>
  </div>
  <div style="text-align:center;margin-bottom:40px;display:flex;gap:10px;justify-content:center;flex-wrap:wrap;">
    <a href="/data/brent-crude-oil-price-today" class="wti-cta-secondary">Brent Page</a>
    <a href="/indices/global-energy-risk-index" class="wti-cta-secondary">GERI Page</a>
    <a href="/data/global-energy-risk-forecast" class="wti-cta-secondary">Forecast Page</a>
  </div>

  <!-- ── 5. WHY WTI MATTERS ─────────────────────────────────────── -->
  <div class="section-label" style="margin-bottom:20px;">&#129504; Why WTI Crude Oil Prices Matter</div>
  <div class="wti-grid-2">
    <div style="background:var(--card);border:1px solid var(--border);border-radius:14px;padding:22px 24px;">
      <h3 style="font-size:15px;font-weight:700;color:#f1f5f9;margin-bottom:10px;">WTI Is the US Oil Benchmark</h3>
      <p style="font-size:13.5px;color:#94a3b8;line-height:1.7;">
        West Texas Intermediate is the deepest US oil contract on NYMEX and the marginal price for
        domestic refiners, gasoline, jet fuel and diesel. Every move in WTI flows directly into US
        fuel prices, freight, logistics and downstream CPI.
      </p>
    </div>
    <div style="background:var(--card);border:1px solid var(--border);border-radius:14px;padding:22px 24px;">
      <h3 style="font-size:15px;font-weight:700;color:#f1f5f9;margin-bottom:10px;">Why WTI Drives Everything Downstream</h3>
      <ul style="font-size:13.5px;color:#94a3b8;line-height:1.85;list-style:none;padding:0;">
        <li>&bull; <strong style="color:#cbd5e1;">Gasoline &amp; diesel prices</strong> &mdash; US pump prices</li>
        <li>&bull; <strong style="color:#cbd5e1;">Inflation</strong> &mdash; oil pass-through into US CPI</li>
        <li>&bull; <strong style="color:#cbd5e1;">Freight &amp; logistics</strong> &mdash; trucking and shipping costs</li>
        <li>&bull; <strong style="color:#cbd5e1;">Global economy</strong> &mdash; recession / growth signal</li>
        <li>&bull; <strong style="color:#cbd5e1;">Energy markets</strong> &mdash; sets baseline for all liquid fuels</li>
      </ul>
      <div style="margin-top:14px;display:flex;gap:14px;flex-wrap:wrap;font-size:12px;">
        <a href="/indices/global-energy-risk-index" style="color:{WTI_COLOR};text-decoration:none;font-weight:700;">&rarr; GERI</a>
        <a href="/data/brent-crude-oil-price-today" style="color:{WTI_COLOR};text-decoration:none;font-weight:700;">&rarr; Brent</a>
      </div>
    </div>
  </div>

  <!-- ── 6. WHAT DRIVES WTI ─────────────────────────────────────── -->
  <div class="section-label" style="margin-bottom:20px;">&#128202; What Moves WTI Crude Oil Prices?</div>
  <div class="wti-driver-grid">
    <div class="wti-driver-card">
      <div class="wti-driver-icon">&#127978;</div>
      <div class="wti-driver-title">OPEC+ Decisions</div>
      <p class="wti-driver-body">Production cuts, voluntary curtailments and quota guidance from OPEC+ set the
        marginal supply curve for global oil. Saudi-led restraint typically lifts WTI; surprise unwinds weigh on it.</p>
      <a href="/research/global-energy-risk-timeline" class="wti-driver-link">View Risk Timeline &rarr;</a>
    </div>
    <div class="wti-driver-card">
      <div class="wti-driver-icon">&#128737;&#65039;</div>
      <div class="wti-driver-title">Geopolitical Risk</div>
      <p class="wti-driver-body">GERI sits at <strong style="color:{geri_c};">{geri_val}/100 ({geri_band})</strong>.
        Middle East conflict, Russia/Ukraine, Red Sea shipping risk and sanctions all push risk premium into WTI.</p>
      <a href="/indices/global-energy-risk-index" class="wti-driver-link">View GERI &rarr;</a>
    </div>
    <div class="wti-driver-card">
      <div class="wti-driver-icon">&#127956;&#65039;</div>
      <div class="wti-driver-title">US Inventory &amp; Shale</div>
      <p class="wti-driver-body">Weekly EIA crude, gasoline and distillate inventories at Cushing drive
        near-term WTI direction. US shale production rate caps how high WTI can sustainably trade.</p>
      <a href="/data/brent-crude-oil-price-today" class="wti-driver-link">Compare with Brent &rarr;</a>
    </div>
    <div class="wti-driver-card">
      <div class="wti-driver-icon">&#127464;&#127475;</div>
      <div class="wti-driver-title">Global Demand</div>
      <p class="wti-driver-body">Chinese industrial activity, refining margins, jet-fuel demand and recession-fear
        cycles set the medium-term demand path. Soft China prints typically weigh on WTI.</p>
      <a href="/research/what-drives-lng-prices" class="wti-driver-link">Read LNG / Demand Research &rarr;</a>
    </div>
    <div class="wti-driver-card">
      <div class="wti-driver-icon">&#128176;</div>
      <div class="wti-driver-title">Financial Markets</div>
      <p class="wti-driver-body">USD strength weighs on WTI (dollar-denominated). VIX at <strong>{vix_close:.2f}</strong>
        captures macro risk-premium; high VIX often correlates with oil-price spikes during shocks.</p>
      <a href="/indices/europe-energy-risk-index" class="wti-driver-link">View EERI &rarr;</a>
    </div>
    <div class="wti-driver-card">
      <div class="wti-driver-icon">&#128293;</div>
      <div class="wti-driver-title">Natural Gas &amp; LNG</div>
      <p class="wti-driver-body">Gas-to-oil switching, oil-indexed LNG contracts and US shale gas/oil joint economics
        link WTI to TTF gas and JKM LNG &mdash; the cross-fuel arbitrage matters.</p>
      <a href="/data/natural-gas-price-today-europe" class="wti-driver-link">NatGas Europe &rarr;</a>
      &nbsp;&nbsp;
      <a href="/data/jkm-lng-spot-price" class="wti-driver-link">JKM LNG &rarr;</a>
    </div>
  </div>

  <!-- ── 7. RISK PANEL ──────────────────────────────────────────── -->
  <div class="section-label" style="margin-bottom:20px;">&#127919; Oil Prices &amp; Energy Risk Signals</div>
  <p style="font-size:13.5px;color:#94a3b8;line-height:1.7;margin-bottom:18px;max-width:780px;">
    Oil prices often react to geopolitical disruptions <em>before</em> traditional economic indicators.
    EnergyRiskIQ&rsquo;s Custom Algorithms score live geopolitical, supply, demand and stress signals
    into structured risk indices so you can see directional risk early.
  </p>
  <div class="wti-risk-grid">
    <a href="/indices/global-energy-risk-index" class="wti-risk-card" style="border-color:{geri_c}33;">
      <div class="wti-risk-name">GERI</div>
      <div class="wti-risk-val">{geri_val}<span style="font-size:14px;color:#64748b;font-weight:600;">/100</span></div>
      <div class="wti-risk-band" style="color:{geri_c};">{geri_band}</div>
      <div class="wti-risk-desc">Global Energy Risk</div>
    </a>
    <a href="/indices/europe-energy-risk-index" class="wti-risk-card" style="border-color:{eeri_c}33;">
      <div class="wti-risk-name">EERI</div>
      <div class="wti-risk-val">{eeri_val}<span style="font-size:14px;color:#64748b;font-weight:600;">/100</span></div>
      <div class="wti-risk-band" style="color:{eeri_c};">{eeri_band}</div>
      <div class="wti-risk-desc">Europe Energy Risk</div>
    </a>
    <a href="/indices/europe-gas-stress-index" class="wti-risk-card" style="border-color:{egsi_m_c}33;">
      <div class="wti-risk-name">EGSI-M</div>
      <div class="wti-risk-val">{egsi_m_val:.1f}</div>
      <div class="wti-risk-band" style="color:{egsi_m_c};">{egsi_m_band}</div>
      <div class="wti-risk-desc">Gas Market Stress</div>
    </a>
    <a href="/indices/europe-gas-stress-index" class="wti-risk-card" style="border-color:{egsi_s_c}33;">
      <div class="wti-risk-name">EGSI-S</div>
      <div class="wti-risk-val">{egsi_s_val:.1f}</div>
      <div class="wti-risk-band" style="color:{egsi_s_c};">{egsi_s_band}</div>
      <div class="wti-risk-desc">Gas System Stress</div>
    </a>
  </div>
  <div style="text-align:center;margin-bottom:40px;">
    <a href="/users" class="wti-cta-primary">Unlock Real-Time Risk Signals &rarr;</a>
  </div>

  <!-- ── 8. BRENT vs WTI ────────────────────────────────────────── -->
  <div class="section-label" style="margin-bottom:20px;">&#9878;&#65039; Brent vs WTI Crude Oil</div>
  <div class="wti-spread-card">
    <div class="wti-spread-grid">
      <div class="wti-spread-cell">
        <div class="wti-spread-cell-label">WTI</div>
        <div class="wti-spread-cell-val wti-protected" style="color:{WTI_COLOR};">${daily_latest:.2f}</div>
        <div class="wti-spread-cell-sub">US benchmark &bull; Cushing</div>
      </div>
      <div class="wti-spread-cell">
        <div class="wti-spread-cell-label">Brent</div>
        <div class="wti-spread-cell-val wti-protected" style="color:#f97316;">${brent_latest:.2f}</div>
        <div class="wti-spread-cell-sub">Global benchmark &bull; North Sea</div>
      </div>
      <div class="wti-spread-cell">
        <div class="wti-spread-cell-label">Brent &minus; WTI Spread</div>
        <div class="wti-spread-cell-val wti-protected" style="color:{spread_color};">
          {('${:+.2f}'.format(spread)) if spread is not None else 'n/a'}
        </div>
        <div class="wti-spread-cell-sub">{spread_label} &bull; per barrel</div>
      </div>
    </div>
    <div class="wti-spread-note">
      <strong>Why this spread matters:</strong> The Brent-WTI differential captures Atlantic-basin tightness versus
      US Gulf Coast supply. A <strong>wider spread</strong> typically signals firm seaborne demand (geopolitical
      stress, supply outages), while a <strong>tighter spread</strong> indicates US shale outpacing global demand.
      Traders use this spread to position transatlantic arbitrage and refining-margin trades.
      <br><br>
      &rarr; <a href="/data/brent-crude-oil-price-today" style="color:{WTI_COLOR};text-decoration:none;font-weight:700;">Full Brent page</a>
    </div>
  </div>

  <!-- ── 9. DAILY COMMENTARY ────────────────────────────────────── -->
  <div class="section-label" style="margin-bottom:20px;">&#128221; Today&rsquo;s WTI Oil Market Analysis</div>
  <div class="wti-commentary">
    <span class="wti-bias-badge" style="background:{bias_bg};color:{bias_color};">{bias_label}</span>
    <p>{p1}</p>
    <p>{p2}</p>
    <p>{outlook}</p>
    <div class="wti-engine-tag">&#9881;&#65039; Generated by EnergyRiskIQ Custom Algorithms &bull; updated daily</div>
  </div>

  <!-- ── 10. HISTORICAL DATA TABLE ──────────────────────────────── -->
  <div class="section-label" style="margin-bottom:20px;">&#128196; WTI Historical Prices (Last 30 Days)</div>
  <div class="wti-table-wrap">
    <div class="wti-table-head">
      <h3>Daily WTI Closing Prices</h3>
      <a href="/api/wti-prices.csv" class="wti-table-csv">&darr; Download CSV</a>
    </div>
    <div class="wti-table-scroll">
      <table class="wti-table">
        <thead>
          <tr><th>Date</th><th>Price ($/bbl)</th><th>Change</th><th>% Change</th></tr>
        </thead>
        <tbody>{table_rows_html}</tbody>
      </table>
    </div>
  </div>

  <!-- ── 11. INTERNAL LINK HUB ──────────────────────────────────── -->
  <div class="section-label" style="margin-bottom:20px;">&#128279; Related EnergyRiskIQ Intelligence</div>
  <div class="wheel-grid">
    <a href="/data/brent-crude-oil-price-today" class="wheel-link">
      <div class="wheel-link-icon">&#128137;</div>
      <div class="wheel-link-label">Brent Crude</div>
      <div class="wheel-link-desc">Global Brent oil benchmark with risk overlays</div>
    </a>
    <a href="/data/natural-gas-price-today-europe" class="wheel-link">
      <div class="wheel-link-icon">&#128293;</div>
      <div class="wheel-link-label">NatGas Europe</div>
      <div class="wheel-link-desc">TTF natural gas benchmark with overlays</div>
    </a>
    <a href="/data/ttf-gas-price-today" class="wheel-link">
      <div class="wheel-link-icon">&#127470;&#127489;</div>
      <div class="wheel-link-label">TTF Daily</div>
      <div class="wheel-link-desc">TTF daily-data page with full timeseries</div>
    </a>
    <a href="/data/jkm-lng-spot-price" class="wheel-link">
      <div class="wheel-link-icon">&#9875;</div>
      <div class="wheel-link-label">JKM LNG</div>
      <div class="wheel-link-desc">Japan/Korea Marker LNG spot price</div>
    </a>
    <a href="/data/jkm-lng-price-chart" class="wheel-link">
      <div class="wheel-link-icon">&#128200;</div>
      <div class="wheel-link-label">JKM Chart</div>
      <div class="wheel-link-desc">JKM LNG price chart with overlays</div>
    </a>
    <a href="/data/global-energy-risk-forecast" class="wheel-link">
      <div class="wheel-link-icon">&#128302;</div>
      <div class="wheel-link-label">24H Forecast</div>
      <div class="wheel-link-desc">Custom Algorithm energy price outlook</div>
    </a>
    <a href="/indices/global-energy-risk-index" class="wheel-link">
      <div class="wheel-link-icon">&#127760;</div>
      <div class="wheel-link-label">GERI</div>
      <div class="wheel-link-desc">Global Energy Risk Index &mdash; methodology</div>
    </a>
    <a href="/indices/europe-energy-risk-index" class="wheel-link">
      <div class="wheel-link-icon">&#9889;</div>
      <div class="wheel-link-label">EERI</div>
      <div class="wheel-link-desc">European Energy Risk Index</div>
    </a>
    <a href="/indices/europe-gas-stress-index" class="wheel-link">
      <div class="wheel-link-icon">&#127777;&#65039;</div>
      <div class="wheel-link-label">EGSI</div>
      <div class="wheel-link-desc">Europe Gas Stress Index (M / S)</div>
    </a>
    <a href="/research/global-energy-risk-timeline" class="wheel-link">
      <div class="wheel-link-icon">&#128197;</div>
      <div class="wheel-link-label">Risk Timeline</div>
      <div class="wheel-link-desc">Historical global energy risk events</div>
    </a>
    <a href="/research/what-drives-lng-prices" class="wheel-link">
      <div class="wheel-link-icon">&#128218;</div>
      <div class="wheel-link-label">LNG Drivers</div>
      <div class="wheel-link-desc">What drives global LNG prices &mdash; research</div>
    </a>
    <a href="/data/energy-risk-snapshot" class="wheel-link">
      <div class="wheel-link-icon">&#128247;</div>
      <div class="wheel-link-label">Risk Snapshot</div>
      <div class="wheel-link-desc">Daily downloadable risk infographic</div>
    </a>
  </div>

  <!-- ── 12. CONVERSION BLOCK ───────────────────────────────────── -->
  <div class="wti-conv">
    <h2>Don&rsquo;t Just Track Oil Prices &mdash;<br>Understand What Drives Them</h2>
    <p>
      Most platforms show price charts. EnergyRiskIQ connects oil prices with
      <strong style="color:#cbd5e1;">geopolitical risk, volatility, LNG markets and global energy stress</strong>
      &mdash; so you see the risk before the price reacts.
    </p>
    <a href="/users" class="wti-cta-primary">Get Free Daily Oil &amp; Energy Alerts &rarr;</a>
    <a href="/energy-risk-intelligence-signals" class="wti-cta-secondary">Upgrade to Pro for Real-Time Signals</a>
  </div>

  <!-- ── 13. FAQ ────────────────────────────────────────────────── -->
  <div class="section-label" style="margin-bottom:20px;">&#10067; Frequently Asked Questions</div>
  <div class="wti-faq">
    {faq_html}
  </div>

  <!-- ── CITATION & REFERENCE ───────────────────────────────────── -->
  <div class="section-label" style="margin-bottom:20px;">&#128196; Citation &amp; Reference</div>
  <div class="wti-cite-card">
    <h3>How to Cite This Page</h3>
    <p class="wti-cite-desc">
      This page is updated continuously with fresh WTI crude-oil data and Custom Algorithm risk context
      from the EnergyRiskIQ production pipeline. To reference this analysis in research, journalism or
      professional reports, use the citation below.
    </p>
    <div class="wti-cite-code-wrap">
      <pre class="wti-cite-code">EnergyRiskIQ. (2026). <em>WTI Crude Oil Price Today (West Texas Intermediate) &mdash; {today_str}</em>.
Retrieved from <a href="{BASE_URL}/data/wti-crude-oil-price-today">{BASE_URL}/data/wti-crude-oil-price-today</a>
Custom Algorithm interpretation. Data sources: NYMEX WTI settlement, intraday WTI captures, OilPriceAPI, Yahoo Finance (VIX), EnergyRiskIQ internal GERI / EERI / EGSI risk pipeline.</pre>
      <button class="wti-cite-copy-btn" onclick="this.textContent='Copied!';setTimeout(()=>this.textContent='Copy',2000);navigator.clipboard&amp;&amp;navigator.clipboard.writeText('EnergyRiskIQ. (2026). WTI Crude Oil Price Today — {today_str}. Retrieved from {BASE_URL}/data/wti-crude-oil-price-today')">Copy</button>
    </div>
    <div class="wti-cite-footer">
      Data is provided by EnergyRiskIQ&rsquo;s production pipeline (NYMEX WTI settlement aggregation),
      intraday WTI captures, OilPriceAPI, Yahoo Finance (VIX) and the internal GERI / EERI / EGSI risk-scoring engines.
      <strong>Not financial advice.</strong>
      See <a href="{BASE_URL}/indices/global-energy-risk-index">GERI methodology</a> for the full risk-scoring detail.
    </div>
  </div>

  <!-- ── DATA LICENSE BLOCK ─────────────────────────────────────── -->
  <div class="wti-license">
    Data on this page is provided for informational and non-commercial use under the
    EnergyRiskIQ <a href="/data-license">data licence</a> (CC BY-NC 4.0). Attribution required
    on republication. Commercial use, redistribution and automated scraping are not permitted.
    Visit <a href="/data-license">/data-license</a> for the full terms.
  </div>

</main>

<footer class="page-footer">
  <div>
    &copy; 2026 EnergyRiskIQ &bull;
    <a href="/">Home</a>
    <a href="/data/brent-crude-oil-price-today">Brent</a>
    <a href="/indices/global-energy-risk-index">GERI</a>
    <a href="/indices/europe-energy-risk-index">EERI</a>
    <a href="/data-license">Data Licence</a>
    <a href="/sitemap-index.xml">Sitemap</a>
    &bull; Not financial advice.
  </div>
</footer>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────────────
# Route
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/data/wti-crude-oil-price-today")
async def wti_crude_oil_price_today():
    async def generate():
        yield _WTI_LOADER_HTML
        try:
            data = await asyncio.to_thread(_compute_wti_data)
        except Exception as exc:
            logger.error(f"WTI data fetch failed: {exc}", exc_info=True)
            yield (
                "<script>var l=document.getElementById('snap-loader');"
                "if(l)l.style.display='none';document.body.style.overflow='';</script>"
                f"<div style='color:#ef4444;padding:40px;font-family:sans-serif;background:#0b0f1a;'>"
                f"<h2>Error loading WTI data</h2><p>{_html.escape(str(exc))}</p></div></body></html>"
            )
            return

        today_str = datetime.now(timezone.utc).strftime('%B %-d, %Y')
        today_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        yield _build_wti_html(data, today_str, today_date)

    return StreamingResponse(generate(), media_type="text/html")


# ─────────────────────────────────────────────────────────────────────────────
# CSV download
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/api/wti-prices.csv")
async def wti_prices_csv():
    rows = execute_production_query(
        "SELECT date, wti_price, brent_price, brent_wti_spread "
        "FROM oil_price_snapshots "
        "WHERE wti_price IS NOT NULL "
        "ORDER BY date DESC LIMIT 365"
    ) or []
    lines = ["date,wti_price_usd_bbl,brent_price_usd_bbl,brent_wti_spread_usd"]
    for r in rows:
        d = r.get('date')
        wti = r.get('wti_price')
        brent = r.get('brent_price')
        spr = r.get('brent_wti_spread')
        if d is not None and wti is not None:
            wti_s = f"{float(wti):.4f}"
            brent_s = f"{float(brent):.4f}" if brent is not None else ""
            spr_s = f"{float(spr):.4f}" if spr is not None else ""
            lines.append(f"{d.isoformat()},{wti_s},{brent_s},{spr_s}")
    csv = "\n".join(lines) + "\n"
    return Response(
        content=csv,
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="energyriskiq-wti-crude.csv"',
            "Cache-Control": "public, max-age=3600",
        },
    )
