"""
What Drives LNG Prices? — Research & Authority Page
Route: /research/what-drives-lng-prices
SEO authority page: full LNG market education, live risk signals, daily insight.
"""
import os
import json
import logging
import asyncio
import html as _html
from datetime import datetime, timezone, date as _date, timedelta

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from src.db.db import execute_production_one, execute_production_query
from src.api.snapshot_routes import _PAGE_CSS, _LOADER_HTML, BAND_COLORS, _safe_float

router = APIRouter()
logger = logging.getLogger(__name__)

BASE_URL = "https://energyriskiq.com"
LNG_COLOR = "#d4a017"

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _sign(v): return "+" if v >= 0 else ""
def _arrow(v): return "&#9650;" if v >= 0 else "&#9660;"
def _chg_color(v): return "#22c55e" if v >= 0 else "#ef4444"

def _fmt_date(d):
    try:
        return d.strftime("%B %-d, %Y") if d else "—"
    except Exception:
        return str(d)

def _short_date(d):
    try:
        return d.strftime("%b %-d") if d else "—"
    except Exception:
        return str(d)


# ─────────────────────────────────────────────────────────────────────────────
# Loader
# ─────────────────────────────────────────────────────────────────────────────

_DRIVERS_LOADER = _LOADER_HTML.replace(
    "Global Energy Risk Snapshot | EnergyRiskIQ",
    "What Drives LNG Prices? | Global LNG Market Explained | EnergyRiskIQ",
).replace(
    'name="description" content="Live global energy risk snapshot. Current GERI, EERI and EGSI-M index values with Brent crude, TTF gas, VIX and LNG market prices."',
    'name="description" content="Learn what drives LNG prices worldwide, including weather, storage, geopolitics, shipping, and supply-demand dynamics. Understand the global LNG market with EnergyRiskIQ."',
).replace(
    'rel="canonical" href="https://energyriskiq.com/data/energy-risk-snapshot"',
    'rel="canonical" href="https://energyriskiq.com/research/what-drives-lng-prices"',
).replace(
    "Fetching GERI\u00a0&\u00a0EERI indices\u2026",
    "Loading LNG market intelligence\u2026",
).replace(
    '<span class="ld-tag">GERI</span>\n    <span class="ld-tag">EERI</span>\n    <span class="ld-tag">EGSI&#8209;M</span>\n    <span class="ld-tag">Brent</span>\n    <span class="ld-tag">TTF</span>',
    '<span class="ld-tag">JKM</span>\n    <span class="ld-tag">TTF</span>\n    <span class="ld-tag">GERI</span>\n    <span class="ld-tag">EERI</span>\n    <span class="ld-tag">Brent</span>',
)


# ─────────────────────────────────────────────────────────────────────────────
# Page CSS
# ─────────────────────────────────────────────────────────────────────────────

