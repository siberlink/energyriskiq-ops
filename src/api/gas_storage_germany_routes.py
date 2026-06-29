"""
Germany Gas Storage Levels — Live Data & Risk Intelligence
Route: /gas-storage-levels-germany

SEO-optimized informational page showing live German gas storage data, trends,
winter readiness, Germany-vs-Europe comparison, a per-country comparison table,
LNG/TTF connections, European risk-index context, and a Custom Algorithms
storage interpretation for energy market professionals.

Design mirrors /gas-storage-levels-in-europe — it reuses the same CSS, loader,
SVG builders and helper utilities from gas_storage_routes / snapshot_routes.
All narrative interpretation is produced by deterministic Custom Algorithms
(no AI wording / no LLM call) so the page always renders.
"""
import json
import logging
import asyncio
import html as _html
from datetime import datetime, timezone, date as _date

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from src.db.db import execute_production_one, execute_production_query
from src.api.snapshot_routes import _LOADER_HTML, BAND_COLORS, _safe_float
from src.api.gas_storage_routes import (
    _GAS_STORAGE_CSS,
    _band_color,
    _sign,
    _arrow,
    _chg_color,
    _build_storage_trend_svg,
    _build_fill_meter_svg,
    BASE_URL,
)

router = APIRouter()
logger = logging.getLogger(__name__)


# ── Readiness / risk band colours ─────────────────────────────────────────────

_READINESS_COLORS = {
    "EXCELLENT": "#22c55e",
    "GOOD":      "#22c55e",
    "MODERATE":  "#3b82f6",
    "WATCH":     "#eab308",
    "LOW":       "#ef4444",
}

def _readiness_color(band: str) -> str:
    return _READINESS_COLORS.get((band or "").upper(), "#94a3b8")


# ── Deterministic Custom Algorithms ───────────────────────────────────────────

def _compute_winter_readiness(storage_pct: float, daily_inj_pp: float, days_to_nov1: int, is_injection: bool):
    """
    Deterministic winter-readiness score (0–100) using a Custom Algorithm.

    Injection season: project storage forward to Nov 1 at the recent daily
    injection pace and score it against the 90% EU mandate.
    Withdrawal season: score current adequacy against a 65% healthy-winter level.
    """
    if is_injection:
        projected = storage_pct + max(0.0, daily_inj_pp) * max(0, days_to_nov1)
        projected = min(projected, 100.0)
        score = int(round(max(0.0, min(100.0, projected / 90.0 * 100.0))))
    else:
        projected = storage_pct
        score = int(round(max(0.0, min(100.0, storage_pct / 65.0 * 100.0))))

    if score >= 90:
        band = "EXCELLENT"
    elif score >= 80:
        band = "GOOD"
    elif score >= 65:
        band = "MODERATE"
    elif score >= 50:
        band = "WATCH"
    else:
        band = "LOW"
    return score, band, projected


def _compute_storage_risk(readiness_score: int, egsi_band: str, eeri_band: str) -> str:
    """Composite Germany storage-risk signal from readiness + EGSI + EERI bands."""
    pts = 0
    if readiness_score >= 85:
        pts += 0
    elif readiness_score >= 70:
        pts += 1
    elif readiness_score >= 55:
        pts += 2
    else:
        pts += 3

    bmap = {"LOW": 0, "NORMAL": 0, "MODERATE": 1, "ELEVATED": 2, "HIGH": 3, "CRITICAL": 3}
    pts += bmap.get((egsi_band or "MODERATE").upper(), 1)
    pts += bmap.get((eeri_band or "ELEVATED").upper(), 2)

    if pts <= 2:
        return "LOW"
    if pts <= 4:
        return "MODERATE"
    if pts <= 6:
        return "ELEVATED"
    return "HIGH"


def _build_germany_analysis(
    de_pct, monthly_change, winter_score, winter_band, projected_nov1,
    eu_pct, diff_eu, eeri_val, eeri_band, egsi_val, egsi_band,
    geri_val, geri_band, ttf_latest, storage_risk, season_label, days_to_nov1,
) -> str:
    """Deterministic multi-paragraph Custom Algorithms interpretation."""
    chg_word = "rose" if monthly_change >= 0 else "fell"
    diff_word = "above" if diff_eu >= 0 else "below"
    bull_bear = (
        "a bullish structural backdrop for TTF gas prices"
        if storage_risk in ("ELEVATED", "HIGH")
        else "a broadly balanced-to-bearish backdrop for TTF gas prices"
    )

    p1 = (
        f"Germany's natural gas storage stands at {de_pct:.1f}% today, having {chg_word} "
        f"{abs(monthly_change):.1f} percentage points over the past month during the {season_label.lower()}. "
        f"As Europe's largest gas consumer, German inventories are a structural anchor for the wider "
        f"European supply picture and feed directly into TTF price formation. The current fill rate sits "
        f"{abs(diff_eu):.1f} percentage points {diff_word} the European aggregate of {eu_pct:.1f}%."
    )

    if season_label == "Injection Season":
        p2 = (
            f"At the recent injection pace, Germany is on a trajectory toward roughly {projected_nov1:.0f}% "
            f"by November 1 — the EU's 90% storage mandate. EnergyRiskIQ's Custom Algorithms translate this "
            f"into a Winter Readiness score of {winter_score}/100 ({winter_band}). With {days_to_nov1} days "
            f"left in the refill window, the decisive variables are LNG send-out from German regasification "
            f"terminals, Norwegian pipeline flows, and industrial demand response."
        )
    else:
        p2 = (
            f"Germany is in the {season_label.lower()}, drawing on stored gas to meet heating and power demand. "
            f"EnergyRiskIQ's Custom Algorithms score current adequacy at a Winter Readiness of "
            f"{winter_score}/100 ({winter_band}), based on how far the {de_pct:.1f}% fill rate sits above the "
            f"level typically required to clear the peak-demand season without stress."
        )

    p3 = (
        f"Broader European risk conditions remain a key overlay. The Europe Gas Stress Index (EGSI-M) reads "
        f"{egsi_val}/10 ({egsi_band}), the Europe Energy Risk Index (EERI) {eeri_val}/100 ({eeri_band}), and "
        f"the Global Energy Risk Index (GERI) {geri_val}/100 ({geri_band}). Combined with German storage, these "
        f"signals produce a composite Gas Storage Risk of {storage_risk} for Germany."
    )

    ttf_line = (
        f"with TTF trading near €{ttf_latest:.2f}/MWh, " if ttf_latest else ""
    )
    p4 = (
        f"For traders and risk managers, German storage is one of the cleanest reads on European supply security: "
        f"{ttf_line}the storage-versus-norm position implies {bull_bear}. Lower-than-expected German fill rates "
        f"raise winter-supply concern and support a TTF premium, while comfortable inventories ease it. "
        f"This interpretation is generated by deterministic Custom Algorithms and is for informational purposes "
        f"only — not financial advice."
    )

    return "\n\n".join([p1, p2, p3, p4])


