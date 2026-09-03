from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from src.alerts import runner
from src.api import internal_routes


class _Tracker:
    instances = []

    def __init__(self, phase, dry_run):
        self.phase = phase
        self.dry_run = dry_run
        self.started = []
        self.ended = []
        self.finished = []
        self.instances.append(self)

    def start(self):
        return "run-1"

    def record_phase_start(self, phase):
        self.started.append(phase)
        return f"item-{phase}"

    def record_phase_end(self, item, status, counts=None, error=None):
        self.ended.append((item, status, counts, error))

    def finish(self, status, counts, error=None):
        self.finished.append((status, counts, error))


def test_execute_phases_preserves_order_bounds_and_observability(monkeypatch):
    calls = []
    _Tracker.instances.clear()
    monkeypatch.setattr("src.alerts.engine_observability.EngineRunTracker", _Tracker)
    monkeypatch.setattr(
        runner,
        "run_phase_a",
        lambda now, dry_run: calls.append(("a", dry_run)) or {
            "status": "success", "counts": {"a": 1}
        },
    )
    monkeypatch.setattr(
        runner,
        "run_phase_b",
        lambda now, since_hours, dry_run: calls.append(
            ("b", since_hours, dry_run)
        ) or {"status": "success", "counts": {"b": 1}},
    )
    monkeypatch.setattr(
        runner,
        "run_phase_d",
        lambda now, dry_run: calls.append(("d", dry_run)) or {
            "status": "success", "counts": {"d": 1}
        },
    )
    monkeypatch.setattr(
        runner,
        "run_phase_c",
        lambda now, batch_size, dry_run: calls.append(
            ("c", batch_size, dry_run)
        ) or {"status": "success", "counts": {"c": 1}},
    )

    result = runner.execute_phases(
        "all", dry_run=True, since_hours=12, batch_size=75
    )

    assert calls == [
        ("a", True),
        ("b", 12, True),
        ("d", True),
        ("c", 75, True),
    ]
    assert result["overall_status"] == "success"
    assert result["phases_executed"] == 4
    tracker = _Tracker.instances[0]
    assert tracker.started == ["a", "b", "d", "c"]
    assert tracker.finished[0][0] == "success"

    with pytest.raises(ValueError):
        runner.execute_phases("invalid")
    with pytest.raises(ValueError):
        runner.execute_phases("a", since_hours=0)
    with pytest.raises(ValueError):
        runner.execute_phases("c", batch_size=1001)


def test_internal_alert_endpoint_runs_preflight_and_forwards_controls(monkeypatch):
    observed = {}
    monkeypatch.setenv("ALERTS_V2_ENABLED", "true")
    monkeypatch.setattr(internal_routes, "validate_runner_token", lambda token: True)
    monkeypatch.setattr(
        internal_routes,
        "run_job_with_lock",
        lambda name, job: ({"status": "ok", "details": job()}, 200),
    )
    monkeypatch.setattr(
        runner,
        "run_preflight",
        lambda log_json=False: {"errors": [], "warnings": []},
    )

    def execute(**kwargs):
        observed.update(kwargs)
        return {"overall_status": "success"}

    monkeypatch.setattr(runner, "execute_phases", execute)

    response = internal_routes.run_alerts(
        phase="b",
        dry_run=True,
        since_hours=12,
        batch_size=50,
        skip_preflight=False,
        x_runner_token="valid",
    )

    assert response["status"] == "ok"
    assert observed == {
        "phase": "b",
        "dry_run": True,
        "since_hours": 12,
        "batch_size": 50,
    }


def test_internal_alert_endpoint_rejects_bad_phase_and_failed_preflight(monkeypatch):
    monkeypatch.setenv("ALERTS_V2_ENABLED", "true")
    monkeypatch.setattr(internal_routes, "validate_runner_token", lambda token: True)

    with pytest.raises(HTTPException) as invalid:
        internal_routes.run_alerts(
            phase="nope",
            dry_run=False,
            since_hours=24,
            batch_size=200,
            skip_preflight=False,
            x_runner_token="valid",
        )
    assert invalid.value.status_code == 400

    monkeypatch.setattr(
        internal_routes,
        "run_job_with_lock",
        lambda name, job: (job(), 200),
    )
    monkeypatch.setattr(
        runner,
        "run_preflight",
        lambda log_json=False: {"errors": ["database unavailable"]},
    )
    monkeypatch.setattr(
        runner,
        "execute_phases",
        lambda **kwargs: pytest.fail("phases must not run after failed preflight"),
    )

    with pytest.raises(RuntimeError, match="database unavailable"):
        internal_routes.run_alerts(
            phase="all",
            dry_run=False,
            since_hours=24,
            batch_size=200,
            skip_preflight=False,
            x_runner_token="valid",
        )


