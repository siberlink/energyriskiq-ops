"""
European Gas Storage Levels — Live Data & Risk Intelligence
Route: /gas-storage-levels-in-europe
SEO-optimized informational page showing live EU gas storage data, trends,
seasonal comparison, EGSI correlation, and AI intelligence for energy market professionals.
"""
import os
import math
import json
import logging
import asyncio
import html as _html
from datetime import datetime, timezone, date as _date, timedelta

from fastapi import APIRouter
from fastapi.responses import StreamingResponse, Response

from src.db.db import execute_production_one, execute_production_query
from src.api.snapshot_routes import _PAGE_CSS, _LOADER_HTML, BAND_COLORS, _safe_float

router = APIRouter()
logger = logging.getLogger(__name__)

BASE_URL = "https://energyriskiq.com"

# ── Band colours ──────────────────────────────────────────────────────────────

_RISK_BAND_COLORS = {
    "CRITICAL":  "#ef4444",
    "HIGH":      "#f97316",
    "ELEVATED":  "#eab308",
    "MODERATE":  "#3b82f6",
    "LOW":       "#22c55e",
    "NORMAL":    "#22c55e",
}

def _band_color(band: str) -> str:
    return _RISK_BAND_COLORS.get((band or "").upper(), "#94a3b8")

def _sign(v):
    return "+" if v >= 0 else ""

def _arrow(v):
    return "&#9650;" if v >= 0 else "&#9660;"

def _chg_color(v):
    return "#22c55e" if v >= 0 else "#ef4444"

def _fmt_month(d) -> str:
    try:
        return d.strftime("%b")
    except Exception:
        return str(d)

def _fmt_date_short(d) -> str:
    try:
        return d.strftime("%-d %b")
    except Exception:
        return str(d)


# ── SVG Chart Builders ────────────────────────────────────────────────────────

def _build_storage_trend_svg(history_rows, width=700, height=200):
    """
    Build a dual-line SVG: actual storage fill rate vs seasonal norm.
    history_rows: list of dicts with keys date, eu_storage_percent, seasonal_norm, risk_band
    """
    if not history_rows or len(history_rows) < 2:
        return ""

    W, H = width, height
    PAD_L, PAD_R, PAD_T, PAD_B = 44, 16, 16, 40

    cw = W - PAD_L - PAD_R
    ch = H - PAD_T - PAD_B

    actuals = [float(r["eu_storage_percent"] or 0) for r in history_rows]
    norms = [float(r["seasonal_norm"] or 0) for r in history_rows]
    all_vals = actuals + norms
    vmin = max(0, min(all_vals) * 0.96)
    vmax = min(100, max(all_vals) * 1.04)
    rng = vmax - vmin or 1

    n = len(history_rows)

    def px(i, v):
        x = PAD_L + (i / (n - 1)) * cw
        y = PAD_T + ch - ((v - vmin) / rng) * ch
        return x, y

    # Build actual line path
    actual_pts = [px(i, v) for i, v in enumerate(actuals)]
    norm_pts = [px(i, v) for i, v in enumerate(norms)]

    def pts_to_path(pts):
        path = f"M {pts[0][0]:.1f} {pts[0][1]:.1f}"
        for p in pts[1:]:
            path += f" L {p[0]:.1f} {p[1]:.1f}"
        return path

    # Fill area under actual line
    fill_path = pts_to_path(actual_pts)
    fill_path += f" L {actual_pts[-1][0]:.1f} {PAD_T + ch:.1f}"
    fill_path += f" L {actual_pts[0][0]:.1f} {PAD_T + ch:.1f} Z"

    # Y-axis labels
    y_ticks = [vmin, (vmin + vmax) / 2, vmax]
    y_labels = ""
    for yv in y_ticks:
        _, y = px(0, yv)
        y_labels += (
            f'<line x1="{PAD_L}" y1="{y:.1f}" x2="{W - PAD_R}" y2="{y:.1f}" '
            f'stroke="rgba(255,255,255,0.05)" stroke-width="1"/>'
            f'<text x="{PAD_L - 4}" y="{y + 4:.1f}" text-anchor="end" font-size="9" '
            f'fill="#475569" font-family="Inter,sans-serif">{yv:.0f}%</text>'
        )

    # X-axis labels (every ~15 data points)
    x_labels = ""
    step = max(1, n // 6)
    for i in range(0, n, step):
        x, _ = px(i, vmin)
        d = history_rows[i].get("date")
        lbl = _fmt_month(d) if d else ""
        x_labels += (
            f'<text x="{x:.1f}" y="{PAD_T + ch + 16}" text-anchor="middle" '
            f'font-size="9" fill="#475569" font-family="Inter,sans-serif">{lbl}</text>'
        )

    # Risk band colouring dots (bands along the actual line)
    dots_svg = ""
    for i, row in enumerate(history_rows):
        band = (row.get("risk_band") or "ELEVATED").upper()
        if band in ("CRITICAL",):
            x, y = px(i, actuals[i])
            dots_svg += (
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.5" '
                f'fill="#ef4444" opacity="0.7"/>'
            )

    return f"""<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg"
  style="width:100%;max-width:{W}px;display:block;overflow:visible">
  {y_labels}
  {x_labels}
  <!-- Fill area -->
  <path d="{fill_path}" fill="rgba(234,179,8,0.08)"/>
  <!-- Seasonal norm dashed line -->
  <path d="{pts_to_path(norm_pts)}" fill="none" stroke="#3b82f6"
    stroke-width="1.5" stroke-dasharray="6 3" opacity="0.6"/>
  <!-- Actual storage line -->
  <path d="{pts_to_path(actual_pts)}" fill="none" stroke="#eab308" stroke-width="2.5"/>
  <!-- Critical dots -->
  {dots_svg}
  <!-- Latest value dot -->
  <circle cx="{actual_pts[-1][0]:.1f}" cy="{actual_pts[-1][1]:.1f}" r="5"
    fill="#eab308" stroke="#0f172a" stroke-width="2"/>
  <!-- Legend -->
  <rect x="{PAD_L}" y="{H - 14}" width="14" height="3" rx="1.5" fill="#eab308"/>
  <text x="{PAD_L + 18}" y="{H - 10}" font-size="9" fill="#94a3b8"
    font-family="Inter,sans-serif">Actual Fill Rate</text>
  <line x1="{PAD_L + 100}" y1="{H - 12}" x2="{PAD_L + 114}" y2="{H - 12}"
    stroke="#3b82f6" stroke-width="1.5" stroke-dasharray="5 2"/>
  <text x="{PAD_L + 118}" y="{H - 10}" font-size="9" fill="#94a3b8"
    font-family="Inter,sans-serif">Seasonal Norm</text>
  <circle cx="{PAD_L + 198}" cy="{H - 12}" r="3" fill="#ef4444" opacity="0.7"/>
  <text x="{PAD_L + 204}" y="{H - 10}" font-size="9" fill="#94a3b8"
    font-family="Inter,sans-serif">Critical risk zone</text>
</svg>"""


def _build_fill_meter_svg(pct: float, norm: float, critical_threshold: float = 20.0, width=480, height=64):
    """Horizontal fill-rate meter comparing current vs norm vs critical."""
    W, H = width, height
    bar_h = 18
    bar_y = 10
    bar_w = W - 80

    # Clamp
    pct = max(0, min(100, pct))
    norm = max(0, min(100, norm))

    actual_w = (pct / 100) * bar_w
    norm_x = (norm / 100) * bar_w
    crit_x = (critical_threshold / 100) * bar_w

    band_color = "#eab308" if pct >= 30 else ("#ef4444" if pct < 25 else "#f97316")

    return f"""<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg"
  style="width:100%;max-width:{W}px;display:block">
  <!-- Background track -->
  <rect x="0" y="{bar_y}" width="{bar_w}" height="{bar_h}" rx="4"
    fill="rgba(255,255,255,0.05)"/>
  <!-- Critical zone hatching -->
  <rect x="0" y="{bar_y}" width="{crit_x:.1f}" height="{bar_h}" rx="4"
    fill="rgba(239,68,68,0.12)"/>
  <!-- Actual fill -->
  <rect x="0" y="{bar_y}" width="{actual_w:.1f}" height="{bar_h}" rx="4"
    fill="{band_color}" opacity="0.85"/>
  <!-- Norm marker -->
  <line x1="{norm_x:.1f}" y1="{bar_y - 4}" x2="{norm_x:.1f}" y2="{bar_y + bar_h + 4}"
    stroke="#3b82f6" stroke-width="2"/>
  <text x="{norm_x:.1f}" y="{bar_y - 7}" text-anchor="middle"
    font-size="9" fill="#3b82f6" font-family="Inter,sans-serif">Norm {norm:.0f}%</text>
  <!-- Value label -->
  <text x="{bar_w + 8}" y="{bar_y + 13}" font-size="13" font-weight="700"
    fill="{band_color}" font-family="Inter,sans-serif">{pct:.1f}%</text>
  <!-- Scale labels -->
  <text x="0" y="{bar_y + bar_h + 14}" font-size="9"
    fill="#475569" font-family="Inter,sans-serif">0%</text>
  <text x="{bar_w / 2:.1f}" y="{bar_y + bar_h + 14}" text-anchor="middle" font-size="9"
    fill="#475569" font-family="Inter,sans-serif">50%</text>
  <text x="{bar_w:.1f}" y="{bar_y + bar_h + 14}" text-anchor="end" font-size="9"
    fill="#475569" font-family="Inter,sans-serif">100%</text>
</svg>"""


# ── AI Interpretation Engine ──────────────────────────────────────────────────

_STORAGE_INTERP_FALLBACK = """European gas storage levels are tracking significantly below seasonal norms, a condition that carries meaningful implications for energy price stability and supply security across the continent. With storage at 30.2% — nearly 15 percentage points below the 5-year average for this time of year — Europe enters the critical spring injection season from a structurally weak starting position.

The refill trajectory over the coming months will be decisive for winter 2026–27 supply adequacy. At current refill speeds of approximately 3,500 GWh/day, the market is observing early positive momentum in the injection season, but this rate must be sustained and ideally accelerated to close the deficit against EU mandated storage targets of 90% by November 1.

The Europe Gas Stress Index (EGSI-M) currently registers a LOW band reading of 3.15/10, indicating that near-term transmission market stress remains contained. However, the EGSI-M is a flow and market stress indicator — it does not directly capture the longer-dated inventory risk embedded in the current storage shortfall. This divergence between low near-term stress and elevated structural storage risk is a key feature of the current European gas market environment.

Traders and risk managers should monitor three key variables: the pace of LNG import volumes through key European terminals, Russian transit flow stability (where applicable), and Nordic hydro reservoir levels, which can substitute for gas in power generation. Any sustained deterioration in these inputs, combined with a delayed injection season, would significantly increase the probability of a storage shortfall entering winter 2026–27 — a scenario likely to drive TTF price volatility substantially higher."""


def _run_storage_ai(
    today_str: str,
    storage_pct: float,
    storage_norm: float,
    storage_dev: float,
    refill_speed: float,
    risk_score: int,
    risk_band: str,
    egsi_val: float,
    egsi_band: str,
    ttf_latest: float,
    withdrawal_rate: float,
    alert_context: str,
) -> str:
    """Generate AI interpretation of current gas storage situation using GPT-4.1-mini."""
    try:
        from openai import OpenAI
        ai_key = os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY")
        ai_url = os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL")
        client = OpenAI(api_key=ai_key, base_url=ai_url) if ai_key and ai_url else OpenAI()

        prompt = f"""You are EnergyRiskIQ's senior European gas market analyst.

Today is {today_str}. You are writing an authoritative intelligence interpretation of current European gas storage conditions for professional energy market participants — traders, risk managers, and analysts.

=== LIVE STORAGE DATA ===
EU Aggregate Gas Storage Fill Rate: {storage_pct:.1f}%
Seasonal Norm (5-year average): {storage_norm:.1f}%
Deviation from Norm: {storage_dev:+.1f} percentage points
7-Day Refill Speed: {refill_speed:,.0f} GWh/day
7-Day Withdrawal Rate: {withdrawal_rate:,.0f} GWh/day
EnergyRiskIQ Storage Risk Score: {risk_score}/100 ({risk_band})
Europe Gas Stress Index (EGSI-M): {egsi_val:.2f}/10 ({egsi_band} band)
TTF Natural Gas Price (latest): €{ttf_latest:.2f}/MWh

=== ALERT CONTEXT (72h) ===
{alert_context}

=== TASK ===
Write a 4-paragraph expert intelligence interpretation (no bullet points, no headers, pure prose paragraphs separated by \\n\\n). Each paragraph must be 3–5 sentences.

Paragraph 1: Current storage situation — context on how far below norm, why this matters structurally for European energy security. Reference specific numbers.
Paragraph 2: Refill season dynamics — what the current injection speed means, what is required to hit EU mandated 90% target by November 1, what risks could disrupt the refill trajectory.
Paragraph 3: EGSI relationship and price implications — how the EGSI-M reading relates to the storage situation, what this means for TTF volatility, forward curve structure, and energy price risk.
Paragraph 4: Intelligence for market professionals — what traders, risk managers, and analysts should be monitoring, key variables that could shift the risk picture, and the forward-looking implication for winter 2026–27.

Write with authority and precision. Reference all key numbers. No markdown. No bullet points. No section labels. Just four expert paragraphs."""

        resp = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.35,
            max_tokens=900,
            timeout=40,
        )
        text = resp.choices[0].message.content.strip()
        if text:
            return text
        return _STORAGE_INTERP_FALLBACK
    except Exception as exc:
        logger.warning(f"Gas storage AI interpretation failed: {exc}")
        return _STORAGE_INTERP_FALLBACK


