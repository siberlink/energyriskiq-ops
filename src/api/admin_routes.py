import os
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

router = APIRouter(prefix="/admin", tags=["admin"])

ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN") or os.environ.get("INTERNAL_RUNNER_TOKEN")


def verify_admin_token(x_admin_token: Optional[str] = Header(None)):
    if not ADMIN_TOKEN:
        raise HTTPException(status_code=500, detail="ADMIN_TOKEN not configured")
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid admin token")


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
