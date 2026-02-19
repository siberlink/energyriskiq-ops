import os
import secrets
import hashlib
import time
import logging
from fastapi import APIRouter, HTTPException, Header
from typing import Optional, List
from pydantic import BaseModel

from src.plans.plan_helpers import (
    get_plan_settings,
    get_all_plan_settings,
    update_plan_settings,
    VALID_PLAN_CODES,
    ALL_ALERT_TYPES
)
from src.db.db import get_cursor
from src.billing.stripe_client import get_stripe_mode, set_stripe_mode, get_free_trial_days, set_free_trial_days, get_banner_settings, set_banner_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN") or os.environ.get("INTERNAL_RUNNER_TOKEN")

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "emicon")
ADMIN_PASSWORD_HASH = os.environ.get("ADMIN_PASSWORD_HASH") or hashlib.sha256(
    os.environ.get("ADMIN_PASSWORD", "Regen@3010").encode()
).hexdigest()
ADMIN_PIN = os.environ.get("ADMIN_PIN", "342256")

SESSION_DURATION = 60 * 60


def _init_admin_sessions_table():
    try:
        with get_cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS admin_sessions (
                    token VARCHAR(64) PRIMARY KEY,
                    username VARCHAR(100) NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    expires_at TIMESTAMPTZ NOT NULL
                )
            """)
    except Exception as e:
        logger.warning(f"Could not create admin_sessions table: {e}")


def _db_session_valid(token: str) -> bool:
    try:
        with get_cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM admin_sessions WHERE token = %s AND expires_at > NOW()",
                (token,)
            )
            return cursor.fetchone() is not None
    except Exception:
        return False


def _db_session_create(token: str, username: str):
    try:
        with get_cursor() as cursor:
            cursor.execute(
                "INSERT INTO admin_sessions (token, username, expires_at) VALUES (%s, %s, NOW() + INTERVAL '%s seconds') ON CONFLICT (token) DO NOTHING",
                (token, username, SESSION_DURATION)
            )
    except Exception as e:
        logger.warning(f"Could not create admin session: {e}")


def _db_session_delete(token: str):
    try:
        with get_cursor() as cursor:
            cursor.execute("DELETE FROM admin_sessions WHERE token = %s", (token,))
    except Exception:
        pass


def _db_session_cleanup():
    try:
        with get_cursor() as cursor:
            cursor.execute("DELETE FROM admin_sessions WHERE expires_at < NOW()")
    except Exception:
        pass


class LoginRequest(BaseModel):
    username: str
    password: str
    pin: str


def verify_admin_token(x_admin_token: Optional[str] = Header(None)):
    if x_admin_token and _db_session_valid(x_admin_token):
        return True

    if ADMIN_TOKEN and x_admin_token == ADMIN_TOKEN:
        return True

    raise HTTPException(status_code=401, detail="Invalid or expired session")


@router.post("/login")
def admin_login(body: LoginRequest):
    password_hash = hashlib.sha256(body.password.encode()).hexdigest()

    if (body.username == ADMIN_USERNAME and
        password_hash == ADMIN_PASSWORD_HASH and
        body.pin == ADMIN_PIN):

        session_token = secrets.token_urlsafe(32)
        _db_session_create(session_token, body.username)
        _db_session_cleanup()

        return {
            "success": True,
            "token": session_token,
            "expires_in": SESSION_DURATION
        }

    raise HTTPException(status_code=401, detail="Invalid credentials")


@router.post("/logout")
def admin_logout(x_admin_token: Optional[str] = Header(None)):
    if x_admin_token:
        _db_session_delete(x_admin_token)
    return {"success": True}


class PlanSettingsUpdate(BaseModel):
    monthly_price_usd: Optional[float] = None
    allowed_alert_types: Optional[List[str]] = None
    max_email_alerts_per_day: Optional[int] = None
    delivery_config: Optional[dict] = None
    is_active: Optional[bool] = None


@router.get("/plan-settings")
def list_plan_settings(x_admin_token: Optional[str] = Header(None)):
    verify_admin_token(x_admin_token)
    
    try:
        settings = get_all_plan_settings()
        return {
            "plans": settings,
            "valid_plan_codes": VALID_PLAN_CODES,
            "supported_alert_types": ALL_ALERT_TYPES
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/plan-settings/{plan_code}")
def get_single_plan_settings(plan_code: str, x_admin_token: Optional[str] = Header(None)):
    verify_admin_token(x_admin_token)
    
    if plan_code not in VALID_PLAN_CODES:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid plan_code: {plan_code}. Must be one of: {VALID_PLAN_CODES}"
        )
    
    try:
        settings = get_plan_settings(plan_code)
        return settings
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/plan-settings/{plan_code}")
def update_single_plan_settings(
    plan_code: str, 
    body: PlanSettingsUpdate,
    x_admin_token: Optional[str] = Header(None)
):
    verify_admin_token(x_admin_token)
    
    if plan_code not in VALID_PLAN_CODES:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid plan_code: {plan_code}. Must be one of: {VALID_PLAN_CODES}"
        )
    
    if body.allowed_alert_types:
        for alert_type in body.allowed_alert_types:
            if alert_type != "ALL" and alert_type not in ALL_ALERT_TYPES:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid alert_type: {alert_type}. Must be one of: {ALL_ALERT_TYPES}"
                )
    
    updates = {}
    if body.monthly_price_usd is not None:
        updates["monthly_price_usd"] = body.monthly_price_usd
    if body.allowed_alert_types is not None:
        updates["allowed_alert_types"] = body.allowed_alert_types
    if body.max_email_alerts_per_day is not None:
        updates["max_email_alerts_per_day"] = body.max_email_alerts_per_day
    if body.delivery_config is not None:
        updates["delivery_config"] = body.delivery_config
    if body.is_active is not None:
        updates["is_active"] = body.is_active
    
    try:
        updated = update_plan_settings(plan_code, updates)
        return {
            "message": f"Plan settings for '{plan_code}' updated successfully",
            "plan": updated
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class StripeModeUpdate(BaseModel):
    mode: str


class SandboxIdsUpdate(BaseModel):
    product_id: Optional[str] = None
    price_id: Optional[str] = None


@router.get("/stripe-mode")
def get_stripe_mode_status(x_admin_token: Optional[str] = Header(None)):
    verify_admin_token(x_admin_token)
    mode = get_stripe_mode()

    live_configured = bool(os.environ.get("STRIPE_SECRET_KEY") and os.environ.get("STRIPE_PUBLISHABLE_KEY"))
    sandbox_configured = bool(os.environ.get("STRIPE_SANDBOX_SECRET_KEY") and os.environ.get("STRIPE_SANDBOX_PUBLISHABLE_KEY"))
    live_webhook = bool(os.environ.get("STRIPE_WEBHOOK_SECRET"))
    sandbox_webhook = bool(os.environ.get("STRIPE_SANDBOX_WEBHOOK_SECRET"))

    with get_cursor(commit=False) as cursor:
        cursor.execute("""
            SELECT plan_code, display_name,
                   stripe_product_id, stripe_price_id,
                   stripe_product_id_sandbox, stripe_price_id_sandbox
            FROM plan_settings
            WHERE plan_code != 'free'
            ORDER BY monthly_price_usd ASC
        """)
        plans = cursor.fetchall()

    return {
        "mode": mode,
        "live": {
            "keys_configured": live_configured,
            "webhook_configured": live_webhook
        },
        "sandbox": {
            "keys_configured": sandbox_configured,
            "webhook_configured": sandbox_webhook
        },
        "plans": [
            {
                "plan_code": p["plan_code"],
                "display_name": p["display_name"],
                "live_product_id": p["stripe_product_id"] or "",
                "live_price_id": p["stripe_price_id"] or "",
                "sandbox_product_id": p["stripe_product_id_sandbox"] or "",
                "sandbox_price_id": p["stripe_price_id_sandbox"] or ""
            }
            for p in plans
        ]
    }


@router.put("/stripe-mode")
def update_stripe_mode(body: StripeModeUpdate, x_admin_token: Optional[str] = Header(None)):
    verify_admin_token(x_admin_token)

    if body.mode not in ("live", "sandbox"):
        raise HTTPException(status_code=400, detail="Mode must be 'live' or 'sandbox'")

    if body.mode == "sandbox":
        if not os.environ.get("STRIPE_SANDBOX_SECRET_KEY") or not os.environ.get("STRIPE_SANDBOX_PUBLISHABLE_KEY"):
            raise HTTPException(status_code=400, detail="Sandbox keys not configured")

    try:
        set_stripe_mode(body.mode)
        return {"success": True, "mode": body.mode, "message": f"Stripe mode switched to {body.mode}"}
    except Exception as e:
        logger.error(f"Failed to switch Stripe mode: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/stripe-sandbox-ids/{plan_code}")
def update_sandbox_ids(
    plan_code: str,
    body: SandboxIdsUpdate,
    x_admin_token: Optional[str] = Header(None)
):
    verify_admin_token(x_admin_token)

    if plan_code not in VALID_PLAN_CODES or plan_code == "free":
        raise HTTPException(status_code=400, detail=f"Invalid plan_code: {plan_code}")

    updates = []
    params = []
    if body.product_id is not None:
        updates.append("stripe_product_id_sandbox = %s")
        params.append(body.product_id)
    if body.price_id is not None:
        updates.append("stripe_price_id_sandbox = %s")
        params.append(body.price_id)

    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")

    params.append(plan_code)

    try:
        with get_cursor() as cursor:
            cursor.execute(
                f"UPDATE plan_settings SET {', '.join(updates)} WHERE plan_code = %s",
                tuple(params)
            )
        return {"success": True, "message": f"Sandbox IDs updated for {plan_code}"}
    except Exception as e:
        logger.error(f"Failed to update sandbox IDs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class FreeTrialUpdate(BaseModel):
    days: int


@router.get("/free-trial")
def get_free_trial_status(x_admin_token: Optional[str] = Header(None)):
    verify_admin_token(x_admin_token)
    days = get_free_trial_days()
    return {"days": days}


@router.put("/free-trial")
def update_free_trial(body: FreeTrialUpdate, x_admin_token: Optional[str] = Header(None)):
    verify_admin_token(x_admin_token)

    if body.days not in (0, 14, 30):
        raise HTTPException(status_code=400, detail="Trial days must be 0 (disabled), 14, or 30")

    try:
        set_free_trial_days(body.days)
        label = f"{body.days}-day free trial enabled" if body.days > 0 else "Free trial disabled"
        return {"success": True, "days": body.days, "message": label}
    except Exception as e:
        logger.error(f"Failed to update free trial: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class BannerSettingsUpdate(BaseModel):
    enabled: bool
    timeframe_days: int = 0


@router.get("/banner-settings")
def get_banner_settings_endpoint(x_admin_token: Optional[str] = Header(None)):
    verify_admin_token(x_admin_token)
    settings = get_banner_settings()
    return settings


@router.put("/banner-settings")
def update_banner_settings_endpoint(body: BannerSettingsUpdate, x_admin_token: Optional[str] = Header(None)):
    verify_admin_token(x_admin_token)
    if body.timeframe_days < 0:
        raise HTTPException(status_code=400, detail="Timeframe days must be >= 0")
    try:
        result = set_banner_settings(body.enabled, body.timeframe_days)
        return {"success": True, **result}
    except Exception as e:
        logger.error(f"Failed to update banner settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))
