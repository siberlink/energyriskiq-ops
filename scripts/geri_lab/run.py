"""Run: python -m scripts.geri_lab.run --variant baseline --start YYYY-MM-DD --end YYYY-MM-DD"""
import argparse
from dataclasses import asdict
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import time

from .acceptance import replication, render_acceptance
from .data import fingerprints, load, readonly_snapshot
from .replay import replay, write_series
from .scorecard import scorecard, write_scorecard
from .variants import get_variant
from .relevance_filters import context_for, sanity_lists


ROOT = Path(__file__).resolve().parents[2] / "reports" / "geri_lab"


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, default=str, allow_nan=False) + "\n")


def execute(variant, start, end):
    began = time.perf_counter()
    if start > end:
        raise ValueError("--start must not be after --end.")
    directory = ROOT / variant.name
    directory.mkdir(parents=True, exist_ok=True)
    with readonly_snapshot() as cursor:
        before = fingerprints(cursor)
        data = load(cursor, start, end, variant)
        filter_context = context_for(variant, data["alerts"])
        series = replay(data["alerts"], start, end, variant, data["warmup"],
                        data["health"], filter_context)
        evaluation = scorecard(series, data["markets"], variant,
                               sanity_lists(data["alerts"], variant, filter_context))
        replica = replication(series, data["published"])
        sensitivity = {"status": "not_applicable_to_this_variant_or_range"}
        if variant.name == "baseline" and start <= date(2026, 10, 22) <= end:
            other = get_variant("baseline_91")
            # Load only the extra warmup day's alerts if needed. Never reuse the
            # 90-day normalization series to stand in for a 91-day replay.
            other_data = load(cursor, start, end, other)
            other_series = replay(other_data["alerts"], start, end, other, other_data["warmup"], other_data["health"])
            other_directory = ROOT / other.name
            other_directory.mkdir(parents=True, exist_ok=True)
            write_series(other_directory / "series.csv", other_series)
            write_scorecard(other_directory, scorecard(other_series, data["markets"], other))
            write_json(other_directory / "manifest.json", {
                "variant": asdict(other), "warmup_start": other_data["warmup"],
                "alert_sha256": other_data["alert_sha256"],
                "generated_by_baseline_sensitivity": True,
            })
            target = next(row for row in other_series if row["date"] == "2026-10-22")
            july = next((row for row in other_series if row["date"] == "2026-07-23"), None)
            sensitivity = {
                "date": "2026-10-22", "window_days": 91, "geri": target["geri"],
                "expected_approximately": 25, "tolerance_points": 1,
                "passed": abs(target["geri"] - 25) <= 1,
                "july_23_replayed_raw_H": july["raw_H"] if july else None,
            }
    # Fresh observation, so concurrent writes aren't hidden by snapshot isolation.
    with readonly_snapshot() as cursor:
        after = fingerprints(cursor)
    write_series(directory / "series.csv", series)
    write_scorecard(directory, evaluation)
    elapsed = time.perf_counter() - began
    full_range = (start, end) == (date(2026, 1, 14), date(2026, 10, 22))
    result = {
        "replication": replica,
        "sensitivity": sensitivity,
        "isolation": {
            "transaction_read_only": "on", "isolation_level": "REPEATABLE READ",
            "server_enforced_no_data_writes": True,
            "before": before, "after": after,
            "fingerprints_unchanged": before == after,
            "intelligence_daily_unchanged": before["intel_indices_daily"] == after["intel_indices_daily"],
        },
        "runtime_seconds": elapsed,
        "runtime_under_5_minutes": elapsed < 300,
        "all_acceptance_passed": bool(
            full_range and variant.name == "baseline" and replica["replication_passed"]
            and replica["known_values_passed"] and sensitivity.get("passed")
            and before["intel_indices_daily"] == after["intel_indices_daily"] and elapsed < 300
        ),
    }
    write_json(directory / "acceptance.json", result)
    (directory / "acceptance.md").write_text(render_acceptance(result))
    code_hashes = {}
    project = ROOT.parents[1]
    for name in ("compute.py", "normalize.py", "service.py", "repo.py", "types.py"):
        path = project / "src" / "geri" / name
        code_hashes[str(path.relative_to(project))] = hashlib.sha256(path.read_bytes()).hexdigest()
    write_json(directory / "manifest.json", {
        "generated_at_utc": datetime.now(timezone.utc),
        "variant": asdict(variant), "start": start, "end": end,
        "warmup_start": data["warmup"], "alert_sha256": data["alert_sha256"],
        "source_code_sha256": code_hashes,
        "historical_baseline": "only previously replayed variant raw components",
    })
    print(json.dumps({
        "output": str(directory.relative_to(project)),
        "within_one_rate": replica["within_one_rate"],
        "exact_days": replica["exact_days"],
        "october_exact_days": replica["october_exact_days"],
        "mismatches_gt_2": len(replica["mismatches_gt_2"]),
        "sensitivity": sensitivity, "runtime_seconds": elapsed,
        "fingerprints_unchanged": before == after,
        "all_acceptance_passed": result["all_acceptance_passed"],
    }, indent=2))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", default="baseline")
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    args = parser.parse_args()
    try:
        result = execute(get_variant(args.variant), args.start, args.end)
    except (ValueError, NotImplementedError) as error:
        parser.error(str(error))
    # Reports remain available on a failed historical acceptance test.
    return 0 if result["all_acceptance_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
