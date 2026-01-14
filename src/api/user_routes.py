import os
import secrets
import bcrypt
import logging
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Header
from typing import Optional
from pydantic import BaseModel, EmailStr

from src.db.db import get_cursor
from src.plans.plan_helpers import get_plan_settings, create_user_plan, ALL_ALERT_TYPES
from src.alerts.channels import send_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])

SESSION_DURATION = 7 * 24 * 60 * 60

APP_URL = os.environ.get("APP_URL", "https://energyriskiq.replit.app")


class SignupRequest(BaseModel):
    email: EmailStr


class VerifyRequest(BaseModel):
    token: str


class SetPasswordRequest(BaseModel):
    token: str
    password: str
    pin: str


class SigninRequest(BaseModel):
    email: EmailStr
    password: str
    pin: str


def generate_verification_token():
    return secrets.token_urlsafe(32)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except Exception:
        return False


def verify_user_session(x_user_token: Optional[str] = Header(None)):
    if not x_user_token:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    with get_cursor(commit=False) as cursor:
        cursor.execute("""
            SELECT user_id, expires_at FROM sessions WHERE token = %s
        """, (x_user_token,))
        session = cursor.fetchone()
        
        if not session:
            raise HTTPException(status_code=401, detail="Invalid or expired session")
        
        if session["expires_at"] < datetime.utcnow():
            with get_cursor() as del_cursor:
                del_cursor.execute("DELETE FROM sessions WHERE token = %s", (x_user_token,))
            raise HTTPException(status_code=401, detail="Session expired")
        
        return {"user_id": session["user_id"], "expires": session["expires_at"].timestamp()}


@router.post("/signup")
def signup(body: SignupRequest):
    email = body.email.lower().strip()
    
    with get_cursor() as cursor:
        cursor.execute("SELECT id, email_verified, password_hash FROM users WHERE email = %s", (email,))
        existing = cursor.fetchone()
        
        if existing:
            if existing['email_verified'] and existing['password_hash']:
                raise HTTPException(status_code=400, detail="An account with this email already exists. Please sign in.")
        
        token = generate_verification_token()
        expires = datetime.utcnow() + timedelta(hours=24)
        
        if existing:
            cursor.execute("""
                UPDATE users SET 
                    verification_token = %s, 
                    verification_expires = %s,
                    updated_at = NOW()
                WHERE email = %s
            """, (token, expires, email))
            user_id = existing['id']
        else:
            cursor.execute("""
                INSERT INTO users (email, verification_token, verification_expires)
                VALUES (%s, %s, %s)
                RETURNING id
            """, (email, token, expires))
            user_id = cursor.fetchone()['id']
    
    verification_link = f"{APP_URL}/users/verify?token={token}"
    
    email_subject = "Verify your EnergyRiskIQ account"
    email_body = f"""Welcome to EnergyRiskIQ!

Please verify your email address by clicking the link below:

{verification_link}

This link will expire in 24 hours.

If you didn't create an account, you can safely ignore this email.

Best regards,
The EnergyRiskIQ Team"""
    
    success, error, _ = send_email(email, email_subject, email_body)
    
    if not success:
        logger.error(f"Failed to send verification email: {error}")
    
    return {
        "success": True,
        "message": "Verification email sent. Please check your inbox.",
        "email": email
    }


@router.post("/verify")
def verify_email(body: VerifyRequest):
    token = body.token
    
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT id, email, verification_expires, email_verified, password_hash
            FROM users WHERE verification_token = %s
        """, (token,))
        user = cursor.fetchone()
        
        if not user:
            raise HTTPException(status_code=400, detail="Invalid verification token")
        
        user_id = user['id']
        email = user['email']
        expires = user['verification_expires']
        verified = user['email_verified']
        password_hash = user['password_hash']
        
        if expires and expires < datetime.utcnow():
            raise HTTPException(status_code=400, detail="Verification token has expired. Please request a new one.")
        
        if verified and password_hash:
            raise HTTPException(status_code=400, detail="Email already verified and account is set up.")
        
        cursor.execute("""
            UPDATE users SET email_verified = TRUE, updated_at = NOW()
            WHERE id = %s
        """, (user_id,))
    
    return {
        "success": True,
        "message": "Email verified successfully",
        "email": email,
        "needs_password": True,
        "token": token
    }


@router.post("/set-password")
def set_password(body: SetPasswordRequest):
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    
    if not body.pin.isdigit() or len(body.pin) != 6:
        raise HTTPException(status_code=400, detail="PIN must be exactly 6 digits")
    
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT id, email, email_verified, password_hash
            FROM users WHERE verification_token = %s
        """, (body.token,))
        user = cursor.fetchone()
        
        if not user:
            raise HTTPException(status_code=400, detail="Invalid token")
        
        user_id = user['id']
        email = user['email']
        verified = user['email_verified']
        existing_password = user['password_hash']
        
        if not verified:
            raise HTTPException(status_code=400, detail="Please verify your email first")
        
        if existing_password:
            raise HTTPException(status_code=400, detail="Password already set. Please sign in.")
        
        password_hash = hash_password(body.password)
        pin_hash = hash_password(body.pin)
        
        cursor.execute("""
            UPDATE users SET 
                password_hash = %s,
                pin_hash = %s,
                verification_token = NULL,
                verification_expires = NULL,
                updated_at = NOW()
            WHERE id = %s
        """, (password_hash, pin_hash, user_id))
        
        create_user_plan(user_id, "free")
    
    session_token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(seconds=SESSION_DURATION)
    
    with get_cursor() as cursor:
        cursor.execute("""
            INSERT INTO sessions (token, user_id, expires_at)
            VALUES (%s, %s, %s)
        """, (session_token, user_id, expires_at))
    
    return {
        "success": True,
        "message": "Account setup complete",
        "token": session_token,
        "user": {
            "id": user_id,
            "email": email
        }
    }


