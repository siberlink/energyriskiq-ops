"""Render the complete diagnosis, counterfactual and disabled production-fix handoff."""
import csv
import json
from pathlib import Path

from .step4_report import table
from .step6_data import OUT, PROJECT
from .step6_blast import build as blast


def read(name):
    return json.loads((OUT / name).read_text())


def rows(name):
    with (OUT / name).open() as stream:
        return list(csv.DictReader(stream))


def build():
    direct, dependent = blast()
    d, summary = read("diagnosis.json"), read("summary_table.json")
    coverage = rows("daily_counterfactual_coverage.csv")
    dry = read("dry_run.json") if (OUT / "dry_run.json").exists() else None
    reliable = [r for r in coverage if r["reliable"] == "True"]
    source_impact = {
        "src/ai/ai_worker.py": "Producer: oldest-first fixed-20 enrichment is the bottleneck; summary/impact absent on pending events.",
        "src/risk/risk_engine.py": "Direct: only enriched events score; delayed inputs decay once and are timestamped into wrong scoring-time windows.",
        "src/api/risk_routes.py": "Direct regional/asset/risk-event API and risk dashboards report stale near-zero upstream values.",
        "src/api/routes.py": "Event API detail/list and event views expose missing summaries and delayed processing states.",
        "src/api/ops_routes.py": "Operational freshness based only last-run time can look healthy despite months-old input cohorts.",
        "src/alerts/alerts_engine_v2.py": "Regional/asset alerts fail thresholds; top drivers use risk-event weights; high-impact alert summaries may be absent.",
        "src/alerts/alerts_engine.py": "Legacy alert engine reads stale risk panels and enriched-event drivers; applies only if this legacy path is invoked.",
        "src/alerts/digest_worker.py": "Daily digest generation uses risk_indices, risk_events, asset_risk and summaries; understated risk / missing enriched context.",
        "src/alerts/templates.py": "Alert formatting consumes supplied summary/asset context; missing values propagate to delivered text.",
        "src/alerts/backfill_metadata.py": "Metadata repair reads source enrichment and can only recover fields that actually exist.",
        "src/egsi/trader_intel.py": "Ancillary legacy GERI/EERI-labelled correlations read risk_indices; stale/case-sensitive scopes can mislead. Not the authoritative EGSI storage formula.",
        "src/delivery/pro_delivery_worker.py": "Delivery consumes assembled GERI components downstream of regional/asset alert eligibility; it is not a direct upstream risk-table reader.",
        "src/geri/live.py": "Consumes GERI component context and event alerts; indirect R/A suppression; direct H event generation can continue.",
        "src/geri/repo.py": "GERI accepted-alert repository / component persistence; downstream of dead regional alerts and the existing asset type mismatch.",
        "src/geri/compute.py": "Pure GERI component math, not an upstream table query; code identifiers match the inventory but it cannot repair missing inputs.",
        "src/geri/normalize.py": "Pure component scaling/normalization downstream, not an enrichment reader.",
        "src/geri/types.py": "Component data model/field names, not an upstream database reader.",
        "src/geri/routes.py": "Account/public GERI API surfaces assembled components; nomenclature match is downstream, not independent upstream scoring.",
        "src/eriq/context.py": "ERIQ assistant reads assembled GERI component context; explanations can inherit understated R/A, not a separate enrichment queue.",
    }
    products = [
        ["GERI Daily / GERI Live / intraday account panels", "Indirect through alerts and components; upstream R/A absence. H alerts still exist. Existing GERI asset-type mismatch remains intentionally unchanged."],
        ["EERI reri_indices_daily and EERI dashboards", "No direct reader of the five fields in its scoring service/repository; may inherit effects through eligible alert overlays. TTF-dominant market layer is separate. Do not call EERI entirely broken."],
        ["EGSI-M / EGSI-S and gas storage dashboards", "No direct upstream enrichment dependency in primary EGSI market/storage scoring. Ancillary trader-intelligence correlations have legacy risk_indices queries; storage inputs and seasonal stress are separate."],
        ["Public /daily-geo-energy-intelligence-digest and dated archives", "Potential indirect alert/narrative context effects; public snapshots/archives are not regenerated or rewritten."],
        ["Daily Intelligence Report / Enterprise report / weekly outlook", "Potential indirect use of GERI/alert context and risk-driver narrative; not every market/storage section is affected. Existing report snapshots remain unchanged."],
        ["Email and Telegram alert / digest / Pro delivery", "Same payload builders consume upstream alerts/digests. Missing/suppressed input affects informational content; no sender, template, customer delivery or message-content change is implemented."],
        ["Brent scenario / forecast engine", "Downstream GERI inputs may inherit suppressed R/A. Market prices, scenario mechanics and H relevance cache are separate; no forecast or trading signal release."],
        ["Admin/internal ingestion and scheduled runners", "Dispatch the same enrichment/risk workers; all deployment and GitHub runner flag values must agree before opt-in."],
    ]
    lines = [
        "# GERI — Enrichment backlog diagnosis, timely counterfactual and disabled pipeline fix",
        "\n**CONFIDENTIAL — internal. No paid enrichment or backlog catch-up executed.**",
        f"\nSnapshot: {d['captured_at']} UTC. Historical daily diagnosis: 2026-01-14 through snapshot date; current day partial.",
        "The independent dry-run and /ops/status checks were captured later. Existing production "
        "ingestion/enrichment jobs were not stopped, so small queue-count differences between "
        "these timestamps reflect normal concurrent activity, not enrichment triggered by this step.",
        "\n## Executive verdict",
        f"**The enrichment queue is the bottleneck, not the risk scoring queue.** "
        f"{d['backlog']['waiting_retryable']:,} retryable events await AI enrichment; "
        f"{d['backlog']['attempts_exhausted']:,} additional events have exhausted the three outer attempts. "
        f"Already-enriched waiting for risk scoring: **{d['ready_unscored']}**.",
        f"Average complete-day 28-day inflow is **{d['average_daily_inflow_28d']:.2f}/day** versus "
        f"AI completions **{d['average_daily_enrichment_28d']:.2f}/day**. Current capacity cannot clear "
        "the queue while the observed inflow continues. Capacity must exceed arrivals, not merely run successfully.",
        "The production fix is shipped **OFF by default**. It changes no published GERI scores, "
        "alert thresholds, existing risk-history rows, customer emails or Telegram content. "
        "The read-only monitoring addition remains available while processing is disabled.",
        "\n## A. Pipeline, queue and cost diagnosis",
        "Pipeline: ingestion writes an event with processed=false → enrichment selects unprocessed "
        "events with ai_attempts<3 → successful AI writes summary, impact JSON, model and ai_processed_at "
        "and sets processed=true atomically → risk engine selects processed events with impact JSON "
        "and no risk row → risk_events append → regional risk_indices and Europe asset_risk append.",
        "**processed is the enrichment completion flag, not a separate pre-AI stage.** No "
        "independent processed-stage completion timestamp exists. A fabricated extra queue would double-count work.",
        "Source scheduler: .github/workflows/ingestion_pipeline.yml runs hourly at minute0, "
        "calling scripts/replit_scheduled_job.py → protected ingestion pipeline handler → AI worker → risk engine. "
        "Standalone main --mode ai / internal AI routes are also entry points. The pipeline lock "
        "prevents overlapping normal ingestion runs, not every possible standalone worker.",
        "Current AI defaults: gpt-4.1-mini; 20 events/run; inserted_at ASC; max6000 input characters; "
        "temperature0.2; max2000 output tokens; 0.5s between events; up to two explicit API retries "
        "with 1s/2s backoff. The existing SDK can also retry internally. ai_attempts increments "
        "once per event processing run; after three outer attempts the event is excluded. "
        "JSON parse errors are stored and retried only on a later outer run. No durable provider "
        "RPM/TPM observation or API-token usage ledger exists in the current worker.",
        "Source fixed-hourly capacity is 20×24=480/day. Observed completion counts can exceed "
        "that number due to additional entry points, overrides or reruns; source defaults alone "
        "do not prove the entire deployed execution history. Operational run statuses are retained "
        "in pipeline_snapshot.json without raw error strings.",
        f"First complete day with completions below inflow: **{d['first_single_day_below_inflow']}**. "
        f"First trailing seven-day shortfall: **{d['first_7day_below_inflow']}**. "
        "A one-day deficit is not by itself proof of a sustained scheduler failure.",
        "\n### Daily evidence and its precision",
        "daily_pipeline_queues_and_delays.csv contains per-day inflow, enrichment completion, "
        "reconstructed EOD enrichment queue, scoring inflow/completion/queue, and median/P95 "
        "enrichment and total-scoring delays. Median post-enrichment scoring delay isolates the "
        "actual scoring stage; the added P95 post-enrichment column is calculated from the same "
        "frozen event timestamps. daily_pipeline_all_stages.csv separately accounts for all five "
        "stage types, including regional and asset snapshot output counts through the capture "
        "cutoff. Risk/asset snapshots are many-to-many aggregate outputs, not distinct "
        "event-completion queues: their per-stage entry/start timestamps and queue are not "
        "instrumented, so processing-delay/queue fields remain explicitly unknown. "
        "Snapshot counts and event counts use different units and are not subtracted.",
        "EOD queues are reconstructed from the surviving event rows and their completion timestamps, "
        "including any pre-period opening cohort. Deleted-row history and retry/exhaustion transitions "
        "were not audited. Therefore exact historical retryable queue depth, unsuccessful attempt "
        "counts, and a source-feed waiting queue cannot be recovered; unknown fields remain blank, "
        "not invented. Current backlog counts are directly measured. The current day is partial.",
        "\n### Current backlog",
        table(["Metric", "Value"], [[k, v] for k, v in d["backlog"].items()] + [
            ["Ready enriched but unscored", d["ready_unscored"]],
            ["Clearance days if arrivals stop", d["days_clear_with_no_new_inflow"]],
            ["Clearance days with observed continuing arrivals", d["days_clear_with_continued_inflow"]]]),
        "A null continuing-arrivals clearance estimate means **no finite clearance time at "
        "current throughput**, not zero days. Exhausted attempts need a separately reviewed retry policy; "
        "this step does not reset them or execute catch-up.",
        "\n### Cost evidence and sensitivity",
        "Measured historical token counts and billed USD/event: **unavailable**. The worker stores "
        "AI model and result, but discards response.usage. Existing generic product token-credit "
        "tables do not measure enrichment API consumption. It would be misleading to report "
        "a measured enrichment invoice.",
        "cost_estimate_sensitivity.csv estimates input tokens from observed input bytes plus the "
        "system prompt and output tokens from stored impact JSON bytes, using 1 token per5/4/3 bytes. "
        "These are explicit scenarios, not tokenizer measurements. Stored JSON formatting differs "
        "from the original response, so output estimates are approximate. Last30-day sample uses "
        "the actually stored gpt-4.1-mini results, not a paid probe.",
        table(["Scenario", "Input tokens/event (est.)", "Output tokens/event (est.)", "USD/event (est.)",
               "30d at inflow", "30d at120% capacity", "Entire retryable backlog"], [
            [r["scenario"], r["estimated_input_tokens_per_event"], r["estimated_output_tokens_per_event"],
             f"{r['estimated_usd_per_event']:.7f}", r["estimated_30d_at_inflow_usd"],
             r["estimated_30d_at_120pct_capacity_usd"], r["estimated_whole_retryable_backlog_usd"]]
            for r in d["cost_estimate_scenarios"]]),
        "Standard GPT-4.1-mini list price: $0.40/M input and $1.60/M output, excluding caching, "
        "retries, provider/managed integration markup, taxes and agent/platform costs. Source: "
        "https://developers.openai.com/api/docs/models/gpt-4.1-mini . No model migration was made.",
        "\n### Blast radius",
        "The complete static field-reference inventory and line references are in "
        "blast_radius_direct_readers.json/CSV. Import dependents are a conservative potential "
        "dependency list, not proof every route executes a stale-data read. Pure component "
        "field-name matches are explicitly separated from upstream database readers below.",
        table(["Module", "Effect / qualification"], [[r["path"], source_impact.get(r["path"],
            "Direct field reference; inspect exported line references and import dependents.")] for r in direct]),
        table(["Product / page / delivery", "Effect / limits"], products),
        "\n## B. Timely reconstruction and honest coverage limits",
        "Counterfactual only: for each currently scored event, weight=base_severity×stored AI "
        "confidence×category weight, with age0; assign it to events.inserted_at, not risk scoring "
        "time. Use causal 180-day maximum comparable regional window sums and 90-day maximum "
        "single-day Europe asset sums, each with minimum denominator1. Rebuild every UTC day "
        "end for seven regions, four Europe assets and both7/30d windows.",
        "This assumes later-stored AI confidence/asset-impact values were available at insertion. "
        "It is NOT genuine point-in-time AI knowledge. Never-scored events remain missing. "
        "Current event impact metadata are not versioned; this is an additional counterfactual "
        "limitation. All timely CSVs and JSON panels are labelled accordingly.",
        f"Reliable coverage (risk-scored cohort / all inserted that day >=50%): **{len(reliable)}** "
        f"calendar days including any current partial day; "
        f"first={reliable[0]['date'] if reliable else None}, last={reliable[-1]['date'] if reliable else None}. "
        "Exact evaluation counts by market, horizon and split appear in each bootstrap table.",
        "All market evidence uses only reliable SIGNAL dates, the same mask for reference and "
        "candidate, and outcomes that end within full/H1/H2 splits. Outcome-day enrichment "
        "coverage is not an extra requirement because outcome prices are separately observed. "
        "The unfinished current day is excluded. Replay series retain all282 completed days "
        "with explicit unreliable flags; normalization follows integrity_v1's existing health "
        "rules, while only market evaluation receives the additional coverage mask. Stability "
        "is shown over the full replay, separately from market evidence.",
        "Variants: continuous timely uses weighted regional means and mean Europe asset risk; "
        "alerts timely creates one severity5 candidate per generated region/asset/day at≥90 "
        "(the ≥70 candidate and ≥90 severity5 gates are unchanged), replacing the observed "
        "regional/asset alert path; continuous timely rel41 additionally uses the COMPLETE "
        "existing stronger-model r_material_events cache. No new paid labels are generated.",
        "Continuous variants retain the original accepted-alert C concentration as in the prior "
        "continuous experiment; alert counterfactuals feed their own R/A contributions into C "
        "through unchanged pure GERI component math. No storyline deduplication is used.",
        "\n### Summary",
        table(["Variant", "Reliable replay days", "Decision status", "Acceptable", "Improvement",
               "Mean|Δ|", "Share|Δ|≥10", "Weekend ratio"], [
            [r["variant"], r["reliable_calendar_days"], r["decision_status"], r["acceptable"], r["improvement"],
             r["mean_absolute_daily_change"], r["share_abs_change_ge_10"], r["weekend_weekday_mean_ratio"]]
            for r in summary]),
        "An unassessable H2 cell is **insufficient coverage**, not evidence of economic deterioration. "
        "No interval is fabricated from fewer than four observations. The requested two-half "
        "acceptance rule cannot establish an improvement while those cells are unavailable.",
        "timely_vs_stored_risk_daily.csv compares every daily reconstructed7/30 value with "
        "stored7/30d values where the prior frozen snapshot has them; unavailable comparisons "
        "are blank. daily_counterfactual_coverage.csv, timely_risk_panels.json and "
        "timely_severity5_candidates.csv provide all coverage and reconstruction inputs. "
        "Per-variant folders contain scorecards, all bootstrap draws/intervals, daily ceilings, "
        "monthly weighted contributions and raw/normalized zero-day counts.",
        "\n## C. Disabled production implementation",
        "**RISK_PIPELINE_V2_ENABLED=false by default.** No environment activation was performed. "
        "The GitHub job also forwards an explicitly default-false repository variable; enabling "
        "only one runner is not a valid rollout. AI and risk entry points return to the "
        "unchanged legacy path when the flag is off.",
        "Freshness: newest-first enrichment and newest-first scoring. Enrichment can still "
        "process older report-useful events when budget/capacity allows. The V2 scoring query "
        "excludes events older than7 days and future timestamps. It inserts only previously "
        "unscored events, with zero-age base weight; it never updates/deletes risk history. "
        "All V2 risk windows, trend windows, maxima and asset-direction queries use inserted_at. "
        "Existing legacy stored weights are not retroactively recomputed.",
        "Capacity: every hourly run targets ceil(1.2×previous28-complete-day average inflow/24), "
        "not a fixed20. Retry-reserved rate-slot capacity is checked before admission. The "
        "default20 RPM is conservative relative to the legacy0.5s pacing, and the tighter "
        "configured limit wins. Shared PostgreSQL transaction-level rate slots enforce pacing "
        "across processes; SDK hidden retries are disabled so each request is accounted.",
        "Budget: short transaction-level advisory mutexes admit durable worst-case per-batch "
        "reservations into the existing job_runs table. New event leases in AI JSON plus "
        "FOR UPDATE SKIP LOCKED avoid concurrent duplicate claims. Usage is recorded in NEW "
        "AI result metadata, and actual/upper cost settles the reservation. Ambiguous failures "
        "and crash-stranded reservations stay conservative, never silently refunded. No new "
        "schema/table is introduced, and no long-lived idle advisory-lock session is relied on.",
        "Defaults: RISK_PIPELINE_V2_MAX_RPM=20, RISK_PIPELINE_V2_RUN_SECONDS=1200, "
        "RISK_PIPELINE_V2_DAILY_BUDGET_USD=10. Budget accounting uses the stated OpenAI token "
        "rates, not a guarantee of final provider invoice including markup. Unknown model "
        "pricing fails closed. Configuration must be approved against the actual provider tier.",
        "Monitoring: /ops/status adds queue depth, exhausted-attempt count, oldest waiting age, "
        "28-day inflow and last24-hour median TOTAL scoring delay. Flag-enabled runs persist "
        "an hourly-deduplicated internal admin alert in job_runs and error logs when median>6h "
        "or queue>one day of inflow. This is the existing watchdog's internal operations "
        "channel; there is no customer email or Telegram delivery call.",
        "A configured capacity target is not a promise that a failing provider can complete it: "
        "runtime, retries, exhausted budget or provider outages raise/log explicit shortfalls. "
        "The normal ingestion handler already fails when AI reports failures. The operator "
        "must monitor actual completions, not only planned batch size.",
        "\n### Dry run",
        "Command: **python -m src.risk.pipeline_v2_dry_run**. The command creates a server-enforced "
        "READ ONLY repeatable-read snapshot; no migrations, event claims, usage reservations, "
        "API clients or paid calls are executed. dry_run.json preserves the full output.",
    ]
    if dry:
        lines += [table(["Item", "Value"], [
            ["Actual flag enabled", dry["flag_currently_enabled"]], ["Events selected newest-first", dry["events_to_enrich"]],
            ["Required hourly batch", dry["plan"]["batch_size"]],
            ["Planned daily capacity", dry["plan"]["planned_daily_capacity"]],
            ["Capacity / inflow", dry["plan"]["capacity_ratio"]],
            ["Max admission USD, all retries", dry["maximum_admission_reservation_usd_including_two_retries"]],
            ["Estimated batch USD, one call/event", dry["estimated_next_batch_usd_one_call_per_event"]],
            ["Can admit within current daily budget", dry["budget_can_admit_batch"]],
            ["Nominal last7d net-clearance days", dry["plan"]["catch_up_last7d_days_at_net_capacity"]],
            ["Already-enriched fresh events ready", dry["already_enriched_fresh_events_to_score"]],
            ["Writes / paid calls", "0 / 0"]]),
            "The projected risk output uses all KNOWN stored/ready confidences only. AI results "
            "for the selected unenriched events are inherently unknown without a paid call, so "
            "their post-enrichment risk effect is explicitly UNKNOWN, with possible0–100 values. "
            "No invented confidence0.5 is presented as a forecast of the next actual output.",
            table(["Known-only regional output today", "7d", "30d"], [
                [region, item["7"], item["30"]] for region, item in
                dry["known_inputs_only_regional_asset_output_today"]["regional"].items()]),
            table(["Known-only Europe asset output today", "7d", "30d"], [
                [asset, item["7"], item["30"]] for asset, item in
                dry["known_inputs_only_regional_asset_output_today"]["asset"].items()])]
        central = d["cost_estimate_scenarios"][1]["estimated_usd_per_event"]
        lines += [f"At the actual rounded plan of {dry['plan']['planned_daily_capacity']} events/day, "
                  f"the central 30-day full-capacity estimate is **${central*dry['plan']['planned_daily_capacity']*30:.2f}** "
                  "(before retries, markup and taxes). This is a planning estimate, not observed billing."]
    lines += [
        "\n### Files changed and verification",
        "Production: src/ai/ai_worker.py; src/ai/pipeline_v2_worker.py; "
        "src/risk/risk_engine.py; src/risk/pipeline_v2_core.py; src/risk/pipeline_v2.py; "
        "src/risk/pipeline_v2_dry_run.py; src/api/ops_routes.py; "
        ".github/workflows/ingestion_pipeline.yml. Research changes stay in scripts/geri_lab.",
        "VERIFICATION.md, full_tests_final.xml/log, protection_checks.json and "
        "deliverable_checks.json contain the final tests and disabled/read-only assurances. "
        "The protected source allowlist prevents unrelated production edits. Published historical "
        "GERI data are fingerprinted before/after. Archive contents have SHA-256 hashes.",
        "\n## Recommendation and estimated operating cost",
        "**Do not enable fleet-wide yet.** Review this code and the dry run, confirm provider "
        "limits and budget, then run a short supervised flag-enabled canary with explicit "
        "approval. This step itself runs no catch-up and makes zero paid enrichment calls.",
        "Recommended rollout after approval: (1) one runner, consistent flag/config; "
        "(2) log actual response usage and costs, queue ages and per-run completions; "
        "(3) temporarily raise approved throughput enough to work through the fresh7-day "
        "cohort before it expires; (4) keep older backlog for report enrichment only; "
        "(5) return to >=120% steady-state capacity once the fresh backlog is small. "
        "The existing 1,109 exhausted records require separate review, not an automatic retry reset.",
        "A120% steady-state plan stops new arrivals being starved, but its spare headroom "
        "does not rapidly clear the existing fresh cohort. The dry-run net-clearance estimate "
        "is a frozen-rate arithmetic estimate, not a promise: arrivals vary, jobs fail, "
        "and events can age beyond7 days before processing. Configure any burst deliberately, "
        "within rate/runtime/budget limits, rather than silently initiating it.",
        "Use the cost sensitivity table for the monthly steady-state forecast. At the default "
        "nominal daily admission budget, exposure is at most$10 per UTC reservation day in "
        "tracked token-rate reservations (up to$300/30days), not the expected invoice. "
        "Normal estimated cost is much smaller and excludes failed-call ambiguity and "
        "provider-specific markup; measure real usage during the canary before committing.",
        "No history rewrite is recommended. Existing risk weights remain stored as-is; "
        "new zero-age weights and corrected time-base windows create a transition/cold-start "
        "regime. Keep version/activation-time records and monitor saturation before allowing "
        "the resulting upstream snapshots to influence published products. This fix alone "
        "does NOT repair GERI's separate ASSET_RISK_SPIKE type mismatch or approve any new "
        "GERI scoring methodology.",
        "**Activation consequence:** a production flag-enabled run writes the normal upstream "
        "risk snapshot tables, so existing consumers can immediately pick up the new values. "
        "There is no separate downstream publication quarantine in this change. A genuinely "
        "shadow-only canary must use an isolated data copy/read-only reconstruction first. "
        "Enabling on production is therefore an approved upstream release, not a harmless preview. "
        "Turning the flag off resumes legacy processing; it does not undo inserted rows, and "
        "the legacy scorer can again process older enriched events. Plan that transition "
        "explicitly rather than claiming an automatic rollback of historical data.",
        "\n## Reproduction / contents",
        "Open REPORT.md first. ORIGINAL_PROMPT.md preserves the request. All CSVs, frozen "
        "scored-event inputs, queue snapshots, dry-run output, per-variant evidence, production "
        "source/diff, tests and manifest are included. Run python -m scripts.geri_lab.step6_analysis "
        "for cached-input research (no paid calls), then the read-only dry run and final "
        "verification/package command. No automatic backlog run is attached to this report.",
    ]
    (OUT / "REPORT.md").write_text("\n\n".join(lines)+"\n")
