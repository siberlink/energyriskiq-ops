# EGSI (Europe Gas Stress Index) - Development Document

**Last Updated:** 2026-01-28

## Overview

EGSI is a gas-specific stress index module that measures market transmission stress and system stress signals for European gas infrastructure. The module consists of two index families, **both now fully implemented**:

- **EGSI-M (Market/Transmission):** Daily index measuring gas market stress signal based on RERI_EU, theme pressure, asset transmission, and infrastructure chokepoint factors. **Status: ✅ COMPLETE**
- **EGSI-S (System):** Daily index for storage/refill/winter stress signals using pluggable data sources. **Status: ✅ COMPLETE**

---

## Quick Reference

### All API Endpoints

| Index | Endpoint | Method | Description |
|-------|----------|--------|-------------|
| EGSI-M | `/api/v1/indices/egsi-m/status` | GET | Module health check |
| EGSI-M | `/api/v1/indices/egsi-m/public` | GET | 24h delayed data (public) |
| EGSI-M | `/api/v1/indices/egsi-m/latest` | GET | Real-time data |
| EGSI-M | `/api/v1/indices/egsi-m/history` | GET | Historical data |
| EGSI-M | `/api/v1/indices/egsi-m/compute` | POST | Trigger computation |
| EGSI-M | `/api/v1/indices/egsi-m/{date}` | GET | Specific date data |
| EGSI-S | `/api/v1/indices/egsi-s/status` | GET | Module status + data source |
| EGSI-S | `/api/v1/indices/egsi-s/latest` | GET | Latest EGSI-S value |
| EGSI-S | `/api/v1/indices/egsi-s/history` | GET | Historical EGSI-S data |
| EGSI-S | `/api/v1/indices/egsi-s/compute` | POST | Trigger computation |
| EGSI-S | `/api/v1/indices/egsi-s/{date}` | GET | Specific date data |

### SEO Public Pages

| Page | URL | Description |
|------|-----|-------------|
| Main | `/egsi` | Overview of EGSI indices |
| Methodology | `/egsi/methodology` | How EGSI is calculated |
| History | `/egsi/history` | All historical data |
| Daily | `/egsi/{date}` | Single day data |
| Monthly | `/egsi/{year}/{month}` | Monthly archive |

### Database Tables

| Table | Index | Purpose |
|-------|-------|---------|
| egsi_m_daily | EGSI-M | Main index values |
| egsi_components_daily | EGSI-M | Component breakdown |
| egsi_drivers_daily | EGSI-M | Top drivers |
| egsi_signals_daily | EGSI-M | Signal details |
| egsi_norm_stats | EGSI-M | Normalization statistics |
| egsi_s_daily | EGSI-S | System index values + components (JSONB) |

---

## Current Implementation Status (as of 2026-01-28)

### EGSI-M Status: ✅ FULLY OPERATIONAL

| Component | Status | Description |
|-----------|--------|-------------|
| Database Tables | ✅ Complete | 5 tables (egsi_m_daily, egsi_components_daily, egsi_drivers_daily, egsi_signals_daily, egsi_norm_stats) |
| types.py | ✅ Complete | Dataclasses, constants, risk bands, Chokepoints v1 config |
| compute.py | ✅ Complete | EGSI-M formula with component calculations |
| repo.py | ✅ Complete | Database operations for save/fetch |
| service.py | ✅ Complete | Orchestration layer for daily computation |
| routes.py | ✅ Complete | API endpoints (public, latest, status, history, compute, date) |
| Workflow Integration | ✅ Complete | Integrated into alerts-engine-v2.yml |
| Feature Flag | ✅ Complete | ENABLE_EGSI (default: true) |

### EGSI-S Status: ✅ FULLY OPERATIONAL

