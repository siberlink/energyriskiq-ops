"""
EUR/USD Currency Rate API Integration

Fetches EUR/USD daily closing prices from Oanda REST API v20.
Stores daily snapshots in eurusd_snapshots table for GERI calculations.

Oanda provides precise forex data with 5-6 decimal places.
Uses daily candles (D granularity) for closing prices.

API Documentation: https://developer.oanda.com/rest-live-v20/pricing-ep/
"""

import os
import json
import logging
import requests
from datetime import datetime, date, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

from src.db.db import get_cursor, execute_one

logger = logging.getLogger(__name__)

OANDA_API_KEY = os.environ.get("OANDA_API_KEY", "")
OANDA_ACCOUNT_ID = os.environ.get("OANDA_ACCOUNT_ID", "")
OANDA_API_BASE = "https://api-fxtrade.oanda.com/v3"
EURUSD_INSTRUMENT = "EUR_USD"


@dataclass
class EURUSDSnapshot:
    """Represents a daily EUR/USD exchange rate snapshot."""
    date: str
    rate: float
    currency_pair: str
    source: str
    raw_data: Dict[str, Any]


def _get_oanda_headers() -> Dict[str, str]:
    """Get headers for Oanda API requests."""
    return {
        "Authorization": f"Bearer {OANDA_API_KEY}",
        "Content-Type": "application/json",
        "Accept-Datetime-Format": "RFC3339"
    }


def _fetch_eurusd_candles(count: int = 30, granularity: str = "D") -> List[Dict[str, Any]]:
    """
    Fetch EUR/USD daily candles from Oanda.
    
    Args:
        count: Number of candles to fetch (max 5000)
        granularity: Candle granularity (D=daily, H1=hourly, etc.)
        
    Returns:
        List of candle data with OHLC prices.
    """
    if not OANDA_API_KEY:
        logger.warning("OANDA_API_KEY not configured")
        return []
    
    url = f"{OANDA_API_BASE}/instruments/{EURUSD_INSTRUMENT}/candles"
    headers = _get_oanda_headers()
    params = {
        "granularity": granularity,
        "count": count,
        "price": "M"
    }
    
    logger.info(f"Fetching {count} EUR/USD daily candles from Oanda...")
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        
        if response.status_code == 401:
            logger.error("Oanda API key is invalid or expired")
            return []
        
        if response.status_code != 200:
            logger.error(f"Oanda API returned {response.status_code}: {response.text[:500]}")
            return []
        
        data = response.json()
        candles = data.get("candles", [])
        logger.info(f"Fetched {len(candles)} EUR/USD candles from Oanda")
        return candles
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Oanda API request failed: {e}")
        return []


def _fetch_eurusd_candles_range(from_date: date, to_date: date, granularity: str = "D") -> List[Dict[str, Any]]:
    """
    Fetch EUR/USD candles for a specific date range from Oanda.
    
    Args:
        from_date: Start date (inclusive)
        to_date: End date (inclusive)
        granularity: Candle granularity (D=daily, H4=4-hour, etc.)
        
    Returns:
        List of candle data with OHLC prices.
    """
    if not OANDA_API_KEY:
        logger.warning("OANDA_API_KEY not configured")
        return []
    
    from_str = from_date.strftime("%Y-%m-%dT00:00:00Z")
    to_str = (to_date + timedelta(days=1)).strftime("%Y-%m-%dT00:00:00Z")
    
    url = f"{OANDA_API_BASE}/instruments/{EURUSD_INSTRUMENT}/candles"
    headers = _get_oanda_headers()
    params = {
        "granularity": granularity,
        "from": from_str,
        "to": to_str,
        "price": "M"
    }
    
    logger.info(f"Fetching EUR/USD {granularity} candles from {from_date} to {to_date}...")
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        
        if response.status_code == 401:
            logger.error("Oanda API key is invalid or expired")
            return []
        
        if response.status_code != 200:
            logger.error(f"Oanda API returned {response.status_code}: {response.text[:500]}")
            return []
        
        data = response.json()
        candles = data.get("candles", [])
        logger.info(f"Fetched {len(candles)} EUR/USD {granularity} candles from Oanda")
        return candles
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Oanda API request failed: {e}")
        return []


