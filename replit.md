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
  /api
    app.py            # FastAPI application with CORS
    routes.py         # Event API endpoints
    risk_routes.py    # Risk API endpoints
    alert_routes.py   # Alert API endpoints
    marketing_routes.py # Marketing copy endpoints
  main.py             # Main entrypoint (--mode api/ingest/ai/risk/alerts)
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
- id, email (unique), telegram_chat_id, created_at

### user_plans table
- user_id (PK/FK), plan (free|trader|pro), alerts_delay_minutes, max_alerts_per_day
- allow_asset_alerts, allow_telegram, daily_digest_enabled, weekly_digest_enabled

### user_alert_prefs table
- id, user_id (FK), region, alert_type, asset, threshold, enabled, cooldown_minutes

### alerts table
- id, user_id (FK), alert_type, region, asset, triggered_value, threshold
- title, message, channel, status, cooldown_key, created_at, sent_at, error

### alert_state table
- id, region, window_days, last_risk_score, last_7d_score, last_30d_score, last_asset_scores

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
- `GET /alerts/user/{user_id}` - View user's alert history

### Marketing
- `GET /marketing/samples` - Sample alert messages
- `GET /marketing/landing-copy` - Landing page copy blocks

### Internal Runner (Secured with INTERNAL_RUNNER_TOKEN)
- `POST /internal/run/ingest` - Trigger ingestion worker
- `POST /internal/run/ai` - Trigger AI processing worker
- `POST /internal/run/risk` - Trigger risk scoring worker
- `POST /internal/run/alerts` - Trigger alerts engine

## Subscription Tiers

| Plan | Delay | Max/Day | Asset Alerts | Telegram | Digest |
|------|-------|---------|--------------|----------|--------|
| Free | 60m | 2 | No | No | No |
| Trader | 0 | 20 | Yes | No | Yes |
| Pro | 0 | 50 | Yes | Yes | Yes |

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

## Recent Changes
- 2026-01-08: Step 4 - Alerts engine with monetization
- 2026-01-07: Step 3 - Risk scoring engine complete
- 2026-01-07: Step 2 - AI processing worker
- 2026-01-07: Step 1 - RSS ingestion and classification
