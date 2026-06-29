"""
Natural Gas Price Today in Europe (TTF Benchmark) Page
Route: /data/natural-gas-price-today-europe

SEO-optimised live European natural gas (TTF) price page with charts,
risk context (EERI / EGSI-M / EGSI-S), storage levels, price drivers,
historical data, FAQ, citation block and internal link hub.

Custom-algorithm wording (not "AI"). Fully mobile responsive.
Anti-copy text protection (does NOT block search engines).
"""
import logging
import asyncio
import html as _html
from datetime import datetime, timezone, date as _date, timedelta

from fastapi import APIRouter
from fastapi.responses import StreamingResponse, Response

from src.db.db import execute_production_one, execute_production_query
from src.api.snapshot_routes import (
    _PAGE_CSS, _LOADER_HTML, BAND_COLORS, _safe_float,
)
from src.api.forecast_routes import (
    _arrow, _chg_color, _fmt_date, _build_price_svg_chart,
)

router = APIRouter()
logger = logging.getLogger(__name__)

BASE_URL = "https://energyriskiq.com"
TTF_COLOR = "#60a5fa"
TTF_COLOR_DIM = "rgba(96,165,250,0.18)"


# ─────────────────────────────────────────────────────────────────────────────
# Loader (re-skin shared loader)
# ─────────────────────────────────────────────────────────────────────────────

_NATGAS_LOADER_HTML = _LOADER_HTML.replace(
    'Global Energy Risk Snapshot | EnergyRiskIQ',
    'Natural Gas Price Today Europe{{TTF_TITLE}} | Live TTF Chart &amp; Storage Levels'
).replace(
    'name="description" content="Live global energy risk snapshot. Current GERI, EERI and EGSI-M index values with Brent crude, TTF gas, VIX and LNG market prices."',
    'name="description" content="Today\'s European natural gas price (TTF){{TTF_DESC}}. Track live TTF charts, EU gas storage levels, LNG market signals and daily risk analysis. Updated every day."'
).replace(
    'rel="canonical" href="https://energyriskiq.com/data/energy-risk-snapshot"',
    'rel="canonical" href="https://energyriskiq.com/data/natural-gas-price-today-europe"'
).replace(
    'Fetching GERI\u00a0&\u00a0EERI indices\u2026',
    'Fetching TTF natural gas prices\u2026',
).replace(
    '<span class="ld-tag">GERI</span>\n    <span class="ld-tag">EERI</span>\n    <span class="ld-tag">EGSI&#8209;M</span>\n    <span class="ld-tag">Brent</span>\n    <span class="ld-tag">TTF</span>',
    '<span class="ld-tag">TTF</span>\n    <span class="ld-tag">EERI</span>\n    <span class="ld-tag">EGSI&#8209;M</span>\n    <span class="ld-tag">Storage</span>\n    <span class="ld-tag">VIX</span>',
)


# ─────────────────────────────────────────────────────────────────────────────
# Page-specific CSS (extends shared _PAGE_CSS)
# ─────────────────────────────────────────────────────────────────────────────

