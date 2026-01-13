from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from src.db.db import execute_one, get_cursor
from src.alerts.digest_worker import build_digest_content
from src.plans.plan_helpers import get_plan_settings, get_allowed_alert_types, create_user_plan, VALID_PLAN_CODES

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
        return row['id'] if row else 0


@router.post("/preview")
def preview_digest(request: DigestPreviewRequest):
    if request.plan not in VALID_PLAN_CODES:
        raise HTTPException(status_code=400, detail=f"Plan must be one of: {', '.join(VALID_PLAN_CODES)}")
    
    user_id = get_or_create_user(request.email)
    create_user_plan(user_id, request.plan)
    
    subject, body = build_digest_content('Europe')
    
    try:
        allowed_alert_types = get_allowed_alert_types(request.plan)
    except ValueError:
        allowed_alert_types = get_allowed_alert_types('free')
    
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
