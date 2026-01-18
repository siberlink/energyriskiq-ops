# EnergyRiskIQ - Event Ingestion & Risk Intelligence Pipeline

## Overview
EnergyRiskIQ is an event ingestion, classification, AI analysis, and risk scoring pipeline for energy risk intelligence. It fetches news events from RSS feeds, classifies them, enriches them with AI, and computes quantitative risk scores. The project aims to provide a comprehensive risk intelligence platform with a global alerts factory for fanout delivery.

## User Preferences
The user prefers clear, concise communication. They value an iterative development approach, with a focus on delivering functional components incrementally. They prefer to be consulted before any major architectural changes or significant code refactoring. Detailed explanations of complex features are appreciated, especially regarding AI models and risk scoring logic.

## System Architecture

EnergyRiskIQ is built with a modular architecture, separating concerns into distinct services for ingestion, AI processing, risk scoring, and alerting.

**UI/UX Decisions:**
- The project includes marketing landing pages, user authentication flows, and an admin portal.
- User-facing dashboards provide event queries, risk summaries, and alert history.
- Admin UI allows management of plan settings.

**Technical Implementations:**
- **Event Ingestion:** RSS feeds are fetched, categorized using keyword classification with hint tie-breaking.
- **AI Processing:** Uses OpenAI (gpt-4.1-mini) for event enrichment, generating summaries, and impact analysis.
- **Risk Scoring:** A dedicated engine computes quantitative risk scores for events, regions, and assets, and derives trends.
- **Alerting (v2):** A global alerts factory generates `alert_events` (user-agnostic) which are then fanned out to eligible users via `user_alert_deliveries`. This supports email, Telegram, and SMS channels with per-user quotas and cooldowns.
- **User Management:** Includes user signup, email verification, password/PIN setup, and plan assignment.
- **Plan Management:** `plan_settings` is the authoritative source for subscription tier features, which are synced with `user_plans`.
- **API:** A FastAPI application provides endpoints for events, risk intelligence, alerts, marketing content, and internal operations.

**Feature Specifications:**
- **Core Pipeline:** RSS Ingestion -> Classification -> AI Enrichment -> Risk Scoring.
- **Alert Types:** Supports `HIGH_IMPACT_EVENT`, `REGIONAL_RISK_SPIKE`, `ASSET_RISK_SPIKE`, and `DAILY_DIGEST`.
- **Delivery Channels:** Email (Resend/Brevo), Telegram Bot API.
- **User Plans:** Configurable subscription tiers (Free, Personal, Trader, Pro, Enterprise) with varying features, alert quotas, and delivery options.
- **Admin Interface:** Secure portal for managing plan settings and monitoring.

**System Design Choices:**
- **Database:** PostgreSQL is used for persistence, with a structured schema designed for events, ingestion runs, risk data, user management, and the new global alerts system.
- **Background Workers:** Ingestion, AI, Risk, and Alerts components are designed as separate workers that can be run independently or orchestrated.
- **Concurrency:** FastAPI with uvicorn for the API server, enabling asynchronous operations.
- **Production Safety (Alerts v2):** Advisory locks prevent concurrent phase execution, `event_fingerprint` unique constraint prevents duplicate alerts, `fanout_completed_at` ensures idempotent fanout, and `FOR UPDATE SKIP LOCKED` prevents delivery races.
- **Retry & Backoff (Alerts v2):** Exponential backoff with jitter for transient failures, max attempts enforcement, failure classification (transient vs permanent), and channel config validation (skips gracefully when secrets missing).
- **Digest Batching (Alerts v2):** Groups multiple alerts into periodic digest messages (daily/hourly). Digest deliveries are batched by user+channel+period, sent as a single consolidated message.

## User Alert Settings

Users can configure their alert preferences at `/users/account` under the Settings tab. Settings are constrained by their subscription plan.

### Plan Constraints
| Plan | Alert Types | Max Regions |
|------|-------------|-------------|
| **Free** | HIGH_IMPACT_EVENT | 1 |
| **Personal** | HIGH_IMPACT_EVENT, REGIONAL_RISK_SPIKE | 2 |
| **Trader** | HIGH_IMPACT_EVENT, REGIONAL_RISK_SPIKE, ASSET_RISK_SPIKE | 3 |
| **Pro** | All 4 types | Unlimited |
| **Enterprise** | All 4 types | Unlimited |

### Database Table
- `user_settings`: Stores per-user alert preferences with unique constraint on (user_id, alert_type, region, asset)

