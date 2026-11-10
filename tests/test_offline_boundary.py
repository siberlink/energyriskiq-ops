"""Prove the default pytest process cannot reach external databases or APIs."""
import os
import socket

import httpx
import psycopg2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_database_block_holds_even_if_credentials_are_reintroduced(monkeypatch):
    monkeypatch.setenv("PRODUCTION_DATABASE_URL", "postgresql://dummy@production.invalid/db")
    monkeypatch.setenv("RISK_PIPELINE_V2_MODE", "shadow")
    with pytest.raises(RuntimeError, match="database access blocked"):
        psycopg2.connect(os.environ["PRODUCTION_DATABASE_URL"])


@pytest.mark.parametrize("method", ["connect", "connect_ex"])
def test_real_network_blocked(method):
    with socket.socket() as sock:
        with pytest.raises(RuntimeError, match="paid API access blocked"):
            getattr(sock, method)(("127.0.0.1", 443))


def test_paid_api_block_holds_with_reintroduced_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "dummy-key-not-a-credential")
    with pytest.raises(RuntimeError, match="paid API access blocked"):
        httpx.get("http://127.0.0.1:443", trust_env=False)


def test_default_mode_off_and_credentials_absent():
    assert os.environ["RISK_PIPELINE_V2_MODE"] == "off"
    assert "PRODUCTION_DATABASE_URL" not in os.environ
    assert "AI_INTEGRATIONS_OPENAI_API_KEY" not in os.environ


def test_asgi_remains_available():
    app = FastAPI()

    @app.get("/")
    def root():
        return {"ok": True}

    with TestClient(app) as client:
        assert client.get("/").json() == {"ok": True}
