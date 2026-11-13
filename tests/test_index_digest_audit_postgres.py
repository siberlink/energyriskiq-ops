"""Real SQL checks on disposable Unix-socket PostgreSQL; no app DB or network."""
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from uuid import uuid4

import psycopg2
import pytest

from tests.disposable_postgres import disposable_pg, sql_cursor
from src.delivery import guarded_index_digest as guard


@pytest.fixture
def database(disposable_pg, monkeypatch):
    @contextmanager
    def cursor(commit=True):
        with sql_cursor(disposable_pg, commit=commit) as cur:
            yield cur
    monkeypatch.setattr(guard, "get_cursor", cursor)
    with cursor() as cur:
        cur.execute((Path(__file__).parents[1] /
                     "migrations/20261113_index_digest_attempts.sql").read_text())
        cur.execute("""
            CREATE TABLE IF NOT EXISTS intel_indices_daily_v12(
              date DATE PRIMARY KEY,index_id TEXT,value NUMERIC,band TEXT,
              trend_1d INT,trend_7d INT,components JSONB,interpretation TEXT,
              model_version TEXT,smoothing_state JSONB);
            CREATE TABLE IF NOT EXISTS reri_indices_daily(
              date DATE PRIMARY KEY,index_id TEXT,value NUMERIC,band TEXT,
              trend_1d INT,trend_7d INT,components JSONB,drivers JSONB,
              interpretation TEXT,model_version TEXT);
            CREATE TABLE IF NOT EXISTS egsi_m_daily(
              index_date DATE PRIMARY KEY,index_value NUMERIC,band TEXT,
              trend_1d INT,trend_7d INT,components_json JSONB,interpretation TEXT);
            TRUNCATE intel_indices_daily_v12,reri_indices_daily,egsi_m_daily;
            INSERT INTO intel_indices_daily_v12 VALUES
              ('2026-11-12','global:geo_energy_risk',7,'LOW',1,1,'{}','text','v1.2',
               '{"data_quality":"OK"}');
            INSERT INTO reri_indices_daily VALUES
              ('2026-11-12','europe:eeri',60,'ELEVATED',1,1,'{}','{}','text','eeri_ttf_v3');
            INSERT INTO egsi_m_daily VALUES
              ('2026-11-12',22.40,'LOW',1,1,'{}','text');
        """)
    return cursor


def test_actual_exact_day_snapshot(database):
    result = guard.read_snapshot(date(2026, 11, 12), "v1.2")
    assert result["geri"]["value"] == 7
    assert result["eeri"]["model_version"] == "eeri_ttf_v3"
    assert float(result["egsi"]["value"]) == 22.4
    assert all(row is None for row in guard.read_snapshot(
        date(2026, 11, 13), "v1.2").values())
    with database() as cur:
        cur.execute("UPDATE reri_indices_daily SET model_version='old'")
    assert guard.read_snapshot(date(2026, 11, 12), "v1.2")["eeri"] is None


@pytest.mark.parametrize("sql", [
    "UPDATE index_digest_attempts SET outcome='failed'",
    "DELETE FROM index_digest_attempts",
    "TRUNCATE index_digest_attempts",
])
def test_attempts_are_append_only(database, sql):
    guard.append_attempt(uuid4(), 700, "telegram", "skipped",
                         {"target_date": "2026-11-12"})
    with pytest.raises(psycopg2.Error, match="append-only"):
        with database() as cur:
            cur.execute(sql)


def test_reservation_held_unless_transport_definitively_did_not_send(database):
    uid = 900
    aid = uuid4()
    metadata = {"target_date": "2026-11-12", "send": True}
    assert not guard.send_reserved(uid, "telegram", date(2026, 11, 12))
    guard.append_attempt(aid, uid, "telegram", "started", metadata)
    assert guard.send_reserved(uid, "telegram", date(2026, 11, 12))
    guard.append_attempt(aid, uid, "telegram", "failed",
                         {**metadata, "delivered": False})
    assert not guard.send_reserved(uid, "telegram", date(2026, 11, 12))
    guard.append_attempt(uuid4(), uid, "telegram", "started", metadata)
    assert guard.send_reserved(uid, "telegram", date(2026, 11, 12))


def test_recipient_lock_is_cross_connection_and_released(database):
    day = date(2026, 11, 12)
    with guard.recipient_lock(1000, "telegram", day) as first:
        with guard.recipient_lock(1000, "telegram", day) as second:
            assert first is True and second is False
    with guard.recipient_lock(1000, "telegram", day) as third:
        assert third is True
