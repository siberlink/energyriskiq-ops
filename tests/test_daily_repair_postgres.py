"""Daily GERI stage against disposable PostgreSQL. Only AI transport is mocked."""
from datetime import datetime, timedelta, timezone
import json

import httpx
import pytest


@pytest.fixture(autouse=True)
def website_pair_offline(monkeypatch):
    monkeypatch.setattr("src.reri.website_trigger.run_website_pair",
                        lambda **kw: {"status": "success"})
from psycopg2.extras import RealDictCursor

from tests.test_storage_writer_postgres import postgres


@pytest.fixture
def geri_database(postgres, monkeypatch):
    from src.geri import integrity_schema, version12, health_finalization, types
    from src.geri import service
    monkeypatch.setenv("DATABASE_URL", postgres.dsn)
    monkeypatch.setenv("PRODUCTION_DATABASE_URL", postgres.dsn)
    monkeypatch.setenv("GERI_PUBLISHED_MODEL", "v1.2")
    monkeypatch.setenv("GERI_LIVE_MODEL", "v1.2")
    monkeypatch.setenv("INTERNAL_RUNNER_TOKEN", "offline-only")
    monkeypatch.setenv("CLOUD_RUN_JOB", "energyriskiq-daily")
    monkeypatch.setenv("CLOUD_RUN_EXECUTION", "offline-daily-test")
    monkeypatch.setattr(service, "ENABLE_GERI", True)
    with postgres.cursor() as c:
        c.execute("""
            ALTER TABLE job_runs ADD COLUMN IF NOT EXISTS id BIGSERIAL;
            ALTER TABLE job_runs ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ DEFAULT now();
            ALTER TABLE job_runs ADD COLUMN IF NOT EXISTS error TEXT;
            CREATE TABLE IF NOT EXISTS intel_indices_daily(
                id SERIAL PRIMARY KEY,index_id TEXT,date DATE,value INTEGER,band TEXT,
                trend_1d INTEGER,trend_7d INTEGER,components JSONB,model_version TEXT,
                computed_at TIMESTAMP DEFAULT now(),interpretation TEXT,
                UNIQUE(index_id,date));
            CREATE TABLE IF NOT EXISTS alert_events(
                id BIGSERIAL PRIMARY KEY,alert_type TEXT,severity INTEGER,confidence NUMERIC,
                scope_region TEXT,created_at TIMESTAMP,headline TEXT,body TEXT,raw_input JSONB);
            CREATE TABLE IF NOT EXISTS events(inserted_at TIMESTAMP);
            CREATE TABLE IF NOT EXISTS geri_shadow_daily(
                index_date DATE,variant TEXT,value INTEGER);
        """)
        c.execute(integrity_schema.UP_SQL)
        c.execute(version12.UP_SQL)
        c.execute(health_finalization.UP_SQL)
        c.execute("TRUNCATE intel_indices_daily,intel_indices_daily_v12,geri_daily_health,"
                  "geri_v12_revisions,geri_v12_ops,geri_live_v12_shadow,"
                  "geri_shadow_daily,alert_events,events,job_runs")
    postgres.commit()
    day = datetime.now(timezone.utc).date() - timedelta(days=1)
    rows, history = [], []
    for offset in range(90, 0, -1):
        d = day - timedelta(days=offset)
        row = version12.calculate_day(d, [], "OK", rows, history, raw_override=[10., 0., 0., 5.])
        with postgres.cursor() as c:
            c.execute("""INSERT INTO geri_daily_health
                (index_date,alerts_count,data_quality,provisional,computed_at)
                VALUES(%s,1,'OK',false,now()-interval '1 hour')""", (d,))
            c.execute("""INSERT INTO intel_indices_daily
                (index_id,date,value,band,components,model_version)
                VALUES(%s,%s,10,'LOW',%s::jsonb,'geri_v1.1')""",
                (types.INDEX_ID, d, json.dumps(row["components"])))
        postgres.commit()
        version12.store(row)
        rows.append(row)
        history.append({"index_date": d, "components": row["smoothing_state"]["normalized_raw"],
                        "inputs": {"data_quality": "OK",
                                   "original_raw": row["smoothing_state"]["original_raw"]}})
    with postgres.cursor() as c:
        c.execute("""INSERT INTO alert_events
            (alert_type,severity,confidence,scope_region,created_at,headline,body,raw_input)
            VALUES('HIGH_IMPACT_EVENT',5,0.9,'Europe',%s,'Offline supply event',
                   'Category: energy','{"category":"energy"}')""",
            (datetime.combine(day, datetime.min.time()) + timedelta(hours=12),))
        c.execute("INSERT INTO events VALUES(%s)", (datetime.combine(day, datetime.min.time()),))
    postgres.commit()
    return postgres, day


