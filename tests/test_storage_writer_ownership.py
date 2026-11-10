"""Offline storage-only regression tests; no provider, DB or customer transport."""
import inspect
import json
from contextlib import contextmanager
from datetime import date
from unittest.mock import Mock

import pytest

from src.ingest import gas_storage_revisions as rev, gie_agsi as gie
from src.scripts import backfill_snapshots as backfill


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    import requests
    import psycopg2
    monkeypatch.setenv("RISK_PIPELINE_V2_MODE", "off")
    monkeypatch.setattr(requests.sessions.Session, "request",
                        Mock(side_effect=AssertionError("Network forbidden")))
    monkeypatch.setattr(psycopg2, "connect", Mock(side_effect=AssertionError("Real DB forbidden")))


def observation(**overrides):
    return {"date": "2026-11-08", "gasDayStart": "2026-11-08", "status": "E",
            "updatedAt": "2026-11-10T12:00:00Z", "full_percent": 72.38,
            "gas_in_storage_twh": 819.5, "working_gas_volume_twh": 1132,
            "injection_twh": 1, "withdrawal_twh": 2, "trend": -.3, **overrides}


class Cursor:
    rowcount = 1
    def __init__(self):
        self.queries = []
    def execute(self, query, args=None):
        self.queries.append((query, args))
    def fetchone(self):
        return {"id": 123}
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass


@pytest.mark.parametrize("area", ["EU", "DE"])
def test_sql_merge_and_timestamp_guard(area):
    cur = Cursor()
    old = {"date": date(2026, 11, 9), "raw_data": {"custom_provenance": 1,
            "updatedAt": "2026-11-10T11:00:00Z"}}
    assert rev._write_observation(cur, area, observation(), old)
    sql = cur.queries[-1][0]
    assert "||" in sql and "timestamptz" in sql
    assert "risk_score" not in sql and "risk_band" not in sql


@pytest.mark.parametrize("area", ["EU", "DE"])
@pytest.mark.parametrize("timestamp", ["2026-11-10T10:00:00Z", None])
def test_old_or_unknown_revision_cannot_replace_timestamped(area, timestamp, caplog):
    cur = Cursor()
    row = {"raw_data": {"updatedAt": "2026-11-10T11:00:00Z"}}
    assert rev._write_observation(cur, area, observation(updatedAt=timestamp), row) is False
    assert not cur.queries
    assert "AGSI_STALE_REJECT" in caplog.text


def test_sql_rejected_write_is_not_reported_as_success(caplog):
    cur = Cursor()
    cur.rowcount = 0
    assert rev._write_observation(cur, "DE", observation(), None) is False
    assert "concurrent" in caplog.text


@pytest.mark.parametrize("patch", [{"gasDayStart": None}, {"date": "2026-11-09"}, {"status": None}])
def test_canonical_writer_rejects_unproven_observations(patch):
    cur = Cursor()
    with pytest.raises(ValueError):
        rev._write_observation(cur, "DE", observation(**patch), None)
    assert not cur.queries


def test_provider_precision_never_rounded_for_persistence():
    data = observation()
    assert backfill.compute_gas_metrics(data, 11)["eu_storage_percent"] == 72.38
    assert gie.compute_storage_metrics(data, []) .eu_storage_percent == 72.38
    assert not hasattr(gie, "_legacy_ingest_country_storage")


def test_alerts_reads_stored_metrics_without_provider_or_storage_writes(monkeypatch):
    from src.alerts import alerts_engine_v2 as alerts
    metrics = backfill.compute_gas_metrics(observation(), 11)
    row = {**metrics, "date": date(2026, 11, 9)}
    read = Mock(return_value=row)
    monkeypatch.setattr(alerts, "execute_one", read)
    monkeypatch.setattr(gie, "_make_api_request", Mock(side_effect=AssertionError("Provider forbidden")))
    monkeypatch.setattr(alerts, "get_cursor", Mock(side_effect=AssertionError("Storage write forbidden")))
    generate = Mock(return_value=None)
    monkeypatch.setattr(gie, "generate_storage_alert", generate)
    result = alerts.generate_storage_risk_events()
    assert result["metrics"]["date"] == "2026-11-08"
    assert generate.call_args.args[0].eu_storage_percent == 72.38
    assert read.call_args.args[0].lstrip().startswith("SELECT")


def test_alerts_still_creates_deduplicated_risk_event(monkeypatch):
    from src.alerts import alerts_engine_v2 as alerts
    monkeypatch.setattr(alerts, "execute_one",
                        Mock(return_value={**backfill.compute_gas_metrics(observation(), 11),
                                           "date": date(2026, 11, 9)}))
    monkeypatch.setattr(gie, "generate_storage_alert", Mock(return_value={"headline": "Storage risk"}))
    event = Mock(return_value=(123, False))
    monkeypatch.setattr(alerts, "create_alert_event", event)
    assert alerts.generate_storage_risk_events()["created"] == [123]
    assert event.call_args.kwargs["event_fingerprint"] == "STORAGE_RISK:2026-11-08"


