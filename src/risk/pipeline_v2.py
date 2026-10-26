"""Disabled-by-default pipeline entry points, read-only monitoring and dry-run."""
from datetime import datetime, timedelta
import json
import logging

from src.db.db import get_cursor
from .pipeline_v2_core import enabled, panels, event_weight, REGIONS, ASSETS

logger = logging.getLogger(__name__)


def metrics(cursor, now):
    cursor.execute("""SELECT
        count(*) FILTER (WHERE NOT processed AND COALESCE(
            ai_impact_json->'_risk_pipeline_v2'->>'status','')<>'skipped_stale') AS waiting_all,
        count(*) FILTER (WHERE NOT processed AND ai_attempts<3 AND COALESCE(
            ai_impact_json->'_risk_pipeline_v2'->>'status','')<>'skipped_stale') AS waiting_retryable,
        count(*) FILTER (WHERE NOT processed AND ai_attempts>=3) AS attempts_exhausted,
        count(*) FILTER (WHERE NOT processed AND inserted_at >= %s-interval '7 days') AS waiting_last7d,
        count(*) FILTER (WHERE NOT processed AND ai_attempts<3
            AND inserted_at >= %s-interval '7 days') AS waiting_last7d_retryable,
        min(inserted_at) FILTER (WHERE NOT processed) AS oldest_waiting,
        min(inserted_at) FILTER (WHERE NOT processed AND ai_attempts<3) AS oldest_retryable,
        count(*) FILTER (WHERE inserted_at>=date_trunc('day',%s::timestamp)-interval '28 days'
                         AND inserted_at<date_trunc('day',%s::timestamp))/28.0 AS average_daily_inflow_28d
        FROM events""", (now, now, now, now))
    value = dict(cursor.fetchone())
    # Actual delivered worker invocations, not the cron's intended 24/day.
    # Historical observations are imported from verified Actions run metadata.
    cursor.execute("""SELECT count(*) AS delivered_runs_3d FROM job_runs
        WHERE job_name='shadow_enrichment_delivery'
          AND started_at >= (%s::timestamp AT TIME ZONE 'UTC')-interval '3 days'
          AND status IN ('running','success','error','observed_success')""", (now,))
    value.update(dict(cursor.fetchone()))
    cursor.execute("""SELECT count(*) AS fresh_waiting FROM events
        WHERE NOT processed AND ai_attempts<3 AND inserted_at >=
        (SELECT activated_at FROM risk_pipeline_v2_control WHERE singleton)""")
    value.update(dict(cursor.fetchone()))
    cursor.execute("""SELECT percentile_cont(.5) WITHIN GROUP
        (ORDER BY EXTRACT(EPOCH FROM (r.created_at-e.inserted_at))/3600) AS median_scoring_delay_hours
        FROM risk_events r JOIN events e ON e.id=r.event_id WHERE r.created_at >= %s-interval '24 hours'""", (now,))
    value.update(dict(cursor.fetchone()))
    value["oldest_waiting_age_hours"] = (
        (now-value["oldest_waiting"]).total_seconds()/3600 if value["oldest_waiting"] else None)
    return value


def warning_reasons(value):
    reasons = []
    if value.get("median_scoring_delay_hours") is not None and value["median_scoring_delay_hours"] > 6:
        reasons.append("median scoring delay exceeds 6 hours")
    if value["waiting_all"] > float(value["average_daily_inflow_28d"]):
        reasons.append("queue exceeds 24 hours of average inflow")
    return reasons


def internal_alert(value):
    """Same internal operations channel as the existing GERI watchdog; no delivery."""
    reasons = warning_reasons(value)
    if not reasons:
        return
    from src.geri.job_health import start_run, finish_run
    now = datetime.utcnow()
    id_ = start_run(now.date(), "risk_pipeline_v2_admin_alert",
                    f"risk-pipeline-admin:{now:%Y-%m-%d-%H}")
    if id_:
        message = "; ".join(reasons)
        finish_run(id_, "error", message)
        logger.critical("INTERNAL ADMIN ALERT: Risk pipeline: %s", message)


def status():
    with get_cursor() as c:
        value = metrics(c, datetime.utcnow())
        c.execute("""SELECT started_at,status,error FROM job_runs
            WHERE job_name='risk_pipeline_v2_admin_alert' ORDER BY started_at DESC LIMIT 1""")
        alert = c.fetchone()
    from .pipeline_v2_core import mode
    from .shadow_monitor import snapshot
    return {"enabled": enabled(), "mode": mode(), "shadow": snapshot(),
            **value, "warning_reasons": warning_reasons(value),
            "internal_admin_alert": dict(alert) if alert else None}


def load_risk_rows(cursor, now):
    cursor.execute("""SELECT r.event_id,e.inserted_at,r.region,r.category,r.base_severity,
        r.ai_confidence,r.weighted_score,e.ai_impact_json->'impact' AS asset_impacts
        FROM risk_events r JOIN events e ON e.id=r.event_id
        WHERE e.inserted_at >= %s-interval '210 days' AND e.inserted_at <= %s
        AND r.created_at<=%s ORDER BY e.inserted_at,r.event_id""", (now, now, now))
    return [dict(r) for r in cursor.fetchall()]


