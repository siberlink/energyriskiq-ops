"""Prospective, private GERI comparisons; writes ONLY its own shadow tables.

Historical normalization is seeded from each lab variant's own replay, never
from published components. Missing labels/health/pillars fail, never impute.
"""
from datetime import datetime, timedelta
import hashlib
import json
import os
import subprocess
import time

from src.db.db import get_cursor
from src.geri.compute import compute_components
from src.geri.normalize import normalize_components, calculate_geri_value
from src.geri.types import HistoricalBaseline, get_region_cluster, get_regional_weight
from scripts.geri_lab.replay import as_alert, RAW_FIELDS, NORMAL_FIELDS, PREFIXES
from scripts.geri_lab.relevance import SYSTEM_PROMPT, RESPONSE_FORMAT, _validate_label
from scripts.geri_lab.step5_data import opinion_text, label_key
from src.ai.shadow_budget import request,validation_failed

VARIANTS = ("prod", "integrity_v1", "rel41", "pillars_v2_continuous",
            "pillars_v2_continuous_rel41")
RAW_NAMES = ("H", "R", "A", "C")


def material_event(label):
    """Byte-for-byte rule semantics of Step 5's r_material_events (no dedup)."""
    return label["materiality"] in ("medium","high") and label["event_type"] in {
        "kinetic_attack","threat","sanctions_policy","supply_outage","diplomacy_deescalation"}


def code_sha():
    return os.environ.get("GITHUB_SHA") or subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True).strip()


def normalize(raw_components, history):
    baseline = HistoricalBaseline(days_count=len(history))
    for i, prefix in enumerate(PREFIXES):
        values = [r[i] for r in history]
        if values:
            setattr(baseline, prefix+"_min", min(values))
            setattr(baseline, prefix+"_max", max(values))
    normalize_components(raw_components, baseline)
    return calculate_geri_value(raw_components)


def label(row, client, deadline):
    """Same rubric, strict schema, exact input cache as the Step 5 GPT-4.1 arm."""
    data = {
        "headline": row["headline"], "alert_body": row.get("body") or "",
        "event_excerpt": row.get("event_excerpt") or "",
        "event_title": row.get("event_title") or "", "ai_summary": row.get("ai_summary") or "",
    }
    key = label_key(data)
    with get_cursor(commit=False) as c:
        c.execute("SELECT labels FROM risk_pipeline_v2_labels WHERE cache_key=%s", (key,))
        cached = c.fetchone()
    if cached:
        return cached["labels"]
    from src.ai.pipeline_v2_worker import rate_slot
    rate_slot(float(os.environ.get("RISK_PIPELINE_V2_MAX_RPM", "20")), deadline)
    raw, usage, amount, finish = request(
        client, "gpt-4.1", [{"role":"system","content":SYSTEM_PROMPT},
                          {"role":"user","content":opinion_text(data)}],
        200, "relevance41", row["id"], RESPONSE_FORMAT)
    try:
        if finish != "stop":
            raise ValueError("Incomplete GPT-4.1 classification; usage retained")
        labels = _validate_label(json.loads(raw))
    except (ValueError,TypeError,KeyError):
        validation_failed("relevance41",row["id"],"Invalid or incomplete label; usage retained")
        raise
    with get_cursor() as c:
        c.execute("""INSERT INTO risk_pipeline_v2_labels(cache_key,alert_id,labels,model,provenance)
            VALUES(%s,%s,%s::jsonb,'gpt-4.1',%s::jsonb) ON CONFLICT DO NOTHING""",
                  (key, row["id"], json.dumps(labels),
                   json.dumps({"usage":usage,"cost_usd":amount,"rubric":"Step5:r_material_events",
                               "input_sha256":key})))
    return labels


def continuous(c, day):
    cutoff = day+timedelta(days=1)
    c.execute("""SELECT DISTINCT ON(region) id,region,risk_score FROM risk_indices_v2
        WHERE window_days=7 AND calculated_at>=%s AND calculated_at<%s
        ORDER BY region,calculated_at DESC,id DESC""", (day, cutoff))
    regions = [dict(r) for r in c.fetchall()]
    c.execute("""SELECT DISTINCT ON(asset) id,asset,risk_score FROM asset_risk_v2
        WHERE window_days=7 AND region='Europe' AND calculated_at>=%s AND calculated_at<%s
        ORDER BY asset,calculated_at DESC,id DESC""", (day, cutoff))
    assets = [dict(r) for r in c.fetchall()]
    from src.risk.pipeline_v2_core import REGIONS, ASSETS
    if {r["region"] for r in regions} != set(REGIONS) or {r["asset"] for r in assets} != set(ASSETS):
        raise ValueError(f"Missing exact-date V2 risk inputs for {day}")
    weights = [get_regional_weight(get_region_cluster(r["region"], "", "")) for r in regions]
    r_value = sum(w*r["risk_score"] for w,r in zip(weights,regions))/sum(weights)
    a_value = sum(r["risk_score"] for r in assets)/4
    return r_value,a_value,{"regional_ids":[r["id"] for r in regions],
                            "asset_ids":[r["id"] for r in assets]}


