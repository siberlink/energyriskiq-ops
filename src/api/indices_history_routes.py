"""
Download Indices History — paid (€1.85/mo) subscription that unlocks CSV/Excel
downloads of the full GERI, EERI, EGSI-M and EGSI-S risk-index history.

Mirrors the WTI Pro Widget subscription technique (Stripe checkout, webhook-
independent confirm, mode-aware activation, cancel-at-period-end).

Routes:
  GET  /api/indices-history/status     — subscription status (mode-aware)
  POST /api/indices-history/checkout   — start Stripe checkout (€1.85/mo)
  POST /api/indices-history/confirm    — webhook-independent activation
  POST /api/indices-history/cancel     — cancel at period end
  GET  /api/indices-history/download   — gated CSV/Excel download (?index=&fmt=)
"""
import logging
from datetime import datetime
from typing import Optional

import stripe
from fastapi import APIRouter, Header, HTTPException, Query

from src.db.db import get_cursor
from src.billing.stripe_client import (
    init_stripe,
    ensure_stripe_initialized,
    get_stripe_mode,
    create_customer,
    cancel_subscription as stripe_cancel_subscription,
)

router = APIRouter(tags=["indices-history"])
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

SUB_CODE = "indices-history"
PLAN_CODE = "indices_history"          # Stripe product metadata key
PRICE_EUR_CENTS = 185                  # €1.85
SUB_NAME = "EnergyRiskIQ — Indices History Downloads"
SUB_DESC = ("Unlimited CSV and Excel downloads of the full GERI, EERI, EGSI-M "
            "and EGSI-S risk-index history. €1.85/month.")

# index_code -> (csv_func_name, xlsx_func_name) in src.geri.routes
_INDEX_DISPATCH = {
    "geri":   ("geri_history_download_csv",   "geri_history_download_xlsx"),
    "eeri":   ("eeri_history_download_csv",   "eeri_history_download_xlsx"),
    "egsi-m": ("egsi_m_history_download_csv", "egsi_m_history_download_xlsx"),
    "egsi-s": ("egsi_s_history_download_csv", "egsi_s_history_download_xlsx"),
}


# ─────────────────────────────────────────────────────────────────────────────
# Migration
# ─────────────────────────────────────────────────────────────────────────────

def run_indices_history_migration():
    try:
        with get_cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_index_history_subs (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'inactive',
                    stripe_subscription_id TEXT,
                    stripe_customer_id TEXT,
                    current_period_end TIMESTAMP,
                    stripe_mode TEXT,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    UNIQUE (user_id)
                )
            """)
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_index_history_subs_sub "
                "ON user_index_history_subs(stripe_subscription_id)"
            )
        logger.info("user_index_history_subs migration complete")
    except Exception as e:
        logger.error(f"user_index_history_subs migration failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Stripe product seeding (idempotent, lazy, mode-scoped)
# ─────────────────────────────────────────────────────────────────────────────

def _settings_key(name: str) -> str:
    return f"{name}_{get_stripe_mode()}"


def _get_stored_price_id() -> Optional[str]:
    key = _settings_key("indices_history_price_id")
    try:
        with get_cursor(commit=False) as cur:
            cur.execute("SELECT value FROM app_settings WHERE key = %s", (key,))
            row = cur.fetchone()
            return row["value"] if row else None
    except Exception:
        return None


def _store_price_id(price_id: str, product_id: str):
    with get_cursor() as cur:
        for k, v in (("indices_history_price_id", price_id),
                     ("indices_history_product_id", product_id)):
            key = _settings_key(k)
            cur.execute("""
                INSERT INTO app_settings (key, value, updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (key) DO UPDATE
                  SET value = EXCLUDED.value, updated_at = NOW()
            """, (key, v))


def ensure_indices_history_price_id() -> str:
    cached = _get_stored_price_id()
    if cached:
        return cached
    ensure_stripe_initialized()
    product = None
    try:
        existing = stripe.Product.search(
            query=f"metadata['plan_code']:'{PLAN_CODE}'"
        )
        if existing.data:
            product = existing.data[0]
    except Exception as e:
        logger.warning(f"Stripe product search failed (will create): {e}")
    if not product:
        product = stripe.Product.create(
            name=SUB_NAME,
            description=SUB_DESC,
            metadata={"plan_code": PLAN_CODE, "kind": "subscription"},
        )
        logger.info(f"Created Stripe product {product.id} for indices history")
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
            metadata={"plan_code": PLAN_CODE},
        )
        price_id = price.id
        logger.info(f"Created Stripe price {price_id} for indices history")
    _store_price_id(price_id, product.id)
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
            SELECT u.id, u.email, u.stripe_customer_id
            FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token = %s AND s.expires_at > NOW()
        """, (token,))
        return cur.fetchone()


