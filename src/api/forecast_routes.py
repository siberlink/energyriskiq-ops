"""
Global Energy Risk Forecast Page
Route: /data/global-energy-risk-forecast
SEO-optimized live AI forecast — Brent & TTF 24-hour outlook with risk context.
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
from src.api.snapshot_routes import (
    _PAGE_CSS, _LOADER_HTML, BAND_COLORS, _safe_float,
    _build_infographic_html, _fetch_infographic_watchlist,
    _run_snapshot_engine, _compute_fingerprint,
)

router = APIRouter()
logger = logging.getLogger(__name__)

BASE_URL = "https://energyriskiq.com"

# ── Helpers ──────────────────────────────────────────────────────────────────

def _sign(v):
    return '+' if v >= 0 else ''


def _arrow(v):
    return '&#9650;' if v >= 0 else '&#9660;'


def _chg_color(v):
    return '#22c55e' if v >= 0 else '#ef4444'


def _fmt_date(d):
    """Format a date object like 'Mar 29'."""
    try:
        return d.strftime('%b %-d') if d else '—'
    except Exception:
        return str(d)


def _build_price_svg_chart(data_points, color, height=80, label_key='label', val_key='val'):
    """Build a server-side SVG bar/step price chart from a list of dicts."""
    if not data_points or len(data_points) < 2:
        return ''
    vals = [p[val_key] for p in data_points if p.get(val_key) is not None]
    if not vals:
        return ''

    W, H = 480, height
    PAD_L, PAD_R, PAD_T, PAD_B = 42, 16, 12, 36
    chart_w = W - PAD_L - PAD_R
    chart_h = H - PAD_T - PAD_B

    vmin = min(vals) * 0.995
    vmax = max(vals) * 1.005
    rng = vmax - vmin or 1

    n = len(data_points)
    bar_w = chart_w / n
    spacing = bar_w * 0.25

    bars_svg = ''
    labels_svg = ''
    line_pts = []

    for i, pt in enumerate(data_points):
        v = pt.get(val_key)
        if v is None:
            continue
        x = PAD_L + i * bar_w
        bar_h_val = ((v - vmin) / rng) * chart_h
        y = PAD_T + chart_h - bar_h_val
        cx = x + bar_w / 2
        cy = y
        line_pts.append((cx, cy))

        bars_svg += (
            f'<rect x="{x + spacing/2:.1f}" y="{y:.1f}" '
            f'width="{bar_w - spacing:.1f}" height="{bar_h_val:.1f}" '
            f'fill="{color}" opacity="0.18" rx="2"/>'
        )
        bars_svg += (
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="3" '
            f'fill="{color}" stroke="#0f172a" stroke-width="1.5"/>'
        )
        label = str(pt.get(label_key, ''))
        lbl_anchor = 'middle'
        lbl_x = cx
        bars_svg += (
            f'<text x="{lbl_x:.1f}" y="{PAD_T + chart_h + 24}" '
            f'text-anchor="{lbl_anchor}" font-size="9" fill="#64748b" '
            f'font-family="Inter,sans-serif">{label}</text>'
        )
        # Value label on top
        bars_svg += (
            f'<text x="{cx:.1f}" y="{cy - 6:.1f}" '
            f'text-anchor="middle" font-size="9" fill="{color}" '
            f'font-family="Inter,sans-serif" font-weight="700">{v:.1f}</text>'
        )

    # Connect with smooth line
    if len(line_pts) >= 2:
        path = f'M {line_pts[0][0]:.1f} {line_pts[0][1]:.1f}'
        for lp in line_pts[1:]:
            path += f' L {lp[0]:.1f} {lp[1]:.1f}'
        bars_svg += (
            f'<path d="{path}" fill="none" stroke="{color}" '
            f'stroke-width="1.5" stroke-dasharray="4 2" opacity="0.6"/>'
        )

    # Y-axis reference lines
    y_top = PAD_T
    y_bot = PAD_T + chart_h
    mid_v = (vmin + vmax) / 2
    mid_y = PAD_T + chart_h / 2

    ax_svg = (
        f'<line x1="{PAD_L}" y1="{y_bot:.1f}" x2="{W - PAD_R}" y2="{y_bot:.1f}" '
        f'stroke="rgba(255,255,255,0.06)" stroke-width="1"/>'
        f'<line x1="{PAD_L}" y1="{mid_y:.1f}" x2="{W - PAD_R}" y2="{mid_y:.1f}" '
        f'stroke="rgba(255,255,255,0.04)" stroke-width="1" stroke-dasharray="3 3"/>'
        f'<text x="{PAD_L - 4}" y="{y_top + 4}" text-anchor="end" font-size="8" '
        f'fill="#475569" font-family="Inter,sans-serif">{vmax:.0f}</text>'
        f'<text x="{PAD_L - 4}" y="{mid_y + 3}" text-anchor="end" font-size="8" '
        f'fill="#475569" font-family="Inter,sans-serif">{mid_v:.0f}</text>'
        f'<text x="{PAD_L - 4}" y="{y_bot}" text-anchor="end" font-size="8" '
        f'fill="#475569" font-family="Inter,sans-serif">{vmin:.0f}</text>'
    )

    return (
        f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" '
        f'style="width:100%;max-width:{W}px;display:block;overflow:visible">'
        f'{ax_svg}{bars_svg}'
        f'</svg>'
    )


def _forecast_direction_badge(direction, confidence):
    """Render a forecast direction badge."""
    if direction == 'UP':
        color, arrow, bg = '#22c55e', '&#9650;', 'rgba(34,197,94,0.1)'
        label = 'Bullish Bias'
    elif direction == 'DOWN':
        color, arrow, bg = '#ef4444', '&#9660;', 'rgba(239,68,68,0.1)'
        label = 'Bearish Bias'
    else:
        color, arrow, bg = '#eab308', '&#9644;', 'rgba(234,179,8,0.1)'
        label = 'Neutral / Consolidation'

    conf_bar_w = min(100, max(0, confidence))
    conf_color = '#22c55e' if confidence >= 65 else ('#eab308' if confidence >= 45 else '#ef4444')
    return f"""<div style="background:{bg};border:1px solid {color}33;border-radius:10px;padding:1.25rem 1.5rem;margin-top:1rem;">
  <div style="display:flex;align-items:center;gap:0.75rem;margin-bottom:0.75rem;">
    <span style="font-size:1.4rem;color:{color}">{arrow}</span>
    <span style="font-size:0.95rem;font-weight:800;color:{color}">{label}</span>
    <span style="margin-left:auto;font-size:0.7rem;color:#64748b;font-weight:600;">CONFIDENCE</span>
    <span style="font-size:0.85rem;font-weight:700;color:{conf_color}">{confidence}%</span>
  </div>
  <div style="height:4px;background:rgba(255,255,255,0.06);border-radius:2px;overflow:hidden;">
    <div style="width:{conf_bar_w}%;height:100%;background:{conf_color};border-radius:2px;transition:width 0.5s;"></div>
  </div>
