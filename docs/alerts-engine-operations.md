# Alerts Engine scheduling

## Schedule layout

The production alert path is intentionally isolated from data collection:

- **Alerts Engine v2** runs every ten minutes and performs alert generation,
  fanout, digest construction, queued alert sending, and plan delivery.
- **Intraday Market Data Capture** runs every ten minutes in a separate
  concurrency group. Provider latency cannot occupy the Alerts Engine slot.
- **Daily Index Computation** owns daily market, oil, storage, and index work.
- **Ingestion Pipeline** runs hourly through one protected application endpoint.
  Ingestion, optional AI enrichment, and optional risk scoring therefore keep
  their required ordering under one PostgreSQL advisory lock.
- **Alert Metadata Backfill** runs hourly through its own protected endpoint.
  Overlap is reported as `busy`, and row-level errors fail the workflow.

GitHub cron schedules use UTC and are best-effort. A run can begin late during
GitHub load, but each workflow has a fixed timeout and bounded HTTP requests so
it cannot wait forever.

## Replit Scheduled Deployment cutover

Keep the existing Autoscale deployment for the API. Create separate Scheduled
Deployments that use the same project code and production environment values:

| Scheduled job | Schedule (UTC) | Run command | Suggested timeout |
|---|---|---|---|
| Alerts and plan delivery | Every 10 minutes | `python scripts/replit_scheduled_job.py --job alerts` | 15 minutes |
| Intraday market capture | Every 10 minutes | `python scripts/replit_scheduled_job.py --job intraday` | 7 minutes |
| Ingestion, AI, and risk | Every hour at minute 00 | `python scripts/replit_scheduled_job.py --job ingestion` | 28 minutes |
| Alert metadata backfill | Every hour at minute 16 | `python scripts/replit_scheduled_job.py --job metadata` | 10 minutes |
| Daily index pipeline | Every day at 01:30 | `python scripts/replit_scheduled_job.py --job daily` | 40 minutes |

Each scheduled deployment needs `INTERNAL_RUNNER_TOKEN` in its deployment
environment. The command imports and invokes the existing protected handlers
directly, avoiding a public HTTP request that could be blocked by Cloudflare.
Those handlers remain the single owner of advisory locks, validation, and
business logic. A `409 busy` result is treated as an expected overlap and does
not start duplicate work.

During migration, leave GitHub cron enabled until every Replit schedule has
completed one successful production run. Then remove only the `schedule`
trigger from the corresponding GitHub workflow while retaining
`workflow_dispatch` for manual recovery. Do not run GitHub and Replit schedules
indefinitely, even though application locks prevent duplicate execution.

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

The ingestion and metadata workflows also intentionally omit GitHub Actions
concurrency groups. Every trigger can reach the application lock instead of
being silently replaced in GitHub's single pending slot. Their mutation
requests are not retried after an unknown response; the server continues a
synchronous job after the client disconnects, while its advisory lock prevents
another trigger from starting the same operation.

The hourly ingestion workflow no longer captures intraday prices. That work is
owned exclusively by the independent Intraday Market Data workflow, preventing
duplicate provider calls and shortening the critical ingestion path.

The daily workflow submits the complete ordered sequence as one protected
request and does not retry it because the sequence includes user delivery.
The application holds a pipeline-wide lock, validates required stage results,
and stops dependent computation after a failed prerequisite. Its 40-minute job
budget exceeds the bounded request plus setup margin.

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

For ingestion, `busy` means an earlier full ingestion/AI/risk pipeline still
owns the application lock. For daily computation, the workflow summary reports
the pipeline result and the uploaded response artifact identifies the operation
that failed. For metadata backfill, inspect the artifact when the summary
reports row errors.

## Git credential action required

The local `origin` URL must never contain a personal access token. Use a clean
HTTPS remote URL and authenticate through the platform credential mechanism.

If a token was ever embedded in a remote URL or exposed in logs, the repository
owner must revoke it in GitHub and create a replacement with only the minimum
required repository permissions. Source-code changes cannot revoke an existing
GitHub credential.