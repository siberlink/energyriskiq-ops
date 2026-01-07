# EnergyRiskIQ - Event Ingestion & Risk Intelligence Pipeline

## Overview
EnergyRiskIQ is an event ingestion, classification, AI analysis, and risk scoring pipeline for energy risk intelligence. It fetches news events from RSS feeds, classifies them, enriches them with AI, and computes quantitative risk scores.

**Current State**: Step 3 complete - Risk scoring engine with regional indices and asset-level risk.

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
  /api
    app.py            # FastAPI application with CORS
    routes.py         # Event API endpoints
    risk_routes.py    # Risk API endpoints
  main.py             # Main entrypoint (--mode api/ingest/ai/risk)
```

## Tech Stack
- **Language**: Python 3.11
- **Web Framework**: FastAPI with uvicorn
- **Database**: PostgreSQL (Replit-provided)
- **AI**: OpenAI via Replit AI Integrations (gpt-4.1-mini)
- **Dependencies**: feedparser, psycopg2-binary, openai, python-dotenv

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

## Risk Scoring Logic

### Event-Level Weighted Score
```
weighted_score = base_severity × ai_confidence × category_weight × recency_decay
```
- category_weight: geopolitical=1.2, energy=1.5, supply_chain=1.0
- recency_decay: exp(-days_since_event / 14)

### Rolling Regional Risk Index
1. Sum weighted_scores for events in window (7d or 30d)
2. Normalize to 0-100 using rolling 90-day max
3. Trend: compare current 7d vs previous 7d (±10% threshold)

### Asset-Level Risk
- Aggregate AI impact directions per asset (oil, gas, fx, freight)
- Weight by event contribution and confidence
- Direction: majority vote with 20% threshold

## Recent Changes
- 2026-01-07: Step 3 - Risk scoring engine complete
- 2026-01-07: Added risk_events, risk_indices, asset_risk tables
- 2026-01-07: Added /risk/* API endpoints
- 2026-01-07: Step 2 - AI processing worker
- 2026-01-07: Step 1 - RSS ingestion and classification
