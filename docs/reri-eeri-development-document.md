# RERI/EERI Development Document

## Overview

This document captures the complete development history and technical specifications for the Regional Escalation Risk Index (RERI) and Europe Energy Risk Index (EERI) v1 implementation.

**Date Completed:** January 2026  
**Status:** Production Ready (v1 Baseline)

---

## 1. Strategic Decisions

### 1.1 Scope for v1

- **Europe-first approach:** EERI is the first regional index, with Middle East and Black Sea planned for v2
- **Contagion disabled:** Cross-regional spillover component set to zero in v1 (ready for v2 activation)
- **Daily computation only:** No backfilling of historical data
- **Feature-flag gated:** `ENABLE_EERI` controls module activation

### 1.2 Architectural Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Database optimization | Speed-optimized schema | Fast reads for API/dashboard |
| Region normalization | Canonical regions table | Consistent taxonomy across system |
| Normalization strategy | Rolling baseline with fallback | Bootstrap for early days, stable long-term |
| Alert filtering | Type-specific rules | Severity vs clustering have different needs |
| Formula redistribution | Weights adjusted for disabled contagion | Maintains 100% weight total |

---

## 2. Database Schema

### 2.1 reri_indices_daily Table

Primary storage for computed regional indices.

```sql
CREATE TABLE reri_indices_daily (
    id SERIAL PRIMARY KEY,
    index_date DATE NOT NULL,
    index_id VARCHAR(32) NOT NULL,
    region_id VARCHAR(32) NOT NULL,
    index_value NUMERIC(5,2) NOT NULL,
    risk_band VARCHAR(16) NOT NULL,
    components JSONB NOT NULL,
    alert_count INTEGER NOT NULL DEFAULT 0,
    computed_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(index_date, index_id, region_id)
);

CREATE INDEX idx_reri_date_region ON reri_indices_daily(index_date DESC, region_id);
CREATE INDEX idx_reri_index_id ON reri_indices_daily(index_id, index_date DESC);
```

### 2.2 reri_canonical_regions Table

Normalized region taxonomy for consistent mapping.

```sql
CREATE TABLE reri_canonical_regions (
    region_id VARCHAR(32) PRIMARY KEY,
    display_name VARCHAR(64) NOT NULL,
    tier INTEGER NOT NULL DEFAULT 1,
    aliases TEXT[] NOT NULL DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW()
);
```

**Tier-1 Regions (v1):**
- `europe` - European Union & UK
- `middle-east` - Middle East & North Africa
- `black-sea` - Black Sea & Caucasus

---

## 3. EERI v1 Formula

### 3.1 Component Weights

| Component | Weight | Description |
|-----------|--------|-------------|
| RERI_EU | 0.50 | Regional severity from Europe alerts |
| ThemePressure | 0.28 | Category-weighted impact analysis |
| AssetTransmission | 0.22 | Cross-asset overlap detection |
| Contagion | 0.00 | Disabled in v1 (reserved for v2) |

**Note:** Original weights (RERI_EU: 0.45, Theme: 0.25, Asset: 0.20, Contagion: 0.10) were redistributed proportionally when contagion was disabled.

### 3.2 RERI_EU Calculation

```
RERI_EU = 0.40 * norm(S) + 0.25 * norm(H) + 0.20 * norm(A) + 0.15 * norm(V)
```

Where:
- **S (Severity Pressure):** Sum of (severity * category_weight * confidence) for HIGH_IMPACT_EVENT alerts only
- **H (High-Impact Count):** Count of alerts matching: alert_type=HIGH_IMPACT_EVENT OR alert_type=REGIONAL_RISK_SPIKE OR severity >= 4
- **A (Asset Overlap):** Count of unique assets mentioned across alerts
- **V (Velocity):** Change in severity pressure vs 3-day historical average

### 3.3 Category Weights

| Category | Weight |
|----------|--------|
| war, military | 1.6 |
| supply_disruption | 1.5 |
| energy, sanctions | 1.3 |
| political | 1.0 |
| diplomacy | 0.7 |
| other | 1.0 |

### 3.4 Risk Bands

| Band | Range | Color |
|------|-------|-------|
| LOW | 0-25 | Green |
| MODERATE | 26-50 | Yellow |
| ELEVATED | 51-75 | Orange |
| CRITICAL | 76-100 | Red |

---

## 4. Alert Filtering Rules

### 4.1 Severity Pressure (S Component)

**Includes:** `HIGH_IMPACT_EVENT` only  
**Excludes:** `REGIONAL_RISK_SPIKE`, `ASSET_RISK_SPIKE`, all other types

Rationale: Severity calculation should use direct impact events, not derived/aggregated alerts.

### 4.2 High-Impact Count (H Component)

