"""
SEO Generator CLI Runner

Usage:
    python -m src.seo.runner --yesterday
    python -m src.seo.runner --date 2026-01-15
    python -m src.seo.runner --rebuild-sitemaps
    python -m src.seo.runner --dry-run --date 2026-01-15
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.db.migrations import run_migrations
from src.seo.seo_generator import (
    get_yesterday_date,
    generate_daily_page_model,
    save_daily_page,
    get_daily_page,
    generate_sitemap_entries,
    get_available_months,
    get_recent_daily_pages,
    generate_and_save_regional_daily_page,
    REGION_DISPLAY_NAMES,
)

logging.basicConfig(
    level=os.environ.get('LOG_LEVEL', 'INFO'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def run_seo_migration():
    """Run the SEO tables migration."""
    from src.db.db import get_cursor
    
    logger.info("Running SEO tables migration...")
    
    with get_cursor() as cursor:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS seo_daily_pages (
                id SERIAL PRIMARY KEY,
                page_date DATE NOT NULL UNIQUE,
                seo_title TEXT NOT NULL,
                seo_description TEXT NOT NULL,
                page_json JSONB NOT NULL,
                alert_count INT NOT NULL DEFAULT 0,
                generated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
        """)
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_seo_daily_pages_date ON seo_daily_pages(page_date DESC);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_seo_daily_pages_alert_count ON seo_daily_pages(alert_count);")
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS seo_page_views (
                id SERIAL PRIMARY KEY,
                page_type TEXT NOT NULL,
                page_path TEXT NOT NULL,
                view_count INT NOT NULL DEFAULT 1,
                last_viewed_at TIMESTAMP NOT NULL DEFAULT NOW(),
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                UNIQUE(page_type, page_path)
            );
        """)
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_seo_page_views_path ON seo_page_views(page_path);")
    
    logger.info("SEO tables migration complete.")


def generate_daily_page(target_date: date, dry_run: bool = False) -> dict:
    """Generate a daily SEO page for the given date."""
    logger.info(f"Generating daily page for {target_date.isoformat()}")
    
    model = generate_daily_page_model(target_date)
    
    logger.info(f"Page model: {model['stats']['total_alerts']} alerts, title: {model['seo_title'][:60]}...")
    
    if dry_run:
        logger.info("[DRY RUN] Would save page to database")
        return {
            'status': 'dry_run',
            'date': target_date.isoformat(),
            'model': model
        }
    
    page_id = save_daily_page(target_date, model)
    logger.info(f"Saved daily page with id={page_id}")
    
    return {
        'status': 'success',
        'date': target_date.isoformat(),
        'page_id': page_id,
        'alert_count': model['stats']['total_alerts']
    }


def generate_regional_pages(target_date: date, dry_run: bool = False) -> list:
    """Generate regional daily pages for all regions for the given date."""
    results = []
    regions = list(REGION_DISPLAY_NAMES.keys())
    
    logger.info(f"Generating regional pages for {target_date.isoformat()} ({len(regions)} regions)")
    
    for region_slug in regions:
        try:
            if dry_run:
                logger.info(f"[DRY RUN] Would generate {region_slug} page for {target_date}")
                results.append({
                    'status': 'dry_run',
                    'region': region_slug,
                    'date': target_date.isoformat()
                })
            else:
                model = generate_and_save_regional_daily_page(target_date, region_slug)
                alert_count = model['stats']['total_alerts']
                logger.info(f"Generated {region_slug} page: {alert_count} alerts")
                results.append({
                    'status': 'success',
                    'region': region_slug,
                    'date': target_date.isoformat(),
                    'alert_count': alert_count
                })
        except Exception as e:
            logger.error(f"Error generating {region_slug} page: {e}")
            results.append({
                'status': 'error',
                'region': region_slug,
                'date': target_date.isoformat(),
                'error': str(e)
            })
    
    return results


def rebuild_sitemaps(dry_run: bool = False) -> dict:
    """Rebuild sitemap.xml entries."""
    logger.info("Rebuilding sitemaps...")
    
    entries = generate_sitemap_entries()
    
    logger.info(f"Generated {len(entries)} sitemap entries")
    
    if dry_run:
        logger.info("[DRY RUN] Sitemap entries:")
        for e in entries[:10]:
            logger.info(f"  {e['loc']} (priority={e['priority']})")
        if len(entries) > 10:
            logger.info(f"  ... and {len(entries) - 10} more")
        return {
            'status': 'dry_run',
            'entry_count': len(entries)
        }
    
    return {
        'status': 'success',
        'entry_count': len(entries),
        'entries': entries
    }


def main():
    parser = argparse.ArgumentParser(description='EnergyRiskIQ SEO Generator')
    parser.add_argument('--yesterday', action='store_true', help='Generate page for yesterday (default)')
    parser.add_argument('--date', type=str, help='Generate page for specific date (YYYY-MM-DD)')
    parser.add_argument('--rebuild-sitemaps', action='store_true', help='Rebuild sitemap entries')
    parser.add_argument('--dry-run', action='store_true', help='Preview without saving')
    parser.add_argument('--backfill', type=int, help='Backfill N days of pages')
    parser.add_argument('--skip-regional', action='store_true', help='Skip regional page generation')
    
    args = parser.parse_args()
    
    run_migrations()
    run_seo_migration()
    
    results = {
        'generated_at': datetime.utcnow().isoformat(),
        'dry_run': args.dry_run,
        'pages': [],
        'regional_pages': [],
        'sitemap': None
    }
    
    if args.backfill:
        logger.info(f"Backfilling {args.backfill} days...")
        yesterday = get_yesterday_date()
        for i in range(args.backfill):
            target = yesterday - timedelta(days=i)
            result = generate_daily_page(target, dry_run=args.dry_run)
            results['pages'].append(result)
            if not args.skip_regional:
                regional_results = generate_regional_pages(target, dry_run=args.dry_run)
                results['regional_pages'].extend(regional_results)
    elif args.date:
        try:
            target = datetime.strptime(args.date, '%Y-%m-%d').date()
        except ValueError:
            logger.error(f"Invalid date format: {args.date}. Use YYYY-MM-DD")
            sys.exit(1)
        result = generate_daily_page(target, dry_run=args.dry_run)
        results['pages'].append(result)
        if not args.skip_regional:
            regional_results = generate_regional_pages(target, dry_run=args.dry_run)
            results['regional_pages'].extend(regional_results)
    else:
        target = get_yesterday_date()
        result = generate_daily_page(target, dry_run=args.dry_run)
        results['pages'].append(result)
        if not args.skip_regional:
            regional_results = generate_regional_pages(target, dry_run=args.dry_run)
            results['regional_pages'].extend(regional_results)
    
    if args.rebuild_sitemaps or not args.date:
        results['sitemap'] = rebuild_sitemaps(dry_run=args.dry_run)
    
    print("\n" + "=" * 60)
    print("EnergyRiskIQ SEO Generator - Results")
    print("=" * 60)
    print(json.dumps(results, indent=2, default=str))
    print("=" * 60)
    
    return results


if __name__ == '__main__':
    main()
