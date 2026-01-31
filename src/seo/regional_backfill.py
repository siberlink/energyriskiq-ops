"""
Regional Daily Pages Backfill Script

One-time script to generate historical regional daily alert pages.
This will create pre-generated pages for all dates with alerts for a specific region.

Usage:
    python -m src.seo.regional_backfill --region middle-east --days 30
    python -m src.seo.regional_backfill --region middle-east --start 2026-01-01 --end 2026-01-30
"""

import argparse
import logging
from datetime import datetime, date, timedelta
from typing import List

from src.seo.seo_generator import (
    generate_and_save_regional_daily_page,
    get_yesterday_date,
    REGION_DISPLAY_NAMES,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_date_range(start_date: date, end_date: date) -> List[date]:
    """Generate list of dates between start and end (inclusive)."""
    dates = []
    current = start_date
    while current <= end_date:
        dates.append(current)
        current += timedelta(days=1)
    return dates


def backfill_region(region_slug: str, start_date: date, end_date: date) -> dict:
    """
    Generate regional daily pages for a date range.
    
    Returns dict with counts of pages generated and alerts found.
    """
    region_name = REGION_DISPLAY_NAMES.get(region_slug, region_slug)
    logger.info(f"Starting backfill for {region_name} from {start_date} to {end_date}")
    
    dates = get_date_range(start_date, end_date)
    yesterday = get_yesterday_date()
    
    dates = [d for d in dates if d <= yesterday]
    
    stats = {
        'region': region_slug,
        'start_date': str(start_date),
        'end_date': str(end_date),
        'total_dates': len(dates),
        'pages_generated': 0,
        'total_alerts': 0,
        'errors': []
    }
    
    for target_date in dates:
        try:
            model = generate_and_save_regional_daily_page(target_date, region_slug)
            alert_count = model['stats']['total_alerts']
            stats['pages_generated'] += 1
            stats['total_alerts'] += alert_count
            logger.info(f"  Generated {target_date}: {alert_count} alerts")
        except Exception as e:
            error_msg = f"{target_date}: {str(e)}"
            stats['errors'].append(error_msg)
            logger.error(f"  Error for {target_date}: {e}")
    
    logger.info(f"Backfill complete: {stats['pages_generated']} pages, {stats['total_alerts']} total alerts")
    return stats


def main():
    parser = argparse.ArgumentParser(description='Backfill regional daily alert pages')
    parser.add_argument('--region', required=True, help='Region slug (e.g., middle-east, europe)')
    parser.add_argument('--days', type=int, help='Number of days to backfill from yesterday')
    parser.add_argument('--start', help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', help='End date (YYYY-MM-DD)')
    
    args = parser.parse_args()
    
    yesterday = get_yesterday_date()
    
    if args.days:
        end_date = yesterday
        start_date = yesterday - timedelta(days=args.days - 1)
    elif args.start and args.end:
        start_date = datetime.strptime(args.start, '%Y-%m-%d').date()
        end_date = datetime.strptime(args.end, '%Y-%m-%d').date()
    else:
        end_date = yesterday
        start_date = yesterday - timedelta(days=29)
    
    if args.region not in REGION_DISPLAY_NAMES:
        logger.warning(f"Unknown region '{args.region}'. Available: {list(REGION_DISPLAY_NAMES.keys())}")
    
    stats = backfill_region(args.region, start_date, end_date)
    
    print("\n=== Backfill Summary ===")
    print(f"Region: {stats['region']}")
    print(f"Date Range: {stats['start_date']} to {stats['end_date']}")
    print(f"Pages Generated: {stats['pages_generated']}/{stats['total_dates']}")
    print(f"Total Alerts: {stats['total_alerts']}")
    if stats['errors']:
        print(f"Errors: {len(stats['errors'])}")
        for err in stats['errors'][:5]:
            print(f"  - {err}")


if __name__ == '__main__':
    main()
