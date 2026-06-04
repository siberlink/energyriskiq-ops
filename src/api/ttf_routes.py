"""
TTF Gas Price Today — Live Daily Update
Route: /data/ttf-gas-price-today
SEO-optimised European natural gas benchmark page: price, chart, snapshot, risk context, FAQ.
Data source: ttf_gas_snapshots (production DB) — 104 daily records.
"""
import io
import csv
import logging
from datetime import date as _date, timedelta

from fastapi import APIRouter
from fastapi.responses import StreamingResponse, Response

from src.db.db import execute_production_one, execute_production_query
from src.api.snapshot_routes import _PAGE_CSS, _LOADER_HTML, BAND_COLORS, _safe_float

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

def _fmt_date(d):
    try:
        return d.strftime("%-d %b %Y")
    except Exception:
        return str(d)

def _fmt_date_short(d):
    try:
        return d.strftime("%b %-d")
    except Exception:
        return str(d)[:6]

def _fmt_date_iso(d):
    try:
        return d.strftime("%Y-%m-%d")
    except Exception:
        return str(d)

def _ttf_status(chg_pct):
    """Returns (label, arrow_symbol, color) based on 24h % change."""
    if chg_pct > 1.5:
        return ("BULLISH",  "&#9650;", "#22c55e")
    elif chg_pct < -1.5:
        return ("BEARISH", "&#9660;", "#ef4444")
    else:
        return ("NEUTRAL", "&#8594;", "#eab308")


# ── SVG Line Chart Builder ────────────────────────────────────────────────────