_DRIVERS_CSS = f"""
/* ── Sticky insight bar ──────────────────────────────────────────────────── */
.drv-sticky {{
  position: fixed; bottom: 0; left: 0; right: 0; z-index: 900;
  background: rgba(15,23,42,0.96); backdrop-filter: blur(8px);
  border-top: 1px solid rgba(212,160,23,0.2);
  padding: 8px 20px;
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  font-size: 13px;
}}
.drv-sticky-label {{ color: #94a3b8; font-weight: 600; white-space: nowrap; }}
.drv-sticky-val {{ color: {LNG_COLOR}; font-weight: 800; font-size: 15px; }}
.drv-sticky-band {{ font-size: 11px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; }}
.drv-sticky-sep {{ color: #334155; }}
.drv-sticky-cta {{
  padding: 5px 14px; border-radius: 6px;
  background: rgba(212,160,23,0.12); border: 1px solid rgba(212,160,23,0.3);
  color: {LNG_COLOR}; font-size: 11px; font-weight: 700;
  text-decoration: none; letter-spacing: 0.04em; white-space: nowrap;
}}
@media (max-width: 640px) {{
  .drv-sticky {{ padding: 6px 10px; font-size: 11px; }}
  .drv-sticky-label {{ display: none; }}
  .drv-sticky-sep {{ display: none; }}
}}

/* ── Quick-answer box ────────────────────────────────────────────────────── */
.drv-snippet {{
  background: linear-gradient(135deg, #0e1a0d 0%, #0f172a 100%);
  border-left: 4px solid {LNG_COLOR}; border-radius: 0 12px 12px 0;
  padding: 24px 28px; margin-bottom: 40px;
  position: relative;
}}
.drv-snippet-label {{
  font-size: 10px; font-weight: 700; letter-spacing: 2px; text-transform: uppercase;
  color: {LNG_COLOR}; margin-bottom: 10px;
}}
.drv-snippet-body {{
  font-size: 17px; color: #e2e8f0; line-height: 1.8; font-weight: 400;
}}
.drv-snippet-body strong {{ color: #ffffff; font-weight: 700; }}
.drv-snippet-tags {{
  display: flex; flex-wrap: wrap; gap: 8px; margin-top: 16px;
}}
.drv-snippet-tag {{
  padding: 4px 12px; border-radius: 20px; font-size: 11px; font-weight: 700;
  letter-spacing: 0.06em; text-transform: uppercase; text-decoration: none;
  background: rgba(212,160,23,0.08); border: 1px solid rgba(212,160,23,0.2);
  color: {LNG_COLOR};
}}

/* ── LNG flow visual ─────────────────────────────────────────────────────── */
.drv-flow {{
  display: flex; align-items: center; justify-content: center;
  gap: 0; flex-wrap: nowrap; margin: 24px 0; overflow-x: auto;
}}
.drv-flow-node {{
  background: var(--card); border: 1px solid var(--border);
  border-radius: 12px; padding: 14px 18px; text-align: center;
  min-width: 110px; flex-shrink: 0;
}}
.drv-flow-icon {{ font-size: 1.8rem; margin-bottom: 4px; }}
.drv-flow-label {{ font-size: 11px; font-weight: 700; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.06em; }}
.drv-flow-sublabel {{ font-size: 10px; color: #64748b; margin-top: 2px; }}
.drv-flow-arrow {{
  font-size: 20px; color: {LNG_COLOR}; margin: 0 4px; flex-shrink: 0;
}}
@media (max-width: 600px) {{
  .drv-flow {{ gap: 0; justify-content: flex-start; }}
  .drv-flow-node {{ min-width: 88px; padding: 10px 10px; }}
  .drv-flow-label {{ font-size: 9px; }}
}}

/* ── Driver section cards ────────────────────────────────────────────────── */
.drv-driver-wrap {{
  display: flex; flex-direction: column; gap: 20px; margin-bottom: 40px;
}}
.drv-driver {{
  background: var(--card); border: 1px solid var(--border);
  border-radius: 14px; padding: 26px 28px;
  display: grid; grid-template-columns: 56px 1fr; gap: 20px; align-items: start;
}}
@media (max-width: 640px) {{
  .drv-driver {{ grid-template-columns: 1fr; gap: 12px; padding: 20px 16px; }}
}}
.drv-driver-num-wrap {{ text-align: center; }}
.drv-driver-icon {{ font-size: 2rem; line-height: 1; margin-bottom: 4px; }}
.drv-driver-num {{
  display: inline-block; font-size: 11px; font-weight: 800;
  letter-spacing: 0.1em; color: {LNG_COLOR};
  background: rgba(212,160,23,0.1); border: 1px solid rgba(212,160,23,0.2);
  border-radius: 4px; padding: 2px 6px;
}}
.drv-driver h3 {{
  font-size: 18px; font-weight: 700; color: #e2e8f0;
  margin-bottom: 10px; line-height: 1.3;
}}
.drv-driver-body {{
  font-size: 14px; color: #94a3b8; line-height: 1.8;
}}
.drv-driver-body strong {{ color: #e2e8f0; font-weight: 600; }}
.drv-driver-body a {{ color: {LNG_COLOR}; text-decoration: none; }}
.drv-driver-body a:hover {{ text-decoration: underline; }}
.drv-driver-link {{
  display: inline-flex; align-items: center; gap: 5px;
  margin-top: 12px; font-size: 12px; font-weight: 700;
  color: {LNG_COLOR}; text-decoration: none; border-bottom: 1px solid transparent;
}}
.drv-driver-link:hover {{ border-color: {LNG_COLOR}; }}

/* ── Live signal pill on driver cards ───────────────────────────────────── */
.drv-live-pill {{
  display: inline-flex; align-items: center; gap: 6px;
  padding: 4px 12px; border-radius: 20px; font-size: 11px; font-weight: 700;
  margin-top: 10px; margin-right: 8px;
  letter-spacing: 0.04em;
}}

/* ── Market context cards ────────────────────────────────────────────────── */
.drv-mkt-grid {{
  display: grid; grid-template-columns: repeat(5,1fr); gap: 12px; margin-bottom: 24px;
}}
@media (max-width: 900px) {{ .drv-mkt-grid {{ grid-template-columns: repeat(3,1fr); }} }}
@media (max-width: 600px) {{ .drv-mkt-grid {{ grid-template-columns: repeat(2,1fr); }} }}
.drv-mkt-card {{
  background: var(--card); border: 1px solid var(--border);
  border-radius: 12px; padding: 16px 14px; text-align: center;
  transition: border-color 0.2s;
}}
.drv-mkt-card:hover {{ border-color: rgba(212,160,23,0.35); }}
.drv-mkt-label {{
  font-size: 9px; font-weight: 700; letter-spacing: 1.5px; text-transform: uppercase;
  color: #64748b; margin-bottom: 6px;
}}
.drv-mkt-value {{ font-size: 22px; font-weight: 800; line-height: 1; margin-bottom: 4px; }}
.drv-mkt-chg {{ font-size: 11px; font-weight: 600; }}
.drv-mkt-note {{ font-size: 9px; color: #64748b; margin-top: 4px; }}

/* ── Risk index cards ────────────────────────────────────────────────────── */
.drv-risk-grid {{
  display: grid; grid-template-columns: repeat(4,1fr); gap: 12px; margin-bottom: 24px;
}}
@media (max-width: 800px) {{ .drv-risk-grid {{ grid-template-columns: repeat(2,1fr); }} }}
@media (max-width: 420px) {{ .drv-risk-grid {{ grid-template-columns: 1fr 1fr; }} }}
.drv-risk-card {{
  background: var(--card); border: 1px solid var(--border);
  border-radius: 12px; padding: 18px 14px; text-align: center;
  text-decoration: none; display: block; transition: all 0.2s;
}}
.drv-risk-card:hover {{
  border-color: rgba(212,160,23,0.3);
  transform: translateY(-1px);
  box-shadow: 0 4px 16px rgba(0,0,0,0.2);
}}
.drv-risk-name {{
  font-size: 9px; font-weight: 700; letter-spacing: 1.2px; text-transform: uppercase;
  color: #94a3b8; margin-bottom: 8px;
}}
.drv-risk-val {{ font-size: 38px; font-weight: 900; line-height: 1; margin-bottom: 4px; }}
.drv-risk-band {{ font-size: 10px; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 6px; }}
.drv-risk-desc {{ font-size: 11px; color: #64748b; line-height: 1.5; }}

/* ── Risk interpretation ─────────────────────────────────────────────────── */
.drv-risk-interp {{
  background: linear-gradient(135deg, rgba(212,160,23,0.05) 0%, transparent 100%);
  border: 1px solid rgba(212,160,23,0.15); border-radius: 12px;
  padding: 22px 26px; margin-bottom: 24px;
}}
.drv-risk-interp p {{
  font-size: 14px; color: #94a3b8; line-height: 1.8; margin-bottom: 10px;
}}
.drv-risk-interp p:last-child {{ margin-bottom: 0; }}
.drv-risk-interp strong {{ color: #e2e8f0; font-weight: 600; }}

/* ── Historical timeline ─────────────────────────────────────────────────── */
.drv-timeline {{ position: relative; margin-bottom: 40px; }}
.drv-timeline::before {{
  content: ''; position: absolute; left: 28px; top: 0; bottom: 0;
  width: 2px; background: linear-gradient({LNG_COLOR}, rgba(212,160,23,0.1));
}}
.drv-tl-item {{
  display: flex; gap: 20px; margin-bottom: 24px; position: relative;
}}
.drv-tl-dot-wrap {{
  flex-shrink: 0; width: 58px; display: flex;
  flex-direction: column; align-items: center;
}}
.drv-tl-dot {{
  width: 16px; height: 16px; border-radius: 50%;
  border: 2px solid {LNG_COLOR}; background: #0f172a;
  flex-shrink: 0; margin-top: 4px; position: relative; z-index: 1;
}}
.drv-tl-year {{
  font-size: 10px; font-weight: 700; color: {LNG_COLOR};
  margin-top: 4px; white-space: nowrap;
}}
.drv-tl-card {{
  flex: 1; background: var(--card); border: 1px solid var(--border);
  border-radius: 12px; padding: 18px 20px;
}}
.drv-tl-event {{
  font-size: 14px; font-weight: 700; color: #e2e8f0; margin-bottom: 6px;
}}
.drv-tl-desc {{
  font-size: 13px; color: #94a3b8; line-height: 1.7;
}}
.drv-tl-price {{
  display: inline-block; margin-top: 8px;
  font-size: 12px; font-weight: 700; color: {LNG_COLOR};
  background: rgba(212,160,23,0.1); border-radius: 4px; padding: 2px 8px;
}}
@media (max-width: 540px) {{
  .drv-timeline::before {{ left: 18px; }}
  .drv-tl-dot-wrap {{ width: 38px; }}
  .drv-tl-card {{ padding: 14px 14px; }}
}}

/* ── Insight card ────────────────────────────────────────────────────────── */
.drv-insight-card {{
  background: linear-gradient(135deg, #0e1708 0%, #0f172a 100%);
  border: 1px solid rgba(212,160,23,0.2); border-radius: 14px;
  padding: 30px 32px; margin-bottom: 40px; position: relative;
}}
.drv-insight-card::before {{
  content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px;
  background: linear-gradient(90deg, {LNG_COLOR}, transparent);
}}
.drv-insight-label {{
  font-size: 10px; font-weight: 700; letter-spacing: 0.12em;
  text-transform: uppercase; color: {LNG_COLOR}; margin-bottom: 18px;
}}
.drv-insight-section {{ margin-bottom: 18px; }}
.drv-insight-section:last-child {{ margin-bottom: 0; }}
.drv-insight-section-title {{
  font-size: 10px; font-weight: 700; letter-spacing: 0.08em;
  text-transform: uppercase; color: #64748b; margin-bottom: 6px;
}}
.drv-insight-body {{
  font-size: 15px; color: #cbd5e1; line-height: 1.8;
}}
.drv-insight-body strong {{ color: #ffffff; font-weight: 600; }}

/* ── CTA card ────────────────────────────────────────────────────────────── */
.drv-cta-card {{
  background: linear-gradient(135deg, #0e1708 0%, #14200a 50%, #0f172a 100%);
  border: 1px solid rgba(212,160,23,0.25); border-radius: 20px;
  padding: 44px 36px; text-align: center; margin-bottom: 40px;
  position: relative; overflow: hidden;
}}
.drv-cta-card::before {{
  content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px;
  background: linear-gradient(90deg, {LNG_COLOR}, rgba(212,160,23,0.3), transparent);
}}
.drv-cta-label {{
  font-size: 10px; font-weight: 700; letter-spacing: 2px;
  text-transform: uppercase; color: {LNG_COLOR}; margin-bottom: 12px;
}}
.drv-cta-h2 {{
  font-size: 28px; font-weight: 800; color: #e2e8f0;
  margin-bottom: 14px; line-height: 1.3;
}}
.drv-cta-sub {{
  font-size: 15px; color: #94a3b8; margin-bottom: 28px;
  max-width: 520px; margin-left: auto; margin-right: auto; line-height: 1.7;
}}
.drv-cta-benefits {{
  display: flex; justify-content: center; gap: 24px; flex-wrap: wrap; margin-bottom: 30px;
}}
.drv-cta-benefit {{
  font-size: 13px; color: #94a3b8; display: flex; align-items: center; gap: 7px;
}}
.drv-cta-benefit::before {{ content: '✓'; color: #22c55e; font-weight: 700; }}
.drv-cta-btn {{
  display: inline-block; padding: 15px 40px;
  background: linear-gradient(135deg, {LNG_COLOR}, #b8880f);
  color: #0f172a; font-size: 16px; font-weight: 800;
  border-radius: 10px; text-decoration: none; letter-spacing: 0.03em;
  box-shadow: 0 4px 20px rgba(212,160,23,0.3); transition: all 0.2s;
}}
.drv-cta-btn:hover {{ box-shadow: 0 6px 28px rgba(212,160,23,0.45); transform: translateY(-1px); }}
.drv-cta-credits {{ font-size: 11px; color: #64748b; margin-top: 12px; }}

/* ── FAQ ─────────────────────────────────────────────────────────────────── */
.drv-faq-card {{
  background: var(--card); border: 1px solid var(--border);
  border-radius: 12px; margin-bottom: 10px; overflow: hidden;
}}
.drv-faq-q {{
  padding: 18px 22px; font-size: 15px; font-weight: 600; color: #e2e8f0;
  cursor: pointer; display: flex; justify-content: space-between; align-items: center;
  user-select: none;
}}
.drv-faq-q:hover {{ color: {LNG_COLOR}; }}
.drv-faq-chevron {{ font-size: 13px; color: #64748b; transition: transform 0.25s; flex-shrink: 0; margin-left: 12px; }}
.drv-faq-a {{
  display: none; padding: 0 22px 18px; font-size: 14px;
  color: #94a3b8; line-height: 1.8;
}}
.drv-faq-a a {{ color: {LNG_COLOR}; text-decoration: none; }}
.drv-faq-card.open .drv-faq-chevron {{ transform: rotate(180deg); }}
.drv-faq-card.open .drv-faq-a {{ display: block; }}

/* ── Link hub ────────────────────────────────────────────────────────────── */
.drv-hub {{
  background: var(--card); border: 1px solid var(--border);
  border-radius: 14px; padding: 28px 30px; margin-bottom: 40px;
}}
.drv-hub-section {{ margin-bottom: 22px; }}
.drv-hub-section:last-child {{ margin-bottom: 0; }}
.drv-hub-title {{
  font-size: 10px; font-weight: 700; letter-spacing: 1.5px; text-transform: uppercase;
  color: #64748b; margin-bottom: 12px; display: flex; align-items: center; gap: 8px;
}}
.drv-hub-grid {{ display: flex; flex-wrap: wrap; gap: 8px; }}
.drv-hub-pill {{
  display: inline-flex; align-items: center; gap: 6px;
  padding: 7px 14px; border-radius: 20px;
  background: rgba(255,255,255,0.03); border: 1px solid var(--border);
  font-size: 12px; font-weight: 600; color: #94a3b8;
  text-decoration: none; transition: all 0.2s;
}}
.drv-hub-pill:hover {{ border-color: rgba(212,160,23,0.35); color: {LNG_COLOR}; }}

/* ── Citation card ───────────────────────────────────────────────────────── */
.drv-cite-card {{
  background: var(--card); border: 1px solid var(--border);
  border-radius: 12px; padding: 24px 26px; margin-bottom: 40px;
}}
.drv-cite-pre {{
  font-size: 12px; font-family: "JetBrains Mono","Courier New",monospace;
  color: #94a3b8; line-height: 1.75; margin: 0; white-space: pre-wrap;
  overflow-wrap: break-word; word-break: break-word;
}}
.drv-cite-pre em {{ color: {LNG_COLOR}; font-style: normal; }}
.drv-cite-pre a {{ color: #3b82f6; }}

/* ── Article section label ───────────────────────────────────────────────── */
.drv-section-lead {{
  font-size: 13px; color: #94a3b8; line-height: 1.8; margin-bottom: 24px;
}}
.drv-section-lead strong {{ color: #e2e8f0; font-weight: 600; }}
.drv-section-lead a {{ color: {LNG_COLOR}; text-decoration: none; }}

/* ── Newsletter capture ──────────────────────────────────────────────────── */
.drv-newsletter {{
  background: rgba(212,160,23,0.05); border: 1px solid rgba(212,160,23,0.15);
  border-radius: 12px; padding: 20px 24px;
  display: flex; align-items: center; gap: 16px; flex-wrap: wrap;
  margin-bottom: 40px;
}}
.drv-newsletter-text {{ flex: 1; min-width: 200px; }}
.drv-newsletter-title {{ font-size: 14px; font-weight: 700; color: #e2e8f0; margin-bottom: 4px; }}
.drv-newsletter-sub {{ font-size: 12px; color: #94a3b8; }}
.drv-newsletter-cta {{
  padding: 9px 22px; border-radius: 8px;
  background: rgba(212,160,23,0.12); border: 1px solid rgba(212,160,23,0.3);
  color: {LNG_COLOR}; font-size: 13px; font-weight: 700;
  text-decoration: none; white-space: nowrap;
}}

/* ── Mobile ──────────────────────────────────────────────────────────────── */
@media (max-width: 640px) {{
  .drv-insight-card {{ padding: 22px 16px; }}
  .drv-cta-card {{ padding: 28px 16px; }}
  .drv-cta-h2 {{ font-size: 22px; }}
  .drv-hub {{ padding: 20px 16px; }}
  .drv-cite-card {{ padding: 18px 16px; }}
  .drv-snippet {{ padding: 18px 16px; }}
  .drv-risk-interp {{ padding: 18px 16px; }}
  body {{ padding-bottom: 64px; }}
}}
@media (max-width: 600px) {{
  .nav-inner > div > a:not(.cta-btn-nav) {{ display: none; }}
}}
"""


