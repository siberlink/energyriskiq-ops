# Closed-day index digest delivery — source prepared 13 November 2026

## Approved contract

- Daily owns the index digest. The Cloud Alerts runner must not call Pro/index
  delivery after its engine. Instant alerts, A/B/D/C, queued alert batches,
  Trader delivery and the alert-email pause are unchanged.
- Manual `POST /internal/run/pro-delivery` and `/internal/run/geri-delivery`
  render deterministically by default, with no AI calls or external sends.
  Sending requires the explicit query parameter `?send=true`, runner
  authentication, and the same guarded path used by Daily.
- Freeze target = UTC yesterday once per invocation. Load selected-methodology
  GERI, `eeri_ttf_v3` EERI and EGSI-M for that exact date in one read-only
  repeatable-read transaction. Never fall back to older observations.
- If incomplete, reopen a snapshot every 10 seconds for at most 120 seconds.
  Polling makes no AI or provider requests. A still-missing section is explicitly
  `pending`; the audit has `freshness_pending=true`. Incomplete digest narratives
  are deterministic, not generated from stale inputs.
- Daily's existing missing-persisted-GERI dependency remains: it blocks report
  warming and delivery. The pending path does not bypass that dependency.
- Keep date-level recipient/channel idempotency. A successfully delivered pending
  digest consumes that day's slot; there is **no correction/resend mechanism**.
  Cross-process advisory locks serialize the sent check and external transport.
  An uncertain send/ledger failure retains an append-only reservation to avoid
  duplicate delivery. Only a definitive non-delivery releases that reservation.
- Append every started/rendered/sent/pending/skipped/failed attempt, including
  already-sent and paused-email skips. Caller, Cloud job/execution, image/commit,
  target, actual index dates/values/models and freshness accompany each attempt.
  The existing date-level ledger remains separate.

## Rollout prerequisite — do not apply yet

`migrations/20261113_index_digest_attempts.sql` creates the new append-only audit
table and its mutation-blocking trigger. It does not alter historical storage
or existing delivery rows. **It has not been run on the application database.**
The new sender deliberately fails closed before transport if the table is absent.

After tomorrow's acceptance and separate owner deployment approval:

1. Review/apply the additive audit migration once to the actual shared database.
   Do not infer that a website startup will apply this standalone SQL file.
2. Publish the website guards and build the reviewed ops source. Both repositories
   must use the identical guarded delivery module.
3. Update only the separately approved Cloud jobs/images; preserve selectors,
   direct OpenAI binding, timeouts, email pause, Telegram and other settings.
   No build, publish, Cloud update or sends are part of this implementation run.
4. Verify next scheduled Daily's provenance, exact target/input dates, report-before-
   delivery order and append-only outcomes. Verify Alerts no longer invokes
   Pro/index delivery while its other phases and Trader still run.

## EU storage date contract — no migration

At `write_eu_scoring_snapshot` in `gas_storage_revisions.py`, the **EU physical
key remains its legacy publication date: provider gas day + 1**. Country rows
remain keyed by provider gas day. Provider `gasDayStart` is the observation
identity; historical EU keys, scores and interpretations must not be shifted.
The only storage writer change in this patch is a clarifying comment.

The source inventory lists readers which already normalize gas day and readers
which still expose/join/filter the physical key. Those readers are **not changed**
here. A later, separately authorized Prompt 2 will create a new `(area, gas_day)`
history from five years of provider `gasDayStart` records, resolve old duplicates/
gaps there, and move readers. This does not authorize backfill or migration now.
