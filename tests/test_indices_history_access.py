import asyncio

from src.api import indices_history_routes as routes


class _Cursor:
    def __init__(self, row):
        self.row = row

    def execute(self, *_args, **_kwargs):
        pass

    def fetchone(self):
        return self.row


class _CursorContext:
    def __init__(self, row):
        self.cursor = _Cursor(row)

    def __enter__(self):
        return self.cursor

    def __exit__(self, *_args):
        return False


def test_manual_indices_history_access_grants_runtime_entitlement(monkeypatch):
    monkeypatch.setattr(
        routes,
        "get_cursor",
        lambda **_kwargs: _CursorContext({"status": "active"}),
    )
    assert routes._manual_access(7) is True


def test_inactive_manual_indices_history_access_is_denied(monkeypatch):
    monkeypatch.setattr(
        routes,
        "get_cursor",
        lambda **_kwargs: _CursorContext({"status": "inactive"}),
    )
    monkeypatch.setattr(routes, "_geri_live_bonus", lambda _user_id: False)
    assert routes.user_has_indices_history(7) is False


def test_status_reports_manual_access_without_exposing_stripe_management(monkeypatch):
    monkeypatch.setattr(
        routes,
        "_get_user_from_token",
        lambda _token: {"id": 7, "email": "emilconstantin22@gmail.com"},
    )
    monkeypatch.setattr(
        routes,
        "_get_or_create_row",
        lambda _user_id: {
            "status": "active",
            "stripe_subscription_id": None,
            "current_period_end": None,
        },
    )
    monkeypatch.setattr(routes, "_geri_live_bonus", lambda _user_id: False)
    monkeypatch.setattr(routes, "_manual_access", lambda _user_id: True)
    result = asyncio.run(routes.status("token"))
    assert result["active"] is True
    assert result["manual_access"] is True
    assert result["geri_live_bonus"] is False