"""
Pro Plan Delivery Worker

Handles alert and GERI delivery for Pro Plan users:
- Email: Up to 15 per day (batched by 15-min windows), prioritized by risk score
- Telegram: All alerts + GERI
"""

import os
import logging
from datetime import datetime, timezone, timedelta, date
from typing import List, Dict, Optional, Tuple
from collections import defaultdict

from src.db.db import get_cursor
from src.alerts.channel_adapters import send_email_v2, send_telegram_v2
from src.geri.repo import get_latest_index

logger = logging.getLogger(__name__)

EMAIL_FROM_NAME = "EnergyRiskIQ"
EMAIL_FROM_ADDRESS = "alerts@energyriskiq.com"
DAILY_EMAIL_LIMIT = 15
GERI_EMAIL_RESERVED = 1


def get_pro_users_with_telegram() -> List[Dict]:
    """
    Get all Pro plan users with their email and Telegram chat_id.
    """
    with get_cursor(commit=False) as cursor:
        cursor.execute("""
            SELECT u.id, u.email, u.telegram_chat_id
            FROM users u
            JOIN user_plans up ON u.id = up.user_id
            WHERE up.plan = 'pro'
              AND u.email_verified = true
        """)
        return [dict(row) for row in cursor.fetchall()]


def get_user_configured_regions(user_id: int) -> List[str]:
    """
    Get the regions a user has configured for alerts.
    """
    with get_cursor(commit=False) as cursor:
        cursor.execute("""
            SELECT DISTINCT region 
            FROM user_alert_prefs 
            WHERE user_id = %s 
              AND enabled = true
              AND region IS NOT NULL
        """, (user_id,))
        return [row['region'] for row in cursor.fetchall()]