# ─────────────────────────────────────────────────────────────────────────────
# Data Fetch
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_drivers_data() -> dict:
    jkm = execute_production_one(
        "SELECT date, jkm_price, jkm_change_24h, jkm_change_pct "
        "FROM lng_price_snapshots ORDER BY date DESC LIMIT 1"
    )
    jkm_prev = execute_production_one(
        "SELECT jkm_price FROM lng_price_snapshots ORDER BY date DESC LIMIT 1 OFFSET 1"
    )
    ttf = execute_production_one(
        "SELECT date, ttf_price FROM ttf_gas_snapshots ORDER BY date DESC LIMIT 1"
    )
    ttf_prev = execute_production_one(
        "SELECT ttf_price FROM ttf_gas_snapshots ORDER BY date DESC LIMIT 1 OFFSET 1"
    )
    brent = execute_production_one(
        "SELECT date, brent_price, brent_change_24h, brent_change_pct "
        "FROM oil_price_snapshots ORDER BY date DESC LIMIT 1"
    )
    vix = execute_production_one(
        "SELECT date, vix_close FROM vix_snapshots ORDER BY date DESC LIMIT 1"
    )
    vix_prev = execute_production_one(
        "SELECT vix_close FROM vix_snapshots ORDER BY date DESC LIMIT 1 OFFSET 1"
    )
    storage = execute_production_one(
        "SELECT date, eu_storage_percent, seasonal_norm, deviation_from_norm, risk_band "
        "FROM gas_storage_snapshots ORDER BY date DESC LIMIT 1"
    )
    geri = execute_production_one(
        "SELECT date, value, band FROM intel_indices_daily "
        "WHERE index_id='global:geo_energy_risk' ORDER BY date DESC LIMIT 1"
    )
    geri_prev = execute_production_one(
        "SELECT value FROM intel_indices_daily "
        "WHERE index_id='global:geo_energy_risk' ORDER BY date DESC LIMIT 1 OFFSET 1"
    )
    eeri = execute_production_one(
        "SELECT date, value, band FROM reri_indices_daily "
        "WHERE index_id='europe:eeri' ORDER BY date DESC LIMIT 1"
    )
    eeri_prev = execute_production_one(
        "SELECT value FROM reri_indices_daily "
        "WHERE index_id='europe:eeri' ORDER BY date DESC LIMIT 1 OFFSET 1"
    )
    egsi_m = execute_production_one(
        "SELECT index_date, index_value, band FROM egsi_m_daily "
        "WHERE region='Europe' ORDER BY index_date DESC LIMIT 1"
    )
    egsi_s = execute_production_one(
        "SELECT index_date, index_value, band FROM egsi_s_daily "
        "WHERE region='Europe' ORDER BY index_date DESC LIMIT 1"
    )
    alert_cats = execute_production_query(
        "SELECT category, COUNT(*) as cnt FROM alert_events "
        "WHERE created_at >= NOW() - INTERVAL '72 hours' "
        "GROUP BY category ORDER BY cnt DESC LIMIT 5"
    ) or []
    return dict(
        jkm=jkm, jkm_prev=jkm_prev,
        ttf=ttf, ttf_prev=ttf_prev,
        brent=brent, vix=vix, vix_prev=vix_prev,
        storage=storage, geri=geri, geri_prev=geri_prev,
        eeri=eeri, eeri_prev=eeri_prev,
        egsi_m=egsi_m, egsi_s=egsi_s,
        alert_cats=alert_cats,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Insight Engine (Custom Algorithms)
# ─────────────────────────────────────────────────────────────────────────────

_INSIGHT_CACHE: dict = {}


def _run_drivers_insight(today_str, jkm_price, jkm_chg_pct, ttf_price,
                         brent_price, vix, storage_pct, geri_val, geri_band,
                         eeri_val, eeri_band, alert_summary) -> dict:
    cache_key = f"drv:{today_str}:{round(jkm_price, 1)}:{geri_val}"
    if cache_key in _INSIGHT_CACHE:
        return _INSIGHT_CACHE[cache_key]

    jkm_ttf_spread = round(jkm_price - (ttf_price / 3.412), 2) if ttf_price else 0
    oil_linked = round(brent_price * 0.135, 2) if brent_price else 0
    arb = "JKM premium" if jkm_ttf_spread > 0 else "TTF premium"

    fallback = {
        "environment": (
            f"The current LNG market environment is characterised by JKM at ${jkm_price:.2f}/MMBtu "
            f"and TTF at €{ttf_price:.2f}/MWh. The JKM-TTF spread of ${jkm_ttf_spread:.2f}/MMBtu ({arb}) "
            f"signals current cargo routing preference between Asia and Europe."
        ),
        "stress": (
            f"Market stress indicators are mixed: GERI at {geri_val}/100 ({geri_band}) and "
            f"EERI at {eeri_val}/100 ({eeri_band}). EU gas storage at {storage_pct:.1f}% "
            f"relative to seasonal norms is a key driver of European LNG demand urgency."
        ),
        "watchpoints": (
            f"Key watchpoints include Asian demand trajectory, EU storage injection pace, "
            f"and shipping lane stability. Brent at ${brent_price:.2f}/bbl sets the reference "
            f"floor for oil-indexed long-term LNG contracts (~${oil_linked:.2f}/MMBtu)."
        ),
    }

    try:
        from openai import OpenAI
        key = os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY")
        url = os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL")
        client = OpenAI(api_key=key, base_url=url) if key and url else OpenAI()

        prompt = f"""You are EnergyRiskIQ's senior LNG market analyst. Today is {today_str}.

LIVE DATA:
JKM LNG: ${jkm_price:.2f}/MMBtu  change={jkm_chg_pct:+.2f}%
TTF Natural Gas: €{ttf_price:.2f}/MWh  JKM-TTF spread: ~${jkm_ttf_spread:.2f}/MMBtu ({arb})
Brent Crude: ${brent_price:.2f}/bbl  Oil-indexed LNG ref: ~${oil_linked:.2f}/MMBtu
VIX: {vix:.2f}
EU Gas Storage: {storage_pct:.1f}%
GERI: {geri_val}/100  band={geri_band}
EERI: {eeri_val}/100  band={eeri_band}
Recent risk alerts: {alert_summary}

Return ONLY valid JSON with exactly these 3 keys. No markdown, no AI mentions. Write as proprietary market analysis.

1. "environment" (≤230 chars): 2 sentences on current LNG market environment. Reference specific prices and spreads.
2. "stress" (≤230 chars): 2 sentences on market stress signals and risk indices. Reference GERI/EERI/storage.
3. "watchpoints" (≤230 chars): 2 forward-looking sentences on what to monitor next in LNG markets.

Authoritative, factual, no bullets, no AI references, no financial advice disclaimers."""

        resp = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.25,
            max_tokens=440,
            response_format={"type": "json_object"},
            timeout=18,
        )
        data = json.loads(resp.choices[0].message.content)
        result = {k: str(data.get(k, fallback[k])).strip() for k in fallback}
        _INSIGHT_CACHE[cache_key] = result
        return result
    except Exception as exc:
        logger.warning(f"LNG drivers insight engine: {exc}")
        return fallback


# ─────────────────────────────────────────────────────────────────────────────
# HTML Builder
# ─────────────────────────────────────────────────────────────────────────────

_FAQ_ENTRIES = [
    ("What affects LNG prices the most?",
     "The single biggest driver of LNG prices is the balance between Asian demand (Japan, Korea, China) and global LNG supply. Weather extremes — cold winters or hot summers in major consuming countries — can override all other factors in the short term. Geopolitical events that threaten supply routes or export capacity (captured in EnergyRiskIQ's GERI) are the second most important driver. Learn more: <a href='/data/jkm-lng-price-chart'>JKM LNG Price Chart</a>."),
    ("Why are LNG prices so volatile?",
     "LNG is a global commodity with thin spot market liquidity. Demand is highly weather-sensitive, supply is lumpy (large export terminals either work or they don't), and shipping is slow — it can take 15–25 days to redirect a cargo. This means supply and demand imbalances can't be fixed quickly, amplifying price volatility. The 2021–2022 energy crisis saw JKM spike from $8 to over $56/MMBtu in 18 months."),
    ("What is JKM LNG?",
     "JKM (Japan Korea Marker) is Asia's primary LNG spot price benchmark, assessed daily by S&P Global Platts in US dollars per MMBtu. It reflects delivered LNG prices for cargoes to Northeast Asia (Japan and Korea) and is the global reference for approximately one-third of all LNG trade. EnergyRiskIQ tracks JKM daily. <a href='/data/jkm-lng-price-chart'>View JKM LNG price chart →</a>"),
    ("Why do LNG prices spike in winter?",
     "Cold winters drive heating demand in Japan, Korea, and China — the world's three largest LNG importers. When winter is unexpectedly cold, these countries rush to procure additional LNG cargoes on the spot market simultaneously, creating supply competition that pushes JKM prices sharply higher. December–February is consistently the highest-demand period for Northeast Asian LNG imports."),
    ("How does Europe affect global LNG prices?",
     "Since 2022, Europe has replaced Russian pipeline gas with LNG, making European buyers permanent competitors for Pacific cargoes. EU gas storage levels (currently shown live on EnergyRiskIQ) determine European LNG demand urgency. When European storage is critically low, TTF prices surge and European buyers outbid Asian buyers, redirecting flexible LNG cargoes westward and constraining Asian supply. <a href='/gas-storage-levels-in-europe'>View Europe gas storage levels →</a>"),
    ("How are LNG prices linked to oil?",
     "A large proportion of long-term LNG contracts (particularly those supplying Japan and Korea) are indexed to crude oil prices — typically at approximately 12–15% of Brent crude price per barrel. For example, with Brent at the current level, the oil-indexed LNG formula reference is approximately $14–16/MMBtu. Spot LNG (JKM) can trade significantly above or below this level depending on supply-demand conditions. <a href='/data/brent-crude-oil-price-today'>View Brent crude oil price today →</a>"),
    ("What is the difference between LNG and natural gas prices?",
     "Natural gas prices (TTF for Europe, Henry Hub for the US) reflect pipeline gas benchmarks for specific regional markets. LNG prices (JKM for Asia) reflect the same commodity after it has been liquefied, shipped at -162°C, and regasified at an import terminal — a process that adds $3–6/MMBtu of costs. LNG allows natural gas to be traded globally, but its price includes these liquefaction and shipping costs on top of the underlying gas price."),
]


def _build_faq_html() -> str:
    out = ""
    for i, (q, a) in enumerate(_FAQ_ENTRIES):
        out += f"""<div class="drv-faq-card" id="drv-faq-{i}">
  <div class="drv-faq-q" onclick="(function(el){{el.closest('.drv-faq-card').classList.toggle('open')}})( this)">
    <span>{_html.escape(q)}</span>
    <span class="drv-faq-chevron">&#9660;</span>
  </div>
  <div class="drv-faq-a">{a}</div>
</div>"""
    return out


