from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from src.db.db import execute_one, get_cursor
from src.alerts.digest_worker import build_digest_content
from src.plans.plan_helpers import get_plan_settings

router = APIRouter(prefix="/digest", tags=["digest"])


class DigestPreviewRequest(BaseModel):
    email: str
    plan: str = "trader"


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
    try:
        settings = get_plan_settings(plan)
    except ValueError:
        settings = get_plan_settings('free')
        plan = 'free'
    
    delivery_config = settings.get('delivery_config', {})
    allow_telegram = delivery_config.get('telegram', False)
    daily_digest = 'DAILY_DIGEST' in settings.get('allowed_alert_types', [])
    allow_asset = 'ASSET_RISK_SPIKE' in settings.get('allowed_alert_types', [])
    alerts_delay = 60 if plan == 'free' else 0
    
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
            (user_id, plan, alerts_delay, settings['max_email_alerts_per_day'],
             allow_asset, allow_telegram, daily_digest)
        )


@router.post("/preview")
def preview_digest(request: DigestPreviewRequest):
    valid_plans = ['free', 'personal', 'trader', 'pro', 'enterprise']
    if request.plan not in valid_plans:
        raise HTTPException(status_code=400, detail=f"Plan must be one of: {', '.join(valid_plans)}")
    
    user_id = get_or_create_user(request.email)
    create_user_plan(user_id, request.plan)
    
    subject, body = build_digest_content('Europe')
    
    try:
        settings = get_plan_settings(request.plan)
    except ValueError:
        settings = get_plan_settings('free')
    
    allowed_alert_types = settings.get('allowed_alert_types', [])
    digest_enabled = 'DAILY_DIGEST' in allowed_alert_types
    
    return {
        "user_id": user_id,
        "email": request.email,
        "plan": request.plan,
        "digest_enabled": digest_enabled,
        "subject": subject,
        "body": body,
        "note": "Free and Personal plan users do not receive daily digests. Upgrade to Trader or higher." if not digest_enabled else None
    }
