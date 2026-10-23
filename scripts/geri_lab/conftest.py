"""Offline research tests must not inherit the activated production pipeline."""
import pytest


@pytest.fixture(autouse=True)
def offline_pipeline_defaults(monkeypatch):
    # Tests that exercise a mode explicitly override this within their own body.
    # The old boolean alone cannot override a shared explicit shadow setting.
    monkeypatch.delenv("RISK_PIPELINE_V2_MODE",raising=False)
    monkeypatch.setenv("RISK_PIPELINE_V2_ENABLED","false")
    import httpx
    import requests
    def forbidden(*args,**kwargs):
        raise AssertionError("Live HTTP requests are forbidden in offline GERI lab tests")
    monkeypatch.setattr(httpx.Client,"send",forbidden)
    monkeypatch.setattr(requests.sessions.Session,"request",forbidden)
