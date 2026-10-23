"""Bounded, cached sales snapshot. No live stream, custom inputs or AI generation."""

import logging
import math
import threading
import time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
_lock = threading.Lock()
_cached = None
_expires = 0.0
PREVIEW_TTL = 300


def _build_preview():
    from src.geri.live import (
        get_latest_live_geri, get_live_geri_timeline,
        _compute_velocity, _compute_peak_low, _compute_band_proximity,
    )
    from src.geri.live_trader_intel import get_full_trader_intelligence
    from src.api.geri_live_brent_routes import BrentScenarioRequest, _build_brent_scenario
    from src.api.brent_forecast_routes import _market_snapshot

    data = {
        "live": None, "timeline": [], "trader_intelligence": None,
        "market": None, "scenario": None, "errors": [],
        "preview_as_of": datetime.now(timezone.utc).isoformat(),
    }
    try:
        latest = get_latest_live_geri()
        timeline = get_live_geri_timeline()
        if latest:
            velocity = _compute_velocity(timeline, latest["value"])
            # Expose just the marketing cards, not the full paid live response.
            data["live"] = {
                key: latest.get(key)
                for key in ("value", "band", "computed_at", "alert_count", "interpretation")
            }
            data["live"].update({
                "top_drivers": (latest.get("top_drivers") or [])[:3],
                "velocity": velocity,
                "peak_low": _compute_peak_low(timeline, latest["value"]),
            })
            # Bound the chart payload while retaining endpoints in chronological order.
            stride = max(1, math.ceil(len(timeline) / 287))
            sampled = timeline[::stride]
            if timeline and sampled[-1] != timeline[-1]:
                sampled.append(timeline[-1])
            data["timeline"] = sampled
        else:
            data["errors"].append("Live index is currently unavailable.")
    except Exception:
        logger.exception("GERI sales preview live snapshot failed")
        data["errors"].append("Live index is currently unavailable.")

    if data["live"]:
        try:
            intel = get_full_trader_intelligence(
                geri_value=latest["value"], geri_band=latest["band"],
                velocity=velocity,
                band_proximity=_compute_band_proximity(latest["value"]),
                top_drivers=latest.get("top_drivers") or [],
            )
            # Keep the bounded cards used by the reference landing page.
            if isinstance(intel.get("flash_headline_feed"), dict):
                feed = dict(intel["flash_headline_feed"])
                feed["feed"] = (feed.get("feed") or [])[:3]
                intel = {**intel, "flash_headline_feed": feed}
            if isinstance(intel.get("position_risk_alerts"), dict):
                alerts = dict(intel["position_risk_alerts"])
                alerts["alerts"] = (alerts.get("alerts") or [])[:2]
                intel = {**intel, "position_risk_alerts": alerts}
            data["trader_intelligence"] = intel
        except Exception:
            logger.exception("GERI sales preview intelligence failed")
            data["errors"].append("Trading intelligence is currently unavailable.")
    try:
        data["market"] = _market_snapshot()
        # The legacy correlation feed can substitute Henry Hub for TTF and label
        # it EUR/MWh. The sales preview must use the actual TTF daily snapshot.
        intel = data["trader_intelligence"]
        correlation = intel.get("price_risk_correlation") if intel else None
        if correlation:
            signals = []
            for signal in correlation.get("signals") or []:
                if signal.get("key") == "ttf":
                    signal = {
                        **signal, "price": data["market"].get("ttf"),
                        "change_pct": None, "unit": "EUR/MWh",
                        "is_intraday": False,
                    }
                signals.append(signal)
            data["trader_intelligence"] = {
                **intel, "price_risk_correlation": {**correlation, "signals": signals},
            }
        brent = data["market"].get("brent_intraday") or data["market"].get("brent")
        if brent is None or not math.isfinite(float(brent)) or not 10 < float(brent) < 300:
            data["errors"].append("Forecast preview requires an available Brent market price.")
        else:
            data["scenario"] = _build_brent_scenario(
                BrentScenarioRequest(
                    brent=float(brent), geri_change_pct=40, vix_change_pct=15,
                    gas_stress_pct=10, supply_scenario="pipeline_attack",
                    demand_outlook="neutral",
                ),
                market=data["market"],
            )
    except Exception:
        logger.exception("GERI sales preview market/scenario failed")
        data["errors"].append("Market and scenario preview is currently unavailable.")
    return {"success": True, "data": data}


def get_sales_preview():
    """Share a five-minute snapshot across users without computing live GERI."""
    global _cached, _expires
    with _lock:
        if _cached is not None and time.monotonic() < _expires:
            return _cached
        _cached = _build_preview()
        # Shorter failure cache prevents outages turning into a recompute storm.
        _expires = time.monotonic() + (30 if _cached["data"]["errors"] else PREVIEW_TTL)
        return _cached
