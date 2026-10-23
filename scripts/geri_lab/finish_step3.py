"""Finalize Step 3 from completed cached labels. Never makes model API calls."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from datetime import date

from .compare import metrics, compare
from .data import readonly_snapshot
from .relevance import load_population, create_gold_sample, label_all, write_outputs
from .run import execute
from .variants import get_variant

ROOT = Path(__file__).resolve().parents[2]
LAB = ROOT / "reports/geri_lab"
OUT = LAB / "step3"
NAMES = ("baseline", "integrity_v1", "relevance_cheap", "relevance_llm")


def read(path):
    return json.loads(path.read_text())


def table(headers, rows):
    def cell(value):
        return str(value).replace("|", "/").replace("\n", " ")
    return "\n".join([
        "| " + " | ".join(map(cell, headers)) + " |",
        "|" + "---|" * len(headers),
        *["| " + " | ".join(map(cell, row)) + " |" for row in rows],
    ])


def percent(value):
    return "unavailable" if value is None else f"{100*value:.2f}%"


def display(metric):
    if not metric:
        return "unavailable"
    if isinstance(metric, str):
        return metric
    value = metric["value"]
    return ("unavailable" if value is None else f"{value:.5g}") + f" (n={metric['n']})"


def write_report(checks, cost):
    gold = read(LAB / "gold_set/gold_set_statistics.json")
    fields = read(LAB / "gold_set/field_availability.json")
    filters = read(LAB / "gold_set/filter_evaluation.json")
    cards = {name: read(LAB / name / "scorecard.json") for name in NAMES}
    xml = ET.parse(OUT / "full_tests_final.xml").getroot()
    suites = [xml] if xml.tag == "testsuite" else list(xml.iter("testsuite"))
    test_n = sum(int(s.get("tests", 0)) for s in suites)
    failed = sum(int(s.get("failures", 0)) + int(s.get("errors", 0)) for s in suites)
    assert failed == 0, "Do not package a failed verification run."
    lines = [
        "# GERI Step 3 — relevance-filter research and mutation-route protection",
        "\nResearch period: **14 January–22 October 2026 inclusive (UTC)**.",
        "\n## Executive summary",
        f"\nThe population contains **{gold['population_n']:,} HIGH_IMPACT_EVENT alerts**. "
        f"The fixed-seed stratified sample contains **{gold['sample_n']} alerts**, "
        f"split into **{filters['train_n']} training / {filters['heldout_n']} held-out** observations. "
        f"Source-event join rate is **{percent(fields['source_join_rate'])}**.",
        f"\nThe training-selected cheap rule is **{filters['best_cheap_conjunction']}**. "
        "Its held-out results are below; it has not been adopted in production. "
        "The LLM replay uses relevance=2, or relevance=1 with medium/high materiality. "
        "Neither replay changes the published index or any alert.",
        f"\nPublished full-row fingerprint unchanged: **{checks['published_unchanged']}**. "
        f"Protected production source hashes unchanged: **{checks['protected_sources_unchanged']}**. "
        f"Full-suite JUnit cases: **{test_n}**, failures/errors: **{failed}** "
        "(see console log for pytest subtest counts).",
        "\n## Part 0 — production endpoint security",
        "\nThe only production behavior change is in `src/geri/routes.py`. POST "
        "`/api/v1/indices/geri/compute`, `/compute-yesterday`, `/backfill`, and "
        "`/backfill-auto` now use the exact existing `validate_runner_token` helper "
        "and `X-Runner-Token` header. Validation occurs before work and outside broad "
        "exception handlers, preserving HTTP 401 for missing/invalid credentials.",
        "\nEight isolated route tests cover all four missing-token and valid-token paths. "
        "The valid-token paths mock computation/storage: no real compute or backfill "
        "was invoked by the tests. The full test harness enforces read-only PostgreSQL "
        "connections and blocks outbound network/delivery.",
        "\nCaller audit: `geri-delivery.yml` and `geri-backfill-v11.yml` use protected "
        "`/internal/run/*` endpoints and already send the runner token. `geri-daily.yml` "
        "and `geri-watchdog.yml` use the direct CLI runner, not these public HTTP routes. "
        "No direct unauthenticated workflow callers were found; no workflow rewrite was needed. "
        "Existing route behavior after authorization is unchanged.",
        "\n## Part A — sample, joins, labels and provisional gold set",
        "\nSampling seed: **20261023**. Strata are month × confidence band: ≤0.05, "
        "(0.05,0.10], (0.10,0.20], (0.20,0.35], (0.35,0.60], >0.60. "
        "Square-root allocation oversamples small cells, with a minimum of two where "
        "the cell population permits. Row weights are population cell size / sampled cell size. "
        "All allocations and weights are exported. Split weights are recomputed by "
        "stratum within each half; singleton cells cannot appear in both halves.",
        "\nA one-source-event-per-alert join avoids duplicate alert rows. Event titles, "
        "text excerpts, sources, categories, regions and persisted classifier fields "
        "are joined read-only. Empty JSON objects are not counted as populated data.",
        "\n### Field availability",
        table(["Field", "Stored source column?", "Populated population", "Populated sample"], [
            [key, item["exists_in_source"], item["non_null_population"], item["non_null_sampled"]]
            for key, item in fields.items() if isinstance(item, dict) and "exists_in_source" in item
        ]),
        "\nDedicated energy-relevance and entity-count columns do not exist for this "
        "history, and no usable persisted quality-details values supply them. They "
        "are explicitly unavailable, not filled from guesses. F5 cannot be evaluated. "
        "Current persisted source metadata is not proven to be a point-in-time "
        "historical snapshot; this limits any causal backtest interpretation.",
        "\n### Weighted relevance distribution",
        table(["Group", "Relevance 0", "Relevance 1", "Relevance 2"], [
            ["Overall", *[percent(gold["weighted_relevance_overall"][str(i)]) for i in range(3)]],
            *[[f"Confidence {key}", *[percent(values[str(i)]) for i in range(3)]]
              for key, values in gold["weighted_relevance_by_bucket"].items()],
            *[[f"Month {key}", *[percent(values[str(i)]) for i in range(3)]]
              for key, values in gold["weighted_relevance_by_month"].items()],
        ]),
        "\nLabels use the fixed attachment rubric, `gpt-4.1-mini`, temperature 0 and "
        "JSON-object output. Prompt hashes, exact prompts, raw outputs and usage are "
        "saved. The target is direct relevance or material indirect relevance. "
        "Relevance 1 with low materiality does not pass. Temperature 0 is not a "
        "guarantee of model-level bit-for-bit reproducibility; cached responses "
        "make these particular replays repeatable.",
        "\nThree initial responses used `policy_move`, which is outside the required "
        "event-type list. Identical unconstrained retries repeated that schema error. "
        "Those three were reclassified with a strict JSON schema enforcing the "
        "original enum, without changing the fixed rubric or manually mapping labels. "
        "Diagnostic raw responses and subsequent pre-validation attempt audits are included.",
        "\nThe CSV column `human_relevance` is intentionally blank. The review sheet "
        "contains 40 fixed-seed random alerts plus up to 40 other alerts with "
        "driver/relevance disagreement or high confidence but relevance 0. "
        "These are LLM labels, not independently verified human ground truth.",
        "\n## Part B — filter evaluation",
        "\nAll threshold and conjunction selection uses the training half only. "
        "The held-out half is used solely for the following weighted evaluation. "
        "F4/F5 threshold curves are included as descriptive diagnostics; they "
        "were not used to select the operating threshold.",
        table(["Filter", "Kept share", "Precision", "Recall", "F1", "Weighted n"], [
            [key, percent(value.get("kept_share")), percent(value.get("precision")),
             percent(value.get("recall")), percent(value.get("f1")), value.get("weighted_n", value.get("status"))]
            for key, value in filters["heldout_filters"].items()
        ]),
        "\nF7 searches the unique confidence choices (none, ≥0.05, ≥0.10), optional "
        "driver requirement, and the full available 0.00–1.00 market-threshold grid "
        "in 0.05 increments. Ties favor precision, then fewer conditions. It also "
        "allows the no-filter rule so the search cannot silently assume filtering "
        "must help. The F6 perfect agreement with its own LLM labels is an oracle "
        "upper bound, not independent evidence of model accuracy.",
        "\n## Part C — shadow replay comparisons",
        "\n`relevance_cheap` and `relevance_llm` inherit `integrity_v1`, including "
        "health exclusions from the baseline window. Filters affect only "
        "HIGH_IMPACT_EVENT; the other accepted alert types and production formulas "
        "remain unchanged. `min_confidence`, `require_geri_driver` and "
        "`relevance_filter=none|cheap|llm` are implemented only in the lab.",
        "\n### Monthly rolling ceiling and high-impact retention",
        "\nDaily active-pillar ceiling = 100 × sum of original weights for raw "
        "components whose minimum is strictly below their maximum in that day's "
        "prior 90-day baseline window, after the variant's health exclusions. "
        "A positive-but-constant pillar does not count as active. This is distinct "
        "from the old full-period nonzero-pillar ceiling and is not a hard bound "
        "during insufficient-history fallback.",
        table(["Variant", "Month", "Ceiling minimum", "Ceiling maximum", "HIGH_IMPACT kept"], [
            [name, month, display(item["active_pillar_ceiling_min"]),
             display(item["active_pillar_ceiling_max"]),
             percent(item["high_impact_kept_share"]["value"])]
            for name, card in cards.items() for month, item in card["coverage"]["monthly"].items()
        ]),
        "\n### Complete scalar scorecard comparison",
        "\nValues include their sample sizes. Pair counts differ for forward "
        "horizons near the period end; absent/constant-series metrics remain "
        "unavailable. These are descriptive research comparisons, not a production "
        "trading validation or a basis for promoting a variant.",
    ]
    flattened = {name: metrics(card) for name, card in cards.items()}
    keys = sorted(set().union(*(set(value) for value in flattened.values())))
    lines.append(table(["Metric", *NAMES], [
        [key, *[display(flattened[name].get(key)) for name in NAMES]]
        for key in keys if not key.startswith("coverage.monthly.")
    ]))
    lines += ["\n### July 23 and October 22 headline sanity checks",
              "\nRank: original single-alert raw H contribution, then alert ID. "
              "Up to 15 actual available headlines per kept/dropped group; no invented padding."]
    for name in ("relevance_cheap", "relevance_llm"):
        for day, groups in cards[name]["sanity_headlines"].items():
            for group, items in groups.items():
                lines += [f"\n#### {name}: {day}, {group} ({len(items)} shown)",
                          table(["ID", "Headline", "Source", "Confidence"], [
                              [r["alert_id"], r["headline"], r.get("source"), r["confidence"]]
                              for r in items
                          ])]
    lines += [
        "\n## LLM usage and cost",
        f"\nUnique cached alert/prompt responses: **{cost['responses']:,}**. "
        f"Recorded input tokens: **{cost['input_tokens']:,}**; output tokens: "
        f"**{cost['output_tokens']:,}** (cached classifications plus separately audited "
        f"diagnostic responses). Estimated total provider token cost, including a "
        f"retry allowance: "
        f"**US${cost['estimated_usd']:.4f}**.",
        f"\nCost components: cached classifications **${cost['cached_success_usd']:.4f}**; "
        f"additional audited responses **${cost['audited_extra_usd']:.4f}**; "
        f"estimated unrecorded retry allowance **${cost['estimated_unrecorded_retry_usd']:.4f}**. "
        f"There were **{cost['unrecorded_retry_attempts']}** earlier failed attempts without "
        "retained usage. Their allowance uses the observed token lengths of the same "
        "three diagnostic prompts/responses. Valuing those retry outputs at the "
        f"140-token request cap instead gives **${cost['accounted_request_cost_upper_usd']:.4f}** "
        "for all accounted requests. This is not an invoice-level guarantee.",
        "\nEstimate = input tokens × $0.40/million + output tokens × $1.60/million. "
        "No discounted cached-input rate is assumed; any provider-side prompt "
        "caching could reduce the invoice relative to this estimate. This is calculated from "
        "recorded responses plus the explicit failed-attempt allowance, not an "
        "invoice audit; exact retry charges cannot be independently confirmed. "
        "No infrastructure/Agent usage is included.",
        "\nPricing references checked for this report: "
        "https://developers.openai.com/api/docs/models/gpt-4.1-mini and "
        "https://docs.replit.com/features/integrations/replit-ai-integrations "
        "(AI Integrations are charged at the provider's public API rates).",
        "\nThe append-only JSONL journal is flushed after every completed response; "
        "the requested Parquet file is its consolidated, unique-key snapshot. "
        "Re-export and replay make no paid calls. Resume reuses completed exact-key "
        "responses. As with any network request, a response lost before durable "
        "receipt cannot provide an absolute guarantee against a retry charge.",
        "\n## Limitations and deployment",
        "\nNo alert generation, ingestion, deduplication, weights, normalization, "
        "interpretation, email or Telegram behavior was changed. No production "
        "index rows were rewritten. Public method formulas remain untouched. "
        "Historical source-field sparsity, small strata and LLM-labeled targets "
        "limit the claims that can be made. Human review and a separate approved "
        "validation step are required before any production relevance-filter change.",
        "\nOnly the token-protection change needs publishing to affect the deployed "
        "API. Publishing does not install any lab variant as the production model. "
        "No publishing was performed by this work.",
        "\n## Included evidence and reproduction",
        "\n- Original task prompt and this full Markdown report.",
        "- Gold CSV, 80-row review CSV, sampling allocation, field availability, "
        "weighted distributions, prompts/raw outputs, train/held-out IDs, curves.",
        "- Full-population Parquet cache plus crash-safe JSONL journal.",
        "- Baseline, baseline-91 sensitivity, integrity, cheap and LLM series, "
        "scorecards, acceptance evidence and comparison tables.",
        "- Full-suite console/JUnit output, published-row fingerprints, protected "
        "source hashes, mutation-route patch and lab source.",
        "\nReproduction in the project: run `python -m scripts.geri_lab.relevance export` "
        "(cached-only); then `python -m scripts.geri_lab.run --variant relevance_cheap` "
        "and `--variant relevance_llm` with the period flags. Alternative variants "
        "are intentionally not required to replicate published values, so the "
        "baseline-replication acceptance gate may be false for them. Each run's "
        "read-only and input fingerprint checks remain separate mandatory evidence. "
        "Parquet export needs PyArrow; it can run under a separate compatible "
        "interpreter without changing the application's Python runtime.",
    ]
    (OUT / "REPORT.md").write_text("\n\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parquet-python", default=sys.executable)
    parser.add_argument("--parquet-site-packages")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    rows = load_population()
    labels = label_all(rows, allow_calls=False)
    write_outputs(rows, create_gold_sample(rows), labels)
    environment = os.environ.copy()
    if args.parquet_site_packages:
        environment["PYTHONPATH"] = args.parquet_site_packages
    subprocess.run([args.parquet_python, "-m", "scripts.geri_lab.write_relevance_parquet"],
                   env=environment, check=True, cwd=ROOT)
    for name in ("relevance_cheap", "relevance_llm"):
        execute(get_variant(name), date(2026, 1, 14), date(2026, 10, 22))
    comparison_dir = OUT / "comparisons"
    comparison_dir.mkdir(exist_ok=True)
    for name in ("baseline", "relevance_cheap", "relevance_llm"):
        path = compare("integrity_v1", name)
        shutil.copy2(path, comparison_dir / path.name)
    from scripts.geri_health_backfill import index_fingerprint
    with readonly_snapshot() as cursor:
        after = index_fingerprint(cursor)
    before = read(OUT / "published_before.json")
    after = json.loads(json.dumps(after, default=str))
    (OUT / "published_after.json").write_text(json.dumps(after, indent=2))
    hashes = read(OUT / "protected_source_hashes.json")
    checks = {
        "published_unchanged": before == after,
        "protected_sources_unchanged": all(
            hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest
            for path, digest in hashes.items()),
    }
    assert all(checks.values()), f"Protection check failed: {checks}"
    (OUT / "protection_checks.json").write_text(json.dumps(checks, indent=2))
    values = list(labels.values())
    diagnostics_path = LAB / "gold_set/retry_diagnostics.jsonl"
    diagnostics = [json.loads(line) for line in diagnostics_path.read_text().splitlines()]
    attempt_path = LAB / "cache/relevance_attempts.jsonl"
    attempts = [json.loads(line) for line in attempt_path.read_text().splitlines()]
    cached_response_ids = {row["response_id"] for row in values if row.get("response_id")}
    extras = diagnostics + [row for row in attempts if row.get("response_id") not in cached_response_ids]
    cached_input = sum(r["prompt_tokens"] or 0 for r in values)
    cached_output = sum(r["completion_tokens"] or 0 for r in values)
    extra_input = sum(r["prompt_tokens"] or 0 for r in extras)
    extra_output = sum(r["completion_tokens"] or 0 for r in extras)
    # Original bulk run plus one identical resume: four attempts per missing alert
    # in each run. Those responses predated the response-usage audit.
    unrecorded_retry_attempts = 8 * len(diagnostics)
    retry_input = 8 * sum(r["prompt_tokens"] for r in diagnostics)
    retry_output = 8 * sum(r["completion_tokens"] for r in diagnostics)
    cost = {
        "responses": len(values), "model": "gpt-4.1-mini",
        "audited_additional_responses": len(extras),
        "input_tokens": cached_input + extra_input,
        "output_tokens": cached_output + extra_output,
        "cached_success_usd": (cached_input * .4 + cached_output * 1.6) / 1_000_000,
        "audited_extra_usd": (extra_input * .4 + extra_output * 1.6) / 1_000_000,
        "unrecorded_retry_attempts": unrecorded_retry_attempts,
        "estimated_unrecorded_retry_usd": (retry_input * .4 + retry_output * 1.6) / 1_000_000,
        "usage_missing": sum(r["prompt_tokens"] is None or r["completion_tokens"] is None for r in values),
    }
    assert not cost["usage_missing"], "Cannot silently estimate missing usage."
    cost["estimated_usd"] = sum(cost[key] for key in
                                ("cached_success_usd", "audited_extra_usd", "estimated_unrecorded_retry_usd"))
    cost["accounted_request_cost_upper_usd"] = (
        (cost["input_tokens"] + retry_input) * .4
        + (cost["output_tokens"] + unrecorded_retry_attempts * 140) * 1.6) / 1_000_000
    (OUT / "llm_cost.json").write_text(json.dumps(cost, indent=2))
    write_report(checks, cost)
    shutil.copy2(ROOT / "attached_assets/GERI_Step3_Relevance_Filter_Replit_Prompt_1792762123520.md",
                 OUT / "ORIGINAL_PROMPT.md")
    if not (OUT / "part0_routes.patch").exists():
        (OUT / "part0_routes.patch").write_text(subprocess.check_output(
            ["git", "diff", "--", "src/geri/routes.py"], text=True))
    files = []
    for path in (OUT, LAB / "gold_set", LAB / "cache",
                 *(LAB / name for name in (*NAMES, "baseline_91")), LAB / "comparisons"):
        files.extend(p for p in path.rglob("*") if p.is_file()
                     and not p.name.endswith(".tmp") and p.name != "MANIFEST.json")
    files.extend(p for p in (ROOT / "scripts/geri_lab").rglob("*")
                 if p.is_file() and "__pycache__" not in p.parts)
    files.append(ROOT / "tests/test_geri_routes_security.py")
    files = sorted(set(files))
    manifest = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    (OUT / "MANIFEST.json").write_text(json.dumps(manifest, indent=2))
    files.append(OUT / "MANIFEST.json")
    archive = LAB / "GERI_Step3_Relevance_Filter_Report.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zipped:
        for path in files:
            zipped.write(path, "GERI_Step3_Relevance_Filter_Report/" + str(path.relative_to(ROOT)))
    with zipfile.ZipFile(archive) as zipped:
        assert zipped.testzip() is None
    print(json.dumps({"archive": str(archive.relative_to(ROOT)), "bytes": archive.stat().st_size,
                      "files": len(files), "checks": checks, "llm_cost": cost}, indent=2))


if __name__ == "__main__":
    main()
