# EnergyRiskIQ - Event Ingestion & Risk Intelligence Pipeline

## Overview
EnergyRiskIQ is an event ingestion, classification, AI analysis, and risk scoring pipeline for energy risk intelligence. It fetches news events from RSS feeds, classifies them, enriches them with AI, and computes quantitative risk scores.

**Current State**: Step 4 complete - Monetizable alerts engine with plan gating.

## Project Architecture

```
/src
  /config
    feeds.json        # RSS feed configuration with category_hint
  /db
    db.py             # PostgreSQL connection helper using psycopg2
    migrations.py     # Creates tables and adds columns safely
  /ingest
    rss_fetcher.py    # Fetches RSS feeds with category_hint passthrough
    classifier.py     # Keyword classification with hint tie-breaking
    ingest_runner.py  # Orchestrates ingestion with detailed stats
  /ai
    ai_worker.py      # AI processing worker using OpenAI
  /risk
    risk_engine.py    # Risk scoring and aggregation engine
  /alerts
    alerts_engine.py  # Alert evaluation and sending
    channels.py       # Email (Resend/Brevo) and Telegram delivery
    templates.py      # Alert message templates and marketing copy
  /plans
    plan_helpers.py   # Plan defaults, enforcement helpers, migration
  /api
    app.py            # FastAPI application with CORS
    routes.py         # Event API endpoints
    risk_routes.py    # Risk API endpoints
    alert_routes.py   # Alert API endpoints
    marketing_routes.py # Marketing copy endpoints
    telegram_routes.py # Telegram bot webhook and linking
  main.py             # Main entrypoint (--mode api/ingest/ai/risk/alerts/migrate_plans)
```

## Tech Stack
- **Language**: Python 3.11
- **Web Framework**: FastAPI with uvicorn
- **Database**: PostgreSQL (Replit-provided)
- **AI**: OpenAI via Replit AI Integrations (gpt-4.1-mini)
- **Email**: Resend or Brevo (optional)
- **Messaging**: Telegram Bot API (optional)
- **Dependencies**: feedparser, psycopg2-binary, openai, requests, python-dotenv

## Database Schema

### events table
- id, title, source_name, source_url (unique), category, region, severity_score
- event_time, raw_text, classification_reason, inserted_at
- processed, ai_summary, ai_impact_json, ai_model, ai_processed_at, ai_error, ai_attempts

### ingestion_runs table
- id, started_at, finished_at, status, total_items, inserted_items, skipped_duplicates, failed_items, notes

### risk_events table
- id, event_id (FK), region, category, base_severity, ai_confidence, weighted_score, created_at

### risk_indices table
- id, region, window_days (7|30), risk_score (0-100), trend (rising|falling|stable), calculated_at

### asset_risk table
- id, asset (oil|gas|fx|freight), region, window_days, risk_score (0-100), direction, calculated_at

### users table
- id, email (unique), telegram_chat_id, telegram_link_code, telegram_link_expires, created_at

### user_plans table (User-Plan Assignment + Denormalized Settings)
- user_id (PK/FK): References users table
- plan: free | personal | trader | pro | enterprise
- plan_price_usd: NUMERIC(10,2) - Synced from plan_settings.monthly_price_usd
- alerts_delay_minutes: INTEGER - Alert delivery delay (0 for pro/enterprise, 60 for others)
- allow_asset_alerts: BOOLEAN - Derived from ASSET_RISK_SPIKE in allowed_alert_types
- allow_telegram: BOOLEAN - Derived from delivery_config.telegram.enabled
- daily_digest_enabled: BOOLEAN - Derived from DAILY_DIGEST in allowed_alert_types
- allow_webhooks: BOOLEAN - Derived from delivery_config.sms.enabled
- max_total_alerts_per_day: INTEGER - max_email_alerts_per_day * 2
- max_email_alerts_per_day: INTEGER - Synced from plan_settings
- max_telegram_alerts_per_day: INTEGER - Same as max_email if telegram enabled, else 0
- preferred_realtime_channel: TEXT - Default 'email'
- custom_thresholds: BOOLEAN - True for pro/enterprise
- priority_processing: BOOLEAN - True for enterprise only
- created_at, updated_at

