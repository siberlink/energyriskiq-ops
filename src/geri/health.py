"""GERI input completeness. Classification is pure and never changes a score."""
from datetime import datetime, timedelta, timezone
from statistics import median

ALERT_RATIO_FLOOR = 0.40
EVENT_RATIO_FLOOR = 0.40
FEED_SUCCESS_FLOOR = 0.50
HEALTH_POLICY = {"OK": "compute", "DEGRADED": "compute_exclude", "UNAVAILABLE": "skip"}


def excluded_history_statuses():
    return [status for status, action in HEALTH_POLICY.items()
            if action in {"compute_exclude", "skip"}]


def badge_html(status):
    label = {"DEGRADED": "Data incomplete", "UNAVAILABLE": "Unavailable"}.get(status)
    return (f'<span class="geri-data-quality-badge" style="display:inline-block;'
            f'padding:3px 8px;border:1px solid #d49d42;border-radius:5px;'
            f'font-size:12px;color:#f3c677;background:#33291c">{label}</span>'
            if label else "")


def utc_today():
    return datetime.now(timezone.utc).date()


def utc_bounds(day):
    start = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
    return start, start + timedelta(days=1)


def evaluate_day(day, alert_counts, event_counts=None, first_day=None, feed=None):
    first_day = first_day or min(alert_counts, default=day)
    prior = [day - timedelta(days=offset) for offset in (7, 14, 21, 28)
             if day - timedelta(days=offset) >= first_day]

    def ratio(counts):
        if counts is None or len(prior) < 3:
            return None, None
        base = median(counts.get(d, 0) for d in prior)
        return (counts.get(day, 0) / base if base > 0 else None), base

    alerts_ratio, alerts_median = ratio(alert_counts)
    events_ratio, events_median = ratio(event_counts)
    feeds_ok = feed.get("feeds_ok") if feed else None
    configured = feed.get("feeds_configured") if feed else None
    success = feeds_ok / configured if feeds_ok is not None and configured else None
    quality = "OK"
    if ((alerts_ratio is not None and alerts_ratio < ALERT_RATIO_FLOOR)
            or (events_ratio is not None and events_ratio < EVENT_RATIO_FLOOR)
            or (success is not None and success < FEED_SUCCESS_FLOOR)):
        quality = "DEGRADED"
    if alert_counts.get(day, 0) == 0 and events_ratio is not None and events_ratio < EVENT_RATIO_FLOOR:
        quality = "UNAVAILABLE"
    return {
        "index_date": day, "alerts_count": alert_counts.get(day, 0),
        "alerts_ratio": alerts_ratio,
        "events_count": event_counts.get(day, 0) if event_counts is not None else None,
        "events_ratio": events_ratio, "feeds_ok": feeds_ok,
        "feeds_configured": configured, "data_quality": quality,
        "details": {
            "same_weekday_observations": len(prior),
            "alerts_median": alerts_median, "events_median": events_median,
            "feed_success": success,
            "feed_note": "No persisted per-feed fetch-success counts exist; ingestion_runs "
                         "records item/run statistics, not feeds fetched OK. Check skipped."
                         if feed is None else None,
            "partial_utc_day": day >= utc_today(),
        },
    }


def load_health_counts(cursor, start, end):
    """SELECT-only; usable from both enforced-read-only lab and production."""
    from src.geri.types import VALID_ALERT_TYPES
    cursor.execute("SELECT min(created_at)::date AS day FROM alert_events WHERE alert_type=ANY(%s)",
                   (VALID_ALERT_TYPES,))
    first = cursor.fetchone()["day"] or start
    lower, _ = utc_bounds(start - timedelta(days=28))
    _, upper = utc_bounds(end)
    cursor.execute(
        """SELECT created_at::date AS day,count(*) AS n FROM alert_events
           WHERE alert_type=ANY(%s) AND created_at >= (%s AT TIME ZONE 'UTC')
             AND created_at < (%s AT TIME ZONE 'UTC') GROUP BY 1""",
        (VALID_ALERT_TYPES, lower, upper))
    alerts = {row["day"]: row["n"] for row in cursor.fetchall()}
    cursor.execute(
        """SELECT inserted_at::date AS day,count(*) AS n FROM events
           WHERE inserted_at >= (%s AT TIME ZONE 'UTC')
             AND inserted_at < (%s AT TIME ZONE 'UTC') GROUP BY 1""", (lower, upper))
    events = {row["day"]: row["n"] for row in cursor.fetchall()}
    return alerts, events, first


def health_series(cursor, start, end):
    alerts, events, first = load_health_counts(cursor, start, end)
    result = {}
    day = start
    while day <= end:
        result[day] = evaluate_day(day, alerts, events, first)
        day += timedelta(days=1)
    return result


def store_health(rows):
    """The ONLY historical backfill here writes health metadata, never indices."""
    import json
    from src.db.db import get_cursor
    with get_cursor() as cursor:
        for row in rows:
            cursor.execute(
                """INSERT INTO geri_daily_health
                   (index_date,alerts_count,alerts_ratio,events_count,events_ratio,
                    feeds_ok,feeds_configured,data_quality,details,computed_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
                   ON CONFLICT(index_date) DO UPDATE SET
                   alerts_count=EXCLUDED.alerts_count, alerts_ratio=EXCLUDED.alerts_ratio,
                   events_count=EXCLUDED.events_count,events_ratio=EXCLUDED.events_ratio,
                   feeds_ok=EXCLUDED.feeds_ok,feeds_configured=EXCLUDED.feeds_configured,
                   data_quality=EXCLUDED.data_quality,details=EXCLUDED.details,computed_at=NOW()""",
                tuple(row.get(k) for k in ("index_date", "alerts_count", "alerts_ratio",
                      "events_count", "events_ratio", "feeds_ok", "feeds_configured", "data_quality"))
                + (json.dumps(row["details"], default=str),))


def record_health(day):
    from src.db.db import get_production_cursor
    with get_production_cursor() as cursor:
        row = health_series(cursor, day, day)[day]
    store_health([row])
    return row
