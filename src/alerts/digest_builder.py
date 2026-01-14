"""
Digest Builder (Phase D) for Alerts v2

Groups digest deliveries into digest batches for efficient sending.
Creates user_alert_digests records and attaches deliveries as items.
"""

import os
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple

from src.db.db import get_cursor, execute_query, execute_one

logger = logging.getLogger(__name__)

ALERTS_DIGEST_PERIOD = os.environ.get('ALERTS_DIGEST_PERIOD', 'daily')
ALERTS_APP_BASE_URL = os.environ.get('ALERTS_APP_BASE_URL', 'https://energyriskiq.com')
ALERTS_DIGEST_TIMEZONE = os.environ.get('ALERTS_DIGEST_TIMEZONE', 'UTC')


def get_digest_window(period: str = 'daily', reference_time: Optional[datetime] = None) -> Tuple[datetime, datetime]:
    """
    Get the digest window (start, end) for a given period.
    
    Daily: [00:00, 24:00) of the previous day
    Hourly: [HH:00, HH+1:00) of the previous hour
    """
    now = reference_time or datetime.now(timezone.utc)
    
    if period == 'hourly':
        end = now.replace(minute=0, second=0, microsecond=0)
        start = end - timedelta(hours=1)
    else:
        end = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start = end - timedelta(days=1)
    
    return start, end


def format_digest_key(user_id: int, channel: str, period: str, window_start: datetime) -> str:
    """Generate unique digest key for idempotency."""
    if period == 'hourly':
        window_str = window_start.strftime('%Y-%m-%dT%H')
    else:
        window_str = window_start.strftime('%Y-%m-%d')
    
    return f"{user_id}:{channel}:{period}:{window_str}"


def get_unbatched_digest_deliveries(window_start: datetime, window_end: datetime) -> List[Dict]:
    """
    Get digest deliveries that haven't been batched yet.
    
    Returns deliveries where:
    - delivery_kind = 'digest'
    - status = 'queued'
    - created_at within window
    - NOT already attached to a digest
    """
    query = """
    SELECT d.id, d.user_id, d.alert_event_id, d.channel, d.created_at,
           ae.headline, ae.body, ae.alert_type, ae.severity, ae.scope_region
    FROM user_alert_deliveries d
    JOIN alert_events ae ON ae.id = d.alert_event_id
    WHERE d.delivery_kind = 'digest'
      AND d.status = 'queued'
      AND d.created_at >= %s
      AND d.created_at < %s
      AND d.channel IN ('email', 'telegram')
      AND NOT EXISTS (
          SELECT 1 FROM user_alert_digest_items di 
          WHERE di.delivery_id = d.id
      )
    ORDER BY d.user_id, d.channel, d.created_at
    """
    results = execute_query(query, (window_start, window_end))
    return results if results else []


def create_digest_record(
    user_id: int,
    channel: str,
    period: str,
    window_start: datetime,
    window_end: datetime,
    digest_key: str
) -> Optional[int]:
    """
    Create a digest record if it doesn't exist.
    Uses ON CONFLICT DO NOTHING for idempotency.
    
    Returns digest_id if created, None if already exists.
    """
    try:
        with get_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO user_alert_digests 
                (user_id, channel, period, window_start, window_end, digest_key, status)
                VALUES (%s, %s, %s, %s, %s, %s, 'queued')
                ON CONFLICT (digest_key) DO NOTHING
                RETURNING id
                """,
                (user_id, channel, period, window_start, window_end, digest_key)
            )
            result = cursor.fetchone()
            if result:
                logger.info(f"Created digest {result['id']} for {digest_key}")
                return result['id']
            else:
                logger.debug(f"Digest already exists: {digest_key}")
                return None
    except Exception as e:
        logger.error(f"Error creating digest: {e}")
        return None


def get_existing_digest_id(digest_key: str) -> Optional[int]:
    """Get the ID of an existing digest by key."""
    result = execute_one(
        "SELECT id FROM user_alert_digests WHERE digest_key = %s",
        (digest_key,)
    )
    return result['id'] if result else None


def attach_delivery_to_digest(digest_id: int, delivery_id: int) -> bool:
    """
    Attach a delivery to a digest.
    Uses UNIQUE constraint for idempotency.
    """
    try:
        with get_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO user_alert_digest_items (digest_id, delivery_id)
                VALUES (%s, %s)
                ON CONFLICT (digest_id, delivery_id) DO NOTHING
                RETURNING id
                """,
                (digest_id, delivery_id)
            )
            result = cursor.fetchone()
            return result is not None
    except Exception as e:
        logger.error(f"Error attaching delivery {delivery_id} to digest {digest_id}: {e}")
        return False


def mark_delivery_batched(delivery_id: int):
    """Mark a delivery as batched into a digest (status=skipped, reason=batched)."""
    try:
        with get_cursor() as cursor:
            cursor.execute(
                """
                UPDATE user_alert_deliveries 
                SET status = 'skipped', last_error = 'batched_into_digest'
                WHERE id = %s AND status = 'queued'
                """,
                (delivery_id,)
            )
    except Exception as e:
        logger.error(f"Error marking delivery {delivery_id} as batched: {e}")