# ── Loader HTML ───────────────────────────────────────────────────────────────

_GERMANY_LOADER = _LOADER_HTML.replace(
    "Global Energy Risk Snapshot | EnergyRiskIQ",
    "Germany Gas Storage Levels Today (%) | Live Data & Storage Trends",
).replace(
    'name="description" content="Live global energy risk snapshot. Current GERI, EERI and EGSI-M index values with Brent crude, TTF gas, VIX and LNG market prices."',
    'name="description" content="Track Germany gas storage levels today with live storage data, historical trends, seasonal comparisons, winter readiness signals, and European gas market analysis."',
).replace(
    'rel="canonical" href="https://energyriskiq.com/data/energy-risk-snapshot"',
    'rel="canonical" href="https://energyriskiq.com/gas-storage-levels-germany"',
).replace(
    '<link rel="icon" type="image/png" href="/static/favicon.png">',
    '<link rel="icon" type="image/png" href="/static/favicon.png">'
    '\n<meta property="og:title" content="Germany Gas Storage Levels Today">'
    '\n<meta property="og:description" content="Daily Germany gas storage data, trends, winter readiness, Germany-vs-Europe comparison, and gas market risk context from EnergyRiskIQ.">'
    '\n<meta property="og:url" content="https://energyriskiq.com/gas-storage-levels-germany">'
    '\n<meta property="og:type" content="website">'
    '\n<meta name="twitter:card" content="summary_large_image">'
    '\n<meta name="twitter:title" content="Germany Gas Storage Levels Today">'
    '\n<meta name="twitter:description" content="Daily Germany gas storage data, trends, winter readiness, and gas market risk context from EnergyRiskIQ.">',
).replace(
    "Fetching GERI\u00a0&\u00a0EERI indices\u2026",
    "Fetching Germany gas storage data\u2026",
).replace(
    '<span class="ld-tag">GERI</span>\n    <span class="ld-tag">EERI</span>\n    <span class="ld-tag">EGSI&#8209;M</span>\n    <span class="ld-tag">Brent</span>\n    <span class="ld-tag">TTF</span>',
    '<span class="ld-tag">AGSI+</span>\n    <span class="ld-tag">Germany</span>\n    <span class="ld-tag">EGSI&#8209;M</span>\n    <span class="ld-tag">TTF</span>',
)


# ── Country display order / names ─────────────────────────────────────────────

_COUNTRY_NAMES = {
    "DE": "Germany", "FR": "France", "IT": "Italy", "AT": "Austria",
    "PL": "Poland", "BE": "Belgium", "NL": "Netherlands", "CZ": "Czechia",
    "HU": "Hungary", "SK": "Slovakia", "ES": "Spain", "PT": "Portugal",
}


# ── Data Fetcher ──────────────────────────────────────────────────────────────

def _fetch_germany_data() -> dict:
    """Fetch all data needed for the Germany gas storage page from production DB."""

    # Germany latest
    de_row = execute_production_one(
        "SELECT date, storage_percent, gas_in_storage_twh, working_gas_volume_twh, "
        "injection_twh, withdrawal_twh, trend "
        "FROM gas_storage_country_snapshots "
        "WHERE country_code='DE' AND level='country' ORDER BY date DESC LIMIT 1"
    )

    # Germany history (ascending) — full available range
    de_history = execute_production_query(
        "SELECT date, storage_percent, gas_in_storage_twh, working_gas_volume_twh, trend "
        "FROM gas_storage_country_snapshots "
        "WHERE country_code='DE' AND level='country' ORDER BY date ASC"
    ) or []

    # EU aggregate latest (for Germany-vs-Europe + seasonal norm benchmark)
    eu_row = execute_production_one(
        "SELECT date, eu_storage_percent, seasonal_norm, deviation_from_norm, risk_band "
        "FROM gas_storage_snapshots ORDER BY date DESC LIMIT 1"
    )

    # EU aggregate history (date -> seasonal_norm) for the chart benchmark line
    eu_history = execute_production_query(
        "SELECT date, eu_storage_percent, seasonal_norm "
        "FROM gas_storage_snapshots ORDER BY date ASC"
    ) or []

    # Per-country latest snapshot (comparison table)
    country_rows = execute_production_query(
        "SELECT DISTINCT ON (country_code) country_code, country_name, date, "
        "storage_percent, gas_in_storage_twh, working_gas_volume_twh, trend "
        "FROM gas_storage_country_snapshots WHERE level='country' "
        "ORDER BY country_code, date DESC"
    ) or []

    # Risk indices
    egsi_row = execute_production_one(
        "SELECT index_date, index_value, band, trend_7d "
        "FROM egsi_m_daily WHERE region='Europe' ORDER BY index_date DESC LIMIT 1"
    )
    geri_row = execute_production_one(
        "SELECT date, value, band FROM intel_indices_daily "
        "WHERE index_id='global:geo_energy_risk' ORDER BY date DESC LIMIT 1"
    )
    eeri_row = execute_production_one(
        "SELECT date, value, band FROM reri_indices_daily "
        "WHERE index_id='europe:eeri' ORDER BY date DESC LIMIT 1"
    )

    # TTF latest 2 rows
    ttf_rows = execute_production_query(
        "SELECT date, ttf_price FROM ttf_gas_snapshots ORDER BY date DESC LIMIT 2"
    ) or []

    return {
        "de_row": de_row,
        "de_history": de_history,
        "eu_row": eu_row,
        "eu_history": eu_history,
        "country_rows": country_rows,
        "egsi_row": egsi_row,
        "geri_row": geri_row,
        "eeri_row": eeri_row,
        "ttf_rows": ttf_rows,
    }


# ── HTML Builder ──────────────────────────────────────────────────────────────

