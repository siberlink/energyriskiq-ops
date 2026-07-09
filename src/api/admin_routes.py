import os
import html as _html
import secrets
import hashlib
import time
import logging
import requests
from fastapi import APIRouter, HTTPException, Header, Query, BackgroundTasks
from typing import Optional, List
from pydantic import BaseModel

from src.plans.plan_helpers import (
    get_plan_settings,
    get_all_plan_settings,
    update_plan_settings,
    apply_plan_settings_to_user,
    VALID_PLAN_CODES,
    ALL_ALERT_TYPES
)
from src.db.db import get_cursor
from src.billing.stripe_client import get_stripe_mode, set_stripe_mode, get_free_trial_days, set_free_trial_days, get_banner_settings, set_banner_settings

APP_URL = os.environ.get("APP_URL", "https://energyriskiq.replit.app")

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN") or os.environ.get("INTERNAL_RUNNER_TOKEN")

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "emicon")
ADMIN_PASSWORD_HASH = os.environ.get("ADMIN_PASSWORD_HASH") or hashlib.sha256(
    os.environ.get("ADMIN_PASSWORD", "Regen@3010").encode()
).hexdigest()
ADMIN_PIN = os.environ.get("ADMIN_PIN", "342256")

SESSION_DURATION = 24 * 60 * 60


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


_BULK_EMAIL_DDL = """
    CREATE TABLE IF NOT EXISTS admin_bulk_email_campaigns (
        id SERIAL PRIMARY KEY,
        subject TEXT NOT NULL,
        content_type TEXT NOT NULL DEFAULT 'html',
        total INTEGER NOT NULL DEFAULT 0,
        sent INTEGER NOT NULL DEFAULT 0,
        failed INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'pending',
        error TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
"""


def _init_bulk_email_table():
    """Create the bulk-email campaign progress table on the primary (Neon) DB and
    mirror it to the Replit-managed DATABASE_URL so the publish schema diff does
    not propose dropping a Neon-only table."""
    try:
        with get_cursor() as cursor:
            cursor.execute(_BULK_EMAIL_DDL)
    except Exception as e:
        logger.warning(f"Could not create admin_bulk_email_campaigns table: {e}")

    prod = os.environ.get("PRODUCTION_DATABASE_URL")
    managed = os.environ.get("DATABASE_URL")
    if not managed or not prod or managed == prod:
        return
    conn = None
    try:
        import psycopg2
        conn = psycopg2.connect(managed)
        cur = conn.cursor()
        cur.execute(_BULK_EMAIL_DDL)
        conn.commit()
        cur.close()
    except Exception as e:
        logger.warning(f"Managed DB bulk-email table sync skipped: {e}")
    finally:
        if conn:
            conn.close()


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


