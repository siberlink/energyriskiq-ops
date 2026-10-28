# Private Daily, selected shadow and Live parity correction

## Exact cause

The first differing date is **2026-10-23**, not October 27. Its authoritative
final health is OK. Private v1.2 used that quality, while the frozen wk_carry15
shadow cohort retained an earlier DEGRADED observation. For October 27 the
private 90-day window included October 23; the shadow's 89-row window omitted
it. The raw October 27 signal and its 44 alert IDs were identical.

The stale quality also made shadow hold rather than advance EWMA on October 23.
Later identical integer values on October 24–26 concealed unequal internal state.

## Consistent rule

Both release paths now use the same frozen vector kernel and authoritative
final-health overlay. Every final-OK date inside the existing windows is eligible,
including late-repaired dates. DEGRADED/UNAVAILABLE dates are excluded from
weekday/normalization history but remain calendar states for the existing
EWMA hold behavior. Repair/backfill flags affect release evidence, not scoring.
Other experimental variants, window sizes, weights and gate predicates are unchanged.

Daily v1.2 requires final closed-day health. An existing private observation
created before final health is recomputed once, with an applied revision and
the existing prospective-evidence exclusion.

## Live boundary

The observed October 27 step was **22 to 8 at 00:21:35 UTC**: a no-alert hold
ended instantly when three alerts arrived, replacing 22 with a low, early
cumulative-sample projection.

Before previous-day final health is available, Live explicitly carries its
previous observation and does not create a speculative Daily row. Once ready,
the first two covered hours blend raw inputs from the previous EWMA steady
state into the current projection. This is Live input completion, not a change
to Daily scoring, clipping or output smoothing. At completion, weight is exactly
one and Live uses the identical full-day calculation.

If a stored closing tick differs from final Daily, it is explicitly reconciled
with its original payload retained in geri_v12_revisions. The metadata records
the actual later availability and original observed value. Every changed close
is excluded by the existing gate predicate; no tick is fabricated or backdated.
Original midnight observations are retained, including the historical 14-point
jump. A hindsight replay cannot turn that date into a passing prospective day.

## Applied private repair

The approved October 23–27 replay preserves frozen raw signals and alert sets.
It writes private Daily revisions and selected-shadow revisions into the existing
private ledger. It does not change published v1.1 or any other shadow arm.

| Date | Private (unchanged value) | Selected shadow old → corrected |
|---|---:|---:|
| Oct 23 | 17 | 16 → 17 |
| Oct 24 | 19 | 19 → 19, internal state corrected |
| Oct 25 | 27 | 27 → 27, internal state corrected |
| Oct 26 | 22 | 22 → 22, internal state corrected |
| Oct 27 | 21 | 22 → 21 |

Every repaired date is excluded from prospective gate evidence. The published
v1.1 table fingerprint and row count were unchanged.

## Verification

- Application full suite: **1423 passed**, 7 subtests passed, one existing
  FastAPI startup-event deprecation warning.
- Ten new regression cases cover final-health guards, identical private/shadow
  state through late repair and unhealthy days, pre-final revision, pending-health
  Live carry, terminal equality, and audited/excluded close reconciliation.
- A corrected-history hindsight replay of October 27's midnight observations
  has a maximum five-minute step of **1 point**, and completed Live equals Daily
  **21**. This is diagnostic only, not prospective evidence.
- Worker-only suite: **128 passed**. Its EGSI tests were synchronized with the
  application's previously approved ASGI/TestClient version; an old external
  HTTP test received HTML rather than JSON. No EGSI runtime code was changed.

## Rollout

The owner must republish the website and rebuild this ops commit into the Cloud
worker image. Update Daily and ingestion only; preserve ingestion 3000 seconds,
shadow mode, the shared $5 cap and 20 RPM. Leave GitHub Ingestion Pipeline and
Daily Index disabled. Keep Private GERI Shadow and Operating Reports enabled:
its next checkout uses this corrected selected-shadow implementation.

Do not re-run the repair merely to deploy the source. For any separately
authorized future correction, the maintenance command is dry-run by default:

```sh
PYTHONPATH=. python scripts/repair_geri_private_parity.py \
  --from-date YYYY-MM-DD --through YYYY-MM-DD --reason "approved reason"
# Only after authorization/review: add --apply.
```

No selector, customer notification or other release gate was changed.
