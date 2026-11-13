"""Offline regression tests shared unchanged with the standalone ops worker."""
from contextlib import contextmanager
from datetime import date
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.delivery import guarded_index_digest as guard


DAY = date(2026, 11, 12)


def snapshot():
    return {name: {"date": DAY, "value": value, "band": "LOW", "components": {},
                   "trend_1d": 1, "trend_7d": 2, "stale": False,
                   "interpretation": "Stored observation."}
            for name, value in (("geri", 7), ("eeri", 60), ("egsi", 22.4))}


@pytest.fixture
def harness(monkeypatch):
    from src.delivery import pro_delivery_worker as worker
    from src.alerts import channel_adapters
    monkeypatch.setenv("GERI_PUBLISHED_MODEL", "v1.2")
    monkeypatch.setattr(guard, "closed_day", lambda: DAY)
    rows, events, ledger = snapshot(), [], set()
    monkeypatch.setattr(guard, "read_snapshot", lambda *args: rows.copy())
    monkeypatch.setattr(guard, "wait_for_snapshot", lambda *args: rows.copy())
    monkeypatch.setattr(guard, "append_attempt",
                        lambda aid, uid, chan, outcome, meta:
                        events.append((str(aid), uid, chan, outcome, dict(meta))))
    monkeypatch.setattr(guard, "send_reserved", lambda uid, channel, target: any(
        e[1] == uid and e[2] == channel and e[3] == "started" and e[4].get("send")
        and not any(f[0] == e[0] and f[4].get("delivered") is False for f in events)
        for e in events))

    @contextmanager
    def lock(*args):
        yield True
    monkeypatch.setattr(guard, "recipient_lock", lock)
    monkeypatch.setattr(worker, "get_all_users_with_plans",
                        lambda: [{"id": 1, "email": "offline@example.invalid",
                                  "telegram_chat_id": "offline", "plan": "free"}])
    monkeypatch.setattr(worker, "get_asset_snapshots", lambda: {})
    monkeypatch.setattr(worker, "get_user_delivery_preferences",
                        lambda ids: {1: {"geri": {"telegram": True},
                                         "eeri": {"telegram": True},
                                         "egsi": {"telegram": True},
                                         "daily_digest": {"telegram": True}}})
    monkeypatch.setattr(worker, "has_been_delivered_today",
                        lambda uid, chan, day: (uid, chan, day) in ledger)
    monkeypatch.setattr(worker, "record_index_delivery",
                        Mock(side_effect=lambda uid, chan, status, **kw:
                             ledger.add((uid, chan, kw["index_date"]))))
    monkeypatch.setattr(worker, "generate_ai_digest_for_plan",
                        Mock(return_value="Exact-day briefing."))
    result = SimpleNamespace(success=True, should_skip=False)
    monkeypatch.setattr(worker, "send_telegram_v2", Mock(return_value=result))
    monkeypatch.setattr(worker, "send_email_v2", Mock(return_value=result))
    monkeypatch.setattr(channel_adapters, "ALERTS_EMAIL_ENABLED", False)
    return SimpleNamespace(worker=worker, rows=rows, events=events, ledger=ledger)


@pytest.mark.parametrize("methodology", ["v1.1", "v1.2"])
def test_snapshot_one_transaction_exact_day_and_methodology(monkeypatch, methodology):
    calls, values = [], iter(snapshot().values())
    class Cursor:
        def execute(self, sql, params=None):
            calls.append((sql, params))
        def fetchone(self):
            return next(values)
    @contextmanager
    def cursor(**kwargs):
        assert kwargs == {"commit": False}
        yield Cursor()
    monkeypatch.setattr(guard, "get_cursor", cursor)
    result = guard.read_snapshot(DAY, methodology)
    assert len(calls) == 4
    assert "REPEATABLE READ READ ONLY" in calls[0][0]
    assert ("public.intel_indices_daily_v12" in calls[1][0]) == (methodology == "v1.2")
    assert "model_version='eeri_ttf_v3'" in calls[2][0]
    assert all(params == (DAY,) and "ORDER BY" not in sql for sql, params in calls[1:])
    assert all(row["date"] == DAY and row["stale"] is False for row in result.values())


@pytest.mark.parametrize("bad", [{"date": date(2026, 11, 11)}, {"value": None},
                                {"stale": True}, {"components": {"stale": True}},
                                {"value": float("nan")}])
