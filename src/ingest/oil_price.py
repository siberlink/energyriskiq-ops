"""
Oil Price API Integration

Fetches Brent Crude and WTI crude oil prices from OilPriceAPI.
Stores daily snapshots in oil_price_snapshots table for future index calculations.

API Documentation: https://docs.oilpriceapi.com/
"""

import os
import json
import logging
import requests
from datetime import datetime, date, timedelta
from typing import Dict, Any, Optional
from dataclasses import dataclass

from src.db.db import get_cursor, execute_one

logger = logging.getLogger(__name__)

OIL_PRICE_API_KEY = os.environ.get("OIL_PRICE_API_KEY", "")
OIL_PRICE_API_BASE = "https://api.oilpriceapi.com/v1"


@dataclass
class OilPriceSnapshot:
    """Represents a daily oil price snapshot."""
    date: str
    brent_price: float
    brent_change_24h: float
    brent_change_pct: float
    wti_price: float
    wti_change_24h: float
    wti_change_pct: float
    brent_wti_spread: float
    source: str
    raw_data: Dict[str, Any]


def _fetch_price(code: str) -> Optional[Dict[str, Any]]:
    """Fetch latest price for a specific oil code."""
    if not OIL_PRICE_API_KEY:
        logger.warning("OIL_PRICE_API_KEY not configured")
        return None
    
    url = f"{OIL_PRICE_API_BASE}/prices/latest"
    headers = {
        "Authorization": f"Token {OIL_PRICE_API_KEY}",
        "Content-Type": "application/json"
    }
    params = {"by_code": code}
    
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
            logger.warning(f"No data returned for {code}")
            return None
        
        return data["data"]
        
    except requests.exceptions.RequestException as e:
        logger.error(f"OilPriceAPI request failed for {code}: {e}")
        return None


def fetch_oil_prices() -> Optional[OilPriceSnapshot]:
    """
    Fetch current Brent and WTI crude oil prices.
    
    Returns:
        OilPriceSnapshot with both prices or None on error.
    """
    logger.info("Fetching oil prices from OilPriceAPI...")
    
    brent_data = _fetch_price("BRENT_CRUDE_USD")
    wti_data = _fetch_price("WTI_USD")
    
    if not brent_data and not wti_data:
        logger.error("Failed to fetch both Brent and WTI prices")
        return None
    
    brent_price = float(brent_data.get("price", 0)) if brent_data else 0
    wti_price = float(wti_data.get("price", 0)) if wti_data else 0
    
    brent_changes = brent_data.get("changes", {}).get("24h", {}) if brent_data else {}
    wti_changes = wti_data.get("changes", {}).get("24h", {}) if wti_data else {}
    
    snapshot = OilPriceSnapshot(
        date=datetime.utcnow().strftime("%Y-%m-%d"),
        brent_price=brent_price,
        brent_change_24h=float(brent_changes.get("amount", 0)),
        brent_change_pct=float(brent_changes.get("percent", 0)),
        wti_price=wti_price,
        wti_change_24h=float(wti_changes.get("amount", 0)),
        wti_change_pct=float(wti_changes.get("percent", 0)),
        brent_wti_spread=brent_price - wti_price if brent_price and wti_price else 0,
        source=brent_data.get("source", "oilpriceapi") if brent_data else "oilpriceapi",
        raw_data={
            "brent": brent_data,
            "wti": wti_data
        }
    )
    
    logger.info(f"Oil prices: Brent ${brent_price:.2f}, WTI ${wti_price:.2f}, Spread ${snapshot.brent_wti_spread:.2f}")
    
    return snapshot


def save_oil_price_snapshot(snapshot: OilPriceSnapshot) -> bool:
    """
    Save oil price snapshot to database.
    
    Uses ON CONFLICT to update if entry for date already exists.
    """
    try:
        with get_cursor() as cursor:
            cursor.execute("""
                INSERT INTO oil_price_snapshots 
                (date, brent_price, brent_change_24h, brent_change_pct,
                 wti_price, wti_change_24h, wti_change_pct,
                 brent_wti_spread, source, raw_data)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (date) DO UPDATE SET
                    brent_price = EXCLUDED.brent_price,
                    brent_change_24h = EXCLUDED.brent_change_24h,
                    brent_change_pct = EXCLUDED.brent_change_pct,
                    wti_price = EXCLUDED.wti_price,
                    wti_change_24h = EXCLUDED.wti_change_24h,
                    wti_change_pct = EXCLUDED.wti_change_pct,
                    brent_wti_spread = EXCLUDED.brent_wti_spread,
                    source = EXCLUDED.source,
                    raw_data = EXCLUDED.raw_data
            """, (
                snapshot.date,
                snapshot.brent_price,
                snapshot.brent_change_24h,
                snapshot.brent_change_pct,
                snapshot.wti_price,
                snapshot.wti_change_24h,
                snapshot.wti_change_pct,
                snapshot.brent_wti_spread,
                snapshot.source,
                json.dumps(snapshot.raw_data)
            ))
        logger.info(f"Saved oil price snapshot for {snapshot.date}")
        return True
    except Exception as e:
        logger.error(f"Failed to save oil price snapshot: {e}")
        return False


def get_oil_price_for_date(target_date: date) -> Optional[Dict[str, Any]]:
    """Get oil price snapshot for a specific date."""
    result = execute_one(
        """SELECT * FROM oil_price_snapshots WHERE date = %s""",
        (target_date,)
    )
    return dict(result) if result else None


def capture_oil_price_snapshot() -> Dict[str, Any]:
    """
    Main entry point: Fetch and store today's oil prices.
    
    Returns:
        Dict with status and data about the operation.
    """
    today = datetime.utcnow().strftime("%Y-%m-%d")
    
    existing = execute_one(
        "SELECT id FROM oil_price_snapshots WHERE date = %s",
        (today,)
    )
    if existing:
        logger.info(f"Oil price snapshot already exists for {today}")
        return {
            "status": "skipped",
            "message": f"Snapshot already exists for {today}",
            "date": today
        }
    
    snapshot = fetch_oil_prices()
    if not snapshot:
        return {
            "status": "error",
            "message": "Failed to fetch oil prices from API",
            "date": today
        }
    
    success = save_oil_price_snapshot(snapshot)
    
    if success:
        return {
            "status": "success",
            "message": f"Captured oil price snapshot for {today}",
            "date": today,
            "brent_price": snapshot.brent_price,
            "wti_price": snapshot.wti_price,
            "brent_wti_spread": snapshot.brent_wti_spread
        }
    else:
        return {
            "status": "error", 
            "message": "Failed to save snapshot to database",
            "date": today
        }
