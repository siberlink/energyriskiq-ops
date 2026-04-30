"""
JKM LNG Spot Price Page
Route: /data/jkm-lng-spot-price
SEO-optimised daily Japan Korea Marker LNG price data, chart, history table, and risk context.
"""
import io
import csv
import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, StreamingResponse, Response

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

# ── SVG Line Chart Builder ────────────────────────────────────────────────────

def _build_jkm_chart_svg(rows, color="#d4a017", W=700, H=220):
    """Server-side SVG line chart with area fill for JKM price history."""
    if not rows or len(rows) < 2:
        return '<div style="text-align:center;color:#475569;padding:40px 0;">No data available</div>'

    vals  = [float(r.get("jkm_price") or 0) for r in rows]
    dates = [r.get("date") for r in rows]
    n = len(vals)

    PAD_L, PAD_R, PAD_T, PAD_B = 54, 18, 16, 40
    cw = W - PAD_L - PAD_R
    ch = H - PAD_T - PAD_B

    vmin = min(vals) * 0.992
    vmax = max(vals) * 1.008
    rng  = vmax - vmin or 1

    def xp(i):  return PAD_L + (i / (n - 1)) * cw
    def yp(v):  return PAD_T + ch - ((v - vmin) / rng) * ch

    pts     = [(xp(i), yp(v)) for i, v in enumerate(vals)]
    path_d  = f"M {pts[0][0]:.1f} {pts[0][1]:.1f}" + "".join(f" L {px:.1f} {py:.1f}" for px, py in pts[1:])
    area_d  = (path_d + f" L {pts[-1][0]:.1f} {PAD_T + ch:.1f} L {pts[0][0]:.1f} {PAD_T + ch:.1f} Z")

    # Y-axis
    y_svg = ""
    for i in range(5):
        v  = vmin + (vmax - vmin) * (i / 4)
        yc = yp(v)
        y_svg += (
            f'<line x1="{PAD_L}" y1="{yc:.1f}" x2="{W - PAD_R}" y2="{yc:.1f}" '
            f'stroke="rgba(255,255,255,0.05)" stroke-width="1"/>'
            f'<text x="{PAD_L - 6}" y="{yc + 4:.1f}" text-anchor="end" '
            f'font-size="10" fill="#475569" font-family="Inter,sans-serif">${v:.2f}</text>'
        )

    # X-axis labels (max 6 evenly spaced)
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

    # Data circles for smaller datasets
    circles = ""
    if n <= 31:
        for i, (px, py) in enumerate(pts):
            circles += (
                f'<circle cx="{px:.1f}" cy="{py:.1f}" r="3.5" '
                f'fill="{color}" stroke="#0f172a" stroke-width="1.5"/>'
            )

    grad_id = f"jkm-area-{W}"
    return f"""<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" style="width:100%;display:block;overflow:visible">
  <defs>
    <linearGradient id="{grad_id}" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="{color}" stop-opacity="0.22"/>
      <stop offset="100%" stop-color="{color}" stop-opacity="0.01"/>
    </linearGradient>
  </defs>
  {y_svg}
  {x_svg}
  <path d="{area_d}" fill="url(#{grad_id})"/>
  <path d="{path_d}" fill="none" stroke="{color}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
  {circles}
</svg>"""


# ── Page-specific CSS ─────────────────────────────────────────────────────────

