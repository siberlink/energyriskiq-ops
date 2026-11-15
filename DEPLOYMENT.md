# Storage history rollout — owner controlled

No build, website publish, Cloud job update or send has been performed.

## Prerequisites

- Review development counts, provider-gap verification and EU/DE/IT spot checks.
- Owner approves production DATA loading separately; it is not authorized yet.
- Replit manages this project's production schema: prepare development schema,
  inspect the additive Publish diff, and use the supported Publish migration path.
  Do not use a production-only migration or startup DDL. An empty pre-Publish
  diff is not possible while these additive changes await their first Publish.
- Backfill never runs at startup, during Publish or in Cloud schedules.

## Order

1. Agree the schema-only rollout and production backfill approval.
2. Owner publishes website with required schema and production history ready.
   The old Cloud Daily image continues its existing local writer until changed;
   do NOT manually invoke the new endpoint while that writer is running.
3. In the prepared ops source commit run build.sh only when explicitly approved.
   It bakes the actual checkout commit/image provenance. It never updates jobs.
4. Between scheduled executions, owner updates ONLY energyriskiq-daily to the new
   image. Keep selectors, all secrets, INCLUDE_DELIVERY and other settings unchanged.
   No ingestion, Alerts, intraday or metadata update is required.
5. Cloud Daily storage capture now calls WEBSITE_BASE_URL/internal/run/storage-pipeline.
   It does not acquire the database's gas_storage_capture lock locally (the
   website owns that lock); it does not fetch AGSI or write storage locally.
6. Acceptance after the next run: one website pipeline audit, 77 observations,
   correct provenance, same legacy date contract and v1 scores, new history current,
   no second provider writer, GERI/EERI/EGSI unchanged, no automatic backfill.

## Failure and rollback

- A failed HTTP response or incomplete observation count fails the storage stage;
  no local fallback writer is invoked.
- HTTP requests have no automatic POST retry. Check the website audit after a
  timeout before a manual retry; transactions and shared locks protect writes.
- Restore the previous Daily image only between executions; stop manual endpoint
  calls first. Legacy tables and v1 columns remain present and compatible.
- No v2 score becomes an entitlement, index input, page score or alert gate.

## Units

New canonical flows: GWh/day, net = injection - withdrawal.
Legacy injection_twh/withdrawal_twh contain misnamed provider GWh/day values:
leave them unchanged. Existing refill_speed_7d/withdrawal_rate_7d semantics are
retained for v1; the public net-volume-change estimator is separately labelled.
