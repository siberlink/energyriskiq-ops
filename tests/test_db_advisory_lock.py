import threading

import pytest

from src.db import db


class _Cursor:
    def __init__(self, connection):
        self.connection = connection
        self.query = None

    def execute(self, query, _params=None):
        self.query = query
        self.connection.queries.append(query)
        if query == "SELECT 1":
            self.connection.heartbeat_seen.set()

    def fetchone(self):
        return {"pg_try_advisory_lock": True}

    def close(self):
        pass


class _Connection:
    def __init__(self):
        self.queries = []
        self.heartbeat_seen = threading.Event()
        self.closed = False

    def cursor(self, **_kwargs):
        return _Cursor(self)

    def close(self):
        self.closed = True


def test_advisory_lock_heartbeats_and_releases(monkeypatch):
    connection = _Connection()
    observed_connect_kwargs = {}

    def connect(_url, **kwargs):
        observed_connect_kwargs.update(kwargs)
        return connection

    monkeypatch.setattr(db.psycopg2, "connect", connect)
    monkeypatch.setenv("DATABASE_URL", "postgresql://test")
    monkeypatch.setenv("ADVISORY_LOCK_HEARTBEAT_SECONDS", "0")

    with db.advisory_lock(7001) as acquired:
        assert acquired is True
        assert connection.heartbeat_seen.wait(timeout=6)

    assert "SELECT 1" in connection.queries
    assert "SELECT pg_advisory_unlock(%s)" in connection.queries
    assert connection.closed is True
    assert observed_connect_kwargs == {
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 3,
    }


def test_advisory_lock_does_not_swallow_job_errors(monkeypatch):
    connection = _Connection()
    monkeypatch.setattr(
        db.psycopg2,
        "connect",
        lambda _url, **_kwargs: connection,
    )
    monkeypatch.setenv("DATABASE_URL", "postgresql://test")

    with pytest.raises(RuntimeError, match="job failed"):
        with db.advisory_lock(7001) as acquired:
            assert acquired is True
            raise RuntimeError("job failed")