import logging
import json
import os
from src.db.db import get_cursor

logger = logging.getLogger(__name__)

PLAN_SETTINGS_SEED = [
    {
        "plan_code": "free",
        "display_name": "Free",
        "monthly_price_usd": 0.00,
        "allowed_alert_types": ["HIGH_IMPACT_EVENT"],
        "max_regions": 1,
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
        "max_regions": 2,
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
        "max_regions": 3,
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
        "max_regions": 4,
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
        "max_regions": -1,
        "max_email_alerts_per_day": 30,
        "delivery_config": {
            "email": {"max_per_day": 30, "realtime_limit": None, "mode": "limited"},
            "telegram": {"enabled": True, "send_all": True},
            "sms": {"enabled": True, "send_all": True},
            "account": {"show_all": True}
        }
    }
]

SOURCES_SEED = [
    # Tier 1 - EU & Policy / Regulation
    {"name": "European Commission – Energy", "feed_url": "https://ec.europa.eu/energy/rss.xml", "category": "energy", "region": "Europe", "signal_type": "regulation", "weight": 1.0, "is_active": True},
    {"name": "Council of the EU – Sanctions", "feed_url": "https://www.consilium.europa.eu/en/press/rss/", "category": "geopolitical", "region": "Europe", "signal_type": "policy", "weight": 1.0, "is_active": True},
    {"name": "ACER (EU Energy Regulator)", "feed_url": "https://acer.europa.eu/rss.xml", "category": "energy", "region": "Europe", "signal_type": "regulation", "weight": 1.0, "is_active": True},
    {"name": "ENTSO-E News", "feed_url": "https://www.entsoe.eu/news/rss/", "category": "energy", "region": "Europe", "signal_type": "infrastructure", "weight": 0.9, "is_active": True},
    
    # Tier 1 - Commodity & Market Intelligence
    {"name": "S&P Global Platts", "feed_url": "https://www.spglobal.com/platts/en/rss", "category": "energy", "region": "Global", "signal_type": "market", "weight": 0.9, "is_active": True},
    {"name": "Argus Media", "feed_url": "https://www.argusmedia.com/en/rss", "category": "energy", "region": "Global", "signal_type": "market", "weight": 0.9, "is_active": True},
    {"name": "EIA (US Energy Info Admin)", "feed_url": "https://www.eia.gov/rss/", "category": "energy", "region": "Global", "signal_type": "market", "weight": 0.9, "is_active": True},
    
    # Tier 2 - Geopolitics, Conflict & Sanctions
    {"name": "Al Jazeera News", "feed_url": "https://www.aljazeera.com/xml/rss/all.xml", "category": "geopolitical", "region": "Global", "signal_type": "conflict", "weight": 0.7, "is_active": True},
    {"name": "Reuters Energy", "feed_url": "https://www.reutersagency.com/feed/?taxonomy=best-sectors&post_type=best&best-sectors=commodities-energy", "category": "energy", "region": "Global", "signal_type": "market", "weight": 1.0, "is_active": True},
    {"name": "Financial Times – Energy", "feed_url": "https://www.ft.com/rss/energy", "category": "energy", "region": "Global", "signal_type": "market", "weight": 0.9, "is_active": True},
    {"name": "Politico Europe – Energy", "feed_url": "https://www.politico.eu/feed/", "category": "geopolitical", "region": "Europe", "signal_type": "policy", "weight": 0.8, "is_active": True},
    {"name": "Institute for the Study of War (ISW)", "feed_url": "https://www.understandingwar.org/rss.xml", "category": "geopolitical", "region": "Global", "signal_type": "conflict", "weight": 0.9, "is_active": True},
    {"name": "ReliefWeb (UN Crisis Feed)", "feed_url": "https://reliefweb.int/rss.xml", "category": "geopolitical", "region": "Global", "signal_type": "conflict", "weight": 0.8, "is_active": True},
    {"name": "NATO News", "feed_url": "https://www.nato.int/cps/en/natohq/rss.htm", "category": "geopolitical", "region": "Global", "signal_type": "policy", "weight": 0.9, "is_active": True},
    
    # Tier 3 - LNG, Shipping, Logistics
    {"name": "FreightWaves", "feed_url": "https://www.freightwaves.com/news/feed", "category": "supply_chain", "region": "Global", "signal_type": "shipping", "weight": 0.8, "is_active": True},
    {"name": "gCaptain (Maritime)", "feed_url": "https://gcaptain.com/feed/", "category": "supply_chain", "region": "Global", "signal_type": "shipping", "weight": 0.7, "is_active": True},
    {"name": "Lloyd's List", "feed_url": "https://lloydslist.maritimeintelligence.informa.com/rss", "category": "supply_chain", "region": "Global", "signal_type": "shipping", "weight": 0.9, "is_active": True},
    {"name": "Splash247", "feed_url": "https://splash247.com/feed/", "category": "supply_chain", "region": "Global", "signal_type": "shipping", "weight": 0.7, "is_active": True},
    {"name": "Port Strategy", "feed_url": "https://www.portstrategy.com/rss", "category": "supply_chain", "region": "Global", "signal_type": "shipping", "weight": 0.7, "is_active": True},
    
    # Tier 4 - Power Markets & Renewables
    {"name": "OilPrice.com", "feed_url": "https://oilprice.com/rss/main", "category": "energy", "region": "Global", "signal_type": "market", "weight": 0.7, "is_active": True},
    {"name": "Energy Live News", "feed_url": "https://www.energylivenews.com/feed/", "category": "energy", "region": "Europe", "signal_type": "market", "weight": 0.7, "is_active": True},
    {"name": "Renewables Now Europe", "feed_url": "https://renewablesnow.com/news/feed/", "category": "energy", "region": "Europe", "signal_type": "market", "weight": 0.7, "is_active": True},
    {"name": "Power Technology", "feed_url": "https://www.power-technology.com/feed/", "category": "energy", "region": "Europe", "signal_type": "infrastructure", "weight": 0.7, "is_active": True},
    {"name": "Euractiv Energy", "feed_url": "https://www.euractiv.com/sections/energy/feed/", "category": "energy", "region": "Europe", "signal_type": "policy", "weight": 0.8, "is_active": True},
    {"name": "Montel News", "feed_url": "https://www.montelnews.com/en/rss", "category": "energy", "region": "Europe", "signal_type": "market", "weight": 0.8, "is_active": True},
    {"name": "ICIS Energy", "feed_url": "https://www.icis.com/explore/rss/", "category": "energy", "region": "Europe", "signal_type": "market", "weight": 0.8, "is_active": True},
    {"name": "Ember Climate", "feed_url": "https://ember-climate.org/feed/", "category": "energy", "region": "Global", "signal_type": "market", "weight": 0.7, "is_active": True},

    # Tier 2 - Maritime (added v1.1)
    {"name": "MarineLink / Maritime Reporter", "feed_url": "https://www.marinelink.com/news/rss", "category": "supply_chain", "region": "Global", "signal_type": "shipping", "weight": 0.85, "is_active": True},
    {"name": "IMO Maritime Security", "feed_url": "https://news.google.com/rss/search?q=when:7d+%22International+Maritime+Organization%22+OR+IMO+shipping+security&ceid=US:en&hl=en-US&gl=US", "category": "supply_chain", "region": "Global", "signal_type": "regulation", "weight": 0.8, "is_active": True},

    # Tier 4 - Middle East / GCC (added v1.1)
    {"name": "QatarEnergy & Qatar LNG", "feed_url": "https://news.google.com/rss/search?q=when:24h+QatarEnergy+OR+%22Qatar+LNG%22+OR+%22Qatar+gas%22&ceid=US:en&hl=en-US&gl=US", "category": "energy", "region": "Middle East", "signal_type": "market", "weight": 0.9, "is_active": True},
    {"name": "Saudi Aramco & Saudi Oil", "feed_url": "https://news.google.com/rss/search?q=when:24h+%22Saudi+Aramco%22+OR+%22Saudi+oil%22+OR+%22Saudi+Arabia+energy%22&ceid=US:en&hl=en-US&gl=US", "category": "energy", "region": "Middle East", "signal_type": "market", "weight": 0.95, "is_active": True},
    {"name": "ADNOC & UAE Energy", "feed_url": "https://news.google.com/rss/search?q=when:24h+ADNOC+OR+%22UAE+energy%22+OR+%22UAE+oil%22&ceid=US:en&hl=en-US&gl=US", "category": "energy", "region": "Middle East", "signal_type": "market", "weight": 0.85, "is_active": True},
    {"name": "Iraq Oil & OPEC", "feed_url": "https://news.google.com/rss/search?q=when:24h+%22Iraq+oil%22+OR+%22Iraq+OPEC%22+OR+%22Basra+crude%22&ceid=US:en&hl=en-US&gl=US", "category": "energy", "region": "Middle East", "signal_type": "market", "weight": 0.8, "is_active": True},

    # Tier 4 - Russia / Black Sea / Caspian (added v1.1)
    {"name": "Ukraine Energy & Infrastructure", "feed_url": "https://news.google.com/rss/search?q=when:24h+%22Ukraine+energy%22+OR+%22Ukraine+gas%22+OR+%22Ukraine+pipeline%22+OR+%22Ukraine+power+grid%22&ceid=US:en&hl=en-US&gl=US", "category": "geopolitical", "region": "Europe", "signal_type": "conflict", "weight": 0.85, "is_active": True},
    {"name": "Kazakhstan & Caspian Energy", "feed_url": "https://news.google.com/rss/search?q=when:7d+%22Kazakhstan+oil%22+OR+%22Caspian+pipeline%22+OR+CPC+Tengiz&ceid=US:en&hl=en-US&gl=US", "category": "energy", "region": "Black Sea", "signal_type": "infrastructure", "weight": 0.8, "is_active": True},

    # Tier 4 - Asia-Pacific (added v1.1)
    {"name": "India Oil & Energy", "feed_url": "https://news.google.com/rss/search?q=when:24h+%22India+oil%22+OR+%22India+LNG%22+OR+%22India+refinery%22+OR+%22India+energy%22&ceid=US:en&hl=en-US&gl=US", "category": "energy", "region": "Asia", "signal_type": "market", "weight": 0.8, "is_active": True},
    {"name": "Japan & Korea LNG", "feed_url": "https://news.google.com/rss/search?q=when:24h+%22Japan+LNG%22+OR+%22Japan+energy%22+OR+%22Korea+LNG%22+OR+KOGAS&ceid=US:en&hl=en-US&gl=US", "category": "energy", "region": "Asia", "signal_type": "market", "weight": 0.8, "is_active": True},

    # Tier 4 - Africa (added v1.1)
    {"name": "Nigeria NNPC & LNG", "feed_url": "https://news.google.com/rss/search?q=when:24h+NNPC+OR+%22Nigeria+LNG%22+OR+%22Nigeria+oil%22&ceid=US:en&hl=en-US&gl=US", "category": "energy", "region": "North Africa", "signal_type": "market", "weight": 0.8, "is_active": True},
    {"name": "Libya & Algeria Oil/Gas", "feed_url": "https://news.google.com/rss/search?q=when:24h+%22Libya+oil%22+OR+Sonatrach+OR+%22Algeria+gas%22+OR+%22Libya+NOC%22&ceid=US:en&hl=en-US&gl=US", "category": "energy", "region": "North Africa", "signal_type": "market", "weight": 0.8, "is_active": True},

    # Tier 4 - Latin America (added v1.1)
    {"name": "Brazil Petrobras & Energy", "feed_url": "https://news.google.com/rss/search?q=when:24h+Petrobras+OR+%22Brazil+oil%22+OR+%22Brazil+energy%22&ceid=US:en&hl=en-US&gl=US", "category": "energy", "region": "South America", "signal_type": "market", "weight": 0.75, "is_active": True},
    {"name": "Venezuela PDVSA & Sanctions", "feed_url": "https://news.google.com/rss/search?q=when:7d+PDVSA+OR+%22Venezuela+oil%22+OR+%22Venezuela+sanctions%22&ceid=US:en&hl=en-US&gl=US", "category": "energy", "region": "South America", "signal_type": "market", "weight": 0.75, "is_active": True},
]


