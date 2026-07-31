"""
Weekly Energy Outlook — Friday Newsletter

Admin endpoints for generating, previewing, and dispatching the weekly
email that goes to all EnergyRiskIQ users every Friday.

Endpoints (all require X-Admin-Token):
  POST /admin/weekly-outlook/generate   → collect data + GPT-5.1 → return rendered HTML
  POST /admin/weekly-outlook/send-test  → send rendered HTML to test address
  POST /admin/weekly-outlook/send-all   → send rendered HTML to all platform users
"""
from __future__ import annotations

import os
import json
import logging
import math
import html as _html
import requests
import time
import urllib.parse
from datetime import date, timedelta
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Header, BackgroundTasks
from pydantic import BaseModel

from src.db.db import get_cursor
from src.api.admin_routes import verify_admin_token, _get_all_user_emails, _email_sender, _update_campaign

APP_URL = os.environ.get("APP_URL", "https://energyriskiq.com")
TEST_EMAIL = "emilconstantin22@gmail.com"

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin-weekly"])


# ─────────────────────────────────────────────────────────────
#  Data collection
# ─────────────────────────────────────────────────────────────

def _week_range():
    """Return (start_date, end_date) for the reporting window.
    From 6 days ago through yesterday (inclusive), giving Sat–Thu when
    called on a Friday.
    """
    today = date.today()
    end = today - timedelta(days=1)          # yesterday (Thursday)
    start = end - timedelta(days=5)           # 6 days total
    return start, end


def _fmt_date(d: date) -> str:
    return d.strftime("%-d %b %Y")


def _fmt_range(start: date, end: date) -> str:
    if start.month == end.month:
        return f"{start.strftime('%-d')}–{end.strftime('%-d %B %Y')}"
    return f"{start.strftime('%-d %b')} – {end.strftime('%-d %b %Y')}"


def _collect_week_data() -> dict:
    start, end = _week_range()
    data: dict = {
        "week_label": _fmt_range(start, end),
        "week_start": start.isoformat(),
        "week_end": end.isoformat(),
    }

    with get_cursor(commit=False) as cur:
        # ── GERI daily ───────────────────────────────────────────────
        cur.execute("""
            SELECT date, value, band, trend_1d
            FROM intel_indices_daily
            WHERE index_id = 'global:geo_energy_risk'
              AND date BETWEEN %s AND %s
            ORDER BY date
        """, (start, end))
        geri_rows = cur.fetchall()
        data["geri_rows"] = [dict(r) for r in geri_rows]

        # Latest & prev-week start for change
        cur.execute("""
            SELECT value, band FROM intel_indices_daily
            WHERE index_id = 'global:geo_energy_risk'
            ORDER BY date DESC LIMIT 1
        """)
        r = cur.fetchone()
        data["geri_latest"] = float(r["value"]) if r else None
        data["geri_band"]   = r["band"] if r else "—"

        cur.execute("""
            SELECT value FROM intel_indices_daily
            WHERE index_id = 'global:geo_energy_risk'
              AND date < %s
            ORDER BY date DESC LIMIT 1
        """, (start,))
        r = cur.fetchone()
        data["geri_week_ago"] = float(r["value"]) if r else None

        # ── EERI daily ───────────────────────────────────────────────
        cur.execute("""
            SELECT date, value, band, trend_1d
            FROM reri_indices_daily
            ORDER BY date DESC LIMIT 1
        """)
        r = cur.fetchone()
        data["eeri_latest"] = float(r["value"]) if r else None
        data["eeri_band"]   = r["band"] if r else "—"

        cur.execute("""
            SELECT value FROM reri_indices_daily
            WHERE date < %s ORDER BY date DESC LIMIT 1
        """, (start,))
        r = cur.fetchone()
        data["eeri_week_ago"] = float(r["value"]) if r else None

        cur.execute("""
            SELECT date, value, band
            FROM reri_indices_daily
            WHERE date BETWEEN %s AND %s
            ORDER BY date
        """, (start, end))
        data["eeri_rows"] = [dict(r) for r in cur.fetchall()]

        # ── EGSI-M ───────────────────────────────────────────────────
        cur.execute("""
            SELECT index_value, band FROM egsi_m_daily
            ORDER BY index_date DESC LIMIT 1
        """)
        r = cur.fetchone()
        data["egsi_m_latest"] = float(r["index_value"]) if r else None
        data["egsi_m_band"]   = r["band"] if r else "—"

        cur.execute("""
            SELECT index_value FROM egsi_m_daily
            WHERE index_date < %s ORDER BY index_date DESC LIMIT 1
        """, (start,))
        r = cur.fetchone()
        data["egsi_m_week_ago"] = float(r["index_value"]) if r else None

        # ── EGSI-S ───────────────────────────────────────────────────
        cur.execute("""
            SELECT index_value, band FROM egsi_s_daily
            ORDER BY index_date DESC LIMIT 1
        """)
        r = cur.fetchone()
        data["egsi_s_latest"] = float(r["index_value"]) if r else None
        data["egsi_s_band"]   = r["band"] if r else "—"

        # ── Brent ────────────────────────────────────────────────────
        cur.execute("""
            SELECT date, brent_price, brent_change_pct
            FROM oil_price_snapshots
            WHERE date BETWEEN %s AND %s AND brent_price IS NOT NULL
            ORDER BY date
        """, (start, end))
        brent_rows = cur.fetchall()
        data["brent_rows"] = [dict(r) for r in brent_rows]

        cur.execute("""
            SELECT brent_price, brent_change_pct
            FROM oil_price_snapshots
            WHERE brent_price IS NOT NULL
            ORDER BY date DESC LIMIT 1
        """)
        r = cur.fetchone()
        data["brent_latest"] = float(r["brent_price"]) if r else None
        data["brent_chg_pct"] = float(r["brent_change_pct"] or 0) if r else None

        cur.execute("""
            SELECT brent_price FROM oil_price_snapshots
            WHERE date < %s AND brent_price IS NOT NULL
            ORDER BY date DESC LIMIT 1
        """, (start,))
        r = cur.fetchone()
        data["brent_week_ago"] = float(r["brent_price"]) if r else None

        # Brent weekly % change
        if data["brent_latest"] and data["brent_week_ago"]:
            data["brent_weekly_pct"] = round(
                (data["brent_latest"] - data["brent_week_ago"]) / data["brent_week_ago"] * 100, 1
            )
        else:
            data["brent_weekly_pct"] = None

        # ── WTI ──────────────────────────────────────────────────────
        cur.execute("""
            SELECT date, wti_price, wti_change_pct
            FROM oil_price_snapshots
            WHERE date BETWEEN %s AND %s AND wti_price IS NOT NULL
            ORDER BY date
        """, (start, end))
        data["wti_rows"] = [dict(r) for r in cur.fetchall()]

        cur.execute("""
            SELECT wti_price FROM oil_price_snapshots
            WHERE wti_price IS NOT NULL ORDER BY date DESC LIMIT 1
        """)
        r = cur.fetchone()
        data["wti_latest"] = float(r["wti_price"]) if r else None

        # ── TTF ───────────────────────────────────────────────────────
        cur.execute("""
            SELECT date, ttf_price FROM ttf_gas_snapshots
            WHERE date BETWEEN %s AND %s AND ttf_price IS NOT NULL
            ORDER BY date
        """, (start, end))
        data["ttf_rows"] = [dict(r) for r in cur.fetchall()]

        cur.execute("""
            SELECT ttf_price FROM ttf_gas_snapshots
            WHERE ttf_price IS NOT NULL ORDER BY date DESC LIMIT 1
        """)
        r = cur.fetchone()
        data["ttf_latest"] = float(r["ttf_price"]) if r else None

        cur.execute("""
            SELECT ttf_price FROM ttf_gas_snapshots
            WHERE date < %s AND ttf_price IS NOT NULL ORDER BY date DESC LIMIT 1
        """, (start,))
        r = cur.fetchone()
        data["ttf_week_ago"] = float(r["ttf_price"]) if r else None

        if data["ttf_latest"] and data["ttf_week_ago"]:
            data["ttf_weekly_pct"] = round(
                (data["ttf_latest"] - data["ttf_week_ago"]) / data["ttf_week_ago"] * 100, 1
            )
        else:
            data["ttf_weekly_pct"] = None

        # ── VIX ───────────────────────────────────────────────────────
        cur.execute("""
            SELECT vix_close FROM vix_snapshots
            WHERE vix_close IS NOT NULL ORDER BY date DESC LIMIT 1
        """)
        r = cur.fetchone()
        data["vix_latest"] = float(r["vix_close"]) if r else None

        cur.execute("""
            SELECT vix_close FROM vix_snapshots
            WHERE date < %s AND vix_close IS NOT NULL ORDER BY date DESC LIMIT 1
        """, (start,))
        r = cur.fetchone()
        data["vix_week_ago"] = float(r["vix_close"]) if r else None

        # ── LNG/JKM ──────────────────────────────────────────────────
        cur.execute("""
            SELECT jkm_price FROM lng_price_snapshots
            WHERE jkm_price IS NOT NULL ORDER BY date DESC LIMIT 1
        """)
        r = cur.fetchone()
        data["lng_latest"] = float(r["jkm_price"]) if r else None

        # ── EU Gas Storage ────────────────────────────────────────────
        cur.execute("""
            SELECT eu_storage_percent FROM gas_storage_snapshots
            ORDER BY date DESC LIMIT 1
        """)
        r = cur.fetchone()
        data["storage_pct"] = float(r["eu_storage_percent"]) if r else None

        # ── Alert events (last 6 days) ────────────────────────────────
        cur.execute("""
            SELECT headline, severity, category, created_at
            FROM alert_events
            WHERE created_at >= %s
            ORDER BY severity DESC, created_at DESC
            LIMIT 20
        """, (start,))
        data["alert_events"] = [dict(r) for r in cur.fetchall()]

        # Stats for "Did You Know" section
        cur.execute("""
            SELECT COUNT(*) AS cnt FROM alert_events
            WHERE created_at >= %s
        """, (start,))
        r = cur.fetchone()
        data["events_processed"] = int(r["cnt"]) if r else 0

    return data


