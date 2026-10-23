"""Deterministic similarity-stratified pairs, held-out threshold tuning and exports."""
from collections import Counter, defaultdict
import csv
from datetime import timedelta
import random

import numpy as np

from .step4_data import SEED, OUT, dump
from .storyline import region_of

BANDS = [(round(.60 + .05 * i, 2), round(.65 + .05 * i, 2)) for i in range(7)]


def write_csv(path, rows):
    if not rows:
        path.write_text("")
        return
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: __import__("json").dumps(v, default=str) if isinstance(v, (dict, list))
                             else v for k, v in row.items()})


def sample_pairs(rows, vectors):
    rng = random.Random(SEED)
    vectors = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
    reservoirs, counts = defaultdict(list), Counter()
    regions = [region_of(row) for row in rows]
    begin = 0
    for right in range(len(rows)):
        while rows[right]["created_at"] - rows[begin]["created_at"] > timedelta(hours=72):
            begin += 1
        if begin == right:
            continue
        similarities = vectors[begin:right] @ vectors[right]
        candidates = np.flatnonzero((similarities >= .60) & (similarities <= .95))
        for offset in candidates:
            left = begin + int(offset)
            if regions[left] != regions[right]:
                continue
            sim = float(similarities[offset])
            band = min(6, int((sim - .60) / .05))
            counts[band] += 1
            item = {"pair_id": f"{rows[left]['id']}-{rows[right]['id']}",
                    "left_id": rows[left]["id"], "right_id": rows[right]["id"],
                    "cosine": sim, "band": band, "region_cluster": regions[right],
                    "hours_apart": (rows[right]["created_at"] - rows[left]["created_at"]).total_seconds() / 3600}
            # A bounded uniform reservoir per band avoids storing millions of pairs.
            reservoir = reservoirs[band]
            if len(reservoir) < 300:
                reservoir.append(item)
            else:
                position = rng.randrange(counts[band])
                if position < 300:
                    reservoir[position] = item
    allocation = {b: min(counts[b], 43 if b < 6 else 42) for b in range(7)}
    while sum(allocation.values()) < 300:
        eligible = [b for b in range(7) if allocation[b] < counts[b]]
        if not eligible:
            raise ValueError("Insufficient eligible similarity pairs")
        allocation[min(eligible, key=lambda b: (allocation[b], b))] += 1
    pairs, training_count = [], 0
    for band in range(7):
        selected = rng.sample(reservoirs[band], allocation[band])
        rng.shuffle(selected)
        # Alternate odd-cell rounding so train/test each have exactly 150.
        ntrain = allocation[band] // 2
        if allocation[band] % 2 and training_count <= len(pairs) / 2:
            ntrain += 1
        for i, pair in enumerate(selected):
            pairs.append({**pair, "split": "train" if i < ntrain else "heldout",
                          "stratum_population": counts[band],
                          "sample_weight": counts[band] / allocation[band]})
        training_count += ntrain
    if training_count != 150:
        raise AssertionError(f"Pair split is {training_count}, expected 150")
    dump(OUT / "pair_sampling.json", {
        "seed": SEED, "bands": [{"band": b, "low": low, "high": high,
                                 "population": counts[b], "sampled": allocation[b]}
                                for b, (low, high) in enumerate(BANDS)],
        "training_pairs": training_count, "heldout_pairs": 300 - training_count,
        "target_population": "same-region pairs <=72h apart with cosine in [0.60,0.95]",
    })
    return pairs


def pair_metrics(rows, threshold, weighted=False):
    tp = fp = fn = tn = 0.
    for row in rows:
        predicted, actual = row["cosine"] >= threshold, row["same_development"]
        weight = row["sample_weight"] if weighted else 1.
        if predicted and actual:
            tp += weight
        elif predicted:
            fp += weight
        elif actual:
            fn += weight
        else:
            tn += weight
    precision = tp / (tp + fp) if tp + fp else 0.
    recall = tp / (tp + fn) if tp + fn else 0.
    return {"precision": precision, "recall": recall,
            "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.,
            "tp": tp, "fp": fp, "fn": fn, "tn": tn, "n": len(rows)}


def tune(pairs, labels, lookup):
    labelled = [{**p, **labels[p["pair_id"]]["labels"]} for p in pairs]
    train = [p for p in labelled if p["split"] == "train"]
    heldout = [p for p in labelled if p["split"] == "heldout"]
    thresholds = [round(.60 + i * .005, 3) for i in range(71)]
    curve = [{"threshold": threshold, **pair_metrics(train, threshold)}
             for threshold in thresholds]
    best = max(curve, key=lambda p: (p["f1"], p["precision"], p["threshold"]))
    threshold = best["threshold"]
    result = {
        "threshold": threshold, "selection": "train F1, then precision, then higher threshold",
        "train": pair_metrics(train, threshold), "heldout": pair_metrics(heldout, threshold),
        "heldout_population_weighted": pair_metrics(heldout, threshold, True),
        "curve_train": curve,
        "curve_heldout_descriptive_only": [
            {"threshold": t, **pair_metrics(heldout, t)} for t in thresholds],
    }
    dump(OUT / "threshold_tuning.json", result)
    write_csv(OUT / "threshold_curve_train.csv", curve)
    write_csv(OUT / "threshold_curve_heldout.csv", result["curve_heldout_descriptive_only"])
    def expanded(pair):
        left, right = lookup[pair["left_id"]], lookup[pair["right_id"]]
        return {**pair, "left_headline": left["display_headline"],
                "right_headline": right["display_headline"],
                "left_created_at": str(left["created_at"]), "right_created_at": str(right["created_at"]),
                "left_excerpt": left.get("event_excerpt"), "right_excerpt": right.get("event_excerpt"),
                "human_same_development": ""}
    write_csv(OUT / "labelled_pairs_300.csv", [expanded(p) for p in labelled])
    review = sorted(labelled, key=lambda p: (abs(p["cosine"] - threshold), p["pair_id"]))[:60]
    write_csv(OUT / "pair_review_60.csv", [expanded(p) for p in review])
    return threshold, result
