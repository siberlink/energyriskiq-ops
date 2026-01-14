#!/usr/bin/env python3
"""
Alerts v2 CLI Runner

Execute Alerts v2 engine phases from command line (for GitHub Actions or local testing).

Usage:
    python -m src.alerts.runner --phase a
    python -m src.alerts.runner --phase b
    python -m src.alerts.runner --phase c
    python -m src.alerts.runner --phase all
    python -m src.alerts.runner --phase all --dry-run

Safety Features:
- Advisory locks per phase prevent concurrent execution
- If lock cannot be acquired, phase returns skip (exit 0)
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Dict, Optional

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

ALERTS_V2_ENABLED = os.environ.get('ALERTS_V2_ENABLED', 'true').lower() == 'true'

LOCK_KEYS = {
    'a': 'alerts_v2_phase_a',
    'b': 'alerts_v2_phase_b',
    'c': 'alerts_v2_phase_c',
}


def validate_environment() -> bool:
    """Validate required environment variables and database connection."""
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        logger.error("DATABASE_URL environment variable is not set")
        return False
    
    try:
        from src.db.db import get_cursor
        with get_cursor() as cursor:
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            if not result:
                logger.error("Database connection test failed")
                return False
        logger.info("Database connection validated")
        return True
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return False


def run_phase_a(now: datetime, dry_run: bool = False) -> Dict:
    """
    Phase A: Generate global alert events (user-agnostic).
    
    Creates alert_events rows for:
    - REGIONAL_RISK_SPIKE
    - ASSET_RISK_SPIKE  
    - HIGH_IMPACT_EVENT
    
    SAFETY: alert_events table must NEVER contain user_id.
    Uses advisory lock to prevent concurrent execution.
    """
    from src.alerts.alerts_engine_v2 import generate_global_alert_events
    from src.alerts.db_locks import AdvisoryLock
    
    start_time = time.time()
    logger.info(f"Phase A starting at {now.isoformat()}")
    
    with AdvisoryLock(LOCK_KEYS['a']) as lock:
        if not lock.acquired:
            logger.warning("Phase A: Lock not acquired, skipping (another instance is running)")
            return {
                'phase': 'A',
                'phase_name': 'Generate Global Alert Events',
                'start_time': now.isoformat(),
                'end_time': datetime.now(timezone.utc).isoformat(),
                'duration_seconds': round(time.time() - start_time, 2),
                'dry_run': dry_run,
                'status': 'skipped',
                'skipped': True,
                'reason': 'lock_not_acquired',
                'counts': {}
            }
        
        if dry_run:
            logger.info("Phase A: DRY RUN - no database changes")
            result = {'dry_run': True, 'regional_spikes': 0, 'asset_spikes': 0, 'high_impact': 0, 'total': 0, 'skipped': 0}
        else:
            result = generate_global_alert_events()
    
    duration = time.time() - start_time
    
    return {
        'phase': 'A',
        'phase_name': 'Generate Global Alert Events',
        'start_time': now.isoformat(),
        'end_time': datetime.now(timezone.utc).isoformat(),
        'duration_seconds': round(duration, 2),
        'dry_run': dry_run,
        'status': 'success',
        'locked': True,
        'counts': result
    }


def run_phase_b(now: datetime, since_hours: int = 24, dry_run: bool = False) -> Dict:
    """
    Phase B: Fanout alert events to eligible users.
    
    For each alert_event, creates user_alert_deliveries rows
    for eligible users based on plan, preferences, and quotas.
    Uses advisory lock to prevent concurrent execution.
    """
    from src.alerts.alerts_engine_v2 import fanout_alert_events_to_users
    from src.alerts.db_locks import AdvisoryLock
    
    start_time = time.time()
    logger.info(f"Phase B starting at {now.isoformat()}, since_hours={since_hours}")
    
    with AdvisoryLock(LOCK_KEYS['b']) as lock:
        if not lock.acquired:
            logger.warning("Phase B: Lock not acquired, skipping (another instance is running)")
            return {
                'phase': 'B',
                'phase_name': 'Fanout to Users',
                'start_time': now.isoformat(),
                'end_time': datetime.now(timezone.utc).isoformat(),
                'duration_seconds': round(time.time() - start_time, 2),
                'dry_run': dry_run,
                'since_hours': since_hours,
                'status': 'skipped',
                'skipped': True,
                'reason': 'lock_not_acquired',
                'counts': {}
            }
        
        if dry_run:
            logger.info("Phase B: DRY RUN - no database changes")
            result = {'dry_run': True, 'processed': 0, 'deliveries_created': 0}
        else:
            result = fanout_alert_events_to_users()
    
    duration = time.time() - start_time
    
    return {
        'phase': 'B',
        'phase_name': 'Fanout to Users',
        'start_time': now.isoformat(),
        'end_time': datetime.now(timezone.utc).isoformat(),
        'duration_seconds': round(duration, 2),
        'dry_run': dry_run,
        'since_hours': since_hours,
        'status': 'success',
        'locked': True,
        'counts': result
    }


def run_phase_c(now: datetime, batch_size: int = 200, dry_run: bool = False) -> Dict:
    """
    Phase C: Send queued deliveries.
    
    Processes user_alert_deliveries with status='queued'
    and sends via appropriate channel (email, telegram, sms).
    Uses advisory lock to prevent concurrent execution.
    Note: Phase C also uses FOR UPDATE SKIP LOCKED internally for row-level safety.
    """
    from src.alerts.alerts_engine_v2 import send_queued_deliveries
    from src.alerts.db_locks import AdvisoryLock
    
    start_time = time.time()
    logger.info(f"Phase C starting at {now.isoformat()}, batch_size={batch_size}")
    
    with AdvisoryLock(LOCK_KEYS['c']) as lock:
        if not lock.acquired:
            logger.warning("Phase C: Lock not acquired, skipping (another instance is running)")
            return {
                'phase': 'C',
                'phase_name': 'Send Queued Deliveries',
                'start_time': now.isoformat(),
                'end_time': datetime.now(timezone.utc).isoformat(),
                'duration_seconds': round(time.time() - start_time, 2),
                'dry_run': dry_run,
                'batch_size': batch_size,
                'status': 'skipped',
                'skipped': True,
                'reason': 'lock_not_acquired',
                'counts': {}
            }
        
        if dry_run:
            logger.info("Phase C: DRY RUN - no messages sent")
            from src.db.db import execute_one
            queued_count = execute_one(
                "SELECT COUNT(*) as cnt FROM user_alert_deliveries WHERE status = 'queued'"
            )
            result = {
                'dry_run': True, 
                'queued_count': queued_count['cnt'] if queued_count else 0,
                'sent': 0, 
                'failed': 0
            }
        else:
            result = send_queued_deliveries(batch_size=batch_size)
    
    duration = time.time() - start_time
    
    return {
        'phase': 'C',
        'phase_name': 'Send Queued Deliveries',
        'start_time': now.isoformat(),
        'end_time': datetime.now(timezone.utc).isoformat(),
        'duration_seconds': round(duration, 2),
        'dry_run': dry_run,
        'batch_size': batch_size,
        'status': 'success',
        'locked': True,
        'counts': result
    }


def format_output(result: Dict, log_json: bool = True) -> str:
    """Format output for logging."""
    if log_json:
        return json.dumps(result, indent=2, default=str)
    else:
        lines = [
            f"Phase: {result.get('phase', 'unknown')} - {result.get('phase_name', '')}",
            f"Status: {result.get('status', 'unknown')}",
            f"Duration: {result.get('duration_seconds', 0)}s",
            f"Dry Run: {result.get('dry_run', False)}",
            f"Counts: {result.get('counts', {})}"
        ]
        return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(
        description='Alerts v2 CLI Runner - Execute alert engine phases',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.alerts.runner --phase a
  python -m src.alerts.runner --phase b --since-hours 12
  python -m src.alerts.runner --phase c --batch-size 100
  python -m src.alerts.runner --phase all --dry-run
  python -m src.alerts.runner --phase all --log-json
        """
    )
    
    parser.add_argument(
        '--phase',
        required=True,
        choices=['a', 'b', 'c', 'all'],
        help='Phase to execute: a (generate), b (fanout), c (send), or all'
    )
    parser.add_argument(
        '--since-hours',
        type=int,
        default=24,
        help='Lookback hours for Phase B selection (default: 24)'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=200,
        help='Batch size for Phase C sending (default: 200)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        default=False,
        help='Run without making database changes or sending messages'
    )
    parser.add_argument(
        '--log-json',
        action='store_true',
        default=os.environ.get('CI', 'false').lower() == 'true',
        help='Output results as JSON (default: true in CI)'
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("EnergyRiskIQ Alerts v2 CLI Runner")
    print("=" * 60)
    print(f"Phase: {args.phase.upper()}")
    print(f"Dry Run: {args.dry_run}")
    print(f"Since Hours: {args.since_hours}")
    print(f"Batch Size: {args.batch_size}")
    print(f"Log JSON: {args.log_json}")
    print("=" * 60)
    
    if not ALERTS_V2_ENABLED:
        logger.info("ALERTS_V2_ENABLED is not 'true', exiting with no-op")
        print(json.dumps({'status': 'noop', 'reason': 'ALERTS_V2_ENABLED is false'}))
        sys.exit(0)
    
    if not validate_environment():
        logger.error("Environment validation failed")
        sys.exit(1)
    
    from src.db.migrations import run_migrations
    try:
        run_migrations()
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        sys.exit(1)
    
    now = datetime.now(timezone.utc)
    results = []
    overall_status = 'success'
    
    try:
        if args.phase in ['a', 'all']:
            result_a = run_phase_a(now, dry_run=args.dry_run)
            results.append(result_a)
            print(format_output(result_a, args.log_json))
            if result_a.get('status') != 'success':
                overall_status = 'failed'
        
        if args.phase in ['b', 'all']:
            result_b = run_phase_b(now, since_hours=args.since_hours, dry_run=args.dry_run)
            results.append(result_b)
            print(format_output(result_b, args.log_json))
            if result_b.get('status') != 'success':
                overall_status = 'failed'
        
        if args.phase in ['c', 'all']:
            result_c = run_phase_c(now, batch_size=args.batch_size, dry_run=args.dry_run)
            results.append(result_c)
            print(format_output(result_c, args.log_json))
            if result_c.get('status') != 'success':
                overall_status = 'failed'
    
    except Exception as e:
        logger.error(f"Phase execution failed: {e}")
        error_result = {
            'status': 'failed',
            'error': str(e),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        print(json.dumps(error_result, indent=2))
        sys.exit(1)
    
    print("=" * 60)
    print(f"Runner Complete - Status: {overall_status}")
    print(f"Phases executed: {len(results)}")
    print("=" * 60)
    
    if args.log_json:
        summary = {
            'overall_status': overall_status,
            'phases_executed': len(results),
            'dry_run': args.dry_run,
            'completed_at': datetime.now(timezone.utc).isoformat(),
            'results': results
        }
        print(json.dumps(summary, indent=2, default=str))
    
    sys.exit(0 if overall_status == 'success' else 1)


if __name__ == '__main__':
    main()
