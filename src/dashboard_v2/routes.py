"""Dashboard V2 HTTP boundary and additive persistence."""

from __future__ import annotations

import json
import logging
import os
import secrets
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
    routine_started,
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
CREATE TABLE IF NOT EXISTS dashboard_v2_newsletter_editions (
    edition_slug TEXT PRIMARY KEY,
    topic TEXT NOT NULL,
    entry_step TEXT NOT NULL CHECK (entry_step IN ('risk','change','confirm','interpret','watch')),
    featured_product TEXT NULL,
    companion_content JSONB NOT NULL DEFAULT '{}'::jsonb,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS dashboard_v2_newsletter_context (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NULL REFERENCES users(id) ON DELETE CASCADE,
    visitor_id TEXT NULL,
    edition_slug TEXT NOT NULL,
    context JSONB NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_dashboard_v2_newsletter_context_visitor
    ON dashboard_v2_newsletter_context(visitor_id) WHERE visitor_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_dashboard_v2_newsletter_context_user
    ON dashboard_v2_newsletter_context(user_id, expires_at DESC);
CREATE TABLE IF NOT EXISTS dashboard_v2_offer_dismissals (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    offer_key TEXT NOT NULL,
    dismissed_until TIMESTAMP NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, offer_key)
);
CREATE TABLE IF NOT EXISTS dashboard_v2_visits (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    snapshot_id TEXT NOT NULL,
    first_seen_at TIMESTAMP NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, snapshot_id)
);
CREATE TABLE IF NOT EXISTS dashboard_v2_subscription_mirror (
    stripe_subscription_id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    product_code TEXT NOT NULL,
    stripe_mode TEXT NOT NULL DEFAULT 'live',
    stripe_price_id TEXT NULL,
    stripe_status TEXT NOT NULL,
    current_period_end TIMESTAMP NULL,
    grace_until TIMESTAMP NULL,
    raw_event JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
ALTER TABLE dashboard_v2_subscription_mirror
    ADD COLUMN IF NOT EXISTS stripe_mode TEXT NOT NULL DEFAULT 'live';
ALTER TABLE dashboard_v2_subscription_mirror
    ADD COLUMN IF NOT EXISTS stripe_price_id TEXT NULL;
ALTER TABLE dashboard_v2_subscription_mirror
    ADD COLUMN IF NOT EXISTS grace_until TIMESTAMP NULL;
CREATE TABLE IF NOT EXISTS dashboard_v2_product_catalog (
    product_code TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    price_eur_cents INTEGER NOT NULL,
    capabilities JSONB NOT NULL,
    stripe_product_id_live TEXT NULL,
    stripe_price_id_live TEXT NULL,
    stripe_product_id_sandbox TEXT NULL,
    stripe_price_id_sandbox TEXT NULL,
    active BOOLEAN NOT NULL DEFAULT FALSE,
    protected BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS dashboard_v2_catalog_prices (
    stripe_price_id TEXT PRIMARY KEY,
    product_code TEXT NOT NULL REFERENCES dashboard_v2_product_catalog(product_code),
    stripe_mode TEXT NOT NULL CHECK (stripe_mode IN ('live','sandbox')),
    active_for_checkout BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    retired_at TIMESTAMP NULL
);
CREATE TABLE IF NOT EXISTS dashboard_v2_billing_transitions (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source_product TEXT NOT NULL,
    target_product TEXT NOT NULL,
    stripe_subscription_id TEXT NOT NULL,
    stripe_mode TEXT NOT NULL,
    status TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS dashboard_v2_audit_log (
    id BIGSERIAL PRIMARY KEY, actor_user_id INTEGER NULL, action TEXT NOT NULL,
    target_user_id INTEGER NULL, reason TEXT NOT NULL, details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
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
    products = (
        ("intelligence_bundle", "EnergyRiskIQ Intelligence Bundle", 2900,
         ["intraday_risk", "dir_full", "brent_forecast"]),
        ("widget_wti", "WTI Intelligence Widget", 495,
         ["widget_wti_internal", "widget_wti_embed"]),
        ("widget_lng", "LNG Intelligence Widget", 495,
         ["widget_lng_internal", "widget_lng_embed"]),
        ("widget_storage", "Gas Storage Intelligence Widget", 495,
         ["widget_storage_internal", "widget_storage_embed"]),
    )
    for code, name, cents, capabilities in products:
        cursor.execute(
            """
            INSERT INTO dashboard_v2_product_catalog
              (product_code, display_name, price_eur_cents, capabilities)
            VALUES (%s, %s, %s, %s::jsonb)
            ON CONFLICT (product_code) DO UPDATE SET
              display_name = EXCLUDED.display_name,
              price_eur_cents = EXCLUDED.price_eur_cents,
              capabilities = EXCLUDED.capabilities
            """,
            (code, name, cents, json.dumps(capabilities)),
        )
    cursor.execute(
        """INSERT INTO dashboard_v2_catalog_prices
             (stripe_price_id,product_code,stripe_mode,active_for_checkout)
           SELECT stripe_price_id_live,product_code,'live',TRUE
           FROM dashboard_v2_product_catalog WHERE stripe_price_id_live IS NOT NULL
           ON CONFLICT(stripe_price_id) DO NOTHING"""
    )
    cursor.execute(
        """INSERT INTO dashboard_v2_catalog_prices
             (stripe_price_id,product_code,stripe_mode,active_for_checkout)
           SELECT stripe_price_id_sandbox,product_code,'sandbox',TRUE
           FROM dashboard_v2_product_catalog WHERE stripe_price_id_sandbox IS NOT NULL
           ON CONFLICT(stripe_price_id) DO NOTHING"""
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
    complete: bool = False


class IntentRequest(BaseModel):
    intent: str = "routine_start"
    capability: Optional[str] = None


class EventRequest(BaseModel):
    event_name: str
    category: str = "analytics"
    payload: dict = {}


class OfferDismissRequest(BaseModel):
    offer_key: str


class MigrationRequest(BaseModel):
    action: str


class CheckoutRequest(BaseModel):
    product_code: str


class AdminFlagRequest(BaseModel):
    enabled: bool
    reason: str


class AdminCatalogRequest(BaseModel):
    stripe_product_id: Optional[str] = None
    stripe_price_id: Optional[str] = None
    active: bool = False
    reason: str


class AdminEditionRequest(BaseModel):
    edition_slug: str
    topic: str
    entry_step: str
    featured_product: Optional[str] = None
    companion_content: dict = {}
    active: bool = True
    reason: str


class AdminMigrationEligibilityRequest(BaseModel):
    user_id: int
    reason: str


@router.get("/dashboard", include_in_schema=False)
def dashboard_v2_page(
    x_user_token: Optional[str] = Header(None),
    v2_session: Optional[str] = Cookie(None),
):
    # Never return the V2 shell to unauthenticated or non-allowlisted users.
    from src.dashboard_v2.services import feature_enabled
    if feature_enabled("legacy_dashboard_override"):
        return RedirectResponse("/users/account", status_code=303)
    if not _optional_session_user(x_user_token, v2_session):
        return RedirectResponse("/users?next=/dashboard", status_code=303)
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "static",
        "dashboard-v2.html",
    )
    return FileResponse(path, media_type="text/html", headers={"Cache-Control": "no-store"})


@router.get("/dashboard/{dashboard_path:path}", include_in_schema=False)
def dashboard_v2_subpage(
    dashboard_path: str,
    x_user_token: Optional[str] = Header(None),
    v2_session: Optional[str] = Cookie(None),
):
    return dashboard_v2_page(x_user_token, v2_session)


@router.get("/api/dashboard/v2/bootstrap")
def dashboard_v2_bootstrap(
    request: Request,
    x_user_token: Optional[str] = Header(None),
    v2_session: Optional[str] = Cookie(None),
):
    user = _session_user(x_user_token, v2_session)
    return bootstrap(user["id"], request.cookies.get("dashboard_v2_newsletter"))


@router.get("/n/{edition_slug}", include_in_schema=False)
def dashboard_v2_newsletter_entry(edition_slug: str):
    """Public deep-link entry preserves an opaque, expiring context for 24h.

    The authenticated bootstrap re-resolves the slug against editorial mapping;
    query strings consequently cannot select capabilities or routine progress.
    """
    token = secrets.token_urlsafe(32)
    edition = None
    from src.dashboard_v2.services import feature_enabled
    if feature_enabled("newsletter_context_enabled") and len(edition_slug) <= 120:
        with get_cursor(commit=False) as cursor:
            cursor.execute(
                """SELECT edition_slug, topic, entry_step, featured_product, companion_content
                   FROM dashboard_v2_newsletter_editions
                   WHERE edition_slug=%s AND active=TRUE""",
                (edition_slug,),
            )
            edition = cursor.fetchone()
    response = RedirectResponse("/dashboard", status_code=303)
    if not edition:
        response.delete_cookie("dashboard_v2_newsletter", path="/")
        return response
    with get_cursor() as cursor:
        cursor.execute(
            """INSERT INTO dashboard_v2_newsletter_context
                 (visitor_id,edition_slug,context,expires_at)
               VALUES(%s,%s,%s::jsonb,NOW() + INTERVAL '24 hours')""",
            (token, edition_slug, json.dumps(dict(edition), default=str)),
        )
    response.set_cookie(
        "dashboard_v2_newsletter", token, max_age=24 * 60 * 60,
        httponly=True, secure=True, samesite="lax", path="/",
    )
    return response


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
    from src.dashboard_v2.services import PREMIUM_INTENT_CAPABILITIES, record_event
    if body.intent == "routine_start" or body.capability in PREMIUM_INTENT_CAPABILITIES:
        experience = activate_welcome(user["id"], body.intent)
        snapshot_id = (
            build_snapshot()["snapshot_id"]
            if body.intent == "routine_start"
            else None
        )
        record_event(
            user["id"],
            "routine_started" if body.intent == "routine_start" else "premium_intent",
            "essential",
            {
                "capability": body.capability,
                "intent": body.intent,
                "snapshot_id": snapshot_id,
            },
            True,
        )
        return {"success": True, "experience": experience}
    return {"success": True, "experience": None}


@router.post("/api/dashboard/v2/routine/step")
def dashboard_v2_routine_step(
    body: RoutineStepRequest,
    x_user_token: Optional[str] = Header(None),
    v2_session: Optional[str] = Cookie(None),
):
    user = _session_user(x_user_token, v2_session)
    snapshot = build_snapshot()
    if not routine_started(user["id"], snapshot["snapshot_id"]):
        raise HTTPException(status_code=409, detail="Start today’s Routine first")
    result = mark_routine_step(
        user["id"], body.step_key, snapshot, body.complete
    )
    return {"success": True, "progress": result}


@router.get("/api/intelligence/{resource}")
def dashboard_v2_intelligence(
    resource: str,
    x_user_token: Optional[str] = Header(None),
    v2_session: Optional[str] = Cookie(None),
):
    """Small targeted endpoint; never returns premium detail before capability verification."""
    from src.dashboard_v2.services import targeted_intelligence
    user = _session_user(x_user_token, v2_session)
    return targeted_intelligence(user["id"], resource)


@router.post("/api/dashboard/v2/events")
def dashboard_v2_event(
    body: EventRequest,
    request: Request,
    x_user_token: Optional[str] = Header(None),
    v2_session: Optional[str] = Cookie(None),
):
    from src.dashboard_v2.services import record_event
    user = _session_user(x_user_token, v2_session)
    # Consent is supplied by the established cookie layer, never trusted from the
    # event payload.  Missing consent fails closed for non-essential analytics.
    consent = request.cookies.get("analytics_consent") == "granted"
    record_event(user["id"], body.event_name, body.category, body.payload, consent)
    return {"accepted": True}


@router.post("/api/dashboard/v2/offers/dismiss")
def dashboard_v2_dismiss_offer(
    body: OfferDismissRequest,
    x_user_token: Optional[str] = Header(None),
    v2_session: Optional[str] = Cookie(None),
):
    from src.dashboard_v2.services import dismiss_offer
    user = _session_user(x_user_token, v2_session)
    dismiss_offer(user["id"], body.offer_key)
    return {"success": True}


@router.get("/api/dashboard/v2/catalog")
def dashboard_v2_catalog(
    x_user_token: Optional[str] = Header(None),
    v2_session: Optional[str] = Cookie(None),
):
    _session_user(x_user_token, v2_session)
    from src.dashboard_v2.services import public_catalog
    return {"products": public_catalog()}


@router.post("/api/dashboard/v2/checkout")
async def dashboard_v2_checkout(
    body: CheckoutRequest,
    x_user_token: Optional[str] = Header(None),
    v2_session: Optional[str] = Cookie(None),
):
    from src.dashboard_v2.services import create_v2_checkout
    user = _session_user(x_user_token, v2_session)
    return await create_v2_checkout(user, body.product_code)


@router.post("/api/dashboard/v2/migration")
def dashboard_v2_migration(
    body: MigrationRequest,
    x_user_token: Optional[str] = Header(None),
    v2_session: Optional[str] = Cookie(None),
):
    from src.dashboard_v2.services import activate_migration, dismiss_migration
    user = _session_user(x_user_token, v2_session)
    if body.action == "activate":
        return {"success": True, "experience": activate_migration(user["id"])}
    if body.action == "dismiss":
        dismiss_migration(user["id"])
        return {"success": True}
    raise HTTPException(status_code=400, detail="Unknown migration action")


def _admin(x_admin_token: Optional[str]) -> None:
    from src.api.admin_routes import verify_admin_token
    verify_admin_token(x_admin_token)


def _audit(action: str, reason: str, details: dict, target_user_id: Optional[int] = None) -> None:
    if not reason.strip():
        raise HTTPException(status_code=400, detail="A reason is required")
    with get_cursor() as cursor:
        cursor.execute(
            """INSERT INTO dashboard_v2_audit_log(action,target_user_id,reason,details)
               VALUES(%s,%s,%s,%s::jsonb)""",
            (action, target_user_id, reason.strip()[:500], json.dumps(details)),
        )


@router.get("/api/admin/dashboard-v2")
def dashboard_v2_admin_status(x_admin_token: Optional[str] = Header(None)):
    _admin(x_admin_token)
    with get_cursor(commit=False) as cursor:
        cursor.execute("SELECT flag_key, enabled, updated_at FROM dashboard_v2_feature_flags ORDER BY flag_key")
        flags = [dict(row) for row in cursor.fetchall()]
        cursor.execute(
            """SELECT product_code, display_name, price_eur_cents, active,
                      stripe_product_id_live, stripe_price_id_live,
                      stripe_product_id_sandbox, stripe_price_id_sandbox, updated_at
               FROM dashboard_v2_product_catalog ORDER BY product_code"""
        )
        products = [dict(row) for row in cursor.fetchall()]
    return {"flags": flags, "products": products}


@router.put("/api/admin/dashboard-v2/flags/{flag_key}")
def dashboard_v2_admin_flag(
    flag_key: str,
    body: AdminFlagRequest,
    x_admin_token: Optional[str] = Header(None),
):
    _admin(x_admin_token)
    allowed = {key for key, _ in V2_FLAGS}
    if flag_key not in allowed:
        raise HTTPException(status_code=404, detail="Unknown V2 flag")
    with get_cursor() as cursor:
        cursor.execute(
            "UPDATE dashboard_v2_feature_flags SET enabled=%s, updated_at=NOW() WHERE flag_key=%s",
            (body.enabled, flag_key),
        )
    _audit("feature_flag_updated", body.reason, {"flag_key": flag_key, "enabled": body.enabled})
    return {"success": True}


@router.put("/api/admin/dashboard-v2/catalog/{product_code}")
def dashboard_v2_admin_catalog(
    product_code: str,
    body: AdminCatalogRequest,
    x_admin_token: Optional[str] = Header(None),
):
    _admin(x_admin_token)
    from src.billing.stripe_client import get_stripe_mode
    if product_code not in {"intelligence_bundle", "widget_wti", "widget_lng", "widget_storage"}:
        raise HTTPException(status_code=404, detail="Unknown protected product")
    mode = get_stripe_mode()
    product_column = "stripe_product_id_sandbox" if mode == "sandbox" else "stripe_product_id_live"
    price_column = "stripe_price_id_sandbox" if mode == "sandbox" else "stripe_price_id_live"
    with get_cursor() as cursor:
        cursor.execute(
            """UPDATE dashboard_v2_catalog_prices
               SET active_for_checkout=FALSE, retired_at=COALESCE(retired_at,NOW())
               WHERE product_code=%s AND stripe_mode=%s AND active_for_checkout=TRUE""",
            (product_code, mode),
        )
        cursor.execute(
            f"""UPDATE dashboard_v2_product_catalog
                SET {product_column}=%s, {price_column}=%s, active=%s, updated_at=NOW()
                WHERE product_code=%s""",
            (body.stripe_product_id, body.stripe_price_id, body.active, product_code),
        )
        if body.stripe_price_id:
            cursor.execute(
                """INSERT INTO dashboard_v2_catalog_prices
                     (stripe_price_id,product_code,stripe_mode,active_for_checkout,retired_at)
                   VALUES(%s,%s,%s,%s,NULL)
                   ON CONFLICT(stripe_price_id) DO UPDATE SET
                     active_for_checkout=EXCLUDED.active_for_checkout,
                     retired_at=NULL""",
                (body.stripe_price_id, product_code, mode, body.active),
            )
    _audit("catalog_updated", body.reason, {"product_code": product_code, "mode": mode, "active": body.active})
    return {"success": True, "mode": mode}


@router.put("/api/admin/dashboard-v2/newsletter-editions")
def dashboard_v2_admin_edition(
    body: AdminEditionRequest,
    x_admin_token: Optional[str] = Header(None),
):
    _admin(x_admin_token)
    if body.entry_step not in {"risk", "change", "confirm", "interpret", "watch"}:
        raise HTTPException(status_code=400, detail="Unknown entry step")
    if body.featured_product and body.featured_product not in {
        "intelligence_bundle", "widget_wti", "widget_lng", "widget_storage"
    }:
        raise HTTPException(status_code=400, detail="Unknown featured product")
    slug = body.edition_slug.strip().lower()
    if not slug or len(slug) > 120 or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for c in slug):
        raise HTTPException(status_code=400, detail="Invalid edition slug")
    with get_cursor() as cursor:
        cursor.execute(
            """INSERT INTO dashboard_v2_newsletter_editions
                 (edition_slug,topic,entry_step,featured_product,companion_content,active,updated_at)
               VALUES(%s,%s,%s,%s,%s::jsonb,%s,NOW())
               ON CONFLICT(edition_slug) DO UPDATE SET topic=EXCLUDED.topic,
                 entry_step=EXCLUDED.entry_step, featured_product=EXCLUDED.featured_product,
                 companion_content=EXCLUDED.companion_content, active=EXCLUDED.active, updated_at=NOW()""",
            (slug, body.topic[:200], body.entry_step, body.featured_product,
             json.dumps(body.companion_content), body.active),
        )
    _audit("newsletter_edition_upserted", body.reason, {"edition_slug": slug, "active": body.active})
    return {"success": True, "edition_slug": slug}


@router.post("/api/admin/dashboard-v2/migration-eligibility")
def dashboard_v2_admin_migration_eligibility(
    body: AdminMigrationEligibilityRequest,
    x_admin_token: Optional[str] = Header(None),
):
    _admin(x_admin_token)
    with get_cursor() as cursor:
        cursor.execute(
            """INSERT INTO dashboard_v2_experiences
                 (user_id,experience_type,status,claim_deadline)
               VALUES(%s,'MIGRATION','ELIGIBLE',NOW() + INTERVAL '14 days')
               ON CONFLICT(user_id) DO NOTHING""",
            (body.user_id,),
        )
        created = cursor.rowcount == 1
    _audit("migration_eligibility_created", body.reason, {"created": created}, body.user_id)
    return {"success": True, "created": created}
