"""
GERI v1 CLI Commands

Usage:
    python -m src.geri.cli compute --date YYYY-MM-DD [--force]
    python -m src.geri.cli backfill --from YYYY-MM-DD --to YYYY-MM-DD [--force]
    python -m src.geri.cli backfill-auto [--force]
"""
import argparse
import sys
import os
import logging
from datetime import datetime, date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.geri import ENABLE_GERI
from src.geri.service import compute_geri_for_date, backfill, auto_backfill
from src.db.migrations import run_migrations

logging.basicConfig(
    level=os.environ.get('LOG_LEVEL', 'INFO'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def cmd_compute(args):
    """Compute GERI for a specific date."""
    if not ENABLE_GERI:
        print("ERROR: GERI module is disabled. Set ENABLE_GERI=true to enable.")
        sys.exit(1)
    
    try:
        target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    except ValueError:
        print(f"ERROR: Invalid date format '{args.date}'. Use YYYY-MM-DD.")
        sys.exit(1)
    
    if target_date >= date.today():
        print("ERROR: Cannot compute index for today or future dates.")
        sys.exit(1)
    
    print(f"Computing GERI for {target_date} (force={args.force})...")
    
    run_migrations()
    
    result = compute_geri_for_date(target_date, force=args.force)
    
    if result:
        print(f"\nGERI Index Computed:")
        print(f"  Date:  {result.index_date}")
        print(f"  Value: {result.value}")
        print(f"  Band:  {result.band.value}")
        print(f"  Trend (1d): {result.trend_1d}")
        print(f"  Trend (7d): {result.trend_7d}")
        print(f"\nComponents:")
        print(f"  High Impact Events: {result.components.high_impact_events}")
        print(f"  Regional Spikes: {result.components.regional_spikes}")
        print(f"  Asset Alerts: {result.components.asset_spikes}")
        print(f"  Total Alerts: {result.components.total_alerts}")
    else:
        print(f"GERI for {target_date} already exists (skipped). Use --force to overwrite.")


def cmd_backfill(args):
    """Backfill GERI for a date range."""
    if not ENABLE_GERI:
        print("ERROR: GERI module is disabled. Set ENABLE_GERI=true to enable.")
        sys.exit(1)
    
    try:
        from_date = datetime.strptime(args.from_date, "%Y-%m-%d").date()
        to_date = datetime.strptime(args.to_date, "%Y-%m-%d").date()
    except ValueError:
        print("ERROR: Invalid date format. Use YYYY-MM-DD.")
        sys.exit(1)
    
    if from_date > to_date:
        print("ERROR: --from date must be before or equal to --to date.")
        sys.exit(1)
    
    print(f"Backfilling GERI from {from_date} to {to_date} (force={args.force})...")
    
    run_migrations()
    
    summary = backfill(from_date, to_date, force=args.force)
    
    print(f"\nBackfill Complete:")
    print(f"  Date Range: {summary['from_date']} to {summary['to_date']}")
    print(f"  Total Days: {summary['total_days']}")
    print(f"  Computed:   {summary['computed']}")
    print(f"  Skipped:    {summary['skipped']}")
    print(f"  Failed:     {summary['failed']}")


def cmd_backfill_auto(args):
    """Auto-backfill all historical alerts."""
    if not ENABLE_GERI:
        print("ERROR: GERI module is disabled. Set ENABLE_GERI=true to enable.")
        sys.exit(1)
    
    print(f"Auto-backfilling GERI (force={args.force})...")
    
    run_migrations()
    
    summary = auto_backfill(force=args.force)
    
    if 'error' in summary:
        print(f"ERROR: {summary['error']}")
        sys.exit(1)
    
    print(f"\nAuto-Backfill Complete:")
    print(f"  Date Range: {summary.get('from_date', 'N/A')} to {summary.get('to_date', 'N/A')}")
    print(f"  Total Days: {summary.get('total_days', 0)}")
    print(f"  Computed:   {summary['computed']}")
    print(f"  Skipped:    {summary['skipped']}")
    print(f"  Failed:     {summary.get('failed', 0)}")


def main():
    parser = argparse.ArgumentParser(
        description='GERI v1 CLI - Global Energy Risk Index',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    compute_parser = subparsers.add_parser('compute', help='Compute GERI for a specific date')
    compute_parser.add_argument('--date', required=True, help='Date to compute (YYYY-MM-DD)')
    compute_parser.add_argument('--force', action='store_true', help='Overwrite existing value')
    
    backfill_parser = subparsers.add_parser('backfill', help='Backfill GERI for a date range')
    backfill_parser.add_argument('--from', dest='from_date', required=True, help='Start date (YYYY-MM-DD)')
    backfill_parser.add_argument('--to', dest='to_date', required=True, help='End date (YYYY-MM-DD)')
    backfill_parser.add_argument('--force', action='store_true', help='Overwrite existing values')
    
    auto_parser = subparsers.add_parser('backfill-auto', help='Auto-backfill all historical alerts')
    auto_parser.add_argument('--force', action='store_true', help='Overwrite existing values')
    
    args = parser.parse_args()
    
    if args.command == 'compute':
        cmd_compute(args)
    elif args.command == 'backfill':
        cmd_backfill(args)
    elif args.command == 'backfill-auto':
        cmd_backfill_auto(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()