**Sync Mechanism**: 
- `apply_plan_settings_to_user(user_id, plan_code)` syncs user_plans with plan_settings
- Called automatically on signup/upgrade via `create_user_plan()`
- `sync_all_user_plans()` re-syncs all users (useful after admin updates plan_settings)

### user_alert_prefs table
- id, user_id (FK), region, alert_type, asset, threshold, enabled, cooldown_minutes

### alerts table
- id, user_id (FK), alert_type, region, asset, triggered_value, threshold
- title, message, channel, status, cooldown_key, created_at, sent_at, error

### alert_state table
- id, region, window_days, last_risk_score, last_7d_score, last_30d_score, last_asset_scores

### plan_settings table (Authoritative Source for Plan Features)
- plan_code (PK): free | personal | trader | pro | enterprise
- display_name: Human-readable plan name
- monthly_price_usd: Price in USD
- allowed_alert_types: TEXT[] of allowed alert types
- max_email_alerts_per_day: Email quota
- delivery_config: JSONB with email/telegram/sms/account_manager settings
- is_active, created_at, updated_at
- NOTE: This is the single source of truth for all plan features

## Running the Project

### API Server (default)
```bash
python src/main.py --mode api
```
Runs on **port 5000**.

### Run Ingestion
```bash
python src/main.py --mode ingest
```

### Run AI Processing
```bash
python src/main.py --mode ai
```

### Run Risk Scoring
```bash
python src/main.py --mode risk
```

### Run Alerts Engine
```bash
python src/main.py --mode alerts
```

## API Endpoints

### Landing Page
- `GET /` - Marketing landing page (Hero section)

### Events & AI
- `GET /health` - Health check
- `GET /events?category=&region=&min_severity=&processed=&limit=50` - Query events
- `GET /events/latest` - Get 20 most recent events with AI summary
- `GET /events/{id}` - Get full event detail with ai_impact analysis
- `GET /ai/stats` - AI processing statistics
- `GET /ingestion-runs` - View ingestion history

### Risk Intelligence
- `GET /risk/summary?region=Europe` - Current risk summary
- `GET /risk/regions` - Latest risk indices per region
- `GET /risk/regions/{region}` - Historical risk for a region
- `GET /risk/assets` - Asset-level risk by region
- `GET /risk/events` - View scored risk events

### Alerts
- `POST /alerts/test` - Create test user and preview alerts
- `POST /alerts/send-test-email` - Send test email via Brevo
- `GET /alerts/user/{user_id}` - View user's alert history

### Marketing
- `GET /marketing/samples` - Sample alert messages
- `GET /marketing/landing-copy` - Landing page copy blocks

### Digest
- `POST /digest/preview` - Preview daily digest without sending

### Operations
- `GET /ops/status` - Worker freshness status (last run times, staleness indicators)

### Internal Runner (Secured with INTERNAL_RUNNER_TOKEN)
- `POST /internal/run/ingest` - Trigger ingestion worker
- `POST /internal/run/ai` - Trigger AI processing worker
- `POST /internal/run/risk` - Trigger risk scoring worker
- `POST /internal/run/alerts` - Trigger alerts engine
- `POST /internal/run/digest` - Trigger daily digest worker

### User Authentication
- `GET /users` - User signup/signin page
- `GET /users/verify` - Email verification (redirects from email link)
- `GET /users/account` - User account dashboard (requires authentication)
- `POST /users/signup` - Register with email
- `POST /users/verify` - Verify email token
- `POST /users/set-password` - Set password and PIN after verification
- `POST /users/signin` - Sign in with email/password/PIN
- `POST /users/signout` - Sign out
- `GET /users/me` - Get current user info (requires X-User-Token header)
- `GET /users/alerts` - Get user's alert history (requires X-User-Token header)
- `POST /users/resend-verification` - Resend verification email

### Admin UI
- `GET /admin` - Admin portal with login (emicon / Regen@3010 / PIN: 342256)

