"""
Backfill script for gas_storage_snapshots and oil_price_snapshots tables.

Fetches historical data from GIE AGSI+ and OilPriceAPI for the specified date range.

Usage:
    python -m src.scripts.backfill_snapshots --days 15
    python -m src.scripts.backfill_snapshots --start 2026-01-14 --end 2026-01-28
"""

import os
import sys
import json
import logging
import argparse
import requests
import time
from datetime import datetime, date, timedelta
from typing import Dict, Any, Optional, List

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

GIE_API_BASE = "https://agsi.gie.eu/api"
GIE_API_KEY = os.environ.get("GIE_API_KEY", "")

OIL_PRICE_API_BASE = "https://api.oilpriceapi.com/v1"
OIL_PRICE_API_KEY = os.environ.get("OIL_PRICE_API_KEY", "")

SEASONAL_NORMS = {
    1: 65.0, 2: 50.0, 3: 40.0, 4: 45.0, 5: 55.0, 6: 65.0,
    7: 75.0, 8: 82.0, 9: 88.0, 10: 92.0, 11: 90.0, 12: 80.0
}


def get_db_connection():
    """Get database connection."""
    import psycopg2
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set")
    return psycopg2.connect(database_url)


def fetch_gas_storage_for_date(target_date: str) -> Optional[Dict[str, Any]]:
    """Fetch EU gas storage data for a specific date from GIE AGSI+."""
    if not GIE_API_KEY:
        logger.warning("GIE_API_KEY not configured")
        return None
    
    url = f"{GIE_API_BASE}/eu"
    headers = {"x-key": GIE_API_KEY, "Accept": "application/json"}
    params = {"date": target_date}
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        if not data or "data" not in data or not data["data"]:
            logger.warning(f"No gas storage data for {target_date}")
            return None
        
        entry = data["data"][0]
        return {
            "date": entry.get("gasDayStart", target_date),
            "gas_in_storage_twh": float(entry.get("gasInStorage", 0) or 0),
            "full_percent": float(entry.get("full", 0) or 0),
            "injection_twh": float(entry.get("injection", 0) or 0),
            "withdrawal_twh": float(entry.get("withdrawal", 0) or 0),
            "working_gas_volume_twh": float(entry.get("workingGasVolume", 0) or 0),
            "trend": float(entry.get("trend", 0) or 0),
            "consumption_twh": float(entry.get("consumption", 0) or 0),
        }
    except Exception as e:
        logger.error(f"Failed to fetch gas storage for {target_date}: {e}")
        return None


def compute_gas_metrics(data: Dict, month: int) -> Dict[str, Any]:
    """Compute risk metrics from gas storage data."""
    eu_storage_percent = data.get("full_percent", 0)
    seasonal_norm = SEASONAL_NORMS.get(month, 70.0)
    deviation = eu_storage_percent - seasonal_norm
    
    is_winter = month in [11, 12, 1, 2, 3]
    winter_risk = "LOW"
    if is_winter:
        if eu_storage_percent < 45:
            winter_risk = "CRITICAL"
        elif eu_storage_percent < 55:
            winter_risk = "ELEVATED"
        elif eu_storage_percent < 65:
            winter_risk = "MODERATE"
    
    base_risk = max(0, 100 - eu_storage_percent)
    deviation_factor = min(30, abs(deviation) * 1.5) if deviation < 0 else (-10 if deviation > 15 else 0)
    seasonal_factor = 15 if is_winter else 0
    risk_score = max(0, min(100, int(base_risk * 0.5 + deviation_factor + seasonal_factor)))
    
    if risk_score <= 25:
        risk_band = "LOW"
    elif risk_score <= 50:
        risk_band = "MODERATE"
    elif risk_score <= 75:
        risk_band = "ELEVATED"
    else:
        risk_band = "CRITICAL"
    
    interpretation = f"EU gas storage at {eu_storage_percent:.1f}%, "
    if deviation >= 10:
        interpretation += f"{abs(deviation):.0f}% above seasonal average."
    elif deviation <= -10:
        interpretation += f"{abs(deviation):.0f}% below seasonal average."
    else:
        interpretation += "near seasonal average."
    
    return {
        "eu_storage_percent": round(eu_storage_percent, 1),
        "seasonal_norm": seasonal_norm,
        "deviation_from_norm": round(deviation, 1),
        "refill_speed_7d": round(data.get("injection_twh", 0), 2),
        "withdrawal_rate_7d": round(data.get("withdrawal_twh", 0), 2),
        "winter_deviation_risk": winter_risk,
        "days_to_target": None,
        "risk_score": risk_score,
        "risk_band": risk_band,
        "interpretation": interpretation,
        "raw_data": data
    }