def _get_last_4h_close_for_date(target_date: date) -> Optional[EURUSDSnapshot]:
    """
    Get the last 4H candle closing price for a specific date.
    
    This is used as a fallback when the daily candle is incomplete (current day).
    The last 4H candle of the day (20:00-00:00 UTC) gives a close approximation
    to the end-of-day price.
    
    Args:
        target_date: The date to get the 4H close for
        
    Returns:
        EURUSDSnapshot with the last 4H candle close, or None if unavailable
    """
    candles = _fetch_eurusd_candles_range(target_date, target_date, granularity="H4")
    
    if not candles:
        logger.warning(f"No 4H candles available for {target_date}")
        return None
    
    completed_candles = [c for c in candles if c.get("complete", False)]
    
    if not completed_candles:
        logger.warning(f"No completed 4H candles for {target_date}")
        return None
    
    last_candle = completed_candles[-1]
    
    try:
        mid = last_candle.get("mid", {})
        close_price = float(mid.get("c", 0))
        
        if close_price == 0:
            return None
        
        candle_time = last_candle.get("time", "")[:19]
        
        return EURUSDSnapshot(
            date=target_date.isoformat(),
            rate=close_price,
            currency_pair="EUR/USD",
            source="oanda_4h_fallback",
            raw_data={
                "open": mid.get("o"),
                "high": mid.get("h"),
                "low": mid.get("l"),
                "close": mid.get("c"),
                "volume": last_candle.get("volume"),
                "complete": last_candle.get("complete"),
                "candle_time": candle_time,
                "granularity": "H4",
                "fallback_reason": "daily_candle_incomplete"
            }
        )
    except Exception as e:
        logger.error(f"Failed to parse 4H candle for {target_date}: {e}")
        return None


def _parse_candle_to_snapshot(candle: Dict[str, Any]) -> Optional[EURUSDSnapshot]:
    """Parse an Oanda candle to a EURUSDSnapshot."""
    try:
        time_str = candle.get("time", "")
        if not time_str:
            return None
        
        candle_date = time_str[:10]
        
        mid = candle.get("mid", {})
        close_price = float(mid.get("c", 0))
        
        if close_price == 0:
            return None
        
        return EURUSDSnapshot(
            date=candle_date,
            rate=close_price,
            currency_pair="EUR/USD",
            source="oanda",
            raw_data={
                "open": mid.get("o"),
                "high": mid.get("h"),
                "low": mid.get("l"),
                "close": mid.get("c"),
                "volume": candle.get("volume"),
                "complete": candle.get("complete")
            }
        )
    except Exception as e:
        logger.error(f"Failed to parse candle: {e}")
        return None


def fetch_eurusd_rate() -> Optional[EURUSDSnapshot]:
    """
    Fetch the latest EUR/USD closing price.
    
    Returns:
        EURUSDSnapshot with rate data or None on error.
    """
    logger.info("Fetching EUR/USD rate from Oanda...")
    
    candles = _fetch_eurusd_candles(count=5, granularity="D")
    
    if not candles:
        logger.error("Failed to fetch EUR/USD candles from Oanda")
        return None
    
    completed_candles = [c for c in candles if c.get("complete", False)]
    
    if not completed_candles:
        logger.warning("No completed daily candles available")
        if candles:
            completed_candles = candles[:-1]
    
    if not completed_candles:
        logger.error("No usable candle data")
        return None
    
    latest_candle = completed_candles[-1]
    snapshot = _parse_candle_to_snapshot(latest_candle)
    
    if snapshot:
        logger.info(f"EUR/USD rate for {snapshot.date}: {snapshot.rate:.6f}")
    
    return snapshot


