"""
Backfill metadata columns for existing alert_events.

This script populates raw_input, classification, category, and confidence
for alert_events that have NULL values in these columns.
"""
import logging
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.db.db import get_cursor
from src.db.migrations import run_migrations

logging.basicConfig(
    level=os.environ.get('LOG_LEVEL', 'INFO'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


ALERT_TYPE_TO_CATEGORY = {
    'HIGH_IMPACT_EVENT': 'high_impact',
    'REGIONAL_RISK_SPIKE': 'regional_risk',
    'ASSET_RISK_ALERT': 'asset_risk',
    'ASSET_RISK_SPIKE': 'asset_risk',
    'DAILY_DIGEST': 'digest',
}


def calculate_confidence_from_severity(severity: int) -> float:
    """Calculate confidence score from severity (1-5 scale)."""
    if severity is None:
        return 0.5
    confidence_map = {
        1: 0.3,
        2: 0.5,
        3: 0.7,
        4: 0.85,
        5: 0.95,
    }
    return confidence_map.get(severity, 0.7)


def build_raw_input(row: dict) -> dict:
    """Build raw_input JSONB from existing row data."""
    return {
        "type": "backfill",
        "alert_type": row['alert_type'],
        "headline": row['headline'],
        "scope_region": row['scope_region'],
        "scope_assets": row['scope_assets'] or [],
        "created_at": row['created_at'].isoformat() if row['created_at'] else None,
        "driver_event_ids": row['driver_event_ids'] or [],
    }


def build_classification(row: dict) -> dict:
    """Build classification JSONB from existing row data."""
    return {
        "alert_type": row['alert_type'],
        "severity": row['severity'],
        "backfilled": True,
    }


def backfill_alert_metadata(dry_run: bool = False) -> dict:
    """
    Backfill raw_input, classification, category, and confidence
    for all alert_events with NULL values.
    
    Returns summary statistics.
    """
    logger.info(f"Starting alert_events metadata backfill (dry_run={dry_run})")
    
    sql_select = """
    SELECT id, alert_type, scope_region, scope_assets, severity, 
           headline, body, driver_event_ids, created_at,
           raw_input, classification, category, confidence
    FROM alert_events
    WHERE raw_input IS NULL 
       OR classification IS NULL 
       OR category IS NULL 
       OR confidence IS NULL
    ORDER BY id
    """
    
    updated = 0
    skipped = 0
    errors = 0
    
    with get_cursor() as cursor:
        cursor.execute(sql_select)
        rows = cursor.fetchall()
        
        logger.info(f"Found {len(rows)} alert_events with NULL metadata")
        
        for row in rows:
            try:
                new_raw_input = row['raw_input']
                new_classification = row['classification']
                new_category = row['category']
                new_confidence = row['confidence']
                
                needs_update = False
                
                if new_raw_input is None:
                    new_raw_input = build_raw_input(row)
                    needs_update = True
                
                if new_classification is None:
                    new_classification = build_classification(row)
                    needs_update = True
                
                if new_category is None:
                    new_category = ALERT_TYPE_TO_CATEGORY.get(row['alert_type'], 'unknown')
                    needs_update = True
                
                if new_confidence is None:
                    new_confidence = calculate_confidence_from_severity(row['severity'])
                    needs_update = True
                
                if not needs_update:
                    skipped += 1
                    continue
                
                if dry_run:
                    logger.info(f"[DRY RUN] Would update alert_event {row['id']}: "
                              f"category={new_category}, confidence={new_confidence}")
                    updated += 1
                else:
                    raw_input_json = json.dumps(new_raw_input) if isinstance(new_raw_input, dict) else new_raw_input
                    classification_json = json.dumps(new_classification) if isinstance(new_classification, dict) else new_classification
                    
                    cursor.execute(
                        """UPDATE alert_events 
                           SET raw_input = %s,
                               classification = %s,
                               category = %s,
                               confidence = %s
                           WHERE id = %s""",
                        (raw_input_json, classification_json, new_category, new_confidence, row['id'])
                    )
                    updated += 1
                    logger.debug(f"Updated alert_event {row['id']}")
                    
            except Exception as e:
                logger.error(f"Error processing alert_event {row['id']}: {e}")
                errors += 1
    
    summary = {
        'total_found': len(rows) if 'rows' in dir() else 0,
        'updated': updated,
        'skipped': skipped,
        'errors': errors,
        'dry_run': dry_run,
    }
    
    logger.info(f"Backfill complete: updated={updated}, skipped={skipped}, errors={errors}")
    
    return summary


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Backfill alert_events metadata columns')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be updated without making changes')
    args = parser.parse_args()
    
    run_migrations()
    
    summary = backfill_alert_metadata(dry_run=args.dry_run)
    
    print(f"\nBackfill Summary:")
    print(f"  Total found with NULL:  {summary['total_found']}")
    print(f"  Updated:                {summary['updated']}")
    print(f"  Skipped:                {summary['skipped']}")
    print(f"  Errors:                 {summary['errors']}")
    if summary['dry_run']:
        print("\n  NOTE: This was a dry run. No changes were made.")
        print("  Run without --dry-run to apply changes.")


if __name__ == '__main__':
    main()
