import logging
import os
import sys
import json
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.db.db import get_cursor, execute_query, execute_one
from src.db.migrations import run_migrations
from src.alerts.templates import (
    format_regional_risk_spike,
    format_asset_risk_spike,
    format_high_impact_event
)
from src.alerts.channels import send_email, send_telegram

logging.basicConfig(
    level=os.environ.get('LOG_LEVEL', 'INFO'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

ALERTS_LOOP = os.environ.get('ALERTS_LOOP', 'false').lower() == 'true'
ALERTS_LOOP_INTERVAL = int(os.environ.get('ALERTS_LOOP_INTERVAL', '600'))

DEFAULT_THRESHOLD = 70
HIGH_IMPACT_REGIONS = ['Europe', 'Middle East', 'Black Sea']
HIGH_IMPACT_CATEGORIES = ['energy', 'geopolitical']

PLAN_DEFAULTS = {
    'free': {
        'alerts_delay_minutes': 60,
        'max_alerts_per_day': 2,
        'allow_asset_alerts': False,
        'allow_telegram': False,
        'daily_digest_enabled': False
    },
    'trader': {
        'alerts_delay_minutes': 0,
        'max_alerts_per_day': 20,
        'allow_asset_alerts': True,
        'allow_telegram': False,
        'daily_digest_enabled': True
    },
    'pro': {
        'alerts_delay_minutes': 0,
        'max_alerts_per_day': 50,
        'allow_asset_alerts': True,
        'allow_telegram': True,
        'daily_digest_enabled': True
    }
}


def get_risk_summary(region: str = 'Europe') -> Dict:
    idx_query = """
    SELECT window_days, risk_score, trend
    FROM risk_indices
    WHERE LOWER(region) = LOWER(%s)
    ORDER BY calculated_at DESC
    LIMIT 2
    """
    idx_results = execute_query(idx_query, (region,))
    
    risk_7d = None
    trend_7d = None
    risk_30d = None
    
    for row in idx_results:
        if row['window_days'] == 7 and risk_7d is None:
            risk_7d = row['risk_score']
            trend_7d = row['trend']
        elif row['window_days'] == 30 and risk_30d is None:
            risk_30d = row['risk_score']
    
    asset_query = """
    SELECT DISTINCT ON (asset) asset, risk_score, direction
    FROM asset_risk
    WHERE LOWER(region) = LOWER(%s) AND window_days = 7
    ORDER BY asset, calculated_at DESC
    """
    asset_results = execute_query(asset_query, (region,))
    
    assets = {}
    for row in asset_results:
        assets[row['asset']] = {
            'risk': row['risk_score'],
            'direction': row['direction']
        }
    
    return {
        'region': region,
        'risk_7d': risk_7d or 0,
        'trend_7d': trend_7d or 'stable',
        'risk_30d': risk_30d or 0,
        'assets': assets
    }


def get_previous_risk_score(region: str) -> Optional[float]:
    query = """
    SELECT last_7d_score FROM alert_state
    WHERE LOWER(region) = LOWER(%s) AND window_days = 7
    """
    result = execute_one(query, (region,))
    return result['last_7d_score'] if result else None


def update_alert_state(region: str, risk_7d: float, risk_30d: float, assets: Dict):
    with get_cursor() as cursor:
        cursor.execute(
            """INSERT INTO alert_state (region, window_days, last_7d_score, last_30d_score, last_asset_scores, updated_at)
               VALUES (%s, 7, %s, %s, %s, NOW())
               ON CONFLICT (region, window_days) DO UPDATE SET
                   last_7d_score = EXCLUDED.last_7d_score,
                   last_30d_score = EXCLUDED.last_30d_score,
                   last_asset_scores = EXCLUDED.last_asset_scores,
                   updated_at = NOW()""",
            (region, risk_7d, risk_30d, json.dumps(assets))
        )


def get_top_driver_events(region: str, limit: int = 3) -> List[Dict]:
    query = """
    SELECT e.title, e.region, e.category, r.weighted_score
    FROM risk_events r
    JOIN events e ON e.id = r.event_id
    WHERE r.created_at >= NOW() - INTERVAL '7 days'
    ORDER BY r.weighted_score DESC
    LIMIT %s
    """
    return execute_query(query, (limit,))


def get_high_impact_events() -> List[Dict]:
    query = """
    SELECT e.id, e.title, e.region, e.category, e.severity_score, e.ai_summary, e.source_url, e.processed
    FROM events e
    WHERE e.severity_score >= 4
      AND e.category IN ('energy', 'geopolitical')
      AND e.region IN ('Europe', 'Middle East', 'Black Sea')
      AND e.inserted_at >= NOW() - INTERVAL '24 hours'
      AND NOT EXISTS (
          SELECT 1 FROM alerts a 
          WHERE a.alert_type = 'HIGH_IMPACT_EVENT' 
          AND a.message LIKE '%%' || e.title || '%%'
          AND a.created_at >= NOW() - INTERVAL '24 hours'
      )
    ORDER BY e.severity_score DESC, e.inserted_at DESC
    LIMIT 10
    """
    return execute_query(query)


def get_users_with_plans() -> List[Dict]:
    query = """
    SELECT u.id, u.email, u.telegram_chat_id,
           p.plan, p.alerts_delay_minutes, p.max_alerts_per_day,
           p.allow_asset_alerts, p.allow_telegram, p.daily_digest_enabled
    FROM users u
    JOIN user_plans p ON p.user_id = u.id
    """
    return execute_query(query)


def get_user_prefs(user_id: int) -> List[Dict]:
    query = """
    SELECT id, region, alert_type, asset, threshold, enabled, cooldown_minutes
    FROM user_alert_prefs
    WHERE user_id = %s AND enabled = TRUE
    """
    return execute_query(query, (user_id,))


def count_alerts_today(user_id: int) -> int:
    query = """
    SELECT COUNT(*) as cnt FROM alerts
    WHERE user_id = %s
      AND created_at >= CURRENT_DATE
      AND status IN ('sent', 'queued')
    """
    result = execute_one(query, (user_id,))
    return result['cnt'] if result else 0


def check_cooldown(user_id: int, cooldown_key: str, cooldown_minutes: int) -> bool:
    query = """
    SELECT 1 FROM alerts
    WHERE cooldown_key = %s
      AND created_at >= NOW() - make_interval(mins => %s)
      AND status IN ('sent', 'queued')
    LIMIT 1
    """
    result = execute_one(query, (cooldown_key, cooldown_minutes))
    return result is not None


def create_alert(user_id: int, alert_type: str, region: str, asset: Optional[str],
                 triggered_value: Optional[float], threshold: Optional[float],
                 title: str, message: str, channel: str, cooldown_key: str,
                 status: str = 'queued') -> int:
    with get_cursor() as cursor:
        cursor.execute(
            """INSERT INTO alerts (user_id, alert_type, region, asset, triggered_value, threshold,
                                   title, message, channel, cooldown_key, status)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               RETURNING id""",
            (user_id, alert_type, region, asset, triggered_value, threshold,
             title, message, channel, cooldown_key, status)
        )
        result = cursor.fetchone()
        return result['id'] if result else 0


def update_alert_status(alert_id: int, status: str, error: Optional[str] = None):
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


def evaluate_regional_risk_spike(user: Dict, pref: Dict, summary: Dict, prev_risk: Optional[float]) -> Optional[Dict]:
    risk_7d = summary['risk_7d']
    threshold = pref.get('threshold') or DEFAULT_THRESHOLD
    
    spike_by_threshold = risk_7d >= threshold
    
    spike_by_change = False
    if prev_risk and prev_risk > 0:
        change_pct = ((risk_7d - prev_risk) / prev_risk) * 100
        spike_by_change = change_pct >= 20
    
    if not (spike_by_threshold or spike_by_change):
        return None
    
    driver_events = get_top_driver_events(pref['region'])
    
    title, message = format_regional_risk_spike(
        region=pref['region'],
        risk_7d=risk_7d,
        prev_risk_7d=prev_risk,
        trend=summary['trend_7d'],
        driver_events=driver_events,
        assets=summary['assets']
    )
    
    return {
        'alert_type': 'REGIONAL_RISK_SPIKE',
        'region': pref['region'],
        'asset': None,
        'triggered_value': risk_7d,
        'threshold': threshold,
        'title': title,
        'message': message
    }


def evaluate_asset_risk_spike(user: Dict, pref: Dict, summary: Dict) -> Optional[Dict]:
    if not user.get('allow_asset_alerts'):
        return None
    
    asset = pref.get('asset')
    if not asset or asset not in summary['assets']:
        return None
    
    asset_data = summary['assets'][asset]
    risk_score = asset_data.get('risk', 0)
    direction = asset_data.get('direction', 'unclear')
    threshold = pref.get('threshold') or DEFAULT_THRESHOLD
    
    spike = risk_score >= threshold
    
    if not spike:
        return None
    
    driver_events = get_top_driver_events(pref['region'], limit=2)
    
    title, message = format_asset_risk_spike(
        asset=asset,
        region=pref['region'],
        risk_score=risk_score,
        direction=direction,
        confidence=0.7,
        driver_events=driver_events
    )
    
    return {
        'alert_type': 'ASSET_RISK_SPIKE',
        'region': pref['region'],
        'asset': asset,
        'triggered_value': risk_score,
        'threshold': threshold,
        'title': title,
        'message': message
    }


def evaluate_high_impact_events(user: Dict, pref: Dict) -> List[Dict]:
    events = get_high_impact_events()
    alerts = []
    
    for event in events:
        if event['region'] != pref['region'] and pref['region'] != 'global':
            continue
        
        title, message = format_high_impact_event(event, event['region'])
        
        alerts.append({
            'alert_type': 'HIGH_IMPACT_EVENT',
            'region': event['region'],
            'asset': None,
            'triggered_value': float(event['severity_score']),
            'threshold': 4.0,
            'title': title,
            'message': message,
            'event_id': event['id']
        })
    
    return alerts


def process_user_alerts(user: Dict, dry_run: bool = False) -> List[Dict]:
    user_id = user['id']
    plan = user['plan']
    
    alerts_today = count_alerts_today(user_id)
    max_per_day = user.get('max_alerts_per_day', PLAN_DEFAULTS[plan]['max_alerts_per_day'])
    quota_left = max_per_day - alerts_today
    
    if quota_left <= 0 and not dry_run:
        logger.info(f"User {user_id} hit max alerts/day ({max_per_day})")
        return []
    
    prefs = get_user_prefs(user_id)
    generated_alerts = []
    
    for pref in prefs:
        if quota_left <= 0 and not dry_run:
            logger.info(f"User {user_id} quota exhausted, skipping remaining prefs")
            break
        
        alert_type = pref['alert_type']
        
        if plan == 'free' and alert_type not in ['REGIONAL_RISK_SPIKE']:
            continue
        
        if plan == 'free' and pref['region'] != 'Europe':
            continue
        
        if alert_type == 'ASSET_RISK_SPIKE' and not user.get('allow_asset_alerts'):
            continue
        
        summary = get_risk_summary(pref['region'])
        prev_risk = get_previous_risk_score(pref['region'])
        
        alert_data = None
        
        if alert_type == 'REGIONAL_RISK_SPIKE':
            alert_data = evaluate_regional_risk_spike(user, pref, summary, prev_risk)
        elif alert_type == 'ASSET_RISK_SPIKE':
            alert_data = evaluate_asset_risk_spike(user, pref, summary)
        elif alert_type == 'HIGH_IMPACT_EVENT':
            event_alerts = evaluate_high_impact_events(user, pref)
            for ea in event_alerts:
                if quota_left <= 0 and not dry_run:
                    break
                cooldown_key = f"user:{user_id}|type:{ea['alert_type']}|region:{ea['region']}|event:{ea.get('event_id')}"
                if not check_cooldown(user_id, cooldown_key, pref['cooldown_minutes']):
                    ea['cooldown_key'] = cooldown_key
                    ea['pref'] = pref
                    generated_alerts.append(ea)
                    quota_left -= 1
            continue
        
        if alert_data:
            cooldown_key = f"user:{user_id}|type:{alert_type}|region:{pref['region']}|asset:{pref.get('asset')}"
            
            if check_cooldown(user_id, cooldown_key, pref['cooldown_minutes']):
                logger.debug(f"Alert for user {user_id} in cooldown")
                continue
            
            alert_data['cooldown_key'] = cooldown_key
            alert_data['pref'] = pref
            generated_alerts.append(alert_data)
            quota_left -= 1
    
    return generated_alerts


def send_alert(user: Dict, alert_data: Dict, alert_id: int) -> bool:
    channel = 'email'
    
    if user.get('allow_telegram') and user.get('telegram_chat_id'):
        channel = 'telegram'
    
    delay_minutes = user.get('alerts_delay_minutes', 0)
    if delay_minutes > 0:
        logger.info(f"Alert {alert_id} delayed by {delay_minutes} minutes (free tier)")
    
    if channel == 'telegram':
        success, error = send_telegram(user['telegram_chat_id'], alert_data['message'])
    else:
        success, error = send_email(user['email'], alert_data['title'], alert_data['message'])
    
    if success:
        update_alert_status(alert_id, 'sent')
    else:
        update_alert_status(alert_id, 'failed', error)
    
    return success


def run_alerts_engine(dry_run: bool = False, user_id_filter: Optional[int] = None):
    logger.info("=" * 60)
    logger.info("Starting EnergyRiskIQ Alerts Engine")
    logger.info(f"Dry run: {dry_run}")
    logger.info("=" * 60)
    
    run_migrations()
    
    users = get_users_with_plans()
    
    if user_id_filter:
        users = [u for u in users if u['id'] == user_id_filter]
    
    if not users:
        logger.info("No users found with plans")
        return []
    
    logger.info(f"Processing {len(users)} users")
    
    all_alerts = []
    
    for user in users:
        try:
            user_id = user['id']
            logger.debug(f"Processing user {user_id} ({user['plan']})")
            
            generated_alerts = process_user_alerts(user, dry_run)
            
            for alert_data in generated_alerts:
                channel = 'telegram' if user.get('allow_telegram') and user.get('telegram_chat_id') else 'email'
                
                if dry_run:
                    all_alerts.append({
                        'user_id': user_id,
                        'email': user['email'],
                        'plan': user['plan'],
                        'channel': channel,
                        **alert_data
                    })
                else:
                    alert_id = create_alert(
                        user_id=user_id,
                        alert_type=alert_data['alert_type'],
                        region=alert_data['region'],
                        asset=alert_data.get('asset'),
                        triggered_value=alert_data.get('triggered_value'),
                        threshold=alert_data.get('threshold'),
                        title=alert_data['title'],
                        message=alert_data['message'],
                        channel=channel,
                        cooldown_key=alert_data['cooldown_key']
                    )
                    
                    if alert_id:
                        send_alert(user, alert_data, alert_id)
                        all_alerts.append({'id': alert_id, **alert_data})
        
        except Exception as e:
            logger.error(f"Error processing user {user.get('id')}: {e}")
            continue
    
    summary = get_risk_summary('Europe')
    update_alert_state('Europe', summary['risk_7d'], summary['risk_30d'], summary['assets'])
    
    logger.info(f"Processed {len(all_alerts)} alerts")
    logger.info("=" * 60)
    logger.info("Alerts Engine Complete")
    logger.info("=" * 60)
    
    return all_alerts


def run_alerts_loop():
    logger.info("Starting alerts engine in loop mode")
    logger.info(f"Interval: {ALERTS_LOOP_INTERVAL} seconds")
    
    while True:
        try:
            run_alerts_engine()
        except Exception as e:
            logger.error(f"Alerts engine error: {e}")
        
        logger.info(f"Sleeping for {ALERTS_LOOP_INTERVAL} seconds...")
        time.sleep(ALERTS_LOOP_INTERVAL)


if __name__ == "__main__":
    if ALERTS_LOOP:
        run_alerts_loop()
    else:
        run_alerts_engine()