_NATGAS_CSS = f"""
/* ── Anti-copy data protection (visual cue only — does NOT block crawlers) ── */
.ng-protected {{
  user-select: none;
  -webkit-user-select: none;
  -moz-user-select: none;
  -ms-user-select: none;
}}

/* ── Sticky price bar ─────────────────────────────────────────────────────── */
.ng-sticky-bar {{
  position: sticky; top: 0; z-index: 99;
  display: flex; align-items: center; flex-wrap: wrap; gap: 14px;
  background: linear-gradient(90deg, #0e1422 0%, #111a2c 100%);
  border-bottom: 1px solid rgba(96,165,250,0.25);
  padding: 10px 18px; font-size: 13px;
}}
.ng-sticky-label {{ font-weight: 800; color: {TTF_COLOR}; letter-spacing: 1px; font-size: 11px; text-transform: uppercase; }}
.ng-sticky-price {{ font-weight: 800; color: #f1f5f9; font-variant-numeric: tabular-nums; font-size: 15px; }}
.ng-sticky-chg {{ font-weight: 700; font-variant-numeric: tabular-nums; }}
.ng-sticky-time {{ color: #64748b; font-size: 11px; margin-left: auto; }}
.ng-sticky-cta {{
  background: linear-gradient(135deg,#3b82f6,#8b5cf6); color:#fff !important;
  text-decoration: none; font-weight: 700; font-size: 12px;
  padding: 6px 14px; border-radius: 6px;
}}
@media (max-width: 640px) {{
  .ng-sticky-time {{ display: none; }}
  .ng-sticky-bar {{ padding: 8px 12px; gap: 10px; font-size: 12px; }}
}}

/* ── Hero live price card ─────────────────────────────────────────────────── */
.ng-hero-card {{
  background: linear-gradient(135deg, #0c1322 0%, #14233a 50%, #0f172a 100%);
  border: 1px solid rgba(96,165,250,0.3);
  border-radius: 20px;
  padding: 32px 36px;
  margin: 28px auto 36px;
  position: relative;
  overflow: hidden;
  max-width: 760px;
}}
.ng-hero-card::before {{
  content: '';
  position: absolute; top: 0; left: 0; right: 0; height: 3px;
  background: linear-gradient(90deg, {TTF_COLOR}, rgba(96,165,250,0.2));
}}
.ng-hero-bench {{
  font-size: 11px; font-weight: 700; letter-spacing: 2px; text-transform: uppercase;
  color: {TTF_COLOR}; margin-bottom: 8px;
}}
.ng-hero-price-row {{ display: flex; align-items: baseline; gap: 14px; flex-wrap: wrap; }}
.ng-hero-price {{
  font-size: 56px; font-weight: 800; line-height: 1; color: #fff;
  font-variant-numeric: tabular-nums;
}}
.ng-hero-price sup {{ font-size: 24px; font-weight: 600; vertical-align: top; margin-top: 8px; }}
.ng-hero-unit {{ font-size: 16px; color: #94a3b8; }}
.ng-hero-chg {{ font-size: 16px; font-weight: 700; margin-top: 10px; }}
.ng-hero-meta {{
  margin-top: 14px; display: flex; flex-wrap: wrap; gap: 14px;
  font-size: 12px; color: #94a3b8;
}}
.ng-hero-meta b {{ color: #cbd5e1; }}
.ng-hero-cta-row {{ margin-top: 22px; display: flex; gap: 12px; flex-wrap: wrap; }}
.ng-cta-primary {{
  background: linear-gradient(135deg,#3b82f6,#8b5cf6); color:#fff !important;
  text-decoration: none; font-weight: 700; font-size: 14px;
  padding: 12px 22px; border-radius: 10px;
}}
.ng-cta-secondary {{
  background: transparent; color: #cbd5e1 !important;
  border: 1px solid rgba(255,255,255,0.18);
  text-decoration: none; font-weight: 600; font-size: 14px;
  padding: 12px 22px; border-radius: 10px;
}}
.ng-cta-secondary:hover {{ border-color: rgba(96,165,250,0.5); color:#fff !important; }}
@media (max-width: 540px) {{
  .ng-hero-card {{ padding: 22px 18px; border-radius: 14px; }}
  .ng-hero-price {{ font-size: 40px; }}
  .ng-hero-price sup {{ font-size: 18px; margin-top: 5px; }}
}}

/* ── Sentiment badges ─────────────────────────────────────────────────────── */
.ng-sentiment {{
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 11px; font-weight: 800; letter-spacing: 1.2px;
  text-transform: uppercase; padding: 4px 12px; border-radius: 20px;
}}

/* ── Main chart card (time ranges + overlays) ─────────────────────────────── */
.ng-chart-card {{
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 24px 26px;
  margin-bottom: 44px;
}}
.ng-chart-toolbar {{
  display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
  margin: 16px 0 12px;
}}
.ng-chart-toolbar .ng-tb-group {{ display: flex; flex-wrap: wrap; gap: 6px; }}
.ng-tb-btn {{
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.08);
  color: #cbd5e1;
  font-size: 11px; font-weight: 700;
  padding: 5px 12px; border-radius: 8px; cursor: pointer;
  user-select: none; letter-spacing: 0.5px;
  transition: all 0.15s;
}}
.ng-tb-btn:hover {{ border-color: rgba(96,165,250,0.4); color: #fff; }}
.ng-tb-btn.active {{
  background: rgba(96,165,250,0.18);
  border-color: rgba(96,165,250,0.6);
  color: {TTF_COLOR};
}}
.ng-tb-divider {{
  width: 1px; height: 18px; background: rgba(255,255,255,0.1);
  margin: 0 6px;
}}
.ng-tb-label {{
  font-size: 10px; font-weight: 700; color: #64748b;
  letter-spacing: 1.2px; text-transform: uppercase; margin-right: 2px;
}}
.ng-chart-panel {{ display: none; }}
.ng-chart-panel.active {{ display: block; }}
.ng-chart-legend {{
  display: flex; flex-wrap: wrap; gap: 14px; margin-top: 10px;
  font-size: 11px; color: #94a3b8;
}}
.ng-chart-legend .lg-dot {{
  display: inline-block; width: 10px; height: 10px;
  border-radius: 2px; margin-right: 6px; vertical-align: middle;
}}

/* ── Quick snapshot grid ──────────────────────────────────────────────────── */
.ng-snap-grid {{
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
  margin-bottom: 40px;
}}
@media (max-width: 780px) {{ .ng-snap-grid {{ grid-template-columns: 1fr 1fr; }} }}
@media (max-width: 460px) {{ .ng-snap-grid {{ grid-template-columns: 1fr; }} }}
.ng-snap-cell {{
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 16px 18px;
}}
.ng-snap-label {{
  font-size: 10px; font-weight: 700; letter-spacing: 1.4px;
  text-transform: uppercase; color: #64748b; margin-bottom: 6px;
}}
.ng-snap-val {{
  font-size: 22px; font-weight: 800; color: #f1f5f9;
  font-variant-numeric: tabular-nums; margin-bottom: 4px;
}}
.ng-snap-sub {{ font-size: 11px; color: #94a3b8; }}

/* ── Driver / risk / link grids ───────────────────────────────────────────── */
.ng-grid-2 {{
  display: grid; grid-template-columns: 1fr 1fr;
  gap: 16px; margin-bottom: 36px;
}}
@media (max-width: 780px) {{ .ng-grid-2 {{ grid-template-columns: 1fr; }} }}
.ng-driver-grid {{
  display: grid; grid-template-columns: repeat(3, 1fr);
  gap: 16px; margin-bottom: 40px;
}}
@media (max-width: 880px) {{ .ng-driver-grid {{ grid-template-columns: 1fr 1fr; }} }}
@media (max-width: 540px) {{ .ng-driver-grid {{ grid-template-columns: 1fr; }} }}
.ng-driver-card {{
  background: var(--card); border: 1px solid var(--border);
  border-radius: 12px; padding: 18px 20px;
  transition: border-color 0.2s, transform 0.2s;
}}
.ng-driver-card:hover {{ border-color: rgba(96,165,250,0.35); transform: translateY(-2px); }}
.ng-driver-icon {{ font-size: 1.6rem; margin-bottom: 6px; }}
.ng-driver-title {{
  font-size: 13px; font-weight: 800; color: #f1f5f9; margin-bottom: 6px;
}}
.ng-driver-body {{ font-size: 12.5px; color: #94a3b8; line-height: 1.55; margin-bottom: 10px; }}
.ng-driver-link {{
  font-size: 11px; font-weight: 700; color: {TTF_COLOR};
  text-decoration: none; letter-spacing: 0.5px;
}}
.ng-driver-link:hover {{ text-decoration: underline; }}

/* ── Risk panel ───────────────────────────────────────────────────────────── */
.ng-risk-grid {{
  display: grid; grid-template-columns: repeat(4, 1fr);
  gap: 14px; margin-bottom: 32px;
}}
@media (max-width: 780px) {{ .ng-risk-grid {{ grid-template-columns: 1fr 1fr; }} }}
@media (max-width: 440px) {{ .ng-risk-grid {{ grid-template-columns: 1fr; }} }}
.ng-risk-card {{
  background: var(--card); border: 1px solid var(--border);
  border-radius: 14px; padding: 18px;
  text-decoration: none; color: inherit;
  display: block;
  transition: border-color 0.2s, transform 0.2s;
}}
.ng-risk-card:hover {{ transform: translateY(-2px); }}
.ng-risk-name {{ font-size: 10px; font-weight: 700; letter-spacing: 1.2px; text-transform: uppercase; color: #64748b; }}
.ng-risk-val {{ font-size: 28px; font-weight: 800; color: #f1f5f9; font-variant-numeric: tabular-nums; margin: 4px 0 2px; }}
.ng-risk-band {{ font-size: 11px; font-weight: 700; letter-spacing: 1px; text-transform: uppercase; }}
.ng-risk-desc {{ font-size: 11px; color: #94a3b8; margin-top: 6px; }}

/* ── Commentary card ──────────────────────────────────────────────────────── */
.ng-commentary {{
  background: linear-gradient(135deg, #111827 0%, #0f172a 100%);
  border: 1px solid rgba(212,160,23,0.2);
  border-radius: 14px;
  padding: 26px 28px;
  margin-bottom: 40px;
  position: relative;
  overflow: hidden;
}}
.ng-commentary::before {{
  content: '';
  position: absolute; top: 0; left: 0; right: 0; height: 3px;
  background: linear-gradient(90deg, var(--gold), transparent);
}}
.ng-commentary p {{ font-size: 15px; color: #cbd5e1; line-height: 1.75; margin-bottom: 1em; }}
.ng-commentary p:last-child {{ margin-bottom: 0; }}
.ng-commentary p strong {{ color: #fff; }}
.ng-bias-badge {{
  display: inline-block; font-size: 11px; font-weight: 800;
  letter-spacing: 1.2px; text-transform: uppercase;
  padding: 5px 14px; border-radius: 20px; margin-bottom: 14px;
}}
.ng-engine-tag {{
  font-size: 10px; font-weight: 700; color: #64748b;
  letter-spacing: 1.2px; text-transform: uppercase; margin-top: 14px;
}}

/* ── Historical data table ────────────────────────────────────────────────── */
.ng-table-wrap {{
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 14px;
  overflow: hidden;
  margin-bottom: 40px;
}}
.ng-table-head {{
  display: flex; justify-content: space-between; align-items: center;
  padding: 16px 20px; border-bottom: 1px solid var(--border);
  flex-wrap: wrap; gap: 10px;
}}
.ng-table-head h3 {{ font-size: 16px; font-weight: 700; color: #f1f5f9; margin: 0; }}
.ng-table-csv {{
  font-size: 12px; font-weight: 700; color: {TTF_COLOR};
  text-decoration: none; padding: 6px 14px; border-radius: 8px;
  border: 1px solid rgba(96,165,250,0.3); background: rgba(96,165,250,0.06);
}}
.ng-table-scroll {{ overflow-x: auto; }}
.ng-table {{ width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }}
.ng-table th, .ng-table td {{
  padding: 10px 16px; text-align: left; font-size: 13px;
  border-bottom: 1px solid rgba(255,255,255,0.04);
}}
.ng-table th {{
  background: rgba(255,255,255,0.02);
  font-size: 10px; font-weight: 700; letter-spacing: 1.2px;
  text-transform: uppercase; color: #64748b;
}}
.ng-table td {{ color: #cbd5e1; }}
.ng-table tr:last-child td {{ border-bottom: none; }}

/* ── FAQ accordion ────────────────────────────────────────────────────────── */
.ng-faq {{ margin-bottom: 40px; }}
.ng-faq details {{
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 0;
  margin-bottom: 10px;
  overflow: hidden;
}}
.ng-faq summary {{
  list-style: none; cursor: pointer;
  font-size: 14px; font-weight: 700; color: #f1f5f9;
  padding: 16px 50px 16px 20px;
  position: relative;
}}
.ng-faq summary::-webkit-details-marker {{ display: none; }}
.ng-faq summary::after {{
  content: '+'; position: absolute; right: 18px; top: 50%;
  transform: translateY(-50%); font-size: 22px;
  color: {TTF_COLOR}; transition: transform 0.2s; font-weight: 400;
}}
.ng-faq details[open] summary::after {{ content: '\u2212'; }}
.ng-faq details > div {{
  padding: 0 20px 18px; font-size: 13.5px; color: #94a3b8; line-height: 1.7;
}}

/* ── Related-intelligence wheel grid ──────────────────────────────────────── */
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
  border-color: rgba(96,165,250,0.45);
  box-shadow: 0 4px 22px rgba(96,165,250,0.10);
  transform: translateY(-2px);
}}
.wheel-link-icon {{ font-size: 1.7rem; line-height: 1; }}
.wheel-link-label {{
  font-size: 11px; font-weight: 800; letter-spacing: 1.2px;
  text-transform: uppercase; color: {TTF_COLOR};
}}
.wheel-link-desc {{
  font-size: 11.5px; color: #94a3b8; line-height: 1.45;
  text-decoration: none;
}}

/* ── License block ───────────────────────────────────────────────────────── */
.ng-license {{
  background: rgba(255,255,255,0.02);
  border: 1px solid rgba(255,255,255,0.06);
  border-radius: 10px; padding: 18px 20px;
  margin-bottom: 40px; font-size: 12px; color: #94a3b8;
}}
.ng-license a {{ color: {TTF_COLOR}; text-decoration: none; font-weight: 700; }}
.ng-license a:hover {{ text-decoration: underline; }}

/* ── Conversion block ─────────────────────────────────────────────────────── */
.ng-conv {{
  background: linear-gradient(135deg, #0c1322 0%, #14233a 50%, #0f172a 100%);
  border: 1px solid rgba(96,165,250,0.3);
  border-radius: 18px; padding: 32px;
  text-align: center; margin-bottom: 40px;
}}
.ng-conv h2 {{
  font-family: 'DM Serif Display', serif;
  font-size: clamp(22px, 4vw, 32px); font-weight: 400;
  color: #fff; line-height: 1.25; margin-bottom: 12px;
}}
.ng-conv p {{ font-size: 14px; color: #94a3b8; max-width: 560px; margin: 0 auto 22px; }}
.ng-conv .ng-cta-primary, .ng-conv .ng-cta-secondary {{ margin: 4px; }}

/* ── Citation card ────────────────────────────────────────────────────────── */
.ng-cite-card {{
  background: var(--card); border: 1px solid var(--border);
  border-radius: 14px; padding: 24px 26px; margin-bottom: 36px;
  position: relative;
}}
.ng-cite-card h3 {{ font-size: 16px; font-weight: 700; color: #f1f5f9; margin-bottom: 8px; }}
.ng-cite-desc {{ font-size: 13px; color: #94a3b8; margin-bottom: 14px; }}
.ng-cite-code-wrap {{ position: relative; background: rgba(0,0,0,0.25); border-radius: 10px; padding: 16px 18px; }}
.ng-cite-code {{
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 12px; color: #cbd5e1; line-height: 1.7;
  margin: 0; white-space: pre-wrap; word-break: break-word;
}}
.ng-cite-code a {{ color: {TTF_COLOR}; text-decoration: none; }}
.ng-cite-copy-btn {{
  position: absolute; top: 12px; right: 12px;
  background: rgba(96,165,250,0.15); color: {TTF_COLOR};
  border: 1px solid rgba(96,165,250,0.35); border-radius: 6px;
  font-size: 11px; font-weight: 700; padding: 5px 12px; cursor: pointer;
}}
.ng-cite-footer {{ font-size: 11px; color: #64748b; margin-top: 12px; line-height: 1.6; }}
@media (max-width: 600px) {{
  .ng-cite-copy-btn {{ position: static; display: block; width: 100%; margin-top: 12px; }}
}}
"""


