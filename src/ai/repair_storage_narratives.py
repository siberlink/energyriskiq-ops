"""Owner-run only. Dry-run by default; no AI calls, sends, scoring or history replay.

python -m src.ai.repair_storage_narratives --production --confirm-production
Add --apply ONLY after owner authorization. Without --production uses development.
"""
import argparse
from copy import deepcopy
import json
import os
import re

from src.ai.storage_narrative import context_from_row, sanitize, violations


def repaired_payload(payload, context, methodology=False):
    """Change only existing text leaves; leave all scores, dates and flags intact."""
    result = deepcopy(payload)
    for key in ("interpretation", "explanation"):
        text = result.get(key)
        if isinstance(text, str) and violations(text, context, methodology):
            result[key] = sanitize(text, context, methodology)
    for key in ("components", "components_json"):
        if isinstance(result.get(key), dict):
            result[key] = repaired_payload(result[key], context, methodology)
    return result


def run(connection, *, apply=False):
    from psycopg2.extras import RealDictCursor, Json
    report = {"apply": apply, "ai_calls": 0, "sends": 0, "changes": []}
    with connection.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT max(date) AS day FROM intel_indices_daily_v12 "
                    "WHERE index_id='global:geo_energy_risk'")
        day = cur.fetchone()["day"]
        if day is None:
            raise RuntimeError("No latest GERI v1.2 index day; refusing repair")
        report["index_day"] = str(day)
        tables = (
            ("intel_indices_daily_v12", "date", True),
            ("egsi_s_daily", "index_date", False),
            ("egsi_m_daily", "index_date", False),
        )
        for table, column, methodology in tables:
            identity = (" AND index_id='global:geo_energy_risk'"
                        if table == "intel_indices_daily_v12" else "")
            cur.execute(f"SELECT max({column}) AS day FROM {table} WHERE true" + identity)
            if cur.fetchone()["day"] != day:
                report["changes"].append({"table": table, "skipped": "latest day differs"})
                continue
            cur.execute(f"SELECT * FROM {table} WHERE {column}=%s" + identity +
                        (" FOR UPDATE" if apply else ""), (day,))
            rows = cur.fetchall()
            cur.execute(
                "SELECT * FROM gas_storage_snapshots WHERE date " +
                ("= %s" if table == "egsi_s_daily" else "<= %s") +
                " ORDER BY date DESC LIMIT 1", (day,))
            storage = cur.fetchone()
            context = context_from_row(dict(storage)) if storage else None
            for original in rows:
                original = dict(original)
                repaired = repaired_payload(original, context, methodology)
                changed = [key for key in original if original[key] != repaired[key]]
                if not changed:
                    continue
                allowed = {"interpretation", "explanation", "components", "components_json"}
                if set(changed) - allowed:
                    raise RuntimeError("Refusing non-narrative field changes")
                report["changes"].append({
                    "table": table, "id": original["id"], "context": context,
                    "before": {key: original[key] for key in changed},
                    "after": {key: repaired[key] for key in changed},
                    "other_fields_unchanged": True,
                })
                if apply:
                    values = [Json(repaired[k]) if isinstance(repaired[k], dict)
                              else repaired[k] for k in changed]
                    cur.execute(f"UPDATE {table} SET " +
                                ",".join(f"{key}=%s" for key in changed) +
                                " WHERE id=%s", (*values, original["id"]))
                    cur.execute(f"SELECT * FROM {table} WHERE id=%s", (original["id"],))
                    if dict(cur.fetchone()) != repaired:
                        raise RuntimeError("Post-write equality failed; transaction will roll back")
        cur.execute("SELECT * FROM gas_storage_snapshots WHERE date<=%s "
                    "ORDER BY date DESC LIMIT 1", (day,))
        storage = cur.fetchone()
        context = context_from_row(dict(storage)) if storage else None
        cur.execute("SELECT * FROM daily_digest_ai_cache WHERE cache_key LIKE %s "
                    "AND cache_key LIKE '%%:geri_v1.2%%' AND cache_key ~ '^v1:[0-9]+:'" +
                    (" FOR UPDATE" if apply else ""), (f"%:{day}:%",))
        for row in cur.fetchall():
            key = row["cache_key"]
            if any(s in key for s in (":input-indices", ":narrative-status")):
                continue
            if not violations(row["narrative"], context, True):
                continue
            new = sanitize(row["narrative"], context, True)
            report["changes"].append({"table": "daily_digest_ai_cache", "key": key,
                                      "before": row["narrative"], "after": new,
                                      "other_fields_unchanged": True})
            if apply:
                cur.execute("UPDATE daily_digest_ai_cache SET narrative=%s WHERE cache_key=%s",
                            (new, key))
                cur.execute("SELECT * FROM daily_digest_ai_cache WHERE cache_key=%s", (key,))
                expected = dict(row)
                expected["narrative"] = new
                if dict(cur.fetchone()) != expected:
                    raise RuntimeError("Cache equality failed; transaction will roll back")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--production", action="store_true")
    parser.add_argument("--confirm-production", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.production and not args.confirm_production:
        parser.error("--production requires --confirm-production, including dry-run")
    import psycopg2
    variable = "PRODUCTION_DATABASE_URL" if args.production else "DATABASE_URL"
    if not os.getenv(variable):
        raise RuntimeError(f"{variable} is required; no target fallback is permitted")
    conn = psycopg2.connect(os.environ[variable])
    conn.set_session(readonly=not args.apply, autocommit=False)
    try:
        report = run(conn, apply=args.apply)
        if args.apply:
            conn.commit()
        else:
            conn.rollback()
        print(json.dumps(report, default=str, indent=2))
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