_JKM_CSS = """
/* ── JKM page layout ── */
.jkm-metric-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 40px;
}
@media (max-width: 900px) { .jkm-metric-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 480px) { .jkm-metric-grid { grid-template-columns: 1fr 1fr; } }

.jkm-metric-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 18px 20px;
  transition: border-color 0.2s;
}
.jkm-metric-card:hover { border-color: rgba(212,160,23,0.35); }
.jkm-metric-label {
  font-size: 10px; font-weight: 700; letter-spacing: 1.6px;
  text-transform: uppercase; color: var(--muted); margin-bottom: 8px;
}
.jkm-metric-value {
  font-size: 26px; font-weight: 800; line-height: 1.1;
  font-variant-numeric: tabular-nums;
}
.jkm-metric-sub {
  font-size: 11px; color: var(--muted); margin-top: 6px;
}

/* ── Chart section ── */
.jkm-chart-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 16px;
  overflow: hidden;
  margin-bottom: 40px;
}
.jkm-chart-header {
  padding: 20px 24px 16px;
  border-bottom: 1px solid rgba(255,255,255,0.06);
  display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px;
}
.jkm-chart-title {
  font-size: 13px; font-weight: 700; color: #e2e8f0;
}
.jkm-period-btns {
  display: flex; gap: 6px;
}
.jkm-period-btn {
  background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.1);
  color: #64748b; padding: 4px 12px; font-size: 11px; font-weight: 700;
  border-radius: 6px; cursor: pointer; transition: all 0.18s; font-family: inherit;
  letter-spacing: 0.04em;
}
.jkm-period-btn.active, .jkm-period-btn:hover {
  background: rgba(212,160,23,0.15); border-color: rgba(212,160,23,0.4);
  color: #d4a017;
}
.jkm-chart-body { padding: 20px 20px 12px; }

/* ── Snapshot table ── */
.jkm-snapshot-table {
  width: 100%; border-collapse: collapse; margin-top: 16px;
}
.jkm-snapshot-table td {
  padding: 10px 14px; border-bottom: 1px solid rgba(255,255,255,0.05);
  font-size: 14px;
}
.jkm-snapshot-table td:first-child { color: #94a3b8; font-size: 13px; }
.jkm-snapshot-table td:last-child  { font-weight: 600; text-align: right; }
.jkm-snapshot-table tr:last-child td { border-bottom: none; }

/* ── History table ── */
.jkm-history-table {
  width: 100%; border-collapse: collapse;
  font-size: 13px;
}
.jkm-history-table th {
  text-align: left; padding: 10px 14px;
  font-size: 10px; font-weight: 700; letter-spacing: 1.2px;
  text-transform: uppercase; color: #64748b;
  border-bottom: 1px solid var(--border);
  background: rgba(255,255,255,0.02);
  cursor: pointer; user-select: none;
  white-space: nowrap;
}
.jkm-history-table th:hover { color: #d4a017; }
.jkm-history-table td {
  padding: 9px 14px; border-bottom: 1px solid rgba(255,255,255,0.04);
  color: #cbd5e1; font-variant-numeric: tabular-nums;
}
.jkm-history-table tr:hover td { background: rgba(255,255,255,0.02); }
.jkm-history-table tr:last-child td { border-bottom: none; }
.jkm-table-wrap {
  background: var(--card); border: 1px solid var(--border);
  border-radius: 16px; overflow: hidden; margin-bottom: 16px;
}
.jkm-table-controls {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 20px; border-bottom: 1px solid rgba(255,255,255,0.06);
  flex-wrap: wrap; gap: 10px;
}
.jkm-table-search {
  background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.1);
  color: #e2e8f0; padding: 7px 14px; border-radius: 8px;
  font-size: 13px; font-family: inherit; outline: none;
  width: 200px;
}
.jkm-table-search::placeholder { color: #475569; }
.jkm-table-search:focus { border-color: rgba(212,160,23,0.4); }
.jkm-table-actions { display: flex; gap: 8px; }
.jkm-btn {
  background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.12);
  color: #94a3b8; padding: 6px 14px; font-size: 12px; font-weight: 600;
  border-radius: 8px; cursor: pointer; font-family: inherit;
  transition: all 0.18s; text-decoration: none; display: inline-flex; align-items: center; gap: 6px;
}
.jkm-btn:hover { border-color: rgba(212,160,23,0.4); color: #d4a017; }
.jkm-btn-gold {
  background: linear-gradient(135deg, rgba(212,160,23,0.15), rgba(251,191,36,0.12));
  border-color: rgba(212,160,23,0.35); color: #d4a017;
}
.jkm-btn-gold:hover { background: linear-gradient(135deg, rgba(212,160,23,0.25), rgba(251,191,36,0.2)); }
.jkm-pagination {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 20px; flex-wrap: wrap; gap: 8px;
}
.jkm-pagination-info { font-size: 12px; color: #475569; }
.jkm-pagination-btns { display: flex; gap: 6px; }
.jkm-page-btn {
  background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.1);
  color: #64748b; padding: 4px 10px; font-size: 12px; font-weight: 600;
  border-radius: 6px; cursor: pointer; font-family: inherit; transition: all 0.18s;
}
.jkm-page-btn:hover, .jkm-page-btn.active {
  border-color: rgba(212,160,23,0.4); color: #d4a017;
}
.jkm-page-btn:disabled { opacity: 0.35; cursor: default; }

/* ── Driver cards ── */
.jkm-driver-grid {
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px;
  margin-bottom: 40px;
}
@media (max-width: 800px) { .jkm-driver-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 480px) { .jkm-driver-grid { grid-template-columns: 1fr; } }
.jkm-driver-card {
  background: var(--card); border: 1px solid var(--border);
  border-radius: 14px; padding: 20px 18px;
  transition: border-color 0.2s, transform 0.2s;
}
.jkm-driver-card:hover { border-color: rgba(212,160,23,0.3); transform: translateY(-2px); }
.jkm-driver-icon { font-size: 1.6rem; margin-bottom: 10px; }
.jkm-driver-title { font-size: 13px; font-weight: 700; color: #e2e8f0; margin-bottom: 6px; }
.jkm-driver-desc { font-size: 12px; color: #64748b; line-height: 1.6; }

/* ── Risk context chips ── */
.jkm-risk-grid {
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px;
  margin-bottom: 40px;
}
@media (max-width: 700px) { .jkm-risk-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 400px) { .jkm-risk-grid { grid-template-columns: 1fr; } }
.jkm-risk-chip {
  background: var(--card); border: 1px solid var(--border);
  border-radius: 12px; padding: 16px 18px; text-align: center;
}
.jkm-risk-chip-label {
  font-size: 9px; font-weight: 700; letter-spacing: 1.8px;
  text-transform: uppercase; color: #475569; margin-bottom: 8px;
}
.jkm-risk-chip-val {
  font-size: 22px; font-weight: 800; font-variant-numeric: tabular-nums;
}
.jkm-risk-chip-band {
  font-size: 10px; font-weight: 700; letter-spacing: 0.08em;
  text-transform: uppercase; margin-top: 4px;
}

/* ── Benchmark comparison cards ── */
.jkm-bench-grid {
  display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px;
  margin-bottom: 40px;
}
@media (max-width: 640px) { .jkm-bench-grid { grid-template-columns: 1fr; } }
.jkm-bench-card {
  background: var(--card); border: 1px solid var(--border);
  border-radius: 14px; padding: 20px 22px;
}
.jkm-bench-title { font-size: 13px; font-weight: 700; color: var(--gold); margin-bottom: 8px; }
.jkm-bench-desc { font-size: 13px; color: #94a3b8; line-height: 1.6; margin-bottom: 10px; }
.jkm-coming-soon {
  display: inline-block; font-size: 10px; font-weight: 700; letter-spacing: 1.2px;
  text-transform: uppercase; color: #475569;
  border: 1px solid #334155; border-radius: 20px; padding: 2px 10px;
}

/* ── Wheel grid ── */
.jkm-wheel-grid {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px;
  margin-bottom: 40px;
}
@media (max-width: 800px) { .jkm-wheel-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 480px) { .jkm-wheel-grid { grid-template-columns: 1fr 1fr; } }
.jkm-wheel-link {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  text-align: center; gap: 8px;
  background: var(--card); border: 1px solid var(--border);
  border-radius: 14px; padding: 20px 12px;
  text-decoration: none; color: inherit;
  transition: border-color 0.2s, box-shadow 0.2s, transform 0.2s;
}
.jkm-wheel-link:hover {
  border-color: rgba(212,160,23,0.4);
  box-shadow: 0 0 20px rgba(212,160,23,0.08);
  transform: translateY(-2px);
}
.jkm-wheel-icon { font-size: 1.7rem; }
.jkm-wheel-label {
  font-size: 11px; font-weight: 700; letter-spacing: 0.08em;
  text-transform: uppercase; color: var(--gold);
}
.jkm-wheel-desc { font-size: 11px; color: var(--muted); line-height: 1.4; }

/* ── FAQ ── */
.jkm-faq { margin-bottom: 40px; }
.jkm-faq-item { border-bottom: 1px solid rgba(255,255,255,0.06); }
.jkm-faq-q {
  width: 100%; text-align: left; background: none; border: none;
  color: #e2e8f0; font-size: 15px; font-weight: 600; font-family: inherit;
  padding: 18px 0; cursor: pointer;
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
}
.jkm-faq-q:hover { color: #d4a017; }
.jkm-faq-icon {
  font-size: 18px; font-weight: 300; color: #475569;
  flex-shrink: 0; transition: transform 0.2s;
}
.jkm-faq-item.open .jkm-faq-icon { transform: rotate(45deg); color: #d4a017; }
.jkm-faq-a {
  display: none; font-size: 14px; color: #94a3b8;
  line-height: 1.7; padding: 0 0 16px;
}
.jkm-faq-item.open .jkm-faq-a { display: block; }

/* ── Cite card (from shared CSS, local override for this page) ── */
.snap-cite-card {
  background: #1e293b; border: 1px solid #334155;
  border-radius: 12px; padding: 24px 28px; margin-bottom: 32px;
}
.snap-cite-card h3 { font-size: 1.05rem; font-weight: 700; color: #f1f5f9; margin-bottom: 10px; }
.snap-cite-desc { font-size: 14px; color: #94a3b8; margin-bottom: 18px; line-height: 1.6; }
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
.snap-cite-footer { margin-top: 14px; font-size: 12px; color: #64748b; }
.snap-cite-footer a { color: #60a5fa; text-decoration: none; }

/* ── Mobile responsive ── */
@media (max-width: 640px) {
  html, body { overflow-x: hidden; max-width: 100%; }
  .hero { padding-left: 16px; padding-right: 16px; }
  .nav-inner { padding: 0 1rem; }
  .nav-inner > div a:not(.cta-btn-nav) { display: none; }
  .jkm-chart-header { flex-direction: column; align-items: flex-start; }
  .snap-cite-card { padding: 18px 16px; overflow: hidden; }
  .snap-cite-code-wrap { overflow-x: auto; padding: 14px; }
  .snap-cite-code { white-space: pre-wrap !important; overflow-wrap: break-word; word-break: break-word; font-size: 11px; }
  .snap-cite-copy-btn { position: static !important; display: block; width: 100%; box-sizing: border-box; text-align: center; margin-top: 12px; }
  .jkm-table-controls { flex-direction: column; align-items: flex-start; }
  .jkm-table-search { width: 100%; }
}
"""