# ─────────────────────────────────────────────────────────────────────────────
# Multi-series time-range chart (TTF + Brent + VIX + Storage overlays)
# ─────────────────────────────────────────────────────────────────────────────

def _build_multi_chart_svg(rows, brent_rows, vix_rows, storage_rows,
                           label="30D", height=300):
    """
    Build a single SVG chart for one time range.
    Primary series: TTF (€/MWh) — left axis.
    Overlay series (toggleable via JS): Brent ($/bbl), VIX, EU Storage (%).
    Each overlay normalised to the same chart area using its own [min,max].

    Overlays are *date-aligned* to the TTF x-axis: for each TTF date, we look
    up the overlay value (or skip if missing) so movements line up truthfully.

    `rows` = list of dicts {date, ttf_price} sorted ascending (oldest -> newest)
    """
    if not rows:
        return f'<div style="padding:40px;color:#64748b;text-align:center;font-size:12px">No data available for {label}.</div>'

    W, H = 900, height
    PAD_L, PAD_R, PAD_T, PAD_B = 56, 56, 22, 44
    cw = W - PAD_L - PAD_R
    ch = H - PAD_T - PAD_B

    n_ttf = len(rows)
    ttf_dates = [r.get('date') for r in rows]
    # Position map: TTF date -> x-coordinate on chart
    x_for_idx = lambda i: PAD_L + (i / max(n_ttf - 1, 1)) * cw

    def _ttf_series():
        vals = [float(r['ttf_price']) for r in rows if r.get('ttf_price') is not None]
        if len(vals) < 2:
            return '', None, None
        vmin, vmax = min(vals), max(vals)
        if vmin == vmax:
            vmax = vmin * 1.01 + 0.0001
        rng = vmax - vmin
        pts = []
        for i, r in enumerate(rows):
            v = r.get('ttf_price')
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
            f'<g class="ng-series-ttf">'
            f'<path d="{area_d}" fill="{TTF_COLOR}" opacity="0.10"/>'
            f'<path d="{path_d}" fill="none" stroke="{TTF_COLOR}" stroke-width="2" '
            f'stroke-linejoin="round" stroke-linecap="round"/>'
            f'</g>'
        )
        return svg, vmin, vmax

    def _overlay_series(data, val_key, color, series_class):
        """Project an overlay series onto the TTF x-axis by date."""
        if not data:
            return ''
        # Build date -> value lookup
        lookup = {r['date']: r[val_key] for r in data if r.get('date') and r.get(val_key) is not None}
        # Restrict to TTF date window
        window_vals = [float(lookup[d]) for d in ttf_dates if d in lookup]
        if len(window_vals) < 2:
            return ''
        vmin, vmax = min(window_vals), max(window_vals)
        if vmin == vmax:
            vmax = vmin * 1.01 + 0.0001
        rng = vmax - vmin
        # Walk TTF dates; emit a polyline segment per contiguous run of dates with data
        segments = []
        cur = []
        for i, d in enumerate(ttf_dates):
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
        return f'<g class="{series_class}">{"".join(paths)}</g>'

    ttf_svg, ttf_min, ttf_max = _ttf_series()
    brent_svg = _overlay_series(brent_rows, 'brent_price', '#f97316', 'ng-series-brent')
    vix_svg   = _overlay_series(vix_rows, 'vix_close', '#a78bfa', 'ng-series-vix')
    stor_svg  = _overlay_series(storage_rows, 'eu_storage_percent', '#22c55e', 'ng-series-storage')

    # Y-axis gridlines + labels (TTF €/MWh)
    grid_svg = ''
    if ttf_min is not None and ttf_max is not None:
        ticks = 5
        rng = ttf_max - ttf_min
        for t in range(ticks + 1):
            frac = t / ticks
            y = PAD_T + ch - frac * ch
            v = ttf_min + frac * rng
            grid_svg += (
                f'<line x1="{PAD_L}" y1="{y:.1f}" x2="{W-PAD_R}" y2="{y:.1f}" '
                f'stroke="rgba(255,255,255,0.05)" stroke-width="1"/>'
                f'<text x="{PAD_L-8}" y="{y+3:.1f}" text-anchor="end" '
                f'font-size="10" fill="#64748b" font-family="Inter,sans-serif">'
                f'€{v:.1f}</text>'
            )

    # X-axis date labels (~6 evenly spaced)
    x_label_svg = ''
    if rows:
        n = len(rows)
        label_count = min(6, n)
        for k in range(label_count):
            idx = int(round(k * (n - 1) / max(label_count - 1, 1))) if label_count > 1 else 0
            x = PAD_L + (idx / max(n - 1, 1)) * cw
            d = rows[idx].get('date')
            txt = _fmt_date(d) if d else ''
            anchor = 'middle' if 0 < k < label_count - 1 else ('start' if k == 0 else 'end')
            x_label_svg += (
                f'<text x="{x:.1f}" y="{PAD_T+ch+22}" text-anchor="{anchor}" '
                f'font-size="10" fill="#64748b" font-family="Inter,sans-serif">{txt}</text>'
            )

    # Watermark
    watermark = (
        f'<text x="{W-PAD_R-6}" y="{PAD_T+16}" text-anchor="end" font-size="10" '
        f'fill="rgba(148,163,184,0.18)" font-family="Inter,sans-serif" '
        f'font-style="italic">EnergyRiskIQ.com</text>'
    )

    return (
        f'<svg viewBox="0 0 {W} {H}" preserveAspectRatio="xMidYMid meet" '
        f'xmlns="http://www.w3.org/2000/svg" '
        f'style="width:100%;height:auto;display:block;max-width:100%;" '
        f'class="ng-protected">'
        f'{grid_svg}{x_label_svg}{watermark}'
        f'{stor_svg}{vix_svg}{brent_svg}{ttf_svg}'
        f'</svg>'
    )


# ─────────────────────────────────────────────────────────────────────────────
# Custom-algorithm commentary (deterministic, no LLM)
# ─────────────────────────────────────────────────────────────────────────────

