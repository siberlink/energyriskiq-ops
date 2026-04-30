"""
Europe LNG Supply & Demand — Live Market Intelligence
Route: /data/europe-lng-supply-demand
SEO-optimized data page. Covers live JKM benchmark, Atlantic basin dynamics,
JKM-TTF spread intelligence, and supply security context for energy professionals.
"""
import os
import json
import logging
import asyncio
import html as _html
from datetime import datetime, timezone, date as _date, timedelta

from fastapi import APIRouter
from fastapi.responses import StreamingResponse, Response

from src.db.db import execute_production_one, execute_production_query
from src.api.snapshot_routes import _LOADER_HTML, BAND_COLORS, _safe_float

router = APIRouter()
logger = logging.getLogger(__name__)

BASE_URL = "https://energyriskiq.com"

# ── Helpers ───────────────────────────────────────────────────────────────────

def _arrow(v):
    return "&#9650;" if v >= 0 else "&#9660;"

def _chg_color(v):
    return "#22c55e" if v >= 0 else "#ef4444"

def _sign(v):
    return "+" if v >= 0 else ""

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

# JKM $/MMBtu → $/MWh conversion (1 MMBtu = 0.29307 MWh)
_MMBTU_TO_MWH = 0.29307

# Approximate EUR/USD for display comparisons
_EUR_USD = 1.09


# ── SVG Chart Builders ────────────────────────────────────────────────────────

