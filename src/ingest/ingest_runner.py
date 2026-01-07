import logging
import os
import sys
from datetime import datetime
from typing import Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.db.db import get_cursor, execute_one
from src.db.migrations import run_migrations
from src.ingest.rss_fetcher import fetch_all_feeds
from src.ingest.classifier import classify_event

logging.basicConfig(
    level=os.environ.get('LOG_LEVEL', 'INFO'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def start_ingestion_run() -> int:
    result = execute_one(
        "INSERT INTO ingestion_runs (status) VALUES ('running') RETURNING id"
    )
    run_id = result['id']
    logger.info(f"Started ingestion run #{run_id}")
    return run_id

def finish_ingestion_run(run_id: int, status: str, notes: str):
    with get_cursor() as cursor:
        cursor.execute(
            """UPDATE ingestion_runs 
               SET finished_at = NOW(), status = %s, notes = %s 
               WHERE id = %s""",
            (status, notes, run_id)
        )
    logger.info(f"Finished ingestion run #{run_id} with status: {status}")

def insert_event(event: dict, category: str, region: str, severity: int) -> Tuple[bool, str]:
    insert_sql = """
    INSERT INTO events (title, source_name, source_url, category, region, severity_score, event_time, raw_text)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (source_url) DO NOTHING
    RETURNING id
    """
    
    try:
        with get_cursor() as cursor:
            cursor.execute(insert_sql, (
                event['title'],
                event['source_name'],
                event['source_url'],
                category,
                region,
                severity,
                event.get('event_time'),
                event.get('raw_text')
            ))
            result = cursor.fetchone()
            
            if result:
                return True, f"Inserted event #{result['id']}"
            else:
                return False, "Duplicate (skipped)"
    
    except Exception as e:
        logger.error(f"Error inserting event: {e}")
        return False, str(e)

def run_ingestion():
    logger.info("=" * 60)
    logger.info("Starting EnergyRiskIQ Event Ingestion Pipeline")
    logger.info("=" * 60)
    
    run_migrations()
    
    run_id = start_ingestion_run()
    
    inserted_count = 0
    skipped_count = 0
    error_count = 0
    
    try:
        events = fetch_all_feeds()
        
        for event in events:
            try:
                category, region, severity = classify_event(
                    event['title'], 
                    event.get('raw_text', '')
                )
                
                success, message = insert_event(event, category, region, severity)
                
                if success:
                    inserted_count += 1
                    logger.debug(f"Inserted: {event['title'][:50]}... ({category}, {region}, sev={severity})")
                else:
                    skipped_count += 1
                    logger.debug(f"Skipped: {event['title'][:50]}... - {message}")
            
            except Exception as e:
                error_count += 1
                logger.error(f"Error processing event '{event.get('title', 'Unknown')}': {e}")
        
        notes = f"Inserted: {inserted_count}, Skipped: {skipped_count}, Errors: {error_count}"
        finish_ingestion_run(run_id, 'success', notes)
        
        logger.info("=" * 60)
        logger.info(f"Ingestion Complete: {notes}")
        logger.info("=" * 60)
        
        return inserted_count, skipped_count, error_count
    
    except Exception as e:
        logger.error(f"Ingestion run failed: {e}")
        finish_ingestion_run(run_id, 'failed', str(e))
        raise

if __name__ == "__main__":
    run_ingestion()
