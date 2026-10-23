"""Paired calendar-week block bootstrap of partial-correlation differences."""
from datetime import date
import json
from pathlib import Path

import numpy as np

SEED = 20261025
RESAMPLES = 1000


def partial_sums(sums):
    """Vectorized partial Pearson correlation from n and nine sufficient sums."""
    n, sx, sy, sz, sxx, syy, szz, sxy, sxz, syz = np.asarray(sums).T
    with np.errstate(divide="ignore", invalid="ignore"):
        vx, vy, vz = sxx - sx * sx / n, syy - sy * sy / n, szz - sz * sz / n
        xy, xz, yz = sxy - sx * sy / n, sxz - sx * sz / n, syz - sy * sz / n
        rx, ry = vx - xz * xz / vz, vy - yz * yz / vz
        result = (xy - xz * yz / vz) / np.sqrt(rx * ry)
    valid = (n >= 4) & (vz > 1e-18) & (rx > 1e-18) & (ry > 1e-18)
    return np.where(valid, np.clip(result, -1, 1), np.nan)


def weekly_bootstrap(reference, candidate, seed=SEED, resamples=RESAMPLES):
    ref = {(r["date"], r["outcome_date"]): r for r in reference}
    other = {(r["date"], r["outcome_date"]): r for r in candidate}
    keys = sorted(ref.keys() & other.keys())
    if len(keys) < 4:
        return {"n": len(keys), "n_weeks": 0, "point_difference": None,
                "ci90_low": None, "ci90_high": None, "valid_resamples": 0}, []
    weeks = sorted({date.fromisoformat(day).isocalendar()[:2] for day, _ in keys})
    week_index = {week: i for i, week in enumerate(weeks)}
    a, b = np.zeros((len(weeks), 10)), np.zeros((len(weeks), 10))
    for key in keys:
        old, new = ref[key], other[key]
        if (abs(old["forward_log_return"] - new["forward_log_return"]) > 1e-12 or
                abs(old["realised_vol_10"] - new["realised_vol_10"]) > 1e-12):
            raise ValueError("Paired bootstrap outcome/control inputs differ")
        y, z = abs(old["forward_log_return"]), old["realised_vol_10"]
        index = week_index[date.fromisoformat(key[0]).isocalendar()[:2]]
        for array, x in ((a, old["signal"]), (b, new["signal"])):
            array[index] += (1, x, y, z, x*x, y*y, z*z, x*y, x*z, y*z)
    rng = np.random.default_rng(seed)
    counts = rng.multinomial(len(weeks), np.full(len(weeks), 1 / len(weeks)), size=resamples)
    # Identical sampled weeks for the two signals: preserve pairing, controls and serial blocks.
    delta = partial_sums(counts @ b) - partial_sums(counts @ a)
    finite = delta[np.isfinite(delta)]
    point = partial_sums(b.sum(axis=0)[None, :])[0] - partial_sums(a.sum(axis=0)[None, :])[0]
    low, high = np.percentile(finite, [5, 95]) if len(finite) else (np.nan, np.nan)
    def clean(value):
        return float(value) if np.isfinite(value) else None
    return {"n": len(keys), "n_weeks": len(weeks), "point_difference": clean(point),
            "ci90_low": clean(low), "ci90_high": clean(high), "valid_resamples": len(finite),
            "requested_resamples": resamples, "seed": seed,
            "block_definition": "non-overlapping ISO calendar weeks, sampled with replacement",
            "reference_partial": clean(partial_sums(a.sum(axis=0)[None, :])[0]),
            "candidate_partial": clean(partial_sums(b.sum(axis=0)[None, :])[0])}, [
                clean(value) for value in delta]


def compare_scorecards(reference, candidate):
    result, samples = [], {}
    for mi, market in enumerate(("Brent", "TTF")):
        for hi, horizon in enumerate(("1", "3")):
            for si, split in enumerate(("full", "H1", "H2")):
                left = reference["market_splits_step4"][market]["splits"][split][horizon]["observations"]
                right = candidate["market_splits_step4"][market]["splits"][split][horizon]["observations"]
                metric, draws = weekly_bootstrap(left, right, SEED + mi*100 + hi*10 + si)
                result.append({"market": market, "horizon_sessions": int(horizon), "split": split, **metric})
                samples[f"{market}_{horizon}_{split}"] = draws
    selected = [r for r in result if r["split"] in ("H1", "H2") and (
        (r["market"], r["horizon_sessions"]) in (("Brent", 3), ("TTF", 1)))]
    acceptable = len(selected) == 4 and all(
        r["ci90_low"] is not None and r["ci90_low"] > -.05 for r in selected)
    improvement = acceptable and any(r["ci90_low"] > 0 for r in selected)
    return {"reference": reference["variant"], "candidate": candidate["variant"],
            "cells": result, "acceptable": acceptable, "improvement": improvement,
            "rule": "Brent 3d and TTF 1d H1/H2 all lower90 > -0.05; improvement also any lower90 > 0",
            "interval": "paired weekly block percentile 90% interval; 1,000 draws"}, samples


def markdown(result):
    def value(x):
        return "N/A" if x is None else f"{x:.4f}"
    lines = ["## Weekly paired block-bootstrap comparison",
             f"\nReference: {result['reference']}; candidate: {result['candidate']}.",
             f"\nAcceptable: **{result['acceptable']}**. Improvement: **{result['improvement']}**.",
             "\n| Market | Sessions | Split | Difference | 90% lower | 90% upper | n | Weeks |",
             "|---|---|---|---|---|---|---|---|"]
    for row in result["cells"]:
        lines.append(f"| {row['market']} | {row['horizon_sessions']} | {row['split']} | "
                     f"{value(row['point_difference'])} | {value(row['ci90_low'])} | "
                     f"{value(row['ci90_high'])} | {row['n']} | {row['n_weeks']} |")
    return "\n".join(lines) + "\n"
