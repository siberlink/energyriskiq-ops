# EnergyRiskIQ - Event Ingestion & AI Analysis Pipeline

## Overview
EnergyRiskIQ is an event ingestion, classification, and AI analysis pipeline for energy risk intelligence. It fetches news events from RSS feeds, classifies them, and enriches them with AI-generated summaries and market impact analysis.

**Current State**: Step 2 complete - AI processing worker with OpenAI integration for event enrichment.

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
  /api
    app.py            # FastAPI application with CORS
    routes.py         # API endpoints including AI stats
  main.py             # Main entrypoint (--mode api/ingest/ai)
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
- id, started_at, finished_at, status (running|success|failed)
- total_items, inserted_items, skipped_duplicates, failed_items, notes

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
Processes unprocessed events with AI enrichment.

## API Endpoints

- `GET /health` - Health check
- `GET /events?category=&region=&min_severity=&processed=&limit=50` - Query events
- `GET /events/latest` - Get 20 most recent events with AI summary
- `GET /events/{id}` - Get full event detail with ai_impact analysis
- `GET /ai/stats` - AI processing statistics
- `GET /ingestion-runs` - View ingestion history

## AI Processing

Uses Replit AI Integrations (OpenAI-compatible, no API key needed).

### Output Structure
- **ai_summary**: 2-3 sentence neutral summary
- **ai_impact_json**: Full structured analysis including:
  - Impact on oil, gas, fx, freight (direction, confidence, rationale)
  - Key facts, entities (countries, companies, commodities, routes)
  - Risk flags (sanctions, supply_disruption, military_escalation, etc.)
  - Time horizon estimate

### Configuration
- `OPENAI_MODEL`: gpt-4.1-mini (default)
- `AI_MAX_EVENTS_PER_RUN`: 20 (default)
- `AI_TEMPERATURE`: 0.2 (default)

## Classification Logic

### Categories (keyword-based with hint tie-breaking)
- **geopolitical**: war, attack, missile, conflict, sanctions, etc.
- **energy**: OPEC, crude, oil, gas, LNG, refinery, etc.
- **supply_chain**: port, shipping, freight, container, strike, etc.

### Regions
Europe, Middle East, Black Sea, North Africa, Asia, North America, Global

### Severity (1-5)
Based on keyword severity: attack (+2), strike (+1), OPEC (+1), etc.

## Recent Changes
- 2026-01-07: Step 2 - Added AI processing worker
- 2026-01-07: Added ai_summary, ai_impact_json columns
- 2026-01-07: Added GET /events/{id} and GET /ai/stats endpoints
- 2026-01-07: Step 1.1 - Added 3rd feed, category hints, classification tracking
- 2026-01-07: Initial Step 1 implementation
