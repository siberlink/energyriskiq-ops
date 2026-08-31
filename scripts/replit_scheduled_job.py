#!/usr/bin/env python3
"""Run one production background job from a Replit Scheduled Deployment.

The scheduled deployment invokes the existing protected handlers directly.
That keeps business logic, authentication, advisory locks, and idempotency in
one place without sending a scheduler request through the public Cloudflare
front door.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


@dataclass(frozen=True)
class Job:
    handler_name: str


JOBS = {
    "intraday": Job(
        handler_name="run_intraday_price_capture",
    ),
    "ingestion": Job(
        handler_name="run_ingestion_pipeline",
    ),
    "metadata": Job(
        handler_name="backfill_alert_metadata_endpoint",
    ),
    "daily": Job(
        handler_name="run_daily_index_pipeline",
    ),
}

ALERTS_JOB = Job(handler_name="run_alerts")


def _configuration() -> str:
    token = os.environ.get("INTERNAL_RUNNER_TOKEN", "")
    if not token:
        raise RuntimeError("Missing scheduled-job configuration: INTERNAL_RUNNER_TOKEN")
    return token


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"{name} must be true or false")


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as error:
        raise RuntimeError(f"{name} must be an integer") from error
    if not minimum <= parsed <= maximum:
        raise RuntimeError(f"{name} must be between {minimum} and {maximum}")
    return parsed


def _handler(name: str):
    from src.api import internal_routes

    try:
        return getattr(internal_routes, name)
    except AttributeError as error:
        raise RuntimeError(f"Scheduled job handler is unavailable: {name}") from error


def _invoke(name: str, handler_name: str, token: str, **kwargs) -> int:
    handler = _handler(handler_name)
    try:
        payload = handler(x_runner_token=token, **kwargs)
        status = 200
    except HTTPException as error:
        status = error.status_code
        payload = error.detail

    if not isinstance(payload, dict):
        payload = {"detail": payload}
    print(json.dumps({"job": name, "status": status, "response": payload}, sort_keys=True))

    if status == 409:
        print(f"{name}: busy; the protected job is already running")
        return status
    if status != 200:
        raise RuntimeError(f"{name} returned HTTP {status}: {payload}")
    if payload.get("status") in {"error", "failed"}:
        raise RuntimeError(f"{name} reported failure: {payload}")
    return status


def run_job(name: str) -> None:
    token = _configuration()
    if name == "alerts":
        if not _env_bool("ALERTS_ENABLED", True):
            print(json.dumps({"job": name, "status": "disabled"}, sort_keys=True))
            return
        alert_status = _invoke(
            name,
            ALERTS_JOB.handler_name,
            token,
            phase=os.environ.get("PHASE", "all"),
            dry_run=_env_bool("DRY_RUN", False),
            since_hours=_env_int("SINCE_HOURS", 24, 1, 168),
            batch_size=_env_int("BATCH_SIZE", 200, 1, 1000),
            skip_preflight=_env_bool("SKIP_PREFLIGHT", False),
        )
        if alert_status == 409:
            return
        if not _env_bool("DRY_RUN", False):
            if _env_bool("INCLUDE_PRO_DELIVERY", True):
                _invoke(
                    "pro_delivery",
                    "run_pro_delivery",
                    token,
                )
            if _env_bool("INCLUDE_TRADER_DELIVERY", True):
                _invoke(
                    "trader_delivery",
                    "run_trader_delivery",
                    token,
                )
        return

    if name == "ingestion":
        _invoke(
            name,
            JOBS[name].handler_name,
            token,
            skip_ai=_env_bool("SKIP_AI", False),
            skip_risk=_env_bool("SKIP_RISK", False),
        )
    elif name == "metadata":
        _invoke(
            name,
            JOBS[name].handler_name,
            token,
            dry_run=_env_bool("DRY_RUN", False),
        )
    elif name == "daily":
        _invoke(
            name,
            JOBS[name].handler_name,
            token,
            include_delivery=_env_bool("INCLUDE_DELIVERY", True),
        )
    else:
        _invoke(name, JOBS[name].handler_name, token)


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