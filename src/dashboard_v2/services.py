"""Server authorities for Dashboard V2 Release 1.

The legacy application has several product-specific entitlement checks.  V2
uses this module as its single capability resolver and reads the existing
market tables through a normalized, freshness-aware snapshot boundary.
"""

from __future__ import annotations

import json
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

    if not v2_enabled():
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

    raw = record.get("date") or record.get("computed_at") or record.get("created_at")
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
    return {
        "snapshot_id": f"intelligence:{snapshot_date or 'unavailable'}",
        "intelligence_date": snapshot_date,
        "datasets": datasets,
        "freshness": {
            "state": "READY" if ready else "UNAVAILABLE",
            "ready_count": ready,
            "dataset_count": len(datasets),
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


def _resolve_entitlements_live(user_id: int, user: Optional[dict] = None) -> dict:
    """Resolve additive capabilities from legacy subscriptions and V2 grants."""
    user = user or get_v2_user(user_id) or {}
    plan = str(user.get("plan") or "free").lower()
    paid = {"daily_risk"}
    sources: dict[str, list[str]] = {"daily_risk": ["free_baseline"]}

    # Preserve the broad access already represented by the legacy plan mirror.
    if plan in {"trader", "pro", "enterprise"}:
        paid.update({"intraday_risk", "dir_full", "brent_forecast"})
        for capability in ("intraday_risk", "dir_full", "brent_forecast"):
            sources[capability] = ["legacy_plan"]

    geri = _strict_one(
        "SELECT status, current_period_end FROM user_geri_live_subs WHERE user_id = %s",
        (user_id,),
    )
    if geri and geri.get("status") in {"active", "trialing", "canceling"}:
        paid.add("intraday_risk")
        sources["intraday_risk"] = ["geri_live_subscription"]

    daily = _strict_one(
        "SELECT status, current_period_end FROM user_daily_report_subs WHERE user_id = %s",
        (user_id,),
    )
    if daily and daily.get("status") in {"active", "trialing", "canceling"}:
        paid.add("dir_full")
        sources["dir_full"] = ["daily_report_subscription"]

    forecast = _strict_one(
        "SELECT paid, status FROM paid_brent_forecast_users WHERE LOWER(email) = LOWER(%s)",
        (user.get("email", ""),),
    )
    if forecast and forecast.get("paid") and forecast.get("status") in {"active", "trialing", "canceling", "paid"}:
        paid.add("brent_forecast")
        sources["brent_forecast"] = ["brent_forecast_subscription"]

    grants = _active_grants(user_id)
    paid.update(grants)
    for capability in grants:
        sources[capability] = ["temporary_grant"]

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
        paid.update(PREMIUM_INTENT_CAPABILITIES)
        for capability in PREMIUM_INTENT_CAPABILITIES:
            sources[capability] = [active_experience["experience_type"].lower()]

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
                            if result.get("sources", {}).get(capability) in (["welcome"], ["migration"], ["temporary_grant"]):
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


def activate_welcome(user_id: int, trigger: str) -> dict:
    """Atomically activate the one-time Welcome experience."""
    if not feature_enabled("welcome_experience_enabled"):
        from fastapi import HTTPException
        raise HTTPException(status_code=409, detail="Welcome experience is not enabled")
    with get_cursor() as cursor:
        cursor.execute(
            "SELECT * FROM dashboard_v2_experiences WHERE user_id = %s FOR UPDATE",
            (user_id,),
        )
        current = cursor.fetchone()
        now = datetime.utcnow()
        if current:
            return _json_value(dict(current))
        cursor.execute(
            """
            INSERT INTO dashboard_v2_experiences
              (user_id, experience_type, status, started_at, ends_at, activation_trigger)
            VALUES (%s, 'WELCOME', 'ACTIVE', %s, %s, %s)
            RETURNING *
            """,
            (user_id, now, now + timedelta(hours=WELCOME_HOURS), trigger),
        )
        row = cursor.fetchone()
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
    for key, title, summary in (
        ("risk", "Risk", "What is the current risk level?"),
        ("change", "Change", "What changed since the last snapshot?"),
        ("confirm", "Confirm", "Which market signals confirm the move?"),
        ("interpret", "Interpret", "What does today’s intelligence mean?"),
        ("watch", "Watch", "What should you monitor next?"),
    ):
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
    completed = sum(step["status"] == "completed" for step in available_steps)
    return {
        "snapshot_id": snapshot_id,
        "steps": steps,
        "completed": completed,
        "available": len(available_steps),
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


def mark_routine_step(user_id: int, step_key: str, snapshot_id: str, complete: bool = False) -> dict:
    if step_key not in {"risk", "change", "confirm", "interpret", "watch"}:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Unknown Routine step")
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
        return _json_value(dict(cursor.fetchone()))


def primary_offer(user_id: int, entitlements: dict, routine: dict) -> Optional[dict]:
    experience = entitlements.get("experience")
    if experience and experience.get("ends_at"):
        return {
            "kind": "welcome",
            "priority": 4,
            "title": "Your 7-day intelligence welcome is active",
            "body": "Explore the full daily workflow, including live risk, reports, and internal widgets.",
            "ends_at": experience["ends_at"],
        }
    if routine["complete"] and routine["available"] >= 4 and not any(
        entitlements["capabilities"].get(cap)
        for cap in ("intraday_risk", "dir_full", "brent_forecast")
    ):
        return {
            "kind": "bundle_discovery",
            "priority": 7,
            "title": "Keep the full intelligence workflow connected",
            "body": "The €29 EnergyRiskIQ Intelligence Bundle brings live risk, Daily Intelligence, and Brent Forecast together.",
            "product_code": "intelligence_bundle",
        }
    return None


def bootstrap(user_id: int) -> dict:
    user = require_v2_access(user_id)
    snapshot = build_snapshot()
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
        "newsletter_context": {"state": "UNAVAILABLE", "context": None},
        "primary_offer": primary_offer(user_id, entitlements, routine),
        "snapshot": snapshot,
    }
