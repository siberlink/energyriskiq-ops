"""
GERI v1 Service Layer

Orchestrates compute and backfill operations.
"""
import logging
from datetime import date, timedelta, datetime, timezone
from typing import Optional, List, Dict, Any

from src.geri import ENABLE_GERI
from src.geri.types import GERIResult, INDEX_ID
from src.geri.repo import (
    get_alerts_for_date,
    get_index_for_date,
    get_previous_values,
    get_historical_baseline,
    save_index,
    get_date_range_with_alerts,
)
from src.geri.compute import compute_components
from src.geri.normalize import (
    normalize_components,
    calculate_geri_value,
    calculate_trends,
    build_result,
)

logger = logging.getLogger(__name__)


def compute_geri_for_date(target_date: date, force: bool = False, reason=None,
                         apply_revision=False) -> Optional[GERIResult]:
    from src.geri.job_health import start_run, finish_run
    if force and not (reason and reason.strip()):
        raise ValueError("Forced computation requires a reason; default is a dry run.")
    if apply_revision and not force:
        raise ValueError("apply_revision requires force=True.")
    if not ENABLE_GERI:
        return None
    run_id = start_run(target_date)
    try:
        result = _compute_geri_for_date(target_date, force, reason, apply_revision)
        finish_run(run_id, getattr(result, "publication_status", "skipped"))
        return result
    except Exception as error:
        finish_run(run_id, "error", str(error))
        raise


def _compute_geri_for_date(target_date, force=False, reason=None, apply_revision=False):
    """
    Compute GERI index for a specific date.
    
    Args:
        target_date: The UTC date to compute the index for
        force: If True, overwrite existing value; if False, skip if exists
    
    Returns:
        GERIResult if computed, None if skipped or error
    """
    if not ENABLE_GERI:
        logger.warning("GERI module is disabled (ENABLE_GERI=false)")
        return None
    
    from src.geri.health import record_health, HEALTH_POLICY
    health = record_health(target_date)
    if HEALTH_POLICY[health["data_quality"]] == "skip":
        logger.error("GERI %s UNAVAILABLE: no index publication attempted", target_date)
        return None
    existing = get_index_for_date(target_date)
    if existing and not force:
        logger.info(f"GERI for {target_date} already exists; immutable publication skipped")
        return None
    
    logger.info(f"Computing GERI for date: {target_date}")
    
    alerts = get_alerts_for_date(target_date)
    logger.info(f"Found {len(alerts)} alerts for {target_date}")
    
    components = compute_components(alerts)
    
    baseline = get_historical_baseline(target_date)
    logger.info(f"Historical baseline: {baseline.days_count} days of history")
    
    components = normalize_components(components, baseline)
    
    value = calculate_geri_value(components)
    
    previous_values = get_previous_values(target_date, days=7)
    trend_1d, trend_7d = calculate_trends(value, previous_values)
    
    from src.geri.interpretation import generate_interpretation
    from src.geri.normalize import get_band
    band = get_band(value)
    top_regions = [r.get('region', '') for r in components.top_regions[:3] if r.get('region')]
    components.interpretation = (existing.get("components", {}).get("interpretation", "")
                                if force and existing else generate_interpretation(
        value=value,
        band=band.value,
        top_drivers=components.top_drivers,
        top_regions=top_regions,
        index_date=target_date.isoformat()
    ))
    
    result = build_result(target_date, value, components, trend_1d, trend_7d)
    
    result.input_snapshot = {
        "alert_ids": [a.id for a in alerts],
        "baseline_start": target_date - timedelta(days=90),
        "baseline_end": target_date - timedelta(days=1),
        "baseline_rows": baseline.days_count,
        "baseline_dates": getattr(baseline, "source_dates", []),
        "fallback_used": components.insufficient_history,
    }
    saved = save_index(result, force=force, reason=reason, apply_revision=apply_revision)
    result.publication_status = ("revision_applied" if apply_revision else "revision_dry_run") if force else (
        "stored" if saved else "skipped")
    
    if saved:
        logger.info(f"GERI computed: date={target_date}, value={value}, band={result.band.value}")
    
    return result


def compute_yesterday() -> Optional[GERIResult]:
    """Compute GERI for yesterday (UTC). Used by scheduler."""
    yesterday = datetime.now(timezone.utc).date() - timedelta(days=1)
    return compute_geri_for_date(yesterday, force=False)


def backfill(
    from_date: date,
    to_date: date,
    force: bool = False,
    reason=None,
    apply_revision=False,
) -> Dict[str, Any]:
    """
    Backfill GERI indices for a date range.
    
    Args:
        from_date: Start date (inclusive)
        to_date: End date (inclusive)
        force: Propose revisions; applying additionally requires apply_revision.
    
    Returns:
        Summary dict with counts
    """
    if not ENABLE_GERI:
        logger.warning("GERI module is disabled (ENABLE_GERI=false)")
        return {'error': 'GERI module disabled', 'computed': 0, 'skipped': 0}
    
    if force and not (reason and reason.strip()):
        raise ValueError("Forced backfill requires a nonempty revision reason.")
    if apply_revision and not force:
        raise ValueError("Applying revisions requires force=True.")
    logger.info(f"Starting GERI backfill from {from_date} to {to_date} (force={force})")
    
    computed = 0
    skipped = 0
    failed = 0
    results = []
    
    current_date = from_date
    while current_date <= to_date:
        try:
            result = compute_geri_for_date(current_date, force=force, reason=reason,
                                          apply_revision=apply_revision)
            if result:
                computed += 1
                results.append({
                    'date': current_date.isoformat(),
                    'value': result.value,
                    'band': result.band.value,
                    'publication_status': getattr(result, "publication_status", None),
                    'revision_diff': getattr(result, "revision_diff", None),
                })
            else:
                skipped += 1
        except Exception as e:
            logger.error(f"Failed to compute GERI for {current_date}: {e}")
            failed += 1
        
        current_date += timedelta(days=1)
    
    summary = {
        'from_date': from_date.isoformat(),
        'to_date': to_date.isoformat(),
        'computed': computed,
        'skipped': skipped,
        'failed': failed,
        'total_days': (to_date - from_date).days + 1,
        'results': results,
        'revision_diffs': [r["revision_diff"] for r in results if r["revision_diff"]],
        'revisions_applied': sum(r["publication_status"] == "revision_applied" for r in results),
        'revision_proposals': sum(r["publication_status"] == "revision_dry_run" for r in results),
    }
    
    logger.info(f"Backfill complete: computed={computed}, skipped={skipped}, failed={failed}")
    
    return summary


def auto_backfill(force: bool = False, reason=None, apply_revision=False) -> Dict[str, Any]:
    """
    Automatically backfill all historical alerts.
    Determines date range from alert_events.
    """
    min_date, max_date = get_date_range_with_alerts()
    
    if not min_date or not max_date:
        return {
            'error': 'No alerts found in alert_events',
            'computed': 0,
            'skipped': 0,
        }
    
    yesterday = datetime.now(timezone.utc).date() - timedelta(days=1)
    to_date = min(max_date, yesterday)
    
    logger.info(f"Auto-backfill: alert range is {min_date} to {max_date}, processing up to {to_date}")
    
    return backfill(min_date, to_date, force=force, reason=reason, apply_revision=apply_revision)
