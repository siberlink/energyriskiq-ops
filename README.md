# EnergyRiskIQ - Event Ingestion & Risk Intelligence Pipeline (v0.4)

A Python-based event ingestion, classification, AI enrichment, risk scoring, and alerting pipeline for energy risk intelligence.

## Features

- **RSS Feed Ingestion**: Fetches events from 3 news sources (geopolitical, energy, supply chain)
- **Automatic Classification**: Categorizes events with keyword matching + category hints
- **AI Enrichment**: Processes events with GPT to generate summaries and market impact analysis
- **Risk Scoring**: Converts AI-enriched events into quantitative risk scores
- **Rolling Risk Indices**: Computes 7-day and 30-day regional risk levels (0-100)
- **Asset-Level Risk**: Tracks risk direction for oil, gas, fx, and freight
- **Monetizable Alerts**: Tiered subscription system (Free/Trader/Pro) with plan gating
- **REST API**: Access events, AI analysis, risk data, and alerts via FastAPI endpoints

## Subscription Tiers (Monetization Ready)

| Feature | Free | Trader (€29-49/mo) | Pro (€99-149/mo) |
|---------|------|-------------------|------------------|
| Regions | Europe only | Europe | All regions |
| Alert Types | Risk Spike only | All alerts | All alerts + custom thresholds |
| Channels | Email (delayed 60m) | Email (real-time) | Email + Telegram |
| Daily Digest | No | Yes | Yes |
| Max Alerts/Day | 2 | 20 | 50 |

## Project Structure

```
/src
  /config
    feeds.json        # RSS feed configuration
  /db
    db.py             # Database connection helper
    migrations.py     # Table creation and schema updates
  /ingest
    rss_fetcher.py    # RSS feed fetching
    classifier.py     # Category/region/severity classification
    ingest_runner.py  # Orchestrates ingestion runs
  /ai
    ai_worker.py      # AI processing worker
  /risk
    risk_engine.py    # Risk scoring and aggregation engine
  /alerts
    alerts_engine.py  # Alert evaluation and sending
    channels.py       # Email and Telegram delivery
    templates.py      # Alert message templates
  /api
    app.py            # FastAPI application
    routes.py         # Event API endpoints
    risk_routes.py    # Risk API endpoints
    alert_routes.py   # Alert API endpoints
    marketing_routes.py # Marketing copy endpoints
  main.py             # Main entrypoint
```

## Setup

### Environment Variables

The `DATABASE_URL` is automatically provided by Replit's PostgreSQL integration.

**AI Processing** uses Replit AI Integrations (no API key required).

**Email Sending** (optional):
- `EMAIL_PROVIDER`: `resend` | `brevo` | `smtp`
- `EMAIL_FROM`: Sender email address
- `RESEND_API_KEY`: For Resend provider
- `BREVO_API_KEY`: For Brevo provider

**Telegram Alerts** (optional):
- `TELEGRAM_BOT_TOKEN`: Your Telegram bot token
- Users provide their `telegram_chat_id` (Pro tier only)

## Usage

### Run the API Server

```bash
python src/main.py --mode api
```

The API runs on **port 5000**.

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

For continuous alerting (every 10 minutes):
```bash
ALERTS_LOOP=true python src/main.py --mode alerts
```

### Full Pipeline

```bash
python src/main.py --mode ingest
python src/main.py --mode ai
python src/main.py --mode risk
python src/main.py --mode alerts
```

## API Endpoints

### Events & AI
- `GET /health` - Health check
- `GET /events` - Query events with filters
- `GET /events/latest` - Get 20 most recent events
- `GET /events/{id}` - Get full event with AI analysis
- `GET /ai/stats` - AI processing statistics
- `GET /ingestion-runs` - View ingestion history

### Risk Intelligence
- `GET /risk/summary` - Current risk summary for a region
- `GET /risk/regions` - Latest risk indices for all regions
- `GET /risk/regions/{region}` - Historical risk data for a region
- `GET /risk/assets` - Asset-level risk by region
- `GET /risk/events` - View scored risk events

### Alerts
- `POST /alerts/test` - Create test user and preview alerts
- `GET /alerts/user/{user_id}` - View user's alert history

### Marketing
- `GET /marketing/samples` - Sample alert messages
- `GET /marketing/landing-copy` - Landing page copy blocks

## Alert Types

### 1. Regional Risk Spike
Triggers when Europe risk score:
- Crosses threshold (default 70)
- Increases by ≥20% vs previous snapshot

### 2. Asset Risk Spike
Triggers when asset risk score crosses threshold (default 70).
Assets: oil, gas, fx, freight

### 3. High-Impact Event
Triggers for new events with:
- Severity ≥ 4
- Category: energy or geopolitical
- Region: Europe, Middle East, or Black Sea

## Risk Scoring System

Risk scores are **relative measures** from 0-100:
- **0-25**: Low relative risk
- **26-50**: Moderate risk
- **51-75**: Elevated risk
- **76-100**: High risk (near recent maximum)

**Event-Level Weighted Score:**
```
weighted_score = base_severity × ai_confidence × category_weight × recency_decay
```

**Rolling Normalization:**
Scores are normalized using a rolling 90-day maximum.

## Scheduling Alerts

For production, schedule the alerts engine to run every 10 minutes:

**Option 1: Replit Scheduled Tasks**
Set up a scheduled task in Replit to run `python src/main.py --mode alerts`

**Option 2: Loop Mode**
```bash
ALERTS_LOOP=true ALERTS_LOOP_INTERVAL=600 python src/main.py --mode alerts
```

## Disclaimer

EnergyRiskIQ provides **informational risk indicators only**. This is not investment advice. Always conduct your own research and consult qualified professionals before making trading or business decisions.

## Database Schema

### Core Tables
- **events**: News events with classification and AI enrichment
- **ingestion_runs**: Ingestion run history

### Risk Tables
- **risk_events**: Per-event normalized risk contributions
- **risk_indices**: Rolling aggregate risk scores by region
- **asset_risk**: Asset-specific risk signals

### Alerts Tables
- **users**: User accounts (email, telegram_chat_id)
- **user_plans**: Subscription tier and limits
- **user_alert_prefs**: Per-user alert preferences
- **alerts**: Alert history with status
- **alert_state**: State for deduplication and trend comparison

## Recent Changes

### v0.4 (2026-01-08) - Alerts Engine
- Added monetizable alerts with Free/Trader/Pro tiers
- Regional risk spike, asset risk, and high-impact event alerts
- Email and Telegram delivery channels
- Cooldown and max alerts/day anti-spam protections
- Marketing endpoints with sample alerts and landing copy

### v0.3 (2026-01-07) - Risk Scoring Engine
- Rolling regional risk indices (7d, 30d)
- Asset-level risk tracking (oil, gas, fx, freight)

### v0.2 (2026-01-07) - AI Processing
- AI-generated summaries and market impact analysis

### v0.1 (2026-01-07) - Initial Release
- RSS ingestion from 3 feeds
- Keyword-based classification
