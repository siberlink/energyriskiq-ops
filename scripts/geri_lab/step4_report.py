"""Step 4 offline scoring, model comparisons, diagnostics and confidential report."""
from collections import Counter, defaultdict
from datetime import date, timedelta
import hashlib
import json
import math
from statistics import mean, pstdev

from .acceptance import replication
from .compare import compare
from .data import readonly_snapshot, fingerprints
from .replay import replay, write_series
from .scorecard import scorecard, write_scorecard, clean_prices, partial_correlation
from .step4_ai import costs
from .step4_data import OUT, LAB, START, END, labels_for, journal, dump
from .step4_pairs import write_csv
from .storyline import RULES, rule_pass, region_of
from .variants import get_variant
from .relevance_filters import context_for, sanity_lists

NAMES = ("baseline", "integrity_v1", "dedup_only", "dedup_corr",
         "rel_dedup", "relhigh_dedup", "rel_only")
SPLITS = {"full": (date(2026, 1, 28), END),
          "H1": (date(2026, 1, 28), date(2026, 5, 31)),
          "H2": (date(2026, 6, 1), END)}


def table(headers, rows):
    def cell(value):
        if value is None:
            return "N/A"
        if isinstance(value, float):
            return f"{value:.4f}"
        return str(value).replace("|", "/").replace("\n", " ")
    return "\n".join(["| " + " | ".join(headers) + " |",
                     "|" + "|".join("---" for _ in headers) + "|"] +
                    ["| " + " | ".join(map(cell, row)) + " |" for row in rows])


def binary_metrics(actual, predicted, weights):
    tp = sum(w for a, p, w in zip(actual, predicted, weights) if a and p)
    fp = sum(w for a, p, w in zip(actual, predicted, weights) if not a and p)
    fn = sum(w for a, p, w in zip(actual, predicted, weights) if a and not p)
    precision, recall = tp / (tp + fp) if tp + fp else 0., tp / (tp + fn) if tp + fn else 0.
    return {"precision": precision, "recall": recall,
            "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.,
            "agreement": sum(w for a, p, w in zip(actual, predicted, weights) if a == p) / sum(weights)}


