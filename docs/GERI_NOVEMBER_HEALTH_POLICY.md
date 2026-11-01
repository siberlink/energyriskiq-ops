# Owner-approved operational policy — 1 November 2026

## Prospective health only

For observation dates from 2026-11-01, low alert counts do not indicate a source
outage. DEGRADED requires events_ratio < 0.40 or known feed success < 0.50.
UNAVAILABLE keeps its existing definition. Unknown feed success is not zero.
The alert ratio remains observable but does not downgrade a quiet day.

Earlier dates retain their old evaluation rule. Existing final health rows are
immutable. Do not backfill, recompute or revise October 31: its DEGRADED health
and logged Live-close reconciliation still exclude it from prospective evidence.
Published v1.1 values are not repaired or rewritten.

Daily uses the shared health evaluator. Private Daily and the selected shadow
candidate consume persisted final health; historical normalization uses those
same final records. Live retains open-day provisional behavior and uses final
health/Daily when closing a day. This changes health policy, not scoring math.

## Enrichment retry evidence

G1 ignores an error only when the usage ledger proves a subsequent completed
enrichment attempt for that event, the event was committed, and both attempts
and the commit fall inside the same finished shadow_enrichment_delivery run.
The run may have status error because its existing counter records failed
attempts, even after recovery. A later-run retry does not satisfy the exception.

Unresolved errors, other-purpose errors, exhausted events and stale reservations
continue to block. Failed attempts and their costs remain in the original ledger.

## Fresh queue

Both G1 and the admin warning count unprocessed events with ai_attempts < 3
inserted since shadow activation. Both compare against the average inflow over
the preceding three closed UTC days. Equality blocks G1 and raises the warning.
Old retryable backlog is still visible in monitoring, but is not the fresh queue.

## Automatic evidence

The owner-armed configuration has auto_rearm_current_build enabled. While armed,
the serving process may rebind it to its current executable build only after
G1–G4 pass and the approved content revision still matches. The capture runner
separately checks the actual public serving hash before beginning Part B.
All evidence remains build-bound; no approval or methodology switch is automated.

## Rollout

Republish the website. Rebuild the ops image and update only energyriskiq-daily
and energyriskiq-ingestion; preserve ingestion timeout 50m, shadow mode, $5/day
and 20 RPM. Do not enable GitHub ingestion or rerun historical calculations.
After publishing, verify the serving hash, armed target, G1 and prospective
records. Do not run the signed-in walkthrough before all G1–G4 are green.
