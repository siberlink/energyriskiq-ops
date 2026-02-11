import logging
from datetime import datetime, timedelta, date
from typing import Optional
from src.db.db import execute_query, execute_one

logger = logging.getLogger(__name__)

PLAN_LEVELS = {"free": 0, "personal": 1, "trader": 2, "pro": 3, "enterprise": 4}

ERIQ_PLAN_CONFIG = {
    "free": {
        "max_questions_per_day": 3,
        "modes": ["explain"],
        "max_response_tokens": 400,
        "history_days": 7,
        "alert_limit": 5,
        "asset_days": 3,
        "show_pillars": False,
        "show_drivers": False,
        "show_regime": False,
        "show_correlations": False,
        "show_betas": False,
        "delayed": True,
    },
    "personal": {
        "max_questions_per_day": 15,
        "modes": ["explain", "interpret"],
        "max_response_tokens": 600,
        "history_days": 30,
        "alert_limit": 10,
        "asset_days": 7,
        "show_pillars": True,
        "show_drivers": False,
        "show_regime": False,
        "show_correlations": True,
        "show_betas": False,
        "delayed": False,
    },
    "trader": {
        "max_questions_per_day": 60,
        "modes": ["explain", "interpret", "decide_support"],
        "max_response_tokens": 1000,
        "history_days": 90,
        "alert_limit": 20,
        "asset_days": 14,
        "show_pillars": True,
        "show_drivers": True,
        "show_regime": True,
        "show_correlations": True,
        "show_betas": True,
        "delayed": False,
    },
    "pro": {
        "max_questions_per_day": 200,
        "modes": ["explain", "interpret", "decide_support"],
        "max_response_tokens": 2000,
        "history_days": 180,
        "alert_limit": 30,
        "asset_days": 30,
        "show_pillars": True,
        "show_drivers": True,
        "show_regime": True,
        "show_correlations": True,
        "show_betas": True,
        "delayed": False,
    },
    "enterprise": {
        "max_questions_per_day": 999999,
        "modes": ["explain", "interpret", "decide_support"],
        "max_response_tokens": 3000,
        "history_days": 365,
        "alert_limit": 50,
        "asset_days": 60,
        "show_pillars": True,
        "show_drivers": True,
        "show_regime": True,
        "show_correlations": True,
        "show_betas": True,
        "delayed": False,
    },
}


def get_user_plan(user_id: int) -> str:
    row = execute_one(
        "SELECT plan FROM user_plans WHERE user_id = %s ORDER BY created_at DESC LIMIT 1",
        (user_id,)
    )
    return row["plan"] if row else "free"


def get_plan_config(plan: str) -> dict:
    return ERIQ_PLAN_CONFIG.get(plan, ERIQ_PLAN_CONFIG["free"])


def get_questions_used_today(user_id: int) -> int:
    today = date.today()
    row = execute_one(
        "SELECT COUNT(*) as cnt FROM eriq_conversations WHERE user_id = %s AND created_at >= %s",
        (user_id, today)
    )
    return row["cnt"] if row else 0


def build_context(user_id: int, plan: str, question: str) -> dict:
    config = get_plan_config(plan)
    ctx = {
        "timestamp": datetime.utcnow().isoformat(),
        "plan": plan,
        "indices": {},
        "alerts": [],
        "assets": {},
        "regime": None,
        "risk_tone": None,
        "correlations": None,
        "betas": None,
        "data_quality": {},
    }

    try:
        ctx["indices"]["geri"] = _get_geri_context(config)
        ctx["indices"]["eeri"] = _get_eeri_context(config)
        ctx["indices"]["egsi_m"] = _get_egsi_m_context(config)
        ctx["indices"]["egsi_s"] = _get_egsi_s_context(config)
        ctx["alerts"] = _get_alerts_context(config)
        ctx["assets"] = _get_asset_context(config)
        ctx["risk_tone"] = _compute_risk_tone(ctx["indices"].get("geri"))
        ctx["regime"] = _compute_regime(ctx)

        if config["show_correlations"]:
            ctx["correlations"] = _compute_correlations(ctx)
        if config["show_betas"]:
            ctx["betas"] = _compute_betas(ctx)

        ctx["data_quality"] = _assess_data_quality(ctx)

    except Exception as e:
        logger.error(f"Error building ERIQ context for user {user_id}: {e}")
        ctx["data_quality"]["error"] = str(e)

    return ctx