def _build_germany_html(data: dict, today_str: str) -> str:

    de_row     = data["de_row"] or {}
    de_history = data["de_history"]
    eu_row     = data["eu_row"] or {}
    eu_history = data["eu_history"]
    country_rows = data["country_rows"]
    egsi_row   = data["egsi_row"] or {}
    geri_row   = data["geri_row"] or {}
    eeri_row   = data["eeri_row"] or {}
    ttf_rows   = data["ttf_rows"]

    # ── Germany values ────────────────────────────────────────────────────────
    de_pct       = _safe_float(de_row.get("storage_percent", 0))
    de_in_twh    = _safe_float(de_row.get("gas_in_storage_twh", 0))
    de_cap_twh   = _safe_float(de_row.get("working_gas_volume_twh", 0))
    de_date      = de_row.get("date", "")
    last_updated_str = str(de_date) if de_date else "Updating…"

    # Monthly change (~30 calendar days back by row offset)
    monthly_change = 0.0
    if de_history and len(de_history) >= 2:
        latest = _safe_float(de_history[-1].get("storage_percent", de_pct))
        idx_30 = max(0, len(de_history) - 31)
        prior = _safe_float(de_history[idx_30].get("storage_percent", latest))
        monthly_change = latest - prior

    # Daily change
    daily_change = 0.0
    if de_history and len(de_history) >= 2:
        daily_change = (
            _safe_float(de_history[-1].get("storage_percent", 0))
            - _safe_float(de_history[-2].get("storage_percent", 0))
        )

    # Recent daily injection pace (pp/day) over last 7 rows
    daily_inj_pp = 0.0
    if de_history and len(de_history) >= 8:
        recent = _safe_float(de_history[-1].get("storage_percent", 0))
        prior7 = _safe_float(de_history[-8].get("storage_percent", 0))
        daily_inj_pp = (recent - prior7) / 7.0

    # ── EU aggregate / comparison ─────────────────────────────────────────────
    eu_pct   = _safe_float(eu_row.get("eu_storage_percent", 0))
    eu_norm  = _safe_float(eu_row.get("seasonal_norm", 0))
    diff_eu  = de_pct - eu_pct

    # ── Indices ───────────────────────────────────────────────────────────────
    egsi_val  = round(_safe_float(egsi_row.get("index_value", 0)), 2)
    egsi_band = (egsi_row.get("band") or "LOW").upper()
    egsi_trend = _safe_float(egsi_row.get("trend_7d", 0))
    egsi_date = egsi_row.get("index_date", "")

    geri_val  = int(round(_safe_float(geri_row.get("value", 0))))
    geri_band = (geri_row.get("band") or "MODERATE").upper()

    eeri_val  = int(round(_safe_float(eeri_row.get("value", 0))))
    eeri_band = (eeri_row.get("band") or "ELEVATED").upper()

    ttf_latest = _safe_float(ttf_rows[0]["ttf_price"]) if ttf_rows else 0.0
    ttf_prev   = _safe_float(ttf_rows[1]["ttf_price"]) if len(ttf_rows) > 1 else ttf_latest
    ttf_chg    = ttf_latest - ttf_prev

    egsi_color = _band_color(egsi_band)
    geri_color = BAND_COLORS.get(geri_band, "#f97316")
    eeri_color = BAND_COLORS.get(eeri_band, "#ef4444")

    # ── Season / target window ────────────────────────────────────────────────
    today = _date.today()
    is_injection = today.month in range(4, 11)  # Apr–Oct
    season_label = "Injection Season" if is_injection else "Withdrawal Season"
    days_to_nov1 = (_date(today.year if today.month < 11 else today.year + 1, 11, 1) - today).days
    gap_to_target_str = f"{max(0.0, 90.0 - de_pct):.1f}pp to reach 90%"

    # ── Winter readiness + storage risk (Custom Algorithms) ──────────────────
    winter_score, winter_band, projected_nov1 = _compute_winter_readiness(
        de_pct, daily_inj_pp, days_to_nov1, is_injection
    )
    winter_color = _readiness_color(winter_band)
    storage_risk = _compute_storage_risk(winter_score, egsi_band, eeri_band)
    storage_risk_color = _band_color(storage_risk)

    daily_chg_str = f"{_sign(daily_change)}{daily_change:.2f}pp"
    daily_chg_col = _chg_color(daily_change)
    monthly_chg_str = f"{_sign(monthly_change)}{monthly_change:.1f}pp"
    monthly_chg_col = _chg_color(monthly_change)

    # ── Trend chart (DE fill rate vs EU seasonal norm benchmark) ──────────────
    eu_norm_by_date = {}
    for r in eu_history:
        eu_norm_by_date[str(r.get("date"))] = _safe_float(r.get("seasonal_norm", 0))
    last_norm = eu_norm or de_pct
    chart_rows = []
    for r in de_history:
        d = r.get("date")
        nrm = eu_norm_by_date.get(str(d))
        if nrm is None or nrm == 0:
            nrm = last_norm
        else:
            last_norm = nrm
        chart_rows.append({
            "date": d,
            "eu_storage_percent": _safe_float(r.get("storage_percent", 0)),
            "seasonal_norm": nrm,
            "risk_band": "",
        })
    trend_svg = _build_storage_trend_svg(chart_rows, width=680, height=200)
    meter_svg = _build_fill_meter_svg(de_pct, eu_norm if eu_norm else de_pct)

    # ── Country comparison table ──────────────────────────────────────────────
    countries = []
    for r in country_rows:
        cc = r.get("country_code")
        countries.append({
            "code": cc,
            "name": r.get("country_name") or _COUNTRY_NAMES.get(cc, cc),
            "pct": _safe_float(r.get("storage_percent", 0)),
            "in_twh": _safe_float(r.get("gas_in_storage_twh", 0)),
            "trend": _safe_float(r.get("trend", 0)),
        })
    countries.sort(key=lambda c: c["pct"], reverse=True)
    country_table_html = ""
    for c in countries:
        is_de = c["code"] == "DE"
        row_style = "background:rgba(212,160,23,0.08);" if is_de else ""
        safe_name = _html.escape(str(c["name"]))
        name_cell = (
            f'<strong style="color:#d4a017">{safe_name} &#127465;&#127466;</strong>'
            if is_de else safe_name
        )
        tr_col = _chg_color(c["trend"])
        country_table_html += f"""<tr style="{row_style}">
          <td>{name_cell}</td>
          <td style="font-variant-numeric:tabular-nums;font-weight:700;color:{_band_color('LOW') if c['pct']>=50 else '#eab308' if c['pct']>=30 else '#ef4444'}">{c['pct']:.1f}%</td>
          <td style="font-variant-numeric:tabular-nums;color:#94a3b8">{c['in_twh']:.1f} TWh</td>
          <td style="color:{tr_col}">{_arrow(c['trend'])} {c['trend']:+.2f}</td>
        </tr>"""

    # ── Custom Algorithms analysis paragraphs ─────────────────────────────────
    analysis = _build_germany_analysis(
        de_pct, monthly_change, winter_score, winter_band, projected_nov1,
        eu_pct, diff_eu, eeri_val, eeri_band, egsi_val, egsi_band,
        geri_val, geri_band, ttf_latest, storage_risk, season_label, days_to_nov1,
    )
    paras = [p.strip() for p in analysis.split("\n\n") if p.strip()]
    interp_html = "".join(f'<p class="gs-interp-para">{_html.escape(p)}</p>' for p in paras)

    # ── JSON-LD ───────────────────────────────────────────────────────────────
    today_iso = str(today)
    faq_entries = [
        {
            "q": "What are Germany gas storage levels today?",
            "a": f"Germany's natural gas storage is currently at {de_pct:.1f}% of working capacity, "
                 f"based on the latest AGSI+ data for {last_updated_str}. This page updates daily.",
        },
        {
            "q": "Why is Germany gas storage important?",
            "a": "Germany is Europe's largest natural gas consumer, so the level of German storage is a key "
                 "indicator of European supply security and a structural driver of TTF gas prices.",
        },
        {
            "q": "How does Germany storage affect TTF gas prices?",
            "a": "Lower-than-expected German storage raises concern about winter supply and tends to support "
                 "higher TTF gas prices, while comfortable storage levels ease that pressure.",
        },
        {
            "q": "What is considered a safe gas storage level?",
            "a": "The EU mandate targets 90% storage by November 1. Levels comfortably on track toward that "
                 "target during the injection season are generally considered healthy for winter readiness.",
        },
        {
            "q": "How often is Germany storage data updated?",
            "a": "This page is updated daily following the AGSI+ (Gas Infrastructure Europe) publication window.",
        },
        {
            "q": "How does Germany compare to Europe?",
            "a": f"Germany's storage is currently {abs(diff_eu):.1f} percentage points "
                 f"{'above' if diff_eu>=0 else 'below'} the European aggregate of {eu_pct:.1f}%.",
        },
    ]
    json_ld = json.dumps({
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "WebPage",
                "name": "Germany Gas Storage Levels Today",
                "headline": "Germany Gas Storage Levels Today",
                "description": (
                    "Track Germany gas storage levels today with live storage data, historical trends, "
                    "winter readiness signals, Germany-vs-Europe comparison, and European gas market analysis."
                ),
                "url": f"{BASE_URL}/gas-storage-levels-germany",
                "dateModified": today_iso,
                "datePublished": "2026-01-15",
                "publisher": {
                    "@type": "Organization",
                    "name": "EnergyRiskIQ",
                    "url": BASE_URL,
                    "logo": {"@type": "ImageObject", "url": f"{BASE_URL}/static/logo.png"},
                },
                "mainEntityOfPage": {"@type": "WebPage", "@id": f"{BASE_URL}/gas-storage-levels-germany"},
                "about": [
                    {"@type": "Thing", "name": "Germany gas storage levels"},
                    {"@type": "Thing", "name": "German gas reserves"},
                    {"@type": "Thing", "name": "natural gas storage"},
                    {"@type": "Thing", "name": "TTF gas price"},
                    {"@type": "Thing", "name": "Germany energy security"},
                    {"@type": "Thing", "name": "winter energy risk"},
                ],
            },
            {
                "@type": "Dataset",
                "name": "Germany Gas Storage Levels Dataset",
                "description": "Daily German gas storage level data and risk context used to monitor storage "
                               "progress, seasonal supply security, winter readiness, and European gas-market stress.",
                "url": f"{BASE_URL}/gas-storage-levels-germany",
                "creator":   {"@type": "Organization", "name": "EnergyRiskIQ", "url": BASE_URL},
                "publisher": {"@type": "Organization", "name": "EnergyRiskIQ", "url": BASE_URL},
                "license": f"{BASE_URL}/data-license",
                "isAccessibleForFree": True,
                "dateModified": today_iso,
                "distribution": {
                    "@type": "DataDownload",
                    "contentUrl": f"{BASE_URL}/gas-storage-levels-germany",
                    "encodingFormat": "text/html",
                },
                "temporalCoverage": "2026-01-15/..",
                "spatialCoverage": "Germany",
                "variableMeasured": [
                    {"@type": "PropertyValue", "name": "Germany gas storage fill rate", "unitText": "percent"},
                    {"@type": "PropertyValue", "name": "Gas in storage", "unitText": "TWh"},
                    {"@type": "PropertyValue", "name": "Winter readiness score", "unitText": "0-100 index"},
                    {"@type": "PropertyValue", "name": "Monthly change", "unitText": "percentage points"},
                ],
                "measurementTechnique": "Daily aggregation of AGSI+ GIE German storage data combined with "
                                        "EnergyRiskIQ Custom Algorithms for winter-readiness and risk scoring.",
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Home", "item": BASE_URL},
                    {"@type": "ListItem", "position": 2, "name": "Data", "item": f"{BASE_URL}/data"},
                    {"@type": "ListItem", "position": 3, "name": "Germany Gas Storage Levels",
                     "item": f"{BASE_URL}/gas-storage-levels-germany"},
                ],
            },
            {
                "@type": "FAQPage",
                "mainEntity": [
                    {"@type": "Question", "name": e["q"],
                     "acceptedAnswer": {"@type": "Answer", "text": e["a"]}}
                    for e in faq_entries
                ],
            },
        ],
    }, indent=2)

    # Pre-computed strings (avoid backslash/quote nesting in f-string)
    de_fill_class = 'gold' if de_pct >= 50 else 'amber' if de_pct >= 30 else 'red'
    diff_color = "#22c55e" if diff_eu >= 0 else "#ef4444"
    diff_word = "above" if diff_eu >= 0 else "below"
    ttf_bias = "support higher" if storage_risk in ("ELEVATED", "HIGH") else "ease pressure on"

    # ── Page HTML ─────────────────────────────────────────────────────────────
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
      <a href="/gas-storage-levels-in-europe" style="font-size:13px;color:#94a3b8;text-decoration:none;">EU Storage</a>
      <a href="/users" class="cta-btn-nav">Unlock Deeper Intelligence</a>
    </div>
  </div>
