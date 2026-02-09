# EGSI Dashboard Implementation

**Last Updated:** 2026-02-09

## Overview

The Europe Gas Stress Index (EGSI) dashboard provides a multi-layered view of European gas market stress through two complementary indices:

- **EGSI-M (Market/Transmission):** Measures how violently risk is transmitting through gas markets today.
- **EGSI-S (System):** Measures how fragile the European gas system is structurally.

The dashboard spans the landing page snapshot card, public SEO pages, and authenticated API endpoints with plan-tiered access.

---

## 1. Landing Page Snapshot Card (`/`)

### Location

`src/static/index.html` — Section ID: `egsi-section`

### Design

- Green accent color (`#10b981` / `rgba(16, 185, 129)`) consistent with gas/energy theming.
- Dark background gradient (`#0f172a` to `#1e293b`).
- Same card structure as GERI, EERI, and Digest sections: header → description → feature grid → snapshot card → CTA buttons → trust line.

### Data Loading

- JavaScript fetches `GET /api/v1/indices/egsi-m/public` on page load.
- Displays: index value (0-100), risk band, 7-day trend with directional arrow.
- Band-based CSS classes: `.egsi-band-LOW`, `.egsi-band-NORMAL`, `.egsi-band-MODERATE`, `.egsi-band-ELEVATED`, `.egsi-band-HIGH`, `.egsi-band-CRITICAL`.
- Data is **24-hour delayed** for public/free access.

### Feature Grid (4 cards)

1. **Dual-Layer Index** — EGSI-M tracks market signals while EGSI-S monitors system fundamentals.
2. **Chokepoint Monitoring** — Tracks 10+ European gas infrastructure chokepoints.
3. **Storage Intelligence** — Real EU gas storage data from AGSI+ with seasonal deviation analysis.
4. **Market Stress Signals** — Live TTF pricing and volatility integrated into stress calculations.

### CTA Buttons

- "View Today's EGSI" → links to `/egsi`
- "Explore EGSI History" → links to `/egsi/history`

---

## 2. Public SEO Pages

### File

`src/egsi/egsi_seo_routes.py`

### Routes

| URL | Function | Description |
|-----|----------|-------------|
| `/egsi` | `egsi_public_page()` | Main EGSI overview page with 24h delayed data |
| `/egsi/methodology` | `egsi_methodology_page()` | How EGSI-M and EGSI-S are calculated |
| `/egsi/history` | `egsi_history_page()` | Historical data overview with links to daily/monthly archives |
| `/egsi/updates` | `egsi_updates_page()` | Changelog of EGSI methodology updates |
| `/egsi/{date}` | `egsi_daily_snapshot()` | Single day snapshot (e.g., `/egsi/2026-02-08`) |
| `/egsi/{year}/{month}` | `egsi_monthly_archive()` | Monthly archive (e.g., `/egsi/2026/02`) |

### Public Page Features

- 24-hour delayed EGSI-M data via `get_egsi_m_delayed()`.
- SEO-optimized HTML with structured meta tags.
- Canonical URLs, breadcrumbs, internal linking.
- Daily AI-generated interpretations when available.
- Component breakdown display (RERI_EU, Theme Pressure, Asset Transmission, Chokepoint Factor).
- Sitemap integration (`sitemap.xml` and `sitemap.html`).

---

## 3. API Endpoints

### File

`src/egsi/routes.py` — Router prefix: `/api/v1/indices`

### EGSI-M Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/v1/indices/egsi-m/public` | GET | None | 24h delayed data for public display |
| `/api/v1/indices/egsi-m/latest` | GET | Pro+ | Real-time latest EGSI-M value |
| `/api/v1/indices/egsi-m/status` | GET | None | Module health check |
| `/api/v1/indices/egsi-m/history` | GET | None | Historical data (query: `days`, `limit`) |
| `/api/v1/indices/egsi-m/compute` | POST | Internal | Trigger computation (body: `{date, force}`) |
| `/api/v1/indices/egsi-m/{date}` | GET | None | Specific date data |

### EGSI-S Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/v1/indices/egsi-s/status` | GET | None | Module status + data source info |
| `/api/v1/indices/egsi-s/latest` | GET | None | Latest EGSI-S value |
| `/api/v1/indices/egsi-s/history` | GET | None | Historical data (query: `days`) |
| `/api/v1/indices/egsi-s/compute` | POST | Internal | Trigger computation |
| `/api/v1/indices/egsi-s/{date}` | GET | None | Specific date data |

### Internal Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/internal/run/egsi-compute` | POST | `INTERNAL_RUNNER_TOKEN` | Workflow trigger for EGSI-M |
| `/internal/run/egsi-s-compute` | POST | `INTERNAL_RUNNER_TOKEN` | Workflow trigger for EGSI-S |

### Public API Response Format (EGSI-M)

```json
{
  "success": true,
  "value": 42,
  "band": "ELEVATED",
  "trend_1d": -3,
  "trend_7d": 5,
  "date": "2026-02-07",
  "explanation": "...",
  "top_drivers": [],
  "chokepoint_watch": [],
  "is_delayed": true,
  "delay_hours": 24
}
```

---

## 4. EGSI-M Computation

### Files

