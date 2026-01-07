# EnergyRiskIQ - Event Ingestion Pipeline (v0.1.1)

A Python-based event ingestion and classification pipeline for energy risk intelligence.

## Features

- **RSS Feed Ingestion**: Fetches events from 3 news sources (geopolitical, energy, supply chain)
- **Automatic Classification**: Categorizes events with keyword matching + category hints
- **Region Detection**: Identifies geographic regions from event content
- **Severity Scoring**: Assigns severity scores (1-5) based on keywords
- **Classification Tracking**: Stores classification reasoning for debugging
- **Duplicate Prevention**: Skips already-ingested events
- **REST API**: Access events via FastAPI endpoints

## Project Structure

```
/src
  /config
    feeds.json        # RSS feed configuration (add/edit feeds here)
  /db
    db.py             # Database connection helper
    migrations.py     # Table creation and schema updates
  /ingest
    rss_fetcher.py    # RSS feed fetching with category_hint support
    classifier.py     # Category/region/severity classification
    ingest_runner.py  # Orchestrates ingestion runs with stats
  /api
    app.py            # FastAPI application
    routes.py         # API endpoints
  main.py             # Main entrypoint
```

## Setup

### Environment Variables

The `DATABASE_URL` is automatically provided by Replit's PostgreSQL integration.

Optional variables:
- `LOG_LEVEL`: Logging level (default: INFO)
- `INGESTION_USER_AGENT`: Custom user agent for RSS fetching

### Configure Feeds

Edit `src/config/feeds.json` to add or modify RSS feed sources:

```json
[
  {
    "source_name": "Source Name",
    "feed_url": "https://example.com/rss",
    "category_hint": "energy"
  }
]
```

**category_hint values**: `geopolitical`, `energy`, `supply_chain`

The hint is used as a tie-breaker when keyword matching produces equal scores.

## Usage

### Run the API Server

```bash
python src/main.py --mode api
```

The API runs on **port 5000**.

Or directly with uvicorn:
```bash
uvicorn src.api.app:app --host 0.0.0.0 --port 5000
```

### Run Ingestion

```bash
python src/main.py --mode ingest
```

Or:
```bash
python -m src.ingest.ingest_runner
```

## API Endpoints

### Health Check
```
GET /health
```
Returns: `{"status": "ok"}`

### Get Events
```
GET /events?category=energy&region=Europe&min_severity=3&limit=50
```

Query parameters:
- `category`: Filter by category (geopolitical, energy, supply_chain)
- `region`: Filter by region (Europe, Middle East, Asia, etc.)
- `min_severity`: Minimum severity score (1-5)
- `limit`: Number of results (default: 50, max: 200)

### Get Latest Events
```
GET /events/latest
```
Returns the 20 most recent events.

### Get Ingestion Runs
```
GET /ingestion-runs?limit=10
```
Returns recent ingestion run logs with detailed stats.

## Classification Logic

### Categories
- **geopolitical**: war, attack, missile, conflict, sanctions, embargo, etc.
- **energy**: OPEC, crude, oil, gas, LNG, refinery, etc.
- **supply_chain**: port, shipping, freight, container, strike, etc.

### Classification Process
1. Count keyword matches for each category
2. If one category has the most matches, use it
3. If there's a tie, use the feed's `category_hint` if it's among the tied categories
4. If still tied, use priority order: energy > geopolitical > supply_chain
5. If no keywords match, use `category_hint` or default to `geopolitical`

Each event stores a `classification_reason` field with debug info like:
```
energy_keywords=3;geo_keywords=1;sc_keywords=0;hint=energy;chosen=energy;decision=keyword_winner
```

### Regions
- Europe, Middle East, Black Sea, North Africa, Asia, North America, Global

### Severity Scoring
- Base score: 2
- +2 for: attack, missile, explosion, shutdown, blockade, sanctions
- +1 for: strike, disruption, outage, congestion
- +1 for: OPEC, production cut
- Range: 1-5

## Database Schema

### events table
- id, title, source_name, source_url (unique), category, region, severity_score
- event_time, raw_text, classification_reason, inserted_at

### ingestion_runs table
- id, started_at, finished_at, status
- total_items, inserted_items, skipped_duplicates, failed_items, notes

## Recent Changes

### v0.1.1 (2026-01-07)
- Added Al Jazeera as 3rd geopolitical RSS feed
- Added `category_hint` support for tie-breaking classification
- Added `classification_reason` column to track classification decisions
- Added detailed stats columns to ingestion_runs table
- Improved README documentation

### v0.1.0 (2026-01-07)
- Initial Step 1 implementation
- PostgreSQL database with events and ingestion_runs tables
- RSS ingestion from OilPrice and FreightWaves
- Keyword-based classification for category, region, severity
- FastAPI endpoints for querying events