def test_ingestion_pipeline_endpoint_runs_stages_under_one_lock(monkeypatch):
    calls = []
    monkeypatch.setenv("OPENAI_API_KEY", "configured-for-test")
    monkeypatch.setattr(internal_routes, "validate_runner_token", lambda token: True)
    monkeypatch.setattr(
        "src.ingest.ingest_runner.run_ingestion",
        lambda: calls.append("ingestion") or (3, 2, 0),
    )
    monkeypatch.setattr(
        "src.ai.ai_worker.run_ai_worker",
        lambda: calls.append("ai") or (3, 0),
    )
    monkeypatch.setattr(
        "src.risk.risk_engine.run_risk_engine",
        lambda: calls.append("risk") or 3,
    )

    def run_locked(name, job):
        assert name == "ingestion_pipeline"
        return {"status": "ok", "details": job()}, 200

    monkeypatch.setattr(internal_routes, "run_job_with_lock", run_locked)

    response = internal_routes.run_ingestion_pipeline(
        skip_ai=False,
        skip_risk=False,
        x_runner_token="valid",
    )

    assert calls == ["ingestion", "ai", "risk"]
    assert response["details"]["ingestion"] == {
        "inserted": 3,
        "skipped": 2,
        "errors": 0,
    }


def test_ingestion_pipeline_skip_controls_and_busy_result(monkeypatch):
    calls = []
    monkeypatch.setattr(internal_routes, "validate_runner_token", lambda token: True)
    monkeypatch.setattr(
        "src.ingest.ingest_runner.run_ingestion",
        lambda: calls.append("ingestion") or (0, 0, 0),
    )
    monkeypatch.setattr(
        internal_routes,
        "run_job_with_lock",
        lambda name, job: (
            {"status": "busy", "job": name},
            409,
        ),
    )

    with pytest.raises(HTTPException) as busy:
        internal_routes.run_ingestion_pipeline(
            skip_ai=True,
            skip_risk=True,
            x_runner_token="valid",
        )

    assert busy.value.status_code == 409
    assert calls == []


def test_metadata_backfill_endpoint_uses_application_lock(monkeypatch):
    monkeypatch.setattr(internal_routes, "validate_runner_token", lambda token: True)
    monkeypatch.setattr(
        "src.alerts.backfill_metadata.backfill_alert_metadata",
        lambda dry_run: {"updated": 4, "errors": 0, "dry_run": dry_run},
    )

    observed = {}

    def run_locked(name, job):
        observed["name"] = name
        observed["result"] = job()
        return {"status": "ok", "details": observed["result"]}, 200

    monkeypatch.setattr(internal_routes, "run_job_with_lock", run_locked)

    response = internal_routes.backfill_alert_metadata_endpoint(
        dry_run=True,
        x_runner_token="valid",
    )

    assert observed == {
        "name": "alert_metadata_backfill",
        "result": {"updated": 4, "errors": 0, "dry_run": True},
    }
    assert response["details"]["updated"] == 4


def test_ingestion_pipeline_propagates_item_failures(monkeypatch):
    monkeypatch.setattr(internal_routes, "validate_runner_token", lambda token: True)
    monkeypatch.setattr(
        "src.ingest.ingest_runner.run_ingestion",
        lambda: (3, 1, 2),
    )
    monkeypatch.setattr(
        internal_routes,
        "run_job_with_lock",
        lambda name, job: ({"status": "ok", "details": job()}, 200),
    )

    with pytest.raises(RuntimeError, match="2 item errors"):
        internal_routes.run_ingestion_pipeline(
            skip_ai=True,
            skip_risk=True,
            x_runner_token="valid",
        )


