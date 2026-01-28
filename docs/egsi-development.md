# EGSI (Europe Gas Stress Index) - Development Document

**Last Updated:** 2026-01-28

## Overview

EGSI is a gas-specific stress index module that measures market transmission stress signals for European gas infrastructure. The module consists of two planned index families:

- **EGSI-M (Market/Transmission):** Daily index measuring gas market stress signal based on RERI_EU, theme pressure, asset transmission, and infrastructure chokepoint factors. **Status: IMPLEMENTED**
- **EGSI-S (System):** Future index for storage/refill/winter stress signals. **Status: PLANNED**

## Current Implementation Status

### Completed Components

| Component | Status | Description |
|-----------|--------|-------------|
| Database Tables | ✅ Complete | 5 tables created (egsi_m_daily, egsi_components_daily, egsi_drivers_daily, egsi_signals_daily, egsi_norm_stats) |
| types.py | ✅ Complete | Dataclasses, constants, risk bands, Chokepoints v1 config |
| compute.py | ✅ Complete | EGSI-M formula implementation with component calculations |
| repo.py | ✅ Complete | Database operations for save/fetch |
| service.py | ✅ Complete | Orchestration layer for daily computation |
| routes.py | ✅ Complete | API endpoints (public, latest, status, history, compute) |
| Workflow Integration | ✅ Complete | Integrated into alerts-engine-v2.yml |
| Feature Flag | ✅ Complete | ENABLE_EGSI (default: true) |

### Pending/Future Work

| Component | Status | Notes |
|-----------|--------|-------|
| EGSI-S (System Index) | 🔲 Planned | Storage/refill/winter stress - requires TTF market data integration |
| Regression Tests | 🔲 Recommended | Add tests for route ordering and endpoint responses |
| SEO Pages | 🔲 Not Started | Public EGSI pages similar to EERI (if needed) |
| Pro Email Integration | 🔲 Not Started | Include EGSI-M in Pro user emails (if desired) |

---

## Technical Architecture

### Module Structure

```
src/egsi/
├── __init__.py          # Module exports
├── types.py             # Dataclasses, constants, chokepoints config
├── compute.py           # EGSI-M formula and component calculations
├── repo.py              # Database operations
├── service.py           # Orchestration and daily computation
└── routes.py            # FastAPI endpoints
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

## Future Development: EGSI-S (System Index)

EGSI-S is planned to measure storage/refill/winter stress signals. Key considerations:

1. **Data Sources Needed:**
   - TTF (Title Transfer Facility) gas prices
   - EU gas storage levels (AGSI+ data)
   - Seasonal demand forecasts

2. **Proposed Formula Components:**
   - Storage level vs. seasonal target
   - Price volatility (TTF day-ahead)
   - Injection/withdrawal rates
   - Winter preparedness metrics

3. **Implementation Notes:**
   - TTF market data integration is pluggable in compute.py
   - Separate table `egsi_s_daily` should be created
   - May require external API integration for real-time storage data

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| ENABLE_EGSI | true | Feature flag to enable/disable EGSI module |
| INTERNAL_RUNNER_TOKEN | (required) | Token for workflow triggers |

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
| 2026-01-28 | Created 5 database tables |
| 2026-01-28 | Integrated into alerts-engine-v2.yml workflow |
| 2026-01-28 | Tested computation for 2026-01-25 (value: 0, band: LOW) |
| 2026-01-28 | Architect review passed |
