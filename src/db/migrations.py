import logging
from src.db.db import get_cursor

logger = logging.getLogger(__name__)

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
    
    logger.info("Migrations completed successfully.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migrations()
