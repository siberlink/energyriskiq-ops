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
    
    # Anonymous sub-product checkouts (no main-app user) must be dispatched
    # BEFORE user_id resolution, or they would be dropped by the early return.
    if session.get("metadata", {}).get("type") == "brent_forecast":
        from src.api.brent_forecast_routes import handle_brent_forecast_checkout_completed
        handle_brent_forecast_checkout_completed(session)
        return

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

    if session.get("metadata", {}).get("type") == "wti_pro_widget":
        from src.api.wti_pro_widget_routes import handle_widget_checkout_completed
        handle_widget_checkout_completed(session)
        return

    if session.get("metadata", {}).get("type") == "lng_pro_widget":
        from src.api.lng_pro_widget_routes import handle_widget_checkout_completed as handle_lng_widget_checkout_completed
        handle_lng_widget_checkout_completed(session)
        return

    if session.get("metadata", {}).get("type") == "gas_storage_pro_widget":
        from src.api.gas_storage_pro_widget_routes import handle_widget_checkout_completed as handle_gas_widget_checkout_completed
        handle_gas_widget_checkout_completed(session)
        return

    if session.get("metadata", {}).get("type") == "indices_history":
        from src.api.indices_history_routes import handle_index_history_checkout_completed
        handle_index_history_checkout_completed(session)
        return

    if session.get("metadata", {}).get("type") == "daily_report":
        from src.api.daily_report_routes import handle_daily_report_checkout_completed
        handle_daily_report_checkout_completed(session)
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

    try:
        from src.api.wti_pro_widget_routes import handle_widget_subscription_event
        if handle_widget_subscription_event(subscription):
            return
    except Exception as e:
        logger.error(f"Widget subscription event handler error: {e}")

    try:
        from src.api.lng_pro_widget_routes import handle_widget_subscription_event as handle_lng_widget_subscription_event
        if handle_lng_widget_subscription_event(subscription):
            return
    except Exception as e:
        logger.error(f"LNG widget subscription event handler error: {e}")

    try:
        from src.api.gas_storage_pro_widget_routes import handle_widget_subscription_event as handle_gas_widget_subscription_event
        if handle_gas_widget_subscription_event(subscription):
            return
    except Exception as e:
        logger.error(f"Gas widget subscription event handler error: {e}")

    try:
        from src.api.indices_history_routes import handle_index_history_subscription_event
        if handle_index_history_subscription_event(subscription):
            return
    except Exception as e:
        logger.error(f"Indices history subscription event handler error: {e}")

    try:
        from src.api.daily_report_routes import handle_daily_report_subscription_event
        if handle_daily_report_subscription_event(subscription):
            return
    except Exception as e:
        logger.error(f"Daily report subscription event handler error: {e}")

    try:
        from src.api.brent_forecast_routes import handle_brent_forecast_subscription_event
        if handle_brent_forecast_subscription_event(subscription):
            return
    except Exception as e:
        logger.error(f"Brent forecast subscription event handler error: {e}")

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

    try:
        from src.api.wti_pro_widget_routes import handle_widget_subscription_deleted
        if handle_widget_subscription_deleted(subscription):
            return
    except Exception as e:
        logger.error(f"Widget subscription deleted handler error: {e}")

    try:
        from src.api.lng_pro_widget_routes import handle_widget_subscription_deleted as handle_lng_widget_subscription_deleted
        if handle_lng_widget_subscription_deleted(subscription):
            return
    except Exception as e:
        logger.error(f"LNG widget subscription deleted handler error: {e}")

    try:
        from src.api.gas_storage_pro_widget_routes import handle_widget_subscription_deleted as handle_gas_widget_subscription_deleted
        if handle_gas_widget_subscription_deleted(subscription):
            return
    except Exception as e:
        logger.error(f"Gas widget subscription deleted handler error: {e}")

    try:
        from src.api.indices_history_routes import handle_index_history_subscription_deleted
        if handle_index_history_subscription_deleted(subscription):
            return
    except Exception as e:
        logger.error(f"Indices history subscription deleted handler error: {e}")

    try:
        from src.api.daily_report_routes import handle_daily_report_subscription_deleted
        if handle_daily_report_subscription_deleted(subscription):
            return
    except Exception as e:
        logger.error(f"Daily report subscription deleted handler error: {e}")

    try:
        from src.api.brent_forecast_routes import handle_brent_forecast_subscription_deleted
        if handle_brent_forecast_subscription_deleted(subscription):
            return
    except Exception as e:
        logger.error(f"Brent forecast subscription deleted handler error: {e}")

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

    # Widget invoices must never touch main user subscription state
    try:
        from src.db.db import get_cursor as _gc
        with _gc(commit=False) as _cur:
            _cur.execute(
                "SELECT 1 FROM user_pro_widgets WHERE stripe_subscription_id = %s",
                (subscription_id,)
            )
            if _cur.fetchone():
                logger.info(f"invoice.paid {invoice['id']} is for a widget subscription — skipping main user_plans logic")
                return
            _cur.execute(
                "SELECT 1 FROM user_index_history_subs WHERE stripe_subscription_id = %s",
                (subscription_id,)
            )
            if _cur.fetchone():
                logger.info(f"invoice.paid {invoice['id']} is for an indices-history subscription — skipping main user_plans logic")
                return
            _cur.execute(
                "SELECT 1 FROM user_daily_report_subs WHERE stripe_subscription_id = %s",
                (subscription_id,)
            )
            if _cur.fetchone():
                logger.info(f"invoice.paid {invoice['id']} is for a daily-report subscription — skipping main user_plans logic")
                return
        from src.api.brent_forecast_routes import handle_brent_forecast_invoice_paid
        if handle_brent_forecast_invoice_paid(invoice):
            logger.info(f"invoice.paid {invoice['id']} is for a brent-forecast subscription — skipping main user_plans logic")
            return
    except Exception as e:
        logger.error(f"Widget invoice-isolation check failed: {e}")

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

    subscription_id = invoice.get("subscription")
    if subscription_id:
        try:
            from src.db.db import get_cursor as _gc
            with _gc(commit=False) as _cur:
                _cur.execute(
                    "SELECT 1 FROM user_pro_widgets WHERE stripe_subscription_id = %s",
                    (subscription_id,)
                )
                if _cur.fetchone():
                    logger.info(f"invoice.payment_failed {invoice['id']} is for a widget subscription — skipping main user_plans logic")
                    return
                _cur.execute(
                    "SELECT 1 FROM user_index_history_subs WHERE stripe_subscription_id = %s",
                    (subscription_id,)
                )
                if _cur.fetchone():
                    logger.info(f"invoice.payment_failed {invoice['id']} is for an indices-history subscription — skipping main user_plans logic")
                    return
                _cur.execute(
                    "SELECT 1 FROM user_daily_report_subs WHERE stripe_subscription_id = %s",
                    (subscription_id,)
                )
                if _cur.fetchone():
                    logger.info(f"invoice.payment_failed {invoice['id']} is for a daily-report subscription — skipping main user_plans logic")
                    return
            from src.api.brent_forecast_routes import handle_brent_forecast_invoice_failed
            if handle_brent_forecast_invoice_failed(invoice):
                logger.info(f"invoice.payment_failed {invoice['id']} is for a brent-forecast subscription — skipping main user_plans logic")
                return
        except Exception as e:
            logger.error(f"Widget invoice-isolation check failed: {e}")

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
