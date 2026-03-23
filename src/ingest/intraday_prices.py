"""
Intraday Price Capture — Hourly prices for Brent, WTI, Natural Gas (US)

Primary source: Yahoo Finance (yfinance) — reliable, no key required.
Fallback source: OilPriceAPI (used only if yfinance fails).

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

from src.db.db import get_production_cursor, execute_production_query

logger = logging.getLogger(__name__)

OIL_PRICE_API_KEY = os.environ.get("OIL_PRICE_API_KEY", "")
OIL_PRICE_API_BASE = "https://api.oilpriceapi.com/v1"

ASSET_CONFIGS = {
    'brent': {
        'yf_ticker': 'BZ=F',
        'oilapi_code': 'BRENT_CRUDE_USD',
        'table': 'intraday_brent',
        'label': 'Brent Crude',
        'unit': 'USD/barrel',
    },
    'wti': {
        'yf_ticker': 'CL=F',
        'oilapi_code': 'WTI_USD',
        'table': 'intraday_wti',
        'label': 'WTI Crude',
        'unit': 'USD/barrel',
    },
    'natgas': {
        'yf_ticker': 'NG=F',
        'oilapi_code': 'NATURAL_GAS_USD',
        'table': 'intraday_natgas',
        'label': 'Natural Gas (US)',
        'unit': 'USD/MMBtu',
    },
}


def run_intraday_migration():
    with get_production_cursor(commit=True) as cursor:
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
                    source VARCHAR(100) DEFAULT 'yfinance',
                    captured_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    UNIQUE(date, hour)
                )
            """)
            cursor.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{table}_date ON {table}(date)
            """)
    logger.info("Intraday price tables migration complete")


def _fetch_via_yfinance(ticker: str, prev_close: Optional[float] = None) -> Optional[Dict[str, Any]]:
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        hist = t.history(period='1d', interval='1h')
        if hist.empty:
            logger.warning(f"yfinance returned empty history for {ticker}")
            return None
        close_series = hist['Close'].dropna()
        if close_series.empty:
            return None
        price = float(close_series.iloc[-1])

        if prev_close is None:
            info = t.info
            prev_close = info.get('previousClose') or info.get('regularMarketPreviousClose')

        change_24h = None
        change_pct = None
        if prev_close:
            change_24h = round(price - float(prev_close), 4)
            change_pct = round((change_24h / float(prev_close)) * 100, 4)

        return {
            'price': price,
            'change_24h': change_24h,
            'change_pct': change_pct,
            'source': 'yfinance',
        }
    except Exception as e:
        logger.error(f"yfinance fetch failed for {ticker}: {e}")
        return None


def _fetch_via_oilpriceapi(code: str) -> Optional[Dict[str, Any]]:
    if not OIL_PRICE_API_KEY:
        return None
    url = f"{OIL_PRICE_API_BASE}/prices/latest"
    headers = {
        "Authorization": f"Token {OIL_PRICE_API_KEY}",
        "Content-Type": "application/json"
    }
    try:
        response = requests.get(url, headers=headers, params={"by_code": code}, timeout=20)
        if response.status_code != 200:
            logger.warning(f"OilPriceAPI returned {response.status_code} for {code}")
            return None
        data = response.json()
        if data.get("status") != "success" or not data.get("data"):
            return None
        pd = data["data"]
        price = pd.get('price')
        if price is None:
            return None
        price = float(price)
        changes = pd.get('changes', {}).get('24h', {})
        change_24h = float(changes['amount']) if changes.get('amount') is not None else None
        change_pct = float(changes['percent']) if changes.get('percent') is not None else None
        return {
            'price': price,
            'change_24h': change_24h,
            'change_pct': change_pct,
            'source': 'oilpriceapi',
        }
    except Exception as e:
        logger.error(f"OilPriceAPI request failed for {code}: {e}")
        return None


def _cleanup_old_data(table: str, today: date):
    with get_production_cursor(commit=True) as cursor:
        cursor.execute(f"DELETE FROM {table} WHERE date < %s", (today,))


def _store_hourly_price(table: str, today: date, hour: int, price: float,
                        change_24h: Optional[float], change_pct: Optional[float],
                        source: str):
    with get_production_cursor(commit=True) as cursor:
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

        price_data = _fetch_via_yfinance(cfg['yf_ticker'])
        if not price_data:
            logger.warning(f"yfinance failed for {key}, trying OilPriceAPI fallback")
            price_data = _fetch_via_oilpriceapi(cfg['oilapi_code'])

        if not price_data:
            results['assets'][key] = {'status': 'failed', 'error': 'all sources failed'}
            continue

        _store_hourly_price(
            table, today, current_hour,
            price_data['price'],
            price_data.get('change_24h'),
            price_data.get('change_pct'),
            price_data['source'],
        )

        results['assets'][key] = {
            'status': 'captured',
            'price': price_data['price'],
            'change_24h': price_data.get('change_24h'),
            'change_pct': price_data.get('change_pct'),
            'source': price_data['source'],
            'label': cfg['label'],
        }
        logger.info(f"Intraday {cfg['label']}: ${price_data['price']} at hour {current_hour} UTC (source={price_data['source']})")

    return results


def get_intraday_prices(asset_key: str) -> List[Dict[str, Any]]:
    if asset_key not in ASSET_CONFIGS:
        return []
    table = ASSET_CONFIGS[asset_key]['table']
    today = date.today()
    rows = execute_production_query(
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
