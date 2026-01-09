import os
from fastapi import APIRouter, Query, HTTPException, Path
from pydantic import BaseModel, EmailStr
from typing import Optional
from src.db.db import execute_query, execute_one, get_cursor
from src.alerts.alerts_engine import run_alerts_engine, PLAN_DEFAULTS
from src.alerts.channels import send_email

router = APIRouter(prefix="/alerts", tags=["alerts"])


class TestAlertRequest(BaseModel):
    email: str
    plan: str = "free"


class SendTestEmailRequest(BaseModel):
    email: str


def get_or_create_user(email: str) -> int:
    result = execute_one("SELECT id FROM users WHERE email = %s", (email,))
    if result:
        return result['id']
    
    with get_cursor() as cursor:
        cursor.execute(
            "INSERT INTO users (email) VALUES (%s) RETURNING id",
            (email,)
        )
        row = cursor.fetchone()
        return row['id']


def create_user_plan(user_id: int, plan: str):
    defaults = PLAN_DEFAULTS.get(plan, PLAN_DEFAULTS['free'])
    
    with get_cursor() as cursor:
        cursor.execute(
            """INSERT INTO user_plans (user_id, plan, alerts_delay_minutes, max_alerts_per_day,
                                       allow_asset_alerts, allow_telegram, daily_digest_enabled)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (user_id) DO UPDATE SET
                   plan = EXCLUDED.plan,
                   alerts_delay_minutes = EXCLUDED.alerts_delay_minutes,
                   max_alerts_per_day = EXCLUDED.max_alerts_per_day,
                   allow_asset_alerts = EXCLUDED.allow_asset_alerts,
                   allow_telegram = EXCLUDED.allow_telegram,
                   daily_digest_enabled = EXCLUDED.daily_digest_enabled,
                   updated_at = NOW()""",
            (user_id, plan, defaults['alerts_delay_minutes'], defaults['max_alerts_per_day'],
             defaults['allow_asset_alerts'], defaults['allow_telegram'], defaults['daily_digest_enabled'])
        )


def create_default_prefs(user_id: int, plan: str):
    with get_cursor() as cursor:
        cursor.execute("DELETE FROM user_alert_prefs WHERE user_id = %s", (user_id,))
        
        cursor.execute(
            """INSERT INTO user_alert_prefs (user_id, region, alert_type, threshold, cooldown_minutes)
               VALUES (%s, 'Europe', 'REGIONAL_RISK_SPIKE', 70, 120)""",
            (user_id,)
        )
        
        if plan in ['trader', 'pro']:
            for asset in ['oil', 'gas', 'fx', 'freight']:
                cursor.execute(
                    """INSERT INTO user_alert_prefs (user_id, region, alert_type, asset, threshold, cooldown_minutes)
                       VALUES (%s, 'Europe', 'ASSET_RISK_SPIKE', %s, 70, 120)""",
                    (user_id, asset)
                )
            
            cursor.execute(
                """INSERT INTO user_alert_prefs (user_id, region, alert_type, cooldown_minutes)
                   VALUES (%s, 'Europe', 'HIGH_IMPACT_EVENT', 60)""",
                (user_id,)
            )


@router.post("/test")
def test_alerts(request: TestAlertRequest):
    if request.plan not in ['free', 'trader', 'pro']:
        raise HTTPException(status_code=400, detail="Plan must be free, trader, or pro")
    
    user_id = get_or_create_user(request.email)
    
    create_user_plan(user_id, request.plan)
    create_default_prefs(user_id, request.plan)
    
    alerts = run_alerts_engine(dry_run=True, user_id_filter=user_id)
    
    plan_features = PLAN_DEFAULTS[request.plan]
    
    return {
        "user_id": user_id,
        "email": request.email,
        "plan": request.plan,
        "plan_features": {
            "delay_minutes": plan_features['alerts_delay_minutes'],
            "max_per_day": plan_features['max_alerts_per_day'],
            "asset_alerts": plan_features['allow_asset_alerts'],
            "telegram": plan_features['allow_telegram'],
            "daily_digest": plan_features['daily_digest_enabled']
        },
        "alert_previews": [
            {
                "type": a.get('alert_type'),
                "region": a.get('region'),
                "asset": a.get('asset'),
                "title": a.get('title'),
                "triggered_value": a.get('triggered_value'),
                "threshold": a.get('threshold'),
                "channel": a.get('channel', 'email'),
                "message_preview": a.get('message', '')[:300] + "..."
            }
            for a in alerts
        ],
        "message": f"Test completed. {len(alerts)} alerts would be generated."
    }


@router.get("/user/{user_id}")
def get_user_alerts(
    user_id: int = Path(..., description="User ID"),
    limit: int = Query(50, ge=1, le=200)
):
    user = execute_one("SELECT id, email FROM users WHERE id = %s", (user_id,))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    query = """
    SELECT id, alert_type, region, asset, triggered_value, threshold,
           title, message, channel, status, created_at, sent_at, error
    FROM alerts
    WHERE user_id = %s
    ORDER BY created_at DESC
    LIMIT %s
    """
    results = execute_query(query, (user_id, limit))
    
    alerts = []
    for row in results:
        alerts.append({
            "id": row['id'],
            "alert_type": row['alert_type'],
            "region": row['region'],
            "asset": row['asset'],
            "triggered_value": row['triggered_value'],
            "threshold": row['threshold'],
            "title": row['title'],
            "message": row['message'][:200] + "..." if len(row['message']) > 200 else row['message'],
            "channel": row['channel'],
            "status": row['status'],
            "created_at": row['created_at'].isoformat() if row['created_at'] else None,
            "sent_at": row['sent_at'].isoformat() if row['sent_at'] else None,
            "error": row['error']
        })
    
    return {
        "user_id": user_id,
        "email": user['email'],
        "count": len(alerts),
        "alerts": alerts
    }


@router.post("/send-test-email")
def send_test_email(request: SendTestEmailRequest):
    from src.alerts.channels import EMAIL_PROVIDER, EMAIL_FROM, BREVO_API_KEY
    
    if EMAIL_PROVIDER != 'brevo':
        raise HTTPException(
            status_code=500, 
            detail=f"EMAIL_PROVIDER must be 'brevo' for test emails. Current: '{EMAIL_PROVIDER}'"
        )
    
    if not BREVO_API_KEY:
        raise HTTPException(status_code=500, detail="BREVO_API_KEY is not configured")
    
    if not EMAIL_FROM or EMAIL_FROM == 'alerts@energyriskiq.com':
        from_env = os.environ.get('EMAIL_FROM', '')
        if not from_env:
            raise HTTPException(status_code=500, detail="EMAIL_FROM is not configured in environment")
    
    subject = "EnergyRiskIQ – Test Email"
    body = """This is a test email from EnergyRiskIQ.

If you received this, your Brevo email configuration is working correctly.

-- EnergyRiskIQ Alerts System"""
    
    success, error, message_id = send_email(request.email, subject, body)
    
    if not success:
        raise HTTPException(status_code=500, detail=error)
    
    return {
        "status": "sent",
        "provider": EMAIL_PROVIDER,
        "to": request.email,
        "from": EMAIL_FROM,
        "message_id": message_id
    }