def build_digests(period: str = None, reference_time: datetime = None) -> Dict:
    """
    Phase D: Build digest batches from queued digest deliveries.
    
    Groups deliveries by (user_id, channel) within the digest window,
    creates digest records, attaches deliveries, and marks them as batched.
    
    Returns structured counts for monitoring.
    """
    period = period or ALERTS_DIGEST_PERIOD
    window_start, window_end = get_digest_window(period, reference_time)
    
    logger.info(f"Phase D: Building {period} digests for window {window_start} to {window_end}")
    
    counts = {
        'digests_created': 0,
        'digest_items_attached': 0,
        'deliveries_marked_batched': 0,
        'period': period,
        'window_start': window_start.isoformat(),
        'window_end': window_end.isoformat()
    }
    
    deliveries = get_unbatched_digest_deliveries(window_start, window_end)
    
    if not deliveries:
        logger.info("No unbatched digest deliveries found in window")
        return counts
    
    logger.info(f"Found {len(deliveries)} unbatched digest deliveries")
    
    grouped: Dict[str, List[Dict]] = {}
    for d in deliveries:
        user_id = d['user_id']
        channel = d['channel']
        digest_key = format_digest_key(user_id, channel, period, window_start)
        
        if digest_key not in grouped:
            grouped[digest_key] = []
        grouped[digest_key].append(d)
    
    logger.info(f"Grouped into {len(grouped)} potential digests")
    
    for digest_key, delivery_list in grouped.items():
        if not delivery_list:
            continue
        
        user_id = delivery_list[0]['user_id']
        channel = delivery_list[0]['channel']
        
        digest_id = create_digest_record(
            user_id=user_id,
            channel=channel,
            period=period,
            window_start=window_start,
            window_end=window_end,
            digest_key=digest_key
        )
        
        if digest_id:
            counts['digests_created'] += 1
        else:
            digest_id = get_existing_digest_id(digest_key)
        
        if not digest_id:
            logger.warning(f"Could not get digest_id for {digest_key}")
            continue
        
        for d in delivery_list:
            delivery_id = d['id']
            
            if attach_delivery_to_digest(digest_id, delivery_id):
                counts['digest_items_attached'] += 1
            
            mark_delivery_batched(delivery_id)
            counts['deliveries_marked_batched'] += 1
    
    logger.info(f"Phase D complete: {counts['digests_created']} digests created, "
                f"{counts['digest_items_attached']} items attached, "
                f"{counts['deliveries_marked_batched']} deliveries batched")
    
    return counts


def get_digest_events(digest_id: int) -> List[Dict]:
    """Get all events included in a digest."""
    query = """
    SELECT ae.id, ae.headline, ae.body, ae.alert_type, ae.severity, 
           ae.scope_region, ae.scope_assets, ae.created_at
    FROM user_alert_digest_items di
    JOIN user_alert_deliveries d ON d.id = di.delivery_id
    JOIN alert_events ae ON ae.id = d.alert_event_id
    WHERE di.digest_id = %s
    ORDER BY ae.severity DESC, ae.created_at DESC
    """
    results = execute_query(query, (digest_id,))
    return results if results else []


def format_email_digest(events: List[Dict], window_start: datetime, window_end: datetime) -> Tuple[str, str]:
    """
    Format digest content for email.
    Returns (subject, body).
    """
    date_str = window_start.strftime('%B %d, %Y')
    
    subject = f"EnergyRiskIQ Daily Digest - {date_str}"
    
    body_parts = [
        f"EnergyRiskIQ Daily Digest",
        f"Period: {window_start.strftime('%Y-%m-%d %H:%M')} to {window_end.strftime('%Y-%m-%d %H:%M')} UTC",
        f"",
        f"You have {len(events)} alert(s) in this digest:",
        f"",
        "=" * 50
    ]
    
    for i, event in enumerate(events, 1):
        severity = event.get('severity', 3)
        severity_label = {1: 'Low', 2: 'Medium', 3: 'High', 4: 'Critical', 5: 'Severe'}.get(severity, 'Medium')
        region = event.get('scope_region', 'Global')
        
        body_parts.append(f"")
        body_parts.append(f"{i}. [{severity_label}] {event['headline']}")
        body_parts.append(f"   Type: {event['alert_type']} | Region: {region}")
        if event.get('body'):
            body_parts.append(f"   {event['body'][:200]}...")
        body_parts.append(f"")
    
    body_parts.extend([
        "=" * 50,
        "",
        f"View all alerts in your dashboard: {ALERTS_APP_BASE_URL}/dashboard",
        "",
        "---",
        "You received this digest because you have digest alerts enabled.",
        "Manage your preferences at: " + ALERTS_APP_BASE_URL + "/settings/alerts"
    ])
    
    return subject, "\n".join(body_parts)


def format_telegram_digest(events: List[Dict], window_start: datetime, window_end: datetime) -> str:
    """
    Format digest content for Telegram.
    Keep it concise for Telegram's message limits.
    """
    date_str = window_start.strftime('%b %d')
    
    parts = [
        f"*EnergyRiskIQ Digest* - {date_str}",
        f"_{len(events)} alert(s)_",
        ""
    ]
    
    for i, event in enumerate(events[:10], 1):
        severity = event.get('severity', 3)
        emoji = {1: '🟢', 2: '🟡', 3: '🟠', 4: '🔴', 5: '🚨'}.get(severity, '🟠')
        headline = event['headline'][:60]
        if len(event['headline']) > 60:
            headline += "..."
        
        parts.append(f"{emoji} {headline}")
    
    if len(events) > 10:
        parts.append(f"_...and {len(events) - 10} more_")
    
    parts.extend([
        "",
        f"[View Dashboard]({ALERTS_APP_BASE_URL}/dashboard)"
    ])
    
    return "\n".join(parts)