# ── Loader HTML ───────────────────────────────────────────────────────────────

_GAS_STORAGE_LOADER = _LOADER_HTML.replace(
    "Global Energy Risk Snapshot | EnergyRiskIQ",
    "Europe Gas Storage Levels Today (Updated Daily) | EnergyRiskIQ",
).replace(
    'name="description" content="Live global energy risk snapshot. Current GERI, EERI and EGSI-M index values with Brent crude, TTF gas, VIX and LNG market prices."',
    'name="description" content="Track Europe gas storage levels today with updated daily data, storage percentage, seasonal context, winter risk signals, and European energy market insights from EnergyRiskIQ."',
).replace(
    'rel="canonical" href="https://energyriskiq.com/data/energy-risk-snapshot"',
    'rel="canonical" href="https://energyriskiq.com/gas-storage-levels-in-europe"',
).replace(
    '<link rel="icon" type="image/png" href="/static/favicon.png">',
    '<link rel="icon" type="image/png" href="/static/favicon.png">'
    '\n<meta property="og:title" content="Europe Gas Storage Levels Today (Updated Daily)">'
    '\n<meta property="og:description" content="Daily Europe gas storage data, trends, storage risk context, and winter supply outlook from EnergyRiskIQ.">'
    '\n<meta property="og:url" content="https://energyriskiq.com/gas-storage-levels-in-europe">'
    '\n<meta property="og:type" content="website">'
    '\n<meta name="twitter:card" content="summary_large_image">'
    '\n<meta name="twitter:title" content="Europe Gas Storage Levels Today (Updated Daily)">'
    '\n<meta name="twitter:description" content="Daily Europe gas storage data, trends, storage risk context, and winter supply outlook from EnergyRiskIQ.">',
).replace(
    "Fetching GERI\u00a0&\u00a0EERI indices\u2026",
    "Fetching EU gas storage data\u2026",
).replace(
    '<span class="ld-tag">GERI</span>\n    <span class="ld-tag">EERI</span>\n    <span class="ld-tag">EGSI&#8209;M</span>\n    <span class="ld-tag">Brent</span>\n    <span class="ld-tag">TTF</span>',
    '<span class="ld-tag">AGSI+</span>\n    <span class="ld-tag">EGSI&#8209;M</span>\n    <span class="ld-tag">TTF</span>\n    <span class="ld-tag">Risk Intelligence</span>',
)


# ── Page-specific CSS ─────────────────────────────────────────────────────────

