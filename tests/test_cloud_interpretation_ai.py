"""Offline credential routing, fallback provenance, persistence and stage audits."""
from datetime import date
import json
from types import SimpleNamespace

import httpx
import pytest


@pytest.fixture(autouse=True)
def website_pair_offline(monkeypatch):
    monkeypatch.setattr("src.reri.website_trigger.run_website_pair",
                        lambda **kw: {"status": "success"})

from src.ai.interpretation_client import client_options
from src.geri.interpretation import generate_interpretation
from src.egsi.interpretation import generate_egsi_interpretation


@pytest.fixture(autouse=True)
def clean_credentials(monkeypatch):
    for key in ("AI_INTEGRATIONS_OPENAI_API_KEY", "AI_INTEGRATIONS_OPENAI_BASE_URL",
                "OPENAI_API_KEY", "OPENAI_BASE_URL"):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def transport(monkeypatch):
    calls = []
    text = ("AI supplied interpretation. Regional and asset components are inactive. " * 26)
    def handle(self, request):
        calls.append((request.url.host, json.loads(request.content)))
        return httpx.Response(200, request=request, json={
            "id": "offline", "object": "chat.completion", "created": 1,
            "model": "offline", "choices": [{"index": 0,
                "message": {"role": "assistant", "content": text + "\n\n" + text},
                "finish_reason": "stop"}]})
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", handle)
    return calls


def generate(kind, status):
    if kind == "geri":
        return generate_interpretation(11, "LOW", [], [], "2026-11-10",
                                      components={}, ai_status=status)
    return generate_egsi_interpretation(30, "NORMAL", [], {}, "2026-11-10",
                                       index_type="EGSI-S", ai_status=status)


@pytest.mark.parametrize("kind", ["geri", "egsi_s"])
@pytest.mark.parametrize("custom_url", [False, True])
def test_direct_key_uses_ai_transport(kind, custom_url, transport, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "offline")
    if custom_url:
        monkeypatch.setenv("OPENAI_BASE_URL", "https://offline.invalid/v1")
    status = {}
    assert generate(kind, status).startswith("AI supplied")
    assert status == {"ai_section_missing": False, "ai_source": "direct"}
    assert transport[0][0] == ("offline.invalid" if custom_url else "api.openai.com")


@pytest.mark.parametrize("kind", ["geri", "egsi_s"])
def test_missing_key_falls_back_and_flags(kind, transport):
    status = {}
    assert generate(kind, status)
    assert status == {"ai_section_missing": True, "ai_source": "none",
                      "ai_fallback_reason": "no_credentials"}
    assert not transport


@pytest.mark.parametrize("kind", ["geri", "egsi_s"])
@pytest.mark.parametrize("failure", ["connection", "empty"])
def test_ai_failure_is_flagged_without_exposing_exception(kind, failure, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "offline")
    def handle(self, request):
        if failure == "connection":
            raise httpx.ConnectError("do-not-log-sensitive-endpoint", request=request)
        return httpx.Response(200, request=request, json={"choices": [{
            "index": 0, "message": {"role": "assistant", "content": ""}}]})
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", handle)
    status = {}
    assert generate(kind, status)
    assert status["ai_section_missing"] is True
    assert status["ai_fallback_reason"] in ("APIConnectionError", "ValueError")
    assert "do-not-log" not in json.dumps(status)


