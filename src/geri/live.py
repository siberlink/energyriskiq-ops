"""
GERI Live — Real-time GERI Index Computation Engine

Computes an intraday GERI value as alerts are processed, storing results
in the `geri_live` table. The daily GERI (intel_indices_daily) remains
the official published value; geri_live is a real-time preview for
Pro and Enterprise users.

Architecture:
  alert_events (today) → compute_components → normalize → geri_live table
  ↓
  SSE broadcast → connected Pro/Enterprise clients
"""

import logging
import json
import asyncio
from datetime import date, datetime, timedelta, timezone
from typing import Optional, Dict, Any, List

from src.db.db import get_cursor, execute_query, execute_one
from src.geri.types import (
    AlertRecord,
    VALID_ALERT_TYPES,
    get_band,
    INDEX_ID,
)
from src.geri.compute import compute_components
from src.geri.normalize import (
    normalize_components,
    calculate_geri_value,
)
from src.geri.repo import get_historical_baseline

logger = logging.getLogger(__name__)

DEBOUNCE_SECONDS = 60

_live_clients: List[asyncio.Queue] = []
_live_clients_lock = asyncio.Lock()


def run_geri_live_migration():
    with get_cursor(commit=True) as cursor:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS geri_live (
                id SERIAL PRIMARY KEY,
                value INTEGER NOT NULL DEFAULT 0,
                band VARCHAR(20) NOT NULL DEFAULT 'LOW',
                trend_vs_yesterday NUMERIC(5,1),
                components JSONB DEFAULT '{}',
                interpretation TEXT DEFAULT '',
                alert_count INTEGER DEFAULT 0,
                last_alert_id INTEGER,
                top_drivers JSONB DEFAULT '[]',
                top_regions JSONB DEFAULT '[]',
                computed_at TIMESTAMP DEFAULT NOW()
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_geri_live_computed_at 
            ON geri_live(computed_at DESC)
        """)
    logger.info("geri_live table migration complete")


def _get_today_alerts() -> List[AlertRecord]:
    now_utc = datetime.now(timezone.utc)
    start_of_day = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)

    sql = """
    SELECT 
        id, alert_type, severity,
        confidence as risk_score,
        scope_region as region,
        1.0 as weight,
        created_at, headline, body, raw_input
    FROM alert_events
    WHERE alert_type = ANY(%s)
      AND created_at >= %s
      AND created_at < %s
    ORDER BY created_at
    """

    alerts = []
    with get_cursor() as cursor:
        cursor.execute(sql, (VALID_ALERT_TYPES, start_of_day, now_utc))
        rows = cursor.fetchall()
        for row in rows:
            risk_score_val = float(row['risk_score']) if row['risk_score'] is not None else None
            event_category = None
            raw_input = row.get('raw_input')
            if raw_input:
                if isinstance(raw_input, str):
                    try:
                        raw_input = json.loads(raw_input)
                    except Exception:
                        raw_input = {}
                if raw_input.get('category'):
                    event_category = raw_input.get('category')
                elif raw_input.get('driver_events'):
                    de = raw_input.get('driver_events', [])
                    if de:
                        event_category = de[0].get('category')

            alerts.append(AlertRecord(
                id=row['id'],
                alert_type=row['alert_type'],
                severity=row['severity'],
                risk_score=risk_score_val,
                region=row['region'],
                weight=float(row['weight']) if row['weight'] else 1.0,
                created_at=row['created_at'],
                headline=row['headline'],
                body=row.get('body'),
                category=event_category,
            ))
    return alerts


def _get_yesterday_geri_value() -> Optional[int]:
    row = execute_one(
        "SELECT value, date, index_id FROM intel_indices_daily ORDER BY date DESC LIMIT 1"
    )
    if row:
        logger.info(f"Yesterday GERI from intel_indices_daily (date={row.get('date')}, index_id={row.get('index_id')}): {row['value']}")
        return int(row['value'])
    yesterday = date.today() - timedelta(days=1)
    yesterday_start = datetime.combine(yesterday, datetime.min.time())
    today_start = datetime.combine(date.today(), datetime.min.time())
    row2 = execute_one(
        "SELECT value FROM geri_live WHERE computed_at >= %s AND computed_at < %s ORDER BY id DESC LIMIT 1",
        (yesterday_start, today_start)
    )
    if row2:
        logger.info(f"Yesterday GERI from geri_live table: {row2['value']}")
        return int(row2['value'])
    logger.warning("No yesterday GERI found in any source")
    return None


def _should_debounce() -> bool:
    row = execute_one(
        "SELECT computed_at FROM geri_live ORDER BY id DESC LIMIT 1"
    )
    if not row:
        return False
    last_computed = row['computed_at']
    if last_computed.tzinfo is None:
        last_computed = last_computed.replace(tzinfo=timezone.utc)
    elapsed = (datetime.now(timezone.utc) - last_computed).total_seconds()
    return elapsed < DEBOUNCE_SECONDS


def compute_live_geri(force: bool = False) -> Optional[Dict[str, Any]]:
    if not force and _should_debounce():
        logger.debug("GERI Live: debounced (< 60s since last compute)")
        return get_latest_live_geri()

    alerts = _get_today_alerts()
    alert_count = len(alerts)

    if alert_count == 0:
        yesterday_val = _get_yesterday_geri_value()
        result = {
            'value': yesterday_val or 0,
            'band': get_band(yesterday_val or 0).value,
            'trend_vs_yesterday': 0,
            'alert_count': 0,
            'top_drivers': [],
            'top_regions': [],
            'components': {},
            'interpretation': '',
            'computed_at': datetime.now(timezone.utc).isoformat(),
            'no_alerts_today': True,
        }
        _store_live_result(result)
        return result

    components = compute_components(alerts)

    today = date.today()
    baseline = get_historical_baseline(today)
    components = normalize_components(components, baseline)
    value = calculate_geri_value(components)
    band = get_band(value)

    yesterday_val = _get_yesterday_geri_value()
    trend = value - yesterday_val if yesterday_val is not None else None

    top_drivers = []
    for d in (components.top_drivers or [])[:5]:
        top_drivers.append({
            'headline': d.get('headline', ''),
            'region': d.get('region', 'Unknown'),
            'category': d.get('category', 'unknown'),
            'severity': d.get('severity', 0),
            'weighted_score': d.get('weighted_score', 0),
        })

    top_regions = []
    for r in (components.top_regions or [])[:5]:
        top_regions.append({
            'region': r.get('region', 'Unknown'),
            'total_risk': r.get('risk_total', r.get('total_risk', 0)),
        })

    last_alert_id = alerts[-1].id if alerts else None

    comp_dict = {
        'high_impact_score': components.high_impact_score,
        'regional_spike_score': components.regional_spike_score,
        'asset_risk_score': components.asset_risk_score,
        'region_concentration': components.region_concentration_score_raw,
        'norm_high_impact': components.norm_high_impact,
        'norm_regional_spike': components.norm_regional_spike,
        'norm_asset_risk': components.norm_asset_risk,
        'norm_region_concentration': components.norm_region_concentration,
    }

    last_live = get_latest_live_geri()
    last_interp = last_live.get('interpretation', '') if last_live else ''
    last_value = last_live.get('value', 0) if last_live else 0
    last_band = last_live.get('band', 'LOW') if last_live else 'LOW'

    interp = last_interp
    interp_updated = False
    if should_regenerate_interpretation(value, last_value, band.value, last_band):
        try:
            new_interp = generate_live_interpretation(
                value=value,
                band=band.value,
                top_drivers=top_drivers,
                top_regions=[r['region'] for r in top_regions],
                alert_count=alert_count,
            )
            if new_interp:
                interp = new_interp
                interp_updated = True
        except Exception as e:
            logger.error(f"GERI Live interpretation error: {e}")

    now_str = datetime.now(timezone.utc).isoformat()

    result = {
        'value': value,
        'band': band.value,
        'trend_vs_yesterday': trend,
        'alert_count': alert_count,
        'top_drivers': top_drivers,
        'top_regions': top_regions,
        'components': comp_dict,
        'interpretation': interp,
        'interpretation_updated': interp_updated,
        'last_alert_id': last_alert_id,
        'computed_at': now_str,
        'yesterday_value': yesterday_val,
        'no_alerts_today': False,
    }

    _store_live_result(result)
    return result


def _store_live_result(result: Dict[str, Any]):
    with get_cursor(commit=True) as cursor:
        cursor.execute("""
            INSERT INTO geri_live 
                (value, band, trend_vs_yesterday, components, interpretation,
                 alert_count, last_alert_id, top_drivers, top_regions, computed_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        """, (
            result['value'],
            result['band'],
            result.get('trend_vs_yesterday'),
            json.dumps(result.get('components', {})),
            result.get('interpretation', ''),
            result.get('alert_count', 0),
            result.get('last_alert_id'),
            json.dumps(result.get('top_drivers', [])),
            json.dumps(result.get('top_regions', [])),
        ))


def get_latest_live_geri() -> Optional[Dict[str, Any]]:
    today_start = datetime.combine(date.today(), datetime.min.time())
    row = execute_one("""
        SELECT id, value, band, trend_vs_yesterday, components, interpretation,
               alert_count, last_alert_id, top_drivers, top_regions, computed_at
        FROM geri_live
        WHERE computed_at >= %s
        ORDER BY id DESC LIMIT 1
    """, (today_start,))

    if not row:
        return None

    return _row_to_dict(row)


def get_live_geri_timeline() -> List[Dict[str, Any]]:
    today_start = datetime.combine(date.today(), datetime.min.time())
    rows = execute_query("""
        SELECT id, value, band, alert_count, computed_at
        FROM geri_live
        WHERE computed_at >= %s
        ORDER BY computed_at ASC
    """, (today_start,))

    timeline = []
    for row in (rows or []):
        ca = row['computed_at']
        if hasattr(ca, 'isoformat'):
            ca = ca.isoformat()
        timeline.append({
            'value': int(row['value']),
            'band': row['band'],
            'alert_count': row['alert_count'],
            'time': ca,
        })
    return timeline


def _row_to_dict(row) -> Dict[str, Any]:
    components = row.get('components', {})
    if isinstance(components, str):
        try:
            components = json.loads(components)
        except Exception:
            components = {}

    top_drivers = row.get('top_drivers', [])
    if isinstance(top_drivers, str):
        try:
            top_drivers = json.loads(top_drivers)
        except Exception:
            top_drivers = []

    top_regions = row.get('top_regions', [])
    if isinstance(top_regions, str):
        try:
            top_regions = json.loads(top_regions)
        except Exception:
            top_regions = []

    ca = row['computed_at']
    if hasattr(ca, 'isoformat'):
        ca = ca.isoformat()

    return {
        'id': row['id'],
        'value': int(row['value']),
        'band': row['band'],
        'trend_vs_yesterday': float(row['trend_vs_yesterday']) if row.get('trend_vs_yesterday') is not None else None,
        'components': components,
        'interpretation': row.get('interpretation', ''),
        'alert_count': row.get('alert_count', 0),
        'last_alert_id': row.get('last_alert_id'),
        'top_drivers': top_drivers,
        'top_regions': top_regions,
        'computed_at': ca,
    }


def should_regenerate_interpretation(new_value: int, last_value: int, new_band: str, last_band: str) -> bool:
    if not last_value and not last_band:
        return True
    if new_band != last_band:
        return True
    if abs(new_value - last_value) >= 2:
        return True
    return False


def generate_live_interpretation(
    value: int,
    band: str,
    top_drivers: List[Dict],
    top_regions: List[str],
    alert_count: int,
) -> str:
    import os
    api_key = os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY")
    base_url = os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL")

    if not api_key or not base_url:
        logger.warning("OpenAI not configured, using fallback live interpretation")
        return _fallback_live_interpretation(value, band, top_regions, alert_count)

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=base_url)

        driver_lines = []
        for i, d in enumerate(top_drivers[:5]):
            headline = d.get('headline', '')
            region = d.get('region', 'Unknown')
            cat = d.get('category', 'unknown').replace('_', ' ')
            driver_lines.append(f"{i+1}. [{region}/{cat}] {headline}")
        drivers_text = "\n".join(driver_lines) if driver_lines else "No significant drivers detected yet today"
        regions_text = ", ".join(top_regions[:3]) if top_regions else "global markets"

        now_utc = datetime.now(timezone.utc).strftime('%H:%M UTC')

        prompt = f"""You are a senior energy market analyst providing a real-time intraday risk assessment. Write a concise 1-2 paragraph interpretation of the current GERI Live index.

LIVE INDEX DATA (as of {now_utc}):
- GERI Live Value: {value}/100
- Risk Band: {band}
- Alerts Processed Today: {alert_count}
- Top Affected Regions: {regions_text}

TOP DRIVERS TODAY:
{drivers_text}

REQUIREMENTS:
1. Start with the current risk posture — what the {value}/100 ({band}) reading means for energy markets RIGHT NOW
2. Reference specific drivers and regions from the data above
3. Note this is an intraday reading based on {alert_count} alerts processed so far today
4. Keep it to 1-2 tight paragraphs (100-150 words total)
5. Write as a human expert, not a template
6. Do NOT use phrases like "in conclusion" or "overall"
7. Use present tense — this is a live reading"""

        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": "You are EnergyRiskIQ's senior risk analyst providing real-time market intelligence."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=300,
            temperature=0.7,
        )

        return response.choices[0].message.content.strip()

    except Exception as e:
        logger.error(f"Live interpretation generation failed: {e}")
        return _fallback_live_interpretation(value, band, top_regions, alert_count)


def _fallback_live_interpretation(value: int, band: str, top_regions: List[str], alert_count: int) -> str:
    regions_text = ", ".join(top_regions[:3]) if top_regions else "global energy markets"
    now_utc = datetime.now(timezone.utc).strftime('%H:%M UTC')

    if value <= 20:
        tone = "Energy markets are currently stable with minimal risk signals detected"
    elif value <= 40:
        tone = "Moderate structural stress is present in energy markets"
    elif value <= 60:
        tone = "Elevated risk conditions are developing across energy markets"
    elif value <= 80:
        tone = "Severe disruption pressure is building in energy markets"
    else:
        tone = "Critical structural stress is present with significant market disruption potential"

    return (
        f"{tone}. As of {now_utc}, the GERI Live index reads {value}/100 ({band}), "
        f"based on {alert_count} alerts processed today. "
        f"Key regions under watch include {regions_text}."
    )


async def register_live_client(queue: asyncio.Queue):
    async with _live_clients_lock:
        _live_clients.append(queue)
    logger.debug(f"GERI Live: client connected ({len(_live_clients)} total)")


async def unregister_live_client(queue: asyncio.Queue):
    async with _live_clients_lock:
        if queue in _live_clients:
            _live_clients.remove(queue)
    logger.debug(f"GERI Live: client disconnected ({len(_live_clients)} total)")


async def broadcast_live_update(data: Dict[str, Any]):
    async with _live_clients_lock:
        dead = []
        for q in _live_clients:
            try:
                q.put_nowait(data)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            _live_clients.remove(q)
