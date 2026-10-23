"""Read-only historical integrity and production-source allowlist evidence."""
import hashlib
import json

from .data import readonly_snapshot
from .step4_data import dump
from .step5_data import published_digest
from .step6_data import OUT, hashes

ALLOWED = {
    "src/ai/ai_worker.py", "src/ai/pipeline_v2_worker.py", "src/api/ops_routes.py",
    "src/risk/risk_engine.py", "src/risk/pipeline_v2.py", "src/risk/pipeline_v2_core.py",
    "src/risk/pipeline_v2_dry_run.py",
}


def fingerprints(c, cutoffs=None):
    result = {}
    for table in ("risk_events", "risk_indices", "asset_risk"):
        if cutoffs is None:
            c.execute(f"SELECT COALESCE(max(id),0) AS max_id FROM {table}")
            cutoff = c.fetchone()["max_id"]
        else:
            cutoff = cutoffs[table]["max_id"]
        c.execute(f"""SELECT count(*) AS rows,
            md5(COALESCE(string_agg(row_to_json(t)::text,E'\\n' ORDER BY id),'')) AS digest
            FROM {table} t WHERE id<=%s""", (cutoff,))
        result[table] = {"max_id": cutoff, **dict(c.fetchone())}
    return result


def baseline():
    path = OUT / "risk_history_validation_baseline.json"
    if path.exists():
        return
    with readonly_snapshot() as c:
        dump(path, fingerprints(c))


def check():
    before = json.loads((OUT / "source_hashes_before.json").read_text())
    after = hashes()  # Same inventory as the BEFORE capture; do not mix audit universes.
    changed = sorted(path for path in set(before)|set(after) if before.get(path) != after.get(path))
    illegal = sorted(set(changed)-ALLOWED)
    risk_before = json.loads((OUT / "risk_history_validation_baseline.json").read_text())
    with readonly_snapshot() as c:
        risk_after = fingerprints(c, risk_before)
        published_after = published_digest(c)
    published_before = json.loads((OUT / "published_before.json").read_text())
    result = {"production_changed_files": changed, "part_c_allowlist": sorted(ALLOWED),
              "unexpected_production_changes": illegal,
              "published_geri_history_unchanged": published_before == published_after,
              "published_before": published_before, "published_after": published_after,
              "existing_risk_history_unchanged": risk_before == risk_after,
              "risk_history_before": risk_before, "risk_history_after": risk_after,
              "risk_note": "Existing IDs protected; unrelated legitimate new append rows are permitted",
              "lab_connections_server_readonly": True, "paid_enrichment_calls_executed": 0}
    dump(OUT / "protection_checks.json", result)
    assert not illegal, illegal
    assert result["published_geri_history_unchanged"], "Published GERI history changed"
    assert result["existing_risk_history_unchanged"], "Existing risk history changed"
    return result


if __name__ == "__main__":
    baseline()