- `src/egsi/compute.py` — Formula and component calculations
- `src/egsi/service.py` — Orchestration layer
- `src/egsi/types.py` — Dataclasses, constants, risk bands, chokepoint config

### Formula

```
EGSI-M = 100 * (
    0.35 * (RERI_EU / 100) +
    0.35 * ThemePressure_norm +
    0.20 * AssetTransmission_norm +
    0.10 * ChokepointFactor_norm
)
```

### Risk Bands

| Band | Range | Color |
|------|-------|-------|
| LOW | 0-20 | Green |
| NORMAL | 21-40 | Light Green |
| ELEVATED | 41-60 | Yellow |
| HIGH | 61-80 | Orange |
| CRITICAL | 81-100 | Red |

### Chokepoints v1

10 monitored European gas infrastructure entities: Ukraine Transit (1.0), TurkStream (0.9), Nord Stream (0.8), Norway Pipelines (0.8), Gate LNG NL (0.7), Zeebrugge LNG (0.7), Dunkerque LNG (0.6), Montoir LNG (0.6), Swinoujscie LNG (0.6), Revithoussa LNG (0.5).

---

## 5. EGSI-S Computation

### Files

- `src/egsi/compute_egsi_s.py` — Formula and component calculations
- `src/egsi/service_egsi_s.py` — Orchestration with data source integration
- `src/egsi/data_sources.py` — Pluggable data source architecture

### Formula

```
EGSI-S = 100 * (
    0.25 * SupplyPressure +
    0.20 * TransitStress +
    0.20 * StorageStress +
    0.20 * PriceVolatility +
    0.15 * PolicyRisk
)
```

### Data Sources

Configured via `EGSI_S_DATA_SOURCE` environment variable:

| Source | Description |
|--------|-------------|
| `mock` | Synthetic seasonal data (default) |
| `agsi` | Real EU gas storage from AGSI+ (GIE API) |
| `ttf` | Real TTF gas prices from OilPriceAPI |
| `composite` | AGSI+ storage + OilPriceAPI TTF combined |

---

## 6. Database Schema

### EGSI-M Tables

| Table | Purpose |
|-------|---------|
| `egsi_m_daily` | Main index values (date, value, band, trend, explanation) |
| `egsi_components_daily` | Component breakdown per day |
| `egsi_drivers_daily` | Top drivers per day |
| `egsi_signals_daily` | Individual signals detected |
| `egsi_norm_stats` | Normalization statistics for percentile-based calculation |

### EGSI-S Table

| Table | Purpose |
|-------|---------|
| `egsi_s_daily` | System index values with JSONB components, data_sources array |

---

## 7. Data Retrieval Services

### File

`src/egsi/egsi_history_service.py`

### Functions

| Function | Description |
|----------|-------------|
| `get_all_egsi_m_dates()` | All dates with EGSI-M data |
| `get_egsi_m_available_months()` | Available monthly archives |
| `get_egsi_m_by_date(date)` | Full data for a specific date |
| `get_egsi_m_components_for_date(date)` | Component breakdown for a date |
| `get_egsi_m_drivers_for_date(date)` | Top drivers for a date |
| `get_egsi_m_monthly_data(year, month)` | All data for a month |
| `get_egsi_m_adjacent_dates(date)` | Previous/next navigation |
| `get_egsi_m_monthly_stats()` | Monthly aggregated statistics |
| `get_egsi_m_delayed(delay_hours)` | 24h delayed data for public display |
| `get_latest_egsi_m_public()` | Latest public-safe EGSI-M value |

---

## 8. Workflow Integration

EGSI computation runs via GitHub Actions in `alerts-engine-v2.yml`:

1. **EGSI-M** runs after alert delivery, alongside GERI and EERI.
2. **EGSI-S** runs every 10 minutes via the same workflow.

Both are triggered via internal endpoints requiring `INTERNAL_RUNNER_TOKEN`.

---

## 9. Feature Flag

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_EGSI` | `true` | Enables/disables the entire EGSI module |

When disabled, all EGSI API endpoints return HTTP 503.

---

## 10. AI Interpretations

### File

`src/egsi/interpretation.py`

Daily AI-generated interpretations are produced via `generate_egsi_interpretation()` using OpenAI (gpt-4.1-mini). These provide contextual analysis of current gas market stress levels and are displayed on:

- EGSI public SEO pages (`/egsi`, `/egsi/{date}`)
- Daily digest emails (when EGSI data is included)

---

## 11. Integration Points

- **Landing page** (`src/static/index.html`): EGSI snapshot card with live data loading.
- **Daily Digest** (`src/api/daily_digest_routes.py`): `get_egsi_snapshot()` provides EGSI data for daily intelligence digests.
- **EERI relationship**: EGSI feeds into EERI via AssetTransmission component.
- **Contextual linking** (`src/utils/contextual_linking.py`): EGSI keywords trigger links to EGSI pages from alert content.
- **Sitemap**: All EGSI pages included in `sitemap.xml` and `sitemap.html`.

---

## Related Documentation

- `docs/EGSI.md` — Original EGSI specification and strategic vision
- `docs/egsi-development.md` — Development status and technical architecture
- `docs/indices-bible.md` — Overall index strategy and access tiers