def save_gas_storage_snapshot(conn, target_date: str, metrics: Dict) -> bool:
    """Save gas storage snapshot to database."""
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO gas_storage_snapshots 
                (date, eu_storage_percent, seasonal_norm, deviation_from_norm,
                 refill_speed_7d, withdrawal_rate_7d, winter_deviation_risk,
                 days_to_target, risk_score, risk_band, interpretation, raw_data)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (date) DO UPDATE SET
                    eu_storage_percent = EXCLUDED.eu_storage_percent,
                    seasonal_norm = EXCLUDED.seasonal_norm,
                    deviation_from_norm = EXCLUDED.deviation_from_norm,
                    refill_speed_7d = EXCLUDED.refill_speed_7d,
                    withdrawal_rate_7d = EXCLUDED.withdrawal_rate_7d,
                    winter_deviation_risk = EXCLUDED.winter_deviation_risk,
                    days_to_target = EXCLUDED.days_to_target,
                    risk_score = EXCLUDED.risk_score,
                    risk_band = EXCLUDED.risk_band,
                    interpretation = EXCLUDED.interpretation,
                    raw_data = EXCLUDED.raw_data
            """, (
                target_date,
                metrics["eu_storage_percent"],
                metrics["seasonal_norm"],
                metrics["deviation_from_norm"],
                metrics["refill_speed_7d"],
                metrics["withdrawal_rate_7d"],
                metrics["winter_deviation_risk"],
                metrics["days_to_target"],
                metrics["risk_score"],
                metrics["risk_band"],
                metrics["interpretation"],
                json.dumps(metrics["raw_data"])
            ))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to save gas storage: {e}")
        conn.rollback()
        return False


def fetch_oil_prices_for_date(target_date: str) -> Optional[Dict[str, Any]]:
    """Fetch Brent and WTI oil prices for a specific date."""
    if not OIL_PRICE_API_KEY:
        logger.warning("OIL_PRICE_API_KEY not configured")
        return None
    
    dt = datetime.strptime(target_date, "%Y-%m-%d")
    from_ts = int(dt.replace(hour=0, minute=0, second=0).timestamp())
    to_ts = int(dt.replace(hour=23, minute=59, second=59).timestamp())
    
    headers = {
        "Authorization": f"Token {OIL_PRICE_API_KEY}",
        "Content-Type": "application/json"
    }
    
    result = {"date": target_date}
    
    for code, name in [("BRENT_CRUDE_USD", "brent"), ("WTI_USD", "wti")]:
        try:
            url = f"{OIL_PRICE_API_BASE}/prices"
            params = {
                "by_code": code,
                "by_period[from]": from_ts,
                "by_period[to]": to_ts
            }
            
            response = requests.get(url, headers=headers, params=params, timeout=30)
            
            if response.status_code != 200:
                logger.warning(f"OilPriceAPI returned {response.status_code} for {code} on {target_date}")
                result[f"{name}_price"] = None
                result[f"{name}_raw"] = None
                continue
            
            data = response.json()
            
            if data.get("status") == "success" and data.get("data"):
                data_obj = data["data"]
                prices = data_obj.get("prices", []) if isinstance(data_obj, dict) else data_obj
                
                if isinstance(prices, list) and len(prices) > 0:
                    price_entry = prices[-1]
                    result[f"{name}_price"] = float(price_entry.get("price", 0))
                    result[f"{name}_raw"] = price_entry
                elif isinstance(data_obj, dict) and data_obj.get("price"):
                    result[f"{name}_price"] = float(data_obj.get("price", 0))
                    result[f"{name}_raw"] = data_obj
                else:
                    result[f"{name}_price"] = None
                    result[f"{name}_raw"] = None
            else:
                result[f"{name}_price"] = None
                result[f"{name}_raw"] = None
                
        except Exception as e:
            logger.error(f"Failed to fetch {code} for {target_date}: {e}")
            result[f"{name}_price"] = None
            result[f"{name}_raw"] = None
    
    if result.get("brent_price") is None and result.get("wti_price") is None:
        return None
    
    brent = result.get("brent_price", 0) or 0
    wti = result.get("wti_price", 0) or 0
    result["brent_wti_spread"] = brent - wti if brent and wti else 0
    
    return result


def save_oil_price_snapshot(conn, data: Dict) -> bool:
    """Save oil price snapshot to database."""
    try:
        raw_data = {
            "brent": data.get("brent_raw"),
            "wti": data.get("wti_raw")
        }
        
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO oil_price_snapshots 
                (date, brent_price, brent_change_24h, brent_change_pct,
                 wti_price, wti_change_24h, wti_change_pct,
                 brent_wti_spread, source, raw_data)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (date) DO UPDATE SET
                    brent_price = EXCLUDED.brent_price,
                    wti_price = EXCLUDED.wti_price,
                    brent_wti_spread = EXCLUDED.brent_wti_spread,
                    raw_data = EXCLUDED.raw_data
            """, (
                data["date"],
                data.get("brent_price"),
                0,
                0,
                data.get("wti_price"),
                0,
                0,
                data.get("brent_wti_spread", 0),
                "oilpriceapi_backfill",
                json.dumps(raw_data)
            ))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to save oil price: {e}")
        conn.rollback()
        return False


