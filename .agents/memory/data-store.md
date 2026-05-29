---
name: Data store reality
description: Which database the app actually uses vs the Replit-managed one
---
The app persists ALL data to an external Neon Postgres reached via `PRODUCTION_DATABASE_URL`.
The Replit-managed `DATABASE_URL` dev DB is essentially unused at runtime.

**Why:** Publish-time schema-diff warnings (e.g. "delete user_pro_widgets table") compare against
the Replit-managed dev DB, which can be empty/stale. Fixing those warnings requires applying the
same schema to the Replit dev DB even though the app never reads it.

**How to apply:** For real data inspection use `psql "$PRODUCTION_DATABASE_URL"`. App startup migrations
run against Neon. When adding columns, also apply to the dev DB (via executeSql environment:"development")
to keep the publish diff clean, but the app's source of truth is Neon.