def _natgas_commentary(ttf_latest, ttf_7d_chg_pct, ttf_30d_chg_pct,
                       storage_pct, storage_dev, storage_band,
                       vix_close, eeri_val, eeri_band,
                       egsi_m_val, egsi_m_band, lng_price):
    """Deterministic 3-paragraph commentary + directional bias."""
    # Bias logic
    bull_score = 0
    bear_score = 0
    if ttf_7d_chg_pct > 2:    bull_score += 1
    if ttf_7d_chg_pct < -2:   bear_score += 1
    if storage_dev < -3:      bull_score += 1
    if storage_dev > 3:       bear_score += 1
    if eeri_val >= 65:        bull_score += 1
    if eeri_val <= 40:        bear_score += 1
    if egsi_m_val >= 60:      bull_score += 1
    if vix_close >= 25:       bull_score += 1
    if lng_price >= 16:       bull_score += 1
    if lng_price <= 10:       bear_score += 1

    if bull_score - bear_score >= 2:
        bias = ('BULLISH BIAS', '#22c55e', 'rgba(34,197,94,0.12)')
    elif bear_score - bull_score >= 2:
        bias = ('BEARISH BIAS', '#ef4444', 'rgba(239,68,68,0.12)')
    else:
        bias = ('NEUTRAL / RANGE-BOUND', '#eab308', 'rgba(234,179,8,0.12)')

    # Paragraph 1 — price action
    trend_word = "advanced" if ttf_7d_chg_pct > 0 else "softened" if ttf_7d_chg_pct < 0 else "held flat"
    p1 = (
        f"<strong>TTF natural gas settled near €{ttf_latest:.2f}/MWh today.</strong> "
        f"Over the past seven sessions, prices have {trend_word} by "
        f"{ttf_7d_chg_pct:+.1f}%, with a {ttf_30d_chg_pct:+.1f}% move across the trailing 30 days. "
        "European gas remains the global benchmark traders watch for winter demand, LNG arbitrage, "
        "and industrial-cost signals across the eurozone."
    )

    # Paragraph 2 — drivers
    storage_word = (
        "running ahead of the seasonal norm" if storage_dev >= 2 else
        "tracking below the seasonal norm" if storage_dev <= -2 else
        "broadly in line with the seasonal norm"
    )
    eeri_word = eeri_band.lower() if eeri_band else 'elevated'
    p2 = (
        f"EU gas storage is at <strong>{storage_pct:.1f}%</strong> ({storage_dev:+.1f}% vs seasonal norm), "
        f"{storage_word} and signalling a {storage_band.lower() if storage_band else 'moderate'} winter-balance risk. "
        f"The European Energy Risk Index (EERI) sits at <strong>{eeri_val}/100 ({eeri_word})</strong>, "
        f"while the gas-market stress signal EGSI-M reads {egsi_m_val:.1f} ({egsi_m_band}). "
        f"Asian JKM LNG is trading near ${lng_price:.2f}/MMBtu, which sets the marginal "
        "pull on US LNG cargoes between Europe and Asia."
    )

    # Paragraph 3 — outlook
    if bias[0].startswith('BULL'):
        outlook = (
            "Risk skew currently favours <strong>upside in TTF</strong> on the combination of "
            "tightening storage trajectory, elevated risk indices, and supportive LNG arbitrage. "
            "Custom Algorithm flags continued sensitivity to weather forecasts, Norwegian flow data, "
            "and any escalation in Red Sea / Middle East shipping risk."
        )
    elif bias[0].startswith('BEAR'):
        outlook = (
            "Risk skew currently favours <strong>downside in TTF</strong> as comfortable storage, "
            "softer JKM premium, and lower European risk indices weigh on near-term prices. "
            "Custom Algorithm flags downside protection from mild weather and resilient LNG send-out."
        )
    else:
        outlook = (
            "Risk balance is currently <strong>range-bound</strong>, with bullish storage and risk-index "
            "signals offset by softer LNG arbitrage and contained volatility. Custom Algorithm flags "
            "weather, LNG flows, and EERI escalation as the most likely directional triggers."
        )

    return bias, p1, p2, outlook


# ─────────────────────────────────────────────────────────────────────────────
# Sentiment badge helper
# ─────────────────────────────────────────────────────────────────────────────

def _sentiment_badge(chg_pct):
    if chg_pct > 1.5:
        return '<span class="ng-sentiment" style="background:rgba(34,197,94,0.14);color:#22c55e;">&#9650; BULLISH</span>'
    if chg_pct < -1.5:
        return '<span class="ng-sentiment" style="background:rgba(239,68,68,0.14);color:#ef4444;">&#9660; BEARISH</span>'
    return '<span class="ng-sentiment" style="background:rgba(234,179,8,0.14);color:#eab308;">&#9644; NEUTRAL</span>'


# ─────────────────────────────────────────────────────────────────────────────
# Data fetcher
# ─────────────────────────────────────────────────────────────────────────────

