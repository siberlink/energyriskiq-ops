"""Offline worker release regression tests; no DB, transport, AI or deliveries."""
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock
import socket

import psycopg2
import pytest


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv("RISK_PIPELINE_V2_MODE", "off")
    monkeypatch.setenv("RISK_PIPELINE_V2_ENABLED", "false")
    monkeypatch.setenv("GERI_PUBLISHED_MODEL", "v1.1")
    monkeypatch.setenv("GERI_LIVE_MODEL", "legacy")
    monkeypatch.setattr(psycopg2, "connect", Mock(side_effect=AssertionError("No database")))
    monkeypatch.setattr(socket.socket, "connect", Mock(side_effect=AssertionError("No network")))


def fixture(monkeypatch, model, existing=False, fail_private=False):
    from src.geri import service, job_health, version12
    from src.geri.model_selection import published_model, live_model
    monkeypatch.setenv("GERI_PUBLISHED_MODEL", model)
    monkeypatch.setenv("GERI_LIVE_MODEL", "v1.2" if model == "v1.2" else "legacy")
    monkeypatch.setattr(service, "ENABLE_GERI", True)
    monkeypatch.setattr(job_health, "start_run", lambda *a: 1)
    finish = Mock()
    monkeypatch.setattr(job_health, "finish_run", finish)
    steps = []
    def legacy(*args):
        assert published_model() == "v1.1"
        assert live_model() == "legacy"
        steps.extend(["final_health", "legacy_skip" if existing else "legacy_write"])
        return None if existing else SimpleNamespace(value=9, publication_status="stored")
    monkeypatch.setattr(service, "_compute_geri_for_date", legacy)
    def private(*args):
        assert steps[0] == "final_health"
        assert published_model() == model
        steps.append("private")
        if fail_private:
            raise RuntimeError("Private computation unavailable")
        return {"smoothing_state": {"data_quality": "OK"}, "value": 11,
                "components": {}, "trend_1d": 1, "trend_7d": 2}
    monkeypatch.setattr(version12, "compute_day", private)
    monkeypatch.setattr(service, "build_result", lambda d, v, *a: SimpleNamespace(value=v))
    return service, steps, finish


@pytest.mark.parametrize("model", ["v1.1", "v1.2"])
@pytest.mark.parametrize("existing", [False, True])
def test_worker_preserves_writer_and_returns_selected_value(monkeypatch, model, existing):
    service, steps, finish = fixture(monkeypatch, model, existing)
    result = service.compute_geri_for_date(date(2026, 11, 9))
    assert steps == ["final_health", "legacy_skip" if existing else "legacy_write", "private"]
    if model == "v1.2":
        assert result.value == 11
        assert result.model_version == "geri_v1.2"
        assert result.publication_status == "stored_v12"
    elif existing:
        assert result is None
    else:
        assert result.value == 9
    assert finish.call_args.args[1] != "error"


def test_selected_private_failure_is_not_reported_as_legacy_success(monkeypatch):
    service, _, finish = fixture(monkeypatch, "v1.2", fail_private=True)
    with pytest.raises(RuntimeError, match="Private computation unavailable"):
        service.compute_geri_for_date(date(2026, 11, 9))
    assert finish.call_args.args[1] == "error"


def test_legacy_availability_is_preserved_when_private_stage_fails(monkeypatch):
    service, _, finish = fixture(monkeypatch, "v1.1", fail_private=True)
    assert service.compute_geri_for_date(date(2026, 11, 9)).value == 9
    assert finish.call_args.args[1] == "stored"


def test_real_handler_uses_legacy_existence_check_and_selected_service(monkeypatch):
    from src.api import internal_routes as routes
    from src.geri import repo, service, job_health
    from src.geri.model_selection import published_model
    monkeypatch.setenv("GERI_PUBLISHED_MODEL", "v1.2")
    monkeypatch.setenv("GERI_LIVE_MODEL", "v1.2")
    monkeypatch.setattr(routes, "validate_runner_token", lambda *a: None)
    monkeypatch.setattr(routes, "run_job_with_lock", lambda name, fn: (fn(), 200))
    def existing(day):
        assert published_model() == "v1.1"
        return {"value": 9}
    monkeypatch.setattr(repo, "get_index_for_date", existing)
    result = SimpleNamespace(index_date=date(2026, 11, 9), value=11,
                             band=SimpleNamespace(value="LOW"),
                             model_version="geri_v1.2", trend_1d=1, trend_7d=2)
    selected = Mock(return_value=result)
    monkeypatch.setattr(service, "compute_geri_for_date", selected)
    monkeypatch.setattr(job_health, "record_existing_skip",
                        Mock(side_effect=AssertionError("Must return selected v1.2")))
    response = routes.run_geri_compute(x_runner_token="offline", force=False, mode="yesterday")
    assert response["value"] == 11
    assert response["model_version"] == "geri_v1.2"
    selected.assert_called_once()
