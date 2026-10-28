"""Offline regression coverage for final-health and midnight parity."""
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.geri import live_v12, version12
from src.geri.shadow_smoothing import calculate
from src.geri.v12_history import FinalHealthPending, final_health, final_history
from scripts.geri_lab.variants import get_variant


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv("RISK_PIPELINE_V2_MODE", "off")
    monkeypatch.setenv("GERI_PUBLISHED_MODEL", "v1.1")
    monkeypatch.setenv("GERI_LIVE_MODEL", "legacy")
    monkeypatch.setattr("psycopg2.connect", Mock(side_effect=AssertionError("Offline test")))
    monkeypatch.setattr("socket.socket.connect", Mock(side_effect=AssertionError("No network")))


def health(day, quality="OK", **extra):
    return {"index_date": day, "data_quality": quality, "provisional": False,
            "computed_at": datetime.combine(day+timedelta(days=1), time(1, 30), timezone.utc),
            **extra}


@pytest.mark.parametrize("missing,provisional", [(True, False), (False, True)])
def test_final_health_refuses_missing_or_provisional(missing, provisional):
    d = date(2026, 10, 27)
    c = Mock()
    c.fetchone.return_value = None if missing else health(d, provisional=provisional)
    with pytest.raises(FinalHealthPending):
        final_health(c, d)


def test_late_repair_affects_evidence_not_history():
    d = date(2026, 10, 23)
    h = [{"index_date": d+timedelta(days=i), "components": {},
          "inputs": {"data_quality": "DEGRADED"}} for i in range(3)]
    c = Mock()
    c.fetchall.return_value = [health(d, late_repair=True),
        health(d+timedelta(days=1), "DEGRADED"),
        health(d+timedelta(days=2), "UNAVAILABLE")]
    result = final_history(c, h)
    assert [r["inputs"]["data_quality"] for r in result] == ["OK", "DEGRADED", "UNAVAILABLE"]
    assert h[0]["inputs"]["data_quality"] == "DEGRADED"  # never mutate frozen inputs


@pytest.mark.parametrize("model", ["v1.1", "v1.2"])
def test_private_and_shadow_identical_through_final_ok_late_repair(monkeypatch, model):
    monkeypatch.setenv("GERI_PUBLISHED_MODEL", model)
    monkeypatch.setenv("GERI_LIVE_MODEL", "legacy" if model == "v1.1" else "v1.2")
    start = date(2026, 6, 1)
    history = []
    previous = None
    for i in range(120):
        d = start+timedelta(days=i)
        quality = "DEGRADED" if i == 63 else "UNAVAILABLE" if i == 80 else "OK"
        original = [100.+i % 17, 0., 0., 40.+i % 11]
        rows = [] if previous is None else [{"date": d-timedelta(days=1),
            "value": 20, "smoothing_state": {"transform_state": previous, "data_quality": "OK"}}]
        private = version12.calculate_day(d, [], quality, rows, history, raw_override=original)
        shadow = calculate(get_variant("wk_carry15"), d, quality, original, history, previous)
        assert private["value"] == shadow[0]
        assert private["smoothing_state"]["normalized_raw"] == shadow[1]
        assert private["smoothing_state"]["transform_state"] == shadow[2]
        assert private["smoothing_state"]["inputs_used"] == shadow[3]
        previous = shadow[2]
        history.append({"index_date": d, "components": shadow[1],
            "inputs": {"data_quality": quality, "original_raw": original,
                       "late_repair": i == 64, "smoothing_state": previous}})
    assert private["smoothing_state"]["inputs_used"]["normalization_rows"] == 88
    assert str(start+timedelta(days=64)) in private["smoothing_state"]["baseline_dates"]
    assert str(start+timedelta(days=63)) not in private["smoothing_state"]["baseline_dates"]


def test_private_does_not_compute_without_final_health(monkeypatch):
    c = Mock()
    c.fetchone.return_value = None
    @contextmanager
    def cursor(**kwargs):
        yield c
    monkeypatch.setattr(version12, "get_cursor", cursor)
    writer = Mock(side_effect=AssertionError("Must not store"))
    monkeypatch.setattr(version12, "store", writer)
    with pytest.raises(FinalHealthPending):
        version12.compute_day(date(2026, 10, 27))
    writer.assert_not_called()