| Component | Status | Description |
|-----------|--------|-------------|
| Database Table | ✅ Complete | egsi_s_daily table with JSONB components |
| types.py | ✅ Complete | EGSISResult, EGSISComponents dataclasses, MarketDataSnapshot |
| compute_egsi_s.py | ✅ Complete | EGSI-S formula with 5-component calculation |
| data_sources.py | ✅ Complete | Pluggable data source architecture (Mock, AGSI+, TTF, Composite) |
| repo.py | ✅ Complete | Save/fetch operations for egsi_s_daily |
| service_egsi_s.py | ✅ Complete | Orchestration with data source integration |
| routes.py | ✅ Complete | API endpoints (status, latest, history, compute, date) |

### SEO & Testing Status: ✅ COMPLETE

| Component | Status | Description |
|-----------|--------|-------------|
| SEO Pages | ✅ Complete | Main, methodology, history, daily ({date}), monthly ({year}/{month}) |
| Sitemap Integration | ✅ Complete | All EGSI pages in sitemap.xml and sitemap.html |
| Regression Tests | ✅ Complete | 9 endpoint tests in tests/test_egsi_endpoints.py |
| History Service | ✅ Complete | egsi_history_service.py for SEO data retrieval |

### Future Enhancements (Optional)

| Enhancement | Priority | Notes |
|-------------|----------|-------|
| Real AGSI+ Data Integration | ✅ DONE | Using GIE_API_KEY from agsi.gie.eu |
| Real TTF Price Integration | Medium | Requires ICE/EEX API access (using placeholder 35 EUR/MWh) |
| Pro Email Integration | Low | Include EGSI indices in Pro user digest emails |
| Automated EGSI-S Workflow | ✅ DONE | EGSI-S runs in alerts-engine-v2.yml every 10 minutes |

---

## Technical Architecture

### Module Structure

```
src/egsi/
├── __init__.py              # Module exports
├── types.py                 # Dataclasses, constants, risk bands, chokepoints config
├── compute.py               # EGSI-M formula and component calculations
├── compute_egsi_s.py        # EGSI-S formula and component calculations
├── data_sources.py          # Pluggable market data providers (Mock, AGSI+, TTF, Composite)
├── repo.py                  # Database operations (both EGSI-M and EGSI-S)
├── service.py               # EGSI-M orchestration
├── service_egsi_s.py        # EGSI-S orchestration
├── routes.py                # API endpoints (both EGSI-M and EGSI-S)
├── egsi_history_service.py  # SEO data retrieval service
└── egsi_seo_routes.py       # Public SEO pages
```

### Test Structure

```
tests/
└── test_egsi_endpoints.py   # 9 regression tests for route ordering and endpoints
```

### Database Schema

**egsi_m_daily** - Main index table
- `id` (serial, PK)
- `index_date` (date, unique)
- `region` (varchar) - Currently "Europe"
- `index_value` (numeric)
- `band` (varchar) - LOW/NORMAL/ELEVATED/HIGH/CRITICAL
- `trend_1d`, `trend_7d` (numeric, nullable)
- `explanation` (text)
- `model_version` (varchar) - "egsi_m_v1"
- `computed_at` (timestamp)

**egsi_components_daily** - Component breakdown per day
- Links to egsi_m_daily via `egsi_m_id`
- Stores RERI_EU, theme_pressure, asset_transmission, chokepoint_factor values

**egsi_drivers_daily** - Top drivers per day
- Links to egsi_m_daily via `egsi_m_id`
- Stores driver name, type, contribution, details

**egsi_signals_daily** - Individual signals detected
- Links to egsi_m_daily via `egsi_m_id`
- Stores signal name, type, value, source

**egsi_norm_stats** - Normalization statistics
- Used for percentile-based normalization after 30+ days

---

## EGSI-M Formula

```
EGSI-M = 100 × (
    0.35 × (RERI_EU / 100) +
    0.35 × ThemePressure_norm +
    0.20 × AssetTransmission_norm +
    0.10 × ChokepointFactor_norm
)
```

### Component Weights

| Component | Weight | Description |
|-----------|--------|-------------|
| RERI_EU | 0.35 | Regional escalation risk for Europe (from EERI) |
| ThemePressure | 0.35 | Gas-specific alert theme pressure (supply disruption, pipeline issues, transit disputes) |
| AssetTransmission | 0.20 | Asset-level risk transmission for gas infrastructure |
| ChokepointFactor | 0.10 | High-signal infrastructure chokepoint hits |

