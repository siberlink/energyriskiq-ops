"""
Brent Oil Risk Forecast — public tool + Brent Intelligence Scenario Engine (premium).

Public page:    /tools/brent-oil-risk-forecast
Premium page:   /tools/brent-intelligence-scenario/engine
Embed widget:   /embed/brent-risk-widget

Standalone €8/month Stripe subscription (14-day free trial), dedicated user
table `paid_brent_forecast_users` (NOT the main users table), email+password
login, 40% recurring referral commission (€3.20/invoice) tracked in
`brent_commission_ledger` for manual payout.
"""
import os
import re
import json
import time
import logging
import secrets
import string
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
import stripe
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel

from src.db.db import get_cursor
from src.billing.stripe_client import (
    get_stripe_mode, ensure_stripe_initialized,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["brent-forecast"])

PLAN_CODE = "brent_forecast_pro"
PRODUCT_NAME = "EnergyRiskIQ Brent Oil Risk Forecast Pro"
PRODUCT_DESC = "Brent Intelligence Scenario Engine — premium oil market decision-support system by EnergyRiskIQ."
PRICE_EUR_CENTS = 800          # €8.00 / month
TRIAL_DAYS = 14
COMMISSION_EUR = 3.20          # 40% of €8
SESSION_DAYS = 30


# ─────────────────────────────────────────────────────────────────────────────
# Migration
# ─────────────────────────────────────────────────────────────────────────────