# ── Loader ────────────────────────────────────────────────────────────────────

_JKM_LOADER = _LOADER_HTML.replace(
    "Global Energy Risk Snapshot | EnergyRiskIQ",
    "JKM LNG Spot Price Today | Japan Korea Marker Chart &amp; Daily Data | EnergyRiskIQ",
).replace(
    'name="description" content="Live global energy risk snapshot. Current GERI, EERI and EGSI-M index values with Brent crude, TTF gas, VIX and LNG market prices."',
    'name="description" content="Track the JKM LNG spot price today with daily Japan Korea Marker data, 24h change, historical chart, and LNG market risk context from EnergyRiskIQ."',
).replace(
    'rel="canonical" href="https://energyriskiq.com/data/energy-risk-snapshot"',
    'rel="canonical" href="https://energyriskiq.com/data/jkm-lng-spot-price"',
).replace(
    "Fetching GERI\u00a0&\u00a0EERI indices\u2026",
    "Fetching JKM price history\u2026",
).replace(
    '<span class="ld-tag">GERI</span>\n    <span class="ld-tag">EERI</span>\n    <span class="ld-tag">EGSI&#8209;M</span>\n    <span class="ld-tag">Brent</span>\n    <span class="ld-tag">TTF</span>',
    '<span class="ld-tag">JKM LNG</span>\n    <span class="ld-tag">Asia LNG</span>\n    <span class="ld-tag">GERI</span>\n    <span class="ld-tag">EERI</span>',
)

# ── Data fetcher ──────────────────────────────────────────────────────────────

def _fetch_jkm_data():
    latest = execute_production_one(
        "SELECT date, jkm_price, jkm_change_24h, jkm_change_pct, source "
        "FROM lng_price_snapshots ORDER BY date DESC LIMIT 1"
    ) or {}

    stats = execute_production_one(
        "SELECT COUNT(*) AS total, MIN(date) AS earliest, MAX(date) AS latest, "
        "ROUND(MAX(jkm_price)::numeric,2) AS highest, "
        "ROUND(MIN(jkm_price)::numeric,2) AS lowest, "
        "ROUND(AVG(jkm_price)::numeric,2) AS avg_price "
        "FROM lng_price_snapshots WHERE jkm_price IS NOT NULL"
    ) or {}

    all_rows = execute_production_query(
        "SELECT date, jkm_price, jkm_change_24h, jkm_change_pct, source "
        "FROM lng_price_snapshots WHERE jkm_price IS NOT NULL ORDER BY date DESC"
    ) or []

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

    ttf_latest = execute_production_one(
        "SELECT date, ttf_price FROM ttf_gas_snapshots ORDER BY date DESC LIMIT 1"
    ) or {}

    return dict(latest=latest, stats=stats, all_rows=all_rows,
                geri=geri, eeri=eeri, egsi=egsi, ttf_latest=ttf_latest)


# ── Page HTML builder ─────────────────────────────────────────────────────────