def seed_plan_settings():
    logger.info("Seeding plan_settings table...")
    
    with get_cursor() as cursor:
        for plan in PLAN_SETTINGS_SEED:
            cursor.execute(
                """
                INSERT INTO plan_settings (
                    plan_code, display_name, monthly_price_usd,
                    allowed_alert_types, max_regions, max_email_alerts_per_day, delivery_config
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (plan_code) DO UPDATE SET
                    display_name = EXCLUDED.display_name,
                    monthly_price_usd = EXCLUDED.monthly_price_usd,
                    allowed_alert_types = EXCLUDED.allowed_alert_types,
                    max_regions = EXCLUDED.max_regions,
                    max_email_alerts_per_day = EXCLUDED.max_email_alerts_per_day,
                    delivery_config = EXCLUDED.delivery_config,
                    updated_at = NOW()
                """,
                (
                    plan["plan_code"],
                    plan["display_name"],
                    plan["monthly_price_usd"],
                    plan["allowed_alert_types"],
                    plan["max_regions"],
                    plan["max_email_alerts_per_day"],
                    json.dumps(plan["delivery_config"])
                )
            )
    
    logger.info(f"Seeded {len(PLAN_SETTINGS_SEED)} plan settings.")

def run_migrations():
    if os.environ.get('SKIP_MIGRATIONS', '').lower() == 'true':
        logger.info("SKIP_MIGRATIONS=true — skipping database migrations (handled by production deployment)")
        return
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
            try:
                cursor.execute(idx_sql)
            except Exception as e:
                if "already exists" in str(e).lower() or "duplicate key" in str(e).lower():
                    logger.info(f"Index already exists, skipping: {idx_sql[:60]}...")
                else:
                    raise
    
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
    
    logger.info("Running engine observability migration...")
    run_engine_observability_migration()
    
    logger.info("Running user settings migration...")
    run_user_settings_migration()
    
    logger.info("Running billing migration...")
    run_billing_migration()
    
    sync_stripe_live_ids()
    
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
        
        cursor.execute("DROP INDEX IF EXISTS uq_user_alert_deliveries_unique;")
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

    run_public_digest_migration()


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


