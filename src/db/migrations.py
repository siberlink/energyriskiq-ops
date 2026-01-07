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
    
    with get_cursor() as cursor:
        logger.info("Creating events table...")
        cursor.execute(create_events_table)
        
        logger.info("Creating ingestion_runs table...")
        cursor.execute(create_ingestion_runs_table)
        
        logger.info("Creating indexes...")
        for idx_sql in create_indexes:
            cursor.execute(idx_sql)
    
    logger.info("Migrations completed successfully.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migrations()
