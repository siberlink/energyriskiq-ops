from contextlib import contextmanager

from src.alerts import db_locks


def test_alerts_lock_delegates_to_hardened_shared_lock(monkeypatch):
    observed = {}

    @contextmanager
    def fake_advisory_lock(lock_id):
        observed["lock_id"] = lock_id
        yield True

    monkeypatch.setattr(db_locks, "advisory_lock", fake_advisory_lock)

    with db_locks.AdvisoryLock("alerts_v2_phase_b") as lock:
        assert lock.acquired is True

    assert observed["lock_id"] == db_locks._key_to_bigint(
        "alerts_v2_phase_b"
    )