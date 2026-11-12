from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

from src.reri import website_trigger as trigger


def response(**updates):
    day = str(datetime.now(timezone.utc).date() - timedelta(days=1))
    body = {"success": True, "stages": {
        "eeri": {"status": "existing", "date": day, "value": 51, "model_version": "eeri_ttf_v3"},
        "egsi_m": {"status": "stored", "date": day, "value": 18.24}}}
    body.update(updates)
    return SimpleNamespace(status_code=200, json=lambda: body)


@pytest.fixture
def transport(monkeypatch):
    monkeypatch.setenv("WEBSITE_BASE_URL", "https://website.invalid")
    monkeypatch.setenv("INTERNAL_RUNNER_TOKEN", "offline")
    post = Mock(return_value=response())
    monkeypatch.setattr(trigger.requests, "post", post)
    monkeypatch.setattr(trigger.time, "sleep", Mock())
    return post


def test_success_and_auth_header_without_logging(transport):
    result = trigger.run_website_pair()
    assert result["status"] == "success"
    assert result["index_observations"]["egsi_m"]["value"] == 18.24
    assert transport.call_args.kwargs["headers"] == {"X-Runner-Token": "offline"}
    assert transport.call_args.kwargs["timeout"] == (10, 90)
    assert transport.call_args.kwargs["allow_redirects"] is False


@pytest.mark.parametrize("error", [requests.Timeout, requests.ConnectionError])
def test_transient_errors_have_two_bounded_retries(transport, error):
    transport.side_effect = error("offline")
    with pytest.raises(RuntimeError):
        trigger.run_website_pair()
    assert transport.call_count == 3
    assert [c.args[0] for c in trigger.time.sleep.call_args_list] == [10, 30]


def test_retry_then_success(transport):
    transport.side_effect = [requests.Timeout(), response()]
    assert trigger.run_website_pair()["attempts"] == 2


@pytest.mark.parametrize("status,retries", [(401, 1), (403, 1), (302, 1), (503, 3)])
def test_http_errors(transport, status, retries):
    transport.return_value.status_code = status
    with pytest.raises((ValueError, RuntimeError)):
        trigger.run_website_pair()
    assert transport.call_count == retries


def test_http_200_failure_is_failure(transport):
    transport.return_value = response(success=False, status="failed")
    with pytest.raises(ValueError):
        trigger.run_website_pair()
    assert transport.call_count == 1


def test_busy_retries(transport):
    transport.side_effect = [response(success=False, status="busy", retryable=True), response()]
    assert trigger.run_website_pair()["attempts"] == 2


def test_wrong_date_or_model_not_success(transport):
    transport.return_value.json()["stages"]["eeri"]["date"] = "2000-01-01"
    with pytest.raises(ValueError):
        trigger.run_website_pair()
    transport.return_value = response()
    transport.return_value.json()["stages"]["eeri"]["model_version"] = "eeri_v1"
    with pytest.raises(ValueError):
        trigger.run_website_pair()


def test_index_dates_are_json_safe_and_staleness_is_explicit():
    import json
    from src.delivery.index_dates import index_observations
    data = index_observations({"date": "2026-11-11", "value": 14},
                              {"date": "2000-01-01", "value": 51},
                              {"date": "2000-01-01", "value": Decimal("18.24")})
    assert data["eeri"]["stale"] is True
    assert data["egsi_m"]["value"] == 18.24
    assert json.loads(json.dumps(data)) == data


@pytest.mark.parametrize("generated", [None, "Generated offline narrative"])
def test_cached_narrative_does_not_relabel_old_input_dates(monkeypatch, generated):
    import json
    from src.api import daily_digest_routes as digest
    cache = {}
    monkeypatch.setattr(digest, "get_cached_ai_narrative", cache.get)
    monkeypatch.setattr(digest, "set_cached_ai_narrative",
                        lambda key, text: cache.update({key: text}))
    args = ("report", lambda: generated, [{"date": "2000-01-01", "value": 14, "band": "LOW"}],
            [{"date": "2000-01-01", "value": 51}], [], "2000-01-01")
    first = digest.resolve_daily_narrative(*args)
    key = "report" + (":deterministic-fallback" if generated is None else "") + ":input-indices"
    original = cache[key]
    args[3][0]["date"] = "2000-01-02"
    assert digest.resolve_daily_narrative(*args) == first
    assert cache[key] == original
    assert json.loads(original)["eeri"]["date"] == "2000-01-01"


@pytest.mark.parametrize("status", [200, 401])
def test_binding_probe_is_read_only_and_never_prints_secret(transport, monkeypatch, capsys, status):
    from scripts import check_website_runner_auth as probe
    get = Mock(return_value=SimpleNamespace(status_code=status))
    monkeypatch.setattr(probe.requests, "get", get)
    assert probe.main() == (0 if status == 200 else 1)
    assert get.call_args.args[0].endswith("/internal/alerts/engine/runs?limit=1")
    assert get.call_args.kwargs["allow_redirects"] is False
    output = capsys.readouterr().out
    assert "offline" not in output and str(status) in output
    transport.assert_not_called()


@pytest.mark.parametrize("pair_failed", [False, True])
def test_stage_order_pair_failure_continues_report_delivery(monkeypatch, pair_failed):
    from src.api import internal_routes as routes
    monkeypatch.setattr(routes, "validate_runner_token", lambda _: None)
    monkeypatch.setattr(routes, "run_job_with_lock",
                        lambda name, fn: ({"status": "ok", "details": fn()}, 200))
    monkeypatch.setattr(routes.time, "sleep", lambda _: None)
    calls = []
    def operation(name):
        def run(**kw):
            calls.append(name)
            if pair_failed and name == "eeri_egsi_m":
                raise RuntimeError("offline unavailable")
            return {"status": "success", "value": 14}
        return run
    names = ["market_data", "oil_price", "gas_storage", "geri", "eeri_egsi_m",
             "lng_price", "egsi_s", "daily_report", "delivery"]
    for name, attr in zip(names, ["run_market_data_capture", "run_oil_price_capture",
        "run_gas_storage_capture", "run_geri_compute", None, "run_lng_price_capture",
        "run_egsi_s_compute", "run_daily_report", "run_pro_delivery"]):
        monkeypatch.setattr(trigger if attr is None else routes,
                            "run_website_pair" if attr is None else attr, operation(name))
    details = routes.run_daily_index_pipeline(True, "offline")["details"]
    assert calls == names
    assert (details["pipeline_status"] == "degraded") is pair_failed
    assert ("eeri_egsi_m" in details.get("failed_stages", [])) is pair_failed