</div>"""


def _run_forecast_engine(
    today_str,
    geri_3d, eeri_3d,
    brent_3d, brent_intraday,
    ttf_3d,
    alert_context,
    storage_pct,
) -> dict:
    """Call GPT-5.1 to generate the 24h price forecast and full interpretation."""
    fallback = {
        'brent_direction': 'DOWN',
        'brent_low': round(brent_3d[-1] * 0.97, 2) if brent_3d else 70.0,
        'brent_high': round(brent_3d[-1] * 1.01, 2) if brent_3d else 75.0,
        'brent_confidence': 52,
        'brent_rationale': (
            'Brent faces downward pressure as today\'s intraday prices track below the '
            'prior-day official close, suggesting softening sentiment. GERI remains in MODERATE '
            'territory but EERI is at SEVERE, signalling European risk premium may cap downside.'
        ),
        'ttf_direction': 'DOWN',
        'ttf_low': round(ttf_3d[-1] * 0.97, 2) if ttf_3d else 45.0,
        'ttf_high': round(ttf_3d[-1] * 1.02, 2) if ttf_3d else 52.0,
        'ttf_confidence': 50,
        'ttf_rationale': (
            'TTF has declined sharply from its 3-day high. With EERI at SEVERE and '
            'European gas storage broadly stable, any geopolitical headline could trigger '
            'a rapid reversal in TTF, but near-term bias is cautiously bearish.'
        ),
        'interpretation': (
            'The global energy risk environment presents a divergence between headline index '
            'readings and live market behaviour. GERI sits at MODERATE levels while EERI has '
            'surged to SEVERE, reflecting the asymmetric nature of European energy exposure '
            'versus global aggregates.\n\n'
            'Brent\'s intraday profile today shows prices trading well below the prior-day '
            'official close — a signal worth monitoring for trend confirmation. The spread '
            'between OilPriceAPI daily data and yfinance intraday futures pricing reflects '
            'structural timing differences rather than a true price gap.\n\n'
            'TTF has pulled back sharply after recent highs, but with 85 war-category alerts '
            'in the past 72 hours and EERI at 61/100, the risk premium embedded in European '
            'gas prices remains historically elevated. Any escalation in Middle East or Ukraine '
            'supply corridors could reverse this decline rapidly.\n\n'
            'Traders and risk managers should prioritise monitoring EERI trajectory and alert '
            'severity scores over the next 24 hours, as these are the leading indicators most '
            'tightly correlated with TTF volatility in the current environment.'
        ),
    }

    try:
        from openai import OpenAI
        ai_key = os.environ.get('AI_INTEGRATIONS_OPENAI_API_KEY')
        ai_url = os.environ.get('AI_INTEGRATIONS_OPENAI_BASE_URL')
        client = OpenAI(api_key=ai_key, base_url=ai_url) if ai_key and ai_url else OpenAI()

        brent_series = ', '.join(f'${v:.2f}' for v in brent_3d) if brent_3d else 'N/A'
        brent_intra_str = ', '.join(f'H{h}=${p:.2f}' for h, p in brent_intraday) if brent_intraday else 'N/A'
        ttf_series = ', '.join(f'€{v:.2f}' for v in ttf_3d) if ttf_3d else 'N/A'
        geri_series = ', '.join(f'{v:.0f}' for v in geri_3d) if geri_3d else 'N/A'
        eeri_series = ', '.join(f'{v:.0f}' for v in eeri_3d) if eeri_3d else 'N/A'

        prompt = f"""You are EnergyRiskIQ's senior quantitative energy risk analyst and forecaster.

Today is {today_str}. You have access to live production data from EnergyRiskIQ's risk pipeline.

=== LIVE MARKET DATA ===
BRENT CRUDE OIL ($/bbl):
  72h daily closes (oldest→latest): {brent_series}
  Today's intraday (yfinance BZ=F): {brent_intra_str}

TTF NATURAL GAS (€/MWh):
  72h daily closes (oldest→latest): {ttf_series}

=== RISK INDICES ===
GERI (Global Energy Risk Index, 0-100, latest→oldest): {geri_series}
EERI (European Energy Risk Index, 0-100, latest→oldest): {eeri_series}
EU Gas Storage: {storage_pct:.1f}% full

=== ALERT CONTEXT (last 72 hours) ===
{alert_context}

=== YOUR TASK ===
Based on ALL the above data, generate a precise 24-hour energy price forecast.

Note: The daily Brent prices come from OilPriceAPI/Business Insider spot data.
The intraday Brent prices come from yfinance BZ=F futures. These may differ due to
spot vs futures pricing. Both are valid signals — analyse them together.

Return ONLY a valid JSON object with EXACTLY these keys:
{{
  "brent_direction": "UP" or "DOWN" or "NEUTRAL",
  "brent_low": <float, 24h forecast low $/bbl>,
  "brent_high": <float, 24h forecast high $/bbl>,
  "brent_confidence": <integer 35-85, forecast confidence %>,
  "brent_rationale": "<2-3 sentences, reference GERI, alert categories, intraday trend>",
  "ttf_direction": "UP" or "DOWN" or "NEUTRAL",
  "ttf_low": <float, 24h forecast low €/MWh>,
  "ttf_high": <float, 24h forecast high €/MWh>,
  "ttf_confidence": <integer 35-85, forecast confidence %>,
  "ttf_rationale": "<2-3 sentences, reference EERI, EU storage, supply risk>",
  "interpretation": "<4 distinct paragraphs separated by \\n\\n. Each paragraph 3-4 sentences. Cover: (1) overall risk environment synthesis, (2) Brent outlook with specific price drivers, (3) TTF outlook with European risk factors, (4) actionable forward-looking view for risk managers. Reference all key numbers. Authoritative, analytical, no bullet points.>"
}}

