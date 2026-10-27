"""Audited UTC health finalization; immutable finals, no index/LLM writes."""
from datetime import timedelta
import json

UP_SQL = """
ALTER TABLE geri_daily_health ADD COLUMN IF NOT EXISTS provisional BOOLEAN;
UPDATE geri_daily_health SET provisional =
 (computed_at < ((index_date + 1)::timestamp AT TIME ZONE 'UTC'))
 WHERE provisional IS NULL;
ALTER TABLE geri_daily_health ALTER COLUMN provisional SET DEFAULT FALSE;
ALTER TABLE geri_daily_health ALTER COLUMN provisional SET NOT NULL;
CREATE TABLE IF NOT EXISTS geri_daily_health_revisions (
 id BIGSERIAL PRIMARY KEY,index_date DATE NOT NULL,
 old_payload JSONB NOT NULL,new_payload JSONB NOT NULL,
 reason TEXT NOT NULL CHECK(length(trim(reason))>0),
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE OR REPLACE FUNCTION geri_guard_final_health() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='UPDATE' AND NOT OLD.provisional THEN
   RETURN NULL;
 END IF;
 NEW.provisional := NEW.computed_at < ((NEW.index_date + 1)::timestamp AT TIME ZONE 'UTC');
 IF TG_OP='UPDATE' AND OLD.provisional AND NOT NEW.provisional THEN
   INSERT INTO geri_daily_health_revisions(index_date,old_payload,new_payload,reason)
    VALUES(OLD.index_date,to_jsonb(OLD),to_jsonb(NEW),
     coalesce(nullif(current_setting('geri.health_revision_reason',true),''),
              'partial-day health flag finalized'));
 END IF;
 RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS geri_health_final_guard ON geri_daily_health;
CREATE TRIGGER geri_health_final_guard BEFORE INSERT OR UPDATE ON geri_daily_health
 FOR EACH ROW EXECUTE FUNCTION geri_guard_final_health();
"""


def migrate():
    from src.db.db import get_cursor
    with get_cursor() as c:
        c.execute(UP_SQL)


def is_provisional(row):
    """Also recognize old-schema rows; do not mislabel immutable final rows."""
    if "provisional" in row:
        return bool(row["provisional"])
    at = row.get("computed_at")
    return bool(at and at.date() <= row["index_date"])


def effective_health(cursor, start, end):
    """SELECT-only overlay: stale past provisional badges use final evaluation."""
    from src.geri.health import health_series, utc_today
    cursor.execute("SELECT * FROM geri_daily_health WHERE index_date BETWEEN %s AND %s",
                   (start, end))
    rows = {r["index_date"]: dict(r) for r in cursor.fetchall()}
    today = utc_today()
    stale = [d for d, r in rows.items() if d < today and is_provisional(r)]
    recalculated = health_series(cursor, min(stale), max(stale)) if stale else {}
    for d, row in list(rows.items()):
        if d >= today:
            rows[d] = {**row, "data_quality": "OK", "provisional": True,
                       "badge_suppressed": "open UTC day"}
        elif d in recalculated:
            rows[d] = {**recalculated[d], "provisional": False,
                       "evaluation_source": "read-only closed-day evaluation; persistence pending"}
    return rows


def finalize_provisional():
    """Serialize with all health writers. Trigger archives each old row first."""
    from src.db.db import get_cursor
    from src.geri.health import health_series, utc_today
    changed = []
    with get_cursor() as c:
        c.execute("SELECT pg_advisory_xact_lock(12014,1)")
        c.execute("""SELECT * FROM geri_daily_health WHERE provisional
                     AND index_date<%s ORDER BY index_date FOR UPDATE""", (utc_today(),))
        old_rows = [dict(r) for r in c.fetchall()]
        if not old_rows:
            return changed
        final = health_series(c, old_rows[0]["index_date"], old_rows[-1]["index_date"])
        c.execute("SELECT set_config('geri.health_revision_reason',%s,true)",
                  ("partial-day health flag finalized",))
        for old in old_rows:
            new = final[old["index_date"]]
            c.execute("""UPDATE geri_daily_health SET alerts_count=%s,alerts_ratio=%s,
                events_count=%s,events_ratio=%s,feeds_ok=%s,feeds_configured=%s,
                data_quality=%s,details=%s::jsonb,computed_at=clock_timestamp(),provisional=false
                WHERE index_date=%s AND provisional RETURNING *""",
                tuple(new.get(k) for k in ("alerts_count", "alerts_ratio", "events_count",
                      "events_ratio", "feeds_ok", "feeds_configured", "data_quality"))
                + (json.dumps(new["details"], default=str), old["index_date"]))
            updated = c.fetchone()
            if updated:
                changed.append({"old": old, "new": dict(updated)})
    return changed


def repair_private_chain(start):
    """Explicit private revisions only; never rewrite frozen shadow or v1.1."""
    from src.db.db import get_cursor
    from src.geri.version12 import compute_day
    from src.geri.model_selection import published_model, live_model
    if published_model() != "v1.1" or live_model() != "legacy":
        raise RuntimeError("Health repair requires unchanged public legacy selectors")
    with get_cursor(commit=False) as c:
        c.execute("""SELECT date,value,smoothing_state FROM intel_indices_daily_v12
                     WHERE date>=%s AND index_id='global:geo_energy_risk'
                     ORDER BY date""", (start,))
        old_rows = [dict(r) for r in c.fetchall()]
    revisions = []
    for old in old_rows:
        with get_cursor(commit=False) as c:
            c.execute("""SELECT 1 FROM geri_v12_ops WHERE index_date=%s
                AND kind='health_finalization_correction'""", (old["date"],))
            if c.fetchone():
                continue
        new = compute_day(old["date"], force=True,
                          reason="partial-day health flag finalized", apply_revision=True)
        details = {"reason": "partial-day health flag finalized", "old_value": old["value"],
                   "new_value": new["value"], "excluded_from_prospective": True,
                   "shadow_rewritten": False}
        with get_cursor() as c:
            c.execute("""INSERT INTO geri_v12_ops(index_date,kind,details)
                VALUES(%s,'health_finalization_correction',%s::jsonb)
                ON CONFLICT(index_date,kind) DO NOTHING""",
                (old["date"], json.dumps(details)))
        revisions.append({"date": old["date"], **details})
    return revisions


def finalize_and_repair():
    changes = finalize_provisional()
    # The revision ledger also acts as a durable retry queue if repair fails
    # after the health transaction commits. Already-repaired dates are skipped.
    from src.db.db import get_cursor
    with get_cursor(commit=False) as c:
        c.execute("""SELECT min(r.index_date) AS start FROM geri_daily_health_revisions r
            WHERE NOT EXISTS(SELECT 1 FROM geri_v12_ops o WHERE o.index_date=r.index_date
              AND o.kind='health_repair_complete')""")
        start = c.fetchone()["start"]
    if start:
        repair_private_chain(start)
        with get_cursor() as c:
            c.execute("""INSERT INTO geri_v12_ops(index_date,kind,details)
                SELECT DISTINCT index_date,'health_repair_complete',
                    '{"reason":"partial-day health flag finalized"}'::jsonb
                FROM geri_daily_health_revisions WHERE index_date>=%s
                ON CONFLICT(index_date,kind) DO NOTHING""", (start,))
    return changes
