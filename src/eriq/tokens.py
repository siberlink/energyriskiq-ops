import logging
from datetime import datetime, timezone
from src.db.db import get_cursor, execute_query

logger = logging.getLogger(__name__)

PLAN_TOKEN_ALLOWANCE = {
    "free": 50_000,
    "personal": 100_000,
    "trader": 300_000,
    "pro": 500_000,
    "enterprise": 1_000_000,
}

TOKEN_PRICE_EUR_PER_100K = 1.35

TOKEN_PACKS = [
    {"tokens": 100_000, "label": "100K", "price_eur": 1.35},
    {"tokens": 300_000, "label": "300K", "price_eur": 4.05},
    {"tokens": 500_000, "label": "500K", "price_eur": 6.75},
    {"tokens": 1_000_000, "label": "1M", "price_eur": 13.50},
]

LOW_BALANCE_THRESHOLD = 3000


def ensure_token_balance(user_id: int, plan: str):
    rows = execute_query(
        "SELECT user_id FROM eriq_token_balances WHERE user_id = %s", (user_id,)
    )
    if rows:
        return

    allowance = PLAN_TOKEN_ALLOWANCE.get(plan, 50_000)
    with get_cursor() as cur:
        cur.execute("""
            INSERT INTO eriq_token_balances
            (user_id, plan_monthly_allowance, allowance_remaining, purchased_balance, period_start)
            VALUES (%s, %s, %s, 0, DATE_TRUNC('month', NOW()))
            ON CONFLICT (user_id) DO NOTHING
        """, (user_id, allowance, allowance))
        _log_ledger(cur, user_id, allowance, "allowance_grant", "Monthly allowance granted")


def get_token_status(user_id: int, plan: str) -> dict:
    ensure_token_balance(user_id, plan)
    _maybe_reset_monthly(user_id, plan)

    rows = execute_query("""
        SELECT plan_monthly_allowance, allowance_remaining, purchased_balance, period_start
        FROM eriq_token_balances WHERE user_id = %s
    """, (user_id,))

    if not rows:
        return {"total_available": 0, "allowance_remaining": 0, "purchased_balance": 0, "low_balance": True}

    r = rows[0]
    total = r["allowance_remaining"] + r["purchased_balance"]
    return {
        "total_available": total,
        "allowance_remaining": r["allowance_remaining"],
        "purchased_balance": r["purchased_balance"],
        "plan_monthly_allowance": r["plan_monthly_allowance"],
        "period_start": r["period_start"].isoformat() if r["period_start"] else None,
        "low_balance": total < LOW_BALANCE_THRESHOLD,
        "low_balance_threshold": LOW_BALANCE_THRESHOLD,
    }


def check_can_use(user_id: int, plan: str) -> tuple:
    status = get_token_status(user_id, plan)
    if status["total_available"] <= 0:
        return False, status
    return True, status


def deduct_tokens(user_id: int, tokens_used: int, conversation_id: int = None):
    if tokens_used <= 0:
        return

    with get_cursor() as cur:
        cur.execute("""
            SELECT allowance_remaining, purchased_balance
            FROM eriq_token_balances WHERE user_id = %s FOR UPDATE
        """, (user_id,))
        row = cur.fetchone()
        if not row:
            return

        allowance_left = row["allowance_remaining"]
        purchased_left = row["purchased_balance"]

        allowance_deduct = min(tokens_used, allowance_left)
        remaining_to_deduct = tokens_used - allowance_deduct
        purchased_deduct = min(remaining_to_deduct, purchased_left)

        new_allowance = allowance_left - allowance_deduct
        new_purchased = purchased_left - purchased_deduct

        cur.execute("""
            UPDATE eriq_token_balances
            SET allowance_remaining = %s, purchased_balance = %s, updated_at = NOW()
            WHERE user_id = %s
        """, (new_allowance, new_purchased, user_id))

        ref_info = f"conversation:{conversation_id}" if conversation_id else "eriq_usage"
        _log_ledger(cur, user_id, -tokens_used, "usage", ref_info)


def credit_purchased_tokens(user_id: int, tokens: int, stripe_session_id: str = None):
    ensure_token_balance_raw(user_id)

    with get_cursor() as cur:
        cur.execute("""
            UPDATE eriq_token_balances
            SET purchased_balance = purchased_balance + %s, updated_at = NOW()
            WHERE user_id = %s
        """, (tokens, user_id))

        ref_info = f"stripe:{stripe_session_id}" if stripe_session_id else "purchase"
        _log_ledger(cur, user_id, tokens, "purchase", ref_info)

    logger.info(f"Credited {tokens} purchased tokens to user {user_id}")


def ensure_token_balance_raw(user_id: int):
    with get_cursor() as cur:
        cur.execute("""
            INSERT INTO eriq_token_balances
            (user_id, plan_monthly_allowance, allowance_remaining, purchased_balance, period_start)
            VALUES (%s, 50000, 50000, 0, DATE_TRUNC('month', NOW()))
            ON CONFLICT (user_id) DO NOTHING
        """, (user_id,))


def update_plan_allowance(user_id: int, plan: str):
    new_allowance = PLAN_TOKEN_ALLOWANCE.get(plan, 50_000)
    with get_cursor() as cur:
        cur.execute("""
            UPDATE eriq_token_balances
            SET plan_monthly_allowance = %s
            WHERE user_id = %s
        """, (new_allowance, user_id))


def _maybe_reset_monthly(user_id: int, plan: str):
    rows = execute_query("""
        SELECT period_start FROM eriq_token_balances WHERE user_id = %s
    """, (user_id,))
    if not rows or not rows[0]["period_start"]:
        return

    period_start = rows[0]["period_start"]
    now = datetime.now(timezone.utc)
    current_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    if period_start.replace(tzinfo=timezone.utc) < current_month_start:
        allowance = PLAN_TOKEN_ALLOWANCE.get(plan, 50_000)
        with get_cursor() as cur:
            cur.execute("""
                UPDATE eriq_token_balances
                SET allowance_remaining = %s, plan_monthly_allowance = %s,
                    period_start = %s, updated_at = NOW()
                WHERE user_id = %s
            """, (allowance, allowance, current_month_start, user_id))
            _log_ledger(cur, user_id, allowance, "monthly_reset", f"Monthly reset for {now.strftime('%Y-%m')}")
        logger.info(f"Monthly token reset for user {user_id}: {allowance} tokens")


def _log_ledger(cur, user_id: int, delta: int, source: str, ref_info: str = None):
    cur.execute("""
        INSERT INTO eriq_token_ledger (user_id, delta_tokens, source, ref_info)
        VALUES (%s, %s, %s, %s)
    """, (user_id, delta, source, ref_info))
