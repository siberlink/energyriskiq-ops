"""Shared final-health policy; repair/evidence flags never alter scoring."""
from datetime import datetime, timedelta, timezone


class FinalHealthPending(ValueError):
    """A closed UTC day has not yet acquired its authoritative health record."""


def utc(value):
    return (value.replace(tzinfo=timezone.utc) if value.tzinfo is None
            else value.astimezone(timezone.utc))


def final_health(cursor, day):
    if day >= datetime.now(timezone.utc).date():
        raise FinalHealthPending(f"UTC day is not closed: {day}")
    cursor.execute("SELECT * FROM geri_daily_health WHERE index_date=%s", (day,))
    row = cursor.fetchone()
    if not row or row.get("provisional", False) or utc(row["computed_at"]).date() <= day:
        raise FinalHealthPending(f"Final closed-day health is not available: {day}")
    return dict(row)


def final_history(cursor, history):
    """Overlay final quality without filtering calendar state or late repairs.

    EWMA still advances/holds on every calendar day. The shared mathematics
    selects only final-OK rows for weekday and normalization windows.
    """
    if not history:
        return []
    dates = [r["index_date"] for r in history]
    cursor.execute("""SELECT index_date,data_quality,provisional,computed_at
        FROM geri_daily_health WHERE index_date=ANY(%s)""", (dates,))
    health = {r["index_date"]: r for r in cursor.fetchall()}
    result = []
    for row in history:
        h = health.get(row["index_date"])
        final = (h and not h["provisional"]
                 and utc(h["computed_at"]).date() > row["index_date"])
        result.append({**row, "inputs": {**row["inputs"],
            "data_quality": h["data_quality"] if final else "UNAVAILABLE"}})
    return result


def exclude_correction(cursor, day, details):
    """Use the existing gate exclusion, never relax a gate for reconstructed data."""
    import json
    cursor.execute("""INSERT INTO geri_v12_ops(index_date,kind,details)
        VALUES(%s,'health_finalization_correction',%s::jsonb)
        ON CONFLICT(index_date,kind) DO UPDATE SET
        details=geri_v12_ops.details || EXCLUDED.details,observed_at=now()""",
        (day, json.dumps({"excluded_from_prospective": True,
                         "latest_parity_correction": details}, default=str)))