_GAS_STORAGE_CSS = """
.gs-metric-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 40px;
}
@media (max-width: 900px) { .gs-metric-grid { grid-template-columns: 1fr 1fr; } }
@media (max-width: 480px) { .gs-metric-grid { grid-template-columns: 1fr; } }
.gs-metric-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 20px 20px 18px;
  position: relative;
  overflow: hidden;
}
.gs-metric-card::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 3px;
  border-radius: 3px 3px 0 0;
}
.gs-metric-card.gold::before { background: linear-gradient(90deg, #d4a017, transparent); }
.gs-metric-card.blue::before  { background: linear-gradient(90deg, #3b82f6, transparent); }
.gs-metric-card.green::before { background: linear-gradient(90deg, #22c55e, transparent); }
.gs-metric-card.red::before   { background: linear-gradient(90deg, #ef4444, transparent); }
.gs-metric-card.amber::before { background: linear-gradient(90deg, #eab308, transparent); }
.gs-metric-label {
  font-size: 10px; font-weight: 700; letter-spacing: 1.8px;
  text-transform: uppercase; color: var(--muted);
  margin-bottom: 8px;
}
.gs-metric-value {
  font-size: 32px; font-weight: 800; line-height: 1.05;
  font-variant-numeric: tabular-nums;
  margin-bottom: 4px;
}
.gs-metric-sub {
  font-size: 11px; color: var(--muted); line-height: 1.4;
}
.gs-chart-wrap {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 24px 24px 16px;
  margin-bottom: 36px;
}
.gs-chart-title {
  font-size: 12px; font-weight: 700; letter-spacing: 1.4px;
  text-transform: uppercase; color: var(--gold);
  margin-bottom: 16px; display: flex; align-items: center; gap: 8px;
}
.gs-three-col {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
  margin-bottom: 40px;
}
@media (max-width: 800px) { .gs-three-col { grid-template-columns: 1fr; } }
.gs-implication-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 22px 22px 20px;
}
.gs-implication-icon {
  font-size: 1.5rem; margin-bottom: 10px;
}
.gs-implication-title {
  font-size: 13px; font-weight: 700; color: #e2e8f0;
  margin-bottom: 8px;
}
.gs-implication-body {
  font-size: 12px; color: var(--muted); line-height: 1.65;
}
.gs-ai-box {
  background: linear-gradient(135deg, #111827 0%, #0f172a 100%);
  border: 1px solid rgba(212,160,23,0.2);
  border-radius: 16px;
  padding: 30px 36px;
  margin-bottom: 44px;
  position: relative;
  overflow: hidden;
}
.gs-ai-box::before {
  content: '';
  position: absolute; top: 0; left: 0; right: 0; height: 3px;
  background: linear-gradient(90deg, #d4a017, #3b82f6, transparent);
}
.gs-ai-label {
  font-size: 10px; font-weight: 700; letter-spacing: 2px;
  text-transform: uppercase; color: var(--gold);
  margin-bottom: 22px; display: flex; align-items: center; gap: 8px;
}
.gs-ai-label::before { content: '\\25B6'; font-size: 8px; }
.gs-interp-para {
  font-size: 15px; color: #cbd5e1; line-height: 1.85;
  margin-bottom: 1.4em; font-weight: 400;
}
.gs-interp-para:last-child { margin-bottom: 0; }
.gs-interp-para strong { color: #fff; font-weight: 600; }
.gs-audience-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
  margin-bottom: 44px;
}
@media (max-width: 800px) { .gs-audience-grid { grid-template-columns: 1fr; } }
.gs-audience-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 24px 22px;
}
.gs-audience-icon { font-size: 1.6rem; margin-bottom: 10px; }
.gs-audience-role {
  font-size: 12px; font-weight: 700; letter-spacing: 0.08em;
  text-transform: uppercase; color: var(--gold); margin-bottom: 10px;
}
.gs-audience-title {
  font-size: 14px; font-weight: 700; color: #e2e8f0; margin-bottom: 8px;
}
.gs-audience-body {
  font-size: 12px; color: var(--muted); line-height: 1.65;
}
.gs-audience-bullets {
  font-size: 11px; color: var(--muted); line-height: 1.8;
  padding-left: 12px; margin: 8px 0 0;
}
.gs-audience-bullets li { list-style: none; }
.gs-audience-bullets li::before { content: '\\2022 '; color: var(--gold); }
.gs-method-box {
  background: rgba(255,255,255,0.02);
  border: 1px solid rgba(255,255,255,0.06);
  border-radius: 14px;
  padding: 24px 28px;
  margin-bottom: 44px;
}
.gs-method-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 20px;
  margin-top: 20px;
}
@media (max-width: 600px) { .gs-method-grid { grid-template-columns: 1fr; } }
.gs-method-item { font-size: 12px; color: var(--muted); line-height: 1.65; }
.gs-method-item strong { color: #e2e8f0; display: block; margin-bottom: 3px; font-size: 12px; }
.gs-wheel-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
  margin-bottom: 44px;
}
@media (max-width: 600px) { .gs-wheel-grid { grid-template-columns: 1fr 1fr; } }
.gs-wheel-link {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  text-align: center; gap: 8px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 20px 12px;
  text-decoration: none;
  color: inherit;
  transition: border-color 0.2s, box-shadow 0.2s, transform 0.2s;
}
.gs-wheel-link:hover {
  border-color: rgba(212,160,23,0.4);
  box-shadow: 0 0 24px rgba(212,160,23,0.08);
  transform: translateY(-2px);
}
.gs-wheel-icon { font-size: 1.7rem; }
.gs-wheel-label {
  font-size: 11px; font-weight: 700; letter-spacing: 0.08em;
  text-transform: uppercase; color: var(--gold);
}
.gs-wheel-desc { font-size: 11px; color: var(--muted); line-height: 1.4; }
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
.gs-egsi-band-chip {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 11px; font-weight: 700; letter-spacing: 0.06em;
  text-transform: uppercase; padding: 4px 12px;
  border-radius: 20px; border: 1px solid currentColor;
}
.gs-deviation-bar {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 20px 24px;
  margin-bottom: 36px;
}
.gs-risk-season-table {
  width: 100%; border-collapse: collapse;
  font-size: 12px; margin-top: 12px;
}
.gs-risk-season-table th {
  font-size: 10px; font-weight: 700; letter-spacing: 1px;
  text-transform: uppercase; color: var(--muted);
  padding: 6px 12px; text-align: left;
  border-bottom: 1px solid rgba(255,255,255,0.06);
}
.gs-risk-season-table td {
  padding: 8px 12px; border-bottom: 1px solid rgba(255,255,255,0.03);
  color: #cbd5e1;
}
.gs-risk-season-table tr:last-child td { border-bottom: none; }

/* ── Mobile responsive ── */
@media (max-width: 640px) {
  .nav-inner {
    padding: 0 1rem;
  }
  .nav-inner > div a:not(.cta-btn-nav) {
    display: none;
  }
  .snap-cite-card {
    padding: 18px 16px;
    max-width: 100%;
    overflow: hidden;
  }
  .snap-cite-code-wrap {
    overflow-x: auto;
    padding: 14px;
    max-width: 100%;
  }
  .snap-cite-code {
    white-space: pre-wrap !important;
    overflow-wrap: break-word;
    word-break: break-word;
    font-size: 11px;
  }
  .snap-cite-copy-btn {
    position: static !important;
    display: block;
    width: 100%;
    box-sizing: border-box;
    text-align: center;
    margin-top: 12px;
  }
  html, body {
    overflow-x: hidden;
    max-width: 100%;
  }
  .hero {
    padding-left: 16px;
    padding-right: 16px;
  }
}

/* ── Snapshot summary card ── */
.gs-snapshot-card {
  background: linear-gradient(135deg, #0f172a 0%, #1a2540 100%);
  border: 1px solid #334155;
  border-radius: 18px;
  padding: 28px 28px 22px;
  margin-bottom: 40px;
  position: relative;
  overflow: hidden;
}
.gs-snapshot-card::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0; height: 3px;
  background: linear-gradient(90deg, #d4a017, #3b82f6, #22c55e);
}
.gs-snapshot-title {
  font-size: 11px; font-weight: 700; letter-spacing: 1.8px;
  text-transform: uppercase; color: #475569; margin-bottom: 18px;
}
.gs-snapshot-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 12px;
}
@media (max-width: 800px) { .gs-snapshot-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 480px) { .gs-snapshot-grid { grid-template-columns: 1fr; } }
.gs-snap-item { display: flex; flex-direction: column; gap: 4px; }
.gs-snap-label { font-size: 10px; font-weight: 600; letter-spacing: 1.2px; text-transform: uppercase; color: #475569; }
.gs-snap-value { font-size: 22px; font-weight: 800; line-height: 1.1; }
.gs-snap-sub { font-size: 11px; color: #475569; }
.gs-snapshot-footer { font-size: 11px; color: #334155; border-top: 1px solid #1e293b; margin-top: 14px; padding-top: 12px; }

/* ── FREE Widget promo banner ── */
.gs-widget-banner {
  display: flex; align-items: center; justify-content: space-between; gap: 24px;
  background: linear-gradient(135deg, #15110a 0%, #1c1608 45%, #0f172a 100%);
  border: 1px solid rgba(212,160,23,0.35);
  border-radius: 16px;
  padding: 22px 26px;
  margin-bottom: 32px;
  position: relative;
  overflow: hidden;
}
.gs-widget-banner::before {
  content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px;
  background: linear-gradient(90deg, #d4a017, #f59e0b);
}
.gs-widget-banner-glow {
  position: absolute; top: -40%; right: -10%; width: 320px; height: 320px;
  background: radial-gradient(circle, rgba(212,160,23,0.16) 0%, transparent 70%);
  pointer-events: none;
}
.gs-widget-banner-text { position: relative; z-index: 1; flex: 1 1 auto; min-width: 0; }
.gs-widget-banner-tag {
  display: inline-block; font-size: 10px; font-weight: 800; letter-spacing: 1.4px;
  text-transform: uppercase; color: #0a0f1e;
  background: linear-gradient(135deg, #d4a017, #f59e0b);
  padding: 3px 10px; border-radius: 20px; margin-bottom: 10px;
}
.gs-widget-banner-title { font-size: 19px; font-weight: 800; color: #f8fafc; line-height: 1.3; margin: 0 0 6px; }
.gs-widget-banner-title span { color: #d4a017; }
.gs-widget-banner-desc { font-size: 13.5px; color: #94a3b8; line-height: 1.6; margin: 0; max-width: 620px; }
.gs-widget-banner-desc strong { color: #cbd5e1; font-weight: 700; }
.gs-widget-banner-cta {
  position: relative; z-index: 1; flex: 0 0 auto;
  display: inline-flex; align-items: center; gap: 8px;
  background: linear-gradient(135deg, #d4a017, #f59e0b); color: #0a0f1e !important;
  text-decoration: none; font-weight: 800; font-size: 14px; white-space: nowrap;
  padding: 13px 24px; border-radius: 10px;
  box-shadow: 0 6px 22px rgba(212,160,23,0.22);
  transition: transform .15s ease, box-shadow .15s ease;
}
.gs-widget-banner-cta:hover { transform: translateY(-2px); box-shadow: 0 10px 28px rgba(212,160,23,0.32); }
@media (max-width: 720px) {
  .gs-widget-banner { flex-direction: column; align-items: flex-start; gap: 16px; padding: 20px; }
  .gs-widget-banner-cta { width: 100%; justify-content: center; }
}

/* ── What This Means section ── */
.gs-wtm-section {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 28px 28px 24px;
  margin-bottom: 44px;
}
.gs-wtm-section h2 {
  font-size: 18px; font-weight: 700; color: #f1f5f9; margin-bottom: 16px;
}
.gs-wtm-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-top: 18px;
}
@media (max-width: 700px) { .gs-wtm-grid { grid-template-columns: 1fr; } }
.gs-wtm-point {
  background: #0f172a;
  border: 1px solid #1e293b;
  border-radius: 12px;
  padding: 16px 18px;
}
.gs-wtm-point h3 { font-size: 13px; font-weight: 700; color: #e2e8f0; margin-bottom: 6px; }
.gs-wtm-point p { font-size: 13px; color: #94a3b8; line-height: 1.7; margin: 0; }

/* ── CTA Blocks ── */
.gs-cta-mid {
  background: linear-gradient(135deg, #0c1832 0%, #141f35 100%);
  border: 1px solid rgba(59,130,246,0.25);
  border-radius: 18px;
  padding: 36px 32px;
  margin-bottom: 44px;
  text-align: center;
}
.gs-cta-mid h2 { font-size: 20px; font-weight: 800; color: #f1f5f9; margin-bottom: 10px; }
.gs-cta-mid p { font-size: 14px; color: #94a3b8; line-height: 1.7; max-width: 520px; margin: 0 auto 24px; }
.gs-cta-btn-primary {
  display: inline-block;
  background: linear-gradient(135deg, #3b82f6, #6366f1);
  color: #fff; font-weight: 700; font-size: 14px;
  padding: 13px 32px; border-radius: 10px;
  text-decoration: none; transition: opacity 0.2s;
}
.gs-cta-btn-primary:hover { opacity: 0.88; }

.gs-cta-bottom {
  background: linear-gradient(135deg, #0b1520 0%, #0f1e2e 100%);
  border: 1px solid rgba(212,160,23,0.2);
  border-radius: 18px;
  padding: 36px 32px;
  margin-bottom: 44px;
  text-align: center;
}
.gs-cta-bottom h2 { font-size: 20px; font-weight: 800; color: #f1f5f9; margin-bottom: 10px; }
.gs-cta-bottom p { font-size: 14px; color: #94a3b8; line-height: 1.7; max-width: 520px; margin: 0 auto 24px; }
.gs-cta-btn-gold {
  display: inline-block;
  background: #d4a017; color: #0a0f1e; font-weight: 700; font-size: 14px;
  padding: 13px 32px; border-radius: 10px;
  text-decoration: none; transition: opacity 0.2s;
}
.gs-cta-btn-gold:hover { opacity: 0.88; }

/* ── Internal links grid ── */
.gs-related-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin-bottom: 44px;
}
@media (max-width: 800px) { .gs-related-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 480px) { .gs-related-grid { grid-template-columns: 1fr; } }
.gs-related-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 16px 18px;
  text-decoration: none;
  display: flex; flex-direction: column; gap: 4px;
  transition: border-color 0.18s, background 0.18s;
}
.gs-related-card:hover { border-color: rgba(59,130,246,0.4); background: #1e293b; }
.gs-related-card-tag { font-size: 10px; font-weight: 700; letter-spacing: 1.4px; text-transform: uppercase; color: #3b82f6; }
.gs-related-card-title { font-size: 14px; font-weight: 600; color: #e2e8f0; line-height: 1.3; }
.gs-related-card-desc { font-size: 12px; color: #475569; }

/* ── FAQ section ── */
.gs-faq-section { margin-bottom: 44px; }
.gs-faq-item {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 14px;
  margin-bottom: 10px;
  overflow: hidden;
}
.gs-faq-q {
  display: flex; justify-content: space-between; align-items: center;
  padding: 18px 22px; cursor: pointer;
  font-size: 14px; font-weight: 600; color: #e2e8f0;
  gap: 12px;
}
.gs-faq-q:hover { color: #f1f5f9; }
.gs-faq-toggle {
  font-size: 18px; color: #475569; flex-shrink: 0;
  transition: transform 0.22s; user-select: none;
}
.gs-faq-item.open .gs-faq-toggle { transform: rotate(45deg); color: #3b82f6; }
.gs-faq-a {
  display: none;
  padding: 0 22px 18px;
  font-size: 13px; color: #94a3b8; line-height: 1.8;
  border-top: 1px solid #1e293b; padding-top: 14px;
}
.gs-faq-item.open .gs-faq-a { display: block; }
"""


# ── Data Fetcher ──────────────────────────────────────────────────────────────

