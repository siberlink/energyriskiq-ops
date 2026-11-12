"""Observation provenance shared by report generation and index delivery."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal


def index_observations(geri, eeri, egsi):
    def latest(rows):
        return rows[0] if isinstance(rows, list) and rows else (
            None if isinstance(rows, list) else rows)
    geri, eeri, egsi = map(latest, (geri, eeri, egsi))
    def value(row):
        v = row.get("value") if row else None
        return float(v) if isinstance(v, Decimal) else v
    target = str(datetime.now(timezone.utc).date() - timedelta(days=1))
    return {
        name: {"date": str(row.get("date")) if row and row.get("date") else None,
               "value": value(row),
               "target_date": target,
               "stale": not row or str(row.get("date")) != target}
        for name, row in (("geri", geri), ("eeri", eeri), ("egsi_m", egsi))
    }