### API Endpoints
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/users/settings` | GET | Get user settings and plan constraints |
| `/users/settings` | POST | Add/update alert setting (validates plan limits) |
| `/users/settings/{id}` | DELETE | Remove an alert setting |

### Available Regions
Europe, Middle East, Asia, North America, Black Sea, North Africa, Global

### Automatic Settings Sync on Plan Upgrade
When a user upgrades their plan, `sync_user_settings_on_upgrade()` automatically:
1. Identifies newly available alert types for the new plan
2. Adds default settings for each new alert type (enabled, region: Europe)
3. Preserves all existing user settings (never deletes)
4. Respects the new plan's region limits when adding defaults

This is triggered automatically by `apply_plan_settings_to_user()` whenever a plan change occurs.

## Digest System (Alerts v2)

The digest system consolidates multiple alert deliveries into periodic summary messages:

### How Digests Work
1. **Phase B** creates deliveries with `delivery_kind='digest'` for lower-tier plans
2. **Phase D** groups these into `user_alert_digests` records by (user_id, channel, period)
3. **Phase C** sends the consolidated digest message with all events

### Digest Tables
- `user_alert_digests`: Tracks digest batches with unique `digest_key` for idempotency
- `user_alert_digest_items`: Links individual deliveries to their parent digest

### Digest Windows
- **Daily**: [00:00 UTC, 24:00 UTC) of previous day
- **Hourly**: [HH:00, HH+1:00) of previous hour

### Digest Idempotency
- `digest_key` is unique (format: `{user_id}:{channel}:{period}:{window_date}`)
- Re-running Phase D won't create duplicate digests
- Individual deliveries are marked `status='skipped', last_error='batched_into_digest'`

### CLI Commands
```bash
python -m src.alerts.runner --phase d          # Build digest batches only
python -m src.alerts.runner --phase all        # Full pipeline: A → B → D → C
python -m src.alerts.runner --phase all --dry-run  # Test without changes
```

## Environment Variables (Alerts v2)

| Variable | Default | Description |
|----------|---------|-------------|
| `ALERTS_MAX_ATTEMPTS` | 5 | Max delivery attempts before permanent failure |
| `ALERTS_RETRY_BASE_SECONDS` | 60 | Base delay for exponential backoff |
| `ALERTS_RETRY_MAX_SECONDS` | 3600 | Maximum retry delay cap |
| `ALERTS_RATE_LIMIT_EMAIL_PER_MINUTE` | 0 | Optional per-channel throttle (0=unlimited) |
| `ALERTS_RATE_LIMIT_TELEGRAM_PER_MINUTE` | 0 | Optional per-channel throttle (0=unlimited) |
| `ALERTS_RATE_LIMIT_SMS_PER_MINUTE` | 0 | Optional per-channel throttle (0=unlimited) |
| `ALERTS_DIGEST_PERIOD` | daily | Digest period: 'daily' or 'hourly' |
| `ALERTS_APP_BASE_URL` | https://energyriskiq.com | Base URL for dashboard links in digests |
| `ALERTS_SEND_ALLOWLIST_USER_IDS` | (none) | Comma-separated user IDs for controlled rollout |
| `ALERTS_MAX_SEND_PER_RUN` | 1000 | Circuit breaker: max sends per engine run |

## Production Hardening (Alerts v2)

The alerts engine includes safety features for controlled rollout and operational stability:

### Preflight Check (--preflight)
Validates environment before running:
- Database connectivity
- Required tables exist
- Channel configuration (email, telegram, sms)
- Returns JSON with errors/warnings

```bash
python -m src.alerts.runner --preflight
```

Example output:
```json
{
  "status": "ok",
  "checks": {
    "database": {"status": "ok"},
    "tables": {"status": "ok", "found": ["alert_events", "user_alert_deliveries", ...]},
    "channels": {
      "email": {"status": "ok", "provider": "brevo"},
      "telegram": {"status": "ok"},
      "sms": {"status": "warning", "message": "not_configured"}
    }
  },
  "errors": [],
  "warnings": ["SMS channel not configured"]
}
```

### Health Check (--health)
Fetches metrics without requiring HTTP server:

```bash
python -m src.alerts.runner --health
```

### User Allowlist
For controlled rollout, set `ALERTS_SEND_ALLOWLIST_USER_IDS`:
- Only allowlisted users receive alerts in Phase B (fanout) and Phase C (send)
- Comma-separated user IDs: `1,2,5,10`
- Leave unset for normal operation

### Circuit Breaker
`ALERTS_MAX_SEND_PER_RUN` prevents runaway sends:
- Default: 1000 sends per engine invocation
- When limit reached, Phase C stops early with `stopped_early: true`
- Protects against unexpected high volumes

### GitHub Actions Workflow
The `.github/workflows/alerts_engine_v2.yml` includes:
1. Preflight check (fails fast if environment invalid)
2. Engine run with all phases
3. Health check output
4. Summary annotation with metrics

Manual dispatch options:
- `skip_preflight`: Skip environment validation
- `phase`: Choose specific phase(s)
- `dry_run`: Test without changes
- `batch_size`: Control delivery batch size

## Engine Observability (Alerts v2)

The alerts engine includes comprehensive observability for production monitoring:

### Run Tracking Tables
- `alerts_engine_runs`: Tracks each engine invocation with run_id, phase, status, duration, and counts
- `alerts_engine_run_items`: Per-phase breakdown for multi-phase runs (e.g., --phase all)

### Triggered By Detection
- `github_actions_schedule`: Scheduled GitHub Actions run
- `github_actions_manual`: Manual GitHub Actions dispatch
- `local`: Local development run

### Admin Endpoints (Token Protected)
All endpoints require `x-internal-token: <INTERNAL_RUNNER_TOKEN>` header.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/internal/alerts/engine/runs` | GET | List recent engine runs |
| `/internal/alerts/engine/runs/{run_id}` | GET | Get run detail with phase breakdown |
| `/internal/alerts/engine/health` | GET | Delivery/digest health metrics |
| `/internal/alerts/engine/retry_failed` | POST | Re-queue failed items for retry |