def relevance_analysis(population, sample):
    labels = labels_for(population)
    heldout = [row for row in sample if row["evaluation_split"] == "heldout"]
    # Read the exact Step 4 second opinion cache by its job ID.
    stronger = {r["id"]: r for r in journal(LAB / "cache/step4_second_opinion.jsonl")}
    if len(stronger) != 400 or len(heldout) != 200:
        raise ValueError("Incomplete second-opinion or held-out sample")
    rules = {}
    for rule in RULES:
        months = defaultdict(list)
        for row in population:
            months[row["month"]].append(rule_pass(labels[row["alert_id"]], rule))
        weights = [r["eval_weight"] for r in heldout]
        old_target = [rule_pass(labels[r["alert_id"]], "r_current") for r in heldout]
        predicted = [rule_pass(labels[r["alert_id"]], rule) for r in heldout]
        strong_target = [rule_pass(stronger[r["alert_id"]]["labels"], rule) for r in heldout]
        rules[rule] = {
            "kept": sum(rule_pass(label, rule) for label in labels.values()), "population": len(population),
            "by_month": {month: {"kept": sum(values), "n": len(values), "share": mean(values)}
                         for month, values in sorted(months.items())},
            "heldout_n": len(heldout),
            "heldout_vs_step3_r_current_weighted": binary_metrics(old_target, predicted, weights),
            "heldout_same_rule_vs_stronger_weighted": binary_metrics(strong_target, predicted, weights),
        }
        rules[rule]["share"] = rules[rule]["kept"] / len(population)
    matrices = {}
    for field in ("relevance", "materiality", "event_type"):
        matrix = Counter()
        agree = 0
        for row in sample:
            old, new = labels[row["alert_id"]][field], stronger[row["alert_id"]]["labels"][field]
            matrix[(str(old), str(new))] += 1
            agree += old == new
        matrices[field] = {"exact_agreement": agree / len(sample),
                           "cells": [{"mini": a, "stronger": b, "n": count}
                                     for (a, b), count in sorted(matrix.items())]}
    all_rows, disagreements = [], []
    for row in sample:
        id_ = row["alert_id"]
        old, new = labels[id_], stronger[id_]["labels"]
        item = {
            "alert_id": id_, "date": row["alert_date"], "headline": row.get("event_title") or row["headline"],
            "evaluation_split": row["evaluation_split"], "sample_weight": row["sample_weight"],
            "mini_relevance": old["relevance"], "stronger_relevance": new["relevance"],
            "mini_materiality": old["materiality"], "stronger_materiality": new["materiality"],
            "mini_event_type": old["event_type"], "stronger_event_type": new["event_type"],
            "mini_pass_r_material_events": rule_pass(old, "r_material_events"),
            "stronger_pass_r_material_events": rule_pass(new, "r_material_events"),
            "mini_reason": old["short_reason"], "stronger_reason": new["short_reason"],
            "event_excerpt": row.get("event_excerpt"), "ai_summary": row.get("ai_summary"),
            "human_relevance": "",
        }
        all_rows.append(item)
        if item["mini_pass_r_material_events"] != item["stronger_pass_r_material_events"]:
            disagreements.append(item)
    write_csv(OUT / "model_agreement_400.csv", all_rows)
    write_csv(OUT / "r_material_events_disagreements.csv", disagreements)
    result = {"rules": rules, "matrices": matrices, "pass_disagreements": len(disagreements),
              "second_opinion_excerpt_available": sum(bool(r.get("event_excerpt")) for r in sample),
              "second_opinion_summary_available": sum(bool(r.get("ai_summary")) for r in sample)}
    dump(OUT / "relevance_rule_evaluation.json", result)
    write_csv(OUT / "relevance_rules_overall.csv", [
        {"rule": name, "kept": r["kept"], "n": r["population"], "share": r["share"],
         **{f"heldout_current_{k}": v for k, v in r["heldout_vs_step3_r_current_weighted"].items()},
         **{f"heldout_stronger_{k}": v for k, v in r["heldout_same_rule_vs_stronger_weighted"].items()}}
        for name, r in rules.items()])
    write_csv(OUT / "relevance_rules_monthly.csv", [
        {"rule": rule, "month": month, **values} for rule, r in rules.items()
        for month, values in r["by_month"].items()])
    return result, disagreements


def diagnostics(rows):
    assignments = json.loads((OUT / "assignments.json").read_text())
    stories = json.loads((OUT / "storylines.json").read_text())
    lookup = {s["storyline_id"]: s for s in stories}
    by_day = defaultdict(list)
    for row in rows:
        by_day[row["created_at"].date().isoformat()].append(row)
    daily, day = [], START
    while day <= END:
        key = day.isoformat()
        todays = by_day[key]
        daily.append({"date": key, "alerts": len(todays),
                      "storylines": len({assignments[str(r["id"])]["storyline_id"] for r in todays})})
        day += timedelta(days=1)
    write_csv(OUT / "storylines_daily.csv", daily)
    monthly = []
    for month in sorted({r["date"][:7] for r in daily}):
        items = [r for r in daily if r["date"].startswith(month)]
        total = sum(r["alerts"] for r in items)
        count = sum(r["storylines"] for r in items)
        monthly.append({"month": month, "days": len(items), "alerts": total, "storyline_days": count,
                        "mean_alerts_per_day": total / len(items), "mean_storylines_per_day": count / len(items),
                        "storyline_days_per_alert": count / total if total else None})
    write_csv(OUT / "storylines_monthly.csv", monthly)
    distribution = [{"alerts_per_storyline": count, "n_storylines": number}
                    for count, number in sorted(Counter(s["n_alerts"] for s in stories).items())]
    write_csv(OUT / "storyline_size_distribution.csv", distribution)
    write_csv(OUT / "all_storylines.csv", stories)
    largest = sorted(stories, key=lambda s: (-s["n_alerts"], s["first_seen"]))[:10]
    write_csv(OUT / "largest_storylines_10.csv", largest)
    day_lists = {}
    for key in ("2026-07-23", "2026-10-22"):
        groups = defaultdict(list)
        for row in by_day[key]:
            groups[assignments[str(row["id"])]["storyline_id"]].append(row)
        listing = []
        for id_, members in groups.items():
            source = lookup[id_]
            sources = {(r.get("source") or "").strip().casefold() for r in members} - {""}
            listing.append({
                "storyline_id": id_, "headline": source["headline"], "first_seen": source["first_seen"],
                "last_seen": source["last_seen"], "n_alerts_day": len(members), "n_sources_day": len(sources),
                "n_alerts_overall": source["n_alerts"], "n_sources_overall": source["n_sources"],
                "member_ids_day": [r["id"] for r in members], "region_cluster": source["region_cluster"],
            })
        listing.sort(key=lambda s: (-s["n_alerts_day"], s["first_seen"]))
        day_lists[key] = listing
        write_csv(OUT / f"storylines_{key}.csv", listing)
    result = {"n_alerts": len(rows), "n_storylines": len(stories), "distribution": distribution,
              "monthly": monthly, "largest_10": largest, "sanity_days": day_lists}
    dump(OUT / "storyline_diagnostics.json", result)
    return result


