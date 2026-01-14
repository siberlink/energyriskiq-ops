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
        plan TEXT NOT NULL CHECK (plan IN ('free','personal','trader','pro','enterprise')),
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    );
    """
    
    create_sessions_table = """
    CREATE TABLE IF NOT EXISTS sessions (
        token TEXT PRIMARY KEY,
        user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        expires_at TIMESTAMP NOT NULL,
        created_at TIMESTAMP DEFAULT NOW()
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
    
    create_alert_events_table = """
    CREATE TABLE IF NOT EXISTS alert_events (
        id SERIAL PRIMARY KEY,
        alert_type TEXT NOT NULL CHECK (alert_type IN ('HIGH_IMPACT_EVENT','REGIONAL_RISK_SPIKE','ASSET_RISK_SPIKE','DAILY_DIGEST')),
        scope_region TEXT NULL,
        scope_assets TEXT[] NOT NULL DEFAULT '{}',
        severity INT NOT NULL DEFAULT 3 CHECK (severity BETWEEN 1 AND 5),
        headline TEXT NOT NULL,
        body TEXT NOT NULL,
        driver_event_ids INT[] NULL,
        cooldown_key TEXT NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT NOW()
    );
    """
    
    create_user_alert_deliveries_table = """
    CREATE TABLE IF NOT EXISTS user_alert_deliveries (
        id SERIAL PRIMARY KEY,
        user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        alert_event_id INT NOT NULL REFERENCES alert_events(id) ON DELETE CASCADE,
        channel TEXT NOT NULL CHECK (channel IN ('email','telegram','sms','account')),
        status TEXT NOT NULL CHECK (status IN ('queued','sent','skipped','failed')),
        reason TEXT NULL,
        provider_message_id TEXT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        sent_at TIMESTAMP NULL
    );
    """
    
    create_alert_v2_indexes = [
        "CREATE INDEX IF NOT EXISTS idx_alert_events_created_at ON alert_events(created_at DESC);",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_alert_events_cooldown_key ON alert_events(cooldown_key);",
        "CREATE INDEX IF NOT EXISTS idx_user_alert_deliveries_user_time ON user_alert_deliveries(user_id, created_at DESC);",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_user_alert_deliveries_unique ON user_alert_deliveries(user_id, alert_event_id, channel);",
        "CREATE INDEX IF NOT EXISTS idx_user_alert_deliveries_status ON user_alert_deliveries(status);",
        "CREATE INDEX IF NOT EXISTS idx_user_alert_deliveries_event ON user_alert_deliveries(alert_event_id);"
    ]
    
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
        
        logger.info("Creating sessions table...")
        cursor.execute(create_sessions_table)
        
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
        
        logger.info("Creating alert_events table (v2)...")
        cursor.execute(create_alert_events_table)
        
        logger.info("Creating user_alert_deliveries table (v2)...")
        cursor.execute(create_user_alert_deliveries_table)
        
        logger.info("Creating alert v2 indexes...")
        for idx_sql in create_alert_v2_indexes:
            cursor.execute(idx_sql)
    
    seed_plan_settings()
    
    logger.info("Adding user authentication columns...")
    add_user_auth_columns()
    
    logger.info("Migrating user_plans price column to decimal...")
    migrate_user_plans_price_to_decimal()
    
    logger.info("Ensuring users have default alert preferences...")
    ensure_user_alert_prefs()
    
    logger.info("Running Alerts v2 safety schema...")
    migrate_alerts_v2_safety_schema()
    
    logger.info("Running digest tables migration...")
    run_digest_tables_migration()
    
    logger.info("Migrations completed successfully.")


def ensure_user_alert_prefs():
    """Ensure all users have default alert preferences."""
    try:
        from src.plans.plan_helpers import migrate_user_alert_prefs
        migrated = migrate_user_alert_prefs()
        if migrated > 0:
            logger.info(f"Created default alert prefs for {migrated} users")
    except Exception as e:
        logger.error(f"Error ensuring user alert prefs: {e}")


def add_user_auth_columns():
    alter_statements = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified BOOLEAN DEFAULT FALSE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS verification_token TEXT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS verification_expires TIMESTAMP",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS pin_hash TEXT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_number VARCHAR(20)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS telegram_link_code VARCHAR(20)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS telegram_link_expires TIMESTAMP",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT NOW()",
        "CREATE INDEX IF NOT EXISTS idx_users_verification_token ON users(verification_token)",
        "CREATE INDEX IF NOT EXISTS idx_users_email_verified ON users(email_verified)",
        "CREATE INDEX IF NOT EXISTS idx_users_telegram_link_code ON users(telegram_link_code)"
    ]
    
    with get_cursor() as cursor:
        for stmt in alter_statements:
            try:
                cursor.execute(stmt)
            except Exception as e:
                logger.debug(f"Column may already exist: {e}")

