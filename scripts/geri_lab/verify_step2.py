"""Run all Python tests without allowing production writes or outbound delivery."""
from unittest.mock import patch
from pathlib import Path
import argparse
import psycopg2
import pytest
import requests


def main(report_dir="reports/geri_lab/step2"):
    Path(report_dir).mkdir(parents=True, exist_ok=True)
    original_connect = psycopg2.connect
    original_request = requests.sessions.Session.request
    client = None

    def readonly_connect(*args, **kwargs):
        kwargs["options"] = kwargs.get("options", "") + " -c default_transaction_read_only=on"
        return original_connect(*args, **kwargs)

    def isolated_request(session, method, url, **kwargs):
        nonlocal client
        if url.startswith("http://localhost:5000/api/v1/indices/egsi-m"):
            if client is None:
                from fastapi import FastAPI
                from fastapi.testclient import TestClient
                from src.egsi.routes import router
                api = FastAPI()
                api.include_router(router)
                client = TestClient(api)
            kwargs.pop("timeout", None)
            return client.request(method, url.replace("http://localhost:5000", ""), **kwargs)
        return original_request(session, method, url, **kwargs)

    with patch("psycopg2.connect", side_effect=readonly_connect), \
         patch("socket.socket.connect", side_effect=RuntimeError("Outbound network disabled in test suite")), \
         patch("requests.sessions.Session.request", isolated_request):
        return pytest.main([
            "tests", "src", "scripts/geri_lab", "-q", "-p", "no:cacheprovider",
            f"--junitxml={report_dir}/full_tests_final.xml",
        ])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", default="reports/geri_lab/step2")
    raise SystemExit(main(parser.parse_args().report_dir))
