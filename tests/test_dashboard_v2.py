from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException

from src.dashboard_v2 import services
from src.dashboard_v2 import routes
from src.billing import webhook_handler


def test_allowlist_is_exact_and_fails_closed(monkeypatch):
    monkeypatch.setattr(services, "v2_enabled", lambda: True)
    monkeypatch.setattr(
        services,
        "get_v2_user",
        lambda _user_id: {"id": 1, "email": "other@example.com"},
    )

    with pytest.raises(HTTPException) as error:
        services.require_v2_access(1)

    assert error.value.status_code == 404


def test_freshness_never_labels_old_data_current():
    old = datetime.now(timezone.utc) - timedelta(days=10)
    state = services._freshness({"computed_at": old}, "geri_live")
    assert state["state"] == "UNAVAILABLE"

    missing = services._freshness(None, "geri_live")
    assert missing == {"state": "UNAVAILABLE", "as_of": None, "age_seconds": None}


def test_freshness_prefers_precise_compute_time_over_daily_date():
    now = datetime.now(timezone.utc)
    state = services._freshness(
        {"date": (now - timedelta(days=1)).date(), "computed_at": now},
        "geri_daily",
    )
    assert state["state"] == "FRESH"
    assert state["as_of"] == now.isoformat()


def test_briefing_synthesizes_low_risk_and_five_step_products():
    now = datetime.now(timezone.utc).isoformat()

    def row(data):
        return {
            "data": data,
            "state": {"state": "FRESH", "as_of": now, "age_seconds": 0},
        }

    snapshot = {
        "datasets": {
            "geri_daily": row({"value": 10, "band": "LOW", "trend_1d": -1}),
            "eeri_daily": row({"value": 17, "band": "LOW", "trend_1d": 0}),
            "egsi_m_daily": row({"index_value": 6.29, "band": "LOW", "trend_1d": 0.2}),
            "brent": row({"brent_price": 80, "brent_change_pct": 1.8}),
            "ttf": row({"ttf_price": 31}),
            "lng": row({"jkm_price": 12, "jkm_change_pct": 0}),
            "vix": row({"vix_close": 18, "vix_open": 17}),
            "geri_live": row({"value": 10, "trend_vs_yesterday": -1}),
            "storage": row({"eu_storage_percent": 82}),
        }
    }

    briefing = services.build_briefing(snapshot)
    assert "remain low" in briefing["summary"]
    assert briefing["what_matters"] == "No major risk escalation signal is currently active."
    assert set(briefing["steps"]) == {"risk", "change", "confirm", "interpret", "watch"}
    assert briefing["steps"]["confirm"]["confirmation_strength"]["total"] == 4
    assert briefing["steps"]["interpret"]["product_label"] == "Daily Intelligence Report · Brent Forecast"
    assert briefing["next_update_at"]


def test_routine_state_reports_five_step_progress(monkeypatch):
    monkeypatch.setattr(
        services,
        "_many",
        lambda *_args, **_kwargs: [
            {"step_key": "risk", "status": "completed", "available": True}
        ],
    )
    monkeypatch.setattr(services, "routine_started", lambda *_args: True)
    snapshot = {
        "snapshot_id": "intelligence:today",
        "datasets": {
            "geri_daily": {"state": {"state": "FRESH"}},
            "eeri_daily": {"state": {"state": "FRESH"}},
            "egsi_m_daily": {"state": {"state": "FRESH"}},
            "geri_live": {"state": {"state": "FRESH"}},
            "brent": {"state": {"state": "FRESH"}},
            "ttf": {"state": {"state": "FRESH"}},
            "vix": {"state": {"state": "FRESH"}},
            "storage": {"state": {"state": "FRESH"}},
        },
    }
    routine = services.routine_state(1, snapshot)
    assert routine["completed"] == 1
    assert routine["total_steps"] == 5
    assert routine["current_step"] == "change"
    assert routine["started"] is True
    assert routine["complete"] is False


