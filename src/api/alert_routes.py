import os
from fastapi import APIRouter, Query, HTTPException, Path
from pydantic import BaseModel, EmailStr
from typing import Optional, List
from src.db.db import execute_query, execute_one, get_cursor
from src.alerts.alerts_engine import run_alerts_engine
from src.alerts.channels import send_email
from src.plans.plan_helpers import get_plan_settings, create_user_plan as create_plan, VALID_PLAN_CODES

router = APIRouter(prefix="/alerts", tags=["alerts"])

ALERTS_V2_ENABLED = os.environ.get('ALERTS_V2_ENABLED', 'true').lower() == 'true'


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
        return row['id'] if row else 0


def create_default_prefs(user_id: int, plan: str):
    try:
        settings = get_plan_settings(plan)
        allowed_types = settings.get('allowed_alert_types', [])
        allow_asset_alerts = 'ASSET_RISK_SPIKE' in allowed_types or 'ALL' in allowed_types
    except ValueError:
        allow_asset_alerts = False
    
    with get_cursor() as cursor:
        cursor.execute("DELETE FROM user_alert_prefs WHERE user_id = %s", (user_id,))
        
        cursor.execute(
            """INSERT INTO user_alert_prefs (user_id, region, alert_type, threshold, cooldown_minutes)
               VALUES (%s, 'Europe', 'REGIONAL_RISK_SPIKE', 70, 120)""",
            (user_id,)
        )
        
        if allow_asset_alerts:
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
    if request.plan not in VALID_PLAN_CODES:
        raise HTTPException(status_code=400, detail=f"Plan must be one of: {', '.join(VALID_PLAN_CODES)}")
    
    user_id = get_or_create_user(request.email)
    
    create_plan(user_id, request.plan)
    create_default_prefs(user_id, request.plan)
    
    alerts = run_alerts_engine(dry_run=True, user_id_filter=user_id)
    
    try:
        plan_settings = get_plan_settings(request.plan)
    except ValueError:
        plan_settings = get_plan_settings('free')
    
    delivery_config = plan_settings.get('delivery_config', {})
    allowed_alert_types = plan_settings.get('allowed_alert_types', [])
    
    return {
        "user_id": user_id,
        "email": request.email,
        "plan": request.plan,
        "plan_features": {
            "delay_minutes": 60 if request.plan == 'free' else 0,
            "max_per_day": plan_settings['max_email_alerts_per_day'],
            "asset_alerts": 'ASSET_RISK_SPIKE' in allowed_alert_types or 'ALL' in allowed_alert_types,
            "telegram": delivery_config.get('telegram', False),
            "daily_digest": 'DAILY_DIGEST' in allowed_alert_types or 'ALL' in allowed_alert_types
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
    if results:
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


@router.get("/events/latest")
def get_latest_alert_events(
    limit: int = Query(20, ge=1, le=100),
    alert_type: Optional[str] = Query(None)
):
    base_query = """
    SELECT id, alert_type, scope_region, scope_assets, severity, 
           headline, body, driver_event_ids, created_at
    FROM alert_events
    """
    
    conditions = []
    params = []
    
    if alert_type:
        conditions.append("alert_type = %s")
        params.append(alert_type)
    
    if conditions:
        base_query += " WHERE " + " AND ".join(conditions)
    
    base_query += " ORDER BY created_at DESC LIMIT %s"
    params.append(limit)
    
    results = execute_query(base_query, tuple(params))
    
    events = []
    if results:
        for row in results:
            events.append({
                "id": row['id'],
                "alert_type": row['alert_type'],
                "scope_region": row['scope_region'],
                "scope_assets": row['scope_assets'] or [],
                "severity": row['severity'],
                "headline": row['headline'],
                "body": row['body'][:500] + "..." if len(row['body']) > 500 else row['body'],
                "driver_event_ids": row['driver_event_ids'] or [],
                "created_at": row['created_at'].isoformat() if row['created_at'] else None
            })
    
    return {
        "count": len(events),
        "events": events
    }


@router.get("/user/{user_id}/deliveries")
def get_user_deliveries(
    user_id: int = Path(..., description="User ID"),
    limit: int = Query(50, ge=1, le=200),
    channel: Optional[str] = Query(None),
    status: Optional[str] = Query(None)
):
    user = execute_one("SELECT id, email FROM users WHERE id = %s", (user_id,))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    base_query = """
    SELECT d.id, d.alert_event_id, d.channel, d.status, d.reason,
           d.provider_message_id, d.created_at, d.sent_at,
           ae.alert_type, ae.scope_region, ae.headline, ae.severity
    FROM user_alert_deliveries d
    JOIN alert_events ae ON ae.id = d.alert_event_id
    WHERE d.user_id = %s
    """
    
    params = [user_id]
    
    if channel:
        base_query += " AND d.channel = %s"
        params.append(channel)
    
    if status:
        base_query += " AND d.status = %s"
        params.append(status)
    
    base_query += " ORDER BY d.created_at DESC LIMIT %s"
    params.append(limit)
    
    results = execute_query(base_query, tuple(params))
    
    deliveries = []
    if results:
        for row in results:
            deliveries.append({
                "id": row['id'],
                "alert_event_id": row['alert_event_id'],
                "alert_type": row['alert_type'],
                "headline": row['headline'],
                "scope_region": row['scope_region'],
                "severity": row['severity'],
                "channel": row['channel'],
                "status": row['status'],
                "reason": row['reason'],
                "created_at": row['created_at'].isoformat() if row['created_at'] else None,
                "sent_at": row['sent_at'].isoformat() if row['sent_at'] else None
            })
    
    return {
        "user_id": user_id,
        "email": user['email'],
        "count": len(deliveries),
        "deliveries": deliveries
    }


@router.get("/me")
def get_my_alerts(
    user_id: int = Query(..., description="User ID (will be replaced by auth)"),
    limit: int = Query(50, ge=1, le=200)
):
    if ALERTS_V2_ENABLED:
        user = execute_one("SELECT id, email FROM users WHERE id = %s", (user_id,))
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        query = """
        SELECT d.id, d.alert_event_id, d.channel, d.status, d.reason,
               d.created_at, d.sent_at,
               ae.alert_type, ae.scope_region, ae.headline, ae.body, ae.severity
        FROM user_alert_deliveries d
        JOIN alert_events ae ON ae.id = d.alert_event_id
        WHERE d.user_id = %s
        ORDER BY d.created_at DESC
        LIMIT %s
        """
        results = execute_query(query, (user_id, limit))
        
        alerts = []
        if results:
            for row in results:
                alerts.append({
                    "id": row['id'],
                    "alert_event_id": row['alert_event_id'],
                    "alert_type": row['alert_type'],
                    "headline": row['headline'],
                    "message": row['body'][:300] + "..." if len(row['body']) > 300 else row['body'],
                    "region": row['scope_region'],
                    "severity": row['severity'],
                    "channel": row['channel'],
                    "status": row['status'],
                    "created_at": row['created_at'].isoformat() if row['created_at'] else None,
                    "sent_at": row['sent_at'].isoformat() if row['sent_at'] else None
                })
        
        return {
            "user_id": user_id,
            "email": user['email'],
            "count": len(alerts),
            "alerts": alerts
        }
    else:
        return get_user_alerts(user_id, limit)
