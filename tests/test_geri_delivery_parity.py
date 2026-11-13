"""Standalone delivery parity. All external boundaries are blocked/mocked."""
import importlib
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from tests.test_guarded_index_digest import harness


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setenv("GERI_PUBLISHED_MODEL", "v1.1")
    monkeypatch.setenv("GERI_LIVE_MODEL", "legacy")
    monkeypatch.setenv("ALERTS_EMAIL_ENABLED", "false")
    monkeypatch.setenv("RISK_PIPELINE_V2_MODE", "off")
    monkeypatch.setenv("RISK_PIPELINE_V2_ENABLED", "false")


@pytest.mark.parametrize("version", ["v1.1", "v1.2"])
def test_delivery_and_daily_read_selected_sql(monkeypatch, version):
    from src.delivery import pro_delivery_worker as worker
    from src.api import daily_digest_routes as daily
    monkeypatch.setenv("GERI_PUBLISHED_MODEL", version)
    queries = []

    def query(sql, *args, **kwargs):
        queries.append(sql)
        selected = "public.intel_indices_daily_v12" in sql
        assert selected == (version == "v1.2")
        return [{"date": date(2026, 11, 8), "value": 11 if selected else 9}]

    monkeypatch.setattr(worker, "execute_one", lambda sql: query(sql)[0])
    monkeypatch.setattr(worker, "execute_query", query)
    monkeypatch.setattr(daily, "execute_production_query", query)
    assert worker.get_latest_geri()["value"] == (11 if version == "v1.2" else 9)
    assert worker.get_latest_geri(delayed=True)["value"] == (11 if version == "v1.2" else 9)
    assert worker.get_geri_history()[0]["value"] == (11 if version == "v1.2" else 9)
    assert daily.get_index_snapshot("global:geo_energy_risk")[0]["value"] == (11 if version == "v1.2" else 9)
    assert len(queries) == 4
    assert "date < CURRENT_DATE" in queries[1]


def test_missing_selected_observation_never_falls_back(monkeypatch):
    from src.delivery import pro_delivery_worker as worker
    monkeypatch.setenv("GERI_PUBLISHED_MODEL", "v1.2")
    read = Mock(return_value=None)
    monkeypatch.setattr(worker, "execute_one", read)
    assert worker.get_latest_geri() is None
    assert read.call_count == 1
    assert "intel_indices_daily_v12" in read.call_args.args[0]


