"""Old decision loop versus bulk mode, on disposable PostgreSQL, with no sends."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import time
from pathlib import Path

from psycopg2.extras import RealDictCursor
import pytest

from tests.disposable_postgres import disposable_pg, sql_cursor


@pytest.fixture
def fanout_db(disposable_pg, monkeypatch):
    from src.db import db
    from src.alerts import quota_helpers, alerts_engine_v2 as engine
    from src.plans import plan_helpers
    monkeypatch.setenv("DATABASE_URL", __import__("psycopg2").extensions.make_dsn(**disposable_pg))
    monkeypatch.setenv("PRODUCTION_DATABASE_URL", __import__("psycopg2").extensions.make_dsn(**disposable_pg))
    monkeypatch.setattr(engine, "ALERTS_SEND_ALLOWLIST_USER_IDS", "")
    quota_helpers._quota_cache.clear()
    quota_helpers._quota_cache_time.clear()
    with sql_cursor(disposable_pg) as c:
        c.execute("""
            DROP TABLE IF EXISTS user_alert_deliveries,user_alert_prefs,user_plans,
                users,plan_settings,alert_events,user_alert_digests CASCADE;
            CREATE TABLE users(id INT PRIMARY KEY,email TEXT,telegram_chat_id TEXT,
                phone_number TEXT,email_verified BOOLEAN);
            CREATE TABLE user_plans(user_id INT PRIMARY KEY,plan TEXT);
            CREATE TABLE plan_settings(plan_code TEXT,display_name TEXT,monthly_price_usd NUMERIC,
                allowed_alert_types TEXT[],max_regions INT,max_email_alerts_per_day INT,
                delivery_config JSONB,is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT now(),updated_at TIMESTAMP DEFAULT now());
            CREATE TABLE user_alert_prefs(user_id INT,region TEXT,alert_type TEXT,asset TEXT,
                threshold NUMERIC,enabled BOOLEAN,cooldown_minutes INT);
            CREATE TABLE alert_events(id INT PRIMARY KEY,alert_type TEXT,scope_region TEXT,
                scope_assets TEXT[],severity INT,headline TEXT,body TEXT,driver_event_ids INT[],
                cooldown_key TEXT,created_at TIMESTAMPTZ DEFAULT now(),fanout_completed_at TIMESTAMPTZ);
            CREATE TABLE user_alert_deliveries(id BIGSERIAL PRIMARY KEY,user_id INT,alert_event_id INT,
                channel TEXT,status TEXT,reason TEXT,delivery_kind TEXT,
                created_at TIMESTAMPTZ DEFAULT now(),sent_at TIMESTAMPTZ,
                attempts INT DEFAULT 0,next_retry_at TIMESTAMPTZ,last_error TEXT,provider_message_id TEXT,
                UNIQUE(alert_event_id,user_id,channel,delivery_kind));
            CREATE TABLE user_alert_digests(id BIGSERIAL PRIMARY KEY,user_id INT,channel TEXT,
                status TEXT,created_at TIMESTAMPTZ DEFAULT now(),sent_at TIMESTAMPTZ);
        """)
        for plan in ("free", "personal", "trader", "pro", "enterprise"):
            limit = 0 if plan == "free" else 1 if plan == "personal" else 1000
            config = {"email": {"max_per_day": limit,
                                "realtime_limit": limit},
                      "telegram": {"enabled": True, "send_all": True},
                      "sms": {"enabled": False}}
            c.execute("""INSERT INTO plan_settings(plan_code,display_name,monthly_price_usd,
                allowed_alert_types,max_regions,max_email_alerts_per_day,delivery_config)
                VALUES(%s,%s,10,ARRAY['ALL'],5,%s,%s)""",
                (plan, plan, limit, json.dumps(config)))
        for uid in range(1, 119):
            c.execute("INSERT INTO users VALUES(%s,%s,%s,%s,TRUE)",
                      (uid, None if uid % 5 == 0 else "offline@example.invalid",
                       None if uid % 3 == 0 else "offline-chat",
                       "offline-phone" if uid % 7 == 0 else None))
            c.execute("INSERT INTO user_plans VALUES(%s,%s)",
                      (uid, "free" if uid % 6 == 0 else
                       ("personal", "trader", "pro", "enterprise")[(uid-1) % 4]))
            if uid % 4 == 0:
                c.execute("INSERT INTO user_alert_prefs VALUES(%s,'Asia','ASSET_RISK_SPIKE','gas',50,TRUE,60)", (uid,))
            elif uid % 4 == 1:
                for typ in ("HIGH_IMPACT_EVENT", "ASSET_RISK_SPIKE"):
                    c.execute("INSERT INTO user_alert_prefs VALUES(%s,'Europe',%s,'gas',50,TRUE,60)", (uid, typ))
        c.execute("""INSERT INTO alert_events(id,alert_type,scope_region,scope_assets,severity,headline,body)
            VALUES(1,'HIGH_IMPACT_EVENT','Europe',ARRAY['oil'],80,'offline','offline'),
                  (2,'ASSET_RISK_SPIKE','Europe',ARRAY['gas'],80,'offline','offline')""")
        c.execute("""INSERT INTO user_alert_deliveries(user_id,alert_event_id,channel,status,delivery_kind)
            VALUES(1,1,'email','queued','instant'),(3,1,'telegram','queued','instant')""")
    return disposable_pg


def decisions(settings):
    with sql_cursor(settings, commit=False) as c:
        c.execute("""SELECT user_id,alert_event_id,channel,status,reason,delivery_kind
            FROM user_alert_deliveries ORDER BY user_id,alert_event_id,channel,delivery_kind""")
        return c.fetchall()


def reset(settings):
    with sql_cursor(settings) as c:
        c.execute("TRUNCATE user_alert_deliveries RESTART IDENTITY")
        c.execute("UPDATE alert_events SET fanout_completed_at=NULL")
        c.execute("""INSERT INTO user_alert_deliveries(user_id,alert_event_id,channel,status,delivery_kind)
            VALUES(1,1,'email','queued','instant'),(3,1,'telegram','queued','instant')""")


def baseline_fanout():
    from src.alerts import alerts_engine_v2 as engine
    # Execute the literal a313 function, not a reimplementation of its rules.
    namespace = vars(engine).copy()
    source = Path(__file__).with_name("fixtures") / "fanout_a313fb38.py"
    exec(compile(source.read_text(), str(source), "exec"), namespace)
    return namespace["fanout_alert_events_to_users"]()


def test_old_vs_new_decisions_counters_queries_and_timing(fanout_db, monkeypatch, record_property):
    from src.alerts import alerts_engine_v2 as engine
    from src.db import db
    from src.plans import plan_helpers
    counts = {"queries": 0, "connections": 0}
    original_cursor, original_connection = db.get_cursor, db.get_connection
    class Meter:
        def __init__(self, cursor):
            self.cursor = cursor
        def execute(self, *args, **kwargs):
            counts["queries"] += 1
            return self.cursor.execute(*args, **kwargs)
        def __getattr__(self, name):
            return getattr(self.cursor, name)
    @contextmanager
    def cursor(**kw):
        with original_cursor(**kw) as c:
            yield Meter(c)
    @contextmanager
    def connection():
        counts["connections"] += 1
        with original_connection() as conn:
            yield conn
    monkeypatch.setattr(db, "get_connection", connection)
    for module in (db, engine, plan_helpers):
        monkeypatch.setattr(module, "get_cursor", cursor)
    started = time.perf_counter()
    old = baseline_fanout()
    old_seconds = time.perf_counter() - started
    expected = decisions(fanout_db)
    old_counts = counts.copy()
    reset(fanout_db)
    started = time.perf_counter()
    new = engine.fanout_alert_events_to_users()
    new_seconds = time.perf_counter() - started
    assert decisions(fanout_db) == expected
    assert {key: new[key] for key in old} == old
    assert new["connection_count"] == 1
    assert new["query_count"] < old_counts["queries"]
    assert not new["fanout_budget_exhausted"]
    evidence = {"user_checks": new["users_considered"], "deliveries": len(expected),
                "old_queries": old_counts["queries"], "new_queries": new["query_count"],
                "old_connections": old_counts["connections"], "new_connections": 1,
                "old_local_seconds": old_seconds, "new_local_seconds": new_seconds,
                "rows_and_skip_counters_identical": True}
    print("FANOUT_COMPARISON " + json.dumps(evidence, sort_keys=True))
    record_property("fanout_comparison", json.dumps(evidence, sort_keys=True))


def test_budget_leaves_partial_event_for_next_run_without_duplicates(fanout_db, monkeypatch):
    from src.alerts import alerts_engine_v2 as engine
    from src.alerts.fanout_snapshot import FanoutSnapshot
    checks = []
    def expired(self):
        checks.append(1)
        return len(checks) > 20
    monkeypatch.setattr(FanoutSnapshot, "expired", expired)
    first = engine.fanout_alert_events_to_users()
    assert first["fanout_budget_exhausted"]
    assert first["events_remaining"] == 2 and first["user_checks_remaining"] == 216
    with sql_cursor(fanout_db, commit=False) as c:
        c.execute("SELECT count(*) n FROM alert_events WHERE fanout_completed_at IS NOT NULL")
        assert c.fetchone()["n"] == 0
    monkeypatch.setattr(FanoutSnapshot, "expired", lambda self: False)
    second = engine.fanout_alert_events_to_users()
    assert not second["fanout_budget_exhausted"]
    actual = decisions(fanout_db)
    assert len({(r["user_id"], r["alert_event_id"], r["channel"], r["delivery_kind"])
                for r in actual}) == len(actual)
    reset(fanout_db)
    baseline_fanout()
    assert decisions(fanout_db) == actual


def test_atomic_last_slot_two_connections(fanout_db):
    from src.alerts.fanout_snapshot import FanoutSnapshot
    with sql_cursor(fanout_db) as c:
        c.execute("DELETE FROM user_alert_deliveries WHERE user_id=1 AND channel='email'")
        c.execute("""UPDATE plan_settings SET max_email_alerts_per_day=1,
            delivery_config='{"email":{"max_per_day":1,"realtime_limit":1},"telegram":{"enabled":true,"send_all":true}}'
            WHERE plan_code='personal'""")
    # Both snapshots see zero before either reserves the last quota slot.
    from threading import Barrier
    barrier = Barrier(2)
    def reserve(event):
        with FanoutSnapshot() as state:
            barrier.wait(timeout=10)
            return state.insert(1, event, "email", "queued", None, "instant")
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(reserve, [1, 2]))
    assert sum(r is not None for r in results) == 1


def test_digest_aggregate_claims_not_item_rows_enforce_limit(fanout_db):
    from src.alerts.send_policy import current_send_permission
    with sql_cursor(fanout_db) as c:
        c.execute("""INSERT INTO user_alert_digests(user_id,channel,status)
            VALUES(1,'telegram','sending'),(1,'telegram','sending') RETURNING id""")
        first, second = [r["id"] for r in c.fetchall()]
    assert current_send_permission(1, "telegram", [1], kind="digest", claim_id=first)[1] is None
    assert current_send_permission(1, "telegram", [1], kind="digest", claim_id=second)[1] == "quota_exceeded"


def test_queued_before_midnight_sends_still_consume_todays_quota(fanout_db):
    from src.alerts.send_policy import current_send_permission
    with sql_cursor(fanout_db) as c:
        c.execute("""UPDATE user_alert_deliveries SET status='sent',
            created_at=now()-interval '1 day',sent_at=now() WHERE user_id=1 AND channel='email'""")
        c.execute("""INSERT INTO user_alert_deliveries(user_id,alert_event_id,channel,status,
            delivery_kind,created_at) VALUES(1,2,'email','sending','instant',now()-interval '1 day')
            RETURNING id""")
        claim = c.fetchone()["id"]
    assert current_send_permission(1, "email", [2], claim_id=claim)[1] == "quota_exceeded"


@pytest.mark.parametrize("change,reason", [
    ("UPDATE user_alert_prefs SET enabled=FALSE WHERE user_id=1", "channel_disabled_by_user"),
    ("UPDATE plan_settings SET allowed_alert_types=ARRAY['DAILY_DIGEST'] WHERE plan_code='personal'", "channel_not_allowed"),
    ("UPDATE plan_settings SET delivery_config=jsonb_set(delivery_config,'{telegram,enabled}','false') WHERE plan_code='personal'", "channel_disabled_by_user"),
    ("UPDATE users SET email_verified=FALSE WHERE id=1", "user_not_eligible"),
])
def test_current_policy_rechecks_revocation_after_fanout(fanout_db, change, reason):
    from src.alerts import alerts_engine_v2 as engine
    from src.alerts.send_policy import current_send_permission
    engine.fanout_alert_events_to_users()
    assert current_send_permission(1, "telegram", [1])[1] is None
    with sql_cursor(fanout_db) as c:
        c.execute(change)
    assert current_send_permission(1, "telegram", [1])[1] == reason


def test_sender_is_not_called_after_revocation(fanout_db, monkeypatch):
    from src.alerts import alerts_engine_v2 as engine, channel_adapters
    engine.fanout_alert_events_to_users()
    with sql_cursor(fanout_db) as c:
        c.execute("UPDATE user_alert_prefs SET enabled=FALSE WHERE user_id=1")
    from unittest.mock import Mock
    send = Mock(side_effect=AssertionError("Must not send revoked content"))
    monkeypatch.setattr(channel_adapters, "send_telegram_v2", send)
    monkeypatch.setattr(channel_adapters, "send_email_v2", send)
    monkeypatch.setattr(engine, "ALERTS_SEND_ALLOWLIST_USER_IDS", "1")
    result = engine.send_queued_deliveries(batch_size=200, max_per_run=200)
    # Other users may be eligible: restrict the test's send selection to revoked user.
    assert result["skipped_current_policy"] >= 1
    send.assert_not_called()


def test_budget_returns_to_phase_c_and_finishes_audit(fanout_db, monkeypatch):
    from src.alerts import runner, alerts_engine_v2 as engine
    from src.alerts.fanout_snapshot import FanoutSnapshot
    from unittest.mock import Mock
    tracker = Mock()
    tracker.start.return_value = "offline-run"
    monkeypatch.setattr("src.alerts.engine_observability.EngineRunTracker", lambda **kw: tracker)
    monkeypatch.setattr(FanoutSnapshot, "expired", lambda self: True)
    order = []
    for phase in ("a", "d", "c"):
        monkeypatch.setattr(runner, "run_phase_" + phase,
            lambda now, _phase=phase, **kw: order.append(_phase) or {"status": "success", "counts": {}})
    monkeypatch.setattr(runner, "run_phase_b",
        lambda now, **kw: {"status": "success", "counts": engine.fanout_alert_events_to_users()})
    result = runner.execute_phases("all")
    assert order == ["a", "d", "c"]
    assert result["overall_status"] == "success"
    tracker.finish.assert_called_once()
    assert tracker.finish.call_args.args[1]["phase_b"]["fanout_budget_exhausted"]
