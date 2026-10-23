"""One read-only, repeatable-read snapshot. No application repository/service calls."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json

from psycopg2 import connect
from psycopg2.extras import RealDictCursor
from src.db.db import get_database_url
from src.geri.types import INDEX_ID


@contextmanager
def readonly_snapshot():
    # Enforce read-only before the first SQL statement, not merely by convention.
    connection = connect(
        get_database_url(), connect_timeout=15,
        options="-c default_transaction_read_only=on -c timezone=UTC "
                "-c statement_timeout=90000",
        application_name="geri_lab_readonly",
    )
    try:
        connection.set_session(readonly=True, isolation_level="REPEATABLE READ")
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SHOW transaction_read_only")
            if cursor.fetchone()["transaction_read_only"] != "on":
                raise RuntimeError("Refusing to run without server-enforced read-only mode.")
            yield cursor
    finally:
        connection.rollback()
        connection.close()


def fingerprints(cursor):
    result = {}
    # Fixed identifiers, never supplied by users.
    for table, timestamp in (
        ("intel_indices_daily", "computed_at"),
        ("alert_events", "created_at"),
        ("events", "inserted_at"),
    ):
        cursor.execute(
            f"SELECT count(*) AS row_count, max(id) AS max_id, "
            f"max({timestamp}) AS max_timestamp FROM {table}"
        )
        result[table] = dict(cursor.fetchone())
    return result


def completed_market_end(end, today=None):
    """Never label a forward daily outcome with today's unfinished snapshot."""
    today = today or datetime.now(timezone.utc).date()
    return min(end + timedelta(days=21), today - timedelta(days=1))


def load(cursor, start, end, variant):
    from src.geri.health import health_series
    cursor.execute(
        "SELECT min(created_at)::date AS first_day FROM alert_events "
        "WHERE alert_type=ANY(%s)", (list(variant.accepted_types),),
    )
    first_day = cursor.fetchone()["first_day"]
    warmup = max(start - timedelta(days=variant.baseline_window_days), first_day or start)
    warmup = min(start, warmup)
    start_at = datetime.combine(warmup, datetime.min.time())
    end_at = datetime.combine(end + timedelta(days=1), datetime.min.time())
    cursor.execute(
        """SELECT a.id, a.alert_type, a.severity, a.confidence AS risk_score,
                  a.scope_region AS region, 1.0 AS weight,
                  a.created_at, a.headline, a.body, a.raw_input,
                  e.is_geri_driver, e.market_relevance, e.source_name AS source,
                  left(COALESCE(e.raw_text,''),700) AS event_excerpt,
                  e.signal_quality_details->'components'->>'energy_relevance' AS energy_relevance
           FROM alert_events a
           LEFT JOIN events e ON e.id = a.driver_event_ids[1]
           WHERE a.alert_type=ANY(%s) AND a.created_at >= %s AND a.created_at < %s
           ORDER BY a.created_at, a.id""",
        (list(variant.accepted_types), start_at, end_at),
    )
    alerts = [dict(row) for row in cursor.fetchall()]
    # No headline/body exports; a digest identifies the exact consumed snapshot.
    digest = hashlib.sha256(json.dumps(alerts, default=str, sort_keys=True).encode()).hexdigest()
    cursor.execute(
        """SELECT date,value,components,model_version,computed_at
           FROM intel_indices_daily WHERE index_id=%s AND date >= %s AND date <= %s
           ORDER BY date""", (INDEX_ID, warmup, end),
    )
    published = [dict(row) for row in cursor.fetchall()]
    markets = {}
    for name, table, column in (
        ("Brent", "oil_price_snapshots", "brent_price"),
        ("TTF", "ttf_gas_snapshots", "ttf_price"),
        ("VIX", "vix_snapshots", "vix_close"),
    ):
        # Earlier prices allow causal 10-return volatility on the first test day.
        # Later prices are needed to label forward 1/3-session outcomes.
        cursor.execute(
            f"SELECT date,{column} AS value FROM {table} "
            "WHERE date >= %s AND date <= %s ORDER BY date,id",
            (start - timedelta(days=60), completed_market_end(end)),
        )
        markets[name] = [dict(row) for row in cursor.fetchall()]
    return {
        "warmup": warmup, "alerts": alerts, "published": published,
        "markets": markets, "alert_sha256": digest,
        "health": health_series(cursor, warmup, end),
    }
