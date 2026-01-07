# EnergyRiskIQ - Event Ingestion & Risk Intelligence Pipeline (v0.3)

A Python-based event ingestion, classification, AI enrichment, and risk scoring pipeline for energy risk intelligence.

## Features

- **RSS Feed Ingestion**: Fetches events from 3 news sources (geopolitical, energy, supply chain)
- **Automatic Classification**: Categorizes events with keyword matching + category hints
- **AI Enrichment**: Processes events with GPT to generate summaries and market impact analysis
- **Risk Scoring**: Converts AI-enriched events into quantitative risk scores
- **Rolling Risk Indices**: Computes 7-day and 30-day regional risk levels (0-100)
- **Asset-Level Risk**: Tracks risk direction for oil, gas, fx, and freight
- **REST API**: Access events, AI analysis, and risk data via FastAPI endpoints

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
  /api
    app.py            # FastAPI application
    routes.py         # Event API endpoints
    risk_routes.py    # Risk API endpoints
  main.py             # Main entrypoint
```

## Setup

### Environment Variables

The `DATABASE_URL` is automatically provided by Replit's PostgreSQL integration.

**AI Processing** uses Replit AI Integrations (no API key required).

Optional settings:
- `OPENAI_MODEL`: Model to use (default: gpt-4.1-mini)
- `AI_MAX_EVENTS_PER_RUN`: Max events per AI run (default: 20)

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

This scores AI-processed events and computes regional/asset risk indices.

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

## Risk Scoring System

### What Risk Scores Mean

Risk scores are **relative measures** from 0-100:
- **0-25**: Low relative risk
- **26-50**: Moderate risk
- **51-75**: Elevated risk
- **76-100**: High risk (near recent maximum)

### How Scoring Works

**Event-Level Weighted Score:**
```
weighted_score = base_severity × ai_confidence × category_weight × recency_decay
```

Where:
- `base_severity`: 1-5 from classification
- `ai_confidence`: Average confidence from AI impact analysis
- `category_weight`: geopolitical=1.2, energy=1.5, supply_chain=1.0
- `recency_decay`: exp(-days_since_event / 14)

**Rolling Normalization:**
- Scores are normalized to 0-100 using a rolling 90-day maximum
- This provides relative context: "Is risk high compared to recent history?"

**Trend Detection:**
- `rising`: Current 7-day score is >10% higher than previous 7 days
- `falling`: Current 7-day score is >10% lower than previous 7 days
- `stable`: Within ±10%

### Asset Direction Logic

Asset directions (oil, gas, fx, freight) are aggregated from AI impact analysis:
- Events vote for directions weighted by confidence
- Majority direction wins (with 20% threshold for decisiveness)
- `mixed` when votes are split, `unclear` when insufficient data

## Disclaimer

Risk scores are **informational indicators only**. They represent relative risk levels based on news event analysis and should not be used as the sole basis for investment, trading, or business decisions. Always consult professional advisors and conduct independent research.

## Database Schema

### Core Tables
- **events**: News events with classification and AI enrichment
- **ingestion_runs**: Ingestion run history

### Risk Tables
- **risk_events**: Per-event normalized risk contributions
- **risk_indices**: Rolling aggregate risk scores by region
- **asset_risk**: Asset-specific risk signals

## Recent Changes

### v0.3 (2026-01-07) - Risk Scoring Engine
- Added risk_events, risk_indices, asset_risk tables
- Implemented weighted scoring with recency decay
- Rolling regional risk indices (7d, 30d)
- Asset-level risk tracking (oil, gas, fx, freight)
- New /risk/* API endpoints

### v0.2 (2026-01-07) - AI Processing
- Added AI processing worker with OpenAI integration
- AI-generated summaries and market impact analysis

### v0.1 (2026-01-07) - Initial Release
- RSS ingestion from 3 feeds
- Keyword-based classification
- FastAPI endpoints