def _build_jkm_trend_svg(history_rows, ttf_rows=None, width=700, height=210):
    """
    Dual-line SVG: JKM ($/MMBtu) and TTF in $/MMBtu-equivalent.
    history_rows: list of dicts with date, jkm_price
    ttf_rows: list of dicts with date, ttf_price (€/MWh) — converted to $/MMBtu
    """
    if not history_rows or len(history_rows) < 2:
        return ""

    W, H = width, height
    PAD_L, PAD_R, PAD_T, PAD_B = 48, 16, 16, 44

    cw = W - PAD_L - PAD_R
    ch = H - PAD_T - PAD_B

    # Build JKM price series
    jkm_vals = [float(r.get("jkm_price") or 0) for r in history_rows]
    jkm_dates = [r.get("date") for r in history_rows]
    n = len(history_rows)

    # Build TTF equivalent series (align by date if available)
    ttf_lookup = {}
    if ttf_rows:
        for r in ttf_rows:
            d = r.get("date")
            p = float(r.get("ttf_price") or 0)
            if d and p:
                # Convert TTF €/MWh → $/MMBtu: multiply by MWh_per_MMBtu × EUR/USD
                ttf_lookup[d] = p * _MMBTU_TO_MWH * _EUR_USD

    ttf_vals = [ttf_lookup.get(jkm_dates[i]) for i in range(n)]
    ttf_valid = [v for v in ttf_vals if v is not None]

    all_vals = jkm_vals + ttf_valid
    vmin = max(0, min(all_vals) * 0.94)
    vmax = max(all_vals) * 1.06
    rng = vmax - vmin or 1

    def px(i, v, total=None):
        total = total or n
        x = PAD_L + (i / (total - 1)) * cw
        y = PAD_T + ch - ((v - vmin) / rng) * ch
        return x, y

    jkm_pts = [px(i, v) for i, v in enumerate(jkm_vals)]

    def pts_to_path(pts, filter_none=False):
        valid = [(i, p) for i, p in enumerate(pts) if p is not None]
        if not valid:
            return ""
        path = f"M {valid[0][1][0]:.1f} {valid[0][1][1]:.1f}"
        for _, p in valid[1:]:
            path += f" L {p[0]:.1f} {p[1]:.1f}"
        return path

    # JKM fill area
    jkm_path = pts_to_path(jkm_pts)
    fill_path = jkm_path + f" L {jkm_pts[-1][0]:.1f} {PAD_T + ch:.1f} L {jkm_pts[0][0]:.1f} {PAD_T + ch:.1f} Z"

    # TTF equivalent line
    ttf_pts_mapped = []
    for i, v in enumerate(ttf_vals):
        if v is not None:
            ttf_pts_mapped.append(px(i, v))
        else:
            ttf_pts_mapped.append(None)

    # Y-axis ticks
    y_ticks = [vmin, (vmin + vmax) / 2, vmax]
    y_labels = ""
    for yv in y_ticks:
        _, y = px(0, yv)
        y_labels += (
            f'<line x1="{PAD_L}" y1="{y:.1f}" x2="{W - PAD_R}" y2="{y:.1f}" '
            f'stroke="rgba(255,255,255,0.05)" stroke-width="1"/>'
            f'<text x="{PAD_L - 4}" y="{y + 4:.1f}" text-anchor="end" font-size="9" '
            f'fill="#475569" font-family="Inter,sans-serif">${yv:.1f}</text>'
        )

    # X-axis labels every ~15 points
    x_labels = ""
    step = max(1, n // 6)
    for i in range(0, n, step):
        x, _ = px(i, vmin)
        d = jkm_dates[i]
        lbl = _fmt_month(d) if d else ""
        x_labels += (
            f'<text x="{x:.1f}" y="{PAD_T + ch + 16}" text-anchor="middle" '
            f'font-size="9" fill="#475569" font-family="Inter,sans-serif">{lbl}</text>'
        )

    # Spread shading: fill between JKM and TTF where JKM > TTF
    spread_svg = ""

    return f"""<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg"
  style="width:100%;max-width:{W}px;display:block;overflow:visible">
  {y_labels}
  {x_labels}
  <path d="{fill_path}" fill="rgba(212,160,23,0.07)"/>
  {(f'<path d="{pts_to_path(ttf_pts_mapped)}" fill="none" stroke="#3b82f6" stroke-width="1.5" stroke-dasharray="6 3" opacity="0.7"/>' if ttf_valid else '')}
  <path d="{jkm_path}" fill="none" stroke="#d4a017" stroke-width="2.5"/>
  <circle cx="{jkm_pts[-1][0]:.1f}" cy="{jkm_pts[-1][1]:.1f}" r="5"
    fill="#d4a017" stroke="#0f172a" stroke-width="2"/>
  <rect x="{PAD_L}" y="{H - 14}" width="14" height="3" rx="1.5" fill="#d4a017"/>
  <text x="{PAD_L + 18}" y="{H - 10}" font-size="9" fill="#94a3b8"
    font-family="Inter,sans-serif">JKM Spot ($/MMBtu)</text>
  {'<line x1="' + str(PAD_L + 120) + '" y1="' + str(H - 12) + '" x2="' + str(PAD_L + 134) + '" y2="' + str(H - 12) + '" stroke="#3b82f6" stroke-width="1.5" stroke-dasharray="5 2"/><text x="' + str(PAD_L + 138) + '" y="' + str(H - 10) + '" font-size="9" fill="#94a3b8" font-family="Inter,sans-serif">TTF equiv. ($/MMBtu)</text>' if ttf_valid else ''}
</svg>"""


def _build_price_bar_chart(rows, color="#d4a017", val_key="jkm_price", label_key="date", width=480, height=90):
    """Build a simple bar+line chart for a short price series (last 30 days)."""
    if not rows or len(rows) < 2:
        return ""

    W, H = width, height
    PAD_L, PAD_R, PAD_T, PAD_B = 40, 12, 10, 30
    cw = W - PAD_L - PAD_R
    ch = H - PAD_T - PAD_B

    vals = [float(r.get(val_key) or 0) for r in rows]
    vmin = min(vals) * 0.98
    vmax = max(vals) * 1.02
    rng = vmax - vmin or 1
    n = len(rows)
    bar_w = cw / n

    bars = ""
    pts = []
    for i, (row, v) in enumerate(zip(rows, vals)):
        x = PAD_L + i * bar_w
        bar_h_val = ((v - vmin) / rng) * ch
        y = PAD_T + ch - bar_h_val
        cx = x + bar_w / 2
        pts.append((cx, y))
        bars += (
            f'<rect x="{x + 1:.1f}" y="{y:.1f}" '
            f'width="{bar_w - 2:.1f}" height="{bar_h_val:.1f}" '
            f'fill="{color}" opacity="0.18" rx="1"/>'
            f'<circle cx="{cx:.1f}" cy="{y:.1f}" r="2.5" fill="{color}" stroke="#0f172a" stroke-width="1"/>'
        )
        # Label every 5th
        d = row.get(label_key)
        if i % max(1, n // 6) == 0:
            lbl = _fmt_date_short(d) if d else ""
            bars += (
                f'<text x="{cx:.1f}" y="{PAD_T + ch + 16}" text-anchor="middle" '
                f'font-size="8" fill="#475569" font-family="Inter,sans-serif">{lbl}</text>'
            )

    # Line connecting dots
    path = f"M {pts[0][0]:.1f} {pts[0][1]:.1f}" + "".join(f" L {p[0]:.1f} {p[1]:.1f}" for p in pts[1:])

    # Y labels
    mid_v = (vmin + vmax) / 2
    _, y_top = (0, PAD_T)
    _, y_bot = (0, PAD_T + ch)
    mid_y = PAD_T + ch / 2
    y_svgs = (
        f'<line x1="{PAD_L}" y1="{PAD_T + ch:.1f}" x2="{W - PAD_R}" y2="{PAD_T + ch:.1f}" '
        f'stroke="rgba(255,255,255,0.06)" stroke-width="1"/>'
        f'<text x="{PAD_L - 4}" y="{PAD_T + 4}" text-anchor="end" font-size="8" fill="#475569" font-family="Inter,sans-serif">${vmax:.1f}</text>'
        f'<text x="{PAD_L - 4}" y="{mid_y + 3:.1f}" text-anchor="end" font-size="8" fill="#475569" font-family="Inter,sans-serif">${mid_v:.1f}</text>'
    )

    return (
        f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" '
        f'style="width:100%;max-width:{W}px;display:block;overflow:visible">'
        f'{y_svgs}{bars}'
        f'<path d="{path}" fill="none" stroke="{color}" stroke-width="1.5" stroke-dasharray="4 2" opacity="0.6"/>'
        f'</svg>'
    )


# ── Analysis Engine ───────────────────────────────────────────────────────────

_LNG_ANALYSIS_FALLBACK = """European LNG import demand has entered a structurally elevated phase, driven by the sustained reduction in Russian pipeline gas supplies since 2022 and the consequent need for Atlantic Basin flexible LNG to fill the gap. The JKM benchmark — Asia's primary LNG price signal — currently trades at a significant premium to the TTF equivalent, meaning every LNG cargo that clears into Asia represents a cargo not available to Europe. This Asia-Europe arbitrage window is one of the most consequential variables in European gas supply security today.

The current JKM level of $16.55/MMBtu reflects robust Asian demand, particularly from Japanese and South Korean power utilities restocking ahead of summer air-conditioning load, and from Chinese industrial buyers resuming LNG procurement following a period of demand softness. When the JKM-TTF spread widens beyond approximately $2/MMBtu on an energy-equivalent basis, Atlantic basin LNG producers systematically divert cargoes eastward — a structural headwind for European import volumes that can tighten the continent's gas balance materially during peak demand periods.

Europe's LNG import infrastructure has expanded significantly since 2022, with new floating storage and regasification units (FSRUs) added across Germany, the Netherlands, Italy, and the Baltic states. This capacity expansion means Europe can now theoretically absorb 150+ bcm per year of LNG, up from approximately 80 bcm pre-crisis. However, infrastructure capacity and actual import volumes are distinct: when Asian netbacks are superior, European terminals operate below nameplate capacity regardless of available regasification slots.

For traders and analysts, the JKM-TTF spread and its trajectory over the coming injection season (April–September) is the single most important variable governing European gas storage refill adequacy. If Asian demand accelerates — driven by heat waves, nuclear outages, or Chinese industrial restocking — the resulting cargo diversion from Europe could translate directly into a structurally tighter gas balance entering winter 2026–27, supporting TTF front-month prices well above current levels."""


def _run_lng_analysis(
    today_str: str,
    jkm_latest: float,
    jkm_chg: float,
    jkm_chg_pct: float,
    jkm_ytd_low: float,
    jkm_ytd_high: float,
    ttf_latest: float,
    jkm_ttf_spread_mmbtu: float,
    storage_pct: float,
    geri_val: int,
    geri_band: str,
    alert_context: str,
) -> str:
    """Generate expert intelligence interpretation using a custom analysis engine."""
    try:
        from openai import OpenAI
        ai_key = os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY")
        ai_url = os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL")
        client = OpenAI(api_key=ai_key, base_url=ai_url) if ai_key and ai_url else OpenAI()

        ttf_mmbtu = ttf_latest * _MMBTU_TO_MWH * _EUR_USD

        prompt = f"""You are EnergyRiskIQ's senior European LNG and gas market analyst. You write for professional energy traders and market analysts.

Today is {today_str}. Write an authoritative, human expert intelligence analysis of the current European LNG supply and demand situation. Do NOT mention AI, machine learning, or algorithms — write as a human expert analyst.

=== LIVE MARKET DATA ===
JKM LNG Spot Price: ${jkm_latest:.2f}/MMBtu
JKM 24h Change: {jkm_chg:+.2f} ({jkm_chg_pct:+.2f}%)
JKM YTD Range: ${jkm_ytd_low:.2f} – ${jkm_ytd_high:.2f}/MMBtu (YTD gain: {((jkm_latest/jkm_ytd_low - 1)*100):+.1f}%)
TTF Natural Gas: €{ttf_latest:.2f}/MWh (equiv. ~${ttf_mmbtu:.2f}/MMBtu)
JKM–TTF Energy-Equivalent Spread: ~${jkm_ttf_spread_mmbtu:.2f}/MMBtu JKM premium
EU Gas Storage: {storage_pct:.1f}% full
GERI (Global Energy Risk): {geri_val}/100 ({geri_band})

=== ALERT CONTEXT (last 72h) ===
{alert_context}

=== YOUR TASK ===
Write exactly 4 expert paragraphs, separated by \\n\\n. No bullet points. No headers. No markdown. Pure analytical prose. Each paragraph 3–5 sentences.

Paragraph 1: Current JKM price context — what the level means, why it matters for European supply, reference the YTD move.
Paragraph 2: The JKM–TTF spread dynamics — how the Asian premium impacts European cargo availability, what the arbitrage threshold means for import volumes.
Paragraph 3: European import infrastructure and storage refill implications — how LNG connects to the storage refill season, what traders need to watch over the next 60–90 days.
Paragraph 4: Forward-looking view for traders and analysts — what signals to monitor, what scenarios would drive significant price moves, and how to position in this environment.

Write like a senior expert analyst who has been covering LNG markets for 15 years. Be precise, reference all key numbers, be actionable."""

        resp = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=900,
            timeout=40,
        )
        text = resp.choices[0].message.content.strip()
        return text if text else _LNG_ANALYSIS_FALLBACK
    except Exception as exc:
        logger.warning(f"LNG analysis engine call failed: {exc}")
        return _LNG_ANALYSIS_FALLBACK


# ── Loader HTML ───────────────────────────────────────────────────────────────

_LNG_LOADER = _LOADER_HTML.replace(
    "Global Energy Risk Snapshot | EnergyRiskIQ",
    "Europe LNG Supply &amp; Demand — Live Market Intelligence | EnergyRiskIQ",
).replace(
    'name="description" content="Live global energy risk snapshot. Current GERI, EERI and EGSI-M index values with Brent crude, TTF gas, VIX and LNG market prices."',
    'name="description" content="Live Europe LNG supply and demand intelligence — JKM spot price, Atlantic basin dynamics, JKM-TTF spread analysis, and storage refill implications for energy traders and analysts."',
).replace(
    'rel="canonical" href="https://energyriskiq.com/data/energy-risk-snapshot"',
    'rel="canonical" href="https://energyriskiq.com/data/europe-lng-supply-demand"',
).replace(
    "Fetching GERI\u00a0&\u00a0EERI indices\u2026",
    "Fetching LNG market data\u2026",
).replace(
    '<span class="ld-tag">GERI</span>\n    <span class="ld-tag">EERI</span>\n    <span class="ld-tag">EGSI&#8209;M</span>\n    <span class="ld-tag">Brent</span>\n    <span class="ld-tag">TTF</span>',
    '<span class="ld-tag">JKM</span>\n    <span class="ld-tag">TTF</span>\n    <span class="ld-tag">LNG Flow</span>\n    <span class="ld-tag">Spread</span>',
)


# ── Page CSS ──────────────────────────────────────────────────────────────────

_LNG_CSS = """
.lng-metric-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 40px;
}
@media (max-width: 900px) { .lng-metric-grid { grid-template-columns: 1fr 1fr; } }
@media (max-width: 480px)  { .lng-metric-grid { grid-template-columns: 1fr; } }
.lng-metric-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 20px 20px 18px;
  position: relative;
  overflow: hidden;
}
.lng-metric-card::before {
  content: '';
  position: absolute; top: 0; left: 0; right: 0;
  height: 3px; border-radius: 3px 3px 0 0;
}
.lng-metric-card.gold::before  { background: linear-gradient(90deg, #d4a017, transparent); }
.lng-metric-card.blue::before  { background: linear-gradient(90deg, #3b82f6, transparent); }
.lng-metric-card.green::before { background: linear-gradient(90deg, #22c55e, transparent); }
.lng-metric-card.amber::before { background: linear-gradient(90deg, #eab308, transparent); }
.lng-metric-card.red::before   { background: linear-gradient(90deg, #ef4444, transparent); }
.lng-label  { font-size:10px; font-weight:700; letter-spacing:1.8px; text-transform:uppercase; color:var(--muted); margin-bottom:8px; }
.lng-value  { font-size:30px; font-weight:800; line-height:1.05; font-variant-numeric:tabular-nums; margin-bottom:4px; }
.lng-sub    { font-size:11px; color:var(--muted); line-height:1.4; }
.lng-chart-wrap {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 24px 24px 16px;
  margin-bottom: 36px;
}
.lng-chart-title {
  font-size:12px; font-weight:700; letter-spacing:1.4px;
  text-transform:uppercase; color:var(--gold);
  margin-bottom:16px; display:flex; align-items:center; gap:8px;
}
.lng-three-col {
  display: grid;
  grid-template-columns: repeat(3,1fr);
  gap: 20px;
  margin-bottom: 40px;
}
@media (max-width: 800px) { .lng-three-col { grid-template-columns: 1fr; } }
.lng-intel-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 22px 22px 20px;
}
.lng-intel-icon  { font-size:1.5rem; margin-bottom:10px; }
.lng-intel-title { font-size:13px; font-weight:700; color:#e2e8f0; margin-bottom:8px; }
.lng-intel-body  { font-size:12px; color:var(--muted); line-height:1.65; }
.lng-spread-box {
  background: linear-gradient(135deg, rgba(212,160,23,0.06) 0%, rgba(59,130,246,0.06) 100%);
  border: 1px solid rgba(212,160,23,0.2);
  border-radius: 16px;
  padding: 28px 32px;
  margin-bottom: 44px;
  position: relative;
  overflow: hidden;
}
.lng-spread-box::before {
  content: '';
  position: absolute; top: 0; left: 0; right: 0; height: 3px;
  background: linear-gradient(90deg, #d4a017, #3b82f6, transparent);
}
.lng-spread-grid {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  gap: 24px;
  margin: 20px 0;
}
@media (max-width: 680px) { .lng-spread-grid { grid-template-columns: 1fr; } }
.lng-spread-side { text-align: center; }
.lng-spread-price {
  font-size: 36px; font-weight: 800; line-height: 1;
  font-variant-numeric: tabular-nums;
}
.lng-spread-unit  { font-size: 12px; color: var(--muted); margin-top: 4px; }
.lng-spread-label { font-size: 10px; font-weight: 700; letter-spacing: 1.5px;
                    text-transform: uppercase; margin-bottom: 8px; }
.lng-spread-divider {
  display: flex; flex-direction: column; align-items: center; gap: 6px;
}
.lng-spread-diff {
  font-size: 20px; font-weight: 800; padding: 8px 16px;
  border-radius: 10px; font-variant-numeric: tabular-nums;
}
.lng-analysis-box {
  background: linear-gradient(135deg, #111827 0%, #0f172a 100%);
  border: 1px solid rgba(212,160,23,0.2);
  border-radius: 16px;
  padding: 30px 36px;
  margin-bottom: 44px;
  position: relative; overflow: hidden;
}
.lng-analysis-box::before {
  content: '';
  position: absolute; top: 0; left: 0; right: 0; height: 3px;
  background: linear-gradient(90deg, #d4a017, #3b82f6, transparent);
}
.lng-analysis-label {
  font-size: 10px; font-weight: 700; letter-spacing: 2px;
  text-transform: uppercase; color: var(--gold);
  margin-bottom: 22px; display: flex; align-items: center; gap: 8px;
}
.lng-analysis-label::before { content: '\\25B6'; font-size: 8px; }
.lng-analysis-para {
  font-size: 15px; color: #cbd5e1; line-height: 1.85;
  margin-bottom: 1.4em; font-weight: 400;
}
.lng-analysis-para:last-child { margin-bottom: 0; }
.lng-analysis-para strong { color: #fff; font-weight: 600; }
.lng-audience-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  margin-bottom: 44px;
}
@media (max-width: 700px) { .lng-audience-grid { grid-template-columns: 1fr; } }
.lng-audience-card {
  background: var(--card); border: 1px solid var(--border);
  border-radius: 14px; padding: 24px 22px;
}
.lng-audience-icon { font-size: 1.5rem; margin-bottom: 10px; }
.lng-audience-role { font-size: 11px; font-weight: 700; letter-spacing: 0.08em;
                     text-transform: uppercase; color: var(--gold); margin-bottom: 8px; }
.lng-audience-title { font-size: 14px; font-weight: 700; color: #e2e8f0; margin-bottom: 8px; }
.lng-audience-bullets { font-size: 12px; color: var(--muted); line-height: 1.8;
                        padding-left: 0; margin: 0; list-style: none; }
.lng-audience-bullets li::before { content: '\\2022 '; color: var(--gold); }
.lng-method-box {
  background: rgba(255,255,255,0.02);
  border: 1px solid rgba(255,255,255,0.06);
  border-radius: 14px; padding: 24px 28px; margin-bottom: 44px;
}
.lng-method-grid {
  display: grid; grid-template-columns: repeat(2, 1fr);
  gap: 20px; margin-top: 20px;
}
@media (max-width: 600px) { .lng-method-grid { grid-template-columns: 1fr; } }
.lng-method-item { font-size: 12px; color: var(--muted); line-height: 1.65; }
.lng-method-item strong { color: #e2e8f0; display: block; margin-bottom: 3px; }
.lng-wheel-grid {
  display: grid; grid-template-columns: repeat(3,1fr);
  gap: 14px; margin-bottom: 44px;
}
@media (max-width: 600px) { .lng-wheel-grid { grid-template-columns: 1fr 1fr; } }
.lng-wheel-link {
  display: flex; flex-direction: column; align-items: center;
  justify-content: center; text-align: center; gap: 8px;
  background: var(--card); border: 1px solid var(--border);
  border-radius: 14px; padding: 20px 12px;
  text-decoration: none; color: inherit;
  transition: border-color 0.2s, box-shadow 0.2s, transform 0.2s;
}
.lng-wheel-link:hover {
  border-color: rgba(212,160,23,0.4);
  box-shadow: 0 0 24px rgba(212,160,23,0.08);
  transform: translateY(-2px);
}
.lng-wheel-icon  { font-size: 1.7rem; }
.lng-wheel-label { font-size: 11px; font-weight: 700; letter-spacing: 0.08em;
                   text-transform: uppercase; color: var(--gold); }
.lng-wheel-desc  { font-size: 11px; color: var(--muted); line-height: 1.4; }
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
.lng-flow-table {
  width:100%; border-collapse:collapse; font-size:12px; margin-top:12px;
}
.lng-flow-table th {
  font-size:10px; font-weight:700; letter-spacing:1px; text-transform:uppercase;
  color:var(--muted); padding:6px 12px; text-align:left;
  border-bottom:1px solid rgba(255,255,255,0.06);
}
.lng-flow-table td {
  padding:9px 12px; border-bottom:1px solid rgba(255,255,255,0.03); color:#cbd5e1;
}
.lng-flow-table tr:last-child td { border-bottom: none; }
.lng-flow-table .upval { color: #22c55e; font-weight: 700; }
.lng-flow-table .dnval { color: #ef4444; font-weight: 700; }
.lng-flow-table .neut  { color: #eab308; font-weight: 700; }
"""


# ── Data Fetcher ──────────────────────────────────────────────────────────────

_RISK_LEVEL_ORDER = ["LOW", "MODERATE", "ELEVATED", "HIGH", "CRITICAL"]
_RISK_COLORS = {
    "CRITICAL": "#ef4444",
    "HIGH":     "#f97316",
    "ELEVATED": "#eab308",
    "MODERATE": "#3b82f6",
    "LOW":      "#22c55e",
}
_WEIGHT = {"war": 3, "supply_disruption": 2.5, "conflict": 2, "energy": 1, "military": 1.5, "geopolitical": 1}


def _score_to_risk(score: float) -> str:
    if score >= 30:   return "CRITICAL"
    if score >= 14:   return "HIGH"
    if score >= 6:    return "ELEVATED"
    if score >= 2:    return "MODERATE"
    return "LOW"


def _fetch_import_sources_intelligence(jkm_ttf_spread: float) -> list:
    """
    Read lng_import_sources from DB and enrich each row with:
    - Dynamic risk level from last 7 days of alert_events per scope_region
    - Most recent critical alert headline for that region
    - Cargo competition signal derived from JKM-TTF spread and flexibility
    """
    sources = execute_production_query(
        "SELECT id, origin, scope_region, est_annual_bcm_display, contract_type, "
        "flexibility, static_notes, sort_order "
        "FROM lng_import_sources WHERE active = TRUE ORDER BY sort_order ASC"
    ) or []

    # Fetch 7-day alert summary per region in one query
    alert_rows = execute_production_query(
        "SELECT scope_region, category, COUNT(*) as cnt, "
        "MAX(severity) as max_sev, "
        "MAX(headline) as top_headline "
        "FROM alert_events "
        "WHERE created_at >= NOW() - INTERVAL '7 days' "
        "GROUP BY scope_region, category"
    ) or []

    # Fetch top headline per region (most recent high-severity)
    headline_rows = execute_production_query(
        "SELECT DISTINCT ON (scope_region) scope_region, headline, category, created_at "
        "FROM alert_events "
        "WHERE created_at >= NOW() - INTERVAL '7 days' "
        "  AND severity >= 4 "
        "ORDER BY scope_region, severity DESC, created_at DESC"
    ) or []
    headline_map = {r["scope_region"]: dict(r) for r in headline_rows}

    # Group alert counts by region
    region_alerts: dict = {}
    for row in alert_rows:
        rgn = row["scope_region"]
        if rgn not in region_alerts:
            region_alerts[rgn] = {"score": 0.0, "total": 0}
        cat = (row.get("category") or "").lower()
        cnt = int(row.get("cnt") or 0)
        w   = _WEIGHT.get(cat, 0.5)
        region_alerts[rgn]["score"] += cnt * w
        region_alerts[rgn]["total"] += cnt

    enriched = []
    for src in sources:
        src = dict(src)
        region = src.get("scope_region", "Global")
        flex   = (src.get("flexibility") or "MEDIUM").upper()

        # Risk from alerts for this region
        agg = region_alerts.get(region, {"score": 0.0, "total": 0})
        # Global region: average of all regions
        if region == "Global":
            all_scores = [v["score"] for v in region_alerts.values()]
            agg = {"score": (sum(all_scores) / len(all_scores)) if all_scores else 0.0, "total": 0}
        risk_level = _score_to_risk(agg["score"])
        alert_count = agg["total"]

        # Top headline for region
        hl_data = headline_map.get(region) or {}
        if not hl_data and region == "Global":
            # Use the region with most alerts as global headline
            top_rgn = max(region_alerts, key=lambda k: region_alerts[k]["score"], default=None)
            hl_data = headline_map.get(top_rgn, {}) if top_rgn else {}
        top_headline  = (hl_data.get("headline") or "")[:120]
        top_hl_cat    = (hl_data.get("category") or "").title()

        # Cargo competition signal from JKM-TTF spread × flexibility
        if flex == "HIGH":
            # Fully spot-exposed: spread has full impact
            if jkm_ttf_spread > 5:   cargo_sig = "CRITICAL"
            elif jkm_ttf_spread > 3: cargo_sig = "HIGH"
            elif jkm_ttf_spread > 1: cargo_sig = "ELEVATED"
            else:                    cargo_sig = "LOW"
        elif flex == "MEDIUM":
            if jkm_ttf_spread > 5:   cargo_sig = "HIGH"
            elif jkm_ttf_spread > 3: cargo_sig = "ELEVATED"
            elif jkm_ttf_spread > 1: cargo_sig = "MODERATE"
            else:                    cargo_sig = "LOW"
        else:  # LOW flexibility — contract bound
            cargo_sig = "LOW"

        src["risk_level"]    = risk_level
        src["risk_color"]    = _RISK_COLORS.get(risk_level, "#3b82f6")
        src["alert_count"]   = alert_count
        src["top_headline"]  = top_headline
        src["top_hl_cat"]    = top_hl_cat
        src["cargo_signal"]  = cargo_sig
        src["cargo_color"]   = _RISK_COLORS.get(cargo_sig, "#3b82f6")
        enriched.append(src)

    return enriched


def _fetch_lng_data() -> dict:
    """Fetch all data needed for the LNG page from production DB."""

    # LNG latest row
    lng_latest = execute_production_one(
        "SELECT date, jkm_price, jkm_change_24h, jkm_change_pct "
        "FROM lng_price_snapshots ORDER BY date DESC LIMIT 1"
    )

    # LNG full history for trend chart
    lng_history = execute_production_query(
        "SELECT date, jkm_price, jkm_change_24h FROM lng_price_snapshots ORDER BY date ASC"
    ) or []

    # LNG last 30 days for recent bar chart
    lng_30d = execute_production_query(
        "SELECT date, jkm_price FROM lng_price_snapshots ORDER BY date DESC LIMIT 30"
    ) or []
    lng_30d = list(reversed(lng_30d))

    # LNG 7-day momentum for supply dynamics
    lng_7d = execute_production_query(
        "SELECT date, jkm_price FROM lng_price_snapshots ORDER BY date DESC LIMIT 7"
    ) or []

    # TTF for spread comparison — use all available for chart
    ttf_history = execute_production_query(
        "SELECT date, ttf_price FROM ttf_gas_snapshots ORDER BY date ASC"
    ) or []
    ttf_latest = execute_production_one(
        "SELECT date, ttf_price FROM ttf_gas_snapshots ORDER BY date DESC LIMIT 1"
    )
    ttf_prev = execute_production_one(
        "SELECT ttf_price FROM ttf_gas_snapshots ORDER BY date DESC LIMIT 1 OFFSET 1"
    )

    # Storage for context
    storage_row = execute_production_one(
        "SELECT eu_storage_percent, seasonal_norm, risk_band, date "
        "FROM gas_storage_snapshots ORDER BY date DESC LIMIT 1"
    )

    # GERI
    geri_row = execute_production_one(
        "SELECT date, value, band FROM intel_indices_daily "
        "WHERE index_id='global:geo_energy_risk' ORDER BY date DESC LIMIT 1"
    )

    # EERI
    eeri_row = execute_production_one(
        "SELECT date, value, band FROM reri_indices_daily "
        "WHERE index_id='europe:eeri' ORDER BY date DESC LIMIT 1"
    )

    # Alert context for AI analysis (72h)
    alert_cats = execute_production_query(
        "SELECT category, COUNT(*) as cnt FROM alert_events "
        "WHERE created_at >= NOW() - INTERVAL '72 hours' "
        "GROUP BY category ORDER BY cnt DESC LIMIT 8"
    ) or []
    alert_context = (
        "Alert categories (last 72h): " + ", ".join(
            f"{r['category']}={r['cnt']}" for r in alert_cats
        ) if alert_cats else "No recent alerts."
    )

    # Per-region alert counts for Supply Dynamics cards (7 days)
    region_alert_counts = execute_production_query(
        "SELECT scope_region, COUNT(*) as cnt FROM alert_events "
        "WHERE created_at >= NOW() - INTERVAL '7 days' "
        "GROUP BY scope_region ORDER BY cnt DESC"
    ) or []
    region_count_map = {r["scope_region"]: int(r["cnt"]) for r in region_alert_counts}
    asian_demand_alerts = (
        region_count_map.get("Asia", 0) +
        region_count_map.get("Middle East", 0)
    )
    na_alerts = region_count_map.get("North America", 0)
    europe_alerts = region_count_map.get("Europe", 0)

    # YTD stats from history
    all_prices = [float(r["jkm_price"]) for r in lng_history if r.get("jkm_price")]
    ytd_low  = min(all_prices) if all_prices else 0.0
    ytd_high = max(all_prices) if all_prices else 0.0

    # 7-day JKM momentum
    if len(lng_7d) >= 2:
        newest = float(lng_7d[0]["jkm_price"] or 0)
        oldest = float(lng_7d[-1]["jkm_price"] or 0)
        jkm_7d_pct = ((newest - oldest) / oldest * 100) if oldest else 0.0
    else:
        jkm_7d_pct = 0.0

    return {
        "lng_latest":         lng_latest,
        "lng_history":        lng_history,
        "lng_30d":            lng_30d,
        "lng_7d":             lng_7d,
        "ttf_history":        ttf_history,
        "ttf_latest":         ttf_latest,
        "ttf_prev":           ttf_prev,
        "storage_row":        storage_row,
        "geri_row":           geri_row,
        "eeri_row":           eeri_row,
        "alert_context":      alert_context,
        "ytd_low":            ytd_low,
        "ytd_high":           ytd_high,
        "jkm_7d_pct":         jkm_7d_pct,
        "asian_demand_alerts": asian_demand_alerts,
        "na_alerts":          na_alerts,
        "europe_alerts":      europe_alerts,
    }


# ── HTML Builder ──────────────────────────────────────────────────────────────

def _build_lng_html(data: dict, analysis: str, today_str: str, import_sources: list = None) -> str:

    lng_row     = data["lng_latest"] or {}
    lng_history = data["lng_history"]
    lng_30d     = data["lng_30d"]
    ttf_history = data["ttf_history"]
    ttf_row     = data["ttf_latest"] or {}
    storage_row = data["storage_row"] or {}
    geri_row    = data["geri_row"] or {}
    eeri_row    = data["eeri_row"] or {}

    # ── Live dynamic fields ───────────────────────────────────────────────────
    jkm_7d_pct         = data.get("jkm_7d_pct", 0.0)
    asian_demand_alerts = data.get("asian_demand_alerts", 0)
    na_alerts           = data.get("na_alerts", 0)
    europe_alerts       = data.get("europe_alerts", 0)

    # ── Core values ──────────────────────────────────────────────────────────
    jkm         = _safe_float(lng_row.get("jkm_price", 0))
    jkm_chg     = _safe_float(lng_row.get("jkm_change_24h", 0))
    jkm_chg_pct = _safe_float(lng_row.get("jkm_change_pct", 0))
    jkm_date    = lng_row.get("date", "")
    ytd_low     = data["ytd_low"]
    ytd_high    = data["ytd_high"]
    ytd_gain    = ((jkm / ytd_low - 1) * 100) if ytd_low else 0.0

    ttf         = _safe_float(ttf_row.get("ttf_price", 0))
    ttf_date    = ttf_row.get("date", "")

    storage_pct  = _safe_float(storage_row.get("eu_storage_percent", 0))
    storage_norm = _safe_float(storage_row.get("seasonal_norm", 0))

    geri_val  = int(round(_safe_float(geri_row.get("value", 0))))
    geri_band = (geri_row.get("band") or "LOW").upper()
    geri_color = BAND_COLORS.get(geri_band, "#3b82f6")

    eeri_val  = int(round(_safe_float(eeri_row.get("value", 0))))
    eeri_band = (eeri_row.get("band") or "MODERATE").upper()
    eeri_color = BAND_COLORS.get(eeri_band, "#f97316")

    # ── Spread calculation ───────────────────────────────────────────────────
    # Convert TTF €/MWh → $/MMBtu: €/MWh × 0.29307 MWh/MMBtu × EUR/USD
    ttf_as_mmbtu = ttf * _MMBTU_TO_MWH * _EUR_USD
    jkm_ttf_spread = jkm - ttf_as_mmbtu  # positive = JKM premium
    spread_color = "#ef4444" if jkm_ttf_spread > 3 else "#eab308" if jkm_ttf_spread > 0 else "#22c55e"
    spread_label = "JKM Premium" if jkm_ttf_spread > 0 else "TTF Premium"
    spread_meaning = (
        "Asian markets paying more — Europe competes for cargoes"
        if jkm_ttf_spread > 2 else
        "Marginal Asia-Europe arb — cargo splits balanced"
        if jkm_ttf_spread > 0 else
        "Europe at premium — Atlantic LNG flows westward"
    )

    # YTD range pct position
    ytd_range = ytd_high - ytd_low
    ytd_pos = int(round(((jkm - ytd_low) / ytd_range * 100))) if ytd_range else 50

    # ── Colour helpers ───────────────────────────────────────────────────────
    jkm_color = "#d4a017"
    chg_color = _chg_color(jkm_chg)
    chg_arrow = _arrow(jkm_chg)

    # ── SVG charts ───────────────────────────────────────────────────────────
    trend_svg = _build_jkm_trend_svg(lng_history, ttf_rows=ttf_history, width=680, height=210)
    bar_svg   = _build_price_bar_chart(lng_30d, color="#d4a017", val_key="jkm_price", label_key="date", width=680, height=100)

    # ── Analysis paragraphs ──────────────────────────────────────────────────
    paras = [p.strip() for p in analysis.split("\n\n") if p.strip()]
    if not paras:
        paras = [analysis.strip()]
    analysis_html = "".join(
        f'<p class="lng-analysis-para">{_html.escape(p)}</p>' for p in paras
    )

    # ── JSON-LD ──────────────────────────────────────────────────────────────
    json_ld = json.dumps({
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Article",
                "headline": "Europe LNG Supply & Demand — Live Market Intelligence",
                "description": (
                    f"Live JKM LNG spot price at ${jkm:.2f}/MMBtu. "
                    f"JKM-TTF energy-equivalent spread: ${jkm_ttf_spread:+.2f}/MMBtu. "
                    "Atlantic basin cargo flow analysis, European import dynamics, "
                    "and storage refill implications for energy traders and analysts."
                ),
                "url": f"{BASE_URL}/data/europe-lng-supply-demand",
                "dateModified": str(_date.today()),
                "datePublished": "2025-01-01",
                "author":    {"@type": "Organization", "name": "EnergyRiskIQ"},
                "publisher": {
                    "@type": "Organization",
                    "name": "EnergyRiskIQ",
                    "logo": {"@type": "ImageObject", "url": f"{BASE_URL}/static/logo.png"},
                },
                "mainEntityOfPage": {"@type": "WebPage", "@id": f"{BASE_URL}/data/europe-lng-supply-demand"},
                "about": [
                    {"@type": "Thing", "name": "LNG Supply and Demand Europe"},
                    {"@type": "Thing", "name": "JKM LNG Price"},
                    {"@type": "Thing", "name": "TTF Natural Gas"},
                    {"@type": "Thing", "name": "European Energy Security"},
                    {"@type": "Thing", "name": "Atlantic Basin LNG Trade"},
                ],
            },
            {
                "@type": "Dataset",
                "name": "JKM LNG Spot Price — Daily",
                "description": "Daily JKM (Japan Korea Marker) LNG spot price in $/MMBtu, with 24h change and YTD range. Sourced and processed by EnergyRiskIQ.",
                "url": f"{BASE_URL}/data/europe-lng-supply-demand",
                "creator":    {"@type": "Organization", "name": "EnergyRiskIQ"},
                "temporalCoverage": "2026-01-13/..",
                "spatialCoverage":  "Global (LNG Atlantic Basin / Europe focus)",
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Home",       "item": BASE_URL},
                    {"@type": "ListItem", "position": 2, "name": "Data",       "item": f"{BASE_URL}/data"},
                    {"@type": "ListItem", "position": 3, "name": "Europe LNG Supply & Demand",
                     "item": f"{BASE_URL}/data/europe-lng-supply-demand"},
                ],
            },
        ],
    }, indent=2)

    # ── LNG flow reference table rows — DYNAMIC from DB + live alert intelligence
    import_sources = import_sources or []

    # Flexibility badge labels
    flex_label = {"HIGH": "Spot-exposed", "MEDIUM": "Partially flexible", "LOW": "Contract-bound"}
    flex_color = {"HIGH": "#f97316", "MEDIUM": "#eab308", "LOW": "#3b82f6"}

    flow_rows_html = ""
    if import_sources:
        for src in import_sources:
            origin    = _html.escape(src.get("origin", ""))
            vol       = _html.escape(src.get("est_annual_bcm_display", "—"))
            ctype     = _html.escape(src.get("contract_type", ""))
            notes     = _html.escape(src.get("static_notes", ""))
            flex      = (src.get("flexibility") or "MEDIUM").upper()
            risk_lvl  = src.get("risk_level", "LOW")
            risk_col  = src.get("risk_color", "#22c55e")
            cargo_sig = src.get("cargo_signal", "LOW")
            cargo_col = src.get("cargo_color", "#22c55e")
            headline  = _html.escape((src.get("top_headline") or "No significant alerts in past 7 days")[:120])
            hl_cat    = _html.escape(src.get("top_hl_cat") or "")
            al_cnt    = int(src.get("alert_count") or 0)
            fl_lbl    = flex_label.get(flex, flex)
            fl_col    = flex_color.get(flex, "#94a3b8")

            flow_rows_html += f"""<tr>
              <td style="font-weight:600;color:#e2e8f0;vertical-align:top;">
                {origin}
                <div style="font-size:10px;color:#475569;margin-top:3px;">{ctype}</div>
              </td>
              <td style="vertical-align:top;">
                <span style="color:#d4a017;font-weight:700;">{vol}</span>
              </td>
              <td style="vertical-align:top;padding:9px 12px;">
                <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:5px;">
                  <span style="font-size:9px;font-weight:700;letter-spacing:0.8px;
                    padding:2px 8px;border-radius:10px;text-transform:uppercase;
                    background:{risk_col}1a;color:{risk_col};border:1px solid {risk_col}44;">
                    &#9888; {risk_lvl}
                  </span>
                  <span style="font-size:9px;font-weight:700;letter-spacing:0.8px;
                    padding:2px 8px;border-radius:10px;text-transform:uppercase;
                    background:{fl_col}1a;color:{fl_col};border:1px solid {fl_col}44;">
                    {fl_lbl}
                  </span>
                  <span style="font-size:9px;font-weight:700;letter-spacing:0.8px;
                    padding:2px 8px;border-radius:10px;text-transform:uppercase;
                    background:{cargo_col}1a;color:{cargo_col};border:1px solid {cargo_col}44;">
                    Cargo competition: {cargo_sig}
                  </span>
                </div>
                <div style="font-size:11px;color:#94a3b8;margin-bottom:4px;">{notes}</div>
                {'<div style="font-size:10px;color:#64748b;font-style:italic;margin-top:4px;">' + (f'&#128680; {hl_cat}: ' if hl_cat else '') + f'{headline}</div>' if headline else ''}
                {'<div style="font-size:10px;color:#334155;margin-top:2px;">' + str(al_cnt) + ' alerts in last 7 days</div>' if al_cnt > 0 else ''}
              </td>
            </tr>"""
    else:
        # Fallback if DB not yet populated
        for origin, vol, note in [
            ("United States (USGC)", "~55 bcm/yr", "Dominant flexible supplier — Sabine Pass, Corpus Christi, Freeport, Cameron."),
            ("Qatar",                "~25 bcm/yr", "Long-term contracts; Hormuz transit risk."),
            ("Norway",               "~5 bcm/yr",  "Europe's only indigenous LNG source."),
            ("Algeria & Egypt",      "~20 bcm/yr", "Key for Southern Europe — Spain, Italy, Greece."),
            ("Nigeria & Angola",     "~15 bcm/yr", "Spot-market cargoes; Asian competition elevated."),
            ("Russia (Yamal LNG)",   "~15 bcm/yr", "Politically sensitive; EU sanctions debate ongoing."),
        ]:
            flow_rows_html += f"""<tr>
              <td style="font-weight:600;color:#e2e8f0;">{_html.escape(origin)}</td>
              <td style="color:#d4a017;font-weight:700;">{vol}</td>
              <td style="font-size:11px;color:#94a3b8;">{_html.escape(note)}</td>
            </tr>"""

    # ── Page HTML ─────────────────────────────────────────────────────────────
    return f"""<script>
var l=document.getElementById('snap-loader');
if(l){{l.style.display='none';}}
document.body.style.overflow='';
</script>

<style>{_LNG_CSS}</style>

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
      <a href="/indices/global-energy-risk-index"  style="font-size:13px;color:#94a3b8;text-decoration:none;">GERI</a>
      <a href="/indices/europe-energy-risk-index"  style="font-size:13px;color:#94a3b8;text-decoration:none;">EERI</a>
      <a href="/indices/europe-gas-stress-index"   style="font-size:13px;color:#94a3b8;text-decoration:none;">EGSI</a>
      <a href="/gas-storage-levels-in-europe"      style="font-size:13px;color:#94a3b8;text-decoration:none;">Storage</a>
      <a href="/users" class="cta-btn-nav">Get Free Access</a>
    </div>
  </div>
</nav>

<!-- HERO -->
<header class="hero">
  <div class="hero-date">&#128200; Live Intelligence &nbsp;&bull;&nbsp; {today_str} &nbsp;&bull;&nbsp; JKM Spot Data</div>
  <h1 style="max-width:860px;margin:0 auto 0.9rem;">
    Europe LNG Supply &amp; Demand
  </h1>
  <h2 style="font-size:1.05rem;font-weight:400;color:#94a3b8;line-height:1.75;
             max-width:680px;margin:0 auto 1.5rem;">
    JKM spot at <strong style="color:{jkm_color}">${jkm:.2f}/MMBtu</strong>
    &mdash; <strong style="color:{spread_color}">${abs(jkm_ttf_spread):.2f}/MMBtu {spread_label} over TTF</strong>.
    Atlantic basin cargo flows, Asian demand competition,
    and what it means for European gas supply security.
  </h2>
  <div style="display:flex;justify-content:center;gap:1rem;flex-wrap:wrap;margin-top:1.2rem;">
    <span style="font-size:12px;font-weight:600;color:{jkm_color};
      border:1px solid {jkm_color}33;border-radius:20px;padding:4px 14px;">
      JKM ${jkm:.2f}/MMBtu &bull; {chg_arrow} {jkm_chg:+.2f} ({jkm_chg_pct:+.2f}%)
    </span>
    <span style="font-size:12px;font-weight:600;color:#3b82f6;
      border:1px solid rgba(59,130,246,0.3);border-radius:20px;padding:4px 14px;">
      TTF &euro;{ttf:.2f}/MWh &bull; Equiv. ${ttf_as_mmbtu:.2f}/MMBtu
    </span>
    <span style="font-size:12px;font-weight:600;color:{geri_color};
      border:1px solid {geri_color}33;border-radius:20px;padding:4px 14px;">
      GERI {geri_val}/100 &bull; {geri_band}
    </span>
  </div>
</header>

<main class="page-body">

<!-- ── SECTION: LIVE METRICS ─────────────────────────────────────────────── -->
<div class="section-label" style="margin-bottom:20px;">&#128268; Live LNG Market Metrics &mdash; {today_str}</div>

<div class="lng-metric-grid">
  <div class="lng-metric-card gold">
    <div class="lng-label">JKM Spot Price</div>
    <div class="lng-value" style="color:{jkm_color}"><sup style="font-size:16px;font-weight:600;vertical-align:top;margin-top:6px;">$</sup>{jkm:.2f}</div>
    <div class="lng-sub">per MMBtu &bull; {chg_arrow} <span style="color:{chg_color}">{jkm_chg:+.2f} ({jkm_chg_pct:+.2f}%)</span> 24h</div>
  </div>
  <div class="lng-metric-card {'red' if jkm_ttf_spread > 3 else 'amber' if jkm_ttf_spread > 0 else 'green'}">
    <div class="lng-label">JKM–TTF Spread</div>
    <div class="lng-value" style="color:{spread_color}"><sup style="font-size:16px;font-weight:600;vertical-align:top;margin-top:6px;">{'+$' if jkm_ttf_spread >= 0 else '-$'}</sup>{abs(jkm_ttf_spread):.2f}</div>
    <div class="lng-sub">{spread_label} &bull; energy-equivalent basis</div>
  </div>
  <div class="lng-metric-card blue">
    <div class="lng-label">TTF Natural Gas</div>
    <div class="lng-value" style="color:#3b82f6"><sup style="font-size:16px;font-weight:600;vertical-align:top;margin-top:6px;">&euro;</sup>{ttf:.2f}</div>
    <div class="lng-sub">per MWh &bull; equiv. ${ttf_as_mmbtu:.2f}/MMBtu</div>
  </div>
  <div class="lng-metric-card {'amber' if ytd_pos > 70 else 'blue'}">
    <div class="lng-label">YTD Range</div>
    <div class="lng-value" style="color:#e2e8f0;font-size:22px;padding-top:6px;">${ytd_low:.2f}&ndash;${ytd_high:.2f}</div>
    <div class="lng-sub">per MMBtu &bull; YTD gain: <span style="color:{'#22c55e' if ytd_gain > 0 else '#ef4444'}">{ytd_gain:+.1f}%</span></div>
  </div>
</div>

<!-- ── SECTION: JKM–TTF SPREAD INTELLIGENCE ───────────────────────────────── -->
<div class="section-label" style="margin-bottom:20px;">&#128257; JKM–TTF Spread — The Arbitrage Signal That Drives European Imports</div>

<div class="lng-spread-box">
  <p style="font-size:13px;color:#94a3b8;margin:0 0 6px;">
    When JKM trades at a premium to TTF on an energy-equivalent basis, LNG producers
    systematically prefer to route Atlantic-basin cargoes to Asia. This is the most direct
    supply constraint on European LNG imports and the clearest leading indicator for TTF price pressure.
  </p>
  <div class="lng-spread-grid">
    <div class="lng-spread-side">
      <div class="lng-spread-label" style="color:#d4a017;">JKM — Asian Benchmark</div>
      <div class="lng-spread-price" style="color:#d4a017;">${jkm:.2f}</div>
      <div class="lng-spread-unit">per MMBtu &bull; Japan/Korea Marker</div>
      <div style="font-size:11px;color:#475569;margin-top:8px;">
        &#127981; South Korea, Japan, China LNG demand
      </div>
    </div>
    <div class="lng-spread-divider">
      <div style="font-size:10px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:#475569;">Spread</div>
      <div class="lng-spread-diff" style="background:{spread_color}1a;color:{spread_color};">
        {'+$' if jkm_ttf_spread >= 0 else '-$'}{abs(jkm_ttf_spread):.2f}
      </div>
      <div style="font-size:10px;color:#475569;text-align:center;max-width:120px;line-height:1.4;">{spread_meaning}</div>
    </div>
    <div class="lng-spread-side">
      <div class="lng-spread-label" style="color:#3b82f6;">TTF Equivalent</div>
      <div class="lng-spread-price" style="color:#3b82f6;">${ttf_as_mmbtu:.2f}</div>
      <div class="lng-spread-unit">per MMBtu equiv. &bull; &euro;{ttf:.2f}/MWh</div>
      <div style="font-size:11px;color:#475569;margin-top:8px;">
        &#127482;&#127466; European gas market benchmark
      </div>
    </div>
  </div>
  <div style="border-top:1px solid rgba(255,255,255,0.05);padding-top:16px;margin-top:4px;">
    <div style="font-size:12px;color:#475569;line-height:1.7;">
      <strong style="color:#e2e8f0;">Arb threshold rule of thumb:</strong>
      When JKM trades more than ~$2/MMBtu above the TTF equivalent, the Atlantic basin arb
      systematically favours Asian destinations. At the current spread of
      <strong style="color:{spread_color}">${abs(jkm_ttf_spread):.2f}/MMBtu</strong>,
      European importers face
      {"<strong style='color:#ef4444;'>active competition</strong> from Asian buyers for available spot cargoes." if jkm_ttf_spread > 2 else
       "<strong style='color:#eab308;'>marginal competition</strong> — cargo routing decisions are on a case-by-case basis." if jkm_ttf_spread > 0 else
       "<strong style='color:#22c55e;'>a structural advantage</strong> — European netbacks are superior and cargo flows are tilted westward."}
    </div>
  </div>
</div>

<!-- ── SECTION: JKM PRICE TREND ───────────────────────────────────────────── -->
<div class="lng-chart-wrap">
  <div class="lng-chart-title">&#128200; JKM Spot vs TTF Equivalent — Price Trend Since January 2026</div>
  <div style="overflow-x:auto;">{trend_svg}</div>
  <div style="margin-top:14px;font-size:11px;color:#334155;line-height:1.6;">
    Gold line = JKM spot ($/MMBtu). Dashed blue = TTF converted to $/MMBtu at {_MMBTU_TO_MWH:.3f} MWh/MMBtu &times; EUR/USD {_EUR_USD:.2f}.
    The gap between the two lines is the real-time arbitrage signal for Atlantic basin cargo routing.
    Source: EnergyRiskIQ proprietary LNG price feed.
  </div>
</div>

<!-- ── SECTION: RECENT 30-DAY JKM ─────────────────────────────────────────── -->
<div class="lng-chart-wrap" style="margin-bottom:44px;">
  <div class="lng-chart-title">&#128248; JKM — Last 30 Days</div>
  <div style="overflow-x:auto;">{bar_svg}</div>
</div>

<!-- ── SECTION: SUPPLY DYNAMICS ───────────────────────────────────────────── -->
<div class="section-label" style="margin-bottom:20px;">&#128268; European LNG Supply Dynamics — Key Market Drivers</div>

<div class="lng-three-col">
  <div class="lng-intel-card">
    <div class="lng-intel-icon">&#127979;</div>
    <div class="lng-intel-title">Asian Demand Competition</div>
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin:6px 0 10px;">
      <span style="font-size:10px;font-weight:700;padding:2px 8px;border-radius:10px;
        background:{'rgba(239,68,68,0.12)' if asian_demand_alerts > 50 else 'rgba(234,179,8,0.12)' if asian_demand_alerts > 20 else 'rgba(59,130,246,0.12)'};
        color:{'#ef4444' if asian_demand_alerts > 50 else '#eab308' if asian_demand_alerts > 20 else '#3b82f6'};">
        {asian_demand_alerts} geopolitical alerts / 7d
      </span>
      <span style="font-size:10px;font-weight:700;padding:2px 8px;border-radius:10px;
        background:rgba(212,160,23,0.12);color:#d4a017;">
        JKM {jkm_7d_pct:+.1f}% / 7d
      </span>
    </div>
    <div class="lng-intel-body">
      Japan, South Korea, and China are Europe's primary competitors for Atlantic-basin LNG cargoes.
      JKM is currently at <strong style="color:#d4a017">${jkm:.2f}/MMBtu</strong> —
      {'up ' + f'{jkm_7d_pct:+.1f}% over the past 7 days, signalling strengthening Asian demand.' if jkm_7d_pct > 1 else
       'down ' + f'{abs(jkm_7d_pct):.1f}% over the past 7 days, indicating some demand softening in Asia.' if jkm_7d_pct < -1 else
       'broadly flat over the past 7 days, suggesting balanced near-term Asian demand.'}
      There are currently <strong>{asian_demand_alerts}</strong> active geopolitical alerts across Middle East and Asia
      in the past 7 days — {'a high-alert environment that is directly impacting LNG shipping routes and cargo security.' if asian_demand_alerts > 50
      else 'an elevated risk environment requiring close monitoring of cargo routing.' if asian_demand_alerts > 20
      else 'a relatively contained backdrop for Asian cargo flows.'} The JKM–TTF spread of
      <strong style="color:{spread_color}">${abs(jkm_ttf_spread):.2f}/MMBtu</strong> currently
      {'places European importers under active cargo competition pressure.' if jkm_ttf_spread > 2
       else 'sits at a level where cargo routing decisions are finely balanced.' if jkm_ttf_spread > 0
       else 'favours European destinations, with Atlantic cargoes biased westward.'}
    </div>
  </div>
  <div class="lng-intel-card">
    <div class="lng-intel-icon">&#127824;</div>
    <div class="lng-intel-title">US Export Capacity — The Swing Supplier</div>
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin:6px 0 10px;">
      <span style="font-size:10px;font-weight:700;padding:2px 8px;border-radius:10px;
        background:rgba(212,160,23,0.12);color:#d4a017;">
        ~55 bcm/yr capacity
      </span>
      <span style="font-size:10px;font-weight:700;padding:2px 8px;border-radius:10px;
        background:{'rgba(239,68,68,0.12)' if jkm_ttf_spread > 3 else 'rgba(234,179,8,0.12)' if jkm_ttf_spread > 1 else 'rgba(34,197,94,0.12)'};
        color:{'#ef4444' if jkm_ttf_spread > 3 else '#eab308' if jkm_ttf_spread > 1 else '#22c55e'};">
        {'Asia pull HIGH' if jkm_ttf_spread > 3 else 'Asia pull MODERATE' if jkm_ttf_spread > 1 else 'Europe preferred'}
      </span>
      {('<span style="font-size:10px;font-weight:700;padding:2px 8px;border-radius:10px;background:rgba(234,179,8,0.12);color:#eab308;">' + str(na_alerts) + ' NA alerts / 7d</span>') if na_alerts > 0 else ''}
    </div>
    <div class="lng-intel-body">
      The United States Gulf Coast (Sabine Pass, Corpus Christi, Freeport, Cameron)
      has become Europe's largest LNG supplier since 2022, providing approximately
      <strong>55 bcm/year</strong> of flexible, destination-free volumes.
      At the current JKM–TTF spread of
      <strong style="color:{spread_color}">${abs(jkm_ttf_spread):.2f}/MMBtu</strong>,
      US producers {'have a structural incentive to divert Atlantic cargoes toward Asian buyers, which directly reduces European import availability.' if jkm_ttf_spread > 2
      else 'are making routing decisions on a cargo-by-cargo basis — European and Asian netbacks are competitive.' if jkm_ttf_spread > 0
      else 'find European netbacks more attractive, supporting a westward bias in US LNG cargo routing.'}
      {('There are currently <strong>' + str(na_alerts) + '</strong> North American geopolitical alerts in the past 7 days — monitor for any Gulf Coast terminal disruption signals.') if na_alerts > 0
       else 'No significant North American disruption alerts in the past 7 days.'}
    </div>
  </div>
  <div class="lng-intel-card">
    <div class="lng-intel-icon">&#127811;</div>
    <div class="lng-intel-title">Storage Refill — The Seasonal Clock</div>
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin:6px 0 10px;">
      <span style="font-size:10px;font-weight:700;padding:2px 8px;border-radius:10px;
        background:{'rgba(239,68,68,0.12)' if storage_pct < 30 else 'rgba(234,179,8,0.12)' if storage_pct < 50 else 'rgba(34,197,94,0.12)'};
        color:{'#ef4444' if storage_pct < 30 else '#eab308' if storage_pct < 50 else '#22c55e'};">
        EU Storage: {storage_pct:.1f}% full
      </span>
      <span style="font-size:10px;font-weight:700;padding:2px 8px;border-radius:10px;
        background:rgba(59,130,246,0.12);color:#3b82f6;">
        Target: 90% by Nov 1
      </span>
    </div>
    <div class="lng-intel-body">
      EU storage is currently at <strong style="color:{'#ef4444' if storage_pct < 30 else '#eab308' if storage_pct < 50 else '#22c55e'}">{storage_pct:.1f}%</strong>
      ({storage_norm:.1f}% seasonal norm).
      Europe must inject approximately <strong>{required_refill_gwh_display(storage_pct)}</strong>
      through to November 1 to reach the 90% EU target — a
      {'demanding refill requirement that makes every lost LNG cargo to Asia directly consequential for winter supply security.' if storage_pct < 35
       else 'significant injection programme where LNG availability remains a key variable alongside Norwegian pipeline flows.' if storage_pct < 55
       else 'manageable injection target, though LNG availability remains a key input into the seasonal gas balance.'}
      When the JKM–TTF spread is elevated — as it is today at <strong style="color:{spread_color}">${abs(jkm_ttf_spread):.2f}/MMBtu</strong> —
      the storage refill and LNG import dynamics create a direct feedback loop into TTF forward pricing.
    </div>
  </div>
</div>

<!-- ── SECTION: IMPORT SOURCES TABLE ──────────────────────────────────────── -->
<div class="section-label" style="margin-bottom:20px;">&#127758; European LNG Import Sources — Origin Breakdown</div>

<div style="background:var(--card);border:1px solid var(--border);border-radius:16px;
            padding:24px 28px;margin-bottom:44px;">
  <p style="font-size:13px;color:#94a3b8;line-height:1.7;margin:0 0 4px;">
    Europe's LNG import mix has fundamentally restructured since 2022, with US Gulf Coast
    now the dominant origin. Understanding the flexibility, contract structure, and
    geopolitical risk of each supply corridor is essential for scenario analysis.
  </p>
  <table class="lng-flow-table">
    <thead>
      <tr>
        <th>Origin &amp; Contract Type</th>
        <th>Est. Volume</th>
        <th>Live Intelligence — Risk &bull; Flexibility &bull; Cargo Competition &bull; Today's Alerts</th>
      </tr>
    </thead>
    <tbody>
      {flow_rows_html}
    </tbody>
  </table>
  <div style="margin-top:12px;font-size:10px;color:#334155;">
    Volumes are approximate annual estimates based on 2024–2025 trade data.
    Actual spot flows vary with JKM–TTF arbitrage, long-term contract nominations, and operational availability.
  </div>
</div>

<!-- ── SECTION: CUSTOM ALGORITHM INTELLIGENCE ────────────────────────────── -->
<div class="section-label" style="margin-bottom:20px;">&#128200; Market Intelligence — Custom Algorithm Analysis</div>

<div class="lng-analysis-box">
  <div class="lng-analysis-label">EnergyRiskIQ Proprietary Analysis &bull; {today_str}</div>
  {analysis_html}
  <div style="margin-top:20px;padding-top:16px;border-top:1px solid rgba(255,255,255,0.05);
              font-size:10px;color:#334155;line-height:1.5;">
    This analysis is produced by EnergyRiskIQ's custom market intelligence algorithms
    using live JKM price data, TTF spread calculations, EU storage context, and
    geopolitical alert signals. For informational purposes only — not financial advice.
    &bull; JKM Source: OilPrice.com via EnergyRiskIQ feed
    &bull; TTF: Yahoo Finance
    &bull; Storage: AGSI+ / GIE
  </div>
</div>

<!-- ── SECTION: FOR TRADERS & ANALYSTS ────────────────────────────────────── -->
<div class="section-label" style="margin-bottom:20px;">&#127919; How Professionals Use This Intelligence</div>

<div class="lng-audience-grid">
  <div class="lng-audience-card">
    <div class="lng-audience-icon">&#128200;</div>
    <div class="lng-audience-role">Energy Traders</div>
    <div class="lng-audience-title">JKM–TTF Arbitrage &amp; TTF Position Sizing</div>
    <ul class="lng-audience-bullets">
      <li>Monitor the JKM–TTF spread daily as the primary European LNG import signal</li>
      <li>Use spread widening as a leading indicator for TTF front-month bullish pressure</li>
      <li>Track US Gulf Coast feed gas supply for cargo availability signals</li>
      <li>Calibrate TTF forward curve positioning against the LNG import outlook</li>
      <li>Identify seasonal JKM demand cycles (Asian summer/winter peaks) and trade the arbitrage window</li>
    </ul>
  </div>
  <div class="lng-audience-card">
    <div class="lng-audience-icon">&#128196;</div>
    <div class="lng-audience-role">Risk Managers &amp; Analysts</div>
    <div class="lng-audience-title">Supply Security Scenario Modelling</div>
    <ul class="lng-audience-bullets">
      <li>Quantify the LNG import gap during high-Asian-demand scenarios</li>
      <li>Stress-test winter gas supply adequacy using JKM-driven cargo diversion models</li>
      <li>Assess how US Gulf Coast terminal outages affect European seasonal balances</li>
      <li>Correlate JKM price trajectory with EGSI-M and TTF volatility regime shifts</li>
      <li>Monitor geopolitical risk impact on Qatar, Nigeria, and Algerian supply corridors</li>
    </ul>
  </div>
</div>

<!-- ── SECTION: METHODOLOGY ────────────────────────────────────────────────── -->
<div class="section-label" style="margin-bottom:20px;">&#128214; Data &amp; Methodology</div>

<div class="lng-method-box">
  <p style="font-size:13px;color:#94a3b8;line-height:1.7;margin:0 0 16px;">
    EnergyRiskIQ's LNG intelligence layer is processed daily through our
    proprietary data pipeline, combining JKM spot prices, TTF market data,
    and geopolitical alert signals to produce a coherent supply-demand picture for European energy professionals.
  </p>
  <div class="lng-method-grid">
    <div class="lng-method-item">
      <strong>JKM Price Source</strong>
      The Japan Korea Marker (JKM) is the leading benchmark for spot LNG prices
      in the Asia-Pacific basin, assessed daily by Platts (S&amp;P Global Commodity Insights).
      EnergyRiskIQ sources JKM via OilPrice.com and proprietary scraping,
      updated daily within the morning London trading session.
    </div>
    <div class="lng-method-item">
      <strong>JKM–TTF Spread Calculation</strong>
      The energy-equivalent spread converts TTF (€/MWh) to $/MMBtu using the
      factor 1 MMBtu = {_MMBTU_TO_MWH} MWh, then applies a EUR/USD conversion rate
      (currently {_EUR_USD:.2f}). This allows direct comparison of European and Asian
      LNG netback values on a per-unit-energy basis — the standard arbitrage calculation
      used by LNG trading desks globally.
    </div>
    <div class="lng-method-item">
      <strong>Cargo Flow Intelligence</strong>
      LNG cargo routing decisions depend on a comparison of destination netbacks
      (delivered price minus shipping cost). When Asian netbacks exceed European netbacks
      by more than the round-trip freight cost differential (~$0.50–1.50/MMBtu),
      Atlantic basin cargoes are systematically diverted eastward.
      EnergyRiskIQ tracks this spread daily as a leading supply constraint indicator.
    </div>
    <div class="lng-method-item">
      <strong>Update Frequency &amp; Coverage</strong>
      JKM spot data is updated daily. The page also incorporates live TTF prices
      (Yahoo Finance), EU gas storage data (AGSI+), and geopolitical alert signals
      from EnergyRiskIQ's 24/7 event ingestion pipeline — providing a fully integrated
      view of the European LNG supply-demand balance in near-real-time.
    </div>
  </div>
</div>

<!-- ── SECTION: INTELLIGENCE WHEEL ────────────────────────────────────────── -->
<div class="section-label" style="margin-bottom:20px;">&#128279; Explore EnergyRiskIQ Intelligence</div>

<div class="lng-wheel-grid">
  <a href="/indices/global-energy-risk-index" class="lng-wheel-link">
    <div class="lng-wheel-icon">&#127758;</div>
    <div class="lng-wheel-label">GERI</div>
    <div class="lng-wheel-desc">Global Energy Risk Index &bull; {geri_val}/100 &bull; {geri_band}</div>
  </a>
  <a href="/indices/europe-energy-risk-index" class="lng-wheel-link">
    <div class="lng-wheel-icon">&#9889;</div>
    <div class="lng-wheel-label">EERI</div>
    <div class="lng-wheel-desc">Europe Energy Risk Index &bull; {eeri_val}/100 &bull; {eeri_band}</div>
  </a>
  <a href="/indices/europe-gas-stress-index" class="lng-wheel-link">
    <div class="lng-wheel-icon">&#128168;</div>
    <div class="lng-wheel-label">EGSI</div>
    <div class="lng-wheel-desc">Europe Gas Stress Index</div>
  </a>
  <a href="/gas-storage-levels-in-europe" class="lng-wheel-link">
    <div class="lng-wheel-icon">&#128268;</div>
    <div class="lng-wheel-label">Gas Storage</div>
    <div class="lng-wheel-desc">EU Storage {storage_pct:.1f}% &bull; vs Norm {storage_norm:.1f}%</div>
  </a>
  <a href="/data/global-energy-risk-forecast" class="lng-wheel-link">
    <div class="lng-wheel-icon">&#127919;</div>
    <div class="lng-wheel-label">Forecast</div>
    <div class="lng-wheel-desc">24H Brent &amp; TTF price outlook</div>
  </a>
  <a href="/data/jkm-lng-spot-price" class="lng-wheel-link">
    <div class="lng-wheel-icon">&#9875;</div>
    <div class="lng-wheel-label">JKM LNG</div>
    <div class="lng-wheel-desc">Japan Korea Marker spot price &bull; daily data</div>
  </a>
  <a href="/users" class="lng-wheel-link">
    <div class="lng-wheel-icon">&#128272;</div>
    <div class="lng-wheel-label">Free Access</div>
    <div class="lng-wheel-desc">Full dashboard &bull; GERI, EERI, EGSI, Alerts</div>
  </a>
</div>

<!-- ── SECTION: CITATION ───────────────────────────────────────────────────── -->
<div class="section-label" style="margin-bottom:20px;">&#128196; Citation &amp; Reference</div>
<div class="snap-cite-card" style="margin-bottom:44px;">
  <h3>How to Cite This Page</h3>
  <p class="snap-cite-desc">
    This page is updated daily with fresh data from live production pipelines.
    To reference this intelligence in research, journalism, or professional reports,
    use the citation below.
  </p>
  <div class="snap-cite-code-wrap">
    <pre class="snap-cite-code">EnergyRiskIQ. (2026). <em>Europe LNG Supply &amp; Demand — Live Market Intelligence — {today_str}</em>.
Retrieved from <a href="{BASE_URL}/data/europe-lng-supply-demand">{BASE_URL}/data/europe-lng-supply-demand</a>
Data sources: OilPriceAPI (JKM), Yahoo Finance (TTF), AGSI+ / GIE (EU storage), EnergyRiskIQ risk pipeline.</pre>
    <button class="snap-cite-copy-btn" onclick="this.textContent='Copied!';setTimeout(()=>this.textContent='Copy',2000);navigator.clipboard&&navigator.clipboard.writeText('EnergyRiskIQ. (2026). Europe LNG Supply & Demand \u2014 Live Market Intelligence \u2014 {today_str}. Retrieved from {BASE_URL}/data/europe-lng-supply-demand')">Copy</button>
  </div>
  <div class="snap-cite-footer">
    Data sourced from: OilPriceAPI (JKM spot price), Yahoo Finance (TTF natural gas futures),
    AGSI+ / GIE (EU gas storage), EnergyRiskIQ internal risk scoring pipeline (GERI, EERI, EGSI-M, alert events).
    Custom algorithm analysis via proprietary EnergyRiskIQ analysis engine. <strong>Not financial advice.</strong>
    See <a href="{BASE_URL}/indices/global-energy-risk-index">GERI methodology</a> for full scoring detail.
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
      Real-time energy risk intelligence — LNG &bull; Gas Storage &bull; GERI &bull; EERI &bull; EGSI &bull; Alerts
    </div>
    <div style="display:flex;justify-content:center;gap:24px;flex-wrap:wrap;
                font-size:11px;margin-bottom:14px;">
      <a href="/indices/global-energy-risk-index"  style="color:#475569;text-decoration:none;">GERI</a>
      <a href="/indices/europe-energy-risk-index"  style="color:#475569;text-decoration:none;">EERI</a>
      <a href="/indices/europe-gas-stress-index"   style="color:#475569;text-decoration:none;">EGSI</a>
      <a href="/gas-storage-levels-in-europe"      style="color:#475569;text-decoration:none;">Gas Storage</a>
      <a href="/data/europe-lng-supply-demand"     style="color:#d4a017;text-decoration:none;">LNG Intelligence</a>
      <a href="/data/global-energy-risk-forecast"  style="color:#475569;text-decoration:none;">Forecast</a>
      <a href="/users"                             style="color:#475569;text-decoration:none;">Sign Up</a>
    </div>
    <div style="font-size:10px;color:#1e293b;">
      &copy; 2026 EnergyRiskIQ. Data for informational purposes only. Not financial advice.
    </div>
  </div>
</footer>

</body>
</html>"""