@pytest.mark.parametrize("has_key", [True, False])
def test_real_daily_geri_stage_persists_selected_model_before_delivery(geri_database, monkeypatch, has_key):
    conn, day = geri_database
    from src.api.internal_routes import run_geri_compute
    from src.geri import interpretation
    calls = []
    monkeypatch.delenv("AI_INTEGRATIONS_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AI_INTEGRATIONS_OPENAI_BASE_URL", raising=False)
    if has_key:
        monkeypatch.setenv("OPENAI_API_KEY", "offline")
    else:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_BASE_URL", "https://offline.invalid/v1")

    def transport(self, request):
        body = json.loads(request.content)
        calls.append(body)
        prose = ("Observed energy risk remains limited. Regional and asset components are inactive. " * 30)
        return httpx.Response(200, request=request, json={
            "id": "offline", "object": "chat.completion", "created": 1,
            "model": "offline", "choices": [{"index": 0,
                "message": {"role": "assistant", "content": prose + "\n\n" + prose},
                "finish_reason": "stop"}]})

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", transport)
    result = run_geri_compute(mode="yesterday", force=False, x_runner_token="offline-only")
    assert result["status"] == "ok"
    assert result["details"]["model_version"] == "geri_v1.2"
    with conn.cursor(cursor_factory=RealDictCursor) as c:
        c.execute("SELECT * FROM intel_indices_daily_v12 WHERE date=%s", (day,))
        private = dict(c.fetchone())
        c.execute("SELECT * FROM geri_daily_health WHERE index_date=%s", (day,))
        health = dict(c.fetchone())
        c.execute("SELECT row_to_json(t) AS row FROM intel_indices_daily t WHERE date=%s", (day,))
        legacy_before = c.fetchone()["row"]
        c.execute("SELECT status FROM job_runs WHERE job_name='geri_daily' ORDER BY id DESC LIMIT 1")
        assert c.fetchone()["status"] == "stored_v12"
        c.execute("SELECT details FROM geri_v12_ops WHERE index_date=%s AND kind='publication_writer'", (day,))
        writer = c.fetchone()["details"]
        assert writer["job"] == "energyriskiq-daily"
        assert writer["execution"] == "offline-daily-test" and writer["value"] == private["value"]
    assert private["value"] == result["details"]["value"]
    assert private["computed_at"].replace(tzinfo=timezone.utc) >= health["computed_at"]
    assert not health["provisional"] and private["interpretation"]
    assert private["components"]["ai_section_missing"] is (not has_key)
    assert result["details"]["ai_section_missing"] is (not has_key)
    if has_key:
        assert any("inactive_component_note" in m["content"] for call in calls for m in call["messages"])
    else:
        assert not calls
        from src.api.internal_routes import _validate_daily_stage
        assert _validate_daily_stage("geri", result) == result
    run_geri_compute(mode="yesterday", force=False, x_runner_token="offline-only")
    with conn.cursor(cursor_factory=RealDictCursor) as c:
        c.execute("SELECT row_to_json(t) AS row FROM intel_indices_daily t WHERE date=%s", (day,))
        assert c.fetchone()["row"] == legacy_before
        c.execute("SELECT count(*) AS n FROM intel_indices_daily_v12 WHERE date=%s", (day,))
        assert c.fetchone()["n"] == 1


