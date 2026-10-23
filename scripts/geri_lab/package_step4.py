"""Validate the completed Step 4 evidence and build a hash-manifested ZIP."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET
import zipfile

from .step4_data import LAB, OUT, CACHE, dump
from .step4_report import NAMES

ZIP = LAB / "GERI_Step4_Storyline_Dedup_Full_Report.zip"


def read_csv(path):
    with path.open() as stream:
        return list(csv.DictReader(stream))


def validate():
    checks = {}
    checks["400_second_opinion_alerts"] = len(read_csv(OUT / "model_agreement_400.csv")) == 400
    checks["300_unique_pairs"] = (
        len({r["pair_id"] for r in read_csv(OUT / "labelled_pairs_300.csv")}) == 300)
    review = read_csv(OUT / "pair_review_60.csv")
    checks["60_pairs_awaiting_human_review"] = (
        len(review) == 60 and all(not r["human_same_development"] for r in review))
    tuning = json.loads((OUT / "threshold_tuning.json").read_text())
    checks["150_train_150_heldout_pairs"] = tuning["train"]["n"] == tuning["heldout"]["n"] == 150
    assignments = json.loads((OUT / "assignments.json").read_text())
    checks["10894_unique_alert_assignments"] = len(assignments) == 10894
    stories = json.loads((OUT / "storylines.json").read_text())
    members = [id_ for story in stories for id_ in story["member_ids"]]
    checks["members_form_exact_partition"] = len(set(members)) == len(members) == 10894
    series = {name: read_csv(LAB / name / "series.csv") for name in NAMES}
    checks["seven_full_282_day_replays"] = all(len(s) == 282 for s in series.values())
    checks["regional_asset_raw_scores_unchanged"] = all(
        [(r["raw_R"], r["raw_A"]) for r in series[name]] ==
        [(r["raw_R"], r["raw_A"]) for r in series["integrity_v1"]]
        for name in NAMES[2:])
    checks["baseline_replication_passed"] = json.loads(
        (OUT / "baseline_replication.json").read_text())["replication_passed"]
    cost = json.loads((OUT / "costs.json").read_text())
    checks["new_cost_below_10_target"] = cost["total_upper_with_unresolved_usd"] <= 10
    checks["second_opinion_below_3"] = (
        cost["phases"]["second_opinion"]["usage_cost_usd"] +
        cost["phases"]["second_opinion"]["unresolved_upper_usd"] <= 3)
    checks.update(json.loads((OUT / "protection_checks.json").read_text()))
    xml = ET.parse(OUT / "full_tests_final.xml").getroot()
    suites = list(xml.iter("testsuite"))
    tests = sum(int(s.attrib.get("tests", 0)) for s in suites)
    failures = sum(int(s.attrib.get("failures", 0)) + int(s.attrib.get("errors", 0)) for s in suites)
    checks["full_test_suite_no_failures"] = tests > 0 and failures == 0
    dump(OUT / "deliverable_checks.json", checks)
    if not all(checks.values()):
        raise ValueError(f"Delivery checks failed: {[k for k, v in checks.items() if not v]}")
    (OUT / "VERIFICATION.md").write_text(
        "# Step 4 verification\n\n"
        f"JUnit cases (including subtests): {tests}; failures/errors: {failures}.\n\n" +
        "\n".join(f"- {key}: PASS" for key in checks) +
        "\n\nAll database connections are server-enforced read-only. Tests block outbound "
        "network and cannot deliver emails/Telegram messages. No production files were edited, "
        "so no workflow restart or republish is needed.\n\n"
        "The archive manifest contains a SHA-256 for every payload file (excluding the "
        "manifest itself). Archive CRC and every stored payload hash are verified after writing.\n")
    return checks


def package():
    validate()
    source_dir = OUT / "source"
    source_dir.mkdir(exist_ok=True)
    project = LAB.parents[1]
    for path in (project / "scripts/geri_lab").glob("*.py"):
        shutil.copy2(path, source_dir / path.name)
    shutil.copy2(project / "scripts/geri_lab/README.md", source_dir / "README.md")
    protected = source_dir / "production_reference_only"
    protected.mkdir(exist_ok=True)
    for name in ("compute.py", "normalize.py", "types.py", "health.py"):
        shutil.copy2(project / "src/geri" / name, protected / name)
    shutil.copy2(
        project / "attached_assets/GERI_Step4_Storyline_Dedup_Replit_Prompt_1792775732564.md",
        OUT / "ORIGINAL_PROMPT.md")
    # No older report ZIPs, no credentials, no application config or databases.
    files = {}
    for path in OUT.rglob("*"):
        if path.is_file() and path.name != "MANIFEST.json":
            files[f"GERI_Step4/{path.relative_to(OUT)}"] = path
    for name in NAMES:
        for file in ("series.csv", "scorecard.json", "scorecard.md", "market_splits_step4.json"):
            path = LAB / name / file
            files[f"GERI_Step4/variants/{name}/{file}"] = path
    for name in NAMES[2:]:
        for reference in ("baseline", "integrity_v1"):
            path = LAB / f"compare_{reference}_vs_{name}.md"
            files[f"GERI_Step4/comparisons/{path.name}"] = path
    for name in ("relevance_labels.jsonl", "step4_second_opinion.jsonl", "step4_pairs.jsonl",
                 "step4_api_attempts.jsonl", "embeddings.jsonl"):
        path = CACHE / name
        files[f"GERI_Step4/cache/{name}"] = path
    for name in ("gold_set.csv", "sampled_alerts.jsonl", "gold_set_prompt.md"):
        path = LAB / "gold_set" / name
        files[f"GERI_Step4/step3_gold_reference/{name}"] = path
    manifest = {
        "confidential": True, "description": "Step 4 lab-only complete reproducible evidence",
        "files": {name: {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                         "bytes": path.stat().st_size} for name, path in sorted(files.items())}}
    dump(OUT / "MANIFEST.json", manifest)
    files["GERI_Step4/MANIFEST.json"] = OUT / "MANIFEST.json"
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name, path in sorted(files.items()):
            archive.write(path, name)
    with zipfile.ZipFile(ZIP) as archive:
        if archive.testzip():
            raise ValueError("Archive CRC check failed")
        for name, record in manifest["files"].items():
            if hashlib.sha256(archive.read(name)).hexdigest() != record["sha256"]:
                raise ValueError(f"Archive hash mismatch {name}")
    print(json.dumps({"zip": str(ZIP), "bytes": ZIP.stat().st_size, "members": len(files),
                      "payload_hashes_verified": len(manifest["files"])}, indent=2))


if __name__ == "__main__":
    package()
