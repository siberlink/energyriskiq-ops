"""Resume exact GPT-4.1 labels via discounted OpenAI Batch, with a hard $15 ceiling."""
import argparse
import json
import time

from .relevance import SYSTEM_PROMPT, RESPONSE_FORMAT, _validate_label
from .step4_ai import append
from .step5_data import OUT, CACHE, capture, population, opinion_text, label_key, journal, dump

LABELS = CACHE / "step5_relevance41.jsonl"
STATE = OUT / "batch_state.json"
LIMIT = 14.99  # extra cent of margin below the user's hard $15 limit


def api():
    from openai import OpenAI
    # Existing configured provider access; no secret inspection or config changes.
    return OpenAI(base_url="https://api.openai.com/v1", timeout=120, max_retries=2)


def bound(row):
    # UTF-8 bytes upper-bound BPE tokens. Include literal schema and 256 envelope
    # tokens, plus the full requested output cap. Batch prices: $1/M in, $4/M out.
    text = SYSTEM_PROMPT + opinion_text(row) + json.dumps(RESPONSE_FORMAT, sort_keys=True)
    return ((len(text.encode()) + 256) + 200 * 4) / 1e6


def reuse():
    existing = {r["cache_key"] for r in journal(LABELS)}
    for record in journal(CACHE / "step4_second_opinion.jsonl"):
        if record["cache_key"] not in existing:
            append(LABELS, {**record, "reused_from_step4": True, "new_cost_usd": 0})
            existing.add(record["cache_key"])


def read_state():
    return json.loads(STATE.read_text()) if STATE.exists() else {"batches": [], "new_usage_usd": 0.,
                                                               "stop_reason": None}


def save_state(state):
    temporary = STATE.with_suffix(".tmp")
    dump(temporary, state)
    temporary.replace(STATE)


def remaining_inputs(rows, cached_keys, pending_keys):
    """Input identity, not alert identity: identical frozen prompts share a label."""
    unique = {}
    for row in rows:
        key = label_key(row)
        if key not in cached_keys and key not in pending_keys:
            unique.setdefault(key, row)
    return list(unique.values())


def cost_report(state):
    records = journal(LABELS)
    new = [r for r in records if not r.get("reused_from_step4")]
    by_key = {r["cache_key"]: r for r in records}
    assignments = [by_key[label_key(row)] for row in population() if label_key(row) in by_key]
    successful = sum(r["new_cost_usd"] for r in new)
    # State usage includes any generated but invalid outputs too.
    result = {"model": "gpt-4.1", "route": "existing direct OpenAI credential, Batch API",
              "batch_input_per_million_usd": 1, "batch_output_per_million_usd": 4,
              "reused_step4_labels": sum(bool(r.get("reused_from_step4")) for r in records),
              "reused_step4_label_assignments": sum(bool(r.get("reused_from_step4")) for r in assignments),
              "new_valid_labels": sum(not r.get("reused_from_step4") for r in assignments),
              "total_valid_labels": len(assignments), "unique_input_labels": len(records),
              "new_unique_input_labels": len(new),
              "identical_input_aliases": len(assignments) - len(records),
              "new_usage_usd": state["new_usage_usd"], "valid_response_cost_usd": successful,
              "inflight_reserved_upper_usd": sum(
                  b["reserved_upper_usd"] for b in state["batches"] if not b.get("terminal")),
              "hard_limit_usd": 15, "stop_reason": state["stop_reason"],
              "note": ("No prompt-cache discount assumed. Prior Step 4 costs excluded; not an invoice. "
                       "Exact duplicate inputs share one cached label; paid duplicate outputs remain in usage.")}
    dump(OUT / "label_costs.json", result)
    return result


def harvest(client, batch, local, rows_by_id, state):
    directory = OUT / "batches"
    directory.mkdir(exist_ok=True)
    local["status"] = batch.status
    local["request_counts"] = batch.request_counts.model_dump() if batch.request_counts else None
    if batch.status not in ("completed", "failed", "expired", "cancelled"):
        return
    if local.get("terminal"):
        return
    existing = {r["cache_key"] for r in journal(LABELS)}
    if batch.output_file_id:
        payload = client.files.content(batch.output_file_id).text
        (directory / f"{batch.id}_output.jsonl").write_text(payload)
        for line in payload.splitlines():
            item = json.loads(line)
            body = (item.get("response") or {}).get("body") or {}
            usage = body.get("usage")
            if not usage:
                continue
            amount = (usage.get("prompt_tokens", 0) + 4 * usage.get("completion_tokens", 0)) / 1e6
            state["new_usage_usd"] += amount
            # Every output, including invalid/length-limited ones, remains in raw evidence.
            id_ = int(item["custom_id"])
            row = rows_by_id[id_]
            key = label_key(row)
            try:
                raw = body["choices"][0]["message"]["content"]
                if body["choices"][0].get("finish_reason") != "stop":
                    raise ValueError("Incomplete classification")
                label = _validate_label(json.loads(raw))
            except (KeyError, ValueError, TypeError):
                continue
            if key not in existing:
                append(LABELS, {"id": id_, "cache_key": key, "model": "gpt-4.1",
                               "system_prompt": SYSTEM_PROMPT, "user_prompt": opinion_text(row),
                               "response_format": RESPONSE_FORMAT, "labels": label, "raw_output": raw,
                               "usage": usage, "batch_id": batch.id, "new_cost_usd": amount,
                               "provider_route": "OpenAI Batch"})
                existing.add(key)
    if batch.error_file_id:
        payload = client.files.content(batch.error_file_id).text
        (directory / f"{batch.id}_errors.jsonl").write_text(payload)
    if batch.errors:
        dump(directory / f"{batch.id}_validation_errors.json", batch.errors.model_dump())
    local["terminal"] = True
    local["status"] = batch.status
    if batch.status == "failed" and not batch.output_file_id:
        # Never spin on an unavailable Batch tier/quota: stop for an explicit report.
        state["stop_reason"] = "Batch validation/provider failure; see cached validation evidence"


