"""Reproducible Step 4 pipeline. API use is confined to three cached lab stages."""
import argparse
import csv
import json
from pathlib import Path
import shutil

from src.geri.compute import extract_event_title_from_body
from .step4_data import OUT, LAB, CACHE, START, END, capture, inputs, labels_for, dump, journal, sha, embedding_text
from .step4_ai import Budget, second_opinion, embeddings, pair_labels, costs
from .step4_pairs import sample_pairs, tune
from .storyline import online_cluster


def prepare():
    capture()
    data = inputs()
    rows = [row for row in data["alerts"] if row["alert_type"] == "HIGH_IMPACT_EVENT"]
    for row in rows:
        row["display_headline"] = extract_event_title_from_body(row.get("body")) or row["headline"]
    population = {r["alert_id"]: r for r in json.loads((OUT / "population.json").read_text())}
    sample = journal(LAB / "gold_set/sampled_alerts.jsonl")
    split = {}
    with (LAB / "gold_set/gold_set.csv").open() as stream:
        for row in csv.DictReader(stream):
            split[int(row["alert_id"])] = {
                "evaluation_split": row["evaluation_split"], "eval_weight": float(row["eval_weight"])}
    for row in sample:
        # Preserve exact Step 3 gold membership, augment with frozen source summary.
        source = population[row["alert_id"]]
        row["ai_summary"] = source.get("ai_summary")
        row.update(split[row["alert_id"]])
    dump(OUT / "gold_400_inputs.json", sample)
    return data, rows, sample


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("ai", "report", "all"), default="all")
    args = parser.parse_args()
    data, rows, sample = prepare()
    if args.stage in ("ai", "all"):
        budget = Budget()
        try:
            second_opinion(sample, budget)
            vectors = embeddings(rows, budget)
            pair_path = OUT / "pairs_sample.json"
            if pair_path.exists():
                pairs = json.loads(pair_path.read_text())
            else:
                pairs = sample_pairs(rows, vectors)
                dump(pair_path, pairs)
            lookup = {r["id"]: r for r in rows}
            labels = pair_labels(pairs, lookup, budget)
            threshold, _ = tune(pairs, labels, lookup)
            assignments, stories = online_cluster(rows, vectors, threshold)
            dump(OUT / "assignments.json", assignments)
            dump(OUT / "storylines.json", stories)
            dump(OUT / "clustering_manifest.json", {
                "threshold": threshold, "embedding_model": "text-embedding-3-small", "dimensions": 256,
                "algorithm": "online normalized centroid, highest cosine; 72h since last member; compatible region",
                "text_hashes": {r["id"]: sha(embedding_text(r)) for r in rows},
                "alert_snapshot_sha256": data["alert_sha256"],
                "no_future_members_in_assignment": True,
            })
            print(f"Clustering: {len(rows)} alerts -> {len(stories)} storylines, tau={threshold}", flush=True)
        finally:
            print(json.dumps(costs(), indent=2), flush=True)
    if args.stage in ("report", "all"):
        from .step4_report import build
        build(data, rows, sample)


if __name__ == "__main__":
    main()
