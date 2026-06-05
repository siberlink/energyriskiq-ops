"""
Europe Gas Storage Pro Widget — paid (€1.49/mo) embeddable intelligence widget.

Modeled exactly on the WTI Pro Widget (src/api/wti_pro_widget_routes.py) and
shares the same `user_pro_widgets` table (distinguished by widget_code).

Routes:
  GET  /embed/gas-storage-pro-widget        — token-gated runtime widget (iframe)
  GET  /widgets/gas-storage-pro.js          — JS loader for <script>+<div> embed
  GET  /api/widgets/gas-storage-pro/status  — account: status + config + token
  POST /api/widgets/gas-storage-pro/checkout
  POST /api/widgets/gas-storage-pro/confirm
  POST /api/widgets/gas-storage-pro/config
  POST /api/widgets/gas-storage-pro/rotate-token
  POST /api/widgets/gas-storage-pro/cancel

Live updates: the embed runtime self-refreshes every 60 s on the client site.
Custom-algorithm wording (never "AI"). Gold storage theme (#d4a017).
"""
import os
import json
import logging
import secrets
import html as _html
from datetime import datetime, timedelta
from typing import Optional

import stripe
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel

from src.db.db import get_cursor, execute_production_one, execute_production_query
from src.billing.stripe_client import (
    init_stripe,
    ensure_stripe_initialized,
    get_stripe_mode,
    create_customer,
    cancel_subscription as stripe_cancel_subscription,
)
from src.api.gas_storage_widget_routes import (
    _flag,
    _clamp,
    _band_level,
    _build_trend_sparkline,
    _compute_signals,
    EU_WINTER_TARGET,
    STORAGE_COLOR,
)
from src.api.snapshot_routes import BAND_COLORS, _safe_float

router = APIRouter(tags=["gas-storage-pro-widget"])
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

WIDGET_CODE = "gas-storage-pro"
WIDGET_PLAN_CODE = "widget_gas_storage_pro"   # Stripe product metadata key
WIDGET_TYPE = "gas_storage_pro_widget"        # Stripe/webhook routing key
WIDGET_PRICE_EUR_CENTS = 149                  # €1.49
WIDGET_NAME = "EnergyRiskIQ Pro Widget — Europe Gas Storage"
WIDGET_DESC = ("Professional embedded Europe gas storage intelligence widget — "
               "live EU storage %, winter readiness, 7D/30D charts, country "
               "leaderboard & comparison, custom-algorithm market summary, "
               "TTF connection, and seasonal comparison. €1.49/month.")

DEFAULT_CONFIG = {
    "theme": "dark",            # dark | light | glass | transparent
    "accent": "#d4a017",
    "size": "medium",           # compact | medium | large
    "mode": "macro",            # macro | trader | energy
    "radius": 14,
    "transparent": False,
    "sections": {"countries": True, "comparison": True,
                 "seasonal": True, "context": True},
}

SIZE_PRESETS = {
    "compact": {"w": 360, "h": 560},
    "medium":  {"w": 460, "h": 740},
    "large":   {"w": 720, "h": 880},
}

EMBED_HEADERS = {
    "Content-Security-Policy": "frame-ancestors *;",
    "Cache-Control": "public, max-age=60",
}

_GOOD_COLOR = "#22c55e"
_MOD_COLOR  = "#eab308"
_ELEV_COLOR = "#ef4444"


# ─────────────────────────────────────────────────────────────────────────────
# Migration (idempotent — shares user_pro_widgets with WTI Pro widget)
# ─────────────────────────────────────────────────────────────────────────────

