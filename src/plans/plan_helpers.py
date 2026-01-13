from typing import Dict, Tuple, Optional, List
from datetime import datetime, timezone
import json
from src.db.db import get_cursor

ALL_ALERT_TYPES = ["HIGH_IMPACT_EVENT", "REGIONAL_RISK_SPIKE", "ASSET_RISK_SPIKE", "DAILY_DIGEST"]
VALID_PLAN_CODES = ["free", "personal", "trader", "pro", "enterprise"]

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


def get_plan_settings(plan_code: str) -> Dict:
    if plan_code not in VALID_PLAN_CODES:
        raise ValueError(f"Invalid plan_code: {plan_code}. Must be one of: {VALID_PLAN_CODES}")
    
    with get_cursor(commit=False) as cur:
        cur.execute("""
            SELECT plan_code, display_name, monthly_price_usd,
                   allowed_alert_types, max_email_alerts_per_day,
                   delivery_config, is_active, created_at, updated_at
            FROM plan_settings
            WHERE plan_code = %s
        """, (plan_code,))
        row = cur.fetchone()
        
        if not row:
            raise ValueError(f"Plan settings not found for plan_code: {plan_code}")
        
        delivery_config = row["delivery_config"]
        if isinstance(delivery_config, str):
            delivery_config = json.loads(delivery_config)
        
        return {
            "plan_code": row["plan_code"],
            "display_name": row["display_name"],
            "monthly_price_usd": float(row["monthly_price_usd"]),
            "allowed_alert_types": list(row["allowed_alert_types"]),
            "max_email_alerts_per_day": row["max_email_alerts_per_day"],
            "delivery_config": delivery_config,
            "is_active": row["is_active"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None
        }


def get_all_plan_settings() -> List[Dict]:
    with get_cursor(commit=False) as cur:
        cur.execute("""
            SELECT plan_code, display_name, monthly_price_usd,
                   allowed_alert_types, max_email_alerts_per_day,
                   delivery_config, is_active, created_at, updated_at
            FROM plan_settings
            ORDER BY monthly_price_usd ASC
        """)
        rows = cur.fetchall()
        
        results = []
        for row in rows:
            delivery_config = row["delivery_config"]
            if isinstance(delivery_config, str):
                delivery_config = json.loads(delivery_config)
            
            results.append({
                "plan_code": row["plan_code"],
                "display_name": row["display_name"],
                "monthly_price_usd": float(row["monthly_price_usd"]),
                "allowed_alert_types": list(row["allowed_alert_types"]),
                "max_email_alerts_per_day": row["max_email_alerts_per_day"],
                "delivery_config": delivery_config,
                "is_active": row["is_active"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None
            })
        
        return results


def get_allowed_alert_types(plan_code: str) -> List[str]:
    settings = get_plan_settings(plan_code)
    allowed = settings["allowed_alert_types"]
    
    if "ALL" in allowed:
        return ALL_ALERT_TYPES.copy()
    
    return allowed


def update_plan_settings(plan_code: str, updates: Dict) -> Dict:
    if plan_code not in VALID_PLAN_CODES:
        raise ValueError(f"Invalid plan_code: {plan_code}. Must be one of: {VALID_PLAN_CODES}")
    
    if "allowed_alert_types" in updates:
        for alert_type in updates["allowed_alert_types"]:
            if alert_type != "ALL" and alert_type not in ALL_ALERT_TYPES:
                raise ValueError(f"Invalid alert_type: {alert_type}. Must be one of: {ALL_ALERT_TYPES}")
    
    update_fields = []
    update_values = []
    
    if "monthly_price_usd" in updates:
        update_fields.append("monthly_price_usd = %s")
        update_values.append(updates["monthly_price_usd"])
    
    if "allowed_alert_types" in updates:
        update_fields.append("allowed_alert_types = %s")
        update_values.append(updates["allowed_alert_types"])
    
    if "max_email_alerts_per_day" in updates:
        update_fields.append("max_email_alerts_per_day = %s")
        update_values.append(updates["max_email_alerts_per_day"])
    
    if "delivery_config" in updates:
        update_fields.append("delivery_config = %s")
        update_values.append(json.dumps(updates["delivery_config"]))
    
    if "is_active" in updates:
        update_fields.append("is_active = %s")
        update_values.append(updates["is_active"])
    
    if not update_fields:
        return get_plan_settings(plan_code)
    
    update_fields.append("updated_at = NOW()")
    update_values.append(plan_code)
    
    with get_cursor() as cur:
        sql = f"""
            UPDATE plan_settings
            SET {", ".join(update_fields)}
            WHERE plan_code = %s
        """
        cur.execute(sql, tuple(update_values))
    
    return get_plan_settings(plan_code)
