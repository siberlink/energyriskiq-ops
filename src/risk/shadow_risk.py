"""Isolated V2 risk outputs. No alert, published-index, or legacy-table writes."""
from collections import defaultdict
from datetime import datetime, timedelta
import json

from src.db.db import get_cursor
from .pipeline_v2_core import ASSETS, REGIONS, event_weight, mode


def window_sums(rows, now):
    result = {}
    for window in (7, 30):
        active = [r for r in rows if now-timedelta(days=window) <= r["inserted_at"] <= now]
        for region in REGIONS:
            result[f"region:{region}:{window}"] = sum(
                r["weighted_score"] for r in active if r["region"] == region)
        for asset in ASSETS:
            value = 0.
            for r in active:
                impact = (r.get("asset_impacts") or {}).get(asset)
                if r["region"] == "Europe" and isinstance(impact, dict):
                    confidence = impact.get("confidence")
                    value += r["weighted_score"] * (.5 if confidence is None else float(confidence))
            result[f"asset:{asset}:{window}"] = value
    return result


def calibrated_scores(raw, previous_max, floors):
    if set(raw) != set(floors):
        raise ValueError("Missing or unexpected calibrated region/asset/window floor")
    output = {}
    for key, value in raw.items():
        floor = float(floors[key])
        if floor < 0:
            raise ValueError("Reference floors cannot be negative")
        denominator = max(float(previous_max.get(key, 0)), value, floor)
        output[key] = {
            "raw": value, "reference_floor": floor, "denominator": denominator,
            "score": min(100., 100 * value / denominator) if denominator else 0.,
        }
    return output


def saturation(scores, previous=None):
    from src.alerts.alerts_engine_v2 import DEFAULT_THRESHOLD
    previous = previous or {}
    result = {}
    for kind in ("region", "asset"):
        for window in (7, 30):
            values = [v["score"] for k, v in scores.items()
                      if k.startswith(kind+":") and k.endswith(":"+str(window))]
            result[f"{kind}_{window}d"] = {
                "count": len(values),
                "share_ge90": sum(v >= 90 for v in values)/len(values),
                "share_at100": sum(v >= 100-1e-8 for v in values)/len(values),
                "threshold": DEFAULT_THRESHOLD,
                "simulated_threshold_candidates": sum(v >= DEFAULT_THRESHOLD for v in values),
                "simulated_severity5_ge90": sum(v >= 90 for v in values),
            }
    # Existing generators use 7d scores only; global is not a generated region.
    region_keys = [k for k in scores if k.startswith("region:") and k.endswith(":7")
                   and k != "region:global:7"]
    asset_keys = [k for k in scores if k.startswith("asset:") and k.endswith(":7")]
    result["simulated_daily_alerts"] = {
        "regional":sum(scores[k]["score"]>=DEFAULT_THRESHOLD or
                       (previous.get(k,0)>0 and scores[k]["score"]>=previous[k]*1.2)
                       for k in region_keys),
        "asset_europe":sum(scores[k]["score"]>=DEFAULT_THRESHOLD for k in asset_keys),
        "regional_change_threshold_pct":20,
        "assumes_no_existing_daily_fingerprint":True,
        "created":0,
    }
    return result


