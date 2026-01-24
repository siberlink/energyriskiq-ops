"""
Trader Plan Delivery Worker

Handles alert delivery for Trader Plan users:
- Email: Up to 8 per day (batched by 30-min windows), prioritized by risk score
- Telegram: All alerts (enabled for Trader plan)
- No GERI (Pro+ only)
"""

import os
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Tuple

from src.db.db import get_cursor
from src.alerts.channel_adapters import send_email_v2, send_telegram_v2

logger = logging.getLogger(__name__)

EMAIL_FROM_NAME = "EnergyRiskIQ"
EMAIL_FROM_ADDRESS = "alerts@energyriskiq.com"
TRADER_DAILY_EMAIL_LIMIT = 8


def get_trader_users() -> List[Dict]:
    """
    Get all Trader plan users with verified emails.
    """
    with get_cursor(commit=False) as cursor:
        cursor.execute("""
            SELECT u.id, u.email, u.telegram_chat_id
            FROM users u
            JOIN user_plans up ON u.id = up.user_id
            WHERE up.plan = 'trader'
              AND u.email_verified = true
        """)
        return [dict(row) for row in cursor.fetchall()]


def get_user_configured_regions(user_id: int) -> List[str]:
    """
    Get the regions a user has configured for alerts from user_settings table.
    """
    with get_cursor(commit=False) as cursor:
        cursor.execute("""
            SELECT DISTINCT region 
            FROM user_settings 
            WHERE user_id = %s 
              AND enabled = true
              AND region IS NOT NULL
        """, (user_id,))
        return [row['region'] for row in cursor.fetchall()]


def get_current_batch_window() -> datetime:
    """
    Get the current 30-minute batch window timestamp.
    Windows: :00, :30
    """
    now = datetime.now(timezone.utc)
    window_minute = (now.minute // 30) * 30
    return now.replace(minute=window_minute, second=0, microsecond=0)


def get_user_email_count_today(user_id: int) -> int:
    """
    Count how many distinct batch windows have been used today for emails.
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


def has_email_been_sent_this_window(user_id: int, batch_window: datetime) -> bool:
    """
    Check if an email was already sent to this user in the current batch window.
    Prevents multiple emails within the same 30-minute window.
    """
    with get_cursor(commit=False) as cursor:
        cursor.execute("""
            SELECT 1 FROM user_alert_deliveries
            WHERE user_id = %s
              AND channel = 'email'
              AND status = 'sent'
              AND batch_window = %s
            LIMIT 1
        """, (user_id, batch_window))
        return cursor.fetchone() is not None


def get_unsent_alerts_for_user(user_id: int, regions: List[str], since_minutes: int = 30) -> List[Dict]:
    """
    Get alerts from the last N minutes that haven't been sent to this user.
    If regions provided, filters by those regions. Otherwise returns ALL alerts.
    Ordered by risk score (confidence) descending.
    """
    since = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
    
    with get_cursor(commit=False) as cursor:
        if regions:
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
        else:
            cursor.execute("""
                SELECT ae.id, ae.alert_type, ae.headline, ae.body, ae.severity,
                       ae.scope_region as region, ae.confidence as risk_score,
                       ae.created_at
                FROM alert_events ae
                WHERE ae.created_at >= %s
                  AND NOT EXISTS (
                      SELECT 1 FROM user_alert_deliveries uad
                      WHERE uad.alert_event_id = ae.id
                        AND uad.user_id = %s
                        AND uad.channel = 'email'
                  )
                ORDER BY ae.confidence DESC NULLS LAST, ae.severity DESC NULLS LAST
            """, (since, user_id))
        return [dict(row) for row in cursor.fetchall()]


def get_unsent_alerts_for_telegram(user_id: int, regions: List[str], since_minutes: int = 30) -> List[Dict]:
    """
    Get alerts for Telegram delivery (all alerts, not limited).
    If regions provided, filters by those regions. Otherwise returns ALL alerts.
    """
    since = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
    
    with get_cursor(commit=False) as cursor:
        if regions:
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
        else:
            cursor.execute("""
                SELECT ae.id, ae.alert_type, ae.headline, ae.body, ae.severity,
                       ae.scope_region as region, ae.confidence as risk_score,
                       ae.created_at
                FROM alert_events ae
                WHERE ae.created_at >= %s
                  AND NOT EXISTS (
                      SELECT 1 FROM user_alert_deliveries uad
                      WHERE uad.alert_event_id = ae.id
                        AND uad.user_id = %s
                        AND uad.channel = 'telegram'
                  )
                ORDER BY ae.created_at DESC
            """, (since, user_id))
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
    if user_regions:
        body_parts.append(f"Your configured regions: {', '.join(user_regions)}")
    else:
        body_parts.append("Your configured regions: All regions (no filter)")
    body_parts.append("To update your alert preferences, visit your account settings at:")
    body_parts.append("https://www.energyriskiq.com/users-account")
    body_parts.append("")
    body_parts.append("Upgrade to Pro for GERI daily index and more features:")
    body_parts.append("https://www.energyriskiq.com/pricing")
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


def run_trader_delivery(since_minutes: int = 30) -> Dict:
    """
    Main function to run Trader plan delivery.
    Called every 30 minutes by GitHub Actions.
    
    Returns summary statistics.
    """
    logger.info(f"Starting Trader delivery run for last {since_minutes} minutes")
    
    run_batch_window = get_current_batch_window()
    
    stats = {
        "users_processed": 0,
        "emails_sent": 0,
        "telegrams_sent": 0,
        "alerts_delivered": 0,
        "errors": []
    }
    
    trader_users = get_trader_users()
    logger.info(f"Found {len(trader_users)} Trader users")
    
    for user in trader_users:
        user_id = user['id']
        email = user['email']
        chat_id = user.get('telegram_chat_id')
        
        try:
            regions = get_user_configured_regions(user_id)
            
            if not regions:
                logger.info(f"User {user_id} has no configured regions, will receive ALL alerts")
            
            if has_email_been_sent_this_window(user_id, run_batch_window):
                logger.debug(f"User {user_id} already received email in this window, skipping")
            else:
                emails_today = get_user_email_count_today(user_id)
                remaining_emails = TRADER_DAILY_EMAIL_LIMIT - emails_today
                
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
    
    logger.info(f"Trader delivery complete: {stats}")
    return stats