def save_eurusd_snapshot(snapshot: EURUSDSnapshot) -> bool:
    """
    Save EUR/USD rate snapshot to database.
    
    Uses ON CONFLICT to update if entry for date already exists.
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
                json.dumps(snapshot.raw_data)
            ))
        logger.info(f"Saved EUR/USD snapshot for {snapshot.date}: {snapshot.rate:.6f}")
        return True
    except Exception as e:
        logger.error(f"Failed to save EUR/USD snapshot: {e}")
        return False


def capture_eurusd_snapshot() -> Dict[str, Any]:
    """
    Main entry point: Fetch and store EUR/USD exchange rate.
    
    Tries daily candle close first. If unavailable (incomplete), falls back
    to the last 4H candle closing price for the target date.
    
    Returns:
        Dict with status and data about the operation.
    """
    target_date = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
    target_date_obj = date.fromisoformat(target_date)
    
    existing = execute_one(
        "SELECT id FROM eurusd_snapshots WHERE date = %s",
        (target_date,)
    )
    if existing:
        logger.info(f"EUR/USD snapshot already exists for {target_date}")
        return {
            "status": "skipped",
            "message": f"Snapshot already exists for {target_date}",
            "date": target_date
        }
    
    snapshot = fetch_eurusd_rate()
    
    if snapshot and snapshot.date == target_date:
        success = save_eurusd_snapshot(snapshot)
        if success:
            return {
                "status": "success",
                "message": f"Captured EUR/USD rate for {snapshot.date}",
                "date": snapshot.date,
                "rate": snapshot.rate,
                "source": "daily_candle"
            }
    
    logger.info(f"Daily candle unavailable for {target_date}, trying 4H fallback...")
    fallback_snapshot = _get_last_4h_close_for_date(target_date_obj)
    
    if fallback_snapshot:
        success = save_eurusd_snapshot(fallback_snapshot)
        if success:
            return {
                "status": "success",
                "message": f"Captured EUR/USD rate for {fallback_snapshot.date} (4H fallback)",
                "date": fallback_snapshot.date,
                "rate": fallback_snapshot.rate,
                "source": "4h_fallback"
            }
    
    return {
        "status": "error",
        "message": f"Failed to fetch EUR/USD rate (daily and 4H fallback both failed)",
        "date": target_date
    }


def get_eurusd_for_date(target_date: date) -> Optional[Dict[str, Any]]:
    """Get EUR/USD snapshot for a specific date."""
    result = execute_one(
        """SELECT * FROM eurusd_snapshots WHERE date = %s""",
        (target_date,)
    )
    return dict(result) if result else None


def backfill_eurusd_history(days: int = 90) -> Dict[str, Any]:
    """
    Backfill EUR/USD history from Oanda.
    
    Uses daily candles with precise closing prices (6 decimal places).
    """
    logger.info(f"Backfilling EUR/USD history for {days} days from Oanda...")
    
    candles = _fetch_eurusd_candles(count=days + 5, granularity="D")
    
    if not candles:
        return {
            "status": "error",
            "message": "No historical EUR/USD data available from Oanda API"
        }
    
    completed_candles = [c for c in candles if c.get("complete", False)]
    
    saved = 0
    dates_saved = []
    
    try:
        with get_cursor() as cursor:
            for candle in completed_candles:
                snapshot = _parse_candle_to_snapshot(candle)
                if not snapshot:
                    continue
                
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
                    json.dumps(snapshot.raw_data)
                ))
                saved += 1
                dates_saved.append(snapshot.date)
        
        logger.info(f"Backfilled {saved} EUR/USD snapshots from Oanda")
        
        return {
            "status": "success",
            "message": f"Backfilled {saved} EUR/USD snapshots from Oanda",
            "days": saved,
            "date_range": f"{min(dates_saved)} to {max(dates_saved)}" if dates_saved else "N/A",
            "source": "oanda"
        }
        
    except Exception as e:
        logger.error(f"Failed to backfill EUR/USD history: {e}")
        return {
            "status": "error",
            "message": str(e)
        }


def backfill_eurusd_range(from_date: date, to_date: date) -> Dict[str, Any]:
    """
    Backfill EUR/USD history for a specific date range.
    
    Uses daily candles for completed days. For incomplete daily candles (current day),
    falls back to the last 4H candle closing price as an approximation.
    
    Args:
        from_date: Start date (inclusive)
        to_date: End date (inclusive)
    """
    logger.info(f"Backfilling EUR/USD from {from_date} to {to_date}...")
    
    candles = _fetch_eurusd_candles_range(from_date, to_date, granularity="D")
    
    if not candles:
        return {
            "status": "error",
            "message": f"No EUR/USD data available from Oanda for {from_date} to {to_date}"
        }
    
    completed_candles = [c for c in candles if c.get("complete", False)]
    incomplete_candles = [c for c in candles if not c.get("complete", False)]
    
    dates_with_data = set()
    for candle in completed_candles:
        time_str = candle.get("time", "")[:10]
        if time_str:
            dates_with_data.add(time_str)
    
    all_dates = set()
    current = from_date
    while current <= to_date:
        all_dates.add(current.isoformat())
        current += timedelta(days=1)
    
    missing_dates = all_dates - dates_with_data
    
    saved = 0
    saved_4h_fallback = 0
    dates_saved = []
    
    try:
        with get_cursor() as cursor:
            for candle in completed_candles:
                snapshot = _parse_candle_to_snapshot(candle)
                if not snapshot:
                    continue
                
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
                    json.dumps(snapshot.raw_data)
                ))
                saved += 1
                dates_saved.append(snapshot.date)
            
            for date_str in missing_dates:
                target = date.fromisoformat(date_str)
                logger.info(f"No daily candle for {date_str}, trying 4H fallback...")
                
                fallback_snapshot = _get_last_4h_close_for_date(target)
                if fallback_snapshot:
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
                        fallback_snapshot.date,
                        fallback_snapshot.rate,
                        fallback_snapshot.currency_pair,
                        fallback_snapshot.source,
                        json.dumps(fallback_snapshot.raw_data)
                    ))
                    saved_4h_fallback += 1
                    dates_saved.append(fallback_snapshot.date)
                    logger.info(f"Saved 4H fallback for {date_str}: {fallback_snapshot.rate:.6f}")
                else:
                    logger.warning(f"No 4H fallback available for {date_str}")
        
        total_saved = saved + saved_4h_fallback
        logger.info(f"Backfilled {total_saved} EUR/USD snapshots ({saved} daily, {saved_4h_fallback} via 4H fallback)")
        
        return {
            "status": "success",
            "message": f"Backfilled {total_saved} EUR/USD snapshots ({saved} daily, {saved_4h_fallback} via 4H fallback)",
            "days": total_saved,
            "daily_candles": saved,
            "fallback_4h": saved_4h_fallback,
            "date_range": f"{min(dates_saved)} to {max(dates_saved)}" if dates_saved else "N/A",
            "source": "oanda"
        }
        
    except Exception as e:
        logger.error(f"Failed to backfill EUR/USD history: {e}")
        return {
            "status": "error",
            "message": str(e)
        }
