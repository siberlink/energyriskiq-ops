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