def run_engine_observability_migration():
    """Create tables for engine run tracking (Step 6)."""
    logger.info("Running engine observability migration...")
    
    with get_cursor() as cursor:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS alerts_engine_runs (
                id SERIAL PRIMARY KEY,
                run_id TEXT NOT NULL UNIQUE,
                triggered_by TEXT NOT NULL,
                phase TEXT NOT NULL,
                started_at TIMESTAMP NOT NULL,
                finished_at TIMESTAMP NULL,
                duration_ms INT NULL,
                status TEXT NOT NULL CHECK (status IN ('running', 'success', 'failed', 'skipped')),
                counts JSONB NULL,
                error_summary TEXT NULL,
                git_sha TEXT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS alerts_engine_run_items (
                id SERIAL PRIMARY KEY,
                run_id TEXT NOT NULL REFERENCES alerts_engine_runs(run_id) ON DELETE CASCADE,
                phase TEXT NOT NULL CHECK (phase IN ('a', 'b', 'c', 'd')),
                started_at TIMESTAMP NOT NULL,
                finished_at TIMESTAMP NULL,
                duration_ms INT NULL,
                status TEXT NOT NULL CHECK (status IN ('running', 'success', 'failed', 'skipped')),
                counts JSONB NULL,
                error_summary TEXT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
        """)
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_engine_runs_started_at ON alerts_engine_runs(started_at DESC);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_engine_runs_status ON alerts_engine_runs(status);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_engine_runs_phase ON alerts_engine_runs(phase);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_engine_run_items_run_id ON alerts_engine_run_items(run_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_engine_run_items_phase ON alerts_engine_run_items(phase);")
    
    logger.info("Engine observability migration complete.")


def run_user_settings_migration():
    """Create user_settings table for plan-based alert preferences."""
    logger.info("Running user_settings migration...")
    
    with get_cursor() as cursor:
        cursor.execute("""
            ALTER TABLE plan_settings 
            ADD COLUMN IF NOT EXISTS max_regions INT DEFAULT -1;
        """)
        
        for plan in PLAN_SETTINGS_SEED:
            cursor.execute("""
                UPDATE plan_settings 
                SET max_regions = %s 
                WHERE plan_code = %s
            """, (plan.get("max_regions", -1), plan["plan_code"]))
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_settings (
                id SERIAL PRIMARY KEY,
                user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                alert_type TEXT NOT NULL CHECK (alert_type IN ('HIGH_IMPACT_EVENT', 'REGIONAL_RISK_SPIKE', 'ASSET_RISK_SPIKE', 'DAILY_DIGEST')),
                region TEXT NULL,
                asset TEXT NULL,
                enabled BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                UNIQUE(user_id, alert_type, region, asset)
            );
        """)
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_settings_user_id ON user_settings(user_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_settings_alert_type ON user_settings(alert_type);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_settings_region ON user_settings(region);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_settings_enabled ON user_settings(enabled);")
    
    logger.info("User settings migration complete.")


STRIPE_LIVE_IDS = {
    "personal": {
        "product_id": "prod_TxDFkfsuuvvLcK",
        "price_id": "price_1SzIp3Q4PqMfSEvF4HhWPB5y"
    },
    "trader": {
        "product_id": "prod_TxDFvAIuiyV101",
        "price_id": "price_1SzIp4Q4PqMfSEvFmU1CTgNj"
    },
    "pro": {
        "product_id": "prod_TxDFtt2O3f7MFs",
        "price_id": "price_1SzIp4Q4PqMfSEvFIOr0QlN9"
    },
    "enterprise": {
        "product_id": "prod_TxDFGvTLiO1yuH",
        "price_id": "price_1SzIp5Q4PqMfSEvFsKBVblKP"
    }
}


def sync_stripe_live_ids():
    """Ensure plan_settings has the correct Live Stripe product/price IDs."""
    logger.info("Syncing Stripe Live IDs to plan_settings...")
    with get_cursor() as cursor:
        for plan_code, ids in STRIPE_LIVE_IDS.items():
            cursor.execute("""
                UPDATE plan_settings
                SET stripe_product_id = %s, stripe_price_id = %s
                WHERE plan_code = %s
                AND (stripe_product_id IS DISTINCT FROM %s OR stripe_price_id IS DISTINCT FROM %s)
            """, (ids["product_id"], ids["price_id"], plan_code, ids["product_id"], ids["price_id"]))
    logger.info("Stripe Live IDs synced.")


def run_billing_migration():
    """Add billing columns to users and plan_settings tables."""
    logger.info("Running billing migration...")
    
    with get_cursor() as cursor:
        cursor.execute("""
            ALTER TABLE users 
            ADD COLUMN IF NOT EXISTS stripe_customer_id TEXT,
            ADD COLUMN IF NOT EXISTS stripe_subscription_id TEXT,
            ADD COLUMN IF NOT EXISTS subscription_status TEXT DEFAULT 'none',
            ADD COLUMN IF NOT EXISTS subscription_current_period_end TIMESTAMP;
        """)
        
        cursor.execute("""
            ALTER TABLE plan_settings 
            ADD COLUMN IF NOT EXISTS currency VARCHAR(3) DEFAULT 'EUR',
            ADD COLUMN IF NOT EXISTS stripe_product_id TEXT,
            ADD COLUMN IF NOT EXISTS stripe_price_id TEXT;
        """)
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_stripe_customer ON users(stripe_customer_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_subscription_status ON users(subscription_status);")
    
    logger.info("Billing migration complete.")


def run_sources_migration():
    """Create sources registry table for RSS feed management."""
    logger.info("Running sources registry migration...")
    
    with get_cursor() as cursor:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sources (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                feed_url TEXT NOT NULL UNIQUE,
                category TEXT NOT NULL CHECK (category IN ('geopolitical', 'energy', 'supply_chain')),
                region TEXT NOT NULL,
                signal_type TEXT NOT NULL CHECK (signal_type IN ('policy', 'market', 'conflict', 'infrastructure', 'shipping', 'regulation')),
                weight NUMERIC(3, 2) NOT NULL DEFAULT 0.5 CHECK (weight >= 0 AND weight <= 1),
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                last_fetched_at TIMESTAMP,
                fetch_error_count INT NOT NULL DEFAULT 0,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
        """)
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sources_category ON sources(category);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sources_region ON sources(region);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sources_signal_type ON sources(signal_type);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sources_is_active ON sources(is_active);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sources_weight ON sources(weight DESC);")
    
    logger.info("Sources registry table created.")
    
    # Seed sources
    logger.info("Seeding sources registry...")
    with get_cursor() as cursor:
        for source in SOURCES_SEED:
            cursor.execute(
                """
                INSERT INTO sources (name, feed_url, category, region, signal_type, weight, is_active)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (feed_url) DO UPDATE SET
                    name = EXCLUDED.name,
                    category = EXCLUDED.category,
                    region = EXCLUDED.region,
                    signal_type = EXCLUDED.signal_type,
                    weight = EXCLUDED.weight,
                    is_active = EXCLUDED.is_active,
                    updated_at = NOW()
                """,
                (
                    source["name"],
                    source["feed_url"],
                    source["category"],
                    source["region"],
                    source["signal_type"],
                    source["weight"],
                    source["is_active"]
                )
            )
    
    logger.info(f"Seeded {len(SOURCES_SEED)} sources.")


def run_seo_tables_migration():
    """Create tables for SEO daily pages system."""
    logger.info("Running SEO tables migration...")
    
    with get_cursor() as cursor:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS seo_daily_pages (
                id SERIAL PRIMARY KEY,
                page_date DATE NOT NULL UNIQUE,
                seo_title TEXT NOT NULL,
                seo_description TEXT NOT NULL,
                page_json JSONB NOT NULL,
                alert_count INT NOT NULL DEFAULT 0,
                generated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
        """)
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_seo_daily_pages_date ON seo_daily_pages(page_date DESC);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_seo_daily_pages_alert_count ON seo_daily_pages(alert_count);")
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS seo_page_views (
                id SERIAL PRIMARY KEY,
                page_type TEXT NOT NULL,
                page_path TEXT NOT NULL,
                view_count INT NOT NULL DEFAULT 1,
                last_viewed_at TIMESTAMP NOT NULL DEFAULT NOW(),
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                UNIQUE(page_type, page_path)
            );
        """)
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_seo_page_views_path ON seo_page_views(page_path);")
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS seo_regional_daily_pages (
                id SERIAL PRIMARY KEY,
                region_slug TEXT NOT NULL,
                page_date DATE NOT NULL,
                seo_title TEXT NOT NULL,
                seo_description TEXT NOT NULL,
                page_json JSONB NOT NULL,
                alert_count INT NOT NULL DEFAULT 0,
                generated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                UNIQUE(region_slug, page_date)
            );
        """)
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_seo_regional_daily_pages_region ON seo_regional_daily_pages(region_slug);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_seo_regional_daily_pages_date ON seo_regional_daily_pages(page_date DESC);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_seo_regional_daily_pages_region_date ON seo_regional_daily_pages(region_slug, page_date DESC);")
    
    logger.info("SEO tables migration complete.")


def run_geri_migration():
    """Create intel_indices_daily table for GERI module."""
    logger.info("Running GERI tables migration...")
    
    with get_cursor() as cursor:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS intel_indices_daily (
                id SERIAL PRIMARY KEY,
                index_id TEXT NOT NULL,
                date DATE NOT NULL,
                value INT NOT NULL,
                band TEXT NOT NULL,
                trend_1d INT,
                trend_7d INT,
                components JSONB NOT NULL,
                model_version TEXT NOT NULL,
                computed_at TIMESTAMP NOT NULL DEFAULT NOW(),
                UNIQUE(index_id, date)
            );
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_intel_indices_daily_lookup 
            ON intel_indices_daily(index_id, date DESC);
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_intel_indices_daily_date 
            ON intel_indices_daily(date DESC);
        """)
    
    logger.info("GERI tables migration complete.")


def run_pro_delivery_migration():
    """Add batch_window and geri_date columns and indexes for Pro plan delivery."""
    logger.info("Running Pro delivery migration...")
    
    with get_cursor() as cursor:
        cursor.execute("""
            ALTER TABLE user_alert_deliveries 
            ADD COLUMN IF NOT EXISTS batch_window TIMESTAMP;
        """)
        
        cursor.execute("""
            ALTER TABLE user_alert_deliveries 
            ADD COLUMN IF NOT EXISTS geri_date DATE;
        """)
        
        cursor.execute("""
            ALTER TABLE user_alert_deliveries 
            ALTER COLUMN alert_event_id DROP NOT NULL;
        """)
        
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_geri_delivery_unique 
            ON user_alert_deliveries (user_id, channel, batch_window) 
            WHERE delivery_kind = 'geri' AND batch_window IS NOT NULL;
        """)
        
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_geri_delivery_by_date 
            ON user_alert_deliveries (user_id, channel, geri_date) 
            WHERE delivery_kind = 'geri' AND geri_date IS NOT NULL;
        """)
    
    logger.info("Pro delivery migration complete.")


def run_reri_migration():
    """Create RERI tables for regional indices (EERI, RERI, etc.)."""
    logger.info("Running RERI tables migration...")
    
    with get_cursor() as cursor:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reri_canonical_regions (
                region_id TEXT PRIMARY KEY,
                region_name TEXT NOT NULL,
                region_type TEXT NOT NULL,
                aliases TEXT[] NOT NULL DEFAULT '{}',
                core_assets TEXT[] DEFAULT '{}',
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reri_indices_daily (
                id SERIAL PRIMARY KEY,
                index_id TEXT NOT NULL,
                region_id TEXT NOT NULL,
                date DATE NOT NULL,
                value INT NOT NULL,
                band TEXT NOT NULL,
                trend_1d INT,
                trend_7d INT,
                components JSONB NOT NULL,
                drivers JSONB,
                model_version TEXT NOT NULL,
                computed_at TIMESTAMP NOT NULL DEFAULT NOW(),
                UNIQUE(index_id, date)
            );
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_reri_lookup 
            ON reri_indices_daily(index_id, date DESC);
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_reri_region 
            ON reri_indices_daily(region_id, date DESC);
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_reri_date 
            ON reri_indices_daily(date DESC);
        """)
        
        cursor.execute("""
            INSERT INTO reri_canonical_regions (region_id, region_name, region_type, aliases, core_assets, is_active)
            VALUES 
                ('europe', 'Europe', 'energy', ARRAY['EU', 'European', 'Western Europe', 'Eastern Europe'], ARRAY['gas', 'oil', 'power', 'fx'], TRUE),
                ('middle-east', 'Middle East', 'conflict', ARRAY['Middle Eastern', 'Gulf', 'MENA', 'Persian Gulf'], ARRAY['oil', 'gas', 'lng', 'freight'], TRUE),
                ('black-sea', 'Black Sea', 'shipping', ARRAY['Black Sea Region', 'Bosphorus', 'Ukraine Region'], ARRAY['freight', 'oil', 'grain', 'gas'], TRUE)
            ON CONFLICT (region_id) DO NOTHING;
        """)
    
    logger.info("RERI tables migration complete.")


