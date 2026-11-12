# EERI website trigger + bounded, bulk Alerts fanout

**Source only, pending owner review. No build or deploy performed.**

One commit directly on `a313fb38066527129e7f205b4f19f8dcdb5a818a`.
One image: `eeri-fanout-20261112-<first-12-of-reviewed-commit>`.
Existing build helper remains build-only, requires the full reviewed commit
and explicit `build` confirmation, and verifies its direct parent.

## Website first

Publish the separately reviewed website change and apply ONLY the EERI
backup workflow patch on the GitHub default branch:

- `X-Runner-Token` validated against existing `INTERNAL_RUNNER_TOKEN`.
- Shared per-date serialization; insert-only repair from frozen EGSI-M payload.
- Backup at 03:00 UTC for seven days.
- Secret bindings synchronized by owner, verified without printing values.

A local copy of a workflow or a commit on this image-source branch does not
activate the default-branch Actions workflow. Do not change any other workflow.
The owner already disabled the three obsolete workflows; do not re-enable them.
The owner will handle Intraday/Metadata after checking their Cloud counterparts.

Use `scripts/check_website_runner_auth.py` from the exact Daily secret binding
to perform an authenticated read-only GET. It prints only HTTP status, never
response contents, headers, token fingerprints or values. The updated backup
has the same preflight. The compute POST's eventual success is a separate
exact-date check; do not use a compute POST just to compare secrets.

## Daily stage and failure contract

Order: market_data, oil_price, gas_storage, geri, **eeri_egsi_m**, lng_price,
egsi_s, daily_report, delivery.

`WEBSITE_BASE_URL=https://energyriskiq.com` is a new non-secret on **Daily only**.
Reuse `INTERNAL_RUNNER_TOKEN`; no new credential.

Connect/read timeout 10/90 seconds, three attempts maximum, backoff 10/30
seconds (approximately 340 seconds worst-case network timeout budget).
No redirects or credential forwarding. HTTP 200 with `success:false` fails.
Validate exact UTC closed-day pair, EERI model `eeri_ttf_v3`, finite values and
successful stored/existing/repaired statuses. Retry recognized transient
transport/server/busy errors, not authentication or permanent data errors.

A failed pair stage yields degraded Daily/non-zero exit; report/delivery
continue if GERI persisted, using latest available EERI/EGSI-M and recording
their actual dates/values and stale flags. No retired ops EERI/EGSI-M writer
is restored. Missing GERI still blocks report/delivery.

Daily report output/warm results include current observation metadata.
Generated/fallback narrative inputs are recorded as JSON sidecars in the
existing narrative cache, with no schema change. A cached narrative without a
sidecar has unknown narrative input provenance, never silently relabeled.
Delivery audit JSON in existing `last_error` records each actual index date,
value, target date and stale status, alongside existing AI/GERI provenance.
Decimal values are normalized before JSON serialization.

## Fanout

Keep the original decision loop and the same defaults/filter order/skip
counters. A run-local ContextVar supplies bulk user/plan/preference/existing
delivery/quota reads. Snapshot is destroyed before send-time checks.
One connection; short committed reservation transactions, never a transaction
held across provider sends. UTC-day count cache refreshes on rollover.

Instant quota count and insert use a per-user/channel/kind/day transaction
advisory lock, current DB count and durable unique conflict protection.
The same last slot cannot be reserved by competing snapshots.
Digest fanout rows are message items, not aggregate-message quota units;
preserve their legacy staging semantics. Aggregate digest claims are checked
at send time using the already atomically claimed sending rows and current
plan limit, independently per user/channel/day.
Send-time checks count today's actual sends plus ordered in-flight claims even
when those records were queued before midnight; creation-time snapshots cannot
authorize extra sends from an older backlog.