def _fetch_gas_storage_data() -> dict:
    """Fetch all data needed for the gas storage page from production DB."""

    # Storage — latest row
    storage_row = execute_production_one(
        "SELECT date, eu_storage_percent, seasonal_norm, deviation_from_norm, "
        "refill_speed_7d, withdrawal_rate_7d, winter_deviation_risk, "
        "risk_score, risk_band "
        "FROM gas_storage_snapshots ORDER BY date DESC LIMIT 1"
    )

    # Storage history — last 90 days for trend chart
    storage_history = execute_production_query(
        "SELECT date, eu_storage_percent, seasonal_norm, deviation_from_norm, "
        "refill_speed_7d, risk_score, risk_band "
        "FROM gas_storage_snapshots ORDER BY date ASC LIMIT 90"
    ) or []

    # EGSI-M latest
    egsi_row = execute_production_one(
        "SELECT index_date, index_value, band, trend_7d "
        "FROM egsi_m_daily WHERE region='Europe' ORDER BY index_date DESC LIMIT 1"
    )

    # GERI latest
    geri_row = execute_production_one(
        "SELECT date, value, band FROM intel_indices_daily "
        "WHERE index_id='global:geo_energy_risk' ORDER BY date DESC LIMIT 1"
    )

    # EERI latest
    eeri_row = execute_production_one(
        "SELECT date, value, band FROM reri_indices_daily "
        "WHERE index_id='europe:eeri' ORDER BY date DESC LIMIT 1"
    )

    # TTF latest 2 rows for price and change
    ttf_rows = execute_production_query(
        "SELECT date, ttf_price FROM ttf_gas_snapshots ORDER BY date DESC LIMIT 2"
    ) or []

    # Alert context for AI
    alert_cats = execute_production_query(
        "SELECT category, COUNT(*) as cnt FROM alert_events "
        "WHERE created_at >= NOW() - INTERVAL '72 hours' "
        "GROUP BY category ORDER BY cnt DESC LIMIT 8"
    ) or []
    alert_context = (
        "Alert categories (last 72h): " + ", ".join(
            f"{r['category']}={r['cnt']}" for r in alert_cats
        )
        if alert_cats else "No recent alerts available."
    )

    return {
        "storage_row": storage_row,
        "storage_history": storage_history,
        "egsi_row": egsi_row,
        "geri_row": geri_row,
        "eeri_row": eeri_row,
        "ttf_rows": ttf_rows,
        "alert_context": alert_context,
    }


# ── HTML Builder ──────────────────────────────────────────────────────────────

