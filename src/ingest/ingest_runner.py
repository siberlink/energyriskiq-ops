import logging
import os
import sys
import re
from datetime import datetime
from typing import Tuple, Set

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

INSERT_SUCCESS = "inserted"
INSERT_DUPLICATE = "duplicate"
INSERT_FAILED = "failed"
INSERT_DEDUPE = "dedupe"

def normalize_title(title: str) -> str:
    """Normalize title for deduplication: lowercase, strip punctuation, collapse whitespace."""
    title = title.lower().strip()
    title = re.sub(r'[^\w\s]', '', title)
    title = re.sub(r'\s+', ' ', title)
    return title

def start_ingestion_run() -> int:
    result = execute_one(
        "INSERT INTO ingestion_runs (status, total_items, inserted_items, skipped_duplicates, failed_items) VALUES ('running', 0, 0, 0, 0) RETURNING id"
    )
    run_id = result['id']
    logger.info(f"Started ingestion run #{run_id}")
    return run_id

def finish_ingestion_run(run_id: int, status: str, total: int, inserted: int, skipped: int, failed: int):
    notes = f"Total: {total}, Inserted: {inserted}, Skipped: {skipped}, Failed: {failed}"
    with get_cursor() as cursor:
        cursor.execute(
            """UPDATE ingestion_runs 
               SET finished_at = NOW(), status = %s, notes = %s,
                   total_items = %s, inserted_items = %s, 
                   skipped_duplicates = %s, failed_items = %s
               WHERE id = %s""",
            (status, notes, total, inserted, skipped, failed, run_id)
        )
    logger.info(f"Finished ingestion run #{run_id} with status: {status}")

def insert_event(event: dict, category: str, region: str, severity: int, classification_reason: str) -> Tuple[str, str]:
    insert_sql = """
    INSERT INTO events (title, source_name, source_url, category, region, severity_score, event_time, raw_text, classification_reason)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                event.get('raw_text'),
                classification_reason
            ))
            result = cursor.fetchone()
            
            if result:
                return INSERT_SUCCESS, f"Inserted event #{result['id']}"
            else:
                return INSERT_DUPLICATE, "Duplicate (skipped)"
    
    except Exception as e:
        logger.error(f"Error inserting event: {e}")
        return INSERT_FAILED, str(e)

def run_ingestion():
    logger.info("=" * 60)
    logger.info("Starting EnergyRiskIQ Event Ingestion Pipeline")
    logger.info("=" * 60)
    
    run_migrations()
    
    run_id = start_ingestion_run()
    
    inserted_count = 0
    skipped_count = 0
    dedupe_count = 0
    error_count = 0
    total_count = 0
    
    seen_titles: Set[str] = set()
    
    try:
        events = fetch_all_feeds()
        total_count = len(events)
        
        events_sorted = sorted(events, key=lambda e: e.get('weight', 0.5), reverse=True)
        
        for event in events_sorted:
            try:
                normalized = normalize_title(event['title'])
                if normalized in seen_titles:
                    dedupe_count += 1
                    logger.debug(f"Dedupe: {event['title'][:50]}... (similar title already processed)")
                    continue
                seen_titles.add(normalized)
                
                category, region, severity, classification_reason, confidence = classify_event(
                    event['title'], 
                    event.get('raw_text', ''),
                    event.get('category_hint'),
                    event.get('signal_type')
                )
                
                status, message = insert_event(event, category, region, severity, classification_reason)
                
                if status == INSERT_SUCCESS:
                    inserted_count += 1
                    logger.debug(f"Inserted: {event['title'][:50]}... ({category}, {region}, sev={severity}, conf={confidence:.2f})")
                elif status == INSERT_DUPLICATE:
                    skipped_count += 1
                    logger.debug(f"Skipped: {event['title'][:50]}... - {message}")
                else:
                    error_count += 1
                    logger.error(f"Failed to insert: {event['title'][:50]}... - {message}")
            
            except Exception as e:
                error_count += 1
                logger.error(f"Error processing event '{event.get('title', 'Unknown')}': {e}")
        
        finish_ingestion_run(run_id, 'success', total_count, inserted_count, skipped_count + dedupe_count, error_count)
        
        logger.info("=" * 60)
        logger.info(f"Ingestion Complete: Total={total_count}, Inserted={inserted_count}, DB-Skipped={skipped_count}, Dedupe={dedupe_count}, Failed={error_count}")
        logger.info("=" * 60)
        
        return inserted_count, skipped_count + dedupe_count, error_count
    
    except Exception as e:
        logger.error(f"Ingestion run failed: {e}")
        finish_ingestion_run(run_id, 'failed', total_count, inserted_count, skipped_count + dedupe_count, error_count)
        raise

if __name__ == "__main__":
    run_ingestion()
