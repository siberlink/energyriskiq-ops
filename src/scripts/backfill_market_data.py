#!/usr/bin/env python3
"""
Backfill Market Data Script

Collects historical VIX, TTF Gas, and other market data for the GERI chart overlays.
Run with: python -m src.scripts.backfill_market_data --days 90
"""

import argparse
import logging
import sys

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def backfill_vix(days: int) -> dict:
    """Backfill VIX data from Yahoo Finance."""
    from src.ingest.market_data import fetch_vix_data, save_vix_snapshots
    
    logger.info(f"Backfilling VIX data for last {days} days...")
    snapshots = fetch_vix_data(days=days)
    
    if not snapshots:
        return {"status": "error", "message": "No VIX data fetched"}
    
    saved = save_vix_snapshots(snapshots)
    return {
        "status": "success",
        "data_points": len(snapshots),
        "saved": saved,
        "date_range": f"{snapshots[0].date} to {snapshots[-1].date}" if snapshots else "N/A"
    }


def backfill_ttf(days: int) -> dict:
    """
    Capture current TTF Gas price from OilPriceAPI.
    
    Note: OilPriceAPI free tier only provides current price, not historical data.
    Historical TTF data requires paid subscription. This function captures
    the latest available price only.
    """
    from src.ingest.ttf_gas import capture_ttf_gas_snapshot
    
    logger.info("Capturing current TTF gas price (historical data requires paid API tier)...")
    result = capture_ttf_gas_snapshot()
    
    return {
        "status": result.get("status", "error"),
        "message": result.get("message", "Unknown error"),
        "date": result.get("date"),
        "price": result.get("ttf_price"),
        "note": "TTF historical backfill requires paid API tier - only current price captured"
    }


def main():
    parser = argparse.ArgumentParser(description="Backfill market data for GERI chart overlays")
    parser.add_argument("--days", type=int, default=90, help="Number of days of history to fetch")
    parser.add_argument("--vix", action="store_true", help="Backfill VIX data only")
    parser.add_argument("--ttf", action="store_true", help="Backfill TTF Gas data only")
    parser.add_argument("--all", action="store_true", help="Backfill all market data (default)")
    
    args = parser.parse_args()
    
    if not (args.vix or args.ttf):
        args.all = True
    
    results = {}
    
    if args.all or args.vix:
        results['vix'] = backfill_vix(args.days)
        logger.info(f"VIX: {results['vix']}")
    
    if args.all or args.ttf:
        results['ttf'] = backfill_ttf(args.days)
        logger.info(f"TTF: {results['ttf']}")
    
    print("\n=== Market Data Backfill Results ===")
    for key, value in results.items():
        print(f"\n{key.upper()}:")
        for k, v in value.items():
            print(f"  {k}: {v}")
    
    success_count = sum(1 for r in results.values() if r.get("status") == "success")
    print(f"\n{success_count}/{len(results)} data sources backfilled successfully")
    
    return 0 if success_count > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
