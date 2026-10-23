"""Human-readable confidential Step 5 findings from cached experiment evidence."""
import csv
import json
from pathlib import Path

from .step4_report import table
from .step5_data import OUT, LAB, START, END


def read(name):
    path = OUT / name
    return json.loads(path.read_text()) if path.exists() else None


def csv_rows(name):
    with (OUT / name).open() as stream:
        return list(csv.DictReader(stream))


def build(summary):
    diagnosis = read("diagnosis.json")
    storage = read("storage_inventory.json")
    coverage = read("fixed_alert_input_coverage.json")
    costs = read("label_costs.json") or {"total_valid_labels": 400, "new_usage_usd": 0.}
    retention = read("relevance41_retention.json")
    complete = len(summary) == 8 and retention is not None and costs["total_valid_labels"] == 10894
    calibration = {}
    for name, expected in (("rel_only", True), ("damp_log", False)):
        result = read(f"variants/{name}/bootstrap_vs_integrity_v1.json")
        if result:
            calibration[name] = {"independent_expected_acceptable": expected,
                                 "actual_acceptable": result["acceptable"],
                                 "matches_expected_decision": expected == result["acceptable"],
                                 "brent3_h2": next(c for c in result["cells"] if (
                                     c["market"], c["horizon_sessions"], c["split"]) == ("Brent", 3, "H2"))}
    from .step5_data import dump
    dump(OUT / "bootstrap_calibration.json", calibration)
    columns = ["variant", "mean_abs_daily_change", "share_change_ge10", "weekend_weekday_ratio",
               "maximum", "acceptable", "improvement", "Brent_3d_H1_partial", "Brent_3d_H2_partial",
               "TTF_1d_H1_partial", "TTF_1d_H2_partial"]
    main_rows = [r for r in summary if r["variant"] != "damp_log"]
    summary_md = table(columns, [[r[k] for k in columns] for r in main_rows])
    (OUT / "summary_table.md").write_text(summary_md + "\n")
    latest_delay = diagnosis.get("scoring_delay_monthly", [])[-1]
    chosen = [r["variant"] for r in main_rows if r["acceptable"] and r["variant"] != "integrity_v1"]
    improvements = [r["variant"] for r in main_rows if r["improvement"]]
    lines = [
        "# GERI — Restored regional and asset pillars, stronger relevance and bootstrap decisions",
        "\n**CONFIDENTIAL — internal research. No production enablement or investment recommendation.**",
        f"\nStatus: **{'COMPLETE' if complete else 'PARTIAL — stronger-label run pending or stopped'}**.",
        "\n## Executive findings",
        "- Historical risk snapshots exist. Both continuous variants use genuine stored end-of-day "
        "normalized regional/asset values, not hindsight reconstructions or simulated production values.",
        "- **The March-peak hypothesis is only a partial explanation, not the complete cause.** "
        "The severity-5 insertion gate is real; assets never entered GERI because ASSET_RISK_SPIKE "
        "does not match the accepted ASSET_RISK_ALERT type. But assets use a 90-day SINGLE-DAY maximum, "
        "not the regional 180-day rolling-window maximum. After March left the relevant windows, "
        "persisted scores remained far below 70, so the gates still could not open.",
        f"- **Input timeliness is a major additional issue:** October risk events have median "
        f"scoring delay **{latest_delay['median_scoring_delay_days']:.1f} days**, mean decay factor "
        f"**{latest_delay['mean_decay_factor_at_scoring']:.6f}**. The newest source event inserted_at "
        f"in the October scored cohort is **{latest_delay['latest_source_inserted_at']}**. "
        "Restoring pillar wiring alone does not fix stale upstream risk inputs.",
        f"- Strict raw-score alert variants exclude **{coverage['original_score_missing_excluded']}** "
        "historical alerts whose backfilled raw_input has no original 0–100 score. No confidence "
        "substitution, guessed score or later snapshot is used. This materially limits those variants.",
        f"- GPT-4.1 labels cached: **{costs['total_valid_labels']:,}/10,894**; "
        f"new API token-rate cost **${costs['new_usage_usd']:.4f}**. "
        "The prior 400 exact labels were reused without new calls.",
        f"- Candidates meeting the requested bootstrap rule: **{', '.join(chosen) or 'none'}**. "
        f"Candidates meeting its improvement extension: **{', '.join(improvements) or 'none'}**.",
        "- Production sources/configuration, published values, ingestion, alert generation, "
        "email and Telegram are unchanged. All database access is server-enforced read-only.",
        "\n## A. Stronger-model full relevance replay",
        "Model gpt-4.1; same rubric, temperature 0, strict enum schema, and byte-identical "
        "Step 4 second-opinion input construction: alert headline, source event title, excerpt "
        "up to 700 characters (alert-body fallback where source text is absent), and ai_summary "
        "up to 1,000 characters, explicitly marked as unverified upstream AI output.",
        "All 10,894 high-impact alerts belong to the frozen Step 4 cohort. Cache identity includes "
        "model, system rubric, response schema and exact user input. rel41_only applies the literal "
        "r_material_events predicate: medium/high materiality and an allowed event type; "
        "it does not silently add a separate relevance>=1 requirement. Other alert types are unchanged.",
        "There are 10,889 unique exact inputs for 10,894 alerts: five pairs have identical "
        "prompt content. Exact-input caching deliberately shares those labels rather than "
        "requiring duplicate paid requests. Every alert's assignment and source cache record "
        "are exported in relevance41_alert_assignments.csv. Any duplicate paid outputs already "
        "generated before the aliases were identified remain included in the cost ledger.",
        "Bulk requests use the existing direct OpenAI credential and Batch API, not a new integration "
        "or changed credential. Batch offers a 50% discount ($1/M input and $4/M output for GPT-4.1), "
        "with up to a 24-hour completion window. Requests and raw outputs, per-response usage, "
        "job state and costs are retained. The first 400 labels came from the managed integration "
        "in Step 4; the model family/alias and prompts match, but provider routing and model "
        "snapshot resolution can differ. This is disclosed, not hidden as perfectly identical execution.",
    ]
    if retention:
        lines += [table(["Period", "Alerts", "Mini kept", "Mini share", "GPT-4.1 kept", "GPT-4.1 share",
                         "Pass disagreements"], [
            [r["month"], r["n"], r["mini_kept"], f"{r['mini_share']:.2%}", r["gpt41_kept"],
             f"{r['gpt41_share']:.2%}", r["pass_disagreements"]] for r in retention])]
    else:
        lines += ["Full retention comparison remains pending; no missing GPT-4.1 labels are imputed."]
    lines += [
        "\n## B. Storage and dead-pillar diagnosis",
        "\n### Storage inventory",
        table(["Table", "Rows at capture", "First", "Last", "History"], [
            [name, value["rows"], value["first"], value["last"], "append history, not latest-only"]
            for name, value in storage["coverage"].items()]),
        "Complete column names/types are in storage_inventory.json. Relevant fields:\n"
        "- risk_indices: id, region, window_days (7/30), risk_score, trend, calculated_at.\n"
        "- asset_risk: id, asset, region, window_days (7/30), risk_score, direction, calculated_at.\n"
        "- risk_events: event_id, region, category, base_severity, ai_confidence, weighted_score, created_at.\n"
        "- events: inserted_at/event_time and ai_impact_json asset confidence metadata for "
        "explaining the original engine's inputs; event metadata have no point-in-time version history.\n"
        "- alert_events: alert_type, scope_region/scope_assets, severity, confidence, raw_input, "
        "body and created_at preserve accepted alerts, not rejected severity-3/4 candidates.\n"
        "- alert_state: mutable last scores and updated_at; this is CURRENT-ONLY state, not daily history.",
        f"Stored regional scopes: {', '.join(diagnosis['stored_regions'])}. "
        f"Generator scopes with no risk_indices history: {', '.join(diagnosis['regions_without_any_history'])}. "
        "Asset writer computes oil/gas/fx/freight for Europe only. No global multi-region asset "
        "panel is invented.",
        "\n### Daily threshold evidence",
        f"regional_daily_thresholds.csv: **{diagnosis['regional_rows']:,}** rows "
        "(282 UTC days × 9 regions × 7/30-day windows). "
        f"asset_daily_thresholds.csv: **{diagnosis['asset_rows']:,}** rows "
        "(282 days × four Europe assets × two windows).",
        "Both files include stored end-of-day scores, snapshot ID/time, age and threshold flags "
        "at 70/80/90. Regional CSV includes the causal current-formula 180-day maximum of "
        "comparable rolling sums and peak start/end. Asset CSV includes the ACTUAL 90-day "
        "max-single-day denominator and the requested 180-day rolling-window diagnostic separately. "
        "The latter is explicitly not the asset engine's production denominator.",
        "Stored snapshots are selected AS OF each UTC day end; no future snapshots are read. "
        "When no new snapshot exists on a day, the last earlier persisted value is carried "
        "as the value then available, with its age disclosed. Missing regional histories stay missing. "
        "Current-formula reconstruction clips every denominator window to data available at that day.",
        "\n### Actual formulas and gates",
        "At first risk scoring, weighted_score = base_severity × mean(asset AI confidences) × "
        "category_weight × exp(−days_since_inserted_at/14). Category weights: geopolitical=1.2, "
        "energy=1.5, supply_chain=1.0; other strings fall back to 1.0. "
        "Despite the constant's HALF_LIFE name, exp(−age/14) is an e-folding time; its actual "
        "half-life is 14×ln(2)≈9.70 days. The score is stored once; it is not newly decayed each day.",
        "Regional risk = min(100, 100×current 7/30-day weighted sum / max(1, highest comparable "
        "window sum within preceding 180 days)). Asset risk = min(100, 100×current 7/30-day "
        "sum(weighted_score×asset_confidence) / max(1, highest SINGLE-DAY asset sum in preceding 90 days)).",
        "Regional candidate triggers at score≥70 OR change≥20% versus mutable alert_state. "
        "Asset candidate triggers at score≥70. Severity is 3 below80, 4 at≥80, 5 at≥90. "
        "create_alert_event rejects severity<5, so candidate generation is NOT successful persistence. "
        "The severity-4 lab counterfactual uses ≥80 end-of-day values, which already satisfy the ≥70 gate; "
        "it does not need to reconstruct mutable previous-risk state.",
        "\n### Monthly observed threshold coverage",
        table(["Kind", "Month", "Entity-days", "Stored", "Missing", "Max risk", "<70", "70–<80",
               "80–<90", "≥90", "Actual alerts"], [
            [r["kind"], r["month"], r["entity_days"], r["available"], r["missing"], r["max_stored_7d"],
             r["days_below70"], r["days_70_to80"], r["days_80_to90"], r["days_ge90"], r["actual_alerts"]]
            for r in diagnosis["monthly"]]),
        "Entity-days count each region/asset separately. Intraday alerts can occur even when "
        "the final daily snapshot falls below90; an end-of-day flag is not a reconstruction "
        "of every historical alert-engine run. alert_type_counts_monthly.csv gives exact monthly "
        "counts independently of end-of-day snapshot availability.",
        "\n### Hypothesis verdict and late-period blockers",
        "**Partially supported for early regional suppression; rejected as the complete/shared cause.** "
        "March peaks can depress regional risk during the 180-day lookback and the severity-5 gate "
        "blocks scores below90. But assets do not share that lookback. A peak leaving a window does "
        "not guarantee reopening: the numerator must also recover and denominator floors are 1.",
        "In August–October every stored generator-region and asset end-of-day score is below70 "
        "(see the monthly table), already failing candidate eligibility, not merely the severity-5 "
        "gate. late_period_ge90_without_alert.csv is empty: no unexplained late-period EOD≥90 case "
        "requires inventing an extra hidden blocker. Russia/South America lack regional snapshots, "
        "and all non-Europe regions lack asset snapshots in this risk writer.",
        "The daily reconstructed regional maxima move to later peaks after March leaves the window. "
        "By October22, remaining numerator contributions are extremely small. Asset denominators "
        "can be at their minimum1 while scores still fail70, directly disproving a March "
        "180-day maximum as the sole remaining asset blocker.",
        "\n### Timeliness evidence",
        table(["Scored month", "Events", "Median delay (days)", "Mean delay", ">30d share",
               "Mean stored weight", "Mean exp(−delay/14)", "Latest inserted_at"], [
            [r["month"], r["n"], r["median_scoring_delay_days"], r["mean_scoring_delay_days"],
             r["share_delay_over30d"], f"{r['mean_weighted_score']:.6g}",
             f"{r['mean_decay_factor_at_scoring']:.6g}",
             r["latest_source_inserted_at"]] for r in diagnosis["scoring_delay_monthly"]]),
        "Delay uses risk_events.created_at − events.inserted_at, not story publication date. "
        "The source engine selects processed/unscored events oldest-first, which is consistent "
        "with a backlog. These records demonstrate late scoring and its decay effect; they do "
        "not by themselves prove the operational reason throughput fell behind. "
        "No queue, ingestion or risk-engine fix is made in this lab step.",
        "\n### Asset type acceptance and original-score availability",
        f"Exactly **{diagnosis['asset_alerts_total']} ASSET_RISK_SPIKE** alerts exist in the study range. "
        "The original GERI type filter accepts 0% of this type; correcting the lab alias accepts "
        "100% by TYPE. This is distinct from raw-score coverage: "
        f"only **{diagnosis['asset_alerts_with_original_risk']}** have the original asset risk "
        f"in raw_input; **{diagnosis['regional_alerts_with_original_risk']}** regional alerts "
        "have risk_7d there. The other records have generic backfill metadata. Their rounded "
        "body text is not asserted to recover the original full-precision score.",
        table(["Month", "Regional spikes", "Asset spikes", "Old asset alert type", "Corrected type share"], [
            [r["month"], r["regional_risk_spike"], r["asset_risk_spike"], r["asset_risk_alert"],
             r["share_accepted_by_corrected_type_filter"]] for r in csv_rows("alert_type_counts_monthly.csv")]),
        "\n## C. Restored-pillar variants and contribution diagnostics",
        "- integrity_v1 remains the reference: same original acceptance, confidence inputs and "
        "health-aware chronological normalization history.\n"
        "- rel_only keeps the frozen mini r_material_events labels, no storyline dedup.\n"
        "- rel41_only changes only that high-impact relevance decision to the stronger cached labels.\n"
        "- pillars_fixed_alerts accepts ASSET_RISK_SPIKE via a LAB-ONLY mapping to the original "
        "compute function's ASSET_RISK_ALERT branch; R and A use original raw_input risk_7d/risk_score, "
        "never confidence. High-impact risk/confidence behavior is untouched.\n"
        "- pillars_fixed_alerts_sev4 retains that strict actual-alert cohort and adds at most one "
        "≥80 regional/asset candidate per UTC day/scope from stored EOD snapshots if no accepted "
        "raw-score actual alert covers that scope/day. These are explicitly reconstructed "
        "COUNTERFACTUAL candidates, not claims that rejected alerts were historically persisted.\n"
        "- pillars_continuous bypasses alert gates for R/A: R=Σ(weight_r×stored risk7d_r)/Σweight_r "
        "over the fixed stored regional universe, using the existing cluster multiplier function. "
        "Unmapped global uses its existing neutral multiplier (not weight zero); its stored risk "
        "is zero in this corpus, but its multiplier still enters the denominator. "
        "A=mean(Europe oil,gas,freight,fx stored7d risk). Missing inputs fail rather than invent zeros.\n"
        "- pillars_continuous_rel41 adds only the stronger high-impact relevance predicate.\n"
        "- damp_log is calibration only: within a storyline-day H=max(member severity×regional "
        "weight)×(1+ln n); C uses the same dampened H contributions. No dedup is proposed for production.",
        "Every variant uses its OWN preceding 90-calendar-day raw history, excludes unhealthy days "
        "from that baseline exactly as integrity_v1 does, and retains original 40/25/20/15 weights "
        "and normalization formulas. No published component history seeds an alternative replay.",
        table(["Stored region", "Existing cluster", "Multiplier"], [
            [region, item["cluster"], item["multiplier"]]
            for region, item in diagnosis.get("continuous_regional_multipliers", {}).items()]),
        "For fixed alert variants, confidence-to-original-score restoration also changes those "
        "alerts' weighted-risk contribution to concentration C, as the unchanged pure compute "
        "function does. For continuous variants, only raw R/A are overwritten; C remains the "
        "original accepted-alert concentration (subject to any high-impact relevance filtering).",
        "The strict raw-score cohort excludes missing-metadata alerts, so it is NOT an exact "
        "full-history corrected-wiring estimate. fixed_alerts_missing_original_risk.csv lists "
        "every exclusion. Continuous variants avoid this limitation by using stored risk snapshots.",
        "Per variant: pillar_monthly.csv gives weighted percentage-point contribution and zero "
        "counts; pillar_daily_and_ceiling.csv gives every raw/normalized pillar, contribution, "
        "quality flag and active-pillar ceiling; pillar_zero_days.json distinguishes raw0 from "
        "normalized0. A normalized zero can mean a lower-window minimum, not a dead upstream pillar. "
        "Cold-start/fallback days are flagged. The active ceiling uses prior-window variation, "
        "not the mere presence of positive values.",
        "\n## D. Paired weekly bootstrap decision rule",
        "For Brent1d/3d and TTF1d/3d, evaluate partial Pearson correlation of the signal with "
        "ABSOLUTE forward log-return size, controlling for trailing ten-return realised volatility "
        "(with intercept). Volatility is causal and includes the current close. "
        "Full=Jan28–Oct22; H1=Jan28–May31; H2=Jun1–Oct22. Outcomes must finish inside their split. "
        "Horizons count cleaned market sessions, not calendar days; the established market cleaning "
        "drops weekends and identical repeated closes. The full cell need not equal a pooled "
        "average of halves because boundary outcomes and correlations differ.",
        "Bootstrap: 1,000 paired resamples of non-overlapping ISO calendar-week blocks; "
        "sample the same weeks for candidate and reference, with replacement, preserving all "
        "observations and controls within each week. Partial edge weeks remain partial. "
        "A resample may have a different row count because weeks differ in observed sessions. "
        "Use 5th/95th percentiles for a 90% interval, fixed base seed20261025 with deterministic "
        "market/horizon/split offsets. Degenerate samples are reported, not assigned correlation0. "
        "All 1,000 draws and original dated observations are exported.",
        "**Acceptable:** each of Brent3d H1/H2 and TTF1d H1/H2 has lower90 > −0.05. "
        "**Improvement:** acceptable AND at least one of those four lower bounds >0. "
        "Full-period results and the other horizons are reported but do not change this decision. "
        "Stability metrics are shown separately, never used to waive a failed interval. "
        "The prior Step 4 point-estimate no-deterioration rule is historical evidence only, "
        "not the Step 5 decision tool.",
        "\n### Calibration against the supplied independent results",
    ]
    for name, result in calibration.items():
        cell = result["brent3_h2"]
        lines += [
            f"- {name}: expected acceptable={result['independent_expected_acceptable']}; "
            f"observed acceptable={result['actual_acceptable']}; decision match="
            f"{result['matches_expected_decision']}. Brent3d H2 difference="
            f"{cell['point_difference']:.4f}, 90% interval "
            f"[{cell['ci90_low']:.4f}, {cell['ci90_high']:.4f}]."]
        if not result["matches_expected_decision"]:
            lines += ["**Calibration discrepancy retained:** the supplied acceptable verdict is NOT "
                      "reproduced by this specified implementation and frozen observation set. "
                      "Do not adjust the rule, seed or intervals to force a match. "
                      "Inspect the four deciding cells in the full bootstrap table. "
                      "Weekly-block definitions, partial weeks, market cleaning, outcome boundaries "
                      "and calibration C construction can alter intervals; the independent resampling "
                      "code/observation set was not supplied, so their exact contribution is unproven."]
    lines += ["\n## E. Single summary table", summary_md,
              "\nFull/H1/H2 point differences, 90% intervals for all four requested horizons, sample "
              "sizes and week counts are in each variant's bootstrap_vs_integrity_v1.json and scorecard.md. "
              "summary_table.csv includes the main full/H1/H2 correlation and interval fields."]
    for row in summary:
        name = row["variant"]
        directory = OUT / "variants" / name
        monthly = csv_rows(f"variants/{name}/pillar_monthly.csv")
        zeros = read(f"variants/{name}/pillar_zero_days.json")
        bootstrap = read(f"variants/{name}/bootstrap_vs_integrity_v1.json")
        from .bootstrap import markdown
        lines += [f"\n### {name}", markdown(bootstrap),
                  table(["Pillar", "Raw-zero days", "Normalized-zero days"],
                        [[p, v["raw_zero_days"], v["normalized_zero_days"]] for p, v in zeros.items()]),
                  table(["Month", "H points", "R points", "A points", "C points", "Ceiling min", "Ceiling max"],
                        [[r["month"], r["mean_weighted_H_points"], r["mean_weighted_R_points"],
                          r["mean_weighted_A_points"], r["mean_weighted_C_points"], r["ceiling_min"],
                          r["ceiling_max"]] for r in monthly])]
    lines += [
        "\n## F. Limits, isolation, cost and reproduction",
        "Restored input availability is not validated economic information. The continuous series "
        "may restore mathematical pillar variation while the underlying risk engine is scoring "
        "very old inputs. Existing risk snapshots are true persisted history, but exact producer "
        "code versions and mutable source AI metadata are not historically versioned. "
        "Bootstrap intervals quantify this paired sample's uncertainty, not causal evidence, "
        "trading profitability or a multiple-testing-adjusted discovery. Independent human label "
        "review remains necessary; GPT-4.1 is not human ground truth.",
        "All SQL is read-only REPEATABLE READ and rolled back. Full production Python/configuration/"
        "workflow hashes and complete historical published-row digests are compared before/after. "
        "The original baseline replication check must pass. Full suite runs with read-only DB "
        "connections and blocked outbound network, so tests cannot deliver emails or Telegram messages.",
        f"New GPT-4.1 cost to date: **${costs['new_usage_usd']:.6f}**. "
        "The budget controller reserves UTF-8-byte upper bounds plus schema/envelope and full "
        "output cap before Batch submission; actual usage releases reservations. New spend "
        "ceiling is $14.99, one cent below the requested $15 cap. Prior 400-label costs are "
        "excluded. No prompt-cache discount is assumed. Agent/infrastructure charges are not "
        "included; these are token-rate estimates, not an invoice.",
        f"Run status/cost stop reason: {costs.get('stop_reason') or 'none'}.",
        "Pricing/method references: https://developers.openai.com/api/docs/guides/batch and "
        "https://developers.openai.com/api/docs/models/gpt-4.1.",
        "\nReproduction:\n"
        "1. python -m scripts.geri_lab.step5_labels — resumes exact cached labels and persisted "
        "Batch jobs, with budget checks; never repeats completed valid labels.\n"
        "2. python -m scripts.geri_lab.step5_diagnosis — frozen daily threshold/timeliness tables.\n"
        "3. python -m scripts.geri_lab.step5_run — all frozen-input, cached-only replays, "
        "bootstrap tables, comparisons and this report. --without-llm runs independent variants "
        "while stronger labels are pending. --finalize-only refreshes narrative from completed evidence.\n"
        "4. python -m scripts.geri_lab.verify_step2 --report-dir reports/geri_lab/step5 — read-only/"
        "network-blocked full suite; then python -m scripts.geri_lab.package_step5.\n"
        "Set OPENBLAS_NUM_THREADS=1 for predictable numeric performance. "
        "compare.py --bootstrap also supports existing lab scorecards containing dated "
        "market_splits_step4 observations. For this output tree use: "
        "python -m scripts.geri_lab.compare integrity_v1 rel41_only --bootstrap "
        "--report-root reports/geri_lab/step5/variants. Replaying does not itself make new LLM calls.",
        "Open REPORT.md first. ORIGINAL_PROMPT.md preserves the request. "
        "VERIFICATION.md, deliverable_checks.json, full_tests_final.xml/log and MANIFEST.json "
        "record final tests, protections and archive hashes. No republish is needed for this lab step.",
    ]
    (OUT / "REPORT.md").write_text("\n\n".join(lines) + "\n")
    print(f"Report written: {'complete' if complete else 'partial'}, {OUT / 'REPORT.md'}", flush=True)