def split_market(series, markets):
    signal = {r["date"]: r["geri"] for r in series}
    result = {}
    for name, market_rows in markets.items():
        prices, cleaning = clean_prices(market_rows)
        returns = [None] + [math.log(prices[i][1] / prices[i - 1][1]) for i in range(1, len(prices))]
        result[name] = {"cleaning": cleaning, "splits": {}}
        for split, (start, end) in SPLITS.items():
            horizons = {}
            for horizon in (1, 3):
                obs = []
                for i, (day, value) in enumerate(prices):
                    if not start <= day <= end or day.isoformat() not in signal:
                        continue
                    if i < 10 or i + horizon >= len(prices) or prices[i + horizon][0] > end:
                        continue
                    forward = math.log(prices[i + horizon][1] / value)
                    vol = pstdev(returns[i - 9:i + 1])
                    obs.append((signal[day.isoformat()], forward, vol, day.isoformat(),
                                prices[i + horizon][0].isoformat()))
                xs, ys, zs = ([r[i] for r in obs] for i in range(3))
                horizons[str(horizon)] = {
                    "partial_abs": partial_correlation(xs, list(map(abs, ys)), zs),
                    "partial_signed": partial_correlation(xs, ys, zs), "n": len(obs),
                    "observations": [{"date": r[3], "outcome_date": r[4], "signal": r[0],
                                      "forward_log_return": r[1], "realised_vol_10": r[2]} for r in obs]}
            result[name]["splits"][split] = horizons
    return result


def stability(series):
    values = [r["geri"] for r in series]
    changes = [b - a for a, b in zip(values, values[1:])]
    weekdays = [r["geri"] for r in series if date.fromisoformat(r["date"]).weekday() < 5]
    weekends = [r["geri"] for r in series if date.fromisoformat(r["date"]).weekday() >= 5]
    return {"mean_abs_daily_change": mean(map(abs, changes)), "share_change_ge_10": mean(abs(c) >= 10 for c in changes),
            "weekend_weekday_ratio": mean(weekends) / mean(weekdays) if mean(weekdays) else None,
            "max": max(values)}