def run_gas_storage_migration():
    """Create gas_storage_snapshots table for EU gas storage monitoring."""
    logger.info("Running gas storage migration...")
    
    with get_cursor() as cursor:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS gas_storage_snapshots (
                id SERIAL PRIMARY KEY,
                date DATE NOT NULL,
                eu_storage_percent NUMERIC(5,2) NOT NULL,
                seasonal_norm NUMERIC(5,2) NOT NULL,
                deviation_from_norm NUMERIC(6,2) NOT NULL,
                refill_speed_7d NUMERIC(8,4),
                withdrawal_rate_7d NUMERIC(8,4),
                winter_deviation_risk TEXT,
                days_to_target INT,
                risk_score INT NOT NULL,
                risk_band TEXT NOT NULL,
                interpretation TEXT,
                raw_data JSONB,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                UNIQUE(date)
            );
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_gas_storage_date 
            ON gas_storage_snapshots(date DESC);
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_gas_storage_risk 
            ON gas_storage_snapshots(risk_score DESC);
        """)
    
    logger.info("Gas storage migration complete.")


def run_oil_price_migration():
    """Create oil_price_snapshots table for crude oil price monitoring."""
    logger.info("Running oil price migration...")
    
    with get_cursor() as cursor:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS oil_price_snapshots (
                id SERIAL PRIMARY KEY,
                date DATE NOT NULL,
                brent_price NUMERIC(8,2),
                brent_change_24h NUMERIC(8,2),
                brent_change_pct NUMERIC(6,2),
                wti_price NUMERIC(8,2),
                wti_change_24h NUMERIC(8,2),
                wti_change_pct NUMERIC(6,2),
                brent_wti_spread NUMERIC(8,2),
                source TEXT,
                raw_data JSONB,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                UNIQUE(date)
            );
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_oil_price_date 
            ON oil_price_snapshots(date DESC);
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_oil_brent_price 
            ON oil_price_snapshots(brent_price DESC);
        """)
    
    logger.info("Oil price migration complete.")


