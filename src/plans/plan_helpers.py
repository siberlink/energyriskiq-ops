from typing import Dict, Tuple, Optional, List
from datetime import datetime, timezone
import json
import logging
from src.db.db import get_cursor

logger = logging.getLogger(__name__)

ALL_ALERT_TYPES = ["HIGH_IMPACT_EVENT", "REGIONAL_RISK_SPIKE", "ASSET_RISK_SPIKE", "DAILY_DIGEST"]
VALID_PLAN_CODES = ["free", "personal", "trader", "pro", "enterprise"]


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


def get_user_plan_code(user_id: int) -> Optional[str]:
    with get_cursor(commit=False) as cur:
        cur.execute("SELECT plan FROM user_plans WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
        if not row:
            return None
        return row["plan"]


def get_user_plan_with_settings(user_id: int) -> Optional[Dict]:
    plan_code = get_user_plan_code(user_id)
    if not plan_code:
        return None
    
    try:
        settings = get_plan_settings(plan_code)
        delivery = settings.get("delivery_config", {})
        allowed_types = get_allowed_alert_types(plan_code)
        
        return {
            "user_id": user_id,
            "plan": plan_code,
            "plan_price_usd": settings["monthly_price_usd"],
            "max_email_alerts_per_day": settings["max_email_alerts_per_day"],
            "allowed_alert_types": allowed_types,
            "allow_telegram": delivery.get("telegram", False),
            "allow_sms": delivery.get("sms", False),
            "allow_webhooks": delivery.get("account_manager", False),
            "daily_digest_enabled": "DAILY_DIGEST" in allowed_types,
            "allow_asset_alerts": "ASSET_RISK_SPIKE" in allowed_types,
            "delivery_config": delivery
        }
    except ValueError:
        logger.warning(f"Unknown plan '{plan_code}' for user {user_id}")
        return None


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


def can_send_email_alert(user_id: int) -> Tuple[bool, str]:
    plan_code = get_user_plan_code(user_id)
    if not plan_code:
        return False, "User has no plan configured"
    
    try:
        settings = get_plan_settings(plan_code)
    except ValueError:
        return False, f"Unknown plan: {plan_code}"
    
    counts = get_today_alert_counts(user_id)
    max_allowed = settings["max_email_alerts_per_day"]
    
    if counts["email"] >= max_allowed:
        return False, f"Daily email alert limit reached ({counts['email']}/{max_allowed})"
    
    return True, "OK"


def can_send_telegram_alert(user_id: int) -> Tuple[bool, str]:
    plan_code = get_user_plan_code(user_id)
    if not plan_code:
        return False, "User has no plan configured"
    
    try:
        settings = get_plan_settings(plan_code)
    except ValueError:
        return False, f"Unknown plan: {plan_code}"
    
    delivery = settings.get("delivery_config", {})
    if not delivery.get("telegram", False):
        return False, "Telegram alerts not available on this plan"
    
    return True, "OK"


def apply_plan_settings_to_user(user_id: int, plan_code: str) -> bool:
    if plan_code not in VALID_PLAN_CODES:
        logger.error(f"Invalid plan code: {plan_code}")
        return False
    
    try:
        settings = get_plan_settings(plan_code)
        delivery = settings.get("delivery_config", {})
        allowed_types = get_allowed_alert_types(plan_code)
        
        telegram_config = delivery.get("telegram", {})
        allow_telegram = telegram_config.get("enabled", False) if isinstance(telegram_config, dict) else bool(telegram_config)
        
        sms_config = delivery.get("sms", {})
        allow_webhooks = sms_config.get("enabled", False) if isinstance(sms_config, dict) else bool(sms_config)
        
        with get_cursor() as cur:
            cur.execute("""
                INSERT INTO user_plans (
                    user_id, plan, plan_price_usd, alerts_delay_minutes,
                    allow_asset_alerts, allow_telegram, daily_digest_enabled, allow_webhooks,
                    max_total_alerts_per_day, max_email_alerts_per_day, max_telegram_alerts_per_day,
                    preferred_realtime_channel, custom_thresholds, priority_processing
                ) VALUES (
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s
                )
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
                user_id,
                plan_code,
                float(settings["monthly_price_usd"]),
                0 if plan_code in ["pro", "enterprise"] else 60,
                "ASSET_RISK_SPIKE" in allowed_types,
                allow_telegram,
                "DAILY_DIGEST" in allowed_types,
                allow_webhooks,
                settings["max_email_alerts_per_day"] * 2,
                settings["max_email_alerts_per_day"],
                settings["max_email_alerts_per_day"] if allow_telegram else 0,
                "email",
                plan_code in ["pro", "enterprise"],
                plan_code == "enterprise"
            ))
        
        logger.info(f"Applied plan settings '{plan_code}' to user {user_id}")
        return True
    except Exception as e:
        logger.error(f"Error applying plan settings to user: {e}")
        return False


def create_default_alert_prefs(user_id: int, plan_code: str) -> int:
    """Create default alert preferences for a new user based on their plan."""
    try:
        allowed_types = get_allowed_alert_types(plan_code)
        prefs_created = 0
        
        with get_cursor() as cursor:
            cursor.execute("SELECT 1 FROM user_alert_prefs WHERE user_id = %s LIMIT 1", (user_id,))
            if cursor.fetchone():
                return 0
            
            if 'HIGH_IMPACT_EVENT' in allowed_types:
                cursor.execute("""
                    INSERT INTO user_alert_prefs (user_id, region, alert_type, threshold, enabled, cooldown_minutes)
                    VALUES (%s, 'Europe', 'HIGH_IMPACT_EVENT', 4, TRUE, 60)
                """, (user_id,))
                prefs_created += 1
            
            if 'REGIONAL_RISK_SPIKE' in allowed_types:
                cursor.execute("""
                    INSERT INTO user_alert_prefs (user_id, region, alert_type, threshold, enabled, cooldown_minutes)
                    VALUES (%s, 'Europe', 'REGIONAL_RISK_SPIKE', 70, TRUE, 120)
                """, (user_id,))
                prefs_created += 1
            
            if 'ASSET_RISK_SPIKE' in allowed_types:
                for asset in ['oil', 'gas']:
                    cursor.execute("""
                        INSERT INTO user_alert_prefs (user_id, region, alert_type, asset, threshold, enabled, cooldown_minutes)
                        VALUES (%s, 'Europe', 'ASSET_RISK_SPIKE', %s, 70, TRUE, 120)
                    """, (user_id, asset))
                    prefs_created += 1
        
        logger.info(f"Created {prefs_created} default alert prefs for user {user_id} (plan: {plan_code})")
        return prefs_created
    except Exception as e:
        logger.error(f"Error creating default alert prefs for user {user_id}: {e}")
        return 0


def create_user_plan(user_id: int, plan: str) -> bool:
    success = apply_plan_settings_to_user(user_id, plan)
    if success:
        create_default_alert_prefs(user_id, plan)
    return success


def migrate_user_plans():
    with get_cursor(commit=False) as cur:
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
            
            apply_plan_settings_to_user(user_id, "free")
            migrated += 1
        
        logger.info(f"Migration complete: {migrated} users migrated, {skipped} skipped (already have plans)")
        return migrated, skipped


def migrate_user_alert_prefs():
    """Migrate existing users to have default alert preferences if they don't have any."""
    with get_cursor(commit=False) as cur:
        cur.execute("""
            SELECT u.id, COALESCE(up.plan, 'free') as plan
            FROM users u
            LEFT JOIN user_plans up ON up.user_id = u.id
            WHERE NOT EXISTS (
                SELECT 1 FROM user_alert_prefs uap WHERE uap.user_id = u.id
            )
        """)
        users = cur.fetchall()
        
        migrated = 0
        
        for row in users:
            user_id = row["id"]
            plan_code = row["plan"]
            prefs_created = create_default_alert_prefs(user_id, plan_code)
            if prefs_created > 0:
                migrated += 1
        
        logger.info(f"Alert prefs migration complete: {migrated} users received default preferences")
        return migrated


def sync_all_user_plans():
    with get_cursor(commit=False) as cur:
        cur.execute("SELECT user_id, plan FROM user_plans")
        rows = cur.fetchall()
        
        synced = 0
        errors = 0
        
        for row in rows:
            user_id = row["user_id"]
            plan_code = row["plan"]
            
            if apply_plan_settings_to_user(user_id, plan_code):
                synced += 1
            else:
                errors += 1
        
        logger.info(f"Sync complete: {synced} users synced, {errors} errors")
        return synced, errors


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
