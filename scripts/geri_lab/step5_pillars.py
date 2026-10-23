"""Lab-only restored risk inputs. No production alert or scoring writes."""
from datetime import datetime, timedelta
import json
import math

from src.geri.types import get_region_cluster, get_regional_weight
from .step4_data import labels_for
from .step5_data import OUT, cached_labels, population
from .step5_diagnosis import original_risk


def context_for(variant, rows):
    context = {"labels": (cached_labels() if variant.label_model == "gpt41"
                          else labels_for(rows) if variant.relevance_rule != "none" else {})}
    if variant.pillar_mode != "none":
        context["asof_pillars"] = json.loads((OUT / "asof_pillars.json").read_text())
        context["regional_universe"] = json.loads((OUT / "diagnosis.json").read_text())["stored_regions"]
    return context


def continuous_values(day, context):
    data = context.get("asof_pillars", {}).get(day.isoformat())
    if not data:
        raise ValueError(f"Missing stored end-of-day pillar inputs {day}")
    if context.get("regional_universe") and set(data["regional"]) != set(context["regional_universe"]):
        raise ValueError(f"Incomplete fixed regional universe {day}")
    weighted, denominator = 0., 0.
    for region, item in data["regional"].items():
        multiplier = get_regional_weight(get_region_cluster(region, "", ""))
        if multiplier:
            value = item["risk"]
            if value is None or not math.isfinite(value) or not 0 <= value <= 100:
                raise ValueError("Invalid stored regional risk")
            weighted += multiplier * value
            denominator += multiplier
    assets = data["asset"]
    if set(assets) != {"oil", "gas", "freight", "fx"} or denominator == 0:
        raise ValueError(f"Incomplete continuous pillar inputs {day}")
    values = [item["risk"] for item in assets.values()]
    if not all(value is not None and math.isfinite(value) and 0 <= value <= 100 for value in values):
        raise ValueError("Invalid stored asset risk")
    return weighted / denominator, sum(values) / 4


def prepare_alerts(rows, variant, context):
    result, present = [], set()
    for row in rows:
        if row["alert_type"] not in ("REGIONAL_RISK_SPIKE", "ASSET_RISK_SPIKE", "ASSET_RISK_ALERT"):
            result.append(row)
            continue
        value = original_risk(row)
        if value is None:
            # Old backfill metadata lack the original score. Do not invent an
            # exact value from confidence, rounded text, or a later snapshot.
            # The driver exports this explicit strict-input exclusion cohort.
            continue
        raw = row.get("raw_input") or {}
        if isinstance(raw, str):
            raw = json.loads(raw)
        asset = raw.get("asset") if row["alert_type"] != "REGIONAL_RISK_SPIKE" else None
        kind = "regional" if asset is None else "asset"
        present.add((row["created_at"].date().isoformat(), row["region"], kind, asset))
        result.append({**row, "risk_score": value,
                       "alert_type": "ASSET_RISK_ALERT" if row["alert_type"] == "ASSET_RISK_SPIKE" else row["alert_type"],
                       "lab_source_alert_type": row["alert_type"]})
    if variant.pillar_mode == "fixed_alerts_sev4":
        synthetic_id = -1000000
        for day, data in sorted(context.get("asof_pillars", {}).items()):
            for kind, values in (("regional", data["regional"]), ("asset", data["asset"])):
                for name, item in sorted(values.items()):
                    region, asset = (name, None) if kind == "regional" else ("Europe", name)
                    key = (day, region, kind, asset)
                    value = item["risk"]
                    # Match the actual generator's supported regions; global isn't called.
                    if region not in ("Europe", "Middle East", "Black Sea", "Asia", "North Africa",
                                      "South America", "Russia", "North America"):
                        continue
                    if key in present or value < 80:
                        continue
                    synthetic_id -= 1
                    result.append({
                        "id": synthetic_id, "alert_type": ("REGIONAL_RISK_SPIKE" if kind == "regional"
                                                           else "ASSET_RISK_ALERT"),
                        "region": region, "severity": 5 if value >= 90 else 4,
                        "risk_score": value, "weight": 1.,
                        "created_at": datetime.fromisoformat(day) + timedelta(days=1, microseconds=-1),
                        "headline": f"Lab reconstructed {kind} end-of-day candidate",
                        "body": "", "raw_input": {}, "source": None,
                        "lab_reconstructed": True, "lab_snapshot_id": item["snapshot_id"],
                    })
    return result