def run_lng_price_migration():
    """Create lng_price_snapshots table for LNG (JKM) price monitoring."""
    logger.info("Running LNG price migration...")

    with get_cursor() as cursor:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS lng_price_snapshots (
                id SERIAL PRIMARY KEY,
                date DATE NOT NULL,
                jkm_price NUMERIC(8,2),
                jkm_change_24h NUMERIC(8,2),
                jkm_change_pct NUMERIC(6,2),
                source TEXT,
                raw_data JSONB,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                UNIQUE(date)
            );
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_lng_price_date
            ON lng_price_snapshots(date DESC);
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_lng_jkm_price
            ON lng_price_snapshots(jkm_price DESC);
        """)

    logger.info("LNG price migration complete.")


def run_fix_skipped_alerts():
    """One-time fix for alert deliveries incorrectly marked as 'failed' when email was disabled."""
    with get_cursor() as cursor:
        cursor.execute("""
            UPDATE user_alert_deliveries 
            SET status = 'skipped', last_error = 'email_disabled'
            WHERE status = 'failed' 
              AND last_error LIKE '%Email sending is disabled%'
        """)
        updated = cursor.rowcount
        if updated > 0:
            logger.info(f"Fixed {updated} alert deliveries from 'failed' to 'skipped'")


def run_signal_quality_migration():
    """Add signal quality scoring columns to events table and expand category constraint."""
    if os.environ.get('SKIP_MIGRATIONS', '').lower() == 'true':
        logger.info("SKIP_MIGRATIONS=true — skipping signal quality migration")
        return
    with get_cursor() as cursor:
        cursor.execute("""
            DO $$
            BEGIN
                ALTER TABLE events DROP CONSTRAINT IF EXISTS events_category_check;
            EXCEPTION WHEN undefined_object THEN
                NULL;
            END $$;
        """)
        cursor.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'events' AND column_name = 'signal_quality_score'
                ) THEN
                    ALTER TABLE events ADD COLUMN signal_quality_score REAL NULL;
                END IF;
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'events' AND column_name = 'signal_quality_band'
                ) THEN
                    ALTER TABLE events ADD COLUMN signal_quality_band TEXT NULL;
                END IF;
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'events' AND column_name = 'signal_quality_details'
                ) THEN
                    ALTER TABLE events ADD COLUMN signal_quality_details JSONB NULL;
                END IF;
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'events' AND column_name = 'is_geri_driver'
                ) THEN
                    ALTER TABLE events ADD COLUMN is_geri_driver BOOLEAN DEFAULT FALSE;
                END IF;
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'events' AND column_name = 'market_relevance'
                ) THEN
                    ALTER TABLE events ADD COLUMN market_relevance REAL NULL;
                END IF;
            END $$;
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_signal_quality ON events (signal_quality_score DESC NULLS LAST);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_geri_driver ON events (is_geri_driver) WHERE is_geri_driver = TRUE;")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_quality_band ON events (signal_quality_band);")
    logger.info("Signal quality migration complete.")


def run_public_digest_migration():
    logger.info("Running public digest pages migration...")
    with get_cursor() as cursor:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS public_digest_pages (
                id SERIAL PRIMARY KEY,
                page_date DATE NOT NULL UNIQUE,
                seo_title TEXT,
                seo_description TEXT,
                page_json JSONB,
                generated_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_public_digest_date ON public_digest_pages(page_date DESC);")
    logger.info("Public digest pages migration complete.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migrations()
    run_seo_tables_migration()
    run_sources_migration()
    run_geri_migration()
    run_pro_delivery_migration()
    run_reri_migration()
    run_gas_storage_migration()
    run_oil_price_migration()
    run_lng_price_migration()
    run_gas_storage_migration()
    run_signal_quality_migration()
    run_public_digest_migration()
    _recalculate_stale_bands()


def _recalculate_stale_bands():
    """Fix any band labels that don't match the 5-band system (20-point intervals)."""
    band_fix_sql = """
    UPDATE {table} SET band = 
      CASE 
        WHEN value <= 20 THEN 'LOW'
        WHEN value <= 40 THEN 'MODERATE'
        WHEN value <= 60 THEN 'ELEVATED'
        WHEN value <= 80 THEN 'SEVERE'
        ELSE 'CRITICAL'
      END
    WHERE band != CASE 
        WHEN value <= 20 THEN 'LOW'
        WHEN value <= 40 THEN 'MODERATE'
        WHEN value <= 60 THEN 'ELEVATED'
        WHEN value <= 80 THEN 'SEVERE'
        ELSE 'CRITICAL'
      END
      AND value IS NOT NULL
    """
    try:
        with get_cursor() as cursor:
            cursor.execute(band_fix_sql.format(table='intel_indices_daily'))
            geri_fixed = cursor.rowcount
            cursor.execute(band_fix_sql.format(table='reri_indices_daily'))
            eeri_fixed = cursor.rowcount
        if geri_fixed or eeri_fixed:
            logger.info(f"Band recalculation: fixed {geri_fixed} GERI + {eeri_fixed} EERI stale band labels.")
        else:
            logger.info("Band recalculation: all bands are correct.")
    except Exception as e:
        logger.warning(f"Band recalculation skipped: {e}")


