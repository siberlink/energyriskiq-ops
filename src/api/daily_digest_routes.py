import os
import json
import logging
from datetime import datetime, timedelta, date
from fastapi import APIRouter, Header, HTTPException
from typing import Optional

from src.db.db import execute_query, execute_one, execute_production_query, execute_production_one
from src.api.user_routes import verify_user_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/digest", tags=["daily-digest"])

PLAN_LEVELS = {"free": 4, "personal": 4, "trader": 4, "pro": 4, "enterprise": 4}


def get_user_plan(user_id: int) -> str:
    return "enterprise"


def get_alerts(limit: int = 20, is_delayed: bool = False):
    if is_delayed:
        start = date.today() - timedelta(days=2)
        end = date.today() - timedelta(days=1)
    else:
        start = date.today() - timedelta(days=1)
        end = date.today() + timedelta(days=1)
    rows = execute_production_query("""
        SELECT id, alert_type, scope_region, scope_assets, severity, headline, body,
               category, confidence, created_at, classification
        FROM alert_events
        WHERE created_at >= %s AND created_at < %s
        ORDER BY severity DESC, created_at DESC
        LIMIT %s
    """, (start, end, limit))
    result = []
    if not rows:
        return result
    for r in rows:
        result.append({
            "id": r["id"],
            "alert_type": r["alert_type"],
            "region": r["scope_region"],
            "assets": r["scope_assets"] if r["scope_assets"] else [],
            "severity": r["severity"],
            "headline": r["headline"],
            "category": r["category"],
            "confidence": float(r["confidence"]) if r["confidence"] else 0,
            "created_at": r["created_at"].isoformat() if r["created_at"] else None
        })
    return result


def get_index_snapshot(index_id: str, days: int = 2):
    rows = execute_production_query("""
        SELECT date, value, band, trend_1d, trend_7d, interpretation, components
        FROM intel_indices_daily
        WHERE index_id = %s
        ORDER BY date DESC
        LIMIT %s
    """, (index_id, days))
    return [dict(r) for r in rows] if rows else []


def get_eeri_snapshot(days: int = 2):
    rows = execute_production_query("""
        SELECT date, value, band, trend_1d, trend_7d, interpretation, components, drivers
        FROM reri_indices_daily
        WHERE index_id = 'europe:eeri'
        ORDER BY date DESC
        LIMIT %s
    """, (days,))
    return [dict(r) for r in rows] if rows else []


def get_egsi_snapshot(days: int = 2):
    rows = execute_production_query("""
        SELECT index_date as date, index_value as value, band, trend_1d, trend_7d, interpretation
        FROM egsi_m_daily
        ORDER BY index_date DESC
        LIMIT %s
    """, (days,))
    return [dict(r) for r in rows] if rows else []


def get_asset_snapshots(days: int = 7):
    brent = execute_production_query(
        "SELECT date, brent_price, brent_change_pct FROM oil_price_snapshots ORDER BY date DESC LIMIT %s",
        (days,)
    )
    ttf = execute_production_query(
        "SELECT date, ttf_price FROM ttf_gas_snapshots ORDER BY date DESC LIMIT %s",
        (days,)
    )
    vix = execute_production_query(
        "SELECT date, vix_close FROM vix_snapshots ORDER BY date DESC LIMIT %s",
        (days,)
    )
    eurusd = execute_production_query(
        "SELECT date, rate FROM eurusd_snapshots ORDER BY date DESC LIMIT %s",
        (days,)
    )
    storage = execute_production_query(
        "SELECT date, eu_storage_percent, risk_band FROM gas_storage_snapshots ORDER BY date DESC LIMIT %s",
        (days,)
    )

    def to_list(rows):
        return [dict(r) for r in rows] if rows else []

    return {
        "brent": to_list(brent),
        "ttf": to_list(ttf),
        "vix": to_list(vix),
        "eurusd": to_list(eurusd),
        "storage": to_list(storage)
    }


def compute_asset_changes(assets):
    changes = {}
    for key in ["brent", "ttf", "vix", "eurusd", "storage"]:
        data = assets.get(key, [])
        if len(data) >= 2:
            if key == "brent":
                current = float(data[0].get("brent_price", 0))
                prev = float(data[1].get("brent_price", 0))
                pct = float(data[0].get("brent_change_pct", 0))
                changes[key] = {"current": current, "previous": prev, "change_pct": pct, "label": "Brent Crude"}
            elif key == "ttf":
                current = float(data[0].get("ttf_price", 0))
                prev = float(data[1].get("ttf_price", 0))
                pct = round(((current - prev) / prev) * 100, 2) if prev else 0
                changes[key] = {"current": current, "previous": prev, "change_pct": pct, "label": "TTF Gas"}
            elif key == "vix":
                current = float(data[0].get("vix_close", 0))
                prev = float(data[1].get("vix_close", 0))
                delta = round(current - prev, 2)
                changes[key] = {"current": current, "previous": prev, "change_delta": delta, "label": "VIX"}
            elif key == "eurusd":
                current = float(data[0].get("rate", 0))
                prev = float(data[1].get("rate", 0))
                pct = round(((current - prev) / prev) * 100, 3) if prev else 0
                changes[key] = {"current": round(current, 4), "previous": round(prev, 4), "change_pct": pct, "label": "EUR/USD"}
            elif key == "storage":
                current = float(data[0].get("eu_storage_percent", 0))
                prev = float(data[1].get("eu_storage_percent", 0))
                delta = round(current - prev, 2)
                changes[key] = {"current": current, "previous": prev, "change_delta": delta, "label": "EU Gas Storage", "risk_band": data[0].get("risk_band", "")}
        elif len(data) == 1:
            if key == "brent":
                changes[key] = {"current": float(data[0].get("brent_price", 0)), "label": "Brent Crude"}
            elif key == "ttf":
                changes[key] = {"current": float(data[0].get("ttf_price", 0)), "label": "TTF Gas"}
            elif key == "vix":
                changes[key] = {"current": float(data[0].get("vix_close", 0)), "label": "VIX"}
            elif key == "eurusd":
                changes[key] = {"current": round(float(data[0].get("rate", 0)), 4), "label": "EUR/USD"}
            elif key == "storage":
                changes[key] = {"current": float(data[0].get("eu_storage_percent", 0)), "label": "EU Gas Storage"}
    return changes


