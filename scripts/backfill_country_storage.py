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
import json
import sys
import time

from psycopg2.extras import execute_values

from src.db.db import get_cursor
from src.ingest.gie_agsi import (
    GIE_API_KEY,
    MAJOR_EU_COUNTRIES,
    COUNTRY_NAMES,
    _make_api_request,
)

UPSERT_SQL = """
    INSERT INTO gas_storage_country_snapshots
    (date, level, country_code, country_name, operator_code, facility_code,
     storage_percent, gas_in_storage_twh, working_gas_volume_twh,
     injection_twh, withdrawal_twh, trend, raw_data)
    VALUES %s
    ON CONFLICT (date, level, country_code, operator_code, facility_code)
    DO UPDATE SET
        country_name = EXCLUDED.country_name,
        storage_percent = EXCLUDED.storage_percent,
        gas_in_storage_twh = EXCLUDED.gas_in_storage_twh,
        working_gas_volume_twh = EXCLUDED.working_gas_volume_twh,
        injection_twh = EXCLUDED.injection_twh,
        withdrawal_twh = EXCLUDED.withdrawal_twh,
        trend = EXCLUDED.trend,
        raw_data = EXCLUDED.raw_data
"""

ROW_TEMPLATE = "(%s, 'country', %s, %s, '', '', %s, %s, %s, %s, %s, %s, %s)"


def _f(entry, key):
    try:
        return float(entry.get(key, 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def backfill_country(code: str, start: str, end: str) -> int:
    """Fetch one country's full range in a single request and upsert each day."""
    params = {"country": code.upper(), "from": start, "to": end, "size": 300}
    data = _make_api_request("", params)
    if not data or "data" not in data:
        print(f"  {code}: no data returned")
        return 0

    entries = data.get("data", [])
    name = COUNTRY_NAMES.get(code.upper(), code.upper())
    values = []
    for entry in entries:
        date_str = entry.get("gasDayStart")
        if not date_str:
            continue
        row = {
            "country": code.upper(),
            "date": date_str,
            "gas_in_storage_twh": _f(entry, "gasInStorage"),
            "full_percent": _f(entry, "full"),
            "injection_twh": _f(entry, "injection"),
            "withdrawal_twh": _f(entry, "withdrawal"),
            "working_gas_volume_twh": _f(entry, "workingGasVolume"),
            "trend": _f(entry, "trend"),
        }
        values.append((
            row["date"],
            code.upper(),
            name,
            row["full_percent"],
            row["gas_in_storage_twh"],
            row["working_gas_volume_twh"],
            row["injection_twh"],
            row["withdrawal_twh"],
            row["trend"],
            json.dumps(row),
        ))

    if not values:
        print(f"  {code}: 0 days")
        return 0

    with get_cursor() as cursor:
        execute_values(cursor, UPSERT_SQL, values, template=ROW_TEMPLATE)

    print(f"  {code}: {len(values)} days upserted "
          f"({entries[-1].get('gasDayStart')} -> {entries[0].get('gasDayStart')})")
    return len(values)


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
