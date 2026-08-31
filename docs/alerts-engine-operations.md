# Alerts Engine scheduling

## Schedule layout

The production alert path is intentionally isolated from data collection:

- **Alerts Engine v2** runs every ten minutes and performs alert generation,
  fanout, digest construction, queued alert sending, and plan delivery.
- **Intraday Market Data Capture** runs every ten minutes in a separate
  concurrency group. Provider latency cannot occupy the Alerts Engine slot.
- **Daily Index Computation** owns daily market, oil, storage, and index work.

GitHub cron schedules use UTC and are best-effort. A run can begin late during
GitHub load, but each workflow has a fixed timeout and bounded HTTP requests so
it cannot wait forever.

## Overlap and retry safety

The alert workflow intentionally has no GitHub Actions concurrency group.
Every cron event can reach the protected application endpoint instead of being
discarded when GitHub replaces an older pending run. The application endpoint
uses a global PostgreSQL advisory lock; concurrent triggers receive `409 busy`.
Alert phases also retain their phase-level database advisory locks and
queued-delivery protections.

Data-capture POSTs are safe to retry because the corresponding jobs are locked
and their writes are idempotent. Delivery POSTs are deliberately **not**
automatically retried: a lost HTTP response after a provider accepted a message
has an unknown outcome, and immediately retrying could duplicate delivery.

HTTP `409` from an alert or capture endpoint means another protected operation
is already running. That is reported as `busy`, not as a second execution.

## Diagnosing a missed run

1. Open GitHub **Actions** and select the specific workflow.
2. Confirm the workflow exists on the repository's default branch and is
   enabled.
3. Check the run summary and the uploaded seven-day diagnostic artifact.
4. A queued run points to concurrency pressure; a timed-out run points to a
   slow application operation; no run record points to GitHub scheduling,
   repository inactivity, branch, or Actions configuration.
5. Manually dispatch the workflow to distinguish scheduler configuration from
   application failures.

## Git credential action required

The local `origin` URL must never contain a personal access token. Use a clean
HTTPS remote URL and authenticate through the platform credential mechanism.

If a token was ever embedded in a remote URL or exposed in logs, the repository
owner must revoke it in GitHub and create a replacement with only the minimum
required repository permissions. Source-code changes cannot revoke an existing
GitHub credential.