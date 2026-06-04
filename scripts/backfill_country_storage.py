"""
One-off backfill for gas_storage_country_snapshots.

Iterates each gas day in [start, end] and calls ingest_country_storage(date_str),
which fetches per-country AGSI+ storage and upserts idempotently.

Usage:
    python scripts/backfill_country_storage.py START_DATE END_DATE

Dates are inclusive, YYYY-MM-DD. The target database is whatever src/db/db.py
resolves (PRODUCTION_DATABASE_URL first, then DATABASE_URL). To target the dev
DB explicitly, run with `env -u PRODUCTION_DATABASE_URL ...`.
"""
import sys
from datetime import datetime, timedelta

from src.ingest.gie_agsi import ingest_country_storage


def daterange(start: datetime, end: datetime):
    cur = start
    while cur <= end:
        yield cur
        cur += timedelta(days=1)


def main():
    if len(sys.argv) != 3:
        print("Usage: python scripts/backfill_country_storage.py START_DATE END_DATE")
        sys.exit(1)

    start = datetime.strptime(sys.argv[1], "%Y-%m-%d")
    end = datetime.strptime(sys.argv[2], "%Y-%m-%d")

    totals = {"days": 0, "success": 0, "failed": 0, "skipped": 0}

    for day in daterange(start, end):
        date_str = day.strftime("%Y-%m-%d")
        res = ingest_country_storage(date_str=date_str)
        totals["days"] += 1
        totals["success"] += res.get("success", 0)
        totals["failed"] += res.get("failed", 0)
        totals["skipped"] += res.get("skipped", 0)
        print(
            f"{date_str} (data_date={res.get('data_date')}): "
            f"success={res.get('success')} failed={res.get('failed')} "
            f"skipped={res.get('skipped')} countries={res.get('countries')}"
        )

    print("\n=== BACKFILL SUMMARY ===")
    print(
        f"days={totals['days']} rows_upserted={totals['success']} "
        f"failed={totals['failed']} skipped={totals['skipped']}"
    )


if __name__ == "__main__":
    main()
