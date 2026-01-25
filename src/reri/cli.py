"""
EERI v1 CLI Commands

Usage:
    python -m src.reri.cli compute --date YYYY-MM-DD [--force]
    python -m src.reri.cli compute-yesterday [--force]
"""
import argparse
import sys
import os
import logging
from datetime import datetime, date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.reri import ENABLE_EERI
from src.reri.service import compute_eeri_for_date
from src.db.migrations import run_migrations

logging.basicConfig(
    level=os.environ.get('LOG_LEVEL', 'INFO'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def cmd_compute(args):
    """Compute EERI for a specific date."""
    if not ENABLE_EERI:
        print("ERROR: EERI module is disabled. Set ENABLE_EERI=true to enable.")
        sys.exit(1)
    
    try:
        target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    except ValueError:
        print(f"ERROR: Invalid date format '{args.date}'. Use YYYY-MM-DD.")
        sys.exit(1)
    
    if target_date >= date.today():
        print("ERROR: Cannot compute index for today or future dates.")
        sys.exit(1)
    
    print(f"Computing EERI for {target_date} (force={args.force})...")
    
    run_migrations()
    
    result = compute_eeri_for_date(target_date, force=args.force)
    
    if result:
        print(f"\nEERI Index Computed:")
        print(f"  Date:   {result.index_date}")
        print(f"  Value:  {result.value}")
        print(f"  Band:   {result.band.value}")
        print(f"\nComponents:")
        print(f"  RERI_EU:            {result.components.reri_eu_value}")
        print(f"  Theme Pressure:     {result.components.theme_pressure_norm:.4f}")
        print(f"  Asset Transmission: {result.components.asset_transmission_norm:.4f}")
    else:
        print(f"EERI for {target_date} already exists (skipped) or failed. Use --force to overwrite.")


def cmd_compute_yesterday(args):
    """Compute EERI for yesterday (for scheduled runs)."""
    if not ENABLE_EERI:
        print("ERROR: EERI module is disabled. Set ENABLE_EERI=true to enable.")
        sys.exit(1)
    
    target_date = date.today() - timedelta(days=1)
    
    print(f"Computing EERI for yesterday ({target_date}) (force={args.force})...")
    
    run_migrations()
    
    result = compute_eeri_for_date(target_date, force=args.force)
    
    if result:
        print(f"\nEERI Index Computed:")
        print(f"  Date:   {result.index_date}")
        print(f"  Value:  {result.value}")
        print(f"  Band:   {result.band.value}")
    else:
        print(f"EERI for {target_date} already exists (skipped) or failed. Use --force to overwrite.")


def main():
    parser = argparse.ArgumentParser(
        description='EERI v1 CLI - Europe Energy Risk Index',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    compute_parser = subparsers.add_parser('compute', help='Compute EERI for a specific date')
    compute_parser.add_argument('--date', required=True, help='Date to compute (YYYY-MM-DD)')
    compute_parser.add_argument('--force', action='store_true', help='Overwrite existing value')
    
    yesterday_parser = subparsers.add_parser('compute-yesterday', help='Compute EERI for yesterday')
    yesterday_parser.add_argument('--force', action='store_true', help='Overwrite existing value')
    
    args = parser.parse_args()
    
    if args.command == 'compute':
        cmd_compute(args)
    elif args.command == 'compute-yesterday':
        cmd_compute_yesterday(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()
