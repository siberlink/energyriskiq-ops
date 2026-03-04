"""
GERI Live — Real-time GERI Index Computation Engine

Computes an intraday GERI value anchored to the previous day's close,
adjusted by today's incoming alerts. Stores results in the `geri_live`
table. The daily GERI (intel_indices_daily) remains the official
published value; geri_live is a real-time preview for Pro/Enterprise users.

Architecture:
  anchor (previous close) + today's alerts → blended GERI Live value
  ↓
  SSE broadcast → connected Pro/Enterprise clients

Continuity Model:
  - At 00:00 UTC, GERI Live starts at the previous day's closing value
  - As today's alerts accumulate, the "today signal" weight increases
  - When GERI Daily is computed (~01:15-01:30 UTC), it becomes the anchor
  - Formula: blended = anchor * (1 - signal_weight) + today_signal * signal_weight
  - signal_weight ramps from 0.0 (0 alerts) to ~0.85 (150+ alerts)
"""

import logging
import json
import asyncio
import math
from datetime import date, datetime, timedelta, timezone
from typing import Optional, Dict, Any, List

from src.db.db import get_cursor, execute_query, execute_one
from src.geri.types import (
    AlertRecord,
    VALID_ALERT_TYPES,
    get_band,
    INDEX_ID,
    GERI_WEIGHTS,
)
from src.geri.compute import compute_components
from src.geri.normalize import (
    normalize_components,
    calculate_geri_value,
)
from src.geri.repo import get_historical_baseline

logger = logging.getLogger(__name__)

DEBOUNCE_SECONDS = 60

TYPICAL_DAILY_ALERTS = 120
SIGNAL_WEIGHT_MAX = 0.85

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
        try:
            cursor.execute("""
                ALTER TABLE geri_live ADD COLUMN IF NOT EXISTS value_raw NUMERIC(6,2) DEFAULT 0.0
            """)
        except Exception as e:
            logger.warning("Could not add value_raw column (may already exist): %s", e)
        try:
            cursor.execute("""
                ALTER TABLE geri_live ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'
            """)
        except Exception as e:
            logger.warning("Could not add metadata column (may already exist): %s", e)
    logger.info("geri_live table migration complete")


def _get_today_alerts() -> List[AlertRecord]:
    now_utc = datetime.utcnow()
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


def _get_anchor_value() -> Dict[str, Any]:
    """
    Get the anchor value for GERI Live continuity.
    
    Priority:
      1. Today's GERI Daily (if already computed, e.g. after 01:30 UTC)
      2. Latest GERI Daily (yesterday's official close)
      3. Last geri_live entry from yesterday (if daily hasn't been computed yet)
      4. Fallback to 50 (neutral midpoint)
    
    Returns dict with 'value', 'source', and 'date'.
    """
    today = date.today()
    
    today_daily = execute_one(
        "SELECT value, date FROM intel_indices_daily WHERE index_id = %s AND date = %s",
        (INDEX_ID, today)
    )
    if today_daily:
        val = int(today_daily['value'])
        logger.info(f"GERI Live anchor: today's daily GERI = {val} (date={today})")
        return {'value': val, 'source': 'daily_today', 'date': today.isoformat()}

    latest_daily = execute_one(
        "SELECT value, date FROM intel_indices_daily WHERE index_id = %s ORDER BY date DESC LIMIT 1",
        (INDEX_ID,)
    )
    if latest_daily:
        val = int(latest_daily['value'])
        d = latest_daily['date']
        logger.info(f"GERI Live anchor: latest daily GERI = {val} (date={d})")
        return {'value': val, 'source': 'daily_previous', 'date': d.isoformat() if hasattr(d, 'isoformat') else str(d)}

    yesterday = today - timedelta(days=1)
    yesterday_start = datetime.combine(yesterday, datetime.min.time())
    today_start = datetime.combine(today, datetime.min.time())
    last_live = execute_one(
        "SELECT value FROM geri_live WHERE computed_at >= %s AND computed_at < %s ORDER BY id DESC LIMIT 1",
        (yesterday_start, today_start)
    )
    if last_live:
        val = int(last_live['value'])
        logger.info(f"GERI Live anchor: yesterday's last live = {val}")
        return {'value': val, 'source': 'live_yesterday', 'date': yesterday.isoformat()}

    logger.warning("No anchor found, using neutral midpoint 50")
    return {'value': 50, 'source': 'default', 'date': today.isoformat()}