def _build_gas_storage_html(data: dict, ai_interp: str, today_str: str) -> str:

    storage_row = data["storage_row"] or {}
    storage_history = data["storage_history"]
    egsi_row = data["egsi_row"] or {}
    geri_row = data["geri_row"] or {}
    eeri_row = data["eeri_row"] or {}
    ttf_rows = data["ttf_rows"]

    # ── Values ──────────────────────────────────────────────────────────────
    storage_pct   = _safe_float(storage_row.get("eu_storage_percent", 30.2))
    storage_norm  = _safe_float(storage_row.get("seasonal_norm", 45.0))
    storage_dev   = _safe_float(storage_row.get("deviation_from_norm", -14.8))
    refill_speed  = _safe_float(storage_row.get("refill_speed_7d", 0))
    withdraw_rate = _safe_float(storage_row.get("withdrawal_rate_7d", 0))
    winter_risk   = storage_row.get("winter_deviation_risk", "LOW")
    risk_score    = int(storage_row.get("risk_score") or 57)
    risk_band     = (storage_row.get("risk_band") or "ELEVATED").upper()
    storage_date  = storage_row.get("date", "")

    # Daily change from last 2 history rows
    daily_change  = 0.0
    if storage_history and len(storage_history) >= 2:
        daily_change = (
            _safe_float(storage_history[-1].get("eu_storage_percent", 0))
            - _safe_float(storage_history[-2].get("eu_storage_percent", 0))
        )
    daily_chg_str = f"{_sign(daily_change)}{daily_change:.2f}pp"
    daily_chg_col = _chg_color(daily_change)

    # Distance to 90% target
    gap_to_target_str = f"{max(0, 90.0 - storage_pct):.1f}pp to reach 90%"

    # Last updated display
    last_updated_str = str(storage_date) if storage_date else "Updating…"

    # Pre-computed strings for f-string expressions (no backslash/quote nesting)
    wtm_position_msg = (
        "This above-average position improves Europe's winter supply buffer."
        if storage_dev >= 0
        else "This below-average position increases pressure on the injection season to recover the deficit."
    )
    wtm_above_below   = "above" if storage_dev >= 0 else "below"
    wtm_pos_neg       = "positive" if storage_dev >= 0 else "concerning"
    wtm_dev_color     = "#22c55e" if storage_dev >= 0 else "#ef4444"

    egsi_val  = round(_safe_float(egsi_row.get("index_value", 0)), 2)
    egsi_band = (egsi_row.get("band") or "LOW").upper()
    egsi_trend= _safe_float(egsi_row.get("trend_7d", 0))
    egsi_date = egsi_row.get("index_date", "")

    geri_val  = int(round(_safe_float(geri_row.get("value", 0))))
    geri_band = (geri_row.get("band") or "MODERATE").upper()

    eeri_val  = int(round(_safe_float(eeri_row.get("value", 0))))
    eeri_band = (eeri_row.get("band") or "ELEVATED").upper()

    ttf_latest = _safe_float(ttf_rows[0]["ttf_price"]) if ttf_rows else 0.0
    ttf_prev   = _safe_float(ttf_rows[1]["ttf_price"]) if len(ttf_rows) > 1 else ttf_latest
    ttf_chg    = ttf_latest - ttf_prev
    ttf_chg_pct = (ttf_chg / ttf_prev * 100) if ttf_prev else 0.0

    # ── Derived values ───────────────────────────────────────────────────────
    rb_color    = _band_color(risk_band)
    egsi_color  = _band_color(egsi_band)
    geri_color  = BAND_COLORS.get(geri_band, "#f97316")
    eeri_color  = BAND_COLORS.get(eeri_band, "#ef4444")

    # Days to 90% target (simplified)
    target_pct = 90.0
    gap_to_target = target_pct - storage_pct
    days_to_nov1 = (
        _date(2026, 11, 1) - (_date.today())
    ).days
    required_daily_gwh_str = "—"
    if refill_speed > 0 and days_to_nov1 > 0:
        # Approximate total capacity ~1100 TWh → 1 pp ≈ 11 TWh
        capacity_twh = 1100.0
        gap_twh = (gap_to_target / 100) * capacity_twh * 1000  # in GWh
        required_daily = gap_twh / days_to_nov1
        required_daily_gwh_str = f"{required_daily:,.0f} GWh/day"

    # Is refill season? April–September = yes
    is_refill = _date.today().month in range(4, 10)
    season_label = "Injection Season" if is_refill else "Withdrawal Season"

    # Deficit vs norm in TWh
    capacity_gwh = 1_100_000  # ~1,100 TWh EU capacity
    deficit_gwh = abs(storage_dev) / 100 * capacity_gwh

    # ── SVG charts ───────────────────────────────────────────────────────────
    trend_svg  = _build_storage_trend_svg(storage_history, width=680, height=200)
    meter_svg  = _build_fill_meter_svg(storage_pct, storage_norm)

    # ── AI interpretation paragraphs ─────────────────────────────────────────
    paras = [p.strip() for p in ai_interp.split("\n\n") if p.strip()]
    if not paras:
        paras = [ai_interp.strip()]
    interp_html = "".join(
        f'<p class="gs-interp-para">{_html.escape(p)}</p>' for p in paras
    )

    # ── TTF change display ───────────────────────────────────────────────────
    ttf_arrow = _arrow(ttf_chg)
    ttf_color = _chg_color(ttf_chg)

    # ── JSON-LD structured data ──────────────────────────────────────────────
    today_iso = str(_date.today())
    faq_entries = [
        {
            "q": "What are Europe gas storage levels?",
            "a": "Europe gas storage levels show how full underground natural gas storage facilities are across European countries. They are used to assess winter supply security, injection progress, and potential pressure on gas markets.",
        },
        {
            "q": "Why is the 90% gas storage target important?",
            "a": "The European Union requires member states to aim for high storage levels before winter. The 90% target by November 1 is widely watched because it indicates whether Europe has enough stored gas entering the peak heating season.",
        },
        {
            "q": "How often is this page updated?",
            "a": "This page is updated daily when new storage data is available.",
        },
        {
            "q": "Do gas storage levels affect TTF gas prices?",
            "a": "Yes. Lower-than-expected storage levels can increase concern about winter supply and may support higher TTF gas prices, especially when combined with cold weather, LNG disruptions, or geopolitical risk.",
        },
        {
            "q": "Are high storage levels enough to remove winter risk?",
            "a": "Not always. Storage is only one part of the European gas-risk picture. Weather, LNG imports, pipeline flows, demand, price volatility, and geopolitical events can still affect market stress.",
        },
        {
            "q": "What is the difference between gas storage data and the Europe Gas Stress Index?",
            "a": "Gas storage data shows physical inventory levels. The Europe Gas Stress Index combines storage, market pressure, supply stress, transit risk, and policy signals into a broader risk indicator.",
        },
    ]
    json_ld = json.dumps({
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "WebPage",
                "name": "Europe Gas Storage Levels Today (Updated Daily)",
                "headline": "Europe Gas Storage Levels Today (Updated Daily)",
                "description": (
                    "Track Europe gas storage levels today with updated daily data, storage percentage, "
                    "seasonal context, winter risk signals, and European energy market insights from EnergyRiskIQ."
                ),
                "url": f"{BASE_URL}/gas-storage-levels-in-europe",
                "dateModified": today_iso,
                "datePublished": "2025-01-01",
                "publisher": {
                    "@type": "Organization",
                    "name": "EnergyRiskIQ",
                    "url": BASE_URL,
                    "logo": {"@type": "ImageObject", "url": f"{BASE_URL}/static/logo.png"},
                },
                "mainEntityOfPage": {"@type": "WebPage", "@id": f"{BASE_URL}/gas-storage-levels-in-europe"},
                "about": [
                    {"@type": "Thing", "name": "Europe gas storage levels"},
                    {"@type": "Thing", "name": "EU gas storage"},
                    {"@type": "Thing", "name": "natural gas storage"},
                    {"@type": "Thing", "name": "TTF gas price"},
                    {"@type": "Thing", "name": "LNG supply"},
                    {"@type": "Thing", "name": "winter energy risk"},
                ],
            },
            {
                "@type": "Dataset",
                "name": "Europe Gas Storage Levels Dataset",
                "description": "Daily European gas storage level data and risk context used to monitor storage progress, seasonal supply security, and European gas-market stress.",
                "url": f"{BASE_URL}/gas-storage-levels-in-europe",
                "creator":   {"@type": "Organization", "name": "EnergyRiskIQ", "url": BASE_URL},
                "publisher": {"@type": "Organization", "name": "EnergyRiskIQ", "url": BASE_URL},
                "license": f"{BASE_URL}/data-license",
                "isAccessibleForFree": True,
                "dateModified": today_iso,
                "distribution": {
                    "@type": "DataDownload",
                    "contentUrl": f"{BASE_URL}/gas-storage-levels-in-europe",
                    "encodingFormat": "text/html",
                },
                "temporalCoverage": "2026-01-14/..",
                "spatialCoverage": "Europe",
                "variableMeasured": [
                    {"@type": "PropertyValue", "name": "EU gas storage fill rate", "unitText": "percent"},
                    {"@type": "PropertyValue", "name": "Deviation from seasonal norm", "unitText": "percentage points"},
                    {"@type": "PropertyValue", "name": "7-day refill speed", "unitText": "GWh/day"},
                    {"@type": "PropertyValue", "name": "Storage Risk Score", "unitText": "0-100 index"},
                ],
                "measurementTechnique": "Daily aggregation of AGSI+ GIE EU storage data combined with EnergyRiskIQ proprietary risk scoring model.",
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Home", "item": BASE_URL},
                    {"@type": "ListItem", "position": 2, "name": "Data", "item": f"{BASE_URL}/data"},
                    {"@type": "ListItem", "position": 3, "name": "Europe Gas Storage Levels",
                     "item": f"{BASE_URL}/gas-storage-levels-in-europe"},
                ],
            },
            {
                "@type": "FAQPage",
                "mainEntity": [
                    {
                        "@type": "Question",
                        "name": e["q"],
                        "acceptedAnswer": {"@type": "Answer", "text": e["a"]},
                    }
                    for e in faq_entries
                ],
            },
        ],
    }, indent=2)

    # ── Risk season reference table ──────────────────────────────────────────
    season_rows = [
        ("Winter (Nov–Feb)",  "Withdrawal", "50–65%",  "ELEVATED–CRITICAL"),
        ("Spring (Mar–May)",  "Mixed",       "30–50%",  "ELEVATED"),
        ("Summer (Jun–Aug)",  "Injection",   "50–80%",  "MODERATE–LOW"),
        ("Autumn (Sep–Oct)",  "Target",       "80–90%+", "LOW"),
    ]
    season_table_html = ""
    for season, phase, typical_range, risk_range in season_rows:
        season_table_html += f"""<tr>
          <td>{season}</td>
          <td>{phase}</td>
          <td style="font-variant-numeric:tabular-nums;">{typical_range}</td>
          <td>{risk_range}</td>
        </tr>"""

    # ── Page HTML ────────────────────────────────────────────────────────────
    return f"""<script>
var l=document.getElementById('snap-loader');
if(l){{l.style.display='none';}}
document.body.style.overflow='';
</script>
<style>
{_GAS_STORAGE_CSS}
</style>

<script type="application/ld+json">
{json_ld}
</script>

<!-- NAV -->
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
      <a href="/data/global-energy-risk-forecast" style="font-size:13px;color:#94a3b8;text-decoration:none;">Forecast</a>
      <a href="/users" class="cta-btn-nav">Unlock Deeper Intelligence</a>
    </div>
  </div>
</nav>

<!-- HERO -->
<header class="hero">
  <div class="hero-date">&#128200; {today_str} &nbsp;&bull;&nbsp; Source: AGSI+ / GIE &nbsp;&bull;&nbsp; Updated Daily</div>
  <h1 style="max-width:820px;margin:0 auto 1rem;">
    Europe Gas Storage Levels Today
  </h1>
  <h2 style="font-size:1.05rem;font-weight:400;color:#94a3b8;line-height:1.7;
             max-width:680px;margin:0 auto 1.5rem;">
    Track current European gas storage levels, daily changes, seasonal progress,
    and winter supply risk signals &mdash; updated daily by EnergyRiskIQ.
  </h2>
  <div style="display:flex;justify-content:center;gap:0.75rem;flex-wrap:wrap;margin-top:1.2rem;">
    <span style="font-size:12px;font-weight:600;color:#22c55e;
      border:1px solid #22c55e33;border-radius:20px;padding:4px 14px;background:rgba(34,197,94,0.06);">
      &#128200; Updated daily
    </span>
    <span style="font-size:12px;font-weight:600;color:#3b82f6;
      border:1px solid #3b82f633;border-radius:20px;padding:4px 14px;background:rgba(59,130,246,0.06);">
      &#127800; Europe gas storage tracker
    </span>
    <span style="font-size:12px;font-weight:600;color:#d4a017;
      border:1px solid #d4a01733;border-radius:20px;padding:4px 14px;background:rgba(212,160,23,0.06);">
      &#10052;&#65039; Winter risk context
    </span>
  </div>
</header>

<main class="page-body">

<!-- ── FREE WIDGET PROMO BANNER ───────────────────────────────────────────── -->
<aside class="gs-widget-banner" aria-label="Free Europe gas storage widget for websites">
  <div class="gs-widget-banner-glow"></div>
  <div class="gs-widget-banner-text">
    <span class="gs-widget-banner-tag">&#9889; Free Embeddable Widget</span>
    <h2 class="gs-widget-banner-title">Put the <span>Europe Gas Storage Widget</span> on Your Own Website &mdash; Free</h2>
    <p class="gs-widget-banner-desc">
      Embed a <strong>live Europe gas storage levels widget</strong> on your blog, app or dashboard in one line of code.
      Show EU storage %, <strong>winter readiness</strong>, top country storage data and gas market risk signals &mdash;
      updated daily, mobile-responsive and free for commercial use.
    </p>
  </div>
  <a href="/widgets/europe-gas-storage-levels" class="gs-widget-banner-cta">
    Get the Free Widget &rarr;
  </a>
</aside>

<!-- ── SECTION: TODAY'S SNAPSHOT ──────────────────────────────────────────── -->
<div class="gs-snapshot-card">
  <div class="gs-snapshot-title">&#9646; Today&rsquo;s Snapshot &mdash; {today_str}</div>
  <div class="gs-snapshot-grid">
    <div class="gs-snap-item">
      <div class="gs-snap-label">EU Storage %</div>
      <div class="gs-snap-value" style="color:{rb_color}">{storage_pct:.1f}<span style="font-size:14px;color:#64748b;">%</span></div>
      <div class="gs-snap-sub">{risk_band} &bull; {season_label}</div>
    </div>
    <div class="gs-snap-item">
      <div class="gs-snap-label">Daily Change</div>
      <div class="gs-snap-value" style="color:{daily_chg_col}">{daily_chg_str}</div>
      <div class="gs-snap-sub">vs prior day</div>
    </div>
    <div class="gs-snap-item">
      <div class="gs-snap-label">To 90% Target</div>
      <div class="gs-snap-value" style="color:#eab308">{gap_to_target_str}</div>
      <div class="gs-snap-sub">EU mandate by Nov 1</div>
    </div>
    <div class="gs-snap-item">
      <div class="gs-snap-label">Days to Nov 1</div>
      <div class="gs-snap-value" style="color:#94a3b8">{days_to_nov1}<span style="font-size:14px;color:#64748b;"> days</span></div>
      <div class="gs-snap-sub">Injection season window</div>
    </div>
    <div class="gs-snap-item">
      <div class="gs-snap-label">Required Injection</div>
      <div class="gs-snap-value" style="color:#3b82f6;font-size:17px;">{required_daily_gwh_str}</div>
      <div class="gs-snap-sub">needed daily to hit 90%</div>
    </div>
    <div class="gs-snap-item">
      <div class="gs-snap-label">Storage Risk Score</div>
      <div class="gs-snap-value" style="color:{rb_color}">{risk_score}<span style="font-size:14px;color:#64748b;">/100</span></div>
      <div class="gs-snap-sub">EnergyRiskIQ proprietary</div>
    </div>
    <div class="gs-snap-item">
      <div class="gs-snap-label">Seasonal Norm</div>
      <div class="gs-snap-value" style="color:#3b82f6">{storage_norm:.1f}<span style="font-size:14px;color:#64748b;">%</span></div>
      <div class="gs-snap-sub">Deviation: {storage_dev:+.1f}pp</div>
    </div>
    <div class="gs-snap-item">
      <div class="gs-snap-label">Last Updated</div>
      <div class="gs-snap-value" style="color:#64748b;font-size:15px;">{last_updated_str}</div>
      <div class="gs-snap-sub">AGSI+ / GIE source</div>
    </div>
  </div>
  <div class="gs-snapshot-footer">
    Data: AGSI+ / Gas Infrastructure Europe (GIE) &bull;
    Risk score: EnergyRiskIQ proprietary model &bull;
    <a href="/data-license" style="color:#475569;">Data License</a>
  </div>
</div>

<!-- ── SECTION: LIVE KEY METRICS ─────────────────────────────────────────── -->
<div class="section-label" style="margin-bottom:20px;">&#128268; Live Storage Metrics &mdash; {today_str}</div>

<div class="gs-metric-grid">
  <div class="gs-metric-card {'gold' if storage_pct >= 40 else 'amber' if storage_pct >= 25 else 'red'}">
    <div class="gs-metric-label">EU Fill Rate</div>
    <div class="gs-metric-value" style="color:{rb_color}">{storage_pct:.1f}<span style="font-size:18px;font-weight:500;color:#64748b;">%</span></div>
    <div class="gs-metric-sub">{risk_band} risk band &bull; {season_label}</div>
  </div>
  <div class="gs-metric-card {'red' if storage_dev < -10 else 'amber' if storage_dev < 0 else 'green'}">
    <div class="gs-metric-label">vs Seasonal Norm</div>
    <div class="gs-metric-value" style="color:{'#ef4444' if storage_dev < -10 else '#eab308' if storage_dev < 0 else '#22c55e'}">{storage_dev:+.1f}<span style="font-size:18px;font-weight:500;color:#64748b;">pp</span></div>
    <div class="gs-metric-sub">Norm: {storage_norm:.1f}% &bull; Deficit: {deficit_gwh:,.0f} GWh</div>
  </div>
  <div class="gs-metric-card {'green' if refill_speed > 1000 else 'blue'}">
    <div class="gs-metric-label">7-Day Refill Speed</div>
    <div class="gs-metric-value" style="color:{'#22c55e' if refill_speed > 2000 else '#3b82f6'}">{refill_speed:,.0f}<span style="font-size:13px;font-weight:500;color:#64748b;"> GWh/d</span></div>
    <div class="gs-metric-sub">Injection season momentum</div>
  </div>
  <div class="gs-metric-card {'amber' if risk_band == 'ELEVATED' else 'red' if risk_band == 'CRITICAL' else 'green'}">
    <div class="gs-metric-label">Storage Risk Score</div>
    <div class="gs-metric-value" style="color:{rb_color}">{risk_score}<span style="font-size:18px;font-weight:500;color:#64748b;">/100</span></div>
    <div class="gs-metric-sub">EnergyRiskIQ proprietary score</div>
  </div>
</div>

<!-- ── SECTION: FILL RATE METER ──────────────────────────────────────────── -->
<div class="gs-deviation-bar">
  <div class="gs-chart-title">&#127919; Current Fill Rate vs Seasonal Norm</div>
  <div style="margin-bottom:8px;">{meter_svg}</div>
  <div style="margin-top:14px;font-size:12px;color:#475569;line-height:1.6;">
    The EU aggregate gas storage target mandated by the European Commission is
    <strong style="color:#e2e8f0">90% by November 1</strong> each year.
    At the current fill rate of <strong style="color:{rb_color}">{storage_pct:.1f}%</strong>,
    Europe must inject approximately
    <strong style="color:#e2e8f0">{required_daily_gwh_str}</strong>
    through to the November deadline
    ({days_to_nov1} days remaining) to meet the target.
    The seasonal norm for this date is <strong style="color:#3b82f6">{storage_norm:.1f}%</strong>.
  </div>
</div>

<!-- ── SECTION: WHAT THIS MEANS ──────────────────────────────────────────── -->
<div class="gs-wtm-section">
  <h2>What Europe&rsquo;s Gas Storage Level Means Today</h2>
  <p style="font-size:14px;color:#94a3b8;line-height:1.8;margin-bottom:4px;">
    European gas storage levels are one of the most closely watched indicators in global energy markets.
    Current EU storage at <strong style="color:{rb_color}">{storage_pct:.1f}%</strong> is
    {wtm_above_below} the {storage_norm:.1f}% seasonal norm
    &mdash; a {wtm_pos_neg} signal for winter supply security.
  </p>
  <div class="gs-wtm-grid">
    <div class="gs-wtm-point">
      <h3>&#128506; Seasonal Context</h3>
      <p>
        Storage is currently tracking <strong style="color:{wtm_dev_color}">{abs(storage_dev):.1f}pp {wtm_above_below}</strong>
        the 5-year seasonal norm of {storage_norm:.1f}%.
        {wtm_position_msg}
      </p>
    </div>
    <div class="gs-wtm-point">
      <h3>&#127963; The 90% November Target</h3>
      <p>
        EU regulation requires member states to aim for <strong style="color:#e2e8f0">90% storage
        by November 1</strong> each year. With {days_to_nov1} days remaining and storage at {storage_pct:.1f}%,
        Europe needs to inject approximately <strong style="color:#3b82f6">{required_daily_gwh_str}</strong> on average
        to reach the mandate.
      </p>
    </div>
    <div class="gs-wtm-point">
      <h3>&#9883;&#65039; TTF Prices and LNG Demand</h3>
      <p>
        Storage levels directly influence <strong style="color:#e2e8f0">TTF natural gas prices</strong>
        and European LNG demand. Lower-than-expected storage typically supports a supply-security premium
        in TTF front-month prices and drives higher LNG import competition from Asia.
      </p>
    </div>
    <div class="gs-wtm-point">
      <h3>&#9888;&#65039; Storage Is Only Part of the Picture</h3>
      <p>
        High storage alone does not eliminate winter risk. LNG import flows,
        Norwegian pipeline exports, weather patterns, industrial demand, and geopolitical
        disruptions all shape the full risk picture. The
        <a href="/indices/europe-gas-stress-index" style="color:#3b82f6;">Europe Gas Stress Index (EGSI)</a>
        combines these signals into one composite risk measure.
      </p>
    </div>
  </div>
</div>

<!-- ── SECTION: TREND CHART ──────────────────────────────────────────────── -->
<div class="gs-chart-wrap">
  <div class="gs-chart-title">&#128200; Europe Gas Storage Trend and Winter Risk Outlook</div>
  <div style="overflow-x:auto;">{trend_svg}</div>
  <div style="margin-top:14px;font-size:11px;color:#334155;line-height:1.6;">
    Chart shows daily EU aggregate gas storage fill rate (gold line) vs the 5-year seasonal average norm (dashed blue).
    Red circles indicate periods when the storage risk band was CRITICAL.
    Data sourced from AGSI+ (Gas Infrastructure Europe) via EnergyRiskIQ's daily ingestion pipeline.
  </div>
</div>

<!-- ── SECTION: MID-PAGE CTA ──────────────────────────────────────────────── -->
<div class="gs-cta-mid">
  <h2>Monitor Europe Gas Risk Before the Market Reacts</h2>
  <p>
    Create a free EnergyRiskIQ account to follow gas storage trends, European energy risk signals,
    and market stress indicators in one place.
  </p>
  <a href="/users" class="gs-cta-btn-primary">Create Free Account</a>
</div>

<!-- ── SECTION: MARKET IMPLICATIONS ─────────────────────────────────────── -->
<div class="section-label" style="margin-bottom:20px;">&#128257; Market Intelligence &mdash; What the Storage Deficit Means</div>

<div class="gs-three-col">
  <div class="gs-implication-card">
    <div class="gs-implication-icon">&#9883;&#65039;</div>
    <div class="gs-implication-title">TTF Price Sensitivity</div>
    <div class="gs-implication-body">
      Storage levels are one of the most structurally significant drivers of European TTF natural gas prices.
      When EU storage deviates significantly below seasonal norms, the market prices in a supply security premium
      — typically manifesting as backwardation flattening or outright contango in the forward curve.
      The current <strong style="color:#ef4444">{storage_dev:+.1f}pp deficit</strong> against seasonal norms
      supports a structural TTF floor premium relative to LNG parity pricing.
      Any deterioration in injection momentum during the critical April–July window
      would be expected to drive TTF front-month prices substantially higher.
    </div>
  </div>
  <div class="gs-implication-card">
    <div class="gs-implication-icon">&#127782;</div>
    <div class="gs-implication-title">Refill Season Risk Outlook</div>
    <div class="gs-implication-body">
      The injection season (April–September) is the only window Europe has to recover from winter withdrawals.
      With storage starting the season at <strong style="color:{rb_color}">{storage_pct:.1f}%</strong>,
      the required injection pace is materially higher than in previous years.
      Three key variables govern the refill trajectory: <em>LNG import volumes</em>
      through European import terminals, <em>Norwegian pipeline exports</em>
      (the dominant swing supplier), and <em>industrial demand response</em>
      from high gas-consuming sectors such as chemicals and fertilisers.
      A sustained injection rate above {required_daily_gwh_str} is required
      to reach the 90% EU target by November 1.
    </div>
  </div>
  <div class="gs-implication-card">
    <div class="gs-implication-icon">&#10052;&#65039;</div>
    <div class="gs-implication-title">Winter 2026–27 Risk Horizon</div>
    <div class="gs-implication-body">
      The adequacy of gas supply through winter 2026–27 depends critically on the outcome
      of this injection season. Historical precedent shows that every 5 percentage point
      shortfall in November storage translates to roughly 2–4 weeks of reduced supply
      buffer at peak winter demand rates. If injection targets are missed by
      a meaningful margin — say, storage entering November at 80% rather than 90% —
      the probability of price spikes, demand curtailment alerts, and
      interruptible supply activations increases sharply.
      EnergyRiskIQ's Storage Risk Score of <strong style="color:{rb_color}">{risk_score}/100</strong>
      reflects this elevated medium-term risk horizon.
    </div>
  </div>
</div>

<!-- ── SECTION: EGSI CORRELATION ─────────────────────────────────────────── -->
<div class="section-label" style="margin-bottom:20px;">&#128279; EGSI-M Correlation &mdash; Gas Stress Index Connection</div>

<div style="background:var(--card);border:1px solid var(--border);border-radius:16px;
            padding:26px 28px;margin-bottom:44px;">
  <div style="display:flex;align-items:center;gap:16px;flex-wrap:wrap;margin-bottom:18px;">
    <a href="/indices/europe-gas-stress-index" style="text-decoration:none;">
      <span class="gs-egsi-band-chip" style="color:{egsi_color};border-color:{egsi_color}55;">
        EGSI-M &nbsp;&bull;&nbsp; {egsi_val}/10 &nbsp;&bull;&nbsp; {egsi_band}
      </span>
    </a>
    <span style="font-size:11px;color:#475569;">
      7-day trend: <span style="color:{_chg_color(egsi_trend)}">{_arrow(egsi_trend)} {egsi_trend:+.2f}</span>
    </span>
    <span style="font-size:11px;color:#475569;">&bull; Data: {egsi_date}</span>
  </div>
  <p style="font-size:14px;color:#cbd5e1;line-height:1.8;margin:0 0 14px;">
    The <strong>Europe Gas Stress Index (EGSI-M)</strong> measures near-term transmission
    market stress: flow disruptions, price spikes, and cross-border congestion events.
    While EGSI-M currently reads <strong style="color:{egsi_color}">{egsi_val}/10 ({egsi_band})</strong>
    — indicating low near-term operational stress — this does not mitigate the
    longer-dated structural risk visible in the storage data.
  </p>
  <p style="font-size:14px;color:#cbd5e1;line-height:1.8;margin:0 0 14px;">
    The divergence between a <strong style="color:{egsi_color}">LOW EGSI-M</strong> and an
    <strong style="color:{rb_color}">ELEVATED Storage Risk Score ({risk_score}/100)</strong>
    is characteristic of the current European gas market environment:
    day-to-day gas flows are functioning normally, but the medium-term inventory
    position is structurally weaker than the same period in prior years.
  </p>
  <p style="font-size:14px;color:#cbd5e1;line-height:1.8;margin:0;">
    Historically, sustained storage deficits of this magnitude (14+ pp below norm)
    have been leading indicators of EGSI-M stress events when paired with
    supply disruption triggers — particularly during the autumn re-injection
    closing window (September–October). Monitoring both EGSI-M and storage
    trajectory together provides the most complete picture of European gas market risk.
  </p>
  <div style="margin-top:18px;padding-top:16px;border-top:1px solid rgba(255,255,255,0.05);">
    <a href="/indices/europe-gas-stress-index"
       style="font-size:12px;font-weight:600;color:var(--gold);text-decoration:none;">
      &#8594; View full EGSI dashboard &rarr;
    </a>
    &nbsp;&nbsp;
    <a href="/indices/europe-energy-risk-index"
       style="font-size:12px;font-weight:600;color:#94a3b8;text-decoration:none;">
      &#8594; EERI European Energy Risk Index &rarr;
    </a>
  </div>
</div>

<!-- ── SECTION: ANALYSIS INTELLIGENCE ────────────────────────────────────── -->
<div class="section-label" style="margin-bottom:20px;">&#129302; Market Intelligence &mdash; Storage Risk Interpretation</div>

<div class="gs-ai-box">
  <div class="gs-ai-label">EnergyRiskIQ Proprietary Analysis Engine &bull; {today_str}</div>
  {interp_html}
  <div style="margin-top:20px;padding-top:16px;border-top:1px solid rgba(255,255,255,0.05);
              font-size:10px;color:#334155;line-height:1.5;">
    This interpretation is generated by EnergyRiskIQ's proprietary analysis engine using live AGSI+ storage data,
    EGSI-M readings, TTF price context, and alert signal inputs. It is for informational purposes only
    and does not constitute financial or trading advice.
    &bull; Storage data: AGSI+ / Gas Infrastructure Europe
    &bull; TTF: Yahoo Finance
    &bull; Risk indices: EnergyRiskIQ proprietary models
  </div>
</div>

<!-- ── SECTION: WHO USES THIS ─────────────────────────────────────────────── -->
<div class="section-label" style="margin-bottom:20px;">&#127919; How EnergyRiskIQ Gas Storage Intelligence Is Used</div>

<div class="gs-audience-grid">
  <div class="gs-audience-card">
    <div class="gs-audience-icon">&#128200;</div>
    <div class="gs-audience-role">Energy Traders</div>
    <div class="gs-audience-title">Storage-Driven TTF Trade Signals</div>
    <div class="gs-audience-body">
      Gas storage deviations from seasonal norms are one of the most reliable
      structural signals in European gas markets. Traders use storage data to:
    </div>
    <ul class="gs-audience-bullets">
      <li>Assess TTF front-month vs forward curve structure (contango/backwardation)</li>
      <li>Size positions ahead of injection season auctions and LNG windows</li>
      <li>Monitor storage momentum as a leading signal for TTF volatility regimes</li>
      <li>Calibrate spread trades between TTF and JKM or Henry Hub</li>
    </ul>
  </div>
  <div class="gs-audience-card">
    <div class="gs-audience-icon">&#128196;</div>
    <div class="gs-audience-role">Risk Managers</div>
    <div class="gs-audience-title">Supply Security & Portfolio Hedging</div>
    <div class="gs-audience-body">
      For utility and industrial risk managers, gas storage levels directly
      determine procurement strategy and hedge ratios:
    </div>
    <ul class="gs-audience-bullets">
      <li>Storage deficit quantification for winter demand coverage ratios</li>
      <li>Trigger monitoring for interruptible supply clause activations</li>
      <li>Regulatory compliance tracking against EU storage mandate (90% by Nov 1)</li>
      <li>Scenario modelling for peak demand periods during cold weather events</li>
    </ul>
  </div>
  <div class="gs-audience-card">
    <div class="gs-audience-icon">&#128202;</div>
    <div class="gs-audience-role">Research Analysts</div>
    <div class="gs-audience-title">Structural Market Context & Citation</div>
    <div class="gs-audience-body">
      Energy analysts and researchers use EnergyRiskIQ's storage intelligence as
      a primary data source for market commentary and research:
    </div>
    <ul class="gs-audience-bullets">
      <li>Daily fill rate snapshots with risk-scored deviation analysis</li>
      <li>EGSI-M correlation to interpret near-term vs medium-term risk</li>
      <li>Historical trend data for seasonal comparisons and report citations</li>
      <li>Custom algorithm narrative interpretation to accelerate research drafting</li>
    </ul>
  </div>
</div>

<!-- ── SECTION: SEASONAL REFERENCE TABLE ──────────────────────────────────── -->
<div class="section-label" style="margin-bottom:20px;">&#128197; European Gas Storage — Seasonal Reference Guide</div>

<div class="gs-method-box" style="margin-bottom:44px;">
  <p style="font-size:13px;color:#94a3b8;line-height:1.7;margin:0 0 14px;">
    EU gas storage follows a predictable seasonal cycle. The European Commission's
    Gas Storage Regulation (EU 2022/1032) sets mandatory filling targets,
    with the primary benchmark being <strong style="color:#e2e8f0">90% full by November 1</strong>
    of each year. Understanding where current levels sit within this cycle
    is essential for accurate price risk assessment.
  </p>
  <table class="gs-risk-season-table">
    <thead>
      <tr>
        <th>Season</th>
        <th>Phase</th>
        <th>Typical Fill Range</th>
        <th>Typical Risk Band</th>
      </tr>
    </thead>
    <tbody>
      {season_table_html}
    </tbody>
  </table>
  <div style="margin-top:14px;font-size:11px;color:#334155;">
    Current storage: <strong style="color:{rb_color}">{storage_pct:.1f}%</strong> &bull;
    Season norm: <strong style="color:#3b82f6">{storage_norm:.1f}%</strong> &bull;
    EnergyRiskIQ risk band: <strong style="color:{rb_color}">{risk_band}</strong>
  </div>
</div>

<!-- ── SECTION: METHODOLOGY ────────────────────────────────────────────────── -->
<div class="section-label" style="margin-bottom:20px;">&#128214; Methodology — How EnergyRiskIQ Calculates Gas Storage Risk</div>

<div class="gs-method-box">
  <p style="font-size:13px;color:#94a3b8;line-height:1.7;margin:0 0 16px;">
    EnergyRiskIQ's gas storage risk intelligence is computed daily using a multi-factor
    proprietary model, combining raw AGSI+ flow data with our EGSI, EERI, and
    geopolitical alert pipeline to produce a holistic risk score.
  </p>
  <div class="gs-method-grid">
    <div class="gs-method-item">
      <strong>Primary Data Source</strong>
      Daily EU aggregate gas storage levels from AGSI+ (Aggregated Gas Storage Inventory),
      published by Gas Infrastructure Europe (GIE). This covers all EU member states
      plus the UK and Ukraine, aggregated to a single European fill rate percentage.
    </div>
    <div class="gs-method-item">
      <strong>Seasonal Norm Calculation</strong>
      The seasonal norm for each calendar date is calculated using the rolling 5-year
      average fill rate for that date. This provides a stable benchmark that captures
      seasonal demand cycles without being distorted by single-year outliers.
    </div>
    <div class="gs-method-item">
      <strong>Deviation & Deficit Scoring</strong>
      The percentage point deviation from the seasonal norm is converted into a
      GWh deficit estimate using a European storage capacity assumption of ~1,100 TWh
      (approximately 1.1 trillion cubic feet equivalent). This quantifies the
      magnitude of the supply buffer shortfall in actionable energy terms.
    </div>
    <div class="gs-method-item">
      <strong>Storage Risk Score (0–100)</strong>
      The proprietary risk score combines: the normalised deviation from seasonal norms
      (weighted 40%), the distance from the 90% EU mandated target (30%),
      current refill/withdrawal momentum (15%), and EGSI-M stress signal (15%).
      Scores above 70 enter CRITICAL band; 55–69 = ELEVATED; 40–54 = MODERATE; below 40 = LOW.
    </div>
    <div class="gs-method-item">
      <strong>Refill Speed Calculation</strong>
      The 7-day refill speed (GWh/day) is derived from the 7-day rolling change in
      total EU stored gas volumes, converted from percentage points using the
      aggregate storage capacity. Negative values indicate net withdrawals;
      positive values confirm the injection season is active.
    </div>
    <div class="gs-method-item">
      <strong>Update Frequency</strong>
      Storage data is updated daily following the AGSI+ publication window
      (typically 10:00–12:00 CET). EnergyRiskIQ's ingestion pipeline processes
      the new data within minutes of publication, updating risk scores,
      EGSI inputs, and algorithm-driven interpretations automatically.
    </div>
  </div>
</div>

<!-- ── SECTION: RELATED DATA & INDICES ────────────────────────────────────── -->
<div class="section-label" style="margin-bottom:20px;">&#128279; Related EnergyRiskIQ Data and Risk Indices</div>

<div class="gs-related-grid">
  <a href="/data/ttf-gas-price-today" class="gs-related-card">
    <div class="gs-related-card-tag">Price Data</div>
    <div class="gs-related-card-title">TTF Gas Price Today</div>
    <div class="gs-related-card-desc">Dutch TTF benchmark &bull; daily updates &bull; charts</div>
  </a>
  <a href="/data/europe-lng-supply-demand" class="gs-related-card">
    <div class="gs-related-card-tag">LNG Intelligence</div>
    <div class="gs-related-card-title">Europe LNG Supply and Demand</div>
    <div class="gs-related-card-desc">Daily LNG flows &bull; terminal data &bull; risk context</div>
  </a>
  <a href="/data/jkm-lng-spot-price" class="gs-related-card">
    <div class="gs-related-card-tag">LNG Price Data</div>
    <div class="gs-related-card-title">JKM LNG Spot Price</div>
    <div class="gs-related-card-desc">Japan Korea Marker &bull; Asia LNG benchmark &bull; daily</div>
  </a>
  <a href="/data/global-energy-risk-forecast" class="gs-related-card">
    <div class="gs-related-card-tag">Forecast</div>
    <div class="gs-related-card-title">Global Energy Risk Forecast</div>
    <div class="gs-related-card-desc">24-hour Brent &amp; TTF outlook &bull; risk signals</div>
  </a>
  <a href="/indices/europe-energy-risk-index" class="gs-related-card">
    <div class="gs-related-card-tag">Risk Index</div>
    <div class="gs-related-card-title">Europe Energy Risk Index</div>
    <div class="gs-related-card-desc">EERI &bull; {eeri_val}/100 &bull; {eeri_band}</div>
  </a>
  <a href="/indices/europe-gas-stress-index" class="gs-related-card">
    <div class="gs-related-card-tag">Gas Risk Index</div>
    <div class="gs-related-card-title">Europe Gas Stress Index</div>
    <div class="gs-related-card-desc">EGSI-M &bull; {egsi_val}/10 &bull; {egsi_band}</div>
  </a>
  <a href="/indices/global-energy-risk-index" class="gs-related-card">
    <div class="gs-related-card-tag">Risk Index</div>
    <div class="gs-related-card-title">Global Energy Risk Index</div>
    <div class="gs-related-card-desc">GERI &bull; {geri_val}/100 &bull; {geri_band}</div>
  </a>
</div>

<!-- ── SECTION: FAQ ───────────────────────────────────────────────────────── -->
<div class="section-label" style="margin-bottom:20px;">&#10067; Europe Gas Storage Levels FAQ</div>

<div class="gs-faq-section">

  <div class="gs-faq-item" onclick="this.classList.toggle('open')">
    <div class="gs-faq-q">
      <span>What are Europe gas storage levels?</span>
      <span class="gs-faq-toggle">+</span>
    </div>
    <div class="gs-faq-a">
      Europe gas storage levels show how full underground natural gas storage facilities are across European
      countries. They are used to assess winter supply security, injection progress, and potential pressure
      on gas markets.
    </div>
  </div>

  <div class="gs-faq-item" onclick="this.classList.toggle('open')">
    <div class="gs-faq-q">
      <span>Why is the 90% gas storage target important?</span>
      <span class="gs-faq-toggle">+</span>
    </div>
    <div class="gs-faq-a">
      The European Union requires member states to aim for high storage levels before winter. The 90% target
      by November 1 is widely watched because it indicates whether Europe has enough stored gas entering
      the peak heating season.
    </div>
  </div>

  <div class="gs-faq-item" onclick="this.classList.toggle('open')">
    <div class="gs-faq-q">
      <span>How often is this page updated?</span>
      <span class="gs-faq-toggle">+</span>
    </div>
    <div class="gs-faq-a">
      This page is updated daily when new storage data is available.
    </div>
  </div>

  <div class="gs-faq-item" onclick="this.classList.toggle('open')">
    <div class="gs-faq-q">
      <span>Do gas storage levels affect TTF gas prices?</span>
      <span class="gs-faq-toggle">+</span>
    </div>
    <div class="gs-faq-a">
      Yes. Lower-than-expected storage levels can increase concern about winter supply and may support
      higher TTF gas prices, especially when combined with cold weather, LNG disruptions, or geopolitical risk.
    </div>
  </div>

  <div class="gs-faq-item" onclick="this.classList.toggle('open')">
    <div class="gs-faq-q">
      <span>Are high storage levels enough to remove winter risk?</span>
      <span class="gs-faq-toggle">+</span>
    </div>
    <div class="gs-faq-a">
      Not always. Storage is only one part of the European gas-risk picture. Weather, LNG imports,
      pipeline flows, demand, price volatility, and geopolitical events can still affect market stress.
    </div>
  </div>

  <div class="gs-faq-item" onclick="this.classList.toggle('open')">
    <div class="gs-faq-q">
      <span>What is the difference between gas storage data and the Europe Gas Stress Index?</span>
      <span class="gs-faq-toggle">+</span>
    </div>
    <div class="gs-faq-a">
      Gas storage data shows physical inventory levels. The Europe Gas Stress Index combines storage,
      market pressure, supply stress, transit risk, and policy signals into a broader risk indicator.
      <a href="/indices/europe-gas-stress-index" style="color:#3b82f6;margin-left:4px;">View EGSI &rarr;</a>
    </div>
  </div>

</div>

<!-- ── SECTION: BOTTOM CTA ────────────────────────────────────────────────── -->
<div class="gs-cta-bottom">
  <h2>Turn Gas Storage Data Into Market Risk Intelligence</h2>
  <p>
    EnergyRiskIQ connects storage levels, LNG flows, TTF gas prices, and European risk indices
    to help you understand changing energy-market conditions.
  </p>
  <a href="/indices/europe-gas-stress-index" class="gs-cta-btn-gold">View Europe Gas Stress Index</a>
</div>

<!-- ── SECTION: CITATION BLOCK ────────────────────────────────────────────── -->
<div class="section-label" style="margin-bottom:20px;">&#128196; Citation &amp; Reference</div>
<div class="snap-cite-card" style="margin-bottom:44px;">
  <h3>How to Cite This Page</h3>
  <p class="snap-cite-desc">
    This page is updated daily with fresh data from live production pipelines.
    To reference this intelligence in research, journalism, or professional reports,
    use the citation below.
  </p>
  <div class="snap-cite-code-wrap">
    <pre class="snap-cite-code">EnergyRiskIQ. (2026). <em>European Gas Storage Levels — Live Data &amp; Risk Intelligence — {today_str}</em>.
Retrieved from <a href="{BASE_URL}/gas-storage-levels-in-europe">{BASE_URL}/gas-storage-levels-in-europe</a>
Data sources: AGSI+ / GIE (EU storage), Yahoo Finance (TTF), EnergyRiskIQ risk pipeline (EGSI-M, GERI, EERI).</pre>
    <button class="snap-cite-copy-btn" onclick="this.textContent='Copied!';setTimeout(()=>this.textContent='Copy',2000);navigator.clipboard&&navigator.clipboard.writeText('EnergyRiskIQ. (2026). European Gas Storage Levels \u2014 Live Data & Risk Intelligence \u2014 {today_str}. Retrieved from {BASE_URL}/gas-storage-levels-in-europe')">Copy</button>
  </div>
  <div class="snap-cite-footer">
    Data sourced from: AGSI+ / Gas Infrastructure Europe (EU aggregate storage),
    Yahoo Finance (TTF natural gas futures), EnergyRiskIQ internal risk scoring pipeline (EGSI-M, GERI, EERI).
    Custom algorithm analysis via proprietary EnergyRiskIQ analysis engine. <strong>Not financial advice.</strong>
    See <a href="{BASE_URL}/indices/europe-gas-stress-index">EGSI methodology</a> for full scoring detail.
  </div>
</div>

</main>

<!-- FOOTER -->
<footer style="background:#080c14;border-top:1px solid rgba(255,255,255,0.05);
               padding:40px 24px 32px;text-align:center;">
  <div style="max-width:900px;margin:0 auto;">
    <a href="/" style="display:inline-flex;align-items:center;gap:8px;text-decoration:none;
                       color:#e2e8f0;font-weight:700;font-size:1rem;margin-bottom:16px;">
      <img src="/static/logo.png" alt="EnergyRiskIQ" style="height:22px">
      EnergyRiskIQ
    </a>
    <div style="font-size:11px;color:#334155;line-height:1.7;margin-bottom:14px;">
      Real-time energy risk intelligence for traders, analysts, and risk managers.
      GERI &bull; EERI &bull; EGSI &bull; Gas Storage &bull; Alerts &bull; AI Briefings
    </div>
    <div style="display:flex;justify-content:center;gap:24px;flex-wrap:wrap;
                font-size:11px;margin-bottom:14px;">
      <a href="/indices/global-energy-risk-index" style="color:#475569;text-decoration:none;">GERI</a>
      <a href="/indices/europe-energy-risk-index" style="color:#475569;text-decoration:none;">EERI</a>
      <a href="/indices/europe-gas-stress-index" style="color:#475569;text-decoration:none;">EGSI</a>
      <a href="/gas-storage-levels-in-europe" style="color:#d4a017;text-decoration:none;">Gas Storage</a>
      <a href="/data/global-energy-risk-forecast" style="color:#475569;text-decoration:none;">Forecast</a>
      <a href="/data/energy-risk-snapshot" style="color:#475569;text-decoration:none;">Snapshot</a>
      <a href="/users" style="color:#475569;text-decoration:none;">Sign Up</a>
    </div>
    <div style="font-size:10px;color:#1e293b;">
      &copy; 2026 EnergyRiskIQ. Data for informational purposes only.
      Not financial advice. &bull;
      <a href="/" style="color:#1e293b;text-decoration:none;">Home</a>
    </div>
  </div>
</footer>

</body>
</html>"""