@router.post("/signin")
def signin(body: SigninRequest):
    email = body.email.lower().strip()
    
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT id, email, email_verified, password_hash, pin_hash
            FROM users WHERE email = %s
        """, (email,))
        user = cursor.fetchone()
        
        if not user:
            raise HTTPException(status_code=401, detail="Invalid email or password")
        
        user_id = user['id']
        user_email = user['email']
        verified = user['email_verified']
        password_hash = user['password_hash']
        pin_hash = user['pin_hash']
        
        if not verified:
            raise HTTPException(status_code=401, detail="Please verify your email first")
        
        if not password_hash:
            raise HTTPException(status_code=401, detail="Account setup incomplete. Please complete verification.")
        
        if not verify_password(body.password, password_hash):
            raise HTTPException(status_code=401, detail="Invalid email or password")
        
        if not verify_password(body.pin, pin_hash):
            raise HTTPException(status_code=401, detail="Invalid PIN")
    
    session_token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(seconds=SESSION_DURATION)
    
    with get_cursor() as cursor:
        cursor.execute("""
            INSERT INTO sessions (token, user_id, expires_at)
            VALUES (%s, %s, %s)
        """, (session_token, user_id, expires_at))
    
    return {
        "success": True,
        "token": session_token,
        "user": {
            "id": user_id,
            "email": user_email
        }
    }


@router.post("/signout")
def signout(x_user_token: Optional[str] = Header(None)):
    if x_user_token:
        with get_cursor() as cursor:
            cursor.execute("DELETE FROM sessions WHERE token = %s", (x_user_token,))
    return {"success": True}


@router.get("/me")
def get_current_user(x_user_token: Optional[str] = Header(None)):
    session = verify_user_session(x_user_token)
    
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT u.id, u.email, u.telegram_chat_id, u.created_at,
                   COALESCE(up.plan, 'free') as plan
            FROM users u
            LEFT JOIN user_plans up ON u.id = up.user_id
            WHERE u.id = %s
        """, (session["user_id"],))
        user = cursor.fetchone()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        plan_code = user['plan']
        plan_settings = get_plan_settings(plan_code)
        
        return {
            "id": user['id'],
            "email": user['email'],
            "telegram_chat_id": user['telegram_chat_id'],
            "created_at": user['created_at'].isoformat() if user['created_at'] else None,
            "plan": plan_code,
            "plan_settings": {
                "display_name": plan_settings.get("display_name", plan_code.title()),
                "allowed_alert_types": plan_settings.get("allowed_alert_types", []),
                "max_email_alerts_per_day": plan_settings.get("max_email_alerts_per_day", 2),
                "delivery_config": plan_settings.get("delivery_config", {})
            }
        }