def required_refill_gwh_display(storage_pct: float) -> str:
    """Helper for inline f-string usage."""
    target = 90.0
    gap = target - storage_pct
    capacity_gwh = 1_100_000
    gap_gwh = (gap / 100) * capacity_gwh
    days = (_date(2026, 11, 1) - _date.today()).days
    if days > 0:
        rate = gap_gwh / days
        return f"~{gap_gwh:,.0f} GWh ({rate:,.0f} GWh/day)"
    return f"~{gap_gwh:,.0f} GWh"


# ── Main Route ─────────────────────────────────────────────────────────────────

@router.get("/data/europe-lng-supply-demand")
async def europe_lng_supply_demand():
    """
    Public SEO page: Europe LNG Supply & Demand — Live Market Intelligence.
    Streams loader immediately, fetches data, generates analysis, renders full page.
    """
    async def generate():
        yield _LNG_LOADER

        try:
            data = await asyncio.to_thread(_fetch_lng_data)
        except Exception as exc:
            logger.error(f"LNG page data fetch failed: {exc}", exc_info=True)
            yield (
                f"<script>var l=document.getElementById('snap-loader');"
                f"if(l)l.style.display='none';document.body.style.overflow='';</script>"
                f"<div style='color:#ef4444;padding:40px;font-family:sans-serif;background:#0b0f1a'>"
                f"<h2>Error loading LNG data</h2><p>{_html.escape(str(exc))}</p></div></body></html>"
            )
            return

        today_str = datetime.now(timezone.utc).strftime("%B %-d, %Y")

        lng_row    = data["lng_latest"] or {}
        ttf_row    = data["ttf_latest"] or {}
        storage_row = data["storage_row"] or {}
        geri_row   = data["geri_row"] or {}

        jkm         = _safe_float(lng_row.get("jkm_price", 0))
        jkm_chg     = _safe_float(lng_row.get("jkm_change_24h", 0))
        jkm_chg_pct = _safe_float(lng_row.get("jkm_change_pct", 0))
        ttf         = _safe_float(ttf_row.get("ttf_price", 0))
        ttf_mmbtu   = ttf * _MMBTU_TO_MWH * _EUR_USD
        spread      = jkm - ttf_mmbtu
        storage_pct = _safe_float(storage_row.get("eu_storage_percent", 30))
        geri_val    = int(round(_safe_float(geri_row.get("value", 0))))
        geri_band   = (geri_row.get("band") or "LOW").upper()

        # Run analysis engine + import sources intelligence in parallel
        analysis_task = asyncio.create_task(asyncio.to_thread(
            _run_lng_analysis,
            today_str,
            jkm, jkm_chg, jkm_chg_pct,
            data["ytd_low"], data["ytd_high"],
            ttf, spread,
            storage_pct,
            geri_val, geri_band,
            data["alert_context"],
        ))
        sources_task = asyncio.create_task(
            asyncio.to_thread(_fetch_import_sources_intelligence, spread)
        )

        analysis, import_sources = await asyncio.gather(
            analysis_task, sources_task, return_exceptions=True
        )
        if isinstance(analysis, Exception):
            logger.warning(f"Analysis engine failed: {analysis}")
            analysis = _LNG_ANALYSIS_FALLBACK
        if isinstance(import_sources, Exception):
            logger.warning(f"Import sources fetch failed: {import_sources}")
            import_sources = []

        html_body = _build_lng_html(data, analysis, today_str, import_sources=import_sources)
        yield html_body

    return StreamingResponse(generate(), media_type="text/html")