</nav>

<!-- HERO -->
<header class="hero">
  <div class="hero-date">&#127465;&#127466; {today_str} &nbsp;&bull;&nbsp; Source: AGSI+ / GIE &nbsp;&bull;&nbsp; Updated Daily</div>
  <h1 style="max-width:820px;margin:0 auto 1rem;">
    Germany Gas Storage Levels Today
  </h1>
  <h2 style="font-size:1.05rem;font-weight:400;color:#94a3b8;line-height:1.7;
             max-width:680px;margin:0 auto 1.5rem;">
    Track Germany&rsquo;s natural gas storage levels, historical trends, winter readiness,
    and market impact on European gas prices &mdash; updated daily by EnergyRiskIQ.
  </h2>
  <div style="display:flex;justify-content:center;gap:0.75rem;flex-wrap:wrap;margin-top:1.2rem;">
    <span style="font-size:12px;font-weight:600;color:#22c55e;
      border:1px solid #22c55e33;border-radius:20px;padding:4px 14px;background:rgba(34,197,94,0.06);">
      &#128200; Updated daily
    </span>
    <span style="font-size:12px;font-weight:600;color:#3b82f6;
      border:1px solid #3b82f633;border-radius:20px;padding:4px 14px;background:rgba(59,130,246,0.06);">
      &#127465;&#127466; German gas storage tracker
    </span>
    <span style="font-size:12px;font-weight:600;color:#d4a017;
      border:1px solid #d4a01733;border-radius:20px;padding:4px 14px;background:rgba(212,160,23,0.06);">
      &#10052;&#65039; Winter readiness
    </span>
  </div>
</header>

<main class="page-body">

