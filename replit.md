# EnergyRiskIQ - Event Ingestion Pipeline

## Overview
EnergyRiskIQ is an event ingestion and classification pipeline for energy risk intelligence. It fetches news events from RSS feeds, classifies them by category (geopolitical, energy, supply_chain), identifies regions, and assigns severity scores.

**Current State**: Step 1 complete - Event ingestion pipeline with PostgreSQL storage and REST API.

## Project Architecture

```
/src
  /config
    feeds.json        # RSS feed configuration (editable without code changes)
  /db
    db.py             # PostgreSQL connection helper using psycopg2
    migrations.py     # Creates events and ingestion_runs tables
  /ingest
    rss_fetcher.py    # Fetches and parses RSS feeds using feedparser
    classifier.py     # Keyword-based category/region/severity classification
    ingest_runner.py  # Orchestrates ingestion runs with logging
  /api
    app.py            # FastAPI application with CORS
    routes.py         # API endpoints: /health, /events, /events/latest
  main.py             # Main entrypoint (--mode api or --mode ingest)
```

## Tech Stack
- **Language**: Python 3.11
- **Web Framework**: FastAPI with uvicorn
- **Database**: PostgreSQL (Replit-provided)
- **Dependencies**: feedparser, psycopg2-binary, python-dotenv

## Database Schema

### events table
- id, title, source_name, source_url (unique), category, region, severity_score, event_time, raw_text, inserted_at
- Indexes on: inserted_at DESC, category, region, severity_score

### ingestion_runs table
- id, started_at, finished_at, status (running|success|failed), notes

## Running the Project

### API Server (default)
```bash
python src/main.py --mode api
```
Runs on port 5000.

### Run Ingestion
```bash
python src/main.py --mode ingest
# or
python -m src.ingest.ingest_runner
```

## API Endpoints

- `GET /health` - Health check
- `GET /events?category=&region=&min_severity=&limit=50` - Query events
- `GET /events/latest` - Get 20 most recent events
- `GET /ingestion-runs` - View ingestion history

## Classification Logic

### Categories (keyword-based)
- **geopolitical**: war, attack, missile, conflict, sanctions, embargo, etc.
- **energy**: OPEC, crude, oil, gas, LNG, refinery, etc.
- **supply_chain**: port, shipping, freight, container, strike, etc.

### Regions
Europe, Middle East, Black Sea, North Africa, Asia, North America, Global

### Severity (1-5)
- Base: 2
- +2: attack, missile, explosion, shutdown, blockade, sanctions
- +1: strike, disruption, outage, congestion
- +1: OPEC, production cut

## Recent Changes
- 2026-01-07: Initial Step 1 implementation complete
  - PostgreSQL database with events and ingestion_runs tables
  - RSS ingestion from 3 sources (Reuters, OilPrice, FreightWaves)
  - Keyword-based classification for category, region, severity
  - FastAPI endpoints for querying events