def test_complete_integration_pair_wins(transport, monkeypatch):
    monkeypatch.setenv("AI_INTEGRATIONS_OPENAI_API_KEY", "integration-offline")
    monkeypatch.setenv("AI_INTEGRATIONS_OPENAI_BASE_URL", "https://integration.invalid/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "direct-offline")
    status = {}
    generate("geri", status)
    assert transport[0][0] == "integration.invalid"
    assert status["ai_source"] == "integration"


@pytest.mark.parametrize("partial", ["AI_INTEGRATIONS_OPENAI_API_KEY",
                                   "AI_INTEGRATIONS_OPENAI_BASE_URL"])
def test_incomplete_integration_pair_uses_direct_key(partial, monkeypatch):
    monkeypatch.setenv(partial, "offline")
    monkeypatch.setenv("OPENAI_API_KEY", "direct-offline")
    options, source = client_options()
    assert options == {"api_key": "direct-offline"}
    assert source == "direct"


@pytest.mark.parametrize("has_key", [True, False])
def test_egsi_s_service_persists_status_and_stage_reports_it(has_key, transport, monkeypatch):
    from src.egsi import service_egsi_s as service
    from src.egsi.types import EGSISComponents
    from src.api import internal_routes as routes
    if has_key:
        monkeypatch.setenv("OPENAI_API_KEY", "offline")
    monkeypatch.setattr(service, "ENABLE_EGSI", True)
    monkeypatch.setattr(service, "get_egsi_s_for_date", lambda _: None)
    monkeypatch.setattr(service, "get_market_data_provider",
                        lambda: SimpleNamespace(get_snapshot=lambda _: SimpleNamespace(source="offline")))
    monkeypatch.setattr(service, "fetch_alerts_for_date", lambda *a, **k: [])
    monkeypatch.setattr(service, "compute_egsi_s_components", lambda *a: EGSISComponents())
    monkeypatch.setattr(service, "compute_egsi_s_value", lambda _: 30)
    monkeypatch.setattr(service, "compute_egsi_s_trends", lambda _: (0, 0))
    saved = []
    monkeypatch.setattr(service, "save_egsi_s_result", lambda r: saved.append(r.components.to_dict()))
    result = service.compute_egsi_s_for_date(date(2026, 11, 10))
    assert saved[0]["ai_section_missing"] is (not has_key)
    monkeypatch.setattr(routes, "validate_runner_token", lambda _: None)
    monkeypatch.setattr(routes, "run_job_with_lock",
                        lambda name, operation: ({"status": "ok", "details": operation()}, 200))
    from src.egsi import repo, types
    monkeypatch.setattr(types, "ENABLE_EGSI", True)
    monkeypatch.setattr(repo, "get_egsi_s_for_date", lambda _: None)
    monkeypatch.setattr(service, "compute_egsi_s_for_date", lambda *a, **k: result)
    stage = routes.run_egsi_s_compute("2026-11-10", False, "offline")
    assert stage["details"]["ai_section_missing"] is (not has_key)
    if not has_key:
        assert routes._validate_daily_stage("egsi_s", stage) == stage
    else:
        assert routes._validate_daily_stage("egsi_s", stage) == stage


def test_existing_fallback_is_usable_without_hiding_its_flag():
    from src.api.internal_routes import _validate_daily_stage
    stage = {"status": "ok", "details": {
        "status": "skipped", "reason": "already_exists", "ai_section_missing": True}}
    assert _validate_daily_stage("egsi_s", stage)["details"]["ai_section_missing"]


def test_existing_ingestion_client_supports_direct_key_without_image_change(monkeypatch):
    from src.ai.ai_worker import get_openai_client
    monkeypatch.setenv("OPENAI_API_KEY", "offline")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://offline.invalid/v1")
    with get_openai_client() as client:
        assert str(client.base_url) == "https://offline.invalid/v1/"


@pytest.mark.parametrize("failed_stage", ["geri", "egsi_s"])
def test_daily_pipeline_records_missing_ai(failed_stage, monkeypatch):
    from src.api import internal_routes as routes
    monkeypatch.setattr(routes, "validate_runner_token", lambda _: None)
    monkeypatch.setattr(routes, "run_job_with_lock",
                        lambda name, operation: ({"status": "ok", "details": operation()}, 200))
    for name in ("run_market_data_capture", "run_oil_price_capture", "run_gas_storage_capture",
                 "run_lng_price_capture", "run_daily_report"):
        monkeypatch.setattr(routes, name, lambda **kw: {"status": "success"})
    monkeypatch.setattr(routes, "run_geri_compute", lambda **kw: {
        "status": "ok", "details": {"status": "success", "value": 11,
                                   "ai_section_missing": failed_stage == "geri"}})
    monkeypatch.setattr(routes, "run_egsi_s_compute", lambda **kw: {
        "status": "ok", "details": {"status": "success", "value": 30,
                                   "ai_section_missing": failed_stage == "egsi_s"}})
    result = routes.run_daily_index_pipeline(include_delivery=False, x_runner_token="offline")
    details = result["details"]
    assert details["pipeline_status"] == "degraded"
    assert details["failed_stages"] == [failed_stage]
    assert details[failed_stage]["ai_section_missing"] is True
    if failed_stage == "geri":
        assert details["daily_report"]["status"] == "success"
