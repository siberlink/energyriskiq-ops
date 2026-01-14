#!/usr/bin/env python3
"""
Alerts v2 CLI Runner

Execute Alerts v2 engine phases from command line (for GitHub Actions or local testing).

Usage:
    python -m src.alerts.runner --phase a
    python -m src.alerts.runner --phase b
    python -m src.alerts.runner --phase c
    python -m src.alerts.runner --phase d
    python -m src.alerts.runner --phase all
    python -m src.alerts.runner --phase all --dry-run

Phase Execution Order (for --phase all):
    A (Generate Events) → B (Fanout) → D (Build Digests) → C (Send)

Safety Features:
- Advisory locks per phase prevent concurrent execution
- If lock cannot be acquired, phase returns skip (exit 0)
- Digest batching is idempotent via unique digest_key constraint
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
    'd': 'alerts_v2_phase_d',
}

REQUIRED_TABLES = [
    'alert_events',
    'user_alert_deliveries', 
    'user_alert_digests',
    'alerts_engine_runs',
    'alerts_engine_run_items',
    'users',
    'user_plans',
    'user_alert_prefs',
]


def run_preflight(log_json: bool = False) -> Dict:
    """
    Run preflight validation checks before executing phases.
    
    Checks:
    1. Database connectivity
    2. Required table existence
    3. Channel configuration (env vars)
    4. Optional timezone/base URL warnings
    
    Returns dict with:
    - db_ok: bool
    - migrations_ok: bool
    - channels_configured: {email: bool, telegram: bool, sms: bool}
    - warnings: list
    - errors: list
    """
    result = {
        'db_ok': False,
        'migrations_ok': False,
        'channels_configured': {'email': False, 'telegram': False, 'sms': False},
        'tables_found': [],
        'tables_missing': [],
        'warnings': [],
        'errors': [],
    }
    
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        result['errors'].append("DATABASE_URL environment variable is not set")
        return result
    
    try:
        from src.db.db import get_cursor
        with get_cursor() as cursor:
            cursor.execute("SELECT 1")
            if cursor.fetchone():
                result['db_ok'] = True
                logger.info("Preflight: Database connection OK")
    except Exception as e:
        result['errors'].append(f"Database connection failed: {str(e)}")
        return result
    
    try:
        from src.db.db import execute_query
        rows = execute_query("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        """, fetch=True)
        existing_tables = {row['table_name'] for row in rows} if rows else set()
        
        for table in REQUIRED_TABLES:
            if table in existing_tables:
                result['tables_found'].append(table)
            else:
                result['tables_missing'].append(table)
        
        if not result['tables_missing']:
            result['migrations_ok'] = True
            logger.info("Preflight: All required tables exist")
        else:
            result['errors'].append(f"Missing tables: {', '.join(result['tables_missing'])}")
    except Exception as e:
        result['errors'].append(f"Table check failed: {str(e)}")
    
    brevo_key = os.environ.get('BREVO_API_KEY')
    resend_key = os.environ.get('RESEND_API_KEY')
    if brevo_key or resend_key:
        result['channels_configured']['email'] = True
        logger.info("Preflight: Email channel configured")
    else:
        result['warnings'].append("Email channel not configured (no BREVO_API_KEY or RESEND_API_KEY)")
    
    telegram_token = os.environ.get('TELEGRAM_BOT_TOKEN')
    if telegram_token:
        result['channels_configured']['telegram'] = True
        logger.info("Preflight: Telegram channel configured")
    else:
        result['warnings'].append("Telegram channel not configured (no TELEGRAM_BOT_TOKEN)")
    
    twilio_sid = os.environ.get('TWILIO_ACCOUNT_SID')
    twilio_token = os.environ.get('TWILIO_AUTH_TOKEN')
    twilio_phone = os.environ.get('TWILIO_PHONE_NUMBER')
    if twilio_sid and twilio_token and twilio_phone:
        result['channels_configured']['sms'] = True
        logger.info("Preflight: SMS channel configured")
    else:
        result['warnings'].append("SMS channel not configured (missing TWILIO_* vars)")
    
    any_channel = any(result['channels_configured'].values())
    if not any_channel:
        result['warnings'].append("No delivery channels configured - Phase C will skip all sends")
    
    base_url = os.environ.get('ALERTS_APP_BASE_URL')
    if not base_url:
        result['warnings'].append("ALERTS_APP_BASE_URL not set (dashboard links may be missing)")
    
    return result


