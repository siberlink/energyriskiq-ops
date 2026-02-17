import os
import stripe
import logging
import requests
from typing import Optional, Dict, Any

from src.db.db import get_cursor

logger = logging.getLogger(__name__)

PLAN_PRICE_EUR = {
    "free": 0.00,
    "personal": 9.95,
    "trader": 29.00,
    "pro": 49.00,
    "enterprise": 129.00
}

_current_stripe_mode = None


def get_stripe_mode() -> str:
    """Get the current Stripe mode from the database (live or sandbox)."""
    global _current_stripe_mode
    try:
        with get_cursor(commit=False) as cursor:
            cursor.execute("SELECT value FROM app_settings WHERE key = 'stripe_mode'")
            row = cursor.fetchone()
            mode = row["value"] if row else "live"
            _current_stripe_mode = mode
            return mode
    except Exception:
        return _current_stripe_mode or "live"


def set_stripe_mode(mode: str) -> bool:
    """Set the Stripe mode in the database. Returns True on success."""
    global _current_stripe_mode
    if mode not in ("live", "sandbox"):
        raise ValueError("Mode must be 'live' or 'sandbox'")
    with get_cursor() as cursor:
        cursor.execute("""
            INSERT INTO app_settings (key, value, updated_at)
            VALUES ('stripe_mode', %s, NOW())
            ON CONFLICT (key) DO UPDATE SET value = %s, updated_at = NOW()
        """, (mode, mode))
    _current_stripe_mode = mode
    _reinit_stripe(mode)
    logger.info(f"Stripe mode switched to: {mode}")
    return True


def get_stripe_credentials_for_mode(mode: str = None) -> Dict[str, str]:
    """Get Stripe credentials for the specified mode."""
    if mode is None:
        mode = get_stripe_mode()

    if mode == "sandbox":
        pub_key = os.environ.get("STRIPE_SANDBOX_PUBLISHABLE_KEY")
        secret_key = os.environ.get("STRIPE_SANDBOX_SECRET_KEY")
        if pub_key and secret_key:
            return {"publishable_key": pub_key, "secret_key": secret_key, "mode": "sandbox"}
        raise ValueError("Sandbox Stripe keys not configured. Set STRIPE_SANDBOX_PUBLISHABLE_KEY and STRIPE_SANDBOX_SECRET_KEY.")

    pub_key = os.environ.get("STRIPE_PUBLISHABLE_KEY")
    secret_key = os.environ.get("STRIPE_SECRET_KEY")
    if pub_key and secret_key:
        return {"publishable_key": pub_key, "secret_key": secret_key, "mode": "live"}

    hostname = os.environ.get("REPLIT_CONNECTORS_HOSTNAME")
    repl_identity = os.environ.get("REPL_IDENTITY")
    web_repl_renewal = os.environ.get("WEB_REPL_RENEWAL")

    if repl_identity:
        x_replit_token = f"repl {repl_identity}"
    elif web_repl_renewal:
        x_replit_token = f"depl {web_repl_renewal}"
    else:
        raise ValueError("No Stripe credentials found. Set STRIPE_PUBLISHABLE_KEY and STRIPE_SECRET_KEY.")

    is_production = os.environ.get("REPLIT_DEPLOYMENT") == "1"
    environments_to_try = ["production", "development"] if is_production else ["development"]

    for target_environment in environments_to_try:
        url = f"https://{hostname}/api/v2/connection"
        params = {
            "include_secrets": "true",
            "connector_names": "stripe",
            "environment": target_environment
        }

        response = requests.get(url, params=params, headers={
            "Accept": "application/json",
            "X_REPLIT_TOKEN": x_replit_token
        })

        if response.status_code != 200:
            continue

        data = response.json()
        items = data.get("items", [])

        if not items:
            continue

        connection = items[0]
        settings = connection.get("settings", {})

        if settings.get("publishable") and settings.get("secret"):
            return {
                "publishable_key": settings["publishable"],
                "secret_key": settings["secret"],
                "mode": "live"
            }

    raise ValueError("No Stripe connection configured. Set STRIPE_PUBLISHABLE_KEY and STRIPE_SECRET_KEY secrets.")


