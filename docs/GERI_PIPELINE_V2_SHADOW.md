# GERI V2 shadow activation — confidential operations runbook

## Scope and authorization

The Step 7 owner prompt authorizes newest-first enrichment and one supervised
trailing-seven-day catch-up, under **one combined $5 UTC-day budget** including
GPT-4.1 relevance labels. It does not authorize a customer-facing model change,
older-backlog processing, exhausted-event resets, new customer notifications,
or a live cut-over.

### Mode semantics

| Setting | Behavior |
| --- | --- |
| `RISK_PIPELINE_V2_MODE=off` | Normal legacy dispatch before activation; default when absent |
| `RISK_PIPELINE_V2_MODE=shadow` | V2 enrichment; risk writes only to private V2 tables |
| `RISK_PIPELINE_V2_MODE=live` | Existing V2 legacy-table write path; requires a separate owner approval |
| Deprecated `RISK_PIPELINE_V2_ENABLED=true` | Alias for live ONLY when explicit mode is absent |

An explicit mode always wins over the old boolean. Shadow deployment keeps the
old boolean false. The app's shared environment and GitHub repository variables
must both specify shadow, a $5 budget and at most 20 requests/minute.

## Isolation and older deployed processes

Private outputs: `risk_events_v2`, `risk_indices_v2`, `asset_risk_v2`,
`geri_shadow_daily` and the private `risk_pipeline_v2_*` control, usage, rate,
label and monitoring tables.

Risk snapshots have the legacy columns plus pipeline version/mode. Private
sequences do not increment legacy table IDs. No public customer consumer reads
these tables. Only the shadow/lab jobs and `/ops/status` expose private results.

Statement-level triggers reject writes to the three legacy risk tables while
the durable control row says shadow. This protects against old app/runners
which do not recognize the new setting yet. A second guard prevents old
enrichment workers from incrementing attempts or marking processed events
outside the seven-day, retryable scope. Stale monitoring flags remain permitted.
A rejected legacy call is an explicit operational error, not silent success.

The app needs republishing to expose the updated `/ops/status` and replace old
entry points. Database guards are already active independently of publishing.
The managed development schema is mirrored additively so publishing should not
propose dropping the newly created private tables. Never approve an unexpected
DROP migration; investigate it instead.

## Enrichment, budget and catch-up

- Only unprocessed events inserted in the trailing seven days, with attempts
  below three, are claimed. Newest inserted timestamp/ID comes first.
- Failed attempts are retained and counted; no exhausted-event resets.
- Retryable events older than 30 days receive a `skipped_stale` JSON status.
  They remain stored and unprocessed. Monitoring excludes them from active
  queue depth, and reports their count separately.
- One durable original-cohort catch-up is tracked. If the supervised run reaches
  its daily budget, bounded hourly work can resume that same catch-up after a
  UTC budget reset. No new older cohort is opened.
- A database advisory lock with heartbeat serializes ingestion/catch-up. GitHub
  concurrency also prevents overlapping scheduled and manual ingestion jobs.
  The catch-up waits for an existing runner; it never steals its lock.
- Capacity planning retains at least 120% of observed 28-day daily inflow,
  subject to the explicit budget, provider errors and runtime limits.
- Every paid request reserves an upper cost bound atomically BEFORE the API
  call. Enrichment and relevance use the same ledger and advisory lock.
  Missing response usage/ambiguous failures retain their conservative charge.
  Crashed reservations are not silently released or treated as free.
- Log actual `response.usage`, raw output and charge before validating labels.
  Validation errors retain usage and are marked failed. SDK retries are off.
- Standard synchronous rates are $0.40/$1.60 per million input/output tokens
  for GPT-4.1-mini and $2/$8 for GPT-4.1. Unknown models fail closed. Cached-token
  discounts are not assumed. These are usage-based charges, not an invoice.
- Rate admission is shared and capped at 20 RPM. Budget refusal starts no
  request and records an internal admin error, never a customer alert.

GitHub `ingestion_pipeline.yml` runs the private ingestion CLI in shadow mode.
Its approved manual `supervised_catchup=true` input starts one up-to-5,000-event
catch-up. Dispatching it again is not necessary while the current run is queued
or running. Schedule delays and lock waiting are visible in Actions.

