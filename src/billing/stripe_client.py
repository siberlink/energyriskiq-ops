import os
import stripe
import logging
import requests
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

PLAN_PRICE_EUR = {
    "free": 0.00,
    "personal": 9.95,
    "trader": 29.00,
    "pro": 49.00,
    "enterprise": 129.00
}

_stripe_initialized = False

def get_stripe_credentials() -> Dict[str, str]:
    hostname = os.environ.get("REPLIT_CONNECTORS_HOSTNAME")
    repl_identity = os.environ.get("REPL_IDENTITY")
    web_repl_renewal = os.environ.get("WEB_REPL_RENEWAL")
    
    if repl_identity:
        x_replit_token = f"repl {repl_identity}"
    elif web_repl_renewal:
        x_replit_token = f"depl {web_repl_renewal}"
    else:
        raise ValueError("No Replit token found for Stripe credentials")
    
    is_production = os.environ.get("REPLIT_DEPLOYMENT") == "1"
    target_environment = "production" if is_production else "development"
    
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
        logger.error(f"Stripe connector request failed: {response.status_code} - {response.text}")
        raise ValueError(f"Failed to fetch Stripe credentials: HTTP {response.status_code}")
    
    data = response.json()
    items = data.get("items", [])
    
    if not items:
        logger.error(f"No Stripe connection found for {target_environment}. Response: {data}")
        raise ValueError(f"Stripe {target_environment} connection not configured. Please set up Stripe in the Integrations tab.")
    
    connection = items[0]
    settings = connection.get("settings", {})
    
    if not settings.get("publishable") or not settings.get("secret"):
        logger.error(f"Stripe {target_environment} connection missing keys. Settings: {list(settings.keys())}")
        raise ValueError(f"Stripe {target_environment} connection incomplete - missing API keys")
    
    return {
        "publishable_key": settings["publishable"],
        "secret_key": settings["secret"]
    }


def init_stripe() -> None:
    global _stripe_initialized
    if _stripe_initialized:
        return
    credentials = get_stripe_credentials()
    stripe.api_key = credentials["secret_key"]
    _stripe_initialized = True
    logger.info("Stripe initialized successfully")


def get_stripe_publishable_key() -> str:
    credentials = get_stripe_credentials()
    return credentials["publishable_key"]


def ensure_stripe_initialized():
    if not _stripe_initialized:
        init_stripe()


async def create_customer(email: str, user_id: int, name: Optional[str] = None) -> Dict[str, Any]:
    ensure_stripe_initialized()
    customer = stripe.Customer.create(
        email=email,
        name=name,
        metadata={"user_id": str(user_id)}
    )
    logger.info(f"Created Stripe customer {customer.id} for user {user_id}")
    return customer


async def create_checkout_session(
    customer_id: str,
    price_id: str,
    success_url: str,
    cancel_url: str,
    user_id: int
) -> Dict[str, Any]:
    ensure_stripe_initialized()
    session = stripe.checkout.Session.create(
        customer=customer_id,
        payment_method_types=["card"],
        line_items=[{"price": price_id, "quantity": 1}],
        mode="subscription",
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={"user_id": str(user_id)},
        subscription_data={
            "metadata": {"user_id": str(user_id)}
        }
    )
    logger.info(f"Created checkout session {session.id} for user {user_id}")
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
