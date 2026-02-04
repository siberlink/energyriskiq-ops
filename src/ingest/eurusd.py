"""
EUR/USD Currency Rate API Integration

Fetches EUR/USD exchange rates from OilPriceAPI.
Stores daily snapshots in eurusd_snapshots table for GERI calculations.

API Documentation: https://docs.oilpriceapi.com/
Commodity Code: EUR_USD
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

OIL_PRICE_API_KEY = os.environ.get("OIL_PRICE_API_KEY", "")
OIL_PRICE_API_BASE = "https://api.oilpriceapi.com/v1"
EURUSD_COMMODITY_CODE = "EUR_USD"


@dataclass
class EURUSDSnapshot:
    """Represents a daily EUR/USD exchange rate snapshot."""
    date: str
    rate: float
    currency_pair: str
    source: str
    raw_data: Dict[str, Any]


def _fetch_eurusd_latest() -> Optional[Dict[str, Any]]:
    """Fetch latest EUR/USD exchange rate."""
    if not OIL_PRICE_API_KEY:
        logger.warning("OIL_PRICE_API_KEY not configured")
        return None
    
    url = f"{OIL_PRICE_API_BASE}/prices/latest"
    headers = {
        "Authorization": f"Token {OIL_PRICE_API_KEY}",
        "Content-Type": "application/json"
    }
    params = {"by_code": EURUSD_COMMODITY_CODE}
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        
        if response.status_code == 401:
            logger.error("OilPriceAPI key is invalid or expired")
            return None
        
        if response.status_code != 200:
            logger.error(f"OilPriceAPI returned {response.status_code}: {response.text}")
            return None
        
        data = response.json()
        if data.get("status") != "success" or not data.get("data"):
            logger.warning(f"No data returned for {EURUSD_COMMODITY_CODE}")
            return None
        
        return data["data"]
        
    except requests.exceptions.RequestException as e:
        logger.error(f"OilPriceAPI request failed for EUR/USD: {e}")
        return None


def _fetch_eurusd_history(days: int = 90) -> List[Dict[str, Any]]:
    """
    Fetch EUR/USD exchange rate history.
    
    Supports multiple time ranges depending on API plan:
    - past_week: ~7 days (free tier)
    - past_month: ~30 days (Production Boost+)
    - past_year: ~365 days (Production Boost+)
    """
    if not OIL_PRICE_API_KEY:
        logger.warning("OIL_PRICE_API_KEY not configured")
        return []
    
    if days > 30:
        endpoint = "past_year"
    elif days > 7:
        endpoint = "past_month"
    else:
        endpoint = "past_week"
    
    url = f"{OIL_PRICE_API_BASE}/prices/{endpoint}"
    headers = {
        "Authorization": f"Token {OIL_PRICE_API_KEY}",
        "Content-Type": "application/json"
    }
    params = {"by_code": EURUSD_COMMODITY_CODE}
    
    logger.info(f"Fetching EUR/USD history from {endpoint} endpoint...")
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=60)
        
        if response.status_code == 403:
            logger.warning(f"API plan doesn't support {endpoint}, falling back to past_week")
            url = f"{OIL_PRICE_API_BASE}/prices/past_week"
            response = requests.get(url, headers=headers, params=params, timeout=30)
        
        if response.status_code != 200:
            logger.error(f"OilPriceAPI history returned {response.status_code}: {response.text[:200]}")
            return []
        
        data = response.json()
        if data.get("status") != "success":
            logger.error(f"OilPriceAPI returned status: {data.get('status')}")
            return []
        
        prices = data.get("data", {}).get("prices", [])
        logger.info(f"Fetched {len(prices)} EUR/USD rate records from {endpoint}")
        return prices
        
    except requests.exceptions.RequestException as e:
        logger.error(f"OilPriceAPI history request failed: {e}")
        return []


def fetch_eurusd_rate() -> Optional[EURUSDSnapshot]:
    """
    Fetch current EUR/USD exchange rate.
    
    Returns:
        EURUSDSnapshot with rate data or None on error.
    """
    logger.info("Fetching EUR/USD rate from OilPriceAPI...")
    
    eurusd_data = _fetch_eurusd_latest()
    
    if not eurusd_data:
        logger.error("Failed to fetch EUR/USD rate")
        return None
    
    rate = float(eurusd_data.get("price", 0))
    
    yesterday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
    snapshot = EURUSDSnapshot(
        date=yesterday,
        rate=rate,
        currency_pair="EUR/USD",
        source="oilpriceapi",
        raw_data=eurusd_data
    )
    
    logger.info(f"EUR/USD rate: {rate:.6f}")
    
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
        logger.info(f"Saved EUR/USD snapshot for {snapshot.date}")
        return True
    except Exception as e:
        logger.error(f"Failed to save EUR/USD snapshot: {e}")
        return False


def capture_eurusd_snapshot() -> Dict[str, Any]:
    """
    Main entry point: Fetch and store EUR/USD exchange rate.
    
    Returns:
        Dict with status and data about the operation.
    """
    target_date = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
    
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
    if not snapshot:
        return {
            "status": "error",
            "message": "Failed to fetch EUR/USD rate from API",
            "date": target_date
        }
    
    success = save_eurusd_snapshot(snapshot)
    
    if success:
        return {
            "status": "success",
            "message": f"Captured EUR/USD rate for {target_date}",
            "date": target_date,
            "rate": snapshot.rate
        }
    else:
        return {
            "status": "error", 
            "message": "Failed to save snapshot to database",
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
    Backfill EUR/USD history from OilPriceAPI.
    
    Uses past_year endpoint for paid API tiers (Production Boost+).
    Groups multiple intraday rates by date and takes the latest for each day.
    """
    logger.info(f"Fetching EUR/USD history for backfill ({days} days)...")
    
    history = _fetch_eurusd_history(days=days)
    
    if not history:
        return {
            "status": "error",
            "message": "No historical EUR/USD data available from API"
        }
    
    daily_rates = {}
    for record in history:
        created_at = record.get("created_at", "")
        if not created_at:
            continue
        
        record_date = created_at[:10]
        rate = float(record.get("price", 0))
        
        if record_date not in daily_rates or created_at > daily_rates[record_date]["created_at"]:
            daily_rates[record_date] = {
                "date": record_date,
                "rate": rate,
                "created_at": created_at,
                "raw_data": record
            }
    
    saved = 0
    try:
        with get_cursor() as cursor:
            for date_str, data in sorted(daily_rates.items()):
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
                    date_str,
                    data["rate"],
                    "EUR/USD",
                    "oilpriceapi",
                    json.dumps(data["raw_data"])
                ))
                saved += 1
        
        logger.info(f"Backfilled {saved} EUR/USD snapshots")
        
        return {
            "status": "success",
            "message": f"Backfilled {saved} EUR/USD snapshots",
            "days": saved,
            "date_range": f"{min(daily_rates.keys())} to {max(daily_rates.keys())}" if daily_rates else "N/A"
        }
        
    except Exception as e:
        logger.error(f"Failed to backfill EUR/USD history: {e}")
        return {
            "status": "error",
            "message": str(e)
        }
