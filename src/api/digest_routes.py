from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from src.db.db import execute_one, get_cursor
from src.alerts.alerts_engine import PLAN_DEFAULTS
from src.alerts.digest_worker import build_digest_content

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


@router.post("/preview")
def preview_digest(request: DigestPreviewRequest):
    if request.plan not in ['free', 'trader', 'pro']:
        raise HTTPException(status_code=400, detail="Plan must be free, trader, or pro")
    
    user_id = get_or_create_user(request.email)
    create_user_plan(user_id, request.plan)
    
    subject, body = build_digest_content('Europe')
    
    plan_info = PLAN_DEFAULTS[request.plan]
    digest_enabled = plan_info['daily_digest_enabled']
    
    return {
        "user_id": user_id,
        "email": request.email,
        "plan": request.plan,
        "digest_enabled": digest_enabled,
        "subject": subject,
        "body": body,
        "note": "Free plan users do not receive daily digests. Upgrade to Trader or Pro." if not digest_enabled else None
    }