### Example Curl Commands
```bash
# Get recent runs
curl -H "x-internal-token: $INTERNAL_RUNNER_TOKEN" \
  https://your-app.replit.dev/internal/alerts/engine/runs?limit=10

# Get health metrics
curl -H "x-internal-token: $INTERNAL_RUNNER_TOKEN" \
  https://your-app.replit.dev/internal/alerts/engine/health

# Get run detail
curl -H "x-internal-token: $INTERNAL_RUNNER_TOKEN" \
  https://your-app.replit.dev/internal/alerts/engine/runs/{run_id}

# Retry failed deliveries (dry-run first)
curl -X POST -H "x-internal-token: $INTERNAL_RUNNER_TOKEN" \
  "https://your-app.replit.dev/internal/alerts/engine/retry_failed?kind=deliveries&dry_run=true"
```

### Health Endpoint Response Example
```json
{
  "deliveries_24h": {
    "period_hours": 24,
    "by_channel": {
      "email": {"sent_instant": 5, "failed_instant": 1},
      "telegram": {"sent_instant": 3}
    },
    "oldest_queued_delivery_minutes": null
  },
  "digests_7d": {
    "period_days": 7,
    "by_channel": {"email": {"sent": 2}},
    "oldest_queued_digest_minutes": null
  },
  "generated_at": "2026-01-14T15:30:00"
}
```

## Smart Organic SEO Growth System

A system for generating SEO-optimized daily alerts pages with 24-hour delay for organic traffic acquisition.

### URL Structure
- `/alerts` - Alerts hub page with recent daily pages and monthly archives
- `/alerts/daily/YYYY-MM-DD` - Daily alerts page (e.g., /alerts/daily/2026-01-15)
- `/alerts/YYYY/MM` - Monthly archive (e.g., /alerts/2026/01)
- `/sitemap.xml` - Dynamic XML sitemap
- `/sitemap.html` - HTML sitemap for users

### SEO Features
- Dynamic SEO titles based on region and alert types
- Meta descriptions enriched with risk intelligence language
- Daily risk posture summaries (Elevated/Moderate/Stable)
- Top risk drivers analysis
- Internal linking for SEO authority flow
- Mobile-responsive templates with conversion CTAs

### 24-Hour Delay Enforcement
- API endpoint enforces: dates must be <= yesterday
- CLI allows arbitrary dates for backfill flexibility
- GitHub Actions triggers for yesterday's content daily

### CLI Commands
```bash
python -m src.seo.runner --yesterday           # Generate yesterday's page
python -m src.seo.runner --date 2026-01-15     # Specific date
python -m src.seo.runner --backfill 7          # Last 7 days
python -m src.seo.runner --yesterday --dry-run # Preview without saving
```

### API Endpoint
```bash
# POST /internal/run/seo with x-internal-token header
curl -X POST -H "x-internal-token: $INTERNAL_RUNNER_TOKEN" \
  "https://your-app.replit.dev/internal/run/seo?backfill=7"
```

### Database Tables
- `seo_daily_pages`: Stores generated page JSON by date
- `seo_page_views`: Tracks page view analytics

### Safety Features
- URL sanitization removes external links from headlines/body
- Public fields only (no premium data exposure)
- Idempotent page generation (upsert on date)
- GitHub Actions workflow with automatic daily triggering

## External Dependencies

- **Database:** PostgreSQL (Replit-provided)
- **AI:** OpenAI via Replit AI Integrations (gpt-4.1-mini)
- **Email Service:** Resend or Brevo
- **Messaging Service:** Telegram Bot API
- **SMS Service:** Twilio (optional, for SMS delivery)
- **Python Libraries:**
    - `FastAPI`: Web framework
    - `uvicorn`: ASGI server
    - `feedparser`: RSS feed parsing
    - `psycopg2-binary`: PostgreSQL adapter
    - `openai`: OpenAI API client
    - `requests`: HTTP client
    - `python-dotenv`: Environment variable management