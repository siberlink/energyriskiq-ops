from typing import Dict, Tuple, Optional
from datetime import datetime, timezone
from src.db.db import get_cursor

PLAN_DEFAULTS = {
    "free": {
        "plan_price_usd": 0,
        "alerts_delay_minutes": 60,
        "allow_asset_alerts": False,
        "allow_telegram": False,
        "daily_digest_enabled": False,
        "allow_webhooks": False,
        "max_total_alerts_per_day": 2,
        "max_email_alerts_per_day": 1,
        "max_telegram_alerts_per_day": 0,
        "preferred_realtime_channel": "email",
        "custom_thresholds": False,
        "priority_processing": False
    },
    "trader": {
        "plan_price_usd": 49,
        "alerts_delay_minutes": 0,
        "allow_asset_alerts": True,
        "allow_telegram": False,
        "daily_digest_enabled": True,
        "allow_webhooks": False,
        "max_total_alerts_per_day": 20,
        "max_email_alerts_per_day": 5,
        "max_telegram_alerts_per_day": 0,
        "preferred_realtime_channel": "email",
        "custom_thresholds": False,
        "priority_processing": False
    },
    "pro": {
        "plan_price_usd": 129,
        "alerts_delay_minutes": 0,
        "allow_asset_alerts": True,
        "allow_telegram": True,
        "daily_digest_enabled": True,
        "allow_webhooks": False,
        "max_total_alerts_per_day": 50,
        "max_email_alerts_per_day": 2,
        "max_telegram_alerts_per_day": 50,
        "preferred_realtime_channel": "telegram",
        "custom_thresholds": False,
        "priority_processing": True
    },
    "enterprise": {
        "plan_price_usd": 299,
        "alerts_delay_minutes": 0,
        "allow_asset_alerts": True,
        "allow_telegram": True,
        "daily_digest_enabled": True,
        "allow_webhooks": True,
        "max_total_alerts_per_day": 150,
        "max_email_alerts_per_day": 2,
        "max_telegram_alerts_per_day": 999999,
        "preferred_realtime_channel": "telegram",
        "custom_thresholds": True,
        "priority_processing": True
    }
}


def get_plan_defaults(plan: str) -> Dict:
    if plan not in PLAN_DEFAULTS:
        raise ValueError(f"Unknown plan: {plan}")
    return PLAN_DEFAULTS[plan].copy()


def get_user_plan(user_id: int) -> Optional[Dict]:
    with get_cursor(commit=False) as cur:
        cur.execute("""
            SELECT plan, plan_price_usd, alerts_delay_minutes,
                   allow_asset_alerts, allow_telegram, daily_digest_enabled, allow_webhooks,
                   max_total_alerts_per_day, max_email_alerts_per_day, max_telegram_alerts_per_day,
                   preferred_realtime_channel, custom_thresholds, priority_processing
            FROM user_plans WHERE user_id = %s
        """, (user_id,))
        row = cur.fetchone()
        if not row:
            return None
        return {
            "plan": row["plan"],
            "plan_price_usd": row["plan_price_usd"],
            "alerts_delay_minutes": row["alerts_delay_minutes"],
            "allow_asset_alerts": row["allow_asset_alerts"],
            "allow_telegram": row["allow_telegram"],
            "daily_digest_enabled": row["daily_digest_enabled"],
            "allow_webhooks": row["allow_webhooks"],
            "max_total_alerts_per_day": row["max_total_alerts_per_day"],
            "max_email_alerts_per_day": row["max_email_alerts_per_day"],
            "max_telegram_alerts_per_day": row["max_telegram_alerts_per_day"],
            "preferred_realtime_channel": row["preferred_realtime_channel"],
            "custom_thresholds": row["custom_thresholds"],
            "priority_processing": row["priority_processing"]
        }


def get_today_alert_counts(user_id: int) -> Dict[str, int]:
    with get_cursor(commit=False) as cur:
        today_utc = datetime.now(timezone.utc).date()
        
        cur.execute("""
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE channel = 'email') as email,
                COUNT(*) FILTER (WHERE channel = 'telegram') as telegram
            FROM alerts 
            WHERE user_id = %s 
              AND DATE(created_at AT TIME ZONE 'UTC') = %s
              AND status = 'sent'
        """, (user_id, today_utc))
        
        row = cur.fetchone()
        return {
            "total": row["total"] if row else 0,
            "email": row["email"] if row else 0,
            "telegram": row["telegram"] if row else 0
        }


def can_send_total_alert(user_id: int) -> Tuple[bool, str]:
    plan = get_user_plan(user_id)
    if not plan:
        return False, "User has no plan configured"
    
    counts = get_today_alert_counts(user_id)
    max_allowed = plan["max_total_alerts_per_day"]
    
    if counts["total"] >= max_allowed:
        return False, f"Daily total alert limit reached ({counts['total']}/{max_allowed})"
    
    return True, "OK"


