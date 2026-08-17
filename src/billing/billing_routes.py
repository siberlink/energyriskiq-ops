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
    ensure_stripe_initialized,
    get_stripe_publishable_key,
    create_customer,
    create_checkout_session,
    create_billing_portal_session,
    cancel_subscription,
    update_subscription,
    get_subscription,
    construct_webhook_event,
    get_webhook_secret,
    get_stripe_mode,
    get_plan_stripe_ids,
    get_free_trial_days,
    get_banner_settings
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
    mode = get_stripe_mode()
    with get_cursor(commit=False) as cur:
        if mode == "sandbox":
            cur.execute("""
                SELECT plan_code, display_name, monthly_price_usd, currency, 
                       stripe_product_id_sandbox as stripe_product_id,
                       stripe_price_id_sandbox as stripe_price_id,
                       allowed_alert_types, max_regions
                FROM plan_settings 
                WHERE plan_code = %s
            """, (plan_code,))
        else:
            cur.execute("""
                SELECT plan_code, display_name, monthly_price_usd, currency, 
                       stripe_product_id, stripe_price_id, allowed_alert_types, max_regions
                FROM plan_settings 
                WHERE plan_code = %s
            """, (plan_code,))
        return cur.fetchone()


def get_all_plans():
    mode = get_stripe_mode()
    with get_cursor(commit=False) as cur:
        if mode == "sandbox":
            cur.execute("""
                SELECT plan_code, display_name, monthly_price_usd as price, currency,
                       stripe_product_id_sandbox as stripe_product_id,
                       stripe_price_id_sandbox as stripe_price_id,
                       allowed_alert_types, max_regions,
                       max_email_alerts_per_day, delivery_config
                FROM plan_settings 
                WHERE is_active = TRUE
                ORDER BY monthly_price_usd ASC
            """)
        else:
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
    trial_days = get_free_trial_days()
    banner = get_banner_settings()
    return {
        "free_trial_days": trial_days,
        "banner_enabled": banner["banner_enabled"],
        "banner_countdown_end": banner["banner_countdown_end"],
        "banner_version": banner.get("banner_version", "none"),
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
        
        is_upgrade_fallback = False
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
            except stripe.InvalidRequestError as e:
                logger.warning(f"Subscription {user['stripe_subscription_id']} invalid (likely sandbox), clearing and creating new checkout: {e}")
                is_upgrade_fallback = True
                with get_cursor() as cur:
                    cur.execute(
                        "UPDATE users SET stripe_subscription_id = NULL, subscription_status = NULL WHERE id = %s",
                        (user["id"],)
                    )
            except Exception as e:
                logger.warning(f"Could not update existing subscription, creating new checkout: {e}")
                is_upgrade_fallback = True
        
        customer_id = user["stripe_customer_id"]
        if customer_id:
            try:
                stripe.Customer.retrieve(customer_id)
            except stripe.InvalidRequestError:
                logger.warning(f"Stripe customer {customer_id} not found (likely sandbox ID), creating new customer for user {user['id']}")
                customer_id = None
                with get_cursor() as cur:
                    cur.execute(
                        "UPDATE users SET stripe_customer_id = NULL, stripe_subscription_id = NULL, subscription_status = NULL WHERE id = %s",
                        (user["id"],)
                    )
        
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
        
        trial_days = 0 if is_upgrade_fallback else get_free_trial_days()
        
        session = await create_checkout_session(
            customer_id=customer_id,
            price_id=plan["stripe_price_id"],
            success_url=f"{base_url}/users/account?billing=success&plan={request.plan_code}",
            cancel_url=f"{base_url}/users/account?billing=cancelled",
            user_id=user["id"],
            trial_period_days=trial_days if trial_days > 0 else None
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
    
    webhook_secret = get_webhook_secret()
    if not webhook_secret:
        mode = get_stripe_mode()
        logger.error(f"Webhook secret not configured for {mode} mode - rejecting webhook")
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


# ─────────────────────────────────────────────────────────────────────────────
# Banner Offer — €28/month "Unlimited Access" checkout
# ─────────────────────────────────────────────────────────────────────────────

BANNER_OFFER_PLAN_CODE  = "banner_offer"
BANNER_OFFER_EUR_CENTS  = 2800           # €28.00/month
BANNER_OFFER_NAME       = "Unlimited Access to EnergyRiskIQ's Features"
BANNER_OFFER_DESC       = ("Full unlimited access to all EnergyRiskIQ features: "
                            "Proprietary Indices, Daily Intelligence Digest, Pro Widgets, "
                            "Alerts, and Indices History. €28/month after a free trial.")
# On successful payment, apply this base plan to the user
BANNER_OFFER_GRANTS_PLAN = "pro"


def _banner_settings_key(name: str) -> str:
    return f"{name}_{get_stripe_mode()}"


def _get_banner_offer_price_id() -> Optional[str]:
    key = _banner_settings_key("banner_offer_price_id")
    try:
        with get_cursor(commit=False) as cur:
            cur.execute("SELECT value FROM app_settings WHERE key = %s", (key,))
            row = cur.fetchone()
            return row["value"] if row else None
    except Exception:
        return None


def _store_banner_offer_price_id(price_id: str, product_id: str):
    with get_cursor() as cur:
        for k, v in (("banner_offer_price_id", price_id),
                     ("banner_offer_product_id", product_id)):
            key = _banner_settings_key(k)
            cur.execute("""
                INSERT INTO app_settings (key, value, updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (key) DO UPDATE
                  SET value = EXCLUDED.value, updated_at = NOW()
            """, (key, v))


def _get_or_create_banner_offer_product():
    ensure_stripe_initialized()
    try:
        existing = stripe.Product.search(
            query=f"metadata['plan_code']:'{BANNER_OFFER_PLAN_CODE}'"
        )
        if existing.data:
            return existing.data[0]
    except Exception as e:
        logger.warning(f"Stripe banner product search failed (will create): {e}")
    product = stripe.Product.create(
        name=BANNER_OFFER_NAME,
        description=BANNER_OFFER_DESC,
        metadata={"plan_code": BANNER_OFFER_PLAN_CODE, "kind": "subscription"},
    )
    logger.info(f"Created Stripe product {product.id} for Banner Offer")
    return product


def ensure_banner_offer_price_id() -> str:
    """Return the Stripe price ID for the €28/month banner offer (lazy, idempotent)."""
    cached = _get_banner_offer_price_id()
    if cached:
        return cached
    ensure_stripe_initialized()
    product = _get_or_create_banner_offer_product()
    price_id = None
    for p in stripe.Price.list(product=product.id, active=True, limit=100).data:
        if (p.unit_amount == BANNER_OFFER_EUR_CENTS
                and p.currency == "eur"
                and p.recurring
                and p.recurring.get("interval") == "month"):
            price_id = p.id
            break
    if not price_id:
        price = stripe.Price.create(
            product=product.id,
            unit_amount=BANNER_OFFER_EUR_CENTS,
            currency="eur",
            recurring={"interval": "month"},
            metadata={"plan_code": BANNER_OFFER_PLAN_CODE},
        )
        price_id = price.id
        logger.info(f"Created Stripe price {price_id} for Banner Offer (€28/mo)")
    _store_banner_offer_price_id(price_id, product.id)
    return price_id


def handle_banner_offer_checkout_completed(session: dict) -> None:
    """Webhook handler: activate pro plan for the user after banner offer payment."""
    from src.plans.plan_helpers import apply_plan_settings_to_user
    user_id = session.get("metadata", {}).get("user_id")
    if not user_id:
        logger.error("banner_offer webhook: no user_id in metadata")
        return
    user_id = int(user_id)
    subscription_id = session.get("subscription")
    try:
        with get_cursor() as cur:
            if subscription_id:
                cur.execute("""
                    UPDATE users
                    SET stripe_subscription_id = %s,
                        subscription_status = 'active'
                    WHERE id = %s
                """, (subscription_id, user_id))
        apply_plan_settings_to_user(user_id, BANNER_OFFER_GRANTS_PLAN)
        logger.info(f"Banner offer: user {user_id} upgraded to {BANNER_OFFER_GRANTS_PLAN}")
    except Exception as e:
        logger.error(f"Banner offer checkout handler error for user {user_id}: {e}", exc_info=True)


def _base_url() -> str:
    app_url = os.environ.get("APP_URL")
    if app_url:
        return app_url.rstrip("/")
    domain = os.environ.get("REPLIT_DOMAINS", "").split(",")[0]
    if domain:
        return f"https://{domain}"
    return "http://localhost:5000"


@router.post("/banner-checkout")
async def banner_checkout(x_user_token: Optional[str] = Header(None)):
    """Start a Stripe checkout for the €28/month Unlimited Access banner offer."""
    user = get_user_from_token(x_user_token)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    init_stripe()

    try:
        price_id = ensure_banner_offer_price_id()
    except Exception as e:
        logger.error(f"Could not ensure banner offer price: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Billing not available")

    # Reuse or create Stripe customer
    customer_id = user.get("stripe_customer_id")
    if customer_id:
        try:
            stripe.Customer.retrieve(customer_id)
        except stripe.InvalidRequestError:
            customer_id = None
            with get_cursor() as cur:
                cur.execute(
                    "UPDATE users SET stripe_customer_id = NULL WHERE id = %s",
                    (user["id"],)
                )
    if not customer_id:
        cust = await create_customer(email=user["email"], user_id=user["id"])
        customer_id = cust["id"]
        with get_cursor() as cur:
            cur.execute(
                "UPDATE users SET stripe_customer_id = %s WHERE id = %s",
                (customer_id, user["id"])
            )

    trial_days = get_free_trial_days()
    base = _base_url()

    subscription_data = {
        "metadata": {
            "user_id": str(user["id"]),
            "type": BANNER_OFFER_PLAN_CODE,
        }
    }
    if trial_days and trial_days > 0:
        subscription_data["trial_period_days"] = trial_days

    try:
        session = stripe.checkout.Session.create(
            customer=customer_id,
            payment_method_types=["card"],
            line_items=[{"price": price_id, "quantity": 1}],
            mode="subscription",
            success_url=f"{base}/users/account?billing=success&plan={BANNER_OFFER_GRANTS_PLAN}",
            cancel_url=f"{base}/users/account",
            metadata={
                "user_id": str(user["id"]),
                "type": BANNER_OFFER_PLAN_CODE,
            },
            subscription_data=subscription_data,
        )
    except Exception as e:
        logger.error(f"Banner offer checkout creation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to start checkout")

    logger.info(f"Banner offer checkout started for user {user['id']}")
    return {"checkout_url": session.url}
