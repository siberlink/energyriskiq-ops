"""
GERI Live — paid (€8/mo, 14-day free trial) standalone subscription that unlocks
the real-time GERI Live dashboard inside the user account.

One-Time Only launch offer: subscribers who start the 14-day free trial also get
BONUS access to the Daily Intelligence Report, WTI Pro Widget, LNG Pro Widget,
Gas Storage Pro Widget and Indices History downloads — for as long as the GERI
Live subscription stays active (trialing/active/canceling). If the trial or the
subscription is cancelled, the bonus access ends automatically because all bonus
entitlement checks derive from this subscription's status.

Mirrors the Daily Intelligence Report subscription technique (Stripe checkout,
webhook-independent confirm, mode-aware activation, cancel-at-period-end).

Routes:
  GET  /api/geri-live/status     — subscription status (mode-aware)
  POST /api/geri-live/checkout   — start Stripe checkout (€8/mo, 14-day trial)
  POST /api/geri-live/confirm    — webhook-independent activation
  POST /api/geri-live/cancel     — cancel at period end
"""
import logging
from datetime import datetime
from typing import Optional

import stripe
from fastapi import APIRouter, Header, HTTPException

from src.db.db import get_cursor
from src.billing.stripe_client import (
    init_stripe,
    ensure_stripe_initialized,
    get_stripe_mode,
    create_customer,
    cancel_subscription as stripe_cancel_subscription,
)

router = APIRouter(tags=["geri-live"])
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

PLAN_CODE = "geri_live"                # Stripe product metadata key + metadata.type
PRICE_EUR_CENTS = 800                  # €8.00 — 36-hour launch offer price
PRICE_STANDARD_EUR_CENTS = 1700       # €17.00 — standard price after offer expires
OFFER_HOURS = 36                       # launch offer window in hours
TRIAL_DAYS = 14                        # 14-day free trial (once per user)
SUB_NAME = "EnergyRiskIQ — GERI Live"
SUB_DESC = ("Real-time GERI Live intelligence dashboard — live index, drivers, "
            "regional risk and intraday energy prices. Includes launch bonus "
            "access to the Daily Intelligence Report, WTI/LNG/Gas Pro Widgets "
            "and Indices History downloads. €8/month after a 14-day free trial.")


# ─────────────────────────────────────────────────────────────────────────────
# Migration
# ─────────────────────────────────────────────────────────────────────────────