# ── Main Route ─────────────────────────────────────────────────────────────────

@router.get("/gas-storage-levels-in-europe")
async def gas_storage_levels_in_europe():
    """
    Public SEO page: European Gas Storage Levels — Live Data & Risk Intelligence.
    Streams loader immediately, then fetches data and renders full page.
    """
    async def generate():
        yield _GAS_STORAGE_LOADER

        try:
            data = await asyncio.to_thread(_fetch_gas_storage_data)
        except Exception as exc:
            logger.error(f"Gas storage data fetch failed: {exc}", exc_info=True)
            yield (
                f"<script>var l=document.getElementById('snap-loader');"
                f"if(l)l.style.display='none';document.body.style.overflow='';</script>"
                f"<div style='color:#ef4444;padding:40px;font-family:sans-serif;background:#0b0f1a'>"
                f"<h2>Error loading storage data</h2>"
                f"<p>{_html.escape(str(exc))}</p></div></body></html>"
            )
            return

        today_str = datetime.now(timezone.utc).strftime("%B %-d, %Y")

        # Run AI interpretation
        storage_row = data["storage_row"] or {}
        egsi_row = data["egsi_row"] or {}
        ttf_rows = data["ttf_rows"]

        storage_pct   = _safe_float(storage_row.get("eu_storage_percent", 30.2))
        storage_norm  = _safe_float(storage_row.get("seasonal_norm", 45.0))
        storage_dev   = _safe_float(storage_row.get("deviation_from_norm", -14.8))
        refill_speed  = _safe_float(storage_row.get("refill_speed_7d", 3494))
        withdraw_rate = _safe_float(storage_row.get("withdrawal_rate_7d", 213))
        risk_score    = int(storage_row.get("risk_score") or 57)
        risk_band     = (storage_row.get("risk_band") or "ELEVATED").upper()

        egsi_val  = round(_safe_float(egsi_row.get("index_value", 3.15)), 2)
        egsi_band = (egsi_row.get("band") or "LOW").upper()

        ttf_latest = _safe_float(ttf_rows[0]["ttf_price"]) if ttf_rows else 0.0

        ai_interp = await asyncio.to_thread(
            _run_storage_ai,
            today_str,
            storage_pct, storage_norm, storage_dev,
            refill_speed, risk_score, risk_band,
            egsi_val, egsi_band,
            ttf_latest, withdraw_rate,
            data["alert_context"],
        )

        html_body = _build_gas_storage_html(data, ai_interp, today_str)
        yield html_body

    return StreamingResponse(generate(), media_type="text/html")