def compute_7d_correlations(assets, geri_data):
    if len(geri_data) < 7:
        return None
    geri_values = [float(g.get("value", 0)) for g in geri_data[:7]]
    correlations = {}
    for key, field in [("brent", "brent_price"), ("ttf", "ttf_price"), ("vix", "vix_close")]:
        data = assets.get(key, [])
        if len(data) >= 7:
            asset_values = [float(d.get(field, 0)) for d in data[:7]]
            if len(geri_values) == len(asset_values):
                n = len(geri_values)
                mean_g = sum(geri_values) / n
                mean_a = sum(asset_values) / n
                cov = sum((geri_values[i] - mean_g) * (asset_values[i] - mean_a) for i in range(n)) / n
                std_g = (sum((g - mean_g) ** 2 for g in geri_values) / n) ** 0.5
                std_a = (sum((a - mean_a) ** 2 for a in asset_values) / n) ** 0.5
                if std_g > 0 and std_a > 0:
                    correlations[key] = round(cov / (std_g * std_a), 2)
    return correlations if correlations else None


def compute_rolling_betas(assets, geri_data, window=30):
    if len(geri_data) < window:
        return None
    geri_vals = [float(g.get("value", 0)) for g in geri_data[:window]]
    betas = {}
    for key, field in [("brent", "brent_price"), ("ttf", "ttf_price"), ("vix", "vix_close")]:
        data = assets.get(key, [])
        if len(data) >= window:
            asset_vals = [float(d.get(field, 0)) for d in data[:window]]
            n = min(len(geri_vals), len(asset_vals))
            if n < 5:
                continue
            gv = geri_vals[:n]
            av = asset_vals[:n]
            mean_g = sum(gv) / n
            mean_a = sum(av) / n
            cov = sum((gv[i] - mean_g) * (av[i] - mean_a) for i in range(n)) / n
            var_g = sum((g - mean_g) ** 2 for g in gv) / n
            if var_g > 0:
                betas[key] = round(cov / var_g, 3)
    return betas if betas else None


def determine_risk_tone(geri_data):
    if not geri_data:
        return {"tone": "Unknown", "color": "gray"}
    val = geri_data[0].get("value", 0)
    trend = geri_data[0].get("trend_1d", 0)
    if val >= 70:
        tone = "Escalating"
        color = "red"
    elif val >= 50:
        if trend > 0:
            tone = "Elevated & Rising"
            color = "orange"
        else:
            tone = "Elevated"
            color = "yellow"
    elif val >= 30:
        tone = "Moderate"
        color = "yellow"
    else:
        if trend < 0:
            tone = "Stabilizing"
            color = "green"
        else:
            tone = "Low"
            color = "green"
    return {"tone": tone, "color": color}


def determine_regime(geri_val, eeri_val, storage_pct, vix_val):
    if geri_val >= 70 and vix_val >= 25:
        return "Shock"
    if eeri_val >= 70 and storage_pct and storage_pct < 40:
        return "Gas-Storage Stress"
    if geri_val >= 50 and vix_val >= 20:
        return "Risk Build"
    if geri_val >= 50:
        return "Elevated Uncertainty"
    if geri_val < 30:
        return "Calm"
    return "Moderate"


# ─────────────────────────────────────────────────────────────────────────────
# Deterministic "Custom Algorithms" sections
# (Executive One-Line Summary, Today's Actionable Takeaways, Forward Watchlist)
# All derived only from data already present in the Daily Intelligence Report.
# ─────────────────────────────────────────────────────────────────────────────

OIL_EVENT_KEYWORDS = [
    "hormuz", "opec", "sanction", "war", "supply disruption", "iran", "iraq",
    "israel", "strait", "pipeline", "embargo", "attack", "military", "tanker",
    "saudi", "russia", "crude", "refinery"
]
SHIP_EVENT_KEYWORDS = [
    "red sea", "suez", "panama", "tanker", "freight", "shipping", "maritime",
    "vessel", "houthi", "blockade", "canal", "route"
]
EUROPE_EVENT_KEYWORDS = [
    "ukraine", "grid", "winter", "cold", "storage", "ttf", "norway", "demand",
    "europe", "european", "eu ", "lng terminal", "power", "pipeline", "gas"
]