def run_gas_storage_pro_widget_migration():
    try:
        with get_cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_pro_widgets (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    widget_code TEXT NOT NULL,
                    embed_token TEXT NOT NULL UNIQUE,
                    config_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                    stripe_subscription_id TEXT,
                    stripe_customer_id TEXT,
                    status TEXT NOT NULL DEFAULT 'inactive',
                    current_period_end TIMESTAMP,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    UNIQUE (user_id, widget_code)
                )
            """)
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_user_pro_widgets_token "
                "ON user_pro_widgets(embed_token)"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_user_pro_widgets_sub "
                "ON user_pro_widgets(stripe_subscription_id)"
            )
            cur.execute(
                "ALTER TABLE user_pro_widgets "
                "ADD COLUMN IF NOT EXISTS stripe_mode TEXT"
            )
        logger.info("gas-storage-pro widget migration complete")
    except Exception as e:
        logger.error(f"gas-storage-pro widget migration failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Stripe product seeding (idempotent, lazy)
# ─────────────────────────────────────────────────────────────────────────────

def _settings_key(name: str) -> str:
    return f"{name}_{get_stripe_mode()}"

def _get_stored_widget_price_id() -> Optional[str]:
    key = _settings_key("gas_storage_pro_widget_price_id")
    try:
        with get_cursor(commit=False) as cur:
            cur.execute("SELECT value FROM app_settings WHERE key = %s", (key,))
            row = cur.fetchone()
            return row["value"] if row else None
    except Exception:
        return None

def _store_widget_price_id(price_id: str, product_id: str):
    with get_cursor() as cur:
        for k, v in (("gas_storage_pro_widget_price_id", price_id),
                     ("gas_storage_pro_widget_product_id", product_id)):
            key = _settings_key(k)
            cur.execute("""
                INSERT INTO app_settings (key, value, updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (key) DO UPDATE
                  SET value = EXCLUDED.value, updated_at = NOW()
            """, (key, v))

def ensure_gas_storage_pro_widget_price_id() -> str:
    cached = _get_stored_widget_price_id()
    if cached:
        return cached
    ensure_stripe_initialized()
    product = None
    try:
        existing = stripe.Product.search(
            query=f"metadata['plan_code']:'{WIDGET_PLAN_CODE}'"
        )
        if existing.data:
            product = existing.data[0]
    except Exception as e:
        logger.warning(f"Stripe product search failed (will create): {e}")
    if not product:
        product = stripe.Product.create(
            name=WIDGET_NAME,
            description=WIDGET_DESC,
            metadata={"plan_code": WIDGET_PLAN_CODE,
                      "widget_code": WIDGET_CODE,
                      "kind": "widget"}
        )
        logger.info(f"Created Stripe gas-storage widget product {product.id}")
    price_id = None
    for p in stripe.Price.list(product=product.id, active=True, limit=100).data:
        if (p.unit_amount == WIDGET_PRICE_EUR_CENTS
            and p.currency == "eur"
            and p.recurring
            and p.recurring.get("interval") == "month"):
            price_id = p.id
            break
    if not price_id:
        price = stripe.Price.create(
            product=product.id,
            unit_amount=WIDGET_PRICE_EUR_CENTS,
            currency="eur",
            recurring={"interval": "month"},
            metadata={"widget_code": WIDGET_CODE, "plan_code": WIDGET_PLAN_CODE},
        )
        price_id = price.id
        logger.info(f"Created Stripe gas-storage widget price {price_id}")
    _store_widget_price_id(price_id, product.id)
    return price_id


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _base_url() -> str:
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


def _merge_config(stored) -> dict:
    if isinstance(stored, dict):
        cfg = stored
    elif isinstance(stored, str) and stored:
        try:
            cfg = json.loads(stored)
        except Exception:
            cfg = {}
    else:
        cfg = {}
    merged = {**DEFAULT_CONFIG, **cfg}
    merged["sections"] = {**DEFAULT_CONFIG["sections"],
                          **(merged.get("sections") or {})}
    return merged


def _get_or_create_widget_row(user_id: int):
    with get_cursor() as cur:
        cur.execute(
            "SELECT * FROM user_pro_widgets WHERE user_id = %s AND widget_code = %s",
            (user_id, WIDGET_CODE)
        )
        row = cur.fetchone()
        if row:
            return row
        token = secrets.token_urlsafe(24)
        cur.execute("""
            INSERT INTO user_pro_widgets
                (user_id, widget_code, embed_token, config_json, status)
            VALUES (%s, %s, %s, %s::jsonb, 'inactive')
            RETURNING *
        """, (user_id, WIDGET_CODE, token, json.dumps(DEFAULT_CONFIG)))
        return cur.fetchone()


def _widget_is_active(row) -> bool:
    """Status-only check — used by the public embed runtime so a live customer's
    widget keeps rendering regardless of the admin's current Stripe mode toggle."""
    if not row:
        return False
    return row.get("status") in ("active", "trialing", "canceling")


def _widget_active_for_mode(row) -> bool:
    """Mode-aware check — used by the account management flow."""
    if not _widget_is_active(row):
        return False
    row_mode = row.get("stripe_mode")
    if not row_mode:
        return True
    return row_mode == get_stripe_mode()


# ─────────────────────────────────────────────────────────────────────────────
# Account REST endpoints
# ─────────────────────────────────────────────────────────────────────────────

class ConfigUpdate(BaseModel):
    config: dict


@router.get("/api/widgets/gas-storage-pro/status")
async def widget_status(x_user_token: Optional[str] = Header(None)):
    user = _get_user_from_token(x_user_token)
    if not user:
        raise HTTPException(401, "Authentication required")
    row = _get_or_create_widget_row(user["id"])
    cfg = _merge_config(row["config_json"])
    return {
        "active": _widget_active_for_mode(row),
        "status": row["status"],
        "embed_token": row["embed_token"],
        "config": cfg,
        "current_period_end": (row["current_period_end"].isoformat()
                               if row.get("current_period_end") else None),
        "price_eur": WIDGET_PRICE_EUR_CENTS / 100.0,
        "size_presets": SIZE_PRESETS,
        "base_url": _base_url(),
    }


@router.post("/api/widgets/gas-storage-pro/checkout")
async def widget_checkout(x_user_token: Optional[str] = Header(None)):
    user = _get_user_from_token(x_user_token)
    if not user:
        raise HTTPException(401, "Authentication required")
    row = _get_or_create_widget_row(user["id"])
    if _widget_active_for_mode(row) and row.get("stripe_subscription_id"):
        return {"already_active": True}

    init_stripe()
    try:
        price_id = ensure_gas_storage_pro_widget_price_id()
    except Exception as e:
        logger.error(f"Could not ensure gas widget price: {e}", exc_info=True)
        raise HTTPException(500, "Widget billing not available")

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
            success_url=f"{base}/users/account?widget=gas_pro_active",
            cancel_url=f"{base}/users/account?widget=cancelled",
            metadata={
                "user_id": str(user["id"]),
                "type": WIDGET_TYPE,
                "widget_code": WIDGET_CODE,
            },
            subscription_data={
                "metadata": {
                    "user_id": str(user["id"]),
                    "type": WIDGET_TYPE,
                    "widget_code": WIDGET_CODE,
                }
            },
        )
    except Exception as e:
        logger.error(f"Gas widget checkout creation failed: {e}", exc_info=True)
        raise HTTPException(500, "Failed to start checkout")

    return {"checkout_url": session.url}


