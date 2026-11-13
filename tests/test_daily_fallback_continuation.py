"""Missing AI is observable but does not block persisted-index delivery."""
import pytest
from tests.test_guarded_index_digest import harness


@pytest.fixture(autouse=True)
def website_pair_offline(monkeypatch):
    monkeypatch.setattr("src.reri.website_trigger.run_website_pair",
                        lambda **kw: {"status": "success"})


def test_report_fallback_is_persisted_and_cache_hit_retains_provenance(monkeypatch):
    from src.api import daily_digest_routes as digest
    cache, calls = {}, []
    monkeypatch.setattr(digest, "get_cached_ai_narrative", cache.get)
    monkeypatch.setattr(digest, "set_cached_ai_narrative",
                        lambda key, text: cache.update({key: text}))
    def generate():
        calls.append("attempt")
        return None
    args = ("report", generate, [{"date": "2026-11-10", "value": 11, "band": "LOW"}],
            [], [], "2026-11-10")
    first = digest.resolve_daily_narrative(*args)
    assert first[1] and "deterministic briefing" in first[0]
    assert cache["report:deterministic-fallback"] == first[0]
    assert digest.resolve_daily_narrative(*args) == first
    assert calls == ["attempt"]
    cache["report"] = "Recovered generated narrative"
    assert digest.resolve_daily_narrative(*args) == ("Recovered generated narrative", False)


@pytest.mark.parametrize("stage", ["geri", "egsi_s", "daily_report"])
def test_fallback_stage_does_not_block_warming_or_delivery(stage, monkeypatch):
    from src.api import internal_routes as routes
    monkeypatch.setattr(routes, "validate_runner_token", lambda _: None)
    monkeypatch.setattr(routes, "run_job_with_lock",
                        lambda name, op: ({"status": "ok", "details": op()}, 200))
    monkeypatch.setattr(routes.time, "sleep", lambda _: None)
    for name in ("run_market_data_capture", "run_oil_price_capture",
                 "run_gas_storage_capture", "run_lng_price_capture"):
        monkeypatch.setattr(routes, name, lambda **kw: {"status": "success"})
    calls = []
    def result(name):
        def operation(**kwargs):
            calls.append((name, kwargs))
            return {"status": "success", "value": 11, "ai_section_missing": name == stage}
        return operation
    for name, operation in (("geri", "run_geri_compute"), ("egsi_s", "run_egsi_s_compute"),
                            ("daily_report", "run_daily_report"), ("delivery", "run_pro_delivery")):
        monkeypatch.setattr(routes, operation, result(name))
    details = routes.run_daily_index_pipeline(True, "offline")["details"]
    assert [name for name, _ in calls] == ["geri", "egsi_s", "daily_report", "delivery"]
    assert calls[-1][1]["ai_section_missing"] is True
    assert details["pipeline_status"] == "degraded"
    assert details[stage]["ai_section_missing"]


def test_stored_geri_fallback_flags_standalone_delivery_audit(monkeypatch, harness):
    harness.rows["geri"]["components"]["ai_section_missing"] = True
    from types import SimpleNamespace
    from src.delivery import pro_delivery_worker as delivery
    monkeypatch.setattr(delivery, "ensure_index_digest_unique_index", lambda: None)
    monkeypatch.setattr(delivery, "get_all_users_with_plans", lambda: [
        {"id": 1, "email": None, "telegram_chat_id": "offline", "plan": "personal"}])
    monkeypatch.setattr(delivery, "get_user_delivery_preferences",
                        lambda _: {1: {"geri": {"telegram": True}}})
    monkeypatch.setattr(delivery, "get_latest_geri", lambda **kw: {
        "date": "2026-11-10", "value": 11, "components": {"ai_section_missing": True}})
    for name in ("get_latest_eeri", "get_latest_egsi", "get_asset_snapshots"):
        monkeypatch.setattr(delivery, name, lambda: {})
    monkeypatch.setattr(delivery, "has_been_delivered_today", lambda *a: False)
    monkeypatch.setattr(delivery, "build_full_telegram", lambda *a, **kw: "offline")
    monkeypatch.setattr(delivery, "send_telegram_v2", lambda *a: SimpleNamespace(success=True))
    audits = []
    monkeypatch.setattr(delivery, "record_index_delivery", lambda *a, **kw: audits.append(kw))
    result = delivery.run_index_delivery(send=True)
    assert result["ai_section_missing"] and audits[0]["ai_section_missing"]