def _build_ttf_chart_svg(rows, color="#3b82f6", W=700, H=220):
    """Server-side SVG line chart with area fill for TTF price history."""
    if not rows or len(rows) < 2:
        return '<div style="text-align:center;color:#475569;padding:40px 0;">No data available</div>'

    vals  = [float(r.get("ttf_price") or 0) for r in rows]
    dates = [r.get("date") for r in rows]
    n = len(vals)

    PAD_L, PAD_R, PAD_T, PAD_B = 54, 18, 16, 40
    cw = W - PAD_L - PAD_R
    ch = H - PAD_T - PAD_B

    vmin = min(vals) * 0.992
    vmax = max(vals) * 1.008
    rng  = vmax - vmin or 1

    def xp(i): return PAD_L + (i / (n - 1)) * cw
    def yp(v): return PAD_T + ch - ((v - vmin) / rng) * ch

    pts    = [(xp(i), yp(v)) for i, v in enumerate(vals)]
    path_d = f"M {pts[0][0]:.1f} {pts[0][1]:.1f}" + "".join(f" L {px:.1f} {py:.1f}" for px, py in pts[1:])
    area_d = path_d + f" L {pts[-1][0]:.1f} {PAD_T + ch:.1f} L {pts[0][0]:.1f} {PAD_T + ch:.1f} Z"

    y_svg = ""
    for i in range(5):
        v  = vmin + (vmax - vmin) * (i / 4)
        yc = yp(v)
        y_svg += (
            f'<line x1="{PAD_L}" y1="{yc:.1f}" x2="{W - PAD_R}" y2="{yc:.1f}" '
            f'stroke="rgba(255,255,255,0.05)" stroke-width="1"/>'
            f'<text x="{PAD_L - 6}" y="{yc + 4:.1f}" text-anchor="end" '
            f'font-size="10" fill="#475569" font-family="Inter,sans-serif">\u20ac{v:.1f}</text>'
        )

    x_svg = ""
    tick_count = min(6, n)
    step = max(1, (n - 1) // (tick_count - 1)) if tick_count > 1 else 1
    indices = list(range(0, n, step))
    if n - 1 not in indices:
        indices.append(n - 1)
    for i in indices:
        lbl = _fmt_date_short(dates[i])
        x_svg += (
            f'<text x="{xp(i):.1f}" y="{PAD_T + ch + 22}" text-anchor="middle" '
            f'font-size="9" fill="#475569" font-family="Inter,sans-serif">{lbl}</text>'
        )

    circles = ""
    if n <= 14:
        for i, (px, py) in enumerate(pts):
            circles += (
                f'<circle cx="{px:.1f}" cy="{py:.1f}" r="3.5" '
                f'fill="{color}" stroke="#0f172a" stroke-width="1.5"/>'
            )

    grad_id = f"ttf-area-{n}"
    return f"""<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" style="width:100%;display:block;overflow:visible">
  <defs>
    <linearGradient id="{grad_id}" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="{color}" stop-opacity="0.2"/>
      <stop offset="100%" stop-color="{color}" stop-opacity="0.01"/>
    </linearGradient>
  </defs>
  {y_svg}
  {x_svg}
  <path d="{area_d}" fill="url(#{grad_id})"/>
  <path d="{path_d}" fill="none" stroke="{color}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
  {circles}
</svg>"""


# ── Custom Algorithm — Daily Market Insight ───────────────────────────────────

def _generate_ttf_insight(latest_price, prev_price, prices_7d, prices_30d,
                           geri_val, eeri_val, egsi_val, jkm_price):
    """Generate a data-driven market insight using custom price and risk algorithms."""
    chg    = latest_price - prev_price
    chg_pct = (chg / prev_price * 100) if prev_price else 0
    avg_7d  = sum(prices_7d)  / len(prices_7d)  if prices_7d  else latest_price
    avg_30d = sum(prices_30d) / len(prices_30d) if prices_30d else latest_price

    # ── What happened
    sign = "+" if chg >= 0 else ""
    move_mag = abs(chg_pct)
    if move_mag > 5:     move_word = "a sharp"
    elif move_mag > 2:   move_word = "a notable"
    elif move_mag > 0.5: move_word = "a modest"
    else:                move_word = "minimal"

    direction = "rise" if chg >= 0 else "decline"
    what_happened = (
        f"TTF European natural gas {direction}d {move_word} {sign}{chg:.2f} to "
        f"&#8364;{latest_price:.2f}/MWh on the latest daily reading, "
        f"a {sign}{chg_pct:.2f}% move day-over-day."
    )

    # ── vs short-term average
    vs_7d   = latest_price - avg_7d
    vs_30d  = latest_price - avg_30d
    above_7d  = vs_7d  >= 0
    above_30d = vs_30d >= 0
    avg_context = (
        f"The price is {'above' if above_7d else 'below'} its 7-day average "
        f"(&#8364;{avg_7d:.2f}) by &#8364;{abs(vs_7d):.2f}, "
        f"and {'above' if above_30d else 'below'} the 30-day average "
        f"(&#8364;{avg_30d:.2f}) by &#8364;{abs(vs_30d):.2f}."
    )

    # ── Risk context
    if geri_val > 60:
        risk_note = "Geopolitical risk signals from EnergyRiskIQ&rsquo;s GERI index remain elevated, which historically correlates with upward pressure on European gas benchmarks."
    elif geri_val > 40:
        risk_note = "GERI geopolitical risk is moderate, suggesting current price moves are driven primarily by seasonal and supply-demand factors rather than geopolitical shocks."
    else:
        risk_note = "GERI geopolitical risk remains contained at current levels, indicating TTF price action is largely driven by fundamental supply-demand and storage dynamics."

    if eeri_val > 55:
        risk_note += " European escalation risk (EERI) is elevated, adding a risk premium to continental gas prices."
    elif eeri_val < 25:
        risk_note += " Europe-specific escalation risk (EERI) is low, providing some support to price stability."

    # ── What to watch
    if latest_price > avg_30d * 1.10:
        watch = "Watch for demand destruction signals and potential LNG arbitrage from Asia if TTF remains well above its 30-day average."
    elif latest_price < avg_30d * 0.90:
        watch = "Monitor European gas storage injection rates and LNG import flows — sustained low prices often trigger additional buying pressure from storage operators."
    elif chg_pct > 3:
        watch = "Today&rsquo;s sharp move warrants close attention to any supply disruption reports or sudden weather forecast changes across Northwest Europe."
    elif chg_pct < -3:
        watch = "Watch storage fill rates and LNG cargo scheduling — a sustained decline may reduce seasonal injection incentives."
    else:
        watch = "Monitor EGSI (European Gas Stress Index) and EU storage weekly updates for the next directional signal in TTF prices."

    return dict(
        what_happened=what_happened,
        avg_context=avg_context,
        risk_note=risk_note,
        watch=watch,
        avg_7d=avg_7d,
        avg_30d=avg_30d,
        vs_7d=vs_7d,
        vs_30d=vs_30d,
    )


# ── Page-specific CSS ─────────────────────────────────────────────────────────

_TTF_CSS = """
/* ── TTF page layout ── */
.ttf-sticky-bar {
  position: sticky; top: 56px; z-index: 98;
  background: rgba(15,23,42,0.96); backdrop-filter: blur(8px);
  border-bottom: 1px solid rgba(59,130,246,0.2);
  padding: 8px 24px;
  display: flex; align-items: center; justify-content: space-between;
  flex-wrap: wrap; gap: 8px;
}
.ttf-sticky-price {
  font-size: 13px; font-weight: 700; color: #e2e8f0;
  display: flex; align-items: center; gap: 10px;
}
.ttf-sticky-dot {
  width: 7px; height: 7px; border-radius: 50%;
  background: #22c55e; box-shadow: 0 0 6px rgba(34,197,94,0.7);
  animation: ttf-pulse 1.6s ease-in-out infinite;
  flex-shrink: 0;
}
@keyframes ttf-pulse { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:.5;transform:scale(.85)} }
.ttf-sticky-cta {
  font-size: 11px; font-weight: 700; color: #3b82f6;
  text-decoration: none; letter-spacing: 0.04em;
}
.ttf-sticky-cta:hover { color: #60a5fa; }

/* ── Hero price card ── */
.ttf-price-card {
  background: var(--card);
  border: 1px solid rgba(59,130,246,0.3);
  border-radius: 20px;
  padding: 28px 32px;
  max-width: 420px; margin: 0 auto 32px;
  text-align: center;
}
.ttf-price-main {
  font-size: 56px; font-weight: 900; line-height: 1;
  color: #3b82f6; font-variant-numeric: tabular-nums;
  margin: 8px 0 4px;
}
.ttf-price-unit {
  font-size: 18px; color: #64748b; font-weight: 500;
}
.ttf-price-chg {
  font-size: 18px; font-weight: 700; margin: 10px 0 6px;
}
.ttf-status-badge {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 11px; font-weight: 700; letter-spacing: 1.4px;
  text-transform: uppercase; padding: 4px 14px; border-radius: 20px;
  margin-top: 6px;
}
.ttf-price-meta {
  font-size: 11px; color: #475569; margin-top: 10px; line-height: 1.6;
}
.ttf-price-meta a { color: #3b82f6; text-decoration: none; }

/* ── Metric grid (4 cards) ── */
.ttf-metric-grid {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px;
  margin-bottom: 40px;
}
@media (max-width: 900px) { .ttf-metric-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 480px) { .ttf-metric-grid { grid-template-columns: 1fr 1fr; } }
.ttf-metric-card {
  background: var(--card); border: 1px solid var(--border);
  border-radius: 14px; padding: 18px 18px;
  transition: border-color 0.2s;
}
.ttf-metric-card:hover { border-color: rgba(59,130,246,0.35); }
.ttf-metric-label { font-size: 10px; font-weight: 700; letter-spacing: 1.6px; text-transform: uppercase; color: var(--muted); margin-bottom: 8px; }
.ttf-metric-value { font-size: 24px; font-weight: 800; line-height: 1.1; font-variant-numeric: tabular-nums; }
.ttf-metric-sub { font-size: 11px; color: var(--muted); margin-top: 6px; }

/* ── Chart section ── */
.ttf-chart-card {
  background: var(--card); border: 1px solid var(--border);
  border-radius: 16px; overflow: hidden; margin-bottom: 40px;
}
.ttf-chart-header {
  padding: 20px 24px 16px; border-bottom: 1px solid rgba(255,255,255,0.06);
  display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px;
}
.ttf-chart-title { font-size: 13px; font-weight: 700; color: #e2e8f0; }
.ttf-period-btns { display: flex; gap: 6px; flex-wrap: wrap; }
.ttf-period-btn {
  background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.1);
  color: #64748b; padding: 4px 12px; font-size: 11px; font-weight: 700;
  border-radius: 6px; cursor: pointer; transition: all 0.18s; font-family: inherit;
  letter-spacing: 0.04em;
}
.ttf-period-btn.active, .ttf-period-btn:hover {
  background: rgba(59,130,246,0.15); border-color: rgba(59,130,246,0.4); color: #3b82f6;
}
.ttf-chart-body { padding: 20px 20px 12px; }

/* ── Snapshot section ── */
.ttf-snapshot-wrap {
  background: var(--card); border: 1px solid var(--border);
  border-radius: 16px; overflow: hidden; margin-bottom: 40px;
}
.ttf-snapshot-table { width: 100%; border-collapse: collapse; }
.ttf-snapshot-table td {
  padding: 11px 20px; border-bottom: 1px solid rgba(255,255,255,0.05); font-size: 14px;
}
.ttf-snapshot-table td:first-child { color: #94a3b8; font-size: 13px; width: 45%; }
.ttf-snapshot-table td:last-child { font-weight: 600; text-align: right; }
.ttf-snapshot-table tr:last-child td { border-bottom: none; }

/* ── Quick nav cards ── */
.ttf-quicknav-grid {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 40px;
}
@media (max-width: 800px) { .ttf-quicknav-grid { grid-template-columns: repeat(2, 1fr); } }
.ttf-quicknav-card {
  background: var(--card); border: 1px solid var(--border);
  border-radius: 12px; padding: 16px 14px; text-decoration: none; color: inherit;
  transition: border-color 0.2s, transform 0.2s;
  display: flex; flex-direction: column; gap: 6px;
}
.ttf-quicknav-card:hover { border-color: rgba(59,130,246,0.4); transform: translateY(-2px); }
.ttf-quicknav-icon { font-size: 1.4rem; }
.ttf-quicknav-label { font-size: 11px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: #3b82f6; }
.ttf-quicknav-desc { font-size: 11px; color: var(--muted); line-height: 1.4; }

/* ── Driver cards ── */
.ttf-driver-grid {
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin-bottom: 40px;
}
@media (max-width: 800px) { .ttf-driver-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 480px) { .ttf-driver-grid { grid-template-columns: 1fr; } }
.ttf-driver-card {
  background: var(--card); border: 1px solid var(--border); border-radius: 14px; padding: 20px 18px;
  transition: border-color 0.2s, transform 0.2s;
}
.ttf-driver-card:hover { border-color: rgba(59,130,246,0.3); transform: translateY(-2px); }
.ttf-driver-icon { font-size: 1.6rem; margin-bottom: 10px; }
.ttf-driver-title { font-size: 13px; font-weight: 700; color: #e2e8f0; margin-bottom: 6px; }
.ttf-driver-desc { font-size: 12px; color: #64748b; line-height: 1.6; }
.ttf-driver-link { font-size: 11px; color: #3b82f6; text-decoration: none; font-weight: 600; margin-top: 8px; display: block; }

/* ── Risk chips ── */
.ttf-risk-grid {
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin-bottom: 40px;
}
@media (max-width: 700px) { .ttf-risk-grid { grid-template-columns: repeat(2, 1fr); } }
.ttf-risk-chip {
  background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 18px; text-align: center;
}
.ttf-risk-chip-label { font-size: 9px; font-weight: 700; letter-spacing: 1.8px; text-transform: uppercase; color: #475569; margin-bottom: 8px; }
.ttf-risk-chip-val { font-size: 22px; font-weight: 800; font-variant-numeric: tabular-nums; }
.ttf-risk-chip-band { font-size: 10px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; margin-top: 4px; }

/* ── Insight box ── */
.ttf-insight-box {
  background: linear-gradient(135deg, rgba(59,130,246,0.08) 0%, rgba(59,130,246,0.03) 100%);
  border: 1px solid rgba(59,130,246,0.2); border-radius: 16px; padding: 28px 28px; margin-bottom: 40px;
}
.ttf-insight-label {
  font-size: 10px; font-weight: 700; letter-spacing: 1.8px; text-transform: uppercase;
  color: #3b82f6; margin-bottom: 16px; display: flex; align-items: center; gap: 8px;
}
.ttf-insight-label::before { content: ''; display: inline-block; width: 20px; height: 2px; background: #3b82f6; }
.ttf-insight-para { font-size: 14px; color: #cbd5e1; line-height: 1.8; margin-bottom: 12px; }
.ttf-insight-para:last-child { margin-bottom: 0; }
.ttf-insight-highlight { color: #60a5fa; font-weight: 600; }

/* ── Historical stats cards ── */
.ttf-hist-grid {
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin-bottom: 40px;
}
@media (max-width: 700px) { .ttf-hist-grid { grid-template-columns: repeat(2, 1fr); } }
.ttf-hist-card {
  background: var(--card); border: 1px solid var(--border); border-radius: 14px; padding: 18px;
  text-align: center;
}
.ttf-hist-label { font-size: 10px; font-weight: 700; letter-spacing: 1.4px; text-transform: uppercase; color: #475569; margin-bottom: 8px; }
.ttf-hist-value { font-size: 22px; font-weight: 800; color: #e2e8f0; font-variant-numeric: tabular-nums; }
.ttf-hist-sub { font-size: 11px; color: #64748b; margin-top: 4px; }

/* ── History table ── */
.ttf-table-wrap {
  background: var(--card); border: 1px solid var(--border);
  border-radius: 16px; overflow: hidden; margin-bottom: 16px;
}
.ttf-table-controls {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 20px; border-bottom: 1px solid rgba(255,255,255,0.06);
  flex-wrap: wrap; gap: 10px;
}
.ttf-table-search {
  background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.1);
  color: #e2e8f0; padding: 7px 14px; border-radius: 8px;
  font-size: 13px; font-family: inherit; outline: none; width: 200px;
}
.ttf-table-search::placeholder { color: #475569; }
.ttf-table-search:focus { border-color: rgba(59,130,246,0.4); }
.ttf-table-actions { display: flex; gap: 8px; }
.ttf-btn {
  background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.12);
  color: #94a3b8; padding: 6px 14px; font-size: 12px; font-weight: 600;
  border-radius: 8px; cursor: pointer; font-family: inherit;
  transition: all 0.18s; text-decoration: none; display: inline-flex; align-items: center; gap: 6px;
}
.ttf-btn:hover { border-color: rgba(59,130,246,0.4); color: #3b82f6; }
.ttf-btn-blue {
  background: linear-gradient(135deg, rgba(59,130,246,0.15), rgba(59,130,246,0.1));
  border-color: rgba(59,130,246,0.35); color: #3b82f6;
}
.ttf-btn-blue:hover { background: linear-gradient(135deg, rgba(59,130,246,0.25), rgba(59,130,246,0.18)); }
.ttf-history-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.ttf-history-table th {
  text-align: left; padding: 10px 16px;
  font-size: 10px; font-weight: 700; letter-spacing: 1.2px; text-transform: uppercase; color: #64748b;
  border-bottom: 1px solid var(--border); background: rgba(255,255,255,0.02);
  cursor: pointer; user-select: none; white-space: nowrap;
}
.ttf-history-table th:hover { color: #3b82f6; }
.ttf-history-table td {
  padding: 9px 16px; border-bottom: 1px solid rgba(255,255,255,0.04);
  color: #cbd5e1; font-variant-numeric: tabular-nums;
}
.ttf-history-table tr:hover td { background: rgba(255,255,255,0.02); }
.ttf-history-table tr:last-child td { border-bottom: none; }
.ttf-pagination {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 20px; flex-wrap: wrap; gap: 8px;
}
.ttf-pagination-info { font-size: 12px; color: #475569; }
.ttf-pagination-btns { display: flex; gap: 6px; }
.ttf-page-btn {
  background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.1);
  color: #64748b; padding: 4px 10px; font-size: 12px; font-weight: 600;
  border-radius: 6px; cursor: pointer; font-family: inherit; transition: all 0.18s;
}
.ttf-page-btn:hover, .ttf-page-btn.active { border-color: rgba(59,130,246,0.4); color: #3b82f6; }
.ttf-page-btn:disabled { opacity: 0.35; cursor: default; }

/* ── Conversion block ── */
.ttf-convert-box {
  background: linear-gradient(135deg, rgba(59,130,246,0.1) 0%, rgba(139,92,246,0.06) 100%);
  border: 1px solid rgba(59,130,246,0.25); border-radius: 20px; padding: 36px 32px;
  text-align: center; margin-bottom: 40px;
}
.ttf-convert-title { font-size: 1.5rem; font-weight: 800; color: #f1f5f9; margin-bottom: 12px; }
.ttf-convert-desc { font-size: 15px; color: #94a3b8; max-width: 480px; margin: 0 auto 24px; line-height: 1.7; }
.ttf-convert-benefits {
  display: flex; justify-content: center; gap: 24px; flex-wrap: wrap; margin-bottom: 24px;
}
.ttf-convert-benefit {
  display: flex; align-items: center; gap: 8px;
  font-size: 13px; font-weight: 600; color: #e2e8f0;
}
.ttf-convert-benefit::before { content: '✓'; color: #22c55e; font-weight: 900; }

/* ── FAQ ── */
.ttf-faq { margin-bottom: 40px; }
.ttf-faq-item { border-bottom: 1px solid rgba(255,255,255,0.06); }
.ttf-faq-q {
  width: 100%; text-align: left; background: none; border: none;
  color: #e2e8f0; font-size: 15px; font-weight: 600; font-family: inherit;
  padding: 18px 0; cursor: pointer;
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
}
.ttf-faq-q:hover { color: #3b82f6; }
.ttf-faq-icon { font-size: 18px; font-weight: 300; color: #475569; flex-shrink: 0; transition: transform 0.2s; }
.ttf-faq-item.open .ttf-faq-icon { transform: rotate(45deg); color: #3b82f6; }
.ttf-faq-a { display: none; font-size: 14px; color: #94a3b8; line-height: 1.7; padding: 0 0 16px; }
.ttf-faq-item.open .ttf-faq-a { display: block; }

/* ── Related links grid ── */
.ttf-related-grid {
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 40px;
}
@media (max-width: 700px) { .ttf-related-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 420px) { .ttf-related-grid { grid-template-columns: 1fr; } }
.ttf-related-group-title {
  font-size: 9px; font-weight: 700; letter-spacing: 2px; text-transform: uppercase;
  color: #3b82f6; margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid rgba(59,130,246,0.2);
}
.ttf-related-link {
  display: flex; align-items: center; gap: 8px; text-decoration: none;
  font-size: 13px; font-weight: 500; color: #94a3b8; padding: 6px 0;
  border-bottom: 1px solid rgba(255,255,255,0.04); transition: color 0.18s;
}
.ttf-related-link:hover { color: #e2e8f0; }
.ttf-related-link:last-child { border-bottom: none; }
.ttf-related-link::before { content: '↗'; font-size: 11px; color: #3b82f6; flex-shrink: 0; }

/* ── Cite card override ── */
.snap-cite-card { background: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 24px 28px; margin-bottom: 32px; }
.snap-cite-card h3 { font-size: 1.05rem; font-weight: 700; color: #f1f5f9; margin-bottom: 10px; }
.snap-cite-desc { font-size: 14px; color: #94a3b8; margin-bottom: 18px; line-height: 1.6; }
.snap-cite-code-wrap { background: #0f172a; border: 1px solid #334155; border-radius: 8px; padding: 16px 20px; position: relative; }
.snap-cite-code { font-family: 'Courier New', Courier, monospace; font-size: 13px; color: #e2e8f0; line-height: 1.8; }
.snap-cite-code a { color: #60a5fa; text-decoration: none; }
.snap-cite-copy-btn { position: absolute; top: 12px; right: 12px; background: rgba(30,41,59,0.9); border: 1px solid #475569; color: #94a3b8; padding: 5px 14px; font-size: 12px; font-weight: 600; border-radius: 6px; cursor: pointer; font-family: inherit; }
.snap-cite-copy-btn:hover { color: #f1f5f9; border-color: #94a3b8; }
.snap-cite-footer { margin-top: 14px; font-size: 12px; color: #64748b; }
.snap-cite-footer a { color: #60a5fa; text-decoration: none; }

/* ── Mobile ── */
@media (max-width: 640px) {
  html, body { overflow-x: hidden; max-width: 100%; }
  .hero { padding-left: 16px; padding-right: 16px; }
  .nav-inner { padding: 0 1rem; }
  .nav-inner > div a:not(.cta-btn-nav) { display: none; }
  .ttf-chart-header { flex-direction: column; align-items: flex-start; }
  .ttf-sticky-bar { flex-direction: column; align-items: flex-start; gap: 4px; }
  .ttf-price-card { padding: 20px 18px; }
  .ttf-price-main { font-size: 42px; }
  .ttf-table-controls { flex-direction: column; align-items: flex-start; }
  .ttf-table-search { width: 100%; }
  .snap-cite-card { padding: 18px 16px; overflow: hidden; }
  .snap-cite-code-wrap { overflow-x: auto; padding: 14px; }
  .snap-cite-code { white-space: pre-wrap !important; overflow-wrap: break-word; word-break: break-word; font-size: 11px; }
  .snap-cite-copy-btn { position: static !important; display: block; width: 100%; box-sizing: border-box; text-align: center; margin-top: 12px; }
  .ttf-convert-benefits { flex-direction: column; align-items: center; gap: 10px; }
}
"""

# ── Loader ────────────────────────────────────────────────────────────────────

_TTF_LOADER = _LOADER_HTML.replace(
    "Global Energy Risk Snapshot | EnergyRiskIQ",
    "TTF Gas Price Today | Live Chart, Storage Levels & Analysis",
).replace(
    'name="description" content="Live global energy risk snapshot. Current GERI, EERI and EGSI-M index values with Brent crude, TTF gas, VIX and LNG market prices."',
    'name="description" content="Latest TTF gas price today with daily updates, historical charts, and market insights. Track European natural gas prices and risk signals."',
).replace(
    'rel="canonical" href="https://energyriskiq.com/data/energy-risk-snapshot"',
    'rel="canonical" href="https://energyriskiq.com/data/ttf-gas-price-today"',
).replace(
    "Fetching GERI\u00a0&\u00a0EERI indices\u2026",
    "Fetching TTF gas price history\u2026",
).replace(
    '<span class="ld-tag">GERI</span>\n    <span class="ld-tag">EERI</span>\n    <span class="ld-tag">EGSI&#8209;M</span>\n    <span class="ld-tag">Brent</span>\n    <span class="ld-tag">TTF</span>',
    '<span class="ld-tag">TTF Gas</span>\n    <span class="ld-tag">Brent</span>\n    <span class="ld-tag">GERI</span>\n    <span class="ld-tag">EERI</span>',
)


# ── Data Fetcher ──────────────────────────────────────────────────────────────

def _fetch_ttf_data():
    all_rows = execute_production_query(
        "SELECT date, ttf_price, currency, unit, source FROM ttf_gas_snapshots "
        "WHERE ttf_price IS NOT NULL ORDER BY date DESC"
    ) or []

    stats = execute_production_one(
        "SELECT COUNT(*) AS total, MIN(date) AS earliest, MAX(date) AS latest, "
        "ROUND(MAX(ttf_price)::numeric,2) AS highest, "
        "ROUND(MIN(ttf_price)::numeric,2) AS lowest, "
        "ROUND(AVG(ttf_price)::numeric,2) AS avg_price "
        "FROM ttf_gas_snapshots WHERE ttf_price IS NOT NULL"
    ) or {}

    brent = execute_production_one(
        "SELECT date, brent_price, brent_change_24h, brent_change_pct FROM oil_price_snapshots "
        "ORDER BY date DESC LIMIT 1"
    ) or {}

    geri = execute_production_one(
        "SELECT value, band, trend_7d FROM intel_indices_daily "
        "WHERE index_id='global:geo_energy_risk' ORDER BY date DESC LIMIT 1"
    ) or {}

    eeri = execute_production_one(
        "SELECT value, band, trend_7d FROM reri_indices_daily "
        "WHERE index_id='europe:eeri' ORDER BY date DESC LIMIT 1"
    ) or {}

    egsi = execute_production_one(
        "SELECT index_value AS value, band, trend_7d FROM egsi_m_daily "
        "WHERE region='Europe' ORDER BY index_date DESC LIMIT 1"
    ) or {}

    jkm = execute_production_one(
        "SELECT date, jkm_price FROM lng_price_snapshots ORDER BY date DESC LIMIT 1"
    ) or {}

    return dict(all_rows=all_rows, stats=stats, brent=brent,
                geri=geri, eeri=eeri, egsi=egsi, jkm=jkm)


# ── Page HTML Builder ─────────────────────────────────────────────────────────

def _build_ttf_html(data: dict) -> str:
    all_rows = data["all_rows"]   # newest first
    stats    = data["stats"]
    brent    = data["brent"]
    geri     = data["geri"]
    eeri     = data["eeri"]
    egsi     = data["egsi"]
    jkm      = data["jkm"]

    # ── Latest price metrics
    latest_row  = all_rows[0]  if all_rows      else {}
    prev_row    = all_rows[1]  if len(all_rows) > 1 else {}
    ttf_price   = _safe_float(latest_row.get("ttf_price"))
    prev_price  = _safe_float(prev_row.get("ttf_price"))
    chg         = ttf_price - prev_price
    chg_pct     = (chg / prev_price * 100) if prev_price else 0
    latest_date = latest_row.get("date")
    currency    = str(latest_row.get("currency", "EUR")).upper()
    unit_label  = str(latest_row.get("unit", "mwh")).upper().replace("MWH", "MWh")

    total_rows  = int(stats.get("total") or 0)
    earliest    = stats.get("earliest")
    stat_latest = stats.get("latest")
    highest     = _safe_float(stats.get("highest"))
    lowest      = _safe_float(stats.get("lowest"))
    avg_price   = _safe_float(stats.get("avg_price"))

    chg_color        = _chg_color(chg)
    arrow            = _arrow(chg)
    sign             = _sign(chg)
    status_label, status_arrow, status_color = _ttf_status(chg_pct)

    date_str  = _fmt_date(latest_date)
    date_iso  = _fmt_date_iso(latest_date)
    date_range = f"{_fmt_date(earliest)} &rarr; {_fmt_date(stat_latest)}"

    # ── Index values
    geri_val  = int(_safe_float(geri.get("value")))
    geri_band = str(geri.get("band", "—"))
    eeri_val  = int(_safe_float(eeri.get("value")))
    eeri_band = str(eeri.get("band", "—"))
    egsi_val  = round(_safe_float(egsi.get("value")), 2)
    egsi_band = str(egsi.get("band", "—"))

    gc = BAND_COLORS.get(geri_band, "#f97316")
    ec = BAND_COLORS.get(eeri_band, "#ef4444")
    xc = BAND_COLORS.get(egsi_band, "#eab308")

    brent_price    = _safe_float(brent.get("brent_price"))
    brent_chg_pct  = _safe_float(brent.get("brent_change_pct"))
    jkm_price      = _safe_float(jkm.get("jkm_price"))

    # JKM → EUR/MWh conversion for spread
    _MMBTU_TO_MWH = 0.29307
    _EUR_USD       = 1.09
    jkm_eur_mwh    = jkm_price / _MMBTU_TO_MWH / _EUR_USD if jkm_price else 0
    ttf_jkm_spread = ttf_price - jkm_eur_mwh

    # ── Chart periods (oldest → newest for SVG)
    rows_asc  = list(reversed(all_rows))

    def _period(n): return rows_asc[-n:] if len(rows_asc) >= n else rows_asc

    # YTD: rows from Jan 1, 2026 onwards
    ytd_start = _date(2026, 1, 1)
    rows_ytd  = [r for r in rows_asc if r.get("date") and r["date"] >= ytd_start]
    if not rows_ytd:
        rows_ytd = rows_asc

    svg_7d  = _build_ttf_chart_svg(_period(7),   W=700, H=200)
    svg_30d = _build_ttf_chart_svg(_period(30),  W=700, H=200)
    svg_90d = _build_ttf_chart_svg(_period(90),  W=700, H=200)
    svg_ytd = _build_ttf_chart_svg(rows_ytd,     W=700, H=200)
    svg_all = _build_ttf_chart_svg(rows_asc,     W=700, H=200)

    # ── 7d and 30d price lists for insight generator
    prices_7d  = [_safe_float(r.get("ttf_price")) for r in _period(7)]
    prices_30d = [_safe_float(r.get("ttf_price")) for r in _period(30)]

    insight = _generate_ttf_insight(
        ttf_price, prev_price, prices_7d, prices_30d,
        geri_val, eeri_val, egsi_val, jkm_price
    )

    avg_7d  = insight["avg_7d"]
    avg_30d = insight["avg_30d"]
    vs_7d   = insight["vs_7d"]
    vs_30d  = insight["vs_30d"]

    # ── 30d high/low (last 30 rows newest-first in all_rows)
    last_30_prices = [_safe_float(r.get("ttf_price")) for r in all_rows[:30]]
    high_30d = max(last_30_prices) if last_30_prices else highest
    low_30d  = min(last_30_prices) if last_30_prices else lowest

    # ── History table HTML
    def _chg_td(v):
        c = _chg_color(v); s = _sign(v)
        return f'<td style="color:{c};font-weight:600;">{s}{v:.2f}</td>'
    def _pct_td(v):
        c = _chg_color(v); s = _sign(v)
        return f'<td style="color:{c};">{s}{v:.2f}%</td>'

    table_rows_html = ""
    prev_p = None
    for row in all_rows:
        d   = row.get("date")
        p   = _safe_float(row.get("ttf_price"))
        src = str(row.get("source", "—")).split(".")[0].capitalize()
        if prev_p is not None and prev_p:
            row_chg     = p - prev_p
            row_chg_pct = (row_chg / prev_p * 100) if prev_p else 0
        else:
            row_chg     = 0.0
            row_chg_pct = 0.0
        prev_p = p
        table_rows_html += (
            f'<tr data-date="{_fmt_date_iso(d)}">'
            f'<td>{_fmt_date(d)}</td>'
            f'<td style="font-weight:700;color:#e2e8f0;">\u20ac{p:.2f}</td>'
            + _chg_td(row_chg) + _pct_td(row_chg_pct) +
            f'<td style="color:#475569;font-size:12px;">{src}</td>'
            f'</tr>'
        )

    # ── FAQ dynamic answers
    faq_q1 = f"The latest EnergyRiskIQ reading shows TTF European natural gas at \u20ac{ttf_price:.2f}/MWh on {date_str}, {sign}{chg:.2f} ({sign}{chg_pct:.2f}%) day-over-day."
    faq_q3 = f"EnergyRiskIQ updates the TTF gas price daily. The page currently tracks {total_rows} daily records from {_fmt_date(earliest)} to {_fmt_date(stat_latest)}."

    # ── Schemas
    schema_dataset = f'''{{
  "@context": "https://schema.org",
  "@type": "Dataset",
  "name": "TTF Gas Prices — Daily Snapshots",
  "description": "Daily Dutch TTF natural gas price snapshots tracked by EnergyRiskIQ from {_fmt_date(earliest)} to {_fmt_date(stat_latest)}.",
  "url": "{BASE_URL}/data/ttf-gas-price-today",
  "creator":   {{"@type": "Organization", "name": "EnergyRiskIQ", "url": "{BASE_URL}"}},
  "publisher": {{"@type": "Organization", "name": "EnergyRiskIQ", "url": "{BASE_URL}"}},
  "license": "{BASE_URL}/data-license",
  "isAccessibleForFree": true,
  "temporalCoverage": "{_fmt_date_iso(earliest)}/{date_iso}",
  "variableMeasured": ["TTF gas price (EUR/MWh)", "Daily price change"],
  "keywords": ["TTF gas price", "TTF gas price today", "Dutch TTF natural gas", "European gas price", "TTF price chart"]
}}'''

    schema_faq = f'''{{
  "@context": "https://schema.org",
  "@type": "FAQPage",
  "mainEntity": [
    {{"@type": "Question", "name": "What is the TTF gas price today?",
      "acceptedAnswer": {{"@type": "Answer", "text": "{faq_q1}"}}}},
    {{"@type": "Question", "name": "What is TTF?",
      "acceptedAnswer": {{"@type": "Answer", "text": "TTF (Title Transfer Facility) is the leading European natural gas price benchmark, traded on the ICE exchange. It serves as the reference price for gas delivered into the Dutch virtual trading hub."}}}},
    {{"@type": "Question", "name": "How often is the TTF price updated?",
      "acceptedAnswer": {{"@type": "Answer", "text": "{faq_q3}"}}}},
    {{"@type": "Question", "name": "What drives TTF gas prices?",
      "acceptedAnswer": {{"@type": "Answer", "text": "TTF gas prices are driven by European storage levels, LNG import flows, weather demand, pipeline supply from Norway and Russia, and geopolitical risk. EnergyRiskIQ tracks all these signals in its GERI, EERI and EGSI risk indices."}}}},
    {{"@type": "Question", "name": "What is the difference between TTF and JKM?",
      "acceptedAnswer": {{"@type": "Answer", "text": "TTF is the European gas benchmark (EUR/MWh), while JKM (Japan Korea Marker) is the Asian LNG spot benchmark (USD/MMBtu). The TTF-JKM spread indicates whether Europe or Asia is offering a premium for LNG cargoes, which drives global LNG cargo routing."}}}},
    {{"@type": "Question", "name": "Why does TTF spike?",
      "acceptedAnswer": {{"@type": "Answer", "text": "TTF spikes are typically triggered by cold weather forecasts, supply disruption events (pipeline outages, LNG facility issues), geopolitical escalation, or unexpected falls in European gas storage levels."}}}}
  ]
}}'''

    cite_copy = f"EnergyRiskIQ. (2026). TTF Gas Price — {date_str}. Retrieved from {BASE_URL}/data/ttf-gas-price-today. Data source: OilPriceAPI daily.".replace('"', '\\"')

    return f"""<script>
var l=document.getElementById('snap-loader');
if(l){{l.style.display='none';}}
document.body.style.overflow='';
</script>

<style>{_TTF_CSS}</style>

<script type="application/ld+json">{schema_dataset}</script>
<script type="application/ld+json">{schema_faq}</script>

<!-- NAV -->
<nav class="nav">
  <div class="nav-inner">
    <a href="/" class="logo">
      <img src="/static/logo.png" alt="EnergyRiskIQ" style="height:28px">
      <span>EnergyRiskIQ</span>
    </a>
    <div style="display:flex;align-items:center;gap:1.5rem;">
      <a href="/indices/global-energy-risk-index" style="font-size:13px;color:#94a3b8;text-decoration:none;">GERI</a>
      <a href="/indices/europe-energy-risk-index"  style="font-size:13px;color:#94a3b8;text-decoration:none;">EERI</a>
      <a href="/data/global-energy-risk-forecast"  style="font-size:13px;color:#94a3b8;text-decoration:none;">Forecast</a>
      <a href="/users" class="cta-btn-nav">Get Free Access</a>
    </div>
  </div>
</nav>

<!-- STICKY PRICE BAR -->
<div class="ttf-sticky-bar">
  <div class="ttf-sticky-price">
    <div class="ttf-sticky-dot" style="background:{chg_color};box-shadow:0 0 6px {chg_color}99;"></div>
    <span>&#128202; TTF Gas Price Today: <strong style="color:#e2e8f0;">\u20ac{ttf_price:.2f}/MWh</strong>
    &nbsp;<span style="color:{chg_color};">{arrow} {sign}{chg:.2f} ({sign}{chg_pct:.2f}%)</span>
    &nbsp;<span style="color:#475569;font-weight:400;">&bull; Updated {date_str} &bull; Source: OilPriceAPI</span></span>
  </div>
  <a href="/users" class="ttf-sticky-cta">Get daily alerts &rarr;</a>
</div>

<!-- HERO -->
<header class="hero">
  <div class="hero-date">&#127470;&#127489; European Natural Gas Benchmark &nbsp;&bull;&nbsp; TTF &nbsp;&bull;&nbsp; Updated Daily</div>
  <h1 style="font-family:'DM Serif Display',serif;font-size:clamp(26px,4.5vw,44px);font-weight:400;color:#fff;line-height:1.2;max-width:760px;margin:0 auto 14px;">
    TTF Gas Price Today
  </h1>
  <p class="hero-sub" style="font-size:clamp(14px,2vw,17px);color:#94a3b8;max-width:620px;margin:0 auto 1.8rem;line-height:1.7;">
    Track the latest Dutch TTF natural gas price, daily changes, and market trends. Updated every day with historical context, risk signals, and energy market intelligence.
  </p>

  <!-- HERO PRICE CARD -->
  <div class="ttf-price-card">
    <div style="font-size:11px;font-weight:700;letter-spacing:1.6px;text-transform:uppercase;color:#64748b;margin-bottom:4px;">TTF Natural Gas</div>
    <div class="ttf-price-main">\u20ac{ttf_price:.2f}</div>
    <div class="ttf-price-unit">/ MWh</div>
    <div class="ttf-price-chg" style="color:{chg_color};">{arrow} {sign}\u20ac{chg:.2f} ({sign}{chg_pct:.2f}%)</div>
    <div style="display:flex;justify-content:center;">
      <span class="ttf-status-badge" style="background:{status_color}22;border:1px solid {status_color}44;color:{status_color};">
        {status_arrow} {status_label}
      </span>
    </div>
    <div class="ttf-price-meta">
      &#128197; {date_str} &nbsp;&bull;&nbsp; Source: OilPriceAPI<br>
      &#128202; {total_rows} daily records &bull; {_fmt_date(earliest)} &rarr; {_fmt_date(stat_latest)}<br>
      <a href="/users">&#128276; Get real-time alerts &amp; risk signals &rarr;</a>
    </div>
  </div>
</header>

<main class="page-body">

  <!-- METRIC GRID -->
  <div class="section-label" style="margin-bottom:20px;">&#128202; Key Metrics</div>
  <div class="ttf-metric-grid">
    <div class="ttf-metric-card">
      <div class="ttf-metric-label">TTF Price</div>
      <div class="ttf-metric-value" style="color:#3b82f6;">\u20ac{ttf_price:.2f}</div>
      <div class="ttf-metric-sub">/MWh &bull; {date_str}</div>
    </div>
    <div class="ttf-metric-card">
      <div class="ttf-metric-label">24h Change</div>
      <div class="ttf-metric-value" style="color:{chg_color};">{sign}{chg:.2f}</div>
      <div class="ttf-metric-sub">{sign}{chg_pct:.2f}% day-over-day</div>
    </div>
    <div class="ttf-metric-card">
      <div class="ttf-metric-label">30-Day Range</div>
      <div class="ttf-metric-value" style="font-size:18px;color:#e2e8f0;">\u20ac{low_30d:.2f}&ndash;\u20ac{high_30d:.2f}</div>
      <div class="ttf-metric-sub">Avg \u20ac{avg_30d:.2f}/MWh</div>
    </div>
    <div class="ttf-metric-card">
      <div class="ttf-metric-label">Brent Crude</div>
      <div class="ttf-metric-value" style="font-size:20px;color:#d4a017;">${brent_price:.2f}</div>
      <div class="ttf-metric-sub">/bbl &bull; {_sign(brent_chg_pct)}{brent_chg_pct:.2f}% d/d</div>
    </div>
  </div>

  <!-- MAIN CHART -->
  <div class="section-label" style="margin-bottom:20px;">&#128200; TTF Gas Price Chart</div>
  <div class="ttf-chart-card">
    <div class="ttf-chart-header">
      <div class="ttf-chart-title">Dutch TTF Natural Gas (&#8364;/MWh) &mdash; {date_str}</div>
      <div class="ttf-period-btns">
        <button class="ttf-period-btn" onclick="ttfSetPeriod('7d',this)">7D</button>
        <button class="ttf-period-btn active" onclick="ttfSetPeriod('30d',this)">30D</button>
        <button class="ttf-period-btn" onclick="ttfSetPeriod('90d',this)">90D</button>
        <button class="ttf-period-btn" onclick="ttfSetPeriod('ytd',this)">YTD</button>
        <button class="ttf-period-btn" onclick="ttfSetPeriod('all',this)">All</button>
      </div>
    </div>
    <div class="ttf-chart-body">
      <div id="ttf-chart-7d"  style="display:none;">{svg_7d}</div>
      <div id="ttf-chart-30d" style="display:block;">{svg_30d}</div>
      <div id="ttf-chart-90d" style="display:none;">{svg_90d}</div>
      <div id="ttf-chart-ytd" style="display:none;">{svg_ytd}</div>
      <div id="ttf-chart-all" style="display:none;">{svg_all}</div>
      <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;margin-top:10px;">
        <div style="font-size:11px;color:#334155;">Source: OilPriceAPI daily. Updated daily. Not financial advice.</div>
        <div style="font-size:11px;color:#334155;border:1px solid #1e293b;border-radius:6px;padding:2px 10px;">
          Brent &amp; Normalized overlays &mdash; <span style="color:#475569;">Coming soon</span>
        </div>
      </div>
    </div>
  </div>

  <!-- MARKET SNAPSHOT -->
  <div class="section-label" style="margin-bottom:20px;">&#128247; TTF Gas Market Snapshot &mdash; Today</div>
  <div class="ttf-snapshot-wrap" style="margin-bottom:24px;">
    <div style="padding:20px 24px;border-bottom:1px solid rgba(255,255,255,0.06);">
      <p style="font-size:15px;color:#cbd5e1;line-height:1.8;margin-bottom:10px;">
        The TTF gas price today stands at <strong style="color:#3b82f6;">\u20ac{ttf_price:.2f}/MWh</strong>,
        <span style="color:{chg_color};">{arrow} {sign}\u20ac{chg:.2f} ({sign}{chg_pct:.2f}%)</span> over the last 24 hours.
        The market is signalling a <strong style="color:{status_color};">{status_label.lower()}</strong> session.
      </p>
      <p style="font-size:14px;color:#94a3b8;line-height:1.8;">
        Over the past 7 days, the average TTF price was
        <strong style="color:#e2e8f0;">\u20ac{avg_7d:.2f}/MWh</strong>
        — the current price is
        <span style="color:{_chg_color(vs_7d)};">{_sign(vs_7d)}\u20ac{abs(vs_7d):.2f} {'above' if vs_7d >= 0 else 'below'}</span>
        that average.
        Over 30 days, the average is \u20ac{avg_30d:.2f}/MWh
        (current is <span style="color:{_chg_color(vs_30d)};">{_sign(vs_30d)}\u20ac{abs(vs_30d):.2f} {'above' if vs_30d >= 0 else 'below'}</span>).
      </p>
    </div>
    <table class="ttf-snapshot-table">
      <tr><td>Latest TTF price</td><td style="color:#3b82f6;">\u20ac{ttf_price:.2f}/MWh</td></tr>
      <tr><td>24h change</td><td style="color:{chg_color};">{sign}\u20ac{chg:.2f} ({sign}{chg_pct:.2f}%)</td></tr>
      <tr><td>Market status</td><td style="color:{status_color};">{status_arrow} {status_label}</td></tr>
      <tr><td>7-day average</td><td>\u20ac{avg_7d:.2f}/MWh</td></tr>
      <tr><td>30-day average</td><td>\u20ac{avg_30d:.2f}/MWh</td></tr>
      <tr><td>30-day high</td><td>\u20ac{high_30d:.2f}/MWh</td></tr>
      <tr><td>30-day low</td><td>\u20ac{low_30d:.2f}/MWh</td></tr>
      <tr><td>All-time high (dataset)</td><td>\u20ac{highest:.2f}/MWh</td></tr>
      <tr><td>All-time low (dataset)</td><td>\u20ac{lowest:.2f}/MWh</td></tr>
      <tr><td>JKM LNG (converted)</td><td style="color:#d4a017;">\u20ac{jkm_eur_mwh:.2f}/MWh (TTF spread: {_sign(ttf_jkm_spread)}\u20ac{abs(ttf_jkm_spread):.2f})</td></tr>
      <tr><td>Brent crude</td><td style="color:#d4a017;">${brent_price:.2f}/bbl</td></tr>
      <tr><td>Data coverage</td><td>{total_rows} daily records &bull; {date_range}</td></tr>
      <tr><td>Source</td><td style="color:#475569;font-size:12px;">OilPriceAPI daily</td></tr>
    </table>
  </div>

  <!-- QUICK CONTEXT NAV -->
  <div class="section-label" style="margin-bottom:14px;">&#128279; Understand What Moves TTF Prices</div>
  <div class="ttf-quicknav-grid">
    <a href="/gas-storage-levels-in-europe" class="ttf-quicknav-card">
      <div class="ttf-quicknav-icon">&#128200;</div>
      <div class="ttf-quicknav-label">Gas Storage</div>
      <div class="ttf-quicknav-desc">EU storage levels &amp; seasonal deficit risk</div>
    </a>
    <a href="/data/europe-lng-supply-demand" class="ttf-quicknav-card">
      <div class="ttf-quicknav-icon">&#128168;</div>
      <div class="ttf-quicknav-label">LNG Supply</div>
      <div class="ttf-quicknav-desc">Europe LNG supply &amp; demand intelligence</div>
    </a>
    <a href="/data/jkm-lng-spot-price" class="ttf-quicknav-card">
      <div class="ttf-quicknav-icon">&#9875;</div>
      <div class="ttf-quicknav-label">JKM LNG Price</div>
      <div class="ttf-quicknav-desc">Asia LNG benchmark &amp; TTF spread</div>
    </a>
    <a href="/data/global-energy-risk-forecast" class="ttf-quicknav-card">
      <div class="ttf-quicknav-icon">&#127919;</div>
      <div class="ttf-quicknav-label">Risk Forecast</div>
      <div class="ttf-quicknav-desc">24h Brent &amp; TTF price outlook</div>
    </a>
  </div>

  <!-- WHAT DRIVES TTF -->
  <div class="section-label" style="margin-bottom:20px;">&#127919; What Drives the TTF Gas Price Today?</div>
  <div class="ttf-driver-grid">
    <div class="ttf-driver-card">
      <div class="ttf-driver-icon">&#128268;</div>
      <div class="ttf-driver-title">Storage Levels</div>
      <div class="ttf-driver-desc">European gas storage is the single most important seasonal driver of TTF. Low storage entering winter triggers aggressive spot buying and price spikes. High storage leads to demand destruction and price softening.</div>
      <a href="/gas-storage-levels-in-europe" class="ttf-driver-link">View EU Gas Storage &rarr;</a>
    </div>
    <div class="ttf-driver-card">
      <div class="ttf-driver-icon">&#128674;</div>
      <div class="ttf-driver-title">LNG Imports &amp; JKM Spread</div>
      <div class="ttf-driver-desc">Europe competes with Asia for LNG cargoes. When TTF rises above JKM (adjusted), LNG cargoes divert to Europe. The JKM&ndash;TTF spread signals which region offers the premium, routing global LNG supply.</div>
      <a href="/data/jkm-lng-spot-price" class="ttf-driver-link">View JKM LNG Price &rarr;</a>
    </div>
    <div class="ttf-driver-card">
      <div class="ttf-driver-icon">&#127783;&#65039;</div>
      <div class="ttf-driver-title">Weather &amp; Demand</div>
      <div class="ttf-driver-desc">Cold winters and hot summers (power cooling demand) create sudden demand surges. Heating degree day (HDD) forecasts move TTF within hours of release, as traders anticipate storage withdrawal rates.</div>
    </div>
    <div class="ttf-driver-card">
      <div class="ttf-driver-icon">&#128481;&#65039;</div>
      <div class="ttf-driver-title">Geopolitical Risk</div>
      <div class="ttf-driver-desc">Supply disruption risk from conflict zones, sanctions, or pipeline infrastructure events can instantly spike TTF. EnergyRiskIQ tracks this in real time via GERI and EERI.</div>
      <a href="/indices/global-energy-risk-index" class="ttf-driver-link">View GERI &rarr;</a>
    </div>
    <div class="ttf-driver-card">
      <div class="ttf-driver-icon">&#127981;</div>
      <div class="ttf-driver-title">Pipeline Flows &amp; Supply Disruptions</div>
      <div class="ttf-driver-desc">Norwegian pipeline maintenance, Algerian LNG outages, or Baltic pipeline disruptions affect daily TTF supply. Any unplanned outage can trigger immediate price moves of 5&ndash;15%.</div>
    </div>
    <div class="ttf-driver-card">
      <div class="ttf-driver-icon">&#128176;</div>
      <div class="ttf-driver-title">Carbon &amp; Power Markets</div>
      <div class="ttf-driver-desc">European Carbon (EUA) prices and electricity spot prices interact with TTF through gas-fired power generation. High carbon prices increase gas substitution costs, often amplifying TTF price moves.</div>
    </div>
  </div>

  <!-- RISK INTELLIGENCE BLOCK -->
  <div class="section-label" style="margin-bottom:20px;">&#9888;&#65039; Energy Risk Signals Behind Today&rsquo;s TTF Price</div>
  <div class="ttf-insight-box" style="margin-bottom:24px;">
    <div class="ttf-insight-label">Custom Algorithms &mdash; EnergyRiskIQ Risk Interpretation</div>
    <p class="ttf-insight-para">
      {insight['what_happened']} {insight['avg_context']}
    </p>
    <p class="ttf-insight-para">
      {insight['risk_note']}
    </p>
  </div>
  <div class="ttf-risk-grid" style="margin-bottom:40px;">
    <div class="ttf-risk-chip" style="border-color:{gc}33;">
      <div class="ttf-risk-chip-label">GERI &mdash; Global Energy Risk</div>
      <div class="ttf-risk-chip-val" style="color:{gc};">{geri_val}</div>
      <div class="ttf-risk-chip-band" style="color:{gc};">{geri_band}</div>
    </div>
    <div class="ttf-risk-chip" style="border-color:{ec}33;">
      <div class="ttf-risk-chip-label">EERI &mdash; Europe Escalation Risk</div>
      <div class="ttf-risk-chip-val" style="color:{ec};">{eeri_val}</div>
      <div class="ttf-risk-chip-band" style="color:{ec};">{eeri_band}</div>
    </div>
    <div class="ttf-risk-chip" style="border-color:{xc}33;">
      <div class="ttf-risk-chip-label">EGSI-M &mdash; Gas Stress Index</div>
      <div class="ttf-risk-chip-val" style="color:{xc};">{egsi_val}</div>
      <div class="ttf-risk-chip-band" style="color:{xc};">{egsi_band}</div>
    </div>
  </div>

  <!-- HISTORICAL ANALYSIS -->
  <div class="section-label" style="margin-bottom:20px;">&#128202; TTF Gas Price History</div>
  <div class="ttf-hist-grid" style="margin-bottom:24px;">
    <div class="ttf-hist-card">
      <div class="ttf-hist-label">30-Day High</div>
      <div class="ttf-hist-value" style="color:#22c55e;">\u20ac{high_30d:.2f}</div>
      <div class="ttf-hist-sub">/MWh</div>
    </div>
    <div class="ttf-hist-card">
      <div class="ttf-hist-label">30-Day Low</div>
      <div class="ttf-hist-value" style="color:#ef4444;">\u20ac{low_30d:.2f}</div>
      <div class="ttf-hist-sub">/MWh</div>
    </div>
    <div class="ttf-hist-card">
      <div class="ttf-hist-label">All-Time High (dataset)</div>
      <div class="ttf-hist-value" style="color:#d4a017;">\u20ac{highest:.2f}</div>
      <div class="ttf-hist-sub">/MWh &bull; {total_rows} records</div>
    </div>
    <div class="ttf-hist-card">
      <div class="ttf-hist-label">All-Time Low (dataset)</div>
      <div class="ttf-hist-value" style="color:#3b82f6;">\u20ac{lowest:.2f}</div>
      <div class="ttf-hist-sub">/MWh</div>
    </div>
    <div class="ttf-hist-card">
      <div class="ttf-hist-label">Dataset Average</div>
      <div class="ttf-hist-value">\u20ac{avg_price:.2f}</div>
      <div class="ttf-hist-sub">/MWh &bull; {date_range}</div>
    </div>
    <div class="ttf-hist-card">
      <div class="ttf-hist-label">Total Records</div>
      <div class="ttf-hist-value">{total_rows}</div>
      <div class="ttf-hist-sub">daily snapshots tracked</div>
    </div>
  </div>
  <div style="text-align:center;margin-bottom:30px;">
    <a href="/research/global-energy-risk-timeline" style="font-size:13px;color:#3b82f6;font-weight:600;text-decoration:none;">
      &#8599; View Global Energy Risk Timeline &rarr;
    </a>
  </div>

  <!-- HISTORICAL DATA TABLE -->
  <div class="section-label" style="margin-bottom:20px;">&#128196; Full Price History</div>
  <div class="ttf-table-wrap">
    <div class="ttf-table-controls">
      <input class="ttf-table-search" id="ttf-search" type="text" placeholder="Search by date&hellip;" oninput="ttfFilterTable()">
      <div class="ttf-table-actions">
        <button class="ttf-btn" onclick="ttfCopyData()">&#128203; Copy data</button>
        <a href="/api/ttf-gas-prices.csv" class="ttf-btn ttf-btn-blue" download>&#11015; Download CSV</a>
      </div>
    </div>
    <div style="overflow-x:auto;">
      <table class="ttf-history-table" id="ttf-table">
        <thead>
          <tr>
            <th onclick="ttfSort('date')">Date &#8597;</th>
            <th onclick="ttfSort('price')">TTF Price &#8597;</th>
            <th onclick="ttfSort('chg')">24h Change &#8597;</th>
            <th onclick="ttfSort('pct')">24h % &#8597;</th>
            <th>Source</th>
          </tr>
        </thead>
        <tbody id="ttf-tbody">{table_rows_html}</tbody>
      </table>
    </div>
    <div class="ttf-pagination">
      <div class="ttf-pagination-info" id="ttf-page-info">Showing 1&ndash;25 of {total_rows}</div>
      <div class="ttf-pagination-btns">
        <button class="ttf-page-btn" id="ttf-prev" onclick="ttfPrevPage()" disabled>&#8592; Prev</button>
        <span id="ttf-page-num" style="font-size:12px;color:#475569;padding:0 8px;line-height:28px;">Page 1</span>
        <button class="ttf-page-btn" id="ttf-next" onclick="ttfNextPage()">Next &#8594;</button>
      </div>
    </div>
  </div>
  <div style="text-align:center;margin-bottom:40px;">
    <p style="font-size:13px;color:#475569;margin-bottom:12px;">Need TTF price history with energy risk context?</p>
    <a href="/users" class="ttf-btn ttf-btn-blue" style="display:inline-flex;">\u2192 Create a free EnergyRiskIQ account</a>
  </div>

  <!-- TODAY'S INSIGHT -->
  <div class="section-label" style="margin-bottom:20px;">&#128161; Today&rsquo;s TTF Gas Market Insight</div>
  <div class="ttf-insight-box" style="margin-bottom:40px;">
    <div class="ttf-insight-label">Custom Algorithm &mdash; Daily Market Interpretation &bull; {date_str}</div>
    <p class="ttf-insight-para"><strong style="color:#e2e8f0;">What happened:</strong> {insight['what_happened']}</p>
    <p class="ttf-insight-para"><strong style="color:#e2e8f0;">Why it matters:</strong> {insight['avg_context']} {insight['risk_note']}</p>
    <p class="ttf-insight-para"><strong style="color:#e2e8f0;">What to watch next:</strong> {insight['watch']}</p>
    <div style="margin-top:16px;padding-top:16px;border-top:1px solid rgba(59,130,246,0.15);text-align:center;">
      <a href="/users" style="font-size:13px;font-weight:600;color:#3b82f6;text-decoration:none;">
        &#128276; Get daily TTF market insights delivered to your inbox &rarr;
      </a>
    </div>
  </div>

  <!-- CONVERSION BLOCK -->
  <div class="ttf-convert-box">
    <div class="ttf-convert-title">Get Ahead of Gas Market Moves</div>
    <p class="ttf-convert-desc">
      EnergyRiskIQ gives you the risk intelligence layer that price charts can&rsquo;t. Know <em>why</em> TTF is moving before the market catches up.
    </p>
    <div class="ttf-convert-benefits">
      <div class="ttf-convert-benefit">Daily TTF risk alerts</div>
      <div class="ttf-convert-benefit">GERI, EERI &amp; EGSI signals</div>
      <div class="ttf-convert-benefit">LNG &amp; storage context</div>
      <div class="ttf-convert-benefit">Free plan, no credit card required</div>
    </div>
    <a href="/users" style="display:inline-block;background:linear-gradient(135deg,#3b82f6,#8b5cf6);color:white;font-weight:700;font-size:14px;padding:12px 28px;border-radius:10px;text-decoration:none;margin-top:4px;">
      Create Free Account &rarr;
    </a>
  </div>

  <!-- FAQ -->
  <div class="section-label" style="margin-bottom:20px;">&#10067; TTF Gas Price &mdash; FAQs</div>
  <div class="ttf-faq" id="ttf-faq">
    <div class="ttf-faq-item">
      <button class="ttf-faq-q">What is the TTF gas price today?<span class="ttf-faq-icon">+</span></button>
      <div class="ttf-faq-a">{faq_q1}</div>
    </div>
    <div class="ttf-faq-item">
      <button class="ttf-faq-q">What is TTF?<span class="ttf-faq-icon">+</span></button>
      <div class="ttf-faq-a">TTF stands for Title Transfer Facility, the leading European natural gas benchmark. It is the primary reference price for gas delivered into the Dutch virtual trading hub and is used across European energy contracts, utility pricing, and financial derivatives.</div>
    </div>
    <div class="ttf-faq-item">
      <button class="ttf-faq-q">Why is TTF the most important European gas benchmark?<span class="ttf-faq-icon">+</span></button>
      <div class="ttf-faq-a">TTF is the most liquid gas trading hub in Europe and serves as the reference for the vast majority of European gas contracts. It replaced the UK NBP as the dominant benchmark after the 2021&ndash;2022 energy crisis, when LNG flows made Europe more interconnected with global gas markets.</div>
    </div>
    <div class="ttf-faq-item">
      <button class="ttf-faq-q">How often is this page updated?<span class="ttf-faq-icon">+</span></button>
      <div class="ttf-faq-a">{faq_q3}</div>
    </div>
    <div class="ttf-faq-item">
      <button class="ttf-faq-q">What affects TTF gas prices?<span class="ttf-faq-icon">+</span></button>
      <div class="ttf-faq-a">TTF is driven by European gas storage levels, LNG import flows, weather demand (heating and cooling), pipeline supply from Norway and Algeria, geopolitical risk (tracked by GERI/EERI), and carbon market dynamics. Our custom algorithm tracks all of these signals daily.</div>
    </div>
    <div class="ttf-faq-item">
      <button class="ttf-faq-q">What is the difference between TTF and JKM (LNG)?<span class="ttf-faq-icon">+</span></button>
      <div class="ttf-faq-a">TTF is the European gas benchmark (EUR/MWh), while JKM (Japan Korea Marker) is the Asian LNG spot benchmark (USD/MMBtu). The TTF&ndash;JKM spread determines whether LNG cargoes head to Europe or Asia. Currently, converted JKM is approximately &#8364;{jkm_eur_mwh:.2f}/MWh against TTF &#8364;{ttf_price:.2f}/MWh.</div>
    </div>
    <div class="ttf-faq-item">
      <button class="ttf-faq-q">Why does TTF spike suddenly?<span class="ttf-faq-icon">+</span></button>
      <div class="ttf-faq-a">TTF spikes are triggered by cold weather forecasts, supply disruption events (pipeline outages, LNG facility issues), geopolitical escalation in supply regions, unexpected falls in European storage levels, or technical market dynamics during peak winter demand.</div>
    </div>
    <div class="ttf-faq-item">
      <button class="ttf-faq-q">Can I download TTF gas price data?<span class="ttf-faq-icon">+</span></button>
      <div class="ttf-faq-a">Yes. Use the Download CSV button in the historical data table above to export all {total_rows} daily TTF records in CSV format. The endpoint is <a href="/api/ttf-gas-prices.csv" style="color:#60a5fa;">/api/ttf-gas-prices.csv</a>.</div>
    </div>
  </div>

  <!-- CITATION -->
  <div class="section-label" style="margin-bottom:20px;">&#128196; Citation &amp; Reference</div>
  <div class="snap-cite-card" style="margin-bottom:40px;">
    <h3>How to Cite This Data</h3>
    <p class="snap-cite-desc">
      This page is updated daily with fresh TTF gas price data from the EnergyRiskIQ production pipeline.
      To reference this data in research, journalism, or professional reports, use the citation below.
    </p>
    <div class="snap-cite-code-wrap">
      <pre class="snap-cite-code">EnergyRiskIQ. (2026). <em>TTF Gas Price &mdash; {date_str}</em>.
Retrieved from <a href="{BASE_URL}/data/ttf-gas-price-today">{BASE_URL}/data/ttf-gas-price-today</a>
Data source: OilPriceAPI daily. {total_rows} records from {_fmt_date(earliest)}.</pre>
      <button class="snap-cite-copy-btn" onclick="this.textContent='Copied!';setTimeout(()=>this.textContent='Copy',2000);navigator.clipboard&&navigator.clipboard.writeText('{cite_copy}')">Copy</button>
    </div>
    <div class="snap-cite-footer">
      Data source: OilPriceAPI. EnergyRiskIQ internal risk pipeline (GERI, EERI, EGSI-M).
      <strong>Not financial advice.</strong>
      See <a href="{BASE_URL}/indices">EnergyRiskIQ Indices</a> for full methodology.
    </div>
  </div>

  <!-- INTERNAL LINKING FOOTER -->
  <div class="section-label" style="margin-bottom:20px;">&#128279; Related Pages</div>
  <div class="ttf-related-grid" style="margin-bottom:40px;">
    <div>
      <div class="ttf-related-group-title">Data</div>
      <a href="/data/europe-lng-supply-demand"   class="ttf-related-link">Europe LNG Supply &amp; Demand</a>
      <a href="/data/jkm-lng-spot-price"         class="ttf-related-link">JKM LNG Spot Price Today</a>
      <a href="/gas-storage-levels-in-europe"    class="ttf-related-link">Gas Storage Levels Europe</a>
      <a href="/data/global-energy-risk-forecast" class="ttf-related-link">Global Energy Risk Forecast</a>
      <a href="/data/energy-risk-snapshot"       class="ttf-related-link">Energy Risk Snapshot</a>
    </div>
    <div>
      <div class="ttf-related-group-title">Indices</div>
      <a href="/indices/global-energy-risk-index"  class="ttf-related-link">Global Energy Risk Index (GERI)</a>
      <a href="/indices/europe-energy-risk-index"  class="ttf-related-link">Europe Energy Risk Index (EERI)</a>
      <a href="/indices/europe-gas-stress-index"   class="ttf-related-link">Europe Gas Stress Index (EGSI)</a>
      <a href="/indices"                           class="ttf-related-link">All EnergyRiskIQ Indices</a>
    </div>
    <div>
      <div class="ttf-related-group-title">Research</div>
      <a href="/research/global-energy-risk-timeline" class="ttf-related-link">Global Energy Risk Timeline</a>
      <a href="/research/global-energy-risk-index"    class="ttf-related-link">GERI Research &amp; Methodology</a>
      <a href="/indices/europe-gas-stress-index"      class="ttf-related-link">EGSI Methodology</a>
    </div>
  </div>

  <!-- CTA -->
  <div class="cta-section">
    <div class="cta-label">Daily TTF Intelligence</div>
    <h2 class="cta-headline">Track European Gas Risk,<br>Not Just the Gas Price</h2>
    <p class="cta-sub">
      TTF tells you what the market is doing. EnergyRiskIQ explains <em>why</em> &mdash;
      combining gas price data with real-time GERI, EERI, and EGSI risk signals.
    </p>
    <a href="/users" class="cta-btn">Get Free Access &rarr;</a>
    <a href="/indices" class="cta-secondary">Explore All Risk Indices</a>
  </div>

</main>

<footer class="page-footer">
  <div>
    &copy; 2026 EnergyRiskIQ &bull;
    <a href="/">Home</a>
    <a href="/indices">Indices</a>
    <a href="/data/ttf-gas-price-today">TTF Gas Price</a>
    <a href="/data/jkm-lng-spot-price">JKM LNG Price</a>
    <a href="/data/global-energy-risk-forecast">Forecast</a>
    <a href="/sitemap-index.xml">Sitemap</a>
    &bull; Not financial advice.
  </div>
</footer>

<!-- ── JavaScript ── -->
<script>
// ── Chart period toggle
function ttfSetPeriod(period, btn) {{
  ['7d','30d','90d','ytd','all'].forEach(function(p) {{
    document.getElementById('ttf-chart-' + p).style.display = 'none';
  }});
  document.getElementById('ttf-chart-' + period).style.display = 'block';
  document.querySelectorAll('.ttf-period-btn').forEach(function(b) {{
    b.classList.remove('active');
  }});
  if (btn) btn.classList.add('active');
}}

// ── Table pagination
var _ttfPage = 1;
var _ttfPerPage = 25;
var _ttfRows = [];
var _ttfFiltered = [];
var _ttfSortCol = 'date';
var _ttfSortAsc = false;

function ttfInitTable() {{
  var tbody = document.getElementById('ttf-tbody');
  _ttfRows = Array.from(tbody.querySelectorAll('tr'));
  _ttfFiltered = _ttfRows.slice();
  ttfRenderTable();
}}

function ttfRenderTable() {{
  var tbody = document.getElementById('ttf-tbody');
  tbody.innerHTML = '';
  var start = (_ttfPage - 1) * _ttfPerPage;
  var end   = Math.min(start + _ttfPerPage, _ttfFiltered.length);
  for (var i = start; i < end; i++) {{
    tbody.appendChild(_ttfFiltered[i]);
  }}
  var total = _ttfFiltered.length;
  document.getElementById('ttf-page-info').innerHTML =
    'Showing ' + (start + 1) + '&ndash;' + end + ' of ' + total;
  document.getElementById('ttf-page-num').textContent = 'Page ' + _ttfPage;
  document.getElementById('ttf-prev').disabled = _ttfPage === 1;
  document.getElementById('ttf-next').disabled = end >= total;
}}

function ttfPrevPage() {{ if (_ttfPage > 1) {{ _ttfPage--; ttfRenderTable(); }} }}
function ttfNextPage() {{
  var maxPage = Math.ceil(_ttfFiltered.length / _ttfPerPage);
  if (_ttfPage < maxPage) {{ _ttfPage++; ttfRenderTable(); }}
}}

function ttfFilterTable() {{
  var q = document.getElementById('ttf-search').value.toLowerCase();
  _ttfFiltered = _ttfRows.filter(function(r) {{
    return r.getAttribute('data-date').indexOf(q) >= 0 ||
           r.textContent.toLowerCase().indexOf(q) >= 0;
  }});
  _ttfPage = 1;
  ttfRenderTable();
}}

function ttfSort(col) {{
  if (_ttfSortCol === col) {{ _ttfSortAsc = !_ttfSortAsc; }} else {{ _ttfSortCol = col; _ttfSortAsc = false; }}
  _ttfFiltered.sort(function(a, b) {{
    var va, vb;
    if (col === 'date') {{
      va = a.getAttribute('data-date'); vb = b.getAttribute('data-date');
    }} else {{
      var colIdx = {{price:1, chg:2, pct:3}}[col] || 1;
      va = parseFloat(a.cells[colIdx].textContent.replace(/[^0-9\.\-]/g,'')) || 0;
      vb = parseFloat(b.cells[colIdx].textContent.replace(/[^0-9\.\-]/g,'')) || 0;
    }}
    if (va < vb) return _ttfSortAsc ? -1 : 1;
    if (va > vb) return _ttfSortAsc ?  1 : -1;
    return 0;
  }});
  _ttfPage = 1;
  ttfRenderTable();
}}

function ttfCopyData() {{
  var lines = ['Date\\tTTF Price (EUR/MWh)\\t24h Change\\t24h %\\tSource'];
  _ttfRows.forEach(function(r) {{
    var cells = Array.from(r.cells).map(function(c){{ return c.textContent.trim(); }});
    lines.push(cells.join('\\t'));
  }});
  navigator.clipboard && navigator.clipboard.writeText(lines.join('\\n'));
  var btn = event.target;
  btn.textContent = 'Copied!';
  setTimeout(function(){{ btn.innerHTML = '&#128203; Copy data'; }}, 2000);
}}

// ── FAQ accordion
document.querySelectorAll('#ttf-faq .ttf-faq-q').forEach(function(btn) {{
  btn.addEventListener('click', function() {{
    var item = btn.parentElement;
    var isOpen = item.classList.contains('open');
    document.querySelectorAll('#ttf-faq .ttf-faq-item').forEach(function(i){{ i.classList.remove('open'); }});
    if (!isOpen) item.classList.add('open');
  }});
}});

ttfInitTable();
</script>
</body>
</html>"""


# ── Route Handlers ────────────────────────────────────────────────────────────

@router.get("/data/ttf-gas-price-today")
async def ttf_page():
    """TTF Gas Price Today — SEO-optimised daily European natural gas benchmark page."""
    async def _stream():
        yield _TTF_LOADER
        try:
            data = _fetch_ttf_data()
            yield _build_ttf_html(data)
        except Exception as exc:
            logger.error(f"TTF page error: {exc}", exc_info=True)
            yield "<script>var l=document.getElementById('snap-loader');if(l){{l.innerHTML='<p style=\"color:#ef4444;text-align:center;padding:40px;\">Data temporarily unavailable. Please refresh.</p>';}}</script>"

    return StreamingResponse(_stream(), media_type="text/html")


@router.get("/api/ttf-gas-prices.csv")
async def ttf_csv():
    """CSV download of all TTF gas price data."""
    try:
        rows = execute_production_query(
            "SELECT date, ttf_price, currency, unit, source "
            "FROM ttf_gas_snapshots WHERE ttf_price IS NOT NULL ORDER BY date DESC"
        ) or []
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["Date", "TTF Price (EUR/MWh)", "Currency", "Unit", "Source"])
        for row in rows:
            writer.writerow([
                _fmt_date_iso(row.get("date")),
                row.get("ttf_price", ""),
                row.get("currency", "EUR"),
                row.get("unit", "mwh"),
                row.get("source", ""),
            ])
        return Response(
            content=buf.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="ttf-gas-prices.csv"'},
        )
    except Exception as exc:
        logger.error(f"TTF CSV error: {exc}")
        return Response("Error generating CSV", status_code=500)