def _compute_natgas_data():
    """Fetch all required data from the production database.

    Each timeseries is fetched with ORDER BY date DESC LIMIT N to guarantee
    we always have the latest rows even if the table grows beyond N, then
    reversed in Python to ascending order for plotting.
    """
    # TTF history — newest first, then reverse to ascending
    ttf_rows = list(reversed(execute_production_query(
        "SELECT date, ttf_price FROM ttf_gas_snapshots "
        "WHERE ttf_price IS NOT NULL "
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

    storage_rows = list(reversed(execute_production_query(
        "SELECT date, eu_storage_percent, seasonal_norm, deviation_from_norm, risk_band "
        "FROM gas_storage_snapshots "
        "WHERE eu_storage_percent IS NOT NULL "
        "ORDER BY date DESC LIMIT 2000"
    ) or []))

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
    geri_row = execute_production_one(
        "SELECT date, value, band FROM intel_indices_daily "
        "WHERE index_id='global:geo_energy_risk' ORDER BY date DESC LIMIT 1"
    )

    # LNG latest
    lng_row = execute_production_one(
        "SELECT jkm_price FROM lng_price_snapshots ORDER BY date DESC LIMIT 1"
    )

    return {
        'ttf_rows': ttf_rows,
        'brent_rows': brent_rows,
        'vix_rows': vix_rows,
        'storage_rows': storage_rows,
        'eeri_row': eeri_row,
        'egsi_m_row': egsi_m_row,
        'egsi_s_row': egsi_s_row,
        'geri_row': geri_row,
        'lng_row': lng_row,
    }


def _filter_range(rows, days, date_key='date'):
    """Filter rows by trailing day window; returns ascending list."""
    if not rows or days is None:
        return rows
    cutoff = _date.today() - timedelta(days=days)
    return [r for r in rows if r.get(date_key) and r[date_key] >= cutoff]


def _filter_ytd(rows, date_key='date'):
    start = _date(_date.today().year, 1, 1)
    return [r for r in rows if r.get(date_key) and r[date_key] >= start]


# ─────────────────────────────────────────────────────────────────────────────
# HTML builder
# ─────────────────────────────────────────────────────────────────────────────

def _build_natgas_html(data, today_str, today_date):
    ttf_rows     = data['ttf_rows']
    brent_rows   = data['brent_rows']
    vix_rows     = data['vix_rows']
    storage_rows = data['storage_rows']
    eeri_row     = data['eeri_row']
    egsi_m_row   = data['egsi_m_row']
    egsi_s_row   = data['egsi_s_row']
    geri_row     = data['geri_row']
    lng_row      = data['lng_row']

    # Latest values
    ttf_latest = _safe_float(ttf_rows[-1]['ttf_price']) if ttf_rows else 0.0
    ttf_prev   = _safe_float(ttf_rows[-2]['ttf_price']) if len(ttf_rows) >= 2 else ttf_latest
    ttf_chg    = ttf_latest - ttf_prev
    ttf_chg_pct = (ttf_chg / ttf_prev * 100) if ttf_prev else 0.0
    ttf_date   = ttf_rows[-1]['date'] if ttf_rows else _date.today()

    # 7D / 30D / YTD changes
    def _pct_chg_from(idx_back):
        if len(ttf_rows) <= idx_back:
            return 0.0
        ref = _safe_float(ttf_rows[-idx_back-1]['ttf_price'])
        return ((ttf_latest - ref) / ref * 100) if ref else 0.0
    ttf_7d_chg_pct  = _pct_chg_from(7)
    ttf_30d_chg_pct = _pct_chg_from(30)

    # Storage / VIX / LNG / EERI / EGSI
    storage_latest = storage_rows[-1] if storage_rows else None
    storage_pct  = _safe_float((storage_latest or {}).get('eu_storage_percent', 0))
    storage_norm = _safe_float((storage_latest or {}).get('seasonal_norm', 0))
    storage_dev  = _safe_float((storage_latest or {}).get('deviation_from_norm', 0))
    storage_band = _html.escape(str((storage_latest or {}).get('risk_band') or 'MODERATE'))

    vix_close = _safe_float(vix_rows[-1]['vix_close']) if vix_rows else 0.0
    lng_price = _safe_float((lng_row or {}).get('jkm_price', 0))

    eeri_val = int(round(_safe_float((eeri_row or {}).get('value', 0))))
    eeri_band = _html.escape(str((eeri_row or {}).get('band') or 'ELEVATED'))
    egsi_m_val = round(_safe_float((egsi_m_row or {}).get('index_value', 0)), 1)
    egsi_m_band = _html.escape(str((egsi_m_row or {}).get('band') or 'ELEVATED'))
    egsi_s_val = round(_safe_float((egsi_s_row or {}).get('index_value', 0)), 1)
    egsi_s_band = _html.escape(str((egsi_s_row or {}).get('band') or 'ELEVATED'))
    geri_val = int(round(_safe_float((geri_row or {}).get('value', 0))))
    geri_band = _html.escape(str((geri_row or {}).get('band') or 'MODERATE'))

    # Trend arrow / colour
    arrow = _arrow(ttf_chg)
    color = _chg_color(ttf_chg)
    sentiment = _sentiment_badge(ttf_chg_pct)

    # Trend indicators
    def _trend(v): return '&#9650;' if v > 0.2 else '&#9660;' if v < -0.2 else '&#9644;'
    def _trend_color(v): return '#22c55e' if v > 0.2 else '#ef4444' if v < -0.2 else '#eab308'

    # Volatility label from VIX proxy
    if vix_close >= 25:
        vol_label, vol_color = 'ELEVATED', '#ef4444'
    elif vix_close >= 18:
        vol_label, vol_color = 'MODERATE', '#eab308'
    else:
        vol_label, vol_color = 'CALM', '#22c55e'

    # LNG context
    if lng_price >= 16:
        lng_ctx_label, lng_ctx_color = 'TIGHT', '#ef4444'
    elif lng_price >= 12:
        lng_ctx_label, lng_ctx_color = 'BALANCED', '#eab308'
    else:
        lng_ctx_label, lng_ctx_color = 'OVERSUPPLIED', '#22c55e'

    # Time range filters
    ttf_7d   = _filter_range(ttf_rows, 7)
    ttf_30d  = _filter_range(ttf_rows, 30)
    ttf_90d  = _filter_range(ttf_rows, 90)
    ttf_ytd  = _filter_ytd(ttf_rows)
    ttf_max  = ttf_rows

    brent_7d  = _filter_range(brent_rows, 7)
    brent_30d = _filter_range(brent_rows, 30)
    brent_90d = _filter_range(brent_rows, 90)
    brent_ytd = _filter_ytd(brent_rows)
    brent_max = brent_rows

    vix_7d  = _filter_range(vix_rows, 7)
    vix_30d = _filter_range(vix_rows, 30)
    vix_90d = _filter_range(vix_rows, 90)
    vix_ytd = _filter_ytd(vix_rows)
    vix_max = vix_rows

    stor_7d  = _filter_range(storage_rows, 7)
    stor_30d = _filter_range(storage_rows, 30)
    stor_90d = _filter_range(storage_rows, 90)
    stor_ytd = _filter_ytd(storage_rows)
    stor_max = storage_rows

    chart_7d  = _build_multi_chart_svg(ttf_7d,  brent_7d,  vix_7d,  stor_7d,  '7D')
    chart_30d = _build_multi_chart_svg(ttf_30d, brent_30d, vix_30d, stor_30d, '30D')
    chart_90d = _build_multi_chart_svg(ttf_90d, brent_90d, vix_90d, stor_90d, '90D')
    chart_ytd = _build_multi_chart_svg(ttf_ytd, brent_ytd, vix_ytd, stor_ytd, 'YTD')
    chart_max = _build_multi_chart_svg(ttf_max, brent_max, vix_max, stor_max, 'MAX')

    # Commentary
    (bias_label, bias_color, bias_bg), p1, p2, outlook = _natgas_commentary(
        ttf_latest, ttf_7d_chg_pct, ttf_30d_chg_pct,
        storage_pct, storage_dev, storage_band,
        vix_close, eeri_val, eeri_band,
        egsi_m_val, egsi_m_band, lng_price,
    )

    # Historical table (last 30 daily rows)
    hist = list(reversed(ttf_rows[-30:]))
    table_rows_html = ''
    for i, r in enumerate(hist):
        p = _safe_float(r['ttf_price'])
        if i + 1 < len(hist):
            prev = _safe_float(hist[i+1]['ttf_price'])
        else:
            prev = p
        chg = p - prev
        chg_pct = (chg / prev * 100) if prev else 0.0
        ccol = _chg_color(chg)
        table_rows_html += (
            f'<tr>'
            f'<td>{r["date"].isoformat() if r.get("date") else ""}</td>'
            f'<td class="ng-protected">&euro;{p:.2f}</td>'
            f'<td class="ng-protected" style="color:{ccol}">{chg:+.2f}</td>'
            f'<td class="ng-protected" style="color:{ccol}">{chg_pct:+.2f}%</td>'
            f'</tr>'
        )

    # Risk band colours
    eeri_c     = BAND_COLORS.get(eeri_band, '#f97316')
    egsi_m_c   = BAND_COLORS.get(egsi_m_band, '#f97316')
    egsi_s_c   = BAND_COLORS.get(egsi_s_band, '#f97316')
    geri_c     = BAND_COLORS.get(geri_band, '#f97316')
    storage_c  = '#22c55e' if storage_pct >= 60 else ('#eab308' if storage_pct >= 40 else '#ef4444')

    # FAQ definitions (schema + visible)
    faqs = [
        ("What is the natural gas price in Europe today?",
         f"As of {today_str}, the European TTF natural gas benchmark is trading near €{ttf_latest:.2f}/MWh, "
         f"a change of {ttf_chg:+.2f} ({ttf_chg_pct:+.2f}%) on the prior session. TTF is the most-watched "
         "wholesale gas price for the eurozone and the global LNG arbitrage reference."),
        ("What is TTF gas price?",
         "TTF (Title Transfer Facility) is the Dutch virtual trading hub for natural gas and the leading "
         "European gas benchmark. TTF prices are quoted in €/MWh and reflect the cost of one megawatt-hour "
         "of natural gas delivered into the Dutch grid for next-day or month-ahead delivery."),
        ("Why is natural gas expensive in Europe?",
         "European gas prices reflect a mix of factors: pipeline supply (Norway, North Africa, residual Russian "
         "flows), LNG imports competing with Asian buyers for cargoes, EU gas storage levels relative to "
         "seasonal norms, weather-driven heating demand, geopolitical risk premia, and crude-oil-linked "
         "long-term LNG contracts."),
        ("How does LNG affect gas prices?",
         "When Asian JKM LNG prices rise above European TTF, LNG cargoes are pulled toward Asia, tightening "
         "European supply and lifting TTF. When TTF trades at a premium to JKM, cargoes are diverted toward "
         "Europe. The JKM-TTF spread is the single most important real-time signal for European gas supply."),
        ("Will gas prices go up?",
         "Forward European gas prices depend on storage trajectory into winter, LNG send-out, weather, "
         "geopolitical risk and industrial demand. EnergyRiskIQ tracks all of these via the EERI risk index, "
         "EGSI gas-stress indices and storage telemetry to flag directional risk before price reacts."),
        ("What time of year are European gas prices highest?",
         "European gas prices typically peak between December and February when heating demand is strongest "
         "and storage withdrawal accelerates. Secondary spikes can occur in late summer (August-September) "
         "if storage refill is running behind seasonal norms ahead of winter."),
    ]
    faq_html = ''
    for q, a in faqs:
        faq_html += (
            f'<details><summary>{_html.escape(q)}</summary>'
            f'<div>{_html.escape(a)}</div></details>'
        )
    faq_schema_items = []
    for q, a in faqs:
        faq_schema_items.append({
            "@type": "Question",
            "name": q,
            "acceptedAnswer": {"@type": "Answer", "text": a},
        })
    import json as _json
    faqpage_schema = _json.dumps({
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": faq_schema_items,
    })

    dataset_schema = _json.dumps({
        "@context": "https://schema.org",
        "@type": "Dataset",
        "name": "European Natural Gas Price (TTF Benchmark) — Daily History",
        "description": (
            "Daily closing price of European TTF (Title Transfer Facility) natural gas in €/MWh, "
            "with risk-context overlays for Brent crude, VIX volatility and EU gas storage levels."
        ),
        "url": f"{BASE_URL}/data/natural-gas-price-today-europe",
        "creator":   {"@type": "Organization", "name": "EnergyRiskIQ", "url": BASE_URL},
        "publisher": {"@type": "Organization", "name": "EnergyRiskIQ", "url": BASE_URL},
        "license": f"{BASE_URL}/data-license",
        "isAccessibleForFree": True,
        "dateModified": today_date,
        "variableMeasured": [
            {"@type": "PropertyValue", "name": "TTF gas price", "unitText": "EUR/MWh"},
            {"@type": "PropertyValue", "name": "Brent crude price (overlay)", "unitText": "USD/barrel"},
            {"@type": "PropertyValue", "name": "EU gas storage", "unitText": "percent"},
            {"@type": "PropertyValue", "name": "VIX volatility (overlay)", "unitText": "index"},
        ],
        "measurementTechnique": "Custom Algorithm aggregation of TTF settlement prices, AGSI+ storage telemetry and reference market data.",
        "keywords": [
            "natural gas price europe", "ttf gas price today", "european gas price",
            "natural gas europe price chart", "europe gas market",
        ],
        "spatialCoverage": "Europe",
    })

    breadcrumb_schema = _json.dumps({
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": BASE_URL},
            {"@type": "ListItem", "position": 2, "name": "Data", "item": f"{BASE_URL}/data/energy-risk-snapshot"},
            {"@type": "ListItem", "position": 3, "name": "Natural Gas Price Today Europe (TTF)",
             "item": f"{BASE_URL}/data/natural-gas-price-today-europe"},
        ],
    })

    webpage_schema = _json.dumps({
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": "Natural Gas Price Today in Europe (TTF Benchmark)",
        "url": f"{BASE_URL}/data/natural-gas-price-today-europe",
        "description": "Live European TTF natural gas price, daily chart, storage levels, risk signals and market drivers.",
        "isAccessibleForFree": True,
        "publisher": {"@type": "Organization", "name": "EnergyRiskIQ", "url": BASE_URL},
        "license": f"{BASE_URL}/data-license",
        "dateModified": today_date,
    })

    finprod_schema = _json.dumps({
        "@context": "https://schema.org",
        "@type": "FinancialProduct",
        "name": "TTF Natural Gas",
        "description": "Dutch Title Transfer Facility (TTF) is the European wholesale natural gas benchmark, quoted in €/MWh.",
        "category": "Commodity / Natural Gas",
        "provider": {"@type": "Organization", "name": "EnergyRiskIQ", "url": BASE_URL},
    })

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
<style>
{_NATGAS_CSS}
</style>

<!-- ── ANTI-COPY PROTECTION (does not block search engines) ───────────── -->
<script>
(function(){{
  document.addEventListener('copy', function(e) {{
    var sel = window.getSelection ? window.getSelection().toString() : '';
    if (sel.length > 0) {{
      var attr = '\\n\\n[Source: EnergyRiskIQ.com — Natural Gas Price Today Europe | CC BY-NC 4.0 — non-commercial use only]';
      e.clipboardData.setData('text/plain', sel + attr);
      e.preventDefault();
    }}
  }});
  document.addEventListener('contextmenu', function(e) {{
    var t = e.target;
    if (t && (t.classList.contains('ng-protected') || (t.closest && t.closest('.ng-protected')))) {{
      e.preventDefault();
    }}
  }});
  document.addEventListener('keydown', function(e) {{
    if ((e.ctrlKey || e.metaKey) && (e.key === 's' || e.key === 'u')) {{
      var t = document.activeElement;
      if (t && (t.classList && t.classList.contains('ng-protected'))) {{
        e.preventDefault();
      }}
    }}
  }});
}})();
</script>

<!-- ── STICKY PRICE BAR ─────────────────────────────────────────────── -->
<div class="ng-sticky-bar">
  <span class="ng-sticky-label">&#128293; TTF Today</span>
  <span class="ng-sticky-price ng-protected">&euro;{ttf_latest:.2f}/MWh</span>
  <span class="ng-sticky-chg" style="color:{color};">{arrow} {ttf_chg:+.2f} ({ttf_chg_pct:+.2f}%)</span>
  <span class="ng-sticky-time">Updated: {today_str}</span>
  <a href="/users" class="ng-sticky-cta">Free Alerts &rarr;</a>
</div>

<!-- ── NAV ───────────────────────────────────────────────────────────── -->
<nav class="nav">
  <div class="nav-inner">
    <a href="/" class="logo">
      <img src="/static/logo.png" alt="EnergyRiskIQ" style="height:28px">
      <span>EnergyRiskIQ</span>
    </a>
    <div style="display:flex;align-items:center;gap:1.5rem;">
      <a href="/indices/europe-energy-risk-index" style="font-size:13px;color:#94a3b8;text-decoration:none;">EERI</a>
      <a href="/indices/europe-gas-stress-index" style="font-size:13px;color:#94a3b8;text-decoration:none;">EGSI</a>
      <a href="/data/ttf-gas-price-today" style="font-size:13px;color:#94a3b8;text-decoration:none;">TTF Daily</a>
      <a href="/gas-storage-levels-in-europe" style="font-size:13px;color:#94a3b8;text-decoration:none;">Storage</a>
      <a href="/users" class="cta-btn-nav">Unlock Deeper Intelligence</a>
    </div>
  </div>
</nav>

<!-- ── HERO ─────────────────────────────────────────────────────────── -->
<header class="hero">
  <div class="hero-date">&#128337; Updated Daily &nbsp;&bull;&nbsp; {today_str}</div>
  <h1>Natural Gas Price Today in Europe (TTF)<br><span style="font-size:0.65em;color:#94a3b8;font-style:italic;">&amp; EU Storage Levels</span></h1>
  <p class="hero-sub">
    Track the latest European natural gas price (TTF), daily changes and market trends.
    Updated daily with risk signals, storage levels and energy-market context &mdash;
    powered by EnergyRiskIQ Custom Algorithms.
  </p>
</header>

<main class="page-body">

  <!-- ── 1. LIVE PRICE CARD (HERO) ────────────────────────────────── -->
  <div class="ng-hero-card">
    <div class="ng-hero-bench">&#127470;&#127481; Dutch TTF &bull; European Benchmark</div>
    <div class="ng-hero-price-row">
      <div class="ng-hero-price ng-protected"><sup>&euro;</sup>{ttf_latest:.2f}</div>
      <div class="ng-hero-unit">/MWh</div>
      <div style="margin-left:auto;">{sentiment}</div>
    </div>
    <div class="ng-hero-chg ng-protected" style="color:{color};">
      {arrow} {ttf_chg:+.2f} &euro;/MWh &bull; {ttf_chg_pct:+.2f}% day-over-day
    </div>
    <div class="ng-hero-meta">
      <div><b>7D:</b> <span style="color:{_trend_color(ttf_7d_chg_pct)};">{_trend(ttf_7d_chg_pct)} {ttf_7d_chg_pct:+.1f}%</span></div>
      <div><b>30D:</b> <span style="color:{_trend_color(ttf_30d_chg_pct)};">{_trend(ttf_30d_chg_pct)} {ttf_30d_chg_pct:+.1f}%</span></div>
      <div><b>Last close:</b> {ttf_date.isoformat() if ttf_date else '—'}</div>
      <div><b>Source:</b> EnergyRiskIQ Daily Pipeline</div>
    </div>
    <div class="ng-hero-cta-row">
      <a href="/users" class="ng-cta-primary">Get Free Daily Energy Risk Alerts &rarr;</a>
      <a href="/users/account" class="ng-cta-secondary">View Full Gas Market Dashboard</a>
    </div>
  </div>

  <!-- ── 2. MAIN CHART ────────────────────────────────────────────── -->
  <div class="section-label" style="margin-bottom:20px;">&#128200; TTF Natural Gas Price Chart (Europe)</div>
  <div class="ng-chart-card">
    <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:12px;">
      <div>
        <div style="font-size:15px;font-weight:700;color:#f1f5f9;">European TTF Natural Gas &mdash; Daily Closing Price</div>
        <div style="font-size:12px;color:#94a3b8;margin-top:4px;">&euro;/MWh &bull; with optional overlays for Brent, VIX and EU Storage</div>
      </div>
      <div>{sentiment}</div>
    </div>

    <div class="ng-chart-toolbar">
      <div class="ng-tb-group">
        <span class="ng-tb-label">Range</span>
        <button class="ng-tb-btn" data-range="7d">7D</button>
        <button class="ng-tb-btn active" data-range="30d">30D</button>
        <button class="ng-tb-btn" data-range="90d">90D</button>
        <button class="ng-tb-btn" data-range="ytd">YTD</button>
        <button class="ng-tb-btn" data-range="max">MAX</button>
      </div>
      <span class="ng-tb-divider"></span>
      <div class="ng-tb-group">
        <span class="ng-tb-label">Overlay</span>
        <button class="ng-tb-btn" data-overlay="brent">Brent Oil</button>
        <button class="ng-tb-btn" data-overlay="vix">VIX</button>
        <button class="ng-tb-btn" data-overlay="storage">EU Storage</button>
      </div>
    </div>

    <div class="ng-chart-panel" data-panel="7d">{chart_7d}</div>
    <div class="ng-chart-panel active" data-panel="30d">{chart_30d}</div>
    <div class="ng-chart-panel" data-panel="90d">{chart_90d}</div>
    <div class="ng-chart-panel" data-panel="ytd">{chart_ytd}</div>
    <div class="ng-chart-panel" data-panel="max">{chart_max}</div>

    <div class="ng-chart-legend">
      <span><span class="lg-dot" style="background:{TTF_COLOR};"></span>TTF (&euro;/MWh)</span>
      <span><span class="lg-dot" style="background:#f97316;"></span>Brent ($/bbl) &mdash; overlay</span>
      <span><span class="lg-dot" style="background:#a78bfa;"></span>VIX &mdash; overlay</span>
      <span><span class="lg-dot" style="background:#22c55e;"></span>EU Storage (%) &mdash; overlay</span>
    </div>
    <div style="font-size:10px;color:#475569;margin-top:8px;">
      Overlay series are normalised to the chart area &mdash; toggle on/off to compare directional movement against TTF.
    </div>
  </div>

  <script>
  (function(){{
    var panels = document.querySelectorAll('.ng-chart-panel');
    var rangeBtns = document.querySelectorAll('.ng-tb-btn[data-range]');
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

    // Overlay toggles — hide overlays by default
    var overlayMap = {{
      brent: '.ng-series-brent',
      vix: '.ng-series-vix',
      storage: '.ng-series-storage'
    }};
    Object.keys(overlayMap).forEach(function(k){{
      document.querySelectorAll(overlayMap[k]).forEach(function(el){{
        el.style.display = 'none';
      }});
    }});
    document.querySelectorAll('.ng-tb-btn[data-overlay]').forEach(function(btn){{
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

  <!-- ── 3. QUICK MARKET SNAPSHOT ─────────────────────────────────── -->
  <div class="section-label" style="margin-bottom:20px;">&#9889; European Gas Market Snapshot (Today)</div>
  <div class="ng-snap-grid">
    <div class="ng-snap-cell">
      <div class="ng-snap-label">TTF Price</div>
      <div class="ng-snap-val ng-protected">&euro;{ttf_latest:.2f}</div>
      <div class="ng-snap-sub">per MWh &bull; {ttf_date.isoformat() if ttf_date else '—'}</div>
    </div>
    <div class="ng-snap-cell">
      <div class="ng-snap-label">7-Day Trend</div>
      <div class="ng-snap-val" style="color:{_trend_color(ttf_7d_chg_pct)};">{_trend(ttf_7d_chg_pct)} {ttf_7d_chg_pct:+.1f}%</div>
      <div class="ng-snap-sub">Weekly directional move</div>
    </div>
    <div class="ng-snap-cell">
      <div class="ng-snap-label">30-Day Trend</div>
      <div class="ng-snap-val" style="color:{_trend_color(ttf_30d_chg_pct)};">{_trend(ttf_30d_chg_pct)} {ttf_30d_chg_pct:+.1f}%</div>
      <div class="ng-snap-sub">Monthly directional move</div>
    </div>
    <div class="ng-snap-cell">
      <div class="ng-snap-label">Volatility (VIX proxy)</div>
      <div class="ng-snap-val" style="color:{vol_color};">{vol_label}</div>
      <div class="ng-snap-sub">VIX {vix_close:.2f}</div>
    </div>
    <div class="ng-snap-cell">
      <div class="ng-snap-label">EU Gas Storage</div>
      <div class="ng-snap-val" style="color:{storage_c};">{storage_pct:.1f}%</div>
      <div class="ng-snap-sub">{storage_dev:+.1f}% vs norm ({storage_norm:.1f}%)</div>
    </div>
    <div class="ng-snap-cell">
      <div class="ng-snap-label">LNG Flow Context</div>
      <div class="ng-snap-val" style="color:{lng_ctx_color};">{lng_ctx_label}</div>
      <div class="ng-snap-sub">JKM ${lng_price:.2f}/MMBtu</div>
    </div>
  </div>
  <div style="text-align:center;margin:-16px 0 40px;">
    <a href="/indices/europe-energy-risk-index" class="ng-cta-secondary">See Full Risk Breakdown &rarr; EERI / EGSI</a>
  </div>

  <!-- ── 4. WHY THIS MATTERS ──────────────────────────────────────── -->
  <div class="section-label" style="margin-bottom:20px;">&#129504; Why the European Natural Gas Price Matters</div>
  <div class="ng-grid-2">
    <div style="background:var(--card);border:1px solid var(--border);border-radius:14px;padding:22px 24px;">
      <h3 style="font-size:15px;font-weight:700;color:#f1f5f9;margin-bottom:10px;">TTF Is Europe&rsquo;s Benchmark Gas Price</h3>
      <p style="font-size:13.5px;color:#94a3b8;line-height:1.7;">
        The Dutch Title Transfer Facility (TTF) is the most-liquid wholesale natural gas hub in Europe
        and the reference price for European utilities, industrial consumers and LNG suppliers.
        TTF futures and spot quotes are the primary benchmark used by every major energy trader in the eurozone.
      </p>
    </div>
    <div style="background:var(--card);border:1px solid var(--border);border-radius:14px;padding:22px 24px;">
      <h3 style="font-size:15px;font-weight:700;color:#f1f5f9;margin-bottom:10px;">Why TTF Moves Everything Downstream</h3>
      <ul style="font-size:13.5px;color:#94a3b8;line-height:1.85;list-style:none;padding:0;">
        <li>&bull; <strong style="color:#cbd5e1;">Electricity prices</strong> &mdash; gas sets marginal-cost power in the EU</li>
        <li>&bull; <strong style="color:#cbd5e1;">Industrial costs</strong> &mdash; chemicals, fertilisers, steel, glass</li>
        <li>&bull; <strong style="color:#cbd5e1;">Inflation</strong> &mdash; gas pass-through into eurozone CPI</li>
        <li>&bull; <strong style="color:#cbd5e1;">Energy security</strong> &mdash; winter heating and storage adequacy</li>
        <li>&bull; <strong style="color:#cbd5e1;">LNG arbitrage</strong> &mdash; pulls cargoes between Europe and Asia</li>
      </ul>
      <div style="margin-top:14px;display:flex;gap:14px;flex-wrap:wrap;font-size:12px;">
        <a href="/indices/europe-energy-risk-index" style="color:{TTF_COLOR};text-decoration:none;font-weight:700;">&rarr; EERI</a>
        <a href="/indices/europe-gas-stress-index" style="color:{TTF_COLOR};text-decoration:none;font-weight:700;">&rarr; EGSI</a>
      </div>
    </div>
  </div>

  <!-- ── 5. PRICE DRIVERS ─────────────────────────────────────────── -->
  <div class="section-label" style="margin-bottom:20px;">&#128202; What Drives Natural Gas Prices in Europe?</div>
  <div class="ng-driver-grid">
    <div class="ng-driver-card">
      <div class="ng-driver-icon">&#128674;</div>
      <div class="ng-driver-title">Supply (LNG &amp; Pipelines)</div>
      <p class="ng-driver-body">LNG send-out from regasification terminals plus pipeline flows from Norway, Algeria
        and residual Russian volumes set Europe&rsquo;s daily supply baseline.</p>
      <a href="/data/europe-lng-supply-demand" class="ng-driver-link">View LNG Supply &amp; Demand &rarr;</a>
    </div>
    <div class="ng-driver-card">
      <div class="ng-driver-icon">&#127981;</div>
      <div class="ng-driver-title">Storage Levels</div>
      <p class="ng-driver-body">EU gas storage at <strong style="color:{storage_c};">{storage_pct:.1f}%</strong>
        ({storage_dev:+.1f}% vs norm). Storage trajectory is the dominant medium-term price signal.</p>
      <a href="/gas-storage-levels-in-europe" class="ng-driver-link">View Storage Levels &rarr;</a>
    </div>
    <div class="ng-driver-card">
      <div class="ng-driver-icon">&#127783;&#65039;</div>
      <div class="ng-driver-title">Weather &amp; Seasonality</div>
      <p class="ng-driver-body">Heating-degree days drive winter demand, while summer cooling and storage-refill
        cycles shape the shoulder seasons. Cold snaps repeatedly cause price spikes.</p>
      <a href="/research/what-drives-lng-prices" class="ng-driver-link">Read the Research &rarr;</a>
    </div>
    <div class="ng-driver-card">
      <div class="ng-driver-icon">&#128737;&#65039;</div>
      <div class="ng-driver-title">Geopolitical Risk</div>
      <p class="ng-driver-body">EERI sits at <strong style="color:{eeri_c};">{eeri_val}/100 ({eeri_band})</strong>.
        Conflict, sanctions and shipping risk drive risk-premia into European gas pricing.</p>
      <a href="/indices/europe-energy-risk-index" class="ng-driver-link">View EERI &rarr;</a>
    </div>
    <div class="ng-driver-card">
      <div class="ng-driver-icon">&#127759;</div>
      <div class="ng-driver-title">Global Energy Markets</div>
      <p class="ng-driver-body">Brent crude (oil-indexed LNG contracts) and the JKM LNG benchmark in Asia set the
        global arbitrage backdrop that pulls cargoes toward Europe or Asia.</p>
      <a href="/data/brent-crude-oil-price-today" class="ng-driver-link">Brent &rarr;</a>
      &nbsp;&nbsp;
      <a href="/data/jkm-lng-spot-price" class="ng-driver-link">JKM LNG &rarr;</a>
    </div>
    <div class="ng-driver-card">
      <div class="ng-driver-icon">&#128293;</div>
      <div class="ng-driver-title">Gas-System Stress</div>
      <p class="ng-driver-body">EGSI-M (market stress) at <strong style="color:{egsi_m_c};">{egsi_m_val} ({egsi_m_band})</strong>
        and EGSI-S (system stress) at <strong style="color:{egsi_s_c};">{egsi_s_val} ({egsi_s_band})</strong>
        capture supply-demand strain inside the European gas system.</p>
      <a href="/indices/europe-gas-stress-index" class="ng-driver-link">View EGSI &rarr;</a>
    </div>
  </div>

  <!-- ── 6. ENERGY RISK CONTEXT (UNIQUE EDGE) ──────────────────────── -->
  <div class="section-label" style="margin-bottom:20px;">&#127919; Energy Risk Signals (Europe)</div>
  <p style="font-size:13.5px;color:#94a3b8;line-height:1.7;margin-bottom:18px;max-width:780px;">
    Prices don&rsquo;t move randomly &mdash; they react to risk. EnergyRiskIQ&rsquo;s Custom Algorithms
    score live geopolitical, supply, demand and market-stress signals into structured indices so you
    can see directional risk <em>before</em> price reacts.
  </p>
  <div class="ng-risk-grid">
    <a href="/indices/europe-energy-risk-index" class="ng-risk-card" style="border-color:{eeri_c}33;">
      <div class="ng-risk-name">EERI</div>
      <div class="ng-risk-val">{eeri_val}<span style="font-size:14px;color:#64748b;font-weight:600;">/100</span></div>
      <div class="ng-risk-band" style="color:{eeri_c};">{eeri_band}</div>
      <div class="ng-risk-desc">Europe Energy Risk Index</div>
    </a>
    <a href="/indices/europe-gas-stress-index" class="ng-risk-card" style="border-color:{egsi_m_c}33;">
      <div class="ng-risk-name">EGSI-M</div>
      <div class="ng-risk-val">{egsi_m_val:.1f}</div>
      <div class="ng-risk-band" style="color:{egsi_m_c};">{egsi_m_band}</div>
      <div class="ng-risk-desc">Gas Market Stress</div>
    </a>
    <a href="/indices/europe-gas-stress-index" class="ng-risk-card" style="border-color:{egsi_s_c}33;">
      <div class="ng-risk-name">EGSI-S</div>
      <div class="ng-risk-val">{egsi_s_val:.1f}</div>
      <div class="ng-risk-band" style="color:{egsi_s_c};">{egsi_s_band}</div>
      <div class="ng-risk-desc">Gas System Stress</div>
    </a>
    <a href="/indices/global-energy-risk-index" class="ng-risk-card" style="border-color:{geri_c}33;">
      <div class="ng-risk-name">GERI</div>
      <div class="ng-risk-val">{geri_val}<span style="font-size:14px;color:#64748b;font-weight:600;">/100</span></div>
      <div class="ng-risk-band" style="color:{geri_c};">{geri_band}</div>
      <div class="ng-risk-desc">Global Energy Risk Index</div>
    </a>
  </div>
  <div style="text-align:center;margin-bottom:40px;">
    <a href="/users" class="ng-cta-primary">Unlock Real-Time Risk Signals &rarr;</a>
  </div>

  <!-- ── 7. DAILY COMMENTARY ──────────────────────────────────────── -->
  <div class="section-label" style="margin-bottom:20px;">&#128221; Today&rsquo;s Natural Gas Market Analysis</div>
  <div class="ng-commentary">
    <span class="ng-bias-badge" style="background:{bias_bg};color:{bias_color};">{bias_label}</span>
    <p>{p1}</p>
    <p>{p2}</p>
    <p>{outlook}</p>
    <div class="ng-engine-tag">&#9881;&#65039; Generated by EnergyRiskIQ Custom Algorithms &bull; updated daily</div>
  </div>

  <!-- ── 8. HISTORICAL DATA TABLE ─────────────────────────────────── -->
  <div class="section-label" style="margin-bottom:20px;">&#128196; TTF Gas Prices &mdash; Historical Data (Last 30 Days)</div>
  <div class="ng-table-wrap">
    <div class="ng-table-head">
      <h3>Daily TTF Closing Prices</h3>
      <a href="/api/natgas-ttf-prices.csv" class="ng-table-csv">&darr; Download CSV</a>
    </div>
    <div class="ng-table-scroll">
      <table class="ng-table">
        <thead>
          <tr><th>Date</th><th>Price (&euro;/MWh)</th><th>Change</th><th>% Change</th></tr>
        </thead>
        <tbody>{table_rows_html}</tbody>
      </table>
    </div>
  </div>

  <!-- ── 9. INTERNAL LINKING HUB ──────────────────────────────────── -->
  <div class="section-label" style="margin-bottom:20px;">&#128279; Related EnergyRiskIQ Intelligence</div>
  <div class="wheel-grid" style="margin-bottom:40px;">
    <a href="/data/ttf-gas-price-today" class="wheel-link">
      <div class="wheel-link-icon">&#127470;&#127489;</div>
      <div class="wheel-link-label">TTF Daily</div>
      <div class="wheel-link-desc">Original TTF daily-data page with full timeseries</div>
    </a>
    <a href="/data/europe-lng-supply-demand" class="wheel-link">
      <div class="wheel-link-icon">&#128168;</div>
      <div class="wheel-link-label">LNG Supply</div>
      <div class="wheel-link-desc">Europe LNG supply &amp; demand intelligence</div>
    </a>
    <a href="/gas-storage-levels-in-europe" class="wheel-link">
      <div class="wheel-link-icon">&#127981;</div>
      <div class="wheel-link-label">Gas Storage</div>
      <div class="wheel-link-desc">Live EU gas storage levels &amp; seasonal risk</div>
    </a>
    <a href="/data/brent-crude-oil-price-today" class="wheel-link">
      <div class="wheel-link-icon">&#128137;</div>
      <div class="wheel-link-label">Brent Crude</div>
      <div class="wheel-link-desc">Brent oil benchmark with risk overlays</div>
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
    <a href="/data/global-energy-risk-forecast" class="wheel-link">
      <div class="wheel-link-icon">&#128302;</div>
      <div class="wheel-link-label">24H Forecast</div>
      <div class="wheel-link-desc">Daily Custom Algorithm energy outlook</div>
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

  <!-- ── 10. CONVERSION BLOCK ─────────────────────────────────────── -->
  <div class="ng-conv">
    <h2>Don&rsquo;t Just Track Prices &mdash;<br>Understand the Risk</h2>
    <p>
      Most platforms show price. EnergyRiskIQ shows <strong style="color:#cbd5e1;">why prices move</strong>
      &mdash; with Custom Algorithm risk indices, daily intelligence digests and real-time alert signals
      across European gas, LNG and global energy markets.
    </p>
    <a href="/users" class="ng-cta-primary">Get Free Daily Risk Alerts &rarr;</a>
    <a href="/energy-risk-intelligence-signals" class="ng-cta-secondary">Upgrade to Pro for Real-Time Signals</a>
  </div>

  <!-- ── 11. FAQ ──────────────────────────────────────────────────── -->
  <div class="section-label" style="margin-bottom:20px;">&#10067; Frequently Asked Questions</div>
  <div class="ng-faq">
    {faq_html}
  </div>

  <!-- ── CITATION & REFERENCE ─────────────────────────────────────── -->
  <div class="section-label" style="margin-bottom:20px;">&#128196; Citation &amp; Reference</div>
  <div class="ng-cite-card">
    <h3>How to Cite This Page</h3>
    <p class="ng-cite-desc">
      This page is updated daily with fresh TTF natural gas data and Custom Algorithm risk context
      from the EnergyRiskIQ production pipeline. To reference this analysis in research, journalism
      or professional reports, use the citation below.
    </p>
    <div class="ng-cite-code-wrap">
      <pre class="ng-cite-code">EnergyRiskIQ. (2026). <em>Natural Gas Price Today in Europe (TTF Benchmark) &mdash; {today_str}</em>.
Retrieved from <a href="{BASE_URL}/data/natural-gas-price-today-europe">{BASE_URL}/data/natural-gas-price-today-europe</a>
Custom Algorithm interpretation. Data sources: TTF settlement prices, AGSI+ / GIE storage, Yahoo Finance (VIX, BZ=F), OilPriceAPI, EnergyRiskIQ internal risk pipeline.</pre>
      <button class="ng-cite-copy-btn" onclick="this.textContent='Copied!';setTimeout(()=>this.textContent='Copy',2000);navigator.clipboard&amp;&amp;navigator.clipboard.writeText('EnergyRiskIQ. (2026). Natural Gas Price Today in Europe (TTF Benchmark) — {today_str}. Retrieved from {BASE_URL}/data/natural-gas-price-today-europe')">Copy</button>
    </div>
    <div class="ng-cite-footer">
      Data is provided by EnergyRiskIQ&rsquo;s production pipeline (TTF settlement aggregation), AGSI+ / GIE
      (EU gas storage), Yahoo Finance (VIX), OilPriceAPI (Brent overlay) and the internal EERI / EGSI / GERI risk-scoring engines.
      <strong>Not financial advice.</strong>
      See <a href="{BASE_URL}/indices/europe-energy-risk-index">EERI methodology</a> for the full risk-scoring detail.
    </div>
  </div>

  <!-- ── 12. DATA LICENSE BLOCK ───────────────────────────────────── -->
  <div class="ng-license">
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
    <a href="/data/ttf-gas-price-today">TTF Daily</a>
    <a href="/indices/europe-energy-risk-index">EERI</a>
    <a href="/indices/europe-gas-stress-index">EGSI</a>
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

@router.get("/data/natural-gas-price-today-europe")
async def natural_gas_price_today_europe():
    async def generate():
        # Cheap latest-price lookup so the live TTF value can be server-rendered
        # into the <title>/meta description (SEO) before the loader streams.
        try:
            _latest = await asyncio.to_thread(
                execute_production_one,
                "SELECT ttf_price FROM ttf_gas_snapshots "
                "WHERE ttf_price IS NOT NULL ORDER BY date DESC LIMIT 1"
            )
            _ttf_latest = _safe_float(_latest['ttf_price']) if _latest else 0.0
        except Exception:
            _ttf_latest = 0.0
        if _ttf_latest > 0:
            _p = f"\u20ac{_ttf_latest:.2f}/MWh"
            _title_price, _desc_price = f" ({_p})", f" is {_p}"
        else:
            _title_price, _desc_price = "", ""
        yield _NATGAS_LOADER_HTML.replace(
            "{{TTF_TITLE}}", _title_price
        ).replace("{{TTF_DESC}}", _desc_price)
        try:
            data = await asyncio.to_thread(_compute_natgas_data)
        except Exception as exc:
            logger.error(f"Natgas data fetch failed: {exc}", exc_info=True)
            yield (
                "<script>var l=document.getElementById('snap-loader');"
                "if(l)l.style.display='none';document.body.style.overflow='';</script>"
                f"<div style='color:#ef4444;padding:40px;font-family:sans-serif;background:#0b0f1a;'>"
                f"<h2>Error loading natural gas data</h2><p>{_html.escape(str(exc))}</p></div></body></html>"
            )
            return

        today_str = datetime.now(timezone.utc).strftime('%B %-d, %Y')
        today_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        yield _build_natgas_html(data, today_str, today_date)

    return StreamingResponse(generate(), media_type="text/html")


# ─────────────────────────────────────────────────────────────────────────────
# CSV download
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/api/natgas-ttf-prices.csv")
async def natgas_ttf_prices_csv():
    rows = execute_production_query(
        "SELECT date, ttf_price FROM ttf_gas_snapshots "
        "WHERE ttf_price IS NOT NULL "
        "ORDER BY date DESC LIMIT 365"
    ) or []
    lines = ["date,ttf_price_eur_mwh"]
    for r in rows:
        d = r.get('date')
        p = r.get('ttf_price')
        if d is not None and p is not None:
            lines.append(f"{d.isoformat()},{float(p):.4f}")
    csv = "\n".join(lines) + "\n"
    return Response(
        content=csv,
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="energyriskiq-ttf-europe.csv"',
            "Cache-Control": "public, max-age=3600",
        },
    )