@router.post("/api/widgets/gas-storage-pro/confirm")
async def widget_confirm(x_user_token: Optional[str] = Header(None)):
    """Activate the widget by checking Stripe directly (webhook-independent)."""
    user = _get_user_from_token(x_user_token)
    if not user:
        raise HTTPException(401, "Authentication required")
    row = _get_or_create_widget_row(user["id"])

    if _widget_active_for_mode(row) and row.get("stripe_subscription_id"):
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
            logger.error(f"Gas widget confirm: customer search failed: {e}")
    if not customer_id:
        return {"active": False, "status": row["status"]}

    try:
        subs = stripe.Subscription.list(
            customer=customer_id, status="all", limit=100
        )
    except Exception as e:
        logger.error(f"Gas widget confirm: could not list subscriptions: {e}")
        return {"active": False, "status": row["status"]}

    matched = None
    for sub in subs.get("data", []):
        meta = sub.get("metadata") or {}
        if meta.get("type") == WIDGET_TYPE and sub.get("status") in (
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
            UPDATE user_pro_widgets
            SET stripe_subscription_id = %s,
                stripe_customer_id = %s,
                status = %s,
                current_period_end = %s,
                stripe_mode = %s,
                updated_at = NOW()
            WHERE id = %s
        """, (subscription_id, customer_id, local_status, period_end_dt,
              matched_mode, row["id"]))
    logger.info(f"Gas Storage Pro Widget activated via confirm for user {user['id']}")
    return {
        "active": local_status in ("active", "trialing", "canceling"),
        "status": local_status,
    }


@router.post("/api/widgets/gas-storage-pro/config")
async def widget_config_update(body: ConfigUpdate,
                               x_user_token: Optional[str] = Header(None)):
    user = _get_user_from_token(x_user_token)
    if not user:
        raise HTTPException(401, "Authentication required")
    row = _get_or_create_widget_row(user["id"])
    incoming = body.config or {}
    safe = json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy
    if incoming.get("theme") in ("dark", "light", "glass", "transparent"):
        safe["theme"] = incoming["theme"]
    if incoming.get("mode") in ("macro", "trader", "energy"):
        safe["mode"] = incoming["mode"]
    if incoming.get("size") in SIZE_PRESETS:
        safe["size"] = incoming["size"]
    accent = incoming.get("accent")
    if (isinstance(accent, str) and accent.startswith("#")
        and 4 <= len(accent) <= 9
        and all(c in "0123456789abcdefABCDEF" for c in accent[1:])):
        safe["accent"] = accent
    try:
        r = int(incoming.get("radius", 14))
        safe["radius"] = max(0, min(32, r))
    except Exception:
        pass
    safe["transparent"] = bool(incoming.get("transparent", False))
    secs = incoming.get("sections") or {}
    if isinstance(secs, dict):
        safe["sections"] = {
            k: bool(secs.get(k, DEFAULT_CONFIG["sections"][k]))
            for k in DEFAULT_CONFIG["sections"]
        }
    with get_cursor() as cur:
        cur.execute("""
            UPDATE user_pro_widgets
            SET config_json = %s::jsonb, updated_at = NOW()
            WHERE id = %s
        """, (json.dumps(safe), row["id"]))
    return {"saved": True, "config": safe}


@router.post("/api/widgets/gas-storage-pro/rotate-token")
async def widget_rotate_token(x_user_token: Optional[str] = Header(None)):
    user = _get_user_from_token(x_user_token)
    if not user:
        raise HTTPException(401, "Authentication required")
    row = _get_or_create_widget_row(user["id"])
    new_token = secrets.token_urlsafe(24)
    with get_cursor() as cur:
        cur.execute(
            "UPDATE user_pro_widgets SET embed_token = %s, updated_at = NOW() "
            "WHERE id = %s",
            (new_token, row["id"])
        )
    return {"embed_token": new_token}


@router.post("/api/widgets/gas-storage-pro/cancel")
async def widget_cancel(x_user_token: Optional[str] = Header(None)):
    user = _get_user_from_token(x_user_token)
    if not user:
        raise HTTPException(401, "Authentication required")
    row = _get_or_create_widget_row(user["id"])
    if not row["stripe_subscription_id"]:
        raise HTTPException(400, "No active subscription")
    if not _widget_active_for_mode(row):
        raise HTTPException(
            400, "No active subscription in the current billing mode"
        )
    init_stripe()
    try:
        sub = await stripe_cancel_subscription(row["stripe_subscription_id"],
                                               at_period_end=True)
        with get_cursor() as cur:
            cur.execute(
                "UPDATE user_pro_widgets SET status = 'canceling', updated_at = NOW() "
                "WHERE id = %s",
                (row["id"],)
            )
        return {"canceled_at_period_end": True,
                "current_period_end": sub.get("current_period_end")}
    except Exception as e:
        logger.error(f"Gas widget cancel error: {e}", exc_info=True)
        raise HTTPException(500, "Failed to cancel widget subscription")


# ─────────────────────────────────────────────────────────────────────────────
# Webhook hook — called from src/billing/webhook_handler.py
# (subscription.updated / .deleted and invoice.* are handled generically by the
#  WTI hooks + the shared user_pro_widgets table, so only checkout is needed.)
# ─────────────────────────────────────────────────────────────────────────────

def handle_widget_checkout_completed(session: dict) -> bool:
    """Mark widget active after Stripe Checkout completes. Returns True if handled."""
    if (session.get("metadata") or {}).get("type") != WIDGET_TYPE:
        return False
    user_id_str = (session.get("metadata") or {}).get("user_id")
    if not user_id_str:
        logger.error("Gas widget checkout completed without user_id metadata")
        return True
    user_id = int(user_id_str)
    subscription_id = session.get("subscription")
    customer_id = session.get("customer")
    if not subscription_id:
        logger.error("Gas widget checkout completed without subscription")
        return True
    ensure_stripe_initialized()
    try:
        sub = stripe.Subscription.retrieve(subscription_id)
    except Exception as e:
        logger.error(f"Could not retrieve gas widget subscription {subscription_id}: {e}")
        return True
    period_end = sub.get("current_period_end")
    period_end_dt = datetime.utcfromtimestamp(period_end) if period_end else None
    status = sub.get("status", "active")
    with get_cursor() as cur:
        cur.execute(
            "SELECT id, embed_token FROM user_pro_widgets "
            "WHERE user_id = %s AND widget_code = %s",
            (user_id, WIDGET_CODE)
        )
        existing = cur.fetchone()
        mode = "live" if sub.get("livemode") else "sandbox"
        if existing:
            cur.execute("""
                UPDATE user_pro_widgets
                SET stripe_subscription_id = %s,
                    stripe_customer_id = %s,
                    status = %s,
                    current_period_end = %s,
                    stripe_mode = %s,
                    updated_at = NOW()
                WHERE id = %s
            """, (subscription_id, customer_id, status, period_end_dt, mode, existing["id"]))
        else:
            token = secrets.token_urlsafe(24)
            cur.execute("""
                INSERT INTO user_pro_widgets
                    (user_id, widget_code, embed_token, config_json,
                     stripe_subscription_id, stripe_customer_id,
                     status, current_period_end, stripe_mode)
                VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s)
            """, (user_id, WIDGET_CODE, token, json.dumps(DEFAULT_CONFIG),
                  subscription_id, customer_id, status, period_end_dt, mode))
    logger.info(f"Gas Storage Pro Widget activated for user {user_id}")
    return True


def handle_widget_subscription_event(subscription: dict) -> bool:
    """Update widget row on subscription.updated. Returns True if gas widget sub (skip main plan)."""
    sub_id = subscription.get("id")
    if not sub_id:
        return False
    is_widget_meta = (subscription.get("metadata") or {}).get("type") == WIDGET_TYPE
    with get_cursor() as cur:
        cur.execute(
            "SELECT id FROM user_pro_widgets WHERE stripe_subscription_id = %s AND widget_code = %s",
            (sub_id, WIDGET_CODE)
        )
        row = cur.fetchone()
    if not row and not is_widget_meta:
        return False
    if not row:
        # metadata says gas widget but row missing → nothing to update, still skip main plan
        return True
    period_end = subscription.get("current_period_end")
    period_end_dt = datetime.utcfromtimestamp(period_end) if period_end else None
    status = subscription.get("status", "inactive")
    with get_cursor() as cur:
        cur.execute("""
            UPDATE user_pro_widgets
            SET status = %s, current_period_end = %s, updated_at = NOW()
            WHERE id = %s
        """, (status, period_end_dt, row["id"]))
    logger.info(f"Gas Storage Pro Widget subscription {sub_id} → status={status}")
    return True


def handle_widget_subscription_deleted(subscription: dict) -> bool:
    sub_id = subscription.get("id")
    if not sub_id:
        return False
    is_widget_meta = (subscription.get("metadata") or {}).get("type") == WIDGET_TYPE
    with get_cursor() as cur:
        cur.execute(
            "SELECT id FROM user_pro_widgets WHERE stripe_subscription_id = %s AND widget_code = %s",
            (sub_id, WIDGET_CODE)
        )
        row = cur.fetchone()
        if not row:
            return True if is_widget_meta else False
        cur.execute("""
            UPDATE user_pro_widgets
            SET status = 'cancelled', updated_at = NOW()
            WHERE id = %s
        """, (row["id"],))
    logger.info(f"Gas Storage Pro Widget subscription {sub_id} cancelled")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Data
# ─────────────────────────────────────────────────────────────────────────────

def _lookup_widget_by_token(token: str):
    if not token:
        return None
    with get_cursor(commit=False) as cur:
        cur.execute(
            "SELECT * FROM user_pro_widgets WHERE embed_token = %s",
            (token,)
        )
        return cur.fetchone()


def _fetch_pro_data():
    latest = execute_production_one(
        "SELECT date, eu_storage_percent, seasonal_norm, deviation_from_norm, "
        "refill_speed_7d, withdrawal_rate_7d, winter_deviation_risk, risk_score, risk_band "
        "FROM gas_storage_snapshots ORDER BY date DESC LIMIT 1"
    )

    week_ago = month_ago = None
    if latest and latest.get("date"):
        week_ago = execute_production_one(
            "SELECT eu_storage_percent FROM gas_storage_snapshots "
            "WHERE date <= %s ORDER BY date DESC LIMIT 1",
            (latest["date"] - timedelta(days=7),),
        )
        month_ago = execute_production_one(
            "SELECT eu_storage_percent FROM gas_storage_snapshots "
            "WHERE date <= %s ORDER BY date DESC LIMIT 1",
            (latest["date"] - timedelta(days=30),),
        )

    storage_hist = execute_production_query(
        "SELECT date, eu_storage_percent FROM gas_storage_snapshots "
        "WHERE eu_storage_percent IS NOT NULL ORDER BY date DESC LIMIT 30"
    ) or []
    storage_hist = list(reversed(storage_hist))

    countries = execute_production_query(
        "SELECT DISTINCT ON (country_code) "
        "country_code, country_name, storage_percent "
        "FROM gas_storage_country_snapshots "
        "WHERE level = 'country' AND storage_percent IS NOT NULL "
        "ORDER BY country_code, date DESC"
    ) or []

    eeri = execute_production_one(
        "SELECT value, band FROM reri_indices_daily "
        "WHERE index_id='europe:eeri' ORDER BY date DESC LIMIT 1"
    )
    egsi_m = execute_production_one(
        "SELECT index_value, band FROM egsi_m_daily "
        "WHERE region='Europe' ORDER BY index_date DESC LIMIT 1"
    )
    egsi_s = None
    try:
        egsi_s = execute_production_one(
            "SELECT index_value, band FROM egsi_s_daily "
            "ORDER BY index_date DESC LIMIT 1"
        )
    except Exception as exc:
        logger.warning(f"egsi_s fetch skipped: {exc}")
    geri = execute_production_one(
        "SELECT value, band FROM geri_live ORDER BY id DESC LIMIT 1"
    )

    ttf = execute_production_one(
        "SELECT date, ttf_price FROM ttf_gas_snapshots ORDER BY date DESC LIMIT 1"
    )
    ttf_prev = execute_production_one(
        "SELECT date, ttf_price FROM ttf_gas_snapshots "
        "ORDER BY date DESC LIMIT 1 OFFSET 1"
    )

    return {
        "latest": latest,
        "week_ago": week_ago,
        "month_ago": month_ago,
        "storage_hist": storage_hist,
        "countries": countries,
        "eeri": eeri,
        "egsi_m": egsi_m,
        "egsi_s": egsi_s,
        "geri": geri,
        "ttf": ttf,
        "ttf_prev": ttf_prev,
    }


def _storage_intelligence_text(mode, s, ttf_last, ttf_chg, eeri_band, egsi_band):
    dev = s["deviation"]
    pct = s["storage_pct"]
    wk = s.get("week_trend", 0.0)
    dirw = "rising" if wk > 0.3 else "falling" if wk < -0.3 else "broadly flat"

    if mode == "trader":
        ttfp = (f"TTF at €{ttf_last:.2f}/MWh ({ttf_chg:+.1f}%)"
                if (ttf_last is not None and ttf_chg is not None)
                else (f"TTF at €{ttf_last:.2f}/MWh" if ttf_last is not None else "TTF gas"))
        return (f"EU storage is {dirw} week-on-week ({wk:+.1f} pts), now {pct:.0f}% full and "
                f"{abs(dev):.0f} pts {'above' if dev >= 0 else 'below'} the seasonal norm. "
                f"{ttfp} is the key cross-check — injections that outpace seasonal norms "
                f"tend to cap gas upside, while faster-than-normal draws support it.")
    if mode == "energy":
        return (f"At {pct:.0f}% full, EU storage is tracking {abs(dev):.0f} pts "
                f"{'above' if dev >= 0 else 'below'} its seasonal norm and {dirw} week-on-week. "
                f"Refill economics hinge on LNG send-out and pipeline flows; the gap to the "
                f"{EU_WINTER_TARGET:.0f}% winter target frames how aggressively injections must run "
                f"into the shoulder season.")
    # macro default
    risk_phrase = {
        "low": "benign", "minimal": "benign", "calm": "benign",
        "moderate": "balanced", "medium": "balanced", "normal": "balanced",
        "elevated": "elevated", "high": "elevated",
        "severe": "acute", "critical": "acute", "extreme": "acute",
    }.get((eeri_band or "moderate").lower(), "balanced")
    return (f"EU gas storage sits at {pct:.0f}% against a {risk_phrase} European energy-risk "
            f"backdrop. Storage is {abs(dev):.0f} pts {'above' if dev >= 0 else 'below'} "
            f"the seasonal norm and {dirw} week-on-week, shaping near-term winter supply risk "
            f"and the gas-market premium.")


def _theme_colors(theme: str, accent: str, transparent: bool):
    if transparent:
        bg = "transparent"
        panel = "rgba(15,23,42,0.0)"
        text = "#0f172a" if theme == "light" else "#f1f5f9"
        muted = "#64748b" if theme == "light" else "#94a3b8"
        border = "rgba(148,163,184,0.18)"
    elif theme == "light":
        bg = "#ffffff"; panel = "#f8fafc"; text = "#0f172a"; muted = "#64748b"
        border = "#e2e8f0"
    elif theme == "glass":
        bg = "rgba(15,23,42,0.55)"; panel = "rgba(30,41,59,0.45)"
        text = "#f1f5f9"; muted = "#94a3b8"; border = "rgba(148,163,184,0.25)"
    else:  # dark
        bg = "#0b1220"; panel = "#0f172a"; text = "#f1f5f9"
        muted = "#94a3b8"; border = "#1e293b"
    return {"bg": bg, "panel": panel, "text": text, "muted": muted,
            "border": border, "accent": accent}


def _range_meta(rows):
    vals = [float(r["eu_storage_percent"]) for r in (rows or [])
            if r.get("eu_storage_percent") is not None]
    if not vals:
        return ("—", "—", "—")
    lo, hi = min(vals), max(vals)
    first, last = vals[0], vals[-1]
    cp = last - first
    return (f"{lo:.0f}%", f"{hi:.0f}%", f"{cp:+.1f} pts")


def _render_pro_widget_html(row, q) -> str:
    cfg = _merge_config(row["config_json"])
    if q.get("theme") in ("dark", "light", "glass", "transparent"):
        cfg["theme"] = q["theme"]
    if q.get("size") in SIZE_PRESETS:
        cfg["size"] = q["size"]
    if q.get("mode") in ("macro", "trader", "energy"):
        cfg["mode"] = q["mode"]
    _q_accent = q.get("accent", "")
    if (isinstance(_q_accent, str) and _q_accent.startswith("#")
            and len(_q_accent) in (4, 7)
            and all(c in "0123456789abcdefABCDEF" for c in _q_accent[1:])):
        cfg["accent"] = _q_accent
    if q.get("transparent") is not None and q["transparent"] != "":
        cfg["transparent"] = q["transparent"].lower() in ("1", "true", "yes")
    if q.get("sections") is not None and q["sections"] != "":
        toks = [t.strip() for t in q["sections"].split(",") if t.strip()]
        cfg["sections"] = {k: (k in toks) for k in DEFAULT_CONFIG["sections"]}

    theme = _theme_colors(cfg["theme"], cfg["accent"], bool(cfg.get("transparent")))
    radius = int(cfg.get("radius", 14))
    accent = cfg["accent"]
    secs = cfg.get("sections") or {}

    data = _fetch_pro_data()
    latest = data.get("latest") or {}
    if not latest or latest.get("eu_storage_percent") is None:
        return _render_unavailable_html(cfg, theme, radius,
                                        "Gas storage data is temporarily unavailable.")

    s = _compute_signals(data)
    # Week-over-week headline change
    wa = data.get("week_ago") or {}
    prev_wk = _safe_float(wa.get("eu_storage_percent"), s["storage_pct"])
    week_trend = s["storage_pct"] - prev_wk
    s["week_trend"] = week_trend

    storage_pct = s["storage_pct"]
    deviation = s["deviation"]
    seasonal = s["seasonal"]
    ts_str = s["date"].isoformat() if s.get("date") else datetime.utcnow().strftime("%Y-%m-%d")

    tr_color = "#22c55e" if week_trend > 0 else "#ef4444" if week_trend < 0 else theme["muted"]
    tr_arrow = "▲" if week_trend > 0 else "▼" if week_trend < 0 else "■"

    dev_color = "#22c55e" if deviation >= 0 else "#ef4444"
    dev_sign = "+" if deviation >= 0 else ""

    # Charts (7D / 30D)
    hist = data.get("storage_hist") or []
    hist_30 = hist[-30:]
    hist_7 = hist[-7:]
    chart_7 = _build_trend_sparkline(hist_7, color=accent, height=70, width=320)
    chart_30 = _build_trend_sparkline(hist_30, color=accent, height=70, width=320)
    lo7, hi7, ch7 = _range_meta(hist_7)
    lo30, hi30, ch30 = _range_meta(hist_30)

    # Winter target progress
    target_pct = _clamp(storage_pct / EU_WINTER_TARGET * 100.0, 0, 100)

    # Country leaderboard
    countries_html = ""
    if secs.get("countries"):
        rows_html = ""
        for code, name, pct in s["all_countries"][:6]:
            rows_html += (
                f'<div class="gw-ctry">'
                f'<span class="gw-ctry-name">{_flag(code)} {_html.escape(code)}</span>'
                f'<span class="gw-ctry-val">{pct:.0f}%</span>'
                f'</div>'
            )
        if not rows_html:
            rows_html = '<div class="gw-ctry"><span class="gw-ctry-name">Awaiting country data</span></div>'
        countries_html = (
            f'<div class="gw-section-title">Country Leaderboard</div>'
            f'<div class="gw-ctry-grid">{rows_html}</div>'
        )

    # Country comparison bar chart
    comparison_html = ""
    if secs.get("comparison"):
        bars = ""
        top = s["all_countries"][:6]
        for code, name, pct in top:
            w = _clamp(pct, 0, 100)
            bars += (
                f'<div class="gw-bar-row">'
                f'<span class="gw-bar-lbl">{_flag(code)} {_html.escape(code)}</span>'
                f'<span class="gw-bar-track"><span class="gw-bar-fill" style="width:{w:.0f}%;"></span></span>'
                f'<span class="gw-bar-val">{pct:.0f}%</span>'
                f'</div>'
            )
        if bars:
            comparison_html = (
                f'<div class="gw-section-title">Country Comparison</div>'
                f'<div class="gw-bars">{bars}</div>'
            )

    # TTF + market context
    ttf = data.get("ttf") or {}
    ttf_prev = data.get("ttf_prev") or {}
    ttf_last = _safe_float(ttf.get("ttf_price")) if ttf else None
    ttf_prev_val = _safe_float(ttf_prev.get("ttf_price")) if ttf_prev else None
    ttf_chg = None
    if ttf_last is not None and ttf_prev_val:
        ttf_chg = (ttf_last - ttf_prev_val) / ttf_prev_val * 100

    eeri = data.get("eeri") or {}
    egsi_m = data.get("egsi_m") or {}
    geri = data.get("geri") or {}
    eeri_band = (eeri.get("band") or "moderate")
    egsi_band = (egsi_m.get("band") or "moderate")
    geri_band = (geri.get("band") or "moderate")
    egsi_val = _safe_float(egsi_m.get("index_value"))
    geri_val = _safe_float(geri.get("value"))
    geri_color = BAND_COLORS.get(geri_band, "#f97316")
    egsi_color = BAND_COLORS.get(egsi_band, "#f97316")

    context_html = ""
    if secs.get("context"):
        pills = []
        if ttf_last is not None:
            ttf_c = theme["muted"]
            ttf_extra = ""
            if ttf_chg is not None:
                ttf_c = "#22c55e" if ttf_chg <= 0 else "#ef4444"
                ttf_extra = f" {ttf_chg:+.1f}%"
            pills.append(
                f'<span class="gw-pill"><b style="color:{theme["muted"]};">TTF</b> '
                f'€{ttf_last:.2f}<span style="color:{ttf_c};">{ttf_extra}</span></span>'
            )
        if geri_val is not None:
            pills.append(
                f'<span class="gw-pill" style="border-color:{geri_color}55;">'
                f'<b style="color:{geri_color};">GERI</b> {geri_val:.1f}</span>'
            )
        if eeri.get("band"):
            ee_c = BAND_COLORS.get(eeri_band, "#f97316")
            pills.append(
                f'<span class="gw-pill" style="border-color:{ee_c}55;">'
                f'<b style="color:{ee_c};">EERI</b> {eeri_band.title()}</span>'
            )
        if egsi_val is not None:
            pills.append(
                f'<span class="gw-pill" style="border-color:{egsi_color}55;">'
                f'<b style="color:{egsi_color};">EGSI-M</b> {egsi_val:.0f}</span>'
            )
        if pills:
            context_html = (
                f'<div class="gw-section-title">Market Context</div>'
                f'<div class="gw-pills">{"".join(pills)}</div>'
            )

    # Seasonal comparison
    seasonal_html = ""
    if secs.get("seasonal"):
        cur_w = _clamp(storage_pct, 0, 100)
        norm_w = _clamp(seasonal, 0, 100) if seasonal else 0
        seasonal_html = (
            f'<div class="gw-section-title">Seasonal Comparison</div>'
            f'<div class="gw-seasonal">'
            f'<div class="gw-bar-row"><span class="gw-bar-lbl">Current</span>'
            f'<span class="gw-bar-track"><span class="gw-bar-fill" style="width:{cur_w:.0f}%;"></span></span>'
            f'<span class="gw-bar-val">{storage_pct:.0f}%</span></div>'
            f'<div class="gw-bar-row"><span class="gw-bar-lbl">Norm (5-Yr)</span>'
            f'<span class="gw-bar-track"><span class="gw-bar-fill" style="width:{norm_w:.0f}%;opacity:.5;"></span></span>'
            f'<span class="gw-bar-val">{seasonal:.0f}%</span></div>'
            f'<div class="gw-seasonal-note">Deviation '
            f'<b style="color:{dev_color};">{dev_sign}{deviation:.1f} pts</b> vs seasonal norm</div>'
            f'</div>'
        )

    intelligence = _storage_intelligence_text(cfg["mode"], s, ttf_last, ttf_chg,
                                              eeri_band, egsi_band)

    size = SIZE_PRESETS.get(cfg["size"], SIZE_PRESETS["medium"])

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="60">
<title>Europe Gas Storage — Pro Widget</title>
<style>
*,*::before,*::after {{ box-sizing:border-box; }}
html,body {{ margin:0; padding:0; background:{theme['bg']}; color:{theme['text']};
  font-family:'Inter',system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;
  font-size:14px; line-height:1.45; }}
.gw-pro {{
  background:{theme['bg']}; color:{theme['text']};
  border:1px solid {theme['border']}; border-radius:{radius}px;
  overflow:hidden; width:100%; max-width:{size['w']}px; margin:0 auto;
}}
.gw-head {{ padding:14px 16px 4px; display:flex; justify-content:space-between; align-items:flex-start; gap:8px; }}
.gw-title {{ font-size:13px; font-weight:600; letter-spacing:.2px; }}
.gw-sub {{ font-size:11px; color:{theme['muted']}; margin-top:2px; }}
.gw-livedot {{ display:inline-block; width:7px; height:7px; border-radius:50%;
  background:{accent}; margin-right:6px; box-shadow:0 0 0 0 {accent}66; animation:gwPulse 2s infinite; }}
@keyframes gwPulse {{ 0% {{ box-shadow:0 0 0 0 {accent}66; }} 70% {{ box-shadow:0 0 0 8px {accent}00; }} 100% {{ box-shadow:0 0 0 0 {accent}00; }} }}
.gw-price-row {{ padding:6px 16px 6px; display:flex; align-items:baseline; gap:10px; flex-wrap:wrap; }}
.gw-price {{ font-size:32px; font-weight:700; letter-spacing:-.5px; }}
.gw-price small {{ font-size:14px; font-weight:600; color:{theme['muted']}; }}
.gw-change {{ font-size:12.5px; font-weight:600; color:{tr_color}; }}
.gw-updated {{ padding:0 16px 8px; font-size:10px; color:{theme['muted']}; }}
.gw-badges {{ padding:2px 14px 8px; display:flex; flex-wrap:wrap; gap:6px; }}
.gw-badge {{ font-size:10.5px; font-weight:700; padding:4px 9px; border-radius:999px; border:1px solid {theme['border']}; }}
.gw-target {{ padding:0 16px 6px; }}
.gw-target-track {{ height:7px; border-radius:999px; background:{theme['panel']}; border:1px solid {theme['border']}; overflow:hidden; }}
.gw-target-fill {{ height:100%; background:{accent}; width:{target_pct:.0f}%; display:block; }}
.gw-target-lbl {{ font-size:9.5px; color:{theme['muted']}; margin-top:3px; display:flex; justify-content:space-between; }}
.gw-section-title {{ padding:10px 16px 4px; font-size:10.5px; font-weight:600; color:{theme['muted']}; text-transform:uppercase; letter-spacing:.6px; }}
.gw-daily-panel {{ padding:0 12px 6px; }}
.gw-tabs {{ display:flex; gap:4px; padding:0 4px 6px; }}
.gw-tab {{ flex:0 0 auto; cursor:pointer; font-size:11px; font-weight:600; padding:5px 10px; border-radius:999px; border:1px solid {theme['border']}; background:transparent; color:{theme['muted']}; }}
.gw-tab.active {{ background:{accent}1a; color:{accent}; border-color:{accent}66; }}
.gw-pane {{ display:none; }}
.gw-pane.active {{ display:block; }}
.gw-range-stats {{ display:flex; justify-content:space-between; gap:6px; padding:6px 6px 0; font-size:10.5px; color:{theme['muted']}; }}
.gw-range-stats b {{ color:{theme['text']}; font-weight:600; }}
.gw-ctry-grid {{ padding:0 14px 6px; display:grid; grid-template-columns:repeat(3,1fr); gap:6px; }}
.gw-ctry {{ display:flex; justify-content:space-between; align-items:center; gap:6px; padding:6px 8px; border-radius:8px; background:{theme['panel']}; border:1px solid {theme['border']}; font-size:11px; }}
.gw-ctry-name {{ color:{theme['text']}; font-weight:600; }}
.gw-ctry-val {{ color:{accent}; font-weight:700; }}
.gw-bars {{ padding:0 16px 6px; display:flex; flex-direction:column; gap:6px; }}
.gw-seasonal {{ padding:0 16px 6px; display:flex; flex-direction:column; gap:6px; }}
.gw-bar-row {{ display:flex; align-items:center; gap:8px; font-size:11px; }}
.gw-bar-lbl {{ flex:0 0 64px; color:{theme['text']}; font-weight:600; }}
.gw-bar-track {{ flex:1 1 auto; height:9px; border-radius:999px; background:{theme['panel']}; border:1px solid {theme['border']}; overflow:hidden; }}
.gw-bar-fill {{ display:block; height:100%; background:{accent}; }}
.gw-bar-val {{ flex:0 0 38px; text-align:right; color:{theme['text']}; font-weight:700; }}
.gw-seasonal-note {{ font-size:11px; color:{theme['muted']}; margin-top:2px; }}
.gw-pills {{ padding:2px 14px 8px; display:flex; flex-wrap:wrap; gap:6px; }}
.gw-pill {{ font-size:10.5px; padding:4px 8px; border-radius:999px; border:1px solid {theme['border']}; background:{theme['panel']}; color:{theme['text']}; display:inline-flex; align-items:center; gap:4px; }}
.gw-intel {{ margin:8px 14px; padding:10px 12px; border-radius:{max(8, radius-2)}px; background:{theme['panel']}; border:1px solid {theme['border']}; font-size:12px; color:{theme['text']}; line-height:1.55; }}
.gw-intel-label {{ display:inline-block; font-size:9.5px; font-weight:700; color:{accent}; letter-spacing:.7px; text-transform:uppercase; margin-bottom:4px; }}
.gw-signals {{ margin:0 14px 12px; padding:8px 10px; border-radius:{max(8, radius-2)}px; background:{theme['panel']}; border:1px solid {theme['border']}; display:grid; grid-template-columns:repeat(3,1fr); gap:6px; text-align:center; }}
.gw-signal {{ display:flex; flex-direction:column; gap:2px; }}
.gw-signal-label {{ font-size:9.5px; color:{theme['muted']}; text-transform:uppercase; letter-spacing:.5px; }}
.gw-signal-val {{ font-size:12px; font-weight:700; }}
@media (max-width:380px) {{
  .gw-price {{ font-size:27px; }}
  .gw-ctry-grid {{ grid-template-columns:repeat(2,1fr); }}
}}
</style>
</head>
<body>
<div class="gw-pro">
  <div class="gw-head">
    <div>
      <div class="gw-title">Europe Gas Storage</div>
      <div class="gw-sub"><span class="gw-livedot"></span>Live Storage Intelligence</div>
    </div>
  </div>
  <div class="gw-price-row">
    <div class="gw-price">{storage_pct:.1f}<small>%</small></div>
    <div class="gw-change">{tr_arrow} {week_trend:+.1f} pts / wk</div>
  </div>
  <div class="gw-updated">EU storage full · Updated {ts_str} · <span style="color:{dev_color};">{dev_sign}{deviation:.1f} pts vs norm</span></div>

  <div class="gw-badges">
    <span class="gw-badge" style="color:{s['readiness_color']};border-color:{s['readiness_color']}55;">Winter Readiness · {s['readiness']} {s['readiness_label']}</span>
    <span class="gw-badge" style="color:{s['risk_color']};border-color:{s['risk_color']}55;">Storage Risk · {s['risk_label']}</span>
  </div>

  <div class="gw-target">
    <div class="gw-target-track"><span class="gw-target-fill"></span></div>
    <div class="gw-target-lbl"><span>Progress to {EU_WINTER_TARGET:.0f}% winter target</span><span>{target_pct:.0f}%</span></div>
  </div>

  <div class="gw-section-title">Storage Trend</div>
  <div class="gw-daily-panel">
    <div class="gw-tabs">
      <button type="button" class="gw-tab active" data-pane="gwPane7">7D</button>
      <button type="button" class="gw-tab" data-pane="gwPane30">30D</button>
    </div>
    <div id="gwPane7" class="gw-pane active">
      {chart_7}
      <div class="gw-range-stats"><span>Low <b>{lo7}</b></span><span>High <b>{hi7}</b></span><span>7D Chg <b>{ch7}</b></span></div>
    </div>
    <div id="gwPane30" class="gw-pane">
      {chart_30}
      <div class="gw-range-stats"><span>Low <b>{lo30}</b></span><span>High <b>{hi30}</b></span><span>30D Chg <b>{ch30}</b></span></div>
    </div>
  </div>

  {countries_html}
  {comparison_html}

  <div class="gw-intel">
    <div class="gw-intel-label">Storage Intelligence · {cfg['mode'].title()} Mode</div>
    {_html.escape(intelligence)}
  </div>

  {context_html}
  {seasonal_html}

  <div class="gw-signals">
    <div class="gw-signal"><div class="gw-signal-label">Readiness</div><div class="gw-signal-val" style="color:{s['readiness_color']};">{s['readiness_label']}</div></div>
    <div class="gw-signal"><div class="gw-signal-label">Storage Risk</div><div class="gw-signal-val" style="color:{s['risk_color']};">{s['risk_label']}</div></div>
    <div class="gw-signal"><div class="gw-signal-label">Gas Stress</div><div class="gw-signal-val" style="color:{egsi_color};">{egsi_band.title()}</div></div>
  </div>
</div>
<script>
(function(){{
  var tabs=document.querySelectorAll('.gw-tab');
  tabs.forEach(function(t){{
    t.addEventListener('click',function(){{
      tabs.forEach(function(x){{ x.classList.remove('active'); }});
      document.querySelectorAll('.gw-pane').forEach(function(p){{ p.classList.remove('active'); }});
      t.classList.add('active');
      var p=document.getElementById(t.getAttribute('data-pane'));
      if(p) p.classList.add('active');
    }});
  }});
  setTimeout(function(){{ try {{ location.reload(); }} catch(e) {{}} }}, 60000);
}})();
</script>
</body>
</html>"""