def _num(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _events_match(alerts, keywords):
    matched = []
    for a in alerts or []:
        text = " ".join([
            str(a.get("headline", "") or ""),
            str(a.get("category", "") or ""),
            str(a.get("region", "") or ""),
        ]).lower()
        if any(kw in text for kw in keywords):
            matched.append(a)
    return matched


def _bias_label(score):
    score = max(-2, min(2, score))
    if score <= -2:
        return "Bearish"
    if score == -1:
        return "Neutral to Bearish"
    if score == 0:
        return "Neutral"
    if score == 1:
        return "Neutral to Bullish"
    return "Bullish"


def build_executive_summary(geri, eeri, asset_changes, regime, esc_prob, de_esc_prob):
    geri_trend = _num(geri[0].get("trend_1d", 0)) if geri else 0
    eeri_trend = _num(eeri[0].get("trend_1d", 0)) if eeri else 0
    brent = asset_changes.get("brent", {})
    ttf = asset_changes.get("ttf", {})
    brent_pct = brent.get("change_pct")
    ttf_pct = ttf.get("change_pct")

    geri_rising = geri_trend > 0
    geri_falling = geri_trend < 0
    esc_high = esc_prob >= 55
    de_esc_high = de_esc_prob >= 55
    ttf_up = ttf_pct is not None and ttf_pct > 0
    brent_down = brent_pct is not None and brent_pct < 0
    eeri_rising = eeri_trend > 0

    if geri_rising and esc_high:
        return ("Global energy risk is rising, increasing upside pressure on Brent and LNG "
                "as supply disruption and geopolitical escalation risks return to market focus today.")
    if eeri_rising and not geri_rising:
        return ("Global risk remains broadly stable while European gas stress increases, as TTF "
                "and winter supply concerns diverge from the calmer overall geopolitical backdrop.")
    if ttf_up and geri_falling:
        return ("TTF strength is diverging from easing global risk, suggesting European gas "
                "fundamentals and winter supply dynamics now matter more than the geopolitical premium.")
    if brent_down and geri_falling:
        return ("Easing geopolitical risk continues to weigh on Brent, with oil markets pricing "
                "out part of the recent risk premium amid steadier supply expectations.")
    if geri_falling and de_esc_high:
        return ("Global energy risk continues to ease, reducing geopolitical support for Brent "
                "while leaving European gas exposed to winter demand and storage-related supply risks.")

    if regime == "Calm":
        return ("Energy risk remains contained with no immediate escalation signal, keeping Brent "
                "and European gas broadly stable while markets monitor geopolitical and supply developments.")
    if regime == "Shock":
        return ("Acute energy disruption risk is elevated, justifying defensive positioning as Brent, "
                "LNG and European gas remain exposed to high-impact supply and geopolitical shocks.")
    return ("Energy risk pressure is building, keeping Brent and European gas exposed to renewed "
            "upside as geopolitical and supply signals warrant closer hedging attention this session.")


def build_actionable_takeaways(geri, eeri, egsi, asset_changes, alerts, regime,
                               storage_pct, esc_prob, de_esc_prob):
    geri_trend = _num(geri[0].get("trend_1d", 0)) if geri else 0
    eeri_trend = _num(eeri[0].get("trend_1d", 0)) if eeri else 0
    egsi_trend = _num(egsi[0].get("trend_1d", 0)) if egsi else 0
    brent_pct = asset_changes.get("brent", {}).get("change_pct")
    ttf_pct = asset_changes.get("ttf", {}).get("change_pct")
    storage_delta = asset_changes.get("storage", {}).get("change_delta")

    geri_rising = geri_trend > 0
    geri_falling = geri_trend < 0
    de_esc_high = de_esc_prob >= 55
    esc_high = esc_prob >= 55

    oil_events = _events_match(alerts, OIL_EVENT_KEYWORDS)
    ship_events = _events_match(alerts, SHIP_EVENT_KEYWORDS)
    europe_events = _events_match(alerts, EUROPE_EVENT_KEYWORDS)

    # ── Oil ──
    oil_score = 0
    if geri_falling:
        oil_score -= 1
    elif geri_rising:
        oil_score += 1
    if brent_pct is not None and brent_pct < -0.3:
        oil_score -= 1
    elif brent_pct is not None and brent_pct > 0.3:
        oil_score += 1
    if de_esc_high:
        oil_score -= 1
    if esc_high:
        oil_score += 1
    if oil_events:
        oil_score += 1
    oil_points = []
    if brent_pct is not None and brent_pct < -0.3:
        oil_points.append("Brent downside pressure remains in play as the geopolitical premium fades.")
    elif brent_pct is not None and brent_pct > 0.3:
        oil_points.append("Brent is firmer as supply-risk concerns regain attention.")
    else:
        oil_points.append("Brent is holding steady with no decisive directional catalyst today.")
    if oil_events:
        oil_points.append("Middle East and supply-related events keep oil sensitive to headline risk.")
    elif de_esc_high:
        oil_points.append("Easing tensions reduce the geopolitical risk premium on crude.")
    else:
        oil_points.append("Geopolitical risk is contained but worth monitoring for surprises.")
    oil_points.append("Watch OPEC+ policy signals and Strait of Hormuz shipping flows.")

    # ── European Gas ──
    gas_score = 0
    if ttf_pct is not None and ttf_pct > 0:
        gas_score += 1
    elif ttf_pct is not None and ttf_pct < 0:
        gas_score -= 1
    if storage_delta is not None and storage_delta > 0:
        gas_score -= 1
    if storage_pct < 45:
        gas_score += 1
    if eeri_trend > 0:
        gas_score += 1
    elif eeri_trend < 0:
        gas_score -= 1
    if egsi_trend > 0:
        gas_score += 1
    elif egsi_trend < 0:
        gas_score -= 1
    if europe_events:
        gas_score += 1
    gas_points = []
    if (ttf_pct is not None and ttf_pct > 0) and geri_falling:
        gas_points.append("TTF diverges from easing global risk, driven by European fundamentals.")
    elif ttf_pct is not None and ttf_pct > 0:
        gas_points.append("TTF is firmer on winter supply and demand concerns.")
    elif ttf_pct is not None and ttf_pct < 0:
        gas_points.append("TTF softens as supply concerns ease.")
    else:
        gas_points.append("TTF is broadly stable with balanced supply and demand signals.")
    if storage_pct < 45:
        gas_points.append(f"EU storage near {storage_pct:.0f}% keeps the supply buffer in focus.")
    else:
        gas_points.append(f"EU storage around {storage_pct:.0f}% offers a reasonable seasonal buffer.")
    gas_points.append("Monitor EU gas storage, Ukraine grid risk and cold-weather demand.")

    # ── LNG ──
    lng_score = 0
    if ttf_pct is not None and ttf_pct >= 2:
        lng_score += 1
    if ship_events:
        lng_score += 1
    if oil_events:
        lng_score += 1
    if geri_falling:
        lng_score -= 1
    if de_esc_high:
        lng_score -= 1
    lng_points = []
    if ship_events:
        lng_points.append("Shipping and maritime risk keeps LNG freight sensitive to disruption.")
    else:
        lng_points.append("Shipping normalization limits near-term LNG upside.")
    if ttf_pct is not None and ttf_pct >= 2:
        lng_points.append("Strong TTF gains spill over into LNG pricing sensitivity.")
    else:
        lng_points.append("LNG remains tied to TTF moves and regional demand signals.")
    lng_points.append("Monitor Asian demand, freight rates and Red Sea / Suez routing.")

    # ── Risk Management ──
    rm_map = {
        "Calm": [
            "Current regime remains calm.",
            "No immediate need for aggressive hedging.",
            "Keep monitoring geopolitical escalation and storage-related stress.",
        ],
        "Moderate": [
            "Regime is moderate and broadly stable.",
            "Selective, low-cost hedging is sufficient for now.",
            "Watch for shifts in GERI and European gas stress.",
        ],
        "Elevated Uncertainty": [
            "Regime shows elevated uncertainty.",
            "Maintain protection against sudden price spikes.",
            "Track escalation triggers and the most exposed assets closely.",
        ],
        "Risk Build": [
            "Risk is building across the complex.",
            "Maintain protection against price spikes and add selective hedges.",
            "Track escalation triggers and the most exposed assets closely.",
        ],
        "Gas-Storage Stress": [
            "Gas-storage stress regime is active.",
            "Maintain protection on European gas exposure.",
            "Monitor storage draws, LNG imports and winter demand.",
        ],
        "Shock": [
            "Regime signals acute disruption risk.",
            "Defensive hedging is justified.",
            "Closely monitor exposed assets and supply availability.",
        ],
    }
    rm_points = rm_map.get(regime, rm_map["Moderate"])

    return {
        "oil": {"bias": _bias_label(oil_score), "points": oil_points[:3]},
        "gas": {"bias": _bias_label(gas_score), "points": gas_points[:3]},
        "lng": {"bias": _bias_label(lng_score), "points": lng_points[:3]},
        "risk_management": {"points": rm_points[:3]},
    }


def build_forward_watchlist(geri, eeri, egsi, asset_changes, alerts,
                            storage_pct, esc_prob, de_esc_prob):
    geri_trend = _num(geri[0].get("trend_1d", 0)) if geri else 0
    eeri_trend = _num(eeri[0].get("trend_1d", 0)) if eeri else 0
    egsi_trend = _num(egsi[0].get("trend_1d", 0)) if egsi else 0
    brent_pct = asset_changes.get("brent", {}).get("change_pct")
    ttf_pct = asset_changes.get("ttf", {}).get("change_pct")

    geri_rising = geri_trend > 0
    geri_falling = geri_trend < 0
    ttf_up = ttf_pct is not None and ttf_pct > 0
    brent_strong = brent_pct is not None and abs(brent_pct) >= 1.0

    oil_events = _events_match(alerts, OIL_EVENT_KEYWORDS)
    ship_events = _events_match(alerts, SHIP_EVENT_KEYWORDS)
    europe_events = _events_match(alerts, EUROPE_EVENT_KEYWORDS)

    items = []

    def add(title, priority, reason):
        if not any(i["title"] == title for i in items):
            items.append({"title": title, "priority": priority, "reason": reason})

    if oil_events:
        add("OPEC and Middle East oil supply signals",
            "High" if geri_rising else "Medium",
            "Production-policy or geopolitical shifts could move Brent's risk premium and short-term oil positioning.")
    if ship_events or oil_events:
        add("Strait of Hormuz and Red Sea shipping flows",
            "Medium",
            "Normalizing flows would reduce the geopolitical premium, while renewed disruption raises upside risk for oil and LNG.")
    if brent_strong:
        direction = "higher" if brent_pct > 0 else "lower"
        add(f"Brent {direction} move confirmation",
            "Medium",
            f"Brent moved {brent_pct:+.1f}% today; watch whether follow-through confirms or contradicts the current risk-index direction.")
    if geri_rising:
        add("Geopolitical escalation and oil supply risk",
            "High",
            "Rising GERI points to building escalation risk; monitor supply disruption, maritime security and Brent risk premium.")
    elif geri_falling:
        add("De-escalation durability and risk confirmation",
            "Low",
            "With GERI easing, watch shipping normalization, lower volatility and Brent downside follow-through to confirm the trend.")
    if eeri_trend > 0 or egsi_trend > 0 or europe_events:
        add("European gas: storage, TTF and Ukraine grid risk",
            "Medium",
            "European stress indicators are firm; monitor EU storage, TTF moves, LNG imports and winter demand.")
    if ttf_up and geri_falling:
        add("European gas divergence from global risk",
            "Medium",
            "TTF is rising while global risk eases, suggesting European fundamentals may be outweighing geopolitical de-escalation.")
    if storage_pct < 50:
        add("EU gas storage injections and draws",
            "Medium",
            "Storage trends shape winter supply confidence and European gas price risk.")
    add("Asian LNG demand and freight developments",
        "Medium" if ship_events else "Low",
        "Freight or shipping stress can affect LNG pricing and regional supply flexibility.")

    fallback = [
        ("Brent trend confirmation", "Low",
         "Track whether Brent follow-through aligns with the current GERI direction and risk tone."),
        ("TTF and European gas trend", "Low",
         "Monitor TTF movement against storage levels and winter demand for direction confirmation."),
        ("GERI direction and volatility", "Low",
         "Watch GERI's daily path and volatility for early signals of a regime change."),
    ]
    for title, priority, reason in fallback:
        if len(items) >= 3:
            break
        add(title, priority, reason)

    order = {"High": 0, "Medium": 1, "Low": 2}
    items.sort(key=lambda i: order.get(i["priority"], 3))
    return items[:5]


def generate_ai_digest(plan: str, alerts, geri, eeri, egsi, asset_changes, correlations, betas, risk_tone, regime):
    try:
        import os
        from openai import OpenAI
        ai_api_key = os.environ.get('AI_INTEGRATIONS_OPENAI_API_KEY')
        ai_base_url = os.environ.get('AI_INTEGRATIONS_OPENAI_BASE_URL')
        if ai_api_key and ai_base_url:
            client = OpenAI(api_key=ai_api_key, base_url=ai_base_url)
        else:
            client = OpenAI()

        plan_level = PLAN_LEVELS.get(plan, 0)

        geri_current = geri[0] if geri else {}
        geri_prev = geri[1] if len(geri) > 1 else {}
        eeri_current = eeri[0] if eeri else {}
        egsi_current = egsi[0] if egsi else {}

        geri_val = geri_current.get("value", "N/A")
        geri_change = geri_current.get("trend_1d", 0)
        eeri_val = eeri_current.get("value", "N/A")
        eeri_change = eeri_current.get("trend_1d", 0)
        egsi_val = egsi_current.get("value", "N/A")

        alerts_text = ""
        alert_limit = 2 if plan_level == 0 else 5 if plan_level <= 2 else 10
        for a in alerts[:alert_limit]:
            alerts_text += f"- [{a['severity']}/5] {a['headline']} | Region: {a['region']} | Category: {a.get('category', 'N/A')}\n"

        asset_text = ""
        for key, data in asset_changes.items():
            label = data.get("label", key)
            current = data.get("current", "N/A")
            if "change_pct" in data:
                asset_text += f"{label}: {current} ({data['change_pct']:+.2f}%)\n"
            elif "change_delta" in data:
                asset_text += f"{label}: {current} ({data['change_delta']:+.2f})\n"
            else:
                asset_text += f"{label}: {current}\n"

        section_instructions = ""
        if plan_level == 0:
            section_instructions = """
OUTPUT SECTIONS (FREE PLAN - keep brief):
1) EXECUTIVE RISK SNAPSHOT (5 lines max): Global risk tone, 2-3 key drivers, 1 interpretation paragraph
2) BASIC ASSET MOVES: Simple price changes, no interpretation
3) GERI DIRECTION: Current value, direction, one-line interpretation
4) SHORT WATCHLIST: 1-2 forward signals, no probability scoring
Keep total output under 300 words."""
        elif plan_level == 1:
            section_instructions = """
OUTPUT SECTIONS (PERSONAL PLAN):
1) EXECUTIVE RISK SNAPSHOT: Global risk tone, 3 key drivers, interpretation paragraph
2) INDEX MOVEMENT SUMMARY: GERI + EERI + EGSI with interpretations
3) TOP RISK EVENTS: Top 3-5 alerts with "Why It Matters" commentary
4) BASIC ASSET IMPACT: Directional impacts for Oil, Gas, VIX, EUR/USD with brief context
5) 7-DAY RISK TREND: Short rolling trend analysis
6) RISK vs ASSET RELATIONSHIP: Brief historical context on correlations
Keep total output under 500 words."""
        elif plan_level == 2:
            section_instructions = f"""
OUTPUT SECTIONS (TRADER PLAN):
1) EXECUTIVE RISK SNAPSHOT: Global risk tone, 3 key drivers, interpretation
2) INDEX MOVEMENT SUMMARY: All indices with WHY each moved
3) TOP RISK EVENTS: Top 5 alerts with detailed "Why It Matters" + spillover
4) CROSS-ASSET IMPACT MATRIX: Each asset with directional impact + magnitude estimate
5) MARKET REACTION vs RISK SIGNAL: Quantified comparison
6) PROBABILITY-BASED OUTLOOK: TTF spike probability, Brent breakout probability, VIX jump probability (estimate based on patterns)
7) 30-DAY RISK TREND ANALYSIS: Pattern analysis with regime transitions
8) FORWARD WATCHLIST WITH PROBABILITY: 3-4 items with impact probability and confidence
9) VOLATILITY OUTLOOK: Short-term volatility regime prediction
Correlations (7d): {json.dumps(correlations) if correlations else 'N/A'}
Keep total output under 700 words."""
        elif plan_level == 3:
            section_instructions = f"""
OUTPUT SECTIONS (PRO PLAN):
1) EXECUTIVE RISK SNAPSHOT with regime classification
2) INDEX DECOMPOSITION: GERI component drivers (supply, transit, freight, storage contributions)
3) TOP RISK EVENTS with cross-regional contagion analysis
4) CROSS-ASSET SENSITIVITY TABLE: GERI beta vs Brent, TTF, VIX, EUR/USD
5) MARKET REACTION vs RISK SIGNAL with divergence analysis
6) REGIME CLASSIFICATION: Current regime + shift detection
7) PROBABILITY FORECASTS with driver attribution
8) 90-DAY RISK CONTEXT: Institutional time horizon analysis
9) SCENARIO OUTLOOK: Base case, Escalation case, De-escalation case
10) FORWARD WATCHLIST with triggers and levels to watch
Correlations (7d): {json.dumps(correlations) if correlations else 'N/A'}
Betas (rolling): {json.dumps(betas) if betas else 'N/A'}
Current Regime: {regime}
Keep total output under 900 words."""
        else:
            section_instructions = f"""
OUTPUT SECTIONS (ENTERPRISE PLAN):
1) EXECUTIVE RISK SNAPSHOT with regime + contagion status
2) FULL INDEX DECOMPOSITION with component attribution
3) MULTI-REGION SPILLOVER ANALYSIS: How risk spreads between regions
4) CROSS-ASSET SENSITIVITY DASHBOARD with beta table
5) DIVERGENCE ANALYSIS: Risk signal vs market pricing gap
6) REGIME CLASSIFICATION + transition probability
7) SECTOR IMPACT FORECAST: Power, Industrial, LNG, Storage
8) PROBABILITY FORECASTS with full driver attribution
9) SCENARIO FORECASTS: 3 scenarios with portfolio implications
10) CUSTOM WATCHLIST with multi-week risk path indicators
11) STRATEGIC INTERPRETATION: EnergyRiskIQ Analyst Note
Correlations (7d): {json.dumps(correlations) if correlations else 'N/A'}
Betas (rolling): {json.dumps(betas) if betas else 'N/A'}
Current Regime: {regime}
Keep total output under 1100 words."""

        system_prompt = """You are EnergyRiskIQ Intelligence Engine.
You must NOT repeat raw news. You must interpret yesterday's alerts + indices + real market data.
Be concise, trader-oriented, and quantify relationships when data is provided.
If you state a probability, base it on provided data patterns, not guesses.
Always separate: Facts / Interpretation / Watchlist.
Use professional, analytical tone. No promotional language.
Never describe yourself as an AI, language model, assistant, or chatbot, and never mention artificial intelligence. If attribution is required, refer only to "EnergyRiskIQ Custom Algorithms".
Format output with clear section headers using markdown (## for sections).
Use bullet points for lists. Use bold for key metrics.
End with one line: "Informational only. Not financial advice."
"""

        user_prompt = f"""DATE: {date.today().isoformat()}
BASED ON ALERTS FROM: {(date.today() - timedelta(days=1)).isoformat()}

RISK TONE: {risk_tone['tone']}

INDEX SNAPSHOT:
GERI: {geri_val} (change: {geri_change:+d})
EERI: {eeri_val} (change: {eeri_change:+d})
EGSI-M: {egsi_val}

YESTERDAY'S TOP ALERTS:
{alerts_text}

ASSET MOVES:
{asset_text}

{section_instructions}
"""

        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.4,
            max_tokens=1500 if plan_level >= 3 else 1000 if plan_level >= 2 else 600
        )

        return response.choices[0].message.content

    except Exception as e:
        logger.error(f"AI digest generation failed: {e}")
        return None


