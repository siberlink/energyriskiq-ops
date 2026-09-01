#!/usr/bin/env bash
#
# Deploy the direct production runners as Cloud Run Jobs and trigger them with
# Cloud Scheduler. Run this from the repository checkout in Google Cloud Shell.
#
# Usage:
#   bash scripts/deploy_gcp_scheduled_jobs.sh [PROJECT_ID] [REGION]
#
# Secret values are never read or printed by this script. The secret names must
# already exist in Google Secret Manager in the selected project.

set -Eeuo pipefail

PROJECT_ID="${1:-${GCP_PROJECT_ID:-energyriskiq}}"
REGION="${2:-${GCP_REGION:-europe-west4}}"
SCHEDULER_LOCATION="${SCHEDULER_LOCATION:-$REGION}"
ARTIFACT_REPOSITORY="${ARTIFACT_REPOSITORY:-energyriskiq-jobs}"
IMAGE_NAME="${IMAGE_NAME:-scheduled-jobs}"
IMAGE_TAG="${IMAGE_TAG:-$(git rev-parse --short HEAD 2>/dev/null || date -u +%Y%m%d%H%M%S)}"

JOB_RUNTIME_SA_NAME="${JOB_RUNTIME_SA_NAME:-energyriskiq-job-runtime}"
SCHEDULER_SA_NAME="${SCHEDULER_SA_NAME:-energyriskiq-scheduler}"
JOB_RUNTIME_SA="${JOB_RUNTIME_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
SCHEDULER_SA="${SCHEDULER_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${ARTIFACT_REPOSITORY}/${IMAGE_NAME}:${IMAGE_TAG}"

REQUIRED_SECRETS=(
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
)

log() {
  printf '\n[gcp-scheduled-jobs] %s\n' "$*"
}

die() {
  printf '\n[gcp-scheduled-jobs] ERROR: %s\n' "$*" >&2
  exit 1
}

command -v gcloud >/dev/null 2>&1 || die "gcloud CLI is required."
command -v git >/dev/null 2>&1 || die "git is required."

log "Using project ${PROJECT_ID} in region ${REGION}"
gcloud config set project "$PROJECT_ID" >/dev/null

log "Enabling required Google Cloud APIs"
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  cloudscheduler.googleapis.com \
  cloudbuild.googleapis.com \
  iamcredentials.googleapis.com \
  --project="$PROJECT_ID" \
  --quiet

log "Checking required Secret Manager secret names"
for secret in "${REQUIRED_SECRETS[@]}"; do
  gcloud secrets describe "$secret" \
    --project="$PROJECT_ID" \
    >/dev/null 2>&1 \
    || die "Secret Manager secret '${secret}' was not found in project ${PROJECT_ID}."
done

log "Ensuring Artifact Registry repository exists"
if ! gcloud artifacts repositories describe "$ARTIFACT_REPOSITORY" \
  --location="$REGION" \
  --project="$PROJECT_ID" \
  >/dev/null 2>&1; then
  gcloud artifacts repositories create "$ARTIFACT_REPOSITORY" \
    --repository-format=docker \
    --location="$REGION" \
    --description="EnergyRiskIQ scheduled-job images" \
    --project="$PROJECT_ID" \
    --quiet
fi

log "Granting Cloud Build permission to publish the image"
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
for build_service_account in \
  "${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com" \
  "service-${PROJECT_NUMBER}@gcp-sa-cloudbuild.iam.gserviceaccount.com"; do
  if gcloud iam service-accounts describe "$build_service_account" \
    --project="$PROJECT_ID" \
    >/dev/null 2>&1; then
    gcloud artifacts repositories add-iam-policy-binding "$ARTIFACT_REPOSITORY" \
      --location="$REGION" \
      --project="$PROJECT_ID" \
      --member="serviceAccount:${build_service_account}" \
      --role="roles/artifactregistry.writer" \
      --quiet \
      >/dev/null
  fi