<!-- ── 1. PRIMARY STORAGE CARD ─────────────────────────────────────────────── -->
<div class="gs-snapshot-card">
  <div class="gs-snapshot-title">&#9646; Germany Storage &mdash; {today_str}</div>
  <div style="display:flex;align-items:flex-end;gap:16px;flex-wrap:wrap;margin-bottom:18px;">
    <div style="font-size:54px;font-weight:800;line-height:1;color:{storage_risk_color};font-variant-numeric:tabular-nums;">
      {de_pct:.1f}<span style="font-size:24px;color:#64748b;">%</span>
    </div>
    <div style="font-size:12px;color:#64748b;padding-bottom:8px;">
      Working capacity: {de_cap_twh:,.0f} TWh<br>Gas in storage: {de_in_twh:,.1f} TWh
    </div>
  </div>
  <div class="gs-snapshot-grid" style="grid-template-columns:repeat(3,1fr);">
    <div class="gs-snap-item">
      <div class="gs-snap-label">Monthly Change</div>
      <div class="gs-snap-value" style="color:{monthly_chg_col}">{monthly_chg_str}</div>
      <div class="gs-snap-sub">vs ~30 days ago</div>
    </div>
    <div class="gs-snap-item">
      <div class="gs-snap-label">Europe 5-Yr Norm</div>
      <div class="gs-snap-value" style="color:#3b82f6">{eu_norm:.1f}<span style="font-size:14px;color:#64748b;">%</span></div>
      <div class="gs-snap-sub">EU seasonal benchmark</div>
    </div>
    <div class="gs-snap-item">
      <div class="gs-snap-label">Winter Readiness</div>
      <div class="gs-snap-value" style="color:{winter_color}">{winter_band}</div>
      <div class="gs-snap-sub">{winter_score}/100 &bull; Custom Algorithms</div>
    </div>
  </div>
  <div class="gs-snapshot-footer">
    Data: AGSI+ / Gas Infrastructure Europe (GIE) &bull;
    Winter readiness &amp; risk: EnergyRiskIQ Custom Algorithms &bull;
    <a href="/data-license" style="color:#475569;">Data License</a>
  </div>
  <div style="margin-top:16px;">
    <a href="/users" class="gs-cta-btn-gold">&#128276; Get Free Energy Risk Alerts</a>
  </div>
</div>

<!-- ── FREE WIDGET PROMO BANNER (same as Europe page) ──────────────────────── -->
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

<!-- ── 2. MAIN GERMANY STORAGE CHART ───────────────────────────────────────── -->
<div class="gs-chart-wrap">
  <div class="gs-chart-title">&#128200; Germany Gas Storage Trend</div>
  <div style="overflow-x:auto;">{trend_svg}</div>
  <div style="margin-top:14px;font-size:11px;color:#334155;line-height:1.6;">
    Chart shows the daily German gas storage fill rate (gold line) since data launch, with the European
    5-year seasonal norm (dashed blue) as a benchmark. Data sourced from AGSI+ (Gas Infrastructure Europe)
    via EnergyRiskIQ&rsquo;s daily ingestion pipeline.
  </div>
</div>

<!-- ── 3. WINTER READINESS ─────────────────────────────────────────────────── -->
<div class="section-label" style="margin-bottom:20px;">&#10052;&#65039; Germany Winter Readiness</div>
<div class="gs-wtm-section">
  <div style="display:flex;align-items:center;gap:24px;flex-wrap:wrap;margin-bottom:18px;">
    <div>
      <div class="gs-snap-label">Winter Readiness Score</div>
      <div style="font-size:44px;font-weight:800;line-height:1;color:{winter_color};">
        {winter_score} <span style="font-size:18px;color:#64748b;">/ 100</span>
      </div>
      <div style="font-size:13px;font-weight:700;color:{winter_color};margin-top:4px;">{winter_band}</div>
    </div>
    <div style="flex:1 1 320px;min-width:280px;">
      <div style="margin-bottom:8px;">{meter_svg}</div>
    </div>
  </div>
  <div class="gs-wtm-grid">
    <div class="gs-wtm-point">
      <h3>&#10067; What does this mean?</h3>
      <p>
        The Winter Readiness score is computed by EnergyRiskIQ&rsquo;s Custom Algorithms. During the injection
        season it projects German storage forward to November 1 at the recent fill pace and scores it against
        the EU&rsquo;s 90% mandate. At current pace, Germany is on track toward roughly
        <strong style="color:{winter_color}">{projected_nov1:.0f}%</strong> by November 1.
      </p>
    </div>
    <div class="gs-wtm-point">
      <h3>&#128200; How does it compare?</h3>
      <p>
        A score of <strong style="color:{winter_color}">{winter_score}/100 ({winter_band})</strong> indicates
        Germany&rsquo;s storage trajectory is {'comfortably on track' if winter_score>=80 else 'broadly on track' if winter_score>=65 else 'lagging the path'}
        for winter supply security. Storage currently sits {abs(diff_eu):.1f}pp {diff_word} the European
        aggregate, with {days_to_nov1} days left in the refill window.
      </p>
    </div>
  </div>
</div>

<!-- ── 4. GERMANY VS EUROPE COMPARISON ─────────────────────────────────────── -->
<div class="section-label" style="margin-bottom:20px;">&#9878;&#65039; Germany vs Europe Storage Levels</div>
<div class="gs-three-col">
  <div class="gs-metric-card blue">
    <div class="gs-metric-label">Germany &#127465;&#127466;</div>
    <div class="gs-metric-value" style="color:{storage_risk_color}">{de_pct:.1f}<span style="font-size:18px;font-weight:500;color:#64748b;">%</span></div>
    <div class="gs-metric-sub">German national fill rate</div>
  </div>
  <div class="gs-metric-card gold">
    <div class="gs-metric-label">Europe &#127466;&#127482;</div>
    <div class="gs-metric-value" style="color:#3b82f6">{eu_pct:.1f}<span style="font-size:18px;font-weight:500;color:#64748b;">%</span></div>
    <div class="gs-metric-sub">EU aggregate fill rate</div>
  </div>
  <div class="gs-metric-card {'green' if diff_eu>=0 else 'red'}">
    <div class="gs-metric-label">Difference</div>
    <div class="gs-metric-value" style="color:{diff_color}">{diff_eu:+.1f}<span style="font-size:18px;font-weight:500;color:#64748b;">pp</span></div>
    <div class="gs-metric-sub">Germany {diff_word} EU aggregate</div>
  </div>
</div>
<div style="margin:-20px 0 40px;">
  <a href="/gas-storage-levels-in-europe" style="font-size:13px;font-weight:600;color:var(--gold);text-decoration:none;">
    &#8594; Europe Gas Storage Levels &rarr;
  </a>
</div>