def _get_geri_context(config: dict) -> dict:
    days = min(config["history_days"], 90)
    rows = execute_query("""
        SELECT date, value, band, trend_1d, trend_7d, interpretation, components
        FROM intel_indices_daily
        WHERE index_id = 'geri'
        ORDER BY date DESC
        LIMIT %s
    """, (days,))
    if not rows:
        return {"available": False}

    latest = dict(rows[0])
    val = float(latest.get("value", 0))
    latest["band"] = _geri_band(val)
    result = {
        "available": True,
        "current": {
            "value": val,
            "band": latest["band"],
            "trend_1d": float(latest.get("trend_1d", 0) or 0),
            "trend_7d": float(latest.get("trend_7d", 0) or 0),
            "date": str(latest.get("date", "")),
            "interpretation": latest.get("interpretation", ""),
        },
        "history": [],
    }

    if config.get("show_pillars") and latest.get("components"):
        import json
        comps = latest["components"]
        if isinstance(comps, str):
            try:
                comps = json.loads(comps)
            except Exception:
                comps = {}
        result["current"]["pillars"] = comps

    for r in rows[1:]:
        v = float(r.get("value", 0))
        result["history"].append({
            "date": str(r.get("date", "")),
            "value": v,
            "band": _geri_band(v),
        })

    return result


def _get_eeri_context(config: dict) -> dict:
    days = min(config["history_days"], 90)
    rows = execute_query("""
        SELECT date, value, band, trend_1d, trend_7d, interpretation, components, drivers
        FROM reri_indices_daily
        WHERE index_id = 'europe:eeri'
        ORDER BY date DESC
        LIMIT %s
    """, (days,))
    if not rows:
        return {"available": False}

    latest = dict(rows[0])
    val = float(latest.get("value", 0))
    latest["band"] = _eeri_band(val)
    result = {
        "available": True,
        "current": {
            "value": val,
            "band": latest["band"],
            "trend_1d": float(latest.get("trend_1d", 0) or 0),
            "trend_7d": float(latest.get("trend_7d", 0) or 0),
            "date": str(latest.get("date", "")),
            "interpretation": latest.get("interpretation", ""),
        },
        "history": [],
    }

    if config.get("show_pillars") and latest.get("components"):
        import json
        comps = latest["components"]
        if isinstance(comps, str):
            try:
                comps = json.loads(comps)
            except Exception:
                comps = {}
        result["current"]["pillars"] = comps

    if config.get("show_drivers") and latest.get("drivers"):
        import json
        drivers = latest["drivers"]
        if isinstance(drivers, str):
            try:
                drivers = json.loads(drivers)
            except Exception:
                drivers = []
        result["current"]["drivers"] = drivers

    for r in rows[1:]:
        v = float(r.get("value", 0))
        result["history"].append({
            "date": str(r.get("date", "")),
            "value": v,
            "band": _eeri_band(v),
        })

    return result


def _get_egsi_m_context(config: dict) -> dict:
    days = min(config["history_days"], 90)
    rows = execute_query("""
        SELECT index_date as date, index_value as value, band, trend_1d, trend_7d, interpretation
        FROM egsi_m_daily
        ORDER BY index_date DESC
        LIMIT %s
    """, (days,))
    if not rows:
        return {"available": False}

    latest = dict(rows[0])
    val = float(latest.get("value", 0))
    latest["band"] = _egsi_band(val)
    result = {
        "available": True,
        "current": {
            "value": val,
            "band": latest["band"],
            "trend_1d": float(latest.get("trend_1d", 0) or 0),
            "trend_7d": float(latest.get("trend_7d", 0) or 0),
            "date": str(latest.get("date", "")),
            "interpretation": latest.get("interpretation", ""),
        },
        "history": [],
    }

    for r in rows[1:]:
        v = float(r.get("value", 0))
        result["history"].append({
            "date": str(r.get("date", "")),
            "value": v,
            "band": _egsi_band(v),
        })

    return result