def get_cached_ai_narrative(cache_key: str):
    try:
        row = execute_one(
            "SELECT narrative FROM daily_digest_ai_cache WHERE cache_key = %s",
            (cache_key,),
        )
        return row["narrative"] if row and row.get("narrative") else None
    except Exception as e:
        logger.error(f"AI narrative cache read failed: {e}")
        return None


def set_cached_ai_narrative(cache_key: str, narrative: str):
    try:
        execute_query(
            """
            INSERT INTO daily_digest_ai_cache (cache_key, narrative, created_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (cache_key)
            DO UPDATE SET narrative = EXCLUDED.narrative, created_at = NOW()
            """,
            (cache_key, narrative),
            fetch=False,
        )
    except Exception as e:
        logger.error(f"AI narrative cache write failed: {e}")


@router.get("/daily")
def get_daily_digest(x_user_token: Optional[str] = Header(None)):
    session = verify_user_session(x_user_token)
    user_id = session["user_id"]

    # Gate the full Daily Intelligence Report behind its €2.99/mo subscription.
    try:
        from src.api.daily_report_routes import user_has_daily_report
        if not user_has_daily_report(user_id):
            raise HTTPException(402, "Daily Intelligence Report subscription required")
    except HTTPException:
        raise
    except Exception as _e:
        logger.error(f"Daily report entitlement check failed: {_e}")
        raise HTTPException(402, "Daily Intelligence Report subscription required")

    plan = get_user_plan(user_id)
    plan_level = PLAN_LEVELS.get(plan, 0)

    is_delayed = plan_level == 0
    alerts = get_alerts(limit=20, is_delayed=is_delayed)

    days_for_assets = 7 if plan_level <= 1 else 30 if plan_level == 2 else 90
    geri_days = 7 if plan_level <= 1 else 30 if plan_level == 2 else 90
    geri = get_index_snapshot("global:geo_energy_risk", days=geri_days)
    eeri = get_eeri_snapshot(days=geri_days)
    egsi = get_egsi_snapshot(days=geri_days)
    assets = get_asset_snapshots(days=days_for_assets)

    asset_changes = compute_asset_changes(assets)

    risk_tone = determine_risk_tone(geri)

    geri_val = geri[0].get("value", 0) if geri else 0
    eeri_val = eeri[0].get("value", 0) if eeri else 0
    storage_pct = float(assets["storage"][0].get("eu_storage_percent", 50)) if assets.get("storage") else 50
    vix_val = float(assets["vix"][0].get("vix_close", 15)) if assets.get("vix") else 15
    regime = determine_regime(geri_val, eeri_val, storage_pct, vix_val)

    correlations = None
    betas = None
    if plan_level >= 1:
        correlations = compute_7d_correlations(assets, geri)
    if plan_level >= 3:
        betas = compute_rolling_betas(assets, geri)

    # The AI narrative is the single slow part of this endpoint (a multi-second
    # LLM call). It is a daily briefing, so cache it per plan-level/day and reuse
    # it for every subsequent view that day instead of regenerating each load.
    digest_day = (date.today() - timedelta(days=2)).isoformat() if is_delayed else (date.today() - timedelta(days=1)).isoformat()
    ai_cache_key = f"v1:{plan_level}:{digest_day}:{'d' if is_delayed else 'l'}"
    ai_narrative = get_cached_ai_narrative(ai_cache_key)
    if ai_narrative is None:
        ai_narrative = generate_ai_digest(plan, alerts, geri, eeri, egsi, asset_changes, correlations, betas, risk_tone, regime)
        if ai_narrative:
            set_cached_ai_narrative(ai_cache_key, ai_narrative)

    alert_limit = 2 if plan_level == 0 else 5 if plan_level <= 2 else 10
    visible_alerts = []
    for a in alerts[:alert_limit]:
        visible_alerts.append({
            "headline": a["headline"],
            "region": a["region"],
            "severity": a["severity"],
            "category": a.get("category", ""),
            "confidence": a.get("confidence", 0)
        })

    geri_summary = None
    if geri:
        g = geri[0]
        geri_summary = {
            "value": g.get("value"),
            "band": g.get("band"),
            "trend_1d": g.get("trend_1d"),
            "trend_7d": g.get("trend_7d"),
            "date": g.get("date").isoformat() if g.get("date") else None
        }

    eeri_summary = None
    if eeri and plan_level >= 1:
        e = eeri[0]
        drivers = e.get("drivers", [])
        if isinstance(drivers, str):
            try:
                drivers = json.loads(drivers)
            except:
                drivers = []
        eeri_summary = {
            "value": e.get("value"),
            "band": e.get("band"),
            "trend_1d": e.get("trend_1d"),
            "trend_7d": e.get("trend_7d"),
            "date": e.get("date").isoformat() if e.get("date") else None,
            "top_drivers": drivers[:3] if isinstance(drivers, list) else []
        }

    egsi_summary = None
    if egsi and plan_level >= 1:
        eg = egsi[0]
        egsi_summary = {
            "value": eg.get("value"),
            "band": eg.get("band"),
            "trend_1d": eg.get("trend_1d"),
            "date": eg.get("date").isoformat() if eg.get("date") else None
        }

    geri_history = None
    if plan_level >= 1 and len(geri) > 1:
        geri_history = [{"date": g.get("date").isoformat() if g.get("date") else None, "value": g.get("value")} for g in geri[:min(len(geri), days_for_assets)]]

    eeri_history = None
    if plan_level >= 2 and len(eeri) > 1:
        eeri_history = [{"date": e.get("date").isoformat() if e.get("date") else None, "value": e.get("value")} for e in eeri[:min(len(eeri), days_for_assets)]]

    # ── Probability scoring & volatility outlook (feed summary/takeaways/watchlist) ──
    probability_scoring = None
    volatility_outlook = None
    if plan_level >= 2:
        geri_values = [g.get("value", 0) for g in geri[:7]] if geri else []
        if len(geri_values) >= 3:
            avg_7d = sum(geri_values) / len(geri_values)
            std_7d = (sum((v - avg_7d) ** 2 for v in geri_values) / len(geri_values)) ** 0.5
            esc_p = min(95, max(5, int(geri_val * 0.8 + std_7d * 5)))
            de_esc_p = min(95, max(5, int(100 - geri_val * 0.8)))
            stab_p = min(95, max(5, int(60 - std_7d * 10))) if std_7d < 5 else max(5, int(30 - std_7d * 3))
            # Mutually exclusive dominant scenarios (probabilities sum to exactly 100%)
            trend_dev = geri_values[0] - avg_7d  # >0 => GERI rising vs 7d average
            esc_w = max(3.0, geri_val * 0.9 + std_7d * 4.0 + max(0.0, trend_dev) * 3.0)
            vol_w = max(3.0, std_7d * 8.0 + max(0.0, vix_val - 18.0) * 2.0)
            stab_w = max(3.0, (100.0 - geri_val) * 0.9 + max(0.0, -trend_dev) * 3.0 + max(0.0, 10.0 - std_7d))
            _tot = esc_w + vol_w + stab_w
            p_esc = int(round(esc_w / _tot * 100))
            p_vol = int(round(vol_w / _tot * 100))
            p_stab = max(0, 100 - p_esc - p_vol)
            probability_scoring = {
                "escalation_probability": esc_p,
                "de_escalation_probability": de_esc_p,
                "stability_probability": stab_p,
                "scenarios": [
                    {"name": "Continued Stabilization", "probability": p_stab},
                    {"name": "Regional Escalation", "probability": p_esc},
                    {"name": "Energy Volatility Spike", "probability": p_vol},
                ],
                "methodology": "Mutually exclusive scenario probabilities from GERI level, 7-day volatility and trend (sums to 100%)."
            }
            vol_regime = "low" if std_7d < 2 else "moderate" if std_7d < 5 else "high" if std_7d < 10 else "extreme"
            volatility_outlook = {
                "current_vol": round(std_7d, 2),
                "regime": vol_regime,
                "vix_level": vix_val,
                "outlook": f"{'Calm conditions' if vol_regime == 'low' else 'Moderate fluctuations' if vol_regime == 'moderate' else 'Elevated volatility' if vol_regime == 'high' else 'Extreme market stress'} expected in near term"
            }

    esc_prob = probability_scoring["escalation_probability"] if probability_scoring else 50
    de_esc_prob = probability_scoring["de_escalation_probability"] if probability_scoring else 50

    # ── Executive one-line summary + actionable takeaways (Custom Algorithms) ──
    executive_summary = build_executive_summary(geri, eeri, asset_changes, regime, esc_prob, de_esc_prob)
    actionable_takeaways = build_actionable_takeaways(
        geri, eeri, egsi, asset_changes, alerts, regime, storage_pct, esc_prob, de_esc_prob
    )

    # ── Forward watchlist: deterministic, prioritised 3-5 items (title/priority/reason) ──
    forward_watchlist = build_forward_watchlist(
        geri, eeri, egsi, asset_changes, alerts, storage_pct, esc_prob, de_esc_prob
    )

    scenario_forecasts = None
    if plan_level >= 3:
        brent_cur = asset_changes.get("brent", {}).get("current")
        ttf_cur = asset_changes.get("ttf", {}).get("current")
        vix_cur = vix_val

        def _impact(brent_lo, brent_hi, ttf_lo, ttf_hi, vix_lo, vix_hi):
            mi = {}
            if brent_cur:
                mi["brent"] = f"${brent_cur * brent_lo:.0f}\u2013${brent_cur * brent_hi:.0f}/bbl"
            if ttf_cur:
                mi["ttf"] = f"\u20ac{ttf_cur * ttf_lo:.0f}\u2013\u20ac{ttf_cur * ttf_hi:.0f}/MWh"
            mi["vix"] = f"{max(10.0, vix_cur + vix_lo):.0f}\u2013{max(12.0, vix_cur + vix_hi):.0f}"
            return mi

        scenarios = []
        base_geri = geri_val
        scenarios.append({
            "scenario": "Base Case",
            "probability": probability_scoring["stability_probability"] if probability_scoring else 50,
            "geri_forecast": round(base_geri, 1),
            "description": "Current trajectory maintained with no major disruptions",
            "market_impact": _impact(0.98, 1.02, 0.97, 1.03, -2, 2)
        })
        scenarios.append({
            "scenario": "Escalation",
            "probability": probability_scoring["escalation_probability"] if probability_scoring else 30,
            "geri_forecast": round(min(100, base_geri * 1.15), 1),
            "description": "Risk drivers intensify, supply disruptions or geopolitical escalation",
            "market_impact": _impact(1.04, 1.12, 1.05, 1.18, 3, 9)
        })
        scenarios.append({
            "scenario": "De-escalation",
            "probability": probability_scoring["de_escalation_probability"] if probability_scoring else 20,
            "geri_forecast": round(max(0, base_geri * 0.85), 1),
            "description": "Risk factors ease, diplomatic progress or supply normalization",
            "market_impact": _impact(0.90, 0.97, 0.85, 0.96, -6, -1)
        })
        scenario_forecasts = scenarios

    result = {
        "digest_date": date.today().isoformat(),
        "alerts_date": (date.today() - timedelta(days=2)).isoformat() if is_delayed else (date.today() - timedelta(days=1)).isoformat(),
        "plan": plan,
        "plan_level": plan_level,
        "risk_tone": risk_tone,
        "regime": regime if plan_level >= 2 else None,
        "geri": geri_summary,
        "eeri": eeri_summary,
        "egsi": egsi_summary,
        "asset_changes": asset_changes,
        "alerts": visible_alerts,
        "total_alerts_yesterday": len(alerts),
        "ai_narrative": ai_narrative,
        "correlations": correlations if plan_level >= 1 else None,
        "betas": betas if plan_level >= 3 else None,
        "geri_history": geri_history,
        "eeri_history": eeri_history,
        "storage_context": {
            "current": storage_pct,
            "risk_band": assets["storage"][0].get("risk_band", "") if assets.get("storage") else None
        } if plan_level >= 1 else None,
        "executive_summary": executive_summary,
        "actionable_takeaways": actionable_takeaways,
        "forward_watchlist": forward_watchlist,
        "probability_scoring": probability_scoring,
        "volatility_outlook": volatility_outlook,
        "scenario_forecasts": scenario_forecasts,
        "is_delayed": is_delayed,
        "upgrade_hints": get_upgrade_hints(plan_level)
    }

    return result


