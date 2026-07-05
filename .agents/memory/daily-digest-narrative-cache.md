---
name: Daily Intelligence Report narrative caching
description: Why the /api/v1/digest/daily LLM narrative is cached per day and what staleness is acceptable
---

The `/api/v1/digest/daily` endpoint's only slow part is its single synchronous
LLM call that writes the prose "narrative" (everything else is fast DB
queries/math). It is cached in `daily_digest_ai_cache` keyed by
`v1:{plan_level}:{digest_day}:{d|l}` (d=delayed/free, l=live).

**Why:** The report is a once-daily briefing, so regenerating the narrative on
every page view was wasting ~30s+ per load. Within-day staleness of the prose is
intentional and acceptable — the live numeric panels (GERI Live, asset changes,
probabilities, scenarios) are still computed fresh on each request; only the
narrative text is reused for the day.

**How to apply:** If you change what the narrative depends on in a way that must
invalidate same-day caches, bump the `v1:` prefix in the cache key. A daily warm
job now precomputes the narrative right after the indices are computed
(`/internal/run/daily-report` -> `warm_daily_digest_cache()`, chained in the
"Daily Index Computation" workflow `geri-daily.yml`), so the first viewer per day
normally hits a warm cache; it iterates distinct `PLAN_LEVELS` values and reuses
the endpoint's own `compute_daily_digest` path so warmed keys match exactly. New
cache tables like this must be created in BOTH PRODUCTION_DATABASE_URL and
DATABASE_URL (see deploy-schema-migration memo) to avoid publish DROP warnings.
