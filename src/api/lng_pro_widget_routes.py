"""
Global LNG Intelligence Pro Widget — paid (€1.95/mo) embeddable intelligence widget.

Routes:
  GET  /embed/lng-pro-widget          — token-gated runtime widget (iframe)
  GET  /widgets/lng-pro.js            — JS loader for <script>+<div> embed pattern
  GET  /api/widgets/lng-pro/status    — account: subscription status + config + token
  POST /api/widgets/lng-pro/checkout  — account: start Stripe checkout (€1.95/mo)
  POST /api/widgets/lng-pro/confirm   — account: webhook-independent activation
  POST /api/widgets/lng-pro/config    — account: save customization
  POST /api/widgets/lng-pro/rotate-token
  POST /api/widgets/lng-pro/cancel    — account: cancel at period end

Live updates: the embed runtime self-refreshes every 60 s on the client site.
Mirrors src/api/wti_pro_widget_routes.py — shared user_pro_widgets table.
"""
import os
import json
import logging
import secrets
import html as _html
from datetime import datetime
from typing import Optional

import stripe
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel

from src.db.db import get_cursor, execute_production_one
from src.billing.stripe_client import (
    init_stripe,
    ensure_stripe_initialized,
    get_stripe_mode,
    create_customer,
    cancel_subscription as stripe_cancel_subscription,
)
from src.api.lng_widget_routes import (
    _fetch_widget_data,
    _build_mini_chart_svg,
    _lng_trend,
    _ttf_spread_usd,
    LNG_COLOR,
)
from src.api.snapshot_routes import BAND_COLORS, _safe_float

router = APIRouter(tags=["lng-pro-widget"])
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

WIDGET_CODE = "lng-pro"
WIDGET_PLAN_CODE = "widget_lng_pro"   # Stripe product metadata key
WIDGET_TYPE = "lng_pro_widget"        # checkout/subscription metadata.type
WIDGET_PRICE_EUR_CENTS = 195          # €1.95
WIDGET_NAME = "EnergyRiskIQ Pro Widget — Global LNG Intelligence"
WIDGET_DESC = ("Professional embedded Global LNG market intelligence widget — "
               "live JKM price, 7D/30D charts, JKM–TTF spread, custom-algorithm "
               "market summary, flow direction, and energy-risk signals. €1.95/month.")

DEFAULT_CONFIG = {
    "theme": "dark",            # dark | light | glass | transparent
    "accent": "#d4a017",
    "size": "medium",           # compact | medium | large
    "mode": "macro",            # macro | trader | energy
    "radius": 12,
    "transparent": False,
    "overlays": {"spread": True, "geri": True, "vix": False, "storage": True},
}

SIZE_PRESETS = {
    "compact": {"w": 350, "h": 440},
    "medium":  {"w": 450, "h": 580},
    "large":   {"w": 700, "h": 700},
}

EMBED_HEADERS = {
    "Content-Security-Policy": "frame-ancestors *;",
    "Cache-Control": "public, max-age=60",
}


# ─────────────────────────────────────────────────────────────────────────────
# Migration (called from app startup) — shared user_pro_widgets table, idempotent
# ─────────────────────────────────────────────────────────────────────────────

