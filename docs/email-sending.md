# Email Sending Functionality

This document describes how email (and other channel) delivery works in EnergyRiskIQ's alerting system.

## Current Status

| Channel | Status | Notes |
|---------|--------|-------|
| **Email** | **DISABLED** | Set `ALERTS_EMAIL_ENABLED=false` on 2026-02-04 |
| **Telegram** | Active | Working normally |
| **SMS** | Not configured | Twilio credentials not set |

**To re-enable email sending:** Set `ALERTS_EMAIL_ENABLED=true` in environment variables.

### Behavior When Email Disabled

When `ALERTS_EMAIL_ENABLED=false`:
- All email delivery attempts are marked as `skipped` with reason `email_disabled`
- Telegram alerts continue normally
- Skipped alerts still appear in user's Alert History (status shows as "skipped")
- No errors are logged for expected email skip behavior

### Fixing Historical Data

If email was disabled and deliveries were incorrectly marked as `failed` instead of `skipped`:

```sql
UPDATE user_alert_deliveries 
SET status = 'skipped' 
WHERE status = 'failed' 
  AND last_error LIKE '%Email sending is disabled%';
```

---

## Overview

EnergyRiskIQ sends alerts to users via three channels:
- **Email** (primary) - via Brevo API
- **Telegram** - via Telegram Bot API
- **SMS** (optional) - via Twilio API

The system uses a 4-phase pipeline triggered by a GitHub Actions workflow that runs every 10 minutes.

---

## Architecture

### GitHub Actions Workflow

**File:** `.github/workflows/alerts_engine_v2.yml`

**Schedule:** Every 10 minutes (`*/10 * * * *`)

**Execution Flow:**

```
┌─────────────────┐
│ Preflight Check │  Validates DB, tables, channel configs
└────────┬────────┘
         │
┌────────▼────────┐
│ Alerts Engine   │  Phase A → B → D → C
│ (runner.py)     │  Generate → Fanout → Digests → Send
└────────┬────────┘
         │
┌────────▼────────┐
│ Pro Delivery    │  /internal/run/pro-delivery
│ (15-min batch)  │  Includes GERI when available
└────────┬────────┘
         │
┌────────▼────────┐
│ Trader Delivery │  /internal/run/trader-delivery
│ (30-min batch)  │  8 emails/day limit
└────────┬────────┘
         │
┌────────▼────────┐
│ Data Capture    │  Gas storage, EGSI, Oil prices
└─────────────────┘
```

---

## Phase Pipeline

### Phase A: Generate Alert Events

Creates `alert_events` records from classified news/events.

**Table:** `alert_events`

### Phase B: Fanout

For each alert_event, creates `user_alert_deliveries` rows for eligible users based on:
- User's plan tier (Pro, Trader, Enterprise)
- User's alert preferences (email enabled, telegram enabled)
- User's daily quota remaining
- Regional/asset filters

**Table:** `user_alert_deliveries`

### Phase D: Build Digests

Groups digest-type deliveries into batched `user_alert_digests` records.
- Pro: 15-minute batching windows
- Trader: 30-minute batching windows

**Table:** `user_alert_digests`

### Phase C: Send

Actually sends emails/Telegram/SMS for:
1. Instant deliveries (status='queued', delivery_kind='instant')
2. Digest batches (status='queued')

Uses `FOR UPDATE SKIP LOCKED` to prevent duplicate sends in concurrent executions.

---

## Email Provider: Brevo

**API Endpoint:** `https://api.brevo.com/v3/smtp/email`

**Configuration:**

| Environment Variable | Description |
|---------------------|-------------|
| `EMAIL_PROVIDER` | Set to `brevo` (default) or `resend` |
| `BREVO_API_KEY` | Brevo API key (secret) |
| `EMAIL_FROM` | Sender address, e.g., `EnergyRiskIQ <alerts@energyriskiq.com>` |