def get_current_batch_window() -> datetime:
    """
    Get the current 15-minute batch window timestamp.
    Windows: :00, :15, :30, :45
    """
    now = datetime.now(timezone.utc)
    window_minute = (now.minute // 15) * 15
    return now.replace(minute=window_minute, second=0, microsecond=0)


def get_user_email_count_today(user_id: int) -> int:
    """
    Count how many distinct 15-minute email batch windows have been used today (UTC).
    Each batch_window counts as 1 toward the daily limit.
    """
    utc_now = datetime.now(timezone.utc)
    today_start = datetime.combine(utc_now.date(), datetime.min.time(), tzinfo=timezone.utc)
    
    with get_cursor(commit=False) as cursor:
        cursor.execute("""
            SELECT COUNT(DISTINCT batch_window) as batch_count
            FROM user_alert_deliveries
            WHERE user_id = %s
              AND channel = 'email'
              AND status = 'sent'
              AND sent_at >= %s
              AND batch_window IS NOT NULL
        """, (user_id, today_start))
        row = cursor.fetchone()
        return row['batch_count'] if row else 0


def get_unsent_alerts_for_user(user_id: int, regions: List[str], since_minutes: int = 15) -> List[Dict]:
    """
    Get alerts from the last N minutes that haven't been sent to this user.
    Filtered by user's configured regions.
    Ordered by risk score (confidence) descending.
    """
    since = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
    
    if not regions:
        return []
    
    with get_cursor(commit=False) as cursor:
        cursor.execute("""
            SELECT ae.id, ae.alert_type, ae.headline, ae.body, ae.severity,
                   ae.scope_region as region, ae.confidence as risk_score,
                   ae.created_at
            FROM alert_events ae
            WHERE ae.created_at >= %s
              AND ae.scope_region = ANY(%s)
              AND NOT EXISTS (
                  SELECT 1 FROM user_alert_deliveries uad
                  WHERE uad.alert_event_id = ae.id
                    AND uad.user_id = %s
                    AND uad.channel = 'email'
              )
            ORDER BY ae.confidence DESC NULLS LAST, ae.severity DESC NULLS LAST
        """, (since, regions, user_id))
        return [dict(row) for row in cursor.fetchall()]


def get_unsent_alerts_for_telegram(user_id: int, regions: List[str], since_minutes: int = 15) -> List[Dict]:
    """
    Get alerts for Telegram delivery (all alerts, not limited).
    """
    since = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
    
    if not regions:
        return []
    
    with get_cursor(commit=False) as cursor:
        cursor.execute("""
            SELECT ae.id, ae.alert_type, ae.headline, ae.body, ae.severity,
                   ae.scope_region as region, ae.confidence as risk_score,
                   ae.created_at
            FROM alert_events ae
            WHERE ae.created_at >= %s
              AND ae.scope_region = ANY(%s)
              AND NOT EXISTS (
                  SELECT 1 FROM user_alert_deliveries uad
                  WHERE uad.alert_event_id = ae.id
                    AND uad.user_id = %s
                    AND uad.channel = 'telegram'
              )
            ORDER BY ae.created_at DESC
        """, (since, regions, user_id))
        return [dict(row) for row in cursor.fetchall()]


def record_delivery(user_id: int, alert_event_id: int, channel: str, 
                   status: str, message_id: Optional[str] = None, 
                   error: Optional[str] = None,
                   batch_window: Optional[datetime] = None) -> int:
    """
    Record an alert delivery in user_alert_deliveries.
    Returns the delivery ID.
    """
    with get_cursor(commit=True) as cursor:
        cursor.execute("""
            INSERT INTO user_alert_deliveries 
                (user_id, alert_event_id, channel, status, provider_message_id, 
                 created_at, sent_at, delivery_kind, last_error, batch_window)
            VALUES (%s, %s, %s, %s, %s, NOW(), NOW(), 'instant', %s, %s)
            ON CONFLICT (alert_event_id, user_id, channel, delivery_kind) 
            DO UPDATE SET status = %s, sent_at = NOW(), last_error = %s, batch_window = %s
            RETURNING id
        """, (user_id, alert_event_id, channel, status, message_id, error, batch_window, 
              status, error, batch_window))
        row = cursor.fetchone()
        return row['id'] if row else 0


def format_alert_email(alerts: List[Dict], user_regions: List[str]) -> Tuple[str, str]:
    """
    Format alerts for email delivery.
    Returns (subject, body)
    """
    if len(alerts) == 1:
        alert = alerts[0]
        subject = f"[EnergyRiskIQ] {alert['alert_type']}: {alert.get('headline', 'New Alert')[:50]}"
    else:
        subject = f"[EnergyRiskIQ] {len(alerts)} New Alerts"
    
    body_parts = []
    body_parts.append("EnergyRiskIQ Alert Notification")
    body_parts.append("=" * 40)
    body_parts.append("")
    
    for i, alert in enumerate(alerts, 1):
        if len(alerts) > 1:
            body_parts.append(f"--- Alert {i} of {len(alerts)} ---")
        
        body_parts.append(f"Type: {alert['alert_type']}")
        body_parts.append(f"Region: {alert.get('region', 'Global')}")
        if alert.get('severity'):
            body_parts.append(f"Severity: {alert['severity']}/5")
        if alert.get('risk_score'):
            body_parts.append(f"Risk Score: {alert['risk_score']:.0f}/100")
        body_parts.append("")
        
        if alert.get('headline'):
            body_parts.append(alert['headline'])
        if alert.get('body'):
            body_parts.append("")
            body_parts.append(alert['body'][:500])
        
        body_parts.append("")
        body_parts.append("-" * 40)
        body_parts.append("")
    
    body_parts.append("---")
    body_parts.append(f"Your configured regions: {', '.join(user_regions)}")
    body_parts.append("To update your alert preferences, visit your account settings at:")
    body_parts.append("https://www.energyriskiq.com/users-account")
    body_parts.append("")
    body_parts.append("---")
    body_parts.append("EnergyRiskIQ - Energy Risk Intelligence")
    body_parts.append("Informational only. Not financial advice.")
    
    return subject, "\n".join(body_parts)


def format_alert_telegram(alert: Dict) -> str:
    """
    Format a single alert for Telegram delivery.
    """
    parts = []
    parts.append(f"*{alert['alert_type']}*")
    parts.append("")
    
    if alert.get('headline'):
        parts.append(alert['headline'])
    
    parts.append("")
    parts.append(f"Region: {alert.get('region', 'Global')}")
    
    if alert.get('severity'):
        parts.append(f"Severity: {alert['severity']}/5")
    if alert.get('risk_score'):
        parts.append(f"Risk Score: {alert['risk_score']:.0f}/100")
    
    if alert.get('body'):
        body_preview = alert['body'][:300]
        if len(alert['body']) > 300:
            body_preview += "..."
        parts.append("")
        parts.append(body_preview)
    
    parts.append("")
    parts.append("---")
    parts.append("_EnergyRiskIQ - Informational only_")
    
    return "\n".join(parts)


def format_geri_email() -> Tuple[Optional[str], Optional[str]]:
    """
    Format GERI for email delivery.
    Returns (subject, body) or (None, None) if no GERI available.
    """
    geri = get_latest_index()
    if not geri:
        return None, None
    
    subject = f"[EnergyRiskIQ] GERI Daily Update: {geri['value']}/100 ({geri['band']})"
    
    body_parts = []
    body_parts.append("Global Energy Risk Index (GERI)")
    body_parts.append("=" * 40)
    body_parts.append("")
    body_parts.append(f"Date: {geri['date']}")
    body_parts.append(f"Value: {geri['value']}/100")
    body_parts.append(f"Risk Band: {geri['band']}")
    
    if geri.get('trend_1d') is not None:
        trend_symbol = "+" if geri['trend_1d'] > 0 else ""
        body_parts.append(f"24h Change: {trend_symbol}{geri['trend_1d']}")
    
    if geri.get('trend_7d') is not None:
        trend_symbol = "+" if geri['trend_7d'] > 0 else ""
        body_parts.append(f"7-Day Change: {trend_symbol}{geri['trend_7d']}")
    
    components = geri.get('components', {})
    if components.get('interpretation'):
        body_parts.append("")
        body_parts.append("Analysis:")
        body_parts.append(components['interpretation'])
    
    if components.get('top_regions'):
        body_parts.append("")
        body_parts.append("Top Regions Under Pressure:")
        for region_data in components['top_regions'][:3]:
            body_parts.append(f"  - {region_data.get('region', 'Unknown')}")
    
    body_parts.append("")
    body_parts.append("---")
    body_parts.append("View full details: https://www.energyriskiq.com/geri")
    body_parts.append("")
    body_parts.append("EnergyRiskIQ - Energy Risk Intelligence")
    body_parts.append("Informational only. Not financial advice.")
    
    return subject, "\n".join(body_parts)


def format_geri_telegram() -> Optional[str]:
    """
    Format GERI for Telegram delivery.
    """
    geri = get_latest_index()
    if not geri:
        return None
    
    parts = []
    parts.append("*GERI Daily Update*")
    parts.append("")
    parts.append(f"Value: *{geri['value']}/100* ({geri['band']})")
    
    if geri.get('trend_1d') is not None:
        trend_symbol = "+" if geri['trend_1d'] > 0 else ""
        parts.append(f"24h: {trend_symbol}{geri['trend_1d']}")
    
    components = geri.get('components', {})
    if components.get('interpretation'):
        parts.append("")
        parts.append(f"_{components['interpretation']}_")
    
    if components.get('top_regions'):
        parts.append("")
        parts.append("Top Regions:")
        for region_data in components['top_regions'][:3]:
            parts.append(f"  - {region_data.get('region', 'Unknown')}")
    
    parts.append("")
    parts.append("[View Details](https://www.energyriskiq.com/geri)")
    
    return "\n".join(parts)


def run_pro_delivery(since_minutes: int = 15) -> Dict:
    """
    Main function to run Pro plan delivery.
    Called every 15 minutes by GitHub Actions.
    
    Returns summary statistics.
    """
    logger.info(f"Starting Pro delivery run for last {since_minutes} minutes")
    
    run_batch_window = get_current_batch_window()
    
    stats = {
        "users_processed": 0,
        "emails_sent": 0,
        "telegrams_sent": 0,
        "alerts_delivered": 0,
        "errors": []
    }
    
    pro_users = get_pro_users_with_telegram()
    logger.info(f"Found {len(pro_users)} Pro users")
    
    for user in pro_users:
        user_id = user['id']
        email = user['email']
        chat_id = user.get('telegram_chat_id')
        
        try:
            regions = get_user_configured_regions(user_id)
            
            if not regions:
                logger.warning(f"User {user_id} has no configured regions, skipping")
                continue
            
            emails_today = get_user_email_count_today(user_id)
            remaining_emails = DAILY_EMAIL_LIMIT - emails_today
            
            email_alerts = get_unsent_alerts_for_user(user_id, regions, since_minutes)
            
            if email_alerts and remaining_emails > 0:
                subject, body = format_alert_email(email_alerts, regions)
                result = send_email_v2(email, subject, body)
                
                if result.success:
                    stats["emails_sent"] += 1
                    for alert in email_alerts:
                        record_delivery(user_id, alert['id'], 'email', 'sent', 
                                       result.message_id, batch_window=run_batch_window)
                        stats["alerts_delivered"] += 1
                else:
                    for alert in email_alerts:
                        record_delivery(user_id, alert['id'], 'email', 'failed',
                                       error=result.error, batch_window=run_batch_window)
                    stats["errors"].append(f"Email to {email}: {result.error}")
            
            if chat_id:
                telegram_alerts = get_unsent_alerts_for_telegram(user_id, regions, since_minutes)
                
                for alert in telegram_alerts:
                    message = format_alert_telegram(alert)
                    result = send_telegram_v2(chat_id, message)
                    
                    if result.success:
                        stats["telegrams_sent"] += 1
                        record_delivery(user_id, alert['id'], 'telegram', 'sent')
                    else:
                        record_delivery(user_id, alert['id'], 'telegram', 'failed',
                                       error=result.error)
                        if not result.should_skip:
                            stats["errors"].append(f"Telegram to {chat_id}: {result.error}")
            
            stats["users_processed"] += 1
            
        except Exception as e:
            logger.error(f"Error processing user {user_id}: {e}")
            stats["errors"].append(f"User {user_id}: {str(e)}")
    
    logger.info(f"Pro delivery complete: {stats}")
    return stats


def send_geri_to_pro_users() -> Dict:
    """
    Send GERI to all Pro users via email and Telegram.
    Called immediately after GERI computation.
    GERI emails count toward the daily 15-email limit.
    
    Returns summary statistics.
    """
    logger.info("Starting GERI delivery to Pro users")
    
    stats = {
        "users_processed": 0,
        "emails_sent": 0,
        "telegrams_sent": 0,
        "errors": []
    }
    
    subject, body = format_geri_email()
    if not subject:
        logger.warning("No GERI available for delivery")
        return stats
    
    telegram_message = format_geri_telegram()
    batch_window = get_current_batch_window()
    
    pro_users = get_pro_users_with_telegram()
    logger.info(f"Sending GERI to {len(pro_users)} Pro users")
    
    for user in pro_users:
        user_id = user['id']
        email = user['email']
        chat_id = user.get('telegram_chat_id')
        
        try:
            emails_today = get_user_email_count_today(user_id)
            
            if emails_today < DAILY_EMAIL_LIMIT:
                result = send_email_v2(email, subject, body)
                if result.success:
                    stats["emails_sent"] += 1
                    record_geri_delivery(user_id, 'email', 'sent', batch_window)
                else:
                    stats["errors"].append(f"GERI email to {email}: {result.error}")
                    record_geri_delivery(user_id, 'email', 'failed', batch_window, result.error)
            
            if chat_id and telegram_message:
                result = send_telegram_v2(chat_id, telegram_message)
                if result.success:
                    stats["telegrams_sent"] += 1
                else:
                    if not result.should_skip:
                        stats["errors"].append(f"GERI telegram to {chat_id}: {result.error}")
            
            stats["users_processed"] += 1
            
        except Exception as e:
            logger.error(f"Error sending GERI to user {user_id}: {e}")
            stats["errors"].append(f"User {user_id}: {str(e)}")
    
    logger.info(f"GERI delivery complete: {stats}")
    return stats


def record_geri_delivery(user_id: int, channel: str, status: str, 
                         batch_window: datetime, error: Optional[str] = None):
    """
    Record a GERI delivery in user_alert_deliveries.
    Uses alert_event_id = NULL and delivery_kind = 'geri'.
    Uses upsert to prevent duplicate counting for same batch window.
    Matches partial unique index: idx_geri_delivery_unique (user_id, channel, batch_window) 
    WHERE delivery_kind = 'geri' AND batch_window IS NOT NULL
    """
    with get_cursor(commit=True) as cursor:
        cursor.execute("""
            INSERT INTO user_alert_deliveries 
                (user_id, channel, status, delivery_kind, 
                 created_at, sent_at, batch_window, last_error)
            VALUES (%s, %s, %s, 'geri', NOW(), NOW(), %s, %s)
            ON CONFLICT (user_id, channel, batch_window) 
                WHERE delivery_kind = 'geri' AND batch_window IS NOT NULL
            DO UPDATE SET status = EXCLUDED.status, sent_at = NOW(), last_error = EXCLUDED.last_error
        """, (user_id, channel, status, batch_window, error))


def get_last_geri_delivery_date() -> Optional[date]:
    """
    Get the date of the last GERI that was delivered.
    Returns None if no GERI has been delivered yet.
    """
    with get_cursor(commit=False) as cursor:
        cursor.execute("""
            SELECT DATE(batch_window) as geri_date
            FROM user_alert_deliveries
            WHERE delivery_kind = 'geri'
              AND status = 'sent'
            ORDER BY batch_window DESC
            LIMIT 1
        """)
        row = cursor.fetchone()
        return row['geri_date'] if row else None


def send_geri_to_pro_users_if_new() -> Dict:
    """
    Send GERI to Pro users only if there's a new one that hasn't been sent yet.
    Checks if the latest GERI date is newer than the last delivered GERI date.
    
    Returns summary statistics or empty dict if no new GERI.
    """
    geri = get_latest_index()
    if not geri:
        logger.info("No GERI available for delivery")
        return {"skipped": True, "reason": "no_geri_available"}
    
    geri_date = geri.get('date')
    if not geri_date:
        logger.warning("GERI missing date field")
        return {"skipped": True, "reason": "geri_missing_date"}
    
    last_delivered_date = get_last_geri_delivery_date()
    
    if last_delivered_date and last_delivered_date >= geri_date:
        logger.info(f"GERI for {geri_date} already delivered (last: {last_delivered_date})")
        return {"skipped": True, "reason": "already_delivered", "geri_date": str(geri_date)}
    
    logger.info(f"New GERI detected for {geri_date}, triggering delivery")
    return send_geri_to_pro_users()
