import logging
import json
from src.db.db import get_cursor

logger = logging.getLogger(__name__)

PLAN_SETTINGS_SEED = [
    {
        "plan_code": "free",
        "display_name": "Free",
        "monthly_price_usd": 0.00,
        "allowed_alert_types": ["HIGH_IMPACT_EVENT"],
        "max_email_alerts_per_day": 2,
        "delivery_config": {
            "email": {"max_per_day": 2, "realtime_limit": 1, "mode": "limited"},
            "telegram": {"enabled": False, "send_all": False},
            "sms": {"enabled": False, "send_all": False},
            "account": {"show_all": True}
        }
    },
    {
        "plan_code": "personal",
        "display_name": "Personal",
        "monthly_price_usd": 9.95,
        "allowed_alert_types": ["HIGH_IMPACT_EVENT", "REGIONAL_RISK_SPIKE"],
        "max_email_alerts_per_day": 4,
        "delivery_config": {
            "email": {"max_per_day": 4, "realtime_limit": 1, "mode": "limited"},
            "telegram": {"enabled": False, "send_all": False},
            "sms": {"enabled": False, "send_all": False},
            "account": {"show_all": True}
        }
    },
    {
        "plan_code": "trader",
        "display_name": "Trader",
        "monthly_price_usd": 29.00,
        "allowed_alert_types": ["HIGH_IMPACT_EVENT", "REGIONAL_RISK_SPIKE", "ASSET_RISK_SPIKE"],
        "max_email_alerts_per_day": 8,
        "delivery_config": {
            "email": {"max_per_day": 8, "realtime_limit": 3, "mode": "limited"},
            "telegram": {"enabled": True, "send_all": True},
            "sms": {"enabled": False, "send_all": False},
            "account": {"show_all": True}
        }
    },
    {
        "plan_code": "pro",
        "display_name": "Pro",
        "monthly_price_usd": 49.00,
        "allowed_alert_types": ["HIGH_IMPACT_EVENT", "REGIONAL_RISK_SPIKE", "ASSET_RISK_SPIKE", "DAILY_DIGEST"],
        "max_email_alerts_per_day": 15,
        "delivery_config": {
            "email": {"max_per_day": 15, "realtime_limit": None, "mode": "limited"},
            "telegram": {"enabled": True, "send_all": True},
            "sms": {"enabled": True, "send_all": True},
            "account": {"show_all": True}
        }
    },
    {
        "plan_code": "enterprise",
        "display_name": "Enterprise",
        "monthly_price_usd": 129.00,
        "allowed_alert_types": ["HIGH_IMPACT_EVENT", "REGIONAL_RISK_SPIKE", "ASSET_RISK_SPIKE", "DAILY_DIGEST"],
        "max_email_alerts_per_day": 30,
        "delivery_config": {
            "email": {"max_per_day": 30, "realtime_limit": None, "mode": "limited"},
            "telegram": {"enabled": True, "send_all": True},
            "sms": {"enabled": True, "send_all": True},
            "account": {"show_all": True}
        }
    }
]


def seed_plan_settings():
    logger.info("Seeding plan_settings table...")
    
    with get_cursor() as cursor:
        for plan in PLAN_SETTINGS_SEED:
            cursor.execute(
                """
                INSERT INTO plan_settings (
                    plan_code, display_name, monthly_price_usd,
                    allowed_alert_types, max_email_alerts_per_day, delivery_config
                ) VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (plan_code) DO UPDATE SET
                    display_name = EXCLUDED.display_name,
                    monthly_price_usd = EXCLUDED.monthly_price_usd,
                    allowed_alert_types = EXCLUDED.allowed_alert_types,
                    max_email_alerts_per_day = EXCLUDED.max_email_alerts_per_day,
                    delivery_config = EXCLUDED.delivery_config,
                    updated_at = NOW()
                """,
                (
                    plan["plan_code"],
                    plan["display_name"],
                    plan["monthly_price_usd"],
                    plan["allowed_alert_types"],
                    plan["max_email_alerts_per_day"],
                    json.dumps(plan["delivery_config"])
                )
            )
    
    logger.info(f"Seeded {len(PLAN_SETTINGS_SEED)} plan settings.")