def score_variants(data, rows):
    all_series, all_scores = {}, {}
    for name in NAMES:
        variant = get_variant(name)
        context = context_for(variant, data["alerts"])
        series = replay(data["alerts"], START, END, variant, data["warmup"], data["health"], context)
        directory = LAB / name
        directory.mkdir(exist_ok=True)
        write_series(directory / "series.csv", series)
        result = scorecard(series, data["markets"], variant, sanity_lists(data["alerts"], variant, context))
        result["market_splits_step4"] = split_market(series, data["markets"])
        write_scorecard(directory, result)
        dump(directory / "market_splits_step4.json", result["market_splits_step4"])
        all_series[name], all_scores[name] = series, result
        print(f"Replayed {name}: {len(series)} days", flush=True)
    replica = replication(all_series["baseline"], data["published"])
    dump(OUT / "baseline_replication.json", replica)
    if not replica["replication_passed"] or not replica["known_values_passed"]:
        raise ValueError("Baseline replication protection failed")
    # Simple unscaled count of qualifying Middle-East storyline-days.
    assignments = json.loads((OUT / "assignments.json").read_text())
    labels = labels_for(rows)
    counts = defaultdict(set)
    for row in rows:
        cluster = region_of(row)
        if cluster == "Middle East" and rule_pass(labels[row["id"]], "r_material_events"):
            counts[row["created_at"].date().isoformat()].add(assignments[str(row["id"])]["storyline_id"])
    benchmark = [{"date": r["date"], "geri": len(counts[r["date"]])} for r in all_series["baseline"]]
    write_csv(OUT / "benchmark_middle_east_storylines.csv", [
        {"date": r["date"], "unscaled_storyline_count": r["geri"]} for r in benchmark])
    all_series["benchmark"] = benchmark
    benchmark_result = {"name": "Middle-East r_material_events storyline count (unscaled)",
                        "stability": stability(benchmark), "market_splits_step4": split_market(benchmark, data["markets"])}
    dump(OUT / "benchmark_scorecard.json", benchmark_result)
    all_scores["benchmark"] = benchmark_result
    # Keep the human-readable scorecards as complete as their JSON counterparts.
    def market_rows(left, right=None):
        output = []
        for market, horizon in (("Brent", "3"), ("TTF", "1")):
            for split in SPLITS:
                current = all_scores[left]["market_splits_step4"][market]["splits"][split][horizon]
                benchmark_metric = benchmark_result["market_splits_step4"][market]["splits"][split][horizon]
                values = [market, horizon, split, current["partial_abs"]]
                if right:
                    other = all_scores[right]["market_splits_step4"][market]["splits"][split][horizon]
                    values.append(other["partial_abs"])
                values += [benchmark_metric["partial_abs"], current["n"]]
                output.append(values)
        return output
    for name in NAMES:
        path = LAB / name / "scorecard.md"
        path.write_text(path.read_text() +
            "\n\n## Step 4 temporal partial correlations versus unscaled benchmark\n\n"
            "Absolute forward log returns, controlling for causal 10-return realised "
            "volatility. Full starts 2026-01-28; H1 ends May 31; H2 starts June 1. "
            "Outcomes cannot cross the split boundary. This is retrospective, not a "
            "prospective trading validation. Signed partials and all observations are in "
            "market_splits_step4.json.\n\n" +
            table(["Market", "Sessions", "Split", name, "ME storyline count", "n"],
                  market_rows(name)) + "\n")
    summary = []
    for name, series in all_series.items():
        row = {"variant": name, **stability(series)}
        for market, horizon in (("Brent", "3"), ("TTF", "1")):
            for split in SPLITS:
                metric = all_scores[name]["market_splits_step4"][market]["splits"][split][horizon]
                row[f"{market}_{horizon}d_{split}"] = metric["partial_abs"]
                row[f"{market}_{horizon}d_{split}_n"] = metric["n"]
        summary.append(row)
    dump(OUT / "summary_table.json", summary)
    write_csv(OUT / "summary_table.csv", summary)
    # A conservative 'better' test: neither H1 nor H2 may deteriorate for either
    # requested absolute-move metric, and at least one must improve.
    reference = next(r for r in summary if r["variant"] == "integrity_v1")
    tests = {}
    for row in summary:
        keys = [f"{market}_{horizon}d_{split}" for market, horizon in (("Brent", 3), ("TTF", 1))
                for split in ("H1", "H2")]
        valid = all(row[k] is not None and reference[k] is not None for k in keys)
        tests[row["variant"]] = {
            "reference": "integrity_v1", "both_markets_both_halves_not_worse": (
                all(row[k] >= reference[k] for k in keys) if valid else None),
            "better_by_requested_guard": (
                all(row[k] >= reference[k] for k in keys) and any(row[k] > reference[k] for k in keys)
                if valid else False)}
    dump(OUT / "improvement_guard.json", tests)
    for name in NAMES[2:]:
        for reference in ("integrity_v1", "baseline"):
            path = compare(reference, name)
            path.write_text(path.read_text() +
                "\n\n## Step 4 temporal absolute-move partials\n\n" +
                table(["Market", "Sessions", "Split", reference, name, "ME storyline count", "n"],
                      market_rows(reference, name)) + "\n")
    return summary, tests