def _compute_signal_weight(alert_count: int) -> float:
    """
    Compute how much weight to give today's alert-based signal vs the anchor.
    
    Uses a logarithmic curve so the weight ramps up quickly with the first
    alerts, then flattens — reflecting diminishing marginal information.
    
    Examples:
      0 alerts  → 0.00 (pure anchor)
      5 alerts  → 0.22
      10 alerts → 0.33
      25 alerts → 0.47
      50 alerts → 0.57
      100 alerts → 0.67
      150 alerts → 0.73
      200+ alerts → approaches 0.85 max
    """
    if alert_count <= 0:
        return 0.0
    weight = SIGNAL_WEIGHT_MAX * (1 - math.exp(-alert_count / (TYPICAL_DAILY_ALERTS * 0.6)))
    return min(weight, SIGNAL_WEIGHT_MAX)


def _get_previous_close() -> Optional[int]:
    """
    Get the previous official GERI Daily close for trend calculation.
    This always returns YESTERDAY's value, never today's daily.
    Used for "Previous Close" display and trend_vs_yesterday.
    """
    latest_daily = execute_one(
        "SELECT value, date FROM intel_indices_daily WHERE index_id = %s ORDER BY date DESC LIMIT 1",
        (INDEX_ID,)
    )
    if latest_daily:
        return int(latest_daily['value'])

    yesterday = date.today() - timedelta(days=1)
    yesterday_start = datetime.combine(yesterday, datetime.min.time())
    today_start = datetime.combine(date.today(), datetime.min.time())
    last_live = execute_one(
        "SELECT value FROM geri_live WHERE computed_at >= %s AND computed_at < %s ORDER BY id DESC LIMIT 1",
        (yesterday_start, today_start)
    )
    if last_live:
        return int(last_live['value'])
    return None


def _get_yesterday_geri_value() -> Optional[int]:
    """Get yesterday's GERI value for trend calculation (alias for previous close)."""
    return _get_previous_close()


def _should_debounce() -> bool:
    today_start = datetime.combine(date.today(), datetime.min.time())
    row = execute_one(
        "SELECT computed_at FROM geri_live WHERE computed_at >= %s ORDER BY id DESC LIMIT 1",
        (today_start,)
    )
    if not row:
        return False
    last_computed = row['computed_at']
    elapsed = (datetime.utcnow() - last_computed).total_seconds()
    return elapsed < DEBOUNCE_SECONDS


BAND_THRESHOLDS = [
    (0, 20, 'LOW'),
    (21, 40, 'MODERATE'),
    (41, 60, 'ELEVATED'),
    (61, 80, 'SEVERE'),
    (81, 100, 'CRITICAL'),
]


def _compute_velocity(timeline: List[Dict[str, Any]], current_value: int) -> Optional[Dict[str, Any]]:
    if not timeline or len(timeline) < 2:
        return None
    now = datetime.utcnow()
    one_hour_ago = now - timedelta(hours=1)
    closest = None
    for point in timeline:
        t = point.get('time') or point.get('computed_at')
        if isinstance(t, str):
            try:
                pt = datetime.fromisoformat(t.replace('Z', '+00:00'))
                if pt.tzinfo is not None:
                    pt = pt.replace(tzinfo=None)
            except Exception:
                continue
        elif hasattr(t, 'isoformat'):
            pt = t if t.tzinfo is None else t.replace(tzinfo=None)
        else:
            continue
        if pt <= one_hour_ago:
            closest = point
    if closest is None:
        closest = timeline[0]
    old_value = closest.get('value', current_value)
    delta = current_value - old_value
    return {
        'delta': delta,
        'label': f"+{delta} pts/hr" if delta > 0 else f"{delta} pts/hr" if delta < 0 else "Stable",
        'direction': 'up' if delta > 0 else 'down' if delta < 0 else 'flat',
    }


def _compute_band_proximity(value: int) -> Optional[Dict[str, Any]]:
    for low, high, band_name in BAND_THRESHOLDS:
        if low <= value <= high:
            dist_to_upper = high - value + 1
            dist_to_lower = value - low + 1
            result = {}
            idx = BAND_THRESHOLDS.index((low, high, band_name))
            if idx < len(BAND_THRESHOLDS) - 1 and dist_to_upper <= 5:
                next_band = BAND_THRESHOLDS[idx + 1][2]
                result = {
                    'points_away': dist_to_upper,
                    'target_band': next_band,
                    'direction': 'up',
                    'label': f"{dist_to_upper} pts from {next_band}",
                }
            elif idx > 0 and dist_to_lower <= 5:
                prev_band = BAND_THRESHOLDS[idx - 1][2]
                result = {
                    'points_away': dist_to_lower,
                    'target_band': prev_band,
                    'direction': 'down',
                    'label': f"{dist_to_lower} pts from {prev_band}",
                }
            return result if result else None
    return None