def run_eriq_migration():
    try:
        with get_cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS eriq_conversations (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    question TEXT NOT NULL,
                    response TEXT,
                    intent VARCHAR(50),
                    mode VARCHAR(30),
                    plan VARCHAR(30),
                    tokens_used INTEGER DEFAULT 0,
                    rating INTEGER,
                    feedback_comment TEXT,
                    success BOOLEAN DEFAULT true,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_eriq_conv_user_date
                ON eriq_conversations (user_id, created_at)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_eriq_conv_created
                ON eriq_conversations (created_at)
            """)
            cursor.execute("""
                ALTER TABLE eriq_conversations
                ADD COLUMN IF NOT EXISTS feedback_tags TEXT[] DEFAULT '{}'
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_eriq_conv_rating
                ON eriq_conversations (rating) WHERE rating IS NOT NULL
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_eriq_conv_intent
                ON eriq_conversations (intent)
            """)
            logger.info("ERIQ conversations table migration completed")

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS eriq_token_balances (
                    user_id INTEGER PRIMARY KEY,
                    plan_monthly_allowance INTEGER NOT NULL DEFAULT 50000,
                    allowance_remaining INTEGER NOT NULL DEFAULT 50000,
                    purchased_balance INTEGER NOT NULL DEFAULT 0,
                    period_start TIMESTAMP DEFAULT DATE_TRUNC('month', NOW()),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS eriq_token_ledger (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    delta_tokens INTEGER NOT NULL,
                    source VARCHAR(30) NOT NULL,
                    ref_info TEXT,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_token_ledger_user
                ON eriq_token_ledger (user_id, created_at)
            """)
            logger.info("ERIQ token tables migration completed")
    except Exception as e:
        logger.warning(f"ERIQ migration skipped: {e}")
