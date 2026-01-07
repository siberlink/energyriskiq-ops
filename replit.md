# EnergyRiskIQ - Event Ingestion Pipeline

## Overview
EnergyRiskIQ is an event ingestion and classification pipeline for energy risk intelligence. It fetches news events from RSS feeds, classifies them by category (geopolitical, energy, supply_chain), identifies regions, and assigns severity scores.

**Current State**: Step 1.1 complete - Hardened event ingestion with 3 feeds, category hints, and classification tracking.

## Project Architecture

```
/src
  /config
    feeds.json        # RSS feed configuration with category_hint support
  /db
    db.py             # PostgreSQL connection helper using psycopg2
    migrations.py     # Creates tables and adds new columns safely
  /ingest
    rss_fetcher.py    # Fetches RSS feeds with category_hint passthrough
    classifier.py     # Keyword classification with hint tie-breaking
    ingest_runner.py  # Orchestrates ingestion with detailed stats
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
- id, title, source_name, source_url (unique), category, region, severity_score
- event_time, raw_text, classification_reason, inserted_at
- Indexes on: inserted_at DESC, category, region, severity_score

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
# or
python -m src.ingest.ingest_runner
```

## API Endpoints

- `GET /health` - Health check
- `GET /events?category=&region=&min_severity=&limit=50` - Query events
- `GET /events/latest` - Get 20 most recent events
- `GET /ingestion-runs` - View ingestion history with stats

## Classification Logic

### Categories (keyword-based with hint tie-breaking)
- **geopolitical**: war, attack, missile, conflict, sanctions, embargo, etc.
- **energy**: OPEC, crude, oil, gas, LNG, refinery, etc.
- **supply_chain**: port, shipping, freight, container, strike, etc.

### Classification Process
1. Count keyword matches for each category
2. If clear winner, use it
3. If tie, use category_hint from feed config
4. If still tied, priority: energy > geopolitical > supply_chain
5. If no keywords, use hint or default to geopolitical

### classification_reason Format
```
energy_keywords=3;geo_keywords=1;sc_keywords=0;hint=energy;chosen=energy;decision=keyword_winner
```

### Regions
Europe, Middle East, Black Sea, North Africa, Asia, North America, Global

### Severity (1-5)
- Base: 2
- +2: attack, missile, explosion, shutdown, blockade, sanctions
- +1: strike, disruption, outage, congestion
- +1: OPEC, production cut

## Feed Configuration

Edit `src/config/feeds.json`:
```json
[
  {"source_name": "Al Jazeera News", "feed_url": "...", "category_hint": "geopolitical"},
  {"source_name": "OilPrice.com", "feed_url": "...", "category_hint": "energy"},
  {"source_name": "FreightWaves", "feed_url": "...", "category_hint": "supply_chain"}
]
```

## Recent Changes
- 2026-01-07: Step 1.1 - Added 3rd geopolitical feed (Al Jazeera)
- 2026-01-07: Added category_hint tie-breaker for classification
- 2026-01-07: Added classification_reason column for debugging
- 2026-01-07: Added detailed stats columns to ingestion_runs
- 2026-01-07: Initial Step 1 implementation complete
