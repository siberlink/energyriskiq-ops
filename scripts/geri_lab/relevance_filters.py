"""Offline selection only; never call an LLM while replaying a variant."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "reports" / "geri_lab"


def context_for(variant, rows):
    if variant.pillar_mode != "none" or variant.label_model == "gpt41":
        from .step5_pillars import context_for as restored_context
        return restored_context(variant, rows)
    if variant.relevance_rule != "none" or variant.dedup_mode != "none":
        from .step4_data import cached_context
        return cached_context(variant, rows)
    if variant.relevance_filter == "none":
        return {}
    if variant.relevance_filter == "cheap":
        evaluation = json.loads((ROOT / "gold_set/filter_evaluation.json").read_text())
        return {"cheap_conditions": evaluation["cheap_selected_conditions"]}
    from .relevance import build_prompts, MODEL
    cached = {}
    with (ROOT / "cache/relevance_labels.jsonl").open() as stream:
        for line in stream:
            item = json.loads(line)
            if item["model"] != MODEL:
                raise ValueError("Cache model mismatch; replay refuses mixed-model labels.")
            cached[(item["alert_id"], item["prompt_hash"])] = item["labels"]
    labels = {}
    for row in rows:
        if row["alert_type"] != "HIGH_IMPACT_EVENT":
            continue
        converted = {**row, "alert_body": row.get("body")}
        key = (row["id"], build_prompts(converted)[1])
        if key not in cached:
            raise ValueError(f"Missing exact input/prompt label for alert {row['id']}")
        labels[row["id"]] = cached[key]
    return {"labels": labels}


def target(label):
    return label["relevance"] == 2 or (
        label["relevance"] == 1 and label["materiality"] in ("medium", "high")
    )


def keep(row, variant, context=None):
    if row["alert_type"] != "HIGH_IMPACT_EVENT":
        return True
    confidence = row.get("risk_score", row.get("confidence"))
    if variant.min_confidence is not None and (
        confidence is None or float(confidence) < variant.min_confidence
    ):
        return False
    if variant.require_geri_driver and row.get("is_geri_driver") is not True:
        return False
    context = context or {}
    if variant.relevance_rule != "none":
        from .storyline import rule_pass
        if row["id"] not in context.get("labels", {}):
            raise ValueError(f"Missing label for alert {row['id']}")
        if not rule_pass(context["labels"][row["id"]], variant.relevance_rule):
            return False
    if variant.relevance_filter == "none":
        return True
    if variant.relevance_filter == "llm":
        if row["id"] not in context.get("labels", {}):
            raise ValueError(f"Missing LLM label for alert {row['id']}")
        return target(context["labels"][row["id"]])
    if "cheap_conditions" not in context:
        raise ValueError("Missing training-selected cheap rule.")
    for condition in context["cheap_conditions"]:
        if condition in ("F1", "F2"):
            floor = .05 if condition == "F1" else .10
            if confidence is None or float(confidence) < floor:
                return False
        elif condition == "F3":
            if row.get("is_geri_driver") is not True:
                return False
        elif condition.startswith(("F4@", "F5@")):
            field = "market_relevance" if condition.startswith("F4") else "energy_relevance"
            value = row.get(field)
            if value is None or float(value) < float(condition.split("@")[1]):
                return False
        else:
            raise ValueError(f"Unsupported cheap condition {condition!r}")
    return True


def sanity_lists(rows, variant, context):
    from src.geri.compute import compute_components
    from .replay import as_alert
    output = {}
    for day in ("2026-10-22", "2026-07-23"):
        selected = [
            row for row in rows if row["alert_type"] == "HIGH_IMPACT_EVENT"
            and row["created_at"].date().isoformat() == day
        ]
        groups = {"kept": [], "dropped": []}
        for row in selected:
            contribution = compute_components([as_alert(row)]).high_impact_score
            label = "kept" if keep(row, variant, context) else "dropped"
            groups[label].append({
                "alert_id": row["id"], "headline": row["headline"],
                "source": row.get("source"),
                "confidence": float(row["risk_score"]) if row["risk_score"] is not None else None,
                "is_geri_driver": row.get("is_geri_driver"),
                "market_relevance": row.get("market_relevance"),
                "single_alert_raw_H": contribution,
            })
        output[day] = {
            group: sorted(items, key=lambda r: (-r["single_alert_raw_H"], r["alert_id"]))[:15]
            for group, items in groups.items()
        }
    return output