def test_noop_refresh_has_persisted_run_audit(monkeypatch):
    cur = Cursor()
    @contextmanager
    def db(**kwargs):
        yield cur
    monkeypatch.setattr(rev, "get_cursor", db)
    monkeypatch.setattr(rev, "run_storage_revision_migration", lambda: None)
    monkeypatch.setattr(rev, "_existing", lambda *a, **k: {
        "date": "2026-11-09", "eu_storage_percent": 72.38, "raw_data": observation()})
    monkeypatch.setenv("CLOUD_RUN_JOB", "energyriskiq-daily")
    result = rev.apply_revision_plan({"start": "2026-11-02", "end": "2026-11-08",
                                     "errors": [], "observations": [{"area": "EU", "data": observation()}]})
    assert result["revision_count"] == 0
    audit = next(args for sql, args in cur.queries if "INSERT INTO job_runs" in sql)
    identity = json.loads(audit[-1])
    assert identity["triggered_by"] == "energyriskiq-daily"
    assert identity["observations"] == 1


def test_new_eu_day_scored_once_with_provider_day(monkeypatch):
    cur = Cursor()
    conn = Mock()
    conn.cursor.return_value = cur
    monkeypatch.setattr(rev, "_existing", lambda *a, **k: None)
    result = rev.write_eu_scoring_snapshot(conn, backfill.compute_gas_metrics(observation(), 11))
    insert = next(args for sql, args in cur.queries if "INSERT INTO gas_storage_snapshots" in sql)
    assert insert[0] == "2026-11-09" and insert[1] == 72.38
    assert json.loads(insert[-1])["gasDayStart"] == "2026-11-08"
    assert result["old"] is None
    conn.commit.assert_not_called()


def test_existing_eu_row_retains_physical_date_and_risk_fields(monkeypatch):
    cur = Cursor()
    conn = Mock()
    conn.cursor.return_value = cur
    row = {"date": date(2026, 11, 9), "eu_storage_percent": 72.4,
           "raw_data": {**observation(), "full_percent": 72.4}}
    monkeypatch.setattr(rev, "_existing", lambda *a, **k: row)
    rev.write_eu_scoring_snapshot(conn, backfill.compute_gas_metrics(observation(), 11))
    update = next((sql, args) for sql, args in cur.queries if "UPDATE gas_storage_snapshots" in sql)
    assert update[1][2] == date(2026, 11, 9)
    assert "risk_score" not in update[0] and "SET date" not in update[0]


def test_capture_refresh_precedes_new_eu_insert(monkeypatch):
    import src.db.db as db
    calls = []
    data = observation()
    monkeypatch.setattr(rev, "prepare_revision_plan", lambda **k: {
        "observations": [{"area": "EU", "data": data}]})
    def refresh(plan):
        calls.append("refresh")
        return {"deferred_eu_days": ["2026-11-08"], "errors": [], "data_date": "2026-11-08"}
    monkeypatch.setattr(rev, "apply_revision_plan", refresh)
    @contextmanager
    def connection():
        yield Mock()
    monkeypatch.setattr(db, "get_connection", connection)
    monkeypatch.setattr(rev, "write_eu_scoring_snapshot",
                        lambda *a: calls.append("score") or True)
    assert rev.capture_storage("2026-11-09")["date"] == "2026-11-08"
    assert calls == ["refresh", "score"]


def test_country_manual_backfill_uses_canonical_writer(monkeypatch):
    from scripts import backfill_country_storage as country
    monkeypatch.setattr(country, "_make_api_request", lambda *a: {"data": [
        {"gasDayStart": "2026-11-08", "full": "58.95", "status": "E"}]})
    apply = Mock(return_value={"success": 1, "revision_count": 1})
    monkeypatch.setattr(rev, "apply_revision_plan", apply)
    assert country.backfill_country("DE", "2026-11-08", "2026-11-08") == 1
    assert apply.call_args.args[0]["observations"][0]["data"]["full_percent"] == 58.95
    assert "INSERT INTO gas_storage" not in inspect.getsource(country)


def test_cloud_job_identity_without_env_changes(monkeypatch):
    from src.alerts import engine_observability as audit
    monkeypatch.setenv("CLOUD_RUN_JOB", "energyriskiq-alerts")
    monkeypatch.setenv("GITHUB_SHA", "test-sha")
    assert audit.get_triggered_by() == "energyriskiq-alerts"
    assert audit.get_git_sha() == "test-sha"
