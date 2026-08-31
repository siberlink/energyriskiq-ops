#!/usr/bin/env python3
"""Run one production background job from a Replit Scheduled Deployment.

The scheduled deployment is intentionally a thin HTTP client. The API remains
the single owner of business logic, authentication, advisory locks, and
idempotency.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class Job:
    path: str
    params: tuple[tuple[str, str], ...] = ()
    timeout: int = 480


JOBS = {
    "intraday": Job(
        path="/internal/run/intraday-price-capture",
        timeout=60,
    ),
    "ingestion": Job(
        path="/internal/run/ingestion-pipeline",
        params=(("skip_ai", "false"), ("skip_risk", "false")),
        timeout=1500,
    ),
    "metadata": Job(
        path="/internal/backfill-alert-metadata",
        params=(("dry_run", "false"),),
        timeout=480,
    ),
    "daily": Job(
        path="/internal/run/daily-index-pipeline",
        params=(("include_delivery", "true"),),
        timeout=2250,
    ),
}

ALERTS_JOB = Job(
    path="/internal/run/alerts",
    params=(
        ("phase", "all"),
        ("dry_run", "false"),
        ("since_hours", "24"),
        ("batch_size", "200"),
        ("skip_preflight", "false"),
    ),
    timeout=480,
)

DELIVERY_JOBS = (
    (
        "pro_delivery",
        Job(
            path="/internal/run/pro-delivery",
            params=(("since_minutes", "15"), ("include_geri", "true")),
            timeout=90,
        ),
    ),
    (
        "trader_delivery",
        Job(
            path="/internal/run/trader-delivery",
            params=(("since_minutes", "30"),),
            timeout=90,
        ),
    ),
)


def _configuration() -> tuple[str, str]:
    app_url = os.environ.get("APP_URL", "").strip().rstrip("/")
    token = os.environ.get("INTERNAL_RUNNER_TOKEN", "")
    missing = [
        name
        for name, value in (
            ("APP_URL", app_url),
            ("INTERNAL_RUNNER_TOKEN", token),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(
            "Missing scheduled-job configuration: " + ", ".join(missing)
        )
    return app_url, token


def _request(app_url: str, token: str, job: Job) -> tuple[int, dict[str, Any]]:
    query = urlencode(job.params)
    url = f"{app_url}{job.path}"
    if query:
        url = f"{url}?{query}"

    request = Request(
        url,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Runner-Token": token,
        },
        data=b"",
    )
    try:
        with urlopen(request, timeout=job.timeout) as response:
            status = response.status
            body = response.read().decode("utf-8")
    except HTTPError as error:
        status = error.code
        body = error.read().decode("utf-8", errors="replace")
    except (TimeoutError, URLError) as error:
        raise RuntimeError(f"Request to {job.path} failed: {error}") from error

    try:
        payload = json.loads(body) if body else {}
    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"{job.path} returned non-JSON HTTP {status}: {body[:300]}"
        ) from error

    if not isinstance(payload, dict):
        raise RuntimeError(f"{job.path} returned an invalid response")
    return status, payload


def _run_one(app_url: str, token: str, name: str, job: Job) -> int:
    status, payload = _request(app_url, token, job)
    print(json.dumps({"job": name, "http_status": status, "response": payload}, sort_keys=True))

    if status == 409:
        print(f"{name}: busy; the protected job is already running")
        return status
    if status != 200:
        raise RuntimeError(f"{name} returned HTTP {status}")
    if payload.get("status") in {"error", "failed"}:
        raise RuntimeError(f"{name} reported failure: {payload}")
    return status


def run_job(name: str) -> None:
    app_url, token = _configuration()
    if name == "alerts":
        alert_status = _run_one(app_url, token, name, ALERTS_JOB)
        if alert_status == 409:
            return
        for delivery_name, delivery_job in DELIVERY_JOBS:
            _run_one(app_url, token, delivery_name, delivery_job)
        return

    _run_one(app_url, token, name, JOBS[name])


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a Replit scheduled production job")
    parser.add_argument(
        "--job",
        choices=("alerts", *JOBS),
        required=True,
        help="Job to invoke through the protected application API",
    )
    args = parser.parse_args()
    try:
        run_job(args.job)
    except RuntimeError as error:
        print(f"scheduled job failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())