<!-- ── 5. STORAGE RISK SIGNAL ──────────────────────────────────────────────── -->
<div class="section-label" style="margin-bottom:20px;">&#128680; Gas Storage Risk Signal</div>
<div class="gs-deviation-bar" style="display:flex;align-items:center;gap:24px;flex-wrap:wrap;">
  <div>
    <div class="gs-snap-label">Storage Risk</div>
    <div style="font-size:34px;font-weight:800;line-height:1;color:{storage_risk_color};">{storage_risk}</div>
  </div>
  <div style="flex:1 1 320px;min-width:260px;font-size:13px;color:#94a3b8;line-height:1.7;">
    Germany&rsquo;s Gas Storage Risk signal is generated by EnergyRiskIQ&rsquo;s Custom Algorithms, combining
    <strong style="color:#e2e8f0">German storage</strong> (winter readiness {winter_score}/100),
    the <a href="/indices/europe-energy-risk-index" style="color:#3b82f6;">EERI</a>
    (<span style="color:{eeri_color}">{eeri_val}/100 {eeri_band}</span>), and the
    <a href="/indices/europe-gas-stress-index" style="color:#3b82f6;">EGSI-M</a>
    (<span style="color:{egsi_color}">{egsi_val}/10 {egsi_band}</span>) into a single forward-looking risk read.
  </div>
</div>

<!-- ── 6. WHY GERMANY GAS STORAGE LEVELS MATTER ────────────────────────────── -->
<div class="section-label" style="margin-bottom:20px;">&#128257; Why Germany Gas Storage Levels Matter</div>
<div class="gs-three-col">
  <div class="gs-implication-card">
    <div class="gs-implication-icon">&#127981;</div>
    <div class="gs-implication-title">Europe&rsquo;s Largest Gas Consumer</div>
    <div class="gs-implication-body">
      Germany is the single largest natural gas consumer in Europe. Its storage trajectory therefore
      carries outsized weight in the continental supply balance &mdash; German injection and withdrawal
      swings move the European aggregate more than any other member state.
    </div>
  </div>
  <div class="gs-implication-card">
    <div class="gs-implication-icon">&#9883;&#65039;</div>
    <div class="gs-implication-title">German Storage Drives TTF</div>
    <div class="gs-implication-body">
      Because Germany sits at the heart of the European gas grid, German storage levels feed directly into
      <a href="/data/ttf-gas-price-today" style="color:#3b82f6;">TTF gas price</a> formation and the
      <a href="/data/natural-gas-price-today-europe" style="color:#3b82f6;">European natural gas benchmark</a>.
      Below-norm storage supports a winter-supply premium.
    </div>
  </div>
  <div class="gs-implication-card">
    <div class="gs-implication-icon">&#128737;&#65039;</div>
    <div class="gs-implication-title">Storage &amp; Energy Security</div>
    <div class="gs-implication-body">
      German storage influences LNG import demand and overall energy security. Comfortable inventories
      reduce reliance on spot LNG cargoes, while a deficit increases competition for global
      <a href="/data/jkm-lng-spot-price" style="color:#3b82f6;">LNG</a> supply and lifts winter risk.
    </div>
  </div>
</div>

<!-- ── 7. TODAY'S GERMANY STORAGE ANALYSIS (Custom Algorithms) ─────────────── -->
<div class="section-label" style="margin-bottom:20px;">&#129518; Today&rsquo;s Germany Storage Analysis</div>
<div class="gs-ai-box">
  <div class="gs-ai-label">EnergyRiskIQ Custom Algorithms &bull; {today_str}</div>
  {interp_html}
  <div style="margin-top:20px;padding-top:16px;border-top:1px solid rgba(255,255,255,0.05);
              font-size:10px;color:#334155;line-height:1.5;">
    This interpretation is generated by EnergyRiskIQ&rsquo;s deterministic Custom Algorithms using live AGSI+
    German storage data, EU aggregate context, EGSI-M / EERI / GERI readings, and TTF price context.
    For informational purposes only &mdash; not financial or trading advice.
    &bull; Storage data: AGSI+ / Gas Infrastructure Europe
    &bull; TTF: Yahoo Finance
    &bull; Risk indices: EnergyRiskIQ Custom Algorithms
  </div>
</div>

<!-- ── 8. EUROPEAN GAS STORAGE LEVELS BY COUNTRY ───────────────────────────── -->
<div class="section-label" style="margin-bottom:20px;">&#127757; European Gas Storage Levels by Country</div>
<div class="gs-method-box" style="margin-bottom:44px;">
  <p style="font-size:13px;color:#94a3b8;line-height:1.7;margin:0 0 14px;">
    Latest per-country gas storage fill rates across the major European storage holders, sorted highest to
    lowest. Germany is highlighted. Data from AGSI+ / Gas Infrastructure Europe, updated daily.
  </p>
  <table class="gs-risk-season-table">
    <thead>
      <tr>
        <th>Country</th>
        <th>Storage %</th>
        <th>Gas in Storage</th>
        <th>Daily Trend</th>
      </tr>
    </thead>
    <tbody>
      {country_table_html}
    </tbody>
  </table>
  <div style="margin-top:14px;font-size:11px;color:#334155;">
    Europe aggregate: <strong style="color:#3b82f6">{eu_pct:.1f}%</strong> &bull;
    Germany: <strong style="color:{storage_risk_color}">{de_pct:.1f}%</strong> &bull;
    as of {last_updated_str}
  </div>
</div>

<!-- ── 9. LNG CONNECTION ───────────────────────────────────────────────────── -->
<div class="section-label" style="margin-bottom:20px;">&#128674; How LNG Impacts Germany Storage</div>
<div style="background:var(--card);border:1px solid var(--border);border-radius:16px;
            padding:26px 28px;margin-bottom:24px;">
  <p style="font-size:14px;color:#cbd5e1;line-height:1.8;margin:0 0 14px;">
    Since 2022, Germany has rapidly built out floating LNG import (regasification) terminals to replace lost
    pipeline supply. <strong>LNG imports</strong> are now a primary swing source for refilling German storage:
    cargoes are regasified at coastal terminals and injected into the grid, directly supporting fill rates.
  </p>
  <p style="font-size:14px;color:#cbd5e1;line-height:1.8;margin:0 0 14px;">
    When global LNG is plentiful and cheap, German <strong>regasification</strong> send-out rises and storage
    refills faster. When Asian demand tightens the market &mdash; visible in the
    <a href="/data/jkm-lng-spot-price" style="color:#3b82f6;">JKM LNG spot price</a> &mdash; Europe competes
    harder for cargoes and German injection can slow, raising <strong>supply security</strong> risk.
  </p>
  <div style="margin-top:8px;padding-top:14px;border-top:1px solid rgba(255,255,255,0.05);font-size:12px;">
    <a href="/data/europe-lng-supply-demand" style="color:var(--gold);text-decoration:none;font-weight:600;">&#8594; Europe LNG Supply &amp; Demand</a>
    &nbsp;&nbsp;
    <a href="/data/jkm-lng-spot-price" style="color:#94a3b8;text-decoration:none;font-weight:600;">&#8594; JKM LNG Spot Price</a>
    &nbsp;&nbsp;
    <a href="/research/what-drives-lng-prices" style="color:#94a3b8;text-decoration:none;font-weight:600;">&#8594; What Drives LNG Prices</a>
  </div>
