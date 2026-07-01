"""
EUR/USD Currency Rate Integration

Fetches EUR/USD daily closing prices and stores daily snapshots in the
eurusd_snapshots table for GERI / EERI (RERI) calculations.

Sources (in priority order):
  1. FRED series DEXUSEU (US dollars to one euro = EUR/USD) — the Federal
     Reserve H.10 official daily rate. Free, no API key, extremely stable.
     Note: this is the noon buying rate and is published with a few days'
     lag, so it is authoritative for backfill but often not yet available
     for "yesterday".
  2. Yahoo Finance (yfinance) ticker EURUSD=X — market close with full OHLC.
     Same-day availability, used as a fallback (mainly for daily capture
     before FRED publishes, and to fill any gaps FRED skips).

FRED CSV endpoint: https://fred.stlouisfed.org/graph/fredgraph.csv?id=DEXUSEU
Yahoo ticker: EURUSD=X
"""

import io
import json
import logging
from datetime import datetime, date, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

import requests
import pandas as pd

from src.db.db import get_cursor, execute_one

logger = logging.getLogger(__name__)

FRED_SERIES_ID = "DEXUSEU"  # US dollars to one euro = EUR/USD
FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
YAHOO_TICKER = "EURUSD=X"


@dataclass
class EURUSDSnapshot:
    """Represents a daily EUR/USD exchange rate snapshot."""
    date: str
    rate: float
    currency_pair: str
    source: str
    raw_data: Dict[str, Any]


# ---------------------------------------------------------------------------
# Source fetchers
# ---------------------------------------------------------------------------

def _fetch_eurusd_from_fred(from_date: date, to_date: date) -> List[EURUSDSnapshot]:
    """
    Fetch EUR/USD daily rates from FRED series DEXUSEU for a date range.

    DEXUSEU is quoted as US dollars per euro, which is the EUR/USD rate
    directly (no inversion needed). Returns closing rates only (no OHLC);
    weekends and US holidays are absent from the series.
    """
    url = (
        f"{FRED_CSV_URL}"
        f"?id={FRED_SERIES_ID}"
        f"&cosd={from_date.isoformat()}"
        f"&coed={to_date.isoformat()}"
    )

    logger.info(f"Fetching EUR/USD from FRED ({FRED_SERIES_ID}) {from_date} to {to_date}...")

    try:
        response = requests.get(url, timeout=20)
        response.raise_for_status()

        df = pd.read_csv(io.StringIO(response.text))
        if df.empty:
            logger.warning("No EUR/USD data returned from FRED")
            return []

        date_col = "observation_date" if "observation_date" in df.columns else "DATE"

        snapshots: List[EURUSDSnapshot] = []
        for _, row in df.iterrows():
            date_str = str(row.get(date_col, "")).strip()[:10]
            value = row.get(FRED_SERIES_ID, "")

            if not date_str or str(value).strip() in ("", ".") or pd.isna(value):
                continue

            try:
                rate = float(value)
            except (ValueError, TypeError):
                continue

            if rate <= 0:
                continue

            snapshots.append(EURUSDSnapshot(
                date=date_str,
                rate=rate,
                currency_pair="EUR/USD",
                source="fred",
                raw_data={
                    "close": rate,
                    "series": FRED_SERIES_ID,
                    "granularity": "D_noon",
                },
            ))

        logger.info(f"Fetched {len(snapshots)} EUR/USD points from FRED")
        return snapshots

    except Exception as e:
        logger.error(f"Failed to fetch EUR/USD from FRED: {e}")
        return []


def _fetch_eurusd_from_yahoo(from_date: date, to_date: date) -> List[EURUSDSnapshot]:
    """
    Fetch EUR/USD daily candles from Yahoo Finance (ticker EURUSD=X).

    Provides market close with full OHLC. Used as a fallback source
    (fresher same-day availability than FRED). Weekends are absent.
    """
    try:
        import yfinance as yf
    except Exception as e:
        logger.error(f"yfinance not available: {e}")
        return []

    logger.info(f"Fetching EUR/USD from Yahoo ({YAHOO_TICKER}) {from_date} to {to_date}...")

    try:
        ticker = yf.Ticker(YAHOO_TICKER)
        # end is exclusive in yfinance history(); add a day to include to_date
        hist = ticker.history(
            start=from_date.isoformat(),
            end=(to_date + timedelta(days=1)).isoformat(),
            interval="1d",
            auto_adjust=False,
        )

        if hist is None or hist.empty:
            logger.warning("No EUR/USD data returned from Yahoo")
            return []

        snapshots: List[EURUSDSnapshot] = []
        for idx, row in hist.iterrows():
            try:
                candle_date = idx.date().isoformat()
            except Exception:
                candle_date = str(idx)[:10]

            try:
                close_price = float(row.get("Close"))
            except (ValueError, TypeError):
                continue

            if not close_price or close_price <= 0 or pd.isna(close_price):
                continue

            def _f(key):
                try:
                    v = float(row.get(key))
                    return None if pd.isna(v) else v
                except (ValueError, TypeError):
                    return None

            snapshots.append(EURUSDSnapshot(
                date=candle_date,
                rate=close_price,
                currency_pair="EUR/USD",
                source="yahoo",
                raw_data={
                    "open": _f("Open"),
                    "high": _f("High"),
                    "low": _f("Low"),
                    "close": close_price,
                    "granularity": "D",
                },
            ))

        logger.info(f"Fetched {len(snapshots)} EUR/USD points from Yahoo")
        return snapshots

    except Exception as e:
        logger.error(f"Failed to fetch EUR/USD from Yahoo: {e}")
        return []


