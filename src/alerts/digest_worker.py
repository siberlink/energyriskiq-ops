import logging
import os
import sys
from datetime import datetime, timezone
from typing import List, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.db.db import get_cursor, execute_query, execute_one
from src.db.migrations import run_migrations
from src.alerts.channels import send_email
from src.alerts.templates import format_daily_digest

logging.basicConfig(
    level=os.environ.get('LOG_LEVEL', 'INFO'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_utc_today_date() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%d')


def get_digest_eligible_users() -> List[Dict]:
    query = """
    SELECT u.id, u.email, u.telegram_chat_id,
           p.plan, p.daily_digest_enabled
    FROM users u
    JOIN user_plans p ON p.user_id = u.id
    WHERE p.daily_digest_enabled = TRUE
      AND p.plan IN ('trader', 'pro')
    """
    return execute_query(query)


def has_digest_today(user_id: int, date_str: str) -> bool:
    cooldown_key = f"user:{user_id}|type:DAILY_DIGEST|date:{date_str}"
    query = """
    SELECT 1 FROM alerts
    WHERE cooldown_key = %s
      AND status IN ('sent', 'queued')
    LIMIT 1
    """
    result = execute_one(query, (cooldown_key,))
    return result is not None


def get_risk_indices(region: str = 'Europe') -> Dict:
    query = """
    SELECT window_days, risk_score, trend
    FROM risk_indices
    WHERE LOWER(region) = LOWER(%s)
    ORDER BY calculated_at DESC
    """
    results = execute_query(query, (region,))
    
    risk_7d = 0
    trend_7d = 'stable'
    risk_30d = 0
    trend_30d = 'stable'
    
    seen_7d = False
    seen_30d = False
    
    for row in results:
        if row['window_days'] == 7 and not seen_7d:
            risk_7d = row['risk_score']
            trend_7d = row['trend']
            seen_7d = True
        elif row['window_days'] == 30 and not seen_30d:
            risk_30d = row['risk_score']
            trend_30d = row['trend']
            seen_30d = True
        if seen_7d and seen_30d:
            break
    
    return {
        'risk_7d': risk_7d,
        'trend_7d': trend_7d,
        'risk_30d': risk_30d,
        'trend_30d': trend_30d
    }


def get_top_driver_events_24h(region: str = 'Europe', limit: int = 3) -> List[Dict]:
    query = """
    SELECT e.title, e.category, e.region, e.source_url, e.ai_summary, r.weighted_score
    FROM risk_events r
    JOIN events e ON e.id = r.event_id
    WHERE r.created_at >= NOW() - INTERVAL '24 hours'
    ORDER BY r.weighted_score DESC
    LIMIT %s
    """
    return execute_query(query, (limit,))


def get_asset_snapshot(region: str = 'Europe') -> Dict:
    query = """
    SELECT DISTINCT ON (asset) asset, risk_score, direction
    FROM asset_risk
    WHERE LOWER(region) = LOWER(%s) AND window_days = 7
    ORDER BY asset, calculated_at DESC
    """
    results = execute_query(query, (region,))
    
    assets = {}
    for row in results:
        assets[row['asset']] = {
            'risk': row['risk_score'],
            'direction': row['direction']
        }
    
    return assets


def build_digest_content(region: str = 'Europe') -> tuple:
    date_str = get_utc_today_date()
    
    risk_data = get_risk_indices(region)
    top_events = get_top_driver_events_24h(region)
    assets = get_asset_snapshot(region)
    
    subject = f"EnergyRiskIQ Daily Digest — {region} Risk {risk_data['risk_7d']:.0f} ({risk_data['trend_7d']})"
    
    body = f"""ENERGYRISKIQ DAILY DIGEST
{region} | {date_str}

RISK OVERVIEW
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
7-Day Risk Index: {risk_data['risk_7d']:.0f}/100 ({risk_data['trend_7d']})
30-Day Risk Index: {risk_data['risk_30d']:.0f}/100

ASSET RISK SNAPSHOT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    
    for asset in ['oil', 'gas', 'fx', 'freight']:
        if asset in assets:
            data = assets[asset]
            body += f"  {asset.upper()}: {data['risk']:.0f}/100 ({data['direction']})\n"
        else:
            body += f"  {asset.upper()}: N/A\n"
    
    body += f"""
TOP RISK DRIVERS (Last 24h)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    
    if top_events:
        for i, event in enumerate(top_events, 1):
            title = event.get('title', 'Unknown')[:70]
            category = event.get('category', 'Unknown')
            ev_region = event.get('region', 'Unknown')
            body += f"{i}. {title}\n"
            body += f"   Category: {category} | Region: {ev_region}\n"
            
            ai_summary = event.get('ai_summary')
            if ai_summary:
                body += f"   Summary: {ai_summary[:150]}...\n"
            
            source_url = event.get('source_url')
            if source_url:
                body += f"   Source: {source_url}\n"
            body += "\n"
    else:
        body += "No significant risk events in the last 24 hours.\n"
    
    body += """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Informational only. Not financial advice.

EnergyRiskIQ - Energy Risk Intelligence
"""
    
    return subject, body


def create_digest_alert(user_id: int, subject: str, body: str, cooldown_key: str, status: str = 'queued') -> int:
    with get_cursor() as cursor:
        cursor.execute(
            """INSERT INTO alerts (user_id, alert_type, region, title, message, channel, cooldown_key, status)
               VALUES (%s, 'DAILY_DIGEST', 'Europe', %s, %s, 'email', %s, %s)
               RETURNING id""",
            (user_id, subject, body, cooldown_key, status)
        )
        result = cursor.fetchone()
        return result['id'] if result else 0


def update_digest_status(alert_id: int, status: str, error: Optional[str] = None):
    with get_cursor() as cursor:
        if status == 'sent':
            cursor.execute(
                "UPDATE alerts SET status = %s, sent_at = NOW(), error = %s WHERE id = %s",
                (status, error, alert_id)
            )
        else:
            cursor.execute(
                "UPDATE alerts SET status = %s, error = %s WHERE id = %s",
                (status, error, alert_id)
            )


def run_digest_worker() -> Dict:
    logger.info("=" * 60)
    logger.info("Starting EnergyRiskIQ Daily Digest Worker")
    logger.info("=" * 60)
    
    run_migrations()
    
    date_str = get_utc_today_date()
    users = get_digest_eligible_users()
    
    if not users:
        logger.info("No users eligible for daily digest")
        return {"processed": 0, "sent": 0, "skipped": 0, "failed": 0}
    
    logger.info(f"Found {len(users)} digest-eligible users")
    
    subject, body = build_digest_content('Europe')
    
    sent_count = 0
    skipped_count = 0
    failed_count = 0
    
    for user in users:
        user_id = user['id']
        email = user['email']
        
        if has_digest_today(user_id, date_str):
            logger.info(f"User {user_id} already received digest today, skipping")
            skipped_count += 1
            continue
        
        cooldown_key = f"user:{user_id}|type:DAILY_DIGEST|date:{date_str}"
        
        alert_id = create_digest_alert(user_id, subject, body, cooldown_key)
        
        if not alert_id:
            logger.error(f"Failed to create digest alert for user {user_id}")
            failed_count += 1
            continue
        
        success, error, _ = send_email(email, subject, body)
        
        if success:
            update_digest_status(alert_id, 'sent')
            logger.info(f"Digest sent to user {user_id} ({email})")
            sent_count += 1
        else:
            update_digest_status(alert_id, 'failed', error)
            logger.error(f"Failed to send digest to user {user_id}: {error}")
            failed_count += 1
    
    logger.info("=" * 60)
    logger.info(f"Digest Worker Complete: sent={sent_count}, skipped={skipped_count}, failed={failed_count}")
    logger.info("=" * 60)
    
    return {
        "processed": len(users),
        "sent": sent_count,
        "skipped": skipped_count,
        "failed": failed_count
    }


if __name__ == "__main__":
    run_digest_worker()
