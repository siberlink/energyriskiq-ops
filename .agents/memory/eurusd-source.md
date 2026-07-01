---
name: EUR/USD data source
description: Why EUR/USD ingestion uses FRED primary + Yahoo fallback, and the FRED publication-lag gotcha
---

EUR/USD (`eurusd_snapshots`) is sourced from FRED series `DEXUSEU` (US dollars
per euro = EUR/USD directly, no inversion) as the primary, with Yahoo Finance
ticker `EURUSD=X` as the fallback.

**Why:** OANDA's v20 API (the original source) stopped returning data and was
retired. FRED is official, free, no API key (public `fredgraph.csv` endpoint,
same pattern already used for VIX), and authoritative for history. Yahoo is an
unofficial/scraped API with no SLA, so it is not trusted as the sole source.

**How to apply:**
- FRED's H.10 daily rate publishes with a ~2–4 day lag, so for *daily capture*
  (yesterday) FRED usually has no value yet → Yahoo fills the fresh end. For
  *backfill* FRED is authoritative and Yahoo only fills weekday gaps FRED skips.
- Sources use different daily conventions (FRED = noon buying rate, Yahoo =
  market close), differing by a few pips — immaterial for GERI/EERI correlations,
  but backfill a whole range from one source where possible to keep it clean.
- Runtime writes hit the Neon prod DB (PRODUCTION_DATABASE_URL), so a local
  `backfill_eurusd_range(from,to)` run refills production directly.