def test_routine_can_complete_when_one_step_is_honestly_unavailable(monkeypatch):
    monkeypatch.setattr(
        services,
        "_many",
        lambda *_args, **_kwargs: [
            {"step_key": key, "status": "completed", "available": True}
            for key in ("risk", "change", "confirm", "interpret")
        ],
    )
    monkeypatch.setattr(services, "routine_started", lambda *_args: True)
    fresh = {"state": {"state": "FRESH"}}
    unavailable = {"state": {"state": "UNAVAILABLE"}}
    snapshot = {
        "snapshot_id": "intelligence:partial",
        "datasets": {
            "geri_daily": fresh,
            "eeri_daily": fresh,
            "egsi_m_daily": fresh,
            "brent": fresh,
            "ttf": fresh,
            "vix": fresh,
            "geri_live": unavailable,
            "storage": unavailable,
        },
    }
    routine = services.routine_state(1, snapshot)
    assert routine["completed"] == 4
    assert routine["available"] == 4
    assert routine["total_steps"] == 5
    assert routine["complete"] is True


def test_briefing_does_not_present_stale_core_risk_as_current():
    now = datetime.now(timezone.utc).isoformat()

    def row(value, state="FRESH"):
        return {
            "data": value,
            "state": {"state": state, "as_of": now, "age_seconds": 10},
        }

    snapshot = {
        "datasets": {
            "geri_daily": row({"value": 10, "band": "LOW"}, "STALE"),
            "eeri_daily": row({"value": 17, "band": "LOW"}),
            "egsi_m_daily": row({"index_value": 6.29, "band": "LOW"}),
        }
    }
    briefing = services.build_briefing(snapshot)
    assert briefing["state"] == "DEGRADED"
    assert "stale" in briefing["summary"].lower()
    assert "not as today’s current conclusion" in briefing["summary"]
    assert briefing["steps"]["confirm"]["confirmation_strength"] == {
        "confirmed": 0,
        "total": 0,
    }
    assert "no market-confirmation score" in briefing["steps"]["confirm"]["conclusion"]


def test_confirmation_requires_fresh_not_delayed_geri_direction():
    now = datetime.now(timezone.utc).isoformat()

    def row(data, state="FRESH"):
        return {
            "data": data,
            "state": {"state": state, "as_of": now, "age_seconds": 10},
        }

    snapshot = {
        "datasets": {
            "geri_daily": row(
                {"value": 10, "band": "LOW", "trend_1d": 1},
                "DELAYED",
            ),
            "eeri_daily": row({"value": 17, "band": "LOW"}),
            "egsi_m_daily": row({"index_value": 6.29, "band": "LOW"}),
            "brent": row({"brent_price": 79, "brent_change_pct": 1}),
        }
    }
    confirmation = services.build_briefing(snapshot)["steps"]["confirm"]
    assert confirmation["confirmation_strength"] == {"confirmed": 0, "total": 0}
    assert all(item["confirmation"] == "not measured" for item in confirmation["items"])


def test_confirmation_does_not_infer_vix_move_without_open_and_close():
    now = datetime.now(timezone.utc).isoformat()

    def row(data):
        return {
            "data": data,
            "state": {"state": "FRESH", "as_of": now, "age_seconds": 10},
        }

    snapshot = {
        "datasets": {
            "geri_daily": row({"value": 10, "band": "LOW", "trend_1d": 1}),
            "eeri_daily": row({"value": 17, "band": "LOW"}),
            "egsi_m_daily": row({"index_value": 6.29, "band": "LOW"}),
            "vix": row({"vix_close": 15.2}),
        }
    }
    confirmation = services.build_briefing(snapshot)["steps"]["confirm"]
    vix = next(item for item in confirmation["items"] if item["dataset"] == "vix")
    assert vix["change"] is None
    assert vix["confirmation"] == "not measured"
    assert confirmation["confirmation_strength"] == {"confirmed": 0, "total": 0}