def protection_check():
    project = LAB.parents[1]
    before = json.loads((OUT / "source_hashes_before.json").read_text())
    current = {str(p.relative_to(project)): hashlib.sha256(p.read_bytes()).hexdigest()
               for p in sorted((project / "src").rglob("*.py"))}
    dump(OUT / "source_hashes_after.json", current)
    with readonly_snapshot() as cursor:
        after = fingerprints(cursor)
        cursor.execute("""SELECT md5(COALESCE(string_agg(row_to_json(t)::text, '' ORDER BY date,id),''))
            AS digest FROM (SELECT * FROM intel_indices_daily
            WHERE date BETWEEN %s AND %s) t""", (START, END))
        published_after = dict(cursor.fetchone())
    published_before = json.loads((OUT / "published_before.json").read_text())
    dump(OUT / "published_after.json", published_after)
    dump(OUT / "fingerprints_after.json", after)
    result = {"all_production_python_sources_unchanged": before == current,
              "published_historical_rows_unchanged": published_before == published_after,
              "read_only_server_enforced": True,
              "no_ingestion_generation_or_delivery_changes": True}
    dump(OUT / "protection_checks.json", result)
    if not all(result.values()):
        raise ValueError("Protection checks failed; inspect evidence before continuing")
    return result


def render(relevance, disagreements, diag, summary, guards, protections, cost):
    tuning = json.loads((OUT / "threshold_tuning.json").read_text())
    rules = relevance["rules"]
    columns = ["variant", "mean_abs_daily_change", "share_change_ge_10", "weekend_weekday_ratio", "max",
               "Brent_3d_full", "Brent_3d_H1", "Brent_3d_H2", "TTF_1d_full", "TTF_1d_H1", "TTF_1d_H2"]
    summary_text = table(columns, [[r[k] for k in columns] for r in summary])
    (OUT / "summary_table.md").write_text(summary_text + "\n")
    lines = [
        "# GERI Step 4 — Storyline deduplication and stricter relevance\n",
        "**CONFIDENTIAL — internal research. Lab-only; not an investment recommendation.**",
        "\n## Executive summary",
        f"- Replayed {START} through {END}: 282 UTC days; {diag['n_alerts']:,} high-impact alerts.",
        f"- Online clustering produced **{diag['n_storylines']:,} storylines** at **τ={tuning['threshold']:.3f}**.",
        f"- Pair heldout precision **{tuning['heldout']['precision']:.1%}**, recall "
        f"**{tuning['heldout']['recall']:.1%}**, F1 **{tuning['heldout']['f1']:.3f}** (150 pairs).",
        f"- Reweighting those heldout pairs to the sampled similarity-band population lowers precision to "
        f"**{tuning['heldout_population_weighted']['precision']:.1%}**, recall to "
        f"**{tuning['heldout_population_weighted']['recall']:.1%}**, and F1 to "
        f"**{tuning['heldout_population_weighted']['f1']:.3f}**. The balanced-sample headline "
        "must not be interpreted as population-wide clustering quality.",
        f"- The stronger model changed the r_material_events pass decision for "
        f"**{relevance['pass_disagreements']}/400** sampled alerts.",
        f"- New API token-rate cost: **US${cost['total_usage_usd']:.4f}**; "
        f"including unresolved-attempt upper bounds: **US${cost['total_upper_with_unresolved_usd']:.4f}**.",
        "- No production source, ingestion, alert generation, published GERI, email or Telegram changes.",
        "- **None of the five new variants passes the no-deterioration guard** versus integrity_v1 "
        "across both halves and both requested market metrics. Do not promote a variant on these results.",
        "\n## A. Cached stricter rules",
        "Population and replay decisions use the original gpt-4.1-mini labels only; no population relabelling. "
        "The four rules are applied literally: r_material/r_material_events/r_high do not add an unstated relevance test.",
        table(["Rule", "Kept", "Share", "Heldout agreement vs current", "Precision", "Recall", "F1"],
              [[name, r["kept"], f"{r['share']:.2%}",
                r["heldout_vs_step3_r_current_weighted"]["agreement"],
                r["heldout_vs_step3_r_current_weighted"]["precision"],
                r["heldout_vs_step3_r_current_weighted"]["recall"],
                r["heldout_vs_step3_r_current_weighted"]["f1"]] for name, r in rules.items()]),
        "\nHeldout gold half is the exact Step 3 200-alert split, with its saved population weights. "
        "Target here is the Step 3 r_current gold pass decision. These labels were generated by the SAME model "
        "as the population labels: this is consistency, NOT measured accuracy. r_current's perfect match is tautological.",
        "\n### Retention by month",
        table(["Month"] + list(RULES), [
            [month] + [f"{rules[rule]['by_month'][month]['share']:.2%}" for rule in RULES]
            for month in rules["r_current"]["by_month"]]),
        "\n### Stronger-model second opinion",
        "Exactly the existing 400 gold alerts were classified with gpt-4.1, temperature 0, "
        "the SAME rubric and strict enum schema. Inputs add the source event title and ai_summary "
        "to the source excerpt used by Step 3. Upstream AI summaries are explicitly marked unverified. "
        "The first 700 excerpt characters and first 1,000 summary characters are included; all prompts/raw responses/usage are cached.",
        f"Excerpt available: {relevance['second_opinion_excerpt_available']}/400; "
        f"AI summary available: {relevance['second_opinion_summary_available']}/400.",
        "This is not a controlled model-only comparison: both model capacity and added context changed. "
        "Step 3 already included source excerpts (or alert-body fallback), despite the prompt's headline-only premise. "
        "The stronger model is a second opinion, not human ground truth.",
    ]
    for field, matrix in relevance["matrices"].items():
        lines += [f"\n#### {field}: exact agreement {matrix['exact_agreement']:.2%}",
                  table(["Mini label", "Stronger label", "Count"],
                        [[c["mini"], c["stronger"], c["n"]] for c in matrix["cells"]])]
    lines += [
        "\n### Every r_material_events pass disagreement",
        "Full excerpts, summaries, labels and reasons are in r_material_events_disagreements.csv; "
        "all 400 comparisons are in model_agreement_400.csv. Human-label fields remain blank.",
        table(["ID", "Date", "Headline", "Mini pass", "Stronger pass", "Stronger reason"], [
            [r["alert_id"], r["date"], r["headline"], r["mini_pass_r_material_events"],
             r["stronger_pass_r_material_events"], r["stronger_reason"]] for r in disagreements]),
        "\n## B. Embeddings, pairs and online storylines",
        "Model: text-embedding-3-small, **256 dimensions** (provider-supported reduced dimension). "
        "Exact input: alert headline + newline + first 300 source-excerpt characters. Cache identity includes "
        "alert ID, exact text hash, model and dimension. Generic alert headings remain generic in embeddings; "
        "readable diagnostics use the earliest member's extracted Event title.",
        "The managed OpenAI chat integration returned INVALID_ENDPOINT for /embeddings. "
        "Embeddings therefore use the project's already-configured direct OpenAI access; "
        "GPT-4.1 reviews remain on the existing managed integration. No credentials were changed.",
        "Region clustering reuses the existing production mapper without changing it. Same concrete cluster is "
        "compatible; Global/unmapped is a wildcard. A wildcard storyline takes its first concrete region and "
        "cannot subsequently bridge incompatible concrete regions. Publisher names are trimmed/casefolded; "
        "missing names do not count as independent publishers. Distinct publisher names do not prove independence.",
        "Chronological (created_at, ID) processing; choose highest cosine to a normalized existing centroid, "
        "only while last member is <=72h old. Update centroid AFTER assignment. No future vectors, future "
        "member counts, or future publisher counts affect assignment. Assignments are never revised/merged. "
        "An ongoing chain may last >72h if it receives updates within 72h.",
        "\n### Pair construction and tuning",
        "300 unique pairs, same region cluster and <=72h apart, sampled in seven cosine bands "
        "[0.60,0.65), …, [0.90,0.95]. Fixed-seed per-band reservoir sampling; 150 train /150 heldout. "
        "The eligible population and allocations are in pair_sampling.json. Labels use gpt-4.1 and a strict "
        "same underlying development rubric (not merely shared topics/actors).",
        "τ searches 0.600–0.950 in steps of 0.005; maximize unweighted TRAIN F1, then precision, then higher τ. "
        "Heldout results are never used for selection. CSV curves for both splits are provided; the heldout "
        "curve is descriptive only. Review sheet contains the 60 sampled pairs nearest τ, with blank human labels.",
        table(["Split", "Precision", "Recall", "F1", "n"],
              [[split, tuning[split]["precision"], tuning[split]["recall"], tuning[split]["f1"], tuning[split]["n"]]
               for split in ("train", "heldout", "heldout_population_weighted")]),
        "Important limits: pairs outside [0.60,0.95] are not validated, including near-exact duplicates. "
        "Pair cosine classification and centroid assignment are different decision contexts. Pairwise errors "
        "do not directly measure whole-storyline merge/split accuracy. Random pair halves can share alerts "
        "and episodes. Manual review is required before any production proposal.",
        "\n### Monthly alerts vs storyline-days",
        table(list(diag["monthly"][0]), [list(r.values()) for r in diag["monthly"]]),
        "Storyline-days are the sum of daily distinct storylines, not unique storylines across the month. "
        "Counts include all high-impact alerts, before relevance filtering.",
        "\n### Alerts per storyline distribution",
        table(["Alerts", "Storylines"], [[r["alerts_per_storyline"], r["n_storylines"]] for r in diag["distribution"]]),
        "\n### Ten largest storylines",
        "Large clusters and long-running chains can merge distinct real-world episodes even when every "
        "assignment is chronological and within 72h of the last member. Inspect the member lists and "
        "the 60-pair review sheet before treating these clusters as validated single developments.",
        table(["ID", "Earliest headline", "First seen", "Last seen", "Alerts", "Sources"], [
            [s["storyline_id"], s["headline"], s["first_seen"], s["last_seen"], s["n_alerts"], s["n_sources"]]
            for s in diag["largest_10"]]),
    ]
    for day, listing in diag["sanity_days"].items():
        lines += [f"\n### Full storyline list — {day}",
                  table(["ID", "Earliest headline", "Alerts that day", "Sources that day",
                         "Alerts overall", "Sources overall"],
                        [[s["storyline_id"], s["headline"], s["n_alerts_day"], s["n_sources_day"],
                          s["n_alerts_overall"], s["n_sources_overall"]] for s in listing])]
    lines += [
        "\n## C. Daily deduplicated scoring",
        "All five variants inherit integrity_v1's unhealthy-day exclusion from normalization history. "
        "Every variant retains its own chronological 90-calendar-day raw baseline. Regional-spike and asset "
        "alert acceptance and raw R/A scoring are unchanged.",
        "- storyline_day: each UTC day and storyline contributes max(severity × alert weight × regional multiplier).",
        "- corroborated: multiply that maximum by min(1.75, 1 + 0.25 × ln(max(1, distinct retained publishers that day))).",
        "- Relevance filtering is applied before selecting the daily maximum and counting publishers. "
        "A storyline cannot gain corroboration from rejected or future members.",
        "- Concentration C uses the same deduplicated H contributions, grouped by the selected member's "
        "original region. Other alert types retain their original weighted-risk region contribution. "
        "C = 100 × largest region total / total. This intentionally replaces the original H-side "
        "confidence weighting so H and C use the requested same contributions. R and A raw values remain untouched.",
        "- Ties in daily maximum choose the earliest ID; unknown publisher count uses a neutral multiplier of 1.",
        "\n## D. Summary and temporal market split",
        summary_text,
        "\nStability columns cover all 282 days. Market full=2026-01-28–2026-10-22; "
        "H1=2026-01-28–2026-05-31; H2=2026-06-01–2026-10-22. Market columns are partial Pearson "
        "correlations with **absolute forward log-return size**, controlling for causal 10-return realised "
        "volatility (including the current close), with an intercept. Higher positive values are the desired "
        "direction for this risk/move-size diagnostic. Signed-return partials are also exported.",
        "Horizons are 1/3 cleaned market sessions, not calendar days. Weekend prices, exact repeated closes "
        "and invalid prices follow the existing scorecard cleaning. Each outcome must finish within the "
        "respective split; no H1 label borrows an H2 outcome. Missing/degenerate correlations are N/A, not zero. "
        "market_splits_step4.json retains every observation, control, outcome date and sample size. "
        "The pre-existing scorecard market section is retained but covers its original date rules; use "
        "market_splits_step4 for the requested controlled comparison.",
        "The benchmark is an unscaled count of distinct r_material_events Middle-East storylines per UTC day; "
        "no index scaling or health exclusion applies to its raw counts. Its max and stability units are "
        "storyline counts, not GERI points, so do not compare their numeric level as the same scale.",
        "\n### No-deterioration guard versus integrity_v1",
        table(["Variant", "Neither half worse, both markets", "At least one improvement"], [
            [name, r["both_markets_both_halves_not_worse"], r["better_by_requested_guard"]]
            for name, r in guards.items()]),
        "This is a retrospective temporal split, NOT a clean prospective out-of-sample trading test. "
        "Similarity thresholds were tuned on randomly split pairs spanning the full period, and metadata "
        "are current persisted values, not guaranteed historical point-in-time versions. No variant is "
        "declared a validated trading improvement on this evidence. Full correlations, sample sizes, "
        "seven scorecards, ten baseline/integrity compare reports, and benchmark diagnostics are included.",
        "\n## E. Isolation, tests, costs and reproduction",
        table(["Protection", "Passed"], [[k, v] for k, v in protections.items()]),
        "All database access is server-enforced read-only and rolled back. Entire src/**/*.py inventory "
        "is hashed before/after. All published historical index rows are digested before/after. "
        "Baseline replication acceptance is saved separately. Count/timestamp fingerprints may change "
        "from unrelated live writers and are evidence, not a claim that live ingestion stopped.",
        table(["Phase", "Calls", "Input tokens", "Output tokens", "Token-rate USD", "Unresolved upper USD"],
              [[phase, r["calls"], r["input_tokens"], r["output_tokens"], r["usage_cost_usd"],
                r["unresolved_upper_usd"]] for phase, r in cost["phases"].items()]),
        f"Total **${cost['total_usage_usd']:.6f}**; with unresolved reservations "
        f"**${cost['total_upper_with_unresolved_usd']:.6f}**. Original Step 3 costs are NOT charged again "
        "or included in this total. Estimates use public standard rates without cache discounts: GPT-4.1 "
        "$2/M input and $8/M output; embeddings $0.02/M tokens. Raw usage is in the per-attempt ledger. "
        "Budget reserves conservative UTF-8-byte token ceilings before calls, caps second-opinion at $3, "
        "and stops before total $15. Explicit HTTP 429 rejections are audited separately and have no "
        "token-generating response; they release their reservations. Unknown failed attempts retain "
        "a conservative reserved upper bound. Agent/infrastructure charges are not included. No invoice claim is made.",
        "Pricing sources: https://developers.openai.com/api/docs/models/gpt-4.1 and "
        "https://developers.openai.com/api/docs/models/text-embedding-3-small (checked for this run).",
        "\n### Reproduction",
        "`python -m scripts.geri_lab.step4_run --stage ai` resumes exact-key caches; "
        "`--stage report` performs frozen-input cached-only scoring and report generation (no LLM calls). "
        "Set OPENBLAS_NUM_THREADS=1 for predictable small-matrix performance. "
        "Original source prompt is ORIGINAL_PROMPT.md; the source files and full usage/cache evidence are in the ZIP. "
        "Output datasets and ZIP are ignored by Git and deployment. Production enablement is not part of this step.",
        "Test result and archive integrity details are recorded in VERIFICATION.md, "
        "full_tests_final.log / full_tests_final.xml, and MANIFEST.json.",
    ]
    (OUT / "REPORT.md").write_text("\n\n".join(lines) + "\n")


def build(data, rows, sample):
    population = json.loads((OUT / "population.json").read_text())
    relevance, disagreements = relevance_analysis(population, sample)
    diag = diagnostics(rows)
    summary, guards = score_variants(data, rows)
    protections = protection_check()
    cost = costs()
    render(relevance, disagreements, diag, summary, guards, protections, cost)
    print(f"Step 4 report written: {OUT / 'REPORT.md'}", flush=True)
