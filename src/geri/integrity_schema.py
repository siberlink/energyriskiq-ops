"""Additive, idempotent GERI integrity migration; no updates to index values."""
UP_SQL = """
CREATE TABLE IF NOT EXISTS geri_daily_health (
 index_date DATE PRIMARY KEY, alerts_count INTEGER NOT NULL, alerts_ratio DOUBLE PRECISION,
 events_count INTEGER, events_ratio DOUBLE PRECISION, feeds_ok INTEGER, feeds_configured INTEGER,
 data_quality TEXT NOT NULL CHECK(data_quality IN ('OK','DEGRADED','UNAVAILABLE')),
 computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), details JSONB NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS geri_revisions (
 id BIGSERIAL PRIMARY KEY, index_date DATE NOT NULL, old_value INTEGER, new_value INTEGER,
 old_payload JSONB, new_payload JSONB, reason TEXT NOT NULL CHECK(length(trim(reason))>0),
 model_version TEXT NOT NULL, code_sha TEXT NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), applied BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE TABLE IF NOT EXISTS geri_compute_snapshots (
 id BIGSERIAL PRIMARY KEY, index_date DATE NOT NULL, alert_ids JSONB NOT NULL,
 baseline_start DATE, baseline_end DATE, baseline_rows INTEGER NOT NULL,
 baseline_dates JSONB NOT NULL, fallback_used BOOLEAN NOT NULL, code_sha TEXT NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS job_runs (
 id BIGSERIAL PRIMARY KEY, job_name TEXT NOT NULL, index_date DATE,
 started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), finished_at TIMESTAMPTZ,
 status TEXT NOT NULL, error TEXT, run_key TEXT UNIQUE
);
CREATE INDEX IF NOT EXISTS geri_job_runs_recent ON job_runs(job_name,started_at DESC);
"""

# Deliberately never run on startup: a manual rollback discards only the NEW
# integrity metadata. It cannot restore any later, explicitly applied revision.
DOWN_SQL = """
DROP TABLE IF EXISTS geri_compute_snapshots;
DROP TABLE IF EXISTS geri_revisions;
DROP TABLE IF EXISTS geri_daily_health;
DROP INDEX IF EXISTS geri_job_runs_recent;
DROP TABLE IF EXISTS job_runs;
"""


def migrate():
    from src.db.db import get_cursor
    with get_cursor() as cursor:
        cursor.execute(UP_SQL)