def run_migrations():
    logger.info("Running database migrations...")
    
    create_events_table = """
    CREATE TABLE IF NOT EXISTS events (
        id SERIAL PRIMARY KEY,
        title TEXT NOT NULL,
        source_name TEXT NOT NULL,
        source_url TEXT NOT NULL UNIQUE,
        category TEXT NOT NULL CHECK (category IN ('geopolitical', 'energy', 'supply_chain')),
        region TEXT NOT NULL,
        severity_score INT NOT NULL CHECK (severity_score BETWEEN 1 AND 5),
        event_time TIMESTAMP NULL,
        raw_text TEXT NULL,
        inserted_at TIMESTAMP NOT NULL DEFAULT NOW()
    );
    """
    
    create_ingestion_runs_table = """
    CREATE TABLE IF NOT EXISTS ingestion_runs (
        id SERIAL PRIMARY KEY,
        started_at TIMESTAMP DEFAULT NOW(),
        finished_at TIMESTAMP NULL,
        status TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'success', 'failed')),
        notes TEXT NULL
    );
    """
    
    create_indexes = [
        "CREATE INDEX IF NOT EXISTS idx_events_inserted_at ON events (inserted_at DESC);",
        "CREATE INDEX IF NOT EXISTS idx_events_category ON events (category);",
        "CREATE INDEX IF NOT EXISTS idx_events_region ON events (region);",
        "CREATE INDEX IF NOT EXISTS idx_events_severity ON events (severity_score);"
    ]
    
    alter_events_add_classification_reason = """
    DO $$ 
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'events' AND column_name = 'classification_reason'
        ) THEN
            ALTER TABLE events ADD COLUMN classification_reason TEXT NULL;
        END IF;
    END $$;
    """
    
    alter_ingestion_runs_add_stats = """
    DO $$ 
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'ingestion_runs' AND column_name = 'total_items'
        ) THEN
            ALTER TABLE ingestion_runs ADD COLUMN total_items INT DEFAULT 0;
        END IF;
        
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'ingestion_runs' AND column_name = 'inserted_items'
        ) THEN
            ALTER TABLE ingestion_runs ADD COLUMN inserted_items INT DEFAULT 0;
        END IF;
        
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'ingestion_runs' AND column_name = 'skipped_duplicates'
        ) THEN
            ALTER TABLE ingestion_runs ADD COLUMN skipped_duplicates INT DEFAULT 0;
        END IF;
        
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'ingestion_runs' AND column_name = 'failed_items'
        ) THEN
            ALTER TABLE ingestion_runs ADD COLUMN failed_items INT DEFAULT 0;
        END IF;
    END $$;
    """
    
    alter_events_add_ai_columns = """
    DO $$ 
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'events' AND column_name = 'processed'
        ) THEN
            ALTER TABLE events ADD COLUMN processed BOOLEAN NOT NULL DEFAULT FALSE;
        END IF;
        
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'events' AND column_name = 'ai_summary'
        ) THEN
            ALTER TABLE events ADD COLUMN ai_summary TEXT NULL;
        END IF;
        
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'events' AND column_name = 'ai_impact_json'
        ) THEN
            ALTER TABLE events ADD COLUMN ai_impact_json JSONB NULL;
        END IF;
        
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'events' AND column_name = 'ai_model'
        ) THEN
            ALTER TABLE events ADD COLUMN ai_model TEXT NULL;
        END IF;
        
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'events' AND column_name = 'ai_processed_at'
        ) THEN
            ALTER TABLE events ADD COLUMN ai_processed_at TIMESTAMP NULL;
        END IF;
        
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'events' AND column_name = 'ai_error'
        ) THEN
            ALTER TABLE events ADD COLUMN ai_error TEXT NULL;
        END IF;
        
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'events' AND column_name = 'ai_attempts'
        ) THEN
            ALTER TABLE events ADD COLUMN ai_attempts INT NOT NULL DEFAULT 0;
        END IF;
    END $$;
    """
    
    create_ai_indexes = [
        "CREATE INDEX IF NOT EXISTS idx_events_processed ON events (processed);",
        "CREATE INDEX IF NOT EXISTS idx_events_ai_processed_at ON events (ai_processed_at);"
    ]
    
    create_risk_events_table = """
    CREATE TABLE IF NOT EXISTS risk_events (
        id SERIAL PRIMARY KEY,
        event_id INT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
        region TEXT NOT NULL,
        category TEXT NOT NULL,
        base_severity INT NOT NULL,
        ai_confidence FLOAT NOT NULL,
        weighted_score FLOAT NOT NULL,
        created_at TIMESTAMP DEFAULT NOW(),
        UNIQUE(event_id)
    );
    """
    
    create_risk_indices_table = """
    CREATE TABLE IF NOT EXISTS risk_indices (
        id SERIAL PRIMARY KEY,
        region TEXT NOT NULL,
        window_days INT NOT NULL,
        risk_score FLOAT NOT NULL,
        trend TEXT NOT NULL,
        calculated_at TIMESTAMP DEFAULT NOW()
    );
    """
    
    create_asset_risk_table = """
    CREATE TABLE IF NOT EXISTS asset_risk (
        id SERIAL PRIMARY KEY,
        asset TEXT NOT NULL,
        region TEXT NOT NULL,
        window_days INT NOT NULL,
        risk_score FLOAT NOT NULL,
        direction TEXT NOT NULL,
        calculated_at TIMESTAMP DEFAULT NOW()
    );
    """
    
    create_risk_indexes = [
        "CREATE INDEX IF NOT EXISTS idx_risk_events_event_id ON risk_events (event_id);",
        "CREATE INDEX IF NOT EXISTS idx_risk_events_region ON risk_events (region);",
        "CREATE INDEX IF NOT EXISTS idx_risk_events_category ON risk_events (category);",
        "CREATE INDEX IF NOT EXISTS idx_risk_events_created_at ON risk_events (created_at DESC);",
        "CREATE INDEX IF NOT EXISTS idx_risk_indices_region ON risk_indices (region);",
        "CREATE INDEX IF NOT EXISTS idx_risk_indices_window ON risk_indices (window_days);",
        "CREATE INDEX IF NOT EXISTS idx_risk_indices_calculated ON risk_indices (calculated_at DESC);",
        "CREATE INDEX IF NOT EXISTS idx_asset_risk_asset ON asset_risk (asset);",
        "CREATE INDEX IF NOT EXISTS idx_asset_risk_region ON asset_risk (region);",
        "CREATE INDEX IF NOT EXISTS idx_asset_risk_window ON asset_risk (window_days);",
        "CREATE INDEX IF NOT EXISTS idx_asset_risk_calculated ON asset_risk (calculated_at DESC);"
    ]
    
    create_users_table = """
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        email TEXT UNIQUE NOT NULL,
        telegram_chat_id TEXT NULL,
        created_at TIMESTAMP DEFAULT NOW()
    );
    """
    
    create_user_plans_table = """
    CREATE TABLE IF NOT EXISTS user_plans (
        user_id INT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        plan TEXT NOT NULL CHECK (plan IN ('free','trader','pro','enterprise')),
        plan_price_usd INT NOT NULL DEFAULT 0,
        alerts_delay_minutes INT NOT NULL DEFAULT 60,
        allow_asset_alerts BOOLEAN NOT NULL DEFAULT FALSE,
        allow_telegram BOOLEAN NOT NULL DEFAULT FALSE,
        daily_digest_enabled BOOLEAN NOT NULL DEFAULT FALSE,
        allow_webhooks BOOLEAN NOT NULL DEFAULT FALSE,
        max_total_alerts_per_day INT NOT NULL DEFAULT 2,
        max_email_alerts_per_day INT NOT NULL DEFAULT 1,
        max_telegram_alerts_per_day INT NOT NULL DEFAULT 0,
        preferred_realtime_channel TEXT NOT NULL DEFAULT 'email' CHECK (preferred_realtime_channel IN ('email','telegram')),
        custom_thresholds BOOLEAN NOT NULL DEFAULT FALSE,
        priority_processing BOOLEAN NOT NULL DEFAULT FALSE,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    );
    """
    
    create_user_alert_prefs_table = """
    CREATE TABLE IF NOT EXISTS user_alert_prefs (
        id SERIAL PRIMARY KEY,
        user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        region TEXT NOT NULL DEFAULT 'Europe',
        alert_type TEXT NOT NULL CHECK (alert_type IN ('REGIONAL_RISK_SPIKE','ASSET_RISK_SPIKE','HIGH_IMPACT_EVENT','DAILY_DIGEST')),
        asset TEXT NULL CHECK (asset IS NULL OR asset IN ('oil','gas','fx','freight')),
        threshold FLOAT NULL,
        enabled BOOLEAN NOT NULL DEFAULT TRUE,
        cooldown_minutes INT NOT NULL DEFAULT 120,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    );
    """
    
    create_alerts_table = """
    CREATE TABLE IF NOT EXISTS alerts (
        id SERIAL PRIMARY KEY,
        user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        alert_type TEXT NOT NULL,
        region TEXT NOT NULL,
        asset TEXT NULL,
        triggered_value FLOAT NULL,
        threshold FLOAT NULL,
        title TEXT NOT NULL,
        message TEXT NOT NULL,
        channel TEXT NOT NULL CHECK (channel IN ('email','telegram')),
        status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','sent','failed','skipped')),
        cooldown_key TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT NOW(),
        sent_at TIMESTAMP NULL,
        error TEXT NULL
    );
    """
    
    create_alert_state_table = """
    CREATE TABLE IF NOT EXISTS alert_state (
        id SERIAL PRIMARY KEY,
        region TEXT NOT NULL,
        window_days INT NOT NULL DEFAULT 7,
        last_risk_score FLOAT NULL,
        last_checked_at TIMESTAMP DEFAULT NOW(),
        last_7d_score FLOAT NULL,
        last_30d_score FLOAT NULL,
        last_asset_scores JSONB NULL,
        updated_at TIMESTAMP DEFAULT NOW(),
        UNIQUE(region, window_days)
    );
    """
    
    create_alerts_indexes = [
        "CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);",
        "CREATE INDEX IF NOT EXISTS idx_user_alert_prefs_user ON user_alert_prefs (user_id);",
        "CREATE INDEX IF NOT EXISTS idx_alerts_user_created ON alerts (user_id, created_at DESC);",
        "CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts (status);",
        "CREATE INDEX IF NOT EXISTS idx_alerts_cooldown ON alerts (cooldown_key, created_at DESC);",
        "CREATE INDEX IF NOT EXISTS idx_alert_state_region ON alert_state (region);"
    ]
    
    create_plan_settings_table = """
    CREATE TABLE IF NOT EXISTS plan_settings (
        plan_code TEXT PRIMARY KEY,
        display_name TEXT NOT NULL,
        monthly_price_usd NUMERIC(8,2) NOT NULL,
        allowed_alert_types TEXT[] NOT NULL,
        max_email_alerts_per_day INT NOT NULL,
        delivery_config JSONB NOT NULL,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
    );
    """
    
    with get_cursor() as cursor:
        logger.info("Creating events table...")
        cursor.execute(create_events_table)
        
        logger.info("Creating ingestion_runs table...")
        cursor.execute(create_ingestion_runs_table)
        
        logger.info("Creating indexes...")
        for idx_sql in create_indexes:
            cursor.execute(idx_sql)
        
        logger.info("Adding classification_reason column to events...")
        cursor.execute(alter_events_add_classification_reason)
        
        logger.info("Adding stats columns to ingestion_runs...")
        cursor.execute(alter_ingestion_runs_add_stats)
        
        logger.info("Adding AI columns to events...")
        cursor.execute(alter_events_add_ai_columns)
        
        logger.info("Creating AI indexes...")
        for idx_sql in create_ai_indexes:
            cursor.execute(idx_sql)
        
        logger.info("Creating risk_events table...")
        cursor.execute(create_risk_events_table)
        
        logger.info("Creating risk_indices table...")
        cursor.execute(create_risk_indices_table)
        
        logger.info("Creating asset_risk table...")
        cursor.execute(create_asset_risk_table)
        
        logger.info("Creating risk indexes...")
        for idx_sql in create_risk_indexes:
            cursor.execute(idx_sql)
        
        logger.info("Creating users table...")
        cursor.execute(create_users_table)
        
        logger.info("Creating user_plans table...")
        cursor.execute(create_user_plans_table)
        
        logger.info("Creating user_alert_prefs table...")
        cursor.execute(create_user_alert_prefs_table)
        
        logger.info("Creating alerts table...")
        cursor.execute(create_alerts_table)
        
        logger.info("Creating alert_state table...")
        cursor.execute(create_alert_state_table)
        
        logger.info("Creating alerts indexes...")
        for idx_sql in create_alerts_indexes:
            cursor.execute(idx_sql)
        
        logger.info("Creating plan_settings table...")
        cursor.execute(create_plan_settings_table)
    
    seed_plan_settings()
    logger.info("Migrations completed successfully.")