def get_stripe_credentials() -> Dict[str, str]:
    """Get Stripe credentials for the currently active mode."""
    return get_stripe_credentials_for_mode()


def get_webhook_secret() -> Optional[str]:
    """Get the webhook secret for the currently active Stripe mode."""
    mode = get_stripe_mode()
    if mode == "sandbox":
        return os.environ.get("STRIPE_SANDBOX_WEBHOOK_SECRET")
    return os.environ.get("STRIPE_WEBHOOK_SECRET")


def _reinit_stripe(mode: str = None):
    """Reinitialize Stripe with the correct API key for the given mode."""
    global _stripe_initialized
    credentials = get_stripe_credentials_for_mode(mode)
    stripe.api_key = credentials["secret_key"]
    _stripe_initialized = True
    logger.info(f"Stripe reinitialized for mode: {credentials['mode']}")


_stripe_initialized = False

def init_stripe() -> None:
    global _stripe_initialized
    if _stripe_initialized:
        return
    credentials = get_stripe_credentials()
    stripe.api_key = credentials["secret_key"]
    _stripe_initialized = True
    logger.info(f"Stripe initialized successfully (mode: {credentials.get('mode', 'unknown')})")


def get_stripe_publishable_key() -> str:
    credentials = get_stripe_credentials()
    return credentials["publishable_key"]


def ensure_stripe_initialized():
    if not _stripe_initialized:
        init_stripe()


def get_plan_stripe_ids(plan_code: str) -> Dict[str, Optional[str]]:
    """Get the Stripe product/price IDs for a plan based on current mode."""
    mode = get_stripe_mode()
    with get_cursor(commit=False) as cursor:
        if mode == "sandbox":
            cursor.execute("""
                SELECT stripe_product_id_sandbox as product_id, stripe_price_id_sandbox as price_id
                FROM plan_settings WHERE plan_code = %s
            """, (plan_code,))
        else:
            cursor.execute("""
                SELECT stripe_product_id as product_id, stripe_price_id as price_id
                FROM plan_settings WHERE plan_code = %s
            """, (plan_code,))
        row = cursor.fetchone()
        if row:
            return {"product_id": row["product_id"], "price_id": row["price_id"]}
        return {"product_id": None, "price_id": None}


async def create_customer(email: str, user_id: int, name: Optional[str] = None) -> Dict[str, Any]:
    ensure_stripe_initialized()
    customer = stripe.Customer.create(
        email=email,
        name=name,
        metadata={"user_id": str(user_id)}
    )
    logger.info(f"Created Stripe customer {customer.id} for user {user_id}")
    return customer


def get_free_trial_days() -> int:
    try:
        with get_cursor(commit=False) as cursor:
            cursor.execute("SELECT value FROM app_settings WHERE key = 'free_trial_days'")
            row = cursor.fetchone()
            return int(row["value"]) if row else 0
    except Exception:
        return 0


def set_free_trial_days(days: int) -> bool:
    if days not in (0, 14, 30):
        raise ValueError("Trial days must be 0, 14, or 30")
    with get_cursor() as cursor:
        cursor.execute("""
            INSERT INTO app_settings (key, value, updated_at)
            VALUES ('free_trial_days', %s, NOW())
            ON CONFLICT (key) DO UPDATE SET value = %s, updated_at = NOW()
        """, (str(days), str(days)))
    logger.info(f"Free trial days set to: {days}")
    return True


