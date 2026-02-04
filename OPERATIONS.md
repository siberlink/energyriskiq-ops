# EnergyRiskIQ Operations Guide

## Deployment Architecture

EnergyRiskIQ uses **Replit Autoscale** for the API server and **GitHub Actions** for scheduled background workers.

### Why This Architecture?

- **Autoscale API**: Stateless, spins up only in response to HTTP traffic
- **No background jobs on Autoscale**: Workers must be triggered externally
- **GitHub Actions**: Free, reliable scheduler that executes jobs on a regular cadence

---

## Background Workers

Your app has 4 separate worker processes:

| Worker | Purpose | Schedule |
|--------|---------|----------|
| **Ingest** | Fetches new events from RSS feeds | Every 15 minutes |
| **AI** | Processes unprocessed events with OpenAI | Every hour |
| **Risk** | Computes risk scores and indices | Every 15 minutes |
| **Alerts** | Evaluates triggers and sends alerts | Every 15 minutes |

---

## GitHub Actions Workflows

### 1. EnergyRiskIQ Scheduler (Ingest/Risk/Alerts)

**File**: `.github/workflows/energyriskiq-scheduler.yml`

**Schedule**: Every 15 minutes (UTC cron)

**Endpoints triggered**:
- `POST /internal/run/ingest`
- `POST /internal/run/risk`
- `POST /internal/run/alerts`

**Authentication**: Uses `INTERNAL_RUNNER_TOKEN` secret

### 2. EnergyRiskIQ AI Worker

**File**: `.github/workflows/energyriskiq-ai.yml`

**Schedule**: Every hour

**Endpoint triggered**:
- `POST /internal/run/ai`

**Why separate?**: AI processing is expensive (OpenAI credits), so it runs hourly instead of every 15 minutes to save costs.

---

## Worker Status Endpoint

`GET /ops/status` - Returns freshness status of all workers (no auth required)

Response includes:
- `now_utc`: Current UTC timestamp
- `workers`: Object with status for each worker (ingest, ai, risk, alerts, digest)
  - `last_run`: ISO timestamp of last successful run
  - `count`: Number of items processed
  - `stale`: Boolean indicating if worker is overdue

**Staleness Thresholds:**
| Worker | Stale If Older Than |
|--------|---------------------|
| ingest | 60 minutes |
| ai | 6 hours |
| risk | 60 minutes |
| alerts | 60 minutes |
| digest | 36 hours |

---

## Internal Runner Endpoints

All endpoints require `X-Runner-Token` header with `INTERNAL_RUNNER_TOKEN` value.

| Endpoint | Description |
|----------|-------------|
| `POST /internal/run/ingest` | Trigger RSS ingestion |
| `POST /internal/run/ai` | Trigger AI processing |
| `POST /internal/run/risk` | Trigger risk scoring |
| `POST /internal/run/alerts` | Trigger alerts engine |
| `POST /internal/run/digest` | Trigger daily digest |
| `POST /internal/run/market-data` | Capture VIX and TTF gas data |

---

## Environment Variables

### Required for GitHub Actions

| Variable | Description |
|----------|-------------|
| `INTERNAL_RUNNER_TOKEN` | Secret token for /internal/run/* endpoints |
| `APP_URL` | Production URL (https://energyriskiq.com) |

### Email Configuration

| Variable | Description |
|----------|-------------|
| `EMAIL_PROVIDER` | Email service: `brevo` or `resend` |
| `EMAIL_FROM` | Sender address |
| `BREVO_API_KEY` | Brevo API key (if using Brevo) |

---

## Summary

The EnergyRiskIQ Scheduler GitHub workflow is your cron job that keeps the backend data pipeline alive and fresh by automatically triggering ingestions, risk recomputation, and alert evaluation every 15 minutes. AI processing runs hourly on a separate workflow to optimize costs.
