"""Offline ownership, order and AI-failure assertions; no provider or app DB."""
from datetime import date
from types import SimpleNamespace
import pytest

from src.api import internal_routes as routes


@pytest.mark.parametrize("name", ["run_eeri_compute", "run_egsi_compute"])
def test_retired_cloud_write_endpoints_refuse_execution(monkeypatch, name):
    from fastapi import HTTPException
    monkeypatch.setattr(routes, "validate_runner_token", lambda token: True)
    with pytest.raises(HTTPException) as error:
        getattr(routes, name)(x_runner_token="offline")
    assert error.value.status_code == 410


@pytest.mark.parametrize("geri_fails", [False, True])
def test_daily_never_calls_eeri_or_egsi_and_gates_delivery(monkeypatch, geri_fails):
    calls = []
    monkeypatch.setattr(routes, "validate_runner_token", lambda token: True)
    monkeypatch.setattr(routes, "run_job_with_lock",
                        lambda name, job: ({"details": job()}, 200))
    monkeypatch.setattr(routes.time, "sleep", lambda n: None)
    for name in ["market_data_capture", "oil_price_capture", "gas_storage_capture",
                 "lng_price_capture", "egsi_s_compute", "daily_report", "pro_delivery"]:
        monkeypatch.setattr(routes, "run_" + name,
            lambda _name=name, **kw: calls.append(_name) or {"status": "success"})
    def geri(**kw):
        calls.append("geri")
        if geri_fails:
            raise RuntimeError("persist failed")
        return {"status": "success", "value": 11, "model_version": "geri_v1.2"}
    monkeypatch.setattr(routes, "run_geri_compute", geri)
    def forbidden(**kw):
        raise AssertionError("Cloud called a website-owned writer")
    monkeypatch.setattr(routes, "run_eeri_compute", forbidden)
    monkeypatch.setattr(routes, "run_egsi_compute", forbidden)
    result = routes.run_daily_index_pipeline(include_delivery=True, x_runner_token="offline")["details"]
    assert "eeri" not in result and "egsi_m" not in result
    if geri_fails:
        assert "pro_delivery" not in calls and "daily_report" not in calls
        assert result["delivery"]["status"] == "blocked"
    else:
        assert calls.index("geri") < calls.index("daily_report") < calls.index("pro_delivery")
        assert result["pipeline_status"] == "success"


def test_warm_empty_narrative_is_not_success(monkeypatch):
    from src.api import daily_digest_routes as digest
    monkeypatch.setattr(digest, "PLAN_LEVELS", {"free": 0})
    monkeypatch.setattr(digest, "get_cached_ai_narrative", lambda key: None)
    monkeypatch.setattr(digest, "compute_daily_digest", lambda *a: {"ai_narrative": "  "})
    result = digest.warm_daily_digest_cache()
    assert result["status"] == "failed" and result["ai_section_missing"]
    assert result["results"][0]["ok"] is False
    assert result["results"][0]["narrative_chars"] == 0
    with pytest.raises(RuntimeError):
        routes._validate_daily_stage("daily_report", result)


def test_delivery_missing_ai_is_in_results_and_audit(monkeypatch):
    from src.delivery import pro_delivery_worker as delivery
    monkeypatch.setattr(delivery, "ensure_index_digest_unique_index", lambda: None)
    monkeypatch.setattr(delivery, "get_all_users_with_plans", lambda: [
        {"id": 1, "email": None, "telegram_chat_id": "offline", "plan": "personal"}])
    monkeypatch.setattr(delivery, "get_user_delivery_preferences",
                        lambda ids: {1: {"daily_digest": {"telegram": True}}})
    monkeypatch.setattr(delivery, "get_latest_geri",
                        lambda **kw: {"date": date(2026, 11, 10), "value": 11})
    for name in ["get_latest_eeri", "get_latest_egsi", "get_asset_snapshots"]:
        monkeypatch.setattr(delivery, name, lambda: {})
    monkeypatch.setattr(delivery, "generate_ai_digest_for_plan", lambda *a: None)
    monkeypatch.setattr(delivery, "has_been_delivered_today", lambda *a: False)
    monkeypatch.setattr(delivery, "build_full_telegram", lambda *a, **kw: "offline render")
    monkeypatch.setattr(delivery, "send_telegram_v2",
                        lambda *a: SimpleNamespace(success=True))
    records = []
    monkeypatch.setattr(delivery, "record_index_delivery",
                        lambda *a, **kw: records.append(kw))
    result = delivery.run_index_delivery()
    assert result["ai_section_missing"] and result["telegrams_sent"] == 1
    assert records[0]["ai_section_missing"] and records[0]["geri_value"] == 11
    with pytest.raises(RuntimeError, match="ai_section_missing: true"):
        routes._validate_daily_stage("delivery", result)


def test_revision_window_uses_latest_published_day_not_requested_yesterday(monkeypatch):
    from contextlib import contextmanager
    from datetime import timedelta
    from unittest.mock import Mock
    from src.ingest import gas_storage_revisions as rev
    from tests.test_storage_writer_postgres import observation
    end = date(2026, 11, 9)
    entries = [observation(str(end-timedelta(days=i))) for i in range(7)]
    requested = []
    monkeypatch.setattr(rev, "fetch_eu_storage_data", lambda: entries[0])
    def provider(endpoint, params):
        requested.append((endpoint, params))
        return {"data": [e for e in entries if e["date"] == params["date"]]} if endpoint == "eu" else {"data": entries}
    monkeypatch.setattr(rev, "_make_api_request", provider)
    monkeypatch.setattr(rev, "select_eu_entry", lambda rows: rows[0] if rows else None)
    monkeypatch.setattr(rev, "normalize_storage_entry", lambda row, area: row.copy())
    monkeypatch.setattr(rev, "_existing", lambda *a: None)
    @contextmanager
    def cursor(**kwargs):
        yield Mock()
    monkeypatch.setattr(rev, "get_cursor", cursor)
    plan = rev.prepare_revision_plan(end_day="2026-11-10")
    assert (plan["start"], plan["end"]) == ("2026-11-03", "2026-11-09")
    assert len(plan["observations"]) == 77 and not plan["errors"]
    assert all(o["data"]["status"] in ("E", "C") for o in plan["observations"])
    assert all(p.get("date") != "2026-11-10" for _, p in requested)