def run_lng_pro_widget_migration():
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
        logger.info("lng-pro widget migration complete")
    except Exception as e:
        logger.error(f"lng_pro_widget migration failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Stripe product seeding (idempotent, lazy)
# ─────────────────────────────────────────────────────────────────────────────

def _settings_key(name: str) -> str:
    return f"{name}_{get_stripe_mode()}"

def _get_stored_widget_price_id() -> Optional[str]:
    key = _settings_key("lng_pro_widget_price_id")
    try:
        with get_cursor(commit=False) as cur:
            cur.execute("SELECT value FROM app_settings WHERE key = %s", (key,))
            row = cur.fetchone()
            return row["value"] if row else None
    except Exception:
        return None

def _store_widget_price_id(price_id: str, product_id: str):
    with get_cursor() as cur:
        for k, v in (("lng_pro_widget_price_id", price_id),
                     ("lng_pro_widget_product_id", product_id)):
            key = _settings_key(k)
            cur.execute("""
                INSERT INTO app_settings (key, value, updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (key) DO UPDATE
                  SET value = EXCLUDED.value, updated_at = NOW()
            """, (key, v))

def ensure_lng_pro_widget_price_id() -> str:
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
        logger.info(f"Created Stripe widget product {product.id}")
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
        logger.info(f"Created Stripe widget price {price_id}")
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
    merged["overlays"] = {**DEFAULT_CONFIG["overlays"],
                          **(merged.get("overlays") or {})}
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


def _geri_live_bonus(user_id) -> bool:
    """GERI Live launch-offer bonus: an active GERI Live subscription also
    unlocks this Pro widget. Ends automatically when GERI Live is cancelled."""
    try:
        from src.api.geri_live_sub_routes import user_has_geri_live
        return user_has_geri_live(user_id)
    except Exception:
        return False


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


@router.get("/api/widgets/lng-pro/status")
async def widget_status(x_user_token: Optional[str] = Header(None)):
    user = _get_user_from_token(x_user_token)
    if not user:
        raise HTTPException(401, "Authentication required")
    row = _get_or_create_widget_row(user["id"])
    cfg = _merge_config(row["config_json"])
    bonus = _geri_live_bonus(user["id"])
    return {
        "active": _widget_active_for_mode(row) or bonus,
        "geri_live_bonus": bonus,
        "status": row["status"],
        "embed_token": row["embed_token"],
        "config": cfg,
        "current_period_end": (row["current_period_end"].isoformat()
                               if row.get("current_period_end") else None),
        "price_eur": WIDGET_PRICE_EUR_CENTS / 100.0,
        "size_presets": SIZE_PRESETS,
        "base_url": _base_url(),
    }


@router.post("/api/widgets/lng-pro/checkout")
async def widget_checkout(x_user_token: Optional[str] = Header(None)):
    user = _get_user_from_token(x_user_token)
    if not user:
        raise HTTPException(401, "Authentication required")
    row = _get_or_create_widget_row(user["id"])
    if _widget_active_for_mode(row) and row.get("stripe_subscription_id"):
        return {"already_active": True}

    init_stripe()
    try:
        price_id = ensure_lng_pro_widget_price_id()
    except Exception as e:
        logger.error(f"Could not ensure widget price: {e}", exc_info=True)
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
            success_url=f"{base}/users/account?widget=lng_pro_active",
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
        logger.error(f"Widget checkout creation failed: {e}", exc_info=True)
        raise HTTPException(500, "Failed to start checkout")

    return {"checkout_url": session.url}


@router.post("/api/widgets/lng-pro/confirm")
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
            logger.error(f"Widget confirm: customer search failed: {e}")
    if not customer_id:
        return {"active": False, "status": row["status"]}

    try:
        subs = stripe.Subscription.list(
            customer=customer_id, status="all", limit=100
        )
    except Exception as e:
        logger.error(f"Widget confirm: could not list subscriptions: {e}")
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
    logger.info(f"LNG Pro Widget activated via confirm for user {user['id']}")
    return {
        "active": local_status in ("active", "trialing", "canceling"),
        "status": local_status,
    }


@router.post("/api/widgets/lng-pro/config")
async def widget_config_update(body: ConfigUpdate,
                               x_user_token: Optional[str] = Header(None)):
    user = _get_user_from_token(x_user_token)
    if not user:
        raise HTTPException(401, "Authentication required")
    row = _get_or_create_widget_row(user["id"])
    incoming = body.config or {}
    safe = dict(DEFAULT_CONFIG)
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
        r = int(incoming.get("radius", 12))
        safe["radius"] = max(0, min(32, r))
    except Exception:
        pass
    safe["transparent"] = bool(incoming.get("transparent", False))
    ovs = incoming.get("overlays") or {}
    if isinstance(ovs, dict):
        safe["overlays"] = {
            k: bool(ovs.get(k, DEFAULT_CONFIG["overlays"][k]))
            for k in DEFAULT_CONFIG["overlays"]
        }
    with get_cursor() as cur:
        cur.execute("""
            UPDATE user_pro_widgets
            SET config_json = %s::jsonb, updated_at = NOW()
            WHERE id = %s
        """, (json.dumps(safe), row["id"]))
    return {"saved": True, "config": safe}


@router.post("/api/widgets/lng-pro/rotate-token")
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


@router.post("/api/widgets/lng-pro/cancel")
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
        logger.error(f"Widget cancel error: {e}", exc_info=True)
        raise HTTPException(500, "Failed to cancel widget subscription")


# ─────────────────────────────────────────────────────────────────────────────
# Webhook hooks — called from src/billing/webhook_handler.py
# ─────────────────────────────────────────────────────────────────────────────

def handle_widget_checkout_completed(session: dict) -> bool:
    """Mark widget active after Stripe Checkout completes. Returns True if handled."""
    if (session.get("metadata") or {}).get("type") != WIDGET_TYPE:
        return False
    user_id_str = (session.get("metadata") or {}).get("user_id")
    if not user_id_str:
        logger.error("LNG widget checkout completed without user_id metadata")
        return True
    user_id = int(user_id_str)
    subscription_id = session.get("subscription")
    customer_id = session.get("customer")
    if not subscription_id:
        logger.error("LNG widget checkout completed without subscription")
        return True
    ensure_stripe_initialized()
    try:
        sub = stripe.Subscription.retrieve(subscription_id)
    except Exception as e:
        logger.error(f"Could not retrieve widget subscription {subscription_id}: {e}")
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
    logger.info(f"LNG Pro Widget activated for user {user_id}")
    return True


def handle_widget_subscription_event(subscription: dict) -> bool:
    """Update widget row on subscription.updated. Returns True if widget sub."""
    sub_id = subscription.get("id")
    if not sub_id:
        return False
    is_widget_meta = (subscription.get("metadata") or {}).get("type") == WIDGET_TYPE
    with get_cursor() as cur:
        cur.execute(
            "SELECT id, widget_code FROM user_pro_widgets WHERE stripe_subscription_id = %s",
            (sub_id,)
        )
        row = cur.fetchone()
    # Only handle rows that belong to THIS widget; let other widget handlers run.
    if row and row.get("widget_code") != WIDGET_CODE:
        return False
    if not row and not is_widget_meta:
        return False
    if not row:
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
    logger.info(f"LNG Pro Widget subscription {sub_id} → status={status}")
    return True


def handle_widget_subscription_deleted(subscription: dict) -> bool:
    sub_id = subscription.get("id")
    if not sub_id:
        return False
    with get_cursor() as cur:
        cur.execute(
            "SELECT id, widget_code FROM user_pro_widgets WHERE stripe_subscription_id = %s",
            (sub_id,)
        )
        row = cur.fetchone()
        if not row:
            return False
        if row.get("widget_code") != WIDGET_CODE:
            return False
        cur.execute("""
            UPDATE user_pro_widgets
            SET status = 'cancelled', updated_at = NOW()
            WHERE id = %s
        """, (row["id"],))
    logger.info(f"LNG Pro Widget subscription {sub_id} cancelled")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Embed runtime
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


def _fetch_lng_extras():
    """Fetch VIX latest + EU gas-storage latest for overlays/intelligence."""
    vix = execute_production_one(
        "SELECT date, vix_close FROM vix_snapshots "
        "WHERE vix_close IS NOT NULL ORDER BY date DESC LIMIT 1"
    )
    storage = execute_production_one(
        "SELECT date, eu_storage_percent, risk_band FROM gas_storage_snapshots "
        "WHERE eu_storage_percent IS NOT NULL ORDER BY date DESC LIMIT 1"
    )
    return {"vix": vix, "storage": storage}


def _geri_color(band: str) -> str:
    if not band:
        return "#f97316"
    return (BAND_COLORS.get(band)
            or BAND_COLORS.get(band.title())
            or BAND_COLORS.get(band.lower())
            or BAND_COLORS.get(band.capitalize())
            or "#f97316")


def _flow_direction(spread):
    """JKM−TTF spread → cargo flow bias."""
    if spread is None:
        return ("Balanced", "#94a3b8")
    if spread > 0.3:
        return ("Asia-Pull", "#f59e0b")
    if spread < -0.3:
        return ("Europe-Pull", "#38bdf8")
    return ("Balanced", "#94a3b8")


def _intelligence_text(mode, trend_label, geri_band, spread, vix_val,
                       storage_pct) -> str:
    band = (geri_band or "moderate").lower()
    trend = (trend_label or "NEUTRAL").lower()
    if mode == "trader":
        if vix_val:
            vix_phrase = (f"VIX at {vix_val:.1f} signals "
                          f"{'elevated' if vix_val > 20 else 'contained'} "
                          f"cross-asset volatility")
        else:
            vix_phrase = "Cross-asset volatility remains contained"
        spr = (f"The JKM–TTF spread at ${spread:+.2f}/MMBtu frames the basin "
               f"arbitrage" if spread is not None
               else "Basin arbitrage sits near parity")
        return (f"Short-term JKM bias reads {trend} on the recent price path. "
                f"{spr}. {vix_phrase} — momentum traders watch cargo flow and "
                f"the Asia–Europe premium for continuation cues.")
    if mode == "energy":
        if storage_pct is not None:
            stor = (f"European storage at {storage_pct:.0f}% of capacity is "
                    f"shaping winter restocking demand")
        else:
            stor = "European storage dynamics are steering restocking demand"
        spr = (f"a JKM–TTF spread of ${spread:+.2f}/MMBtu" if spread is not None
               else "a JKM–TTF spread near parity")
        return (f"LNG fundamentals reflect Asian demand, cargo availability and "
                f"shipping economics, with {spr} directing where flexible "
                f"cargoes land. {stor}.")
    # macro default
    risk_phrase = {
        "low": "benign", "moderate": "balanced",
        "elevated": "elevated", "high": "elevated", "critical": "acute"
    }.get(band, "balanced")
    return (f"Global LNG is trading against a {risk_phrase} energy-risk backdrop "
            f"with a {trend} market trend. Asia–Europe price competition and the "
            f"geopolitical supply premium continue to drive the LNG complex.")


def _signals_panel(trend_label, geri_band, spread) -> dict:
    energy_risk = {
        "low": "Low", "moderate": "Moderate",
        "elevated": "Elevated", "high": "High", "critical": "Critical"
    }.get((geri_band or "moderate").lower(), "Moderate")
    flow_label, flow_color = _flow_direction(spread)
    regime = (trend_label or "NEUTRAL").title()
    return {"regime": regime, "energy_risk": energy_risk,
            "flow": flow_label, "flow_color": flow_color}


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
    if q.get("overlays") is not None and q["overlays"] != "":
        toks = [t.strip() for t in q["overlays"].split(",") if t.strip()]
        cfg["overlays"] = {k: (k in toks) for k in DEFAULT_CONFIG["overlays"]}

    theme = _theme_colors(cfg["theme"], cfg["accent"], bool(cfg.get("transparent")))
    radius = int(cfg.get("radius", 12))

    # ---- data ----
    data = _fetch_widget_data()
    daily = data["daily"]
    daily_hist = data.get("daily_hist") or []
    geri = data["geri_live"]
    ttf = data["ttf"]
    extras = _fetch_lng_extras()
    vix = extras["vix"]
    storage = extras["storage"]

    if not daily:
        return _render_unavailable_html(cfg, theme, radius,
                                        "LNG price data is temporarily unavailable.")

    latest = daily[0]
    last_price = _safe_float(latest.get("jkm_price"))
    if last_price is None:
        return _render_unavailable_html(cfg, theme, radius,
                                        "LNG price data is temporarily unavailable.")

    chg_abs = _safe_float(latest.get("jkm_change_24h")) if latest.get("jkm_change_24h") is not None else None
    chg_pct = _safe_float(latest.get("jkm_change_pct")) if latest.get("jkm_change_pct") is not None else None
    if chg_abs is None and len(daily) >= 2:
        prev = _safe_float(daily[1].get("jkm_price"))
        if prev:
            chg_abs = last_price - prev
            chg_pct = (chg_abs / prev) * 100.0
    chg_abs = chg_abs or 0.0
    chg_pct = chg_pct or 0.0

    dir_color = "#22c55e" if chg_abs > 0 else ("#ef4444" if chg_abs < 0 else theme["muted"])
    dir_arrow = "▲" if chg_abs > 0 else ("▼" if chg_abs < 0 else "■")

    # 7D / 30D daily charts
    hist_30 = daily_hist[-30:] if daily_hist else []
    hist_7 = daily_hist[-7:] if daily_hist else []
    chart_30_svg = _build_mini_chart_svg(hist_30, color=cfg["accent"], height=70,
                                          price_key="jkm_price",
                                          empty_msg="Awaiting daily data")
    chart_7_svg = _build_mini_chart_svg(hist_7, color=cfg["accent"], height=70,
                                         price_key="jkm_price",
                                         empty_msg="Awaiting daily data")

    def _range_meta(rows):
        vals = [float(r["jkm_price"]) for r in rows if r.get("jkm_price") is not None]
        if not vals:
            return ("—", "—", "—")
        lo, hi = min(vals), max(vals)
        first, last = vals[0], vals[-1]
        cp = ((last - first) / first * 100) if first else 0.0
        return (f"${lo:.2f}", f"${hi:.2f}", f"{cp:+.2f}%")

    lo7, hi7, ch7 = _range_meta(hist_7)
    lo30, hi30, ch30 = _range_meta(hist_30)

    # GERI
    geri_band = str((geri or {}).get("band") or "moderate")
    geri_value = _safe_float((geri or {}).get("value"))
    geri_color = _geri_color(geri_band)

    # Spread + trend
    spread = _ttf_spread_usd(last_price, ttf)
    trend_label, trend_color = _lng_trend(daily_hist)

    vix_val = _safe_float((vix or {}).get("vix_close")) if vix else None
    storage_pct = _safe_float((storage or {}).get("eu_storage_percent")) if storage else None

    intelligence = _intelligence_text(cfg["mode"], trend_label, geri_band,
                                       spread, vix_val, storage_pct)
    signals = _signals_panel(trend_label, geri_band, spread)

    # Updated label (daily series)
    updated_iso = None
    d = latest.get("date")
    if d is not None:
        try:
            updated_iso = f"{d.isoformat()} (daily close)"
        except Exception:
            updated_iso = str(d)
    if not updated_iso:
        updated_iso = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    # Overlays
    ov = cfg.get("overlays") or {}
    overlay_pills = []
    if ov.get("spread") and spread is not None:
        sp_color = "#22c55e" if spread > 0 else ("#ef4444" if spread < 0 else theme["muted"])
        overlay_pills.append(
            f'<span class="erq-pill" style="border-color:{theme["border"]};color:{theme["text"]};">'
            f'<b style="color:{sp_color};">JKM–TTF</b> ${spread:+.2f}</span>'
        )
    if ov.get("geri") and geri_value is not None:
        overlay_pills.append(
            f'<span class="erq-pill" style="border-color:{geri_color}55;color:{theme["text"]};">'
            f'<b style="color:{geri_color};">GERI</b> {geri_value:.1f} · {geri_band.title()}</span>'
        )
    if ov.get("vix") and vix_val is not None:
        overlay_pills.append(
            f'<span class="erq-pill" style="border-color:{theme["border"]};color:{theme["text"]};">'
            f'<b style="color:{theme["muted"]};">VIX</b> {vix_val:.1f}</span>'
        )
    if ov.get("storage") and storage_pct is not None:
        overlay_pills.append(
            f'<span class="erq-pill" style="border-color:{theme["border"]};color:{theme["text"]};">'
            f'<b style="color:{cfg["accent"]};">EU STOR</b> {storage_pct:.0f}%</span>'
        )
    overlays_html = ('<div class="erq-overlays">' + "".join(overlay_pills) +
                     '</div>') if overlay_pills else ''

    size = SIZE_PRESETS.get(cfg["size"], SIZE_PRESETS["medium"])

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="60">
<title>Global LNG — Pro Widget</title>
<style>
*,*::before,*::after {{ box-sizing:border-box; }}
html,body {{ margin:0; padding:0; background:{theme['bg']}; color:{theme['text']};
  font-family:'Inter',system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;
  font-size:14px; line-height:1.45; }}
.erq-pro {{
  background:{theme['bg']}; color:{theme['text']};
  border:1px solid {theme['border']}; border-radius:{radius}px;
  overflow:hidden; width:100%; max-width:{size['w']}px; margin:0 auto;
}}
.erq-head {{ padding:14px 16px 6px; display:flex; justify-content:space-between; align-items:flex-start; gap:8px; }}
.erq-title {{ font-size:13px; font-weight:600; color:{theme['text']}; letter-spacing:.2px; }}
.erq-sub   {{ font-size:11px; color:{theme['muted']}; margin-top:2px; }}
.erq-trendtag {{ font-size:10px; font-weight:700; padding:3px 8px; border-radius:999px;
  background:{trend_color}1f; color:{trend_color}; border:1px solid {trend_color}55;
  text-transform:uppercase; letter-spacing:.5px; white-space:nowrap; }}
.erq-livedot {{ display:inline-block; width:7px; height:7px; border-radius:50%;
  background:{cfg['accent']}; margin-right:6px; box-shadow:0 0 0 0 {cfg['accent']}66;
  animation:erqPulse 2s infinite; }}
@keyframes erqPulse {{
  0% {{ box-shadow:0 0 0 0 {cfg['accent']}66; }}
  70% {{ box-shadow:0 0 0 8px {cfg['accent']}00; }}
  100% {{ box-shadow:0 0 0 0 {cfg['accent']}00; }}
}}
.erq-price-row {{ padding:6px 16px 4px; display:flex; align-items:baseline; gap:10px; flex-wrap:wrap; }}
.erq-price {{ font-size:30px; font-weight:700; color:{theme['text']}; letter-spacing:-.5px; }}
.erq-unit {{ font-size:11px; color:{theme['muted']}; font-weight:600; }}
.erq-change {{ font-size:13px; font-weight:600; color:{dir_color}; }}
.erq-updated {{ padding:0 16px 8px; font-size:10px; color:{theme['muted']}; }}
.erq-overlays {{ padding:4px 14px 10px; display:flex; flex-wrap:wrap; gap:6px; }}
.erq-pill {{ font-size:10.5px; padding:4px 8px; border-radius:999px;
  border:1px solid {theme['border']}; background:{theme['panel']};
  color:{theme['text']}; display:inline-flex; align-items:center; gap:4px; }}
.erq-section-title {{ padding:8px 16px 4px; font-size:10.5px; font-weight:600;
  color:{theme['muted']}; text-transform:uppercase; letter-spacing:.6px; }}
.erq-daily-panel {{ padding:0 12px 8px; }}
.erq-tabs {{ display:flex; gap:4px; padding:0 4px 6px; }}
.erq-tab {{ flex:0 0 auto; cursor:pointer; font-size:11px; font-weight:600;
  padding:5px 10px; border-radius:999px; border:1px solid {theme['border']};
  background:transparent; color:{theme['muted']}; }}
.erq-tab.active {{ background:{cfg['accent']}1a; color:{cfg['accent']}; border-color:{cfg['accent']}66; }}
.erq-pane {{ display:none; }}
.erq-pane.active {{ display:block; }}
.erq-range-stats {{ display:flex; justify-content:space-between; gap:6px;
  padding:6px 6px 0; font-size:10.5px; color:{theme['muted']}; }}
.erq-range-stats b {{ color:{theme['text']}; font-weight:600; }}
.erq-intel {{ margin:8px 14px; padding:10px 12px; border-radius:{max(8, radius-2)}px;
  background:{theme['panel']}; border:1px solid {theme['border']};
  font-size:12px; color:{theme['text']}; line-height:1.55; }}
.erq-intel-label {{ display:inline-block; font-size:9.5px; font-weight:700;
  color:{cfg['accent']}; letter-spacing:.7px; text-transform:uppercase; margin-bottom:4px; }}
.erq-signals {{ margin:0 14px 12px; padding:8px 10px; border-radius:{max(8, radius-2)}px;
  background:{theme['panel']}; border:1px solid {theme['border']};
  display:grid; grid-template-columns:repeat(3,1fr); gap:6px; text-align:center; }}
.erq-signal {{ display:flex; flex-direction:column; gap:2px; }}
.erq-signal-label {{ font-size:9.5px; color:{theme['muted']}; text-transform:uppercase; letter-spacing:.5px; }}
.erq-signal-val {{ font-size:12px; font-weight:700; color:{theme['text']}; }}
@media (max-width:380px) {{
  .erq-price {{ font-size:26px; }}
  .erq-signals {{ gap:4px; padding:6px 8px; }}
  .erq-signal-val {{ font-size:11px; }}
}}
</style>
</head>
<body>
<div class="erq-pro">
  <div class="erq-head">
    <div>
      <div class="erq-title">Global LNG · JKM</div>
      <div class="erq-sub"><span class="erq-livedot"></span>Live Market Intelligence</div>
    </div>
    <span class="erq-trendtag">{_html.escape(trend_label)}</span>
  </div>
  <div class="erq-price-row">
    <div class="erq-price">${last_price:,.2f}</div>
    <span class="erq-unit">/MMBtu</span>
    <div class="erq-change">{dir_arrow} {chg_abs:+.2f} ({chg_pct:+.2f}%)</div>
  </div>
  <div class="erq-updated">Updated {_html.escape(updated_iso)}</div>
  {overlays_html}

  <div class="erq-section-title">LNG Price Chart</div>
  <div class="erq-daily-panel">
    <div class="erq-tabs">
      <button type="button" class="erq-tab active" data-pane="erqPane7">7D</button>
      <button type="button" class="erq-tab" data-pane="erqPane30">30D</button>
    </div>
    <div id="erqPane7" class="erq-pane active">
      {chart_7_svg}
      <div class="erq-range-stats">
        <span>Low <b>{lo7}</b></span><span>High <b>{hi7}</b></span><span>7D Chg <b>{ch7}</b></span>
      </div>
    </div>
    <div id="erqPane30" class="erq-pane">
      {chart_30_svg}
      <div class="erq-range-stats">
        <span>Low <b>{lo30}</b></span><span>High <b>{hi30}</b></span><span>30D Chg <b>{ch30}</b></span>
      </div>
    </div>
  </div>

  <div class="erq-intel">
    <div class="erq-intel-label">Market Intelligence · {cfg['mode'].title()} Mode</div>
    {_html.escape(intelligence)}
  </div>

  <div class="erq-signals">
    <div class="erq-signal">
      <div class="erq-signal-label">Regime</div>
      <div class="erq-signal-val">{signals['regime']}</div>
    </div>
    <div class="erq-signal">
      <div class="erq-signal-label">Energy Risk</div>
      <div class="erq-signal-val" style="color:{geri_color};">{signals['energy_risk']}</div>
    </div>
    <div class="erq-signal">
      <div class="erq-signal-label">Cargo Flow</div>
      <div class="erq-signal-val" style="color:{signals['flow_color']};">{signals['flow']}</div>
    </div>
  </div>
</div>
<script>
(function(){{
  var tabs=document.querySelectorAll('.erq-tab');
  tabs.forEach(function(t){{
    t.addEventListener('click',function(){{
      tabs.forEach(function(x){{ x.classList.remove('active'); }});
      document.querySelectorAll('.erq-pane').forEach(function(p){{ p.classList.remove('active'); }});
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
<title>Global LNG Pro Widget</title>
<style>
html,body{{margin:0;padding:0;background:{theme['bg']};color:{theme['text']};
font-family:'Inter',system-ui,sans-serif;}}
.box{{padding:20px;border:1px solid {theme['border']};border-radius:{radius}px;
max-width:420px;margin:20px auto;background:{theme['panel']};text-align:center;}}
</style></head><body><div class="box">
<div style="font-weight:600;margin-bottom:6px;">Global LNG · JKM</div>
<div style="font-size:12px;color:{theme['muted']};">{_html.escape(msg)}</div>
</div></body></html>"""


def _render_inactive_html() -> str:
    return """<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Global LNG Pro Widget — Inactive</title>
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
<div class="h">Global LNG Pro Widget</div>
<div class="p">This widget requires an active subscription. Manage your widget in your
<a href="https://energyriskiq.com/users/account">EnergyRiskIQ account</a>.</div>
</div></body></html>"""


@router.get("/embed/lng-pro-widget", response_class=HTMLResponse)
async def embed_lng_pro_widget(request: Request):
    qp = request.query_params
    token = qp.get("t") or qp.get("token") or ""
    row = _lookup_widget_by_token(token)
    if not row or not (_widget_is_active(row) or _geri_live_bonus(row["user_id"])):
        return HTMLResponse(_render_inactive_html(), headers=EMBED_HEADERS)
    try:
        html = _render_pro_widget_html(row, dict(qp))
    except Exception as e:
        logger.error(f"LNG Pro widget render error: {e}", exc_info=True)
        theme = _theme_colors("dark", "#d4a017", False)
        html = _render_unavailable_html({}, theme, 12,
                                         "Temporary data error — please retry shortly.")
    return HTMLResponse(html, headers=EMBED_HEADERS)


# ─────────────────────────────────────────────────────────────────────────────
# JS loader  — for <script src=".../lng-pro.js"></script>
#                <div data-eriq-widget="lng-pro" data-token="..."></div>
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/widgets/lng-pro.js")
async def widgets_lng_pro_js():
    base = _base_url()
    js = (
        "/* EnergyRiskIQ Global LNG Pro Widget loader */\n"
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
        "    var overlays=el.getAttribute('data-overlays')||'';\n"
        "    var q=['t='+encodeURIComponent(t)];\n"
        "    if(theme) q.push('theme='+encodeURIComponent(theme));\n"
        "    if(size)  q.push('size='+encodeURIComponent(size));\n"
        "    if(mode)  q.push('mode='+encodeURIComponent(mode));\n"
        "    if(accent)q.push('accent='+encodeURIComponent(accent));\n"
        "    if(transparent) q.push('transparent='+encodeURIComponent(transparent));\n"
        "    if(overlays)    q.push('overlays='+encodeURIComponent(overlays));\n"
        "    var sizes={compact:[350,440],medium:[450,580],large:[700,700]};\n"
        "    var dims=sizes[size]||sizes.medium;\n"
        "    var f=document.createElement('iframe');\n"
        "    f.src=BASE+'/embed/lng-pro-widget?'+q.join('&');\n"
        "    f.title='Global LNG Pro Widget';\n"
        "    f.loading='lazy';\n"
        "    f.style.border='0'; f.style.display='block';\n"
        "    f.style.width='100%'; f.style.maxWidth=dims[0]+'px';\n"
        "    f.style.height=dims[1]+'px';\n"
        "    f.setAttribute('allowtransparency','true');\n"
        "    el.appendChild(f);\n"
        "  }\n"
        "  function init(){\n"
        "    var nodes=document.querySelectorAll('[data-eriq-widget=\"lng-pro\"]');\n"
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