done

ensure_service_account() {
  local account_name="$1"
  local display_name="$2"
  if ! gcloud iam service-accounts describe \
    "${account_name}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --project="$PROJECT_ID" \
    >/dev/null 2>&1; then
    gcloud iam service-accounts create "$account_name" \
      --display-name="$display_name" \
      --project="$PROJECT_ID" \
      --quiet
  fi
}

log "Ensuring runtime and scheduler service accounts exist"
ensure_service_account "$JOB_RUNTIME_SA_NAME" "EnergyRiskIQ scheduled job runtime"
ensure_service_account "$SCHEDULER_SA_NAME" "EnergyRiskIQ Cloud Scheduler invoker"

log "Granting the runtime service account access to required secrets"
for secret in "${REQUIRED_SECRETS[@]}"; do
  gcloud secrets add-iam-policy-binding "$secret" \
    --member="serviceAccount:${JOB_RUNTIME_SA}" \
    --role="roles/secretmanager.secretAccessor" \
    --project="$PROJECT_ID" \
    --quiet \
    >/dev/null
done

log "Building image ${IMAGE}"
gcloud builds submit \
  --tag="$IMAGE" \
  --project="$PROJECT_ID" \
  .

deploy_job() {
  local job_name="$1"
  local timeout="$2"
  local args="$3"
  local env_vars="$4"
  local secret_vars="$5"

  log "Deploying Cloud Run Job ${job_name}"
  gcloud run jobs deploy "$job_name" \
    --image="$IMAGE" \
    --region="$REGION" \
    --project="$PROJECT_ID" \
    --service-account="$JOB_RUNTIME_SA" \
    --tasks=1 \
    --parallelism=1 \
    --max-retries=0 \
    --task-timeout="$timeout" \
    --memory=2Gi \
    --cpu=1 \
    --command=python \
    --args="scripts/replit_scheduled_job.py,${args}" \
    --set-env-vars="$env_vars" \
    --set-secrets="$secret_vars" \
    --quiet

  gcloud run jobs add-iam-policy-binding "$job_name" \
    --region="$REGION" \
    --project="$PROJECT_ID" \
    --member="serviceAccount:${SCHEDULER_SA}" \
    --role="roles/run.invoker" \
    --quiet \
    >/dev/null
}

COMMON_ENV="PYTHONPATH=/app,SKIP_MIGRATIONS=true"
COMMON_SECRETS="DATABASE_URL=DATABASE_URL:latest,INTERNAL_RUNNER_TOKEN=INTERNAL_RUNNER_TOKEN:latest"

deploy_job \
  "energyriskiq-alerts" \
  "1800s" \
  "--job,alerts" \
  "${COMMON_ENV},ALERTS_V2_ENABLED=true,ALERTS_ENABLED=true,PHASE=all,DRY_RUN=false,SINCE_HOURS=24,BATCH_SIZE=200,SKIP_PREFLIGHT=false,INCLUDE_PRO_DELIVERY=true,INCLUDE_TRADER_DELIVERY=true" \
  "${COMMON_SECRETS},BREVO_API_KEY=BREVO_API_KEY:latest,EMAIL_PROVIDER=EMAIL_PROVIDER:latest,EMAIL_FROM=EMAIL_FROM:latest,TELEGRAM_BOT_TOKEN=TELEGRAM_BOT_TOKEN:latest,GIE_API_KEY=GIE_API_KEY:latest"

deploy_job \
  "energyriskiq-intraday" \
  "420s" \
  "--job,intraday" \
  "$COMMON_ENV" \
  "$COMMON_SECRETS"

deploy_job \
  "energyriskiq-ingestion" \
  "1680s" \
  "--job,ingestion" \
  "${COMMON_ENV},SKIP_AI=false,SKIP_RISK=false" \
  "${COMMON_SECRETS},OPENAI_API_KEY=OPENAI_API_KEY:latest"