def run(day=None):
    from src.risk.pipeline_v2_core import mode
    if mode() != "shadow":
        raise RuntimeError("Private GERI job requires shadow mode")
    with get_cursor(commit=False) as c:
        c.execute("SELECT * FROM risk_pipeline_v2_control WHERE singleton AND mode='shadow'")
        control = c.fetchone()
        if not control:
            raise RuntimeError("No active shadow control")
        # Never invent a published reference or compute an open UTC day.
        c.execute("""SELECT date,value,components,computed_at FROM intel_indices_daily
            WHERE index_id='global:geo_energy_risk' AND date>=%s AND date<%s
            AND (%s::date IS NULL OR date=%s::date) ORDER BY date""",
                  (control["start_date"], datetime.utcnow().date(), day, day))
        published = [dict(r) for r in c.fetchall()]
    results = []
    client = None
    for source in published:
        day = source["date"]
        with get_cursor(commit=False) as c:
            c.execute("SELECT variant FROM geri_shadow_daily WHERE index_date=%s", (day,))
            existing = {r["variant"] for r in c.fetchall()}
            if existing == set(VARIANTS):
                continue  # Immutable first observation; no retroactive selection.
            c.execute("""SELECT data_quality,alerts_ratio,events_ratio FROM geri_daily_health
                WHERE index_date=%s""", (day,))
            health = c.fetchone()
            if not health:
                raise ValueError(f"Missing production health for {day}")
            c.execute("""SELECT ae.id,ae.alert_type,ae.scope_region AS region,ae.severity,
                1.0 AS weight,ae.confidence AS risk_score,ae.created_at,ae.headline,ae.body,ae.raw_input,
                e.title AS event_title,e.raw_text AS event_excerpt,e.ai_summary
                FROM alert_events ae LEFT JOIN events e ON e.id=ae.driver_event_ids[1]
                WHERE ae.created_at>=%s AND ae.created_at<%s
                AND ae.alert_type IN ('HIGH_IMPACT_EVENT','REGIONAL_RISK_SPIKE','ASSET_RISK_ALERT')
                ORDER BY ae.created_at,ae.id""", (day,day+timedelta(days=1)))
            rows = [dict(r) for r in c.fetchall()]
            regional,asset,pillar_inputs = continuous(c,day)
        if client is None and any(r["alert_type"]=="HIGH_IMPACT_EVENT" for r in rows):
            from src.ai.ai_worker import get_openai_client
            # Existing credential route; no new key or secret handling.
            client = get_openai_client().with_options(timeout=60,max_retries=0)
        deadline = time.monotonic()+1200
        labels = {r["id"]:label(r,client,deadline) for r in rows if r["alert_type"]=="HIGH_IMPACT_EVENT"}
        for variant in VARIANTS:
            if variant in existing:
                continue
            selected = [r for r in rows if "rel41" not in variant or r["alert_type"]!="HIGH_IMPACT_EVENT"
                        or material_event(labels[r["id"]])]
            components = compute_components([as_alert(r) for r in selected])
            if "pillars_v2" in variant:
                components.regional_spike_score = regional
                components.asset_risk_score = asset
            with get_cursor(commit=False) as c:
                c.execute("""SELECT components FROM geri_shadow_daily
                    WHERE variant=%s AND index_date>=%s AND index_date<%s
                    AND inputs->>'data_quality'='OK' ORDER BY index_date""",
                          (variant,day-timedelta(days=90),day))
                history = [tuple(float(r["components"]["raw_"+p]) for p in RAW_NAMES)
                           for r in c.fetchall()] if variant!="prod" else []
            value = normalize(components,history)
            inputs = {"seed":False,"data_quality":health["data_quality"],
                      "alerts_ratio":health["alerts_ratio"],"events_ratio":health["events_ratio"],
                      "alert_ids":[r["id"] for r in selected],"normalization_rows":len(history),
                      "published_computed_at":str(source["computed_at"]),
                      "partial_activation_day":day==control["start_date"],
                      "v2_inputs":pillar_inputs if "pillars_v2" in variant else None,
                      "label_model":"gpt-4.1" if "rel41" in variant else None}
            output = {f"raw_{p}":getattr(components,f) for p,f in zip(RAW_NAMES,RAW_FIELDS)}
            output["raw_C"] = round(output["raw_C"],2)
            output.update({f"norm_{p}":getattr(components,f) for p,f in zip(RAW_NAMES,NORMAL_FIELDS)})
            if variant=="prod":
                value = source["value"]
                inputs["published_components"] = source["components"]
            with get_cursor() as c:
                c.execute("""INSERT INTO geri_shadow_daily
                    (index_date,variant,value,components,inputs,code_sha)
                    VALUES(%s,%s,%s,%s::jsonb,%s::jsonb,%s)
                    ON CONFLICT(index_date,variant) DO NOTHING""",
                          (day,variant,value,json.dumps(output),json.dumps(inputs),code_sha()))
            results.append({"date":str(day),"variant":variant,"value":value})
    return {"rows":results,"pending_first_closed_published_day":not published}
