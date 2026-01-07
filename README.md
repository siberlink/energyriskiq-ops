# EnergyRiskIQ - Event Ingestion Pipeline (v0.1)

A Python-based event ingestion and classification pipeline for energy risk intelligence.

## Features

- **RSS Feed Ingestion**: Fetches events from multiple news sources
- **Automatic Classification**: Categorizes events as geopolitical, energy, or supply_chain
- **Region Detection**: Identifies geographic regions from event content
- **Severity Scoring**: Assigns severity scores (1-5) based on keywords
- **Duplicate Prevention**: Skips already-ingested events
- **REST API**: Access events via FastAPI endpoints

## Project Structure

```
/src
  /config
    feeds.json        # RSS feed configuration
  /db
    db.py             # Database connection helper
    migrations.py     # Table creation
  /ingest
    rss_fetcher.py    # RSS feed fetching
    classifier.py     # Category/region/severity classification
    ingest_runner.py  # Orchestrates ingestion runs
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

## Usage

### Run the API Server

```bash
python src/main.py --mode api
```

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
- `region`: Filter by region
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
Returns recent ingestion run logs.

## Classification Logic

### Categories
- **geopolitical**: war, attack, missile, conflict, sanctions, embargo, etc.
- **energy**: OPEC, crude, oil, gas, LNG, refinery, etc.
- **supply_chain**: port, shipping, freight, container, strike, etc.

### Regions
- Europe, Middle East, Black Sea, North Africa, Asia, North America, Global

### Severity Scoring
- Base score: 2
- +2 for: attack, missile, explosion, shutdown, blockade, sanctions
- +1 for: strike, disruption, outage, congestion
- +1 for: OPEC, production cut
- Range: 1-5
