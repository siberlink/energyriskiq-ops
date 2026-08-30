from datetime import datetime, timedelta, timezone

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