def backfill_date_range(start_date: date, end_date: date) -> Dict[str, Any]:
    """Backfill both tables for the given date range."""
    conn = get_db_connection()
    
    results = {
        "gas_storage": {"success": 0, "failed": 0, "skipped": 0},
        "oil_price": {"success": 0, "failed": 0, "skipped": 0},
        "dates_processed": []
    }
    
    current_date = start_date
    while current_date <= end_date:
        date_str = current_date.strftime("%Y-%m-%d")
        logger.info(f"Processing {date_str}...")
        results["dates_processed"].append(date_str)
        
        gas_data = fetch_gas_storage_for_date(date_str)
        if gas_data:
            month = current_date.month
            metrics = compute_gas_metrics(gas_data, month)
            if save_gas_storage_snapshot(conn, date_str, metrics):
                logger.info(f"  Gas storage: {metrics['eu_storage_percent']}% ({metrics['risk_band']})")
                results["gas_storage"]["success"] += 1
            else:
                results["gas_storage"]["failed"] += 1
        else:
            logger.warning(f"  Gas storage: No data available")
            results["gas_storage"]["skipped"] += 1
        
        oil_data = fetch_oil_prices_for_date(date_str)
        if oil_data:
            if save_oil_price_snapshot(conn, oil_data):
                brent = oil_data.get("brent_price", "N/A")
                wti = oil_data.get("wti_price", "N/A")
                logger.info(f"  Oil price: Brent ${brent}, WTI ${wti}")
                results["oil_price"]["success"] += 1
            else:
                results["oil_price"]["failed"] += 1
        else:
            logger.warning(f"  Oil price: No data available")
            results["oil_price"]["skipped"] += 1
        
        time.sleep(0.5)
        current_date += timedelta(days=1)
    
    conn.close()
    return results


def backfill_egsi_indices(start_date: date, end_date: date) -> Dict[str, Any]:
    """
    Backfill EGSI-M and EGSI-S indices for a date range.
    
    EGSI-M requires: EERI data + alert events
    EGSI-S requires: gas storage data + TTF prices + alert events
    
    Returns:
        Dict with status and counts for each index.
    """
    from src.egsi.service import compute_egsi_m_for_date
    from src.egsi.service_egsi_s import compute_egsi_s_for_date
    
    results = {
        "egsi_m": {"success": 0, "failed": 0, "skipped": 0},
        "egsi_s": {"success": 0, "failed": 0, "skipped": 0},
        "dates_processed": []
    }
    
    current = start_date
    while current <= end_date:
        logger.info(f"Backfilling EGSI indices for {current}...")
        results["dates_processed"].append(str(current))
        
        try:
            m_result = compute_egsi_m_for_date(current, save=True, force=True)
            if m_result:
                results["egsi_m"]["success"] += 1
                logger.info(f"  EGSI-M: {m_result.value:.1f} ({m_result.band.value})")
            else:
                results["egsi_m"]["skipped"] += 1
                logger.info(f"  EGSI-M: skipped (no data or disabled)")
        except Exception as e:
            results["egsi_m"]["failed"] += 1
            logger.error(f"  EGSI-M failed: {e}")
        
        try:
            s_result = compute_egsi_s_for_date(current, save=True, force=True)
            if s_result:
                results["egsi_s"]["success"] += 1
                logger.info(f"  EGSI-S: {s_result.value:.1f} ({s_result.band.value})")
            else:
                results["egsi_s"]["skipped"] += 1
                logger.info(f"  EGSI-S: skipped (no data or disabled)")
        except Exception as e:
            results["egsi_s"]["failed"] += 1
            logger.error(f"  EGSI-S failed: {e}")
        
        current += timedelta(days=1)
    
    return results