def can_send_email_alert(user_id: int) -> Tuple[bool, str]:
    plan = get_user_plan(user_id)
    if not plan:
        return False, "User has no plan configured"
    
    can_total, reason = can_send_total_alert(user_id)
    if not can_total:
        return False, reason
    
    counts = get_today_alert_counts(user_id)
    max_allowed = plan["max_email_alerts_per_day"]
    
    if counts["email"] >= max_allowed:
        return False, f"Daily email alert limit reached ({counts['email']}/{max_allowed})"
    
    return True, "OK"


def can_send_telegram_alert(user_id: int) -> Tuple[bool, str]:
    plan = get_user_plan(user_id)
    if not plan:
        return False, "User has no plan configured"
    
    if not plan["allow_telegram"]:
        return False, "Telegram alerts not available on this plan"
    
    can_total, reason = can_send_total_alert(user_id)
    if not can_total:
        return False, reason
    
    counts = get_today_alert_counts(user_id)
    max_allowed = plan["max_telegram_alerts_per_day"]
    
    if counts["telegram"] >= max_allowed:
        return False, f"Daily Telegram alert limit reached ({counts['telegram']}/{max_allowed})"
    
    return True, "OK"


def create_user_plan(user_id: int, plan: str) -> bool:
    defaults = get_plan_defaults(plan)
    try:
        with get_cursor() as cur:
            cur.execute("""
                INSERT INTO user_plans (
                    user_id, plan, plan_price_usd, alerts_delay_minutes,
                    allow_asset_alerts, allow_telegram, daily_digest_enabled, allow_webhooks,
                    max_total_alerts_per_day, max_email_alerts_per_day, max_telegram_alerts_per_day,
                    preferred_realtime_channel, custom_thresholds, priority_processing
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    plan = EXCLUDED.plan,
                    plan_price_usd = EXCLUDED.plan_price_usd,
                    alerts_delay_minutes = EXCLUDED.alerts_delay_minutes,
                    allow_asset_alerts = EXCLUDED.allow_asset_alerts,
                    allow_telegram = EXCLUDED.allow_telegram,
                    daily_digest_enabled = EXCLUDED.daily_digest_enabled,
                    allow_webhooks = EXCLUDED.allow_webhooks,
                    max_total_alerts_per_day = EXCLUDED.max_total_alerts_per_day,
                    max_email_alerts_per_day = EXCLUDED.max_email_alerts_per_day,
                    max_telegram_alerts_per_day = EXCLUDED.max_telegram_alerts_per_day,
                    preferred_realtime_channel = EXCLUDED.preferred_realtime_channel,
                    custom_thresholds = EXCLUDED.custom_thresholds,
                    priority_processing = EXCLUDED.priority_processing,
                    updated_at = NOW()
            """, (
                user_id, plan, defaults["plan_price_usd"], defaults["alerts_delay_minutes"],
                defaults["allow_asset_alerts"], defaults["allow_telegram"],
                defaults["daily_digest_enabled"], defaults["allow_webhooks"],
                defaults["max_total_alerts_per_day"], defaults["max_email_alerts_per_day"],
                defaults["max_telegram_alerts_per_day"], defaults["preferred_realtime_channel"],
                defaults["custom_thresholds"], defaults["priority_processing"]
            ))
        return True
    except Exception as e:
        print(f"Error creating user plan: {e}")
        return False


def migrate_user_plans():
    with get_cursor() as cur:
        cur.execute("SELECT id FROM users")
        users = cur.fetchall()
        
        migrated = 0
        skipped = 0
        
        for row in users:
            user_id = row["id"]
            cur.execute("SELECT user_id FROM user_plans WHERE user_id = %s", (user_id,))
            existing = cur.fetchone()
            
            if existing:
                skipped += 1
                continue
            
            defaults = get_plan_defaults("free")
            cur.execute("""
                INSERT INTO user_plans (
                    user_id, plan, plan_price_usd, alerts_delay_minutes,
                    allow_asset_alerts, allow_telegram, daily_digest_enabled, allow_webhooks,
                    max_total_alerts_per_day, max_email_alerts_per_day, max_telegram_alerts_per_day,
                    preferred_realtime_channel, custom_thresholds, priority_processing
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                user_id, "free", defaults["plan_price_usd"], defaults["alerts_delay_minutes"],
                defaults["allow_asset_alerts"], defaults["allow_telegram"],
                defaults["daily_digest_enabled"], defaults["allow_webhooks"],
                defaults["max_total_alerts_per_day"], defaults["max_email_alerts_per_day"],
                defaults["max_telegram_alerts_per_day"], defaults["preferred_realtime_channel"],
                defaults["custom_thresholds"], defaults["priority_processing"]
            ))
            migrated += 1
        
        print(f"Migration complete: {migrated} users migrated, {skipped} skipped (already have plans)")
        return migrated, skipped
