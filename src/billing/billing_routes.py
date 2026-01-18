from fastapi import APIRouter, Request, HTTPException, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
import logging
import os
import stripe

from src.db.db import get_cursor
from src.billing.stripe_client import (
    init_stripe, 
    get_stripe_publishable_key,
    create_customer,
    create_checkout_session,
    create_billing_portal_session,
    cancel_subscription,
    update_subscription,
    get_subscription,
    construct_webhook_event
)
from src.billing.webhook_handler import process_webhook_event
from src.plans.plan_helpers import apply_plan_settings_to_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["billing"])


class CheckoutRequest(BaseModel):
    plan_code: str


class SubscriptionUpdateRequest(BaseModel):
    new_plan_code: str


def get_user_from_token(token: Optional[str]):
    if not token:
        return None
    with get_cursor(commit=False) as cur:
        cur.execute("""
            SELECT u.id, u.email, u.stripe_customer_id, u.stripe_subscription_id, u.subscription_status
            FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token = %s AND s.expires_at > NOW()
        """, (token,))
        return cur.fetchone()


def get_plan_with_stripe_ids(plan_code: str):
    with get_cursor(commit=False) as cur:
        cur.execute("""
            SELECT plan_code, display_name, monthly_price_usd, currency, 
                   stripe_product_id, stripe_price_id, allowed_alert_types, max_regions
            FROM plan_settings 
            WHERE plan_code = %s
        """, (plan_code,))
        return cur.fetchone()


def get_all_plans():
    with get_cursor(commit=False) as cur:
        cur.execute("""
            SELECT plan_code, display_name, monthly_price_usd as price, currency,
                   stripe_product_id, stripe_price_id, allowed_alert_types, max_regions,
                   max_email_alerts_per_day, delivery_config
            FROM plan_settings 
            WHERE is_active = TRUE
            ORDER BY monthly_price_usd ASC
        """)
        return cur.fetchall()


@router.get("/config")
async def get_billing_config():
    try:
        publishable_key = get_stripe_publishable_key()
        return {"publishable_key": publishable_key}
    except Exception as e:
        logger.error(f"Error getting Stripe config: {e}")
        raise HTTPException(status_code=500, detail="Billing not configured")


@router.post("/seed-products")
async def seed_stripe_products(x_internal_token: Optional[str] = Header(None)):
    internal_token = os.environ.get("INTERNAL_RUNNER_TOKEN")
    if not internal_token or x_internal_token != internal_token:
        raise HTTPException(status_code=403, detail="Forbidden")
    
    try:
        from src.billing.seed_products import create_products_and_prices
        result = create_products_and_prices()
        return {"success": True, "products": result}
    except Exception as e:
        logger.error(f"Error seeding Stripe products: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/plans")
async def list_plans():
    plans = get_all_plans()
    return {
        "plans": [
            {
                "plan_code": p["plan_code"],
                "display_name": p["display_name"],
                "price": float(p["price"]),
                "currency": p["currency"] or "EUR",
                "stripe_price_id": p["stripe_price_id"],
                "features": {
                    "alert_types": list(p["allowed_alert_types"]) if p["allowed_alert_types"] else [],
                    "max_regions": p["max_regions"],
                    "max_email_alerts_per_day": p["max_email_alerts_per_day"]
                }
            }
            for p in plans
        ]
    }


@router.post("/checkout")
async def create_checkout(
    request: CheckoutRequest,
    x_user_token: Optional[str] = Header(None)
):
    try:
        user = get_user_from_token(x_user_token)
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        plan = get_plan_with_stripe_ids(request.plan_code)
        if not plan:
            raise HTTPException(status_code=400, detail="Invalid plan")
        
        if not plan["stripe_price_id"]:
            raise HTTPException(status_code=400, detail="Plan not available for purchase")
        
        init_stripe()
        
        if user["stripe_subscription_id"] and user["subscription_status"] in ("active", "trialing"):
            try:
                updated_sub = await update_subscription(
                    user["stripe_subscription_id"],
                    plan["stripe_price_id"]
                )
                
                apply_plan_settings_to_user(user["id"], request.plan_code)
                
                return {
                    "success": True,
                    "message": "Plan updated successfully",
                    "subscription_id": updated_sub["id"]
                }
            except Exception as e:
                logger.warning(f"Could not update existing subscription, creating new checkout: {e}")
        
        customer_id = user["stripe_customer_id"]
        if not customer_id:
            customer = await create_customer(
                email=user["email"],
                user_id=user["id"]
            )
            customer_id = customer["id"]
            
            with get_cursor() as cur:
                cur.execute(
                    "UPDATE users SET stripe_customer_id = %s WHERE id = %s",
                    (customer_id, user["id"])
                )
        
        app_url = os.environ.get("APP_URL")
        if app_url:
            base_url = app_url.rstrip("/")
        else:
            domain = os.environ.get("REPLIT_DOMAINS", "").split(",")[0]
            if domain:
                base_url = f"https://{domain}"
            else:
                base_url = "http://localhost:5000"
        
        session = await create_checkout_session(
            customer_id=customer_id,
            price_id=plan["stripe_price_id"],
            success_url=f"{base_url}/users/account?billing=success&plan={request.plan_code}",
            cancel_url=f"{base_url}/users/account?billing=cancelled",
            user_id=user["id"]
        )
        
        return {"checkout_url": session["url"], "session_id": session["id"]}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Checkout error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create checkout session: {str(e)}")