def get_banner_settings() -> dict:
    try:
        with get_cursor(commit=False) as cursor:
            cursor.execute("SELECT value FROM app_settings WHERE key = 'banner_enabled'")
            row = cursor.fetchone()
            enabled = row["value"] == "true" if row else False

            cursor.execute("SELECT value FROM app_settings WHERE key = 'banner_countdown_end'")
            row2 = cursor.fetchone()
            countdown_end = row2["value"] if row2 else None

            return {"banner_enabled": enabled, "banner_countdown_end": countdown_end}
    except Exception:
        return {"banner_enabled": False, "banner_countdown_end": None}


def set_banner_settings(enabled: bool, timeframe_days: int = 0) -> dict:
    import datetime
    with get_cursor() as cursor:
        val = "true" if enabled else "false"
        cursor.execute("""
            INSERT INTO app_settings (key, value, updated_at)
            VALUES ('banner_enabled', %s, NOW())
            ON CONFLICT (key) DO UPDATE SET value = %s, updated_at = NOW()
        """, (val, val))

        if timeframe_days > 0 and enabled:
            end_time = (datetime.datetime.utcnow() + datetime.timedelta(days=timeframe_days)).isoformat() + "Z"
        else:
            end_time = ""

        cursor.execute("""
            INSERT INTO app_settings (key, value, updated_at)
            VALUES ('banner_countdown_end', %s, NOW())
            ON CONFLICT (key) DO UPDATE SET value = %s, updated_at = NOW()
        """, (end_time, end_time))

    logger.info(f"Banner settings updated: enabled={enabled}, timeframe_days={timeframe_days}")
    return get_banner_settings()


async def create_checkout_session(
    customer_id: str,
    price_id: str,
    success_url: str,
    cancel_url: str,
    user_id: int,
    trial_period_days: Optional[int] = None
) -> Dict[str, Any]:
    ensure_stripe_initialized()
    subscription_data = {
        "metadata": {"user_id": str(user_id)}
    }
    if trial_period_days and trial_period_days > 0:
        subscription_data["trial_period_days"] = trial_period_days

    session = stripe.checkout.Session.create(
        customer=customer_id,
        payment_method_types=["card"],
        line_items=[{"price": price_id, "quantity": 1}],
        mode="subscription",
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={"user_id": str(user_id)},
        subscription_data=subscription_data
    )
    logger.info(f"Created checkout session {session.id} for user {user_id} (trial_days={trial_period_days})")
    return session


async def create_billing_portal_session(customer_id: str, return_url: str) -> Dict[str, Any]:
    ensure_stripe_initialized()
    session = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=return_url
    )
    return session


async def cancel_subscription(subscription_id: str, at_period_end: bool = True) -> Dict[str, Any]:
    ensure_stripe_initialized()
    if at_period_end:
        subscription = stripe.Subscription.modify(
            subscription_id,
            cancel_at_period_end=True
        )
    else:
        subscription = stripe.Subscription.delete(subscription_id)
    logger.info(f"Cancelled subscription {subscription_id} (at_period_end={at_period_end})")
    return subscription


async def update_subscription(subscription_id: str, new_price_id: str) -> Dict[str, Any]:
    ensure_stripe_initialized()
    subscription = stripe.Subscription.retrieve(subscription_id)
    
    items_data = subscription.get("items", {}).get("data", [])
    if not items_data:
        raise ValueError(f"Subscription {subscription_id} has no items to update")
    
    updated = stripe.Subscription.modify(
        subscription_id,
        items=[{
            "id": items_data[0]["id"],
            "price": new_price_id
        }],
        proration_behavior="always_invoice"
    )
    logger.info(f"Updated subscription {subscription_id} to price {new_price_id}")
    return updated


def construct_webhook_event(payload: bytes, sig_header: str, webhook_secret: str):
    return stripe.Webhook.construct_event(payload, sig_header, webhook_secret)


def get_subscription(subscription_id: str) -> Dict[str, Any]:
    ensure_stripe_initialized()
    return stripe.Subscription.retrieve(subscription_id)


def get_customer(customer_id: str) -> Dict[str, Any]:
    ensure_stripe_initialized()
    return stripe.Customer.retrieve(customer_id)