def test_invalid_or_stale_rows_become_pending(monkeypatch, bad):
    rows = list(snapshot().values())
    rows[0].update(bad)
    class Cursor:
        def execute(self, *args):
            pass
        def fetchone(self):
            return rows.pop(0)
    @contextmanager
    def cursor(**kwargs):
        yield Cursor()
    monkeypatch.setattr(guard, "get_cursor", cursor)
    assert guard.read_snapshot(DAY, "v1.2")["geri"] is None


def test_timing_race_reopens_snapshot_until_pair_ready():
    elapsed, calls = [0], []
    def reader(day, methodology):
        calls.append((day, methodology))
        rows = snapshot()
        if elapsed[0] < 10:
            rows["eeri"] = None
        if elapsed[0] < 20:
            rows["egsi"] = None
        return rows
    result = guard.wait_for_snapshot(
        DAY, "v1.2", reader=reader, clock=lambda: elapsed[0],
        sleep=lambda seconds: elapsed.__setitem__(0, elapsed[0] + seconds))
    assert elapsed == [20]
    assert len(calls) == 3 and all(row for row in result.values())
    assert all(call == (DAY, "v1.2") for call in calls)


def test_timeout_is_120_seconds_in_ten_second_steps():
    elapsed, sleeps, reads = [0], [], []
    def sleep(seconds):
        sleeps.append(seconds)
        elapsed[0] += seconds
    def reader(*args):
        reads.append(args)
        return {"geri": None, "eeri": None, "egsi": None}
    result = guard.wait_for_snapshot(
        DAY, "v1.2", reader=reader, clock=lambda: elapsed[0], sleep=sleep)
    assert sleeps == [10] * 12 and len(reads) == 13
    assert all(row is None for row in result.values())


def test_default_worker_call_only_renders_no_ai_or_sends(harness):
    result = harness.worker.run_index_delivery()
    assert result["renders"] and not result["errors"]
    harness.worker.generate_ai_digest_for_plan.assert_not_called()
    harness.worker.send_telegram_v2.assert_not_called()
    harness.worker.send_email_v2.assert_not_called()
    assert any(event[3] == "rendered" for event in harness.events)


def test_timeout_sends_pending_never_older_values_and_never_corrects(harness):
    harness.rows["eeri"], harness.rows["egsi"] = None, None
    result = harness.worker.run_index_delivery(send=True, caller="daily.delivery")
    assert result["freshness_pending"] is True
    assert result["telegrams_sent"] == 1
    text = harness.worker.send_telegram_v2.call_args.args[1]
    assert "EERI: pending" in text and "EGSI-M: pending" in text
    assert "2026-11-12" in text and "2026-11-11" not in text
    harness.worker.generate_ai_digest_for_plan.assert_not_called()
    assert any(e[3] == "pending" and e[4].get("delivered") for e in harness.events)
    harness.rows.update(snapshot())
    second = harness.worker.run_index_delivery(send=True)
    assert second["telegrams_sent"] == 0
    assert harness.worker.send_telegram_v2.call_count == 1


def test_complete_send_then_audited_skip_without_second_ai_call(harness):
    first = harness.worker.run_index_delivery(send=True)
    second = harness.worker.run_index_delivery(send=True)
    assert first["telegrams_sent"] == 1 and second["telegrams_skipped"] == 1
    assert harness.worker.generate_ai_digest_for_plan.call_count == 1
    assert any(e[3] == "skipped" and e[4].get("reason") == "already_sent"
               for e in harness.events)
    metadata = next(e[4] for e in harness.events if e[3] == "sent")
    assert all(key in metadata for key in
               ("caller", "job", "execution_id", "image", "target_date",
                "index_observations", "freshness_pending", "methodology"))


def test_daily_origin_not_confused_with_manual_handler(harness):
    with guard.delivery_origin("daily.delivery"):
        harness.worker.run_index_delivery(send=True, caller="pro-delivery")
    assert all(e[4]["caller"] == "daily.delivery" for e in harness.events)
    assert guard.provenance("manual")["caller"] == "manual"


