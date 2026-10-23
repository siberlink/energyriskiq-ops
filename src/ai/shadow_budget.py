"""One durable UTC-day budget for enrichment AND GPT-4.1 labels.

Reserve before every provider request under a transaction advisory lock. Crashed
requests retain their reservation. Unknown/ambiguous charges use the upper bound.
No secrets or provider request headers are logged.
"""
import json
import os
from datetime import datetime, timezone, timedelta
import time

from src.db.db import get_cursor

RATES = {"gpt-4.1-mini": (.4, 1.6), "gpt-4.1": (2., 8.)}


class BudgetStopped(RuntimeError):
    pass


def rate_slot(rpm,deadline):
    """Shared private rate ledger; the daily shadow job never writes job_runs."""
    if rpm<=0:
        raise ValueError("Positive request rate required")
    rpm=min(20.,rpm)
    with get_cursor() as c:
        c.execute("SELECT pg_advisory_xact_lock(hashtext('risk_pipeline_v2_rate'))")
        c.execute("SELECT max(slot_at) AS last FROM risk_pipeline_v2_rate_slot")
        previous=c.fetchone()["last"]
        now=datetime.utcnow()
        slot=max(now,previous+timedelta(seconds=60/rpm)) if previous else now
        if time.monotonic()+(slot-now).total_seconds()+60>deadline:
            raise RuntimeError("Rate slot would exceed runtime deadline")
        c.execute("INSERT INTO risk_pipeline_v2_rate_slot(slot_at) VALUES(%s)",(slot,))
    time.sleep(max(0.,(slot-datetime.utcnow()).total_seconds()))


def limit():
    value = float(os.environ.get("RISK_PIPELINE_V2_DAILY_BUDGET_USD", "5"))
    if not 0 < value <= 5:
        raise ValueError("Approved shared daily budget must be in (0, $5]")
    return value


def upper_bound(model, messages, output_tokens, response_format=None):
    rates = RATES[model]  # Unknown models fail closed.
    # UTF-8 bytes upper-bound BPE tokens; envelope/schema allowance included.
    text = json.dumps({"messages": messages, "response_format": response_format}, ensure_ascii=False)
    return ((len(text.encode()) + 512) * rates[0] + output_tokens * rates[1]) / 1e6


def reserve(model, purpose, item_id, bound):
    if bound <= 0:
        raise ValueError("Positive reservation required")
    now = datetime.now(timezone.utc)
    with get_cursor() as c:
        c.execute("SELECT pg_advisory_xact_lock(hashtext('risk_pipeline_v2_budget'))")
        c.execute("""SELECT COALESCE(sum(CASE WHEN status='reserved' THEN reserved_usd
            ELSE charged_usd END),0) AS committed FROM risk_pipeline_v2_usage
            WHERE budget_date=%s""", (now.date(),))
        committed = float(c.fetchone()["committed"])
        if committed + bound > limit():
            raise BudgetStopped("Shared $5/day budget admission stopped; no paid request made")
        c.execute("""INSERT INTO risk_pipeline_v2_usage
            (budget_date,purpose,item_id,model,status,reserved_usd)
            VALUES(%s,%s,%s,%s,'reserved',%s) RETURNING id""",
                  (now.date(), purpose, item_id, model, bound))
        return c.fetchone()["id"], now.date()


def settle(id_, model, bound, usage, raw_output=None, error=None, rejected=False):
    """Persist usage/raw output BEFORE callers validate or save a classification."""
    charged = (float(usage["prompt_tokens"]) * RATES[model][0] +
               float(usage["completion_tokens"]) * RATES[model][1]) / 1e6 if usage else (0. if rejected else bound)
    with get_cursor() as c:
        c.execute("""UPDATE risk_pipeline_v2_usage SET status=%s,charged_usd=%s,
            usage=%s::jsonb,raw_output=%s,error=%s,finished_at=now()
            WHERE id=%s AND status='reserved'""",
                  ("error" if error else "completed", charged, json.dumps(usage),
                   raw_output, error, id_))
    if charged > bound or charged > limit():
        # Upper-bound violation must halt, not continue with an understated ledger.
        raise BudgetStopped("Observed request cost exceeded reserved upper bound")
    return charged


def request(client, model, messages, max_tokens, purpose, item_id, response_format=None):
    bound = upper_bound(model, messages, max_tokens, response_format)
    id_, day = reserve(model, purpose, item_id, bound)
    if datetime.now(timezone.utc).date() != day:
        settle(id_, model, bound, None, error="UTC day ended before request", rejected=True)
        raise BudgetStopped("Budget day ended")
    try:
        args = dict(model=model, messages=messages, max_tokens=max_tokens, temperature=0)
        if response_format:
            args["response_format"] = response_format
        response = client.chat.completions.create(**args)
    except Exception as exc:
        code = getattr(exc, "status_code", None)
        settle(id_, model, bound, None, error=f"{type(exc).__name__}: request failed",
               rejected=code is not None and 400 <= code < 500 and code != 408)
        raise
    raw = response.choices[0].message.content or ""
    usage = response.usage.model_dump() if response.usage else None
    amount = settle(id_, model, bound, usage, raw_output=raw)
    return raw, usage, amount, response.choices[0].finish_reason


def validation_failed(purpose,item_id,message):
    """Retain paid usage/raw evidence while recording post-response failures."""
    with get_cursor() as c:
        c.execute("""UPDATE risk_pipeline_v2_usage SET status='error',error=%s
            WHERE status='completed' AND id=(SELECT id FROM risk_pipeline_v2_usage
                WHERE purpose=%s AND item_id=%s ORDER BY id DESC LIMIT 1)""",
                  (message,purpose,item_id))
