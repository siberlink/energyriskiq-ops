import json
import logging
from datetime import datetime, timedelta, date
from typing import Optional
from src.db.db import execute_query, execute_one, execute_production_query, execute_production_one

logger = logging.getLogger(__name__)

PLAN_LEVELS = {"free": 0, "personal": 1, "trader": 2, "pro": 3, "enterprise": 4}

ERIQ_PLAN_CONFIG = {
    "free": {
        "max_questions_per_day": 3,
        "modes": ["explain"],
        "max_response_tokens": 1200,
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
        "max_response_tokens": 2000,
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
        "max_response_tokens": 3000,
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
        "max_response_tokens": 4000,
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
        "max_response_tokens": 5000,
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


def _parse_json(val):
    if val is None:
        return None
    if isinstance(val, dict) or isinstance(val, list):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:
            return None
    return None


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
        "analytics_insights": None,
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
        ctx["analytics_insights"] = _get_analytics_insights()

    except Exception as e:
        logger.error(f"Error building ERIQ context for user {user_id}: {e}", exc_info=True)
        ctx["data_quality"]["error"] = str(e)

    return ctx


def _get_geri_context(config: dict) -> dict:
    days = min(config["history_days"], 90)
    if config.get("delayed"):
        rows = execute_production_query("""
            SELECT date, value, band, trend_1d, trend_7d, interpretation, components
            FROM intel_indices_daily
            WHERE index_id = 'global:geo_energy_risk' AND date < CURRENT_DATE
            ORDER BY date DESC
            LIMIT %s
        """, (days,))
    else:
        rows = execute_production_query("""
            SELECT date, value, band, trend_1d, trend_7d, interpretation, components
            FROM intel_indices_daily
            WHERE index_id = 'global:geo_energy_risk'
            ORDER BY date DESC
            LIMIT %s
        """, (days,))
    if not rows:
        return {"available": False}

    latest = dict(rows[0])
    val = float(latest.get("value", 0))
    latest["band"] = _geri_band(val)
    components = _parse_json(latest.get("components"))

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

    if config.get("show_pillars") and components:
        normalized = components.get("normalized", {})
        weights = components.get("weights", {})
        result["current"]["pillars"] = {
            "high_impact": {"value": normalized.get("high_impact", 0), "weight": weights.get("high_impact", 0.4)},
            "regional_spike": {"value": normalized.get("regional_spike", 0), "weight": weights.get("regional_spike", 0.25)},
            "region_concentration": {"value": normalized.get("region_concentration", 0), "weight": weights.get("region_concentration", 0.15)},
            "asset_risk": {"value": normalized.get("asset_risk", 0), "weight": weights.get("asset_risk", 0.2)},
        }
        result["current"]["total_alerts"] = components.get("total_alerts", 0)
        result["current"]["avg_severity"] = components.get("avg_severity", 0)

    if config.get("show_drivers") and components:
        top_drivers = components.get("top_drivers", [])
        result["current"]["top_drivers"] = []
        for d in top_drivers[:7]:
            result["current"]["top_drivers"].append({
                "headline": d.get("headline", ""),
                "category": d.get("category", ""),
                "region": d.get("region", ""),
                "cluster": d.get("cluster", ""),
                "severity": d.get("severity", 0),
                "risk_score": round(d.get("risk_score", 0), 3),
            })
        top_regions = components.get("top_regions", [])
        result["current"]["top_regions"] = top_regions[:5]
        regional_weighting = components.get("regional_weighting", {})
        if regional_weighting:
            dist = regional_weighting.get("distribution", {})
            result["current"]["regional_distribution"] = {
                k: {"share_pct": v.get("share_pct", 0), "alert_count": v.get("alert_count", 0)}
                for k, v in dist.items()
            }

    if config.get("show_regime") and components:
        result["current"]["asset_spikes"] = components.get("asset_spikes", 0)
        result["current"]["regional_spikes"] = components.get("regional_spikes", 0)
        result["current"]["insufficient_history"] = components.get("insufficient_history", False)

    for r in rows[1:]:
        v = float(r.get("value", 0))
        result["history"].append({
            "date": str(r.get("date", "")),
            "value": v,
            "band": _geri_band(v),
            "trend_1d": float(r.get("trend_1d", 0) or 0),
        })

    return result


def _get_eeri_context(config: dict) -> dict:
    days = min(config["history_days"], 90)
    if config.get("delayed"):
        rows = execute_production_query("""
            SELECT date, value, band, trend_1d, trend_7d, interpretation, components, drivers
            FROM reri_indices_daily
            WHERE index_id = 'europe:eeri' AND date < CURRENT_DATE
            ORDER BY date DESC
            LIMIT %s
        """, (days,))
    else:
        rows = execute_production_query("""
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
    components = _parse_json(latest.get("components"))
    drivers_raw = _parse_json(latest.get("drivers"))

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

    if config.get("show_pillars") and components:
        weights = components.get("weights", {})
        result["current"]["pillars"] = {}
        for key in ["reri_eu", "theme_pressure", "asset_transmission", "contagion"]:
            comp_data = components.get(key, {})
            if isinstance(comp_data, dict):
                result["current"]["pillars"][key] = {
                    "value": comp_data.get("value", comp_data.get("raw", 0)),
                    "normalized": comp_data.get("normalized", 0),
                    "weight": weights.get(key, 0),
                }

    if config.get("show_drivers") and drivers_raw:
        result["current"]["top_drivers"] = []
        driver_list = drivers_raw if isinstance(drivers_raw, list) else components.get("top_drivers", [])
        for d in driver_list[:7]:
            result["current"]["top_drivers"].append({
                "headline": d.get("headline", ""),
                "category": d.get("category", ""),
                "severity": d.get("severity", 0),
                "score": round(d.get("score", 0), 3),
                "confidence": d.get("confidence", 0),
            })

    for r in rows[1:]:
        v = float(r.get("value", 0))
        result["history"].append({
            "date": str(r.get("date", "")),
            "value": v,
            "band": _eeri_band(v),
            "trend_1d": float(r.get("trend_1d", 0) or 0),
        })

    return result


def _get_egsi_m_context(config: dict) -> dict:
    days = min(config["history_days"], 90)
    if config.get("delayed"):
        rows = execute_production_query("""
            SELECT index_date as date, index_value as value, band, trend_1d, trend_7d,
                   interpretation, components_json
            FROM egsi_m_daily
            WHERE index_date < CURRENT_DATE
            ORDER BY index_date DESC
            LIMIT %s
        """, (days,))
    else:
        rows = execute_production_query("""
            SELECT index_date as date, index_value as value, band, trend_1d, trend_7d,
                   interpretation, components_json
            FROM egsi_m_daily
            ORDER BY index_date DESC
            LIMIT %s
        """, (days,))
    if not rows:
        return {"available": False}

    latest = dict(rows[0])
    val = float(latest.get("value", 0))
    latest["band"] = _egsi_band(val)
    components = _parse_json(latest.get("components_json"))

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

    if config.get("show_pillars") and components:
        weights = components.get("weights", {})
        result["current"]["pillars"] = {}
        for key in ["reri_eu", "theme_pressure", "chokepoint_factor", "asset_transmission"]:
            comp_data = components.get(key, {})
            if isinstance(comp_data, dict):
                result["current"]["pillars"][key] = {
                    "raw": comp_data.get("raw", 0),
                    "normalized": comp_data.get("normalized", 0),
                    "contribution": comp_data.get("contribution", 0),
                    "weight": weights.get(key, 0),
                }

    if config.get("show_drivers") and components:
        top_drivers = components.get("top_drivers", [])
        result["current"]["top_drivers"] = []
        for d in top_drivers[:5]:
            result["current"]["top_drivers"].append({
                "headline": d.get("headline", ""),
                "category": d.get("category", ""),
                "region": d.get("region", ""),
                "severity": d.get("severity", 0),
                "score": round(d.get("score", 0), 3),
            })

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
    if config.get("delayed"):
        rows = execute_production_query("""
            SELECT index_date as date, index_value as value, band, trend_1d, trend_7d,
                   interpretation, components_json
            FROM egsi_s_daily
            WHERE index_date < CURRENT_DATE
            ORDER BY index_date DESC
            LIMIT %s
        """, (days,))
    else:
        rows = execute_production_query("""
            SELECT index_date as date, index_value as value, band, trend_1d, trend_7d,
                   interpretation, components_json
            FROM egsi_s_daily
            ORDER BY index_date DESC
            LIMIT %s
        """, (days,))
    if not rows:
        return {"available": False}

    latest = dict(rows[0])
    val = float(latest.get("value", 0))
    latest["band"] = _egsi_band(val)
    components = _parse_json(latest.get("components_json"))

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

    if config.get("show_pillars") and components:
        result["current"]["pillars"] = {}
        for key in ["storage", "flows", "price", "alerts", "winter_readiness"]:
            comp_data = components.get(key, {})
            if isinstance(comp_data, dict):
                result["current"]["pillars"][key] = {
                    "contribution": comp_data.get("contribution", 0),
                }
                if key == "storage":
                    result["current"]["pillars"][key]["level_pct"] = comp_data.get("level_pct", 0)
                    result["current"]["pillars"][key]["target_pct"] = comp_data.get("target_pct", 0)
                    result["current"]["pillars"][key]["stress_raw"] = comp_data.get("stress_raw", 0)
                elif key == "price":
                    result["current"]["pillars"][key]["ttf_current"] = comp_data.get("ttf_current", 0)
                    result["current"]["pillars"][key]["ttf_ma7"] = comp_data.get("ttf_ma7", 0)
                    result["current"]["pillars"][key]["volatility_raw"] = comp_data.get("volatility_raw", 0)
                elif key == "flows":
                    result["current"]["pillars"][key]["injection_rate"] = comp_data.get("injection_rate", 0)

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
        rows = execute_production_query("""
            SELECT id, alert_type, scope_region, scope_assets, severity, headline,
                   category, confidence, created_at, classification
            FROM alert_events
            WHERE created_at < NOW() - INTERVAL '24 hours'
            ORDER BY created_at DESC, severity DESC
            LIMIT %s
        """, (limit,))
    else:
        rows = execute_production_query("""
            SELECT id, alert_type, scope_region, scope_assets, severity, headline,
                   category, confidence, created_at, classification
            FROM alert_events
            ORDER BY created_at DESC, severity DESC
            LIMIT %s
        """, (limit,))

    if not rows:
        return []

    alerts = []
    for r in rows:
        assets_val = r.get("scope_assets")
        if isinstance(assets_val, list):
            assets_list = assets_val
        elif isinstance(assets_val, str) and assets_val.startswith("{"):
            assets_list = [a.strip() for a in assets_val.strip("{}").split(",") if a.strip()]
        else:
            assets_list = []

        alerts.append({
            "headline": r["headline"],
            "severity": r["severity"],
            "category": r.get("category", ""),
            "region": r.get("scope_region", "Global"),
            "alert_type": r.get("alert_type", ""),
            "assets": assets_list,
            "confidence": float(r["confidence"]) if r.get("confidence") else 0,
            "classification": r.get("classification", ""),
            "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
        })
    return alerts


def _get_asset_context(config: dict) -> dict:
    days = config["asset_days"]
    brent = execute_production_query(
        "SELECT date, brent_price, brent_change_pct, wti_price, brent_wti_spread FROM oil_price_snapshots ORDER BY date DESC LIMIT %s",
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

    def fmt(rows, fields):
        if not rows:
            return []
        result = []
        for r in rows:
            entry = {"date": str(r.get("date", ""))}
            for f in fields:
                v = r.get(f)
                entry[f] = float(v) if v is not None else None
            result.append(entry)
        return result

    assets = {
        "brent": fmt(brent, ["brent_price", "brent_change_pct", "wti_price", "brent_wti_spread"]),
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
    egsi_s = ctx["indices"].get("egsi_s", {})
    if not geri.get("available"):
        return None

    geri_val = geri["current"]["value"]
    eeri_val = eeri["current"]["value"] if eeri.get("available") else 0

    vix_val = 0
    vix_data = ctx["assets"].get("vix", [])
    if vix_data:
        vix_val = vix_data[0].get("vix_close", 0) or 0

    storage_pct = None
    storage_data = ctx["assets"].get("storage", [])
    if storage_data:
        storage_pct = storage_data[0].get("eu_storage_percent")

    egsi_s_val = egsi_s["current"]["value"] if egsi_s.get("available") else 0

    if geri_val >= 70 and vix_val >= 25:
        return "Shock"
    if egsi_s_val >= 60 and storage_pct and storage_pct < 40:
        return "Gas-Storage Stress"
    if eeri_val >= 70:
        return "European Energy Crisis"
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

    geri_values = [float(g.get("value", 0)) for g in geri_history[:14]]
    assets = ctx["assets"]
    correlations = {}

    for key, field in [("brent", "brent_price"), ("ttf", "ttf_price"), ("vix", "vix_close")]:
        data = assets.get(key, [])
        if len(data) >= 7:
            asset_values = [float(d.get(field, 0) or 0) for d in data[:14]]
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
    quality = {"overall": "good", "issues": [], "available_indices": []}

    for idx_name in ["geri", "eeri", "egsi_m", "egsi_s"]:
        idx = ctx["indices"].get(idx_name, {})
        if idx.get("available"):
            quality["available_indices"].append(idx_name.upper())
            cur_date = idx["current"].get("date", "")
            if cur_date:
                try:
                    d = datetime.strptime(cur_date, "%Y-%m-%d").date()
                    age = (date.today() - d).days
                    if age > 2:
                        quality["issues"].append(f"{idx_name.upper()} data is {age} days old")
                except Exception:
                    pass
        else:
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


def _get_analytics_insights() -> dict:
    try:
        top_questions = execute_production_query("""
            SELECT question, COUNT(*) as ask_count
            FROM eriq_conversations
            WHERE success = true AND created_at > NOW() - INTERVAL '14 days'
            GROUP BY question
            ORDER BY ask_count DESC
            LIMIT 10
        """)

        low_satisfaction = execute_production_query("""
            SELECT intent, mode, COUNT(*) as count,
                   ROUND(AVG(rating)::numeric, 2) as avg_rating
            FROM eriq_conversations
            WHERE rating IS NOT NULL AND rating <= 2
                  AND created_at > NOW() - INTERVAL '14 days'
            GROUP BY intent, mode
            ORDER BY count DESC
            LIMIT 5
        """)

        tag_summary = execute_production_query("""
            SELECT unnest(feedback_tags) as tag, COUNT(*) as count
            FROM eriq_conversations
            WHERE feedback_tags IS NOT NULL AND feedback_tags != '{}'
                  AND created_at > NOW() - INTERVAL '14 days'
            GROUP BY tag
            ORDER BY count DESC
            LIMIT 8
        """)

        return {
            "frequently_asked": [
                {"question": r["question"], "count": r["ask_count"]}
                for r in (top_questions or [])
            ],
            "low_satisfaction_patterns": [
                {"intent": r["intent"], "mode": r["mode"], "count": r["count"],
                 "avg_rating": float(r["avg_rating"]) if r.get("avg_rating") else None}
                for r in (low_satisfaction or [])
            ],
            "feedback_tags": [
                {"tag": r["tag"], "count": r["count"]}
                for r in (tag_summary or [])
            ],
        }
    except Exception as e:
        logger.warning(f"Analytics insights unavailable: {e}")
        return None


def format_context_for_prompt(ctx: dict) -> str:
    parts = []
    parts.append(f"=== ERIQ LIVE CONTEXT SNAPSHOT ({ctx['timestamp']}) ===")
    parts.append(f"User Plan: {ctx['plan'].upper()}")

    if ctx.get("risk_tone"):
        parts.append(f"Overall Risk Tone: {ctx['risk_tone']['tone']}")
    if ctx.get("regime"):
        parts.append(f"Current Regime Classification: {ctx['regime']}")

    dq = ctx.get("data_quality", {})
    if dq.get("available_indices"):
        parts.append(f"Active Indices: {', '.join(dq['available_indices'])}")

    for idx_key, idx_label in [("geri", "GERI (Global Energy Risk Index)"), ("eeri", "EERI (European Escalation Risk Index)"), ("egsi_m", "EGSI-M (Europe Gas Stress - Market)"), ("egsi_s", "EGSI-S (Europe Gas Stress - System)")]:
        idx = ctx["indices"].get(idx_key, {})
        if idx.get("available"):
            cur = idx["current"]
            parts.append(f"\n--- {idx_label} ---")
            parts.append(f"Current Value: {cur['value']:.1f} | Band: {cur['band']} | Date: {cur['date']}")
            parts.append(f"1-Day Change: {cur['trend_1d']:+.1f} | 7-Day Change: {cur['trend_7d']:+.1f}")

            if cur.get("interpretation"):
                interp = cur["interpretation"]
                if len(interp) > 500:
                    interp = interp[:500] + "..."
                parts.append(f"AI Interpretation: {interp}")

            if cur.get("pillars"):
                pillars = cur["pillars"]
                parts.append("Pillar Contributions:")
                for p_name, p_data in pillars.items():
                    if isinstance(p_data, dict):
                        val_str = ""
                        if "value" in p_data:
                            val_str = f"value={p_data['value']}"
                        elif "contribution" in p_data:
                            val_str = f"contribution={p_data['contribution']}"
                        if "normalized" in p_data:
                            val_str += f", normalized={p_data['normalized']}"
                        if "weight" in p_data:
                            val_str += f", weight={p_data['weight']}"
                        if "level_pct" in p_data:
                            val_str += f", storage_level={p_data['level_pct']}"
                        if "ttf_current" in p_data:
                            val_str += f", ttf={p_data['ttf_current']}"
                        parts.append(f"  {p_name}: {val_str}")

            if cur.get("top_drivers"):
                parts.append("Top Drivers:")
                for d in cur["top_drivers"]:
                    parts.append(f"  [{d.get('severity', 0)}/5] {d.get('headline', '')} (Category: {d.get('category', '')}, Region: {d.get('region', d.get('cluster', 'N/A'))})")

            if cur.get("top_regions"):
                regions_str = ", ".join([f"{r.get('region', 'N/A')}: {r.get('risk_total', 0):.2f}" for r in cur["top_regions"]])
                parts.append(f"Top Risk Regions: {regions_str}")

            if cur.get("regional_distribution"):
                parts.append("Regional Risk Distribution:")
                for region, rd in cur["regional_distribution"].items():
                    if rd.get("share_pct", 0) > 1:
                        parts.append(f"  {region}: {rd['share_pct']:.1f}% ({rd.get('alert_count', 0)} alerts)")

            if cur.get("total_alerts"):
                parts.append(f"Total Contributing Alerts: {cur['total_alerts']}")

            hist = idx.get("history", [])
            if hist:
                recent = hist[:7]
                hist_str = ", ".join([f"{h['date']}: {h['value']:.1f} ({h.get('band', _geri_band(h['value']) if idx_key in ['geri'] else '')})" for h in recent])
                parts.append(f"Recent History: {hist_str}")
        else:
            parts.append(f"\n--- {idx_label} ---")
            parts.append("Data: Not available")

    if ctx.get("alerts"):
        parts.append(f"\n--- RECENT ALERTS ({len(ctx['alerts'])} shown) ---")
        for a in ctx["alerts"][:15]:
            time_str = ""
            if a.get("created_at"):
                time_str = f" @ {a['created_at'][:16]}"
            parts.append(f"  [{a['severity']}/5] {a['headline']} (Region: {a.get('region', 'Global')}, Category: {a.get('category', 'N/A')}, Type: {a.get('alert_type', 'N/A')}{time_str})")
    else:
        parts.append("\n--- RECENT ALERTS ---")
        parts.append("No recent alerts available")

    assets = ctx.get("assets", {})
    if any(assets.get(k) for k in ["brent", "ttf", "vix", "eurusd", "storage"]):
        parts.append("\n--- ASSET SNAPSHOT ---")
        if assets.get("brent"):
            b = assets["brent"][0]
            price = b.get('brent_price', 'N/A')
            change = b.get('brent_change_pct', 'N/A')
            wti = b.get('wti_price', 'N/A')
            spread = b.get('brent_wti_spread', 'N/A')
            parts.append(f"Brent Crude: ${price}/bbl (Change: {change}%) | WTI: ${wti}/bbl | Spread: ${spread}")
            if len(assets["brent"]) > 1:
                hist_brent = [f"{b2.get('date', '?')}: ${b2.get('brent_price', 0)}" for b2 in assets["brent"][1:5]]
                parts.append(f"  Brent History: {', '.join(hist_brent)}")
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
        parts.append(f"\n--- ROLLING CORRELATIONS (GERI vs.) ---")
        for k, v in ctx["correlations"].items():
            label = {"brent": "Brent Crude", "ttf": "TTF Gas", "vix": "VIX"}.get(k, k.upper())
            parts.append(f"  {label}: {v:+.2f}")

    if ctx.get("betas"):
        parts.append(f"\n--- ROLLING BETAS (GERI sensitivity) ---")
        for k, v in ctx["betas"].items():
            label = {"brent": "Brent Crude", "ttf": "TTF Gas", "vix": "VIX"}.get(k, k.upper())
            parts.append(f"  {label}: {v:.3f}")

    if dq.get("issues"):
        parts.append(f"\n--- DATA QUALITY: {dq.get('overall', 'unknown').upper()} ---")
        for issue in dq["issues"]:
            parts.append(f"  Warning: {issue}")

    analytics = ctx.get("analytics_insights")
    if analytics:
        parts.append("\n--- ANALYTICS INSIGHTS (Self-Improvement Context) ---")
        if analytics.get("frequently_asked"):
            parts.append("Most frequently asked questions (last 14 days):")
            for faq in analytics["frequently_asked"][:5]:
                parts.append(f"  [{faq['count']}x] {faq['question']}")
        if analytics.get("low_satisfaction_patterns"):
            parts.append("Low-satisfaction patterns:")
            for lsp in analytics["low_satisfaction_patterns"]:
                parts.append(f"  intent={lsp['intent']}, mode={lsp['mode']}, count={lsp['count']}, avg_rating={lsp['avg_rating']}")
        if analytics.get("feedback_tags"):
            tags_str = ", ".join(f"{t['tag']}({t['count']})" for t in analytics["feedback_tags"])
            parts.append(f"Feedback tag distribution: {tags_str}")

    return "\n".join(parts)