def _build_jkm_html(data: dict) -> str:
    latest   = data["latest"]
    stats    = data["stats"]
    all_rows = data["all_rows"]   # newest first
    geri     = data["geri"]
    eeri     = data["eeri"]
    egsi     = data["egsi"]
    ttf      = data["ttf_latest"]

    # ── Current price metrics
    jkm_price  = _safe_float(latest.get("jkm_price"))
    jkm_chg    = _safe_float(latest.get("jkm_change_24h"))
    jkm_chg_pct = _safe_float(latest.get("jkm_change_pct"))
    latest_date = latest.get("date")
    source_raw  = str(latest.get("source", "OilPrice / Firecrawl"))
    source_display = "OilPrice / Firecrawl"

    total_rows  = int(stats.get("total") or 0)
    earliest    = stats.get("earliest")
    stat_latest = stats.get("latest")
    highest     = _safe_float(stats.get("highest"))
    lowest      = _safe_float(stats.get("lowest"))
    avg_price   = _safe_float(stats.get("avg_price"))

    chg_color   = _chg_color(jkm_chg)
    arrow       = _arrow(jkm_chg)
    sign        = _sign(jkm_chg)

    date_str    = _fmt_date(latest_date)
    date_range  = f"{_fmt_date(earliest)} &rarr; {_fmt_date(stat_latest)}"

    # ── Index values
    geri_val  = int(_safe_float(geri.get("value")))
    geri_band = str(geri.get("band", "—"))
    eeri_val  = int(_safe_float(eeri.get("value")))
    eeri_band = str(eeri.get("band", "—"))
    egsi_val  = round(_safe_float(egsi.get("value")), 1)
    egsi_band = str(egsi.get("band", "—"))

    gc = BAND_COLORS.get(geri_band, "#f97316")
    ec = BAND_COLORS.get(eeri_band, "#ef4444")
    xc = BAND_COLORS.get(egsi_band, "#eab308")

    ttf_price   = _safe_float(ttf.get("ttf_price"))

    # ── Build chart data sets (rows newest-first → reverse for chart oldest-first)
    rows_all = list(reversed(all_rows))

    def _period_rows(n):
        return rows_all[-n:] if len(rows_all) >= n else rows_all

    rows_7d  = _period_rows(7)
    rows_30d = _period_rows(30)
    rows_90d = _period_rows(90)

    svg_7d  = _build_jkm_chart_svg(rows_7d,  W=700, H=200)
    svg_30d = _build_jkm_chart_svg(rows_30d, W=700, H=200)
    svg_90d = _build_jkm_chart_svg(rows_90d, W=700, H=200)
    svg_all = _build_jkm_chart_svg(rows_all, W=700, H=200)

    # ── History table HTML (all rows, newest first — JS paginates)
    def _chg_td(v):
        c = _chg_color(v)
        s = _sign(v)
        return f'<td style="color:{c};font-weight:600;">{s}{v:.2f}</td>'

    def _pct_td(v):
        c = _chg_color(v)
        s = _sign(v)
        return f'<td style="color:{c};">{s}{v:.2f}%</td>'

    table_rows_html = ""
    for row in all_rows:
        d  = row.get("date")
        p  = _safe_float(row.get("jkm_price"))
        ch = _safe_float(row.get("jkm_change_24h"))
        cp = _safe_float(row.get("jkm_change_pct"))
        src = str(row.get("source", "—")).split(".")[0].capitalize()
        table_rows_html += (
            f'<tr data-date="{_fmt_date_iso(d)}">'
            f'<td>{_fmt_date(d)}</td>'
            f'<td style="font-weight:700;color:#e2e8f0;">${p:.2f}</td>'
            + _chg_td(ch) + _pct_td(cp) +
            f'<td style="color:#475569;font-size:12px;">{src}</td>'
            f'</tr>'
        )

    # ── FAQ dynamic answers with live data
    faq_q1_a = f"The latest EnergyRiskIQ reading shows JKM LNG at ${jkm_price:.2f}/MMBtu on {date_str}."

    # ── Citation text
    cite_text = f"EnergyRiskIQ. (2026). JKM LNG Spot Price — {date_str}. Retrieved from {BASE_URL}/data/jkm-lng-spot-price"
    cite_copy = cite_text.replace('"', '\\"')

    # ── Dataset schema (JSON-LD)
    schema_dataset = f"""{{
  "@context": "https://schema.org",
  "@type": "Dataset",
  "name": "JKM LNG Spot Price Daily Snapshots",
  "description": "Daily JKM LNG spot price snapshots including price, 24-hour change, percentage change, date, and source.",
  "url": "{BASE_URL}/data/jkm-lng-spot-price",
  "creator": {{"@type": "Organization", "name": "EnergyRiskIQ", "url": "{BASE_URL}"}},
  "temporalCoverage": "{_fmt_date_iso(earliest)}/{_fmt_date_iso(stat_latest)}",
  "variableMeasured": ["JKM LNG spot price", "24-hour price change", "24-hour percentage change"],
  "keywords": ["JKM LNG price", "JKM LNG spot price today", "Japan Korea Marker", "LNG spot price", "Asia LNG price"]
}}"""

    schema_faq = f"""{{
  "@context": "https://schema.org",
  "@type": "FAQPage",
  "mainEntity": [
    {{"@type": "Question", "name": "What is the JKM LNG price today?",
      "acceptedAnswer": {{"@type": "Answer", "text": "{faq_q1_a}"}}}},
    {{"@type": "Question", "name": "What does JKM mean in LNG?",
      "acceptedAnswer": {{"@type": "Answer", "text": "JKM stands for Japan Korea Marker, a benchmark for spot liquefied natural gas delivered into Northeast Asia."}}}},
    {{"@type": "Question", "name": "How often is this page updated?",
      "acceptedAnswer": {{"@type": "Answer", "text": "EnergyRiskIQ updates the JKM LNG spot price daily."}}}},
    {{"@type": "Question", "name": "How much historical data is available?",
      "acceptedAnswer": {{"@type": "Answer", "text": "EnergyRiskIQ currently tracks {total_rows} daily JKM LNG records from {_fmt_date(earliest)} to {_fmt_date(stat_latest)}."}}}},
    {{"@type": "Question", "name": "Why does JKM matter?",
      "acceptedAnswer": {{"@type": "Answer", "text": "JKM is one of the most important LNG price benchmarks because it reflects Asian spot LNG demand and global cargo competition."}}}}
  ]
}}"""

    return f"""<script>
var l=document.getElementById('snap-loader');
if(l){{l.style.display='none';}}
document.body.style.overflow='';
</script>

<style>{_JKM_CSS}</style>

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
      <a href="/indices/europe-energy-risk-index" style="font-size:13px;color:#94a3b8;text-decoration:none;">EERI</a>
      <a href="/data/global-energy-risk-forecast" style="font-size:13px;color:#94a3b8;text-decoration:none;">Forecast</a>
      <a href="/users" class="cta-btn-nav">Get Free Access</a>
    </div>
  </div>
</nav>

<!-- HERO -->
<header class="hero">
  <div class="hero-date">&#9875; Updated Daily &nbsp;&bull;&nbsp; {date_str} &nbsp;&bull;&nbsp; Japan Korea Marker</div>
  <h1 style="font-family:'DM Serif Display',serif;font-size:clamp(28px,5vw,46px);font-weight:400;color:#fff;line-height:1.2;max-width:720px;margin:0 auto 14px;">
    JKM LNG Spot Price Today
  </h1>
  <p class="hero-sub" style="font-size:clamp(14px,2vw,17px);color:#94a3b8;max-width:640px;margin:0 auto 1.5rem;line-height:1.7;">
    Daily Japan Korea Marker LNG price data, 24-hour change, historical trend, and market risk context for Asia LNG spot markets.
  </p>
  <div style="display:flex;justify-content:center;gap:1rem;flex-wrap:wrap;">
    <span style="font-size:12px;font-weight:600;color:#d4a017;border:1px solid rgba(212,160,23,0.3);border-radius:20px;padding:4px 14px;">
      JKM: ${jkm_price:.2f}/MMBtu
    </span>
    <span style="font-size:12px;font-weight:600;color:{chg_color};border:1px solid {chg_color}33;border-radius:20px;padding:4px 14px;">
      {arrow} {sign}{jkm_chg:.2f} ({sign}{jkm_chg_pct:.2f}%) d/d
    </span>
    <span style="font-size:12px;font-weight:600;color:{gc};border:1px solid {gc}33;border-radius:20px;padding:4px 14px;">
      GERI {geri_val}/100 &bull; {geri_band}
    </span>
  </div>
</header>

<main class="page-body">

  <!-- SECTION LABEL -->
  <div class="section-label" style="margin-bottom:20px;">&#128202; Key Metrics</div>

  <!-- METRIC CARDS -->
  <div class="jkm-metric-grid">
    <div class="jkm-metric-card">
      <div class="jkm-metric-label">JKM LNG Spot Price</div>
      <div class="jkm-metric-value" style="color:#d4a017;">${jkm_price:.2f}</div>
      <div class="jkm-metric-sub">/MMBtu &bull; {date_str}</div>
    </div>
    <div class="jkm-metric-card">
      <div class="jkm-metric-label">24h Change</div>
      <div class="jkm-metric-value" style="color:{chg_color};">{sign}{jkm_chg:.2f}</div>
      <div class="jkm-metric-sub">{sign}{jkm_chg_pct:.2f}% day-over-day</div>
    </div>
    <div class="jkm-metric-card">
      <div class="jkm-metric-label">Dataset Range</div>
      <div class="jkm-metric-value" style="font-size:18px;color:#60a5fa;">{total_rows}</div>
      <div class="jkm-metric-sub">daily records tracked</div>
    </div>
    <div class="jkm-metric-card">
      <div class="jkm-metric-label">Price Range (All)</div>
      <div class="jkm-metric-value" style="font-size:18px;color:#e2e8f0;">${lowest:.2f} &ndash; ${highest:.2f}</div>
      <div class="jkm-metric-sub">Avg ${avg_price:.2f}/MMBtu</div>
    </div>
  </div>

  <!-- CHART -->
  <div class="section-label" style="margin-bottom:20px;">&#128200; JKM LNG Price Chart</div>
  <div class="jkm-chart-card">
    <div class="jkm-chart-header">
      <div class="jkm-chart-title">JKM LNG Spot Price ($/MMBtu) &mdash; {date_str}</div>
      <div class="jkm-period-btns">
        <button class="jkm-period-btn" onclick="jkmSetPeriod('7d',this)">7D</button>
        <button class="jkm-period-btn active" onclick="jkmSetPeriod('30d',this)">30D</button>
        <button class="jkm-period-btn" onclick="jkmSetPeriod('90d',this)">90D</button>
        <button class="jkm-period-btn" onclick="jkmSetPeriod('all',this)">All</button>
      </div>
    </div>
    <div class="jkm-chart-body">
      <div id="jkm-chart-7d"  style="display:none;">{svg_7d}</div>
      <div id="jkm-chart-30d" style="display:block;">{svg_30d}</div>
      <div id="jkm-chart-90d" style="display:none;">{svg_90d}</div>
      <div id="jkm-chart-all" style="display:none;">{svg_all}</div>
      <div style="font-size:11px;color:#334155;margin-top:10px;">
        Source: OilPrice / Firecrawl daily scrape. Updated daily. Not financial advice.
      </div>
    </div>
  </div>

  <!-- TODAY'S SNAPSHOT -->
  <div class="section-label" style="margin-bottom:20px;">&#128247; Today's JKM LNG Market Snapshot</div>
  <div class="main-content" style="margin-bottom:40px;">
    <p style="font-size:15px;color:#cbd5e1;line-height:1.8;margin-bottom:12px;">
      The latest EnergyRiskIQ JKM LNG snapshot shows the Japan Korea Marker at
      <strong style="color:#d4a017;">${jkm_price:.2f}/MMBtu</strong> on {date_str},
      <span style="color:{chg_color};">{arrow} {sign}${jkm_chg:.2f} ({sign}{jkm_chg_pct:.2f}%)</span> on the day.
    </p>
    <p style="font-size:15px;color:#94a3b8;line-height:1.8;margin-bottom:20px;">
      {"This indicates short-term upward pressure in Asian LNG spot pricing, with buyers paying more for flexible LNG cargo exposure." if jkm_chg > 0 else "This indicates short-term softening in Asian LNG spot pricing, with sellers facing lower demand for flexible LNG cargoes." if jkm_chg < 0 else "Asian LNG spot pricing is stable with no significant movement today."}
    </p>
    <div style="background:var(--card);border:1px solid var(--border);border-radius:14px;overflow:hidden;">
      <table class="jkm-snapshot-table">
        <tr><td>Latest price</td><td style="color:#d4a017;">${jkm_price:.2f}/MMBtu</td></tr>
        <tr><td>Daily change</td><td style="color:{chg_color};">{sign}${jkm_chg:.2f}</td></tr>
        <tr><td>Daily % change</td><td style="color:{chg_color};">{sign}{jkm_chg_pct:.2f}%</td></tr>
        <tr><td>Latest date</td><td>{date_str}</td></tr>
        <tr><td>All-time high</td><td>${highest:.2f}/MMBtu</td></tr>
        <tr><td>All-time low</td><td>${lowest:.2f}/MMBtu</td></tr>
        <tr><td>Average price</td><td>${avg_price:.2f}/MMBtu</td></tr>
        <tr><td>Records tracked</td><td>{total_rows} daily snapshots</td></tr>
        <tr><td>Data start</td><td>{_fmt_date(earliest)}</td></tr>
        <tr><td>Source</td><td style="color:#475569;font-size:12px;">{source_display}</td></tr>
      </table>
    </div>
    <p style="font-size:12px;color:#334155;margin-top:10px;">
      EnergyRiskIQ tracks JKM LNG spot price snapshots daily. Data is provided for market intelligence and research purposes, not as investment advice.
    </p>
  </div>

  <!-- HISTORICAL DATA TABLE -->
  <div class="section-label" style="margin-bottom:20px;">&#128196; JKM LNG Price History</div>
  <div class="jkm-table-wrap">
    <div class="jkm-table-controls">
      <input class="jkm-table-search" id="jkm-search" type="text" placeholder="Search by date&hellip;" oninput="jkmFilterTable()">
      <div class="jkm-table-actions">
        <button class="jkm-btn" onclick="jkmCopyData()">&#128203; Copy data</button>
        <a href="/api/jkm-lng-spot-price.csv" class="jkm-btn jkm-btn-gold" download>&#11015; Download CSV</a>
      </div>
    </div>
    <div style="overflow-x:auto;">
      <table class="jkm-history-table" id="jkm-table">
        <thead>
          <tr>
            <th onclick="jkmSort('date')">Date &#8597;</th>
            <th onclick="jkmSort('price')">JKM Price &#8597;</th>
            <th onclick="jkmSort('chg')">24h Change &#8597;</th>
            <th onclick="jkmSort('pct')">24h % &#8597;</th>
            <th>Source</th>
          </tr>
        </thead>
        <tbody id="jkm-tbody">{table_rows_html}</tbody>
      </table>
    </div>
    <div class="jkm-pagination">
      <div class="jkm-pagination-info" id="jkm-page-info">Showing 1&ndash;25 of {total_rows}</div>
      <div class="jkm-pagination-btns">
        <button class="jkm-page-btn" id="jkm-prev" onclick="jkmPrevPage()" disabled>&#8592; Prev</button>
        <span id="jkm-page-num" style="font-size:12px;color:#475569;padding:0 8px;line-height:28px;">Page 1</span>
        <button class="jkm-page-btn" id="jkm-next" onclick="jkmNextPage()">Next &#8594;</button>
      </div>
    </div>
  </div>
  <div style="text-align:center;margin-bottom:40px;">
    <p style="font-size:13px;color:#475569;margin-bottom:12px;">Need LNG price history with risk context?</p>
    <a href="/users" class="jkm-btn jkm-btn-gold" style="display:inline-flex;">Create a free EnergyRiskIQ account &rarr;</a>
  </div>

  <!-- WHAT IS JKM -->
  <div class="section-label" style="margin-bottom:20px;">&#128218; What Is the JKM LNG Spot Price?</div>
  <div class="main-content" style="margin-bottom:40px;">
    <h2 style="font-size:1.3rem;font-weight:700;color:#f1f5f9;margin-bottom:14px;">What Is the JKM LNG Spot Price?</h2>
    <p style="font-size:15px;color:#cbd5e1;line-height:1.8;margin-bottom:12px;">
      The <strong style="color:#e2e8f0;">JKM LNG price</strong>, also known as the <strong style="color:#e2e8f0;">Japan Korea Marker</strong>, is a key benchmark for spot liquefied natural gas delivered into Northeast Asia. It is widely followed by LNG traders, energy analysts, utilities, and risk teams because it reflects the cost of flexible LNG cargoes in one of the world&rsquo;s most important demand regions.
    </p>
    <p style="font-size:15px;color:#94a3b8;line-height:1.8;">
      JKM is assessed daily by S&amp;P Global Platts and is used as a reference price in LNG supply contracts, financial derivatives, and risk management frameworks across Asia and globally. Unlike pipeline gas, LNG is transported by ship — making JKM highly sensitive to shipping costs, geopolitical supply disruption, and competition from European buyers.
    </p>
  </div>

  <!-- WHAT DRIVES JKM -->
  <div class="section-label" style="margin-bottom:20px;">&#127919; What Moves the JKM LNG Spot Price?</div>
  <div class="jkm-driver-grid">
    <div class="jkm-driver-card">
      <div class="jkm-driver-icon">&#127981;</div>
      <div class="jkm-driver-title">Asian Demand</div>
      <div class="jkm-driver-desc">Japan, South Korea, China, and Taiwan drive the bulk of Northeast Asian LNG demand. Seasonal peaks and industrial activity directly move spot prices.</div>
    </div>
    <div class="jkm-driver-card">
      <div class="jkm-driver-icon">&#127757;</div>
      <div class="jkm-driver-title">European LNG Competition</div>
      <div class="jkm-driver-desc">When Europe competes aggressively for LNG cargoes — especially in winter — JKM rises as supply tightens in the Atlantic basin.</div>
    </div>
    <div class="jkm-driver-card">
      <div class="jkm-driver-icon">&#127783;&#65039;</div>
      <div class="jkm-driver-title">Weather Patterns</div>
      <div class="jkm-driver-desc">Cold winters and hot summers sharply increase gas demand for heating and power generation, creating rapid spikes in LNG spot prices.</div>
    </div>
    <div class="jkm-driver-card">
      <div class="jkm-driver-icon">&#128674;</div>
      <div class="jkm-driver-title">Shipping &amp; Freight</div>
      <div class="jkm-driver-desc">LNG carrier availability, Panama Canal restrictions, and route disruptions affect the effective delivered cost and cargo economics.</div>
    </div>
    <div class="jkm-driver-card">
      <div class="jkm-driver-icon">&#128481;&#65039;</div>
      <div class="jkm-driver-title">Geopolitical Risk</div>
      <div class="jkm-driver-desc">Supply shocks, sanctions, chokepoint disruptions, and war risk in key supply regions create sudden pricing dislocations in spot markets.</div>
    </div>
    <div class="jkm-driver-card">
      <div class="jkm-driver-icon">&#128202;</div>
      <div class="jkm-driver-title">Storage &amp; Inventory</div>
      <div class="jkm-driver-desc">Low gas storage levels in importing countries raise urgency for spot LNG buying, amplifying price moves during peak demand periods.</div>
    </div>
  </div>

  <!-- RISK CONTEXT -->
  <div class="section-label" style="margin-bottom:20px;">&#9888;&#65039; JKM LNG Price and Energy Risk Context</div>
  <div class="forecast-box" style="margin-bottom:24px;">
    <div class="forecast-box-label">EnergyRiskIQ Risk Intelligence Context</div>
    <p class="interp-para">
      Price alone does not explain LNG risk. A rising JKM price may reflect normal seasonal demand, but it may also signal tightening supply, regional competition for LNG cargoes, or geopolitical pressure on global gas flows.
    </p>
    <p class="interp-para">
      EnergyRiskIQ connects JKM price movement with broader energy risk indicators such as European gas stress, global escalation risk, LNG supply disruption alerts, and market volatility. The current GERI reading of <strong>{geri_val}/100 ({geri_band})</strong> and EERI at <strong>{eeri_val}/100 ({eeri_band})</strong> provide the risk backdrop for interpreting today&rsquo;s JKM move.
    </p>
  </div>
  <div class="jkm-risk-grid" style="margin-bottom:40px;">
    <div class="jkm-risk-chip" style="border-color:{gc}33;">
      <div class="jkm-risk-chip-label">GERI</div>
      <div class="jkm-risk-chip-val" style="color:{gc};">{geri_val}</div>
      <div class="jkm-risk-chip-band" style="color:{gc};">{geri_band}</div>
    </div>
    <div class="jkm-risk-chip" style="border-color:{ec}33;">
      <div class="jkm-risk-chip-label">EERI</div>
      <div class="jkm-risk-chip-val" style="color:{ec};">{eeri_val}</div>
      <div class="jkm-risk-chip-band" style="color:{ec};">{eeri_band}</div>
    </div>
    <div class="jkm-risk-chip" style="border-color:{xc}33;">
      <div class="jkm-risk-chip-label">EGSI-M</div>
      <div class="jkm-risk-chip-val" style="color:{xc};">{egsi_val}</div>
      <div class="jkm-risk-chip-band" style="color:{xc};">{egsi_band}</div>
    </div>
  </div>

  <!-- JKM VS BENCHMARKS -->
  <div class="section-label" style="margin-bottom:20px;">&#9878;&#65039; JKM LNG vs TTF, Brent and European Gas Risk</div>
  <div class="jkm-bench-grid">
    <div class="jkm-bench-card">
      <div class="jkm-bench-title">JKM vs TTF Natural Gas</div>
      <div class="jkm-bench-desc">The JKM&ndash;TTF spread signals Asia&ndash;Europe LNG cargo competition. A narrowing spread means Europe and Asia are competing aggressively for the same cargoes.</div>
      {'<div style="font-size:13px;font-weight:700;color:#e2e8f0;">JKM: $' + f'{jkm_price:.2f}/MMBtu &nbsp;&bull;&nbsp; TTF: &euro;{ttf_price:.2f}/MWh</div>' if ttf_price else ''}
      <span class="jkm-coming-soon">Normalised overlay coming soon</span>
    </div>
    <div class="jkm-bench-card">
      <div class="jkm-bench-title">JKM vs Brent Crude Oil</div>
      <div class="jkm-bench-desc">Comparing JKM to Brent provides a broader view of energy cost parity. When LNG spot prices diverge sharply from oil benchmarks, it signals structural supply or demand shifts.</div>
      <span class="jkm-coming-soon">JKM vs Brent chart coming soon</span>
    </div>
    <div class="jkm-bench-card">
      <div class="jkm-bench-title">JKM vs European Gas Storage</div>
      <div class="jkm-bench-desc">Low European gas storage increases demand for LNG imports, which competes with Asian buyers and drives JKM higher. EnergyRiskIQ tracks EU storage daily via AGSI+.</div>
      <a href="/gas-storage-levels-in-europe" style="font-size:12px;color:#d4a017;text-decoration:none;font-weight:600;">View EU Gas Storage Levels &rarr;</a>
    </div>
    <div class="jkm-bench-card">
      <div class="jkm-bench-title">JKM vs EnergyRiskIQ Risk Indices</div>
      <div class="jkm-bench-desc">GERI and EERI track geopolitical and escalation risk in real time. Elevated risk indices often precede JKM volatility — providing a leading signal beyond price charts.</div>
      <a href="/indices" style="font-size:12px;color:#d4a017;text-decoration:none;font-weight:600;">Explore All Risk Indices &rarr;</a>
    </div>
  </div>

  <!-- FAQ -->
  <div class="section-label" style="margin-bottom:20px;">&#10067; Frequently Asked Questions</div>
  <div class="jkm-faq" id="jkm-faq">
    <div class="jkm-faq-item">
      <button class="jkm-faq-q">What is the JKM LNG price today?<span class="jkm-faq-icon">+</span></button>
      <div class="jkm-faq-a">{faq_q1_a}</div>
    </div>
    <div class="jkm-faq-item">
      <button class="jkm-faq-q">What does JKM mean in LNG?<span class="jkm-faq-icon">+</span></button>
      <div class="jkm-faq-a">JKM stands for Japan Korea Marker, a benchmark for spot liquefied natural gas delivered into Northeast Asia. It is published daily by S&amp;P Global Platts and is widely used as a reference price in LNG contracts and derivatives.</div>
    </div>
    <div class="jkm-faq-item">
      <button class="jkm-faq-q">How often is this page updated?<span class="jkm-faq-icon">+</span></button>
      <div class="jkm-faq-a">EnergyRiskIQ updates the JKM LNG spot price daily, typically on business days. The source is OilPrice / Firecrawl daily scrape.</div>
    </div>
    <div class="jkm-faq-item">
      <button class="jkm-faq-q">How much historical data is available?<span class="jkm-faq-icon">+</span></button>
      <div class="jkm-faq-a">EnergyRiskIQ currently tracks {total_rows} daily JKM LNG records from {_fmt_date(earliest)} to {_fmt_date(stat_latest)}. Historical data is continuously extended as new daily snapshots are captured.</div>
    </div>
    <div class="jkm-faq-item">
      <button class="jkm-faq-q">Why does JKM matter?<span class="jkm-faq-icon">+</span></button>
      <div class="jkm-faq-a">JKM is one of the most important LNG price benchmarks because it reflects Asian spot LNG demand and global cargo competition. Traders, utilities, and risk managers use JKM to price contracts, manage exposure, and assess supply security risk across Asia and Europe.</div>
    </div>
    <div class="jkm-faq-item">
      <button class="jkm-faq-q">Can I download JKM LNG price data?<span class="jkm-faq-icon">+</span></button>
      <div class="jkm-faq-a">Yes. Use the Download CSV button in the historical data table above to export all {total_rows} daily JKM LNG records in CSV format. The download endpoint is <a href="/api/jkm-lng-spot-price.csv" style="color:#60a5fa;">/api/jkm-lng-spot-price.csv</a>.</div>
    </div>
  </div>

  <!-- CITATION -->
  <div class="section-label" style="margin-bottom:20px;">&#128196; Citation &amp; Reference</div>
  <div class="snap-cite-card" style="margin-bottom:40px;">
    <h3>How to Cite This Data</h3>
    <p class="snap-cite-desc">
      This page is updated daily with fresh JKM LNG spot price data from the EnergyRiskIQ production pipeline.
      To reference this data in research, journalism, or professional reports, use the citation below.
    </p>
    <div class="snap-cite-code-wrap">
      <pre class="snap-cite-code">EnergyRiskIQ. (2026). <em>JKM LNG Spot Price &mdash; {date_str}</em>.
Retrieved from <a href="{BASE_URL}/data/jkm-lng-spot-price">{BASE_URL}/data/jkm-lng-spot-price</a>
Data source: OilPrice / Firecrawl daily scrape. {total_rows} daily records from {_fmt_date(earliest)}.</pre>
      <button class="snap-cite-copy-btn" onclick="this.textContent='Copied!';setTimeout(()=>this.textContent='Copy',2000);navigator.clipboard&&navigator.clipboard.writeText('{cite_copy}')">Copy</button>
    </div>
    <div class="snap-cite-footer">
      Data sourced from OilPrice / Firecrawl daily scrape. EnergyRiskIQ internal risk pipeline (GERI, EERI, EGSI-M).
      <strong>Not financial advice.</strong>
      See <a href="{BASE_URL}/indices">EnergyRiskIQ Indices</a> for full methodology.
    </div>
  </div>

  <!-- DATA /data/ LINK WHEEL -->
  <div class="section-label" style="margin-bottom:20px;">&#128279; Data &amp; Intelligence Hub</div>
  <div class="jkm-wheel-grid" style="margin-bottom:40px;">
    <a href="/data/energy-risk-snapshot" class="jkm-wheel-link">
      <div class="jkm-wheel-icon">&#128247;</div>
      <div class="jkm-wheel-label">Risk Snapshot</div>
      <div class="jkm-wheel-desc">Daily downloadable global energy risk infographic</div>
    </a>
    <a href="/data/global-energy-risk-forecast" class="jkm-wheel-link">
      <div class="jkm-wheel-icon">&#127919;</div>
      <div class="jkm-wheel-label">Forecast</div>
      <div class="jkm-wheel-desc">24h Brent &amp; TTF price outlook with risk context</div>
    </a>
    <a href="/data/europe-lng-supply-demand" class="jkm-wheel-link">
      <div class="jkm-wheel-icon">&#128168;</div>
      <div class="jkm-wheel-label">LNG Supply</div>
      <div class="jkm-wheel-desc">Europe LNG supply &amp; demand intelligence</div>
    </a>
    <a href="/gas-storage-levels-in-europe" class="jkm-wheel-link">
      <div class="jkm-wheel-icon">&#128200;</div>
      <div class="jkm-wheel-label">Gas Storage</div>
      <div class="jkm-wheel-desc">Live EU gas storage levels &amp; seasonal risk</div>
    </a>
    <a href="/data/ttf-gas-price-today" class="jkm-wheel-link">
      <div class="jkm-wheel-icon">&#127470;&#127489;</div>
      <div class="jkm-wheel-label">TTF Gas Price</div>
      <div class="jkm-wheel-desc">European natural gas benchmark &mdash; daily data</div>
    </a>
  </div>

  <!-- CTA -->
  <div class="cta-section">
    <div class="cta-label">LNG Risk Intelligence</div>
    <h2 class="cta-headline">Track LNG Price Risk,<br>Not Just LNG Prices</h2>
    <p class="cta-sub">
      JKM price tells you where the LNG market is. EnergyRiskIQ explains <em>why</em> it is moving —
      and what risk may come next.
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
    <a href="/data/jkm-lng-spot-price">JKM LNG Price</a>
    <a href="/data/ttf-gas-price-today">TTF Gas Price</a>
    <a href="/data/global-energy-risk-forecast">Forecast</a>
    <a href="/data/energy-risk-snapshot">Risk Snapshot</a>
    <a href="/sitemap-index.xml">Sitemap</a>
    &bull; Not financial advice.
  </div>
</footer>

<!-- ── JavaScript ── -->
<script>
// ── Chart period toggle
function jkmSetPeriod(period, btn) {{
  ['7d','30d','90d','all'].forEach(function(p) {{
    document.getElementById('jkm-chart-' + p).style.display = 'none';
  }});
  document.getElementById('jkm-chart-' + period).style.display = 'block';
  document.querySelectorAll('.jkm-period-btn').forEach(function(b) {{
    b.classList.remove('active');
  }});
  if (btn) btn.classList.add('active');
}}

// ── Table pagination
var _jkmPage = 1;
var _jkmPerPage = 25;
var _jkmRows = [];
var _jkmFiltered = [];
var _jkmSortCol = 'date';
var _jkmSortAsc = false;

function jkmInitTable() {{
  var tbody = document.getElementById('jkm-tbody');
  _jkmRows = Array.from(tbody.querySelectorAll('tr'));
  _jkmFiltered = _jkmRows.slice();
  jkmRenderTable();
}}

function jkmRenderTable() {{
  var tbody = document.getElementById('jkm-tbody');
  tbody.innerHTML = '';
  var start = (_jkmPage - 1) * _jkmPerPage;
  var end   = Math.min(start + _jkmPerPage, _jkmFiltered.length);
  for (var i = start; i < end; i++) {{
    tbody.appendChild(_jkmFiltered[i]);
  }}
  var total = _jkmFiltered.length;
  document.getElementById('jkm-page-info').innerHTML =
    'Showing ' + (start + 1) + '&ndash;' + end + ' of ' + total;
  document.getElementById('jkm-page-num').textContent = 'Page ' + _jkmPage;
  document.getElementById('jkm-prev').disabled = _jkmPage === 1;
  document.getElementById('jkm-next').disabled = end >= total;
}}

function jkmPrevPage() {{
  if (_jkmPage > 1) {{ _jkmPage--; jkmRenderTable(); }}
}}
function jkmNextPage() {{
  var maxPage = Math.ceil(_jkmFiltered.length / _jkmPerPage);
  if (_jkmPage < maxPage) {{ _jkmPage++; jkmRenderTable(); }}
}}

function jkmFilterTable() {{
  var q = document.getElementById('jkm-search').value.toLowerCase();
  _jkmFiltered = _jkmRows.filter(function(r) {{
    return r.getAttribute('data-date').indexOf(q) >= 0 ||
           r.textContent.toLowerCase().indexOf(q) >= 0;
  }});
  _jkmPage = 1;
  jkmRenderTable();
}}

function jkmSort(col) {{
  if (_jkmSortCol === col) {{ _jkmSortAsc = !_jkmSortAsc; }}
  else {{ _jkmSortCol = col; _jkmSortAsc = false; }}
  _jkmFiltered.sort(function(a, b) {{
    var va, vb;
    if (col === 'date') {{
      va = a.getAttribute('data-date');
      vb = b.getAttribute('data-date');
    }} else {{
      var colIdx = {{price:1, chg:2, pct:3}}[col] || 1;
      va = parseFloat(a.cells[colIdx].textContent.replace(/[^0-9\.\-]/g,'')) || 0;
      vb = parseFloat(b.cells[colIdx].textContent.replace(/[^0-9\.\-]/g,'')) || 0;
    }}
    if (va < vb) return _jkmSortAsc ? -1 : 1;
    if (va > vb) return _jkmSortAsc ? 1 : -1;
    return 0;
  }});
  _jkmPage = 1;
  jkmRenderTable();
}}

function jkmCopyData() {{
  var lines = ['Date\\tJKM Price\\t24h Change\\t24h %\\tSource'];
  _jkmRows.forEach(function(r) {{
    var cells = Array.from(r.cells).map(function(c){{ return c.textContent.trim(); }});
    lines.push(cells.join('\\t'));
  }});
  navigator.clipboard && navigator.clipboard.writeText(lines.join('\\n'));
  var btn = event.target;
  btn.textContent = 'Copied!';
  setTimeout(function(){{ btn.innerHTML = '&#128203; Copy data'; }}, 2000);
}}

// ── FAQ accordion
document.querySelectorAll('#jkm-faq .jkm-faq-q').forEach(function(btn) {{
  btn.addEventListener('click', function() {{
    var item = btn.parentElement;
    var isOpen = item.classList.contains('open');
    document.querySelectorAll('#jkm-faq .jkm-faq-item').forEach(function(i){{ i.classList.remove('open'); }});
    if (!isOpen) item.classList.add('open');
  }});
}});

// ── Init
jkmInitTable();
</script>
</body>
</html>"""


