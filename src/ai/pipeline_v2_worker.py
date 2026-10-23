"""Opt-in newest-first enrichment, durable budget admission, leases and rate slots."""
from datetime import datetime, timedelta
import json
import logging
import time
import uuid

from src.db.db import get_cursor
from src.risk.pipeline_v2_core import enabled, plan
from src.risk.pipeline_v2 import metrics, internal_alert

logger = logging.getLogger(__name__)


def request_bound(text, system):
    # GPT-4.1-mini standard rates. Unknown models fail closed rather than underbudget.
    return (len((system+text).encode())+256)*.4/1e6 + 2000*1.6/1e6


def claim(settings, now):
    from .ai_worker import build_input_text, SYSTEM_PROMPT
    with get_cursor() as c:
        c.execute("SELECT pg_advisory_xact_lock(hashtext('risk_pipeline_v2_budget'))")
        c.execute("""SELECT COALESCE(sum((error::jsonb->>'charged_or_reserved_usd')::numeric),0) AS spent
            FROM job_runs WHERE job_name='risk_pipeline_v2_budget' AND index_date=%s""", (now.date(),))
        spent = float(c.fetchone()["spent"])
        c.execute("""SELECT id,title,raw_text,ai_attempts FROM events
            WHERE NOT processed AND ai_attempts<3 AND inserted_at<=%s
            AND (ai_impact_json->'_risk_pipeline_v2'->>'lease_until' IS NULL OR
                 (ai_impact_json->'_risk_pipeline_v2'->>'lease_until')::timestamp<%s)
            ORDER BY inserted_at DESC,id DESC FOR UPDATE SKIP LOCKED LIMIT %s""",
                  (now, now, settings["batch_size"]))
        rows = [dict(row) for row in c.fetchall()]
        if not rows:
            return None, [], 0.
        for row in rows:
            row["request_bound_usd"] = request_bound(build_input_text(row["title"], row["raw_text"]), SYSTEM_PROMPT)
        reserve = sum(row["request_bound_usd"]*3 for row in rows)
        if spent+reserve > settings["daily_budget_usd"]:
            raise RuntimeError("V2 daily budget cannot admit the required batch; capacity shortfall")
        c.execute("""INSERT INTO job_runs(job_name,index_date,status,run_key,error)
            VALUES('risk_pipeline_v2_budget',%s,'running',%s,%s) RETURNING id""",
                  (now.date(), f"risk-v2-budget:{uuid.uuid4()}",
                   json.dumps({"charged_or_reserved_usd": reserve, "initial_reserved_usd": reserve})))
        id_ = c.fetchone()["id"]
        lease = json.dumps({"lease_until": (now+timedelta(seconds=settings["runtime_seconds"]+300)).isoformat(),
                            "budget_run_id": id_})
        for row in rows:
            c.execute("""UPDATE events SET ai_attempts=ai_attempts+1,
                ai_impact_json=jsonb_set(COALESCE(ai_impact_json,'{}'::jsonb),
                '{_risk_pipeline_v2}',%s::jsonb,true) WHERE id=%s""", (lease, row["id"]))
    return id_, rows, reserve


def rate_slot(rpm, deadline):
    with get_cursor() as c:
        c.execute("SELECT pg_advisory_xact_lock(hashtext('risk_pipeline_v2_rate'))")
        c.execute("""SELECT max(started_at) AT TIME ZONE 'UTC' AS last FROM job_runs
            WHERE job_name='risk_pipeline_v2_rate_slot' AND started_at>=NOW()-interval '1 hour'""")
        previous = c.fetchone()["last"]
        now = datetime.utcnow()
        slot = max(now, previous+timedelta(seconds=60/rpm)) if previous else now
        if time.monotonic()+(slot-now).total_seconds()+60 > deadline:
            raise RuntimeError("V2 runtime limit reached before another paid request")
        c.execute("""INSERT INTO job_runs(job_name,index_date,status,run_key,started_at)
            VALUES('risk_pipeline_v2_rate_slot',%s,'running',%s,%s)""",
                  (now.date(), f"risk-v2-rate:{uuid.uuid4()}", slot))
    time.sleep(max(0., (slot-datetime.utcnow()).total_seconds()))


