import logging
import stripe
from typing import Optional
from src.db.db import get_cursor
from src.plans.plan_helpers import apply_plan_settings_to_user

logger = logging.getLogger(__name__)


def get_plan_code_from_price_id(price_id: str) -> Optional[str]:
    with get_cursor(commit=False) as cur:
        cur.execute(
            "SELECT plan_code FROM plan_settings WHERE stripe_price_id = %s OR stripe_price_id_sandbox = %s",
            (price_id, price_id)
        )
        row = cur.fetchone()
        return row["plan_code"] if row else None


def update_user_subscription(
    user_id: int,
    subscription_id: str,
    status: str,
    current_period_end: Optional[int] = None
):
    with get_cursor() as cur:
        if current_period_end:
            from datetime import datetime
            period_end = datetime.utcfromtimestamp(current_period_end)
            cur.execute("""
                UPDATE users 
                SET stripe_subscription_id = %s,
                    subscription_status = %s,
                    subscription_current_period_end = %s
                WHERE id = %s
            """, (subscription_id, status, period_end, user_id))
        else:
            cur.execute("""
                UPDATE users 
                SET stripe_subscription_id = %s,
                    subscription_status = %s
                WHERE id = %s
            """, (subscription_id, status, user_id))


def get_user_id_from_customer(customer_id: str) -> Optional[int]:
    with get_cursor(commit=False) as cur:
        cur.execute(
            "SELECT id FROM users WHERE stripe_customer_id = %s",
            (customer_id,)
        )
        row = cur.fetchone()
        return row["id"] if row else None


async def handle_checkout_session_completed(session: dict):
    logger.info(f"Processing checkout.session.completed: {session['id']}")
    
    user_id = session.get("metadata", {}).get("user_id")
    if not user_id:
        customer_id = session.get("customer")
        if customer_id:
            user_id = get_user_id_from_customer(customer_id)
    
    if not user_id:
        logger.error(f"Could not find user for checkout session {session['id']}")
        return
    
    user_id = int(user_id)

    if session.get("metadata", {}).get("type") == "eriq_tokens":
        from src.api.eriq_routes import handle_token_purchase_webhook
        handle_token_purchase_webhook(session)
        return

    subscription_id = session.get("subscription")
    
    if subscription_id:
        from src.billing.stripe_client import get_subscription
        subscription = get_subscription(subscription_id)
        
        price_id = subscription["items"]["data"][0]["price"]["id"]
        plan_code = get_plan_code_from_price_id(price_id)
        
        if plan_code:
            update_user_subscription(
                user_id=user_id,
                subscription_id=subscription_id,
                status=subscription["status"],
                current_period_end=subscription.get("current_period_end")
            )
            
            apply_plan_settings_to_user(user_id, plan_code)
            logger.info(f"User {user_id} upgraded to {plan_code}")

            try:
                from src.eriq.tokens import reset_monthly_allowance_on_payment
                reset_monthly_allowance_on_payment(user_id, plan_code, session["id"])
                logger.info(f"Initial token allowance granted for user {user_id} on plan {plan_code}")
            except Exception as e:
                logger.error(f"Failed to grant initial token allowance for user {user_id}: {e}")
        else:
            logger.error(f"Could not find plan for price {price_id}")


async def handle_subscription_updated(subscription: dict):
    logger.info(f"Processing customer.subscription.updated: {subscription['id']}")
    
    customer_id = subscription.get("customer")
    user_id = get_user_id_from_customer(customer_id)
    
    if not user_id:
        logger.error(f"Could not find user for customer {customer_id}")
        return
    
    price_id = subscription["items"]["data"][0]["price"]["id"]
    plan_code = get_plan_code_from_price_id(price_id)
    
    update_user_subscription(
        user_id=user_id,
        subscription_id=subscription["id"],
        status=subscription["status"],
        current_period_end=subscription.get("current_period_end")
    )
    
    if plan_code and subscription["status"] in ("active", "trialing"):
        apply_plan_settings_to_user(user_id, plan_code)
        logger.info(f"User {user_id} subscription updated to {plan_code} (status: {subscription['status']})")

        try:
            from src.eriq.tokens import handle_plan_upgrade_tokens
            handle_plan_upgrade_tokens(user_id, plan_code, subscription["id"])
        except Exception as e:
            logger.error(f"Failed to adjust tokens on plan change for user {user_id}: {e}")


async def handle_subscription_deleted(subscription: dict):
    logger.info(f"Processing customer.subscription.deleted: {subscription['id']}")
    
    customer_id = subscription.get("customer")
    user_id = get_user_id_from_customer(customer_id)
    
    if not user_id:
        logger.error(f"Could not find user for customer {customer_id}")
        return
    
    with get_cursor() as cur:
        cur.execute("""
            UPDATE users 
            SET subscription_status = 'cancelled',
                stripe_subscription_id = NULL
            WHERE id = %s
        """, (user_id,))
    
    apply_plan_settings_to_user(user_id, "free")
    logger.info(f"User {user_id} subscription cancelled, downgraded to free")


async def handle_invoice_paid(invoice: dict):
    logger.info(f"Processing invoice.paid: {invoice['id']}")
    
    subscription_id = invoice.get("subscription")
    if not subscription_id:
        return
    
    customer_id = invoice.get("customer")
    user_id = get_user_id_from_customer(customer_id)
    
    if user_id:
        with get_cursor() as cur:
            cur.execute(
                "UPDATE users SET subscription_status = 'active' WHERE id = %s",
                (user_id,)
            )
        logger.info(f"User {user_id} invoice paid, subscription active")

        try:
            from src.billing.stripe_client import get_subscription
            subscription = get_subscription(subscription_id)
            price_id = subscription["items"]["data"][0]["price"]["id"]
            plan_code = get_plan_code_from_price_id(price_id)

            if plan_code and plan_code != "free":
                from src.eriq.tokens import reset_monthly_allowance_on_payment
                reset_monthly_allowance_on_payment(user_id, plan_code, invoice["id"])
                logger.info(f"Token allowance reset for user {user_id} on plan {plan_code}")
        except Exception as e:
            logger.error(f"Failed to reset token allowance for user {user_id}: {e}")


async def handle_invoice_payment_failed(invoice: dict):
    logger.info(f"Processing invoice.payment_failed: {invoice['id']}")
    
    customer_id = invoice.get("customer")
    user_id = get_user_id_from_customer(customer_id)
    
    if user_id:
        with get_cursor() as cur:
            cur.execute(
                "UPDATE users SET subscription_status = 'past_due' WHERE id = %s",
                (user_id,)
            )
        logger.info(f"User {user_id} payment failed, subscription past_due")


async def process_webhook_event(event: stripe.Event):
    event_type = event["type"]
    data = event["data"]["object"]
    
    handlers = {
        "checkout.session.completed": handle_checkout_session_completed,
        "customer.subscription.updated": handle_subscription_updated,
        "customer.subscription.deleted": handle_subscription_deleted,
        "invoice.paid": handle_invoice_paid,
        "invoice.payment_failed": handle_invoice_payment_failed,
    }
    
    handler = handlers.get(event_type)
    if handler:
        await handler(data)
    else:
        logger.debug(f"Unhandled event type: {event_type}")
