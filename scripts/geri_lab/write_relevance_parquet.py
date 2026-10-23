"""Consolidate the crash-safe labeling journal into the requested Parquet cache.

Run with an interpreter that has PyArrow; independent of the app's Python runtime.
"""
import json
from pathlib import Path


def main():
    import pyarrow as pa
    import pyarrow.parquet as pq
    root = Path(__file__).resolve().parents[2] / "reports/geri_lab/cache"
    unique = {}
    with (root / "relevance_labels.jsonl").open() as stream:
        for line in stream:
            item = json.loads(line)
            unique[(item["alert_id"], item["prompt_hash"])] = item
    records = []
    for key in sorted(unique):
        item = dict(unique[key])
        item.update(item.pop("labels"))
        records.append(item)
    columns = sorted(set().union(*(set(record) for record in records)))
    table = pa.Table.from_pylist([{key: record.get(key) for key in columns} for record in records])
    table = table.replace_schema_metadata({
        b"cache_key": b"alert_id,prompt_hash",
        b"journal": b"relevance_labels.jsonl (append-only crash-safe request cache)",
    })
    temp = root / "relevance_labels.parquet.tmp"
    pq.write_table(table, temp, compression="zstd")
    temp.replace(root / "relevance_labels.parquet")
    assert pq.read_table(root / "relevance_labels.parquet").num_rows == len(unique)
    print(f"Verified Parquet cache: {len(unique)} unique alert/prompt keys")


if __name__ == "__main__":
    main()