def _build_drivers_html(data: dict) -> str:
    today_str = datetime.now(timezone.utc).strftime("%B %-d, %Y")
    today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # ── Extract values ──
    jr = data["jkm"] or {}
    jkm_price = _safe_float(jr.get("jkm_price", 0))
    jkm_chg = _safe_float(jr.get("jkm_change_24h", 0))
    jkm_chg_pct = _safe_float(jr.get("jkm_change_pct", 0))
    jkm_date = jr.get("date", today_iso)

    tr = data["ttf"] or {}
    ttf_price = _safe_float(tr.get("ttf_price", 0))
    ttf_prev_price = _safe_float((data["ttf_prev"] or {}).get("ttf_price", ttf_price))
    ttf_chg = ttf_price - ttf_prev_price

    br = data["brent"] or {}
    brent_price = _safe_float(br.get("brent_price", 0))
    brent_chg = _safe_float(br.get("brent_change_24h", 0))
    brent_chg_pct = _safe_float(br.get("brent_change_pct", 0))

    vr = data["vix"] or {}
    vix_close = _safe_float(vr.get("vix_close", 18))
    vix_prev = _safe_float((data["vix_prev"] or {}).get("vix_close", vix_close))
    vix_chg = vix_close - vix_prev

    sr = data["storage"] or {}
    storage_pct = _safe_float(sr.get("eu_storage_percent", 45))
    storage_norm = _safe_float(sr.get("seasonal_norm", 55))
    storage_dev = _safe_float(sr.get("deviation_from_norm", 0))
    storage_vs = "above" if storage_dev >= 0 else "below"

    gr = data["geri"] or {}
    geri_val = int(round(_safe_float(gr.get("value", 0))))
    geri_band = str(gr.get("band", "MODERATE"))
    geri_prev_val = int(round(_safe_float((data["geri_prev"] or {}).get("value", geri_val))))
    geri_delta = geri_val - geri_prev_val

    er = data["eeri"] or {}
    eeri_val = int(round(_safe_float(er.get("value", 0))))
    eeri_band = str(er.get("band", "LOW"))
    eeri_prev_val = int(round(_safe_float((data["eeri_prev"] or {}).get("value", eeri_val))))
    eeri_delta = eeri_val - eeri_prev_val

    mr = data["egsi_m"] or {}
    egsi_m_val = round(_safe_float(mr.get("index_value", 0)), 1)
    egsi_m_band = str(mr.get("band", "LOW"))

    ss = data["egsi_s"] or {}
    egsi_s_val = round(_safe_float(ss.get("index_value", 0)), 1)
    egsi_s_band = str(ss.get("band", "LOW"))

    gc = BAND_COLORS.get(geri_band, "#f97316")
    ec = BAND_COLORS.get(eeri_band, "#22c55e")
    mgc = BAND_COLORS.get(egsi_m_band, "#f97316")
    sgc = BAND_COLORS.get(egsi_s_band, "#f97316")

    # ── Derived signals ──
    jkm_ttf_spread = round(jkm_price - (ttf_price / 3.412), 2) if ttf_price else 0.0
    oil_linked = round(brent_price * 0.135, 2)
    arb_dir = "JKM premium \u2014 Asia attracting LNG cargoes" if jkm_ttf_spread > 0 else "TTF premium \u2014 Europe attracting LNG cargoes"
    storage_implication = (
        "below-normal storage level creates urgency for European LNG procurement and supports JKM prices"
        if storage_dev < 0 else
        "above-normal level reduces European LNG demand urgency and limits JKM upside from the European arbitrage channel"
    )
    storage_status = "critically low" if storage_pct < 40 else ("low" if storage_pct < 50 else "moderate" if storage_pct < 65 else "healthy")
    geri_risk_desc = {"LOW": "low geopolitical supply risk", "MODERATE": "moderate geopolitical risk",
                      "ELEVATED": "elevated geopolitical risk", "SEVERE": "severe supply risk",
                      "CRITICAL": "critical geopolitical threat"}.get(geri_band, "moderate risk")
    vix_desc = "low market anxiety" if vix_close < 18 else ("moderate volatility" if vix_close < 25 else "elevated fear")

    j_arrow = _arrow(jkm_chg)
    j_color = _chg_color(jkm_chg)
    t_arrow = _arrow(ttf_chg)
    t_color = _chg_color(ttf_chg)
    b_arrow = _arrow(brent_chg)
    b_color = _chg_color(brent_chg)
    v_arrow = _arrow(vix_chg)
    v_color = _chg_color(vix_chg)

    alert_summary = ", ".join(
        f"{r['category']}={r['cnt']}" for r in (data["alert_cats"] or [])
    ) or "no recent alerts"

    insight = _run_drivers_insight(
        today_str, jkm_price, jkm_chg_pct, ttf_price,
        brent_price, vix_close, storage_pct, geri_val, geri_band,
        eeri_val, eeri_band, alert_summary,
    )

    faq_ld = json.dumps({
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": q,
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": a.replace("<a href", "<a href").replace("</a>", "")
                }
            }
            for q, a in _FAQ_ENTRIES
        ]
    }, indent=2)

    schemas_ld = json.dumps({
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Article",
                "headline": "What Drives LNG Prices? Understanding the Global LNG Market",
                "description": "Learn what drives LNG prices worldwide, including weather, storage, geopolitics, shipping, and supply-demand dynamics. Understand the global LNG market with EnergyRiskIQ.",
                "url": f"{BASE_URL}/research/what-drives-lng-prices",
                "dateModified": today_iso,
                "datePublished": "2024-01-01",
                "publisher": {"@type": "Organization", "name": "EnergyRiskIQ", "url": BASE_URL},
                "author": {"@type": "Organization", "name": "EnergyRiskIQ"},
                "about": [
                    {"@type": "Thing", "name": "LNG Prices"},
                    {"@type": "Thing", "name": "Global LNG Market"},
                    {"@type": "Thing", "name": "Energy Risk"},
                ],
                "image": f"{BASE_URL}/static/og-default.png",
            },
            {
                "@type": "Dataset",
                "name": "LNG Market Risk Indicators — Daily",
                "description": "Daily JKM LNG price, TTF gas, Brent crude, EU storage, GERI and EERI risk indices updated by EnergyRiskIQ.",
                "url": f"{BASE_URL}/research/what-drives-lng-prices",
                "creator": {"@type": "Organization", "name": "EnergyRiskIQ", "url": BASE_URL},
                "publisher": {"@type": "Organization", "name": "EnergyRiskIQ", "url": BASE_URL},
                "license": f"{BASE_URL}/data-license",
                "isAccessibleForFree": True,
                "dateModified": today_iso,
                "variableMeasured": [
                    {"@type": "PropertyValue", "name": "JKM LNG Price", "unitCode": "USD/MMBTU"},
                    {"@type": "PropertyValue", "name": "TTF Natural Gas", "unitCode": "EUR/MWH"},
                    {"@type": "PropertyValue", "name": "GERI (Global Energy Risk Index)", "unitCode": "score"},
                ],
                "measurementTechnique": "EnergyRiskIQ proprietary risk pipeline; OilPriceAPI; AGSI+",
                "keywords": ["LNG prices", "JKM", "what drives LNG prices", "LNG market", "energy risk"],
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Home", "item": BASE_URL},
                    {"@type": "ListItem", "position": 2, "name": "Research", "item": f"{BASE_URL}/research"},
                    {"@type": "ListItem", "position": 3, "name": "What Drives LNG Prices?",
                     "item": f"{BASE_URL}/research/what-drives-lng-prices"},
                ]
            },
        ]
    }, indent=2)

    faq_html = _build_faq_html()

    # ── Assemble page ──
    return f"""<script>
var l=document.getElementById('snap-loader');
if(l){{l.style.display='none';}}
document.body.style.overflow='';
</script>
<script type="application/ld+json">
{schemas_ld}
</script>
<script type="application/ld+json">
{faq_ld}
</script>
<style>
{_DRIVERS_CSS}
</style>

<!-- ── STICKY INSIGHT BAR ────────────────────────────────────────────────── -->
<div class="drv-sticky">
  <span class="drv-sticky-label">&#128200; LNG Market Risk Level</span>
  <span class="drv-sticky-val">{geri_val}/100</span>
  <span class="drv-sticky-band" style="color:{gc};">{geri_band}</span>
  <span class="drv-sticky-sep">&bull;</span>
  <span style="color:#94a3b8;font-size:12px;">JKM <strong style="color:{LNG_COLOR};">${jkm_price:.2f}</strong></span>
  <span class="drv-sticky-sep">&bull;</span>
  <span style="color:#94a3b8;font-size:12px;white-space:nowrap;">Updated daily</span>
  <a href="/users" class="drv-sticky-cta">Free Alerts &rarr;</a>
</div>

<!-- ── NAV ───────────────────────────────────────────────────────────────── -->
<nav class="nav">
  <div class="nav-inner">
    <a href="/" class="logo">
      <img src="/static/logo.png" alt="EnergyRiskIQ" style="height:28px">
      <span>EnergyRiskIQ</span>
    </a>
    <div style="display:flex;align-items:center;gap:1.5rem;">
      <a href="/indices/global-energy-risk-index" style="font-size:13px;color:#94a3b8;text-decoration:none;">GERI</a>
      <a href="/indices/europe-energy-risk-index" style="font-size:13px;color:#94a3b8;text-decoration:none;">EERI</a>
      <a href="/data/energy-risk-snapshot" style="font-size:13px;color:#94a3b8;text-decoration:none;">Snapshot</a>
      <a href="/research/global-energy-risk-timeline" style="font-size:13px;color:#94a3b8;text-decoration:none;">Timeline</a>
      <a href="/users" class="cta-btn-nav">Unlock Deeper Intelligence</a>
    </div>
  </div>
</nav>

<!-- ══ SECTION 1: HERO ════════════════════════════════════════════════════ -->
<header class="hero">
  <div class="hero-date">
    &#128337; Updated {today_str} &nbsp;&bull;&nbsp; Data-backed analysis &nbsp;&bull;&nbsp; Powered by EnergyRiskIQ
  </div>
  <h1>What Drives LNG Prices?</h1>
  <p class="hero-sub" style="max-width:680px;margin:0 auto 28px;">
    Learn what affects LNG prices worldwide &mdash; from supply disruptions and weather to geopolitics,
    shipping, storage, and energy market risk signals. The definitive resource for understanding the global LNG market.
  </p>
  <div style="display:flex;justify-content:center;gap:12px;flex-wrap:wrap;margin-bottom:24px;">
    <a href="/users" class="cta-btn" style="background:linear-gradient(135deg,{LNG_COLOR},#b8880f);color:#0f172a;font-weight:800;">
      &#128276; Track LNG prices &amp; market risks live &rarr; Free Account
    </a>
    <a href="/data/jkm-lng-price-chart" style="padding:11px 22px;border-radius:8px;
      background:rgba(212,160,23,0.08);border:1px solid rgba(212,160,23,0.3);
      color:{LNG_COLOR};font-size:14px;font-weight:700;text-decoration:none;">
      View JKM LNG Price Chart &rarr;
    </a>
  </div>
  <!-- Index trust badges -->
  <div style="display:flex;justify-content:center;gap:10px;flex-wrap:wrap;">
    <a href="/indices/global-energy-risk-index"
      style="font-size:12px;font-weight:600;color:{gc};border:1px solid {gc}33;border-radius:20px;padding:4px 14px;text-decoration:none;">
      GERI {geri_val}/100 &bull; {geri_band}
    </a>
    <a href="/indices/europe-energy-risk-index"
      style="font-size:12px;font-weight:600;color:{ec};border:1px solid {ec}33;border-radius:20px;padding:4px 14px;text-decoration:none;">
      EERI {eeri_val}/100 &bull; {eeri_band}
    </a>
    <span style="font-size:12px;font-weight:600;color:#94a3b8;border:1px solid #334155;border-radius:20px;padding:4px 14px;">
      JKM ${jkm_price:.2f}/MMBtu &bull; {j_arrow} {jkm_chg_pct:+.1f}%
    </span>
    <span style="font-size:12px;font-weight:600;color:#94a3b8;border:1px solid #334155;border-radius:20px;padding:4px 14px;">
      EU Storage {storage_pct:.1f}% &bull; {storage_status.title()}
    </span>
  </div>
</header>

<main class="page-body">

<!-- ══ SECTION 2: QUICK ANSWER — FEATURED SNIPPET TARGET ══════════════════ -->
<div class="drv-snippet">
  <div class="drv-snippet-label">&#9889; Quick Answer &mdash; What Drives LNG Prices?</div>
  <p class="drv-snippet-body">
    <strong>LNG prices are driven by seven primary factors:</strong> global supply and demand balances,
    weather conditions (cold winters, hot summers), European and Asian gas storage levels,
    shipping constraints and freight costs, geopolitical risks affecting supply routes,
    oil price linkages through long-term contracts, and the competition between
    <strong>Asia (JKM)</strong> and <strong>Europe (TTF)</strong> for flexible LNG cargoes.
    Key benchmarks &mdash; the Japan Korea Marker (JKM) and TTF gas &mdash; anchor regional
    LNG price discovery globally.
  </p>
  <div class="drv-snippet-tags">
    <a href="/data/jkm-lng-price-chart" class="drv-snippet-tag">JKM LNG</a>
    <a href="/data/ttf-gas-price-today" class="drv-snippet-tag">TTF Gas</a>
    <a href="/gas-storage-levels-in-europe" class="drv-snippet-tag">Gas Storage</a>
    <a href="/indices/global-energy-risk-index" class="drv-snippet-tag">Geopolitical Risk</a>
    <a href="/data/brent-crude-oil-price-today" class="drv-snippet-tag">Oil Linkage</a>
    <span class="drv-snippet-tag">Shipping</span>
    <span class="drv-snippet-tag">Seasonal Demand</span>
  </div>
</div>

<!-- ══ SECTION 3: HOW THE LNG MARKET WORKS ═══════════════════════════════ -->
<div class="section-label" style="margin-bottom:20px;">&#127758; How the Global LNG Market Works</div>
<h2 style="font-size:22px;font-weight:700;color:#e2e8f0;margin-bottom:16px;">How the Global LNG Market Works</h2>
<p class="drv-section-lead">
  Liquefied Natural Gas (LNG) is natural gas cooled to &minus;162&deg;C until it becomes a liquid,
  reducing its volume by a factor of 600. This enables natural gas to be transported by sea in
  specially-designed cryogenic tankers &mdash; making gas a globally traded commodity and unlocking
  price linkages between markets that were previously separate.
</p>

<!-- LNG Flow Visual -->
<div class="drv-flow">
  <div class="drv-flow-node">
    <div class="drv-flow-icon">&#9981;</div>
    <div class="drv-flow-label">Gas Field</div>
    <div class="drv-flow-sublabel">Upstream Production</div>
  </div>
  <div class="drv-flow-arrow">&#8594;</div>
  <div class="drv-flow-node">
    <div class="drv-flow-icon">&#127981;</div>
    <div class="drv-flow-label">Liquefaction</div>
    <div class="drv-flow-sublabel">Export Terminal</div>
  </div>
  <div class="drv-flow-arrow">&#8594;</div>
  <div class="drv-flow-node">
    <div class="drv-flow-icon">&#9875;</div>
    <div class="drv-flow-label">LNG Tanker</div>
    <div class="drv-flow-sublabel">15&ndash;25 day voyage</div>
  </div>
  <div class="drv-flow-arrow">&#8594;</div>
  <div class="drv-flow-node">
    <div class="drv-flow-icon">&#127963;</div>
    <div class="drv-flow-label">Import Terminal</div>
    <div class="drv-flow-sublabel">Regasification</div>
  </div>
  <div class="drv-flow-arrow">&#8594;</div>
  <div class="drv-flow-node">
    <div class="drv-flow-icon">&#127970;</div>
    <div class="drv-flow-label">End User</div>
    <div class="drv-flow-sublabel">Power &bull; Heat &bull; Industry</div>
  </div>
</div>

<div style="background:var(--card);border:1px solid var(--border);border-radius:14px;padding:24px 28px;margin-bottom:40px;">
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;">
    <div>
      <div style="font-size:12px;font-weight:700;color:{LNG_COLOR};text-transform:uppercase;letter-spacing:0.08em;margin-bottom:10px;">Spot vs Long-Term Contracts</div>
      <p style="font-size:14px;color:#94a3b8;line-height:1.75;margin:0;">
        LNG is sold under two mechanisms: <strong style="color:#e2e8f0;">long-term contracts</strong>
        (15–25 years, often oil-indexed, at ~13.5% of Brent) and the
        <strong style="color:#e2e8f0;">spot market</strong> (priced at JKM for Asia, TTF for Europe).
        Spot LNG has grown from 10% to nearly 40% of global trade — and spot prices set the
        marginal price signal that influences even long-term contracts.
      </p>
    </div>
    <div>
      <div style="font-size:12px;font-weight:700;color:{LNG_COLOR};text-transform:uppercase;letter-spacing:0.08em;margin-bottom:10px;">Key Price Benchmarks</div>
      <p style="font-size:14px;color:#94a3b8;line-height:1.75;margin:0;">
        <strong style="color:#e2e8f0;"><a href="/data/jkm-lng-price-chart" style="color:{LNG_COLOR};">JKM</a>
        (Japan Korea Marker)</strong>: Asia's primary LNG spot benchmark. Currently
        <strong style="color:#e2e8f0;">${jkm_price:.2f}/MMBtu</strong>.
        <strong style="color:#e2e8f0;"><a href="/data/ttf-gas-price-today" style="color:#60a5fa;">TTF</a>
        (Title Transfer Facility)</strong>: Europe's dominant gas benchmark. Currently
        <strong style="color:#e2e8f0;">&euro;{ttf_price:.2f}/MWh</strong>.
        The spread between them drives global cargo routing.
      </p>
    </div>
  </div>
</div>

<!-- ══ SECTION 4: THE 7 MAIN LNG PRICE DRIVERS ═══════════════════════════ -->
<div class="section-label" style="margin-bottom:20px;">&#128293; The 7 Factors That Drive LNG Prices</div>
<h2 style="font-size:22px;font-weight:700;color:#e2e8f0;margin-bottom:20px;">
  The Main Factors That Drive LNG Prices
</h2>
<p class="drv-section-lead">
  Understanding what drives LNG prices requires tracking seven interconnected forces. EnergyRiskIQ
  monitors all seven in real time — the live data below reflects today&rsquo;s market conditions.
</p>

<div class="drv-driver-wrap">

  <!-- Driver 1 -->
  <div class="drv-driver">
    <div class="drv-driver-num-wrap">
      <div class="drv-driver-icon">&#127777;</div>
      <div class="drv-driver-num">01</div>
    </div>
    <div>
      <h3>&#127777; Weather &amp; Seasonal Demand</h3>
      <div class="drv-driver-body">
        <p>Weather is the single most acute short-term driver of LNG price volatility.
        <strong>Cold winters</strong> in Japan, Korea, and China drive emergency LNG procurement that
        sends spot prices sharply higher. <strong>Hot summers</strong> in China and Korea boost
        air-conditioning demand, adding a second seasonal price peak (typically July&ndash;August).
        The 2021 winter demand surge and the 2022 European energy crisis both had significant
        weather components.</p>
        <p>Winter LNG demand in Japan and Korea is relatively predictable but its magnitude varies
        significantly year to year. Chinese demand is the swing factor &mdash; when China enters
        the spot market aggressively during cold weather, the impact on JKM is immediate.
        European weather increasingly matters as Europe has become a major LNG consumer.
        Cold Northern European winters now compete directly with Asia for LNG cargoes.</p>
        <div class="drv-live-pill" style="background:rgba(96,165,250,0.1);border:1px solid rgba(96,165,250,0.2);color:#60a5fa;">
          &#9798; EU Storage: {storage_pct:.1f}% ({storage_status.title()}, {storage_vs} {storage_norm:.0f}% norm)
        </div>
        <a href="/gas-storage-levels-in-europe" class="drv-driver-link">
          View Europe gas storage levels &rarr;
        </a>
      </div>
    </div>
  </div>

  <!-- Driver 2 -->
  <div class="drv-driver">
    <div class="drv-driver-num-wrap">
      <div class="drv-driver-icon">&#127981;</div>
      <div class="drv-driver-num">02</div>
    </div>
    <div>
      <h3>&#127981; Global LNG Supply &amp; Export Capacity</h3>
      <div class="drv-driver-body">
        <p>LNG supply is inelastic in the short term &mdash; you can&rsquo;t build a new export
        terminal in months. Global LNG liquefaction capacity is dominated by
        <strong>Qatar</strong> (~80 mtpa, the world&rsquo;s largest single exporter),
        <strong>Australia</strong> (~80 mtpa across multiple projects),
        <strong>US Gulf Coast</strong> (~120 mtpa of operational and approved capacity), and
        <strong>Russia</strong> (Yamal LNG, Sakhalin, now subject to sanctions risk).
        When a major export facility experiences an unplanned outage &mdash; as happened with
        Freeport LNG in 2022 (8 months offline) &mdash; spot prices spike globally.</p>
        <p>New LNG supply capacity coming online between 2025&ndash;2028 from the US and Qatar
        is expected to significantly increase global LNG availability, which is a structural
        bearish pressure on LNG prices in the medium term. However, demand growth from
        South and Southeast Asia (India, Pakistan, Bangladesh, Vietnam) is absorbing new supply.</p>
        <div class="drv-live-pill" style="background:rgba(212,160,23,0.08);border:1px solid rgba(212,160,23,0.2);color:{LNG_COLOR};">
          &#9875; JKM Spot: ${jkm_price:.2f}/MMBtu &nbsp;{j_arrow} {jkm_chg_pct:+.1f}%
        </div>
        <a href="/data/jkm-lng-price-chart" class="drv-driver-link">
          View JKM LNG price chart &rarr;
        </a>
      </div>
    </div>
  </div>

  <!-- Driver 3 -->
  <div class="drv-driver">
    <div class="drv-driver-num-wrap">
      <div class="drv-driver-icon">&#9875;</div>
      <div class="drv-driver-num">03</div>
    </div>
    <div>
      <h3>&#9875; LNG Shipping &amp; Freight Rates</h3>
      <div class="drv-driver-body">
        <p>Shipping economics are the hidden driver of LNG arbitrage. A typical US Gulf Coast
        to Asia voyage costs approximately <strong>$1.50&ndash;$2.50/MMBtu</strong> in freight,
        taking 15&ndash;25 days. This freight cost sets the minimum JKM-TTF spread required
        for Atlantic-to-Pacific cargo redirection to be economically viable. When the spread
        is below freight costs, cargoes stay in the Atlantic basin (Europe); when above, they
        divert to Asia.</p>
        <p><strong>Canal constraints</strong> are particularly impactful.
        Panama Canal draught restrictions (driven by La Ni&ntilde;a drought conditions) add 15&ndash;20
        days to US-to-Asia routes via Cape Horn, significantly increasing effective freight costs.
        <strong>Red Sea disruptions</strong> (Houthi attacks since late 2023) have rerouted
        Middle East and European LNG flows around the Cape of Good Hope, adding cost and voyage time.
        These constraints effectively tighten global LNG supply, supporting prices.</p>
        <div class="drv-live-pill" style="background:rgba(248,113,19,0.08);border:1px solid rgba(248,113,19,0.2);color:#f97316;">
          &#128307; EGSI-S (Shipping Stress): {egsi_s_val:.1f} &bull; {egsi_s_band}
        </div>
      </div>
    </div>
  </div>

  <!-- Driver 4 -->
  <div class="drv-driver">
    <div class="drv-driver-num-wrap">
      <div class="drv-driver-icon">&#9888;</div>
      <div class="drv-driver-num">04</div>
    </div>
    <div>
      <h3>&#9888; Geopolitical Risk &amp; Energy Security</h3>
      <div class="drv-driver-body">
        <p>Geopolitical events are the most unpredictable and violent LNG price driver.
        The <strong>Russia&ndash;Ukraine war</strong> (February 2022) eliminated approximately
        150 bcm/year of Russian pipeline gas supply to Europe, triggering an emergency
        European LNG import surge that sent TTF to record levels and pulled JKM sharply higher
        as Europe competed with Asia for every available cargo.
        <strong>Middle East conflicts</strong> threaten Strait of Hormuz transits, through which
        approximately 20% of global LNG passes from Qatar and UAE export terminals.</p>
        <p>EnergyRiskIQ&rsquo;s <a href="/indices/global-energy-risk-index"><strong>GERI (Global Energy Risk Index)</strong></a>
        quantifies geopolitical and supply-chain risk across 100+ countries, providing an
        early-warning signal for LNG price stress. GERI is currently at
        <strong style="color:{gc};">{geri_val}/100 ({geri_band})</strong> &mdash; reflecting {geri_risk_desc}
        in global energy supply corridors today.</p>
        <div class="drv-live-pill" style="background:{gc}18;border:1px solid {gc}33;color:{gc};">
          &#9889; GERI Today: {geri_val}/100 &bull; {geri_band} &nbsp;{_sign(geri_delta)}{geri_delta}pt
        </div>
        <a href="/indices/global-energy-risk-index" class="drv-driver-link">
          View Global Energy Risk Index &rarr;
        </a>
      </div>
    </div>
  </div>

  <!-- Driver 5 -->
  <div class="drv-driver">
    <div class="drv-driver-num-wrap">
      <div class="drv-driver-icon">&#128137;</div>
      <div class="drv-driver-num">05</div>
    </div>
    <div>
      <h3>&#128137; Oil Prices &amp; Energy Substitution</h3>
      <div class="drv-driver-body">
        <p>A significant share of LNG is sold under long-term contracts indexed to crude oil &mdash;
        typically at <strong>13&ndash;15% of Brent crude price per barrel</strong>.
        With Brent at <strong>${brent_price:.2f}/bbl</strong> today, the oil-indexed LNG formula
        reference is approximately <strong>${oil_linked:.2f}/MMBtu</strong>.
        When JKM spot trades significantly above this level, buyers seek more spot supply and
        push back on oil-indexation in new contracts. When below, it signals LNG spot oversupply.</p>
        <p>Oil prices also drive <strong>fuel switching</strong>. When oil-based fuels (diesel, fuel oil)
        are expensive relative to LNG, industrial and power buyers substitute towards gas, increasing
        LNG demand. Conversely, when oil is cheap, LNG demand softens in dual-fuel applications.
        Brent is currently {_arrow(brent_chg)} <strong>${brent_price:.2f}/bbl</strong>
        ({brent_chg:+.2f} day-on-day).</p>
        <div class="drv-live-pill" style="background:rgba(249,115,22,0.08);border:1px solid rgba(249,115,22,0.2);color:#f97316;">
          &#128137; Brent: ${brent_price:.2f}/bbl &nbsp;{b_arrow} {brent_chg:+.2f} &bull; Oil-linked ref: ${oil_linked:.2f}/MMBtu
        </div>
        <a href="/data/brent-crude-oil-price-today" class="drv-driver-link">
          View Brent crude oil price today &rarr;
        </a>
      </div>
    </div>
  </div>

  <!-- Driver 6 -->
  <div class="drv-driver">
    <div class="drv-driver-num-wrap">
      <div class="drv-driver-icon">&#127482;&#127466;</div>
      <div class="drv-driver-num">06</div>
    </div>
    <div>
      <h3>&#127482;&#127466; Europe vs Asia &mdash; TTF vs JKM Cargo Competition</h3>
      <div class="drv-driver-body">
        <p>The single most transformative structural change in LNG markets since 2022 is the
        permanent entry of Europe as a major LNG spot buyer. Before 2022, European gas was
        largely supplied by Russian pipelines; since the war, Europe has pivoted to LNG,
        importing 120+ bcm/year equivalent and competing directly with Asia for every flexible cargo.</p>
        <p>The <strong>JKM-TTF arbitrage spread</strong> determines where flexible LNG cargoes
        (primarily from the US Gulf Coast) are directed. Today&rsquo;s spread of approximately
        <strong>${jkm_ttf_spread:.2f}/MMBtu</strong> ({arb_dir}).
        EU gas storage at <strong>{storage_pct:.1f}%</strong> sets the urgency of European LNG demand
        &mdash; when storage is low, European buyers bid aggressively, diverting cargoes from Asia
        and lifting both TTF and JKM simultaneously.
        EERI at <strong style="color:{ec};">{eeri_val}/100 ({eeri_band})</strong> reflects current European supply stress.</p>
        <div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:10px;">
          <div class="drv-live-pill" style="background:rgba(212,160,23,0.08);border:1px solid rgba(212,160,23,0.2);color:{LNG_COLOR};">
            &#9875; JKM: ${jkm_price:.2f}/MMBtu
          </div>
          <div class="drv-live-pill" style="background:rgba(96,165,250,0.08);border:1px solid rgba(96,165,250,0.2);color:#60a5fa;">
            &#127470;&#127489; TTF: &euro;{ttf_price:.2f}/MWh
          </div>
          <div class="drv-live-pill" style="background:rgba(255,255,255,0.04);border:1px solid #334155;color:#94a3b8;">
            Spread: ${jkm_ttf_spread:.2f}/MMBtu
          </div>
        </div>
        <div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:6px;">
          <a href="/data/jkm-lng-price-chart" class="drv-driver-link">JKM LNG Price Chart &rarr;</a>
          <a href="/data/ttf-gas-price-today" class="drv-driver-link" style="margin-left:16px;">TTF Gas Price Today &rarr;</a>
        </div>
      </div>
    </div>
  </div>

  <!-- Driver 7 -->
  <div class="drv-driver">
    <div class="drv-driver-num-wrap">
      <div class="drv-driver-icon">&#128201;</div>
      <div class="drv-driver-num">07</div>
    </div>
    <div>
      <h3>&#128201; Gas Storage Levels &amp; Supply Security</h3>
      <div class="drv-driver-body">
        <p><strong>Gas storage levels</strong> are the primary buffer between supply disruption and
        energy crisis. Europe&rsquo;s gas storage fills up between April and October (injection
        season) and draws down October to March (withdrawal season). EU regulations require
        storage to be at least 90% full by November 1 each year.
        When storage is below target, European buyers must procure LNG aggressively, competing
        with Asian buyers and lifting global LNG prices. When storage is full, European LNG
        demand softens and JKM can trade at a discount to TTF.</p>
        <p>Today, EU gas storage stands at <strong>{storage_pct:.1f}%</strong> &mdash; {storage_vs}
        the {storage_norm:.1f}% seasonal norm by {abs(storage_dev):.1f} percentage points.
        This {storage_implication}.
        Panic buying events &mdash; as seen in Q3 2022 &mdash; can push LNG prices to extreme
        levels when storage is critically low and winter approach accelerates procurement urgency.</p>
        <div class="drv-live-pill" style="background:rgba(96,165,250,0.08);border:1px solid rgba(96,165,250,0.2);color:#60a5fa;">
          &#128201; EU Storage: {storage_pct:.1f}% &bull; {storage_status.title()} &bull; {storage_vs} norm by {abs(storage_dev):.1f}pp
        </div>
        <a href="/gas-storage-levels-in-europe" class="drv-driver-link">
          View Europe gas storage levels &rarr;
        </a>
      </div>
    </div>
  </div>

</div>

<!-- ══ SECTION 5: LIVE MARKET CONTEXT ════════════════════════════════════ -->
<div class="section-label" style="margin-bottom:20px;">&#128200; LNG Market Indicators to Watch</div>
<h2 style="font-size:22px;font-weight:700;color:#e2e8f0;margin-bottom:16px;">
  LNG Market Indicators to Watch
</h2>
<p class="drv-section-lead">
  These five live indicators provide the essential cross-market context for understanding
  current LNG price drivers. EnergyRiskIQ updates all indicators daily.
</p>

<div class="drv-mkt-grid">
  <a href="/data/jkm-lng-price-chart" style="text-decoration:none;">
    <div class="drv-mkt-card">
      <div class="drv-mkt-label">&#9875; JKM LNG</div>
      <div class="drv-mkt-value" style="color:{LNG_COLOR};">${jkm_price:.2f}</div>
      <div class="drv-mkt-chg" style="color:{j_color};">{j_arrow} {jkm_chg:+.2f} ({jkm_chg_pct:+.1f}%)</div>
      <div class="drv-mkt-note">$/MMBtu &bull; Asia benchmark</div>
    </div>
  </a>
  <a href="/data/ttf-gas-price-today" style="text-decoration:none;">
    <div class="drv-mkt-card">
      <div class="drv-mkt-label">&#127470;&#127489; TTF Gas</div>
      <div class="drv-mkt-value" style="color:#60a5fa;">&euro;{ttf_price:.2f}</div>
      <div class="drv-mkt-chg" style="color:{t_color};">{t_arrow} {ttf_chg:+.2f}</div>
      <div class="drv-mkt-note">&euro;/MWh &bull; Europe benchmark</div>
    </div>
  </a>
  <a href="/data/brent-crude-oil-price-today" style="text-decoration:none;">
    <div class="drv-mkt-card">
      <div class="drv-mkt-label">&#128137; Brent Crude</div>
      <div class="drv-mkt-value" style="color:#f97316;">${brent_price:.2f}</div>
      <div class="drv-mkt-chg" style="color:{b_color};">{b_arrow} {brent_chg:+.2f}</div>
      <div class="drv-mkt-note">$/bbl &bull; Oil-indexed ref</div>
    </div>
  </a>
  <a href="/gas-storage-levels-in-europe" style="text-decoration:none;">
    <div class="drv-mkt-card">
      <div class="drv-mkt-label">&#128201; EU Storage</div>
      <div class="drv-mkt-value" style="color:{'#22c55e' if storage_pct > 55 else ('#f97316' if storage_pct > 35 else '#ef4444')};">{storage_pct:.1f}%</div>
      <div class="drv-mkt-chg" style="color:{'#ef4444' if storage_dev < 0 else '#22c55e'};">{storage_vs} norm {abs(storage_dev):.1f}pp</div>
      <div class="drv-mkt-note">Seasonal fill rate</div>
    </div>
  </a>
  <div class="drv-mkt-card">
    <div class="drv-mkt-label">&#128200; VIX</div>
    <div class="drv-mkt-value" style="color:#94a3b8;">{vix_close:.1f}</div>
    <div class="drv-mkt-chg" style="color:{v_color};">{v_arrow} {vix_chg:+.2f}</div>
    <div class="drv-mkt-note">{vix_desc.title()}</div>
  </div>
</div>

<div style="margin-bottom:28px;text-align:center;">
  <a href="/data/energy-risk-snapshot" style="font-size:13px;font-weight:700;color:{LNG_COLOR};
    border:1px solid rgba(212,160,23,0.3);border-radius:8px;padding:9px 22px;
    text-decoration:none;display:inline-block;">
    &#128200; Explore live market dashboards &rarr;
  </a>
</div>

<!-- JKM-TTF spread context strip -->
<div style="background:var(--card);border:1px solid var(--border);border-radius:12px;
  padding:20px 24px;margin-bottom:40px;">
  <div style="font-size:10px;font-weight:700;color:#64748b;letter-spacing:1.2px;text-transform:uppercase;margin-bottom:14px;">
    JKM-TTF Arbitrage Signal &mdash; Updated {today_str}
  </div>
  <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:14px;">
    <div>
      <div style="font-size:11px;color:#94a3b8;margin-bottom:4px;">Spread ($/MMBtu equivalent)</div>
      <div style="font-size:22px;font-weight:800;color:#e2e8f0;">${jkm_ttf_spread:.2f}</div>
      <div style="font-size:11px;color:#64748b;">{arb_dir.split('—')[0].strip()}</div>
    </div>
    <div>
      <div style="font-size:11px;color:#94a3b8;margin-bottom:4px;">Cargo Direction Signal</div>
      <div style="font-size:13px;font-weight:700;color:{'#d4a017' if jkm_ttf_spread > 0 else '#60a5fa'};">
        {'&#9875; Asia-bound cargoes preferred' if jkm_ttf_spread > 0 else '&#127482;&#127466; Europe-bound cargoes preferred'}
      </div>
      <div style="font-size:11px;color:#64748b;">Based on spread vs typical freight of $1.50&ndash;2.50/MMBtu</div>
    </div>
    <div>
      <div style="font-size:11px;color:#94a3b8;margin-bottom:4px;">Oil-Indexed LNG Reference</div>
      <div style="font-size:22px;font-weight:800;color:#e2e8f0;">${oil_linked:.2f}</div>
      <div style="font-size:11px;color:#64748b;">13.5% &times; Brent ${brent_price:.2f}/bbl</div>
    </div>
  </div>
</div>

<!-- ══ SECTION 6: ENERGY RISK INTELLIGENCE ════════════════════════════════ -->
<div class="section-label" style="margin-bottom:20px;">&#9888; How Energy Risk Signals Affect LNG Prices</div>
<h2 style="font-size:22px;font-weight:700;color:#e2e8f0;margin-bottom:16px;">
  How Energy Risk Signals Affect LNG Prices
</h2>
<p class="drv-section-lead">
  EnergyRiskIQ&rsquo;s proprietary risk indices quantify the geopolitical, supply, and market stress
  factors that drive LNG price moves before they appear in market data. These indices are
  built on 100+ real-time signals and updated daily.
</p>

<div class="drv-risk-grid">
  <a href="/indices/global-energy-risk-index" class="drv-risk-card">
    <div class="drv-risk-name">Global Energy Risk Index</div>
    <div class="drv-risk-val" style="color:{gc};">{geri_val}</div>
    <div class="drv-risk-band" style="color:{gc};">{geri_band}</div>
    <div class="drv-risk-desc">GERI &bull; {_sign(geri_delta)}{geri_delta}pt vs yesterday &bull; 0&ndash;100 scale</div>
  </a>
  <a href="/indices/europe-energy-risk-index" class="drv-risk-card">
    <div class="drv-risk-name">European Energy Risk Index</div>
    <div class="drv-risk-val" style="color:{ec};">{eeri_val}</div>
    <div class="drv-risk-band" style="color:{ec};">{eeri_band}</div>
    <div class="drv-risk-desc">EERI &bull; {_sign(eeri_delta)}{eeri_delta}pt vs yesterday &bull; Europe focus</div>
  </a>
  <a href="/indices/europe-gas-stress-index" class="drv-risk-card">
    <div class="drv-risk-name">Geopolitical Stress (Market)</div>
    <div class="drv-risk-val" style="color:{mgc};font-size:28px;">{egsi_m_val:.1f}</div>
    <div class="drv-risk-band" style="color:{mgc};">{egsi_m_band}</div>
    <div class="drv-risk-desc">EGSI-M &bull; market stress signal</div>
  </a>
  <a href="/indices/europe-gas-stress-index" class="drv-risk-card">
    <div class="drv-risk-name">Shipping &amp; Supply Stress</div>
    <div class="drv-risk-val" style="color:{sgc};font-size:28px;">{egsi_s_val:.1f}</div>
    <div class="drv-risk-band" style="color:{sgc};">{egsi_s_band}</div>
    <div class="drv-risk-desc">EGSI-S &bull; LNG shipping lanes</div>
  </a>
</div>

<div class="drv-risk-interp">
  <p>
    <strong>How escalation affects LNG:</strong> When GERI rises above 60 (ELEVATED), geopolitical
    stress historically correlates with LNG price premium of 8&ndash;15% above fundamentals as buyers
    pay for supply security insurance. GERI above 80 (SEVERE/CRITICAL) has coincided with the most
    violent LNG price spikes &mdash; 2022 saw GERI reach CRITICAL while JKM peaked above $56/MMBtu.
    Current GERI at <strong style="color:{gc};">{geri_val}/100 ({geri_band})</strong> reflects
    {geri_risk_desc} &mdash; {'monitoring remains active for escalation signals' if geri_val < 50 else 'supply chain stress is actively pricing into LNG markets'}.
  </p>
  <p>
    <strong>EERI and European LNG demand:</strong> EERI at <strong style="color:{ec};">{eeri_val}/100 ({eeri_band})</strong>
    signals the intensity of European energy supply risk. Higher EERI values indicate Europe is
    more likely to enter the spot LNG market aggressively, competing with Asian buyers and
    creating a floor under JKM prices globally.
  </p>
  <div style="margin-top:16px;display:flex;gap:12px;flex-wrap:wrap;">
    <a href="/users" style="font-size:13px;font-weight:700;color:{LNG_COLOR};
      border:1px solid rgba(212,160,23,0.3);border-radius:8px;padding:8px 20px;
      text-decoration:none;display:inline-block;">
      &#128275; Access full energy risk dashboard &rarr; Free account
    </a>
    <a href="/data/energy-risk-snapshot" style="font-size:13px;font-weight:700;color:#94a3b8;
      border:1px solid #334155;border-radius:8px;padding:8px 20px;
      text-decoration:none;display:inline-block;">
      View live risk snapshot &rarr;
    </a>
  </div>
</div>

<!-- ══ SECTION 7: HISTORICAL LNG PRICE SHOCKS ════════════════════════════ -->
<div class="section-label" style="margin-bottom:20px;">&#128199; Major LNG Price Shocks in History</div>
<h2 style="font-size:22px;font-weight:700;color:#e2e8f0;margin-bottom:20px;">
  Major LNG Price Shocks in History
</h2>
<p class="drv-section-lead">
  Understanding what drives LNG prices is best illustrated by examining historic price shocks &mdash;
  each episode reveals how the seven drivers interact to create extreme market conditions.
</p>

<div class="drv-timeline">

  <div class="drv-tl-item">
    <div class="drv-tl-dot-wrap">
      <div class="drv-tl-dot"></div>
      <div class="drv-tl-year">2021</div>
    </div>
    <div class="drv-tl-card">
      <div class="drv-tl-event">&#127774; Asian Winter + Post-COVID Demand Surge</div>
      <div class="drv-tl-desc">
        As global economies reopened post-COVID, Asian LNG demand surged simultaneously with
        a colder-than-average winter across Northeast Asia. Chinese industrial activity drove
        unprecedented spot buying. JKM, which had traded below $5/MMBtu during COVID,
        exploded higher through 2021, setting the stage for the 2022 crisis.
      </div>
      <span class="drv-tl-price">JKM: $5 &rarr; $35/MMBtu (2021)</span>
    </div>
  </div>

  <div class="drv-tl-item">
    <div class="drv-tl-dot-wrap">
      <div class="drv-tl-dot"></div>
      <div class="drv-tl-year">2021–22</div>
    </div>
    <div class="drv-tl-card">
      <div class="drv-tl-event">&#128293; The Global Energy Crisis &mdash; JKM All-Time High</div>
      <div class="drv-tl-desc">
        Winter 2021&ndash;22 saw all seven LNG price drivers activate simultaneously: extreme cold,
        pre-war Russian gas supply restrictions to Europe, low EU storage, shipping bottlenecks,
        and soaring Asian demand. JKM hit its all-time high of <strong>$56.33/MMBtu</strong>
        in October 2021. Europe paid record prices to fill storage, outbidding Asian buyers.
        This episode established Europe as a permanent LNG competitor to Asia.
      </div>
      <span class="drv-tl-price">JKM All-Time High: $56.33/MMBtu &bull; Oct 2021</span>
    </div>
  </div>

  <div class="drv-tl-item">
    <div class="drv-tl-dot-wrap">
      <div class="drv-tl-dot"></div>
      <div class="drv-tl-year">2022</div>
    </div>
    <div class="drv-tl-card">
      <div class="drv-tl-event">&#9889; Russia-Ukraine War &mdash; Pipeline Gas Eliminated</div>
      <div class="drv-tl-desc">
        Russia&rsquo;s invasion of Ukraine (February 2022) triggered the most significant structural
        shift in global gas markets since the 1970s oil crisis. Europe lost access to ~150 bcm/year
        of Russian pipeline gas over 2022&ndash;2023, accelerating a massive LNG import buildout.
        European TTF traded above &euro;300/MWh at peak, and European LNG demand permanently
        increased by 60+ bcm/year, reshaping global LNG trade flows forever.
      </div>
      <span class="drv-tl-price">TTF: &euro;343/MWh peak &bull; Aug 2022</span>
    </div>
  </div>

  <div class="drv-tl-item">
    <div class="drv-tl-dot-wrap">
      <div class="drv-tl-dot"></div>
      <div class="drv-tl-year">2022</div>
    </div>
    <div class="drv-tl-card">
      <div class="drv-tl-event">&#127981; Freeport LNG Outage &mdash; US Export Disruption</div>
      <div class="drv-tl-desc">
        In June 2022, the Freeport LNG terminal (Texas, ~15 mtpa capacity) suffered an explosion
        and fire, taking it offline for 8 months. As Europe was desperately trying to replace
        Russian gas, losing 20% of US LNG export capacity was a major supply shock.
        The outage demonstrates how a single facility failure can move global LNG prices.
      </div>
      <span class="drv-tl-price">Removed ~15 mtpa from market for 8 months</span>
    </div>
  </div>

  <div class="drv-tl-item">
    <div class="drv-tl-dot-wrap">
      <div class="drv-tl-dot"></div>
      <div class="drv-tl-year">2023–24</div>
    </div>
    <div class="drv-tl-card">
      <div class="drv-tl-event">&#9875; Red Sea Crisis &mdash; Shipping Lane Disruption</div>
      <div class="drv-tl-desc">
        Houthi attacks on commercial shipping in the Red Sea (from late 2023) forced LNG tankers
        to reroute around the Cape of Good Hope, adding 10&ndash;15 days to voyages between
        Europe and Middle East export terminals. This increased effective shipping costs and
        tightened the functional supply of LNG available for European import, providing
        price support through 2024 and demonstrating how shipping constraints alone
        can sustain LNG price premiums.
      </div>
      <span class="drv-tl-price">Added $0.30&ndash;0.80/MMBtu freight premium</span>
    </div>
  </div>

  <div class="drv-tl-item">
    <div class="drv-tl-dot-wrap">
      <div class="drv-tl-dot"></div>
      <div class="drv-tl-year">2024–25</div>
    </div>
    <div class="drv-tl-card">
      <div class="drv-tl-event">&#128201; European Storage Depletion &mdash; Injection Season Pressure</div>
      <div class="drv-tl-desc">
        As European gas storage entered 2025 below long-run seasonal averages following a
        cold Q1 2025 withdrawal season, European LNG imports had to accelerate sharply to
        meet November 1 storage targets. EU storage at <strong>{storage_pct:.1f}%</strong>
        today ({storage_vs} the {storage_norm:.1f}% seasonal norm) reflects the ongoing
        supply-demand dynamics that continue to shape JKM-TTF arbitrage flows.
      </div>
      <a href="/gas-storage-levels-in-europe" style="display:inline-block;margin-top:8px;font-size:12px;color:{LNG_COLOR};text-decoration:none;">
        View current EU gas storage levels &rarr;
      </a>
    </div>
  </div>

</div>

<div style="text-align:center;margin-bottom:40px;">
  <a href="/research/global-energy-risk-timeline"
    style="font-size:13px;font-weight:700;color:{LNG_COLOR};
    border:1px solid rgba(212,160,23,0.3);border-radius:8px;padding:9px 22px;
    text-decoration:none;display:inline-block;">
    &#128337; View full Global Energy Risk Timeline &rarr;
  </a>
</div>

<!-- ══ SECTION 8: TODAY'S LNG MARKET INSIGHT ══════════════════════════════ -->
<div class="section-label" style="margin-bottom:20px;">&#129504; Today&rsquo;s LNG Market Insight</div>
<div class="drv-insight-card">
  <h2 style="font-size:20px;font-weight:700;color:#e2e8f0;margin-bottom:20px;">
    Today&rsquo;s LNG Market Insight
  </h2>
  <div class="drv-insight-section">
    <div class="drv-insight-section-title">Current LNG Market Environment</div>
    <div class="drv-insight-body">{_html.escape(insight['environment'])}</div>
  </div>
  <div class="drv-insight-section">
    <div class="drv-insight-section-title">Market Stress Indicators</div>
    <div class="drv-insight-body">{_html.escape(insight['stress'])}</div>
  </div>
  <div class="drv-insight-section">
    <div class="drv-insight-section-title">Key Watchpoints</div>
    <div class="drv-insight-body">{_html.escape(insight['watchpoints'])}</div>
  </div>
  <div style="margin-top:20px;font-size:11px;color:#64748b;">
    Analysis generated by EnergyRiskIQ&rsquo;s proprietary LNG intelligence pipeline (Custom Algorithms)
    &bull; {today_str} &bull; Not financial advice &bull; Updated daily
  </div>
</div>

<!-- Newsletter capture -->
<div class="drv-newsletter">
  <div class="drv-newsletter-text">
    <div class="drv-newsletter-title">&#128276; Get daily LNG market insights</div>
    <div class="drv-newsletter-sub">Daily JKM alerts, spread signals, GERI risk levels, and market interpretation — free account.</div>
  </div>
  <a href="/users" class="drv-newsletter-cta">Get Daily Alerts &rarr;</a>
</div>

<!-- ══ SECTION 9: CONVERSION BLOCK ════════════════════════════════════════ -->
<div class="drv-cta-card">
  <div class="drv-cta-label">Daily LNG Market Intelligence</div>
  <h2 class="drv-cta-h2">Stay Ahead of LNG Market Risks</h2>
  <p class="drv-cta-sub">
    EnergyRiskIQ tracks every driver of LNG prices daily &mdash; from JKM and TTF spot prices
    to geopolitical risk signals, shipping constraints, and gas storage trends.
    Get actionable intelligence before price moves happen.
  </p>
  <div class="drv-cta-benefits">
    <span class="drv-cta-benefit">JKM LNG daily price alerts</span>
    <span class="drv-cta-benefit">JKM-TTF spread monitoring</span>
    <span class="drv-cta-benefit">GERI &amp; EERI geopolitical signals</span>
    <span class="drv-cta-benefit">EU storage daily updates</span>
    <span class="drv-cta-benefit">Shipping &amp; freight signals</span>
    <span class="drv-cta-benefit">Daily market insight briefing</span>
  </div>
  <a href="/users" class="drv-cta-btn">&#128275; Create Free Account</a>
  <div class="drv-cta-credits">No credit card required &bull; Free plan always available</div>
</div>

<!-- ══ SECTION 10: FAQ ════════════════════════════════════════════════════ -->
<div class="section-label" style="margin-bottom:20px;">&#128218; LNG Market FAQs</div>
<h2 style="font-size:22px;font-weight:700;color:#e2e8f0;margin-bottom:20px;">
  LNG Market &mdash; Frequently Asked Questions
</h2>
{faq_html}
<div style="margin-bottom:40px;"></div>

<!-- ══ SECTION 11: INTERNAL LINK HUB ════════════════════════════════════ -->
<div class="drv-hub">
  <h3 style="font-size:15px;font-weight:700;color:#e2e8f0;margin-bottom:20px;">&#128279; LNG Research &amp; Data Hub</h3>
  <div class="drv-hub-section">
    <div class="drv-hub-title">&#128201; LNG &amp; Gas Data</div>
    <div class="drv-hub-grid">
      <a href="/data/jkm-lng-price-chart" class="drv-hub-pill">&#9875; JKM LNG Price Chart</a>
      <a href="/data/europe-lng-supply-demand" class="drv-hub-pill">&#128168; Europe LNG Supply-Demand</a>
      <a href="/data/ttf-gas-price-today" class="drv-hub-pill">&#127470;&#127489; TTF Gas Price Today</a>
      <a href="/gas-storage-levels-in-europe" class="drv-hub-pill">&#128201; Europe Gas Storage</a>
    </div>
  </div>
  <div class="drv-hub-section">
    <div class="drv-hub-title">&#128137; Oil &amp; Cross-Market Data</div>
    <div class="drv-hub-grid">
      <a href="/data/brent-crude-oil-price-today" class="drv-hub-pill">&#128137; Brent Crude Price Today</a>
      <a href="/data/energy-risk-snapshot" class="drv-hub-pill">&#128248; Energy Risk Snapshot</a>
      <a href="/data/global-energy-risk-forecast" class="drv-hub-pill">&#127760; Global Energy Forecast</a>
    </div>
  </div>
  <div class="drv-hub-section">
    <div class="drv-hub-title">&#128200; Risk Indices</div>
    <div class="drv-hub-grid">
      <a href="/indices/global-energy-risk-index" class="drv-hub-pill">&#127760; Global Energy Risk Index (GERI)</a>
      <a href="/indices/europe-energy-risk-index" class="drv-hub-pill">&#127482;&#127466; Europe Energy Risk Index (EERI)</a>
      <a href="/indices/europe-gas-stress-index" class="drv-hub-pill">&#9889; Europe Gas Stress Index (EGSI)</a>
    </div>
  </div>
  <div class="drv-hub-section">
    <div class="drv-hub-title">&#128218; Research</div>
    <div class="drv-hub-grid">
      <a href="/research/global-energy-risk-timeline" class="drv-hub-pill">&#128337; Global Energy Risk Timeline</a>
      <a href="/research/global-energy-risk-index" class="drv-hub-pill">&#128202; GERI Research &amp; Methodology</a>
      <a href="/research/europe-energy-risk-index" class="drv-hub-pill">&#128202; EERI Research</a>
    </div>
  </div>
  <div class="drv-hub-section">
    <div class="drv-hub-title">&#128221; License</div>
    <div class="drv-hub-grid">
      <a href="/data-license" class="drv-hub-pill">&#128221; Data License &amp; Usage Terms</a>
    </div>
  </div>
</div>

<!-- ══ CITATION & REFERENCE ══════════════════════════════════════════════ -->
<div class="drv-cite-card">
  <div style="font-size:14px;font-weight:700;color:#e2e8f0;margin-bottom:12px;">
    &#128221; Citation &amp; Attribution
  </div>
  <div style="font-size:13px;color:#94a3b8;margin-bottom:14px;">
    When referencing this research page in reports, journalism, or academic work,
    please cite as follows. All data is subject to the
    <a href="/data-license" style="color:{LNG_COLOR};">EnergyRiskIQ Data License</a>.
  </div>
  <pre class="drv-cite-pre">EnergyRiskIQ. <em>"What Drives LNG Prices? Understanding the Global LNG Market."</em>
EnergyRiskIQ Research, <em>{today_str}</em>.
<a href="{BASE_URL}/research/what-drives-lng-prices">{BASE_URL}/research/what-drives-lng-prices</a>

Data sources: OilPriceAPI (JKM, Brent, TTF), AGSI+ (EU gas storage),
Yahoo Finance (VIX), EnergyRiskIQ proprietary risk pipeline (GERI, EERI, EGSI).
License: <a href="{BASE_URL}/data-license">{BASE_URL}/data-license</a>
</pre>
</div>

</main>

<script>
(function() {{
  document.addEventListener('copy', function(e) {{
    var sel = window.getSelection ? window.getSelection().toString() : '';
    if (sel.length > 30) {{
      var attr = '\\n\\n[Source: EnergyRiskIQ.com — What Drives LNG Prices | {BASE_URL}/research/what-drives-lng-prices]';
      e.clipboardData.setData('text/plain', sel + attr);
      e.preventDefault();
    }}
  }});
}})();
</script>
"""


# ─────────────────────────────────────────────────────────────────────────────
# Route
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/research/what-drives-lng-prices")
async def what_drives_lng_prices():
    """Research authority page: What Drives LNG Prices?"""

    async def _stream():
        yield _DRIVERS_LOADER
        try:
            data = await asyncio.get_event_loop().run_in_executor(None, _fetch_drivers_data)
            body = await asyncio.get_event_loop().run_in_executor(None, _build_drivers_html, data)
            yield body
        except Exception as exc:
            logger.error(f"LNG drivers page error: {exc}", exc_info=True)
            yield (
                "<script>"
                "var l=document.getElementById('snap-loader');"
                "if(l){l.innerHTML='<p style=\"color:#ef4444;text-align:center;padding:2rem;\">"
                "Data temporarily unavailable. Please try again.</p>';}"
                "</script>"
            )

    return StreamingResponse(_stream(), media_type="text/html")