def run_geri_live_sub_migration():
    try:
        with get_cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_geri_live_subs (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'inactive',
                    stripe_subscription_id TEXT,
                    stripe_customer_id TEXT,
                    current_period_end TIMESTAMP,
                    stripe_mode TEXT,
                    trial_used BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    UNIQUE (user_id)
                )
            """)
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_geri_live_subs_sub "
                "ON user_geri_live_subs(stripe_subscription_id)"
            )
            # Add offer expiry column to users table (additive, idempotent)
            cur.execute("""
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS geri_live_offer_expires_at TIMESTAMP WITHOUT TIME ZONE
            """)
        logger.info("user_geri_live_subs migration complete")
    except Exception as e:
        logger.error(f"user_geri_live_subs migration failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Stripe product seeding (idempotent, lazy, mode-scoped)
# ─────────────────────────────────────────────────────────────────────────────

def _settings_key(name: str) -> str:
    return f"{name}_{get_stripe_mode()}"


def _get_stored_price_id() -> Optional[str]:
    key = _settings_key("geri_live_price_id")
    try:
        with get_cursor(commit=False) as cur:
            cur.execute("SELECT value FROM app_settings WHERE key = %s", (key,))
            row = cur.fetchone()
            return row["value"] if row else None
    except Exception:
        return None


def _store_price_id(price_id: str, product_id: str):
    with get_cursor() as cur:
        for k, v in (("geri_live_price_id", price_id),
                     ("geri_live_product_id", product_id)):
            key = _settings_key(k)
            cur.execute("""
                INSERT INTO app_settings (key, value, updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (key) DO UPDATE
                  SET value = EXCLUDED.value, updated_at = NOW()
            """, (key, v))


def _get_or_create_product() -> object:
    """Return the Stripe product for GERI Live (search then create)."""
    ensure_stripe_initialized()
    try:
        existing = stripe.Product.search(
            query=f"metadata['plan_code']:'{PLAN_CODE}'"
        )
        if existing.data:
            return existing.data[0]
    except Exception as e:
        logger.warning(f"Stripe product search failed (will create): {e}")
    product = stripe.Product.create(
        name=SUB_NAME,
        description=SUB_DESC,
        metadata={"plan_code": PLAN_CODE, "kind": "subscription"},
    )
    logger.info(f"Created Stripe product {product.id} for GERI Live")
    return product


def ensure_geri_live_price_id() -> str:
    """Return the launch-offer Stripe price ID (€8/month)."""
    cached = _get_stored_price_id()
    if cached:
        return cached
    product = _get_or_create_product()
    price_id = None
    for p in stripe.Price.list(product=product.id, active=True, limit=100).data:
        if (p.unit_amount == PRICE_EUR_CENTS
                and p.currency == "eur"
                and p.recurring
                and p.recurring.get("interval") == "month"):
            price_id = p.id
            break
    if not price_id:
        price = stripe.Price.create(
            product=product.id,
            unit_amount=PRICE_EUR_CENTS,
            currency="eur",
            recurring={"interval": "month"},
            metadata={"plan_code": PLAN_CODE, "tier": "launch"},
        )
        price_id = price.id
        logger.info(f"Created Stripe launch price {price_id} for GERI Live (€8)")
    _store_price_id(price_id, product.id)
    return price_id


def ensure_geri_live_standard_price_id() -> str:
    """Return the standard Stripe price ID (€17/month, used after offer expires)."""
    key = _settings_key("geri_live_standard_price_id")
    try:
        with get_cursor(commit=False) as cur:
            cur.execute("SELECT value FROM app_settings WHERE key = %s", (key,))
            row = cur.fetchone()
            if row:
                return row["value"]
    except Exception:
        pass
    product = _get_or_create_product()
    price_id = None
    for p in stripe.Price.list(product=product.id, active=True, limit=100).data:
        if (p.unit_amount == PRICE_STANDARD_EUR_CENTS
                and p.currency == "eur"
                and p.recurring
                and p.recurring.get("interval") == "month"):
            price_id = p.id
            break
    if not price_id:
        price = stripe.Price.create(
            product=product.id,
            unit_amount=PRICE_STANDARD_EUR_CENTS,
            currency="eur",
            recurring={"interval": "month"},
            metadata={"plan_code": PLAN_CODE, "tier": "standard"},
        )
        price_id = price.id
        logger.info(f"Created Stripe standard price {price_id} for GERI Live (€17)")
    with get_cursor() as cur:
        cur.execute("""
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
        """, (key, price_id))
    return price_id


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _base_url() -> str:
    import os
    app_url = os.environ.get("APP_URL")
    if app_url:
        return app_url.rstrip("/")
    domain = os.environ.get("REPLIT_DOMAINS", "").split(",")[0]
    if domain:
        return f"https://{domain}"
    return "http://localhost:5000"


def _get_user_from_token(token: Optional[str]):
    if not token:
        return None
    with get_cursor(commit=False) as cur:
        cur.execute("""
            SELECT u.id, u.email, u.stripe_customer_id, u.geri_live_offer_expires_at
            FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token = %s AND s.expires_at > (NOW() AT TIME ZONE 'UTC')
        """, (token,))
        return cur.fetchone()


def _ensure_offer_expiry(user_id: int, user_row) -> "datetime":
    """Return the offer expiry for this user, initialising it to NOW()+36h if
    the column is NULL (covers both new users and existing users who are treated
    as first-time users)."""
    expiry = user_row.get("geri_live_offer_expires_at") if user_row else None
    if expiry is None:
        with get_cursor() as cur:
            cur.execute("""
                UPDATE users
                SET geri_live_offer_expires_at = NOW() + INTERVAL '%s hours'
                WHERE id = %%s
                RETURNING geri_live_offer_expires_at
            """ % OFFER_HOURS, (user_id,))
            row = cur.fetchone()
            expiry = row["geri_live_offer_expires_at"] if row else None
    return expiry


def _offer_active(expiry) -> bool:
    """True while the user is still inside the 36-hour launch-offer window."""
    if expiry is None:
        return True   # fallback: treat as active if we couldn't read it
    from datetime import timezone as _tz
    now = datetime.now(_tz.utc).replace(tzinfo=None)  # naive UTC for comparison
    # expiry is stored as naive UTC
    exp_naive = expiry.replace(tzinfo=None) if hasattr(expiry, "tzinfo") else expiry
    return now < exp_naive


def _get_or_create_row(user_id: int):
    with get_cursor() as cur:
        cur.execute(
            "SELECT * FROM user_geri_live_subs WHERE user_id = %s",
            (user_id,)
        )
        row = cur.fetchone()
        if row:
            return row
        cur.execute("""
            INSERT INTO user_geri_live_subs (user_id, status)
            VALUES (%s, 'inactive')
            RETURNING *
        """, (user_id,))
        return cur.fetchone()


def _is_active(row) -> bool:
    if not row:
        return False
    return row.get("status") in ("active", "trialing", "canceling")


def _active_for_mode(row) -> bool:
    """Mode-aware check: only counts a subscription as active if it belongs to
    the Stripe mode currently selected, so a sandbox test does not block a real
    live purchase (and vice versa). Legacy NULL-mode rows are treated as current."""
    if not _is_active(row):
        return False
    row_mode = row.get("stripe_mode")
    if not row_mode:
        return True
    return row_mode == get_stripe_mode()


def _trial_eligible(row) -> bool:
    """A user may start the 14-day free trial only if they have never had a
    subscription (no Stripe sub on record) and have not already used a trial."""
    if not row:
        return True
    if row.get("trial_used"):
        return False
    if row.get("stripe_subscription_id"):
        return False
    return True


def user_has_geri_live(user_id: int) -> bool:
    """Mode-agnostic runtime entitlement check for GERI Live and its launch
    bonus (Daily Intelligence Report, Pro Widgets, Indices History)."""
    try:
        with get_cursor(commit=False) as cur:
            cur.execute(
                "SELECT status FROM user_geri_live_subs WHERE user_id = %s",
                (user_id,)
            )
            row = cur.fetchone()
        return _is_active(row)
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Account endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/api/geri-live/status")
async def status(x_user_token: Optional[str] = Header(None)):
    user = _get_user_from_token(x_user_token)
    if not user:
        raise HTTPException(401, "Authentication required")
    row = _get_or_create_row(user["id"])
    plan_entitled = False
    try:
        from src.db.db import execute_one
        prow = execute_one("SELECT plan FROM user_plans WHERE user_id = %s", (user["id"],))
        plan_entitled = bool(prow and prow.get("plan") in ("pro", "enterprise"))
    except Exception as e:
        logger.error(f"geri-live status plan lookup failed: {e}")

    # Ensure the 36-hour offer window is initialised (sets it on first call if NULL)
    expiry = _ensure_offer_expiry(user["id"], user)
    offer_on = _offer_active(expiry)
    offer_price = PRICE_EUR_CENTS if offer_on else PRICE_STANDARD_EUR_CENTS

    return {
        "active": _active_for_mode(row),
        "plan_entitled": plan_entitled,
        "status": row["status"],
        "current_period_end": (row["current_period_end"].isoformat()
                               if row.get("current_period_end") else None),
        "price_eur": offer_price / 100.0,
        "trial_eligible": _trial_eligible(row),
        "trial_days": TRIAL_DAYS,
        "trialing": row["status"] == "trialing",
        # Offer fields
        "offer_active": offer_on,
        "offer_expires_at": expiry.isoformat() if expiry else None,
        "offer_price_eur": PRICE_EUR_CENTS / 100.0,
        "standard_price_eur": PRICE_STANDARD_EUR_CENTS / 100.0,
    }


@router.post("/api/geri-live/checkout")
async def checkout(x_user_token: Optional[str] = Header(None)):
    user = _get_user_from_token(x_user_token)
    if not user:
        raise HTTPException(401, "Authentication required")
    row = _get_or_create_row(user["id"])
    if _active_for_mode(row) and row.get("stripe_subscription_id"):
        return {"already_active": True}

    # Pick price based on whether the user is still in the 36-hour offer window
    expiry = _ensure_offer_expiry(user["id"], user)
    use_offer_price = _offer_active(expiry)

    init_stripe()
    try:
        price_id = (ensure_geri_live_price_id() if use_offer_price
                    else ensure_geri_live_standard_price_id())
    except Exception as e:
        logger.error(f"Could not ensure GERI Live price: {e}", exc_info=True)
        raise HTTPException(500, "Billing not available")

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

    base = _base_url()
    subscription_data = {
        "metadata": {
            "user_id": str(user["id"]),
            "type": "geri_live",
        }
    }
    trial_granted = _trial_eligible(row)
    if trial_granted:
        subscription_data["trial_period_days"] = TRIAL_DAYS
    try:
        session = stripe.checkout.Session.create(
            customer=customer_id,
            payment_method_types=["card"],
            line_items=[{"price": price_id, "quantity": 1}],
            mode="subscription",
            success_url=f"{base}/users/account?geri_live=active",
            cancel_url=f"{base}/users/account?geri_live=cancelled",
            metadata={
                "user_id": str(user["id"]),
                "type": "geri_live",
            },
            subscription_data=subscription_data,
        )
    except Exception as e:
        logger.error(f"GERI Live checkout creation failed: {e}", exc_info=True)
        raise HTTPException(500, "Failed to start checkout")

    return {"checkout_url": session.url, "trial_granted": trial_granted}


@router.post("/api/geri-live/confirm")
async def confirm(x_user_token: Optional[str] = Header(None)):
    """Activate the subscription by checking Stripe directly (webhook-independent).
    Called by the account page when the user returns from Stripe Checkout."""
    user = _get_user_from_token(x_user_token)
    if not user:
        raise HTTPException(401, "Authentication required")
    row = _get_or_create_row(user["id"])

    if _active_for_mode(row) and row.get("stripe_subscription_id"):
        return {"active": True, "status": row["status"]}

    init_stripe()

    customer_id = user.get("stripe_customer_id")
    if customer_id:
        try:
            cust = stripe.Customer.retrieve(customer_id)
            if cust.get("deleted"):
                customer_id = None
        except Exception:
            customer_id = None
    if not customer_id:
        try:
            found = stripe.Customer.search(
                query=f"metadata['user_id']:'{user['id']}'", limit=1
            )
            if found.get("data"):
                customer_id = found["data"][0]["id"]
        except Exception as e:
            logger.error(f"GERI Live confirm: customer search failed: {e}")
    if not customer_id:
        return {"active": False, "status": row["status"]}

    try:
        subs = stripe.Subscription.list(
            customer=customer_id, status="all", limit=100
        )
    except Exception as e:
        logger.error(f"GERI Live confirm: could not list subscriptions: {e}")
        return {"active": False, "status": row["status"]}

    matched = None
    for sub in subs.get("data", []):
        meta = sub.get("metadata") or {}
        if meta.get("type") == "geri_live" and sub.get("status") in (
            "active", "trialing",
        ):
            matched = sub
            break

    if not matched:
        return {"active": False, "status": row["status"]}

    subscription_id = matched.get("id")
    period_end = matched.get("current_period_end")
    period_end_dt = datetime.utcfromtimestamp(period_end) if period_end else None
    cancel_at_end = matched.get("cancel_at_period_end")
    stripe_status = matched.get("status", "active")
    local_status = "canceling" if cancel_at_end else stripe_status
    matched_mode = "live" if matched.get("livemode") else "sandbox"

    with get_cursor() as cur:
        cur.execute("""
            UPDATE user_geri_live_subs
            SET stripe_subscription_id = %s,
                stripe_customer_id = %s,
                status = %s,
                current_period_end = %s,
                stripe_mode = %s,
                trial_used = TRUE,
                updated_at = NOW()
            WHERE id = %s
        """, (subscription_id, customer_id, local_status, period_end_dt,
              matched_mode, row["id"]))
    logger.info(f"GERI Live subscription activated via confirm for user {user['id']}")
    return {
        "active": local_status in ("active", "trialing", "canceling"),
        "status": local_status,
    }


@router.post("/api/geri-live/cancel")
async def cancel(x_user_token: Optional[str] = Header(None)):
    user = _get_user_from_token(x_user_token)
    if not user:
        raise HTTPException(401, "Authentication required")
    row = _get_or_create_row(user["id"])
    if not row["stripe_subscription_id"]:
        raise HTTPException(400, "No active subscription")
    if not _active_for_mode(row):
        raise HTTPException(
            400, "No active subscription in the current billing mode"
        )
    init_stripe()
    try:
        sub = await stripe_cancel_subscription(row["stripe_subscription_id"],
                                               at_period_end=True)
        with get_cursor() as cur:
            cur.execute(
                "UPDATE user_geri_live_subs SET status = 'canceling', "
                "updated_at = NOW() WHERE id = %s",
                (row["id"],)
            )
        return {"canceled_at_period_end": True,
                "current_period_end": sub.get("current_period_end")}
    except Exception as e:
        logger.error(f"GERI Live cancel error: {e}", exc_info=True)
        raise HTTPException(500, "Failed to cancel subscription")


# ─────────────────────────────────────────────────────────────────────────────
# Webhook handlers (called from src.billing.webhook_handler by metadata.type)
# ─────────────────────────────────────────────────────────────────────────────

def handle_geri_live_checkout_completed(session: dict) -> bool:
    user_id_str = (session.get("metadata") or {}).get("user_id")
    if not user_id_str:
        logger.error("GERI Live checkout completed without user_id metadata")
        return True
    user_id = int(user_id_str)
    subscription_id = session.get("subscription")
    customer_id = session.get("customer")
    if not subscription_id:
        logger.error("GERI Live checkout completed without subscription")
        return True
    ensure_stripe_initialized()
    try:
        sub = stripe.Subscription.retrieve(subscription_id)
    except Exception as e:
        logger.error(f"Could not retrieve GERI Live subscription {subscription_id}: {e}")
        return True
    period_end = sub.get("current_period_end")
    period_end_dt = datetime.utcfromtimestamp(period_end) if period_end else None
    status_val = sub.get("status", "active")
    mode = "live" if sub.get("livemode") else "sandbox"
    with get_cursor() as cur:
        cur.execute(
            "SELECT id FROM user_geri_live_subs WHERE user_id = %s",
            (user_id,)
        )
        existing = cur.fetchone()
        if existing:
            cur.execute("""
                UPDATE user_geri_live_subs
                SET stripe_subscription_id = %s,
                    stripe_customer_id = %s,
                    status = %s,
                    current_period_end = %s,
                    stripe_mode = %s,
                    trial_used = TRUE,
                    updated_at = NOW()
                WHERE id = %s
            """, (subscription_id, customer_id, status_val, period_end_dt,
                  mode, existing["id"]))
        else:
            cur.execute("""
                INSERT INTO user_geri_live_subs
                    (user_id, status, stripe_subscription_id, stripe_customer_id,
                     current_period_end, stripe_mode, trial_used)
                VALUES (%s, %s, %s, %s, %s, %s, TRUE)
            """, (user_id, status_val, subscription_id, customer_id,
                  period_end_dt, mode))
    logger.info(f"GERI Live subscription activated for user {user_id}")
    return True


def handle_geri_live_subscription_event(subscription: dict) -> bool:
    """Update row on subscription.updated. Returns True if this is a GERI Live
    subscription (so the caller skips main plan logic)."""
    sub_id = subscription.get("id")
    if not sub_id:
        return False
    is_meta = (subscription.get("metadata") or {}).get("type") == "geri_live"
    with get_cursor() as cur:
        cur.execute(
            "SELECT id FROM user_geri_live_subs WHERE stripe_subscription_id = %s",
            (sub_id,)
        )
        row = cur.fetchone()
    if not row and not is_meta:
        return False
    if not row:
        return True
    period_end = subscription.get("current_period_end")
    period_end_dt = datetime.utcfromtimestamp(period_end) if period_end else None
    cancel_at_end = subscription.get("cancel_at_period_end")
    stripe_status = subscription.get("status", "inactive")
    local_status = "canceling" if cancel_at_end else stripe_status
    with get_cursor() as cur:
        cur.execute("""
            UPDATE user_geri_live_subs
            SET status = %s, current_period_end = %s, updated_at = NOW()
            WHERE id = %s
        """, (local_status, period_end_dt, row["id"]))
    logger.info(f"GERI Live subscription {sub_id} → status={local_status}")
    return True


def handle_geri_live_subscription_deleted(subscription: dict) -> bool:
    sub_id = subscription.get("id")
    if not sub_id:
        return False
    is_meta = (subscription.get("metadata") or {}).get("type") == "geri_live"
    with get_cursor() as cur:
        cur.execute(
            "SELECT id FROM user_geri_live_subs WHERE stripe_subscription_id = %s",
            (sub_id,)
        )
        row = cur.fetchone()
        if not row:
            # Short-circuit on metadata even if the local row is missing, so a
            # GERI Live deletion never falls through to main user_plans logic.
            return True if is_meta else False
        cur.execute("""
            UPDATE user_geri_live_subs
            SET status = 'cancelled', updated_at = NOW()
            WHERE id = %s
        """, (row["id"],))
    logger.info(f"GERI Live subscription {sub_id} cancelled")
    return True