### Risk Bands

| Band | Range | Interpretation |
|------|-------|----------------|
| LOW | 0-20 | Minimal gas market stress |
| NORMAL | 21-40 | Baseline market conditions |
| ELEVATED | 41-60 | Heightened stress, monitor closely |
| HIGH | 61-80 | Significant stress, potential supply concerns |
| CRITICAL | 81-100 | Severe stress, immediate market impact likely |

---

## Chokepoints v1 Configuration

High-signal European gas infrastructure entities used for ChokepointFactor calculation:

| Entity | Keywords | Weight |
|--------|----------|--------|
| Ukraine Transit | ukraine, transit, sudzha, urengoy | 1.0 |
| TurkStream | turkstream, turk stream, blue stream | 0.9 |
| Nord Stream | nord stream, nordstream | 0.8 |
| Norway Pipelines | norway, equinor, langeled, europipe | 0.8 |
| Gate LNG (NL) | gate terminal, rotterdam lng | 0.7 |
| Zeebrugge LNG | zeebrugge, fluxys | 0.7 |
| Dunkerque LNG | dunkerque lng, dunkirk | 0.6 |
| Montoir LNG | montoir, elengy | 0.6 |
| Swinoujscie LNG | swinoujscie, polish lng | 0.6 |
| Revithoussa LNG | revithoussa, greece lng | 0.5 |

---

## API Endpoints

### Public Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/indices/egsi-m/public` | GET | 24h delayed EGSI-M data for public access |
| `/api/v1/indices/egsi-m/status` | GET | Module health check and status |
| `/api/v1/indices/egsi-m/history` | GET | Historical EGSI-M data (query params: days, limit) |
| `/api/v1/indices/egsi-m/{date}` | GET | EGSI-M for specific date |

### Authenticated Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/indices/egsi-m/latest` | GET | Real-time EGSI-M for Pro users |
| `/api/v1/indices/egsi-m/compute` | POST | Trigger EGSI-M computation (body: {date, force}) |

### Internal Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/internal/run/egsi-compute` | POST | Workflow trigger (requires INTERNAL_RUNNER_TOKEN) |

---

## Workflow Integration

EGSI-M computation is integrated into `alerts-engine-v2.yml` and runs:
1. After alert delivery (Pro/Trader)
2. Alongside GERI and EERI computation
3. Before the summary step

Workflow step:
```yaml
- name: Run EGSI-M Compute
  run: |
    curl -s -X POST "${{ secrets.APP_BASE_URL }}/internal/run/egsi-compute" \
      -H "Authorization: Bearer ${{ secrets.INTERNAL_RUNNER_TOKEN }}" \
      -H "Content-Type: application/json" \
      -d '{"date": "'$(date -u +%Y-%m-%d)'"}'
```

---

## Test Results

**Computation Test (2026-01-25):**
- Result: Value 0, Band LOW
- Reason: No alert activity to drive the index (expected baseline behavior)
- All endpoints verified working

---

## EGSI-S (System Index) - IMPLEMENTED

EGSI-S measures storage/refill/winter stress signals using a pluggable data source architecture.

### Formula

```
EGSI-S = 100 × (
    0.25 × SupplyPressure +
    0.20 × TransitStress +
    0.20 × StorageStress +
    0.20 × PriceVolatility +
    0.15 × PolicyRisk
)
```

### Components

| Component | Weight | Description |
|-----------|--------|-------------|
| Supply (Winter Readiness) | 25% | Readiness for winter heating season |
| Transit (Injection Stress) | 20% | Injection/withdrawal rate stress |
| Storage | 20% | Storage level vs seasonal targets |
| Market (Price Volatility) | 20% | TTF price volatility |
| Policy (Alert Pressure) | 15% | Supply-related alert pressure |

### Data Sources

The EGSI-S module uses a **pluggable data source architecture**:

- **Mock Provider (default):** Synthetic data based on seasonal patterns
- **AGSI+ Provider (planned):** Real EU gas storage data from agsi.gie.eu
- **TTF Price Provider (planned):** Real gas prices from ICE/EEX

Configure via environment variables:
- `EGSI_S_DATA_SOURCE`: "mock", "agsi", "ttf", or "composite"
- `AGSI_API_KEY`: API key for AGSI+ (when using real data)
- `TTF_PRICE_API_KEY`: API key for TTF prices (when using real data)

### Database Schema

**egsi_s_daily** table:
- `index_date`, `region`, `index_value`, `band`
- `trend_1d`, `trend_7d`
- `components_json` (JSONB)
- `data_sources` (TEXT[])
- `model_version` (egsi_s_v1)

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/indices/egsi-s/status` | GET | Module status and data source info |
| `/api/v1/indices/egsi-s/latest` | GET | Latest EGSI-S value |
| `/api/v1/indices/egsi-s/history` | GET | Historical EGSI-S data |
| `/api/v1/indices/egsi-s/compute` | POST | Trigger computation |
| `/api/v1/indices/egsi-s/{date}` | GET | Get data for specific date |

### Seasonal Storage Targets

| Season | Target | Description |
|--------|--------|-------------|
| Winter Start (Nov 1) | 90% | EU mandate for heating season |
| Spring (Mar-May) | 30% | Post-winter low point |
| Summer (Jun-Aug) | 50% | Mid-injection season |
| Autumn (Sep-Oct) | 80% | Pre-winter buildup |

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| ENABLE_EGSI | true | Feature flag to enable/disable entire EGSI module |
| INTERNAL_RUNNER_TOKEN | (required) | Token for workflow triggers |
| EGSI_S_DATA_SOURCE | mock | Data source for EGSI-S: "mock", "agsi", "ttf", or "composite" |
| AGSI_API_KEY | (optional) | API key for AGSI+ real storage data |
| TTF_PRICE_API_KEY | (optional) | API key for TTF real price data |

### Normalization

- **First 14 days:** Uses cap-based fallback (no historical baseline)
- **After 30+ days:** Percentile-based normalization using egsi_norm_stats table
- Normalization stats are updated during each computation

---

## Related Documentation

- `docs/EGSI.md` - Original specification document
- `docs/reri.md` - RERI/EERI architecture (similar patterns)
- `docs/reri-eeri-development-document.md` - RERI/EERI development history

---

## Change Log

| Date | Change |
|------|--------|
| 2026-01-28 | Initial EGSI-M implementation complete |
| 2026-01-28 | Created 5 database tables for EGSI-M |
| 2026-01-28 | Integrated into alerts-engine-v2.yml workflow |
| 2026-01-28 | Tested EGSI-M computation for 2026-01-25 (value: 0, band: LOW) |
| 2026-01-28 | Architect review passed for EGSI-M |
| 2026-01-28 | Added regression tests for EGSI endpoints (9 tests passing) |
| 2026-01-28 | Created EGSI SEO pages (main, methodology, history, daily, monthly) |
| 2026-01-28 | Added EGSI pages to sitemap.xml and sitemap.html |
| 2026-01-28 | Implemented EGSI-S with pluggable data source architecture |
| 2026-01-28 | Created data_sources.py with Mock, AGSI+, and TTF providers |
| 2026-01-28 | Added EGSI-S database table (egsi_s_daily) |
| 2026-01-28 | Added EGSI-S API endpoints (status, latest, history, compute, date) |
| 2026-01-28 | Tested EGSI-S computation for 2026-01-25 (value: 2.8, band: LOW with mock data) |
| 2026-01-28 | Integrated real AGSI+ data for EGSI-S (GIE_API_KEY) |
| 2026-01-28 | Added EGSI-S to alerts-engine-v2.yml workflow (runs every 10 min) |
| 2026-01-28 | Created internal endpoint /internal/run/egsi-s-compute |
| 2026-01-28 | Tested with real AGSI+ data: 2025-01-25 storage=56%, value=1.18, band=LOW |