</div>

<!-- ── 10. TTF CONNECTION ──────────────────────────────────────────────────── -->
<div class="section-label" style="margin-bottom:20px;">&#9883;&#65039; Germany Storage and TTF Gas Prices</div>
<div style="background:var(--card);border:1px solid var(--border);border-radius:16px;
            padding:26px 28px;margin-bottom:44px;">
  <p style="font-size:14px;color:#cbd5e1;line-height:1.8;margin:0 0 14px;">
    German storage and the Dutch <strong>TTF benchmark</strong> are tightly linked. As Europe&rsquo;s largest
    consumer, German inventory conditions are a leading structural input to TTF price formation:
  </p>
  <ul style="font-size:13px;color:#94a3b8;line-height:1.9;padding-left:18px;margin:0 0 14px;">
    <li><strong style="color:#ef4444">Low storage &rarr; bullish TTF:</strong> below-norm German fill raises winter-supply concern and supports higher prices.</li>
    <li><strong style="color:#22c55e">High storage &rarr; bearish TTF:</strong> comfortable inventories ease supply concern and weigh on prices.</li>
  </ul>
  <p style="font-size:13px;color:#94a3b8;line-height:1.7;margin:0 0 14px;">
    With Germany&rsquo;s current Gas Storage Risk reading <strong style="color:{storage_risk_color}">{storage_risk}</strong>,
    the storage position is likely to {ttf_bias} TTF gas prices, all else equal.
  </p>
  <div style="padding-top:14px;border-top:1px solid rgba(255,255,255,0.05);font-size:12px;">
    <a href="/data/ttf-gas-price-today" style="color:var(--gold);text-decoration:none;font-weight:600;">&#8594; TTF Gas Price Today</a>
    &nbsp;&nbsp;
    <a href="/data/natural-gas-price-today-europe" style="color:#94a3b8;text-decoration:none;font-weight:600;">&#8594; Natural Gas Price Today (Europe)</a>
  </div>
</div>

<!-- ── 11. EUROPEAN ENERGY RISK CONTEXT ────────────────────────────────────── -->
<div class="section-label" style="margin-bottom:20px;">&#128202; European Energy Risk Context</div>
<div class="gs-related-grid">
  <a href="/indices/europe-energy-risk-index" class="gs-related-card">
    <div class="gs-related-card-tag">Risk Index</div>
    <div class="gs-related-card-title">Europe Energy Risk Index</div>
    <div class="gs-related-card-desc">EERI &bull; <span style="color:{eeri_color}">{eeri_val}/100 &bull; {eeri_band}</span></div>
  </a>
  <a href="/indices/europe-gas-stress-index" class="gs-related-card">
    <div class="gs-related-card-tag">Gas Risk Index</div>
    <div class="gs-related-card-title">Europe Gas Stress Index</div>
    <div class="gs-related-card-desc">EGSI-M &bull; <span style="color:{egsi_color}">{egsi_val}/10 &bull; {egsi_band}</span></div>
  </a>
  <a href="/indices/global-energy-risk-index" class="gs-related-card">
    <div class="gs-related-card-tag">Risk Index</div>
    <div class="gs-related-card-title">Global Energy Risk Index</div>
    <div class="gs-related-card-desc">GERI &bull; <span style="color:{geri_color}">{geri_val}/100 &bull; {geri_band}</span></div>
  </a>
</div>

<!-- ── 12. FREE ALERTS ─────────────────────────────────────────────────────── -->
<div class="gs-cta-mid">
  <h2>Stay Ahead of Gas Market Risk</h2>
  <p>
    Create a free EnergyRiskIQ account to receive daily updates on Germany storage, Europe storage,
    TTF gas prices, LNG flows, and European energy risk signals &mdash; all in one place.
  </p>
  <a href="/users" class="gs-cta-btn-primary">Create Free Account</a>
</div>

<!-- ── 13 mirrors the widget banner above (Europe Gas Storage Widget) ──────── -->

<!-- ── RELATED DATA & INDICES (internal link hub) ─────────────────────────── -->
<div class="section-label" style="margin-bottom:20px;">&#128279; Related EnergyRiskIQ Data and Risk Indices</div>
<div class="gs-related-grid">
  <a href="/gas-storage-levels-in-europe" class="gs-related-card">
    <div class="gs-related-card-tag">Storage Data</div>
    <div class="gs-related-card-title">Europe Gas Storage Levels</div>
    <div class="gs-related-card-desc">EU aggregate &bull; daily &bull; winter risk</div>
  </a>
  <a href="/data/ttf-gas-price-today" class="gs-related-card">
    <div class="gs-related-card-tag">Price Data</div>
    <div class="gs-related-card-title">TTF Gas Price Today</div>
    <div class="gs-related-card-desc">Dutch TTF benchmark &bull; daily &bull; charts</div>
  </a>
  <a href="/data/natural-gas-price-today-europe" class="gs-related-card">
    <div class="gs-related-card-tag">Price Data</div>
    <div class="gs-related-card-title">Natural Gas Price Today (Europe)</div>
    <div class="gs-related-card-desc">European TTF benchmark &bull; drivers &bull; charts</div>
  </a>
  <a href="/data/europe-lng-supply-demand" class="gs-related-card">
    <div class="gs-related-card-tag">LNG Intelligence</div>
    <div class="gs-related-card-title">Europe LNG Supply &amp; Demand</div>
    <div class="gs-related-card-desc">Daily LNG flows &bull; terminal data &bull; risk</div>
  </a>
  <a href="/data/jkm-lng-spot-price" class="gs-related-card">
    <div class="gs-related-card-tag">LNG Price Data</div>
    <div class="gs-related-card-title">JKM LNG Spot Price</div>
    <div class="gs-related-card-desc">Asia LNG benchmark &bull; daily updates</div>
  </a>
  <a href="/data/global-energy-risk-forecast" class="gs-related-card">
    <div class="gs-related-card-tag">Forecast</div>
    <div class="gs-related-card-title">Global Energy Risk Forecast</div>
    <div class="gs-related-card-desc">24-hour Brent &amp; TTF outlook &bull; risk signals</div>
  </a>
</div>