@router.post("/portal")
async def create_portal(x_user_token: Optional[str] = Header(None)):
    user = get_user_from_token(x_user_token)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    if not user["stripe_customer_id"]:
        raise HTTPException(status_code=400, detail="No billing account found")
    
    try:
        init_stripe()
        
        app_url = os.environ.get("APP_URL")
        if app_url:
            base_url = app_url.rstrip("/")
        else:
            domain = os.environ.get("REPLIT_DOMAINS", "").split(",")[0]
            if domain:
                base_url = f"https://{domain}"
            else:
                base_url = "http://localhost:5000"
        
        session = await create_billing_portal_session(
            customer_id=user["stripe_customer_id"],
            return_url=f"{base_url}/users/account"
        )
        
        return {"portal_url": session["url"]}
        
    except Exception as e:
        logger.error(f"Portal error: {e}")
        raise HTTPException(status_code=500, detail="Failed to create billing portal")


@router.get("/subscription")
async def get_user_subscription(x_user_token: Optional[str] = Header(None)):
    user = get_user_from_token(x_user_token)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    with get_cursor(commit=False) as cur:
        cur.execute("""
            SELECT up.plan, up.plan_price_usd, ps.display_name, ps.currency
            FROM user_plans up
            LEFT JOIN plan_settings ps ON ps.plan_code = up.plan
            WHERE up.user_id = %s
        """, (user["id"],))
        current_plan = cur.fetchone()
    
    subscription_info = None
    if user["stripe_subscription_id"]:
        try:
            init_stripe()
            sub = get_subscription(user["stripe_subscription_id"])
            subscription_info = {
                "id": sub["id"],
                "status": sub["status"],
                "current_period_end": sub["current_period_end"],
                "cancel_at_period_end": sub.get("cancel_at_period_end", False)
            }
        except Exception as e:
            logger.error(f"Error fetching subscription: {e}")
    
    return {
        "current_plan": {
            "plan_code": current_plan["plan"] if current_plan else "free",
            "display_name": current_plan["display_name"] if current_plan else "Free",
            "price": float(current_plan["plan_price_usd"]) if current_plan else 0,
            "currency": current_plan["currency"] if current_plan else "EUR"
        } if current_plan else None,
        "subscription": subscription_info,
        "has_billing_account": bool(user["stripe_customer_id"])
    }


@router.post("/cancel")
async def cancel_user_subscription(x_user_token: Optional[str] = Header(None)):
    user = get_user_from_token(x_user_token)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    if not user["stripe_subscription_id"]:
        raise HTTPException(status_code=400, detail="No active subscription")
    
    try:
        init_stripe()
        subscription = await cancel_subscription(
            user["stripe_subscription_id"],
            at_period_end=True
        )
        
        with get_cursor() as cur:
            cur.execute(
                "UPDATE users SET subscription_status = 'canceling' WHERE id = %s",
                (user["id"],)
            )
        
        return {
            "message": "Subscription will be cancelled at period end",
            "cancel_at": subscription.get("current_period_end")
        }
        
    except Exception as e:
        logger.error(f"Cancel subscription error: {e}")
        raise HTTPException(status_code=500, detail="Failed to cancel subscription")


@router.post("/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    
    if not sig_header:
        raise HTTPException(status_code=400, detail="Missing stripe-signature header")
    
    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET")
    if not webhook_secret:
        logger.error("STRIPE_WEBHOOK_SECRET not configured - rejecting webhook")
        raise HTTPException(status_code=500, detail="Webhook not configured")
    
    try:
        init_stripe()
        event = construct_webhook_event(payload, sig_header, webhook_secret)
        
        await process_webhook_event(event)
        
        return {"received": True}
        
    except stripe.SignatureVerificationError as e:
        logger.error(f"Webhook signature verification failed: {e}")
        raise HTTPException(status_code=400, detail="Invalid signature")
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        raise HTTPException(status_code=500, detail="Webhook processing failed")