def _fetch_eurusd_range_merged(from_date: date, to_date: date) -> Dict[str, EURUSDSnapshot]:
    """
    Fetch a date range from FRED (primary) and fill any gaps with Yahoo
    (fallback). Returns a dict keyed by ISO date string.
    """
    merged: Dict[str, EURUSDSnapshot] = {}

    for snap in _fetch_eurusd_from_fred(from_date, to_date):
        merged[snap.date] = snap

    # Determine which weekdays FRED did not cover, then backfill from Yahoo.
    needed = set()
    cur = from_date
    while cur <= to_date:
        if cur.weekday() < 5:  # Mon-Fri (FX daily observations are weekdays)
            needed.add(cur.isoformat())
        cur += timedelta(days=1)

    missing = needed - set(merged.keys())
    if missing:
        logger.info(f"FRED missing {len(missing)} weekday(s); trying Yahoo fallback...")
        for snap in _fetch_eurusd_from_yahoo(from_date, to_date):
            if snap.date not in merged:
                merged[snap.date] = snap

    return merged


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def save_eurusd_snapshot(snapshot: EURUSDSnapshot) -> bool:
    """
    Save a EUR/USD rate snapshot to the database.

    Uses ON CONFLICT (date) to update if an entry for the date already exists.
    """
    try:
        with get_cursor() as cursor:
            cursor.execute("""
                INSERT INTO eurusd_snapshots
                (date, rate, currency_pair, source, raw_data)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (date) DO UPDATE SET
                    rate = EXCLUDED.rate,
                    currency_pair = EXCLUDED.currency_pair,
                    source = EXCLUDED.source,
                    raw_data = EXCLUDED.raw_data
            """, (
                snapshot.date,
                snapshot.rate,
                snapshot.currency_pair,
                snapshot.source,
                json.dumps(snapshot.raw_data),
            ))
        logger.info(f"Saved EUR/USD snapshot for {snapshot.date}: {snapshot.rate:.6f} ({snapshot.source})")
        return True
    except Exception as e:
        logger.error(f"Failed to save EUR/USD snapshot: {e}")
        return False


def _save_snapshots(snapshots: List[EURUSDSnapshot]) -> Dict[str, Any]:
    """Bulk upsert a list of snapshots. Returns counts and date range."""
    saved = 0
    by_source: Dict[str, int] = {}
    dates_saved: List[str] = []

    try:
        with get_cursor() as cursor:
            for snapshot in snapshots:
                cursor.execute("""
                    INSERT INTO eurusd_snapshots
                    (date, rate, currency_pair, source, raw_data)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (date) DO UPDATE SET
                        rate = EXCLUDED.rate,
                        currency_pair = EXCLUDED.currency_pair,
                        source = EXCLUDED.source,
                        raw_data = EXCLUDED.raw_data
                """, (
                    snapshot.date,
                    snapshot.rate,
                    snapshot.currency_pair,
                    snapshot.source,
                    json.dumps(snapshot.raw_data),
                ))
                saved += 1
                by_source[snapshot.source] = by_source.get(snapshot.source, 0) + 1
                dates_saved.append(snapshot.date)
    except Exception as e:
        logger.error(f"Failed to persist EUR/USD snapshots: {e}")
        return {"status": "error", "message": str(e)}

    return {
        "status": "success",
        "days": saved,
        "by_source": by_source,
        "date_range": f"{min(dates_saved)} to {max(dates_saved)}" if dates_saved else "N/A",
    }


# ---------------------------------------------------------------------------
# Public API (interface preserved for callers in internal_routes.py)
# ---------------------------------------------------------------------------

