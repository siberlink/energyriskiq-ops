"""
GERI Live — Brent Intelligence Forecast Engine bridge.

Accepts x-user-token (main user session) and enforces GERI Live entitlement,
then calls the same internal scenario engine used by the standalone
Brent Intelligence Scenario Engine (brent_forecast_routes.py).
"""
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from src.api.geri_live_sub_routes import _get_user_from_token, user_has_geri_live
from src.api.brent_forecast_routes import (
    _market_snapshot,
    _compute_scenario,
    _match_analogs,
    _risk_score,
    _market_regime,
    _what_to_watch,
    _scenario_risk_line,
    _SUPPLY_SHOCKS,
    _DEMAND,
    _clamp,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["geri-live-brent-engine"])


def _require_geri_live(token: Optional[str]):
    user = _get_user_from_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    if not user_has_geri_live(user["id"]):
        raise HTTPException(status_code=403, detail="GERI Live subscription required")
    return user


@router.get("/api/geri-live/brent-engine/market")
async def geri_live_brent_market(x_user_token: Optional[str] = Header(None)):
    _require_geri_live(x_user_token)
    try:
        snap = _market_snapshot()
        return {"success": True, "market": snap}
    except Exception as e:
        logger.error(f"geri-live brent market: {e}")
        raise HTTPException(status_code=500, detail="Market data unavailable")


class BrentScenarioRequest(BaseModel):
    brent: Optional[float] = None
    geri_change_pct: float = 0.0
    vix_change_pct: float = 0.0
    gas_stress_pct: float = 0.0
    supply_scenario: str = "normal"
    demand_outlook: str = "neutral"


@router.post("/api/geri-live/brent-engine/scenario")
async def geri_live_brent_scenario(
    body: BrentScenarioRequest,
    x_user_token: Optional[str] = Header(None),
):
    _require_geri_live(x_user_token)
    snap = _market_snapshot()
    brent = (
        body.brent if body.brent and 10 < body.brent < 300
        else (snap.get("brent_intraday") or snap.get("brent", 75.0))
    )
    geri_pct = _clamp(body.geri_change_pct, -50, 100)
    vix_pct = _clamp(body.vix_change_pct, -50, 100)
    gas_pct = _clamp(body.gas_stress_pct, -50, 100)
    supply = body.supply_scenario if body.supply_scenario in _SUPPLY_SHOCKS else "normal"
    demand = body.demand_outlook if body.demand_outlook in _DEMAND else "neutral"

    horizons, attribution, total_pct = _compute_scenario(
        brent, geri_pct, vix_pct, gas_pct, supply, demand
    )
    bias = "bullish" if total_pct > 1.5 else "bearish" if total_pct < -1.5 else "neutral"

    drivers = []
    if abs(attribution["geri"]) > 0.5:
        drivers.append(
            ("Rising" if attribution["geri"] > 0 else "Falling") + " geopolitical risk (GERI)"
        )
    if abs(attribution["supply"]) > 0.5:
        drivers.append("Supply disruption: " + supply.replace("_", " ").title())
    if abs(attribution["gas_stress"]) > 0.5:
        drivers.append(
            ("Elevated" if attribution["gas_stress"] > 0 else "Easing") + " European gas stress"
        )
    if abs(attribution["vix"]) > 0.5:
        drivers.append(
            "Market fear adding a volatility premium"
            if attribution["vix"] > 0
            else "Market volatility weighing on demand outlook"
        )
    if abs(attribution["demand"]) > 0.5:
        drivers.append(f"{demand.title()} demand outlook")
    if not drivers:
        drivers.append("Conditions broadly unchanged from current market")

    interp_lines = [
        f"The model expects Brent to hold a {bias} tone across the selected horizons.",
        ("Primary support comes from: " if total_pct >= 0 else "Primary pressure comes from: ")
        + "; ".join(drivers) + ".",
        (
            "Market fear remains moderate, partially offsetting the geopolitical premium."
            if attribution["vix"] < 0 and attribution["geri"] > 0
            else "Volatility and risk signals are aligned, reinforcing the projected move."
            if (attribution["vix"] >= 0) == (attribution["geri"] >= 0)
            else "Cross-currents between risk drivers moderate the projected move."
        ),
    ]

    scenario_shift = geri_pct + _SUPPLY_SHOCKS.get(supply, 0) * 2

    return {
        "success": True,
        "brent": round(brent, 2),
        "horizons": horizons,
        "attribution": attribution,
        "interpretation_lines": interp_lines,
        "what_to_watch": _what_to_watch(snap, supply, total_pct),
        "scenario_risk": _scenario_risk_line(snap, total_pct, bias),
        "market_regime": _market_regime(snap),
        "analogs": _match_analogs(scenario_shift),
        "risk_score": _risk_score(snap, geri_pct, gas_pct, supply, demand),
        "market": snap,
        "as_of": datetime.utcnow().strftime("%d %B %Y, %H:%M UTC"),
    }