def test_daily_pipeline_runs_ordered_stages_under_one_lock(monkeypatch):
    calls = []
    monkeypatch.setattr(internal_routes, "validate_runner_token", lambda token: True)
    monkeypatch.setattr(internal_routes.time, "sleep", lambda seconds: calls.append("settle"))

    stages = [
        ("run_market_data_capture", "market_data"),
        ("run_oil_price_capture", "oil_price"),
        ("run_gas_storage_capture", "gas_storage"),
        ("run_geri_compute", "geri"),
        ("run_eeri_compute", "eeri"),
        ("run_lng_price_capture", "lng_price"),
        ("run_egsi_compute", "egsi_m"),
        ("run_egsi_s_compute", "egsi_s"),
        ("run_daily_report", "daily_report"),
        ("run_pro_delivery", "delivery"),
    ]
    for function_name, stage_name in stages:
        details = {"status": "success"}
        if stage_name == "geri":
            details["value"] = 42.0
        monkeypatch.setattr(
            internal_routes,
            function_name,
            lambda stage=stage_name, **_kwargs: (
                calls.append(stage)
                or {
                    "status": "ok",
                    "details": {
                        "status": "success",
                        **({"value": 42.0} if stage == "geri" else {}),
                    },
                }
            ),
        )

    def run_locked(name, job):
        assert name == "daily_index_pipeline"
        return {"status": "ok", "details": job()}, 200

    monkeypatch.setattr(internal_routes, "run_job_with_lock", run_locked)

    response = internal_routes.run_daily_index_pipeline(
        include_delivery=True,
        x_runner_token="valid",
    )

    assert calls == [
        "market_data",
        "oil_price",
        "gas_storage",
        "geri",
        "eeri",
        "lng_price",
        "egsi_m",
        "egsi_s",
        "daily_report",
        "settle",
        "delivery",
    ]
    assert response["status"] == "ok"


def test_daily_pipeline_stops_after_failed_prerequisite(monkeypatch):
    calls = []
    monkeypatch.setattr(internal_routes, "validate_runner_token", lambda token: True)
    monkeypatch.setattr(
        internal_routes,
        "run_market_data_capture",
        lambda **_kwargs: calls.append("market_data") or {
            "status": "ok",
            "details": {
                "sources": {
                    "vix": {"status": "success"},
                    "ttf": {"status": "error"},
                }
            },
        },
    )
    monkeypatch.setattr(
        internal_routes,
        "run_oil_price_capture",
        lambda **_kwargs: calls.append("oil_price") or {},
    )
    monkeypatch.setattr(
        internal_routes,
        "run_job_with_lock",
        lambda name, job: ({"status": "ok", "details": job()}, 200),
    )

    with pytest.raises(RuntimeError, match="failed sources: ttf"):
        internal_routes.run_daily_index_pipeline(
            include_delivery=False,
            x_runner_token="valid",
        )

    assert calls == ["market_data"]


def test_daily_pipeline_allows_disabled_optional_indices(monkeypatch):
    calls = []
    monkeypatch.setattr(internal_routes, "validate_runner_token", lambda token: True)
    monkeypatch.setattr(internal_routes.time, "sleep", lambda _seconds: None)

    successful_stages = [
        ("run_market_data_capture", "market_data"),
        ("run_oil_price_capture", "oil_price"),
        ("run_gas_storage_capture", "gas_storage"),
        ("run_geri_compute", "geri"),
        ("run_lng_price_capture", "lng_price"),
        ("run_daily_report", "daily_report"),
        ("run_pro_delivery", "delivery"),
    ]
    for function_name, stage_name in successful_stages:
        details = {"status": "success"}
        if stage_name == "geri":
            details["value"] = 42
        monkeypatch.setattr(
            internal_routes,
            function_name,
            lambda stage=stage_name, result=details, **_kwargs: (
                calls.append(stage)
                or {"status": "ok", "details": result}
            ),
        )

    monkeypatch.setattr(
        internal_routes,
        "run_eeri_compute",
        lambda **_kwargs: calls.append("eeri") or {
            "status": "skipped",
            "message": "EERI module is disabled (ENABLE_EERI=false)",
        },
    )
    monkeypatch.setattr(
        internal_routes,
        "run_egsi_compute",
        lambda **_kwargs: pytest.fail("EGSI-M depends on EERI and must be skipped"),
    )
    monkeypatch.setattr(
        internal_routes,
        "run_egsi_s_compute",
        lambda **_kwargs: calls.append("egsi_s") or {
            "status": "skipped",
            "message": "EGSI module is disabled (ENABLE_EGSI=false)",
        },
    )
    monkeypatch.setattr(
        internal_routes,
        "run_job_with_lock",
        lambda name, job: ({"status": "ok", "details": job()}, 200),
    )

    response = internal_routes.run_daily_index_pipeline(
        include_delivery=True,
        x_runner_token="valid",
    )

    assert calls == [
        "market_data",
        "oil_price",
        "gas_storage",
        "geri",
        "eeri",
        "lng_price",
        "egsi_s",
        "daily_report",
        "delivery",
    ]
    assert response["details"]["egsi_m"]["status"] == "skipped"
    assert response["details"]["delivery"]["status"] == "ok"


