# EnergyRiskIQ - Event Ingestion & AI Analysis Pipeline (v0.2)

A Python-based event ingestion, classification, and AI analysis pipeline for energy risk intelligence.

## Features

- **RSS Feed Ingestion**: Fetches events from 3 news sources (geopolitical, energy, supply chain)
- **Automatic Classification**: Categorizes events with keyword matching + category hints
- **AI Enrichment**: Processes events with GPT to generate summaries and market impact analysis
- **Region Detection**: Identifies geographic regions from event content
- **Severity Scoring**: Assigns severity scores (1-5) based on keywords
- **REST API**: Access events and AI analysis via FastAPI endpoints

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
  /api
    app.py            # FastAPI application
    routes.py         # API endpoints
  main.py             # Main entrypoint
```

## Setup

### Environment Variables

The `DATABASE_URL` is automatically provided by Replit's PostgreSQL integration.

**AI Processing** uses Replit AI Integrations (no API key required - charges billed to your credits):
- `AI_INTEGRATIONS_OPENAI_BASE_URL` - Auto-configured
- `AI_INTEGRATIONS_OPENAI_API_KEY` - Auto-configured

Optional AI settings:
- `OPENAI_MODEL`: Model to use (default: gpt-4.1-mini)
- `AI_MAX_EVENTS_PER_RUN`: Max events per AI run (default: 20)
- `AI_MAX_CHARS`: Max input chars (default: 6000)
- `AI_TEMPERATURE`: Temperature (default: 0.2)

### Configure Feeds

Edit `src/config/feeds.json` to add or modify RSS feed sources.

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

This processes unprocessed events and generates AI summaries and impact analysis.

## API Endpoints

### Health Check
```
GET /health
```

### Get Events
```
GET /events?category=energy&region=Europe&min_severity=3&processed=true&limit=50
```

### Get Latest Events
```
GET /events/latest
```
Returns 20 most recent events with AI summary fields.

### Get Event Detail (with full AI analysis)
```
GET /events/{id}
```
Returns complete event including `ai_impact` with market impact analysis.

### Get AI Processing Stats
```
GET /ai/stats
```
Returns processing statistics (total, processed, unprocessed, errors).

### Get Ingestion Runs
```
GET /ingestion-runs
```

## AI Analysis Output

Each processed event includes:

- **ai_summary**: 2-3 sentence neutral summary
- **ai_impact**: Structured market impact analysis
  - Impact on oil, gas, fx, freight (direction, confidence, rationale)
  - Key facts and entities extracted
  - Risk flags (sanctions, supply_disruption, etc.)
  - Time horizon estimate

Example impact:
```json
{
  "oil": {"direction": "up", "confidence": 0.8, "rationale": "Supply cuts..."},
  "gas": {"direction": "unclear", "confidence": 0.2, "rationale": "No direct mention..."}
}
```

## Database Schema

### events table
- id, title, source_name, source_url (unique), category, region, severity_score
- event_time, raw_text, classification_reason, inserted_at
- processed, ai_summary, ai_impact_json, ai_model, ai_processed_at, ai_error, ai_attempts

### ingestion_runs table
- id, started_at, finished_at, status
- total_items, inserted_items, skipped_duplicates, failed_items, notes

## Recent Changes

### v0.2 (2026-01-07)
- Added AI processing worker with OpenAI integration
- Added ai_summary, ai_impact_json columns for AI enrichment
- Added GET /events/{id} endpoint for full AI analysis
- Added GET /ai/stats endpoint for processing statistics
- Added retry logic and error handling for AI calls

### v0.1.1 (2026-01-07)
- Added Al Jazeera as 3rd geopolitical RSS feed
- Added category_hint support for classification
- Added classification_reason tracking
- Added detailed ingestion stats

### v0.1.0 (2026-01-07)
- Initial implementation with RSS ingestion
- Keyword-based classification
- FastAPI endpoints