# ─────────────────────────────────────────────────────────────
#  AI generation
# ─────────────────────────────────────────────────────────────

def _band_signal(band: Optional[str]) -> str:
    if not band:
        return "—"
    b = band.upper()
    if b == "LOW":
        return "🟢 Low"
    elif b in ("MODERATE", "MEDIUM"):
        return "🟡 Moderate"
    elif b == "ELEVATED":
        return "🟠 Elevated"
    elif b in ("HIGH", "CRITICAL", "EXTREME"):
        return "🔴 High"
    return f"🔵 {band.title()}"


def _delta_str(latest, prev, unit="") -> str:
    if latest is None or prev is None:
        return "—"
    d = latest - prev
    sign = "▲" if d >= 0 else "▼"
    return f"{sign} {'+' if d >= 0 else ''}{d:.1f}{unit}"


def _pct_str(pct: Optional[float]) -> str:
    if pct is None:
        return "—"
    sign = "▲" if pct >= 0 else "▼"
    return f"{sign} {'+' if pct >= 0 else ''}{pct:.1f}%"


def _call_gpt(data: dict) -> dict:
    """Call GPT-5.1 with the week data and return structured AI content."""
    alert_text = ""
    for ev in data.get("alert_events", [])[:10]:
        sev = ev.get("severity", "")
        cat = ev.get("category", "")
        hl  = ev.get("headline", "")
        alert_text += f"  [{sev}] {cat}: {hl}\n"
    if not alert_text:
        alert_text = "  No significant alert events recorded this week.\n"

    geri_series = ", ".join(
        f"{r['date']}: {r['value']}" for r in data.get("geri_rows", [])
    ) or "N/A"
    eeri_series = ", ".join(
        f"{r['date']}: {r['value']}" for r in data.get("eeri_rows", [])
    ) or "N/A"
    brent_series = ", ".join(
        f"{r['date']}: ${r['brent_price']:.2f}" for r in data.get("brent_rows", [])
    ) or "N/A"
    ttf_series = ", ".join(
        f"{r['date']}: €{r['ttf_price']:.2f}" for r in data.get("ttf_rows", [])
    ) or "N/A"

    prompt = f"""You are EnergyRiskIQ's senior energy market analyst and intelligence writer.
Today's date: {date.today().isoformat()}
Reporting week: {data['week_label']}

=== MARKET & RISK DATA (WEEK {data['week_label']}) ===
GERI (Global Energy Risk Index, 0-100): {geri_series}
  Latest: {data.get('geri_latest', 'N/A')} | Band: {data.get('geri_band', 'N/A')}
  Week-ago: {data.get('geri_week_ago', 'N/A')}
EERI (European Energy Risk Index, 0-100): {eeri_series}
  Latest: {data.get('eeri_latest', 'N/A')} | Band: {data.get('eeri_band', 'N/A')}
EGSI-M: {data.get('egsi_m_latest', 'N/A')} ({data.get('egsi_m_band', 'N/A')})
EGSI-S: {data.get('egsi_s_latest', 'N/A')} ({data.get('egsi_s_band', 'N/A')})
Brent ($/bbl): {brent_series}
  Latest: ${data.get('brent_latest', 'N/A')} | Weekly change: {data.get('brent_weekly_pct', 'N/A')}%
WTI: ${data.get('wti_latest', 'N/A')}
TTF (€/MWh): {ttf_series}
  Latest: €{data.get('ttf_latest', 'N/A')} | Weekly change: {data.get('ttf_weekly_pct', 'N/A')}%
VIX: {data.get('vix_latest', 'N/A')}
LNG/JKM: ${data.get('lng_latest', 'N/A')}
EU Gas Storage: {data.get('storage_pct', 'N/A')}%

=== ALERT EVENTS THIS WEEK ===
{alert_text}

=== YOUR TASK ===
Generate the following sections for EnergyRiskIQ's Friday weekly email newsletter.
Write in a confident, professional, intelligence-briefing tone. Never mention AI or GPT.
Reference "our proprietary algorithms" or "our intelligence systems" when appropriate.
Use real numbers from the data above.

Return ONLY a valid JSON object with EXACTLY these keys:

{{
  "executive_summary": "<2-3 sentences summarising global energy risk this week. Reference GERI level and main drivers. Confident, direct tone.>",

  "biggest_story_title": "<Punchy 5-7 word headline for the week's most important development, derived from alert events and data>",
  "biggest_story_body": "<3 paragraphs. Para 1: what happened. Para 2: market context and data (prices, indices). Para 3: 'Why it matters' — forward-looking implication for energy markets. Separate paragraphs with \\n\\n.>",

  "oil_view": "<Label: Bullish/Neutral/Bearish>",
  "oil_analysis": "<2 sentences on Brent outlook — reference price, GERI, key drivers.>",
  "oil_watch": ["<item 1>", "<item 2>", "<item 3>"],

  "gas_view": "<Label: Bullish/Neutral/Bearish/Mildly Bearish/Mildly Bullish>",
  "gas_analysis": "<2 sentences on TTF/European gas — reference price, EERI, storage.>",
  "gas_watch": ["<item 1>", "<item 2>", "<item 3>"],

  "lng_view": "<Label: Bullish/Neutral/Bearish/Neutral to Bullish>",
  "lng_analysis": "<2 sentences on LNG/JKM markets.>",
  "lng_watch": ["<item 1>", "<item 2>", "<item 3>"],

  "geri_commentary": "<1 sentence on GERI status and what it signals.>",
  "eeri_commentary": "<1 sentence on EERI status.>",
  "egsi_commentary": "<1 sentence on EGSI storage/market stress.>",

  "watch_1_title": "<Short title for #1 thing to watch next week>",
  "watch_1_body": "<1-2 sentence explanation.>",
  "watch_2_title": "<Short title for #2 thing to watch next week>",
  "watch_2_body": "<1-2 sentence explanation.>",
  "watch_3_title": "<Short title for #3 thing to watch next week>",
  "watch_3_body": "<1-2 sentence explanation.>",

  "scenario_base_pct": <integer, base case probability %>,
  "scenario_base_label": "Base Case",
  "scenario_base_brent_range": "<e.g. $85–90/bbl>",
  "scenario_base_ttf_range": "<e.g. €43–47/MWh>",
  "scenario_base_body": "<2 sentences: market stays stable, index levels, key assumption.>",

  "scenario_elevated_pct": <integer, elevated risk probability %>,
  "scenario_elevated_label": "Elevated Risk",
  "scenario_elevated_brent": "<price level if this scenario>",
  "scenario_elevated_ttf": "<price level if this scenario>",
  "scenario_elevated_body": "<2 sentences: what triggers this, market reaction.>",

  "scenario_high_pct": <integer, high impact probability %>,
  "scenario_high_label": "High Impact Scenario",
  "scenario_high_body": "<2 sentences: tail risk event, cross-market impact.>",

  "chart_choice": "<One of: GERI_BRENT, GERI_WTI, EERI_TTF — pick the pair that best illustrates the week's story>",
  "chart_title": "<Chart title, e.g. 'GERI vs. Brent Crude — Weekly View'>",
  "chart_interpretation": "<3 sentences interpreting the chart. Reference divergence/convergence, what the pattern means for risk managers.>",

  "professional_insight": "<3-4 sentence closing insight. Markets, data convergence, value of the platform. Thoughtful, not salesy.>"
}}

No markdown. No extra keys. Valid JSON only. Keep all text values concise — email clients render long blocks poorly."""

    try:
        from openai import OpenAI
        ai_key = os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY")
        ai_url = os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL")
        client = OpenAI(api_key=ai_key, base_url=ai_url) if (ai_key and ai_url) else OpenAI()

        resp = client.chat.completions.create(
            model="gpt-5.1",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_completion_tokens=3000,
            response_format={"type": "json_object"},
            timeout=90,
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as exc:
        logger.warning(f"Weekly outlook GPT call failed: {exc}")
        return _ai_fallback(data)


def _ai_fallback(data: dict) -> dict:
    geri = data.get("geri_latest") or 0
    band = (data.get("geri_band") or "Moderate").title()
    brent = data.get("brent_latest") or 0
    ttf = data.get("ttf_latest") or 0
    return {
        "executive_summary": (
            f"Global energy risk indicators registered {band} levels this week, with GERI at {geri:.0f}. "
            f"Brent crude traded near ${brent:.2f}/bbl while European gas markets showed mixed signals. "
            "Geopolitical and supply-side dynamics remain key variables heading into next week."
        ),
        "biggest_story_title": "Energy Markets Navigate Geopolitical Crosscurrents",
        "biggest_story_body": (
            "This week saw continued uncertainty across global energy supply chains, with geopolitical pressures adding risk premiums to oil and gas markets.\n\n"
            f"Brent crude closed near ${brent:.2f}/bbl, while GERI remained at {geri:.0f}, indicating {band} risk conditions across global energy infrastructure. "
            "European gas markets continued to track both storage trends and seasonal demand shifts.\n\n"
            "Why it matters: Elevated risk indicators suggest traders and risk managers should maintain heightened vigilance — "
            "any sudden supply disruption or geopolitical escalation could amplify current price volatility significantly."
        ),
        "oil_view": "Neutral",
        "oil_analysis": f"Brent crude at ${brent:.2f}/bbl reflects balanced supply-demand dynamics with moderate geopolitical risk overlay. GERI at {geri:.0f} supports cautious short-term positioning.",
        "oil_watch": ["OPEC+ guidance", "Middle East security", "US inventory data"],
        "gas_view": "Neutral",
        "gas_analysis": f"European gas prices at €{ttf:.2f}/MWh remain driven by storage injection season and Norwegian supply reliability. Demand remains seasonally subdued.",
        "gas_watch": ["EU storage levels", "Norwegian maintenance", "LNG import volumes"],
        "lng_view": "Neutral to Bullish",
        "lng_analysis": "LNG freight markets remain stable with Asian demand providing baseline support. Geopolitical risk to shipping routes remains the primary upside uncertainty.",
        "lng_watch": ["Asian demand signals", "Panama Canal throughput", "Middle East shipping"],
        "geri_commentary": f"GERI at {geri:.0f} ({band}) indicates measured geopolitical risk — monitoring continues for escalation triggers.",
        "eeri_commentary": "EERI remains stable with European infrastructure operating without significant disruption.",
        "egsi_commentary": "EU gas storage and market stress indicators remain within seasonal norms.",
        "watch_1_title": "OPEC+ Policy Signals",
        "watch_1_body": "Any unexpected production guidance could sharply influence Brent volatility and sentiment heading into Q3.",
        "watch_2_title": "European Gas Storage",
        "watch_2_body": "Injection rates remain one of the most reliable forward indicators for European gas price direction into winter.",
        "watch_3_title": "Geopolitical Risk Developments",
        "watch_3_body": "Ongoing tensions in key energy corridors could rapidly reintroduce geopolitical risk premiums across multiple asset classes.",
        "scenario_base_pct": 65,
        "scenario_base_label": "Base Case",
        "scenario_base_brent_range": f"${max(brent-5,60):.0f}–{brent+3:.0f}/bbl",
        "scenario_base_ttf_range": f"€{max(ttf-3,30):.0f}–{ttf+3:.0f}/MWh",
        "scenario_base_body": "Markets remain stable with moderate volatility. GERI holds within current range and no major supply disruptions materialize.",
        "scenario_elevated_pct": 25,
        "scenario_elevated_label": "Elevated Risk",
        "scenario_elevated_brent": f"${brent+8:.0f}",
        "scenario_elevated_ttf": f"€{ttf+5:.0f}",
        "scenario_elevated_body": "Regional geopolitical escalation increases risk premiums. Brent and TTF move above current trading ranges as supply uncertainty grows.",
        "scenario_high_pct": 10,
        "scenario_high_label": "High Impact Scenario",
        "scenario_high_body": "An unexpected major supply disruption triggers a rapid cross-market repricing. Significant volatility across oil, gas, and freight markets.",
        "chart_choice": "GERI_BRENT",
        "chart_title": "GERI vs. Brent Crude — Weekly View",
        "chart_interpretation": "This week's chart shows the relationship between measured geopolitical risk (GERI) and Brent crude prices. Divergences between these two series often precede market repricing events — a rising GERI without corresponding price reaction suggests risk is being underpriced. Risk managers should monitor any narrowing of this gap closely.",
        "professional_insight": "Energy markets rarely move on a single headline. Our algorithms synthesise thousands of geopolitical signals, infrastructure events, and market indicators each day to surface the patterns that matter. This weekly summary represents a distillation of that intelligence — curated specifically to inform your decisions before markets open next week.",
    }


# ─────────────────────────────────────────────────────────────
#  QuickChart.io chart builder (email-safe PNG image)
# ─────────────────────────────────────────────────────────────

def _chart_destination(chart_choice: str) -> str:
    """Return the dashboard path the chart click-through should land on."""
    if chart_choice == "EERI_TTF":
        return "/eeri"
    return "/geri"


def _build_quickchart_url(data: dict, chart_choice: str) -> str:
    """Build a QuickChart.io PNG image URL for dual-axis chart.
    Returns an empty string if insufficient data."""
    from datetime import datetime as _dt

    # Pick data series based on chart type
    if chart_choice == "EERI_TTF":
        left_rows  = data.get("eeri_rows", [])
        left_vals  = [float(r["value"]) for r in left_rows]
        left_dates = [str(r["date"]) for r in left_rows]
        right_rows  = data.get("ttf_rows", [])
        right_vals  = [float(r["ttf_price"]) for r in right_rows]
        right_dates = [str(r["date"]) for r in right_rows]
        left_label  = "EERI"
        right_label = "TTF (€/MWh)"
        left_color  = "rgb(99,102,241)"
        right_color = "rgb(245,158,11)"
        left_fill   = "rgba(99,102,241,0.18)"
    elif chart_choice == "GERI_WTI":
        left_rows  = data.get("geri_rows", [])
        left_vals  = [float(r["value"]) for r in left_rows]
        left_dates = [str(r["date"]) for r in left_rows]
        right_rows  = data.get("wti_rows", [])
        right_vals  = [float(r["wti_price"]) for r in right_rows if r.get("wti_price")]
        right_dates = [str(r["date"]) for r in right_rows if r.get("wti_price")]
        left_label  = "GERI"
        right_label = "WTI ($/bbl)"
        left_color  = "rgb(99,102,241)"
        right_color = "rgb(34,197,94)"
        left_fill   = "rgba(99,102,241,0.18)"
    else:  # GERI_BRENT (default)
        left_rows  = data.get("geri_rows", [])
        left_vals  = [float(r["value"]) for r in left_rows]
        left_dates = [str(r["date"]) for r in left_rows]
        right_rows  = data.get("brent_rows", [])
        right_vals  = [float(r["brent_price"]) for r in right_rows]
        right_dates = [str(r["date"]) for r in right_rows]
        left_label  = "GERI"
        right_label = "Brent ($/bbl)"
        left_color  = "rgb(99,102,241)"
        right_color = "rgb(212,160,23)"
        left_fill   = "rgba(99,102,241,0.18)"

    # Align series by date, forward-fill gaps
    all_dates = sorted(set(left_dates) | set(right_dates))
    if not all_dates:
        return ""

    lmap = dict(zip(left_dates, left_vals))
    rmap = dict(zip(right_dates, right_vals))
    lv = [lmap.get(d) for d in all_dates]
    rv = [rmap.get(d) for d in all_dates]

    for i in range(1, len(lv)):
        if lv[i] is None: lv[i] = lv[i - 1]
        if rv[i] is None: rv[i] = rv[i - 1]

    pairs = [(d, l, r) for d, l, r in zip(all_dates, lv, rv)
             if l is not None and r is not None]
    if len(pairs) < 2:
        return ""

    dates_used, lv_used, rv_used = zip(*pairs)

    # Date labels
    labels = []
    for d in dates_used:
        try:
            labels.append(_dt.strptime(d, "%Y-%m-%d").strftime("%-d %b"))
        except Exception:
            labels.append(str(d)[-5:])

    # Right-axis scale: auto around the data, with 1-unit step size
    r_min  = max(0, math.floor(min(rv_used)) - 2)
    r_max  = math.ceil(max(rv_used)) + 2
    r_range = max(r_max - r_min, 1)
    r_step  = max(1, round(r_range / 8))   # ~8 ticks max

    cfg = {
        "type": "line",
        "data": {
            "labels": list(labels),
            "datasets": [
                {
                    "label": left_label,
                    "data": [round(v, 1) for v in lv_used],
                    "borderColor": left_color,
                    "backgroundColor": left_fill,
                    "fill": True,
                    "tension": 0.35,
                    "yAxisID": "y",
                    "borderWidth": 2,
                    "pointBackgroundColor": left_color,
                    "pointBorderColor": left_color,
                    "pointRadius": 5,
                    "pointHoverRadius": 8,
                },
                {
                    "label": right_label,
                    "data": [round(v, 2) for v in rv_used],
                    "borderColor": right_color,
                    "backgroundColor": "transparent",
                    "fill": False,
                    "tension": 0.35,
                    "yAxisID": "y1",
                    "borderWidth": 2,
                    "borderDash": [6, 3],
                    "pointBackgroundColor": right_color,
                    "pointBorderColor": right_color,
                    "pointRadius": 5,
                    "pointHoverRadius": 8,
                },
            ],
        },
        "options": {
            "plugins": {
                "legend": {
                    "display": True,
                    "labels": {
                        "color": "rgb(226,232,240)",
                        "font": {"size": 11},
                        "usePointStyle": True,
                        "padding": 16,
                    },
                },
                "tooltip": {"mode": "index", "intersect": False},
            },
            "scales": {
                "y": {
                    "type": "linear",
                    "position": "left",
                    "min": 0,
                    "max": 100,
                    "title": {
                        "display": True,
                        "text": f"{left_label} (0\u2013100)",
                        "color": left_color,
                        "font": {"size": 11, "weight": "600"},
                    },
                    "ticks": {
                        "color": left_color,
                        "stepSize": 10,
                        "font": {"size": 10},
                    },
                    "grid": {
                        "color": "rgba(226,232,240,0.07)",
                    },
                    "border": {
                        "display": False,
                    },
                },
                "y1": {
                    "type": "linear",
                    "position": "right",
                    "min": r_min,
                    "max": r_max,
                    "title": {
                        "display": True,
                        "text": right_label,
                        "color": right_color,
                        "font": {"size": 11, "weight": "600"},
                    },
                    "ticks": {
                        "color": right_color,
                        "stepSize": r_step,
                        "font": {"size": 10},
                    },
                    "grid": {
                        "drawOnChartArea": False,
                    },
                    "border": {
                        "display": False,
                    },
                },
                "x": {
                    "ticks": {
                        "color": "rgb(148,163,184)",
                        "font": {"size": 10},
                        "maxRotation": 0,
                    },
                    "grid": {
                        "color": "rgba(226,232,240,0.04)",
                    },
                    "border": {
                        "display": False,
                    },
                },
            },
            "animation": False,
        },
    }

    cfg_str = json.dumps(cfg, separators=(",", ":"))
    encoded = urllib.parse.quote(cfg_str)
    bkg     = urllib.parse.quote("rgb(15,23,42)")
    return f"https://quickchart.io/chart?c={encoded}&w=560&h=280&bkg={bkg}&f=png&v=4"


# ─────────────────────────────────────────────────────────────
#  Email HTML builder
# ─────────────────────────────────────────────────────────────

def _band_dot(band: Optional[str]) -> str:
    b = (band or "").upper()
    if b == "LOW":           return "🟢"
    elif b in ("MODERATE", "MEDIUM"): return "🟡"
    elif b == "ELEVATED":    return "🟠"
    elif b in ("HIGH", "CRITICAL"):   return "🔴"
    return "🔵"


def _sign_arrow(val: Optional[float]) -> str:
    if val is None: return ""
    return "▲" if val >= 0 else "▼"


def _color_pct(pct: Optional[float]) -> str:
    if pct is None: return "#94a3b8"
    return "#22c55e" if pct >= 0 else "#ef4444"


def _esc(s) -> str:
    return _html.escape(str(s)) if s is not None else ""


def _nl2br(s: str) -> str:
    return _esc(s).replace("\n\n", "</p><p style='margin:0 0 12px;font-size:15px;line-height:1.6;color:#334155;'>")


def _view_str(v: Optional[str]) -> str:
    if not v:
        return "Neutral"
    v = v.strip()
    color_map = {
        "bullish": "#22c55e",
        "mildly bullish": "#86efac",
        "neutral to bullish": "#6ee7b7",
        "neutral": "#94a3b8",
        "mildly bearish": "#fbbf24",
        "bearish": "#ef4444",
    }
    color = color_map.get(v.lower(), "#94a3b8")
    return f'<span style="color:{color};font-weight:700;">{_esc(v)}</span>'


def build_weekly_email_html(data: dict, ai: dict,
                            login_url: str = "",
                            chart_login_url: str = "") -> str:
    if not login_url:
        login_url = f"{APP_URL}/users/account"
    if not chart_login_url:
        chart_login_url = login_url

    logo_url = f"{APP_URL}/static/logo.png"
    week = _esc(data.get("week_label", ""))
    subject = f"This Week's Global Energy Risk Outlook — {week}"

    # ── Glance table rows ────────────────────────────────────
    geri_chg   = _delta_str(data.get("geri_latest"), data.get("geri_week_ago"))
    eeri_chg   = _delta_str(data.get("eeri_latest"), data.get("eeri_week_ago"))
    egsi_chg   = _delta_str(data.get("egsi_m_latest"), data.get("egsi_m_week_ago"))
    brent_chg  = _pct_str(data.get("brent_weekly_pct"))
    ttf_chg    = _pct_str(data.get("ttf_weekly_pct"))
    vix_chg    = _delta_str(data.get("vix_latest"), data.get("vix_week_ago"))

    brent_clr = _color_pct(data.get("brent_weekly_pct"))
    ttf_clr   = _color_pct(data.get("ttf_weekly_pct"))
    geri_clr  = "#22c55e" if (data.get("geri_latest") or 0) <= (data.get("geri_week_ago") or 100) else "#ef4444"
    vix_clr   = "#22c55e" if (data.get("vix_latest") or 0) <= (data.get("vix_week_ago") or 100) else "#ef4444"

    def trow(label, current, change, signal, chg_color="#94a3b8"):
        return f"""
        <tr>
          <td style="padding:10px 14px;border-bottom:1px solid #e2e8f0;font-size:14px;font-weight:600;color:#0f172a;">{_esc(label)}</td>
          <td style="padding:10px 14px;border-bottom:1px solid #e2e8f0;font-size:14px;color:#0f172a;text-align:center;">{_esc(current)}</td>
          <td style="padding:10px 14px;border-bottom:1px solid #e2e8f0;font-size:13px;color:{chg_color};text-align:center;">{_esc(change)}</td>
          <td style="padding:10px 14px;border-bottom:1px solid #e2e8f0;font-size:13px;text-align:center;">{signal}</td>
        </tr>"""

    glance_rows = (
        trow("GERI",  f"{data.get('geri_latest', '—'):.0f}" if data.get("geri_latest") else "—",
             geri_chg,  _band_signal(data.get("geri_band")),  geri_clr) +
        trow("EERI",  f"{data.get('eeri_latest', '—'):.0f}" if data.get("eeri_latest") else "—",
             eeri_chg,  _band_signal(data.get("eeri_band")),  geri_clr) +
        trow("EGSI-M", f"{data.get('egsi_m_latest', '—'):.1f}" if data.get("egsi_m_latest") else "—",
             egsi_chg,  _band_signal(data.get("egsi_m_band")), geri_clr) +
        trow("Brent", f"${data.get('brent_latest', 0):.2f}" if data.get("brent_latest") else "—",
             brent_chg, "Neutral" if abs(data.get("brent_weekly_pct") or 0) < 2 else ("Bullish" if (data.get("brent_weekly_pct") or 0) > 0 else "Bearish"),
             brent_clr) +
        trow("TTF",   f"€{data.get('ttf_latest', 0):.2f}" if data.get("ttf_latest") else "—",
             ttf_chg,   "Neutral" if abs(data.get("ttf_weekly_pct") or 0) < 2 else ("Bullish" if (data.get("ttf_weekly_pct") or 0) > 0 else "Bearish"),
             ttf_clr) +
        trow("VIX",   f"{data.get('vix_latest', 0):.1f}" if data.get("vix_latest") else "—",
             vix_chg,   "Stable" if abs((data.get("vix_latest") or 0) - (data.get("vix_week_ago") or 0)) < 2 else "Volatile",
             vix_clr)
    )

    # ── Outlook commodity cards ──────────────────────────────
    def commodity_card(icon, name, view, analysis, watch_items):
        watch_li = "".join(
            f'<li style="margin:4px 0;font-size:13px;color:#475569;">{_esc(w)}</li>'
            for w in watch_items
        )
        return f"""
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:16px;background:#f8fafc;border-radius:8px;border-left:4px solid #d4a017;overflow:hidden;">
          <tr>
            <td style="padding:16px 20px;">
              <div style="font-size:16px;font-weight:700;color:#0f172a;margin-bottom:4px;">{icon} {_esc(name)}</div>
              <div style="font-size:13px;color:#64748b;margin-bottom:8px;">Current View: {_view_str(view)}</div>
              <p style="margin:0 0 10px;font-size:14px;line-height:1.5;color:#334155;">{_esc(analysis)}</p>
              <div style="font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;color:#94a3b8;margin-bottom:4px;">Watch</div>
              <ul style="margin:0;padding-left:18px;">{watch_li}</ul>
            </td>
          </tr>
        </table>"""

    oil_card = commodity_card("🛢", "Oil (Brent)", ai.get("oil_view", "Neutral"),
                               ai.get("oil_analysis", ""), ai.get("oil_watch", []))
    gas_card = commodity_card("🔥", "European Gas (TTF)", ai.get("gas_view", "Neutral"),
                               ai.get("gas_analysis", ""), ai.get("gas_watch", []))
    lng_card = commodity_card("🚢", "LNG", ai.get("lng_view", "Neutral"),
                               ai.get("lng_analysis", ""), ai.get("lng_watch", []))

    # ── Risk Dashboard Snapshot ──────────────────────────────
    def risk_row(label, band, commentary):
        dot = _band_dot(band)
        b_label = (band or "—").upper()
        return f"""
        <tr>
          <td style="padding:12px 16px;border-bottom:1px solid #e2e8f0;width:120px;">
            <div style="font-size:14px;font-weight:700;color:#0f172a;">{_esc(label)}</div>
            <div style="font-size:12px;margin-top:2px;">{dot} {_esc(b_label)}</div>
          </td>
          <td style="padding:12px 16px;border-bottom:1px solid #e2e8f0;font-size:13px;color:#475569;">{_esc(commentary)}</td>
        </tr>"""

    risk_rows = (
        risk_row("GERI", data.get("geri_band"), ai.get("geri_commentary", ""))  +
        risk_row("EERI", data.get("eeri_band"), ai.get("eeri_commentary", ""))  +
        risk_row("EGSI", data.get("egsi_m_band"), ai.get("egsi_commentary", ""))
    )

    # ── Top 3 watch items ───────────────────────────────────
    def watch_item(num, title, body):
        nums = ["①", "②", "③"]
        n = nums[num - 1] if 1 <= num <= 3 else str(num)
        return f"""
        <tr>
          <td style="padding:14px 16px;border-bottom:1px solid #e2e8f0;vertical-align:top;width:36px;font-size:22px;color:#d4a017;">{n}</td>
          <td style="padding:14px 16px;border-bottom:1px solid #e2e8f0;">
            <div style="font-size:14px;font-weight:700;color:#0f172a;margin-bottom:4px;">{_esc(title)}</div>
            <div style="font-size:13px;color:#475569;line-height:1.5;">{_esc(body)}</div>
          </td>
        </tr>"""

    watch_rows = (
        watch_item(1, ai.get("watch_1_title", ""), ai.get("watch_1_body", "")) +
        watch_item(2, ai.get("watch_2_title", ""), ai.get("watch_2_body", "")) +
        watch_item(3, ai.get("watch_3_title", ""), ai.get("watch_3_body", ""))
    )

    # ── Scenarios ────────────────────────────────────────────
    def scenario_card(emoji, color, label, pct, extra, body):
        return f"""
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:12px;border-radius:8px;border-left:4px solid {color};background:#f8fafc;">
          <tr>
            <td style="padding:14px 18px;">
              <div style="font-size:14px;font-weight:700;color:#0f172a;margin-bottom:4px;">{emoji} {_esc(label)} <span style="color:{color};font-weight:400;font-size:12px;">({pct}%)</span></div>
              {f'<div style="font-size:12px;color:#64748b;margin-bottom:6px;">{_esc(extra)}</div>' if extra else ""}
              <div style="font-size:13px;color:#475569;line-height:1.5;">{_esc(body)}</div>
            </td>
          </tr>
        </table>"""

    base_extra = (f"Brent: {ai.get('scenario_base_brent_range','')}  |  "
                  f"TTF: {ai.get('scenario_base_ttf_range','')}")
    elev_extra = (f"Brent: {ai.get('scenario_elevated_brent','')}  |  "
                  f"TTF: {ai.get('scenario_elevated_ttf','')}")

    scenarios = (
        scenario_card("🟢", "#22c55e", ai.get("scenario_base_label", "Base Case"),
                      ai.get("scenario_base_pct", 65), base_extra, ai.get("scenario_base_body", "")) +
        scenario_card("🟡", "#f59e0b", ai.get("scenario_elevated_label", "Elevated Risk"),
                      ai.get("scenario_elevated_pct", 25), elev_extra, ai.get("scenario_elevated_body", "")) +
        scenario_card("🔴", "#ef4444", ai.get("scenario_high_label", "High Impact"),
                      ai.get("scenario_high_pct", 10), "", ai.get("scenario_high_body", ""))
    )

    # ── Chart ────────────────────────────────────────────────
    chart_choice   = ai.get("chart_choice", "GERI_BRENT")
    chart_img_url  = _build_quickchart_url(data, chart_choice)
    chart_title    = _esc(ai.get("chart_title", "Chart of the Week"))
    chart_interp   = _nl2br(ai.get("chart_interpretation", ""))
    chart_dest     = _chart_destination(chart_choice)
    chart_dest_label = "EERI Dashboard" if chart_choice == "EERI_TTF" else "GERI Dashboard"

    # Top 5 alert events for chart context
    top_events = data.get("alert_events", [])[:5]
    events_li = "".join(
        f'<li style="margin:4px 0;font-size:12px;color:#64748b;">'
        f'<span style="font-weight:600;color:#475569;">[{_esc(ev.get("severity",""))}]</span> '
        f'{_esc(ev.get("headline",""))}</li>'
        for ev in top_events
    ) or '<li style="font-size:12px;color:#94a3b8;">No significant events recorded this week.</li>'

    # ── Stats ────────────────────────────────────────────────
    events_count = data.get("events_processed", 0)
    countries_count = 128  # platform constant

    # ── CTA links ────────────────────────────────────────────
    def cta_link(label, path):
        url = f"{APP_URL}{path}"
        return (f'<tr><td style="padding:6px 0;">'
                f'<a href="{_esc(url)}" style="font-size:14px;color:#d4a017;text-decoration:none;">'
                f'→ {_esc(label)}</a></td></tr>')

    cta_links = (
        cta_link("GERI Dashboard", "/geri") +
        cta_link("GERI Live", "/geri/live") +
        cta_link("EERI Dashboard", "/eeri") +
        cta_link("EGSI Dashboard", "/egsi") +
        cta_link("Daily Intelligence Report", "/users/account")
    )

    biggest_paras = _nl2br(ai.get("biggest_story_body", ""))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{_esc(subject)}</title>
</head>
<body style="margin:0;padding:0;background-color:#0f172a;font-family:Arial,Helvetica,sans-serif;color:#1a1a1a;-webkit-text-size-adjust:100%;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#0f172a;padding:24px 0;">
  <tr>
    <td align="center">
      <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background-color:#ffffff;border-radius:12px;overflow:hidden;">

        <!-- HEADER -->
        <tr>
          <td style="background:linear-gradient(135deg,#0f172a 0%,#1e293b 100%);padding:28px 32px;text-align:center;">
            <table role="presentation" cellpadding="0" cellspacing="0" align="center" style="margin:0 auto;">
              <tr>
                <td style="vertical-align:middle;padding-right:12px;">
                  <img src="{logo_url}" alt="EnergyRiskIQ" width="44" height="44" style="display:block;border:0;">
                </td>
                <td style="vertical-align:middle;">
                  <span style="color:#d4a017;font-size:22px;font-weight:bold;letter-spacing:0.5px;">EnergyRiskIQ</span>
                </td>
              </tr>
            </table>
            <p style="margin:10px 0 4px;color:#94a3b8;font-size:12px;letter-spacing:1px;text-transform:uppercase;">Energy Risk Intelligence</p>
            <div style="margin-top:16px;background:#1e293b;border-radius:8px;padding:12px 20px;display:inline-block;">
              <p style="margin:0;color:#f8fafc;font-size:18px;font-weight:700;">This Week's Global Energy Risk Outlook</p>
              <p style="margin:6px 0 0;color:#94a3b8;font-size:13px;">Week of {week}</p>
            </div>
          </td>
        </tr>

        <!-- BODY -->
        <tr>
          <td style="padding:32px;">

            <!-- Greeting -->
            <p style="margin:0 0 6px;font-size:16px;color:#0f172a;">Hello dear User of EnergyRiskIQ,</p>
            <p style="margin:0 0 28px;font-size:14px;line-height:1.6;color:#475569;">
              Every Friday, we summarise the week's most important developments across global energy markets, geopolitical risks, and our proprietary EnergyRiskIQ indicators — so you know what deserves your attention before markets open next week.
            </p>

            <!-- EXECUTIVE SUMMARY -->
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:28px;">
              <tr>
                <td style="border-left:4px solid #d4a017;padding:16px 20px;background:#fffbeb;border-radius:0 8px 8px 0;">
                  <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#d4a017;margin-bottom:8px;">Executive Summary</div>
                  <p style="margin:0;font-size:15px;line-height:1.6;color:#0f172a;font-style:italic;">{_esc(ai.get('executive_summary',''))}</p>
                </td>
              </tr>
            </table>

            <!-- AT A GLANCE TABLE -->
            <div style="font-size:16px;font-weight:700;color:#0f172a;margin-bottom:12px;padding-bottom:8px;border-bottom:2px solid #e2e8f0;">
              📊 This Week at a Glance
            </div>
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:28px;border-radius:8px;overflow:hidden;border:1px solid #e2e8f0;">
              <tr style="background:#0f172a;">
                <th style="padding:10px 14px;text-align:left;font-size:12px;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:0.5px;">Indicator</th>
                <th style="padding:10px 14px;text-align:center;font-size:12px;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:0.5px;">Current</th>
                <th style="padding:10px 14px;text-align:center;font-size:12px;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:0.5px;">Weekly Change</th>
                <th style="padding:10px 14px;text-align:center;font-size:12px;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:0.5px;">Signal</th>
              </tr>
              {glance_rows}
            </table>

            <!-- BIGGEST STORY -->
            <div style="font-size:16px;font-weight:700;color:#0f172a;margin-bottom:14px;padding-bottom:8px;border-bottom:2px solid #e2e8f0;">
              🔍 This Week's Biggest Story
            </div>
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:28px;background:#f8fafc;border-radius:8px;overflow:hidden;">
              <tr>
                <td style="padding:20px 24px;">
                  <div style="font-size:17px;font-weight:700;color:#0f172a;margin-bottom:14px;">{_esc(ai.get('biggest_story_title',''))}</div>
                  <p style="margin:0 0 12px;font-size:15px;line-height:1.6;color:#334155;">{biggest_paras}</p>
                </td>
              </tr>
            </table>

            <!-- ENERGYRISKIQ OUTLOOK -->
            <div style="font-size:16px;font-weight:700;color:#0f172a;margin-bottom:14px;padding-bottom:8px;border-bottom:2px solid #e2e8f0;">
              📈 EnergyRiskIQ Outlook
            </div>
            <div style="margin-bottom:28px;">
              {oil_card}
              {gas_card}
              {lng_card}
            </div>

            <!-- RISK DASHBOARD SNAPSHOT -->
            <div style="font-size:16px;font-weight:700;color:#0f172a;margin-bottom:12px;padding-bottom:8px;border-bottom:2px solid #e2e8f0;">
              🛡 Risk Dashboard Snapshot
            </div>
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:28px;border-radius:8px;overflow:hidden;border:1px solid #e2e8f0;">
              {risk_rows}
            </table>

            <!-- TOP 3 THINGS TO WATCH -->
            <div style="font-size:16px;font-weight:700;color:#0f172a;margin-bottom:12px;padding-bottom:8px;border-bottom:2px solid #e2e8f0;">
              👁 Top 3 Things to Watch Next Week
            </div>
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:28px;border-radius:8px;overflow:hidden;border:1px solid #e2e8f0;">
              {watch_rows}
            </table>

            <!-- SCENARIO OUTLOOK -->
            <div style="font-size:16px;font-weight:700;color:#0f172a;margin-bottom:14px;padding-bottom:8px;border-bottom:2px solid #e2e8f0;">
              🎯 Scenario Outlook
            </div>
            <div style="margin-bottom:28px;">
              {scenarios}
            </div>

            <!-- CHART OF THE WEEK -->
            <div style="font-size:16px;font-weight:700;color:#0f172a;margin-bottom:14px;padding-bottom:8px;border-bottom:2px solid #e2e8f0;">
              📉 Chart of the Week
            </div>
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:4px;background:#0f172a;border-radius:8px;overflow:hidden;">
              <tr>
                <td style="padding:16px 20px 10px;">
                  <div style="font-size:13px;font-weight:700;color:#d4a017;margin-bottom:12px;">{chart_title}</div>
                  {'<a href="' + _esc(chart_login_url) + '" style="display:block;text-decoration:none;cursor:pointer;" title="Click to open ' + chart_dest_label + '">' + '<img src="' + _esc(chart_img_url) + '" alt="' + chart_title + '" width="528" style="display:block;width:100%;max-width:528px;border:0;border-radius:6px;" />' + '</a>' if chart_img_url else '<p style="color:#64748b;font-size:13px;text-align:center;padding:20px 0;">Chart data unavailable</p>'}
                  <div style="margin-top:8px;text-align:center;">
                    <a href="{_esc(chart_login_url)}" style="font-size:11px;color:#6366f1;text-decoration:none;">
                      ↗ Click chart to open {_esc(chart_dest_label)} →
                    </a>
                  </div>
                </td>
              </tr>
            </table>
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:10px;background:#f8fafc;border-radius:8px;">
              <tr>
                <td style="padding:14px 18px;">
                  <p style="margin:0 0 10px;font-size:14px;line-height:1.6;color:#334155;">{chart_interp}</p>
                  <div style="font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;color:#94a3b8;margin-bottom:6px;">Key Events This Week</div>
                  <ul style="margin:0;padding-left:18px;">{events_li}</ul>
                </td>
              </tr>
            </table>

            <!-- PROFESSIONAL INSIGHT -->
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:28px 0 0;background:#1e293b;border-radius:8px;">
              <tr>
                <td style="padding:20px 24px;">
                  <div style="font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#d4a017;margin-bottom:10px;">Professional Insight</div>
                  <p style="margin:0 0 16px;font-size:14px;line-height:1.6;color:#e2e8f0;">{_esc(ai.get('professional_insight',''))}</p>
                  <table role="presentation" cellpadding="0" cellspacing="0" style="margin-top:10px;">
                    <tr>
                      <td style="background:#0f172a;border-radius:6px;padding:12px 18px;text-align:center;">
                        <div style="font-size:13px;color:#94a3b8;margin-bottom:6px;">Did You Know?</div>
                        <div style="font-size:13px;color:#e2e8f0;">This week, EnergyRiskIQ processed</div>
                        <div style="font-size:26px;font-weight:700;color:#d4a017;margin:4px 0;">{events_count:,}</div>
                        <div style="font-size:13px;color:#e2e8f0;">intelligence events across <strong style="color:#d4a017;">{countries_count}</strong> countries</div>
                      </td>
                    </tr>
                  </table>
                </td>
              </tr>
            </table>

          </td>
        </tr>

        <!-- CONTINUE YOUR ANALYSIS -->
        <tr>
          <td style="padding:24px 32px;background:#f8fafc;">
            <div style="font-size:15px;font-weight:700;color:#0f172a;margin-bottom:4px;">Continue Your Analysis</div>
            <p style="margin:0 0 14px;font-size:13px;color:#64748b;">Explore today's intelligence:</p>
            <table role="presentation" cellpadding="0" cellspacing="0">
              {cta_links}
            </table>
            <table role="presentation" cellpadding="0" cellspacing="0" style="margin-top:16px;">
              <tr>
                <td align="center" style="border-radius:8px;background-color:#d4a017;">
                  <a href="{_esc(login_url)}" style="display:inline-block;padding:12px 28px;font-size:15px;font-weight:bold;color:#0f172a;text-decoration:none;border-radius:8px;">Login To Your Account</a>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- SUPPORT -->
        <tr>
          <td style="padding:20px 32px;background:#fff;border-top:1px solid #e2e8f0;">
            <p style="margin:0 0 6px;font-size:14px;color:#475569;"><strong>Need Help?</strong></p>
            <p style="margin:0 0 16px;font-size:13px;color:#64748b;line-height:1.5;">
              Have a question about today's outlook or one of the dashboards? Open a support ticket from your account or use ERIQ, and we'll be happy to help.
            </p>
            <p style="margin:0 0 4px;font-size:14px;color:#475569;">Thank you for being part of the EnergyRiskIQ community.</p>
            <p style="margin:0 0 16px;font-size:14px;color:#475569;">Have a productive and well-informed week.</p>
            <p style="margin:0;font-size:15px;color:#0f172a;"><strong>Best regards,</strong><br>
            Emil C<br>
            <span style="color:#64748b;font-size:13px;">Founder, EnergyRiskIQ</span></p>
          </td>
        </tr>

        <!-- FOOTER -->
        <tr>
          <td style="background:#0f172a;padding:20px 32px;">
            <p style="margin:0 0 6px;font-size:12px;color:#94a3b8;text-align:center;">
              <strong style="color:#d4a017;">EnergyRiskIQ</strong> — Energy Risk Intelligence
            </p>
            <p style="margin:0;font-size:12px;color:#64748b;text-align:center;line-height:1.5;">
              You are receiving this email because you have an EnergyRiskIQ account.<br>
              You can reply directly to this email at any time.
            </p>
          </td>
        </tr>

      </table>
    </td>
  </tr>
</table>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────
#  Pydantic models
# ─────────────────────────────────────────────────────────────

class WeeklyOutlookSendRequest(BaseModel):
    html: str
    subject: str
    test_email: Optional[str] = TEST_EMAIL
    chart_destination: Optional[str] = "/geri"   # e.g. "/geri" or "/eeri"


class WeeklyOutlookSendAllRequest(BaseModel):
    html: str
    subject: str
    chart_destination: Optional[str] = "/geri"   # e.g. "/geri" or "/eeri"


# ─────────────────────────────────────────────────────────────
#  Background sender (mirrors _run_bulk_email)
# ─────────────────────────────────────────────────────────────

def _run_weekly_send_all(campaign_id: int, subject: str, full_html: str,
                         emails: List[str], chart_destination: str = "/geri"):
    brevo_api_key = os.environ.get("BREVO_API_KEY")
    if not brevo_api_key:
        _update_campaign(campaign_id, status="failed", error="BREVO_API_KEY not configured")
        return

    sender = _email_sender()
    fallback_login_url  = f"{APP_URL}/users/account"
    fallback_chart_url  = f"{APP_URL}{chart_destination}"
    login_urls          = {}   # email → magic-login URL
    chart_login_urls    = {}   # email → magic-login URL + ?next=<dest>

    try:
        from src.api.user_routes import create_email_login_token
        from src.db.db import get_cursor as _gc
        with _gc(commit=False) as cur:
            cur.execute(
                "SELECT id, email FROM users "
                "WHERE LOWER(email) = ANY(%s) AND email_verified = TRUE "
                "AND password_hash IS NOT NULL",
                ([e.lower() for e in emails],),
            )
            user_rows = {r["email"].lower(): r["id"] for r in cur.fetchall()}

        next_encoded = urllib.parse.quote(chart_destination)
        for e in emails:
            uid = user_rows.get(e.lower())
            if uid:
                tok1 = create_email_login_token(uid, e)
                tok2 = create_email_login_token(uid, e)
                login_urls[e]       = f"{APP_URL}/users/email-login?t={tok1}"
                chart_login_urls[e] = f"{APP_URL}/users/email-login?t={tok2}&next={next_encoded}"
            else:
                login_urls[e]       = fallback_login_url
                chart_login_urls[e] = fallback_chart_url
    except Exception as exc:
        logger.warning(f"Weekly outlook campaign {campaign_id}: login-link generation failed: {exc}")

    sent = 0; failed = 0; last_error = None
    batch_size = 500; max_attempts = 4
    _update_campaign(campaign_id, status="sending")

    for i in range(0, len(emails), batch_size):
        chunk = emails[i:i + batch_size]

        payload = {
            "sender": sender,
            "subject": subject,
            "htmlContent": full_html,
            "messageVersions": [
                {
                    "to": [{"email": e}],
                    "params": {
                        "login_url":       login_urls.get(e, fallback_login_url),
                        "chart_login_url": chart_login_urls.get(e, fallback_chart_url),
                    },
                }
                for e in chunk
            ],
        }

        chunk_ok = False
        for attempt in range(1, max_attempts + 1):
            try:
                resp = requests.post(
                    "https://api.brevo.com/v3/smtp/email",
                    headers={"api-key": brevo_api_key, "Content-Type": "application/json"},
                    json=payload,
                    timeout=60,
                )
                if resp.status_code in (200, 201, 202):
                    chunk_ok = True; break
                last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                if 400 <= resp.status_code < 500 and resp.status_code != 429:
                    break
            except Exception as exc:
                last_error = str(exc)
            if attempt < max_attempts:
                time.sleep(min(2 ** attempt, 30))

        if chunk_ok:
            sent += len(chunk)
        else:
            failed += len(chunk)
        _update_campaign(campaign_id, sent=sent, failed=failed)

    final_status = "completed" if failed == 0 else ("completed_with_errors" if sent > 0 else "failed")
    _update_campaign(campaign_id, status=final_status, sent=sent, failed=failed,
                     error=(last_error if failed else None))
    logger.info(f"Weekly outlook campaign {campaign_id} finished: {final_status}, sent={sent}, failed={failed}")


# ─────────────────────────────────────────────────────────────
#  API endpoints
# ─────────────────────────────────────────────────────────────

@router.post("/weekly-outlook/generate")
def weekly_outlook_generate(x_admin_token: Optional[str] = Header(None)):
    """Collect the last 6 days of data, call GPT-5.1, and return the rendered email HTML."""
    verify_admin_token(x_admin_token)
    try:
        data = _collect_week_data()
    except Exception as exc:
        logger.error(f"Weekly outlook data collection failed: {exc}")
        raise HTTPException(status_code=500, detail=f"Data collection failed: {exc}")

    ai = _call_gpt(data)

    start = date.fromisoformat(data["week_start"])
    end   = date.fromisoformat(data["week_end"])
    subject = f"This Week's Global Energy Risk Outlook — {_fmt_range(start, end)}"

    chart_choice = ai.get("chart_choice", "GERI_BRENT")
    chart_dest   = _chart_destination(chart_choice)

    # Build the HTML with Brevo per-recipient placeholders for both login URLs
    full_html = build_weekly_email_html(
        data, ai,
        login_url="{{params.login_url}}",
        chart_login_url="{{params.chart_login_url}}",
    )

    return {
        "success": True,
        "subject": subject,
        "html":    full_html,
        "week_label": data["week_label"],
        "chart_destination": chart_dest,
        "stats": {
            "geri":    data.get("geri_latest"),
            "brent":   data.get("brent_latest"),
            "ttf":     data.get("ttf_latest"),
            "events":  data.get("events_processed", 0),
        },
        "chart_choice": chart_choice,
    }


@router.post("/weekly-outlook/send-test")
def weekly_outlook_send_test(body: WeeklyOutlookSendRequest,
                             x_admin_token: Optional[str] = Header(None)):
    """Send the generated email to a single test address."""
    verify_admin_token(x_admin_token)

    subject  = (body.subject or "").strip()
    html_body = (body.html or "").strip()
    to_email  = (body.test_email or TEST_EMAIL).strip()

    if not subject or not html_body:
        raise HTTPException(status_code=400, detail="Subject and html are required")

    brevo_api_key = os.environ.get("BREVO_API_KEY")
    if not brevo_api_key:
        raise HTTPException(status_code=500, detail="BREVO_API_KEY not configured")

    # Build per-recipient login URLs (with and without dashboard redirect)
    chart_dest = (body.chart_destination or "").strip() or "/geri"
    fallback   = f"{APP_URL}/users/account"
    chart_fallback = f"{APP_URL}{chart_dest}"
    try:
        from src.api.user_routes import build_email_login_url, create_email_login_token
        from src.db.db import get_cursor as _gc
        base_url = build_email_login_url(to_email) or fallback
        # Build chart-login URL with ?next= redirect
        try:
            with _gc(commit=False) as cur:
                cur.execute(
                    "SELECT id FROM users WHERE LOWER(email)=LOWER(%s) AND email_verified=TRUE",
                    (to_email,)
                )
                u = cur.fetchone()
            if u:
                tok = create_email_login_token(u["id"], to_email)
                chart_url = (f"{APP_URL}/users/email-login?t={tok}"
                             f"&next={urllib.parse.quote(chart_dest)}")
            else:
                chart_url = chart_fallback
        except Exception:
            chart_url = chart_fallback
    except Exception:
        base_url  = fallback
        chart_url = chart_fallback

    final_html = (html_body
                  .replace("{{params.login_url}}", base_url)
                  .replace("{{params.chart_login_url}}", chart_url))

    try:
        resp = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={"api-key": brevo_api_key, "Content-Type": "application/json"},
            json={
                "sender": _email_sender(),
                "to": [{"email": to_email}],
                "subject": f"[TEST] {subject}",
                "htmlContent": final_html,
            },
            timeout=30,
        )
        if resp.status_code in (200, 201, 202):
            return {"success": True, "message": f"Test email sent to {to_email}"}
        error = f"Brevo error: {resp.status_code} — {resp.text[:200]}"
        raise HTTPException(status_code=500, detail=error)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/weekly-outlook/send-all")