def get_upgrade_hints(plan_level: int):
    hints = []
    if plan_level < 1:
        hints.append({"feature": "Full Alert Analysis", "plan": "Personal", "price": "$9.95/mo"})
        hints.append({"feature": "Multi-Index Interpretation", "plan": "Personal", "price": "$9.95/mo"})
        hints.append({"feature": "7-Day Risk Trends", "plan": "Personal", "price": "$9.95/mo"})
    if plan_level < 2:
        hints.append({"feature": "Probability Scoring", "plan": "Trader", "price": "$29/mo"})
        hints.append({"feature": "Cross-Asset Impact Matrix", "plan": "Trader", "price": "$29/mo"})
        hints.append({"feature": "Volatility Outlook", "plan": "Trader", "price": "$29/mo"})
    if plan_level < 3:
        hints.append({"feature": "Index Decomposition", "plan": "Pro", "price": "$49/mo"})
        hints.append({"feature": "Contagion Analysis", "plan": "Pro", "price": "$49/mo"})
        hints.append({"feature": "Scenario Forecasts", "plan": "Pro", "price": "$49/mo"})
    if plan_level < 4:
        hints.append({"feature": "Portfolio Risk Mapping", "plan": "Enterprise", "price": "$129/mo"})
        hints.append({"feature": "API Access", "plan": "Enterprise", "price": "$129/mo"})
    return hints


@router.get("/public")
def get_digest_public_snapshot():
    row = execute_one("""
        SELECT page_date, page_json
        FROM public_digest_pages
        ORDER BY page_date DESC
        LIMIT 1
    """)
    if not row:
        return {"available": False}

    page_json = row["page_json"]
    if isinstance(page_json, str):
        model = json.loads(page_json)
    else:
        model = page_json

    geri = model.get("geri") or {}
    raw_tone = model.get("risk_tone", "Unknown")
    if isinstance(raw_tone, dict):
        risk_tone = raw_tone.get("tone", "Unknown")
    else:
        risk_tone = str(raw_tone) if raw_tone else "Unknown"
    total_alerts = model.get("total_alerts_yesterday", 0)
    digest_date = model.get("digest_date", row["page_date"].isoformat() if hasattr(row["page_date"], "isoformat") else str(row["page_date"]))
    alerts = model.get("alerts", [])
    top_headlines = [a.get("headline", "") for a in alerts[:2]]

    return {
        "available": True,
        "date": digest_date,
        "risk_tone": risk_tone,
        "total_alerts": total_alerts,
        "geri_value": geri.get("value"),
        "geri_band": geri.get("band"),
        "top_headlines": top_headlines,
        "is_delayed": True
    }