def test_delivery_audit_persists_missing_ai_and_exact_geri_value(geri_database):
    conn, day = geri_database
    from src.delivery.pro_delivery_worker import record_index_delivery
    with conn.cursor() as c:
        c.execute("""CREATE TABLE user_alert_deliveries(
            user_id INTEGER,channel TEXT,status TEXT,delivery_kind TEXT,
            created_at TIMESTAMP,sent_at TIMESTAMP,geri_date DATE,last_error TEXT);
            CREATE UNIQUE INDEX ON user_alert_deliveries(user_id,channel,geri_date)
            WHERE delivery_kind='index_digest' AND geri_date IS NOT NULL;""")
    conn.commit()
    record_index_delivery(1, "telegram", "sent", index_date=day,
                          ai_section_missing=True, geri_value=11, methodology="v1.2")
    with conn.cursor() as c:
        c.execute("SELECT status,last_error FROM user_alert_deliveries")
        status, raw = c.fetchone()
    audit = json.loads(raw)
    assert status == "sent" and audit["ai_section_missing"] is True
    assert audit["geri_value"] == 11 and audit["geri_methodology"] == "v1.2"


def test_failed_ai_persists_geri_warms_fallback_delivers_and_exits_nonzero(
    geri_database, monkeypatch, capsys
):
    """Real GERI/cache/audit writes to disposable PG; failed AI; mocked send."""
    import sys
    from types import SimpleNamespace
    from scripts import replit_scheduled_job as runner
    from src.api import internal_routes as routes, daily_digest_routes as digest
    from src.delivery import pro_delivery_worker as delivery
    conn, day = geri_database
    # New exact-day boundary and append-only ledger are exercised on this
    # disposable database too; no mock bypasses the real snapshot SQL.
    from pathlib import Path
    with conn.cursor() as c:
        c.execute((Path(__file__).parents[1] /
                   "migrations/20261113_index_digest_attempts.sql").read_text())
        c.execute("""
            CREATE TABLE IF NOT EXISTS reri_indices_daily(
              date DATE PRIMARY KEY,index_id TEXT,value NUMERIC,band TEXT,
              trend_1d INT,trend_7d INT,components JSONB,drivers JSONB,
              interpretation TEXT,model_version TEXT);
            CREATE TABLE IF NOT EXISTS egsi_m_daily(
              index_date DATE PRIMARY KEY,index_value NUMERIC,band TEXT,
              trend_1d INT,trend_7d INT,components_json JSONB,interpretation TEXT);
            TRUNCATE reri_indices_daily,egsi_m_daily;
        """)
        c.execute("""INSERT INTO reri_indices_daily VALUES
            (%s,'europe:eeri',60,'ELEVATED',1,1,'{}','{}','text','eeri_ttf_v3')""", (day,))
        c.execute("""INSERT INTO egsi_m_daily VALUES
            (%s,22.4,'LOW',1,1,'{}','text')""", (day,))
    conn.commit()
    monkeypatch.setenv("OPENAI_API_KEY", "offline")
    monkeypatch.delenv("AI_INTEGRATIONS_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AI_INTEGRATIONS_OPENAI_BASE_URL", raising=False)
    monkeypatch.setenv("INCLUDE_DELIVERY", "true")
    monkeypatch.setattr(runner, "_configuration", lambda: "offline-only")
    monkeypatch.setattr(sys, "argv", ["replit_scheduled_job.py", "--job", "daily"])
    monkeypatch.setattr(routes.time, "sleep", lambda _: None)
    attempts = []
    def failed_transport(self, request):
        attempts.append(request.url.host)
        raise httpx.ConnectError("offline transport failure", request=request)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", failed_transport)
    for name in ("run_market_data_capture", "run_oil_price_capture",
                 "run_gas_storage_capture", "run_lng_price_capture"):
        monkeypatch.setattr(routes, name, lambda **kw: {"status": "success"})
    monkeypatch.setattr(routes, "run_egsi_s_compute", lambda **kw: {
        "status": "success", "value": 30, "ai_section_missing": True})
    with conn.cursor() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS daily_digest_ai_cache(
            cache_key TEXT PRIMARY KEY,narrative TEXT,created_at TIMESTAMP);
            CREATE TABLE IF NOT EXISTS user_alert_deliveries(
            user_id INTEGER,channel TEXT,status TEXT,delivery_kind TEXT,
            created_at TIMESTAMP,sent_at TIMESTAMP,geri_date DATE,last_error TEXT);
            CREATE UNIQUE INDEX IF NOT EXISTS fallback_test_delivery
            ON user_alert_deliveries(user_id,channel,geri_date)
            WHERE delivery_kind='index_digest' AND geri_date IS NOT NULL;
            TRUNCATE daily_digest_ai_cache,user_alert_deliveries;""")
    conn.commit()
    def persisted_geri(**kw):
        with conn.cursor(cursor_factory=RealDictCursor) as c:
            c.execute("SELECT * FROM intel_indices_daily_v12 WHERE date=%s", (day,))
            return dict(c.fetchone())
    monkeypatch.setattr(digest, "PLAN_LEVELS", {"personal": 1})
    def report(*args):
        text, missing = digest.resolve_daily_narrative(
            "offline-report", lambda: None, persisted_geri(), {}, {}, str(day))
        return {"ai_narrative": text, "ai_section_missing": missing}
    monkeypatch.setattr(digest, "compute_daily_digest", report)
    monkeypatch.setattr(delivery, "ensure_index_digest_unique_index", lambda: None)
    monkeypatch.setattr(delivery, "get_all_users_with_plans", lambda: [
        {"id": 1, "email": None, "telegram_chat_id": "offline", "plan": "personal"}])
    monkeypatch.setattr(delivery, "get_user_delivery_preferences",
                        lambda _: {1: {"daily_digest": {"telegram": True}}})
    monkeypatch.setattr(delivery, "get_latest_geri", persisted_geri)
    for name in ("get_latest_eeri", "get_latest_egsi", "get_asset_snapshots"):
        monkeypatch.setattr(delivery, name, lambda: {})
    monkeypatch.setattr(delivery, "generate_ai_digest_for_plan", lambda *a: None)
    monkeypatch.setattr(delivery, "has_been_delivered_today", lambda *a: False)
    rendered = []
    monkeypatch.setattr(delivery, "send_telegram_v2",
                        lambda chat, text: rendered.append(text) or SimpleNamespace(success=True))
    assert runner.main() == 1
    output = capsys.readouterr()
    assert attempts and "stage errors" in output.err
    payload = json.loads(output.out.splitlines()[-1])["response"]["details"]
    assert payload["pipeline_status"] == "degraded"
    assert {"geri", "egsi_s", "daily_report", "delivery"} <= set(payload["failed_stages"])
    for stage in ("geri", "egsi_s", "daily_report", "delivery"):
        assert payload[stage]["ai_section_missing"] is True
    row = persisted_geri()
    assert row["interpretation"] and row["components"]["ai_section_missing"]
    assert payload["daily_report"]["details"]["levels_warmed"] == [1]
    assert payload["delivery"]["details"]["telegrams_sent"] == 1
    assert rendered and f"Stored observations for {day}" in rendered[0]
    with conn.cursor(cursor_factory=RealDictCursor) as c:
        c.execute("SELECT cache_key,narrative FROM daily_digest_ai_cache")
        cached = dict(c.fetchone())
        c.execute("SELECT status,last_error FROM user_alert_deliveries")
        audit = dict(c.fetchone())
    assert cached["cache_key"].endswith(":deterministic-fallback:geri_v1.2")
    assert "deterministic briefing" in cached["narrative"]
    assert audit["status"] == "sent"
    assert json.loads(audit["last_error"])["ai_section_missing"] is True
