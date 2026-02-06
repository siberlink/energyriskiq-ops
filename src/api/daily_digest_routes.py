import os
import json
import logging
from datetime import datetime, timedelta, date
from fastapi import APIRouter, Header, HTTPException
from typing import Optional

from src.db.db import execute_query, execute_one
from src.api.user_routes import verify_user_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/digest", tags=["daily-digest"])

PLAN_LEVELS = {"free": 0, "personal": 1, "trader": 2, "pro": 3, "enterprise": 4}


def get_user_plan(user_id: int) -> str:
    row = execute_one(
        "SELECT plan FROM user_plans WHERE user_id = %s ORDER BY created_at DESC LIMIT 1",
        (user_id,)
    )
    return row["plan"] if row else "free"


def get_alerts(limit: int = 20, is_delayed: bool = False):
    if is_delayed:
        start = date.today() - timedelta(days=2)
        end = date.today() - timedelta(days=1)
    else:
        start = date.today() - timedelta(days=1)
        end = date.today() + timedelta(days=1)
    rows = execute_query("""
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
    rows = execute_query("""
        SELECT date, value, band, trend_1d, trend_7d, interpretation, components
        FROM intel_indices_daily
        WHERE index_id = %s
        ORDER BY date DESC
        LIMIT %s
    """, (index_id, days))
    return [dict(r) for r in rows] if rows else []


def get_eeri_snapshot(days: int = 2):
    rows = execute_query("""
        SELECT date, value, band, trend_1d, trend_7d, interpretation, components, drivers
        FROM reri_indices_daily
        WHERE index_id = 'europe:eeri'
        ORDER BY date DESC
        LIMIT %s
    """, (days,))
    return [dict(r) for r in rows] if rows else []


def get_egsi_snapshot(days: int = 2):
    rows = execute_query("""
        SELECT index_date as date, index_value as value, band, trend_1d, trend_7d, interpretation
        FROM egsi_m_daily
        ORDER BY index_date DESC
        LIMIT %s
    """, (days,))
    return [dict(r) for r in rows] if rows else []


def get_asset_snapshots(days: int = 7):
    brent = execute_query(
        "SELECT date, brent_price, brent_change_pct FROM oil_price_snapshots ORDER BY date DESC LIMIT %s",
        (days,)
    )
    ttf = execute_query(
        "SELECT date, ttf_price FROM ttf_gas_snapshots ORDER BY date DESC LIMIT %s",
        (days,)
    )
    vix = execute_query(
        "SELECT date, vix_close FROM vix_snapshots ORDER BY date DESC LIMIT %s",
        (days,)
    )
    eurusd = execute_query(
        "SELECT date, rate FROM eurusd_snapshots ORDER BY date DESC LIMIT %s",
        (days,)
    )
    storage = execute_query(
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


def generate_ai_digest(plan: str, alerts, geri, eeri, egsi, asset_changes, correlations, betas, risk_tone, regime):
    try:
        from openai import OpenAI
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


@router.get("/daily")
def get_daily_digest(x_user_token: Optional[str] = Header(None)):
    session = verify_user_session(x_user_token)
    user_id = session["user_id"]
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

    ai_narrative = generate_ai_digest(plan, alerts, geri, eeri, egsi, asset_changes, correlations, betas, risk_tone, regime)

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

    forward_watchlist = None
    if plan_level >= 2:
        watchlist_items = []
        for a in alerts[:5]:
            if a.get("severity", 0) >= 7:
                watchlist_items.append({
                    "headline": a["headline"],
                    "region": a["region"],
                    "severity": a["severity"],
                    "watch_reason": "High severity event requiring monitoring"
                })
        if geri and geri[0].get("value", 0) > 60:
            watchlist_items.append({
                "headline": "GERI elevated above 60",
                "region": "Global",
                "severity": 8,
                "watch_reason": "Global risk index in elevated territory"
            })
        if storage_pct < 40:
            watchlist_items.append({
                "headline": f"EU gas storage at {storage_pct:.1f}%",
                "region": "Europe",
                "severity": 7,
                "watch_reason": "Storage below seasonal comfort level"
            })
        forward_watchlist = watchlist_items[:5]

    probability_scoring = None
    volatility_outlook = None
    if plan_level >= 2:
        geri_values = [g.get("value", 0) for g in geri[:7]] if geri else []
        if len(geri_values) >= 3:
            avg_7d = sum(geri_values) / len(geri_values)
            std_7d = (sum((v - avg_7d) ** 2 for v in geri_values) / len(geri_values)) ** 0.5
            probability_scoring = {
                "escalation_probability": min(95, max(5, int(geri_val * 0.8 + std_7d * 5))),
                "de_escalation_probability": min(95, max(5, int(100 - geri_val * 0.8))),
                "stability_probability": min(95, max(5, int(60 - std_7d * 10))) if std_7d < 5 else max(5, int(30 - std_7d * 3)),
                "methodology": "Based on GERI level, 7-day volatility, and trend direction"
            }
            vol_regime = "low" if std_7d < 2 else "moderate" if std_7d < 5 else "high" if std_7d < 10 else "extreme"
            volatility_outlook = {
                "current_vol": round(std_7d, 2),
                "regime": vol_regime,
                "vix_level": vix_val,
                "outlook": f"{'Calm conditions' if vol_regime == 'low' else 'Moderate fluctuations' if vol_regime == 'moderate' else 'Elevated volatility' if vol_regime == 'high' else 'Extreme market stress'} expected in near term"
            }

    scenario_forecasts = None
    if plan_level >= 3:
        scenarios = []
        base_geri = geri_val
        scenarios.append({
            "scenario": "Base Case",
            "probability": probability_scoring["stability_probability"] if probability_scoring else 50,
            "geri_forecast": round(base_geri, 1),
            "description": "Current trajectory maintained with no major disruptions"
        })
        scenarios.append({
            "scenario": "Escalation",
            "probability": probability_scoring["escalation_probability"] if probability_scoring else 30,
            "geri_forecast": round(min(100, base_geri * 1.15), 1),
            "description": "Risk drivers intensify, supply disruptions or geopolitical escalation"
        })
        scenarios.append({
            "scenario": "De-escalation",
            "probability": probability_scoring["de_escalation_probability"] if probability_scoring else 20,
            "geri_forecast": round(max(0, base_geri * 0.85), 1),
            "description": "Risk factors ease, diplomatic progress or supply normalization"
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