@router.get("/users")
def admin_list_users(
    x_admin_token: Optional[str] = Header(None),
    search: Optional[str] = Query(None),
    plan_filter: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
):
    verify_admin_token(x_admin_token)
    offset = (page - 1) * per_page
    conditions = []
    params = []

    if search:
        conditions.append("LOWER(u.email) LIKE %s")
        params.append(f"%{search.lower()}%")

    if plan_filter and plan_filter in VALID_PLAN_CODES:
        conditions.append("up.plan = %s")
        params.append(plan_filter)

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    try:
        with get_cursor(commit=False) as cur:
            cur.execute(f"""
                SELECT COUNT(*) as total
                FROM users u
                LEFT JOIN user_plans up ON u.id = up.user_id
                {where}
            """, params)
            total = cur.fetchone()["total"]

            cur.execute(f"""
                SELECT u.id, u.email, u.created_at,
                       u.subscription_status, u.last_login_at,
                       COALESCE(up.plan, 'free') as plan,
                       up.updated_at as plan_updated_at
                FROM users u
                LEFT JOIN user_plans up ON u.id = up.user_id
                {where}
                ORDER BY u.created_at DESC
                LIMIT %s OFFSET %s
            """, params + [per_page, offset])
            rows = cur.fetchall()

        users = []
        for r in rows:
            users.append({
                "id": r["id"],
                "email": r["email"],
                "plan": r["plan"],
                "subscription_status": r["subscription_status"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "plan_updated_at": r["plan_updated_at"].isoformat() if r.get("plan_updated_at") else None,
                "last_login_at": r["last_login_at"].isoformat() if r.get("last_login_at") else None,
            })

        return {
            "success": True,
            "users": users,
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": max(1, (total + per_page - 1) // per_page),
        }
    except Exception as e:
        logger.error(f"Failed to list users: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/users/{user_id}")
def admin_delete_user(user_id: int, x_admin_token: Optional[str] = Header(None)):
    """Permanently delete a user and all their data. Non-cascading tables are
    cleaned up explicitly; FK CASCADE covers sessions, plans, settings, alerts."""
    verify_admin_token(x_admin_token)
    try:
        with get_cursor() as cur:
            cur.execute("SELECT id, email FROM users WHERE id = %s", (user_id,))
            user = cur.fetchone()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            email = user["email"]

            cur.execute("DELETE FROM ticket_messages WHERE ticket_id IN (SELECT id FROM tickets WHERE user_id = %s)", (user_id,))
            for table in ("tickets", "eriq_token_ledger", "eriq_token_balances",
                          "eriq_conversations", "email_login_tokens",
                          "password_reset_tokens", "user_daily_report_subs",
                          "user_index_history_subs", "user_pro_widgets",
                          "user_activity_events"):
                cur.execute(f"DELETE FROM {table} WHERE user_id = %s", (user_id,))

            cur.execute("DELETE FROM users WHERE id = %s", (user_id,))

        logger.info(f"Admin deleted user {user_id} ({email})")
        return {"success": True, "message": f"User {email} and all associated data deleted."}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/users/{user_id}")
def admin_get_user(user_id: int, x_admin_token: Optional[str] = Header(None)):
    verify_admin_token(x_admin_token)
    try:
        with get_cursor(commit=False) as cur:
            cur.execute("""
                SELECT u.id, u.email, u.created_at,
                       u.stripe_customer_id, u.stripe_subscription_id,
                       u.subscription_status, u.subscription_current_period_end,
                       u.telegram_chat_id,
                       COALESCE(up.plan, 'free') as plan,
                       up.plan_price_usd, up.alerts_delay_minutes,
                       up.allow_asset_alerts, up.allow_telegram,
                       up.daily_digest_enabled, up.max_email_alerts_per_day,
                       up.max_total_alerts_per_day,
                       up.custom_thresholds, up.priority_processing,
                       up.created_at as plan_created_at, up.updated_at as plan_updated_at
                FROM users u
                LEFT JOIN user_plans up ON u.id = up.user_id
                WHERE u.id = %s
            """, (user_id,))
            row = cur.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="User not found")

        user = {
            "id": row["id"],
            "email": row["email"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "stripe_customer_id": row.get("stripe_customer_id"),
            "stripe_subscription_id": row.get("stripe_subscription_id"),
            "subscription_status": row.get("subscription_status"),
            "subscription_current_period_end": row["subscription_current_period_end"].isoformat() if row.get("subscription_current_period_end") else None,
            "telegram_chat_id": row.get("telegram_chat_id"),
            "plan": row["plan"],
            "plan_price_usd": float(row["plan_price_usd"]) if row.get("plan_price_usd") is not None else 0,
            "alerts_delay_minutes": row.get("alerts_delay_minutes"),
            "allow_asset_alerts": row.get("allow_asset_alerts"),
            "allow_telegram": row.get("allow_telegram"),
            "daily_digest_enabled": row.get("daily_digest_enabled"),
            "max_email_alerts_per_day": row.get("max_email_alerts_per_day"),
            "max_total_alerts_per_day": row.get("max_total_alerts_per_day"),
            "custom_thresholds": row.get("custom_thresholds"),
            "priority_processing": row.get("priority_processing"),
            "plan_created_at": row["plan_created_at"].isoformat() if row.get("plan_created_at") else None,
            "plan_updated_at": row["plan_updated_at"].isoformat() if row.get("plan_updated_at") else None,
        }
        return {"success": True, "user": user}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class AssignPlanRequest(BaseModel):
    plan_code: str


@router.put("/users/{user_id}/plan")
def admin_assign_plan(user_id: int, body: AssignPlanRequest, x_admin_token: Optional[str] = Header(None)):
    verify_admin_token(x_admin_token)

    if body.plan_code not in VALID_PLAN_CODES:
        raise HTTPException(status_code=400, detail=f"Invalid plan. Must be one of: {VALID_PLAN_CODES}")

    try:
        with get_cursor(commit=False) as cur:
            cur.execute("SELECT id, email FROM users WHERE id = %s", (user_id,))
            user = cur.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        success = apply_plan_settings_to_user(user_id, body.plan_code)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to apply plan settings")

        logger.info(f"Admin assigned plan '{body.plan_code}' to user {user_id} ({user['email']})")
        return {
            "success": True,
            "message": f"Plan '{body.plan_code}' assigned to {user['email']}",
            "user_id": user_id,
            "plan": body.plan_code,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to assign plan to user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class SendEmailRequest(BaseModel):
    to_email: str
    subject: str
    html_body: str


@router.post("/users/send-email")
def admin_send_email(body: SendEmailRequest, x_admin_token: Optional[str] = Header(None)):
    verify_admin_token(x_admin_token)

    if not body.to_email or not body.subject or not body.html_body:
        raise HTTPException(status_code=400, detail="Email, subject, and body are required")

    brevo_api_key = os.environ.get("BREVO_API_KEY")
    if not brevo_api_key:
        raise HTTPException(status_code=500, detail="BREVO_API_KEY not configured")

    email_from = os.environ.get("EMAIL_FROM", "EnergyRiskIQ <alerts@energyriskiq.com>")
    import re
    match = re.match(r'^(.+?)<(.+?)>$', email_from.strip())
    if match:
        sender = {"name": match.group(1).strip(), "email": match.group(2).strip()}
    else:
        sender = {"email": email_from.strip()}

    try:
        response = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={
                "api-key": brevo_api_key,
                "Content-Type": "application/json",
            },
            json={
                "sender": sender,
                "to": [{"email": body.to_email}],
                "subject": body.subject,
                "htmlContent": body.html_body,
            },
            timeout=30,
        )

        if response.status_code in [200, 201, 202]:
            data = response.json()
            message_id = data.get("messageId")
            logger.info(f"Admin email sent to {body.to_email}, subject='{body.subject}', messageId={message_id}")
            return {"success": True, "message": f"Email sent to {body.to_email}", "message_id": message_id}
        else:
            error = f"Brevo API error: {response.status_code} - {response.text}"
            logger.error(f"Admin email send failed: {error}")
            raise HTTPException(status_code=500, detail=error)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Admin email send failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Bulk email / newsletter to ALL platform users
# ─────────────────────────────────────────────────────────────────────────────

class SendBulkEmailRequest(BaseModel):
    subject: str
    body: str
    content_type: str = "html"  # 'html' or 'text'


def _email_sender():
    email_from = os.environ.get("EMAIL_FROM", "EnergyRiskIQ <alerts@energyriskiq.com>")
    import re
    match = re.match(r'^(.+?)<(.+?)>$', email_from.strip())
    if match:
        return {"name": match.group(1).strip(), "email": match.group(2).strip()}
    return {"email": email_from.strip()}


def _get_all_user_emails() -> List[str]:
    with get_cursor(commit=False) as cur:
        cur.execute(
            "SELECT DISTINCT LOWER(email) AS email FROM users "
            "WHERE email IS NOT NULL AND email LIKE '%@%' ORDER BY email"
        )
        return [r["email"] for r in cur.fetchall() if r.get("email")]


def _update_campaign(campaign_id: int, **fields):
    if not fields:
        return
    sets = ", ".join(f"{k} = %s" for k in fields)
    vals = list(fields.values())
    vals.append(campaign_id)
    try:
        with get_cursor() as cur:
            cur.execute(
                f"UPDATE admin_bulk_email_campaigns SET {sets}, updated_at = NOW() WHERE id = %s",
                tuple(vals),
            )
    except Exception as e:
        logger.error(f"Bulk email campaign {campaign_id} update failed: {e}")


def _bulk_body_to_html(body: str, content_type: str) -> str:
    """Normalise the composer body into HTML fit for the branded template.
    HTML bodies are inserted as-is; plain-text bodies are escaped and newlines
    converted to line breaks."""
    if content_type == "text":
        return _html.escape(body).replace("\n", "<br>\n")
    return body


def _build_bulk_email_html(subject: str, body_html: str,
                           login_url: Optional[str] = None,
                           button_label: str = "Login Your Account") -> str:
    """Wrap an admin newsletter subject + body in the branded EnergyRiskIQ
    template (navy background, logo header, footer with founder signature).
    Mirrors the welcome email styling in src/api/user_routes.py.
    login_url: href for the centred "Login Your Account" button. May be a
    Brevo placeholder like {{params.login_url}} for per-recipient links."""
    logo_url = f"{APP_URL}/static/logo.png"
    safe_subject = _html.escape(subject, quote=True)
    if not login_url:
        login_url = f"{APP_URL}/users/account"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{safe_subject}</title>
</head>
<body style="margin:0; padding:0; background-color:#0f172a; font-family:Arial, Helvetica, sans-serif; color:#1a1a1a; -webkit-text-size-adjust:100%;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#0f172a; padding:24px 0;">
    <tr>
      <td align="center">
        <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px; width:100%; background-color:#ffffff; border-radius:12px; overflow:hidden;">
          <tr>
            <td style="background-color:#0f172a; padding:28px 32px; text-align:center;">
              <table role="presentation" cellpadding="0" cellspacing="0" align="center" style="margin:0 auto;">
                <tr>
                  <td style="vertical-align:middle; padding-right:12px;">
                    <img src="{logo_url}" alt="EnergyRiskIQ" width="40" height="40" style="display:block; border:0; outline:none; text-decoration:none;">
                  </td>
                  <td style="vertical-align:middle;">
                    <span style="color:#d4a017; font-size:22px; font-weight:bold; letter-spacing:0.5px;">EnergyRiskIQ</span>
                  </td>
                </tr>
              </table>
              <p style="margin:12px 0 0; color:#94a3b8; font-size:13px;">Energy Risk Intelligence</p>
            </td>
          </tr>
          <tr>
            <td style="padding:32px;">
              <h1 style="margin:0 0 20px; font-size:22px; line-height:1.35; color:#0f172a;">{safe_subject}</h1>
              <div style="font-size:16px; line-height:1.6; color:#1a1a1a;">{body_html}</div>
              <table role="presentation" cellpadding="0" cellspacing="0" style="margin:28px auto 4px;">
                <tr>
                  <td align="center" style="border-radius:8px; background-color:#d4a017;">
                    <a href="{login_url}" style="display:inline-block; padding:14px 28px; font-size:16px; font-weight:bold; color:#0f172a; text-decoration:none; border-radius:8px;">{button_label}</a>
                  </td>
                </tr>
              </table>
              <p style="margin:28px 0 4px; font-size:16px; line-height:1.6;">Kind regards,</p>
              <p style="margin:0; font-size:16px; line-height:1.6;"><strong>Emil C</strong><br>Founder, EnergyRiskIQ</p>
            </td>
          </tr>
          <tr>
            <td style="background-color:#f1f5f9; padding:20px 32px; font-size:13px; line-height:1.6; color:#64748b;">
              <p style="margin:0 0 6px;"><strong>EnergyRiskIQ</strong> — Energy Risk Intelligence</p>
              <p style="margin:0;">You are receiving this email because you have an EnergyRiskIQ account. You can reply directly to this email at any time.</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _run_bulk_email(campaign_id: int, subject: str, body: str,
                    content_type: str, emails: List[str]):
    brevo_api_key = os.environ.get("BREVO_API_KEY")
    if not brevo_api_key:
        _update_campaign(campaign_id, status="failed", error="BREVO_API_KEY not configured")
        return

    sender = _email_sender()
    body_html = _bulk_body_to_html(body, content_type)
    # Per-recipient magic-login links are injected via Brevo params.
    full_html = _build_bulk_email_html(subject, body_html,
                                       login_url="{{params.login_url}}")
    content_field = {"htmlContent": full_html}

    fallback_login_url = f"{APP_URL}/users/account"
    login_urls = {}
    try:
        from src.api.user_routes import build_email_login_url
        for e in emails:
            login_urls[e] = build_email_login_url(e) or fallback_login_url
    except Exception as e:
        logger.warning(f"Bulk email campaign {campaign_id}: login-link generation failed, using fallback: {e}")

    sent = 0
    failed = 0
    batch_size = 500
    max_attempts = 4
    last_error = None
    _update_campaign(campaign_id, status="sending")
    for i in range(0, len(emails), batch_size):
        chunk = emails[i:i + batch_size]
        payload = {
            "sender": sender,
            "subject": subject,
            "messageVersions": [
                {
                    "to": [{"email": e}],
                    "params": {"login_url": login_urls.get(e, fallback_login_url)},
                }
                for e in chunk
            ],
        }
        payload.update(content_field)

        chunk_ok = False
        for attempt in range(1, max_attempts + 1):
            try:
                resp = requests.post(
                    "https://api.brevo.com/v3/smtp/email",
                    headers={"api-key": brevo_api_key, "Content-Type": "application/json"},
                    json=payload,
                    timeout=60,
                )
                if resp.status_code in (200, 201, 202):
                    chunk_ok = True
                    break
                last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                logger.error(
                    f"Bulk email campaign {campaign_id} chunk attempt {attempt}/{max_attempts} "
                    f"failed: {last_error}"
                )
                # 4xx other than 429 are not retryable
                if 400 <= resp.status_code < 500 and resp.status_code != 429:
                    break
            except Exception as e:
                last_error = str(e)
                logger.error(
                    f"Bulk email campaign {campaign_id} chunk attempt {attempt}/{max_attempts} "
                    f"exception: {e}"
                )
            if attempt < max_attempts:
                time.sleep(min(2 ** attempt, 30))

        if chunk_ok:
            sent += len(chunk)
        else:
            failed += len(chunk)
        _update_campaign(campaign_id, sent=sent, failed=failed)

    final_status = "completed" if failed == 0 else ("completed_with_errors" if sent > 0 else "failed")
    _update_campaign(
        campaign_id, status=final_status, sent=sent, failed=failed,
        error=(last_error if failed else None),
    )
    logger.info(
        f"Bulk email campaign {campaign_id} finished: status={final_status}, "
        f"sent={sent}, failed={failed}, total={len(emails)}"
    )


@router.post("/users/send-bulk-email")
def admin_send_bulk_email(body: SendBulkEmailRequest, background_tasks: BackgroundTasks,
                          x_admin_token: Optional[str] = Header(None)):
    verify_admin_token(x_admin_token)

    subject = (body.subject or "").strip()
    content = (body.body or "").strip()
    content_type = body.content_type if body.content_type in ("html", "text") else "html"
    if not subject or not content:
        raise HTTPException(status_code=400, detail="Subject and body are required")

    if not os.environ.get("BREVO_API_KEY"):
        raise HTTPException(status_code=500, detail="BREVO_API_KEY not configured")

    emails = _get_all_user_emails()
    if not emails:
        raise HTTPException(status_code=400, detail="No platform users to email")

    try:
        with get_cursor() as cur:
            cur.execute(
                "INSERT INTO admin_bulk_email_campaigns (subject, content_type, total, status) "
                "VALUES (%s, %s, %s, 'sending') RETURNING id",
                (subject, content_type, len(emails)),
            )
            campaign_id = cur.fetchone()["id"]
    except Exception as e:
        logger.error(f"Could not create bulk email campaign: {e}")
        raise HTTPException(status_code=500, detail="Could not start campaign")

    background_tasks.add_task(_run_bulk_email, campaign_id, subject, content, content_type, emails)
    logger.info(f"Bulk email campaign {campaign_id} queued for {len(emails)} recipients")
    return {"success": True, "campaign_id": campaign_id, "total": len(emails)}


@router.get("/users/bulk-email-status/{campaign_id}")
def admin_bulk_email_status(campaign_id: int, x_admin_token: Optional[str] = Header(None)):
    verify_admin_token(x_admin_token)
    with get_cursor(commit=False) as cur:
        cur.execute(
            "SELECT id, subject, content_type, total, sent, failed, status, error "
            "FROM admin_bulk_email_campaigns WHERE id = %s",
            (campaign_id,),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return {
        "id": row["id"],
        "subject": row["subject"],
        "content_type": row["content_type"],
        "total": row["total"],
        "sent": row["sent"],
        "failed": row["failed"],
        "status": row["status"],
        "error": row["error"],
    }


class SendBulkEmailTestRequest(BaseModel):
    subject: str
    body: str
    content_type: str = "html"
    to_email: str


@router.post("/users/send-bulk-email-test")
def admin_send_bulk_email_test(body: SendBulkEmailTestRequest, x_admin_token: Optional[str] = Header(None)):
    """Send a single test copy of a bulk email, rendered with the exact same
    branded template used for the full send, so admins can review before blasting."""
    verify_admin_token(x_admin_token)

    subject = (body.subject or "").strip()
    content = (body.body or "").strip()
    to_email = (body.to_email or "").strip()
    content_type = body.content_type if body.content_type in ("html", "text") else "html"
    if not subject or not content:
        raise HTTPException(status_code=400, detail="Subject and body are required")
    if not to_email or "@" not in to_email:
        raise HTTPException(status_code=400, detail="A valid test recipient email is required")

    brevo_api_key = os.environ.get("BREVO_API_KEY")
    if not brevo_api_key:
        raise HTTPException(status_code=500, detail="BREVO_API_KEY not configured")

    body_html = _bulk_body_to_html(content, content_type)
    try:
        from src.api.user_routes import build_email_login_url
        login_url = build_email_login_url(to_email)
    except Exception:
        login_url = None
    full_html = _build_bulk_email_html(subject, body_html, login_url=login_url)
    sender = _email_sender()

    try:
        resp = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={"api-key": brevo_api_key, "Content-Type": "application/json"},
            json={
                "sender": sender,
                "to": [{"email": to_email}],
                "subject": f"[TEST] {subject}",
                "htmlContent": full_html,
            },
            timeout=30,
        )
        if resp.status_code in (200, 201, 202):
            message_id = resp.json().get("messageId")
            logger.info(f"Bulk email TEST sent to {to_email}, subject='{subject}', messageId={message_id}")
            return {"success": True, "message": f"Test email sent to {to_email}", "message_id": message_id}
        error = f"Brevo API error: {resp.status_code} - {resp.text}"
        logger.error(f"Bulk email test send failed: {error}")
        raise HTTPException(status_code=500, detail=error)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Bulk email test send failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
