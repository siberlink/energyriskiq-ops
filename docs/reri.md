# RERI - Regional Escalation Risk Index

Development reference for RERI implementation.

---

## 1. Core Concept (What RERI Really Is)

> **RERI = "Probability-weighted disruption pressure for a specific region"**

It answers one institutional question:

> "How dangerous is THIS REGION for energy, shipping, FX, and supply chains right now?"

Unlike GERI (global), RERI is:
- **Actionable**
- **Hedge-driven**
- **Procurement-driven**
- **Insurance-driven**

This is where real budgets live.

---

## 2. Canonical Regions (Lock These Early)

Do NOT let regions be dynamic or messy. You need stable, licensable region taxonomy.

### Tier 1 (Must Have)

| Region ID | Display Name | Type |
|-----------|--------------|------|
| `middle-east` | Middle East | conflict / energy |
| `europe` | Europe | energy |
| `black-sea` | Black Sea | shipping / conflict |
| `east-asia` | East Asia | energy / shipping |
| `south-china-sea` | South China Sea | shipping / conflict |
| `north-africa` | North Africa | energy |
| `ukraine-region` | Ukraine Region | conflict (high-value war zone) |
| `persian-gulf` | Persian Gulf | energy / shipping |

### Tier 2 (Add Later)

| Region ID | Display Name |
|-----------|--------------|
| `latin-america` | Latin America |
| `west-africa` | West Africa |
| `caucasus` | Caucasus |
| `central-asia` | Central Asia |
| `indian-ocean` | Indian Ocean |

**Store as controlled vocabulary, not free text.**

### Database Schema

```sql
regions (
  region_id TEXT PRIMARY KEY,     -- "middle-east"
  region_name TEXT,               -- "Middle East"
  region_type TEXT,               -- "conflict" | "energy" | "shipping"
  core_assets JSONB               -- ["oil","gas","freight","fx"]
)
```

This becomes part of your IP.

---

## 3. Event → Region Mapping Logic

Every alert/event should already have:
- `region_primary`
- `regions_secondary[]`
- `entities[]`
- `assets[]`

### Region Inclusion Rule

An event contributes to RERI if:

```
event.region_primary == this_region
OR this_region ∈ event.regions_secondary
OR event.entities map to region influence (pipeline, strait, exporter)
```

### Examples

| Event | Regions Counted |
|-------|-----------------|
| Iran unrest | `middle-east`, `persian-gulf` |
| Gaza escalation | `middle-east` |
| Black Sea port strike | `black-sea`, `europe` |
| Qatar LNG outage | `middle-east`, `europe` |

This gives **cross-regional spillover**, which institutions love.

---

## Implementation Status

| Component | Status | Notes |
|-----------|--------|-------|
| Region taxonomy | 📋 Planned | Define controlled vocabulary |
| Event-region mapping | 📋 Planned | Extend alert_events schema |
| RERI compute engine | 📋 Planned | Similar to GERI architecture |
| Public display (24h delay) | 📋 Planned | Region pages |
| Pro dashboard | 📋 Planned | User account section |

---

## Related Documents

- [Indices Bible](./indices-bible.md) - Overall index strategy and access tiers

---

*Last updated: January 2026*
