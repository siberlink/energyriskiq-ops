"""Actual NUMERIC storage/audit SQL and scheduled CLI; no external transports."""
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import subprocess
import sys

import psycopg2
from psycopg2.extras import RealDictCursor
import pytest

from tests.test_storage_writer_postgres import postgres, database, observation


def configure(monkeypatch, conn, job):
    """Replace external boundaries, not the storage, audit or CLI implementation."""
    from src.db import db
    from src.alerts import alerts_engine_v2 as engine, engine_observability as obs, runner
    from src.ingest import gas_storage_revisions as rev
    from src.api import internal_routes as routes
    from src.scripts.backfill_snapshots import compute_gas_metrics

    @contextmanager
    def cursor(commit=True, **kwargs):
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                yield cur
            if commit:
                conn.commit()
        except BaseException:
            conn.rollback()
            raise

    @contextmanager
    def connection():
        yield conn

    for module in (db, engine, obs, rev):
        monkeypatch.setattr(module, "get_cursor", cursor)
    monkeypatch.setattr(db, "get_connection", connection)
    monkeypatch.setattr(db, "get_database_url", lambda: conn.dsn)
    monkeypatch.setattr(rev, "run_storage_revision_migration", lambda: None)
    monkeypatch.setattr(rev, "runtime_identity", lambda: {
        "git_sha": "offline-numeric-test", "image": "offline-image",
        "triggered_by": f"energyriskiq-{job}", "execution": "offline-execution",
    })
    monkeypatch.setenv("CLOUD_RUN_JOB", f"energyriskiq-{job}")
    monkeypatch.setenv("INTERNAL_RUNNER_TOKEN", "offline-test")
    monkeypatch.setenv("ALERTS_V2_ENABLED", "true")
    monkeypatch.setenv("ALERTS_ENABLED", "true")
    monkeypatch.setenv("PHASE", "all")
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("SKIP_PREFLIGHT", "true")
    monkeypatch.setenv("INCLUDE_PRO_DELIVERY", "true")
    monkeypatch.setenv("INCLUDE_TRADER_DELIVERY", "true")
    monkeypatch.setenv("INCLUDE_DELIVERY", "true")
    monkeypatch.setenv("GERI_PUBLISHED_MODEL", "v1.1")
    monkeypatch.setenv("GERI_LIVE_MODEL", "legacy")

    with cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS alerts_engine_runs(
                run_id TEXT PRIMARY KEY,triggered_by TEXT,phase TEXT,
                started_at TIMESTAMPTZ,finished_at TIMESTAMPTZ,status TEXT,
                git_sha TEXT,duration_ms BIGINT,counts JSONB,error_summary TEXT);
            CREATE TABLE IF NOT EXISTS alerts_engine_run_items(
                id BIGSERIAL,run_id TEXT,phase TEXT,started_at TIMESTAMPTZ,
                finished_at TIMESTAMPTZ,duration_ms BIGINT,status TEXT,
                counts JSONB,error_summary TEXT);
            CREATE TABLE IF NOT EXISTS alert_events(
                id BIGSERIAL PRIMARY KEY,alert_type TEXT,scope_region TEXT,
                scope_assets TEXT[],severity INTEGER,headline TEXT,body TEXT,
                driver_event_ids INTEGER[],cooldown_key TEXT,
                event_fingerprint TEXT UNIQUE,raw_input JSONB,classification JSONB,
                category TEXT,confidence NUMERIC);
            TRUNCATE alerts_engine_runs,alerts_engine_run_items,alert_events;
        """)
    with cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM gas_storage_snapshots")
        empty = cur.fetchone()["n"] == 0
    if empty:
        metrics = compute_gas_metrics(observation(), 11)
        metrics.update(risk_score=80, risk_band="CRITICAL", winter_deviation_risk="CRITICAL")
        rev.write_eu_scoring_snapshot(conn, metrics)
        conn.commit()
    with cursor() as cur:
        cur.execute("TRUNCATE gas_storage_revision_log")

    # Other Phase A generators are isolated; storage's read/format/upsert are real.
    for name in ("generate_regional_risk_spike_events", "generate_asset_risk_spike_events",
                 "generate_high_impact_event_alerts"):
        monkeypatch.setattr(engine, name, lambda: {"created": [], "skipped": 0})
    monkeypatch.setattr(engine, "get_risk_summary", lambda *args: {
        "risk_7d": 0, "risk_30d": 0, "assets": {}})
    monkeypatch.setattr(engine, "update_alert_state", lambda *args: None)
    for phase in ("b", "c", "d"):
        monkeypatch.setattr(runner, f"run_phase_{phase}", lambda *args, **kwargs: {
            "status": "success", "counts": {"sent": 0}})

    observations = []
    for offset in range(7):
        day = str(date(2026, 11, 2) + timedelta(days=offset))
        for area in ["EU"] + list(rev.MAJOR_EU_COUNTRIES):
            data = observation(day)
            if area != "EU":
                data["country"] = area
            observations.append({"area": area, "data": data})
    monkeypatch.setattr(rev, "prepare_revision_plan", lambda **kwargs: {
        "start": "2026-11-02", "end": "2026-11-08",
        "errors": [], "observations": observations})

    def isolated_stage(**kwargs):
        return {"status": "ok", "details": {
            "status": "success", "value": Decimal("21.00"),
            "observation_date": date(2026, 11, 9)}}

    for name in ("run_market_data_capture", "run_oil_price_capture", "run_geri_compute",
                 "run_eeri_compute", "run_lng_price_capture", "run_egsi_compute",
                 "run_egsi_s_compute", "run_daily_report",
                 "run_pro_delivery", "run_trader_delivery"):
        monkeypatch.setattr(routes, name, isolated_stage)
    monkeypatch.setattr(routes.time, "sleep", lambda seconds: None)
    return engine, obs, rev, routes, runner


@pytest.fixture
def configured(database, monkeypatch):
    modules = configure(monkeypatch, database, "alerts")
    return database, modules


def test_real_phase_a_numeric_storage_and_duplicate_event(configured):
    conn, (engine, obs, rev, routes, runner) = configured
    with conn.cursor() as cur:
        cur.execute("SELECT eu_storage_percent FROM gas_storage_snapshots")
        assert isinstance(cur.fetchone()[0], Decimal)
        cur.execute("SELECT row_to_json(s) FROM gas_storage_snapshots s")
        before = cur.fetchall()
    for _ in range(2):
        result = runner.run_phase_a(datetime.now(timezone.utc))
        assert result["status"] == "success"
        assert isinstance(result["counts"]["storage_metrics"]["storage_percent"], float)
        assert result["counts"]["storage_metrics"]["date"] == "2026-11-08"
        json.dumps(result)  # No custom serializer needed after the read boundary.
    with conn.cursor() as cur:
        cur.execute("SELECT row_to_json(s) FROM gas_storage_snapshots s")
        assert cur.fetchall() == before
        cur.execute("SELECT count(*) FROM alert_events")
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT count(*) FROM gas_storage_revision_log")
        assert cur.fetchone()[0] == 0


def test_audit_real_sql_nested_numeric_date_and_datetime(configured):
    conn, (_, obs, rev, _, _) = configured
    tracker = obs.EngineRunTracker("all")
    tracker.start()
    counts = {"storage": Decimal("72.38"), "day": date(2026, 11, 8),
              "at": datetime(2026, 11, 10, tzinfo=timezone.utc)}
    phase = tracker.record_phase_start("a")
    tracker.record_phase_end(phase, "success", counts)
    tracker.finish("success", {"phase_a": counts})
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT status,finished_at,counts FROM alerts_engine_runs WHERE run_id=%s",
                    (tracker.run_id,))
        row = cur.fetchone()
        assert row["status"] == "success" and row["finished_at"]
        assert row["counts"]["phase_a"]["storage"] == 72.38
        assert row["counts"]["phase_a"]["day"] == "2026-11-08"
        assert row["counts"]["storage_runtime"]["image"] == "offline-image"
        cur.execute("SELECT counts FROM alerts_engine_run_items WHERE run_id=%s",
                    (tracker.run_id,))
        assert cur.fetchone()["counts"]["at"] == "2026-11-10T00:00:00+00:00"


def test_failed_audit_and_bad_metadata_warn_without_raising(configured, monkeypatch, caplog):
    _, (_, obs, rev, _, _) = configured
    tracker = obs.EngineRunTracker("all")
    tracker.start()

    @contextmanager
    def unavailable(**kwargs):
        raise RuntimeError("isolated audit DB failure")
        yield

    monkeypatch.setattr(obs, "get_cursor", unavailable)
    tracker.record_phase_end(tracker.record_phase_start("a"), "success", {"value": Decimal("1")})
    tracker.finish("success", {"value": object()})
    monkeypatch.setattr(rev, "runtime_identity", lambda: (_ for _ in ()).throw(
        ValueError("isolated metadata failure")))
    tracker.finish("success", {})
    assert "Failed to record phase item" in caplog.text
    assert "Failed to update run record" in caplog.text


def test_daily_capture_and_real_job_audit(configured, monkeypatch):
    conn, (_, _, rev, _, _) = configured
    monkeypatch.setenv("CLOUD_RUN_JOB", "energyriskiq-daily")
    result = rev.capture_storage("2026-11-08")
    assert result["status"] == "success"
    with conn.cursor() as cur:
        cur.execute("""SELECT count(*) FROM (
            SELECT raw_data FROM gas_storage_snapshots UNION ALL
            SELECT raw_data FROM gas_storage_country_snapshots) s
            WHERE raw_data->>'status' IN ('E','C')""")
        assert cur.fetchone()[0] == 77
        cur.execute("SELECT status,finished_at,run_key FROM job_runs")
        status, finished, key = cur.fetchone()
        assert status == "success" and finished
        assert json.loads(key)["image"] == "offline-image"


@pytest.mark.parametrize(("job", "audit_failure"), [
    ("alerts", False), ("daily", False), ("alerts", True)])
def test_full_scheduled_script_exit_zero_with_real_numeric(configured, tmp_path, job, audit_failure):
    conn, _ = configured
    root = Path(__file__).resolve().parents[1]
    # The actual CLI is a fresh Python process. sitecustomize installs the same
    # offline guards BEFORE imports and substitutes only external boundaries.
    (tmp_path / "sitecustomize.py").write_text(
        "import os, runpy\n"
        f"runpy.run_path({str(root / 'conftest.py')!r})\n"
        "import psycopg2, pytest\n"
        "from tests.test_storage_decimal_entrypoints import configure\n"
        f"connection=psycopg2.connect({conn.dsn!r})\n"
        f"patches=pytest.MonkeyPatch(); configure(patches, connection, {job!r})\n"
        + ("from src.alerts import engine_observability as obs\n"
           "def fail_audit(*args, **kwargs): raise RuntimeError('isolated audit unavailable')\n"
           "patches.setattr(obs, 'get_cursor', fail_audit)\n" if audit_failure else ""))
    env = {**os.environ, "PYTHONPATH": str(tmp_path) + os.pathsep + str(root)}
    completed = subprocess.run(
        [sys.executable, str(root / "scripts/replit_scheduled_job.py"), "--job", job],
        env=env, cwd=root, text=True, capture_output=True, timeout=90)
    assert completed.returncode == 0, completed.stderr + completed.stdout
    assert '"status": 200' in completed.stdout
    assert "Error in sitecustomize" not in completed.stderr
    if job == "alerts":
        assert '"job": "pro_delivery"' in completed.stdout
        assert '"job": "trader_delivery"' in completed.stdout
    if audit_failure:
        assert "Failed to create run record" in completed.stderr
        return
    conn.rollback()  # Observe the child's committed transactions.
    with conn.cursor() as cur:
        if job == "alerts":
            cur.execute("SELECT status,finished_at FROM alerts_engine_runs")
            assert all(status == "success" and finished for status, finished in cur.fetchall())
            cur.execute("SELECT count(*) FROM alerts_engine_run_items WHERE phase='a'")
            assert cur.fetchone()[0] == 1
        else:
            cur.execute("SELECT status,finished_at FROM job_runs WHERE job_name='gas_storage_refresh'")
            assert all(status == "success" and finished for status, finished in cur.fetchall())