def calculate_oil_price_changes() -> Dict[str, Any]:
    """
    Calculate 24h changes for oil price snapshots by comparing consecutive days.
    Updates existing records in the database.
    
    Returns:
        Dict with status and count of updated records.
    """
    conn = get_db_connection()
    updated_count = 0
    
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT date, brent_price, wti_price 
                FROM oil_price_snapshots 
                WHERE brent_price IS NOT NULL AND brent_price > 0
                ORDER BY date ASC
            """)
            rows = cursor.fetchall()
        
        if len(rows) < 2:
            logger.warning("Not enough data to calculate changes (need at least 2 days)")
            return {"status": "skipped", "message": "Not enough data", "updated": 0}
        
        previous = None
        for row in rows:
            current_date, brent_price, wti_price = row
            
            if previous is not None:
                prev_date, prev_brent, prev_wti = previous
                
                brent_change = brent_price - prev_brent if prev_brent else 0
                brent_pct = (brent_change / prev_brent * 100) if prev_brent else 0
                
                wti_change = wti_price - prev_wti if prev_wti else 0
                wti_pct = (wti_change / prev_wti * 100) if prev_wti else 0
                
                with conn.cursor() as cursor:
                    cursor.execute("""
                        UPDATE oil_price_snapshots 
                        SET brent_change_24h = %s,
                            brent_change_pct = %s,
                            wti_change_24h = %s,
                            wti_change_pct = %s
                        WHERE date = %s
                    """, (
                        round(brent_change, 2),
                        round(brent_pct, 2),
                        round(wti_change, 2),
                        round(wti_pct, 2),
                        current_date
                    ))
                conn.commit()
                updated_count += 1
                
                logger.info(f"{current_date}: Brent {brent_change:+.2f} ({brent_pct:+.2f}%), WTI {wti_change:+.2f} ({wti_pct:+.2f}%)")
            
            previous = (current_date, brent_price, wti_price)
        
        conn.close()
        
        return {
            "status": "success",
            "message": f"Updated {updated_count} records with 24h changes",
            "updated": updated_count
        }
        
    except Exception as e:
        logger.error(f"Failed to calculate changes: {e}")
        conn.close()
        return {"status": "error", "message": str(e), "updated": 0}


def main():
    parser = argparse.ArgumentParser(description="Backfill gas storage and oil price snapshots")
    parser.add_argument("--days", type=int, default=15, help="Number of days to backfill")
    parser.add_argument("--start", type=str, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, help="End date (YYYY-MM-DD)")
    parser.add_argument("--calculate-changes", action="store_true", help="Calculate 24h changes for existing data")
    
    args = parser.parse_args()
    
    if args.calculate_changes:
        logger.info("Calculating 24h changes for oil price snapshots...")
        result = calculate_oil_price_changes()
        print("\n" + "="*50)
        print("CALCULATE CHANGES RESULTS")
        print("="*50)
        print(f"Status: {result['status']}")
        print(f"Message: {result['message']}")
        print(f"Updated: {result['updated']} records")
        print("="*50)
        return result
    
    if args.start and args.end:
        start_date = datetime.strptime(args.start, "%Y-%m-%d").date()
        end_date = datetime.strptime(args.end, "%Y-%m-%d").date()
    else:
        end_date = date.today() - timedelta(days=1)
        start_date = end_date - timedelta(days=args.days - 1)
    
    logger.info(f"Backfilling data from {start_date} to {end_date}")
    logger.info(f"GIE API Key: {'configured' if GIE_API_KEY else 'NOT SET'}")
    logger.info(f"OilPrice API Key: {'configured' if OIL_PRICE_API_KEY else 'NOT SET'}")
    
    results = backfill_date_range(start_date, end_date)
    
    print("\n" + "="*50)
    print("BACKFILL RESULTS")
    print("="*50)
    print(f"\nGas Storage Snapshots:")
    print(f"  Success: {results['gas_storage']['success']}")
    print(f"  Failed:  {results['gas_storage']['failed']}")
    print(f"  Skipped: {results['gas_storage']['skipped']}")
    print(f"\nOil Price Snapshots:")
    print(f"  Success: {results['oil_price']['success']}")
    print(f"  Failed:  {results['oil_price']['failed']}")
    print(f"  Skipped: {results['oil_price']['skipped']}")
    print(f"\nDates: {start_date} to {end_date}")
    print("="*50)
    
    return results


if __name__ == "__main__":
    main()