def today_panel(rows, now):
    """Match elapsed 7/30d numerator cutoffs; rolling maxima use causal daily buckets."""
    rows = [row for row in rows if row["inserted_at"] <= now]
    result = panels(rows, [now.date()], zero_age=False)[now.date().isoformat()]
    # Denominator first-day clipping matches legacy NOW()-lookback boundaries.
    regional_rows = [r for r in rows if r["inserted_at"] >= now-timedelta(days=180)]
    asset_rows = [r for r in rows if r["inserted_at"] >= now-timedelta(days=90)]
    def maximum(selected, region, window, asset=None):
        from collections import defaultdict
        daily = defaultdict(float)
        for row in selected:
            if row["region"] != region:
                continue
            value = 1.
            if asset:
                impact = (row.get("asset_impacts") or {}).get(asset)
                if not isinstance(impact, dict):
                    continue
                value = .5 if impact.get("confidence") is None else float(impact["confidence"])
            daily[row["inserted_at"].date()] += row["weighted_score"]*value
        return max(1., max((sum(value for day, value in daily.items()
                                 if start <= day < start+timedelta(days=window))
                            for start in daily), default=0.))
    regional_max = {f"{region}_{window}": maximum(regional_rows, region, window)
                    for region in REGIONS for window in (7, 30)}
    asset_max = {asset: maximum(asset_rows, "Europe", 1, asset) for asset in ASSETS}
    result["denominators"].update(regional_max)
    result["denominators"].update(asset_max)
    for window in (7, 30):
        active = [r for r in rows if r["inserted_at"] >= now-timedelta(days=window)]
        for region in REGIONS:
            raw = sum(r["weighted_score"] for r in active if r["region"] == region)
            result["regional"][region][str(window)] = min(100., 100*raw/regional_max[f"{region}_{window}"])
        for asset in ASSETS:
            raw = 0.
            for row in active:
                value = (row.get("asset_impacts") or {}).get(asset)
                if row["region"] == "Europe" and isinstance(value, dict):
                    confidence = value.get("confidence")
                    raw += row["weighted_score"] * (.5 if confidence is None else float(confidence))
            result["asset"][asset][str(window)] = min(100., 100*raw/asset_max[asset])
    return result


def run_risk():
    if not enabled():
        raise RuntimeError("Risk pipeline V2 is disabled")
    from .pipeline_v2_core import mode
    if mode() == "shadow":
        from .shadow_risk import run
        return run()
    from .risk_engine import insert_risk_event, save_risk_index, save_asset_risk, get_asset_directions
    now = datetime.utcnow()
    with get_cursor() as c:
        c.execute("""SELECT e.id AS event_id,e.region,e.category,e.severity_score AS base_severity,
            e.ai_impact_json,e.inserted_at FROM events e WHERE e.processed
            AND e.ai_impact_json IS NOT NULL AND e.inserted_at BETWEEN %s-interval '7 days' AND %s
            AND NOT EXISTS(SELECT 1 FROM risk_events r WHERE r.event_id=e.id)
            ORDER BY e.inserted_at DESC,e.id DESC""", (now, now))
        fresh = [dict(r) for r in c.fetchall()]
    from .risk_engine import extract_avg_confidence
    for row in fresh:
        confidence = extract_avg_confidence(row["ai_impact_json"])
        weight = event_weight({**row, "ai_confidence": confidence}, True)
        insert_risk_event(row["event_id"], row["region"], row["category"], row["base_severity"], confidence, weight)
    now = datetime.utcnow()
    with get_cursor() as c:
        stored_rows = load_risk_rows(c, now)
        values = today_panel(stored_rows, now)
        health = metrics(c, now)
    for region in REGIONS:
        previous = sum(r["weighted_score"] for r in stored_rows if r["region"] == region
                       and now-timedelta(days=14) <= r["inserted_at"] < now-timedelta(days=7))
        current = sum(r["weighted_score"] for r in stored_rows if r["region"] == region
                      and r["inserted_at"] >= now-timedelta(days=7))
        change = (current-previous)/previous*100 if previous else 0
        trend = "rising" if change >= 10 else "falling" if change <= -10 else "stable"
        for window in (7, 30):
            save_risk_index(region, window, round(values["regional"][region][str(window)], 2), trend)
    directions = {window: get_asset_directions("Europe", window) for window in (7, 30)}
    for asset in ASSETS:
        for window in (7, 30):
            save_asset_risk(asset, "Europe", window, round(values["asset"][asset][str(window)], 2),
                            directions[window][asset]["direction"])
    internal_alert(health)
    logger.info("RISK_PIPELINE_V2 risk scored=%s, time_base=events.inserted_at", len(fresh))
    return len(fresh)