def _get_egsi_s_context(config: dict) -> dict:
    days = min(config["history_days"], 90)
    rows = execute_query("""
        SELECT index_date as date, index_value as value, band, trend_1d, trend_7d, interpretation
        FROM egsi_s_daily
        ORDER BY index_date DESC
        LIMIT %s
    """, (days,))
    if not rows:
        return {"available": False}

    latest = dict(rows[0])
    val = float(latest.get("value", 0))
    latest["band"] = _egsi_band(val)
    result = {
        "available": True,
        "current": {
            "value": val,
            "band": latest["band"],
            "trend_1d": float(latest.get("trend_1d", 0) or 0),
            "trend_7d": float(latest.get("trend_7d", 0) or 0),
            "date": str(latest.get("date", "")),
            "interpretation": latest.get("interpretation", ""),
        },
        "history": [],
    }

    for r in rows[1:]:
        v = float(r.get("value", 0))
        result["history"].append({
            "date": str(r.get("date", "")),
            "value": v,
            "band": _egsi_band(v),
        })

    return result


def _get_alerts_context(config: dict) -> list:
    limit = config["alert_limit"]
    if config.get("delayed"):
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

    if not rows:
        return []

    alerts = []
    for r in rows:
        alerts.append({
            "headline": r["headline"],
            "severity": r["severity"],
            "category": r["category"],
            "region": r["scope_region"],
            "assets": r["scope_assets"] if r["scope_assets"] else [],
            "confidence": float(r["confidence"]) if r["confidence"] else 0,
            "classification": r.get("classification"),
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        })
    return alerts


def _get_asset_context(config: dict) -> dict:
    days = config["asset_days"]
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

    def fmt(rows, fields):
        if not rows:
            return []
        result = []
        for r in rows:
            entry = {"date": str(r.get("date", ""))}
            for f in fields:
                entry[f] = float(r[f]) if r.get(f) is not None else None
            result.append(entry)
        return result

    assets = {
        "brent": fmt(brent, ["brent_price", "brent_change_pct"]),
        "ttf": fmt(ttf, ["ttf_price"]),
        "vix": fmt(vix, ["vix_close"]),
        "eurusd": fmt(eurusd, ["rate"]),
        "storage": [],
    }

    if storage:
        for r in storage:
            assets["storage"].append({
                "date": str(r.get("date", "")),
                "eu_storage_percent": float(r["eu_storage_percent"]) if r.get("eu_storage_percent") is not None else None,
                "risk_band": r.get("risk_band"),
            })

    return assets


def _compute_risk_tone(geri: Optional[dict]) -> Optional[dict]:
    if not geri or not geri.get("available"):
        return None
    val = geri["current"]["value"]
    trend = geri["current"]["trend_1d"]
    if val >= 70:
        return {"tone": "Escalating", "color": "red"}
    if val >= 50:
        if trend > 0:
            return {"tone": "Elevated & Rising", "color": "orange"}
        return {"tone": "Elevated", "color": "yellow"}
    if val >= 30:
        return {"tone": "Moderate", "color": "yellow"}
    if trend < 0:
        return {"tone": "Stabilizing", "color": "green"}
    return {"tone": "Low", "color": "green"}


def _compute_regime(ctx: dict) -> Optional[str]:
    geri = ctx["indices"].get("geri", {})
    eeri = ctx["indices"].get("eeri", {})
    if not geri.get("available") or not eeri.get("available"):
        return None

    geri_val = geri["current"]["value"]
    eeri_val = eeri["current"]["value"]

    vix_val = 0
    vix_data = ctx["assets"].get("vix", [])
    if vix_data:
        vix_val = vix_data[0].get("vix_close", 0) or 0

    storage_pct = None
    storage_data = ctx["assets"].get("storage", [])
    if storage_data:
        storage_pct = storage_data[0].get("eu_storage_percent")

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


