"""Compare existing file outputs, without connecting to any database."""
import argparse
import csv
import json
from pathlib import Path
from .run import ROOT
from .scorecard import formatted
from .variants import GeriVariant


def metrics(value, prefix=""):
    result = {}
    if isinstance(value, dict):
        if "value" in value and "n" in value:
            result[prefix] = formatted(value)
        else:
            for key, child in value.items():
                result.update(metrics(child, f"{prefix}.{key}" if prefix else key))
    return result


def compare(a, b, bootstrap=False, report_root=None):
    root = Path(report_root) if report_root is not None else ROOT
    for name in (a, b):
        GeriVariant(name=name).validate()
    score_a = json.loads((root / a / "scorecard.json").read_text())
    score_b = json.loads((root / b / "scorecard.json").read_text())
    def read_series(name):
        with (root / name / "series.csv").open(newline="") as stream:
            return {row["date"]: row for row in csv.DictReader(stream)}
    series_a, series_b = read_series(a), read_series(b)
    common = sorted(series_a.keys() & series_b.keys())
    if not common:
        raise ValueError("The variants have no common replay dates.")
    differences = [(day, int(series_a[day]["geri"]), int(series_b[day]["geri"]))
                   for day in common]
    differences.sort(key=lambda row: (-abs(row[2] - row[1]), row[0]))
    left, right = metrics(score_a), metrics(score_b)
    lines = [f"# GERI Lab comparison — {a} versus {b}",
             "\n**CONFIDENTIAL — internal. Diagnostic only, not a forecast.**",
             f"\nCommon dates: {len(common)}. Left-only: {len(series_a.keys() - series_b.keys())}. "
             f"Right-only: {len(series_b.keys() - series_a.keys())}.",
             "\nScorecard metrics cover each variant's full range; compare identical "
             "ranges for a controlled experiment. The diff table uses only common dates.",
             f"\n| Metric | {a} | {b} |", "|---|---|---|"]
    for key in sorted(left.keys() | right.keys()):
        lines.append(f"| {key} | {left.get(key, 'N/A')} | {right.get(key, 'N/A')} |")
    lines += ["\n## Twenty largest daily score differences",
              f"\n| Date | {a} | {b} | Difference (right − left) |", "|---|---|---|---|"]
    for day, x, y in differences[:20]:
        lines.append(f"| {day} | {x} | {y} | {y - x:+d} |")
    if bootstrap:
        from .bootstrap import compare_scorecards, markdown
        result, samples = compare_scorecards(score_a, score_b)
        lines += ["\n", markdown(result)]
        (root / f"bootstrap_{a}_vs_{b}.json").write_text(json.dumps(result, indent=2))
        (root / f"bootstrap_draws_{a}_vs_{b}.json").write_text(json.dumps(samples))
    path = root / f"compare_{a}_vs_{b}.md"
    path.write_text("\n".join(lines) + "\n")
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("a")
    parser.add_argument("b")
    parser.add_argument("--bootstrap", action="store_true")
    parser.add_argument("--report-root", type=Path, help="Alternative scorecard/series output directory")
    args = parser.parse_args()
    try:
        print(compare(args.a, args.b, bootstrap=args.bootstrap, report_root=args.report_root))
    except (ValueError, FileNotFoundError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
