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

AVAILABLE_REGIONS = ['Europe', 'Middle East', 'Asia', 'North America', 'Black Sea', 'North Africa', 'Global']
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


class UserSettingRequest(BaseModel):
    alert_type: str
    region: Optional[str] = None
    enabled: bool = True


class DeliveryPreferencesRequest(BaseModel):
    geri_email: bool = False
    geri_telegram: bool = False
    eeri_email: bool = False
    eeri_telegram: bool = False
    egsi_email: bool = False
    egsi_telegram: bool = False
    daily_digest_email: bool = False
    daily_digest_telegram: bool = False


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
            result = cursor.fetchone()
            user_id = result['id'] if result else None
    
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
            return {
                "success": False,
                "status": "incomplete_setup",
                "message": "Account setup incomplete. Please verify your email to complete setup.",
                "email": user_email
            }
        
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
    user_id = session["user_id"]
    
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT COALESCE(up.plan, 'free') as plan
            FROM users u
            LEFT JOIN user_plans up ON u.id = up.user_id
            WHERE u.id = %s
        """, (user_id,))
        user_plan = cursor.fetchone()
        plan_code = user_plan['plan'] if user_plan else 'free'
        
        plan_settings = get_plan_settings(plan_code)
        allowed_types = plan_settings.get("allowed_alert_types", [])
        
        has_all = 'ALL' in allowed_types
        effective_allowed = ALL_ALERT_TYPES if has_all else allowed_types
        locked_types = [t for t in ALL_ALERT_TYPES if t not in effective_allowed]
        
        cursor.execute("""
            SELECT alert_type, region, asset, enabled
            FROM user_settings
            WHERE user_id = %s AND enabled = TRUE
        """, (user_id,))
        user_settings = cursor.fetchall()
        
        has_user_settings = len(user_settings) > 0
        
        user_setting_filters = []
        if has_user_settings:
            for setting in user_settings:
                if setting['alert_type'] in effective_allowed:
                    user_setting_filters.append({
                        'alert_type': setting['alert_type'],
                        'region': setting['region'],
                        'asset': setting['asset']
                    })
        
        alerts = []
        
        if effective_allowed:
            try:
                cursor.execute("""
                    SELECT uad.id, ae.alert_type, ae.scope_region as region, ae.scope_assets as assets,
                           ae.severity, ae.headline as title, ae.body as message,
                           uad.channel, uad.status, ae.created_at, uad.sent_at
                    FROM user_alert_deliveries uad
                    JOIN alert_events ae ON uad.alert_event_id = ae.id
                    WHERE uad.user_id = %s
                      AND ae.alert_type = ANY(%s)
                      AND uad.status IN ('sent', 'skipped')
                    ORDER BY ae.created_at DESC
                    LIMIT 100
                """, (user_id, effective_allowed,))
                delivered_alerts = cursor.fetchall()
            except Exception as e:
                import logging
                logging.warning(f"Alert query failed (schema mismatch?): {e}")
                delivered_alerts = []
            
            for row in delivered_alerts:
                if has_user_settings:
                    matches_setting = False
                    for flt in user_setting_filters:
                        type_match = row['alert_type'] == flt['alert_type']
                        region_match = flt['region'] is None or row['region'] == flt['region']
                        if type_match and region_match:
                            matches_setting = True
                            break
                    if not matches_setting:
                        continue
                
                assets_list = row['assets'] if row['assets'] else []
                asset_str = assets_list[0] if len(assets_list) == 1 else ', '.join(assets_list) if assets_list else None
                alerts.append({
                    "id": row['id'],
                    "alert_type": row['alert_type'],
                    "region": row['region'],
                    "asset": asset_str,
                    "severity": row['severity'],
                    "title": row['title'],
                    "message": row['message'],
                    "channel": row['channel'],
                    "status": row['status'],
                    "created_at": row['created_at'].isoformat() if row['created_at'] else None,
                    "sent_at": row['sent_at'].isoformat() if row['sent_at'] else None,
                    "allowed_by_plan": True
                })
            
            if not alerts:
                try:
                    cursor.execute("""
                        SELECT ae.id, ae.alert_type, ae.scope_region as region, ae.scope_assets as assets,
                               ae.severity, ae.headline as title, ae.body as message, ae.created_at
                        FROM alert_events ae
                        WHERE ae.alert_type = ANY(%s)
                          AND ae.created_at >= NOW() - INTERVAL '7 days'
                        ORDER BY ae.created_at DESC
                        LIMIT %s
                    """, (effective_allowed, limit))
                    fallback_rows = cursor.fetchall()
                except Exception as e:
                    import logging
                    logging.warning(f"Fallback alert query failed: {e}")
                    fallback_rows = []
                
                for row in fallback_rows:
                    if has_user_settings:
                        matches_setting = False
                        for flt in user_setting_filters:
                            type_match = row['alert_type'] == flt['alert_type']
                            region_match = flt['region'] is None or row['region'] == flt['region']
                            if type_match and region_match:
                                matches_setting = True
                                break
                        if not matches_setting:
                            continue
                    
                    assets_list = row['assets'] if row['assets'] else []
                    asset_str = assets_list[0] if len(assets_list) == 1 else ', '.join(assets_list) if assets_list else None
                    alerts.append({
                        "id": row['id'],
                        "alert_type": row['alert_type'],
                        "region": row['region'],
                        "asset": asset_str,
                        "severity": row['severity'],
                        "title": row['title'],
                        "message": row['message'],
                        "channel": "email",
                        "status": "available",
                        "created_at": row['created_at'].isoformat() if row['created_at'] else None,
                        "sent_at": None,
                        "allowed_by_plan": True
                    })
        
        alerts = sorted(alerts, key=lambda r: r['created_at'] or '', reverse=True)[:limit]
        
        locked_samples = []
        if locked_types:
            try:
                cursor.execute("""
                    SELECT DISTINCT ON (alert_type)
                           ae.id, ae.alert_type, ae.scope_region as region, ae.scope_assets as assets,
                           ae.headline as title, ae.body as message, ae.created_at
                    FROM alert_events ae
                    WHERE ae.alert_type = ANY(%s)
                      AND ae.created_at >= NOW() - INTERVAL '30 days'
                    ORDER BY ae.alert_type, ae.created_at DESC
                """, (locked_types,))
                locked_rows = cursor.fetchall()
            except Exception as e:
                import logging
                logging.warning(f"Locked samples query failed: {e}")
                locked_rows = []
            
            for row in locked_rows:
                assets = row['assets'] if row['assets'] else []
                asset_str = assets[0] if len(assets) == 1 else ', '.join(assets) if assets else None
                locked_samples.append({
                    "alert_type": row['alert_type'],
                    "region": row['region'],
                    "asset": asset_str,
                    "title": row['title'],
                    "preview": (row['message'][:100] + "...") if row['message'] and len(row['message']) > 100 else row['message'],
                    "created_at": row['created_at'].isoformat() if row['created_at'] else None
                })
        
        return {
            "alerts": alerts,
            "plan": plan_code,
            "allowed_alert_types": effective_allowed,
            "locked_alert_types": locked_types,
            "locked_samples": locked_samples,
            "has_user_settings": has_user_settings,
            "active_settings_count": len(user_setting_filters)
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


TELEGRAM_ELIGIBLE_PLANS = ['free', 'personal', 'trader', 'pro', 'enterprise']


@router.post("/telegram/generate-code")
def generate_telegram_link_code(x_user_token: Optional[str] = Header(None)):
    session = verify_user_session(x_user_token)
    user_id = session["user_id"]
    
    with get_cursor() as cursor:
        code = secrets.token_urlsafe(12)[:16]
        expires = datetime.utcnow() + timedelta(minutes=15)
        
        cursor.execute("""
            UPDATE users SET 
                telegram_link_code = %s,
                telegram_link_expires = %s,
                updated_at = NOW()
            WHERE id = %s
        """, (code, expires, user_id))
    
    bot_username = "energyriskiq_bot"
    deep_link = f"https://t.me/{bot_username}?start={code}"
    
    return {
        "success": True,
        "code": code,
        "expires_in_minutes": 15,
        "bot_username": bot_username,
        "deep_link": deep_link,
        "instructions": f"Click the link or send this code to the bot: {code}"
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
                telegram_connected_at = NULL,
                updated_at = NOW()
            WHERE id = %s
        """, (user_id,))
    
    return {"success": True, "message": "Telegram unlinked successfully"}


