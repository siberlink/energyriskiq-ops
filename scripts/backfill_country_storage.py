"""
One-off backfill for gas_storage_country_snapshots.

Uses AGSI+ date-range queries (one request per country covering the whole
window via from/to/size) and upserts each daily entry idempotently. This is
far faster than per-day requests: ~10 requests total instead of one per day.

Usage:
    python scripts/backfill_country_storage.py START_DATE END_DATE

Dates are inclusive, YYYY-MM-DD. The target database is whatever src/db/db.py
resolves (PRODUCTION_DATABASE_URL first, then DATABASE_URL). To target the dev
DB explicitly, run with `env -u PRODUCTION_DATABASE_URL ...`.
"""
import sys
import time
from datetime import date
from src.ingest.gie_agsi import (
    GIE_API_KEY,
    MAJOR_EU_COUNTRIES,
    _make_api_request,
    normalize_storage_entry,
)

def backfill_country(code: str, start: str, end: str) -> int:
    """Fetch one country's full range in a single request and upsert each day."""
    params = {"country": code.upper(), "from": start, "to": end, "size": 300}
    data = _make_api_request("", params)
    if not data or "data" not in data:
        print(f"  {code}: no data returned")
        return 0

    entries = data.get("data", [])
    from src.ingest.gas_storage_revisions import apply_revision_plan
    observations = []
    for entry in entries:
        row = normalize_storage_entry(entry, code.upper())
        if not row or not start <= row["date"] <= end:
            continue
        row["country"] = code.upper()
        observations.append({"area": code.upper(), "data": row})

    if not observations:
        print(f"  {code}: 0 days")
        return 0

    result = apply_revision_plan({"start": str(date.fromisoformat(start)), "end": end,
                                  "errors": [], "observations": observations})
    print(f"  {code}: {result['success']} observations; {result['revision_count']} revisions")
    return result["success"]


def main():
    if len(sys.argv) != 3:
        print("Usage: python scripts/backfill_country_storage.py START_DATE END_DATE")
        sys.exit(1)
    start, end = sys.argv[1], sys.argv[2]

    if not GIE_API_KEY:
        print("ERROR: GIE_API_KEY not configured")
        sys.exit(1)

    print(f"Backfilling gas_storage_country_snapshots {start} -> {end}")
    total = 0
    for code in MAJOR_EU_COUNTRIES:
        total += backfill_country(code, start, end)
        time.sleep(0.3)

    print(f"\n=== BACKFILL SUMMARY ===\ntotal rows upserted: {total}")


if __name__ == "__main__":
    main()
