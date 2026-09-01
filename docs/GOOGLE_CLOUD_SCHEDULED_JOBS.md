# Google Cloud scheduled jobs

EnergyRiskIQ's five production background jobs can run as direct Python
invocations in Cloud Run Jobs, with Cloud Scheduler triggering each job. This
keeps the existing PostgreSQL advisory-lock and idempotency behavior and does
not send long-running work through the public API or Cloudflare.

## Current deployment

- Project: `energyriskiq`
- Region: `europe-west4`
- Scheduler timezone: `Etc/UTC`
- Source branch: `main`
- Container build: Google Cloud Build
- Image storage: Artifact Registry
- Runtime credentials: Google Secret Manager

## One-time setup from Cloud Shell

Clone the `main` branch, authenticate with the Google Cloud account that owns
the project, and run:

```bash
git clone https://github.com/siberlink/energyriskiq-ops.git
cd energyriskiq-ops
git checkout main
bash scripts/deploy_gcp_scheduled_jobs.sh energyriskiq europe-west4
```

The script is safe to re-run. It creates or updates the Artifact Registry
repository, service accounts, Cloud Run Jobs, and Cloud Scheduler jobs.

## Secret Manager names

The script expects these secret names to already exist in project
`energyriskiq`. It only references their names; it never prints their values:

```text
DATABASE_URL
INTERNAL_RUNNER_TOKEN
OPENAI_API_KEY
AI_INTEGRATIONS_OPENAI_API_KEY
AI_INTEGRATIONS_OPENAI_BASE_URL
GIE_API_KEY
OIL_PRICE_API_KEY
BREVO_API_KEY
EMAIL_PROVIDER
EMAIL_FROM
TELEGRAM_BOT_TOKEN
```

The value of `DATABASE_URL` should remain the existing production PostgreSQL
connection. No Cloud SQL database is created or used by this deployment.

## Schedules

| Cloud Run Job | Cloud Scheduler schedule |
|---|---|
| `energyriskiq-alerts` | `*/10 * * * *` |
| `energyriskiq-intraday` | `*/10 * * * *` |
| `energyriskiq-ingestion` | `0 * * * *` |
| `energyriskiq-metadata` | `16 * * * *` |
| `energyriskiq-daily` | `30 1 * * *` |

The existing GitHub Actions schedules and Replit API should remain active
during verification. Pause or disable those old schedules only after the
Google Cloud jobs have completed successful runs and the database/output
checks are confirmed.

## Manual verification

To run one job immediately without waiting for its schedule:

```bash
gcloud run jobs execute energyriskiq-intraday \
  --region=europe-west4 \
  --project=energyriskiq \
  --wait
```

Replace `energyriskiq-intraday` with another job name as needed. View recent
executions with:

```bash
gcloud run jobs executions list \
  --job=energyriskiq-intraday \
  --region=europe-west4 \
  --project=energyriskiq
```

The execution logs are available in Google Cloud Logging under the Cloud Run
Job resource.