## Reference calibration and simulated alerts

The configurable `--percentile` setup argument defaults to 0.90. Floors are
derived from the frozen Step 6 timely reconstruction on January 14–June 3,
2026, excluding days below 50% coverage and missing coverage. The control row
and report record the eligible dates, empirical distributions and input hashes.
This historical reconstruction uses later-known AI confidence: it is a
hindsight calibration, not point-in-time validation.

Each region and Europe asset has its own seven- AND thirty-day floor.
The denominator is `max(reference_floor, current_window_sum,
previous_V2_window_sum_maximum)`, with the V2 region/asset lookback lengths
retained. Zero raw with a genuinely zero floor/maximum yields zero.

Each risk run records saturation at >=90 and 100, by region/asset and window.
Simulations apply the existing threshold 70 and regional +20% change criterion
against preceding private state. Global is not a generated alert region.
Simulated keys are unioned by UTC date to estimate daily unique fingerprints;
these are counterfactual candidates, not delivered alerts. No customer
`alert_events` or public `alert_state` updates are made.

## Private prospective GERI

Daily variants: `prod`, `integrity_v1`, `rel41`,
`pillars_v2_continuous`, `pillars_v2_continuous_rel41`.

- `prod` copies the published reference; other arms use the frozen lab integrity
  definition, including its confidence-valued risk input and accepted types.
- Continuous R is the regional-cluster-weighted seven-day V2 risk mean;
  continuous A is the four Europe assets' seven-day mean.
- Relevance uses the exact cached Step 5 GPT-4.1 rubric and strict output schema;
  `r_material_events` is unchanged. No storyline scoring/deduplication.
- Each arm uses its OWN previous 90-day raw history, seeded from its own frozen
  lab replay, excluding unhealthy days. C is persisted to two decimals as in
  production. The production reference does not seed candidate components.
- Compute only closed UTC dates with an actual published production value,
  production health, and exact-date V2 risk inputs. Never fabricate missing
  published references, labels or risk snapshots.
- Preserve the first observation; reruns do not overwrite a variant/date.
  Seeds and the partial activation day are excluded from prospective testing.
  Late reconstructions are flagged and excluded too.

The private GitHub workflow runs after the production daily workflow when it
runs, with an hourly closed-date readiness fallback. The existing production
daily GitHub workflow was disabled before this work; it was NOT enabled or
changed. Shadow computations wait for the actual published reference regardless
of which existing scheduler produces it.

```sh
python scripts/geri_shadow_job.py daily
python scripts/geri_shadow_job.py monitor
python -m scripts.geri_lab.step7_compare
python -m scripts.geri_lab.package_step7
```

Comparison uses Step 5's paired weekly bootstrap and thresholds but ONLY mature
prospective observations. H1/H2 split the prospective interval, not the old
historical sample. With no observations or inadequate independent weeks, the
answer is unassessable; no positive verdict is inferred.

## Monitoring and operating checkpoints

`/ops/status` shows mode, active/total/fresh queues, skipped stale count, oldest
fresh age, median enrichment delay for newly inserted events, hourly request
counts, actual tokens/costs, conservative reservations, today's committed spend,
private saturation and latest prospective values.

The private monitor persists the first real observation after 24h and 72h.
Before due time it explicitly reports `not_due`. The requested elapsed-time
reports cannot honestly be supplied at activation. GitHub artifacts and the
private monitor table retain actual observations; regenerate the ZIP later.

Safe pause: stop the ingestion/catch-up runner or use its skip-AI/skip-risk
controls, while leaving the durable shadow guards active. Do NOT remove guards
or switch the control row to off/live as a rollback: timely enriched events
could then be scored by legacy maxima and produce the very alert burst this
isolation prevents. Telegram/alert workers must remain enabled.

## Cut-over decision

72h can reveal operating failures, not establish market predictive performance.
Require sustained fresh coverage, acceptable delays, no budget violations,
unexplained saturation resolved, enough complete 7/30-day history, and adequately
powered prospective weekly-bootstrap evidence. Obtain separate owner approval
for consumer changes and guard removal; this activation supplies neither.
