---
name: Gas storage ingestion paths
description: EU-aggregate vs per-country storage are populated by two separate daily code paths; one being current does not imply the other is.
---

# Gas storage ingestion: two independent paths

There are TWO separate tables and TWO separate daily writers for European gas storage:

- **EU aggregate** (`gas_storage_snapshots`): written daily by the GitHub Action
  `alerts_engine_v2.yml` step that POSTs `/internal/run/gas-storage-capture`
  (`run_gas_storage_capture` → `backfill_snapshots` funcs). Reliable, runs ~22:0X UTC daily.
- **Per-country** (`gas_storage_country_snapshots`, `level='country'`, 10 countries
  DE/FR/IT/AT/PL/BE/NL/CZ/HU/SK): written ONLY inside alerts Phase A
  (`runner --phase A` → `generate_global_alert_events` → `generate_storage_risk_events`
  → `ingest_country_storage`). Phase A cron is every 10 min.

**Why this matters:** the EU-aggregate table being up to date does NOT mean the country
table is. They are different code paths. If country data stalls while EU is current, the
country path (Phase A / `ingest_country_storage`) is the thing to check, not the capture endpoint.

**Field-name gotcha:** `fetch_country_storage_data()` returns the storage percentage under
key `full_percent` (NOT `storage_percent`). `ingest_country_storage` writes `full_percent`
into the `storage_percent` column. Reading `.get("storage_percent")` off the fetch result
gives None — that is a test mistake, not missing data.

**Source lag:** AGSI+ publishes country day-end data with ~1-2 day lag. The date-range API
(used by `scripts/backfill_country_storage.py`) only returns confirmed days; the per-day
fetch can return a fallback/latest value for not-yet-published dates. Trust the date-range
backfill for "what is actually published."

**Backfill tool:** `PYTHONPATH=/home/runner/workspace python scripts/backfill_country_storage.py START END`
(inclusive YYYY-MM-DD) idempotently upserts country rows; targets PRODUCTION_DATABASE_URL via db.py.

**How to apply:** when asked to verify country storage freshness, check the country table's
MAX(date) and created_at cadence separately from the EU table. A single backfill `created_at`
across all rows = a one-off load, not daily ingestion — confirm the deployed app contains the
country-ingestion code and that Phase A is running.