def weekly_outlook_send_all(body: WeeklyOutlookSendAllRequest,
                            background_tasks: BackgroundTasks,
                            x_admin_token: Optional[str] = Header(None)):
    """Send the generated weekly email to all platform users."""
    verify_admin_token(x_admin_token)

    subject   = (body.subject or "").strip()
    html_body = (body.html or "").strip()

    if not subject or not html_body:
        raise HTTPException(status_code=400, detail="Subject and html are required")
    if not os.environ.get("BREVO_API_KEY"):
        raise HTTPException(status_code=500, detail="BREVO_API_KEY not configured")

    emails = _get_all_user_emails()
    if not emails:
        raise HTTPException(status_code=400, detail="No platform users found")

    try:
        with get_cursor() as cur:
            cur.execute(
                "INSERT INTO admin_bulk_email_campaigns (subject, content_type, total, status) "
                "VALUES (%s, %s, %s, 'sending') RETURNING id",
                (subject, "html", len(emails)),
            )
            campaign_id = cur.fetchone()["id"]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not create campaign: {exc}")

    chart_dest = (body.chart_destination or "/geri").strip()
    background_tasks.add_task(_run_weekly_send_all, campaign_id, subject, html_body, emails, chart_dest)
    return {"success": True, "campaign_id": campaign_id, "total": len(emails)}
