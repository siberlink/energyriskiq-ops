"""Offline policy regression tests. No network, provider or application DB."""
from datetime import date, timedelta
import sqlite3

import pytest

from src.geri.health import evaluate_day
from src.geri.enrichment_evidence import spend_sql
from src.risk.pipeline_v2 import warning_reasons


@pytest.mark.parametrize("alerts,events,feed,expected", [
    (0, 100, None, "OK"), (5, 100, None, "OK"),
    (5, 39, None, "DEGRADED"), (0, 39, None, "UNAVAILABLE"),
    (5, 100, {"feeds_ok": 4, "feeds_configured": 10}, "DEGRADED"),
    (0, 100, {"feeds_ok": 5, "feeds_configured": 10}, "OK"),
    (5, 40, None, "OK"),
])
def test_prospective_source_coverage(alerts, events, feed, expected):
    day = date(2026, 11, 1)
    a = {day-timedelta(days=i): 100 for i in (7, 14, 21, 28)}
    e = dict(a)
    a[day], e[day] = alerts, events
    assert evaluate_day(day, a, e, min(a), feed)["data_quality"] == expected


def test_october_policy_not_reinterpreted():
    day = date(2026, 10, 31)
    a = {day-timedelta(days=i): 100 for i in (7, 14, 21, 28)}
    e = dict(a)
    a[day], e[day] = 5, 100
    assert evaluate_day(day, a, e, min(a))["data_quality"] == "DEGRADED"


@pytest.mark.parametrize("change,recovered", [
    (None, True), ("other_run", False), ("unprocessed", False),
    ("missing_success", False), ("other_purpose", False),
    ("unfinished_run", False), ("failed_after_run", False),
])
def test_retry_evidence_query(change, recovered):
    # Execute the real FILTER/EXISTS query against an in-memory relational fixture.
    # Only PostgreSQL timezone/interval syntax is adapted; predicates are unchanged.
    db = sqlite3.connect(":memory:")
    db.executescript("""
        CREATE TABLE risk_pipeline_v2_usage (
            budget_date TEXT, charged_usd REAL, reserved_usd REAL, status TEXT,
            purpose TEXT, item_id INTEGER, requested_at TEXT, finished_at TEXT);
        CREATE TABLE events (id INTEGER, processed BOOLEAN, ai_processed_at TEXT);
        CREATE TABLE job_runs (job_name TEXT, started_at TEXT, finished_at TEXT, status TEXT);
        INSERT INTO events VALUES(1,1,'2026-11-01 09:18:59');
        INSERT INTO job_runs VALUES('shadow_enrichment_delivery',
            '2026-11-01 09:15:00','2026-11-01 09:20:00','error');
        INSERT INTO risk_pipeline_v2_usage VALUES('2026-11-01',.01,0,'error',
            'enrichment',1,'2026-11-01 09:18:44','2026-11-01 09:18:45');
        INSERT INTO risk_pipeline_v2_usage VALUES('2026-11-01',.02,0,'completed',
            'enrichment',1,'2026-11-01 09:18:50','2026-11-01 09:18:58');
    """)
    if change == "other_run":
        db.execute("UPDATE job_runs SET finished_at='2026-11-01 09:18:46'")
    elif change == "unprocessed":
        db.execute("UPDATE events SET processed=0")
    elif change == "missing_success":
        db.execute("DELETE FROM risk_pipeline_v2_usage WHERE status='completed'")
    elif change == "other_purpose":
        db.execute("UPDATE risk_pipeline_v2_usage SET purpose='relevance41'")
    elif change == "unfinished_run":
        db.execute("UPDATE job_runs SET finished_at=NULL")
    elif change == "failed_after_run":
        db.execute("UPDATE risk_pipeline_v2_usage SET finished_at='2026-11-01 09:21:00' WHERE status='error'")
    sql = spend_sql().replace("(e.ai_processed_at AT TIME ZONE 'UTC')", "e.ai_processed_at")
    sql = sql.replace("NOW()-interval '1 hour'", "'2026-11-01 12:00:00'").replace("%s", "?")
    row = db.execute(sql, ("2026-11-01", "2026-11-01")).fetchone()
    assert row[2] == (0 if recovered else 1)
    assert row[3] == (1 if recovered else 0)
    assert row[1] >= .01  # Attempts remain charged, not removed from evidence.
    db.close()


def test_queue_warning_ignores_legacy_backlog_and_matches_g1_boundary():
    value = {"waiting_all": 100000, "fresh_waiting": 0, "fresh_queue_limit": 700}
    assert warning_reasons(value) == []
    value["fresh_waiting"] = 700
    assert warning_reasons(value) == ["queue exceeds 24 hours of average inflow"]