def run(max_batches=2, batch_size=1000):
    capture()
    reuse()
    rows = population()
    rows_by_id = {r["alert_id"]: r for r in rows}
    client, state = api(), read_state()
    expected_keys = {label_key(row) for row in rows}
    print(f"Resuming {len(journal(LABELS))} unique exact inputs for {len(rows)} alerts", flush=True)
    while True:
        for local in state["batches"]:
            if not local.get("terminal"):
                harvest(client, client.batches.retrieve(local["id"]), local, rows_by_id, state)
                save_state(state)
        cached = {r["cache_key"] for r in journal(LABELS)}
        pending = {id_ for b in state["batches"] if not b.get("terminal") for id_ in b["alert_ids"]}
        pending_keys = {label_key(rows_by_id[id_]) for id_ in pending}
        remaining = remaining_inputs(rows, cached, pending_keys)
        if expected_keys.issubset(cached) and all(b.get("terminal") for b in state["batches"]):
            break
        active = [b for b in state["batches"] if not b.get("terminal")]
        if not state["stop_reason"]:
            for _ in range(max_batches - len(active)):
                reserved = sum(b["reserved_upper_usd"] for b in state["batches"] if not b.get("terminal"))
                available = LIMIT - state["new_usage_usd"] - reserved
                selected, reservation = [], 0.
                for row in remaining[:batch_size]:
                    amount = bound(row)
                    if reservation + amount > available:
                        break
                    selected.append(row)
                    reservation += amount
                if not selected:
                    if not pending and remaining:
                        state["stop_reason"] = "Hard budget: no additional request fits the remaining reservation"
                    break
                directory = OUT / "batches"
                directory.mkdir(exist_ok=True)
                path = directory / f"input_{len(state['batches']):03d}.jsonl"
                with path.open("w") as stream:
                    for row in selected:
                        request = {"custom_id": str(row["alert_id"]), "method": "POST",
                                   "url": "/v1/chat/completions", "body": {
                                       "model": "gpt-4.1", "temperature": 0, "max_tokens": 200,
                                       "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                                                    {"role": "user", "content": opinion_text(row)}],
                                       "response_format": RESPONSE_FORMAT}}
                        stream.write(json.dumps(request) + "\n")
                with path.open("rb") as stream:
                    uploaded = client.files.create(file=stream, purpose="batch")
                batch = client.batches.create(input_file_id=uploaded.id, endpoint="/v1/chat/completions",
                                               completion_window="24h", metadata={"experiment": "geri_lab_step5"})
                state["batches"].append({"id": batch.id, "input_file_id": uploaded.id,
                                        "alert_ids": [r["alert_id"] for r in selected],
                                        "reserved_upper_usd": reservation, "terminal": False, "status": batch.status})
                save_state(state)
                chosen = {r["alert_id"] for r in selected}
                remaining = [r for r in remaining if r["alert_id"] not in chosen]
                pending.update(chosen)
                print(f"Submitted {len(selected)} classifications; reserved upper ${reservation:.3f}", flush=True)
        save_state(state)
        report = cost_report(state)
        print(f"Cached {report['total_valid_labels']}/{len(rows)}; usage ${state['new_usage_usd']:.4f}; "
              f"active batches {sum(not b.get('terminal') for b in state['batches'])}", flush=True)
        if state["new_usage_usd"] > 15:
            raise RuntimeError("Budget violated unexpectedly; do not submit anything else")
        if state["stop_reason"] and all(b.get("terminal") for b in state["batches"]):
            raise RuntimeError(state["stop_reason"])
        time.sleep(60)
    cost_report(state)
    print("All 10,894 stronger-model labels cached", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--max-batches", type=int, default=2)
    args = parser.parse_args()
    run(args.max_batches, args.batch_size)