@pytest.mark.parametrize("version", ["v1.1", "v1.2"])
@pytest.mark.parametrize("plan", ["free", "personal", "trader", "pro", "enterprise"])
@pytest.mark.parametrize("target", ["delivery", "daily"])
def test_actual_prompts_use_context_without_decomposition(monkeypatch, version, plan, target):
    import openai
    from src.delivery import pro_delivery_worker as worker
    from src.api import daily_digest_routes as daily
    from src.geri.narrative_context import INACTIVE_NOTE
    monkeypatch.setenv("GERI_PUBLISHED_MODEL", version)
    create = Mock(return_value=SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="Offline test answer"))]))
    monkeypatch.setattr(openai, "OpenAI", lambda **kwargs: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    observation = {"value": 11 if version == "v1.2" else 9,
                   "date": date(2026, 11, 8), "band": "LOW", "trend_1d": -1}
    if target == "delivery":
        result = worker.generate_ai_digest_for_plan(plan, observation, {}, {})
    else:
        result = daily.generate_ai_digest(
            plan, [], [observation], [], [], {}, {}, {}, {"tone": "Calm"}, "Calm")
    assert result == "Offline test answer"
    text = "\n".join(m["content"] for m in create.call_args.kwargs["messages"])
    assert f'"methodology_version": "{version}"' in text
    assert '"observation_date": "2026-11-08"' in text
    assert ("inactive_component_note" in text)
    assert (INACTIVE_NOTE in text) == (version == "v1.2")
    assert "INDEX DECOMPOSITION" not in text
    assert "component drivers" not in text
    assert "component attribution" not in text
    assert "Do not invent or provide a breakdown" in text


@pytest.mark.parametrize("version", ["v1.1", "v1.2"])
def test_channel_renderers_include_selected_methodology(monkeypatch, version):
    from src.delivery import pro_delivery_worker as worker
    from src.geri.delivery_context import methodology_note
    monkeypatch.setenv("GERI_PUBLISHED_MODEL", version)
    observation = {"value": 11 if version == "v1.2" else 9, "date": date(2026, 11, 8),
                   "components": {"regional_spike_score": 0, "asset_risk_score": 0}}
    html = worker.build_geri_section_email(observation, "enterprise")
    text = worker.build_geri_telegram(observation, "enterprise")
    for rendered in (html, text):
        assert f"GERI methodology {version}" in rendered
        assert methodology_note() in rendered
        assert ("currently inactive" in rendered) == (version == "v1.2")
        assert "Component Scores" not in rendered
        assert "Regional Spike Score:" not in rendered


@pytest.mark.parametrize("version", ["v1.1", "v1.2"])
def test_daily_cache_matches_website_namespace(monkeypatch, version):
    from src.api import daily_digest_routes as daily
    monkeypatch.setenv("GERI_PUBLISHED_MODEL", version)
    read, write = Mock(return_value=None), Mock()
    monkeypatch.setattr(daily, "execute_one", read)
    monkeypatch.setattr(daily, "execute_query", write)
    daily.get_cached_ai_narrative("v1:4:2026-11-09:l")
    daily.set_cached_ai_narrative("v1:4:2026-11-09:l", "Offline fixture")
    key = "v1:4:2026-11-09:l" + (":geri_v1.2" if version == "v1.2" else "")
    assert read.call_args.args[1] == (key,)
    assert write.call_args.args[1] == (key, "Offline fixture")


@pytest.mark.parametrize("flag", [None, "false", "", "invalid"])
def test_alert_pause_defaults_off_and_never_calls_transport(monkeypatch, flag):
    from src.alerts import channels, channel_adapters
    if flag is None:
        monkeypatch.delenv("ALERTS_EMAIL_ENABLED", raising=False)
    else:
        monkeypatch.setenv("ALERTS_EMAIL_ENABLED", flag)
    adapter = importlib.reload(channel_adapters)
    transport = Mock(side_effect=AssertionError("No real send"))
    monkeypatch.setattr(channels, "send_email", transport)
    assert channels.send_alert_email("fixture@example.invalid", "Test", "Offline")[0] is False
    result = adapter.send_email_v2("fixture@example.invalid", "Test", "Offline")
    assert result.should_skip and result.skip_reason == "email_disabled"
    transport.assert_not_called()


def test_legacy_sender_bindings_and_telegram_preserved(monkeypatch):
    from src.alerts import channels, alerts_engine, alerts_engine_v2, digest_worker
    for module in (alerts_engine, alerts_engine_v2, digest_worker):
        assert module.send_email is channels.send_alert_email
    monkeypatch.setattr(channels, "TELEGRAM_BOT_TOKEN", "offline-fixture")
    post = Mock(return_value=SimpleNamespace(
        status_code=200, json=lambda: {"ok": True}))
    monkeypatch.setattr(channels.requests, "post", post)
    assert channels.send_telegram("offline-chat", "Offline test")[0] is True
    post.assert_called_once()


def test_transactional_email_transport_is_not_paused(monkeypatch):
    from src.alerts import channels
    monkeypatch.setattr(channels, "EMAIL_PROVIDER", "brevo")
    transport = Mock(return_value=(True, None, "offline-id"))
    monkeypatch.setattr(channels, "_send_brevo", transport)
    assert channels.send_email("fixture@example.invalid", "Verification", "Offline")[0]
    transport.assert_called_once()


@pytest.mark.parametrize("version", ["v1.1", "v1.2"])
def test_real_delivery_loop_preserves_opt_ins_and_email_pause(monkeypatch, version, harness):
    from src.delivery import pro_delivery_worker as worker
    from src.alerts import channel_adapters as adapters
    monkeypatch.setenv("GERI_PUBLISHED_MODEL", version)
    monkeypatch.setattr(adapters, "ALERTS_EMAIL_ENABLED", False)
    monkeypatch.setattr(worker, "ensure_index_digest_unique_index", lambda: None)
    monkeypatch.setattr(worker, "get_all_users_with_plans", lambda: [
        {"id": 1, "email": "fixture@example.invalid", "telegram_chat_id": "offline-chat",
         "plan": "enterprise"}])
    prefs = {1: {"geri": {"email": True, "telegram": True}}}
    monkeypatch.setattr(worker, "get_user_delivery_preferences", lambda ids: prefs)
    observation = {"value": 11 if version == "v1.2" else 9,
                   "date": date(2026, 11, 8), "band": "LOW", "trend_1d": -1}
    harness.rows["geri"]["value"] = observation["value"]
    monkeypatch.setattr(worker, "get_latest_geri", lambda **kwargs: observation)
    for name in ("get_latest_eeri", "get_latest_egsi", "get_asset_snapshots"):
        monkeypatch.setattr(worker, name, lambda: {})
    monkeypatch.setattr(worker, "has_been_delivered_today", lambda *args: False)
    monkeypatch.setattr(worker, "send_email_v2", adapters.send_email_v2)
    telegram = Mock(return_value=adapters.SendResult(success=True))
    record = Mock()
    monkeypatch.setattr(worker, "send_telegram_v2", telegram)
    monkeypatch.setattr(worker, "record_index_delivery", record)
    result = worker.run_index_delivery(send=True)
    assert result["emails_sent"] == 0 and result["emails_skipped"] == 1
    assert result["telegrams_sent"] == 1
    assert f"GERI methodology {version}" in telegram.call_args.args[1]
    assert str(observation["value"]) in telegram.call_args.args[1]
    assert prefs == {1: {"geri": {"email": True, "telegram": True}}}
    assert any(e[2] == "email" and e[3] == "skipped"
               and e[4].get("reason") == "email_disabled" for e in harness.events)
    assert record.call_args_list[0].args == (1, "telegram", "sent")