def _compute_peak_low(timeline: List[Dict[str, Any]], current_value: int) -> Dict[str, Any]:
    if not timeline:
        return {'peak': current_value, 'peak_time': None, 'low': current_value, 'low_time': None}
    peak_val = current_value
    peak_time = None
    low_val = current_value
    low_time = None
    for point in timeline:
        v = point.get('value', 0)
        t = point.get('time') or point.get('computed_at')
        if v >= peak_val:
            peak_val = v
            peak_time = t
        if v <= low_val:
            low_val = v
            low_time = t
    return {'peak': peak_val, 'peak_time': peak_time, 'low': low_val, 'low_time': low_time}


def compute_live_geri(force: bool = False) -> Optional[Dict[str, Any]]:
    if not force and _should_debounce():
        logger.debug("GERI Live: debounced (< 60s since last compute)")
        return get_latest_live_geri()

    anchor = _get_anchor_value()
    anchor_val = anchor['value']

    alerts = _get_today_alerts()
    alert_count = len(alerts)

    if alert_count == 0:
        result = {
            'value': anchor_val,
            'value_raw': float(anchor_val),
            'band': get_band(anchor_val).value,
            'trend_vs_yesterday': 0,
            'alert_count': 0,
            'top_drivers': [],
            'top_regions': [],
            'components': {},
            'interpretation': '',
            'computed_at': datetime.utcnow().isoformat(),
            'no_alerts_today': True,
            'anchor_value': anchor_val,
            'anchor_source': anchor['source'],
            'signal_weight': 0.0,
        }
        _store_live_result(result)
        return result

    components = compute_components(alerts)

    today = date.today()
    baseline = get_historical_baseline(today)
    components = normalize_components(components, baseline)
    today_signal = calculate_geri_value(components)
    today_signal_raw = round(
        GERI_WEIGHTS['high_impact'] * components.norm_high_impact +
        GERI_WEIGHTS['regional_spike'] * components.norm_regional_spike +
        GERI_WEIGHTS['asset_risk'] * components.norm_asset_risk +
        GERI_WEIGHTS['region_concentration'] * components.norm_region_concentration,
        2
    )

    signal_weight = _compute_signal_weight(alert_count)

    if anchor['source'] == 'daily_today':
        blended_raw = float(anchor_val)
        blended = anchor_val
        signal_weight = 0.0
        logger.info(
            "GERI Live: using today's daily GERI as definitive value = %d", anchor_val
        )
    else:
        blended_raw = round(
            anchor_val * (1 - signal_weight) + today_signal_raw * signal_weight,
            2
        )
        blended = max(0, min(100, round(blended_raw)))
        logger.info(
            "GERI Live: anchor=%d, today_signal=%d (raw=%.2f), weight=%.3f → blended=%d (raw=%.2f), alerts=%d",
            anchor_val, today_signal, today_signal_raw, signal_weight, blended, blended_raw, alert_count
        )

    band = get_band(blended)

    yesterday_val = _get_yesterday_geri_value()
    trend = blended - yesterday_val if yesterday_val is not None else None

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
    if should_regenerate_interpretation(blended, last_value, band.value, last_band):
        try:
            new_interp = generate_live_interpretation(
                value=blended,
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

    now_str = datetime.utcnow().isoformat()

    timeline = get_live_geri_timeline()
    velocity = _compute_velocity(timeline, blended)
    band_proximity = _compute_band_proximity(blended)
    peak_low = _compute_peak_low(timeline, blended)

    result = {
        'value': blended,
        'value_raw': blended_raw,
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
        'anchor_value': anchor_val,
        'anchor_source': anchor['source'],
        'signal_weight': round(signal_weight, 3),
        'today_signal': today_signal,
        'today_signal_raw': today_signal_raw,
        'velocity': velocity,
        'band_proximity': band_proximity,
        'peak_low': peak_low,
    }

    _store_live_result(result)
    return result


def _has_value_raw_column() -> bool:
    try:
        row = execute_one(
            "SELECT column_name FROM information_schema.columns WHERE table_name='geri_live' AND column_name='value_raw'"
        )
        return row is not None
    except Exception:
        return False

_value_raw_available = None

def _check_value_raw() -> bool:
    global _value_raw_available
    if _value_raw_available is None:
        _value_raw_available = _has_value_raw_column()
    return _value_raw_available


def _store_live_result(result: Dict[str, Any]):
    has_raw = _check_value_raw()
    metadata = json.dumps({
        'anchor_value': result.get('anchor_value'),
        'anchor_source': result.get('anchor_source'),
        'signal_weight': result.get('signal_weight'),
        'today_signal': result.get('today_signal'),
        'today_signal_raw': result.get('today_signal_raw'),
    })
    with get_cursor(commit=True) as cursor:
        if has_raw:
            cursor.execute("""
                INSERT INTO geri_live 
                    (value, value_raw, band, trend_vs_yesterday, components, interpretation,
                     alert_count, last_alert_id, top_drivers, top_regions, metadata, computed_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            """, (
                result['value'],
                result.get('value_raw', float(result['value'])),
                result['band'],
                result.get('trend_vs_yesterday'),
                json.dumps(result.get('components', {})),
                result.get('interpretation', ''),
                result.get('alert_count', 0),
                result.get('last_alert_id'),
                json.dumps(result.get('top_drivers', [])),
                json.dumps(result.get('top_regions', [])),
                metadata,
            ))
        else:
            cursor.execute("""
                INSERT INTO geri_live 
                    (value, band, trend_vs_yesterday, components, interpretation,
                     alert_count, last_alert_id, top_drivers, top_regions, metadata, computed_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
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
                metadata,
            ))


def get_latest_live_geri() -> Optional[Dict[str, Any]]:
    today_start = datetime.combine(date.today(), datetime.min.time())
    has_raw = _check_value_raw()
    cols = "id, value, value_raw, band, trend_vs_yesterday, components, interpretation, alert_count, last_alert_id, top_drivers, top_regions, metadata, computed_at" if has_raw else "id, value, band, trend_vs_yesterday, components, interpretation, alert_count, last_alert_id, top_drivers, top_regions, metadata, computed_at"
    row = execute_one(f"""
        SELECT {cols}
        FROM geri_live
        WHERE computed_at >= %s
        ORDER BY id DESC LIMIT 1
    """, (today_start,))

    if not row:
        return None

    return _row_to_dict(row)


def get_live_geri_timeline() -> List[Dict[str, Any]]:
    today_start = datetime.combine(date.today(), datetime.min.time())
    has_raw = _check_value_raw()
    cols = "id, value, value_raw, band, alert_count, computed_at" if has_raw else "id, value, band, alert_count, computed_at"
    rows = execute_query(f"""
        SELECT {cols}
        FROM geri_live
        WHERE computed_at >= %s
        ORDER BY computed_at ASC
    """, (today_start,))

    timeline = []
    for row in (rows or []):
        ca = row['computed_at']
        if hasattr(ca, 'isoformat'):
            ca = ca.isoformat()
        val = int(row['value'])
        val_raw = float(row['value_raw']) if row.get('value_raw') is not None else float(val)
        timeline.append({
            'value': val,
            'value_raw': val_raw,
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

    metadata = row.get('metadata', {})
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except Exception:
            metadata = {}
    if metadata is None:
        metadata = {}

    ca = row['computed_at']
    if hasattr(ca, 'isoformat'):
        ca = ca.isoformat()

    val = int(row['value'])
    val_raw = float(row['value_raw']) if row.get('value_raw') is not None else float(val)

    return {
        'id': row['id'],
        'value': val,
        'value_raw': val_raw,
        'band': row['band'],
        'trend_vs_yesterday': float(row['trend_vs_yesterday']) if row.get('trend_vs_yesterday') is not None else None,
        'components': components,
        'interpretation': row.get('interpretation', ''),
        'alert_count': row.get('alert_count', 0),
        'last_alert_id': row.get('last_alert_id'),
        'top_drivers': top_drivers,
        'top_regions': top_regions,
        'computed_at': ca,
        'anchor_value': metadata.get('anchor_value'),
        'anchor_source': metadata.get('anchor_source'),
        'signal_weight': metadata.get('signal_weight'),
        'today_signal': metadata.get('today_signal'),
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

        now_utc = datetime.utcnow().strftime('%H:%M UTC')

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
7. Use present tense — this is a live reading
8. Do NOT mention anchoring, blending, or technical computation details"""

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
    now_utc = datetime.utcnow().strftime('%H:%M UTC')

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


PERIODIC_RECOMPUTE_INTERVAL = 300

async def periodic_geri_live_recompute():
    logger.info("GERI Live: periodic recomputation task started (every %ds)", PERIODIC_RECOMPUTE_INTERVAL)
    while True:
        await asyncio.sleep(PERIODIC_RECOMPUTE_INTERVAL)
        try:
            result = compute_live_geri(force=True)
            if result:
                logger.info(
                    "GERI Live periodic recompute: value=%s (raw=%.2f), band=%s, alerts=%d",
                    result['value'], result.get('value_raw', 0), result['band'], result.get('alert_count', 0)
                )
                await broadcast_live_update({
                    'type': 'update',
                    **result,
                })
            else:
                logger.debug("GERI Live periodic recompute: no result (no change)")
        except Exception as e:
            logger.error("GERI Live periodic recompute error: %s", e)
