"""Server authorities for Dashboard V2 Release 1.

The legacy application has several product-specific entitlement checks.  V2
uses this module as its single capability resolver and reads the existing
market tables through a normalized, freshness-aware snapshot boundary.
"""

from __future__ import annotations

import json
import hashlib
import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from src.db.db import get_cursor

logger = logging.getLogger(__name__)

V2_ALLOWLIST_EMAIL = "emilconstantin22@gmail.com"
WELCOME_HOURS = 168
MIGRATION_CLAIM_DAYS = 14
ENTITLEMENT_CACHE_HOURS = 24
EVENT_SCHEMA_VERSION = "v1"

# This is deliberately code-owned rather than editable campaign data.  Stripe
# identifiers are deployment configuration and are never accepted from a client.
PRODUCT_CATALOG = {
    "intelligence_bundle": {"price_eur": "29.00", "capabilities": ("intraday_risk", "dir_full", "brent_forecast")},
    "widget_wti": {"price_eur": "4.95", "capabilities": ("widget_wti_internal", "widget_wti_embed")},
    "widget_lng": {"price_eur": "4.95", "capabilities": ("widget_lng_internal", "widget_lng_embed")},
    "widget_storage": {"price_eur": "4.95", "capabilities": ("widget_storage_internal", "widget_storage_embed")},
}

CAPABILITIES = (
    "daily_risk",
    "intraday_risk",
    "dir_full",
    "brent_forecast",
    "widget_wti_internal",
    "widget_lng_internal",
    "widget_storage_internal",
    "widget_wti_embed",
    "widget_lng_embed",
    "widget_storage_embed",
)

PREMIUM_INTENT_CAPABILITIES = {
    "intraday_risk",
    "dir_full",
    "brent_forecast",
    "widget_wti_internal",
    "widget_lng_internal",
    "widget_storage_internal",
}

DATASET_RULES = {
    "geri_daily": (timedelta(hours=1.5), timedelta(hours=30), timedelta(hours=48)),
    "eeri_daily": (timedelta(hours=1.5), timedelta(hours=30), timedelta(hours=48)),
    "egsi_daily": (timedelta(hours=1.5), timedelta(hours=30), timedelta(hours=48)),
    "geri_live": (timedelta(minutes=15), timedelta(minutes=60), timedelta(hours=4)),
    "brent": (timedelta(minutes=15), timedelta(hours=1), timedelta(hours=1)),
    "ttf": (timedelta(minutes=15), timedelta(hours=1), timedelta(hours=1)),
    "vix": (timedelta(minutes=15), timedelta(hours=1), timedelta(hours=1)),
    "lng": (timedelta(hours=6), timedelta(hours=36), timedelta(hours=72)),
    "storage": (timedelta(hours=6), timedelta(hours=36), timedelta(hours=72)),
}

ROUTINE_STEPS = (
    ("risk", "Risk", "What is the current risk level?"),
    ("change", "Change", "What changed since the last snapshot?"),
    ("confirm", "Confirm", "Which market signals confirm the move?"),
    ("interpret", "Interpret", "What does today’s intelligence mean?"),
    ("watch", "Watch", "What should you monitor next?"),
)


