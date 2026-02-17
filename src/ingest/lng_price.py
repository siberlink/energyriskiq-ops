"""
LNG Price API Integration

Fetches JKM (Japan/Korea Marker) LNG prices from OilPriceAPI.
Stores daily snapshots in lng_price_snapshots table for future index calculations.

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
class LngPriceSnapshot:
    """Represents a daily LNG price snapshot."""
    date: str
    jkm_price: float
    jkm_change_24h: float
    jkm_change_pct: float
    source: str
    raw_data: Dict[str, Any]


def _fetch_lng_price() -> Optional[Dict[str, Any]]:
    """Fetch latest JKM LNG price from OilPriceAPI."""
    if not OIL_PRICE_API_KEY:
        logger.warning("OIL_PRICE_API_KEY not configured")
        return None

    url = f"{OIL_PRICE_API_BASE}/prices/latest"
    headers = {
        "Authorization": f"Token {OIL_PRICE_API_KEY}",
        "Content-Type": "application/json"
    }
    params = {"by_code": "JKM_LNG_USD"}

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
            logger.warning("No data returned for JKM_LNG_USD")
            return None

        return data["data"]

    except requests.exceptions.RequestException as e:
        logger.error(f"OilPriceAPI request failed for JKM_LNG_USD: {e}")
        return None


def fetch_lng_prices() -> Optional[LngPriceSnapshot]:
    """
    Fetch current JKM LNG price.

    Returns:
        LngPriceSnapshot with JKM price or None on error.
    """
    logger.info("Fetching LNG prices from OilPriceAPI...")

    jkm_data = _fetch_lng_price()

    if not jkm_data:
        logger.error("Failed to fetch JKM LNG price")
        return None

    jkm_price = float(jkm_data.get("price", 0))
    jkm_changes = jkm_data.get("changes", {}).get("24h", {}) if jkm_data else {}

    yesterday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
    snapshot = LngPriceSnapshot(
        date=yesterday,
        jkm_price=jkm_price,
        jkm_change_24h=float(jkm_changes.get("amount", 0)),
        jkm_change_pct=float(jkm_changes.get("percent", 0)),
        source=jkm_data.get("source", "oilpriceapi"),
        raw_data={"jkm": jkm_data}
    )

    logger.info(f"LNG price: JKM ${jkm_price:.2f}")

    return snapshot


def save_lng_price_snapshot(snapshot: LngPriceSnapshot) -> bool:
    """
    Save LNG price snapshot to database.

    Uses ON CONFLICT to update if entry for date already exists.
    """
    try:
        with get_cursor() as cursor:
            cursor.execute("""
                INSERT INTO lng_price_snapshots
                (date, jkm_price, jkm_change_24h, jkm_change_pct,
                 source, raw_data)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (date) DO UPDATE SET
                    jkm_price = EXCLUDED.jkm_price,
                    jkm_change_24h = EXCLUDED.jkm_change_24h,
                    jkm_change_pct = EXCLUDED.jkm_change_pct,
                    source = EXCLUDED.source,
                    raw_data = EXCLUDED.raw_data
            """, (
                snapshot.date,
                snapshot.jkm_price,
                snapshot.jkm_change_24h,
                snapshot.jkm_change_pct,
                snapshot.source,
                json.dumps(snapshot.raw_data)
            ))
        logger.info(f"Saved LNG price snapshot for {snapshot.date}")
        return True
    except Exception as e:
        logger.error(f"Failed to save LNG price snapshot: {e}")
        return False


def get_lng_price_for_date(target_date: date) -> Optional[Dict[str, Any]]:
    """Get LNG price snapshot for a specific date."""
    result = execute_one(
        """SELECT * FROM lng_price_snapshots WHERE date = %s""",
        (target_date,)
    )
    return dict(result) if result else None


def capture_lng_price_snapshot() -> Dict[str, Any]:
    """
    Main entry point: Fetch and store yesterday's LNG prices.

    LNG prices are captured for the day that just ended (yesterday),
    since we're capturing end-of-day data.

    Returns:
        Dict with status and data about the operation.
    """
    target_date = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")

    existing = execute_one(
        "SELECT id FROM lng_price_snapshots WHERE date = %s",
        (target_date,)
    )
    if existing:
        logger.info(f"LNG price snapshot already exists for {target_date}")
        return {
            "status": "skipped",
            "message": f"Snapshot already exists for {target_date}",
            "date": target_date
        }

    snapshot = fetch_lng_prices()
    if not snapshot:
        return {
            "status": "error",
            "message": "Failed to fetch LNG prices from API",
            "date": target_date
        }

    success = save_lng_price_snapshot(snapshot)

    if success:
        return {
            "status": "success",
            "message": f"Captured LNG price snapshot for {target_date}",
            "date": target_date,
            "jkm_price": snapshot.jkm_price
        }
    else:
        return {
            "status": "error",
            "message": "Failed to save snapshot to database",
            "date": target_date
        }
