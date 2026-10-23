"""Evidence-based replication diagnostics; never repair or overwrite published data."""
from datetime import date
import json
from .replay import PILLARS, RAW_FIELDS


KNOWN = {"2026-10-22": 40, "2026-10-21": 12, "2026-07-23": 55}


def replication(series, published):
    stored = {row["date"].isoformat(): row for row in published}
    compared, unmatched, missing, october = [], [], [], []
    for row in series:
        old = stored.get(row["date"])
        if old is None:
            missing.append(row["date"])
            continue
        diff = row["geri"] - old["value"]
        item = {"date": row["date"], "published": old["value"], "replayed": row["geri"],
                "difference": diff}
        compared.append(item)
        if "2026-10-01" <= row["date"] <= "2026-10-22":
            october.append(item)
        if diff:
            components = old["components"]
            if isinstance(components, str):
                components = json.loads(components)
            reasons = []
            for pillar, field in zip(PILLARS, RAW_FIELDS):
                current = row["raw_" + pillar]
                # C is serialized to two decimals by production.
                current = round(current, 2) if pillar == "C" else current
                previous = components.get(field, 0)
                if abs(current - float(previous)) > 1e-7:
                    reasons.append(f"raw {pillar}: published {previous}, replay {current:.6g}")
            if not reasons:
                reasons.append(
                    "Raw components agree; normalization history/precision differs. "
                    "Production uses stored historical rows; lab uses its own replay."
                )
            else:
                reasons.append(
                    "Current alert-derived raw inputs differ from the saved snapshot; "
                    "backfill, edits or historical code version cannot be distinguished "
                    "from these records alone."
                )
            item["reason"] = "; ".join(reasons)
            unmatched.append(item)
    count = len(compared)
    within = sum(abs(row["difference"]) <= 1 for row in compared)
    exact = sum(row["difference"] == 0 for row in compared)
    october_exact = sum(row["difference"] == 0 for row in october)
    lookup = {row["date"]: row for row in series}
    known = {
        day: {"expected": expected, "replayed": lookup.get(day, {}).get("geri"),
              "published": stored.get(day, {}).get("value"),
              "passed": lookup.get(day, {}).get("geri") == expected
                        and stored.get(day, {}).get("value") == expected}
        for day, expected in KNOWN.items() if day in lookup
    }
    return {
        "compared_days": count, "requested_days": len(series),
        "exact_days": exact, "exact_rate": exact / count if count else None,
        "within_one_days": within, "within_one_rate": within / count if count else None,
        "missing_published_dates": missing,
        "october_days": len(october), "october_exact_days": october_exact,
        "mismatches": unmatched,
        "mismatches_gt_2": [row for row in unmatched if abs(row["difference"]) > 2],
        "known_values": known,
        "replication_passed": bool(count and within / count >= .9
                                   and len(october) == 22 and october_exact == 22),
        "known_values_passed": len(known) == 3 and all(x["passed"] for x in known.values()),
        "scope_note": "Full acceptance applies to 2026-01-14 through 2026-10-22; "
                      "shorter runs still report comparisons but do not claim full acceptance.",
    }


def render_acceptance(result):
    replica = result["replication"]
    rate = replica["within_one_rate"]
    lines = [
        "# GERI Lab acceptance results", "\n**CONFIDENTIAL — internal.**",
        f"\nFull-range acceptance passed: **{result['all_acceptance_passed']}**.",
        "\n## Replication",
        f"\nCompared {replica['compared_days']} published dates out of "
        f"{replica['requested_days']} replayed dates.",
        f"\nWithin ±1: {replica['within_one_days']}/{replica['compared_days']} "
        f"({rate:.2%})." if rate is not None else "\nWithin ±1: N/A.",
        f"\nExact: {replica['exact_days']}/{replica['compared_days']}.",
        f"\nOctober 1–22 exact: {replica['october_exact_days']}/{replica['october_days']} "
        "(22 required).",
        f"\nMissing published dates: {', '.join(replica['missing_published_dates']) or 'none'}.",
        "\n### Known values",
        "\n| Date | Expected | Published | Replayed | Pass |", "|---|---|---|---|---|",
    ]
    for day, item in replica["known_values"].items():
        lines.append(f"| {day} | {item['expected']} | {item['published']} | "
                     f"{item['replayed']} | {item['passed']} |")
    lines += ["\n### Every mismatch larger than two points",
              "\n| Date | Published | Replayed | Difference | Evidence / reason |",
              "|---|---|---|---|---|"]
    for item in replica["mismatches_gt_2"]:
        lines.append(f"| {item['date']} | {item['published']} | {item['replayed']} | "
                     f"{item['difference']:+d} | {item['reason']} |")
    if not replica["mismatches_gt_2"]:
        lines.append("| — | — | — | — | None |")
    lines += [
        "\nAll nonzero differences, including ±1 and ±2, are retained in acceptance.json.",
        "\n## Window sensitivity",
        "\nThe 91-day variant replays its own preceding raw history. It is not "
        "seeded from published components.",
        "\n```json\n" + json.dumps(result["sensitivity"], indent=2, default=str) + "\n```",
        "\n## Isolation and runtime",
        "\n```json\n" + json.dumps(result["isolation"], indent=2, default=str) + "\n```",
        f"\nMeasured end-to-end computation/report runtime: {result['runtime_seconds']:.3f} seconds; "
        f"under five minutes: {result['runtime_under_5_minutes']}.",
        "\nA repeatable-read snapshot makes all calculation inputs consistent. "
        "The after-run fingerprints use a separate fresh connection, not the same "
        "frozen snapshot. Concurrent application writes can legitimately change "
        "those fingerprints; read-only enforcement is the independent guarantee "
        "that this tool cannot issue production data mutations.",
    ]
    return "\n".join(lines) + "\n"