def _get_or_create_row(user_id: int):
    with get_cursor() as cur:
        cur.execute(
            "SELECT * FROM user_index_history_subs WHERE user_id = %s",
            (user_id,)
        )
        row = cur.fetchone()
        if row:
            return row
        cur.execute("""
            INSERT INTO user_index_history_subs (user_id, status)
            VALUES (%s, 'inactive')
            RETURNING *
        """, (user_id,))
        return cur.fetchone()


def _geri_live_bonus(user_id) -> bool:
    """GERI Live launch-offer bonus: an active GERI Live subscription also
    unlocks Indices History downloads. Ends automatically when GERI Live
    is cancelled."""
    try:
        from src.api.geri_live_sub_routes import user_has_geri_live
        return user_has_geri_live(user_id)
    except Exception:
        return False


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


# ─────────────────────────────────────────────────────────────────────────────
# Account endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/api/indices-history/status")
async def status(x_user_token: Optional[str] = Header(None)):
    user = _get_user_from_token(x_user_token)
    if not user:
        raise HTTPException(401, "Authentication required")
    row = _get_or_create_row(user["id"])
    bonus = _geri_live_bonus(user["id"])
    return {
        "active": _active_for_mode(row) or bonus,
        "geri_live_bonus": bonus,
        "status": row["status"],
        "current_period_end": (row["current_period_end"].isoformat()
                               if row.get("current_period_end") else None),
        "price_eur": PRICE_EUR_CENTS / 100.0,
    }


@router.post("/api/indices-history/checkout")
async def checkout(x_user_token: Optional[str] = Header(None)):
    user = _get_user_from_token(x_user_token)
    if not user:
        raise HTTPException(401, "Authentication required")
    row = _get_or_create_row(user["id"])
    if _active_for_mode(row) and row.get("stripe_subscription_id"):
        return {"already_active": True}

    init_stripe()
    try:
        price_id = ensure_indices_history_price_id()
    except Exception as e:
        logger.error(f"Could not ensure indices history price: {e}", exc_info=True)
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
    try:
        session = stripe.checkout.Session.create(
            customer=customer_id,
            payment_method_types=["card"],
            line_items=[{"price": price_id, "quantity": 1}],
            mode="subscription",
            success_url=f"{base}/users/account?indices_history=active",
            cancel_url=f"{base}/users/account?indices_history=cancelled",
            metadata={
                "user_id": str(user["id"]),
                "type": "indices_history",
            },
            subscription_data={
                "metadata": {
                    "user_id": str(user["id"]),
                    "type": "indices_history",
                }
            },
        )
    except Exception as e:
        logger.error(f"Indices history checkout creation failed: {e}", exc_info=True)
        raise HTTPException(500, "Failed to start checkout")

    return {"checkout_url": session.url}