@router.get("/alerts")
def get_user_alerts(x_user_token: Optional[str] = Header(None), limit: int = 50):
    session = verify_user_session(x_user_token)
    
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT COALESCE(up.plan, 'free') as plan
            FROM users u
            LEFT JOIN user_plans up ON u.id = up.user_id
            WHERE u.id = %s
        """, (session["user_id"],))
        user_plan = cursor.fetchone()
        plan_code = user_plan['plan'] if user_plan else 'free'
        
        plan_settings = get_plan_settings(plan_code)
        allowed_types = plan_settings.get("allowed_alert_types", [])
        
        has_all = 'ALL' in allowed_types
        effective_allowed = ALL_ALERT_TYPES if has_all else allowed_types
        locked_types = [t for t in ALL_ALERT_TYPES if t not in effective_allowed]
        
        if effective_allowed:
            cursor.execute("""
                SELECT DISTINCT ON (COALESCE(cooldown_key, alert_type || '|' || COALESCE(region,'') || '|' || title))
                       id, alert_type, region, asset, triggered_value, threshold,
                       title, message, channel, status, created_at, sent_at
                FROM alerts
                WHERE alert_type = ANY(%s)
                  AND status = 'sent'
                ORDER BY COALESCE(cooldown_key, alert_type || '|' || COALESCE(region,'') || '|' || title), created_at DESC
            """, (effective_allowed,))
            all_allowed_alerts = cursor.fetchall()
        else:
            all_allowed_alerts = []
        
        sorted_alerts = sorted(all_allowed_alerts, key=lambda r: r['created_at'] or datetime.min, reverse=True)[:limit]
        
        alerts = []
        for row in sorted_alerts:
            alerts.append({
                "id": row['id'],
                "alert_type": row['alert_type'],
                "region": row['region'],
                "asset": row['asset'],
                "triggered_value": float(row['triggered_value']) if row['triggered_value'] else None,
                "threshold": float(row['threshold']) if row['threshold'] else None,
                "title": row['title'],
                "message": row['message'],
                "channel": row['channel'],
                "status": row['status'],
                "created_at": row['created_at'].isoformat() if row['created_at'] else None,
                "sent_at": row['sent_at'].isoformat() if row['sent_at'] else None,
                "allowed_by_plan": True
            })
        
        locked_samples = []
        if locked_types:
            cursor.execute("""
                SELECT DISTINCT ON (alert_type)
                       id, alert_type, region, asset, title, message, created_at
                FROM alerts
                WHERE alert_type = ANY(%s)
                  AND status = 'sent'
                ORDER BY alert_type, created_at DESC
            """, (locked_types,))
            
            for row in cursor.fetchall():
                locked_samples.append({
                    "alert_type": row['alert_type'],
                    "region": row['region'],
                    "asset": row['asset'],
                    "title": row['title'],
                    "preview": (row['message'][:100] + "...") if row['message'] and len(row['message']) > 100 else row['message'],
                    "created_at": row['created_at'].isoformat() if row['created_at'] else None
                })
        
        return {
            "alerts": alerts,
            "plan": plan_code,
            "allowed_alert_types": effective_allowed,
            "locked_alert_types": locked_types,
            "locked_samples": locked_samples
        }


@router.post("/resend-verification")
def resend_verification(body: SignupRequest):
    email = body.email.lower().strip()
    
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT id, email_verified, password_hash FROM users WHERE email = %s
        """, (email,))
        user = cursor.fetchone()
        
        if not user:
            return {"success": True, "message": "If an account exists, a verification email will be sent."}
        
        if user['email_verified'] and user['password_hash']:
            raise HTTPException(status_code=400, detail="Account already verified. Please sign in.")
        
        token = generate_verification_token()
        expires = datetime.utcnow() + timedelta(hours=24)
        
        cursor.execute("""
            UPDATE users SET 
                verification_token = %s, 
                verification_expires = %s,
                updated_at = NOW()
            WHERE id = %s
        """, (token, expires, user['id']))
    
    verification_link = f"{APP_URL}/users/verify?token={token}"
    
    email_subject = "Verify your EnergyRiskIQ account"
    email_body = f"""Hello,

You requested a new verification link for your EnergyRiskIQ account.

Please verify your email address by clicking the link below:

{verification_link}

This link will expire in 24 hours.

Best regards,
The EnergyRiskIQ Team"""
    
    send_email(email, email_subject, email_body)
    
    return {"success": True, "message": "If an account exists, a verification email will be sent."}


@router.post("/telegram/generate-code")
def generate_telegram_link_code(x_user_token: Optional[str] = Header(None)):
    session = verify_user_session(x_user_token)
    user_id = session["user_id"]
    
    code = secrets.token_hex(4).upper()
    expires = datetime.utcnow() + timedelta(minutes=15)
    
    with get_cursor() as cursor:
        cursor.execute("""
            UPDATE users SET 
                telegram_link_code = %s,
                telegram_link_expires = %s,
                updated_at = NOW()
            WHERE id = %s
        """, (code, expires, user_id))
    
    return {
        "success": True,
        "code": code,
        "expires_in_minutes": 15,
        "bot_username": os.environ.get("TELEGRAM_BOT_USERNAME", "EnergyRiskIQBot"),
        "instructions": f"Send this code to the bot: {code}"
    }


@router.post("/telegram/unlink")
def unlink_telegram(x_user_token: Optional[str] = Header(None)):
    session = verify_user_session(x_user_token)
    user_id = session["user_id"]
    
    with get_cursor() as cursor:
        cursor.execute("""
            UPDATE users SET 
                telegram_chat_id = NULL,
                telegram_link_code = NULL,
                telegram_link_expires = NULL,
                updated_at = NOW()
            WHERE id = %s
        """, (user_id,))
    
    return {"success": True, "message": "Telegram unlinked successfully"}