def test_no_opt_in_means_no_delivery(harness, monkeypatch):
    monkeypatch.setattr(harness.worker, "get_user_delivery_preferences", lambda ids: {})
    harness.worker.run_index_delivery(send=True)
    harness.worker.send_telegram_v2.assert_not_called()
    assert any(e[4].get("reason") == "not_opted_in" for e in harness.events)


@pytest.mark.parametrize("plan,reason", [("free", "plan_not_entitled"),
                                       ("pro", "email_disabled")])
def test_email_entitlement_and_pause_kept(harness, monkeypatch, plan, reason):
    monkeypatch.setattr(harness.worker, "get_all_users_with_plans",
                        lambda: [{"id": 1, "email": "offline@example.invalid", "plan": plan}])
    monkeypatch.setattr(harness.worker, "get_user_delivery_preferences",
                        lambda ids: {1: {"daily_digest": {"email": True}}})
    result = harness.worker.run_index_delivery(send=True)
    assert result["emails_sent"] == 0 and result["emails_skipped"] == 1
    assert any(e[4].get("reason") == reason for e in harness.events)
    harness.worker.send_email_v2.assert_not_called()
    harness.worker.generate_ai_digest_for_plan.assert_not_called()


def test_recipient_lock_prevents_overlapping_send(harness, monkeypatch):
    @contextmanager
    def busy(*args):
        yield False
    monkeypatch.setattr(guard, "recipient_lock", busy)
    harness.worker.run_index_delivery(send=True)
    harness.worker.send_telegram_v2.assert_not_called()
    assert any(e[4].get("reason") == "recipient_busy" for e in harness.events)


def test_failed_ledger_after_send_is_not_retried(harness):
    harness.worker.record_index_delivery.side_effect = RuntimeError("offline ledger failure")
    with pytest.raises(RuntimeError, match="offline ledger failure"):
        harness.worker.run_index_delivery(send=True)
    result = harness.worker.run_index_delivery(send=True)
    assert result["telegrams_skipped"] == 1
    assert harness.worker.send_telegram_v2.call_count == 1


def test_missing_audit_table_fails_before_transport(harness, monkeypatch):
    monkeypatch.setattr(guard, "append_attempt", Mock(side_effect=RuntimeError("migration required")))
    with pytest.raises(RuntimeError, match="migration required"):
        harness.worker.run_index_delivery(send=True)
    harness.worker.send_telegram_v2.assert_not_called()


@pytest.mark.parametrize("endpoint", ["pro-delivery", "geri-delivery"])
@pytest.mark.parametrize("send", [False, True])
def test_manual_endpoint_requires_explicit_send(harness, monkeypatch, endpoint, send):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.api import internal_routes
    monkeypatch.setattr(internal_routes, "validate_runner_token", lambda *a: None)
    monkeypatch.setattr(internal_routes, "run_job_with_lock",
                        lambda name, operation: (operation(), 200))
    app = FastAPI()
    app.include_router(internal_routes.router)
    response = TestClient(app).post(
        f"/internal/run/{endpoint}" + ("?send=true" if send else ""))
    assert response.status_code == 200
    assert harness.worker.send_telegram_v2.call_count == int(send)
    assert bool(response.json()["renders"]) is not send


def test_alerts_runner_only_engine_and_trader(monkeypatch):
    path = Path(__file__).parents[1] / "generated-artifacts/digest-guard-20261113-ops/scripts/replit_scheduled_job.py"
    # The website does not deploy this Cloud entry point; test its ops candidate
    # when running this shared test from the website checkout.
    if not path.exists():
        path = Path(__file__).parents[1] / "scripts" / "replit_scheduled_job.py"
    spec = importlib.util.spec_from_file_location("guarded_test_runner", path)
    import sys
    runner = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, runner)
    spec.loader.exec_module(runner)
    monkeypatch.setattr(runner, "_configuration", lambda: "offline")
    calls = []
    monkeypatch.setattr(runner, "_invoke", lambda name, *a, **kw: calls.append((name, kw)))
    monkeypatch.setenv("ALERTS_ENABLED", "true")
    monkeypatch.setenv("INCLUDE_PRO_DELIVERY", "true")
    monkeypatch.setenv("INCLUDE_TRADER_DELIVERY", "true")
    monkeypatch.setenv("DRY_RUN", "false")
    runner.run_job("alerts")
    assert [call[0] for call in calls] == ["alerts", "trader_delivery"]
    assert calls[0][1]["phase"] == "all"