def run_health_check(log_json: bool = False) -> Dict:
    """
    Get health metrics without requiring HTTP server.
    
    Returns dict with:
    - deliveries_24h: counts by channel/status
    - digests_7d: counts by channel/status
    - oldest_queued: minutes
    - last_run: run info
    """
    from src.alerts.engine_observability import get_delivery_health_metrics, get_digest_health_metrics, get_engine_runs
    from datetime import datetime, timezone
    
    result = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'deliveries_24h': {},
        'digests_7d': {},
        'last_run': None,
        'errors': [],
    }
    
    try:
        result['deliveries_24h'] = get_delivery_health_metrics(hours=24)
    except Exception as e:
        result['errors'].append(f"Failed to get delivery metrics: {str(e)}")
    
    try:
        result['digests_7d'] = get_digest_health_metrics(days=7)
    except Exception as e:
        result['errors'].append(f"Failed to get digest metrics: {str(e)}")
    
    try:
        runs = get_engine_runs(limit=1)
        if runs:
            result['last_run'] = runs[0]
    except Exception as e:
        result['errors'].append(f"Failed to get last run: {str(e)}")
    
    return result


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
    Phase C: Send queued deliveries and digests.
    
    Processes:
    1. user_alert_deliveries with status='queued' and delivery_kind='instant'
    2. user_alert_digests with status='queued'
    
    Sends via appropriate channel (email, telegram, sms).
    Uses advisory lock to prevent concurrent execution.
    Note: Phase C also uses FOR UPDATE SKIP LOCKED internally for row-level safety.
    """
    from src.alerts.alerts_engine_v2 import send_queued_deliveries, send_queued_digests
    from src.alerts.db_locks import AdvisoryLock
    
    start_time = time.time()
    logger.info(f"Phase C starting at {now.isoformat()}, batch_size={batch_size}")
    
    with AdvisoryLock(LOCK_KEYS['c']) as lock:
        if not lock.acquired:
            logger.warning("Phase C: Lock not acquired, skipping (another instance is running)")
            return {
                'phase': 'C',
                'phase_name': 'Send Queued Deliveries & Digests',
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
                "SELECT COUNT(*) as cnt FROM user_alert_deliveries WHERE status = 'queued' AND delivery_kind = 'instant'"
            )
            digest_count = execute_one(
                "SELECT COUNT(*) as cnt FROM user_alert_digests WHERE status = 'queued'"
            )
            result = {
                'dry_run': True, 
                'queued_instant_count': queued_count['cnt'] if queued_count else 0,
                'queued_digest_count': digest_count['cnt'] if digest_count else 0,
                'sent': 0, 
                'failed': 0,
                'digests': {'dry_run': True, 'digests_sent': 0}
            }
        else:
            result = send_queued_deliveries(batch_size=batch_size)
            digest_result = send_queued_digests(batch_size=batch_size // 2)
            result['digests'] = digest_result
    
    duration = time.time() - start_time
    
    return {
        'phase': 'C',
        'phase_name': 'Send Queued Deliveries & Digests',
        'start_time': now.isoformat(),
        'end_time': datetime.now(timezone.utc).isoformat(),
        'duration_seconds': round(duration, 2),
        'dry_run': dry_run,
        'batch_size': batch_size,
        'status': 'success',
        'locked': True,
        'counts': result
    }


def run_phase_d(now: datetime, period: str = None, dry_run: bool = False) -> Dict:
    """
    Phase D: Build digest batches.
    
    Groups digest deliveries into digest batches by (user_id, channel, period).
    Creates user_alert_digests records and marks individual deliveries as batched.
    
    Uses advisory lock to prevent concurrent execution.
    Idempotent via unique digest_key constraint.
    """
    from src.alerts.digest_builder import build_digests
    from src.alerts.db_locks import AdvisoryLock
    
    start_time = time.time()
    logger.info(f"Phase D starting at {now.isoformat()}, period={period or 'default'}")
    
    with AdvisoryLock(LOCK_KEYS['d']) as lock:
        if not lock.acquired:
            logger.warning("Phase D: Lock not acquired, skipping (another instance is running)")
            return {
                'phase': 'D',
                'phase_name': 'Build Digest Batches',
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
            logger.info("Phase D: DRY RUN - no database changes")
            from src.db.db import execute_one
            pending_count = execute_one(
                """SELECT COUNT(*) as cnt FROM user_alert_deliveries 
                   WHERE delivery_kind = 'digest' AND status = 'queued'"""
            )
            result = {
                'dry_run': True,
                'pending_digest_deliveries': pending_count['cnt'] if pending_count else 0,
                'digests_created': 0,
                'digest_items_attached': 0,
                'deliveries_marked_batched': 0
            }
        else:
            result = build_digests(period=period, reference_time=now)
    
    duration = time.time() - start_time
    
    return {
        'phase': 'D',
        'phase_name': 'Build Digest Batches',
        'start_time': now.isoformat(),
        'end_time': datetime.now(timezone.utc).isoformat(),
        'duration_seconds': round(duration, 2),
        'dry_run': dry_run,
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
  python -m src.alerts.runner --phase d
  python -m src.alerts.runner --phase all --dry-run
  python -m src.alerts.runner --phase all --log-json

Phase Order (for --phase all): A → B → D → C
  A: Generate global alert events
  B: Fanout to eligible users  
  D: Build digest batches
  C: Send instant + digest messages
        """
    )
    
    parser.add_argument(
        '--phase',
        required=False,
        choices=['a', 'b', 'c', 'd', 'all'],
        help='Phase to execute: a (generate), b (fanout), c (send), d (digest build), or all'
    )
    parser.add_argument(
        '--preflight',
        action='store_true',
        default=False,
        help='Run preflight validation only (check DB, tables, channels)'
    )
    parser.add_argument(
        '--health',
        action='store_true',
        default=False,
        help='Output health metrics JSON (deliveries, digests, last run)'
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
    
    if args.preflight:
        print("=" * 60)
        print("EnergyRiskIQ Alerts v2 - Preflight Check")
        print("=" * 60)
        result = run_preflight(log_json=args.log_json)
        print(json.dumps(result, indent=2, default=str))
        if result['errors']:
            print("=" * 60)
            print("PREFLIGHT FAILED - errors detected")
            sys.exit(1)
        else:
            print("=" * 60)
            print("PREFLIGHT PASSED" + (" (with warnings)" if result['warnings'] else ""))
            sys.exit(0)
    
    if args.health:
        print("=" * 60)
        print("EnergyRiskIQ Alerts v2 - Health Check")
        print("=" * 60)
        result = run_health_check(log_json=args.log_json)
        print(json.dumps(result, indent=2, default=str))
        print("=" * 60)
        sys.exit(0)
    
    if not args.phase:
        parser.error("--phase is required when not using --preflight or --health")
    
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
    all_counts = {}
    error_msg = None
    
    from src.alerts.engine_observability import EngineRunTracker
    tracker = EngineRunTracker(phase=args.phase, dry_run=args.dry_run)
    run_id = tracker.start()
    
    try:
        if args.phase in ['a', 'all']:
            phase_item = None
            try:
                phase_item = tracker.record_phase_start('a')
            except Exception as obs_error:
                logger.warning(f"Observability phase start failed: {obs_error}")
            try:
                result_a = run_phase_a(now, dry_run=args.dry_run)
                results.append(result_a)
                print(format_output(result_a, args.log_json))
                if phase_item:
                    try:
                        tracker.record_phase_end(phase_item, result_a.get('status', 'success'), result_a.get('counts'))
                    except Exception as obs_error:
                        logger.warning(f"Observability phase end failed: {obs_error}")
                if result_a.get('status') not in ['success', 'skipped']:
                    overall_status = 'failed'
                all_counts['phase_a'] = result_a.get('counts')
            except Exception as e:
                if phase_item:
                    try:
                        tracker.record_phase_end(phase_item, 'failed', error=str(e))
                    except Exception as obs_error:
                        logger.warning(f"Observability phase end failed: {obs_error}")
                raise
        
        if args.phase in ['b', 'all']:
            phase_item = None
            try:
                phase_item = tracker.record_phase_start('b')
            except Exception as obs_error:
                logger.warning(f"Observability phase start failed: {obs_error}")
            try:
                result_b = run_phase_b(now, since_hours=args.since_hours, dry_run=args.dry_run)
                results.append(result_b)
                print(format_output(result_b, args.log_json))
                if phase_item:
                    try:
                        tracker.record_phase_end(phase_item, result_b.get('status', 'success'), result_b.get('counts'))
                    except Exception as obs_error:
                        logger.warning(f"Observability phase end failed: {obs_error}")
                if result_b.get('status') not in ['success', 'skipped']:
                    overall_status = 'failed'
                all_counts['phase_b'] = result_b.get('counts')
            except Exception as e:
                if phase_item:
                    try:
                        tracker.record_phase_end(phase_item, 'failed', error=str(e))
                    except Exception as obs_error:
                        logger.warning(f"Observability phase end failed: {obs_error}")
                raise
        
        if args.phase in ['d', 'all']:
            phase_item = None
            try:
                phase_item = tracker.record_phase_start('d')
            except Exception as obs_error:
                logger.warning(f"Observability phase start failed: {obs_error}")
            try:
                result_d = run_phase_d(now, dry_run=args.dry_run)
                results.append(result_d)
                print(format_output(result_d, args.log_json))
                if phase_item:
                    try:
                        tracker.record_phase_end(phase_item, result_d.get('status', 'success'), result_d.get('counts'))
                    except Exception as obs_error:
                        logger.warning(f"Observability phase end failed: {obs_error}")
                if result_d.get('status') not in ['success', 'skipped']:
                    overall_status = 'failed'
                all_counts['phase_d'] = result_d.get('counts')
            except Exception as e:
                if phase_item:
                    try:
                        tracker.record_phase_end(phase_item, 'failed', error=str(e))
                    except Exception as obs_error:
                        logger.warning(f"Observability phase end failed: {obs_error}")
                raise
        
        if args.phase in ['c', 'all']:
            phase_item = None
            try:
                phase_item = tracker.record_phase_start('c')
            except Exception as obs_error:
                logger.warning(f"Observability phase start failed: {obs_error}")
            try:
                result_c = run_phase_c(now, batch_size=args.batch_size, dry_run=args.dry_run)
                results.append(result_c)
                print(format_output(result_c, args.log_json))
                if phase_item:
                    try:
                        tracker.record_phase_end(phase_item, result_c.get('status', 'success'), result_c.get('counts'))
                    except Exception as obs_error:
                        logger.warning(f"Observability phase end failed: {obs_error}")
                if result_c.get('status') not in ['success', 'skipped']:
                    overall_status = 'failed'
                all_counts['phase_c'] = result_c.get('counts')
            except Exception as e:
                if phase_item:
                    try:
                        tracker.record_phase_end(phase_item, 'failed', error=str(e))
                    except Exception as obs_error:
                        logger.warning(f"Observability phase end failed: {obs_error}")
                raise
        
        try:
            tracker.finish(overall_status, all_counts)
        except Exception as obs_error:
            logger.warning(f"Observability finish failed (continuing anyway): {obs_error}")
    
    except Exception as e:
        logger.error(f"Phase execution failed: {e}")
        error_msg = str(e)
        try:
            tracker.finish('failed', all_counts, error=error_msg)
        except Exception as obs_error:
            logger.warning(f"Observability finish failed (continuing anyway): {obs_error}")
        error_result = {
            'status': 'failed',
            'error': str(e),
            'run_id': run_id,
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