def _compute_correlations(ctx: dict) -> Optional[dict]:
    geri = ctx["indices"].get("geri", {})
    if not geri.get("available"):
        return None
    geri_history = [geri["current"]] + geri.get("history", [])
    if len(geri_history) < 7:
        return None

    geri_values = [float(g.get("value", 0)) for g in geri_history[:7]]
    assets = ctx["assets"]
    correlations = {}

    for key, field in [("brent", "brent_price"), ("ttf", "ttf_price"), ("vix", "vix_close")]:
        data = assets.get(key, [])
        if len(data) >= 7:
            asset_values = [float(d.get(field, 0) or 0) for d in data[:7]]
            n = min(len(geri_values), len(asset_values))
            if n < 5:
                continue
            gv = geri_values[:n]
            av = asset_values[:n]
            mean_g = sum(gv) / n
            mean_a = sum(av) / n
            cov = sum((gv[i] - mean_g) * (av[i] - mean_a) for i in range(n)) / n
            std_g = (sum((g - mean_g) ** 2 for g in gv) / n) ** 0.5
            std_a = (sum((a - mean_a) ** 2 for a in av) / n) ** 0.5
            if std_g > 0 and std_a > 0:
                correlations[key] = round(cov / (std_g * std_a), 2)

    return correlations if correlations else None


def _compute_betas(ctx: dict) -> Optional[dict]:
    geri = ctx["indices"].get("geri", {})
    if not geri.get("available"):
        return None
    geri_history = [geri["current"]] + geri.get("history", [])
    if len(geri_history) < 14:
        return None

    window = min(30, len(geri_history))
    geri_vals = [float(g.get("value", 0)) for g in geri_history[:window]]
    assets = ctx["assets"]
    betas = {}

    for key, field in [("brent", "brent_price"), ("ttf", "ttf_price"), ("vix", "vix_close")]:
        data = assets.get(key, [])
        if len(data) >= window:
            asset_vals = [float(d.get(field, 0) or 0) for d in data[:window]]
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


def _assess_data_quality(ctx: dict) -> dict:
    quality = {"overall": "good", "issues": []}

    for idx_name in ["geri", "eeri", "egsi_m", "egsi_s"]:
        idx = ctx["indices"].get(idx_name, {})
        if not idx.get("available"):
            quality["issues"].append(f"{idx_name.upper()} data unavailable")

    for asset_name in ["brent", "ttf", "vix", "eurusd", "storage"]:
        data = ctx["assets"].get(asset_name, [])
        if not data:
            quality["issues"].append(f"{asset_name} asset data missing")

    if not ctx["alerts"]:
        quality["issues"].append("No recent alerts available")

    if len(quality["issues"]) >= 3:
        quality["overall"] = "degraded"
    elif quality["issues"]:
        quality["overall"] = "partial"

    return quality


def _geri_band(value: float) -> str:
    if value >= 80:
        return "CRITICAL"
    if value >= 60:
        return "SEVERE"
    if value >= 40:
        return "ELEVATED"
    if value >= 20:
        return "MODERATE"
    return "LOW"


def _eeri_band(value: float) -> str:
    if value >= 80:
        return "CRITICAL"
    if value >= 60:
        return "SEVERE"
    if value >= 40:
        return "ELEVATED"
    if value >= 20:
        return "MODERATE"
    return "LOW"


def _egsi_band(value: float) -> str:
    if value >= 80:
        return "CRITICAL"
    if value >= 60:
        return "HIGH"
    if value >= 40:
        return "ELEVATED"
    if value >= 20:
        return "NORMAL"
    return "LOW"