def settle(run_id, charged, remaining, done=False):
    with get_cursor() as c:
        c.execute("""UPDATE job_runs SET error=%s,status=%s,
            finished_at=CASE WHEN %s THEN NOW() ELSE finished_at END WHERE id=%s""",
                  (json.dumps({"charged_or_reserved_usd": charged+remaining,
                               "observed_or_upper_cost_usd": charged,
                               "unstarted_reserved_usd": remaining}),
                   "success" if done else "running", done, run_id))


def run():
    if not enabled():
        raise RuntimeError("Risk pipeline V2 is disabled")
    from src.risk.pipeline_v2_core import mode
    if mode() == "shadow":
        from .shadow_enrichment import run as run_shadow
        return run_shadow()
    from . import ai_worker as legacy
    if legacy.OPENAI_MODEL != "gpt-4.1-mini":
        raise RuntimeError("V2 budget pricing requires approved gpt-4.1-mini model")
    now = datetime.utcnow()
    with get_cursor() as c:
        health = metrics(c, now)
    internal_alert(health)
    settings = plan(health)
    # The SDK's hidden retries are off: every paid attempt gets rate/budget accounting.
    client = legacy.get_openai_client().with_options(timeout=60, max_retries=0)
    id_, rows, reserved = claim(settings, now)
    if not rows:
        return 0, 0
    deadline = time.monotonic()+settings["runtime_seconds"]
    charged, remaining, successes, failures = 0., reserved, 0, 0
    for row in rows:
        input_text = legacy.build_input_text(row["title"], row["raw_text"])
        amount, result, usage, error = 0., None, None, None
        attempted = False
        for attempt in range(3):
            accounted = False
            try:
                rate_slot(settings["max_rpm"], deadline)
                if datetime.utcnow().date() != now.date():
                    raise RuntimeError("UTC budget admission day ended")
                attempted = True
                response = client.chat.completions.create(
                    model=legacy.OPENAI_MODEL, temperature=legacy.AI_TEMPERATURE, max_tokens=2000,
                    messages=[{"role": "system", "content": legacy.SYSTEM_PROMPT},
                              {"role": "user", "content": f"Analyze this news event:\n\n{input_text}"}])
                usage = response.usage.model_dump() if response.usage else None
                amount += ((usage["prompt_tokens"]*.4+usage["completion_tokens"]*1.6)/1e6
                           if usage else row["request_bound_usd"])
                accounted = True
                ok, result, error = legacy.parse_ai_response(response.choices[0].message.content or "")
                if not ok:
                    result = None
                break
            except Exception as exc:
                code = getattr(exc, "status_code", None)
                # Explicit HTTP rejections generated no output. Timeout/network ambiguity stays charged upper.
                if attempted and not accounted and not (code is not None and 400 <= code < 500 and code != 408):
                    amount += row["request_bound_usd"]
                error = f"{type(exc).__name__}: request failed"
                if isinstance(exc, RuntimeError) or (code is not None and 400 <= code < 500 and code != 429):
                    break
                if attempt < 2:
                    time.sleep(2**attempt)
            finally:
                attempted = False
        charged += amount
        remaining = max(0., remaining-3*row["request_bound_usd"])
        metadata = {"usage": usage, "observed_or_upper_cost_usd": amount,
                    "budget_run_id": id_, "lease_until": datetime.utcnow().isoformat()}
        if result is not None:
            result["_risk_pipeline_v2"] = metadata
            legacy.save_ai_result(row["id"], result["summary"], result, legacy.OPENAI_MODEL)
            successes += 1
        else:
            legacy.save_ai_error(row["id"], error or "V2 processing failed")
            with get_cursor() as c:
                c.execute("""UPDATE events SET ai_impact_json=jsonb_set(ai_impact_json,
                    '{_risk_pipeline_v2}',%s::jsonb,true) WHERE id=%s""", (json.dumps(metadata), row["id"]))
            failures += 1
        settle(id_, charged, remaining)
        logger.info("RISK_PIPELINE_V2 event_id=%s success=%s cost_or_upper_usd=%.6f",
                    row["id"], result is not None, amount)
    settle(id_, charged, 0., True)
    if successes < min(settings["batch_size"], len(rows)):
        logger.error("INTERNAL ADMIN ALERT: V2 throughput shortfall success=%s target=%s", successes, len(rows))
    logger.info("RISK_PIPELINE_V2 throughput success=%s failure=%s required_batch=%s capacity_ratio=%s",
                successes, failures, settings["batch_size"], settings["capacity_ratio"])
    return successes, failures