def _truthy(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def v2_enabled() -> bool:
    # The exact-email allowlist is the primary safety boundary.  The flag is
    # enabled for the internal pilot but can be turned off immediately.
    environment_enabled = _truthy(os.environ.get("DASHBOARD_V2_ENABLED"), True)
    if not environment_enabled:
        return False
    try:
        flag = _one(
            "SELECT enabled FROM dashboard_v2_feature_flags WHERE flag_key = %s",
            ("dashboard_v2_enabled",),
        )
        return bool(flag and flag.get("enabled"))
    except Exception:
        return False


def feature_enabled(flag_key: str) -> bool:
    flag = _one(
        "SELECT enabled FROM dashboard_v2_feature_flags WHERE flag_key = %s",
        (flag_key,),
    )
    return bool(flag and flag.get("enabled"))


def _json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _one(query: str, params: tuple = ()) -> Optional[dict]:
    try:
        with get_cursor(commit=False) as cursor:
            cursor.execute(query, params)
            row = cursor.fetchone()
            return dict(row) if row else None
    except Exception as exc:
        # A single source being unavailable must degrade its dataset, not
        # turn the complete bootstrap into a 500 response.
        logger.warning("Dashboard V2 data source unavailable: %s", exc)
        return None


def _many(query: str, params: tuple = ()) -> list[dict]:
    try:
        with get_cursor(commit=False) as cursor:
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
    except Exception as exc:
        logger.warning("Dashboard V2 data source unavailable: %s", exc)
        return []


def _strict_one(query: str, params: tuple = ()) -> Optional[dict]:
    with get_cursor(commit=False) as cursor:
        cursor.execute(query, params)
        row = cursor.fetchone()
        return dict(row) if row else None


def _strict_many(query: str, params: tuple = ()) -> list[dict]:
    with get_cursor(commit=False) as cursor:
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def get_v2_user(user_id: int) -> Optional[dict]:
    return _one(
        """
        SELECT u.id, u.email, u.created_at,
               COALESCE(up.plan, 'free') AS plan,
               u.subscription_status, u.subscription_current_period_end
        FROM users u
        LEFT JOIN user_plans up ON up.user_id = u.id
        WHERE u.id = %s
        """,
        (user_id,),
    )


def is_allowlisted_user(user_id: int) -> bool:
    user = get_v2_user(user_id)
    return bool(
        user
        and str(user.get("email", "")).strip().lower() == V2_ALLOWLIST_EMAIL
    )


def require_v2_access(user_id: int) -> dict:
    """Return the authenticated user or raise a closed-by-default error."""
    from fastapi import HTTPException

    if not v2_enabled() or feature_enabled("legacy_dashboard_override"):
        raise HTTPException(status_code=404, detail="Dashboard not available")
    user = get_v2_user(user_id)
    if not user or str(user.get("email", "")).strip().lower() != V2_ALLOWLIST_EMAIL:
        raise HTTPException(status_code=404, detail="Dashboard not available")
    return user


def _table_latest(table: str, columns: str, order_column: str = "date") -> Optional[dict]:
    # Table names and column lists are constants in this module; no user input
    # is interpolated into these queries.
    return _one(f"SELECT {columns} FROM {table} ORDER BY {order_column} DESC LIMIT 1")


def _freshness(record: Optional[dict], dataset: str) -> dict:
    if not record:
        return {"state": "UNAVAILABLE", "as_of": None, "age_seconds": None}

    raw = (
        record.get("computed_at")
        or record.get("captured_at")
        or record.get("created_at")
        or record.get("date")
    )
    if isinstance(raw, date) and not isinstance(raw, datetime):
        as_of = datetime.combine(raw, datetime.min.time(), tzinfo=timezone.utc)
    elif isinstance(raw, datetime):
        as_of = raw.replace(tzinfo=timezone.utc) if raw.tzinfo is None else raw
    else:
        as_of = None
    if as_of is None:
        return {"state": "DELAYED", "as_of": _json_value(raw), "age_seconds": None}

    now = datetime.now(timezone.utc)
    age = max(0.0, (now - as_of).total_seconds())
    delayed_after, stale_after, last_good_after = DATASET_RULES[dataset]
    if age <= delayed_after.total_seconds():
        state = "FRESH"
    elif age <= stale_after.total_seconds():
        state = "DELAYED"
    elif age <= last_good_after.total_seconds():
        state = "STALE"
    else:
        state = "UNAVAILABLE"
    return {
        "state": state,
        "as_of": _json_value(raw),
        "age_seconds": round(age, 1),
    }


def _dataset(dataset: str, table: str, columns: str, order_column: str = "date") -> dict:
    record = _table_latest(table, columns, order_column)
    return {
        "dataset": dataset,
        "state": _freshness(record, dataset),
        "data": _json_value(record) if record else None,
    }


def build_snapshot() -> dict:
    """Read the existing data tables and return a normalized V2 snapshot."""
    datasets = {
        "geri_daily": _dataset(
            "geri_daily", "intel_indices_daily",
            "date, value, band, trend_1d, trend_7d, interpretation, computed_at",
        ),
        "eeri_daily": _dataset(
            "eeri_daily", "reri_indices_daily",
            "date, value, band, trend_1d, trend_7d, interpretation, computed_at",
        ),
        "egsi_m_daily": _dataset(
            "egsi_daily", "egsi_m_daily",
            "index_date AS date, index_value, band, trend_1d, trend_7d, interpretation, computed_at",
            "index_date",
        ),
        "egsi_s_daily": _dataset(
            "egsi_daily", "egsi_s_daily",
            "index_date AS date, index_value, band, trend_1d, trend_7d, interpretation, computed_at",
            "index_date",
        ),
        "geri_live": _dataset(
            "geri_live", "geri_live",
            "value, value_raw, band, trend_vs_yesterday, interpretation, top_drivers, computed_at",
            "computed_at",
        ),
        "brent": _dataset(
            "brent", "oil_price_snapshots",
            "date, brent_price, brent_change_pct, wti_price, wti_change_pct",
        ),
        "ttf": _dataset("ttf", "ttf_gas_snapshots", "date, ttf_price, currency, unit"),
        "vix": _dataset("vix", "vix_snapshots", "date, vix_close, vix_open, vix_high, vix_low", "date"),
        "lng": _dataset("lng", "lng_price_snapshots", "date, jkm_price, jkm_change_pct"),
        "storage": _dataset(
            "storage", "gas_storage_snapshots",
            "date, eu_storage_percent, deviation_from_norm, risk_score, risk_band, interpretation",
        ),
    }

    # Intraday tables are source-driven and have captured_at timestamps.
    for dataset, table in (("brent", "intraday_brent"), ("wti", "intraday_wti"), ("natgas", "intraday_natgas")):
        row = _table_latest(
            table, "date, hour, price, change_pct, captured_at", "captured_at"
        )
        datasets[f"intraday_{dataset}"] = {
            "dataset": f"intraday_{dataset}",
            "state": _freshness(row, "brent" if dataset == "brent" else "geri_live"),
            "data": _json_value(row) if row else None,
        }

    daily_dates = [
        item["data"].get("date")
        for item in datasets.values()
        if item.get("data") and item["data"].get("date")
    ]
    snapshot_date = max(daily_dates) if daily_dates else None
    ready = sum(1 for item in datasets.values() if item["state"]["state"] in {"FRESH", "DELAYED", "STALE"})
    routine_snapshot_datasets = (
        "geri_daily", "eeri_daily", "egsi_m_daily", "egsi_s_daily",
        "brent", "ttf", "vix", "lng", "storage",
    )
    identity = {
        key: {
            "data": datasets[key].get("data"),
            "state": (datasets[key].get("state") or {}).get("state"),
            "as_of": (datasets[key].get("state") or {}).get("as_of"),
        }
        for key in routine_snapshot_datasets
    }
    fingerprint = hashlib.sha256(
        json.dumps(identity, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:12]
    return {
        "snapshot_id": f"intelligence:{snapshot_date or 'unavailable'}:{fingerprint}",
        "intelligence_date": snapshot_date,
        "datasets": datasets,
        "freshness": {
            "state": "READY" if ready else "UNAVAILABLE",
            "ready_count": ready,
            "dataset_count": len(datasets),
        },
    }


def _number(value: Any) -> Optional[float]:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _direction(value: Any) -> str:
    number = _number(value)
    if number is not None:
        if number > 0.05:
            return "up"
        if number < -0.05:
            return "down"
        return "flat"
    text = str(value or "").strip().lower()
    if any(word in text for word in ("up", "rise", "higher", "increase", "accelerat")):
        return "up"
    if any(word in text for word in ("down", "fall", "lower", "decrease", "declin")):
        return "down"
    return "flat"


def _briefing_item(
    snapshot: dict,
    dataset: str,
    label: str,
    value_fields: tuple[str, ...],
    *,
    change_fields: tuple[str, ...] = (),
    note_field: Optional[str] = None,
) -> dict:
    row = snapshot["datasets"].get(dataset) or {}
    data = row.get("data") or {}
    freshness = row.get("state") or {
        "state": "UNAVAILABLE", "as_of": None, "age_seconds": None,
    }
    value = next((data.get(field) for field in value_fields if data.get(field) is not None), None)
    change = next((data.get(field) for field in change_fields if data.get(field) is not None), None)
    return {
        "dataset": dataset,
        "label": label,
        "value": _json_value(value),
        "band": data.get("band") or data.get("risk_band"),
        "state": freshness.get("state", "UNAVAILABLE"),
        "as_of": freshness.get("as_of"),
        "age_seconds": freshness.get("age_seconds"),
        "change": _json_value(change),
        "direction": _direction(change),
        "note": data.get(note_field) if note_field else None,
    }


def _latest_refresh(
    snapshot: dict, datasets: Optional[tuple[str, ...]] = None
) -> Optional[str]:
    latest: Optional[datetime] = None
    rows = (
        (snapshot["datasets"].get(key) or {} for key in datasets)
        if datasets
        else snapshot["datasets"].values()
    )
    for row in rows:
        raw = (row.get("state") or {}).get("as_of")
        if not raw:
            continue
        try:
            parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            parsed = parsed.astimezone(timezone.utc)
        except (TypeError, ValueError):
            continue
        if latest is None or parsed > latest:
            latest = parsed
    return latest.isoformat() if latest else None


def _next_daily_update() -> str:
    now = datetime.now(timezone.utc)
    expected = now.replace(hour=1, minute=30, second=0, microsecond=0)
    if expected <= now:
        expected += timedelta(days=1)
    return expected.isoformat()


def build_briefing(snapshot: dict) -> dict:
    """Create concise, deterministic conclusions from the normalized snapshot."""
    risk_items = [
        _briefing_item(snapshot, "geri_daily", "GERI", ("value",), change_fields=("trend_1d",), note_field="interpretation"),
        _briefing_item(snapshot, "eeri_daily", "EERI", ("value",), change_fields=("trend_1d",), note_field="interpretation"),
        _briefing_item(snapshot, "egsi_m_daily", "EGSI-M", ("index_value",), change_fields=("trend_1d",), note_field="interpretation"),
    ]
    core_states = [item["state"] for item in risk_items]
    usable_risk = [
        item for item in risk_items
        if item["state"] in {"FRESH", "DELAYED"} and item["value"] is not None
    ]
    severity = {"LOW": 0, "MODERATE": 1, "ELEVATED": 2, "HIGH": 3, "CRITICAL": 4}
    highest = max(
        usable_risk,
        key=lambda item: severity.get(str(item.get("band") or "").upper(), 1),
        default=None,
    )
    if "UNAVAILABLE" in core_states or not highest:
        briefing_state = "UNAVAILABLE"
        summary = "Today’s normalized risk indicators are unavailable, so no current risk conclusion can be issued."
        what_matters = "Wait for the next verified intelligence refresh before treating older signals as current."
    elif "STALE" in core_states:
        briefing_state = "DEGRADED"
        summary = "One or more core risk inputs are stale; the latest readings are shown for context, not as today’s current conclusion."
        what_matters = "Wait for the stale core indicator to refresh before relying on a combined risk picture."
    elif "DELAYED" in core_states:
        briefing_state = "DEGRADED"
        if severity.get(str(highest.get("band") or "").upper(), 1) == 0:
            summary = "Core risk inputs are delayed; the latest readings indicate low risk, but today’s combined picture is not yet fully current."
        else:
            summary = f"Core risk inputs are delayed; {highest['label']} is the strongest latest reading, pending a current refresh."
        what_matters = "Treat the latest risk readings as provisional until all three core indicators are current."
    elif severity.get(str(highest.get("band") or "").upper(), 1) == 0:
        briefing_state = "FRESH"
        summary = "Global and European energy risk remain low, with no broad escalation signal across the core indicators."
        what_matters = "No major risk escalation signal is currently active."
    else:
        briefing_state = "FRESH"
        band = str(highest.get("band") or "elevated").lower()
        summary = f"Energy risk is not uniformly calm: {highest['label']} is the strongest current signal at {band}."
        what_matters = f"Watch {highest['label']} for confirmation or reversal before treating the move as systemic."

    change_items = [
        *risk_items,
        _briefing_item(snapshot, "brent", "Brent", ("brent_price",), change_fields=("brent_change_pct",)),
        _briefing_item(snapshot, "lng", "JKM LNG", ("jkm_price",), change_fields=("jkm_change_pct",)),
    ]
    changed = [
        item for item in change_items
        if item["direction"] != "flat" and item["state"] in {"FRESH", "DELAYED"}
    ]
    if changed:
        rising = sum(item["direction"] == "up" for item in changed)
        falling = sum(item["direction"] == "down" for item in changed)
        change_conclusion = (
            "The latest signals are mixed rather than systemic; risk and market moves are not all pointing in one direction."
            if rising and falling
            else f"The latest available signals are broadly moving {'higher' if rising else 'lower'}."
        )
    else:
        change_conclusion = "No broad day-over-day move is visible in the latest available signals."

    geri_item = risk_items[0]
    geri_direction_is_current = (
        geri_item["state"] == "FRESH"
        and geri_item["value"] is not None
        and geri_item["change"] is not None
    )
    geri_direction = geri_item["direction"] if geri_direction_is_current else None
    confirm_items = [
        _briefing_item(snapshot, "brent", "Brent", ("brent_price",), change_fields=("brent_change_pct",)),
        _briefing_item(snapshot, "ttf", "TTF", ("ttf_price",)),
        _briefing_item(snapshot, "lng", "JKM LNG", ("jkm_price",), change_fields=("jkm_change_pct",)),
        _briefing_item(snapshot, "vix", "VIX", ("vix_close",)),
        _briefing_item(snapshot, "geri_live", "GERI Live", ("value",), change_fields=("trend_vs_yesterday",), note_field="interpretation"),
    ]
    vix_data = (snapshot["datasets"].get("vix") or {}).get("data") or {}
    vix_open = _number(vix_data.get("vix_open"))
    vix_close = _number(vix_data.get("vix_close"))
    vix_move = (
        vix_close - vix_open
        if vix_open is not None and vix_close is not None
        else None
    )
    confirm_items[3]["change"] = round(vix_move, 2) if vix_move is not None else None
    confirm_items[3]["direction"] = _direction(vix_move)
    measured_confirmation = []
    for item in confirm_items:
        has_change = item.get("change") is not None
        if not geri_direction_is_current or item["state"] not in {"FRESH", "DELAYED"} or not has_change:
            item["confirmation"] = "not measured"
        elif item["direction"] == "flat" or geri_direction == "flat":
            item["confirmation"] = "neutral"
        elif item["direction"] == geri_direction:
            item["confirmation"] = "confirming"
        else:
            item["confirmation"] = "diverging"
        if item["confirmation"] != "not measured":
            measured_confirmation.append(item)
    strength = sum(item["confirmation"] == "confirming" for item in measured_confirmation)
    measured_total = len(measured_confirmation)
    if not geri_direction_is_current:
        confirm_conclusion = "A current measured GERI daily direction is unavailable, so no market-confirmation score can be issued."
    elif not measured_total:
        confirm_conclusion = "Current change data is insufficient to issue a market-confirmation score."
    elif geri_direction == "flat":
        confirm_conclusion = "There is no broad daily risk move requiring confirmation; markets remain a monitoring signal."
    elif strength / measured_total >= 0.6:
        confirm_conclusion = f"Broad confirmation: {strength} of {measured_total} measured signals agree with the daily risk direction."
    elif strength:
        confirm_conclusion = f"Moderate confirmation: {strength} of {measured_total} measured signals agree; the move has not propagated broadly."
    else:
        confirm_conclusion = "Weak confirmation: tracked markets are neutral or diverging from the daily risk direction."

    interpretations = [
        item["note"] for item in risk_items
        if item.get("note") and item["state"] != "UNAVAILABLE"
    ]
    interpretation = interpretations[0] if interpretations else summary
    watch_items = [
        _briefing_item(snapshot, "geri_live", "GERI Live", ("value",), change_fields=("trend_vs_yesterday",)),
        _briefing_item(snapshot, "brent", "Brent", ("brent_price",), change_fields=("brent_change_pct",)),
        _briefing_item(snapshot, "storage", "European storage", ("eu_storage_percent",), note_field="interpretation"),
        _briefing_item(snapshot, "ttf", "TTF", ("ttf_price",)),
    ]
    watch_notes = {
        "GERI Live": "Monitor for acceleration away from the daily risk signal.",
        "Brent": "Watch whether the next move confirms or rejects today’s risk direction.",
        "European storage": "Monitor the next update and any change in deviation from seasonal norms.",
        "TTF": "Watch for a response to European gas and storage conditions.",
    }
    for item in watch_items:
        item["note"] = watch_notes[item["label"]]

    return {
        "state": briefing_state,
        "summary": summary,
        "what_matters": what_matters,
        "refreshed_at": _latest_refresh(
            snapshot, ("geri_daily", "eeri_daily", "egsi_m_daily")
        ),
        "next_update_at": _next_daily_update(),
        "steps": {
            "risk": {
                "title": "Current risk picture",
                "conclusion": summary,
                "what_matters": what_matters,
                "product_label": "GERI · EERI · EGSI",
                "items": risk_items,
            },
            "change": {
                "title": "What changed",
                "conclusion": change_conclusion,
                "product_label": "Daily changes · GERI Live",
                "items": change_items,
            },
            "confirm": {
                "title": "Market confirmation",
                "conclusion": confirm_conclusion,
                "confirmation_strength": {"confirmed": strength, "total": measured_total},
                "product_label": "Brent · TTF · LNG · VIX · GERI Live",
                "items": confirm_items,
            },
            "interpret": {
                "title": "Today’s interpretation",
                "conclusion": interpretation,
                "summary": summary,
                "product_label": "Daily Intelligence Report · Brent Forecast",
                "items": risk_items,
            },
            "watch": {
                "title": "What to watch next",
                "conclusion": "Focus on whether live risk and traded markets begin to move together before the next daily update.",
                "product_label": "Alerts · GERI Live",
                "items": watch_items,
            },
        },
    }


def _active_grants(user_id: int) -> set[str]:
    rows = _strict_many(
        """
        SELECT capability FROM dashboard_v2_grants
        WHERE user_id = %s AND revoked_at IS NULL
          AND starts_at <= NOW() AND ends_at > NOW()
        """,
        (user_id,),
    )
    return {row["capability"] for row in rows}


def widget_access(entitlements: dict, widget: str) -> dict:
    """Keep in-dashboard use distinct from a publishable embed entitlement."""
    if widget not in {"wti", "lng", "storage"}:
        raise ValueError("Unknown widget")
    caps = entitlements["capabilities"]
    return {
        "internal": bool(caps.get(f"widget_{widget}_internal")),
        "embed": bool(caps.get(f"widget_{widget}_embed")),
    }


def _resolve_entitlements_live(user_id: int, user: Optional[dict] = None) -> dict:
    """Resolve additive capabilities from legacy subscriptions and V2 grants."""
    user = user or get_v2_user(user_id) or {}
    plan = str(user.get("plan") or "free").lower()
    paid = {"daily_risk"}
    sources: dict[str, list[str]] = {"daily_risk": ["free_baseline"]}

    def add_capability(capability: str, source: str) -> None:
        paid.add(capability)
        capability_sources = sources.setdefault(capability, [])
        if source not in capability_sources:
            capability_sources.append(source)

    # Preserve the broad access already represented by the legacy plan mirror.
    if plan in {"trader", "pro", "enterprise"}:
        for capability in ("intraday_risk", "dir_full", "brent_forecast"):
            add_capability(capability, "legacy_plan")

    geri = _strict_one(
        "SELECT status, current_period_end FROM user_geri_live_subs WHERE user_id = %s",
        (user_id,),
    )
    if geri and geri.get("status") in {"active", "trialing", "canceling"}:
        add_capability("intraday_risk", "geri_live_subscription")
        add_capability("dir_full", "geri_live_complimentary")

    daily = _strict_one(
        "SELECT status, current_period_end FROM user_daily_report_subs WHERE user_id = %s",
        (user_id,),
    )
    if daily and daily.get("status") in {"active", "trialing", "canceling"}:
        add_capability("dir_full", "daily_report_subscription")
        add_capability("intraday_risk", "daily_report_complimentary")

    forecast = _strict_one(
        "SELECT paid, status FROM paid_brent_forecast_users WHERE LOWER(email) = LOWER(%s)",
        (user.get("email", ""),),
    )
    if forecast and forecast.get("paid") and forecast.get("status") in {"active", "trialing", "canceling", "paid"}:
        add_capability("brent_forecast", "brent_forecast_subscription")

    # Existing paid Widget products retain both in-dashboard and external embed
    # rights. Temporary experiences only ever add the internal capability.
    widget_rows = _strict_many(
        """SELECT widget_code, status, current_period_end
           FROM user_pro_widgets
           WHERE user_id=%s AND status IN ('active','trialing','canceling')
             AND (current_period_end IS NULL OR current_period_end > NOW())""",
        (user_id,),
    )
    widget_map = {
        "wti-pro": ("widget_wti_internal", "widget_wti_embed"),
        "lng-pro": ("widget_lng_internal", "widget_lng_embed"),
        "gas-storage-pro": ("widget_storage_internal", "widget_storage_embed"),
    }
    for widget_row in widget_rows:
        for capability in widget_map.get(widget_row["widget_code"], ()):
            add_capability(capability, "legacy_widget_subscription")

    # V2 billing is isolated in its own mirror. It is additive and therefore
    # cannot overwrite, cancel, or otherwise alter any legacy subscription.
    v2_subscriptions = _strict_many(
        """SELECT product_code FROM dashboard_v2_subscription_mirror
           WHERE user_id=%s
             AND (stripe_status IN ('active','trialing')
                  OR (stripe_status='past_due' AND grace_until > NOW()))
              AND stripe_mode=%s
              AND (current_period_end IS NULL OR current_period_end > NOW())""",
        (user_id, _current_stripe_mode()),
    )
    for subscription in v2_subscriptions:
        product = PRODUCT_CATALOG.get(subscription["product_code"])
        if product:
            for capability in product["capabilities"]:
                add_capability(capability, "dashboard_v2_billing")

    grants = _active_grants(user_id)
    for capability in grants:
        add_capability(capability, "temporary_grant")

    active_experience = _strict_one(
        """
        SELECT experience_type, status, started_at, ends_at
        FROM dashboard_v2_experiences
        WHERE user_id = %s AND status = 'ACTIVE' AND ends_at > NOW()
        ORDER BY ends_at DESC LIMIT 1
        """,
        (user_id,),
    )
    if active_experience:
        for capability in PREMIUM_INTENT_CAPABILITIES:
            add_capability(capability, active_experience["experience_type"].lower())

    return {
        "capabilities": {capability: capability in paid for capability in CAPABILITIES},
        "sources": sources,
        "verification": {"state": "VERIFIED", "checked_at": datetime.now(timezone.utc).isoformat()},
        "experience": _json_value(active_experience),
    }


def resolve_entitlements(user_id: int, user: Optional[dict] = None) -> dict:
    """Resolve live access, falling back only to a recent positive snapshot."""
    try:
        result = _resolve_entitlements_live(user_id, user)
        with get_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO dashboard_v2_entitlement_cache
                  (user_id, entitlement_snapshot, verified_at, updated_at)
                VALUES (%s, %s, NOW(), NOW())
                ON CONFLICT (user_id) DO UPDATE SET
                  entitlement_snapshot = EXCLUDED.entitlement_snapshot,
                  verified_at = EXCLUDED.verified_at,
                  updated_at = NOW()
                """,
                (user_id, json.dumps(result, default=str)),
            )
        return result
    except Exception as exc:
        logger.error("Dashboard V2 entitlement verification failed: %s", exc)
        cached = _one(
            """
            SELECT entitlement_snapshot, verified_at
            FROM dashboard_v2_entitlement_cache
            WHERE user_id = %s
              AND verified_at > NOW() - INTERVAL '24 hours'
            """,
            (user_id,),
        )
        if cached:
            result = cached["entitlement_snapshot"]
            if isinstance(result, str):
                result = json.loads(result)
            experience = result.get("experience")
            if experience and experience.get("ends_at"):
                try:
                    if datetime.fromisoformat(experience["ends_at"]).replace(tzinfo=timezone.utc) <= datetime.now(timezone.utc):
                        for capability in PREMIUM_INTENT_CAPABILITIES:
                            capability_sources = result.get("sources", {}).get(capability, [])
                            if any(
                                source in {"welcome", "migration", "temporary_grant"}
                                for source in capability_sources
                            ) and not any(
                                source not in {"welcome", "migration", "temporary_grant"}
                                for source in capability_sources
                            ):
                                result["capabilities"][capability] = False
                except (TypeError, ValueError):
                    pass
            result["verification"] = {
                "state": "LAST_KNOWN_GOOD",
                "checked_at": _json_value(cached["verified_at"]),
                "message": "We’re temporarily unable to verify your premium access. Your subscription has not been changed.",
            }
            return result
        return {
            "capabilities": {capability: capability == "daily_risk" for capability in CAPABILITIES},
            "sources": {"daily_risk": ["free_baseline"]},
            "verification": {
                "state": "UNAVAILABLE",
                "checked_at": None,
                "message": "We’re temporarily unable to verify your premium access. Your subscription has not been changed.",
            },
            "experience": None,
        }


def get_experience(user_id: int) -> Optional[dict]:
    return _one(
        """
        SELECT experience_type, status, claim_deadline, started_at, ends_at,
               dismissed_at, created_at, updated_at
        FROM dashboard_v2_experiences WHERE user_id = %s
        """,
        (user_id,),
    )


def ensure_migration_eligibility(user_id: int, created_at: Any) -> None:
    """Lazily seed the deterministic pre-cutoff cohort exactly once."""
    cutoff = os.environ.get("DASHBOARD_V2_MIGRATION_COHORT_CUTOFF")
    if not cutoff:
        return
    try:
        cutoff_at = datetime.fromisoformat(cutoff.replace("Z", "+00:00")).replace(tzinfo=None)
        registered = created_at.replace(tzinfo=None) if isinstance(created_at, datetime) else datetime.fromisoformat(str(created_at)).replace(tzinfo=None)
    except (TypeError, ValueError):
        logger.warning("Invalid Dashboard V2 migration cutoff configuration")
        return
    if registered >= cutoff_at:
        return
    with get_cursor() as cursor:
        cursor.execute(
            """INSERT INTO dashboard_v2_experiences(user_id,experience_type,status,claim_deadline)
               VALUES(%s,'MIGRATION','ELIGIBLE',NOW() + INTERVAL '14 days')
               ON CONFLICT(user_id) DO NOTHING""",
            (user_id,),
        )


def activate_welcome(user_id: int, trigger: str) -> dict:
    """Atomically activate the one-time Welcome experience."""
    if not feature_enabled("welcome_experience_enabled"):
        from fastapi import HTTPException
        raise HTTPException(status_code=409, detail="Welcome experience is not enabled")
    user = get_v2_user(user_id)
    if not user:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Account not found")
    ensure_migration_eligibility(user_id, user.get("created_at"))
    with get_cursor() as cursor:
        now = datetime.utcnow()
        cursor.execute(
            """
            INSERT INTO dashboard_v2_experiences
              (user_id, experience_type, status, started_at, ends_at, activation_trigger)
            VALUES (%s, 'WELCOME', 'ACTIVE', %s, %s, %s)
            ON CONFLICT(user_id) DO NOTHING
            RETURNING *
            """,
            (user_id, now, now + timedelta(hours=WELCOME_HOURS), trigger),
        )
        row = cursor.fetchone()
        if not row:
            cursor.execute(
                "SELECT * FROM dashboard_v2_experiences WHERE user_id=%s",
                (user_id,),
            )
            return _json_value(dict(cursor.fetchone()))
        cursor.execute(
            """
            INSERT INTO dashboard_v2_grants
              (user_id, capability, source, starts_at, ends_at)
            SELECT %s, capability, 'WELCOME', %s, %s
            FROM unnest(%s::text[]) AS capability
            """,
            (
                user_id,
                now,
                now + timedelta(hours=WELCOME_HOURS),
                list(PREMIUM_INTENT_CAPABILITIES),
            ),
        )
        cursor.execute(
            """
            INSERT INTO dashboard_v2_events (user_id, event_name, event_envelope)
            VALUES (%s, 'welcome_activated', %s)
            """,
            (user_id, json.dumps({"version": "v1", "trigger": trigger, "category": "essential"})),
        )
        return _json_value(dict(row))


def activate_migration(user_id: int) -> dict:
    """Claim an already-created migration eligibility without touching paid plans."""
    from fastapi import HTTPException
    if not feature_enabled("migration_experience_enabled"):
        raise HTTPException(status_code=409, detail="Migration experience is not enabled")
    with get_cursor() as cursor:
        cursor.execute("SELECT * FROM dashboard_v2_experiences WHERE user_id=%s FOR UPDATE", (user_id,))
        row = cursor.fetchone()
        if not row or row["experience_type"] != "MIGRATION":
            raise HTTPException(status_code=409, detail="Migration is not available")
        current = dict(row)
        if current["status"] == "DISMISSED" and current.get("claim_deadline") and current["claim_deadline"] > datetime.utcnow():
            cursor.execute("UPDATE dashboard_v2_experiences SET status='ELIGIBLE', dismissed_at=NULL, updated_at=NOW() WHERE user_id=%s", (user_id,))
            current["status"] = "ELIGIBLE"
        if current["status"] != "ELIGIBLE" or not current.get("claim_deadline") or current["claim_deadline"] <= datetime.utcnow():
            cursor.execute("UPDATE dashboard_v2_experiences SET status='CLAIM_WINDOW_EXPIRED', updated_at=NOW() WHERE user_id=%s AND status IN ('ELIGIBLE','DISMISSED')", (user_id,))
            raise HTTPException(status_code=409, detail="Migration claim window has expired")
        now = datetime.utcnow()
        ends = now + timedelta(hours=WELCOME_HOURS)
        cursor.execute("""UPDATE dashboard_v2_experiences SET status='ACTIVE', started_at=%s, ends_at=%s,
            activation_trigger='migration_claim', updated_at=NOW() WHERE user_id=%s RETURNING *""", (now, ends, user_id))
        # Migration provides broad temporary access. Existing single-product
        # subscribers retain their paid product and receive complementary access.
        cursor.execute("""INSERT INTO dashboard_v2_grants (user_id, capability, source, starts_at, ends_at)
            SELECT %s, capability, 'MIGRATION', %s, %s FROM unnest(%s::text[]) AS capability""",
            (user_id, now, ends, list(PREMIUM_INTENT_CAPABILITIES)))
        activated = _json_value(dict(cursor.fetchone()))
    record_event(user_id, "migration_activated", "essential", {"duration_hours": WELCOME_HOURS}, True)
    return activated


def dismiss_migration(user_id: int) -> None:
    with get_cursor() as cursor:
        cursor.execute("""UPDATE dashboard_v2_experiences SET status='DISMISSED', dismissed_at=NOW(), updated_at=NOW()
            WHERE user_id=%s AND experience_type='MIGRATION' AND status='ELIGIBLE' AND claim_deadline > NOW()""", (user_id,))
    record_event(user_id, "migration_dismissed", "essential", {}, True)


def routine_started(user_id: int, snapshot_id: str) -> bool:
    row = _one(
        """
        SELECT 1
        FROM dashboard_v2_events
        WHERE user_id = %s
          AND event_name = 'routine_started'
          AND event_envelope->'payload'->>'snapshot_id' = %s
        LIMIT 1
        """,
        (user_id, snapshot_id),
    )
    if row:
        return True
    return bool(
        _one(
            """
            SELECT 1 FROM dashboard_v2_routine_progress
            WHERE user_id = %s AND snapshot_id = %s LIMIT 1
            """,
            (user_id, snapshot_id),
        )
    )


def routine_state(user_id: int, snapshot: dict) -> dict:
    snapshot_id = snapshot["snapshot_id"]
    rows = _many(
        """
        SELECT step_key, status, viewed_at, completed_at, available
        FROM dashboard_v2_routine_progress
        WHERE user_id = %s AND snapshot_id = %s
        """,
        (user_id, snapshot_id),
    )
    by_step = {row["step_key"]: row for row in rows}
    steps = []
    for key, title, summary in ROUTINE_STEPS:
        available = _step_available(key, snapshot)
        row = by_step.get(key, {})
        steps.append({
            "key": key,
            "title": title,
            "summary": summary,
            "available": available,
            "status": row.get("status", "pending") if available else "unavailable",
            "viewed_at": _json_value(row.get("viewed_at")),
            "completed_at": _json_value(row.get("completed_at")),
        })
    available_steps = [step for step in steps if step["available"]]
    completed = sum(step["status"] == "completed" for step in steps)
    current = next(
        (
            step["key"] for step in steps
            if step["available"] and step["status"] != "completed"
        ),
        None,
    )
    return {
        "snapshot_id": snapshot_id,
        "steps": steps,
        "completed": completed,
        "available": len(available_steps),
        "total_steps": len(ROUTINE_STEPS),
        "current_step": current,
        "started": routine_started(user_id, snapshot_id),
        "complete": bool(available_steps) and completed == len(available_steps),
    }


def _step_available(key: str, snapshot: dict) -> bool:
    datasets = snapshot["datasets"]
    requirements = {
        "risk": ("geri_daily", "eeri_daily", "egsi_m_daily"),
        "change": ("geri_daily", "eeri_daily"),
        "confirm": ("brent", "ttf", "vix"),
        "interpret": ("geri_daily", "geri_live"),
        "watch": ("storage", "geri_live"),
    }
    return any(
        datasets.get(name, {}).get("state", {}).get("state") in {"FRESH", "DELAYED", "STALE"}
        for name in requirements[key]
    )


def mark_routine_step(user_id: int, step_key: str, snapshot: dict, complete: bool = False) -> dict:
    if step_key not in {"risk", "change", "confirm", "interpret", "watch"}:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Unknown Routine step")
    snapshot_id = snapshot["snapshot_id"]  # client snapshot identifiers are never authoritative
    if not _step_available(step_key, snapshot):
        from fastapi import HTTPException
        raise HTTPException(status_code=409, detail="Routine step data is unavailable")
    status = "completed" if complete else "viewed"
    with get_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO dashboard_v2_routine_progress
              (user_id, snapshot_id, step_key, status, viewed_at, completed_at)
            VALUES (%s, %s, %s, %s, NOW(), CASE WHEN %s THEN NOW() ELSE NULL END)
            ON CONFLICT (user_id, snapshot_id, step_key) DO UPDATE SET
              status = CASE WHEN EXCLUDED.status = 'completed' THEN 'completed'
                       ELSE dashboard_v2_routine_progress.status END,
              viewed_at = COALESCE(dashboard_v2_routine_progress.viewed_at, NOW()),
              completed_at = COALESCE(dashboard_v2_routine_progress.completed_at, EXCLUDED.completed_at)
            RETURNING *
            """,
            (user_id, snapshot_id, step_key, status, complete),
        )
        result = _json_value(dict(cursor.fetchone()))
    current = routine_state(user_id, snapshot)
    if current["complete"]:
        with get_cursor() as cursor:
            cursor.execute(
                """UPDATE dashboard_v2_newsletter_context
                   SET completed_at=NOW()
                   WHERE user_id=%s AND completed_at IS NULL AND expires_at > NOW()""",
                (user_id,),
            )
    record_event(
        user_id,
        "routine_step_completed" if complete else "routine_step_viewed",
        "essential",
        {"step_key": step_key, "snapshot_id": snapshot["snapshot_id"]},
        True,
    )
    return result


def _offer_is_dismissed(user_id: int, offer_key: str) -> bool:
    row = _one("SELECT 1 FROM dashboard_v2_offer_dismissals WHERE user_id=%s AND offer_key=%s AND dismissed_until > NOW()", (user_id, offer_key))
    return bool(row)


def dismiss_offer(user_id: int, offer_key: str) -> None:
    if offer_key not in {"welcome", "migration", "bundle_discovery", "locked_bundle"}:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Unknown offer")
    with get_cursor() as cursor:
        cursor.execute("""INSERT INTO dashboard_v2_offer_dismissals(user_id, offer_key, dismissed_until)
            VALUES (%s,%s,NOW() + INTERVAL '7 days')
            ON CONFLICT(user_id, offer_key) DO UPDATE SET dismissed_until=EXCLUDED.dismissed_until""", (user_id, offer_key))
    record_event(user_id, "offer_dismissed", "essential", {"offer_key": offer_key}, True)


def primary_offer(user_id: int, entitlements: dict, routine: dict) -> Optional[dict]:
    experience_record = get_experience(user_id) or {}
    # Migration lifecycle messaging is rendered in the dedicated status notice.
    # It suppresses every lower-priority commercial banner in every state.
    if experience_record.get("experience_type") == "MIGRATION":
        return None
    experience = entitlements.get("experience")
    if experience and experience.get("ends_at") and not _offer_is_dismissed(user_id, "welcome"):
        now = datetime.now(timezone.utc)
        try:
            started_at = datetime.fromisoformat(
                str(experience.get("started_at")).replace("Z", "+00:00")
            )
            ends_at = datetime.fromisoformat(
                str(experience["ends_at"]).replace("Z", "+00:00")
            )
            if started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=timezone.utc)
            if ends_at.tzinfo is None:
                ends_at = ends_at.replace(tzinfo=timezone.utc)
            elapsed_days = max(0, int((now - started_at).total_seconds() // 86400))
            remaining_seconds = max(0, (ends_at - now).total_seconds())
            days_remaining = min(7, max(1, int((remaining_seconds + 86399) // 86400)))
            day_number = min(7, elapsed_days + 1)
        except (TypeError, ValueError):
            day_number = 1
            days_remaining = 7
        return {
            "kind": "welcome",
            "priority": 4,
            "title": f"Your 7-Day Intelligence Welcome — Day {day_number} of 7",
            "body": "Full internal access to GERI Live, Daily Intelligence Report, Brent Forecast, and market intelligence is active.",
            "started_at": experience.get("started_at"),
            "ends_at": experience["ends_at"],
            "day_number": day_number,
            "total_days": 7,
            "days_remaining": days_remaining,
            "cta_href": "/dashboard/intelligence/geri-live",
            "cta_label": "Explore Premium Intelligence",
        }
    behavior = _one(
        """SELECT
             (SELECT COUNT(*) FROM dashboard_v2_visits WHERE user_id=%s) AS visits,
             EXISTS(
               SELECT 1 FROM dashboard_v2_events
               WHERE user_id=%s AND event_name='premium_intent'
             ) AS has_interest,
             EXISTS(
               SELECT 1 FROM dashboard_v2_events
               WHERE user_id=%s AND event_name='locked_capability_opened'
             ) AS has_locked_intent""",
        (user_id, user_id, user_id),
    ) or {}
    behavior_eligible = (
        routine["complete"]
        and int(behavior.get("visits") or 0) >= 2
        and bool(behavior.get("has_interest"))
    )
    expired_locked_eligible = (
        experience_record.get("status") in {"EXPIRED", "CLAIM_WINDOW_EXPIRED"}
        and bool(behavior.get("has_locked_intent"))
    )
    ownership = _one(
        """SELECT
             EXISTS(
               SELECT 1 FROM dashboard_v2_subscription_mirror
               WHERE user_id=%s AND product_code='intelligence_bundle'
                 AND stripe_mode=%s
                 AND (stripe_status IN ('active','trialing')
                      OR (stripe_status='past_due' AND grace_until > NOW()))
             ) AS owns_bundle,
             (SELECT COUNT(*) FROM (
                SELECT stripe_subscription_id FROM user_geri_live_subs
                 WHERE user_id=%s AND status IN ('active','trialing','canceling')
                   AND stripe_subscription_id IS NOT NULL
                UNION ALL
                SELECT stripe_subscription_id FROM user_daily_report_subs
                 WHERE user_id=%s AND status IN ('active','trialing','canceling')
                   AND stripe_subscription_id IS NOT NULL
              ) standalone) AS standalone_count""",
        (user_id, _current_stripe_mode(), user_id, user_id),
    ) or {}
    premium_sources = entitlements.get("sources", {})
    owns_legacy_plan = any(
        "legacy_plan" in premium_sources.get(capability, [])
        for capability in ("intraday_risk", "dir_full", "brent_forecast")
    )
    standalone_count = int(ownership.get("standalone_count") or 0)
    owns_any_premium = any(
        entitlements["capabilities"].get(capability)
        for capability in ("intraday_risk", "dir_full", "brent_forecast")
    )
    may_buy_bundle = (
        not ownership.get("owns_bundle")
        and not owns_legacy_plan
        and (not owns_any_premium or standalone_count == 1)
    )
    if (behavior_eligible or expired_locked_eligible) and may_buy_bundle and not _offer_is_dismissed(user_id, "bundle_discovery"):
        offer = {
            "kind": "bundle_discovery",
            "priority": 7,
            "title": (
                "Upgrade your intelligence subscription to the Bundle"
                if standalone_count == 1
                else "Keep the full intelligence workflow connected"
            ),
            "body": "The €29 EnergyRiskIQ Intelligence Bundle brings live risk, Daily Intelligence, and Brent Forecast together.",
            "product_code": "intelligence_bundle",
            "transition": "immediate_prorated_upgrade" if standalone_count == 1 else None,
        }
        if feature_enabled("intelligence_bundle_checkout_enabled"):
            offer["checkout_endpoint"] = "/api/dashboard/v2/checkout"
        return offer
    return None


def targeted_intelligence(user_id: int, resource: str) -> dict:
    """Capability boundary for heavy V2 resources (not just a UI lock)."""
    resource_capabilities = {
        "geri-live": "intraday_risk", "daily-report": "dir_full",
        "brent-forecast": "brent_forecast", "wti": "widget_wti_internal",
        "lng": "widget_lng_internal", "storage": "widget_storage_internal",
        "daily-risk": "daily_risk",
    }
    capability = resource_capabilities.get(resource)
    if not capability:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Unknown intelligence resource")
    entitlements = resolve_entitlements(user_id)
    if not entitlements["capabilities"].get(capability):
        from fastapi import HTTPException
        record_event(
            user_id, "locked_capability_opened", "essential",
            {"resource": resource, "capability": capability}, True,
        )
        raise HTTPException(status_code=403, detail="Capability required")
    snapshot = build_snapshot()
    relevant = {
        "geri-live": ("geri_live",), "daily-report": ("geri_daily", "eeri_daily", "egsi_m_daily"),
        "brent-forecast": ("brent", "geri_daily"), "wti": ("intraday_wti", "brent"),
        "lng": ("lng", "ttf"), "storage": ("storage",), "daily-risk": ("geri_daily", "eeri_daily", "egsi_m_daily"),
    }[resource]
    return {"resource": resource, "methodology_version": "v1", "datasets": {key: snapshot["datasets"].get(key) for key in relevant},
            "widget_access": widget_access(entitlements, resource) if resource in {"wti", "lng", "storage"} else None}


def record_event(user_id: int, event_name: str, category: str, payload: dict, analytics_consent: bool) -> None:
    """Canonical, versioned and PII-free event persistence."""
    if category not in {"essential", "analytics", "marketing"}:
        return
    if category != "essential" and not analytics_consent:
        return
    # Keep only primitive, explicitly non-PII product fields.  This makes the
    # endpoint safe even when a client accidentally submits an email/name.
    forbidden = {"email", "name", "first_name", "last_name", "phone", "address"}
    safe = {str(k): _json_value(v) for k, v in (payload or {}).items()
            if str(k).lower() not in forbidden and isinstance(v, (str, int, float, bool, type(None)))}
    with get_cursor() as cursor:
        cursor.execute("INSERT INTO dashboard_v2_events(user_id,event_name,event_envelope) VALUES(%s,%s,%s)",
                       (user_id, event_name[:100], json.dumps({"version": EVENT_SCHEMA_VERSION, "category": category, "payload": safe})))


def public_catalog() -> list[dict]:
    rows = _many(
        """SELECT product_code, display_name, price_eur_cents, capabilities, active
           FROM dashboard_v2_product_catalog ORDER BY product_code"""
    )
    return [_json_value(row) for row in rows]


def _current_stripe_mode() -> str:
    try:
        from src.billing.stripe_client import get_stripe_mode
        return get_stripe_mode()
    except Exception:
        # Failure is handled by the entitlement resolver's last-known-good path.
        raise


async def create_v2_checkout(user: dict, product_code: str) -> dict:
    """Create a separately-labelled Stripe subscription only when explicitly enabled."""
    from fastapi import HTTPException
    if not feature_enabled("intelligence_bundle_checkout_enabled"):
        raise HTTPException(status_code=409, detail="Dashboard V2 checkout is not enabled")
    if product_code not in PRODUCT_CATALOG:
        raise HTTPException(status_code=404, detail="Unknown product")
    if product_code != "intelligence_bundle":
        raise HTTPException(
            status_code=409,
            detail="Use the existing standalone Widget billing flow; nothing has been changed.",
        )

    from src.billing.stripe_client import (
        create_customer, ensure_stripe_initialized, get_stripe_mode,
    )
    mode = get_stripe_mode()
    price_column = "stripe_price_id_sandbox" if mode == "sandbox" else "stripe_price_id_live"
    row = _strict_one(
        f"""SELECT {price_column} AS price_id, active
            FROM dashboard_v2_product_catalog WHERE product_code=%s""",
        (product_code,),
    )
    if not row or not row["active"] or not row.get("price_id"):
        raise HTTPException(status_code=409, detail="This product is not configured for checkout")

    ensure_stripe_initialized()
    customer_row = _strict_one(
        "SELECT stripe_customer_id FROM users WHERE id=%s", (user["id"],)
    )
    stripe_customer_id = customer_row.get("stripe_customer_id") if customer_row else None
    user = {**user, "stripe_customer_id": stripe_customer_id}
    legacy_rows = _strict_many(
        """SELECT 'geri_live' AS source_product, stripe_subscription_id, stripe_mode
           FROM user_geri_live_subs
           WHERE user_id=%s AND status IN ('active','trialing','canceling')
             AND stripe_subscription_id IS NOT NULL
         UNION ALL
         SELECT 'daily_report', stripe_subscription_id, stripe_mode
           FROM user_daily_report_subs
           WHERE user_id=%s AND status IN ('active','trialing','canceling')
             AND stripe_subscription_id IS NOT NULL""",
        (user["id"], user["id"]),
    )
    current_legacy = [
        item for item in legacy_rows
        if not item.get("stripe_mode") or item.get("stripe_mode") == mode
    ]
    if len(current_legacy) > 1:
        raise HTTPException(
            status_code=409,
            detail="Multiple existing intelligence subscriptions require manual review; nothing has been changed.",
        )
    forecast = _strict_one(
        """SELECT stripe_subscription_id FROM paid_brent_forecast_users
           WHERE LOWER(email)=LOWER(%s) AND status IN ('active','trialing','canceling','paid')
             AND stripe_subscription_id IS NOT NULL""",
        (user["email"],),
    )
    if forecast:
        raise HTTPException(
            status_code=409,
            detail="Your Brent Forecast subscription requires manual review before Bundle upgrade; nothing has been changed.",
        )

    if current_legacy:
        return _upgrade_legacy_to_bundle(
            user, current_legacy[0], row["price_id"], mode
        )

    if not stripe_customer_id:
        customer = await create_customer(user["email"], user["id"])
        stripe_customer_id = customer["id"]
        with get_cursor() as cursor:
            cursor.execute("UPDATE users SET stripe_customer_id=%s WHERE id=%s", (stripe_customer_id, user["id"]))

    import stripe
    domain = os.environ.get("REPLIT_DOMAINS", "").split(",")[0]
    base = os.environ.get("APP_URL") or (f"https://{domain}" if domain else "http://localhost:5000")
    metadata = {"user_id": str(user["id"]), "dashboard_v2_product": product_code}
    session = stripe.checkout.Session.create(
        customer=stripe_customer_id,
        payment_method_types=["card"],
        line_items=[{"price": row["price_id"], "quantity": 1}],
        mode="subscription",
        success_url=f"{base.rstrip('/')}/dashboard?checkout=success",
        cancel_url=f"{base.rstrip('/')}/dashboard?checkout=cancelled",
        metadata=metadata,
        subscription_data={"metadata": metadata},
    )
    record_event(user["id"], "checkout_started", "essential", {"product_code": product_code, "stripe_mode": mode}, True)
    return {"checkout_url": session.url}


def _upgrade_legacy_to_bundle(
    user: dict, legacy: dict, bundle_price_id: str, mode: str
) -> dict:
    """Immediately prorate one GERI or DIR subscription into the Bundle."""
    from fastapi import HTTPException
    import stripe

    subscription_id = legacy["stripe_subscription_id"]
    source = legacy["source_product"]
    subscription = stripe.Subscription.retrieve(subscription_id)
    if str(subscription.get("customer")) != str(user.get("stripe_customer_id")):
        raise HTTPException(status_code=409, detail="Subscription ownership could not be verified")
    items = (subscription.get("items") or {}).get("data") or []
    if not items:
        raise HTTPException(status_code=409, detail="Subscription has no billable item")
    current_price = ((items[0].get("price") or {}).get("id"))
    metadata = dict(subscription.get("metadata") or {})
    metadata.update({
        "user_id": str(user["id"]),
        "dashboard_v2_product": "intelligence_bundle",
        "dashboard_v2_transition_from": source,
    })
    with get_cursor() as cursor:
        cursor.execute(
            """INSERT INTO dashboard_v2_billing_transitions
                 (user_id,source_product,target_product,stripe_subscription_id,
                  stripe_mode,status,details)
               VALUES(%s,%s,'intelligence_bundle',%s,%s,'PENDING',%s::jsonb)
               RETURNING id""",
            (user["id"], source, subscription_id, mode,
             json.dumps({"from_price_id": current_price, "to_price_id": bundle_price_id})),
        )
        transition_id = cursor.fetchone()["id"]
    try:
        if current_price != bundle_price_id:
            subscription = stripe.Subscription.modify(
                subscription_id,
                items=[{"id": items[0]["id"], "price": bundle_price_id}],
                proration_behavior="always_invoice",
                metadata=metadata,
            )
        period = subscription.get("current_period_end")
        period_end = datetime.utcfromtimestamp(period) if period else None
        source_table = (
            "user_geri_live_subs" if source == "geri_live"
            else "user_daily_report_subs"
        )
        with get_cursor() as cursor:
            cursor.execute(
                f"""UPDATE {source_table}
                    SET status='upgraded', updated_at=NOW() WHERE user_id=%s""",
                (user["id"],),
            )
            cursor.execute(
                """INSERT INTO dashboard_v2_subscription_mirror
                     (stripe_subscription_id,user_id,product_code,stripe_mode,
                      stripe_price_id,stripe_status,current_period_end,raw_event)
                   VALUES(%s,%s,'intelligence_bundle',%s,%s,%s,%s,%s::jsonb)
                   ON CONFLICT(stripe_subscription_id) DO UPDATE SET
                     product_code='intelligence_bundle',stripe_mode=EXCLUDED.stripe_mode,
                     stripe_price_id=EXCLUDED.stripe_price_id,
                     stripe_status=EXCLUDED.stripe_status,
                     current_period_end=EXCLUDED.current_period_end,
                     raw_event=EXCLUDED.raw_event,updated_at=NOW()""",
                (subscription_id, user["id"], mode, bundle_price_id,
                 subscription.get("status", "active"), period_end,
                 json.dumps({"transition_id": transition_id})),
            )
            cursor.execute(
                """UPDATE dashboard_v2_billing_transitions
                   SET status='SUCCEEDED',updated_at=NOW() WHERE id=%s""",
                (transition_id,),
            )
        record_event(
            user["id"], "bundle_upgrade_completed", "essential",
            {"source_product": source, "stripe_mode": mode}, True,
        )
        return {"upgraded": True, "product_code": "intelligence_bundle"}
    except Exception as exc:
        with get_cursor() as cursor:
            cursor.execute(
                """UPDATE dashboard_v2_billing_transitions
                   SET status='FAILED',details=details || %s::jsonb,updated_at=NOW()
                   WHERE id=%s""",
                (json.dumps({"error_type": type(exc).__name__}), transition_id),
            )
        raise


def newsletter_context(user_id: int, visitor_token: Optional[str]) -> dict:
    """Claim a short-lived opaque click context and resolve editorial mapping."""
    if not visitor_token or not feature_enabled("newsletter_context_enabled"):
        return {"state": "UNAVAILABLE", "context": None}
    edition = _one(
        """SELECT e.edition_slug, e.topic, e.entry_step, e.featured_product,
                  e.companion_content, c.expires_at
           FROM dashboard_v2_newsletter_context c
           JOIN dashboard_v2_newsletter_editions e ON e.edition_slug=c.edition_slug
           WHERE c.visitor_id=%s AND c.expires_at > NOW()
             AND c.completed_at IS NULL AND e.active=TRUE
           ORDER BY c.created_at DESC LIMIT 1""",
        (visitor_token,),
    )
    if not edition:
        return {"state": "INVALID", "context": None}
    context = _json_value(edition)
    with get_cursor() as cursor:
        cursor.execute(
            """UPDATE dashboard_v2_newsletter_context SET user_id=%s
               WHERE visitor_id=%s AND user_id IS NULL""",
            (user_id, visitor_token),
        )
    return {"state": "ACTIVE", "context": context}


def bootstrap(user_id: int, edition_slug: Optional[str] = None) -> dict:
    user = require_v2_access(user_id)
    ensure_migration_eligibility(user_id, user.get("created_at"))
    snapshot = build_snapshot()
    with get_cursor() as cursor:
        cursor.execute(
            """INSERT INTO dashboard_v2_visits(user_id,snapshot_id)
               VALUES(%s,%s) ON CONFLICT(user_id,snapshot_id) DO NOTHING""",
            (user_id, snapshot["snapshot_id"]),
        )
    entitlements = resolve_entitlements(user_id, user)
    routine = routine_state(user_id, snapshot)
    return {
        "version": "v1",
        "account": {
            "id": user["id"],
            "email": user["email"],
            "plan": user.get("plan", "free"),
        },
        "entitlements": entitlements,
        "experience": _json_value(get_experience(user_id)),
        "routine": routine,
        "newsletter_context": newsletter_context(user_id, edition_slug),
        "primary_offer": primary_offer(user_id, entitlements, routine),
        "briefing": build_briefing(snapshot),
        "snapshot": snapshot,
    }