### Admin API (Secured with X-Admin-Token header or session token)
- `POST /admin/login` - Authenticate and get session token
- `POST /admin/logout` - Invalidate session
- `GET /admin/plan-settings` - List all plan settings
- `GET /admin/plan-settings/{plan_code}` - Get single plan settings
- `PUT /admin/plan-settings/{plan_code}` - Update plan settings (price, alert types, delivery config)

## Subscription Tiers (from plan_settings table)

| Plan | Price | Email/Day | Alert Types | Telegram | SMS |
|------|-------|-----------|-------------|----------|-----|
| Free | $0 | 2 | HIGH_IMPACT_EVENT | No | No |
| Personal | $9.95 | 4 | +REGIONAL_RISK_SPIKE | No | No |
| Trader | $29 | 8 | +ASSET_RISK_SPIKE | Yes | No |
| Pro | $49 | 15 | +DAILY_DIGEST | Yes | Yes |
| Enterprise | $129 | 30 | ALL | Yes | Yes |

## Alert Types
- **REGIONAL_RISK_SPIKE**: Europe risk crosses threshold or +20%
- **ASSET_RISK_SPIKE**: Oil/gas/fx/freight risk crosses threshold
- **HIGH_IMPACT_EVENT**: Severity ≥4 events in key regions
- **DAILY_DIGEST**: Daily summary (placeholder)

## Environment Variables

### Email (optional)
- `EMAIL_PROVIDER`: resend | brevo | smtp
- `EMAIL_FROM`: Sender address
- `RESEND_API_KEY` or `BREVO_API_KEY`

### Telegram (optional)
- `TELEGRAM_BOT_TOKEN`: Bot token

### Alerts Loop
- `ALERTS_LOOP`: true to run continuously
- `ALERTS_LOOP_INTERVAL`: Seconds between runs (default 600)

### Internal Runner
- `INTERNAL_RUNNER_TOKEN`: Secret token for /internal/run/* endpoints

### Production URL
- `APP_URL`: Production domain for email verification links (https://energyriskiq.com)

## Operations & Scheduling

See **[OPERATIONS.md](OPERATIONS.md)** for detailed documentation on:
- GitHub Actions scheduler workflows
- Background worker architecture (Ingest, AI, Risk, Alerts)
- Internal runner endpoints and authentication

## Recent Changes
- 2026-01-14: Telegram account linking - Users on Trader/Pro/Enterprise plans can now link their Telegram accounts from the dashboard Settings page. Uses secure time-limited codes (15 min expiry), plan enforcement server-side, and bot webhook for /start, /status, /help, /unlink commands.
- 2026-01-14: Alert processing fix - Expanded HIGH_SEVERITY_KEYWORDS to include crisis, turmoil, halt, suspend, collapse, war, conflict, seize, capture, embargo, invasion, emergency, critical. Previous keywords (attack, missile, explosion, shutdown, blockade, sanctions) were too restrictive.
- 2026-01-14: Alert UI improvements - Added 24-hour filter, Latest badge for <3hr alerts, date/time filter, risk as percentage, upgrade sidebar card, cleaner type labels.
- 2026-01-13: User plans sync - user_plans now syncs with plan_settings via apply_plan_settings_to_user(). plan_price_usd is NUMERIC(10,2). Added sync_all_user_plans() for bulk resync.
- 2026-01-13: Step 7 - User authentication system with signup, email verification, password/PIN setup, and account dashboard at /users.
- 2026-01-13: Step 6 - Admin UI page at /admin with server-side authentication, header, left navigation, dashboard, and plan settings management.
- 2026-01-13: Step 5.1 - Comprehensive migration: plan_settings is now single source of truth for all plan features. user_plans simplified to only store user-plan assignment.
- 2026-01-13: Step 5 - Admin-configurable plan_settings table with GET/PUT API endpoints
- 2026-01-09: Step 4.2 - Authoritative user_plans table with enforcement helpers
- 2026-01-09: Step 4.1 - Go-Live Hardening (Brevo, Digest, Upgrade hooks, UTC quota)
- 2026-01-08: Step 4 - Alerts engine with monetization
- 2026-01-07: Step 3 - Risk scoring engine complete
- 2026-01-07: Step 2 - AI processing worker
- 2026-01-07: Step 1 - RSS ingestion and classification
