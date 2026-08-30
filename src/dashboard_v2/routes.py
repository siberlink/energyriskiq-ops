"""Dashboard V2 HTTP boundary and additive persistence."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Optional

import psycopg2
from fastapi import APIRouter, Cookie, Header, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel

from src.db.db import get_cursor
from src.dashboard_v2.services import (
    bootstrap,
    build_snapshot,
    activate_welcome,
    mark_routine_step,
    require_v2_access,
    routine_state,
)
from src.api.user_routes import verify_user_session

logger = logging.getLogger(__name__)
router = APIRouter(tags=["dashboard-v2"])

V2_DDL = """
CREATE TABLE IF NOT EXISTS dashboard_v2_feature_flags (
    flag_key TEXT PRIMARY KEY,
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS dashboard_v2_experiences (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    experience_type TEXT NOT NULL CHECK (experience_type IN ('WELCOME','MIGRATION')),
    status TEXT NOT NULL CHECK (status IN ('ELIGIBLE','ACTIVE','EXPIRED','DISMISSED','CLAIM_WINDOW_EXPIRED')),
    claim_deadline TIMESTAMP NULL,
    started_at TIMESTAMP NULL,
    ends_at TIMESTAMP NULL,
    dismissed_at TIMESTAMP NULL,
    activation_trigger TEXT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS dashboard_v2_grants (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    capability TEXT NOT NULL,
    source TEXT NOT NULL,
    starts_at TIMESTAMP NOT NULL,
    ends_at TIMESTAMP NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    revoked_at TIMESTAMP NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_dashboard_v2_grants_active
    ON dashboard_v2_grants(user_id, capability, ends_at);
CREATE TABLE IF NOT EXISTS dashboard_v2_routine_progress (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    snapshot_id TEXT NOT NULL,
    step_key TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    available BOOLEAN NOT NULL DEFAULT TRUE,
    viewed_at TIMESTAMP NULL,
    completed_at TIMESTAMP NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (user_id, snapshot_id, step_key)
);
CREATE TABLE IF NOT EXISTS dashboard_v2_events (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NULL REFERENCES users(id) ON DELETE SET NULL,
    event_name TEXT NOT NULL,
    event_envelope JSONB NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_dashboard_v2_events_user_time
    ON dashboard_v2_events(user_id, created_at DESC);
CREATE TABLE IF NOT EXISTS dashboard_v2_entitlement_cache (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    entitlement_snapshot JSONB NOT NULL,
    verified_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
"""

V2_FLAGS = (
    ("dashboard_v2_enabled", True),
    ("legacy_dashboard_override", False),
    ("routine_enabled", True),
    ("welcome_experience_enabled", True),
    ("migration_experience_enabled", False),
    ("intelligence_bundle_checkout_enabled", False),
    ("newsletter_context_enabled", False),
    ("internal_widgets_enabled", True),
    ("offer_rules_enabled", True),
)


def _apply_v2_schema(cursor) -> None:
    for statement in V2_DDL.split(";"):
        if statement.strip():
            cursor.execute(statement)
    for key, enabled in V2_FLAGS:
        cursor.execute(
            """
            INSERT INTO dashboard_v2_feature_flags(flag_key, enabled)
            VALUES (%s, %s)
            ON CONFLICT (flag_key) DO NOTHING
            """,
            (key, enabled),
        )


def run_dashboard_v2_migration() -> None:
    """Apply additive V2 schema to Neon and mirror it to managed DB."""
    with get_cursor() as cursor:
        _apply_v2_schema(cursor)

    production = os.environ.get("PRODUCTION_DATABASE_URL")
    managed = os.environ.get("DATABASE_URL")
    if not managed or not production or managed == production:
        return
    connection = None
    try:
        connection = psycopg2.connect(managed)
        with connection.cursor() as cursor:
            _apply_v2_schema(cursor)
        connection.commit()
    except Exception as exc:
        if connection:
            connection.rollback()
        logger.warning("Managed database V2 schema mirror skipped: %s", exc)
    finally:
        if connection:
            connection.close()


def _session_user(
    x_user_token: Optional[str], v2_session: Optional[str]
) -> dict:
    token = x_user_token or v2_session
    session = verify_user_session(token)
    user = require_v2_access(session["user_id"])
    return user


def _optional_session_user(
    x_user_token: Optional[str], v2_session: Optional[str]
) -> Optional[dict]:
    try:
        return _session_user(x_user_token, v2_session)
    except HTTPException:
        return None


class RoutineStepRequest(BaseModel):
    step_key: str
    snapshot_id: str
    complete: bool = False


class IntentRequest(BaseModel):
    intent: str = "routine_start"
    capability: Optional[str] = None


@router.get("/dashboard", include_in_schema=False)
def dashboard_v2_page(
    x_user_token: Optional[str] = Header(None),
    v2_session: Optional[str] = Cookie(None),
):
    # Never return the V2 shell to unauthenticated or non-allowlisted users.
    if not _optional_session_user(x_user_token, v2_session):
        return RedirectResponse("/users?next=/dashboard", status_code=303)
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "static",
        "dashboard-v2.html",
    )
    return FileResponse(path, media_type="text/html", headers={"Cache-Control": "no-store"})


@router.get("/api/dashboard/v2/bootstrap")
def dashboard_v2_bootstrap(
    x_user_token: Optional[str] = Header(None),
    v2_session: Optional[str] = Cookie(None),
):
    user = _session_user(x_user_token, v2_session)
    return bootstrap(user["id"])


@router.get("/api/dashboard/v2/routine")
def dashboard_v2_routine(
    x_user_token: Optional[str] = Header(None),
    v2_session: Optional[str] = Cookie(None),
):
    user = _session_user(x_user_token, v2_session)
    snapshot = build_snapshot()
    return routine_state(user["id"], snapshot)


@router.post("/api/dashboard/v2/intent")
def dashboard_v2_intent(
    body: IntentRequest,
    x_user_token: Optional[str] = Header(None),
    v2_session: Optional[str] = Cookie(None),
):
    user = _session_user(x_user_token, v2_session)
    if body.intent == "routine_start" or body.capability in {
        "intraday_risk", "dir_full", "brent_forecast",
        "widget_wti_internal", "widget_lng_internal", "widget_storage_internal",
    }:
        experience = activate_welcome(user["id"], body.intent)
        return {"success": True, "experience": experience}
    return {"success": True, "experience": None}


@router.post("/api/dashboard/v2/routine/step")
def dashboard_v2_routine_step(
    body: RoutineStepRequest,
    x_user_token: Optional[str] = Header(None),
    v2_session: Optional[str] = Cookie(None),
):
    user = _session_user(x_user_token, v2_session)
    result = mark_routine_step(
        user["id"], body.step_key, body.snapshot_id, body.complete
    )
    return {"success": True, "progress": result}
