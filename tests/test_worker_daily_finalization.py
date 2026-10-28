"""Worker regression tests. All database/provider/network access is forbidden."""
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    import psycopg2
    import socket
    def refuse(*args, **kwargs):
        raise AssertionError("No database/network access in worker unit tests")
    monkeypatch.setattr(psycopg2, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setenv("GERI_PUBLISHED_MODEL", "v1.1")
    monkeypatch.setenv("GERI_LIVE_MODEL", "legacy")
    monkeypatch.delenv("RISK_PIPELINE_V2_MODE", raising=False)


def test_skip_finalizes_health_then_private_before_success():
    from src.geri import job_health, version12, health
    day = date(2026, 10, 26)
    order = []
    with patch.object(job_health, "start_run", return_value=7), \
         patch.object(health, "record_health", side_effect=lambda d: order.append(("health", d))), \
         patch.object(version12, "compute_day", side_effect=lambda d: order.append(("private", d))), \
         patch.object(job_health, "finish_run", side_effect=lambda *a: order.append(("finish", a))):
        job_health.record_existing_skip(day)
    assert order == [("health", day), ("private", day), ("finish", (7, "skipped"))]


def test_private_failure_marks_run_error_and_propagates():
    from src.geri import job_health, version12, health
    with patch.object(job_health, "start_run", return_value=7), \
         patch.object(health, "record_health"), \
         patch.object(version12, "compute_day", side_effect=RuntimeError("private failed")), \
         patch.object(job_health, "finish_run") as finish:
        with pytest.raises(RuntimeError, match="private failed"):
            job_health.record_existing_skip(date(2026, 10, 26))
    finish.assert_called_once_with(7, "error", "private failed")


def test_existing_private_row_is_not_recalculated_or_revised():
    from src.geri import version12
    row = {"date": date(2026, 10, 26), "value": 22,
           "computed_at": datetime(2026, 10, 27, 1, 31)}
    cursor = MagicMock()
    cursor.fetchone.side_effect = [
        {"data_quality": "OK", "provisional": False,
         "computed_at": datetime(2026, 10, 27, 1, 30)}, row]
    @contextmanager
    def context(*a, **kw):
        yield cursor
    with patch.object(version12, "get_cursor", context), \
         patch.object(version12, "parity_monitor"), \
         patch.object(version12, "calculate_day") as calculate, \
         patch.object(version12, "store") as store:
        assert version12.compute_day(row["date"]) == row
    calculate.assert_not_called()
    store.assert_not_called()


def test_endpoint_existing_publication_calls_helper_not_public_writer():
    from src.api import internal_routes as routes
    from src.geri import repo, service, job_health
    with patch.object(routes, "validate_runner_token"), \
         patch.object(routes, "run_job_with_lock",
                      side_effect=lambda n, fn: (fn(), 200)), \
         patch.object(repo, "get_index_for_date", return_value=object()), \
         patch.object(service, "compute_geri_for_date") as public, \
         patch.object(job_health, "record_existing_skip") as final:
        result = routes.run_geri_compute(x_runner_token="offline-test")
    final.assert_called_once_with(datetime.utcnow().date() - timedelta(days=1))
    public.assert_not_called()
    assert result["reason"] == "already_exists"
    assert result["health_and_private_computation"] == "completed"


def test_endpoint_does_not_report_success_when_private_fails():
    from src.api import internal_routes as routes
    from src.geri import repo, service, job_health
    with patch.object(routes, "validate_runner_token"), \
         patch.object(routes, "run_job_with_lock",
                      side_effect=lambda n, fn: (fn(), 200)), \
         patch.object(repo, "get_index_for_date", return_value=object()), \
         patch.object(service, "compute_geri_for_date") as public, \
         patch.object(job_health, "record_existing_skip", side_effect=RuntimeError("private failed")):
        with pytest.raises(RuntimeError, match="private failed"):
            routes.run_geri_compute(x_runner_token="offline-test")
    public.assert_not_called()


def test_health_upsert_cannot_overwrite_an_immutable_final():
    from src.geri import health
    cursor = MagicMock()
    @contextmanager
    def context(*a, **kw):
        yield cursor
    row = {"index_date": date(2026, 10, 26), "details": {}}
    with patch("src.db.db.get_cursor", context):
        health.store_health([row])
    sql = "\n".join(call.args[0] for call in cursor.execute.call_args_list)
    assert "pg_advisory_xact_lock(12014,1)" in sql
    assert "WHERE geri_daily_health.provisional" in sql
    assert "intel_indices_daily" not in sql


def test_health_requires_closed_utc_day():
    from src.geri import health
    with pytest.raises(ValueError, match="closed UTC"):
        health.record_health(health.utc_today())


def test_new_private_day_resolves_all_helpers_without_publication_or_llm():
    from src.geri import version12, repo, interpretation
    from src.geri.model_selection import published_model, live_model
    cursor = MagicMock()
    cursor.fetchone.side_effect = [
        {"data_quality": "OK", "provisional": False,
         "computed_at": datetime(2026, 10, 27, 1, 30)}, None]
    @contextmanager
    def context(*a, **kw):
        yield cursor
    day = date(2026, 10, 26)
    previous = {
        "date": day - timedelta(days=1), "value": 27,
        "smoothing_state": {"data_quality": "OK", "transform_state": {
            "ewma": [250., 0., 0., 70.], "display_previous": 27.}},
    }
    with patch.object(version12, "get_cursor", context), \
         patch.object(version12, "history_for", return_value=([previous], [])), \
         patch.object(version12, "health_for", return_value={"data_quality": "OK"}), \
         patch.object(repo, "get_alerts_for_date", return_value=[]), \
         patch.object(version12, "store") as private_store, \
         patch("src.geri.live_v12.finalize_close"), \
         patch.object(version12, "parity_monitor"), \
         patch.object(interpretation, "generate_interpretation") as llm:
        result = version12.compute_day(day)
    assert result["date"] == day
    assert result["model_version"] == "geri_v1.2"
    assert result["smoothing_state"]["data_quality"] == "OK"
    assert 0 <= result["value"] <= 100
    assert private_store.call_count == 1
    llm.assert_not_called()
    assert published_model() == "v1.1"
    assert live_model() == "legacy"
