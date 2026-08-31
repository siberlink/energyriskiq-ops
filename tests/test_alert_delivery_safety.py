from contextlib import contextmanager

import pytest

from src.alerts import alerts_engine_v2


class _Cursor:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.query = None
        self.params = None

    def execute(self, query, params):
        self.query = query
        self.params = params
        if self.error:
            raise self.error

    def fetchone(self):
        return self.result


def test_create_delivery_uses_live_four_column_idempotency_key(monkeypatch):
    cursor = _Cursor(result={"id": 42})

    @contextmanager
    def fake_cursor():
        yield cursor

    monkeypatch.setattr(alerts_engine_v2, "get_cursor", fake_cursor)

    delivery_id = alerts_engine_v2.create_delivery(
        user_id=7,
        alert_event_id=11,
        channel="email",
        status="queued",
        delivery_kind="instant",
    )

    assert delivery_id == 42
    normalized = " ".join(cursor.query.split())
    assert (
        "ON CONFLICT (alert_event_id, user_id, channel, delivery_kind) "
        "DO NOTHING"
    ) in normalized


def test_create_delivery_propagates_database_errors(monkeypatch):
    cursor = _Cursor(error=RuntimeError("constraint mismatch"))

    @contextmanager
    def fake_cursor():
        yield cursor

    monkeypatch.setattr(alerts_engine_v2, "get_cursor", fake_cursor)

    with pytest.raises(RuntimeError, match="constraint mismatch"):
        alerts_engine_v2.create_delivery(
            user_id=7,
            alert_event_id=11,
            channel="email",
            status="queued",
            delivery_kind="instant",
        )