def ensure_user_plans_table():
    logger.info("Ensuring user_plans table has correct schema...")
    
    alter_user_plans_columns = """
    DO $$ 
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'user_plans' AND column_name = 'plan_price_usd'
        ) THEN
            ALTER TABLE user_plans ADD COLUMN plan_price_usd INT NOT NULL DEFAULT 0;
        END IF;
        
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'user_plans' AND column_name = 'allow_webhooks'
        ) THEN
            ALTER TABLE user_plans ADD COLUMN allow_webhooks BOOLEAN NOT NULL DEFAULT FALSE;
        END IF;
        
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'user_plans' AND column_name = 'max_total_alerts_per_day'
        ) THEN
            ALTER TABLE user_plans ADD COLUMN max_total_alerts_per_day INT NOT NULL DEFAULT 2;
        END IF;
        
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'user_plans' AND column_name = 'max_email_alerts_per_day'
        ) THEN
            ALTER TABLE user_plans ADD COLUMN max_email_alerts_per_day INT NOT NULL DEFAULT 1;
        END IF;
        
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'user_plans' AND column_name = 'max_telegram_alerts_per_day'
        ) THEN
            ALTER TABLE user_plans ADD COLUMN max_telegram_alerts_per_day INT NOT NULL DEFAULT 0;
        END IF;
        
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'user_plans' AND column_name = 'preferred_realtime_channel'
        ) THEN
            ALTER TABLE user_plans ADD COLUMN preferred_realtime_channel TEXT NOT NULL DEFAULT 'email';
        END IF;
        
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'user_plans' AND column_name = 'custom_thresholds'
        ) THEN
            ALTER TABLE user_plans ADD COLUMN custom_thresholds BOOLEAN NOT NULL DEFAULT FALSE;
        END IF;
        
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'user_plans' AND column_name = 'priority_processing'
        ) THEN
            ALTER TABLE user_plans ADD COLUMN priority_processing BOOLEAN NOT NULL DEFAULT FALSE;
        END IF;
    END $$;
    """
    
    with get_cursor() as cursor:
        cursor.execute(alter_user_plans_columns)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_plans_plan ON user_plans(plan);")
    
    logger.info("user_plans table schema updated.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migrations()