def test_snapshot_identity_changes_when_same_day_daily_data_changes(monkeypatch):
    marker = {"geri_daily": 10}

    def fake_dataset(dataset, *_args, **_kwargs):
        return {
            "dataset": dataset,
            "data": {
                "date": "2026-08-30",
                "value": marker.get(dataset, 1),
            },
            "state": {
                "state": "FRESH",
                "as_of": "2026-08-30T01:30:00+00:00",
                "age_seconds": 0,
            },
        }

    monkeypatch.setattr(services, "_dataset", fake_dataset)
    monkeypatch.setattr(
        services,
        "_table_latest",
        lambda *_args, **_kwargs: {
            "date": "2026-08-30",
            "price": 1,
            "captured_at": datetime(2026, 8, 30, 1, 30, tzinfo=timezone.utc),
        },
    )
    first = services.build_snapshot()["snapshot_id"]
    marker["geri_daily"] = 11
    second = services.build_snapshot()["snapshot_id"]
    assert first != second
    assert first.startswith("intelligence:2026-08-30:")


def test_entitlement_sources_accumulate_paid_and_temporary_access(monkeypatch):
    def strict_one(query, _params=()):
        if "user_geri_live_subs" in query:
            return {"status": "active", "current_period_end": None}
        if "dashboard_v2_experiences" in query:
            return {
                "experience_type": "WELCOME",
                "status": "ACTIVE",
                "started_at": datetime.now(timezone.utc),
                "ends_at": datetime.now(timezone.utc) + timedelta(days=7),
            }
        return None

    monkeypatch.setattr(services, "_strict_one", strict_one)
    monkeypatch.setattr(services, "_strict_many", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(services, "_active_grants", lambda _user_id: {"intraday_risk"})
    monkeypatch.setattr(services, "_current_stripe_mode", lambda: "live")
    result = services._resolve_entitlements_live(
        1, {"id": 1, "email": services.V2_ALLOWLIST_EMAIL, "plan": "free"}
    )
    assert result["capabilities"]["intraday_risk"] is True
    assert set(result["sources"]["intraday_risk"]) == {
        "geri_live_subscription",
        "temporary_grant",
        "welcome",
    }


def test_access_ui_only_labels_exclusively_temporary_capabilities_as_included():
    html = Path("src/static/dashboard-v2.html").read_text()
    assert "sources.length>0&&sources.every" in html
    assert 'temporaryOnly?"Included":"Available"' in html


def test_client_honors_server_offer_dismissal_and_newsletter_entry_step():
    html = Path("src/static/dashboard-v2.html").read_text()
    assert "state.offerDismissed||!o" in html
    assert 'newsletter?.state==="ACTIVE"?newsletter.context?.entry_step:null' in html
    assert html.index("validSteps.includes(mappedStep)") < html.index(
        "validSteps.includes(state.data.routine.current_step)"
    )


def test_dismissed_welcome_is_not_returned_as_primary_offer(monkeypatch):
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(services, "get_experience", lambda _user_id: {})
    monkeypatch.setattr(services, "_offer_is_dismissed", lambda *_args: True)

    def one(query, _params=()):
        if "dashboard_v2_visits" in query:
            return {"visits": 0, "has_interest": False, "has_locked_intent": False}
        return {"owns_bundle": False, "standalone_count": 0}

    monkeypatch.setattr(services, "_one", one)
    offer = services.primary_offer(
        1,
        {
            "experience": {
                "experience_type": "WELCOME",
                "started_at": now.isoformat(),
                "ends_at": (now + timedelta(days=7)).isoformat(),
            },
            "capabilities": {},
            "sources": {},
        },
        {"complete": False},
    )
    assert offer is None


def test_welcome_offer_includes_day_and_exploration_cta(monkeypatch):
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(
        services,
        "get_experience",
        lambda _user_id: {
            "experience_type": "WELCOME",
            "status": "ACTIVE",
            "started_at": now - timedelta(days=1),
            "ends_at": now + timedelta(days=6),
        },
    )
    monkeypatch.setattr(services, "_offer_is_dismissed", lambda *_args: False)
    offer = services.primary_offer(
        1,
        {
            "experience": {
                "started_at": (now - timedelta(days=1)).isoformat(),
                "ends_at": (now + timedelta(days=6)).isoformat(),
            }
        },
        {"complete": False},
    )
    assert offer["kind"] == "welcome"
    assert offer["day_number"] == 2
    assert offer["days_remaining"] == 6
    assert offer["cta_href"] == "/dashboard/intelligence/geri-live"


def test_temporary_internal_widget_access_does_not_imply_embed():
    entitlements = {
        "capabilities": {
            "widget_wti_internal": True,
            "widget_wti_embed": False,
        }
    }
    assert services.widget_access(entitlements, "wti") == {
        "internal": True,
        "embed": False,
    }


def test_catalog_has_no_widget_pack_and_locked_prices():
    assert "widget_pack" not in services.PRODUCT_CATALOG
    assert services.PRODUCT_CATALOG["intelligence_bundle"]["price_eur"] == "29.00"
    for code in ("widget_wti", "widget_lng", "widget_storage"):
        assert services.PRODUCT_CATALOG[code]["price_eur"] == "4.95"


def test_routine_progress_uses_server_snapshot(monkeypatch):
    seen = {"calls": []}

    class Cursor:
        def execute(self, _query, params):
            seen["calls"].append(params)

        def fetchone(self):
            return {
                "user_id": 7,
                "snapshot_id": "intelligence:server",
                "step_key": "risk",
                "status": "completed",
            }

    class Context:
        def __enter__(self):
            return Cursor()

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(services, "get_cursor", lambda *args, **kwargs: Context())
    monkeypatch.setattr(
        services,
        "routine_state",
        lambda _user_id, _snapshot: {"complete": False},
    )
    monkeypatch.setattr(services, "record_event", lambda *args, **kwargs: None)
    snapshot = {
        "snapshot_id": "intelligence:server",
        "datasets": {
            "geri_daily": {"state": {"state": "FRESH"}},
            "eeri_daily": {"state": {"state": "UNAVAILABLE"}},
            "egsi_m_daily": {"state": {"state": "UNAVAILABLE"}},
        },
    }

    result = services.mark_routine_step(7, "risk", snapshot, complete=True)
    assert seen["calls"][0][1] == "intelligence:server"
    assert result["status"] == "completed"


def test_event_payload_strips_direct_pii(monkeypatch):
    captured = {}

    class Cursor:
        def execute(self, _query, params):
            captured["params"] = params

    class Context:
        def __enter__(self):
            return Cursor()

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(services, "get_cursor", lambda *args, **kwargs: Context())
    services.record_event(
        2,
        "premium_intent",
        "analytics",
        {"capability": "dir_full", "email": "not-stored@example.com", "name": "No"},
        True,
    )
    envelope = captured["params"][2]
    assert "not-stored@example.com" not in envelope
    assert '"name"' not in envelope
    assert "dir_full" in envelope


def test_analytics_event_without_consent_is_not_written(monkeypatch):
    monkeypatch.setattr(
        services,
        "get_cursor",
        lambda *args, **kwargs: pytest.fail("database should not be called"),
    )
    services.record_event(2, "viewed", "analytics", {"step": "risk"}, False)


def test_v2_invoice_is_classified_before_mirror_exists():
    invoice = {
        "parent": {
            "subscription_details": {
                "metadata": {"dashboard_v2_product": "intelligence_bundle"}
            }
        }
    }
    assert webhook_handler._invoice_is_dashboard_v2(invoice) is True


def test_unknown_invoice_remains_legacy_when_stripe_lookup_fails(monkeypatch):
    monkeypatch.setattr(
        webhook_handler.stripe.Subscription,
        "retrieve",
        lambda _subscription_id: (_ for _ in ()).throw(RuntimeError("temporary outage")),
    )
    assert webhook_handler._invoice_is_dashboard_v2(
        {"subscription": "sub_unknown"}
    ) is False


def test_valid_newsletter_entry_creates_opaque_context(monkeypatch):
    calls = []

    class Cursor:
        def execute(self, query, params):
            calls.append((query, params))

        def fetchone(self):
            return {
                "edition_slug": "weekly-1",
                "topic": "Gas storage",
                "entry_step": "watch",
                "featured_product": None,
                "companion_content": {},
            }

    class Context:
        def __enter__(self):
            return Cursor()

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(services, "feature_enabled", lambda _key: True)
    monkeypatch.setattr(routes, "get_cursor", lambda *args, **kwargs: Context())
    response = routes.dashboard_v2_newsletter_entry("weekly-1")

    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"
    assert "dashboard_v2_newsletter=" in response.headers["set-cookie"]
    assert any("INSERT INTO dashboard_v2_newsletter_context" in query for query, _ in calls)