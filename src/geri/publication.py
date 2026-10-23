"""Atomic publication: immutable by default, reasoned revision proposals otherwise."""
from dataclasses import asdict
import json
import subprocess
from src.db.db import get_cursor


def code_sha():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, timeout=5,
            stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.SubprocessError):
        return "unavailable"


def publish(result, force=False, reason=None, apply_revision=False):
    if apply_revision and not force:
        raise ValueError("Applying a revision requires force=True.")
    if force and not (reason and reason.strip()):
        raise ValueError("A nonempty reason is required for forced recomputation.")
    payload = {
        "index_id": result.index_id, "date": result.index_date.isoformat(),
        "value": result.value, "band": result.band.value,
        "trend_1d": result.trend_1d, "trend_7d": result.trend_7d,
        "components": result.components.to_dict(), "model_version": result.model_version,
        "interpretation": result.components.interpretation or "",
    }
    sha = code_sha()
    snapshot = getattr(result, "input_snapshot", None)
    with get_cursor() as cursor:
        # Lock concurrent revision writers to the same observation.
        cursor.execute("SELECT * FROM intel_indices_daily WHERE index_id=%s AND date=%s FOR UPDATE",
                       (result.index_id, result.index_date))
        old = cursor.fetchone()
        if force:
            cursor.execute(
                """INSERT INTO geri_revisions
                   (index_date,old_value,new_value,old_payload,new_payload,reason,model_version,code_sha,applied)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (result.index_date, old["value"] if old else None, result.value,
                 json.dumps(dict(old), default=str) if old else None,
                 json.dumps(payload, default=str), reason.strip(), result.model_version, sha,
                 apply_revision))
            result.revision_diff = {
                "date": result.index_date.isoformat(), "old_value": old["value"] if old else None,
                "new_value": result.value, "reason": reason.strip(), "applied": apply_revision,
            }
        should_write = (not force and not old) or (force and apply_revision)
        stored = False
        if should_write:
            sql = """INSERT INTO intel_indices_daily
                     (index_id,date,value,band,trend_1d,trend_7d,components,interpretation,model_version,computed_at)
                     VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
                     ON CONFLICT(index_id,date) """
            sql += ("""DO UPDATE SET value=EXCLUDED.value,band=EXCLUDED.band,
                       trend_1d=EXCLUDED.trend_1d,trend_7d=EXCLUDED.trend_7d,
                       components=EXCLUDED.components,interpretation=EXCLUDED.interpretation,
                       model_version=EXCLUDED.model_version,computed_at=NOW()"""
                    if apply_revision else "DO NOTHING")
            cursor.execute(sql + " RETURNING id",
                           (result.index_id,result.index_date,result.value,result.band.value,
                            result.trend_1d,result.trend_7d,json.dumps(payload["components"]),
                            payload["interpretation"],result.model_version))
            stored = cursor.fetchone() is not None
        if snapshot:
            cursor.execute(
                """INSERT INTO geri_compute_snapshots
                   (index_date,alert_ids,baseline_start,baseline_end,baseline_rows,
                    baseline_dates,fallback_used,code_sha) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                (result.index_date,json.dumps(snapshot["alert_ids"]),
                 snapshot["baseline_start"],snapshot["baseline_end"],snapshot["baseline_rows"],
                 json.dumps(snapshot["baseline_dates"]),snapshot["fallback_used"],sha))
    return stored
