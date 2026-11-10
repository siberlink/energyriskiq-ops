"""Real SQL tests on a disposable Unix-socket PostgreSQL, never the app DB."""
import json
import os
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor
import pytest

from src.ingest import gas_storage_revisions as rev
from src.scripts.backfill_snapshots import compute_gas_metrics


@pytest.fixture(scope="module")
def postgres():
    if not shutil.which("initdb"):
        pytest.skip("Disposable PostgreSQL binaries unavailable")
    with tempfile.TemporaryDirectory(prefix="storage-sql-") as directory:
        data = str(Path(directory) / "pg")
        port = 20000 + os.getpid() % 30000
        subprocess.run(["initdb", "-D", data, "-A", "trust", "-U", "storage_test",
                        "--no-locale", "--encoding=UTF8"], check=True, capture_output=True)
        subprocess.run(["pg_ctl", "-D", data, "-l", directory + "/server.log",
                        "-o", f"-k {directory} -p {port} -c listen_addresses=''",
                        "-w", "start"], check=True, capture_output=True)
        try:
            conn = psycopg2.connect(dbname="postgres", user="storage_test", host=directory, port=port)
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE gas_storage_snapshots(
                        id BIGSERIAL,date DATE PRIMARY KEY,eu_storage_percent NUMERIC,
                        seasonal_norm NUMERIC,deviation_from_norm NUMERIC,refill_speed_7d NUMERIC,
                        withdrawal_rate_7d NUMERIC,winter_deviation_risk TEXT,days_to_target INTEGER,
                        risk_score INTEGER,risk_band TEXT,interpretation TEXT,raw_data JSONB);
                    CREATE TABLE gas_storage_country_snapshots(
                        date DATE,level TEXT,country_code TEXT,country_name TEXT,operator_code TEXT,
                        facility_code TEXT,storage_percent NUMERIC,gas_in_storage_twh NUMERIC,
                        working_gas_volume_twh NUMERIC,injection_twh NUMERIC,withdrawal_twh NUMERIC,
                        trend NUMERIC,raw_data JSONB,
                        UNIQUE(date,level,country_code,operator_code,facility_code));
                    CREATE TABLE gas_storage_widget_daily_cache(id INTEGER);
                    CREATE TABLE job_runs(job_name TEXT,index_date DATE,
                        finished_at TIMESTAMPTZ,status TEXT,run_key TEXT UNIQUE);
                """)
                cur.execute(rev.SCHEMA)
            conn.commit()
            yield conn
            conn.close()
        finally:
            subprocess.run(["pg_ctl", "-D", data, "-m", "immediate", "-w", "stop"],
                           check=True, capture_output=True)


@pytest.fixture
def database(postgres, monkeypatch):
    postgres.rollback()
    with postgres.cursor() as cur:
        cur.execute("TRUNCATE gas_storage_snapshots,gas_storage_country_snapshots,"
                    "gas_storage_revision_log,job_runs,gas_storage_widget_daily_cache")
    postgres.commit()
    @contextmanager
    def cursor(**kwargs):
        try:
            with postgres.cursor(cursor_factory=RealDictCursor) as cur:
                yield cur
            postgres.commit()
        except BaseException:
            postgres.rollback()
            raise
    monkeypatch.setattr(rev, "get_cursor", cursor)
    monkeypatch.setattr(rev, "run_storage_revision_migration", lambda: None)
    monkeypatch.setenv("CLOUD_RUN_JOB", "energyriskiq-daily")
    return postgres


def observation(day="2026-11-08", **overrides):
    return {"date": day, "gasDayStart": day, "status": "E", "full_percent": 72.38,
            "updatedAt": "2026-11-10T12:00:00Z", "gas_in_storage_twh": 819.5,
            "working_gas_volume_twh": 1132, "injection_twh": 1, "withdrawal_twh": 2,
            "trend": -.3, **overrides}


def test_real_sql_new_and_revised_eu_preserves_key_scores_and_unknown_json(database):
    initial = observation()
    rev.write_eu_scoring_snapshot(database, compute_gas_metrics(initial, 11))
    database.commit()
    with database.cursor() as cur:
        cur.execute("UPDATE gas_storage_snapshots SET raw_data=raw_data || '{\"independent_key\":7}'")
    database.commit()
    updated = observation(full_percent=72.39, status="C", updatedAt="2026-11-10T13:00:00Z")
    rev.write_eu_scoring_snapshot(database, compute_gas_metrics(updated, 11))
    database.commit()
    with database.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT date,eu_storage_percent,risk_score,raw_data FROM gas_storage_snapshots")
        row = cur.fetchone()
    assert row["date"] == date(2026, 11, 9)
    assert float(row["eu_storage_percent"]) == 72.39
    assert row["raw_data"]["independent_key"] == 7 and row["raw_data"]["status"] == "C"
    assert row["risk_score"] == compute_gas_metrics(initial, 11)["risk_score"]


@pytest.mark.parametrize("area", ["EU", "DE"])
def test_database_guard_independently_rejects_stale_even_with_obsolete_python_row(database, area):
    data = observation()
    if area == "EU":
        rev.write_eu_scoring_snapshot(database, compute_gas_metrics(data, 11))
    else:
        with database.cursor(cursor_factory=RealDictCursor) as cur:
            rev._write_observation(cur, area, data, None)
    database.commit()
    # Deliberately stale Python state: only the SQL guard knows stored updatedAt.
    with database.cursor(cursor_factory=RealDictCursor) as cur:
        assert rev._write_observation(cur, area,
            observation(full_percent=1.11, updatedAt="2026-11-10T11:00:00Z"),
            {"date": date(2026, 11, 9), "raw_data": {}} if area == "EU" else None) is False
    database.commit()
    table, column = ("gas_storage_snapshots", "eu_storage_percent") if area == "EU" else (
        "gas_storage_country_snapshots", "storage_percent")
    with database.cursor() as cur:
        cur.execute(f"SELECT {column},raw_data->>'updatedAt' FROM {table}")
        value, stamp = cur.fetchone()
    assert float(value) == 72.38 and stamp == "2026-11-10T12:00:00Z"


def test_seven_days_77_flags_and_audited_noop_refetch(database):
    observations = []
    for offset in range(7):
        day = str(date(2026, 11, 2) + timedelta(days=offset))
        data = observation(day)
        rev.write_eu_scoring_snapshot(database, compute_gas_metrics(data, 11))
        for area in ["EU"] + gie_countries():
            observations.append({"area": area, "data": data})
    database.commit()
    plan = {"start": "2026-11-02", "end": "2026-11-08", "errors": [], "observations": observations}
    rev.apply_revision_plan(plan)
    second = rev.apply_revision_plan(plan)
    assert second["revision_count"] == 0
    with database.cursor() as cur:
        cur.execute("""SELECT count(*) FROM (
            SELECT raw_data FROM gas_storage_snapshots UNION ALL
            SELECT raw_data FROM gas_storage_country_snapshots) rows
            WHERE raw_data->>'status' IN ('E','C')""")
        assert cur.fetchone()[0] == 77
        cur.execute("SELECT count(*) FROM gas_storage_revision_log WHERE area='REFRESH'")
        assert cur.fetchone()[0] == 2
        cur.execute("SELECT run_key FROM job_runs ORDER BY finished_at DESC LIMIT 1")
        assert json.loads(cur.fetchone()[0])["triggered_by"] == "energyriskiq-daily"


def gie_countries():
    from src.ingest.gie_agsi import MAJOR_EU_COUNTRIES
    return list(MAJOR_EU_COUNTRIES)


def test_existing_country_json_merge_not_replacement(database):
    with database.cursor(cursor_factory=RealDictCursor) as cur:
        rev._write_observation(cur, "DE", observation(), None)
        cur.execute("UPDATE gas_storage_country_snapshots SET raw_data=raw_data || '{\"unrelated\":42}'")
        # Simulates a writer that read before another transaction added that key.
        rev._write_observation(cur, "DE",
            observation(full_percent=58.95, updatedAt="2026-11-10T13:00:00Z"), None)
        cur.execute("SELECT storage_percent,raw_data FROM gas_storage_country_snapshots")
        row = cur.fetchone()
    database.commit()
    assert float(row["storage_percent"]) == 58.95 and row["raw_data"]["unrelated"] == 42