@router.post("/telegram/link-manual")
def link_telegram_manual(x_user_token: Optional[str] = Header(None), chat_id: str = ""):
    """Link Telegram using a manually-entered Chat ID."""
    session = verify_user_session(x_user_token)
    user_id = session["user_id"]
    
    if not chat_id or not chat_id.strip():
        raise HTTPException(status_code=400, detail="Chat ID is required")
    
    chat_id = chat_id.strip()
    
    if not chat_id.lstrip('-').isdigit():
        raise HTTPException(status_code=400, detail="Invalid Chat ID format. Chat ID should be a number.")
    
    with get_cursor() as cursor:
        cursor.execute("""
            UPDATE users SET 
                telegram_chat_id = %s,
                telegram_link_code = NULL,
                telegram_link_expires = NULL,
                telegram_connected_at = NOW(),
                updated_at = NOW()
            WHERE id = %s
        """, (chat_id, user_id))
    
    return {"success": True, "message": "Telegram linked successfully", "chat_id": chat_id}


@router.get("/telegram/status")
def get_telegram_status(x_user_token: Optional[str] = Header(None)):
    """Get current Telegram connection status."""
    session = verify_user_session(x_user_token)
    user_id = session["user_id"]
    
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT u.telegram_chat_id, u.telegram_connected_at, up.plan
            FROM users u
            LEFT JOIN user_plans up ON u.id = up.user_id
            WHERE u.id = %s
        """, (user_id,))
        row = cursor.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        
        plan = row.get('plan') or 'free'
        is_eligible = plan in TELEGRAM_ELIGIBLE_PLANS
        is_connected = row['telegram_chat_id'] is not None
        
        return {
            "connected": is_connected,
            "chat_id": row['telegram_chat_id'] if is_connected else None,
            "connected_at": row['telegram_connected_at'].isoformat() if row.get('telegram_connected_at') else None,
            "eligible": is_eligible,
            "plan": plan,
            "bot_username": "energyriskiq_bot"
        }


@router.get("/settings")
def get_user_settings(x_user_token: Optional[str] = Header(None)):
    """Get user alert settings and plan constraints."""
    session = verify_user_session(x_user_token)
    user_id = session["user_id"]
    
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT COALESCE(up.plan, 'free') as plan
            FROM users u
            LEFT JOIN user_plans up ON u.id = up.user_id
            WHERE u.id = %s
        """, (user_id,))
        user_plan = cursor.fetchone()
        plan_code = user_plan['plan'] if user_plan else 'free'
        
        plan_settings = get_plan_settings(plan_code)
        allowed_types = plan_settings.get("allowed_alert_types", [])
        max_regions = plan_settings.get("max_regions", 1)
        
        has_all = 'ALL' in allowed_types
        effective_allowed = ALL_ALERT_TYPES if has_all else allowed_types
        
        cursor.execute("""
            SELECT id, alert_type, region, asset, enabled, created_at
            FROM user_settings
            WHERE user_id = %s
            ORDER BY alert_type, region
        """, (user_id,))
        settings = cursor.fetchall()
        
        cursor.execute("""
            SELECT COUNT(DISTINCT region) as region_count
            FROM user_settings
            WHERE user_id = %s AND region IS NOT NULL AND enabled = TRUE
        """, (user_id,))
        region_count_row = cursor.fetchone()
        current_region_count = region_count_row['region_count'] if region_count_row else 0
    
    return {
        "plan": plan_code,
        "allowed_alert_types": effective_allowed,
        "max_regions": max_regions,
        "current_region_count": current_region_count,
        "available_regions": AVAILABLE_REGIONS,
        "settings": [
            {
                "id": s['id'],
                "alert_type": s['alert_type'],
                "region": s['region'],
                "asset": s['asset'],
                "enabled": s['enabled'],
                "created_at": s['created_at'].isoformat() if s['created_at'] else None
            }
            for s in settings
        ]
    }


