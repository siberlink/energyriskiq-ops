import os
import secrets
import hashlib
import time
import logging
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Header
from typing import Optional
from pydantic import BaseModel, EmailStr

from src.db.db import get_cursor
from src.alerts.channels import send_email
from src.plans.plan_helpers import create_user_plan

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])

user_sessions = {}
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
    return hashlib.sha256(password.encode()).hexdigest()


def verify_user_session(x_user_token: Optional[str] = Header(None)):
    if not x_user_token:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    if x_user_token not in user_sessions:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    
    session = user_sessions[x_user_token]
    if session["expires"] < time.time():
        del user_sessions[x_user_token]
        raise HTTPException(status_code=401, detail="Session expired")
    
    return session


@router.post("/signup")
def signup(body: SignupRequest):
    email = body.email.lower().strip()
    
    with get_cursor() as cursor:
        cursor.execute("SELECT id, email_verified, password_hash FROM users WHERE email = %s", (email,))
        existing = cursor.fetchone()
        
        if existing:
            if existing[1] and existing[2]:
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
            user_id = existing[0]
        else:
            cursor.execute("""
                INSERT INTO users (email, verification_token, verification_expires)
                VALUES (%s, %s, %s)
                RETURNING id
            """, (email, token, expires))
            user_id = cursor.fetchone()[0]
    
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
        
        user_id, email, expires, verified, password_hash = user
        
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
        
        user_id, email, verified, existing_password = user
        
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
    user_sessions[session_token] = {
        "user_id": user_id,
        "email": email,
        "created": time.time(),
        "expires": time.time() + SESSION_DURATION
    }
    
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
        
        user_id, user_email, verified, password_hash, pin_hash = user
        
        if not verified:
            raise HTTPException(status_code=401, detail="Please verify your email first")
        
        if not password_hash:
            raise HTTPException(status_code=401, detail="Account setup incomplete. Please complete verification.")
        
        if hash_password(body.password) != password_hash:
            raise HTTPException(status_code=401, detail="Invalid email or password")
        
        if hash_password(body.pin) != pin_hash:
            raise HTTPException(status_code=401, detail="Invalid PIN")
    
    session_token = secrets.token_urlsafe(32)
    user_sessions[session_token] = {
        "user_id": user_id,
        "email": user_email,
        "created": time.time(),
        "expires": time.time() + SESSION_DURATION
    }
    
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
    if x_user_token and x_user_token in user_sessions:
        del user_sessions[x_user_token]
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
        
        return {
            "id": user[0],
            "email": user[1],
            "telegram_chat_id": user[2],
            "created_at": user[3].isoformat() if user[3] else None,
            "plan": user[4]
        }


@router.get("/alerts")
def get_user_alerts(x_user_token: Optional[str] = Header(None), limit: int = 20):
    session = verify_user_session(x_user_token)
    
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT id, alert_type, region, asset, triggered_value, threshold,
                   title, message, channel, status, created_at, sent_at
            FROM alerts
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT %s
        """, (session["user_id"], limit))
        
        alerts = []
        for row in cursor.fetchall():
            alerts.append({
                "id": row[0],
                "alert_type": row[1],
                "region": row[2],
                "asset": row[3],
                "triggered_value": float(row[4]) if row[4] else None,
                "threshold": float(row[5]) if row[5] else None,
                "title": row[6],
                "message": row[7],
                "channel": row[8],
                "status": row[9],
                "created_at": row[10].isoformat() if row[10] else None,
                "sent_at": row[11].isoformat() if row[11] else None
            })
        
        return {"alerts": alerts}


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
        
        if user[1] and user[2]:
            raise HTTPException(status_code=400, detail="Account already verified. Please sign in.")
        
        token = generate_verification_token()
        expires = datetime.utcnow() + timedelta(hours=24)
        
        cursor.execute("""
            UPDATE users SET 
                verification_token = %s, 
                verification_expires = %s,
                updated_at = NOW()
            WHERE id = %s
        """, (token, expires, user[0]))
    
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