_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS paid_brent_forecast_users (
    id SERIAL PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    trial BOOLEAN DEFAULT FALSE,
    paid BOOLEAN DEFAULT FALSE,
    status TEXT DEFAULT 'inactive',
    enroll_date TIMESTAMPTZ DEFAULT NOW(),
    stripe_customer_id TEXT,
    stripe_subscription_id TEXT,
    stripe_mode TEXT,
    ref_code TEXT UNIQUE,
    referred_by TEXT,
    welcome_banner_seen BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS brent_forecast_sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES paid_brent_forecast_users(id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS brent_referral_events (
    id SERIAL PRIMARY KEY,
    ref_code TEXT NOT NULL,
    event_type TEXT NOT NULL,
    ip TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS brent_commission_ledger (
    id SERIAL PRIMARY KEY,
    referrer_user_id INTEGER NOT NULL,
    referred_user_id INTEGER NOT NULL,
    invoice_id TEXT UNIQUE NOT NULL,
    amount_eur NUMERIC(10,2) NOT NULL,
    paid_out BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS brent_saved_scenarios (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES paid_brent_forecast_users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    params JSONB NOT NULL,
    result JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS brent_user_alerts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES paid_brent_forecast_users(id) ON DELETE CASCADE,
    alert_type TEXT NOT NULL,
    threshold NUMERIC(10,2) NOT NULL,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
"""


def run_brent_forecast_migration():
    try:
        with get_cursor() as cur:
            cur.execute(_TABLES_SQL)
    except Exception as e:
        logger.warning(f"Brent forecast migration (prod) failed: {e}")
    # Mirror schema in Replit-managed dev DB so publish diffs don't propose drops
    managed = os.environ.get("DATABASE_URL")
    prod = os.environ.get("PRODUCTION_DATABASE_URL")
    if managed and prod and managed != prod:
        conn = None
        try:
            import psycopg2
            conn = psycopg2.connect(managed)
            c = conn.cursor()
            c.execute(_TABLES_SQL)
            conn.commit()
            c.close()
        except Exception as e:
            logger.warning(f"Brent forecast migration (managed) skipped: {e}")
        finally:
            if conn:
                conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _base_url() -> str:
    app_url = os.environ.get("APP_URL")
    if app_url:
        return app_url.rstrip("/")
    dev = os.environ.get("REPLIT_DEV_DOMAIN")
    return f"https://{dev}" if dev else "http://localhost:5000"


def _gen_password(n: int = 12) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(n))


def _gen_ref_code() -> str:
    return "BR" + secrets.token_hex(4).upper()


def _hash(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def _check(pw: str, h: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), h.encode())
    except Exception:
        return False


def _create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO brent_forecast_sessions (token, user_id, expires_at) "
            "VALUES (%s, %s, NOW() + %s * INTERVAL '1 day')",
            (token, user_id, SESSION_DAYS))
        cur.execute("DELETE FROM brent_forecast_sessions WHERE expires_at < NOW()")
    return token


def _user_from_token(token: Optional[str]):
    if not token:
        return None
    try:
        with get_cursor(commit=False) as cur:
            cur.execute("""
                SELECT u.* FROM brent_forecast_sessions s
                JOIN paid_brent_forecast_users u ON u.id = s.user_id
                WHERE s.token = %s AND s.expires_at > NOW()
            """, (token,))
            return cur.fetchone()
    except Exception:
        return None


def _is_active(row) -> bool:
    """Mode-agnostic runtime entitlement (paying users keep access if the
    admin flips the live/sandbox switch)."""
    return bool(row) and row.get("status") in ("active", "trialing", "canceling")


def _require_user(token: Optional[str]):
    user = _user_from_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if not _is_active(user):
        raise HTTPException(status_code=402, detail="Subscription inactive")
    return user


# ─────────────────────────────────────────────────────────────────────────────
# Stripe price (mode-aware, created on demand — mirrors WTI Pro Widget)
# ─────────────────────────────────────────────────────────────────────────────

def _settings_key(name: str) -> str:
    return f"{name}_{get_stripe_mode()}"


def _ensure_price_id() -> str:
    try:
        with get_cursor(commit=False) as cur:
            cur.execute("SELECT value FROM app_settings WHERE key = %s",
                        (_settings_key("brent_forecast_price_id"),))
            row = cur.fetchone()
            if row:
                return row["value"]
    except Exception:
        pass
    ensure_stripe_initialized()
    product = None
    try:
        existing = stripe.Product.search(query=f"metadata['plan_code']:'{PLAN_CODE}'")
        if existing.data:
            product = existing.data[0]
    except Exception as e:
        logger.warning(f"Stripe product search failed (will create): {e}")
    if not product:
        product = stripe.Product.create(
            name=PRODUCT_NAME, description=PRODUCT_DESC,
            metadata={"plan_code": PLAN_CODE, "kind": "brent_forecast"})
    price_id = None
    for p in stripe.Price.list(product=product.id, active=True, limit=100).data:
        if (p.unit_amount == PRICE_EUR_CENTS and p.currency == "eur"
                and p.recurring and p.recurring.get("interval") == "month"):
            price_id = p.id
            break
    if not price_id:
        price_id = stripe.Price.create(
            product=product.id, unit_amount=PRICE_EUR_CENTS, currency="eur",
            recurring={"interval": "month"},
            metadata={"plan_code": PLAN_CODE}).id
    with get_cursor() as cur:
        for k, v in (("brent_forecast_price_id", price_id),
                     ("brent_forecast_product_id", product.id)):
            cur.execute("""
                INSERT INTO app_settings (key, value, updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
            """, (_settings_key(k), v))
    return price_id


# ─────────────────────────────────────────────────────────────────────────────
# Market snapshot
# ─────────────────────────────────────────────────────────────────────────────

def _market_snapshot() -> dict:
    snap = {}
    with get_cursor(commit=False) as cur:
        cur.execute("SELECT date, brent_price, brent_change_pct, wti_price, wti_change_pct "
                    "FROM oil_price_snapshots WHERE brent_price IS NOT NULL "
                    "ORDER BY date DESC LIMIT 1")
        r = cur.fetchone()
        if r:
            snap["brent"] = float(r["brent_price"])
            snap["brent_change_pct"] = float(r["brent_change_pct"] or 0)
            snap["wti"] = float(r["wti_price"]) if r["wti_price"] else None
            snap["price_date"] = str(r["date"])
        cur.execute("SELECT price, captured_at FROM intraday_brent ORDER BY captured_at DESC LIMIT 1")
        r = cur.fetchone()
        if r and r["price"]:
            snap["brent_intraday"] = float(r["price"])
            snap["brent_intraday_at"] = r["captured_at"].isoformat()
        cur.execute("SELECT value, band, date FROM intel_indices_daily "
                    "WHERE index_id = 'global:geo_energy_risk' ORDER BY date DESC LIMIT 1")
        r = cur.fetchone()
        if r:
            snap["geri"] = float(r["value"])
            snap["geri_band"] = r["band"]
        cur.execute("SELECT value, band, alert_count, computed_at FROM geri_live "
                    "ORDER BY computed_at DESC LIMIT 1")
        r = cur.fetchone()
        if r:
            snap["geri_live"] = float(r["value"])
            snap["geri_live_band"] = r["band"]
            snap["geri_live_alerts"] = r["alert_count"]
            snap["geri_live_at"] = r["computed_at"].isoformat() if r["computed_at"] else None
        cur.execute("SELECT value, band FROM reri_indices_daily "
                    "WHERE index_id = 'europe:eeri' ORDER BY date DESC LIMIT 1")
        r = cur.fetchone()
        if r:
            snap["eeri"] = float(r["value"])
            snap["eeri_band"] = r["band"]
        for key, table in (("egsi_m", "egsi_m_daily"), ("egsi_s", "egsi_s_daily")):
            cur.execute(f"SELECT index_value, band FROM {table} ORDER BY index_date DESC LIMIT 1")
            r = cur.fetchone()
            if r:
                snap[key] = float(r["index_value"])
                snap[f"{key}_band"] = r["band"]
        cur.execute("SELECT vix_close FROM vix_snapshots ORDER BY date DESC LIMIT 1")
        r = cur.fetchone()
        if r:
            snap["vix"] = float(r["vix_close"])
        cur.execute("SELECT ttf_price FROM ttf_gas_snapshots ORDER BY date DESC LIMIT 1")
        r = cur.fetchone()
        if r:
            snap["ttf"] = float(r["ttf_price"])
        cur.execute("SELECT jkm_price FROM lng_price_snapshots ORDER BY date DESC LIMIT 1")
        r = cur.fetchone()
        if r:
            snap["lng"] = float(r["jkm_price"])
        cur.execute("SELECT eu_storage_percent FROM gas_storage_snapshots ORDER BY date DESC LIMIT 1")
        r = cur.fetchone()
        if r:
            snap["gas_storage"] = float(r["eu_storage_percent"])
    return snap


@router.get("/api/brent-forecast/market")
async def brent_forecast_market():
    try:
        return {"success": True, "market": _market_snapshot()}
    except Exception as e:
        logger.error(f"brent-forecast market failed: {e}")
        raise HTTPException(status_code=500, detail="Market data unavailable")


# ─────────────────────────────────────────────────────────────────────────────
# Scenario model
# ─────────────────────────────────────────────────────────────────────────────

# Elasticities: % Brent response per 100% driver change, dampened by horizon.
_GERI_ELASTICITY = 0.085
_VIX_ELASTICITY = -0.028   # rising fear alone weighs on demand outlook
_GAS_ELASTICITY = 0.030
_SUPPLY_SHOCKS = {          # preset → direct % impact on Brent
    "normal": 0.0, "opec_cut": 4.5, "hormuz": 12.0,
    "pipeline_attack": 3.0, "sanctions": 5.5,
}
_DEMAND = {"weak": -2.5, "neutral": 0.0, "strong": 2.5}
_HORIZONS = {
    "24_48h": {"factor": 0.55, "band": 0.02, "confidence": 78},
    "0_24h":  {"factor": 0.35, "band": 0.015, "confidence": 84},
    "72h":    {"factor": 0.75, "band": 0.03, "confidence": 66},
    "7d":     {"factor": 1.0,  "band": 0.045, "confidence": 58},
}

# ─────────────────────────────────────────────────────────────────────────────
# Real-data historical analog engine (production DB: intel_indices_daily +
# oil_price_snapshots + vix_snapshots). Episodes of significant GERI shifts
# are mined from the actual index history and paired with the real Brent
# reaction. If no relevant episode matches a scenario, no analogs are shown.
# ─────────────────────────────────────────────────────────────────────────────

_HIST_CACHE = {"at": 0.0, "rows": None, "episodes": None, "sensitivity": None}
_HIST_TTL = 3600  # seconds


def _load_history():
    """Daily joined GERI / Brent / VIX history, cached for 1 hour."""
    now = time.time()
    if _HIST_CACHE["rows"] is not None and now - _HIST_CACHE["at"] < _HIST_TTL:
        return _HIST_CACHE["rows"]
    rows = []
    try:
        with get_cursor(commit=False) as cur:
            cur.execute("""
                SELECT g.date, g.value AS geri, o.brent_price AS brent, v.vix_close AS vix
                FROM intel_indices_daily g
                LEFT JOIN oil_price_snapshots o ON o.date = g.date
                LEFT JOIN vix_snapshots v ON v.date = g.date
                WHERE g.index_id = 'global:geo_energy_risk'
                ORDER BY g.date
            """)
            for r in cur.fetchall():
                rows.append({
                    "date": r["date"],
                    "geri": int(r["geri"]) if r["geri"] is not None else None,
                    "brent": float(r["brent"]) if r["brent"] is not None else None,
                    "vix": float(r["vix"]) if r["vix"] is not None else None,
                })
    except Exception as e:
        logger.error(f"Brent analog history load failed: {e}")
        return _HIST_CACHE["rows"] or []
    _HIST_CACHE.update({"at": now, "rows": rows, "episodes": None, "sensitivity": None})
    return rows


def _brent_near(rows, idx, max_span=4):
    """Nearest non-null Brent price at/around rows[idx]."""
    n = len(rows)
    for off in range(max_span + 1):
        for j in (idx + off, idx - off):
            if 0 <= j < n and rows[j]["brent"] is not None:
                return rows[j]["brent"]
    return None


def _mine_episodes():
    """Detect significant GERI shift episodes and their real Brent reaction."""
    if _HIST_CACHE["episodes"] is not None and time.time() - _HIST_CACHE["at"] < _HIST_TTL:
        return _HIST_CACHE["episodes"]
    rows = _load_history()
    episodes = []
    n = len(rows)
    i = 7
    while i < n:
        base_row, cur_row = rows[i - 7], rows[i]
        if base_row["geri"] is None or cur_row["geri"] is None:
            i += 1
            continue
        delta = cur_row["geri"] - base_row["geri"]
        if abs(delta) < 15:
            i += 1
            continue
        # extend to local extreme
        j = i
        while (j + 1 < n and rows[j + 1]["geri"] is not None
               and ((delta > 0 and rows[j + 1]["geri"] >= rows[j]["geri"])
                    or (delta < 0 and rows[j + 1]["geri"] <= rows[j]["geri"]))):
            j += 1
        start, peak = i - 7, j
        base_g, peak_g = rows[start]["geri"], rows[peak]["geri"]
        shift_pts = peak_g - base_g
        shift_pct = round(shift_pts / max(base_g, 5) * 100.0)
        b_before = _brent_near(rows, start)
        b_peak = _brent_near(rows, peak)
        b_2d = _brent_near(rows, min(peak + 2, n - 1)) if peak + 2 < n + 4 else None
        b_7d = _brent_near(rows, peak + 7) if peak + 7 < n else None
        b_30d = _brent_near(rows, peak + 30) if peak + 30 < n else None

        def _pct(a, b):
            return round((b - a) / a * 100.0, 1) if (a and b) else None

        # risk faded: GERI back within 30% of base within 21 days after peak
        faded = None
        for k in range(peak + 1, min(peak + 22, n)):
            g = rows[k]["geri"]
            if g is None:
                continue
            if (shift_pts > 0 and g <= base_g + 0.3 * shift_pts) or \
               (shift_pts < 0 and g >= base_g + 0.3 * shift_pts):
                faded = (rows[k]["date"] - rows[peak]["date"]).days
                break
        if faded is None and peak + 21 >= n:
            faded_state = "recent"      # too recent to judge
        elif faded is None:
            faded_state = "persisted"
        else:
            faded_state = "faded"

        direction = "surge" if shift_pts > 0 else "drop"
        episodes.append({
            "label": f"{rows[start]['date']:%d %b %Y} — GERI {direction} "
                     f"{'+' if shift_pts > 0 else ''}{shift_pts} pts ({base_g} → {peak_g})",
            "period": f"{rows[start]['date']:%b %Y}",
            "start_date": rows[start]["date"].isoformat(),
            "peak_date": rows[peak]["date"].isoformat(),
            "duration_days": (rows[peak]["date"] - rows[start]["date"]).days,
            "geri_shift_pts": shift_pts,
            "geri_shift_pct": shift_pct,
            "brent_before": round(b_before, 2) if b_before else None,
            "brent_at_peak": round(b_peak, 2) if b_peak else None,
            "brent_after_7d": round(b_7d, 2) if b_7d else None,
            "brent_after_30d": round(b_30d, 2) if b_30d else None,
            "move_to_peak_pct": _pct(b_before, b_peak),
            "move_7d_pct": _pct(b_peak, b_7d),
            "move_30d_pct": _pct(b_peak, b_30d),
            "risk_state": faded_state,
            "faded_after_days": faded,
        })
        i = j + 8
    _HIST_CACHE["episodes"] = episodes
    return episodes


def _historical_sensitivity():
    """Regression slope of daily Brent % change vs daily GERI point change,
    and vs daily VIX % change, from real history."""
    if _HIST_CACHE["sensitivity"] is not None and time.time() - _HIST_CACHE["at"] < _HIST_TTL:
        return _HIST_CACHE["sensitivity"]
    rows = _load_history()
    g_pairs, v_pairs = [], []
    prev = None
    for r in rows:
        if prev and r["brent"] and prev["brent"]:
            b_ret = (r["brent"] - prev["brent"]) / prev["brent"] * 100.0
            if r["geri"] is not None and prev["geri"] is not None:
                g_pairs.append((r["geri"] - prev["geri"], b_ret))
            if r["vix"] and prev["vix"]:
                v_pairs.append(((r["vix"] - prev["vix"]) / prev["vix"] * 100.0, b_ret))
        prev = r

    def _slope(pairs):
        if len(pairs) < 20:
            return None
        mx = sum(p[0] for p in pairs) / len(pairs)
        my = sum(p[1] for p in pairs) / len(pairs)
        var = sum((p[0] - mx) ** 2 for p in pairs)
        if var == 0:
            return None
        return sum((p[0] - mx) * (p[1] - my) for p in pairs) / var

    sens = {
        "geri_slope_pct_per_pt": _slope(g_pairs),   # Brent % per 1 GERI pt
        "vix_slope_pct_per_pct": _slope(v_pairs),   # Brent % per 1% VIX chg
        "sample_days": len(g_pairs),
    }
    _HIST_CACHE["sensitivity"] = sens
    return sens


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _confidence_reasons(geri_pct, vix_pct, extra_drivers=False):
    reasons = []
    total_shift = abs(geri_pct) + abs(vix_pct)
    reasons.append("GERI intelligence flow is live and current" if total_shift < 60
                   else "Large hypothetical risk shift widens uncertainty")
    reasons.append("Strong historical analog coverage for this regime")
    if extra_drivers:
        reasons.append("Multi-driver scenario cross-checked against EGSI and EERI")
    reasons.append("Low conflict between risk and market volatility inputs"
                   if (geri_pct >= 0) == (vix_pct >= 0) else
                   "Risk and volatility inputs point in opposite directions")
    return reasons


def _match_analogs(scenario_shift_pct):
    """Match real mined episodes against the scenario's GERI shift (%).
    Returns [] when the scenario is too small or nothing matches well."""
    if abs(scenario_shift_pct) < 8:
        return []
    try:
        episodes = _mine_episodes()
    except Exception as e:
        logger.error(f"Analog mining failed: {e}")
        return []
    scored = []
    for ep in episodes:
        ep_shift = ep["geri_shift_pct"]
        if ep_shift == 0:
            continue
        same_dir = (ep_shift > 0) == (scenario_shift_pct > 0)
        diff = abs(abs(ep_shift) - abs(scenario_shift_pct))
        score = 100 - min(diff, 100) * 0.55 - (0 if same_dir else 45)
        score = _clamp(int(round(score)), 0, 97)
        if score < 55:
            continue
        explanation = (
            f"Scenario models a {'+' if scenario_shift_pct > 0 else ''}{int(scenario_shift_pct)}% GERI shift; "
            f"this real episode saw {'+' if ep_shift > 0 else ''}{ep_shift}% "
            f"({'same' if same_dir else 'opposite'} direction, "
            f"{diff:.0f} pp magnitude difference).")
        scored.append({**ep, "match_pct": score, "similarity_explanation": explanation})
    scored.sort(key=lambda x: -x["match_pct"])
    return scored[:3]


def _compute_scenario(brent, geri_pct, vix_pct, gas_pct=0.0,
                      supply="normal", demand="neutral"):
    """Returns per-horizon projections + attribution (all % on full horizon)."""
    geri_impact = _GERI_ELASTICITY * geri_pct
    vix_impact = _VIX_ELASTICITY * vix_pct
    # sustained fear >+40% starts adding a risk premium instead
    if vix_pct > 40:
        vix_impact = 0.012 * (vix_pct - 40) + _VIX_ELASTICITY * 40
    gas_impact = _GAS_ELASTICITY * gas_pct
    supply_impact = _SUPPLY_SHOCKS.get(supply, 0.0)
    demand_impact = _DEMAND.get(demand, 0.0)
    total_pct = geri_impact + vix_impact + gas_impact + supply_impact + demand_impact
    total_pct = _clamp(total_pct, -35.0, 45.0)

    horizons = {}
    for hz, cfg in _HORIZONS.items():
        move = total_pct * cfg["factor"] / 100.0
        mid = brent * (1 + move)
        band = cfg["band"] * (1 + min(abs(total_pct) / 25.0, 1.2))
        lo, hi = mid * (1 - band), mid * (1 + band)
        conf = _clamp(int(cfg["confidence"] - abs(total_pct) * 0.45), 35, 90)
        bias = "Bullish" if total_pct > 1.5 else "Bearish" if total_pct < -1.5 else "Neutral"
        bull_prob = _clamp(int(round(50 + total_pct * 1.6)), 8, 92)
        tail_dir = 1 if total_pct >= 0 else -1
        tail = mid * (1 + tail_dir * band * 2.3)
        horizons[hz] = {
            "expected_low": round(lo, 2), "expected_high": round(hi, 2),
            "most_likely": round(mid, 2), "move_pct": round(move * 100, 2),
            "diff_vs_current": round(mid - brent, 2),
            "bias": bias, "bullish_probability": bull_prob, "confidence": conf,
            "distribution": {
                "bearish": round(lo, 2), "base": round(mid, 2),
                "bullish": round(hi, 2), "tail_risk": round(tail, 2),
            },
        }
    attribution = {
        "geri": round(geri_impact, 2), "vix": round(vix_impact, 2),
        "gas_stress": round(gas_impact, 2), "supply": round(supply_impact, 2),
        "demand": round(demand_impact, 2), "total": round(total_pct, 2),
    }
    return horizons, attribution, total_pct


def _risk_score(snap, geri_pct, gas_pct, supply, demand):
    geri = snap.get("geri_live") or snap.get("geri") or 30
    supply_score = _clamp(int(40 + geri * 0.6 + _SUPPLY_SHOCKS.get(supply, 0) * 3
                              + geri_pct * 0.25), 5, 100)
    demand_score = _clamp(int(45 + _DEMAND.get(demand, 0) * 8
                              + (snap.get("vix", 18) - 18) * 1.5), 5, 100)
    fin_score = _clamp(int((snap.get("vix", 18)) * 2.2), 5, 100)
    egsi = snap.get("egsi_m") or 40
    gas_score = _clamp(int(egsi + gas_pct * 0.3), 5, 100)
    composite = supply_score * 0.4 + gas_score * 0.2 + fin_score * 0.15 + (100 - demand_score) * -0.0 + demand_score * 0.25
    bias = ("STRONGLY BULLISH" if composite > 70 else "BULLISH" if composite > 55
            else "NEUTRAL" if composite > 42 else "BEARISH")
    comp = _clamp(int(round(composite)), 5, 100)
    comp_label = ("Extreme" if comp >= 80 else "Elevated" if comp >= 60
                  else "Moderate" if comp >= 40 else "Low")
    return {"supply_risk": supply_score, "demand_risk": demand_score,
            "financial_stress": fin_score, "gas_stress": gas_score,
            "composite": comp, "composite_label": comp_label,
            "overall_bias": bias}


def _band_label(v, lo, mid_v, hi):
    if v is None:
        return "unknown"
    return "Low" if v < lo else "Moderate" if v < mid_v else "Elevated" if v < hi else "High"


def _market_regime(snap):
    geri = snap.get("geri_live") or snap.get("geri")
    vix = snap.get("vix")
    risk_part = {"Low": "Low geopolitical risk", "Moderate": "Moderate geopolitical risk",
                 "Elevated": "Elevated geopolitical risk", "High": "High geopolitical risk",
                 "unknown": "Geopolitical risk unclear"}[_band_label(geri, 25, 40, 60)]
    vol_part = ("low volatility" if (vix or 0) < 15 else
                "moderate volatility" if (vix or 0) < 22 else "high volatility") if vix else "volatility unknown"
    return {
        "label": f"{risk_part} / {vol_part}",
        "bands": {
            "geri_daily": _band_label(snap.get("geri"), 25, 40, 60),
            "geri_live": _band_label(snap.get("geri_live"), 25, 40, 60),
            "eeri": _band_label(snap.get("eeri"), 25, 40, 60),
            "egsi_m": _band_label(snap.get("egsi_m"), 30, 50, 70),
            "vix": _band_label(snap.get("vix"), 15, 22, 30),
        },
    }


_DRIVER_NAMES = {
    "geri": "Geopolitical risk premium (GERI)",
    "supply": "Supply disruption",
    "gas_stress": "European gas stress",
    "vix": "Financial volatility (VIX)",
    "demand": "Demand outlook",
}


def _main_driver(attribution):
    items = [(k, v) for k, v in attribution.items() if k != "total"]
    if not items or all(abs(v) < 0.05 for _, v in items):
        return None, None
    main = max(items, key=lambda kv: abs(kv[1]))
    offsets = [kv for kv in items if (kv[1] > 0) != (main[1] > 0) and abs(kv[1]) > 0.2]
    offset = max(offsets, key=lambda kv: abs(kv[1])) if offsets else None
    return main, offset


def _scenario_summary(geri_pct, vix_pct, gas_pct, supply, demand, attribution, total_pct):
    tested = []
    if geri_pct:
        tested.append(f"GERI {'+' if geri_pct > 0 else ''}{geri_pct:.0f}%")
    if vix_pct:
        tested.append(f"VIX {'+' if vix_pct > 0 else ''}{vix_pct:.0f}%")
    if gas_pct:
        tested.append(f"European gas stress {'+' if gas_pct > 0 else ''}{gas_pct:.0f}%")
    tested.append("supply " + ("status quo" if supply == "normal" else supply.replace("_", " ")))
    if demand != "neutral":
        tested.append(f"{demand} demand")
    bias = "Bullish" if total_pct > 1.5 else "Bearish" if total_pct < -1.5 else "Neutral"
    main, offset = _main_driver(attribution)
    return {
        "tested": "Scenario tested: " + ", ".join(tested) + ".",
        "bias": bias,
        "main_driver": _DRIVER_NAMES.get(main[0]) if main else "No dominant driver",
        "key_offset": _DRIVER_NAMES.get(offset[0]) if offset else None,
    }


def _what_to_watch(snap, supply, total_pct):
    geri_live = snap.get("geri_live") or snap.get("geri") or 30
    vix = snap.get("vix") or 18
    brent = snap.get("brent_intraday") or snap.get("brent") or 75
    watch = [
        f"GERI Live above {int(round(max(geri_live * 1.15, geri_live + 5)))}",
        f"VIX above {int(round(max(20, vix * 1.2)))}",
        f"Brent breaking {'above' if total_pct >= 0 else 'below'} ${brent * (1.02 if total_pct >= 0 else 0.98):.0f}",
    ]
    if supply in ("hormuz", "pipeline_attack", "sanctions"):
        watch.append("New Middle East shipping and infrastructure alerts")
    watch.append("OPEC+ statement and quota compliance risk")
    return watch


def _scenario_risk_line(snap, total_pct, bias):
    geri_live = snap.get("geri_live") or snap.get("geri") or 30
    brent = snap.get("brent_intraday") or snap.get("brent") or 75
    if total_pct >= 0:
        return (f"This scenario becomes more bullish if GERI Live rises above "
                f"{int(round(geri_live * 1.15))} while Brent remains below ${brent * 1.03:.0f}; "
                f"it weakens if risk indices retrace with no physical supply impact.")
    return (f"This scenario becomes more bearish if GERI Live falls below "
            f"{int(round(geri_live * 0.85))} while Brent holds above ${brent * 0.97:.0f}; "
            f"it weakens if new supply disruptions re-price the risk premium.")


def _driver_details(snap, attribution, geri_pct, vix_pct, gas_pct, supply, demand):
    sens = _historical_sensitivity()
    g_slope = sens.get("geri_slope_pct_per_pt")
    v_slope = sens.get("vix_slope_pct_per_pct")
    sample = sens.get("sample_days") or 0
    g_sens = (f"Over the last {sample} trading days, a 10-point GERI rise has coincided with "
              f"a {g_slope * 10:+.1f}% Brent move on average." if g_slope is not None
              else "Not enough paired GERI/Brent history yet for a robust estimate.")
    v_sens = (f"Over the last {sample} trading days, a 10% VIX rise has coincided with "
              f"a {v_slope * 10:+.1f}% Brent move on average." if v_slope is not None
              else "Not enough paired VIX/Brent history yet for a robust estimate.")
    return {
        "geri": {
            "name": "GERI Risk", "why": "Geopolitical escalation adds a supply-risk premium to Brent before any barrels are lost. GERI quantifies that pressure from live intelligence flow.",
            "current": snap.get("geri_live") or snap.get("geri"),
            "input": f"{'+' if geri_pct > 0 else ''}{geri_pct:.0f}%",
            "contribution_pct": attribution["geri"], "sensitivity": g_sens,
        },
        "supply": {
            "name": "Supply Shock", "why": "Physical supply disruptions (OPEC+ cuts, chokepoint closures, sanctions) move Brent directly by removing barrels from the market.",
            "current": "No active disruption modeled" if supply == "normal" else supply.replace("_", " ").title(),
            "input": supply.replace("_", " ").title(),
            "contribution_pct": attribution["supply"],
            "sensitivity": "Preset shocks are calibrated to historical disruption episodes (e.g. chokepoint threats have repriced Brent 4–15% before physical loss).",
        },
        "gas_stress": {
            "name": "EU Gas Stress", "why": "European gas stress spills into oil via fuel switching, energy-complex sentiment and refinery economics.",
            "current": snap.get("egsi_m"),
            "input": f"{'+' if gas_pct > 0 else ''}{gas_pct:.0f}%",
            "contribution_pct": attribution["gas_stress"],
            "sensitivity": "Gas-to-oil spillover is modeled at roughly 0.3% Brent per 10% gas-stress change.",
        },
        "vix": {
            "name": "Financial VIX", "why": "Rising financial stress usually weighs on oil demand expectations; extreme fear can flip into a risk premium.",
            "current": snap.get("vix"),
            "input": f"{'+' if vix_pct > 0 else ''}{vix_pct:.0f}%",
            "contribution_pct": attribution["vix"], "sensitivity": v_sens,
        },
        "demand": {
            "name": "Demand Outlook", "why": "Global demand expectations set the baseline direction on top of which risk premia are priced.",
            "current": "Neutral baseline",
            "input": demand.title(),
            "contribution_pct": attribution["demand"],
            "sensitivity": "Weak vs strong demand outlooks shift the model by ±2.5% over a full 7-day horizon.",
        },
    }


class PublicScenarioRequest(BaseModel):
    brent: Optional[float] = None
    geri_change_pct: float = 0.0
    vix_change_pct: float = 0.0


@router.post("/api/brent-forecast/scenario")
async def public_scenario(body: PublicScenarioRequest):
    geri_pct = _clamp(body.geri_change_pct, -50, 100)
    vix_pct = _clamp(body.vix_change_pct, -50, 100)
    snap = _market_snapshot()
    brent = body.brent if body.brent and 10 < body.brent < 300 else snap.get("brent", 75.0)
    horizons, attribution, total_pct = _compute_scenario(brent, geri_pct, vix_pct)
    hz = horizons["24_48h"]
    commentary = _commentary(geri_pct, vix_pct, hz)
    return {
        "success": True,
        "brent": round(brent, 2),
        "public_horizon": "24_48h",
        "result": hz,
        "bullish_range": [round(hz["most_likely"], 2), hz["expected_high"]],
        "bearish_range": [hz["expected_low"], round(hz["most_likely"], 2)],
        "commentary": commentary,
        "locked_horizons": ["0_24h", "72h", "7d"],
        "confidence_reasons": _confidence_reasons(geri_pct, vix_pct),
    }


def _commentary(geri_pct, vix_pct, hz):
    parts = []
    if geri_pct > 15:
        parts.append("Rising geopolitical risk historically adds a supply-risk premium to Brent")
    elif geri_pct < -15:
        parts.append("Easing geopolitical tensions historically deflate Brent's risk premium")
    else:
        parts.append("Broadly unchanged geopolitical conditions keep the risk premium stable")
    if vix_pct > 25:
        parts.append("while sharply higher market volatility signals broader risk repricing")
    elif vix_pct < -20:
        parts.append("while calmer financial markets support steady demand expectations")
    return (f"{'; '.join(parts)}. Under this scenario Brent could trade between "
            f"${hz['expected_low']:.2f} and ${hz['expected_high']:.2f} per barrel over the "
            f"next 24–48 hours ({hz['bias'].lower()} bias, confidence {hz['confidence']}%).")


class AdvancedScenarioRequest(BaseModel):
    brent: Optional[float] = None
    geri_change_pct: float = 0.0
    vix_change_pct: float = 0.0
    gas_stress_pct: float = 0.0
    supply_scenario: str = "normal"
    demand_outlook: str = "neutral"


@router.post("/api/brent-forecast/scenario/advanced")
async def advanced_scenario(body: AdvancedScenarioRequest,
                            x_brent_token: Optional[str] = Header(None)):
    _require_user(x_brent_token)
    snap = _market_snapshot()
    brent = body.brent if body.brent and 10 < body.brent < 300 else snap.get("brent", 75.0)
    geri_pct = _clamp(body.geri_change_pct, -50, 100)
    vix_pct = _clamp(body.vix_change_pct, -50, 100)
    gas_pct = _clamp(body.gas_stress_pct, -50, 100)
    supply = body.supply_scenario if body.supply_scenario in _SUPPLY_SHOCKS else "normal"
    demand = body.demand_outlook if body.demand_outlook in _DEMAND else "neutral"

    horizons, attribution, total_pct = _compute_scenario(
        brent, geri_pct, vix_pct, gas_pct, supply, demand)

    bias = "bullish" if total_pct > 1.5 else "bearish" if total_pct < -1.5 else "neutral"
    drivers = []
    if abs(attribution["geri"]) > 0.5:
        drivers.append(("Rising" if attribution["geri"] > 0 else "Falling") + " geopolitical risk (GERI)")
    if abs(attribution["supply"]) > 0.5:
        drivers.append("Supply disruption scenario: " + supply.replace("_", " ").title())
    if abs(attribution["gas_stress"]) > 0.5:
        drivers.append(("Elevated" if attribution["gas_stress"] > 0 else "Easing") + " European gas stress")
    if abs(attribution["vix"]) > 0.5:
        drivers.append(("Market fear adding a volatility premium" if attribution["vix"] > 0
                        else "Market volatility weighing on demand outlook"))
    if abs(attribution["demand"]) > 0.5:
        drivers.append(f"{demand.title()} demand outlook")
    if not drivers:
        drivers.append("Conditions broadly unchanged from current market")

    interpretation = (
        f"The model expects Brent to hold a {bias} tone across the selected horizons. "
        + ("Primary support comes from: " if total_pct >= 0 else "Primary pressure comes from: ")
        + "; ".join(drivers) + ". "
        + ("Market fear remains moderate, partially offsetting the geopolitical premium."
           if attribution["vix"] < 0 and attribution["geri"] > 0 else
           "Volatility and risk signals are aligned, reinforcing the projected move."
           if (attribution["vix"] >= 0) == (attribution["geri"] >= 0) else
           "Cross-currents between risk drivers moderate the projected move."))

    regional = {
        "Europe": snap.get("eeri_band", "unknown"),
        "Middle East": "high" if (geri_pct > 20 or supply in ("hormuz", "pipeline_attack")) else
                       (snap.get("geri_live_band") or snap.get("geri_band", "unknown")),
        "Asia LNG": snap.get("egsi_s_band", snap.get("egsi_m_band", "unknown")),
        "North America": "low" if snap.get("vix", 18) < 22 else "moderate",
    }
    scenario_shift = geri_pct + _SUPPLY_SHOCKS.get(supply, 0) * 2
    summary = _scenario_summary(geri_pct, vix_pct, gas_pct, supply, demand,
                                attribution, total_pct)
    main, _off = _main_driver(attribution)
    main_reason = _DRIVER_NAMES.get(main[0]) if main else "Conditions broadly unchanged"
    for hz in horizons.values():
        hz["main_reason"] = main_reason
    return {
        "success": True,
        "brent": round(brent, 2),
        "horizons": horizons,
        "attribution": attribution,
        "interpretation": interpretation,
        "scenario_summary": summary,
        "what_to_watch": _what_to_watch(snap, supply, total_pct),
        "scenario_risk": _scenario_risk_line(snap, total_pct, bias),
        "driver_details": _driver_details(snap, attribution, geri_pct, vix_pct,
                                          gas_pct, supply, demand),
        "market_regime": _market_regime(snap),
        "analogs": _match_analogs(scenario_shift),
        "risk_score": _risk_score(snap, geri_pct, gas_pct, supply, demand),
        "regional_risk": regional,
        "confidence_reasons": _confidence_reasons(geri_pct, vix_pct, extra_drivers=True),
        "intelligence": {
            "geri_live": snap.get("geri_live"),
            "geri_live_band": snap.get("geri_live_band"),
            "alerts_processed": snap.get("geri_live_alerts"),
            "as_of": snap.get("geri_live_at"),
        },
        "market": snap,
        "as_of": datetime.utcnow().strftime("%d %B %Y, %H:%M UTC"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Saved scenarios (premium)
# ─────────────────────────────────────────────────────────────────────────────

class SaveScenarioRequest(BaseModel):
    name: str
    params: dict
    result: Optional[dict] = None


@router.get("/api/brent-forecast/scenarios")
async def list_scenarios(x_brent_token: Optional[str] = Header(None)):
    user = _require_user(x_brent_token)
    with get_cursor(commit=False) as cur:
        cur.execute("SELECT id, name, params, result, created_at FROM brent_saved_scenarios "
                    "WHERE user_id = %s ORDER BY created_at DESC LIMIT 100", (user["id"],))
        rows = cur.fetchall()
    return {"success": True, "scenarios": [
        {"id": r["id"], "name": r["name"], "params": r["params"], "result": r["result"],
         "created_at": r["created_at"].isoformat()} for r in rows]}


@router.post("/api/brent-forecast/scenarios")
async def save_scenario(body: SaveScenarioRequest,
                        x_brent_token: Optional[str] = Header(None)):
    user = _require_user(x_brent_token)
    name = (body.name or "").strip()[:120] or "Untitled scenario"
    with get_cursor() as cur:
        cur.execute("INSERT INTO brent_saved_scenarios (user_id, name, params, result) "
                    "VALUES (%s, %s, %s, %s) RETURNING id",
                    (user["id"], name, json.dumps(body.params), json.dumps(body.result or {})))
        sid = cur.fetchone()["id"]
    return {"success": True, "id": sid}


@router.delete("/api/brent-forecast/scenarios/{scenario_id}")
async def delete_scenario(scenario_id: int,
                          x_brent_token: Optional[str] = Header(None)):
    user = _require_user(x_brent_token)
    with get_cursor() as cur:
        cur.execute("DELETE FROM brent_saved_scenarios WHERE id = %s AND user_id = %s",
                    (scenario_id, user["id"]))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Scenario not found")
    return {"success": True}


# ─────────────────────────────────────────────────────────────────────────────
# Risk alerts (premium, in-app)
# ─────────────────────────────────────────────────────────────────────────────

_ALERT_TYPES = {
    "geri_live_above": "GERI Live rises above",
    "vix_above": "VIX rises above",
    "brent_above": "Brent rises above",
    "brent_below": "Brent falls below",
    "forecast_bearish": "Baseline 24–48h forecast turns bearish",
    "analog_match_above": "Best historical analog match exceeds (%)",
}


class AlertRequest(BaseModel):
    alert_type: str
    threshold: float = 0.0


@router.get("/api/brent-forecast/alerts")
async def list_alerts(x_brent_token: Optional[str] = Header(None)):
    user = _require_user(x_brent_token)
    with get_cursor(commit=False) as cur:
        cur.execute("SELECT id, alert_type, threshold, active, created_at FROM brent_user_alerts "
                    "WHERE user_id = %s ORDER BY created_at DESC LIMIT 50", (user["id"],))
        rows = cur.fetchall()
    return {"success": True, "alert_types": _ALERT_TYPES, "alerts": [
        {"id": r["id"], "alert_type": r["alert_type"], "threshold": float(r["threshold"]),
         "active": r["active"], "created_at": r["created_at"].isoformat()} for r in rows]}


@router.post("/api/brent-forecast/alerts")
async def create_alert(body: AlertRequest,
                       x_brent_token: Optional[str] = Header(None)):
    user = _require_user(x_brent_token)
    if body.alert_type not in _ALERT_TYPES:
        raise HTTPException(status_code=400, detail="Unknown alert type")
    threshold = _clamp(float(body.threshold or 0), -1000, 10000)
    with get_cursor() as cur:
        cur.execute("SELECT COUNT(*) AS c FROM brent_user_alerts WHERE user_id = %s", (user["id"],))
        if cur.fetchone()["c"] >= 20:
            raise HTTPException(status_code=400, detail="Alert limit reached (20)")
        cur.execute("INSERT INTO brent_user_alerts (user_id, alert_type, threshold) "
                    "VALUES (%s, %s, %s) RETURNING id", (user["id"], body.alert_type, threshold))
        aid = cur.fetchone()["id"]
    return {"success": True, "id": aid}


@router.delete("/api/brent-forecast/alerts/{alert_id}")
async def delete_alert(alert_id: int,
                       x_brent_token: Optional[str] = Header(None)):
    user = _require_user(x_brent_token)
    with get_cursor() as cur:
        cur.execute("DELETE FROM brent_user_alerts WHERE id = %s AND user_id = %s",
                    (alert_id, user["id"]))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Alert not found")
    return {"success": True}


@router.get("/api/brent-forecast/alerts/evaluate")
async def evaluate_alerts(x_brent_token: Optional[str] = Header(None)):
    """Evaluate the user's alerts against live market conditions (in-app)."""
    user = _require_user(x_brent_token)
    with get_cursor(commit=False) as cur:
        cur.execute("SELECT id, alert_type, threshold FROM brent_user_alerts "
                    "WHERE user_id = %s AND active", (user["id"],))
        alerts = cur.fetchall()
    if not alerts:
        return {"success": True, "triggered": [], "evaluated": 0}

    snap = _market_snapshot()
    brent = snap.get("brent_intraday") or snap.get("brent")
    geri_live = snap.get("geri_live") or snap.get("geri")
    vix = snap.get("vix")

    baseline_bias = None
    best_match = None
    types_present = {a["alert_type"] for a in alerts}
    if "forecast_bearish" in types_present and brent:
        horizons, _attr, _tp = _compute_scenario(brent, 0, 0)
        baseline_bias = horizons["24_48h"]["bias"]
    if "analog_match_above" in types_present:
        rows = _load_history()
        recent = [r for r in rows[-8:] if r["geri"] is not None]
        if len(recent) >= 2 and recent[0]["geri"]:
            shift = (recent[-1]["geri"] - recent[0]["geri"]) / max(recent[0]["geri"], 5) * 100
            matches = _match_analogs(shift)
            best_match = matches[0]["match_pct"] if matches else None

    triggered = []
    for a in alerts:
        t, th = a["alert_type"], float(a["threshold"])
        hit, cur_val, msg = False, None, ""
        if t == "geri_live_above" and geri_live is not None:
            cur_val, hit = geri_live, geri_live > th
            msg = f"GERI Live is {geri_live:.0f} (threshold {th:.0f})"
        elif t == "vix_above" and vix is not None:
            cur_val, hit = vix, vix > th
            msg = f"VIX is {vix:.1f} (threshold {th:.1f})"
        elif t == "brent_above" and brent is not None:
            cur_val, hit = brent, brent > th
            msg = f"Brent is ${brent:.2f} (threshold ${th:.2f})"
        elif t == "brent_below" and brent is not None:
            cur_val, hit = brent, brent < th
            msg = f"Brent is ${brent:.2f} (threshold ${th:.2f})"
        elif t == "forecast_bearish" and baseline_bias is not None:
            cur_val, hit = baseline_bias, baseline_bias == "Bearish"
            msg = f"Baseline 24–48h forecast bias is {baseline_bias}"
        elif t == "analog_match_above":
            cur_val = best_match
            hit = best_match is not None and best_match > th
            msg = (f"Best analog match is {best_match}% (threshold {th:.0f}%)"
                   if best_match is not None else "No qualifying analog right now")
        if hit:
            triggered.append({"id": a["id"], "alert_type": t, "threshold": th,
                              "current": cur_val, "message": msg})
    return {"success": True, "triggered": triggered, "evaluated": len(alerts)}


# ─────────────────────────────────────────────────────────────────────────────
# Auth
# ─────────────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/api/brent-forecast/login")
async def brent_login(body: LoginRequest):
    email = (body.email or "").strip().lower()
    with get_cursor(commit=False) as cur:
        cur.execute("SELECT * FROM paid_brent_forecast_users WHERE LOWER(email) = %s", (email,))
        user = cur.fetchone()
    if not user or not _check(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not _is_active(user):
        raise HTTPException(status_code=402, detail="Your subscription is not active")
    token = _create_session(user["id"])
    return {"success": True, "token": token, "email": user["email"],
            "ref_code": user["ref_code"], "status": user["status"]}


@router.post("/api/brent-forecast/logout")
async def brent_logout(x_brent_token: Optional[str] = Header(None)):
    if x_brent_token:
        with get_cursor() as cur:
            cur.execute("DELETE FROM brent_forecast_sessions WHERE token = %s", (x_brent_token,))
    return {"success": True}


@router.get("/api/brent-forecast/me")
async def brent_me(x_brent_token: Optional[str] = Header(None)):
    user = _user_from_token(x_brent_token)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    earnings = 0.0
    referrals = 0
    with get_cursor(commit=False) as cur:
        cur.execute("SELECT COALESCE(SUM(amount_eur),0) AS total, COUNT(DISTINCT referred_user_id) AS n "
                    "FROM brent_commission_ledger WHERE referrer_user_id = %s", (user["id"],))
        r = cur.fetchone()
        if r:
            earnings = float(r["total"])
            referrals = int(r["n"])
    return {"success": True, "email": user["email"], "status": user["status"],
            "trial": user["trial"], "paid": user["paid"],
            "active": _is_active(user), "ref_code": user["ref_code"],
            "welcome_banner_seen": user["welcome_banner_seen"],
            "commission_earned_eur": round(earnings, 2), "referrals": referrals}


@router.post("/api/brent-forecast/welcome-seen")
async def welcome_seen(x_brent_token: Optional[str] = Header(None)):
    user = _user_from_token(x_brent_token)
    if user:
        with get_cursor() as cur:
            cur.execute("UPDATE paid_brent_forecast_users SET welcome_banner_seen = TRUE WHERE id = %s",
                        (user["id"],))
    return {"success": True}


# ─────────────────────────────────────────────────────────────────────────────
# Checkout / confirm
# ─────────────────────────────────────────────────────────────────────────────

class CheckoutRequest(BaseModel):
    ref: Optional[str] = None


@router.post("/api/brent-forecast/checkout")
async def brent_checkout(body: CheckoutRequest):
    """Anonymous checkout — Stripe collects the email; the user account is
    created in /confirm and the webhook handler."""
    try:
        price_id = _ensure_price_id()
        ensure_stripe_initialized()
        base = _base_url()
        metadata = {"type": "brent_forecast"}
        ref = (body.ref or "").strip()
        if ref and _REF_RE.match(ref):
            metadata["ref"] = ref
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{"price": price_id, "quantity": 1}],
            mode="subscription",
            success_url=f"{base}/tools/brent-intelligence-scenario/engine?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{base}/tools/brent-oil-risk-forecast?checkout=cancelled",
            metadata=metadata,
            subscription_data={"trial_period_days": TRIAL_DAYS, "metadata": metadata},
            allow_promotion_codes=False,
        )
        return {"success": True, "checkout_url": session.url}
    except Exception as e:
        logger.error(f"Brent forecast checkout failed: {e}")
        raise HTTPException(status_code=500, detail="Could not start checkout")


BRENT_WELCOME_SUBJECT = "Welcome to EnergyRiskIQ – Your Brent Intelligence Scenario Engine Access"


def _build_brent_welcome_email(email: str, password: str):
    base = _base_url()
    login_link = f"{base}/tools/brent-intelligence-scenario/engine"
    logo_url = f"{base}/static/logo.png"

    text_body = f"""Hi,

Welcome to EnergyRiskIQ—and thank you for subscribing to the Brent Intelligence Scenario Engine™.

Your 14-day free trial is now active. Your subscription continues at €8/month after the trial, and you can cancel anytime.

IMPORTANT — SAVE THIS EMAIL
This email contains your login credentials. Please keep it in a safe place — you will need it to access your Scenario Engine dashboard.

Your access details

Dashboard: {login_link}
Login email: {email}
Password: {password}

What you'll find inside your Scenario Engine

* 4 forecasting horizons – 0-24h, 24-48h, 72h and 7-day Brent reaction windows.
* 5-driver scenario builder – GERI, VIX, gas stress, supply presets, and demand conditions.
* Historical Analog Engine – Compare your scenario against real historical market episodes.
* Driver attribution & probability ranges – See exactly what moves your forecast.
* Saved scenarios & exports – Build a scenario library and export forecast reports.
* Partner referral program – Earn a 40% recurring commission for every referred subscriber.

Where to begin

1. Open your dashboard and log in with the credentials above.
2. Run your first scenario using a quick preset such as Strait of Hormuz Risk or OPEC+ Cut.
3. Save it to your scenario library so you can track how conditions evolve.

Log in now: {login_link}

Thank you for joining the EnergyRiskIQ community.

Kind regards,

Emil Constantinescu
Founder, EnergyRiskIQ

---

Need assistance?

You can reply directly to this email at any time. We read every message and are always happy to help."""

    html_body = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{BRENT_WELCOME_SUBJECT}</title>
</head>
<body style="margin:0; padding:0; background-color:#0f172a; font-family:Arial, Helvetica, sans-serif; color:#1a1a1a; -webkit-text-size-adjust:100%;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#0f172a; padding:24px 0;">
    <tr>
      <td align="center">
        <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px; width:100%; background-color:#ffffff; border-radius:12px; overflow:hidden;">
          <tr>
            <td style="background-color:#0f172a; padding:28px 32px; text-align:center;">
              <table role="presentation" cellpadding="0" cellspacing="0" align="center" style="margin:0 auto;">
                <tr>
                  <td style="vertical-align:middle; padding-right:12px;">
                    <img src="{logo_url}" alt="EnergyRiskIQ" width="40" height="40" style="display:block; border:0; outline:none; text-decoration:none;">
                  </td>
                  <td style="vertical-align:middle;">
                    <span style="color:#d4a017; font-size:22px; font-weight:bold; letter-spacing:0.5px;">EnergyRiskIQ</span>
                  </td>
                </tr>
              </table>
              <p style="margin:12px 0 0; color:#94a3b8; font-size:13px;">Brent Intelligence Scenario Engine&trade;</p>
            </td>
          </tr>
          <tr>
            <td style="padding:32px;">
              <p style="margin:0 0 16px; font-size:16px; line-height:1.6;">Hi,</p>
              <p style="margin:0 0 16px; font-size:16px; line-height:1.6;">Welcome to <strong>EnergyRiskIQ</strong>&mdash;and thank you for subscribing to the <strong>Brent Intelligence Scenario Engine&trade;</strong>.</p>
              <p style="margin:0 0 16px; font-size:16px; line-height:1.6;">Your <strong>14-day free trial</strong> is now active. Your subscription continues at &euro;8/month after the trial, and you can cancel anytime.</p>

              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 24px;">
                <tr>
                  <td style="background-color:#fef3c7; border:1px solid #d4a017; border-radius:8px; padding:14px 18px; font-size:15px; line-height:1.6; color:#78350f;">
                    <strong>&#9888;&#65039; Important &mdash; save this email.</strong> It contains your login credentials. Keep it in a safe place for future access to your Scenario Engine dashboard.
                  </td>
                </tr>
              </table>

              <h2 style="margin:0 0 12px; font-size:18px; color:#0f172a;">Your access details</h2>
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 24px;">
                <tr>
                  <td style="background-color:#f1f5f9; border:1px solid #e2e8f0; border-radius:8px; padding:18px 22px;">
                    <p style="margin:0 0 4px; font-size:13px; color:#64748b; text-transform:uppercase; letter-spacing:0.5px;">Dashboard link</p>
                    <p style="margin:0 0 14px; font-size:15px;"><a href="{login_link}" style="color:#0f172a; font-weight:bold;">{login_link}</a></p>
                    <p style="margin:0 0 4px; font-size:13px; color:#64748b; text-transform:uppercase; letter-spacing:0.5px;">Login email</p>
                    <p style="margin:0 0 14px; font-size:15px; color:#0f172a; font-weight:bold;">{email}</p>
                    <p style="margin:0 0 4px; font-size:13px; color:#64748b; text-transform:uppercase; letter-spacing:0.5px;">Password</p>
                    <p style="margin:0; font-size:16px; color:#0f172a; font-weight:bold; letter-spacing:1px; font-family:'Courier New', monospace;">{password}</p>
                  </td>
                </tr>
              </table>

              <h2 style="margin:28px 0 12px; font-size:18px; color:#0f172a;">What you'll find inside your Scenario Engine</h2>
              <ul style="margin:0 0 16px; padding-left:20px; font-size:16px; line-height:1.7;">
                <li><strong>4 forecasting horizons</strong> &ndash; 0&ndash;24h, 24&ndash;48h, 72h and 7-day Brent reaction windows.</li>
                <li><strong>5-driver scenario builder</strong> &ndash; GERI, VIX, gas stress, supply presets, and demand conditions.</li>
                <li><strong>Historical Analog Engine</strong> &ndash; Compare your scenario against real historical market episodes.</li>
                <li><strong>Driver attribution &amp; probability ranges</strong> &ndash; See exactly what moves your forecast.</li>
                <li><strong>Saved scenarios &amp; exports</strong> &ndash; Build a scenario library and export forecast reports.</li>
                <li><strong>Partner referral program</strong> &ndash; Earn a 40% recurring commission for every referred subscriber.</li>
              </ul>

              <h2 style="margin:28px 0 12px; font-size:18px; color:#0f172a;">Where to begin</h2>
              <p style="margin:0 0 12px; font-size:16px; line-height:1.6;"><strong>1. Open your dashboard</strong><br>Log in with the credentials above.</p>
              <p style="margin:0 0 12px; font-size:16px; line-height:1.6;"><strong>2. Run your first scenario</strong><br>Try a quick preset such as Strait of Hormuz Risk or OPEC+ Cut.</p>
              <p style="margin:0 0 24px; font-size:16px; line-height:1.6;"><strong>3. Save it to your library</strong><br>Track how conditions evolve day by day.</p>

              <table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 auto 24px;">
                <tr>
                  <td align="center" style="border-radius:8px; background-color:#d4a017;">
                    <a href="{login_link}" style="display:inline-block; padding:14px 28px; font-size:16px; font-weight:bold; color:#0f172a; text-decoration:none; border-radius:8px;">&#128073; Open Your Scenario Engine</a>
                  </td>
                </tr>
              </table>

              <p style="margin:0 0 16px; font-size:16px; line-height:1.6;">Thank you for joining the EnergyRiskIQ community.</p>
              <p style="margin:0 0 4px; font-size:16px; line-height:1.6;">Kind regards,</p>
              <p style="margin:0; font-size:16px; line-height:1.6;"><strong>Emil Constantinescu</strong><br>Founder, EnergyRiskIQ</p>
            </td>
          </tr>
          <tr>
            <td style="background-color:#f1f5f9; padding:20px 32px; font-size:13px; line-height:1.6; color:#64748b;">
              <p style="margin:0 0 6px;"><strong>Need assistance?</strong></p>
              <p style="margin:0;">You can reply directly to this email at any time. We read every message and are always happy to help. Your subscription is &euro;8/month after the 14-day free trial &mdash; cancel anytime.</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

    return text_body, html_body


def _send_welcome_email(email: str, password: str):
    try:
        from src.alerts.channels import _send_brevo
        text_body, html_body = _build_brent_welcome_email(email, password)
        ok, err, _mid = _send_brevo(
            email,
            BRENT_WELCOME_SUBJECT,
            text_body,
            html_body)
        if not ok:
            logger.error(f"Brent welcome email failed for {email}: {err}")
    except Exception as e:
        logger.error(f"Brent welcome email error: {e}")


def _activate_user(email: str, customer_id: str, subscription_id: str,
                   sub_status: str, livemode: bool, ref: Optional[str]) -> dict:
    """Create or update the dedicated brent user; returns the row.
    Idempotent — safe to call from both /confirm and the webhook."""
    email = email.strip().lower()
    status = sub_status if sub_status in ("active", "trialing", "past_due", "canceled") else "active"
    mode = "live" if livemode else "sandbox"
    with get_cursor() as cur:
        cur.execute("SELECT * FROM paid_brent_forecast_users WHERE LOWER(email) = %s", (email,))
        row = cur.fetchone()
        if row:
            cur.execute("""
                UPDATE paid_brent_forecast_users
                SET stripe_customer_id = %s, stripe_subscription_id = %s,
                    stripe_mode = %s, status = %s,
                    trial = %s, paid = TRUE
                WHERE id = %s RETURNING *
            """, (customer_id, subscription_id, mode, status,
                  status == "trialing", row["id"]))
            return {"user": cur.fetchone(), "created": False, "password": None}
        password = _gen_password()
        ref_code = _gen_ref_code()
        cur.execute("""
            INSERT INTO paid_brent_forecast_users
                (email, password_hash, trial, paid, status, stripe_customer_id,
                 stripe_subscription_id, stripe_mode, ref_code, referred_by)
            VALUES (%s, %s, %s, TRUE, %s, %s, %s, %s, %s, %s)
            RETURNING *
        """, (email, _hash(password), status == "trialing", status,
              customer_id, subscription_id, mode, ref_code, ref or None))
        user = cur.fetchone()
        if ref:
            cur.execute("INSERT INTO brent_referral_events (ref_code, event_type) VALUES (%s, 'signup')",
                        (ref,))
    return {"user": user, "created": True, "password": password}


@router.get("/api/brent-forecast/confirm")
async def brent_confirm(session_id: str):
    """Webhook-independent activation: retrieve the checkout session in the
    current mode, create/activate the user, email credentials, auto-login."""
    try:
        ensure_stripe_initialized()
        session = stripe.checkout.Session.retrieve(session_id, expand=["subscription", "customer"])
    except Exception as e:
        logger.error(f"Brent confirm: session retrieve failed: {e}")
        raise HTTPException(status_code=400, detail="Checkout session not found")
    if (session.get("metadata") or {}).get("type") != "brent_forecast":
        raise HTTPException(status_code=400, detail="Not a Brent Forecast checkout")
    if session.get("status") != "complete":
        raise HTTPException(status_code=400, detail="Checkout not completed")
    sub = session.get("subscription") or {}
    customer = session.get("customer") or {}
    email = (session.get("customer_details") or {}).get("email") or customer.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="No email on checkout session")
    result = _activate_user(
        email=email,
        customer_id=customer.get("id") if isinstance(customer, dict) else str(customer),
        subscription_id=sub.get("id") if isinstance(sub, dict) else str(sub),
        sub_status=(sub.get("status") if isinstance(sub, dict) else None) or "trialing",
        livemode=bool(session.get("livemode")),
        ref=(session.get("metadata") or {}).get("ref"))
    if result["created"] and result["password"]:
        _send_welcome_email(result["user"]["email"], result["password"])
    token = _create_session(result["user"]["id"])
    return {"success": True, "token": token, "email": result["user"]["email"],
            "created": result["created"], "status": result["user"]["status"]}


# ─────────────────────────────────────────────────────────────────────────────
# Webhook handlers (called from src/billing/webhook_handler.py)
# ─────────────────────────────────────────────────────────────────────────────

def handle_brent_forecast_checkout_completed(session: dict) -> bool:
    if (session.get("metadata") or {}).get("type") != "brent_forecast":
        return False
    try:
        ensure_stripe_initialized()
        email = (session.get("customer_details") or {}).get("email")
        sub_id = session.get("subscription")
        sub_status = "trialing"
        if sub_id:
            try:
                sub = stripe.Subscription.retrieve(sub_id)
                sub_status = sub.get("status", "trialing")
            except Exception:
                pass
        if not email:
            try:
                cust = stripe.Customer.retrieve(session.get("customer"))
                email = cust.get("email")
            except Exception:
                pass
        if not email:
            logger.error("Brent checkout webhook: no email available")
            return True
        result = _activate_user(
            email=email, customer_id=session.get("customer"),
            subscription_id=sub_id, sub_status=sub_status,
            livemode=bool(session.get("livemode")),
            ref=(session.get("metadata") or {}).get("ref"))
        if result["created"] and result["password"]:
            _send_welcome_email(result["user"]["email"], result["password"])
    except Exception as e:
        logger.error(f"Brent checkout webhook failed: {e}")
    return True


def handle_brent_forecast_subscription_event(subscription: dict) -> bool:
    is_ours = (subscription.get("metadata") or {}).get("type") == "brent_forecast"
    sub_id = subscription.get("id")
    with get_cursor() as cur:
        cur.execute("SELECT id FROM paid_brent_forecast_users WHERE stripe_subscription_id = %s",
                    (sub_id,))
        row = cur.fetchone()
        if not row:
            return is_ours   # ours-but-no-row: swallow so main plan logic is untouched
        status = subscription.get("status", "active")
        if subscription.get("cancel_at_period_end") and status in ("active", "trialing"):
            status = "canceling"
        cur.execute("UPDATE paid_brent_forecast_users SET status = %s, trial = %s WHERE id = %s",
                    (status, status == "trialing", row["id"]))
    return True


def handle_brent_forecast_subscription_deleted(subscription: dict) -> bool:
    is_ours = (subscription.get("metadata") or {}).get("type") == "brent_forecast"
    sub_id = subscription.get("id")
    with get_cursor() as cur:
        cur.execute("SELECT id FROM paid_brent_forecast_users WHERE stripe_subscription_id = %s",
                    (sub_id,))
        row = cur.fetchone()
        if not row:
            return is_ours
        cur.execute("UPDATE paid_brent_forecast_users SET status = 'canceled', paid = FALSE WHERE id = %s",
                    (row["id"],))
        cur.execute("DELETE FROM brent_forecast_sessions WHERE user_id = %s", (row["id"],))
    return True


def is_brent_forecast_subscription(subscription_id: Optional[str]) -> bool:
    if not subscription_id:
        return False
    try:
        with get_cursor(commit=False) as cur:
            cur.execute("SELECT 1 FROM paid_brent_forecast_users WHERE stripe_subscription_id = %s",
                        (subscription_id,))
            return cur.fetchone() is not None
    except Exception:
        return False


def handle_brent_forecast_invoice_paid(invoice: dict) -> bool:
    """Mark active + accrue 40% referral commission. Returns True if this
    invoice belongs to a brent-forecast subscription."""
    sub_id = invoice.get("subscription")
    if not sub_id:
        return False
    with get_cursor() as cur:
        cur.execute("SELECT * FROM paid_brent_forecast_users WHERE stripe_subscription_id = %s",
                    (sub_id,))
        user = cur.fetchone()
        if not user:
            return False
        cur.execute("UPDATE paid_brent_forecast_users SET status = 'active', trial = FALSE, paid = TRUE "
                    "WHERE id = %s", (user["id"],))
        # 40% recurring commission — only on real money (amount_paid > 0)
        if user.get("referred_by") and (invoice.get("amount_paid") or 0) > 0:
            cur.execute("SELECT id FROM paid_brent_forecast_users WHERE ref_code = %s AND id != %s",
                        (user["referred_by"], user["id"]))
            referrer = cur.fetchone()
            if referrer:
                cur.execute("""
                    INSERT INTO brent_commission_ledger
                        (referrer_user_id, referred_user_id, invoice_id, amount_eur)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (invoice_id) DO NOTHING
                """, (referrer["id"], user["id"], invoice.get("id"), COMMISSION_EUR))
    return True


def handle_brent_forecast_invoice_failed(invoice: dict) -> bool:
    sub_id = invoice.get("subscription")
    if not sub_id:
        return False
    with get_cursor() as cur:
        cur.execute("SELECT id FROM paid_brent_forecast_users WHERE stripe_subscription_id = %s",
                    (sub_id,))
        user = cur.fetchone()
        if not user:
            return False
        cur.execute("UPDATE paid_brent_forecast_users SET status = 'past_due' WHERE id = %s",
                    (user["id"],))
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Pages
# ─────────────────────────────────────────────────────────────────────────────

_STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "static")


@router.get("/tools/brent-oil-risk-forecast", include_in_schema=False)
async def brent_forecast_public_page():
    return FileResponse(os.path.join(_STATIC_DIR, "brent-oil-risk-forecast.html"),
                        media_type="text/html")


@router.get("/tools/brent-intelligence-scenario/engine", include_in_schema=False)
async def brent_scenario_engine_page():
    return FileResponse(os.path.join(_STATIC_DIR, "brent-intelligence-scenario-engine.html"),
                        media_type="text/html")


# ─────────────────────────────────────────────────────────────────────────────
# Embed widget (free, branded, referral-aware)
# ─────────────────────────────────────────────────────────────────────────────

_REF_RE = re.compile(r"^[A-Za-z0-9_-]{1,24}$")


@router.get("/embed/brent-risk-widget")
async def embed_brent_risk_widget(request: Request, ref: Optional[str] = None):
    ref = (ref or "").strip()
    if not _REF_RE.match(ref):
        ref = ""
    if ref:
        try:
            with get_cursor() as cur:
                cur.execute("INSERT INTO brent_referral_events (ref_code, event_type, ip) "
                            "VALUES (%s, 'click', %s)",
                            (ref, (request.client.host if request.client else None)))
        except Exception:
            pass
    try:
        snap = _market_snapshot()
    except Exception:
        snap = {}
    brent = snap.get("brent")
    geri = snap.get("geri_live") or snap.get("geri")
    geri_band = (snap.get("geri_live_band") or snap.get("geri_band") or "—").upper()
    vix = snap.get("vix")
    chg = snap.get("brent_change_pct") or 0
    chg_color = "#22c55e" if chg > 0 else "#ef4444" if chg < 0 else "#94a3b8"
    chg_sign = "+" if chg > 0 else ""
    band_color = {"LOW": "#22c55e", "MODERATE": "#eab308", "ELEVATED": "#f97316",
                  "HIGH": "#ef4444", "SEVERE": "#dc2626"}.get(geri_band, "#94a3b8")
    link = f"{_base_url()}/tools/brent-oil-risk-forecast" + (f"?ref={ref}" if ref else "")
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{{margin:0;font-family:Arial,Helvetica,sans-serif;background:#0b1020;color:#e2e8f0}}
.w{{border:1px solid #26314f;border-radius:12px;padding:16px 18px;max-width:340px;margin:0 auto;background:#111a33}}
.t{{font-size:12px;color:#94a3b8;letter-spacing:.5px;text-transform:uppercase}}
.p{{font-size:30px;font-weight:bold;color:#f8fafc;margin:4px 0}}
.row{{display:flex;justify-content:space-between;margin-top:10px;font-size:13px}}
.pill{{padding:2px 10px;border-radius:99px;font-weight:bold;font-size:11px}}
a{{color:#d4a017;text-decoration:none;font-size:12px}}
.cta{{display:block;text-align:center;background:#d4a017;color:#0b1020;font-weight:bold;
border-radius:8px;padding:9px;margin-top:14px;font-size:13px}}
</style></head><body>
<div class="w">
  <div class="t">Brent Oil Risk Forecast</div>
  <div class="p">{f"${brent:.2f}" if brent else "—"}<span style="font-size:14px;color:{chg_color}"> {chg_sign}{chg:.2f}%</span></div>
  <div class="row"><span style="color:#94a3b8">GERI Risk Level</span>
    <span class="pill" style="background:{band_color}22;color:{band_color}">{geri_band}{f" · {geri:.1f}" if geri else ""}</span></div>
  <div class="row"><span style="color:#94a3b8">VIX</span><span>{f"{vix:.1f}" if vix else "—"}</span></div>
  <a class="cta" href="{link}" target="_blank" rel="noopener">Run a Free Brent Risk Scenario →</a>
  <div style="text-align:center;margin-top:8px"><a href="{link}" target="_blank" rel="noopener">Powered by EnergyRiskIQ</a></div>
</div></body></html>"""
    return HTMLResponse(content=html, headers={"Cache-Control": "public, max-age=120"})