Both instant and digest sending re-read current user eligibility, matching
disabled-preference opt-outs, enabled event/region/asset consent, current plan
entitlement, channel configuration, destination and quota. No new paid-only
gate is added to Telegram. The existing email pause stays enforced in the
unchanged channel adapters; no channel credentials/settings are modified.

Fanout stops starting another user decision at **1200 seconds**. It reports
`fanout_budget_exhausted`, `events_remaining`, `user_checks_remaining`, budget,
query count, connection count and elapsed time. A partial event is NOT marked
complete. Subsequent runs restart it idempotently and create only missing
deliveries. The normal return allows D/C/final audit to execute; tests cover
that continuation. It is not a guarantee against process death, DB outages,
or provider failures elsewhere.

DB statements are bounded to five seconds and lock waits to one second on the
fanout connection, not by changing Cloud task settings.

## Offline verification

Tests run with the collection-time production DB/TCP/paid-API guard.
Disposable PostgreSQL listens only on a temporary Unix socket.
Tests include a literal frozen a313 baseline function, comparing resulting
rows and all legacy skip counters, connection/query counts and local timing;
last-slot concurrency; partial-budget resumption; current-policy revocation;
bounded HTTP success/down/timeout/auth/error handling; real SQL stage order
and stale audit dates; and existing index/storage/AI/delivery regressions.

Local timing is not Cloud runtime acceptance. Verify the first three scheduled
Alerts runs and the next scheduled Daily run after the approved rollout.

## Build and rollout — commands are for the owner, NOT executed here

After diff/test approval, use the full commit recorded in `ops-commit.json`:

```bash
bash scripts/build_daily_repair.sh FULL_REVIEWED_COMMIT
```

Wait for build SUCCESS and image digest. Then:

```bash
IMAGE='europe-west4-docker.pkg.dev/energyriskiq/energyriskiq-jobs/scheduled-jobs:eeri-fanout-20261112-COMMIT_PREFIX'
gcloud run jobs update energyriskiq-alerts \
  --project=energyriskiq --region=europe-west4 --image="$IMAGE"
```

After three successful scheduled Alerts executions, including Phase C and
finished final audits:

```bash
gcloud run jobs update energyriskiq-daily \
  --project=energyriskiq --region=europe-west4 --image="$IMAGE" \
  --update-env-vars=WEBSITE_BASE_URL=https://energyriskiq.com
```

Preserve **Alerts 1800s/retries 0** and **Daily 2400s/retries 0**.
The owner's names-only evidence confirms these settings; the 11 November
fanout reached the 30-minute deadline with no retry. No increase is proposed.
Preserve direct OpenAI configuration, selectors, email pause, Telegram, all
other environment values and secret references.
Do not update Ingestion, Intraday or Metadata.

## Acceptance

Alerts: first three scheduled executions exit 0; A/B/D/C and final audits
finish; query/connection/timing counts recorded; any budget exhaustion reports
remaining work; no provider storage writes or duplicate storage events; email
pause and Telegram settings unchanged. No manual sends for acceptance.

Daily: selected GERI persists, pair follows captured data, current pair before
report/delivery; actual observation dates appear in report/warm and delivery
audits; failures remain non-zero but pair failure alone does not block paid
content; all previously approved storage/provenance/AI checks remain.

## Rollback

Use the prior image on Alerts and Daily, preserving all other settings:

```bash
OLD='europe-west4-docker.pkg.dev/energyriskiq/energyriskiq-jobs/scheduled-jobs:cloud-ai-fallback-20261111-a313fb380665'
gcloud run jobs update energyriskiq-alerts --project=energyriskiq \
  --region=europe-west4 --image="$OLD"
gcloud run jobs update energyriskiq-daily --project=energyriskiq \
  --region=europe-west4 --image="$OLD" --remove-env-vars=WEBSITE_BASE_URL
```

Keep the website authentication/date-lock/insert-only repair and authenticated
03:00 GitHub backup; it can continue supplying the pair if Cloud is rolled back.
No schema migration or history rollback is required.