def format_context_for_prompt(ctx: dict) -> str:
    parts = []
    parts.append(f"=== ERIQ CONTEXT SNAPSHOT ({ctx['timestamp']}) ===")
    parts.append(f"User Plan: {ctx['plan'].upper()}")

    if ctx.get("risk_tone"):
        parts.append(f"Overall Risk Tone: {ctx['risk_tone']['tone']}")
    if ctx.get("regime"):
        parts.append(f"Current Regime: {ctx['regime']}")

    for idx_key, idx_label in [("geri", "GERI"), ("eeri", "EERI"), ("egsi_m", "EGSI-M"), ("egsi_s", "EGSI-S")]:
        idx = ctx["indices"].get(idx_key, {})
        if idx.get("available"):
            cur = idx["current"]
            parts.append(f"\n--- {idx_label} ---")
            parts.append(f"Value: {cur['value']:.1f} | Band: {cur['band']} | Date: {cur['date']}")
            parts.append(f"1-Day Trend: {cur['trend_1d']:+.1f} | 7-Day Trend: {cur['trend_7d']:+.1f}")
            if cur.get("interpretation"):
                interp = cur["interpretation"]
                if len(interp) > 300:
                    interp = interp[:300] + "..."
                parts.append(f"AI Interpretation: {interp}")
            if cur.get("pillars"):
                pillars = cur["pillars"]
                if isinstance(pillars, dict):
                    pillar_strs = [f"{k}: {v}" for k, v in pillars.items()]
                    parts.append(f"Pillar Components: {', '.join(pillar_strs)}")
            if cur.get("drivers"):
                drivers = cur["drivers"]
                if isinstance(drivers, list):
                    for d in drivers[:5]:
                        if isinstance(d, dict):
                            parts.append(f"  Driver: {d.get('label', d.get('headline', str(d)))}")

            hist = idx.get("history", [])
            if hist:
                recent = hist[:5]
                hist_str = ", ".join([f"{h['date']}: {h['value']:.1f}" for h in recent])
                parts.append(f"Recent History: {hist_str}")

    if ctx.get("alerts"):
        parts.append(f"\n--- RECENT ALERTS ({len(ctx['alerts'])} total) ---")
        for a in ctx["alerts"][:10]:
            parts.append(f"  [{a['severity']}] {a['headline']} (Region: {a.get('region', 'Global')}, Category: {a.get('category', 'N/A')})")

    assets = ctx.get("assets", {})
    if any(assets.get(k) for k in ["brent", "ttf", "vix", "eurusd", "storage"]):
        parts.append("\n--- ASSET SNAPSHOT ---")
        if assets.get("brent"):
            b = assets["brent"][0]
            parts.append(f"Brent Crude: ${b.get('brent_price', 'N/A')}/bbl (Change: {b.get('brent_change_pct', 'N/A')}%)")
        if assets.get("ttf"):
            t = assets["ttf"][0]
            parts.append(f"TTF Gas: EUR {t.get('ttf_price', 'N/A')}/MWh")
        if assets.get("vix"):
            v = assets["vix"][0]
            parts.append(f"VIX: {v.get('vix_close', 'N/A')}")
        if assets.get("eurusd"):
            e = assets["eurusd"][0]
            parts.append(f"EUR/USD: {e.get('rate', 'N/A')}")
        if assets.get("storage"):
            s = assets["storage"][0]
            parts.append(f"EU Gas Storage: {s.get('eu_storage_percent', 'N/A')}% (Band: {s.get('risk_band', 'N/A')})")

    if ctx.get("correlations"):
        parts.append(f"\n--- 7-DAY CORRELATIONS (GERI vs.) ---")
        for k, v in ctx["correlations"].items():
            parts.append(f"  {k.upper()}: {v:+.2f}")

    if ctx.get("betas"):
        parts.append(f"\n--- ROLLING BETAS ---")
        for k, v in ctx["betas"].items():
            parts.append(f"  {k.upper()}: {v:.3f}")

    dq = ctx.get("data_quality", {})
    if dq.get("issues"):
        parts.append(f"\n--- DATA QUALITY: {dq.get('overall', 'unknown').upper()} ---")
        for issue in dq["issues"]:
            parts.append(f"  Warning: {issue}")

    return "\n".join(parts)