def ensure_user_plans_table():
    logger.info("Ensuring user_plans table has correct schema...")
    
    with get_cursor() as cursor:
        cursor.execute("""
            DO $$ 
            BEGIN
                BEGIN
                    ALTER TABLE user_plans DROP CONSTRAINT IF EXISTS user_plans_plan_check;
                EXCEPTION WHEN OTHERS THEN
                    NULL;
                END;
                
                ALTER TABLE user_plans ADD CONSTRAINT user_plans_plan_check 
                    CHECK (plan IN ('free','personal','trader','pro','enterprise'));
            EXCEPTION WHEN OTHERS THEN
                NULL;
            END $$;
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_plans_plan ON user_plans(plan);")
    
    logger.info("user_plans table schema updated.")


def migrate_user_plans_price_to_decimal():
    logger.info("Migrating user_plans.plan_price_usd from INTEGER to NUMERIC(10,2)...")
    
    with get_cursor() as cursor:
        cursor.execute("""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'user_plans' 
                    AND column_name = 'plan_price_usd'
                    AND data_type = 'integer'
                ) THEN
                    ALTER TABLE user_plans 
                    ALTER COLUMN plan_price_usd TYPE NUMERIC(10,2) 
                    USING plan_price_usd::NUMERIC(10,2);
                    RAISE NOTICE 'Migrated plan_price_usd to NUMERIC(10,2)';
                END IF;
            END $$;
        """)
    
    logger.info("user_plans.plan_price_usd migration complete.")


def migrate_alerts_v2_safety_schema():
    """
    Step 3 migrations: Add advisory lock safety columns and constraints.
    
    1. alert_events: Add event_fingerprint (unique), fanout_completed_at
    2. user_alert_deliveries: Add delivery_kind, attempts, next_retry_at, last_error
    3. Add unique constraints for idempotency
    """
    logger.info("Running Alerts v2 safety schema migration...")
    
    with get_cursor() as cursor:
        cursor.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'alert_events' AND column_name = 'event_fingerprint'
                ) THEN
                    ALTER TABLE alert_events ADD COLUMN event_fingerprint TEXT;
                    RAISE NOTICE 'Added event_fingerprint column to alert_events';
                END IF;
            END $$;
        """)
        
        cursor.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'alert_events' AND column_name = 'fanout_completed_at'
                ) THEN
                    ALTER TABLE alert_events ADD COLUMN fanout_completed_at TIMESTAMP NULL;
                    RAISE NOTICE 'Added fanout_completed_at column to alert_events';
                END IF;
            END $$;
        """)
        
        cursor.execute("""
            UPDATE alert_events 
            SET event_fingerprint = cooldown_key 
            WHERE event_fingerprint IS NULL;
        """)
        
        cursor.execute("""
            DO $$
            BEGIN
                ALTER TABLE alert_events ALTER COLUMN event_fingerprint SET NOT NULL;
            EXCEPTION WHEN OTHERS THEN
                RAISE NOTICE 'event_fingerprint NOT NULL constraint may already exist: %', SQLERRM;
            END $$;
        """)
        
        cursor.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_indexes 
                    WHERE tablename = 'alert_events' AND indexname = 'uq_alert_events_fingerprint'
                ) THEN
                    CREATE UNIQUE INDEX uq_alert_events_fingerprint ON alert_events(event_fingerprint);
                    RAISE NOTICE 'Created unique index on event_fingerprint';
                END IF;
            END $$;
        """)
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_alert_events_fanout_completed ON alert_events(fanout_completed_at);")
        
        cursor.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'user_alert_deliveries' AND column_name = 'delivery_kind'
                ) THEN
                    ALTER TABLE user_alert_deliveries ADD COLUMN delivery_kind TEXT NOT NULL DEFAULT 'instant';
                    RAISE NOTICE 'Added delivery_kind column to user_alert_deliveries';
                END IF;
            END $$;
        """)
        
        cursor.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'user_alert_deliveries' AND column_name = 'attempts'
                ) THEN
                    ALTER TABLE user_alert_deliveries ADD COLUMN attempts INT NOT NULL DEFAULT 0;
                    RAISE NOTICE 'Added attempts column to user_alert_deliveries';
                END IF;
            END $$;
        """)
        
        cursor.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'user_alert_deliveries' AND column_name = 'next_retry_at'
                ) THEN
                    ALTER TABLE user_alert_deliveries ADD COLUMN next_retry_at TIMESTAMP NULL;
                    RAISE NOTICE 'Added next_retry_at column to user_alert_deliveries';
                END IF;
            END $$;
        """)
        
        cursor.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'user_alert_deliveries' AND column_name = 'last_error'
                ) THEN
                    ALTER TABLE user_alert_deliveries ADD COLUMN last_error TEXT NULL;
                    RAISE NOTICE 'Added last_error column to user_alert_deliveries';
                END IF;
            END $$;
        """)
        
        cursor.execute("""
            ALTER TABLE user_alert_deliveries 
            DROP CONSTRAINT IF EXISTS user_alert_deliveries_status_check;
        """)
        cursor.execute("""
            ALTER TABLE user_alert_deliveries 
            ADD CONSTRAINT user_alert_deliveries_status_check 
            CHECK (status IN ('queued','sending','sent','failed','skipped'));
        """)
        
        cursor.execute("""
            DROP INDEX IF EXISTS uq_user_alert_deliveries_unique;
        """)
        cursor.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_indexes 
                    WHERE tablename = 'user_alert_deliveries' AND indexname = 'uq_user_alert_deliveries_full'
                ) THEN
                    CREATE UNIQUE INDEX uq_user_alert_deliveries_full 
                    ON user_alert_deliveries(alert_event_id, user_id, channel, delivery_kind);
                    RAISE NOTICE 'Created unique index on (alert_event_id, user_id, channel, delivery_kind)';
                END IF;
            END $$;
        """)
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_alert_deliveries_retry ON user_alert_deliveries(next_retry_at) WHERE next_retry_at IS NOT NULL;")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_alert_deliveries_queued ON user_alert_deliveries(created_at) WHERE status = 'queued';")
    
    logger.info("Alerts v2 safety schema migration complete.")


def run_digest_tables_migration():
    """Create tables for digest batching (Step 5)."""
    logger.info("Running digest tables migration...")
    
    with get_cursor() as cursor:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_alert_digests (
                id SERIAL PRIMARY KEY,
                user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                channel TEXT NOT NULL CHECK (channel IN ('email', 'telegram')),
                period TEXT NOT NULL CHECK (period IN ('daily', 'hourly')),
                window_start TIMESTAMP NOT NULL,
                window_end TIMESTAMP NOT NULL,
                digest_key TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'sending', 'sent', 'failed', 'skipped')),
                attempts INT NOT NULL DEFAULT 0,
                next_retry_at TIMESTAMP NULL,
                last_error TEXT NULL,
                sent_at TIMESTAMP NULL,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_alert_digest_items (
                id SERIAL PRIMARY KEY,
                digest_id INT NOT NULL REFERENCES user_alert_digests(id) ON DELETE CASCADE,
                delivery_id INT NOT NULL REFERENCES user_alert_deliveries(id) ON DELETE CASCADE,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                UNIQUE(digest_id, delivery_id)
            );
        """)
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_alert_digests_status ON user_alert_digests(status);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_alert_digests_user ON user_alert_digests(user_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_alert_digests_window ON user_alert_digests(window_start, window_end);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_alert_digests_retry ON user_alert_digests(next_retry_at) WHERE next_retry_at IS NOT NULL;")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_alert_digest_items_delivery ON user_alert_digest_items(delivery_id);")
    
    logger.info("Digest tables migration complete.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migrations()
