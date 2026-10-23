"""Check the complete deliverable, then archive evidence with SHA-256 manifests."""
import csv
import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET
import zipfile

from .step5_data import OUT, LAB, CACHE, PROJECT, dump, cached_labels, population, protections
from .step5_run import NAMES
from .step5_report import build

ZIP = LAB / "GERI_Step5_Restore_Pillars_Full_Report.zip"


def rows(path):
    with path.open() as stream:
        return list(csv.DictReader(stream))


def validate():
    labels = cached_labels()
    checks = {"10894_exact_complete_stronger_labels": len(labels) == 10894}
    costs = json.loads((OUT / "label_costs.json").read_text())
    checks["400_cached_inputs_and_complete_new_label_assignments"] = (
        costs["reused_step4_labels"] == 400 and costs["total_valid_labels"] == 10894 and
        costs["new_valid_labels"] + costs["reused_step4_label_assignments"] == 10894)
    checks["new_spend_within_15_and_no_pending_reservations"] = (
        costs["new_usage_usd"] <= 15 and costs["inflight_reserved_upper_usd"] == 0)
    checks["all_eight_replays_282_days"] = all(
        len(rows(OUT / "variants" / name / "series.csv")) == 282 for name in NAMES)
    checks["full_regional_daily_grid"] = len(rows(OUT / "regional_daily_thresholds.csv")) == 5076
    checks["full_asset_daily_grid"] = len(rows(OUT / "asset_daily_thresholds.csv")) == 2256
    checks["no_storyline_dedup_in_candidates"] = all(
        json.loads((OUT / "variants" / name / "variant.json").read_text())["dedup_mode"] == "none"
        for name in NAMES if name != "damp_log")
    checks["bootstrap_all_cells_1000_valid_draws_and_correct_decisions"] = True
    checks["outcomes_end_within_splits"] = True
    bounds = {"full": ("2026-01-28", "2026-10-22"), "H1": ("2026-01-28", "2026-05-31"),
              "H2": ("2026-06-01", "2026-10-22")}
    for name in NAMES:
        result = json.loads((OUT / "variants" / name / "scorecard.json").read_text())
        guard = result["bootstrap_vs_integrity_v1"]
        cells = guard["cells"]
        deciders = [r for r in cells if r["split"] != "full" and
                    (r["market"], r["horizon_sessions"]) in (("Brent", 3), ("TTF", 1))]
        acceptable = len(deciders) == 4 and all(
            r["ci90_low"] is not None and r["ci90_low"] > -.05 for r in deciders)
        improvement = acceptable and any(r["ci90_low"] > 0 for r in deciders)
        checks["bootstrap_all_cells_1000_valid_draws_and_correct_decisions"] &= (
            len(cells) == 12 and all(r["valid_resamples"] == 1000 for r in cells)
            and acceptable == guard["acceptable"] and improvement == guard["improvement"])
        for market in ("Brent", "TTF"):
            for split, (start, end) in bounds.items():
                for horizon in ("1", "3"):
                    obs = result["market_splits_step4"][market]["splits"][split][horizon]["observations"]
                    checks["outcomes_end_within_splits"] &= all(
                        start <= r["date"] < r["outcome_date"] <= end for r in obs)
    rep = json.loads((OUT / "baseline_replication.json").read_text())
    checks["baseline_replication_passed"] = rep["replication_passed"] and rep["known_values_passed"]
    checks.update(protections())
    xml = ET.parse(OUT / "full_tests_final.xml").getroot()
    suites = list(xml.iter("testsuite"))
    tests = sum(int(s.attrib.get("tests", 0)) for s in suites)
    subtests = sum(int(s.attrib.get("subtests", 0)) for s in suites)
    failures = sum(int(s.attrib.get("failures", 0)) + int(s.attrib.get("errors", 0)) for s in suites)
    checks["full_suite_passed"] = tests > 0 and failures == 0
    dump(OUT / "deliverable_checks.json", checks)
    if not all(checks.values()):
        raise ValueError(f"Delivery checks failed: {[k for k, v in checks.items() if not v]}")
    lines = ["# Final verification", f"\nTests: **{tests}**, failures/errors: **{failures}**.",
             "\nThe test suite blocks outbound sockets and forces server read-only DB connections.",
             "\n" + "\n".join(f"- PASS: {k}" for k in checks),
             "\nCalibration disagreements are research findings, not silently converted to passing "
             "results. Full details are in bootstrap_calibration.json and REPORT.md.",
             f"\nNew GPT-4.1 token-rate cost: ${costs['new_usage_usd']:.6f}, below $15. "
             "All batch jobs are harvested; no spending reservations remain."]
    (OUT / "VERIFICATION.md").write_text("\n".join(lines) + "\n")
    return checks


def package():
    validate()
    source = PROJECT / "attached_assets/GERI_Step5_Restore_Pillars_Replit_Prompt_1792777933674.md"
    shutil.copyfile(source, OUT / "ORIGINAL_PROMPT.md")
    selections = [(p, str(p.relative_to(OUT))) for p in OUT.rglob("*") if p.is_file()
                  and p.name != "MANIFEST.json"]
    frozen = ["step4/snapshot.json", "step4/population.json", "step4/assignments.json",
              "step4/clustering_manifest.json", "step4/storylines.json",
              "cache/relevance_labels.jsonl", "cache/step4_second_opinion.jsonl",
              "cache/step5_relevance41.jsonl", "cache/step4_embeddings.jsonl"]
    for relative in frozen:
        path = LAB / relative
        if not path.exists():
            # The embedding cache has a provider-independent historical filename.
            if relative == "cache/step4_embeddings.jsonl":
                path = CACHE / "embeddings.jsonl"
            if not path.exists():
                raise FileNotFoundError(path)
        selections.append((path, f"frozen_inputs/{relative}"))
    for path in sorted((PROJECT / "scripts/geri_lab").glob("*.py")):
        selections.append((path, f"source/scripts/geri_lab/{path.name}"))
    selections.append((PROJECT / "scripts/geri_lab/README.md", "source/scripts/geri_lab/README.md"))
    for relative in ("src/geri/compute.py", "src/geri/normalize.py", "src/geri/types.py",
                     "src/risk/risk_engine.py", "src/alerts/alerts_engine_v2.py"):
        selections.append((PROJECT / relative, "source/" + relative))
    selections.sort(key=lambda pair: pair[1])
    manifest = {"confidential": True, "files": [
        {"path": name, "bytes": path.stat().st_size,
         "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        for path, name in selections]}
    dump(OUT / "MANIFEST.json", manifest)
    with zipfile.ZipFile(ZIP, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path, name in selections:
            archive.write(path, name)
        archive.write(OUT / "MANIFEST.json", "MANIFEST.json")
    with zipfile.ZipFile(ZIP) as archive:
        if archive.testzip() is not None:
            raise ValueError("Archive CRC check failed")
        for record in manifest["files"]:
            if hashlib.sha256(archive.read(record["path"])).hexdigest() != record["sha256"]:
                raise ValueError(f"Archive hash check failed: {record['path']}")
    print(f"Verified ZIP: {ZIP} ({ZIP.stat().st_size:,} bytes, {len(manifest['files'])} payloads)", flush=True)
    return ZIP


if __name__ == "__main__":
    package()
