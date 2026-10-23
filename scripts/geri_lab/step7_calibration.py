"""Frozen Step 6 reconstruction -> provenance-bearing window-specific floors."""
from collections import defaultdict
from datetime import date, datetime, timedelta
import csv
import hashlib
import json
from pathlib import Path

from src.risk.pipeline_v2_core import REGIONS, ASSETS, event_weight


def percentile(values, q):
    ordered = sorted(values)
    if not ordered or not 0 <= q <= 1:
        raise ValueError("Nonempty sample and percentile in [0,1] required")
    position = (len(ordered)-1)*q
    lo = int(position)
    return ordered[lo]+(ordered[min(lo+1,len(ordered)-1)]-ordered[lo])*(position-lo)


def build(root, q=.90):
    source = root / "reports/geri_lab/step6/scored_event_snapshot.json"
    coverage_file = root / "reports/geri_lab/step6/daily_counterfactual_coverage.csv"
    coverage = list(csv.DictReader(coverage_file.open()))
    # Step 6 names this fraction explicitly; fail instead of guessing a column.
    fraction_key = next(k for k in coverage[0] if "coverage" in k and "reliable" not in k)
    days = [date.fromisoformat(r["date"]) for r in coverage
            if date(2026,1,14) <= date.fromisoformat(r["date"]) <= date(2026,6,3)
            and r[fraction_key] not in ("",None)
            and float(r[fraction_key]) >= .5]
    if not days:
        raise ValueError("No eligible calibration dates")
    totals = defaultdict(lambda: defaultdict(float))
    for row in json.loads(source.read_text()):
        day = date.fromisoformat(row["inserted_at"][:10])
        weight = event_weight(row, True)
        totals["region:"+row["region"]][day] += weight
        if row["region"] == "Europe":
            for asset, value in (row.get("asset_impacts") or {}).items():
                if asset in ASSETS and isinstance(value, dict):
                    confidence = value.get("confidence")
                    totals["asset:"+asset][day] += weight*(.5 if confidence is None else float(confidence))
    distributions = {}
    for entity in [*("region:"+r for r in REGIONS), *("asset:"+a for a in ASSETS)]:
        for window in (7,30):
            distributions[f"{entity}:{window}"] = [
                sum(totals[entity].get(day-timedelta(days=i), 0.) for i in range(window))
                for day in days]
    return {
        "percentile": q, "period": ["2026-01-14","2026-06-03"],
        "coverage_rule": f"{fraction_key} >= 0.50", "eligible_days": len(days),
        "eligible_dates": [str(d) for d in days],
        "source": str(source.relative_to(root)),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "coverage_sha256": hashlib.sha256(coverage_file.read_bytes()).hexdigest(),
        "zero_floor_policy": "zero raw and zero maximum -> score 0, not fabricated positive floor",
        "interpretation": "hindsight timely reconstruction; not genuine point-in-time history",
        "floors": {key: percentile(values,q) for key, values in distributions.items()},
        "distributions": distributions,
    }
