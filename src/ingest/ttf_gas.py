"""
TTF Gas Price API Integration

Fetches Dutch TTF natural gas prices from OilPriceAPI.
Stores daily snapshots in ttf_gas_snapshots table.

TTF (Title Transfer Facility) is Europe's primary natural gas benchmark.
Prices are in EUR/MWh.

API Documentation: https://docs.oilpriceapi.com/
Commodity Code: DUTCH_TTF_EUR
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
TTF_COMMODITY_CODE = "DUTCH_TTF_EUR"


@dataclass
class TTFGasSnapshot:
    """Represents a daily TTF gas price snapshot."""
    date: str
    ttf_price: float
    currency: str
    unit: str
    source: str
    raw_data: Dict[str, Any]


def _fetch_ttf_latest() -> Optional[Dict[str, Any]]:
    """Fetch latest TTF gas price."""
    if not OIL_PRICE_API_KEY:
        logger.warning("OIL_PRICE_API_KEY not configured")
        return None
    
    url = f"{OIL_PRICE_API_BASE}/prices/latest"
    headers = {
        "Authorization": f"Token {OIL_PRICE_API_KEY}",
        "Content-Type": "application/json"
    }
    params = {"by_code": TTF_COMMODITY_CODE}
    
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
            logger.warning(f"No data returned for {TTF_COMMODITY_CODE}")
            return None
        
        return data["data"]
        
    except requests.exceptions.RequestException as e:
        logger.error(f"OilPriceAPI request failed for TTF: {e}")
        return None


def _fetch_ttf_history(days: int = 30) -> List[Dict[str, Any]]:
    """Fetch TTF gas price history."""
    if not OIL_PRICE_API_KEY:
        logger.warning("OIL_PRICE_API_KEY not configured")
        return []
    
    url = f"{OIL_PRICE_API_BASE}/prices/past_week"
    headers = {
        "Authorization": f"Token {OIL_PRICE_API_KEY}",
        "Content-Type": "application/json"
    }
    params = {"by_code": TTF_COMMODITY_CODE}
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        
        if response.status_code != 200:
            logger.error(f"OilPriceAPI history returned {response.status_code}")
            return []
        
        data = response.json()
        if data.get("status") != "success":
            return []
        
        return data.get("data", {}).get("prices", [])
        
    except requests.exceptions.RequestException as e:
        logger.error(f"OilPriceAPI history request failed: {e}")
        return []


def fetch_ttf_gas_price() -> Optional[TTFGasSnapshot]:
    """
    Fetch current TTF gas price.
    
    Returns:
        TTFGasSnapshot with price data or None on error.
    """
    logger.info("Fetching TTF gas price from OilPriceAPI...")
    
    ttf_data = _fetch_ttf_latest()
    
    if not ttf_data:
        logger.error("Failed to fetch TTF gas price")
        return None
    
    ttf_price = float(ttf_data.get("price", 0))
    
    yesterday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
    snapshot = TTFGasSnapshot(
        date=yesterday,
        ttf_price=ttf_price,
        currency=ttf_data.get("currency", "EUR"),
        unit=ttf_data.get("unit", "EUR/MWh"),
        source="oilpriceapi",
        raw_data=ttf_data
    )
    
    logger.info(f"TTF Gas price: {ttf_price:.2f} EUR/MWh")
    
    return snapshot


def save_ttf_gas_snapshot(snapshot: TTFGasSnapshot) -> bool:
    """
    Save TTF gas price snapshot to database.
    
    Uses ON CONFLICT to update if entry for date already exists.
    """
    try:
        with get_cursor() as cursor:
            cursor.execute("""
                INSERT INTO ttf_gas_snapshots 
                (date, ttf_price, currency, unit, source, raw_data)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (date) DO UPDATE SET
                    ttf_price = EXCLUDED.ttf_price,
                    currency = EXCLUDED.currency,
                    unit = EXCLUDED.unit,
                    source = EXCLUDED.source,
                    raw_data = EXCLUDED.raw_data
            """, (
                snapshot.date,
                snapshot.ttf_price,
                snapshot.currency,
                snapshot.unit,
                snapshot.source,
                json.dumps(snapshot.raw_data)
            ))
        logger.info(f"Saved TTF gas snapshot for {snapshot.date}")
        return True
    except Exception as e:
        logger.error(f"Failed to save TTF gas snapshot: {e}")
        return False


def capture_ttf_gas_snapshot() -> Dict[str, Any]:
    """
    Main entry point: Fetch and store TTF gas price.
    
    Returns:
        Dict with status and data about the operation.
    """
    target_date = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    existing = execute_one(
        "SELECT id FROM ttf_gas_snapshots WHERE date = %s",
        (target_date,)
    )
    if existing:
        logger.info(f"TTF gas snapshot already exists for {target_date}")
        return {
            "status": "skipped",
            "message": f"Snapshot already exists for {target_date}",
            "date": target_date
        }
    
    snapshot = fetch_ttf_gas_price()
    if not snapshot:
        return {
            "status": "error",
            "message": "Failed to fetch TTF gas price from API",
            "date": target_date
        }
    
    success = save_ttf_gas_snapshot(snapshot)
    
    if success:
        return {
            "status": "success",
            "message": f"Captured TTF gas price for {target_date}",
            "date": target_date,
            "ttf_price": snapshot.ttf_price,
            "unit": snapshot.unit
        }
    else:
        return {
            "status": "error", 
            "message": "Failed to save snapshot to database",
            "date": target_date
        }


def get_ttf_gas_for_date(target_date: date) -> Optional[Dict[str, Any]]:
    """Get TTF gas snapshot for a specific date."""
    result = execute_one(
        """SELECT * FROM ttf_gas_snapshots WHERE date = %s""",
        (target_date,)
    )
    return dict(result) if result else None