@router.get("/api/gas-storage-by-country")
async def gas_storage_by_country():
    """
    JSON API: latest per-country EU gas storage breakdown.

    Returns the most recent country-level snapshot for each country, sorted by
    fill percentage ascending (lowest/most-at-risk first).
    """
    rows = execute_production_query(
        """
        SELECT DISTINCT ON (country_code)
            date, country_code, country_name, storage_percent,
            gas_in_storage_twh, working_gas_volume_twh,
            injection_twh, withdrawal_twh, trend
        FROM gas_storage_country_snapshots
        WHERE level = 'country'
        ORDER BY country_code, date DESC
        """
    ) or []

    def _f(v):
        return float(v) if v is not None else None

    countries = sorted(
        [
            {
                "date": str(r["date"]),
                "country_code": r["country_code"],
                "country_name": r["country_name"],
                "storage_percent": _f(r["storage_percent"]),
                "gas_in_storage_twh": _f(r["gas_in_storage_twh"]),
                "working_gas_volume_twh": _f(r["working_gas_volume_twh"]),
                "injection_twh": _f(r["injection_twh"]),
                "withdrawal_twh": _f(r["withdrawal_twh"]),
                "trend": _f(r["trend"]),
            }
            for r in rows
        ],
        key=lambda c: (c["storage_percent"] is None, c["storage_percent"]),
    )

    latest_date = max((c["date"] for c in countries), default=None)

    return Response(
        content=json.dumps({"as_of": latest_date, "count": len(countries), "countries": countries}),
        media_type="application/json",
    )
