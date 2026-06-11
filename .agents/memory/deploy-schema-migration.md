---
name: Republish destructive column-drop warnings
description: Why Replit Publish proposes dropping columns even though the app uses Neon, and how to stop it safely.
---

# Republish "may permanently remove data" column-drop warnings

The app reads/writes the **Neon** DB (`PRODUCTION_DATABASE_URL`) for all real
data, in both dev and deployment (db.py prefers PRODUCTION_DATABASE_URL, falls
back to DATABASE_URL). But the project ALSO has a **Replit-managed** Postgres
(the `postgresql-16` module → `DATABASE_URL`) that the app never really uses.

Replit's **Publish** flow runs a schema diff/migration on the *Replit-managed*
databases: it syncs the managed **dev** DB schema onto the managed **prod** DB.

**Why the destructive warning appears:** runtime schema changes (db.py
`ALTER TABLE ... ADD COLUMN IF NOT EXISTS`) only ever hit Neon, because the app
connects to Neon. The managed dev DB never receives them, so it drifts behind.
At publish time the managed dev DB is *missing* the new columns while the
managed prod DB still has them (with data) → the diff proposes DROP COLUMN.

**Why it looked like data loss:** applying that drop wipes the column values in
the managed prod DB. Real app data lives in Neon and is unaffected, but the
warning is genuinely destructive to the managed DB and must not be applied.

## How to apply (fix + prevention)
- **Fix:** make the managed dev DB match by ADDING (never dropping) the columns:
  `psql "$DATABASE_URL" -c "ALTER TABLE <t> ADD COLUMN IF NOT EXISTS <col> <type> DEFAULT ...;"`
  Then the publish diff is clean and proposes no drop. Always decline/skip any
  publish migration that proposes DROP on real tables.
- **Prevention:** whenever you add a column to the app schema (which lands in
  Neon via db.py runtime migration), ALSO run the same additive ALTER against
  `$DATABASE_URL` (managed dev DB) so the next Publish stays non-destructive.
