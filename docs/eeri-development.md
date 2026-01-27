# EERI Development Document

## Overview

The European Energy Risk Index (EERI) is a daily composite index measuring Europe's exposure to energy disruption risk. This document covers the public-facing SEO infrastructure implemented to expose EERI data for organic traffic acquisition.

## EERI Formula (v1)

```
EERI = 0.45 × RERI_EU + 0.25 × ThemePressure + 0.20 × AssetTransmission + 0.10 × Contagion
```

**Components:**
- **RERI_EU**: Regional Escalation Risk Index for Europe (base regional risk)
- **ThemePressure**: Weighted severity by event category (war/military: 1.6, strike/conflict: 1.6, supply_disruption: 1.5, energy: 1.3, sanctions: 1.3, political: 1.0, diplomacy: 0.7)
- **AssetTransmission**: Risk transmission across energy asset classes (gas, oil, power, lng, electricity, freight, fx)
- **Contagion**: Spillover risk from adjacent regions (Middle East: 0.6 weight, Black Sea: 0.4 weight)

**Risk Bands:**
- LOW: 0-25
- MODERATE: 26-50
- ELEVATED: 51-75
- CRITICAL: 76-100

## Public SEO Infrastructure

### Design Principles

1. **24-Hour Delay**: All public EERI data is delayed by 24 hours to protect paying subscribers who receive real-time alerts
2. **No Proprietary Data Leakage**: Public pages show interpretive data only (level, band, trend, interpretation, driver headlines, affected assets) - never raw scores, weights, normalized values, or component breakdowns
3. **SEO Optimization**: Proper canonical tags, meta descriptions, Open Graph tags, and sitemap inclusion

### Page Structure

| Route | Description | Data Shown |
|-------|-------------|------------|
| `/eeri` | Main EERI page | Current level, band, trend, interpretation, top 3 drivers, affected assets, methodology summary |
| `/eeri/methodology` | How EERI is calculated | High-level component descriptions, use cases, limitations (no weights/formulas) |
| `/eeri/history` | Archive landing page | Links to available months and recent dates |
| `/eeri/{date}` | Daily snapshot | Level, band, trend, interpretation, drivers, assets for specific date |
| `/eeri/{year}/{month}` | Monthly archive | All daily values for the month with stats (avg, min, max, band distribution) |

### Implementation Files

```
src/reri/
├── seo_routes.py          # FastAPI router with all EERI public routes
├── eeri_history_service.py # Service layer for retrieving historical/delayed data
├── compute.py             # EERI computation logic
├── service.py             # Core EERI service
├── repo.py                # Database repository
└── backfill.py            # Historical data backfill logic

src/seo/
└── seo_generator.py       # Sitemap generation (includes EERI pages)
```

## Service Layer: eeri_history_service.py

### Functions

| Function | Purpose |
|----------|---------|
| `get_all_eeri_dates()` | Returns all dates with EERI data (for sitemap) |
| `get_eeri_available_months()` | Returns list of (year, month) tuples with data |
| `get_eeri_by_date(date)` | Retrieves EERI for a specific date |
| `get_latest_eeri_public()` | Gets latest EERI with 24h delay applied |
| `get_eeri_delayed()` | Alias for latest delayed EERI |
| `get_eeri_monthly_data(year, month)` | All daily records for a month |
| `get_eeri_adjacent_dates(date)` | Previous/next dates for navigation |
| `get_eeri_monthly_stats(records)` | Computes avg, min, max, band distribution |

### Database Query Pattern

All queries use dictionary-based row access (RealDictCursor):
```python
row['index_value']  # Correct
row[0]              # WRONG - will fail
```

## SEO Routes: seo_routes.py

### Router Registration

```python
# In src/api/app.py
from src.reri.seo_routes import router as eeri_seo_router
app.include_router(eeri_seo_router)
```

### Response Pattern

All routes return HTML responses with:
- Proper `Content-Type: text/html`
- Canonical tags matching the URL
- Meta descriptions for search engines
- Open Graph tags for social sharing
- Structured data hints for rich snippets

### Public Data Filtering

The `_prepare_public_eeri_data()` function filters EERI records to only expose:
```python
{
    'level': int,           # 0-100 index value
    'band': str,            # LOW/MODERATE/ELEVATED/CRITICAL
    'trend': str,           # RISING/FALLING/STABLE
    'interpretation': str,  # AI-generated interpretation text
    'drivers': [            # Top 3 risk drivers
        {'headline': str, 'title': str}
    ],
    'assets': [str],        # Affected energy assets
    'computed_at': datetime
}
```

**Excluded from public view:**
- Raw component scores (reri_eu_score, theme_pressure_score, etc.)
- Normalized values
- Component weights
- Internal metadata

## Sitemap Integration

### XML Sitemap (sitemap.xml)

The sitemap generator in `src/seo/seo_generator.py` includes:

```python
def generate_sitemap_xml():
    # ... existing GERI entries ...
    
    # EERI static pages
    eeri_static = ['/eeri', '/eeri/methodology', '/eeri/history']
    
    # EERI monthly archives
    eeri_months = get_eeri_available_months()
    
    # EERI daily snapshots (with 24h delay)
    eeri_dates = get_all_eeri_dates()
```

### HTML Sitemap (sitemap.html)

Added EERI section with links to:
- Main EERI page
- Methodology page
- History archive

## Canonical URL Strategy

All EERI pages use trailing-slash-free canonical URLs:
- `https://energyriskiq.com/eeri` (not `/eeri/`)
- `https://energyriskiq.com/eeri/methodology`
- `https://energyriskiq.com/eeri/2026-01-25`

The `TrailingSlashRedirectMiddleware` in `app.py` returns 301 redirects for any trailing slash requests.

## Backfill Process

### CLI Command
```bash
python -m src.reri.cli backfill --start 2025-01-01 --end 2025-12-31
```

### API Endpoint
```
POST /api/v1/indices/eeri/backfill
{
    "start_date": "2025-01-01",
    "end_date": "2025-12-31"
}
```

Note: Dev database is empty - backfill must run in production for actual data.

## Feature Flag

EERI is controlled by the `ENABLE_EERI` environment variable:
- `ENABLE_EERI=true`: EERI computation and SEO pages active
- `ENABLE_EERI=false`: EERI disabled (computation skipped, pages return empty state)

## Testing

### Manual Verification
```bash
# Test main page
curl -s http://localhost:5000/eeri | head -50

# Test methodology
curl -s http://localhost:5000/eeri/methodology | head -30

# Check sitemap includes EERI
curl -s http://localhost:5000/sitemap.xml | grep eeri

# Verify no weight leakage
curl -s http://localhost:5000/eeri/methodology | grep -i "0\.[0-9]"
```

### Expected Behavior
- All pages return 200 with valid HTML
- No numerical weights (0.45, 0.25, etc.) appear in public pages
- Sitemap includes all EERI URLs
- 24h delay is enforced on public data

## Future Considerations

1. **Rate Limiting**: Consider adding rate limits to prevent scraping
2. **Caching**: Add response caching for frequently accessed pages
3. **Schema.org Markup**: Add structured data for rich search results
4. **RSS Feed**: Consider EERI RSS feed for automated tracking
5. **API Access**: Tiered API access for programmatic EERI retrieval

## Related Documentation

- `docs/reri.md` - RERI/EERI architecture overview
- `docs/reri-eeri-development-document.md` - Complete development history
- `replit.md` - Project overview and preferences
