import logging
import os
import sys
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.db.db import get_cursor, execute_query, execute_one
from src.db.migrations import run_migrations
from src.alerts.templates import (
    format_regional_risk_spike,
    format_asset_risk_spike,
    format_high_impact_event,
    add_upgrade_hook_if_free
)
from src.alerts.channels import send_email, send_telegram, send_sms
from src.plans.plan_helpers import get_plan_settings, get_allowed_alert_types

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
    
    if idx_results:
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
    if asset_results:
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
    SELECT e.id, e.title, e.region, e.category, e.source_url, e.ai_summary, 
           e.ai_impact_score, e.ai_confidence, r.weighted_score
    FROM risk_events r
    JOIN events e ON e.id = r.event_id
    WHERE r.created_at >= NOW() - INTERVAL '7 days'
    ORDER BY r.weighted_score DESC
    LIMIT %s
    """
    results = execute_query(query, (limit,))
    return results if results else []


def get_high_impact_events(user_id: int) -> List[Dict]:
    query = """
    SELECT e.id, e.title, e.region, e.category, e.severity_score, e.ai_summary, e.source_url, e.processed
    FROM events e
    WHERE e.severity_score >= 4
      AND e.category IN ('energy', 'geopolitical')
      AND e.region IN ('Europe', 'Middle East', 'Black Sea')
      AND e.inserted_at >= NOW() - INTERVAL '24 hours'
      AND NOT EXISTS (
          SELECT 1 FROM alert_events ae
          JOIN user_alert_deliveries uad ON uad.alert_event_id = ae.id
          WHERE uad.user_id = %s
          AND ae.alert_type = 'HIGH_IMPACT_EVENT' 
          AND ae.headline LIKE '%%' || e.title || '%%'
          AND ae.created_at >= NOW() - INTERVAL '24 hours'
      )
    ORDER BY e.severity_score DESC, e.inserted_at DESC
    LIMIT 10
    """
    results = execute_query(query, (user_id,))
    return results if results else []


def get_users_with_plans() -> List[Dict]:
    query = """
    SELECT u.id, u.email, u.telegram_chat_id, u.phone_number, p.plan
    FROM users u
    JOIN user_plans p ON p.user_id = u.id
    """
    results = execute_query(query)
    return results if results else []


def get_user_prefs(user_id: int) -> List[Dict]:
    query = """
    SELECT id, region, alert_type, asset, threshold, enabled, cooldown_minutes
    FROM user_alert_prefs
    WHERE user_id = %s AND enabled = TRUE
    """
    results = execute_query(query, (user_id,))
    return results if results else []


def get_utc_today_date() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%d')


def count_alerts_today(user_id: int) -> int:
    today_utc = get_utc_today_date()
    query = """
    SELECT COUNT(*) as cnt FROM user_alert_deliveries
    WHERE user_id = %s
      AND created_at::date = %s
      AND status IN ('sent', 'queued')
    """
    result = execute_one(query, (user_id, today_utc))
    return result['cnt'] if result else 0


def check_cooldown(user_id: int, cooldown_key: str, cooldown_minutes: int) -> bool:
    query = """
    SELECT 1 FROM alert_events ae
    JOIN user_alert_deliveries uad ON uad.alert_event_id = ae.id
    WHERE ae.cooldown_key = %s
      AND uad.user_id = %s
      AND uad.created_at >= NOW() - make_interval(mins => %s)
      AND uad.status IN ('sent', 'queued')
    LIMIT 1
    """
    result = execute_one(query, (cooldown_key, user_id, cooldown_minutes))
    return result is not None


def create_alert_event_and_delivery(user_id: int, alert_type: str, region: str, asset: Optional[str],
                                     triggered_value: Optional[float], threshold: Optional[float],
                                     title: str, message: str, channel: str, cooldown_key: str,
                                     status: str = 'queued', event_id: Optional[int] = None,
                                     driver_events: Optional[List[Dict]] = None) -> tuple:
    severity = 3
    if triggered_value and triggered_value >= 80:
        severity = 5
    elif triggered_value and triggered_value >= 60:
        severity = 4
    elif triggered_value and triggered_value >= 40:
        severity = 3
    else:
        severity = 2
    
    category_map = {
        'REGIONAL_RISK_SPIKE': 'regional_risk',
        'ASSET_RISK_SPIKE': 'asset_risk',
        'HIGH_IMPACT_EVENT': 'high_impact',
        'DAILY_DIGEST': 'digest'
    }
    category = category_map.get(alert_type, 'geopolitical')
    
    confidence = 0.8
    if triggered_value:
        confidence = min(1.0, triggered_value / 100)
    
    raw_input_data = {
        "alert_type": alert_type,
        "region": region,
        "asset": asset,
        "triggered_value": triggered_value,
        "threshold": threshold,
        "event_id": event_id,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    classification_data = {
        "alert_type": alert_type,
        "severity": severity,
        "triggered_value": triggered_value,
        "region": region,
        "category": category,
        "confidence": confidence
    }
    
    if driver_events:
        driver_summaries = []
        for e in driver_events[:3]:
            driver_info = {
                "id": e.get('id'),
                "title": e.get('title', '')[:100],
                "category": e.get('category'),
                "source_url": e.get('source_url'),
                "ai_summary": e.get('ai_summary', '')[:200] if e.get('ai_summary') else None,
                "ai_impact_score": float(e['ai_impact_score']) if e.get('ai_impact_score') else None,
                "ai_confidence": float(e['ai_confidence']) if e.get('ai_confidence') else None,
                "weighted_score": float(e['weighted_score']) if e.get('weighted_score') else None
            }
            driver_summaries.append(driver_info)
        raw_input_data["driver_events"] = driver_summaries
        classification_data["driver_summary"] = [d["title"] for d in driver_summaries]
        if driver_summaries:
            avg_confidence = sum(d.get('ai_confidence') or 0.7 for d in driver_summaries) / len(driver_summaries)
            classification_data["avg_driver_confidence"] = round(avg_confidence, 2)
    
    driver_event_ids = None
    if event_id:
        driver_event_ids = [event_id]
    elif driver_events:
        driver_event_ids = [e.get('id') for e in driver_events if e.get('id')]
    
    if driver_event_ids:
        sorted_ids = sorted(driver_event_ids)
        global_cooldown_key = f"{alert_type}:{region}:{asset}:events:{'-'.join(map(str, sorted_ids))}"
        fingerprint = f"{alert_type}:{region}:{asset}:events:{'-'.join(map(str, sorted_ids))}"
    else:
        date_key = datetime.now(timezone.utc).strftime('%Y%m%d')
        global_cooldown_key = f"{alert_type}:{region}:{asset}:date:{date_key}"
        fingerprint = f"{alert_type}:{region}:{asset}:date:{date_key}"
    
    with get_cursor() as cursor:
        cursor.execute(
            """INSERT INTO alert_events 
               (alert_type, scope_region, scope_assets, severity, headline, body, 
                driver_event_ids, cooldown_key, event_fingerprint, raw_input, classification, category, confidence)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (cooldown_key) DO UPDATE SET 
                   raw_input = EXCLUDED.raw_input,
                   classification = EXCLUDED.classification,
                   category = EXCLUDED.category,
                   confidence = EXCLUDED.confidence
               RETURNING id""",
            (alert_type, region, [asset] if asset else [], severity, title, message,
             driver_event_ids, global_cooldown_key, fingerprint, 
             json.dumps(raw_input_data), json.dumps(classification_data),
             category, confidence)
        )
        ae_result = cursor.fetchone()
        alert_event_id = ae_result['id'] if ae_result else None
        
        if not alert_event_id:
            cursor.execute("SELECT id FROM alert_events WHERE cooldown_key = %s", (global_cooldown_key,))
            existing = cursor.fetchone()
            alert_event_id = existing['id'] if existing else None
        
        if not alert_event_id:
            return None, None
        
        cursor.execute(
            """INSERT INTO user_alert_deliveries 
               (user_id, alert_event_id, channel, status)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT DO NOTHING
               RETURNING id""",
            (user_id, alert_event_id, channel, status)
        )
        delivery_result = cursor.fetchone()
        delivery_id = delivery_result['id'] if delivery_result else None
        
        return alert_event_id, delivery_id


def update_delivery_status(delivery_id: int, status: str, error: Optional[str] = None):
    with get_cursor() as cursor:
        if status == 'sent':
            cursor.execute(
                "UPDATE user_alert_deliveries SET status = %s, sent_at = NOW(), last_error = %s WHERE id = %s",
                (status, error, delivery_id)
            )
        else:
            cursor.execute(
                "UPDATE user_alert_deliveries SET status = %s, last_error = %s WHERE id = %s",
                (status, error, delivery_id)
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
        'message': message,
        'driver_events': driver_events
    }


def evaluate_asset_risk_spike(user: Dict, pref: Dict, summary: Dict, allow_asset_alerts: bool) -> Optional[Dict]:
    if not allow_asset_alerts:
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
        'message': message,
        'driver_events': driver_events
    }


def evaluate_high_impact_events(user: Dict, pref: Dict) -> List[Dict]:
    user_id = user['id']
    events = get_high_impact_events(user_id)
    alerts = []
    
    for event in events:
        if event['region'] != pref['region'] and pref['region'] != 'global':
            continue
        
        title, message = format_high_impact_event(event, event['region'])
        
        event_metadata = {
            'id': event['id'],
            'title': event['title'],
            'region': event['region'],
            'category': event.get('category'),
            'source_url': event.get('source_url'),
            'ai_summary': event.get('ai_summary'),
            'severity_score': float(event['severity_score']) if event.get('severity_score') else None
        }
        
        alerts.append({
            'alert_type': 'HIGH_IMPACT_EVENT',
            'region': event['region'],
            'asset': None,
            'triggered_value': float(event['severity_score']),
            'threshold': 4.0,
            'title': title,
            'message': message,
            'event_id': event['id'],
            'driver_events': [event_metadata]
        })
    
    return alerts


def process_user_alerts(user: Dict, dry_run: bool = False) -> List[Dict]:
    user_id = user['id']
    plan = user['plan']
    
    try:
        plan_settings = get_plan_settings(plan)
        allowed_alert_types = get_allowed_alert_types(plan)
        max_per_day = plan_settings['max_email_alerts_per_day']
        delivery_config = plan_settings.get('delivery_config', {})
    except ValueError:
        logger.warning(f"Unknown plan '{plan}' for user {user_id}, using free tier defaults")
        plan_settings = get_plan_settings('free')
        allowed_alert_types = get_allowed_alert_types('free')
        max_per_day = plan_settings['max_email_alerts_per_day']
        delivery_config = plan_settings.get('delivery_config', {})
    
    allow_telegram = delivery_config.get('telegram', False)
    allow_asset_alerts = 'ASSET_RISK_SPIKE' in allowed_alert_types
    
    alerts_today = count_alerts_today(user_id)
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
        
        if alert_type not in allowed_alert_types:
            logger.debug(f"Alert type {alert_type} not allowed for plan {plan}")
            continue
        
        if plan == 'free' and pref['region'] != 'Europe':
            continue
        
        summary = get_risk_summary(pref['region'])
        prev_risk = get_previous_risk_score(pref['region'])
        
        alert_data = None
        
        if alert_type == 'REGIONAL_RISK_SPIKE':
            alert_data = evaluate_regional_risk_spike(user, pref, summary, prev_risk)
        elif alert_type == 'ASSET_RISK_SPIKE':
            alert_data = evaluate_asset_risk_spike(user, pref, summary, allow_asset_alerts)
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


def send_alert(user: Dict, alert_data: Dict, delivery_id: int, plan_settings: Dict) -> bool:
    delivery_config = plan_settings.get('delivery_config', {})
    email_config = delivery_config.get('email', {})
    telegram_config = delivery_config.get('telegram', {})
    sms_config = delivery_config.get('sms', {})
    
    channels_sent = []
    channels_failed = []
    last_error = None
    
    if isinstance(email_config, dict):
        email_enabled = email_config.get('mode') in ['limited', 'unlimited']
    else:
        email_enabled = True
    if email_enabled and user.get('email'):
        success, error, _ = send_email(user['email'], alert_data['title'], alert_data['message'])
        if success:
            channels_sent.append('email')
        else:
            channels_failed.append('email')
            last_error = error
    
    if isinstance(telegram_config, dict):
        telegram_enabled = telegram_config.get('enabled', False)
    else:
        telegram_enabled = telegram_config
    if telegram_enabled and user.get('telegram_chat_id'):
        success, error = send_telegram(user['telegram_chat_id'], alert_data['message'])
        if success:
            channels_sent.append('telegram')
        else:
            channels_failed.append('telegram')
            last_error = error
    
    if isinstance(sms_config, dict):
        sms_enabled = sms_config.get('enabled', False)
    else:
        sms_enabled = sms_config
    if sms_enabled and user.get('phone_number'):
        sms_message = f"{alert_data['title']}\n{alert_data['message'][:500]}"
        success, error = send_sms(user['phone_number'], sms_message)
        if success:
            channels_sent.append('sms')
        else:
            channels_failed.append('sms')
            last_error = error
    
    if channels_sent:
        update_delivery_status(delivery_id, 'sent')
        logger.info(f"Delivery {delivery_id} sent via: {', '.join(channels_sent)}")
        return True
    else:
        update_delivery_status(delivery_id, 'failed', last_error)
        logger.warning(f"Delivery {delivery_id} failed on all channels: {channels_failed}")
        return False


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
            plan = user['plan']
            logger.debug(f"Processing user {user_id} ({plan})")
            
            try:
                plan_settings = get_plan_settings(plan)
                delivery_config = plan_settings.get('delivery_config', {})
                allow_telegram = delivery_config.get('telegram', False)
            except ValueError:
                plan_settings = get_plan_settings('free')
                allow_telegram = False
            
            generated_alerts = process_user_alerts(user, dry_run)
            
            for alert_data in generated_alerts:
                channel = 'telegram' if allow_telegram and user.get('telegram_chat_id') else 'email'
                
                message = alert_data['message']
                if plan == 'free':
                    message = add_upgrade_hook_if_free(message, plan)
                    alert_data['message'] = message
                
                if dry_run:
                    all_alerts.append({
                        'user_id': user_id,
                        'email': user['email'],
                        'plan': plan,
                        'channel': channel,
                        **alert_data
                    })
                else:
                    alert_event_id, delivery_id = create_alert_event_and_delivery(
                        user_id=user_id,
                        alert_type=alert_data['alert_type'],
                        region=alert_data['region'],
                        asset=alert_data.get('asset'),
                        triggered_value=alert_data.get('triggered_value'),
                        threshold=alert_data.get('threshold'),
                        title=alert_data['title'],
                        message=message,
                        channel=channel,
                        cooldown_key=alert_data['cooldown_key'],
                        event_id=alert_data.get('event_id'),
                        driver_events=alert_data.get('driver_events')
                    )
                    
                    if delivery_id:
                        send_alert(user, alert_data, delivery_id, plan_settings)
                        all_alerts.append({'id': delivery_id, 'alert_event_id': alert_event_id, **alert_data})
        
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
