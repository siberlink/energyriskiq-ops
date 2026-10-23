"""Step 4 lab-only relevance, chronological clustering and daily contribution rules."""
from collections import Counter, defaultdict
from datetime import timedelta
import math

import numpy as np

from src.geri.compute import get_effective_severity, get_effective_risk_score
from src.geri.types import get_region_cluster, get_regional_weight
from .relevance_filters import target

RULES = ("r_current", "r_material", "r_material_events", "r_high")
EVENTS = {"kinetic_attack", "threat", "sanctions_policy", "supply_outage",
          "diplomacy_deescalation"}


def rule_pass(label, rule):
    if rule == "none":
        return True
    if rule == "r_current":
        return target(label)
    if rule == "r_material":
        return label["materiality"] in ("medium", "high") and label["event_type"] != "market_commentary"
    if rule == "r_material_events":
        return label["materiality"] in ("medium", "high") and label["event_type"] in EVENTS
    if rule == "r_high":
        return label["materiality"] == "high"
    raise ValueError(f"Unknown relevance rule {rule!r}")


def region_of(row):
    cluster = get_region_cluster(row.get("region", row.get("alert_region")),
                                 row.get("headline") or "",
                                 row.get("body", row.get("alert_body")) or "")
    return cluster if cluster and cluster.lower() not in ("global", "unmapped", "unattributed") else None


def compatible(left, right):
    return left is None or right is None or left == right


def source_of(row):
    # Missing publishers are NOT counted as independent sources.
    return (row.get("source") or "").strip().casefold()


def corroboration(n_sources):
    return min(1.75, 1 + .25 * math.log(max(1, n_sources)))


def online_cluster(rows, vectors, threshold):
    """Online centroid assignment; never revisit old assignments or merge clusters."""
    if not 0 <= threshold <= 1 or len(rows) != len(vectors):
        raise ValueError("Invalid clustering inputs")
    if any((a["created_at"], a["id"]) > (b["created_at"], b["id"])
           for a, b in zip(rows, rows[1:])):
        raise ValueError("Clustering requires chronological (timestamp, id) order")
    vectors = np.asarray(vectors, dtype=np.float32)
    if not np.isfinite(vectors).all() or np.any(np.linalg.norm(vectors, axis=1) == 0):
        raise ValueError("Invalid embedding vectors")
    vectors = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
    stories, assignments, active = [], {}, []
    for row, vector in zip(rows, vectors):
        when, region = row["created_at"], region_of(row)
        active = [i for i in active if when - stories[i]["last_seen"] <= timedelta(hours=72)]
        eligible = [i for i in active if compatible(region, stories[i]["region_cluster"])]
        chosen, similarity = None, None
        if eligible:
            centroids = np.stack([stories[i]["centroid"] for i in eligible])
            scores = centroids @ vector
            best = int(np.argmax(scores))
            if float(scores[best]) >= threshold:
                chosen, similarity = eligible[best], float(scores[best])
        if chosen is None:
            chosen = len(stories)
            stories.append({
                "storyline_id": f"S{row['id']}", "first_seen": when, "last_seen": when,
                "region_cluster": region, "n_alerts": 0, "sources": set(), "member_ids": [],
                "headline": row.get("display_headline", row.get("headline")),
                "vector_sum": np.zeros_like(vector), "centroid": vector,
            })
            active.append(chosen)
        story = stories[chosen]
        story["vector_sum"] += vector
        story["centroid"] = story["vector_sum"] / np.linalg.norm(story["vector_sum"])
        story["last_seen"] = when
        story["n_alerts"] += 1
        story["member_ids"].append(row["id"])
        if source_of(row):
            story["sources"].add(source_of(row))
        if story["region_cluster"] is None and region is not None:
            story["region_cluster"] = region
        assignments[row["id"]] = {
            "storyline_id": story["storyline_id"], "similarity_at_assignment": similarity,
            "first_seen": story["first_seen"], "last_seen_as_of_assignment": when,
            "n_alerts_as_of_assignment": story["n_alerts"],
        }
    for story in stories:
        story["n_sources"] = len(story.pop("sources"))
        del story["centroid"], story["vector_sum"]
    return assignments, stories


def dedup_components(alerts, components, assignments, mode, source_map):
    """Change H and C only. C uses the SAME severity-weighted story contributions."""
    groups = defaultdict(list)
    for alert in alerts:
        if alert.alert_type == "HIGH_IMPACT_EVENT":
            if alert.id not in assignments:
                raise ValueError(f"Missing storyline assignment {alert.id}")
            groups[assignments[alert.id]["storyline_id"]].append(alert)
    region_totals = defaultdict(float)
    high_total = 0.
    for members in groups.values():
        def weight(alert):
            cluster = get_region_cluster(alert.region, alert.headline or "", alert.body or "")
            return get_effective_severity(alert) * (alert.weight or 1) * get_regional_weight(cluster)
        best = max(members, key=lambda alert: (weight(alert), -alert.id))
        value = weight(best)
        sources = {source_map.get(a.id, "") for a in members} - {""}
        if mode == "storyline_day_corroborated":
            value *= corroboration(len(sources))
        elif mode == "storyline_day_damp_log":
            value *= 1 + math.log(len(members))
        high_total += value
        region_totals[best.region or "Unknown"] += value
    # Regional/asset alerts retain their original weighted-risk contributions to C.
    for alert in alerts:
        if alert.alert_type != "HIGH_IMPACT_EVENT":
            cluster = get_region_cluster(alert.region, alert.headline or "", alert.body or "")
            region_totals[alert.region or "Unknown"] += (
                get_effective_risk_score(alert) * get_regional_weight(cluster))
    components.high_impact_score = high_total
    total = sum(region_totals.values())
    components.region_concentration_score_raw = 100 * max(region_totals.values()) / total if total else 0
    components.top_region_weight = components.region_concentration_score_raw / 100
    return components
