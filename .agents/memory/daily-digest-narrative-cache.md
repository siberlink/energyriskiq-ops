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
invalidate same-day caches, bump the `v1:` prefix in the cache key. The first
viewer per plan-level per day still pays the full LLM latency (no precompute/warm
job exists) — add a daily warm job if first-load latency becomes a concern. New
cache tables like this must be created in BOTH PRODUCTION_DATABASE_URL and
DATABASE_URL (see deploy-schema-migration memo) to avoid publish DROP warnings.
