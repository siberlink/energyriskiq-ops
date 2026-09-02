from contextlib import contextmanager

import pytest
from fastapi import HTTPException

from src.api import user_routes


class _ProfileCursor:
    def __init__(self):
        self.params = None

    def execute(self, _query, params):
        self.params = params

    def fetchone(self):
        first_name, last_name, interests, user_id = self.params
        return {
            "id": user_id,
            "email": "profile@example.com",
            "first_name": first_name,
            "last_name": last_name,
            "industry_interests": interests,
        }


def test_profile_interest_enum_and_labels_stay_aligned():
    enum_values = {item.value for item in user_routes.IndustryInterest}

    assert enum_values == set(user_routes.INDUSTRY_INTEREST_LABELS)
    assert {
        "oil_trading",
        "gas_trading",
        "lng_trading",
        "energy_market_analysis",
        "risk_management",
        "portfolio_management",
    }.issubset(enum_values)


def test_save_user_profile_trims_names_and_deduplicates_interests(monkeypatch):
    cursor = _ProfileCursor()

    @contextmanager
    def fake_get_cursor(*_args, **_kwargs):
        yield cursor

    monkeypatch.setattr(
        user_routes,
        "verify_user_session",
        lambda _token: {"user_id": 42},
    )
    monkeypatch.setattr(user_routes, "get_cursor", fake_get_cursor)

    body = user_routes.UserProfileRequest(
        first_name="  Ada ",
        last_name=" Lovelace  ",
        industry_interests=["oil_trading", "oil_trading", "risk_management"],
    )
    result = user_routes.save_user_profile(body, "session-token")

    assert cursor.params == (
        "Ada",
        "Lovelace",
        ["oil_trading", "risk_management"],
        42,
    )
    assert result["profile_complete"] is True
    assert result["industry_interests"] == ["oil_trading", "risk_management"]


@pytest.mark.parametrize(
    ("first_name", "last_name", "interests", "message"),
    [
        ("", "Lovelace", ["oil_trading"], "First and last name are required"),
        ("Ada", " ", ["oil_trading"], "First and last name are required"),
        ("Ada", "Lovelace", [], "Select at least one industry interest"),
    ],
)
def test_save_user_profile_rejects_incomplete_profiles(
    monkeypatch,
    first_name,
    last_name,
    interests,
    message,
):
    monkeypatch.setattr(
        user_routes,
        "verify_user_session",
        lambda _token: {"user_id": 42},
    )
    body = user_routes.UserProfileRequest(
        first_name=first_name,
        last_name=last_name,
        industry_interests=interests,
    )

    with pytest.raises(HTTPException) as exc:
        user_routes.save_user_profile(body, "session-token")

    assert exc.value.status_code == 400
    assert exc.value.detail == message