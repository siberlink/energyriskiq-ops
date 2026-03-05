"""
Intraday Price Capture — Hourly prices for Brent, WTI, Natural Gas (US)

Fetches live prices from OilPriceAPI every ~10 minutes (called by alerts_engine_v2).
Stores one row per commodity per hour in dedicated intraday tables.
Data is for the CURRENT UTC day only — at midnight UTC, old data is deleted.

Tables:
  - intraday_brent    (hour 0-23, price, captured_at)
  - intraday_wti      (hour 0-23, price, captured_at)
  - intraday_natgas   (hour 0-23, price, captured_at)

Used by GERI Live for real-time asset context.
"""

import os
import logging
import requests
from datetime import datetime, date
from typing import Dict, Any, Optional, List

from src.db.db import get_cursor, execute_query

logger = logging.getLogger(__name__)

OIL_PRICE_API_KEY = os.environ.get("OIL_PRICE_API_KEY", "")
OIL_PRICE_API_BASE = "https://api.oilpriceapi.com/v1"

ASSET_CONFIGS = {
    'brent': {
        'code': 'BRENT_CRUDE_USD',
        'table': 'intraday_brent',
        'label': 'Brent Crude',
        'unit': 'USD/barrel',
    },
    'wti': {
        'code': 'WTI_USD',
        'table': 'intraday_wti',
        'label': 'WTI Crude',
        'unit': 'USD/barrel',
    },
    'natgas': {
        'code': 'NATURAL_GAS_USD',
        'table': 'intraday_natgas',
        'label': 'Natural Gas (US)',
        'unit': 'USD/MMBtu',
    },
}


def run_intraday_migration():
    with get_cursor(commit=True) as cursor:
        for key, cfg in ASSET_CONFIGS.items():
            table = cfg['table']
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {table} (
                    id SERIAL PRIMARY KEY,
                    date DATE NOT NULL DEFAULT CURRENT_DATE,
                    hour INTEGER NOT NULL CHECK (hour >= 0 AND hour <= 23),
                    price NUMERIC(10,4) NOT NULL,
                    change_24h NUMERIC(10,4),
                    change_pct NUMERIC(8,4),
                    source VARCHAR(100) DEFAULT 'oilpriceapi',
                    captured_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    UNIQUE(date, hour)
                )
            """)
            cursor.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{table}_date ON {table}(date)
            """)
    logger.info("Intraday price tables migration complete")


def _fetch_latest_price(code: str) -> Optional[Dict[str, Any]]:
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
            logger.error(f"OilPriceAPI returned {response.status_code} for {code}: {response.text[:200]}")
            return None

        data = response.json()
        if data.get("status") != "success" or not data.get("data"):
            logger.warning(f"No data returned for {code}")
            return None

        return data["data"]

    except requests.exceptions.RequestException as e:
        logger.error(f"OilPriceAPI request failed for {code}: {e}")
        return None


def _cleanup_old_data(table: str, today: date):
    with get_cursor(commit=True) as cursor:
        cursor.execute(f"DELETE FROM {table} WHERE date < %s", (today,))


def _store_hourly_price(table: str, today: date, hour: int, price: float,
                        change_24h: Optional[float], change_pct: Optional[float],
                        source: str):
    with get_cursor(commit=True) as cursor:
        cursor.execute(f"""
            INSERT INTO {table} (date, hour, price, change_24h, change_pct, source, captured_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (date, hour) DO UPDATE SET
                price = EXCLUDED.price,
                change_24h = EXCLUDED.change_24h,
                change_pct = EXCLUDED.change_pct,
                source = EXCLUDED.source,
                captured_at = NOW()
        """, (today, hour, price, change_24h, change_pct, source))


def capture_intraday_prices() -> Dict[str, Any]:
    now_utc = datetime.utcnow()
    today = now_utc.date()
    current_hour = now_utc.hour

    results = {
        'date': today.isoformat(),
        'hour': current_hour,
        'captured_at': now_utc.isoformat(),
        'assets': {},
    }

    for key, cfg in ASSET_CONFIGS.items():
        table = cfg['table']

        _cleanup_old_data(table, today)

        price_data = _fetch_latest_price(cfg['code'])
        if not price_data:
            results['assets'][key] = {'status': 'failed', 'error': 'no data from API'}
            continue

        price = price_data.get('price')
        if price is None:
            results['assets'][key] = {'status': 'failed', 'error': 'price is null'}
            continue

        price = float(price)
        changes = price_data.get('changes', {}).get('24h', {})
        change_24h = changes.get('amount')
        change_pct = changes.get('percent')
        source = price_data.get('source', 'oilpriceapi')

        if change_24h is not None:
            change_24h = float(change_24h)
        if change_pct is not None:
            change_pct = float(change_pct)

        _store_hourly_price(table, today, current_hour, price, change_24h, change_pct, source)

        results['assets'][key] = {
            'status': 'captured',
            'price': price,
            'change_24h': change_24h,
            'change_pct': change_pct,
            'source': source,
            'label': cfg['label'],
        }
        logger.info(f"Intraday {cfg['label']}: ${price} at hour {current_hour} UTC")

    return results


def get_intraday_prices(asset_key: str) -> List[Dict[str, Any]]:
    if asset_key not in ASSET_CONFIGS:
        return []
    table = ASSET_CONFIGS[asset_key]['table']
    today = date.today()
    rows = execute_query(
        f"SELECT hour, price, change_pct, captured_at FROM {table} WHERE date = %s ORDER BY hour ASC",
        (today,)
    )
    result = []
    for row in (rows or []):
        ca = row['captured_at']
        if hasattr(ca, 'isoformat'):
            ca = ca.isoformat()
        result.append({
            'hour': row['hour'],
            'price': float(row['price']),
            'change_pct': float(row['change_pct']) if row.get('change_pct') is not None else None,
            'captured_at': ca,
        })
    return result


def get_all_intraday_prices() -> Dict[str, Any]:
    today = date.today()
    result = {'date': today.isoformat(), 'assets': {}}
    for key, cfg in ASSET_CONFIGS.items():
        prices = get_intraday_prices(key)
        result['assets'][key] = {
            'label': cfg['label'],
            'unit': cfg['unit'],
            'prices': prices,
            'count': len(prices),
        }
    return result