@router.post("/api/indices-history/confirm")
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
            logger.error(f"Indices history confirm: customer search failed: {e}")
    if not customer_id:
        return {"active": False, "status": row["status"]}

    try:
        subs = stripe.Subscription.list(
            customer=customer_id, status="all", limit=100
        )
    except Exception as e:
        logger.error(f"Indices history confirm: could not list subscriptions: {e}")
        return {"active": False, "status": row["status"]}

    matched = None
    for sub in subs.get("data", []):
        meta = sub.get("metadata") or {}
        if meta.get("type") == "indices_history" and sub.get("status") in (
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
            UPDATE user_index_history_subs
            SET stripe_subscription_id = %s,
                stripe_customer_id = %s,
                status = %s,
                current_period_end = %s,
                stripe_mode = %s,
                updated_at = NOW()
            WHERE id = %s
        """, (subscription_id, customer_id, local_status, period_end_dt,
              matched_mode, row["id"]))
    logger.info(f"Indices history subscription activated via confirm for user {user['id']}")
    return {
        "active": local_status in ("active", "trialing", "canceling"),
        "status": local_status,
    }


@router.post("/api/indices-history/cancel")
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
                "UPDATE user_index_history_subs SET status = 'canceling', "
                "updated_at = NOW() WHERE id = %s",
                (row["id"],)
            )
        return {"canceled_at_period_end": True,
                "current_period_end": sub.get("current_period_end")}
    except Exception as e:
        logger.error(f"Indices history cancel error: {e}", exc_info=True)
        raise HTTPException(500, "Failed to cancel subscription")


@router.get("/api/indices-history/download")
async def download(
    index: str = Query(...),
    fmt: str = Query("csv"),
    x_user_token: Optional[str] = Header(None),
    limit: int = Query(default=1000, ge=1, le=1000),
):
    """Gated download: requires an active indices-history subscription, then
    reuses the existing per-index download generators."""
    user = _get_user_from_token(x_user_token)
    if not user:
        raise HTTPException(401, "Authentication required")
    row = _get_or_create_row(user["id"])
    # Runtime entitlement is mode-agnostic (mirrors WTI widget embed): a paying
    # subscriber must never be denied a download just because the app's Stripe
    # mode was toggled. Mode-awareness only gates account management (checkout).
    if not (_is_active(row) or _geri_live_bonus(user["id"])):
        raise HTTPException(402, "Active Indices History subscription required")

    index = (index or "").lower()
    fmt = (fmt or "csv").lower()
    if index not in _INDEX_DISPATCH:
        raise HTTPException(400, "Unknown index")
    if fmt not in ("csv", "xlsx"):
        raise HTTPException(400, "Unknown format")

    csv_name, xlsx_name = _INDEX_DISPATCH[index]
    func_name = csv_name if fmt == "csv" else xlsx_name

    from src.geri import routes as geri_routes
    func = getattr(geri_routes, func_name)
    return await func(x_user_token=x_user_token, limit=limit)


# ─────────────────────────────────────────────────────────────────────────────
# Webhook handlers (called from src.billing.webhook_handler by metadata.type)
# ─────────────────────────────────────────────────────────────────────────────

def handle_index_history_checkout_completed(session: dict) -> bool:
    user_id_str = (session.get("metadata") or {}).get("user_id")
    if not user_id_str:
        logger.error("Indices history checkout completed without user_id metadata")
        return True
    user_id = int(user_id_str)
    subscription_id = session.get("subscription")
    customer_id = session.get("customer")
    if not subscription_id:
        logger.error("Indices history checkout completed without subscription")
        return True
    ensure_stripe_initialized()
    try:
        sub = stripe.Subscription.retrieve(subscription_id)
    except Exception as e:
        logger.error(f"Could not retrieve indices history subscription {subscription_id}: {e}")
        return True
    period_end = sub.get("current_period_end")
    period_end_dt = datetime.utcfromtimestamp(period_end) if period_end else None
    status_val = sub.get("status", "active")
    mode = "live" if sub.get("livemode") else "sandbox"
    with get_cursor() as cur:
        cur.execute(
            "SELECT id FROM user_index_history_subs WHERE user_id = %s",
            (user_id,)
        )
        existing = cur.fetchone()
        if existing:
            cur.execute("""
                UPDATE user_index_history_subs
                SET stripe_subscription_id = %s,
                    stripe_customer_id = %s,
                    status = %s,
                    current_period_end = %s,
                    stripe_mode = %s,
                    updated_at = NOW()
                WHERE id = %s
            """, (subscription_id, customer_id, status_val, period_end_dt,
                  mode, existing["id"]))
        else:
            cur.execute("""
                INSERT INTO user_index_history_subs
                    (user_id, status, stripe_subscription_id, stripe_customer_id,
                     current_period_end, stripe_mode)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (user_id, status_val, subscription_id, customer_id,
                  period_end_dt, mode))
    logger.info(f"Indices history subscription activated for user {user_id}")
    return True


def handle_index_history_subscription_event(subscription: dict) -> bool:
    """Update row on subscription.updated. Returns True if this is an indices-history
    subscription (so the caller skips main plan logic)."""
    sub_id = subscription.get("id")
    if not sub_id:
        return False
    is_meta = (subscription.get("metadata") or {}).get("type") == "indices_history"
    with get_cursor() as cur:
        cur.execute(
            "SELECT id FROM user_index_history_subs WHERE stripe_subscription_id = %s",
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
            UPDATE user_index_history_subs
            SET status = %s, current_period_end = %s, updated_at = NOW()
            WHERE id = %s
        """, (local_status, period_end_dt, row["id"]))
    logger.info(f"Indices history subscription {sub_id} → status={local_status}")
    return True


def handle_index_history_subscription_deleted(subscription: dict) -> bool:
    sub_id = subscription.get("id")
    if not sub_id:
        return False
    with get_cursor() as cur:
        cur.execute(
            "SELECT id FROM user_index_history_subs WHERE stripe_subscription_id = %s",
            (sub_id,)
        )
        row = cur.fetchone()
        if not row:
            return False
        cur.execute("""
            UPDATE user_index_history_subs
            SET status = 'cancelled', updated_at = NOW()
            WHERE id = %s
        """, (row["id"],))
    logger.info(f"Indices history subscription {sub_id} cancelled")
    return True
