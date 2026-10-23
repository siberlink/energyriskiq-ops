"""Frozen read-only inputs and exact-cache access for the Step 4 experiment."""
import hashlib
import json
from datetime import date, datetime
from pathlib import Path

from .data import readonly_snapshot, fingerprints, load
from .relevance import load_population, build_prompts, MODEL
from .variants import get_variant

LAB = Path(__file__).resolve().parents[2] / "reports/geri_lab"
OUT = LAB / "step4"
CACHE = LAB / "cache"
START, END = date(2026, 1, 14), date(2026, 10, 22)
SEED = 20261024


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, default=str, allow_nan=False) + "\n")


def journal(path):
    if not path.exists():
        return []
    with path.open() as stream:
        return [json.loads(line) for line in stream if line.strip()]


def sha(value):
    return hashlib.sha256(value.encode()).hexdigest()


def capture():
    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT / "snapshot.json").exists():
        return
    # Full production source inventory makes 'no production changes' verifiable.
    project = LAB.parents[1]
    paths = sorted((project / "src").rglob("*.py"))
    dump(OUT / "source_hashes_before.json", {
        str(p.relative_to(project)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    with readonly_snapshot() as cursor:
        before = fingerprints(cursor)
        data = load(cursor, START, END, get_variant("integrity_v1"))
        # JSON maps cannot use date keys.
        data["health"] = {day.isoformat(): value for day, value in data["health"].items()}
        dump(OUT / "snapshot.json", data)
        # Digest full historical rows, not only counts/max timestamps.
        cursor.execute("""SELECT md5(COALESCE(string_agg(row_to_json(t)::text, '' ORDER BY date,id),''))
            AS digest FROM (SELECT * FROM intel_indices_daily
            WHERE date BETWEEN %s AND %s) t""", (START, END))
        dump(OUT / "published_before.json", cursor.fetchone())
    dump(OUT / "fingerprints_before.json", before)
    population = load_population()
    dump(OUT / "population.json", population)
    if len(population) != 10894:
        raise ValueError("Historical population changed; inspect before proceeding")


def inputs():
    data = json.loads((OUT / "snapshot.json").read_text())
    for row in data["alerts"]:
        row["created_at"] = datetime.fromisoformat(row["created_at"])
    for row in data["published"]:
        row["date"] = date.fromisoformat(row["date"])
    for rows in data["markets"].values():
        for row in rows:
            row["date"] = date.fromisoformat(row["date"])
    data["warmup"] = date.fromisoformat(data["warmup"])
    data["health"] = {date.fromisoformat(k): v for k, v in data["health"].items()}
    return data


def labels_for(rows):
    records = {(r["alert_id"], r["prompt_hash"]): r for r in journal(CACHE / "relevance_labels.jsonl")}
    result = {}
    for row in rows:
        if row.get("alert_type", "HIGH_IMPACT_EVENT") != "HIGH_IMPACT_EVENT":
            continue
        id_ = row.get("alert_id", row.get("id"))
        prompt_row = {**row, "alert_body": row.get("alert_body", row.get("body"))}
        key = (id_, build_prompts(prompt_row)[1])
        record = records.get(key)
        if not record or record["model"] != MODEL:
            raise ValueError(f"Missing exact Step 3 label {id_}")
        result[id_] = record["labels"]
    return result


def cached_context(variant, rows):
    result = {"labels": labels_for(rows)}
    if variant.dedup_mode != "none":
        from .storyline import source_of
        assignments = json.loads((OUT / "assignments.json").read_text())
        result["assignments"] = {int(k): v for k, v in assignments.items()}
        manifest = json.loads((OUT / "clustering_manifest.json").read_text())
        for row in rows:
            if row["alert_type"] == "HIGH_IMPACT_EVENT":
                text = embedding_text(row)
                if manifest["text_hashes"].get(str(row["id"])) != sha(text):
                    raise ValueError(f"Stale storyline input {row['id']}")
        result["sources"] = {row["id"]: source_of(row) for row in rows}
    return result


def embedding_text(row):
    return (row.get("headline") or "") + "\n" + (row.get("event_excerpt") or "")[:300]