@router.post("/settings")
def add_user_setting(body: UserSettingRequest, x_user_token: Optional[str] = Header(None)):
    """Add a new alert setting for the user."""
    session = verify_user_session(x_user_token)
    user_id = session["user_id"]
    
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT COALESCE(up.plan, 'free') as plan
            FROM users u
            LEFT JOIN user_plans up ON u.id = up.user_id
            WHERE u.id = %s
        """, (user_id,))
        user_plan = cursor.fetchone()
        plan_code = user_plan['plan'] if user_plan else 'free'
        
        plan_settings = get_plan_settings(plan_code)
        allowed_types = plan_settings.get("allowed_alert_types", [])
        max_regions = plan_settings.get("max_regions", 1)
        
        has_all = 'ALL' in allowed_types
        effective_allowed = ALL_ALERT_TYPES if has_all else allowed_types
        
        if body.alert_type not in effective_allowed:
            raise HTTPException(
                status_code=403, 
                detail=f"Alert type '{body.alert_type}' is not available on your plan"
            )
        
        if body.region and body.region not in AVAILABLE_REGIONS:
            raise HTTPException(status_code=400, detail=f"Invalid region: {body.region}")
        
        if max_regions != -1 and body.region:
            cursor.execute("""
                SELECT COUNT(DISTINCT region) as region_count
                FROM user_settings
                WHERE user_id = %s AND region IS NOT NULL AND enabled = TRUE
                  AND region != %s
            """, (user_id, body.region))
            count_row = cursor.fetchone()
            current_count = count_row['region_count'] if count_row else 0
            
            if current_count >= max_regions:
                raise HTTPException(
                    status_code=403,
                    detail=f"You can only configure alerts for {max_regions} region(s) on your plan. Please remove a region or upgrade."
                )
        
        try:
            cursor.execute("""
                INSERT INTO user_settings (user_id, alert_type, region, enabled)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (user_id, alert_type, region, asset) 
                DO UPDATE SET enabled = EXCLUDED.enabled, updated_at = NOW()
                RETURNING id
            """, (user_id, body.alert_type, body.region, body.enabled))
            result = cursor.fetchone()
            setting_id = result['id'] if result else None
        except Exception as e:
            logger.error(f"Error adding user setting: {e}")
            raise HTTPException(status_code=500, detail="Failed to save setting")
    
    return {
        "success": True,
        "id": setting_id,
        "alert_type": body.alert_type,
        "region": body.region,
        "enabled": body.enabled
    }


@router.delete("/settings/{setting_id}")
def delete_user_setting(setting_id: int, x_user_token: Optional[str] = Header(None)):
    """Delete a user alert setting."""
    session = verify_user_session(x_user_token)
    user_id = session["user_id"]
    
    with get_cursor() as cursor:
        cursor.execute("""
            DELETE FROM user_settings
            WHERE id = %s AND user_id = %s
            RETURNING id
        """, (setting_id, user_id))
        deleted = cursor.fetchone()
        
        if not deleted:
            raise HTTPException(status_code=404, detail="Setting not found")
    
    return {"success": True, "deleted_id": setting_id}


VALID_INDEX_CODES = ['geri', 'eeri', 'egsi', 'daily_digest']

@router.get("/delivery-preferences")
def get_delivery_preferences(x_user_token: Optional[str] = Header(None)):
    """Get user delivery preferences for index notifications."""
    session = verify_user_session(x_user_token)
    user_id = session["user_id"]
    
    with get_cursor() as cursor:
        cursor.execute("""
            INSERT INTO user_delivery_preferences (user_id, index_code, email_enabled, telegram_enabled)
            SELECT %s, code, FALSE, FALSE
            FROM unnest(%s::text[]) AS code
            ON CONFLICT (user_id, index_code) DO NOTHING
        """, (user_id, VALID_INDEX_CODES))
        
        cursor.execute("""
            SELECT index_code, email_enabled, telegram_enabled
            FROM user_delivery_preferences
            WHERE user_id = %s
            ORDER BY index_code
        """, (user_id,))
        rows = cursor.fetchall()
    
    prefs = {}
    for row in rows:
        prefs[row['index_code']] = {
            'email': row['email_enabled'],
            'telegram': row['telegram_enabled']
        }
    
    return {"preferences": prefs}


@router.put("/delivery-preferences")
def update_delivery_preferences(body: DeliveryPreferencesRequest, x_user_token: Optional[str] = Header(None)):
    """Update user delivery preferences for index notifications."""
    session = verify_user_session(x_user_token)
    user_id = session["user_id"]
    
    user_plan = execute_one(
        "SELECT COALESCE(up.plan, 'free') as plan FROM users u LEFT JOIN user_plans up ON u.id = up.user_id WHERE u.id = %s",
        (user_id,)
    )
    is_free = (not user_plan or user_plan['plan'] == 'free')
    
    updates = [
        ('geri', False if is_free else body.geri_email, body.geri_telegram),
        ('eeri', False if is_free else body.eeri_email, body.eeri_telegram),
        ('egsi', False if is_free else body.egsi_email, body.egsi_telegram),
        ('daily_digest', False if is_free else body.daily_digest_email, body.daily_digest_telegram),
    ]
    
    with get_cursor() as cursor:
        for index_code, email_on, tg_on in updates:
            cursor.execute("""
                INSERT INTO user_delivery_preferences (user_id, index_code, email_enabled, telegram_enabled)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (user_id, index_code)
                DO UPDATE SET email_enabled = EXCLUDED.email_enabled,
                              telegram_enabled = EXCLUDED.telegram_enabled,
                              updated_at = NOW()
            """, (user_id, index_code, email_on, tg_on))
    
    logger.info(f"Updated delivery preferences for user {user_id}")
    return {"success": True}


@router.get("/dashboard")
def get_user_dashboard(x_user_token: Optional[str] = Header(None), alerts_limit: int = 100):
    """
    Combined endpoint that returns user data, alerts, and settings in a single request.
    This reduces the number of API calls needed to load the dashboard from 4 to 1.
    """
    session = verify_user_session(x_user_token)
    user_id = session["user_id"]
    
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT u.id, u.email, u.telegram_chat_id, u.created_at,
                   COALESCE(up.plan, 'free') as plan
            FROM users u
            LEFT JOIN user_plans up ON u.id = up.user_id
            WHERE u.id = %s
        """, (user_id,))
        user = cursor.fetchone()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        plan_code = user['plan']
        plan_settings = get_plan_settings(plan_code)
        allowed_types = plan_settings.get("allowed_alert_types", [])
        max_regions = plan_settings.get("max_regions", 1)
        
        has_all = 'ALL' in allowed_types
        effective_allowed = ALL_ALERT_TYPES if has_all else allowed_types
        locked_types = [t for t in ALL_ALERT_TYPES if t not in effective_allowed]
        
        cursor.execute("""
            SELECT id, alert_type, region, asset, enabled, created_at
            FROM user_settings
            WHERE user_id = %s
            ORDER BY alert_type, region
        """, (user_id,))
        settings_rows = cursor.fetchall()
        
        cursor.execute("""
            SELECT COUNT(DISTINCT region) as region_count
            FROM user_settings
            WHERE user_id = %s AND region IS NOT NULL AND enabled = TRUE
        """, (user_id,))
        region_count_row = cursor.fetchone()
        current_region_count = region_count_row['region_count'] if region_count_row else 0
        
        user_settings_enabled = [s for s in settings_rows if s['enabled']]
        has_user_settings = len(user_settings_enabled) > 0
        
        user_setting_filters = []
        if has_user_settings:
            for setting in user_settings_enabled:
                if setting['alert_type'] in effective_allowed:
                    user_setting_filters.append({
                        'alert_type': setting['alert_type'],
                        'region': setting['region'],
                        'asset': setting['asset']
                    })
        
        alerts = []
        three_hours_ago = datetime.utcnow() - timedelta(hours=3)
        
        if effective_allowed:
            try:
                cursor.execute("""
                    SELECT uad.id, ae.alert_type, ae.scope_region as region, ae.scope_assets as assets,
                           ae.severity, ae.headline as title, ae.body as message,
                           uad.channel, uad.status, ae.created_at, uad.sent_at
                    FROM user_alert_deliveries uad
                    JOIN alert_events ae ON uad.alert_event_id = ae.id
                    WHERE uad.user_id = %s
                      AND ae.alert_type = ANY(%s)
                      AND uad.status IN ('sent', 'skipped')
                    ORDER BY ae.created_at DESC
                    LIMIT 100
                """, (user_id, effective_allowed,))
                delivered_alerts = cursor.fetchall()
            except Exception as e:
                import logging
                logging.warning(f"Dashboard alert query failed: {e}")
                delivered_alerts = []
            
            for row in delivered_alerts:
                if has_user_settings:
                    matches_setting = False
                    for flt in user_setting_filters:
                        type_match = row['alert_type'] == flt['alert_type']
                        region_match = flt['region'] is None or row['region'] == flt['region']
                        if type_match and region_match:
                            matches_setting = True
                            break
                    if not matches_setting:
                        continue
                
                assets_list = row['assets'] if row['assets'] else []
                asset_str = assets_list[0] if len(assets_list) == 1 else ', '.join(assets_list) if assets_list else None
                is_latest = row['created_at'] and row['created_at'] > three_hours_ago
                alerts.append({
                    "id": row['id'],
                    "alert_type": row['alert_type'],
                    "region": row['region'],
                    "asset": asset_str,
                    "severity": row['severity'],
                    "title": row['title'],
                    "message": row['message'],
                    "channel": row['channel'],
                    "status": row['status'],
                    "created_at": row['created_at'].isoformat() if row['created_at'] else None,
                    "sent_at": row['sent_at'].isoformat() if row['sent_at'] else None,
                    "is_latest": is_latest,
                    "allowed_by_plan": True
                })
            
            if not alerts:
                try:
                    cursor.execute("""
                        SELECT id, alert_type, scope_region as region, scope_assets as assets,
                               severity, headline as title, body as message, created_at
                        FROM alert_events
                        WHERE alert_type = ANY(%s)
                          AND created_at > NOW() - INTERVAL '7 days'
                        ORDER BY created_at DESC
                        LIMIT %s
                    """, (effective_allowed, alerts_limit,))
                    available_alerts = cursor.fetchall()
                except Exception as e:
                    import logging
                    logging.warning(f"Dashboard fallback query failed: {e}")
                    available_alerts = []
                
                for row in available_alerts:
                    if has_user_settings:
                        matches_setting = False
                        for flt in user_setting_filters:
                            type_match = row['alert_type'] == flt['alert_type']
                            region_match = flt['region'] is None or row['region'] == flt['region']
                            if type_match and region_match:
                                matches_setting = True
                                break
                        if not matches_setting:
                            continue
                    
                    assets_list = row['assets'] if row['assets'] else []
                    asset_str = assets_list[0] if len(assets_list) == 1 else ', '.join(assets_list) if assets_list else None
                    is_latest = row['created_at'] and row['created_at'] > three_hours_ago
                    alerts.append({
                        "id": row['id'],
                        "alert_type": row['alert_type'],
                        "region": row['region'],
                        "asset": asset_str,
                        "severity": row['severity'],
                        "title": row['title'],
                        "message": row['message'],
                        "channel": None,
                        "status": "available",
                        "created_at": row['created_at'].isoformat() if row['created_at'] else None,
                        "sent_at": None,
                        "is_latest": is_latest,
                        "allowed_by_plan": True
                    })
        
        cursor.execute("""
            INSERT INTO user_delivery_preferences (user_id, index_code, email_enabled, telegram_enabled)
            SELECT %s, code, FALSE, FALSE
            FROM unnest(%s::text[]) AS code
            ON CONFLICT (user_id, index_code) DO NOTHING
        """, (user_id, VALID_INDEX_CODES))
        cursor.execute("""
            SELECT index_code, email_enabled, telegram_enabled
            FROM user_delivery_preferences
            WHERE user_id = %s
        """, (user_id,))
        delivery_pref_rows = cursor.fetchall()
        delivery_prefs = {}
        for row in delivery_pref_rows:
            delivery_prefs[row['index_code']] = {
                'email': row['email_enabled'],
                'telegram': row['telegram_enabled']
            }
        
        locked_samples = []
        if locked_types:
            try:
                cursor.execute("""
                    SELECT alert_type, scope_region as region, scope_assets as assets,
                           severity, headline as title, body as message, created_at
                    FROM alert_events
                    WHERE alert_type = ANY(%s)
                    ORDER BY created_at DESC
                    LIMIT 3
                """, (locked_types,))
                sample_rows = cursor.fetchall()
            except Exception as e:
                import logging
                logging.warning(f"Dashboard locked samples query failed: {e}")
                sample_rows = []
            
            for row in sample_rows:
                assets_list = row['assets'] if row['assets'] else []
                asset_str = assets_list[0] if len(assets_list) == 1 else ', '.join(assets_list) if assets_list else None
                locked_samples.append({
                    "alert_type": row['alert_type'],
                    "region": row['region'],
                    "asset": asset_str,
                    "severity": row['severity'],
                    "title": row['title'],
                    "message": row['message'][:100] + "..." if row['message'] and len(row['message']) > 100 else row['message'],
                    "created_at": row['created_at'].isoformat() if row['created_at'] else None
                })
    
    return {
        "user": {
            "id": user['id'],
            "email": user['email'],
            "telegram_chat_id": user['telegram_chat_id'],
            "created_at": user['created_at'].isoformat() if user['created_at'] else None,
            "plan": plan_code,
            "plan_settings": {
                "display_name": plan_settings.get("display_name", plan_code.title()),
                "allowed_alert_types": plan_settings.get("allowed_alert_types", []),
                "max_regions": max_regions,
                "max_email_alerts_per_day": plan_settings.get("max_email_alerts_per_day", 2),
                "delivery_config": plan_settings.get("delivery_config", {})
            }
        },
        "alerts": {
            "items": alerts[:alerts_limit],
            "total": len(alerts),
            "allowed_types": effective_allowed,
            "locked_types": locked_types,
            "locked_samples": locked_samples,
            "has_user_settings": has_user_settings
        },
        "settings": {
            "plan": plan_code,
            "allowed_alert_types": effective_allowed,
            "max_regions": max_regions,
            "current_region_count": current_region_count,
            "available_regions": AVAILABLE_REGIONS,
            "items": [
                {
                    "id": s['id'],
                    "alert_type": s['alert_type'],
                    "region": s['region'],
                    "asset": s['asset'],
                    "enabled": s['enabled'],
                    "created_at": s['created_at'].isoformat() if s['created_at'] else None
                }
                for s in settings_rows
            ]
        },
        "delivery_preferences": delivery_prefs
    }