def test_daily_stage_validation_allows_explicit_existing_geri_skip():
    response = {
        "status": "ok",
        "details": {
            "status": "skipped",
            "reason": "already_exists",
            "date": "2026-09-02",
        },
    }

    assert internal_routes._validate_daily_stage("geri", response) is response


def test_daily_stage_validation_rejects_ambiguous_geri_no_result():
    with pytest.raises(RuntimeError, match="geri did not produce"):
        internal_routes._validate_daily_stage(
            "geri",
            {
                "status": "ok",
                "details": {
                    "message": "No computation needed (already exists or no data)"
                },
            },
        )

    with pytest.raises(RuntimeError, match="gas_storage has no required source"):
        internal_routes._validate_daily_stage(
            "gas_storage",
            {
                "status": "ok",
                "details": {
                    "status": "skipped",
                    "message": "No EU-aggregate gas storage data available",
                },
            },
        )


def test_geri_compute_skips_existing_yesterday_without_writing(monkeypatch):
    from src.geri import repo as geri_repo
    from src.geri import service as geri_service

    monkeypatch.setattr(internal_routes, "validate_runner_token", lambda token: True)
    monkeypatch.setattr(geri_repo, "get_index_for_date", lambda _target_date: {"value": 42})
    monkeypatch.setattr(
        geri_service,
        "compute_geri_for_date",
        lambda *_args, **_kwargs: pytest.fail(
            "existing GERI must not be recomputed or written"
        ),
    )
    monkeypatch.setattr(
        internal_routes,
        "run_job_with_lock",
        lambda name, job: ({"status": "ok", "details": job()}, 200),
    )

    response = internal_routes.run_geri_compute(
        mode="yesterday",
        force=False,
        x_runner_token="valid",
    )

    assert response["details"]["status"] == "skipped"
    assert response["details"]["reason"] == "already_exists"
    assert response["details"]["date"] == (
        internal_routes.date.today() - internal_routes.timedelta(days=1)
    ).isoformat()


def test_daily_pipeline_continues_after_optional_gas_storage_failure(monkeypatch):
    calls = []
    monkeypatch.setattr(internal_routes, "validate_runner_token", lambda token: True)
    monkeypatch.setattr(internal_routes.time, "sleep", lambda _seconds: None)

    stage_names = [
        ("run_market_data_capture", "market_data"),
        ("run_oil_price_capture", "oil_price"),
        ("run_geri_compute", "geri"),
        ("run_eeri_compute", "eeri"),
        ("run_lng_price_capture", "lng_price"),
        ("run_egsi_compute", "egsi_m"),
        ("run_egsi_s_compute", "egsi_s"),
        ("run_daily_report", "daily_report"),
        ("run_pro_delivery", "delivery"),
    ]
    for function_name, stage_name in stage_names:
        monkeypatch.setattr(
            internal_routes,
            function_name,
            lambda stage=stage_name, **_kwargs: (
                calls.append(stage)
                or {
                    "status": "ok",
                    "details": {
                        "status": "success",
                        **({"value": 42.0} if stage == "geri" else {}),
                    },
                }
            ),
        )

    monkeypatch.setattr(
        internal_routes,
        "run_gas_storage_capture",
        lambda **_kwargs: calls.append("gas_storage") or {
            "status": "ok",
            "details": {
                "status": "error",
                "message": "invalid upstream storage value",
            },
        },
    )
    monkeypatch.setattr(
        internal_routes,
        "run_job_with_lock",
        lambda name, job: ({"status": "ok", "details": job()}, 200),
    )

    response = internal_routes.run_daily_index_pipeline(
        include_delivery=True,
        x_runner_token="valid",
    )

    assert calls == [
        "market_data",
        "oil_price",
        "gas_storage",
        "geri",
        "eeri",
        "lng_price",
        "egsi_m",
        "egsi_s",
        "daily_report",
        "delivery",
    ]
    assert response["details"]["gas_storage"]["status"] == "degraded"