def fetch_eurusd_rate() -> Optional[EURUSDSnapshot]:
    """
    Fetch the most recent available EUR/USD closing price.

    Tries FRED first (a recent window) and falls back to Yahoo. Returns the
    snapshot for the latest available date, or None on failure.
    """
    logger.info("Fetching latest EUR/USD rate (FRED primary, Yahoo fallback)...")

    end = date.today()
    start = end - timedelta(days=14)

    # Merge both sources so we return the freshest available date. FRED is
    # authoritative for any date it covers, but it lags a few days, so Yahoo
    # typically holds the most recent close.
    merged: Dict[str, EURUSDSnapshot] = {}
    for snap in _fetch_eurusd_from_yahoo(start, end):
        merged[snap.date] = snap
    for snap in _fetch_eurusd_from_fred(start, end):
        merged[snap.date] = snap  # FRED overrides Yahoo for shared dates

    if not merged:
        logger.error("No EUR/USD data available from FRED or Yahoo")
        return None

    latest = merged[max(merged.keys())]
    logger.info(f"Latest EUR/USD for {latest.date}: {latest.rate:.6f} ({latest.source})")
    return latest


def capture_eurusd_snapshot() -> Dict[str, Any]:
    """
    Main daily entry point: fetch and store yesterday's EUR/USD rate.

    Looks for the target date (yesterday, UTC) in FRED first; if FRED has not
    published it yet (typical, due to the H.10 release lag), falls back to
    Yahoo's same-day close. Returns a status dict.
    """
    target_date = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")

    existing = execute_one(
        "SELECT id FROM eurusd_snapshots WHERE date = %s",
        (target_date,),
    )
    if existing:
        logger.info(f"EUR/USD snapshot already exists for {target_date}")
        return {
            "status": "skipped",
            "message": f"Snapshot already exists for {target_date}",
            "date": target_date,
        }

    target_obj = date.fromisoformat(target_date)
    window_start = target_obj - timedelta(days=10)

    fred = _fetch_eurusd_from_fred(window_start, target_obj)
    match = next((s for s in fred if s.date == target_date), None)

    if match is None:
        logger.info(f"FRED has no value for {target_date} yet; trying Yahoo...")
        yahoo = _fetch_eurusd_from_yahoo(window_start, target_obj)
        match = next((s for s in yahoo if s.date == target_date), None)
        fetched_any = bool(fred or yahoo)
    else:
        fetched_any = True

    if match:
        if save_eurusd_snapshot(match):
            return {
                "status": "success",
                "message": f"Captured EUR/USD rate for {match.date}",
                "date": match.date,
                "rate": match.rate,
                "source": match.source,
            }
        return {
            "status": "error",
            "message": f"Failed to save EUR/USD snapshot for {target_date}",
            "date": target_date,
        }

    if fetched_any:
        # Sources responded but had no observation for the target date
        # (weekend or holiday). Not an error condition.
        logger.info(f"No EUR/USD observation for {target_date} (likely weekend/holiday)")
        return {
            "status": "skipped",
            "message": f"No EUR/USD observation for {target_date} (weekend/holiday)",
            "date": target_date,
        }

    return {
        "status": "error",
        "message": f"Failed to fetch EUR/USD rate for {target_date} (FRED and Yahoo both failed)",
        "date": target_date,
    }


def get_eurusd_for_date(target_date: date) -> Optional[Dict[str, Any]]:
    """Get the EUR/USD snapshot for a specific date."""
    result = execute_one(
        "SELECT * FROM eurusd_snapshots WHERE date = %s",
        (target_date,),
    )
    return dict(result) if result else None


def backfill_eurusd_history(days: int = 90) -> Dict[str, Any]:
    """
    Backfill EUR/USD history for the last `days` days.

    Uses FRED as the authoritative source and fills any gaps with Yahoo.
    """
    end = date.today()
    start = end - timedelta(days=days)
    return backfill_eurusd_range(start, end)


def backfill_eurusd_range(from_date: date, to_date: date) -> Dict[str, Any]:
    """
    Backfill EUR/USD history for a specific date range.

    FRED (DEXUSEU) is the primary source; any missing weekdays are filled
    from Yahoo (EURUSD=X). Existing rows are upserted (ON CONFLICT).
    """
    logger.info(f"Backfilling EUR/USD from {from_date} to {to_date}...")

    merged = _fetch_eurusd_range_merged(from_date, to_date)

    if not merged:
        return {
            "status": "error",
            "message": f"No EUR/USD data available from FRED or Yahoo for {from_date} to {to_date}",
        }

    snapshots = [merged[k] for k in sorted(merged.keys())]
    result = _save_snapshots(snapshots)

    if result.get("status") != "success":
        return result

    by_source = result.get("by_source", {})
    logger.info(
        f"Backfilled {result['days']} EUR/USD snapshots "
        f"({by_source.get('fred', 0)} FRED, {by_source.get('yahoo', 0)} Yahoo)"
    )

    return {
        "status": "success",
        "message": (
            f"Backfilled {result['days']} EUR/USD snapshots "
            f"({by_source.get('fred', 0)} FRED, {by_source.get('yahoo', 0)} Yahoo)"
        ),
        "days": result["days"],
        "saved": result["days"],
        "fred": by_source.get("fred", 0),
        "yahoo": by_source.get("yahoo", 0),
        "date_range": result["date_range"],
        "source": "fred+yahoo",
    }