def run():
    if mode() != "shadow":
        raise RuntimeError("Shadow risk writer requires shadow mode")
    from .risk_engine import extract_avg_confidence
    now = datetime.utcnow()
    with get_cursor() as c:
        c.execute("SELECT calibration FROM risk_pipeline_v2_control WHERE singleton AND mode='shadow'")
        control = c.fetchone()
        if not control:
            raise RuntimeError("Shadow activation/control row missing")
        floors = control["calibration"]["floors"]
        c.execute("""SELECT id AS event_id,region,category,severity_score AS base_severity,
            ai_impact_json,inserted_at FROM events e
            WHERE processed AND ai_impact_json IS NOT NULL
            AND inserted_at BETWEEN %s-interval '7 days' AND %s
            AND NOT EXISTS(SELECT 1 FROM risk_events_v2 r WHERE r.event_id=e.id)
            ORDER BY inserted_at DESC,id DESC""", (now, now))
        fresh = [dict(r) for r in c.fetchall()]
        for row in fresh:
            confidence = extract_avg_confidence(row["ai_impact_json"])
            weight = event_weight({**row, "ai_confidence": confidence}, True)
            c.execute("""INSERT INTO risk_events_v2
                (event_id,region,category,base_severity,ai_confidence,weighted_score,created_at)
                VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(event_id) DO NOTHING""",
                      (row["event_id"], row["region"], row["category"], row["base_severity"],
                       confidence, weight, now))
        c.execute("""SELECT r.event_id,e.inserted_at,r.region,r.weighted_score,
            e.ai_impact_json->'impact' AS asset_impacts
            FROM risk_events_v2 r JOIN events e ON e.id=r.event_id
            WHERE e.inserted_at BETWEEN %s-interval '210 days' AND %s""", (now, now))
        rows = [dict(r) for r in c.fetchall()]
        raw = window_sums(rows, now)
        # Prior daily raw sums are saved on our own monitoring rows, not normalized
        # legacy scores. Region lookback 180d; asset lookback 90d.
        c.execute("""SELECT observed_at,payload FROM risk_pipeline_v2_monitor
            WHERE checkpoint='risk_panel' AND observed_at>=NOW()-interval '180 days'""")
        previous_max = defaultdict(float)
        previous_day = {}
        latest_previous_time = None
        for record in c.fetchall():
            if record["observed_at"].date() < now.date() and (
                    latest_previous_time is None or record["observed_at"]>latest_previous_time):
                previous_day = {key: v["score"] for key,v in record["payload"].get("scores",{}).items()}
                latest_previous_time = record["observed_at"]
            for key, value in record["payload"].get("scores", {}).items():
                if key.startswith("asset:") and record["observed_at"].replace(tzinfo=None) < now-timedelta(days=90):
                    continue
                previous_max[key] = max(previous_max[key], value["raw"])
        scores = calibrated_scores(raw, previous_max, floors)
        for region in REGIONS:
            current = sum(r["weighted_score"] for r in rows if r["region"] == region and
                          r["inserted_at"] >= now-timedelta(days=7))
            previous = sum(r["weighted_score"] for r in rows if r["region"] == region and
                           now-timedelta(days=14) <= r["inserted_at"] < now-timedelta(days=7))
            change = (current-previous)/previous*100 if previous else 0
            trend = "rising" if change >= 10 else "falling" if change <= -10 else "stable"
            for window in (7, 30):
                c.execute("""INSERT INTO risk_indices_v2
                    (region,window_days,risk_score,trend,calculated_at) VALUES(%s,%s,%s,%s,%s)""",
                          (region, window, scores[f"region:{region}:{window}"]["score"], trend, now))
        for asset in ASSETS:
            for window in (7, 30):
                direction_values = defaultdict(float)
                for r in rows:
                    impact = (r.get("asset_impacts") or {}).get(asset)
                    if r["region"] == "Europe" and r["inserted_at"] >= now-timedelta(days=window) and isinstance(impact, dict):
                        direction_values[impact.get("direction", "neutral")] += r["weighted_score"]
                direction = max(direction_values, key=direction_values.get) if direction_values else "neutral"
                c.execute("""INSERT INTO asset_risk_v2
                    (asset,region,window_days,risk_score,direction,calculated_at)
                    VALUES(%s,'Europe',%s,%s,%s,%s)""",
                          (asset, window, scores[f"asset:{asset}:{window}"]["score"], direction, now))
        payload = {"scores": scores, "saturation": saturation(scores,previous_day), "scored": len(fresh),
                   "simulated_only": True, "customer_alerts_created": 0}
        c.execute("""INSERT INTO risk_pipeline_v2_monitor(checkpoint,payload)
            VALUES('risk_panel',%s::jsonb)""", (json.dumps(payload),))
    return len(fresh)