**Includes:**
- `alert_type = HIGH_IMPACT_EVENT` (always)
- `alert_type = REGIONAL_RISK_SPIKE` (for clustering signal)
- `severity >= 4` (any alert type)

Rationale: Count captures clustering behavior and high-severity events across all types per docs section 3.6.

---

## 5. Normalization Strategy

### 5.1 Bootstrap Phase (Days 1-14)

Uses fallback caps to prevent extreme values:

| Component | Fallback Cap |
|-----------|--------------|
| Severity Max | 50.0 |
| High-Impact Max | 10 |
| Asset Overlap Max | 8 |
| Velocity Offset | 5.0 |

### 5.2 Transition Phase (Days 15-29)

Continues using fallback caps while accumulating history.

### 5.3 Rolling Phase (Days 30+)

Uses 90-day rolling baseline computed from historical component values:

```python
baseline = compute_rolling_baseline(historical_components, days=90)
```

Baseline provides dynamic caps:
- `severity_max` - 95th percentile of historical severity
- `high_impact_max` - 95th percentile of historical counts
- `asset_overlap_max` - 95th percentile of historical overlaps
- `velocity_range` - max - min of historical velocity

---

## 6. Module Structure

```
src/reri/
├── __init__.py          # Package exports
├── types.py             # Data classes (AlertRecord, RERIComponents, EERIResult, etc.)
├── compute.py           # Core computation functions
├── normalize.py         # Normalization utilities and rolling baseline
├── repo.py              # Database operations
├── service.py           # Orchestration and main entry point
└── tests/
    └── test_compute.py  # Unit tests (15 tests)
```

---

## 7. Feature Flag

```python
ENABLE_EERI = os.getenv('ENABLE_EERI', 'false').lower() == 'true'
```

When disabled, `compute_eeri_for_date()` returns `None` immediately.

---

## 8. Test Coverage

15 unit tests covering:

| Test | Description |
|------|-------------|
| test_clamp | Boundary clamping function |
| test_extract_category_from_body | Category parsing from alert body |
| test_normalize_region | Region name normalization |
| test_get_category_weight | Category weight lookup |
| test_compute_severity_pressure | Severity calculation |
| test_severity_pressure_excludes_regional_spike | REGIONAL_RISK_SPIKE exclusion |
| test_compute_high_impact_count | Basic high-impact counting |
| test_high_impact_includes_regional_spike_for_clustering | REGIONAL_RISK_SPIKE inclusion |
| test_high_impact_counts_severity_ge_4 | severity >= 4 rule |
| test_compute_asset_overlap | Asset overlap detection |
| test_compute_velocity | Velocity calculation |
| test_compute_reri_components | Full component computation |
| test_compute_reri_value | RERI value from components |
| test_compute_eeri_value | EERI value from components |
| test_empty_alerts | Empty input handling |

---

## 9. Integration Points

### 9.1 Input

- **Source Table:** `alert_events`
- **Filter:** Europe-region alerts for current date
- **Historical:** 3-day lookback for velocity, 90-day for normalization

### 9.2 Output

- **Target Table:** `reri_indices_daily`
- **Fields:** index_date, index_id, region_id, index_value, risk_band, components, alert_count

---

## 10. Future Roadmap (v2+)

### Phase 1: Regional Expansion
- Add Middle East RERI (`middle-east`)
- Add Black Sea RERI (`black-sea`)
- Each uses same formula with region-specific alerts

### Phase 2: Contagion Activation
- Enable cross-regional spillover component
- Redistribute weights: RERI_EU 0.45, Theme 0.25, Asset 0.20, Contagion 0.10
- Compute contagion from adjacent region indices

### Phase 3: Velocity Normalization
- Add rolling baseline for velocity component
- Implement after 90+ days of history accumulated

---

## 11. Configuration Summary

| Setting | Value |
|---------|-------|
| Index ID | `EERI` |
| Region | `europe` |
| Computation | Daily (no backfill) |
| Feature Flag | `ENABLE_EERI` |
| Normalization Threshold | 30 days |
| Rolling Window | 90 days |
| Historical Lookback (velocity) | 3 days |

---

## 12. Appendix: Key Code References

### Main Entry Point
```python
# src/reri/service.py
def compute_eeri_for_date(target_date: date) -> Optional[EERIResult]:
```

### RERI Component Calculation
```python
# src/reri/compute.py
def compute_reri_components(
    alerts: List[AlertRecord],
    historical_severity: List[float],
    use_rolling_normalization: bool = False,
    baseline_caps: Optional[Dict] = None,
) -> RERIComponents:
```

### Database Persistence
```python
# src/reri/repo.py
def save_eeri_result(result: EERIResult) -> bool:
```

---

*Document Version: 1.0*  
*Last Updated: January 2026*