<!-- ── 14. FAQ ─────────────────────────────────────────────────────────────── -->
<div class="section-label" style="margin-bottom:20px;">&#10067; Germany Gas Storage Levels FAQ</div>
<div class="gs-faq-section">

  <div class="gs-faq-item" onclick="this.classList.toggle('open')">
    <div class="gs-faq-q">
      <span>What are Germany gas storage levels today?</span>
      <span class="gs-faq-toggle">+</span>
    </div>
    <div class="gs-faq-a">
      Germany&rsquo;s natural gas storage is currently at {de_pct:.1f}% of working capacity, based on the latest
      AGSI+ data for {last_updated_str}. This page is updated daily.
    </div>
  </div>

  <div class="gs-faq-item" onclick="this.classList.toggle('open')">
    <div class="gs-faq-q">
      <span>Why is Germany gas storage important?</span>
      <span class="gs-faq-toggle">+</span>
    </div>
    <div class="gs-faq-a">
      Germany is Europe&rsquo;s largest natural gas consumer, so the level of German storage is a key indicator
      of European supply security and a structural driver of TTF gas prices.
    </div>
  </div>

  <div class="gs-faq-item" onclick="this.classList.toggle('open')">
    <div class="gs-faq-q">
      <span>How does Germany storage affect TTF gas prices?</span>
      <span class="gs-faq-toggle">+</span>
    </div>
    <div class="gs-faq-a">
      Lower-than-expected German storage raises concern about winter supply and tends to support higher TTF gas
      prices, while comfortable storage levels ease that pressure.
      <a href="/data/ttf-gas-price-today" style="color:#3b82f6;margin-left:4px;">View TTF &rarr;</a>
    </div>
  </div>

  <div class="gs-faq-item" onclick="this.classList.toggle('open')">
    <div class="gs-faq-q">
      <span>What is considered a safe gas storage level?</span>
      <span class="gs-faq-toggle">+</span>
    </div>
    <div class="gs-faq-a">
      The EU mandate targets 90% storage by November 1. Levels comfortably on track toward that target during
      the injection season are generally considered healthy for winter readiness.
    </div>
  </div>

  <div class="gs-faq-item" onclick="this.classList.toggle('open')">
    <div class="gs-faq-q">
      <span>How often is Germany storage updated?</span>
      <span class="gs-faq-toggle">+</span>
    </div>
    <div class="gs-faq-a">
      This page is updated daily following the AGSI+ (Gas Infrastructure Europe) publication window.
    </div>
  </div>

  <div class="gs-faq-item" onclick="this.classList.toggle('open')">
    <div class="gs-faq-q">
      <span>How does Germany compare to Europe?</span>
      <span class="gs-faq-toggle">+</span>
    </div>
    <div class="gs-faq-a">
      Germany&rsquo;s storage is currently {abs(diff_eu):.1f} percentage points {diff_word} the European
      aggregate of {eu_pct:.1f}%.
      <a href="/gas-storage-levels-in-europe" style="color:#3b82f6;margin-left:4px;">Europe storage &rarr;</a>
    </div>
  </div>

</div>

<!-- ── BOTTOM CTA ──────────────────────────────────────────────────────────── -->
<div class="gs-cta-bottom">
  <h2>Turn Germany Gas Storage Data Into Market Risk Intelligence</h2>
  <p>
    EnergyRiskIQ connects German and European storage levels, LNG flows, TTF gas prices, and European risk
    indices to help you understand changing energy-market conditions.
  </p>
  <a href="/gas-storage-levels-in-europe" class="gs-cta-btn-gold">View Europe Gas Storage Levels</a>
</div>

<!-- ── CITATION BLOCK ──────────────────────────────────────────────────────── -->
<div class="section-label" style="margin-bottom:20px;">&#128196; Citation &amp; Reference</div>
<div class="snap-cite-card" style="margin-bottom:44px;">
  <h3>How to Cite This Page</h3>
  <p class="snap-cite-desc">
    This page is updated daily with fresh data from live production pipelines.
    To reference this intelligence in research, journalism, or professional reports,
    use the citation below.
  </p>
  <div class="snap-cite-code-wrap">
    <pre class="snap-cite-code">EnergyRiskIQ. (2026). <em>Germany Gas Storage Levels &mdash; Live Data &amp; Risk Intelligence &mdash; {today_str}</em>.
Retrieved from <a href="{BASE_URL}/gas-storage-levels-germany">{BASE_URL}/gas-storage-levels-germany</a>
Data sources: AGSI+ / GIE (German storage), Yahoo Finance (TTF), EnergyRiskIQ Custom Algorithms (winter readiness, EGSI-M, GERI, EERI).</pre>
    <button class="snap-cite-copy-btn" onclick="this.textContent='Copied!';setTimeout(()=>this.textContent='Copy',2000);navigator.clipboard&&navigator.clipboard.writeText('EnergyRiskIQ. (2026). Germany Gas Storage Levels \u2014 Live Data & Risk Intelligence \u2014 {today_str}. Retrieved from {BASE_URL}/gas-storage-levels-germany')">Copy</button>
  </div>
  <div class="snap-cite-footer">
    Data sourced from: AGSI+ / Gas Infrastructure Europe (German storage),
    Yahoo Finance (TTF natural gas futures), EnergyRiskIQ Custom Algorithms (winter readiness, EGSI-M, GERI, EERI).
    <strong>Not financial advice.</strong>
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
      GERI &bull; EERI &bull; EGSI &bull; Gas Storage &bull; Alerts &bull; Custom Algorithms
    </div>
    <div style="display:flex;justify-content:center;gap:24px;flex-wrap:wrap;
                font-size:11px;margin-bottom:14px;">
      <a href="/indices/global-energy-risk-index" style="color:#475569;text-decoration:none;">GERI</a>
      <a href="/indices/europe-energy-risk-index" style="color:#475569;text-decoration:none;">EERI</a>
      <a href="/indices/europe-gas-stress-index" style="color:#475569;text-decoration:none;">EGSI</a>
      <a href="/gas-storage-levels-in-europe" style="color:#475569;text-decoration:none;">EU Storage</a>
      <a href="/gas-storage-levels-germany" style="color:#d4a017;text-decoration:none;">DE Storage</a>
      <a href="/data/global-energy-risk-forecast" style="color:#475569;text-decoration:none;">Forecast</a>
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

@router.get("/gas-storage-levels-germany")
async def gas_storage_levels_germany():
    """
    Public SEO page: Germany Gas Storage Levels — Live Data & Risk Intelligence.
    Streams loader immediately, then fetches data and renders the full page.
    """
    async def generate():
        yield _GERMANY_LOADER

        try:
            data = await asyncio.to_thread(_fetch_germany_data)
        except Exception as exc:
            logger.error(f"Germany gas storage data fetch failed: {exc}", exc_info=True)
            yield (
                f"<script>var l=document.getElementById('snap-loader');"
                f"if(l)l.style.display='none';document.body.style.overflow='';</script>"
                f"<div style='color:#ef4444;padding:40px;font-family:sans-serif;background:#0b0f1a'>"
                f"<h2>Error loading storage data</h2>"
                f"<p>{_html.escape(str(exc))}</p></div></body></html>"
            )
            return

        today_str = datetime.now(timezone.utc).strftime("%B %-d, %Y")
        html_body = _build_germany_html(data, today_str)
        yield html_body

    return StreamingResponse(generate(), media_type="text/html")