# ── Route handlers ────────────────────────────────────────────────────────────

@router.get("/data/jkm-lng-spot-price")
async def jkm_page():
    """JKM LNG Spot Price SEO page — streams loader then data."""
    async def _stream():
        yield _JKM_LOADER
        try:
            data = _fetch_jkm_data()
            yield _build_jkm_html(data)
        except Exception as exc:
            logger.error(f"JKM page error: {exc}", exc_info=True)
            yield "<script>document.getElementById('snap-loader').innerHTML='<p style=\"color:#ef4444;text-align:center;padding:40px;\">Data temporarily unavailable. Please refresh.</p>';</script>"

    return StreamingResponse(_stream(), media_type="text/html")


@router.get("/api/jkm-lng-spot-price.csv")
async def jkm_csv():
    """CSV download of all JKM LNG price data."""
    try:
        rows = execute_production_query(
            "SELECT date, jkm_price, jkm_change_24h, jkm_change_pct, source "
            "FROM lng_price_snapshots WHERE jkm_price IS NOT NULL ORDER BY date DESC"
        ) or []
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["Date", "JKM Price ($/MMBtu)", "24h Change ($)", "24h Change (%)", "Source"])
        for row in rows:
            writer.writerow([
                _fmt_date_iso(row.get("date")),
                row.get("jkm_price", ""),
                row.get("jkm_change_24h", ""),
                row.get("jkm_change_pct", ""),
                row.get("source", ""),
            ])
        content = buf.getvalue()
        return Response(
            content=content,
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="jkm-lng-spot-price.csv"'},
        )
    except Exception as exc:
        logger.error(f"JKM CSV error: {exc}")
        return Response("Error generating CSV", status_code=500)