def test_pre_final_private_row_recomputed_once_and_logged(monkeypatch):
    d = date(2026, 10, 27)
    old = {"date": d, "value": 21, "computed_at": datetime(2026, 10, 28, 0, 1)}
    c = Mock()
    c.fetchone.side_effect = [health(d), old]
    @contextmanager
    def cursor(**kwargs):
        yield c
    monkeypatch.setattr(version12, "get_cursor", cursor)
    monkeypatch.setattr(version12, "history_for", lambda day: ([{"date": day-timedelta(days=1)}], []))
    monkeypatch.setattr("src.geri.repo.get_alerts_for_date", lambda day: [])
    expected = {"date": d, "value": 21, "smoothing_state": {"data_quality": "OK"}}
    monkeypatch.setattr(version12, "calculate_day", lambda *a: expected)
    store = Mock()
    monkeypatch.setattr(version12, "store", store)
    monkeypatch.setattr(version12, "parity_monitor", Mock())
    monkeypatch.setattr(live_v12, "finalize_close", Mock())
    assert version12.compute_day(d) == expected
    assert store.call_args.kwargs["apply_revision"] is True
    assert store.call_args.kwargs["backfilled"] is True
    assert any("health_finalization_correction" in str(call) for call in c.execute.call_args_list)


def test_live_waits_without_creating_speculative_daily(monkeypatch):
    previous = {"value": 22, "band": "MODERATE", "components": {},
                "metadata": {"smoothing_state": {"data_quality": "OK"}}}
    monkeypatch.setattr(live_v12, "latest", lambda: previous)
    monkeypatch.setattr(live_v12, "compute_day",
                        Mock(side_effect=FinalHealthPending("pending")))
    persist = Mock(side_effect=lambda row, *a: row)
    monkeypatch.setattr(live_v12, "persist", persist)
    result = live_v12.tick(20, datetime(2026, 10, 27, 0, 21, tzinfo=timezone.utc))
    assert result["value"] == 22
    assert result["metadata"]["awaiting_final_health"]
    assert result["metadata"]["boundary_hold"]
    assert "awaiting_final_health" not in previous["metadata"]


def test_live_raw_transition_preserves_daily_endpoint(monkeypatch):
    d = date(2026, 10, 27)
    # A sharp projected target must enter continuously, rather than replacing
    # the no-alert hold as soon as the first three alerts arrive.
    state = {"transform_state": {"ewma": [240., 0., 0., 65.]}, "data_quality": "OK"}
    rows = [{"date": d-timedelta(days=1), "value": 22, "smoothing_state": state}]
    history = [{"index_date": d-timedelta(days=i), "components":
        {"raw_H": 100.+i*5, "raw_R": 0., "raw_A": 0., "raw_C": 30.+i},
        "inputs": {"data_quality": "OK", "original_raw": [230., 0., 0., 65.]}}
        for i in range(1, 57)]
    alerts = [SimpleNamespace(id=i, created_at=datetime.combine(d, time(0, 20)))
              for i in range(3)]
    from src.geri.types import GERIComponents
    def components(alerts):
        result = GERIComponents()
        result.high_impact_score = 13.75
        result.region_concentration_score_raw = 40.
        return result
    monkeypatch.setattr(live_v12, "compute_components", components)
    monkeypatch.setattr(version12, "compute_components", components)
    at = datetime.combine(d, time(0, 21), timezone.utc)
    result = live_v12.estimate(at, alerts, rows, history, {}, set(), previous_live=22)
    assert result["metadata"]["transition_weight"] == pytest.approx(21/120)
    assert result["smoothing_state"]["original_raw"][0] > 55.
    for seconds in (0, 600, 7200):
        complete = live_v12.estimate(at, [], rows, history, {}, set(),
                                    complete=True, transition_seconds=seconds)
        daily = version12.calculate_day(d, [], "OK", rows, history,
                                         raw_override=[13.75, 0., 0., 40.])
        assert complete["value"] == daily["value"]
        assert complete["smoothing_state"] == daily["smoothing_state"]


def test_close_revision_is_private_audited_and_not_gate_evidence(monkeypatch):
    d = date(2026, 10, 27)
    c = Mock()
    c.fetchone.return_value = {"id": 1, "computed_at": datetime(2026, 10, 27, 23, 56,
        tzinfo=timezone.utc), "value": 22, "band": "MODERATE", "components": {}, "metadata": {}}
    @contextmanager
    def cursor(**kwargs):
        yield c
    monkeypatch.setattr(live_v12, "get_cursor", cursor)
    assert live_v12.finalize_close({"date": d, "value": 21, "band": "MODERATE",
                                    "components": {}, "smoothing_state": {}})
    statements = [call.args[0] for call in c.execute.call_args_list]
    assert any("INSERT INTO geri_v12_revisions" in sql for sql in statements)
    assert any("UPDATE geri_live_v12_shadow" in sql for sql in statements)
    assert any("health_finalization_correction" in sql for sql in statements)
    assert not any("UPDATE intel_indices_daily " in sql for sql in statements)