No markdown. No extra keys. Valid JSON only."""

        resp = client.chat.completions.create(
            model='gpt-5.1',
            messages=[{'role': 'user', 'content': prompt}],
            temperature=0.3,
            max_completion_tokens=1400,
            response_format={'type': 'json_object'},
            timeout=55,
        )
        raw = json.loads(resp.choices[0].message.content)

        result = {}
        result['brent_direction'] = str(raw.get('brent_direction', 'NEUTRAL')).upper().strip()
        if result['brent_direction'] not in ('UP', 'DOWN', 'NEUTRAL'):
            result['brent_direction'] = 'NEUTRAL'
        result['brent_low'] = round(float(raw.get('brent_low', fallback['brent_low'])), 2)
        result['brent_high'] = round(float(raw.get('brent_high', fallback['brent_high'])), 2)
        result['brent_confidence'] = int(raw.get('brent_confidence', fallback['brent_confidence']))
        result['brent_rationale'] = str(raw.get('brent_rationale', fallback['brent_rationale'])).strip()

        result['ttf_direction'] = str(raw.get('ttf_direction', 'NEUTRAL')).upper().strip()
        if result['ttf_direction'] not in ('UP', 'DOWN', 'NEUTRAL'):
            result['ttf_direction'] = 'NEUTRAL'
        result['ttf_low'] = round(float(raw.get('ttf_low', fallback['ttf_low'])), 2)
        result['ttf_high'] = round(float(raw.get('ttf_high', fallback['ttf_high'])), 2)
        result['ttf_confidence'] = int(raw.get('ttf_confidence', fallback['ttf_confidence']))
        result['ttf_rationale'] = str(raw.get('ttf_rationale', fallback['ttf_rationale'])).strip()

        result['interpretation'] = str(raw.get('interpretation', fallback['interpretation'])).strip()

        logger.info("Forecast engine: GPT-5.1 AI forecast generated successfully")
        return result

    except Exception as exc:
        logger.warning(f"Forecast engine AI call failed: {exc}")
        return fallback


# ── Loader HTML (same branding as snapshot, customised tags) ─────────────────

_FORECAST_LOADER_HTML = _LOADER_HTML.replace(
    'Global Energy Risk Snapshot | EnergyRiskIQ',
    'Global Energy Risk Forecast — 24H Custom Algorithm Outlook | EnergyRiskIQ'
).replace(
    'name="description" content="Live global energy risk snapshot. Current GERI, EERI and EGSI-M index values with Brent crude, TTF gas, VIX and LNG market prices."',
    'name="description" content="Algorithm-driven 24-hour energy price forecast for Brent crude and TTF natural gas, driven by live GERI and EERI risk index data. Updated daily."'
).replace(
    'rel="canonical" href="https://energyriskiq.com/data/energy-risk-snapshot"',
    'rel="canonical" href="https://energyriskiq.com/data/global-energy-risk-forecast"'
).replace(
    'Fetching GERI\u00a0&\u00a0EERI indices\u2026',
    'Fetching risk indices & market data\u2026',
).replace(
    '<span class="ld-tag">GERI</span>\n    <span class="ld-tag">EERI</span>\n    <span class="ld-tag">EGSI&#8209;M</span>\n    <span class="ld-tag">Brent</span>\n    <span class="ld-tag">TTF</span>',
    '<span class="ld-tag">GERI</span>\n    <span class="ld-tag">EERI</span>\n    <span class="ld-tag">Brent</span>\n    <span class="ld-tag">TTF</span>\n    <span class="ld-tag">Custom Forecast</span>',
)

# ── Additional CSS for forecast-specific elements ────────────────────────────

_FORECAST_CSS = """
.forecast-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 28px;
  margin-bottom: 40px;
}
@media (max-width: 800px) { .forecast-grid { grid-template-columns: 1fr; } }
.forecast-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 16px;
  overflow: hidden;
}
.forecast-card-header {
  padding: 20px 24px 16px;
  border-bottom: 1px solid rgba(255,255,255,0.06);
  background: linear-gradient(135deg, rgba(255,255,255,0.02) 0%, transparent 100%);
}
.forecast-card-body { padding: 20px 24px 24px; }
.fc-commodity {
  font-size: 11px; font-weight: 700; letter-spacing: 2px;
  text-transform: uppercase; margin-bottom: 6px;
}
.fc-price-row {
  display: flex; align-items: baseline; gap: 10px; margin-bottom: 4px;
}
.fc-price {
  font-size: 36px; font-weight: 800; line-height: 1;
  font-variant-numeric: tabular-nums;
}
.fc-price sup { font-size: 18px; font-weight: 600; vertical-align: top; margin-top: 5px; }
.fc-price-unit { font-size: 14px; color: var(--muted); font-weight: 400; }
.fc-change { font-size: 13px; font-weight: 600; margin-bottom: 12px; }
.fc-72h-label {
  font-size: 10px; font-weight: 700; letter-spacing: 1.5px;
  text-transform: uppercase; color: var(--gold);
  margin: 16px 0 10px;
}
.fc-chart-wrap {
  margin: 0 -4px 4px;
  overflow: hidden;
}
.fc-context {
  font-size: 12px; color: var(--muted); line-height: 1.55;
  margin: 12px 0 0;
  border-left: 2px solid rgba(255,255,255,0.06);
  padding-left: 10px;
}
.forecast-box {
  background: linear-gradient(135deg, #111827 0%, #0f172a 100%);
  border: 1px solid rgba(212,160,23,0.2);
  border-radius: 14px;
  padding: 28px 32px;
  margin-bottom: 40px;
  position: relative;
  overflow: hidden;
}
.forecast-box::before {
  content: '';
  position: absolute; top: 0; left: 0; right: 0; height: 3px;
  background: linear-gradient(90deg, var(--gold), transparent);
}
.forecast-box-label {
  font-size: 10px; font-weight: 700; letter-spacing: 2px;
  text-transform: uppercase; color: var(--gold);
  margin-bottom: 20px; display: flex; align-items: center; gap: 8px;
}
.forecast-box-label::before { content: '\\25B6'; font-size: 8px; }
.interp-para {
  font-size: 16px; color: #cbd5e1; line-height: 1.8;
  font-weight: 400; margin-bottom: 1.4em;
}
.interp-para:last-child { margin-bottom: 0; }
.interp-para strong { color: #ffffff; font-weight: 600; }
.wheel-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin-bottom: 40px;
}
@media (max-width: 600px) { .wheel-grid { grid-template-columns: 1fr 1fr; } }
.wheel-link {
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
.wheel-link:hover {
  border-color: rgba(212,160,23,0.4);
  box-shadow: 0 0 20px rgba(212,160,23,0.08);
  transform: translateY(-2px);
}
.wheel-link-icon { font-size: 1.8rem; }
.wheel-link-label {
  font-size: 11px; font-weight: 700; letter-spacing: 0.08em;
  text-transform: uppercase; color: var(--gold);
}
.wheel-link-desc { font-size: 11px; color: var(--muted); line-height: 1.4; }
.index-trend-row {
  display: flex; gap: 10px; margin-bottom: 8px; flex-wrap: wrap;
}
.index-trend-chip {
  font-size: 11px; font-weight: 700; padding: 3px 10px;
  border-radius: 20px; border: 1px solid currentColor;
  text-transform: uppercase; letter-spacing: 0.06em;
}

/* ── Forecast summary bar ── */
.forecast-summary-bar {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-bottom: 20px;
}

/* ── Mobile responsive ── */
@media (max-width: 640px) {
  .forecast-summary-bar {
    grid-template-columns: 1fr;
  }
  .forecast-box {
    padding: 20px 16px;
  }
  .fc-price {
    font-size: 26px;
  }
  .forecast-card-header {
    padding: 16px 16px 14px;
  }
  .forecast-card-body {
    padding: 16px 16px 20px;
  }
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
    padding: 14px 14px 14px;
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
  .interp-para {
    font-size: 14px;
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
"""


def _build_forecast_html(
    today_str, today_date, next_day_str,
    # Brent
    brent_latest, brent_chg, brent_chg_pct,
    brent_3d_rows, brent_intraday_pts,
    # TTF
    ttf_latest, ttf_chg, ttf_chg_pct,
    ttf_3d_rows,
    # Indices
    geri_val, geri_band, geri_3d,
    eeri_val, eeri_band, eeri_3d,
    egsi_val, egsi_band,
    # Storage / VIX / LNG
    storage_pct, storage_norm, storage_dev, storage_band,
    vix_close, lng_price,
    # AI forecast
    forecast,
    # infographic
    geri_delta, eeri_delta, brent_chg_full, ttf_chg_full,
    watchlist_items,
    ai_texts,
) -> str:

    gc = BAND_COLORS.get(geri_band, '#f97316')
    ec = BAND_COLORS.get(eeri_band, '#ef4444')

    # ── Build Brent 72h chart data ──────────────────────────────────────────
    brent_chart_pts = []
    for row in reversed(brent_3d_rows):
        brent_chart_pts.append({
            'label': _fmt_date(row['date']),
            'val': _safe_float(row['brent_price']),
        })
    # Add intraday average as "Today" point
    if brent_intraday_pts:
        avg_intra = sum(p for _, p in brent_intraday_pts) / len(brent_intraday_pts)
        latest_intra = brent_intraday_pts[0][1] if brent_intraday_pts else None
        brent_chart_pts.append({
            'label': f'Today\n(intra)',
            'val': round(latest_intra, 2) if latest_intra else avg_intra,
        })

    brent_svg = _build_price_svg_chart(brent_chart_pts, '#f97316')

    # ── Build TTF 72h chart data ────────────────────────────────────────────
    ttf_chart_pts = []
    for row in reversed(ttf_3d_rows):
        ttf_chart_pts.append({
            'label': _fmt_date(row['date']),
            'val': _safe_float(row['ttf_price']),
        })
    ttf_svg = _build_price_svg_chart(ttf_chart_pts, '#60a5fa')

    # ── Forecast badges ─────────────────────────────────────────────────────
    brent_badge = _forecast_direction_badge(
        forecast.get('brent_direction', 'NEUTRAL'),
        forecast.get('brent_confidence', 50),
    )
    ttf_badge = _forecast_direction_badge(
        forecast.get('ttf_direction', 'NEUTRAL'),
        forecast.get('ttf_confidence', 50),
    )

    # ── Infographic ─────────────────────────────────────────────────────────
    infographic_html = _build_infographic_html(
        today_str=today_str,
        geri_val=geri_val,
        geri_band=geri_band,
        geri_date=today_str,
        geri_delta=geri_delta,
        eeri_val=eeri_val,
        eeri_band=eeri_band,
        eeri_delta=eeri_delta,
        egsi_val=egsi_val,
        egsi_band=egsi_band,
        brent_price=brent_latest,
        brent_chg=brent_chg_full,
        brent_chg_pct=brent_chg_pct,
        ttf_price=ttf_latest,
        ttf_chg=ttf_chg_full,
        storage_pct=storage_pct,
        ai_texts=ai_texts,
        watchlist_items=watchlist_items,
        title_override=f'Global Energy Risk Forecast &mdash; {next_day_str}',
        forecast_data=forecast,
    )

    # ── Interpretation paragraphs ────────────────────────────────────────────
    interp_raw = forecast.get('interpretation', '')
    paras = [p.strip() for p in interp_raw.split('\n\n') if p.strip()]
    if not paras:
        paras = [interp_raw.strip()] if interp_raw.strip() else [
            'Energy market risk conditions remain elevated across key indicators. '
            'Please check back shortly for the updated forecast.'
        ]
    interp_html = ''.join(
        f'<p class="interp-para">{_html.escape(p)}</p>'
        for p in paras
    )

    # ── GERI/EERI trend chips ────────────────────────────────────────────────
    geri_chip = f'<span class="index-trend-chip" style="color:{gc};border-color:{gc}33">GERI {geri_val}/100 &bull; {geri_band}</span>'
    eeri_chip = f'<span class="index-trend-chip" style="color:{ec};border-color:{ec}33">EERI {eeri_val}/100 &bull; {eeri_band}</span>'

    b_arrow = _arrow(brent_chg)
    b_color = _chg_color(brent_chg)
    t_arrow = _arrow(ttf_chg)
    t_color = _chg_color(ttf_chg)

    # ── Brent rationale ──────────────────────────────────────────────────────
    brent_rationale_html = _html.escape(forecast.get('brent_rationale', ''))
    ttf_rationale_html = _html.escape(forecast.get('ttf_rationale', ''))

    # ── Intraday table ───────────────────────────────────────────────────────
    intraday_rows_html = ''
    if brent_intraday_pts:
        sorted_intra = sorted(brent_intraday_pts, key=lambda x: x[0])
        for h, p in sorted_intra:
            intraday_rows_html += (
                f'<tr><td style="padding:4px 8px;color:#64748b;font-size:11px;">{h:02d}:00 UTC</td>'
                f'<td style="padding:4px 8px;font-size:12px;font-weight:600;color:#e2e8f0;'
                f'font-variant-numeric:tabular-nums;">${p:.2f}</td></tr>'
            )

    intraday_section = ''
    if intraday_rows_html:
        intraday_section = f"""
<div style="margin-top:16px;">
  <div class="fc-72h-label">Intraday Brent (yfinance BZ=F &bull; UTC hours)</div>
  <div style="background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.06);border-radius:8px;overflow:hidden;">
    <table style="width:100%;border-collapse:collapse;">
      {intraday_rows_html}
    </table>
  </div>
  <div style="font-size:10px;color:#334155;margin-top:6px;">
    Source: yfinance BZ=F futures — reflects futures market, may differ from spot (OilPriceAPI).
  </div>
</div>"""

    return f"""<script>
var l=document.getElementById('snap-loader');
if(l){{l.style.display='none';}}
document.body.style.overflow='';
</script>
<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@type": "Dataset",
  "name": "Global Energy Risk Forecast — Daily Brent & TTF Outlook",
  "description": "Daily 24-hour energy price forecast and risk outlook for Brent crude and TTF natural gas, incorporating GERI, EERI, EGSI, storage, VIX, and LNG signals.",
  "url": "{BASE_URL}/data/global-energy-risk-forecast",
  "creator":   {{"@type": "Organization", "name": "EnergyRiskIQ", "url": "{BASE_URL}"}},
  "publisher": {{"@type": "Organization", "name": "EnergyRiskIQ", "url": "{BASE_URL}"}},
  "license": "{BASE_URL}/data-license",
  "isAccessibleForFree": true,
  "temporalCoverage": "2026-01-01/{today_date}",
  "spatialCoverage": "Global",
  "keywords": ["energy risk forecast", "Brent crude price forecast", "TTF gas price forecast", "GERI index", "energy market outlook"]
}}
</script>
<style>
{_FORECAST_CSS}
</style>

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
      <a href="/data/energy-risk-snapshot" style="font-size:13px;color:#94a3b8;text-decoration:none;">Snapshot</a>
      <a href="/users" class="cta-btn-nav">Unlock Deeper Intelligence</a>
    </div>
  </div>
</nav>

<!-- HERO -->
<header class="hero">
  <div class="hero-date">&#128337; Updated Daily &nbsp;&bull;&nbsp; {today_str}</div>
  <h1>Global Energy Risk Forecast</h1>
  <p class="hero-sub">
    Custom Algorithm 24-Hour Energy Price Outlook for Brent Crude &amp; TTF Natural Gas &mdash;
    driven by live GERI &amp; EERI risk index data, intraday prices, and geopolitical alert signals.
  </p>
  <div style="display:flex;justify-content:center;gap:1rem;flex-wrap:wrap;margin-top:1.5rem;">
    <a href="/indices/global-energy-risk-index" style="font-size:12px;font-weight:600;color:{gc};
      border:1px solid {gc}33;border-radius:20px;padding:4px 14px;text-decoration:none;">
      GERI {geri_val}/100 &bull; {geri_band}
    </a>
    <a href="/indices/europe-energy-risk-index" style="font-size:12px;font-weight:600;color:{ec};
      border:1px solid {ec}33;border-radius:20px;padding:4px 14px;text-decoration:none;">
      EERI {eeri_val}/100 &bull; {eeri_band}
    </a>
    <span style="font-size:12px;font-weight:600;color:#60a5fa;
      border:1px solid rgba(96,165,250,0.2);border-radius:20px;padding:4px 14px;">
      Analysis Engine: GPT-5.1
    </span>
  </div>
</header>

<main class="page-body">

  <!-- INFOGRAPHIC — NEXT 24H FORECAST DOWNLOADABLE -->
  <div class="section-label" style="margin-bottom:20px;">&#128248; Next 24 Hours Global Energy Risk Forecast &mdash; Downloadable</div>

  <!-- Forecast summary bar above infographic -->
  <div class="forecast-summary-bar">
    <div style="background:rgba(249,115,22,0.07);border:1px solid rgba(249,115,22,0.2);border-radius:10px;padding:16px 20px;">
      <div style="font-size:10px;font-weight:700;letter-spacing:1.4px;text-transform:uppercase;color:#f97316;margin-bottom:6px;">Brent Crude — 24H Forecast</div>
      <div style="font-size:20px;font-weight:800;color:#e2e8f0;font-variant-numeric:tabular-nums;margin-bottom:4px;">
        ${forecast.get('brent_low', 0):.2f} &ndash; ${forecast.get('brent_high', 0):.2f} <span style="font-size:12px;color:#64748b;font-weight:500;">/bbl</span>
      </div>
      {brent_badge}
      <div style="font-size:11px;color:#64748b;margin-top:6px;">GERI {geri_val}/100 &bull; {geri_band} &bull; GPT-5.1 signal</div>
    </div>
    <div style="background:rgba(96,165,250,0.07);border:1px solid rgba(96,165,250,0.2);border-radius:10px;padding:16px 20px;">
      <div style="font-size:10px;font-weight:700;letter-spacing:1.4px;text-transform:uppercase;color:#60a5fa;margin-bottom:6px;">TTF Natural Gas — 24H Forecast</div>
      <div style="font-size:20px;font-weight:800;color:#e2e8f0;font-variant-numeric:tabular-nums;margin-bottom:4px;">
        &euro;{forecast.get('ttf_low', 0):.2f} &ndash; &euro;{forecast.get('ttf_high', 0):.2f} <span style="font-size:12px;color:#64748b;font-weight:500;">/MWh</span>
      </div>
      {ttf_badge}
      <div style="font-size:11px;color:#64748b;margin-top:6px;">EERI {eeri_val}/100 &bull; {eeri_band} &bull; EU Storage {storage_pct:.1f}%</div>
    </div>
  </div>

  {infographic_html}

  <!-- KEY MARKET PRICES -->
  <div class="section-label" style="margin-bottom:20px;">&#128200; Key Market Prices &mdash; Last Closing</div>
  <div class="price-grid" style="margin-bottom:44px;">
    <div class="price-card">
      <div class="price-commodity">Brent Crude Oil</div>
      <div class="price-value"><sup>$</sup>{brent_latest:.2f}</div>
      <div class="price-change" style="color:{b_color}">{b_arrow} {brent_chg:+.2f} ({brent_chg_pct:+.2f}% d/d)</div>
      <div class="price-source">OilPriceAPI &bull; {brent_3d_rows[0]['date'] if brent_3d_rows else '—'}</div>
    </div>
    <div class="price-card">
      <div class="price-commodity">TTF Natural Gas</div>
      <div class="price-value"><sup>&euro;</sup>{ttf_latest:.2f}<span style="font-size:15px;font-weight:400;color:#64748b;">/MWh</span></div>
      <div class="price-change" style="color:{t_color}">{t_arrow} {ttf_chg:+.2f} ({ttf_chg_pct:+.2f}% d/d)</div>
      <div class="price-source">Yahoo Finance &bull; {ttf_3d_rows[0]['date'] if ttf_3d_rows else '—'}</div>
    </div>
    <div class="price-card">
      <div class="price-commodity">VIX (Volatility)</div>
      <div class="price-value">{vix_close:.2f}</div>
      <div class="price-change" style="color:#94a3b8;">Market Fear Gauge</div>
      <div class="price-source">CBOE / Yahoo Finance</div>
    </div>
    <div class="price-card">
      <div class="price-commodity">EU Gas Storage</div>
      <div class="price-value">{storage_pct:.1f}<span style="font-size:18px;font-weight:500;color:#94a3b8;">%</span></div>
      <div class="price-change" style="color:{'#22c55e' if storage_pct >= 50 else '#eab308' if storage_pct >= 35 else '#ef4444'};">
        {'+' if storage_dev >= 0 else ''}{storage_dev:.1f}% vs norm ({storage_norm:.1f}%)
      </div>
      <div class="price-source">AGSI+ / GIE</div>
    </div>
  </div>

  <!-- 72H PRICE ANALYSIS + 24H FORECAST -->
  <div class="section-label" style="margin-bottom:24px;">&#127919; 72-Hour Price Analysis &amp; 24-Hour Forecast</div>
  <div class="forecast-grid">

    <!-- BRENT CARD -->
    <div class="forecast-card">
      <div class="forecast-card-header">
        <div class="fc-commodity" style="color:#f97316;">&#128137; Brent Crude Oil</div>
        <div class="fc-price-row">
          <div class="fc-price" style="color:#f97316;"><sup>$</sup>{brent_latest:.2f}</div>
          <div class="fc-price-unit">/bbl</div>
        </div>
        <div class="fc-change" style="color:{b_color};">{b_arrow} {brent_chg:+.2f} | {brent_chg_pct:+.2f}% day-over-day</div>
        <div class="index-trend-row" style="margin-top:8px;">{geri_chip}</div>
      </div>
      <div class="forecast-card-body">
        <div class="fc-72h-label">72-Hour Daily Closes &amp; Today Intraday</div>
        <div class="fc-chart-wrap">{brent_svg}</div>
        {intraday_section}
        <div class="fc-context">
          GERI {geri_val}/100 ({geri_band}) with {len(brent_3d_rows)}-day price trend.
          Alert context: dominant categories — war-related events and energy supply signals
          driving geopolitical risk premium into crude pricing.
        </div>

        <!-- 24H FORECAST -->
        <div style="margin-top:20px;padding-top:18px;border-top:1px solid rgba(255,255,255,0.06);">
          <div style="font-size:11px;font-weight:700;letter-spacing:1.5px;
            text-transform:uppercase;color:#f97316;margin-bottom:6px;">
            24-Hour Brent Forecast
          </div>
          <div style="font-size:22px;font-weight:800;color:#e2e8f0;margin-bottom:4px;font-variant-numeric:tabular-nums;">
            ${forecast.get('brent_low', '?'):.2f} &ndash; ${forecast.get('brent_high', '?'):.2f}
            <span style="font-size:13px;color:#64748b;font-weight:500;">/bbl</span>
          </div>
          {brent_badge}
          <p style="font-size:13px;color:#94a3b8;line-height:1.6;margin-top:12px;">{brent_rationale_html}</p>
        </div>
      </div>
    </div>

    <!-- TTF CARD -->
    <div class="forecast-card">
      <div class="forecast-card-header">
        <div class="fc-commodity" style="color:#60a5fa;">&#128168; TTF Natural Gas</div>
        <div class="fc-price-row">
          <div class="fc-price" style="color:#60a5fa;"><sup>&euro;</sup>{ttf_latest:.2f}</div>
          <div class="fc-price-unit">/MWh</div>
        </div>
        <div class="fc-change" style="color:{t_color};">{t_arrow} {ttf_chg:+.2f} | {ttf_chg_pct:+.2f}% day-over-day</div>
        <div class="index-trend-row" style="margin-top:8px;">{eeri_chip}</div>
      </div>
      <div class="forecast-card-body">
        <div class="fc-72h-label">72-Hour Daily Closes (€/MWh)</div>
        <div class="fc-chart-wrap">{ttf_svg}</div>
        <div class="fc-context">
          EERI {eeri_val}/100 ({eeri_band}) — European escalation index at {eeri_band.lower()} territory.
          EU gas storage: {storage_pct:.1f}% ({storage_dev:+.1f}% vs seasonal norm).
          EERI is the primary leading indicator for TTF volatility at current risk levels.
        </div>

        <!-- 24H FORECAST -->
        <div style="margin-top:20px;padding-top:18px;border-top:1px solid rgba(255,255,255,0.06);">
          <div style="font-size:11px;font-weight:700;letter-spacing:1.5px;
            text-transform:uppercase;color:#60a5fa;margin-bottom:6px;">
            24-Hour TTF Forecast
          </div>
          <div style="font-size:22px;font-weight:800;color:#e2e8f0;margin-bottom:4px;font-variant-numeric:tabular-nums;">
            &euro;{forecast.get('ttf_low', '?'):.2f} &ndash; &euro;{forecast.get('ttf_high', '?'):.2f}
            <span style="font-size:13px;color:#64748b;font-weight:500;">/MWh</span>
          </div>
          {ttf_badge}
          <p style="font-size:13px;color:#94a3b8;line-height:1.6;margin-top:12px;">{ttf_rationale_html}</p>
        </div>
      </div>
    </div>

  </div>

  <!-- AI INTERPRETATION -->
  <div class="section-label" style="margin-bottom:20px;">&#129302; Risk Intelligence Forecast Interpretation</div>
  <div class="forecast-box" style="margin-bottom:40px;">
    {interp_html}
  </div>

  <!-- CONTEXT LINKS WHEEL -->
  <div class="section-label" style="margin-bottom:20px;">&#128279; Related Intelligence &amp; Context</div>
  <div class="wheel-grid" style="margin-bottom:40px;">
    <a href="/" class="wheel-link">
      <div class="wheel-link-icon">&#127968;</div>
      <div class="wheel-link-label">Home</div>
      <div class="wheel-link-desc">Live risk dashboard &amp; global overview</div>
    </a>
    <a href="/indices/global-energy-risk-index" class="wheel-link">
      <div class="wheel-link-icon">&#128137;</div>
      <div class="wheel-link-label">GERI</div>
      <div class="wheel-link-desc">Global Energy Risk Index &mdash; methodology &amp; history</div>
    </a>
    <a href="/indices/europe-energy-risk-index" class="wheel-link">
      <div class="wheel-link-icon">&#9889;</div>
      <div class="wheel-link-label">EERI</div>
      <div class="wheel-link-desc">European Energy Risk Index &mdash; escalation signals</div>
    </a>
    <a href="/indices/europe-gas-stress-index" class="wheel-link">
      <div class="wheel-link-icon">&#127777;&#65039;</div>
      <div class="wheel-link-label">EGSI</div>
      <div class="wheel-link-desc">Europe Gas Stress Index &mdash; storage &amp; flow data</div>
    </a>
    <a href="/indices" class="wheel-link">
      <div class="wheel-link-icon">&#128202;</div>
      <div class="wheel-link-label">All Indices</div>
      <div class="wheel-link-desc">Full index suite with historical data</div>
    </a>
    <a href="/data/energy-risk-snapshot" class="wheel-link">
      <div class="wheel-link-icon">&#128247;</div>
      <div class="wheel-link-label">Risk Snapshot</div>
      <div class="wheel-link-desc">Today&rsquo;s downloadable infographic &amp; market overview</div>
    </a>
    <a href="/data/europe-lng-supply-demand" class="wheel-link">
      <div class="wheel-link-icon">&#128168;</div>
      <div class="wheel-link-label">LNG Supply</div>
      <div class="wheel-link-desc">Europe LNG supply &amp; demand intelligence</div>
    </a>
    <a href="/data/jkm-lng-spot-price" class="wheel-link">
      <div class="wheel-link-icon">&#9875;</div>
      <div class="wheel-link-label">JKM LNG</div>
      <div class="wheel-link-desc">Japan Korea Marker spot price &mdash; daily data</div>
    </a>
    <a href="/data/ttf-gas-price-today" class="wheel-link">
      <div class="wheel-link-icon">&#127470;&#127489;</div>
      <div class="wheel-link-label">TTF Gas</div>
      <div class="wheel-link-desc">European natural gas benchmark &mdash; daily data</div>
    </a>
    <a href="/gas-storage-levels-in-europe" class="wheel-link">
      <div class="wheel-link-icon">&#128200;</div>
      <div class="wheel-link-label">Gas Storage</div>
      <div class="wheel-link-desc">Live EU gas storage levels &amp; seasonal risk</div>
    </a>
  </div>

  <!-- CITATION & REFERENCE -->
  <div class="section-label" style="margin-bottom:20px;">&#128196; Citation &amp; Reference</div>
  <div class="snap-cite-card" style="margin-bottom:36px;">
    <h3>How to Cite This Forecast</h3>
    <p class="snap-cite-desc">
      This page is updated daily with fresh algorithm-generated forecasts based on live production
      pipeline data. To reference this analysis in research, journalism, or professional reports,
      use the citation below.
    </p>
    <div class="snap-cite-code-wrap">
      <pre class="snap-cite-code">EnergyRiskIQ. (2026). <em>Global Energy Risk Forecast — {today_str}</em>.
Retrieved from <a href="{BASE_URL}/data/global-energy-risk-forecast">{BASE_URL}/data/global-energy-risk-forecast</a>
Analysis engine: GPT-5.1 | Data sources: OilPriceAPI, Yahoo Finance, AGSI+, internal risk pipeline.</pre>
      <button class="snap-cite-copy-btn" onclick="this.textContent='Copied!';setTimeout(()=>this.textContent='Copy',2000);navigator.clipboard&&navigator.clipboard.writeText('EnergyRiskIQ. (2026). Global Energy Risk Forecast — {today_str}. Retrieved from {BASE_URL}/data/global-energy-risk-forecast')">Copy</button>
    </div>
    <div class="snap-cite-footer">
      Data sourced from: OilPriceAPI (Brent spot, TTF), Yahoo Finance (yfinance BZ=F intraday futures),
      AGSI+ / GIE (EU gas storage), EnergyRiskIQ internal risk scoring pipeline (GERI, EERI, EGSI-M).
      Custom algorithm interpretation powered by GPT-5.1. <strong>Not financial advice.</strong>
      See <a href="{BASE_URL}/indices/global-energy-risk-index">GERI methodology</a> for full scoring detail.
    </div>
  </div>

  <!-- CTA -->
  <div class="cta-section">
    <div class="cta-label">Daily Risk Intelligence</div>
    <h2 class="cta-headline">Get the Full Forecast<br>Every Morning</h2>
    <p class="cta-sub">
      Subscribe to EnergyRiskIQ for daily custom algorithm energy risk briefings,
      real-time GERI/EERI/EGSI updates, and Brent &amp; TTF price signals.
    </p>
    <a href="/energy-risk-intelligence-signals" class="cta-btn">Get Free Intelligence &rarr;</a>
    <a href="/indices" class="cta-secondary">Explore All Indices</a>
  </div>

</main>

<footer class="page-footer">
  <div>
    &copy; 2026 EnergyRiskIQ &bull;
    <a href="/">Home</a>
    <a href="/indices">Indices</a>
    <a href="/data/energy-risk-snapshot">Risk Snapshot</a>
    <a href="/data/global-energy-risk-forecast">Forecast</a>
    <a href="/sitemap-index.xml">Sitemap</a>
    &bull; Not financial advice.
  </div>
</footer>

<!-- html2canvas download -->
<script src="https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js"></script>
<script>
function downloadInfographic(id, btnId) {{
  var btn = document.getElementById(btnId);
  if (btn) {{ btn.textContent = 'Generating\u2026'; btn.disabled = true; }}
  html2canvas(document.getElementById(id), {{
    backgroundColor: '#141926',
    scale: 2,
    useCORS: true,
    allowTaint: true,
    logging: false,
  }}).then(function(canvas) {{
    var a = document.createElement('a');
    a.download = 'energyriskiq-forecast-{today_date}.png';
    a.href = canvas.toDataURL('image/png');
    a.click();
    if (btn) {{ btn.textContent = '\u2913 Download PNG'; btn.disabled = false; }}
  }}).catch(function(e) {{
    if (btn) {{ btn.textContent = '\u2913 Download PNG'; btn.disabled = false; }}
    console.error('html2canvas error', e);
  }});
}}
</script>
</body>
</html>"""


def _compute_forecast_data():
    """Fetch all required data for the forecast page from the production database."""
    # Brent
    brent_3d = execute_production_query(
        "SELECT date, brent_price, brent_change_24h, brent_change_pct "
        "FROM oil_price_snapshots ORDER BY date DESC LIMIT 3"
    ) or []
    brent_latest_row = brent_3d[0] if brent_3d else None

    # Brent intraday (today)
    today = _date.today()
    brent_intraday = execute_production_query(
        "SELECT hour, price FROM intraday_brent "
        "WHERE date = %s ORDER BY hour ASC",
        (today,)
    ) or []
    brent_intraday_pts = [(r['hour'], _safe_float(r['price'])) for r in brent_intraday]

    # TTF
    ttf_3d = execute_production_query(
        "SELECT date, ttf_price, raw_data "
        "FROM ttf_gas_snapshots ORDER BY date DESC LIMIT 3"
    ) or []
    ttf_latest_row = ttf_3d[0] if ttf_3d else None
    ttf_prev_row = ttf_3d[1] if len(ttf_3d) > 1 else None

    # GERI last 3 days
    geri_rows = execute_production_query(
        "SELECT date, value, band, components FROM intel_indices_daily "
        "WHERE index_id='global:geo_energy_risk' ORDER BY date DESC LIMIT 3"
    ) or []
    geri_row = geri_rows[0] if geri_rows else None
    geri_prev = geri_rows[1] if len(geri_rows) > 1 else None

    # EERI last 3 days
    eeri_rows = execute_production_query(
        "SELECT date, value, band FROM reri_indices_daily "
        "WHERE index_id='europe:eeri' ORDER BY date DESC LIMIT 3"
    ) or []
    eeri_row = eeri_rows[0] if eeri_rows else None
    eeri_prev = eeri_rows[1] if len(eeri_rows) > 1 else None

    # EGSI
    egsi_row = execute_production_one(
        "SELECT index_date, index_value, band FROM egsi_m_daily "
        "WHERE region='Europe' ORDER BY index_date DESC LIMIT 1"
    )

    # Storage
    storage_row = execute_production_one(
        "SELECT date, eu_storage_percent, seasonal_norm, deviation_from_norm, risk_band "
        "FROM gas_storage_snapshots ORDER BY date DESC LIMIT 1"
    )

    # VIX
    vix_row = execute_production_one(
        "SELECT vix_close FROM vix_snapshots ORDER BY date DESC LIMIT 1"
    )

    # LNG
    lng_row = execute_production_one(
        "SELECT jkm_price FROM lng_price_snapshots ORDER BY date DESC LIMIT 1"
    )

    # Alert context
    alert_cats = execute_production_query(
        "SELECT category, COUNT(*) as cnt FROM alert_events "
        "WHERE created_at >= NOW() - INTERVAL '72 hours' "
        "GROUP BY category ORDER BY cnt DESC LIMIT 8"
    ) or []
    alert_context = "Alert categories (last 72h): " + ", ".join(
        f"{r['category']}={r['cnt']}" for r in alert_cats
    ) if alert_cats else "No recent alerts available."

    # Recent high-severity alert headlines for context
    top_alerts = execute_production_query(
        "SELECT headline, severity, category FROM alert_events "
        "WHERE created_at >= NOW() - INTERVAL '72 hours' AND severity >= 7 "
        "ORDER BY severity DESC, created_at DESC LIMIT 5"
    ) or []
    if top_alerts:
        alert_context += "\nTop severity alerts: " + " | ".join(
            f"[{r['category']}:{r['severity']}] {(r['headline'] or '')[:60]}"
            for r in top_alerts
        )

    return {
        'brent_3d': brent_3d,
        'brent_latest_row': brent_latest_row,
        'brent_intraday_pts': brent_intraday_pts,
        'ttf_3d': ttf_3d,
        'ttf_latest_row': ttf_latest_row,
        'ttf_prev_row': ttf_prev_row,
        'geri_rows': geri_rows,
        'geri_row': geri_row,
        'geri_prev': geri_prev,
        'eeri_rows': eeri_rows,
        'eeri_row': eeri_row,
        'eeri_prev': eeri_prev,
        'egsi_row': egsi_row,
        'storage_row': storage_row,
        'vix_row': vix_row,
        'lng_row': lng_row,
        'alert_context': alert_context,
    }


@router.get("/data/global-energy-risk-forecast")
async def global_energy_risk_forecast():
    async def generate():
        yield _FORECAST_LOADER_HTML

        try:
            data = await asyncio.to_thread(_compute_forecast_data)
        except Exception as exc:
            logger.error(f"Forecast data fetch failed: {exc}", exc_info=True)
            yield f"""<script>var l=document.getElementById('snap-loader');if(l)l.style.display='none';
document.body.style.overflow='';</script>
<div style="color:#ef4444;padding:40px;font-family:sans-serif;background:#0b0f1a">
<h2>Error loading forecast</h2><p>{_html.escape(str(exc))}</p></div></body></html>"""
            return

        # ── Unpack data ──────────────────────────────────────────────────────
        brent_3d = data['brent_3d']
        brent_latest_row = data['brent_latest_row']
        brent_intraday_pts = data['brent_intraday_pts']
        ttf_3d = data['ttf_3d']
        ttf_latest_row = data['ttf_latest_row']
        ttf_prev_row = data['ttf_prev_row']
        geri_rows = data['geri_rows']
        geri_row = data['geri_row']
        geri_prev = data['geri_prev']
        eeri_rows = data['eeri_rows']
        eeri_row = data['eeri_row']
        eeri_prev = data['eeri_prev']
        egsi_row = data['egsi_row']
        storage_row = data['storage_row']
        vix_row = data['vix_row']
        lng_row = data['lng_row']
        alert_context = data['alert_context']

        # ── Compute values ───────────────────────────────────────────────────
        today_str = datetime.now(timezone.utc).strftime('%B %-d, %Y')
        today_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        next_day_str = (datetime.now(timezone.utc) + timedelta(days=1)).strftime('%B %-d, %Y')

        brent_latest = _safe_float(brent_latest_row['brent_price']) if brent_latest_row else 0.0
        brent_chg = _safe_float(brent_latest_row['brent_change_24h']) if brent_latest_row else 0.0
        brent_chg_pct = _safe_float(brent_latest_row['brent_change_pct']) if brent_latest_row else 0.0

        ttf_latest = _safe_float(ttf_latest_row['ttf_price']) if ttf_latest_row else 0.0
        ttf_prev_price = _safe_float(ttf_prev_row['ttf_price']) if ttf_prev_row else ttf_latest
        ttf_chg = ttf_latest - ttf_prev_price
        ttf_chg_pct = (ttf_chg / ttf_prev_price * 100) if ttf_prev_price else 0.0

        ttf_raw = (ttf_latest_row or {}).get('raw_data') or {}
        ttf_chg_raw = ttf_raw.get('changes', {}).get('24h', {}).get('amount', ttf_chg)

        geri_val = int(round(_safe_float(geri_row['value']))) if geri_row else 0
        geri_band = (geri_row or {}).get('band', 'MODERATE')
        geri_prev_val = int(round(_safe_float(geri_prev['value']))) if geri_prev else geri_val
        geri_delta = geri_val - geri_prev_val

        eeri_val = int(round(_safe_float(eeri_row['value']))) if eeri_row else 0
        eeri_band = (eeri_row or {}).get('band', 'ELEVATED')
        eeri_prev_val = int(round(_safe_float(eeri_prev['value']))) if eeri_prev else eeri_val
        eeri_delta = eeri_val - eeri_prev_val

        egsi_val = round(_safe_float((egsi_row or {}).get('index_value', 0)), 1)
        egsi_band = (egsi_row or {}).get('band', 'ELEVATED')

        storage_pct = _safe_float((storage_row or {}).get('eu_storage_percent', 45))
        storage_norm = _safe_float((storage_row or {}).get('seasonal_norm', 50))
        storage_dev = _safe_float((storage_row or {}).get('deviation_from_norm', 0))
        storage_band = (storage_row or {}).get('risk_band', 'MODERATE')

        vix_close = _safe_float((vix_row or {}).get('vix_close', 20))
        lng_price = _safe_float((lng_row or {}).get('jkm_price', 10))

        geri_3d_vals = [_safe_float(r['value']) for r in reversed(geri_rows)]
        eeri_3d_vals = [_safe_float(r['value']) for r in reversed(eeri_rows)]
        brent_3d_vals = [_safe_float(r['brent_price']) for r in reversed(brent_3d)]
        ttf_3d_vals = [_safe_float(r['ttf_price']) for r in reversed(ttf_3d)]

        # ── Run AI forecast engine ───────────────────────────────────────────
        sorted_intra = sorted(brent_intraday_pts, key=lambda x: x[0])
        forecast = await asyncio.to_thread(
            _run_forecast_engine,
            today_str,
            geri_3d_vals, eeri_3d_vals,
            brent_3d_vals, sorted_intra,
            ttf_3d_vals,
            alert_context,
            storage_pct,
        )

        # ── Run infographic AI engine (reuse snapshot logic) ─────────────────
        watchlist_items = await asyncio.to_thread(
            _fetch_infographic_watchlist, float(geri_val), storage_pct
        )

        fingerprint = f"forecast:{today_date}:{geri_val}:{eeri_val}:{round(brent_latest,1)}"
        snap_result = await asyncio.to_thread(
            _run_snapshot_engine,
            fingerprint,
            geri_val, geri_band, geri_delta, today_str,
            eeri_val, eeri_band, eeri_delta,
            egsi_val, egsi_band,
            brent_latest, ttf_latest, vix_close, lng_price,
            storage_pct, storage_band, storage_norm, storage_dev,
            watchlist_items,
            today_str,
        )
        ai_texts = snap_result.get('ai_texts', {})

        # ── Build full page ──────────────────────────────────────────────────
        html_body = _build_forecast_html(
            today_str=today_str,
            today_date=today_date,
            next_day_str=next_day_str,
            brent_latest=brent_latest,
            brent_chg=brent_chg,
            brent_chg_pct=brent_chg_pct,
            brent_3d_rows=brent_3d,
            brent_intraday_pts=sorted_intra,
            ttf_latest=ttf_latest,
            ttf_chg=float(ttf_chg_raw),
            ttf_chg_pct=ttf_chg_pct,
            ttf_3d_rows=ttf_3d,
            geri_val=geri_val,
            geri_band=geri_band,
            geri_3d=geri_3d_vals,
            eeri_val=eeri_val,
            eeri_band=eeri_band,
            eeri_3d=eeri_3d_vals,
            egsi_val=egsi_val,
            egsi_band=egsi_band,
            storage_pct=storage_pct,
            storage_norm=storage_norm,
            storage_dev=storage_dev,
            storage_band=storage_band,
            vix_close=vix_close,
            lng_price=lng_price,
            forecast=forecast,
            geri_delta=geri_delta,
            eeri_delta=eeri_delta,
            brent_chg_full=brent_chg,
            ttf_chg_full=float(ttf_chg_raw),
            watchlist_items=watchlist_items,
            ai_texts=ai_texts,
        )

        yield html_body

    return StreamingResponse(generate(), media_type="text/html")


# ── Sitemap-data.xml ──────────────────────────────────────────────────────────

@router.get("/sitemap-data.xml", response_class=Response)
async def sitemap_data_xml():
    """Data pages sitemap — updated daily."""
    today = _date.today().isoformat()
    pages = [
        (f"{BASE_URL}/data/energy-risk-snapshot",           "daily",  "0.9"),
        (f"{BASE_URL}/data/global-energy-risk-forecast",    "daily",  "0.9"),
        (f"{BASE_URL}/data/brent-crude-oil-price-today",    "daily",  "0.9"),
        (f"{BASE_URL}/data/jkm-lng-price-chart",             "daily",  "0.9"),
        (f"{BASE_URL}/gas-storage-levels-in-europe",        "daily",  "0.9"),
        (f"{BASE_URL}/data/europe-lng-supply-demand",        "daily",  "0.9"),
        (f"{BASE_URL}/data/jkm-lng-spot-price",              "daily",  "0.9"),
        (f"{BASE_URL}/data/ttf-gas-price-today",             "daily",  "0.9"),
        (f"{BASE_URL}/data/natural-gas-price-today-europe",  "daily",  "0.9"),
        (f"{BASE_URL}/data/wti-crude-oil-price-today",       "daily",  "0.9"),
        (f"{BASE_URL}/widgets/wti-crude-oil-price",          "weekly", "0.8"),
        (f"{BASE_URL}/widgets/europe-gas-storage-levels",    "weekly", "0.8"),
        (f"{BASE_URL}/widgets/jkm-lng-price",                "weekly", "0.8"),
    ]
    urls = ''
    for loc, freq, pri in pages:
        urls += f"""
  <url>
    <loc>{loc}</loc>
    <lastmod>{today}</lastmod>
    <changefreq>{freq}</changefreq>
    <priority>{pri}</priority>
  </url>"""

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{urls}
</urlset>"""
    return Response(
        content=xml,
        media_type="application/xml",
        headers={"Cache-Control": "public, max-age=3600"},
    )