**Request Format:**
```json
{
  "sender": {"name": "EnergyRiskIQ", "email": "alerts@energyriskiq.com"},
  "to": [{"email": "user@example.com"}],
  "subject": "Risk Alert: ...",
  "textContent": "Alert body..."
}
```

**Rate Limits:**
- Brevo allows up to 1000 emails per batch (recommend 700-800 for safety)
- Internal rate limiting via `ALERTS_RATE_LIMIT_EMAIL_PER_MINUTE`

---

## Key Source Files

### Low-Level Channel Functions

**File:** `src/alerts/channels.py`

```python
def send_email(to_email, subject, body) -> (success, error, message_id)
def send_telegram(chat_id, message) -> (success, error)
def send_sms(to_phone, message) -> (success, error)
```

- Selects provider based on `EMAIL_PROVIDER` env var
- Makes HTTP requests to provider APIs
- Returns tuple with success status

### Production Adapters

**File:** `src/alerts/channel_adapters.py`

```python
def send_email_v2(to_email, subject, body, delivery_id) -> SendResult
def send_telegram_v2(chat_id, message, delivery_id) -> SendResult
def send_sms_v2(to_phone, message, delivery_id) -> SendResult
```

Features:
- **Config validation** - Checks API keys exist before sending
- **Rate limiting** - Sliding window throttle
- **Failure classification** - Transient (retry) vs Permanent (skip)
- **Retry logic** - Exponential backoff with jitter

### Delivery Engine

**File:** `src/alerts/alerts_engine_v2.py`

```python
def send_queued_deliveries(batch_size=100, max_per_run=None) -> Dict
def send_queued_digests(batch_size=50, max_per_run=None) -> Dict
```

Features:
- `FOR UPDATE SKIP LOCKED` prevents duplicate sends
- Circuit breaker: `ALERTS_MAX_SEND_PER_RUN`
- User allowlist filtering: `ALERTS_SEND_ALLOWLIST_USER_IDS`

### CLI Runner

**File:** `src/alerts/runner.py`

```bash
python -m src.alerts.runner --phase all
python -m src.alerts.runner --phase c --batch-size 200
python -m src.alerts.runner --preflight
python -m src.alerts.runner --health
```

---

## Plan-Specific Delivery

### Pro Plan

**Endpoint:** `POST /internal/run/pro-delivery?since_minutes=15&include_geri=true`

| Feature | Value |
|---------|-------|
| Email limit | 15/day |
| Batching window | 15 minutes |
| Telegram | Unlimited |
| GERI index | Included when available |

### Trader Plan

**Endpoint:** `POST /internal/run/trader-delivery?since_minutes=30`

| Feature | Value |
|---------|-------|
| Email limit | 8/day |
| Batching window | 30 minutes |
| Telegram | Included |
| GERI index | Not included (Pro+ only) |

---

## Retry Logic

### Failure Classification

**Transient (will retry):**
- Timeouts, network errors
- Rate limiting (429)
- Server errors (5xx)
- Provider unavailable

**Permanent (no retry):**
- Invalid recipient
- Malformed payload
- Authentication errors
- Client errors (4xx except 429)

### Backoff Formula

```python
delay = min(RETRY_MAX, RETRY_BASE * 2^(attempts-1))
jitter = random(0, 0.2) * delay
next_retry = delay + jitter
```

**Defaults:**
- `ALERTS_RETRY_BASE_SECONDS`: 60
- `ALERTS_RETRY_MAX_SECONDS`: 3600 (1 hour)
- `ALERTS_MAX_ATTEMPTS`: 5

---

## Database Tables

### user_alert_deliveries

Tracks individual delivery attempts:

| Column | Description |
|--------|-------------|
| id | Primary key |
| user_id | Target user |
| alert_event_id | Source alert |
| channel | email, telegram, sms |
| status | queued, sent, failed, skipped |
| delivery_kind | instant, digest |
| attempts | Retry count |
| last_error | Error message |
| next_retry_at | Next retry timestamp |
| sent_at | When successfully sent |

### user_alert_digests

Batched digest records:

| Column | Description |
|--------|-------------|
| id | Primary key |
| user_id | Target user |
| channel | email, telegram |
| digest_key | Unique batch identifier |
| status | pending, sent, failed |
| window_start | Batch period start |
| window_end | Batch period end |
| event_count | Number of events in digest |

### alerts_engine_runs

Observability for engine executions:

| Column | Description |
|--------|-------------|
| id | Primary key |
| phase | a, b, c, d |
| started_at | Execution start |
| completed_at | Execution end |
| status | running, completed, failed |
| stats | JSON with counts |

---

## Safety Features

### Concurrency Control

1. **Advisory locks** - One phase execution at a time
2. **FOR UPDATE SKIP LOCKED** - Prevents duplicate sends
3. **Unique constraints** - Idempotent delivery creation
4. **Concurrency group** - GitHub Actions prevents parallel runs

### Circuit Breakers

| Variable | Default | Description |
|----------|---------|-------------|
| `ALERTS_EMAIL_ENABLED` | true | **Email channel kill switch** - Set to `false` to disable all email sending |
| `ALERTS_MAX_SEND_PER_RUN` | 1000 | Max sends per execution |
| `ALERTS_V2_ENABLED` | true | Master kill switch for entire alerts system |
| `ALERTS_SEND_ALLOWLIST_USER_IDS` | (none) | Comma-separated user IDs for controlled rollout |

### Preflight Checks

Before sending, the runner validates:
1. Database connectivity
2. Required tables exist
3. At least one channel configured
4. API keys present

---

## Monitoring

### Health Metrics Endpoint

```bash
python -m src.alerts.runner --health
```

Returns JSON with:
- Deliveries by channel/status (last 24h)
- Digest counts
- Last engine run stats

### Log Artifacts

GitHub Actions uploads logs to artifacts:
- `alerts_engine_output.txt`
- `pro_delivery_output.txt`
- `trader_delivery_output.txt`
- `health_output.txt`

Retention: 7 days

---

## Troubleshooting

### Emails Not Sending

1. Check `BREVO_API_KEY` is set
2. Check `EMAIL_FROM` is configured
3. Run preflight: `python -m src.alerts.runner --preflight`
4. Check user has email enabled in preferences
5. Check user hasn't exceeded daily quota

### Duplicate Emails

Should not happen due to:
- Unique constraint on `(user_id, alert_event_id, channel)`
- `FOR UPDATE SKIP LOCKED` in send loop
- Advisory locks per phase

### Retry Storm

Circuit breaker `ALERTS_MAX_SEND_PER_RUN` prevents runaway retries.
If hitting limit, check for permanent failures being misclassified.

---

## Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | - | PostgreSQL connection string |
| `BREVO_API_KEY` | Yes* | - | Brevo API key for email |
| `EMAIL_PROVIDER` | No | brevo | Email provider (brevo/resend) |
| `EMAIL_FROM` | Yes | - | Sender address |
| `TELEGRAM_BOT_TOKEN` | Yes* | - | Telegram bot token |
| `TWILIO_ACCOUNT_SID` | No | - | Twilio account SID |
| `TWILIO_AUTH_TOKEN` | No | - | Twilio auth token |
| `TWILIO_PHONE_NUMBER` | No | - | Twilio sender number |
| `ALERTS_V2_ENABLED` | No | true | Enable/disable entire system |
| `ALERTS_EMAIL_ENABLED` | No | true | **Enable/disable email channel** |
| `ALERTS_MAX_SEND_PER_RUN` | No | 1000 | Circuit breaker limit |
| `ALERTS_MAX_ATTEMPTS` | No | 5 | Max retry attempts |
| `ALERTS_RETRY_BASE_SECONDS` | No | 60 | Base retry delay |
| `ALERTS_RETRY_MAX_SECONDS` | No | 3600 | Max retry delay |
| `ALERTS_SEND_ALLOWLIST_USER_IDS` | No | - | Allowlist for controlled rollout |

*At least one channel (email or telegram) must be configured.