def _render_unavailable_html(cfg, theme, radius, msg):
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="120">
<title>Europe Gas Storage Pro Widget</title>
<style>
html,body{{margin:0;padding:0;background:{theme['bg']};color:{theme['text']};
font-family:'Inter',system-ui,sans-serif;}}
.box{{padding:20px;border:1px solid {theme['border']};border-radius:{radius}px;
max-width:420px;margin:20px auto;background:{theme['panel']};text-align:center;}}
</style></head><body><div class="box">
<div style="font-weight:600;margin-bottom:6px;">Europe Gas Storage</div>
<div style="font-size:12px;color:{theme['muted']};">{_html.escape(msg)}</div>
</div></body></html>"""


def _render_inactive_html() -> str:
    return """<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Europe Gas Storage Pro Widget — Inactive</title>
<style>
html,body{margin:0;padding:0;background:#0b1220;color:#f1f5f9;
font-family:'Inter',system-ui,sans-serif;}
.box{padding:24px;border:1px solid #1e293b;border-radius:12px;
max-width:380px;margin:24px auto;background:#0f172a;text-align:center;}
.t{font-weight:700;color:#d4a017;font-size:13px;letter-spacing:.5px;text-transform:uppercase;}
.h{font-size:18px;margin:8px 0 6px;}
.p{font-size:12px;color:#94a3b8;line-height:1.5;}
a{color:#d4a017;text-decoration:none;}
</style></head><body><div class="box">
<div class="t">Widget Inactive</div>
<div class="h">Europe Gas Storage Pro Widget</div>
<div class="p">This widget requires an active subscription. Manage your widget in your
<a href="https://energyriskiq.com/users/account">EnergyRiskIQ account</a>.</div>
</div></body></html>"""


@router.get("/embed/gas-storage-pro-widget", response_class=HTMLResponse)
async def embed_gas_storage_pro_widget(request: Request):
    qp = request.query_params
    token = qp.get("t") or qp.get("token") or ""
    row = _lookup_widget_by_token(token)
    if not row or not _widget_is_active(row):
        return HTMLResponse(_render_inactive_html(), headers=EMBED_HEADERS)
    try:
        html = _render_pro_widget_html(row, dict(qp))
    except Exception as e:
        logger.error(f"Gas Pro widget render error: {e}", exc_info=True)
        theme = _theme_colors("dark", "#d4a017", False)
        html = _render_unavailable_html({}, theme, 14,
                                         "Temporary data error — please retry shortly.")
    return HTMLResponse(html, headers=EMBED_HEADERS)


# ─────────────────────────────────────────────────────────────────────────────
# JS loader  — <script src=".../gas-storage-pro.js"></script>
#              <div data-eriq-widget="gas-storage-pro" data-token="..."></div>
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/widgets/gas-storage-pro.js")
async def widgets_gas_storage_pro_js():
    base = _base_url()
    js = (
        "/* EnergyRiskIQ Europe Gas Storage Pro Widget loader */\n"
        "(function(){\n"
        "  var BASE=" + json.dumps(base) + ";\n"
        "  function build(el){\n"
        "    if(el.getAttribute('data-eriq-loaded')==='1') return;\n"
        "    el.setAttribute('data-eriq-loaded','1');\n"
        "    var t=el.getAttribute('data-token')||'';\n"
        "    var theme=el.getAttribute('data-theme')||'';\n"
        "    var size=el.getAttribute('data-size')||'';\n"
        "    var mode=el.getAttribute('data-mode')||'';\n"
        "    var accent=el.getAttribute('data-accent')||'';\n"
        "    var transparent=el.getAttribute('data-transparent')||'';\n"
        "    var sections=el.getAttribute('data-sections')||'';\n"
        "    var q=['t='+encodeURIComponent(t)];\n"
        "    if(theme) q.push('theme='+encodeURIComponent(theme));\n"
        "    if(size)  q.push('size='+encodeURIComponent(size));\n"
        "    if(mode)  q.push('mode='+encodeURIComponent(mode));\n"
        "    if(accent)q.push('accent='+encodeURIComponent(accent));\n"
        "    if(transparent) q.push('transparent='+encodeURIComponent(transparent));\n"
        "    if(sections)    q.push('sections='+encodeURIComponent(sections));\n"
        "    var sizes={compact:[360,560],medium:[460,740],large:[720,880]};\n"
        "    var dims=sizes[size]||sizes.medium;\n"
        "    var f=document.createElement('iframe');\n"
        "    f.src=BASE+'/embed/gas-storage-pro-widget?'+q.join('&');\n"
        "    f.title='Europe Gas Storage Pro Widget';\n"
        "    f.loading='lazy';\n"
        "    f.style.border='0'; f.style.display='block';\n"
        "    f.style.width='100%'; f.style.maxWidth=dims[0]+'px';\n"
        "    f.style.height=dims[1]+'px';\n"
        "    f.setAttribute('allowtransparency','true');\n"
        "    el.appendChild(f);\n"
        "  }\n"
        "  function init(){\n"
        "    var nodes=document.querySelectorAll('[data-eriq-widget=\"gas-storage-pro\"]');\n"
        "    for(var i=0;i<nodes.length;i++) build(nodes[i]);\n"
        "  }\n"
        "  if(document.readyState==='loading'){\n"
        "    document.addEventListener('DOMContentLoaded', init);\n"
        "  } else { init(); }\n"
        "})();\n"
    )
    return PlainTextResponse(
        js,
        media_type="application/javascript",
        headers={"Cache-Control": "public, max-age=300",
                 "Access-Control-Allow-Origin": "*"},
    )
