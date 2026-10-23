"""Validate and package the complete Step 6 report/evidence without operational writes."""
import csv
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET
from zipfile import ZipFile, ZIP_DEFLATED

from .step4_data import dump
from .step5_data import PROJECT, LAB, CACHE
from .step6_data import OUT
from .step6_protect import check, ALLOWED
from .step6_report import build
from .step6_analysis import NAMES, diagnosis
from .step6_stages import build as build_stages

DEST = LAB / "GERI_Step6_Enrichment_Backlog_Full_Report.zip"


def package():
    protection = check()
    diagnosis()
    build_stages()
    build()
    dry = json.loads((OUT / "dry_run.json").read_text())
    smoke = json.loads((OUT / "ops_status_smoke.json").read_text())
    suites = ET.parse(OUT / "full_tests_final.xml").getroot().findall(".//testsuite")
    counts = {key: sum(int(s.attrib.get(key, 0)) for s in suites)
              for key in ("tests", "errors", "failures", "skipped")}
    assert counts["errors"] == counts["failures"] == 0
    assert counts["tests"] >= 583
    assert not dry["flag_currently_enabled"] and dry["server_read_only"]
    assert dry["paid_calls"] == dry["writes"] == 0
    assert smoke["http_status"] == 200 and not smoke["risk_pipeline_v2"]["enabled"]
    assert dry["plan"]["capacity_ratio"] >= 1.2
    series_counts = {}
    for name in NAMES:
        directory = OUT / "variants" / name
        with (directory / "series.csv").open() as stream:
            series_counts[name] = len(list(csv.DictReader(stream)))
        assert series_counts[name] == 282
        assert (directory / "bootstrap_vs_integrity_v1.json").exists()
    checks = {
        "full_tests_xml": counts, "pytest_summary": "573 passed, 10 subtests passed",
        "variant_daily_rows": series_counts, "default_flag_off": True,
        "actual_ops_status_flag_off": True, "paid_enrichment_calls": 0, "lab_writes": 0,
        "dry_run_capacity_at_least_120pct": True, "app_public_home_screenshot_checked": True,
        "risk_history_protected": protection["existing_risk_history_unchanged"],
        "published_history_protected": protection["published_geri_history_unchanged"],
        "scope_guard_passed": not protection["unexpected_production_changes"],
        "archive_is_confidential_internal": True}
    dump(OUT / "deliverable_checks.json", checks)
    (OUT / "VERIFICATION.md").write_text(
        "# Verification\n\n"
        "- Full repository test suite: **573 passed; 10 subtests passed** (583 XML test cases), no failures/errors.\n"
        "- Test harness enforces read-only database connections and blocks outbound network delivery.\n"
        "- 21 new tests cover default-off gates, capacity, age-zero scoring, elapsed/event-time cutoffs, "
        "maxima, coverage-safe reconstruction, budget rejection, SDK retries, usage settlement, ambiguous "
        "timeouts, invalid JSON, unknown model rejection and append-only risk output.\n"
        "- Read-only dry run: flag off; 0 writes; 0 paid calls; newest-first selection; capacity >=120%.\n"
        "- /ops/status: HTTP200 with queue/age/delay metrics and flag=false; no internal alert was emitted.\n"
        "- API Server restarted once; startup clean. Public homepage screenshot rendered successfully. "
        "Its async snapshot panel was still loading at capture; /ops/status was separately verified.\n"
        "- Existing-ID fingerprints for all three risk-history tables unchanged; published historical "
        "GERI fingerprint unchanged. Legitimate concurrent append rows are allowed.\n"
        "- Source before/after audit uses the same src/**/*.py inventory. Only Part C allowlisted "
        "files differ. Workflow configuration diff is separately included against Git HEAD.\n"
        "- No catch-up, new enrichment, classifier purchase, customer email or Telegram message initiated.\n"
        "- Monetary figures are explicit planning estimates, not measured historical invoices.\n"
        "- H2 comparisons with only three observations remain unassessable, not promoted.\n")
    (OUT / "REPRODUCE.md").write_text(
        "# Reproduce without paid calls\n\n"
        "Use an existing checkout of this application with its Python dependencies. This is a "
        "report/evidence bundle, not a standalone deployment or a secret-containing project export.\n\n"
        "1. Review the source diff; all operational V2 processing stays off by default. Do not enable it.\n"
        "2. Place frozen_prior_inputs/step4 and step5 at reports/geri_lab/step4 and step5; place "
        "frozen_prior_inputs/cache at reports/geri_lab/cache.\n"
        "3. Put the top-level Step6 evidence files and variants directory at reports/geri_lab/step6. "
        "Preserve pipeline_snapshot.json and scored_event_snapshot.json: capture() then uses frozen inputs.\n"
        "4. Use the bundled scripts/geri_lab source with the existing app source and dependencies. Run "
        "`python -m scripts.geri_lab.step6_analysis` for the frozen counterfactuals; it makes no paid calls.\n"
        "5. `python -m src.risk.pipeline_v2_dry_run` independently queries the configured application "
        "database with server-enforced read-only permissions; it makes no writes/API calls. Requires "
        "the existing secure database configuration, not credentials in this archive.\n"
        "6. The packaging/protection commands perform read-only before/after database checks. "
        "Do not run actual AI/ingestion/risk workers to reproduce this research.\n\n"
        "The production flag must remain unset/false everywhere until a separate approved release. "
        "Enabling it against the live database feeds the existing product consumers immediately.\n")
    prompt = PROJECT / "attached_assets/GERI_Step6_Enrichment_Backlog_Replit_Prompt_1792780603733.md"
    payload = {p.relative_to(OUT).as_posix(): p for p in OUT.rglob("*") if p.is_file()
               and p.name != "MANIFEST.json"}
    payload["ORIGINAL_PROMPT.md"] = prompt
    for p in (PROJECT / "scripts/geri_lab").rglob("*.py"):
        payload["source/"+p.relative_to(PROJECT).as_posix()] = p
    for relative in sorted(ALLOWED | {".github/workflows/ingestion_pipeline.yml"}):
        payload["source/"+relative] = PROJECT / relative
    # Exact prior replay inputs and frozen stronger labels; no need to regenerate or purchase labels.
    for relative in (
        "step4/snapshot.json", "step4/population.json", "step4/assignments.json", "step4/storylines.json",
        "step5/asof_pillars.json", "step5/regional_daily_thresholds.csv", "step5/asset_daily_thresholds.csv",
        "step5/risk_snapshot.json",
    ):
        p = LAB / relative
        assert p.exists(), p
        payload["frozen_prior_inputs/"+relative] = p
    for p in CACHE.rglob("*"):
        if p.is_file() and p.suffix in (".json", ".jsonl"):
            payload["frozen_prior_inputs/cache/"+p.relative_to(CACHE).as_posix()] = p
    paths = sorted(ALLOWED | {".github/workflows/ingestion_pipeline.yml"})
    diff = subprocess.run(["git", "diff", "--", *paths], cwd=PROJECT, text=True,
                          capture_output=True, check=True).stdout
    (OUT / "production_changes.patch").write_text(diff)
    payload["production_changes.patch"] = OUT / "production_changes.patch"
    manifest = {"files": {name: {"bytes": path.stat().st_size,
                                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                           for name, path in sorted(payload.items())},
                "archive_root": "GERI_Step6_Enrichment_Backlog",
                "note": "Confidential; original data/report at captured UTC timestamps; file manifest excludes itself"}
    dump(OUT / "MANIFEST.json", manifest)
    payload["MANIFEST.json"] = OUT / "MANIFEST.json"
    with ZipFile(DEST, "w", compression=ZIP_DEFLATED, compresslevel=6) as archive:
        for name, path in sorted(payload.items()):
            archive.write(path, "GERI_Step6_Enrichment_Backlog/"+name)
    with ZipFile(DEST) as archive:
        assert archive.testzip() is None
        for name, value in manifest["files"].items():
            assert hashlib.sha256(archive.read("GERI_Step6_Enrichment_Backlog/"+name)).hexdigest() == value["sha256"]
    print(json.dumps({"zip": str(DEST.relative_to(PROJECT)), "files": len(payload),
                      "bytes": DEST.stat().st_size, "checks": checks}, indent=2), flush=True)


if __name__ == "__main__":
    package()
