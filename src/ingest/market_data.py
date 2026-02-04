"""
Market Data Collection Module

Fetches VIX (Volatility Index) data from Yahoo Finance using yfinance library.
Data is stored in vix_snapshots table.

Note: Freight (BDI/Baltic Dry Index) requires paid subscription to Baltic Exchange.
Freight functions are disabled and return "unavailable" status.
"""

import logging
from datetime import datetime, date, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

import yfinance as yf
import pandas as pd

from src.db.db import get_cursor, execute_one

logger = logging.getLogger(__name__)


@dataclass
class VIXSnapshot:
    """Represents a daily VIX snapshot."""
    date: str
    vix_close: float
    vix_open: float
    vix_high: float
    vix_low: float
    source: str = "yfinance"


@dataclass 
class FreightSnapshot:
    """Represents a daily Baltic Dry Index snapshot."""
    date: str
    bdi_close: float
    bdi_open: float
    bdi_high: float
    bdi_low: float
    source: str = "yfinance"


def fetch_vix_data(days: int = 30) -> List[VIXSnapshot]:
    """
    Fetch VIX data from Yahoo Finance.
    
    Args:
        days: Number of days of history to fetch (default 30)
        
    Returns:
        List of VIXSnapshot objects
    """
    logger.info(f"Fetching VIX data for last {days} days...")
    
    try:
        vix = yf.Ticker("^VIX")
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days + 5)
        
        hist = vix.history(start=start_date, end=end_date)
        
        if hist.empty:
            logger.warning("No VIX data returned from yfinance")
            return []
        
        snapshots = []
        for idx, row in hist.iterrows():
            date_str = pd.Timestamp(idx).strftime("%Y-%m-%d")
            snapshots.append(VIXSnapshot(
                date=date_str,
                vix_close=float(row.get('Close') or 0),
                vix_open=float(row.get('Open') or 0),
                vix_high=float(row.get('High') or 0),
                vix_low=float(row.get('Low') or 0)
            ))
        
        logger.info(f"Fetched {len(snapshots)} VIX data points")
        return snapshots
        
    except Exception as e:
        logger.error(f"Failed to fetch VIX data: {e}")
        return []


def fetch_freight_data(days: int = 30) -> List[FreightSnapshot]:
    """
    DISABLED: Baltic Dry Index (BDI) requires paid subscription to Baltic Exchange.
    
    This function is a no-op stub that returns an empty list.
    To enable, obtain subscription from https://www.balticexchange.com/
    """
    logger.warning("Freight (BDI) data unavailable - requires paid Baltic Exchange subscription (~$500+/month)")
    return []


def save_vix_snapshots(snapshots: List[VIXSnapshot]) -> int:
    """
    Save VIX snapshots to database.
    
    Uses ON CONFLICT to update if entry for date already exists.
    
    Returns:
        Number of snapshots saved/updated
    """
    if not snapshots:
        return 0
    
    saved = 0
    try:
        with get_cursor() as cursor:
            for snapshot in snapshots:
                cursor.execute("""
                    INSERT INTO vix_snapshots 
                    (date, vix_close, vix_open, vix_high, vix_low, source)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (date) DO UPDATE SET
                        vix_close = EXCLUDED.vix_close,
                        vix_open = EXCLUDED.vix_open,
                        vix_high = EXCLUDED.vix_high,
                        vix_low = EXCLUDED.vix_low,
                        source = EXCLUDED.source
                """, (
                    snapshot.date,
                    snapshot.vix_close,
                    snapshot.vix_open,
                    snapshot.vix_high,
                    snapshot.vix_low,
                    snapshot.source
                ))
                saved += 1
        logger.info(f"Saved {saved} VIX snapshots")
    except Exception as e:
        logger.error(f"Failed to save VIX snapshots: {e}")
    
    return saved


def save_freight_snapshots(snapshots: List[FreightSnapshot]) -> int:
    """
    DISABLED: Baltic Dry Index (BDI) requires paid subscription.
    This function is a no-op stub that returns 0.
    """
    logger.warning("Freight saving disabled - requires paid subscription")
    return 0


def capture_vix_snapshot() -> Dict[str, Any]:
    """
    Main entry point: Fetch and store VIX data.
    
    Returns:
        Dict with status and data about the operation.
    """
    snapshots = fetch_vix_data(days=7)
    
    if not snapshots:
        return {
            "status": "error",
            "message": "Failed to fetch VIX data from Yahoo Finance"
        }
    
    saved = save_vix_snapshots(snapshots)
    latest = snapshots[-1] if snapshots else None
    
    return {
        "status": "success",
        "message": f"Captured {saved} VIX snapshots",
        "latest_date": latest.date if latest else None,
        "latest_value": latest.vix_close if latest else None,
        "count": saved
    }


def capture_freight_snapshot() -> Dict[str, Any]:
    """
    DISABLED: Baltic Dry Index (BDI) requires paid subscription.
    
    Returns unavailable status - no data collection performed.
    To enable, obtain subscription from https://www.balticexchange.com/
    """
    return {
        "status": "unavailable",
        "message": "Freight (BDI) requires paid Baltic Exchange subscription (~$500+/month)",
        "note": "Contact https://www.balticexchange.com/ for access"
    }


def capture_all_market_data() -> Dict[str, Any]:
    """
    Capture all available market data (VIX only).
    
    Note: Freight (BDI) requires paid Baltic Exchange subscription - not collected.
    
    Returns:
        Dict with status for each data source.
    """
    results = {
        "vix": capture_vix_snapshot()
    }
    
    success_count = sum(1 for r in results.values() if r.get("status") == "success")
    
    return {
        "status": "success" if success_count > 0 else "error",
        "message": f"Captured {success_count}/1 market data sources",
        "results": results,
        "note": "Freight (BDI) requires paid subscription - not collected"
    }


def get_vix_for_date(target_date: date) -> Optional[Dict[str, Any]]:
    """Get VIX snapshot for a specific date."""
    result = execute_one(
        """SELECT * FROM vix_snapshots WHERE date = %s""",
        (target_date,)
    )
    return dict(result) if result else None


def get_freight_for_date(target_date: date) -> Optional[Dict[str, Any]]:
    """Get freight (BDI) snapshot for a specific date."""
    result = execute_one(
        """SELECT * FROM freight_snapshots WHERE date = %s""",
        (target_date,)
    )
    return dict(result) if result else None