deploy_job \
  "energyriskiq-metadata" \
  "600s" \
  "--job,metadata" \
  "${COMMON_ENV},DRY_RUN=false" \
  "$COMMON_SECRETS"

deploy_job \
  "energyriskiq-daily" \
  "2400s" \
  "--job,daily" \
  "${COMMON_ENV},INCLUDE_DELIVERY=true,ENABLE_GERI=true,ENABLE_EERI=true,ENABLE_EGSI=true,EGSI_S_DATA_SOURCE=composite" \
  "${COMMON_SECRETS},OPENAI_API_KEY=OPENAI_API_KEY:latest,AI_INTEGRATIONS_OPENAI_API_KEY=AI_INTEGRATIONS_OPENAI_API_KEY:latest,AI_INTEGRATIONS_OPENAI_BASE_URL=AI_INTEGRATIONS_OPENAI_BASE_URL:latest,GIE_API_KEY=GIE_API_KEY:latest,OIL_PRICE_API_KEY=OIL_PRICE_API_KEY:latest,BREVO_API_KEY=BREVO_API_KEY:latest,EMAIL_PROVIDER=EMAIL_PROVIDER:latest,EMAIL_FROM=EMAIL_FROM:latest,TELEGRAM_BOT_TOKEN=TELEGRAM_BOT_TOKEN:latest"

create_or_update_scheduler_job() {
  local scheduler_name="$1"
  local schedule="$2"
  local run_job_name="$3"
  local uri="https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}/jobs/${run_job_name}:run"

  log "Configuring Cloud Scheduler job ${scheduler_name} (${schedule} UTC)"
  local common_args=(
    "--location=${SCHEDULER_LOCATION}"
    "--schedule=${schedule}"
    "--time-zone=Etc/UTC"
    "--uri=${uri}"
    "--http-method=POST"
    "--headers=Content-Type=application/json"
    "--message-body={}"
    "--oauth-service-account-email=${SCHEDULER_SA}"
    "--oauth-token-scope=https://www.googleapis.com/auth/cloud-platform"
    "--attempt-deadline=60s"
    "--max-retry-attempts=3"
    "--project=${PROJECT_ID}"
    "--quiet"
  )

  if gcloud scheduler jobs describe "$scheduler_name" \
    --location="$SCHEDULER_LOCATION" \
    --project="$PROJECT_ID" \
    >/dev/null 2>&1; then
    gcloud scheduler jobs update http "$scheduler_name" "${common_args[@]}"
  else
    gcloud scheduler jobs create http "$scheduler_name" "${common_args[@]}"
  fi
}

create_or_update_scheduler_job "energyriskiq-alerts" "*/10 * * * *" "energyriskiq-alerts"
create_or_update_scheduler_job "energyriskiq-intraday" "*/10 * * * *" "energyriskiq-intraday"
create_or_update_scheduler_job "energyriskiq-ingestion" "0 * * * *" "energyriskiq-ingestion"
create_or_update_scheduler_job "energyriskiq-metadata" "16 * * * *" "energyriskiq-metadata"
create_or_update_scheduler_job "energyriskiq-daily" "30 1 * * *" "energyriskiq-daily"

log "Deployment complete"
printf 'Project: %s\nRegion: %s\nImage: %s\n' "$PROJECT_ID" "$REGION" "$IMAGE"
printf '\nCloud Run Jobs:\n'
gcloud run jobs list --region="$REGION" --project="$PROJECT_ID" \
  --filter='metadata.name~^energyriskiq-' \
  --format='table(metadata.name,status.latestCreatedTime)'
printf '\nCloud Scheduler jobs:\n'
gcloud scheduler jobs list --location="$SCHEDULER_LOCATION" --project="$PROJECT_ID" \
  --filter='name~energyriskiq-' \
  --format='table(name.basename(),schedule,state)'