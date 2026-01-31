"""
GERI History Service Layer

Data access layer for GERI history pages using intel_indices_daily table.
This is the single source of truth for all GERI snapshots.
"""

import json
from datetime import date, timedelta
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from src.db.db import get_cursor
from src.geri.types import INDEX_ID


@dataclass
class GERISnapshot:
    """View model for GERI snapshot data."""
    id: int
    index_id: str
    date: str
    value: int
    band: str
    trend_1d: Optional[float]
    trend_7d: Optional[float]
    components: Dict[str, Any]
    model_version: str
    computed_at: str
    
    @property
    def top_drivers(self) -> List[str]:
        """Extract top driver headlines from components."""
        drivers = self.components.get('top_drivers', [])
        seen = set()
        result = []
        for d in drivers:
            headline = d.get('headline', '')
            if headline and headline not in seen:
                seen.add(headline)
                result.append(headline)
        return result
    
    @property
    def top_drivers_detailed(self) -> List[Dict[str, str]]:
        """Extract top drivers with region and category from components."""
        drivers = self.components.get('top_drivers', [])
        seen = set()
        result = []
        for d in drivers:
            headline = d.get('headline', '')
            if headline and headline not in seen:
                seen.add(headline)
                result.append({
                    'headline': headline,
                    'region': d.get('region', ''),
                    'category': d.get('category', '')
                })
        return result
    
    @property
    def top_regions(self) -> List[str]:
        """Extract top region names from components."""
        regions = self.components.get('top_regions', [])
        return [r.get('region', '') for r in regions[:5] if r.get('region')]
    
    @property
    def interpretation(self) -> str:
        """Get AI-generated interpretation from components."""
        return self.components.get('interpretation', '')
    
    @property
    def computed_at_formatted(self) -> str:
        """Get computed_at date in YYYY-MM-DD format."""
        if self.computed_at:
            return self.computed_at[:10]
        return self.date


def _row_to_snapshot(row: Dict[str, Any]) -> GERISnapshot:
    """Convert database row to GERISnapshot."""
    components = row.get('components', {})
    if isinstance(components, str):
        components = json.loads(components)
    
    date_val = row.get('date')
    if hasattr(date_val, 'isoformat'):
        date_val = date_val.isoformat()
    
    computed_at = row.get('computed_at')
    if hasattr(computed_at, 'isoformat'):
        computed_at = computed_at.isoformat()
    
    return GERISnapshot(
        id=row.get('id'),
        index_id=row.get('index_id'),
        date=date_val,
        value=row.get('value', 0),
        band=row.get('band', 'UNKNOWN'),
        trend_1d=row.get('trend_1d'),
        trend_7d=row.get('trend_7d'),
        components=components,
        model_version=row.get('model_version', ''),
        computed_at=computed_at
    )


def get_snapshot_by_date(snapshot_date: str) -> Optional[GERISnapshot]:
    """
    Get a specific GERI snapshot by date.
    
    Args:
        snapshot_date: Date in YYYY-MM-DD format
    
    Returns:
        GERISnapshot or None if not found
    """
    sql = """
    SELECT id, index_id, date, value, band, trend_1d, trend_7d,
           components, model_version, computed_at
    FROM intel_indices_daily
    WHERE index_id = %s AND date = %s
    LIMIT 1
    """
    
    with get_cursor() as cursor:
        cursor.execute(sql, (INDEX_ID, snapshot_date))
        row = cursor.fetchone()
        if row:
            return _row_to_snapshot(dict(row))
    
    return None


def list_snapshots(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    limit: int = 90,
    offset: int = 0
) -> List[GERISnapshot]:
    """
    List GERI snapshots with optional date range filtering.
    
    Args:
        from_date: Start date (inclusive) in YYYY-MM-DD format
        to_date: End date (inclusive) in YYYY-MM-DD format
        limit: Maximum number of results
        offset: Number of results to skip
    
    Returns:
        List of GERISnapshot ordered by date descending
    """
    conditions = ["index_id = %s"]
    params = [INDEX_ID]
    
    if from_date:
        conditions.append("date >= %s")
        params.append(from_date)
    
    if to_date:
        conditions.append("date <= %s")
        params.append(to_date)
    
    where_clause = " AND ".join(conditions)
    
    sql = f"""
    SELECT id, index_id, date, value, band, trend_1d, trend_7d,
           components, model_version, computed_at
    FROM intel_indices_daily
    WHERE {where_clause}
    ORDER BY date DESC
    LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])
    
    snapshots = []
    with get_cursor() as cursor:
        cursor.execute(sql, tuple(params))
        rows = cursor.fetchall()
        for row in rows:
            snapshots.append(_row_to_snapshot(dict(row)))
    
    return snapshots


def list_monthly(year: int, month: int) -> List[GERISnapshot]:
    """
    List all GERI snapshots for a specific month.
    
    Args:
        year: Year (e.g., 2026)
        month: Month (1-12)
    
    Returns:
        List of GERISnapshot ordered by date ascending
    """
    sql = """
    SELECT id, index_id, date, value, band, trend_1d, trend_7d,
           components, model_version, computed_at
    FROM intel_indices_daily
    WHERE index_id = %s
      AND EXTRACT(YEAR FROM date) = %s
      AND EXTRACT(MONTH FROM date) = %s
    ORDER BY date ASC
    """
    
    snapshots = []
    with get_cursor() as cursor:
        cursor.execute(sql, (INDEX_ID, year, month))
        rows = cursor.fetchall()
        for row in rows:
            snapshots.append(_row_to_snapshot(dict(row)))
    
    return snapshots


def get_latest_snapshot() -> Optional[GERISnapshot]:
    """
    Get the most recent GERI snapshot by computed_at.
    
    Returns:
        The latest GERISnapshot or None
    """
    sql = """
    SELECT id, index_id, date, value, band, trend_1d, trend_7d,
           components, model_version, computed_at
    FROM intel_indices_daily
    WHERE index_id = %s
    ORDER BY computed_at DESC
    LIMIT 1
    """
    
    with get_cursor() as cursor:
        cursor.execute(sql, (INDEX_ID,))
        row = cursor.fetchone()
        if row:
            return _row_to_snapshot(dict(row))
    
    return None


def get_latest_published_snapshot() -> Optional[GERISnapshot]:
    """
    Get the latest published GERI snapshot (24h delayed for public).
    
    Returns:
        The latest snapshot where date <= yesterday
    """
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    
    sql = """
    SELECT id, index_id, date, value, band, trend_1d, trend_7d,
           components, model_version, computed_at
    FROM intel_indices_daily
    WHERE index_id = %s AND date <= %s
    ORDER BY date DESC
    LIMIT 1
    """
    
    with get_cursor() as cursor:
        cursor.execute(sql, (INDEX_ID, yesterday))
        row = cursor.fetchone()
        if row:
            return _row_to_snapshot(dict(row))
    
    return None


def get_available_months(public_only: bool = False) -> List[Dict[str, Any]]:
    """
    Get list of months that have GERI snapshots.
    
    Args:
        public_only: If True, only include snapshots with 24h delay (date <= yesterday)
    
    Returns:
        List of dicts with year, month, snapshot_count, min_date, max_date
    """
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    date_filter = f"AND date <= '{yesterday}'" if public_only else ""
    
    sql = f"""
    SELECT 
        EXTRACT(YEAR FROM date)::int as year,
        EXTRACT(MONTH FROM date)::int as month,
        COUNT(*) as snapshot_count,
        MIN(date) as min_date,
        MAX(date) as max_date
    FROM intel_indices_daily
    WHERE index_id = %s {date_filter}
    GROUP BY EXTRACT(YEAR FROM date), EXTRACT(MONTH FROM date)
    ORDER BY year DESC, month DESC
    """
    
    results = []
    with get_cursor() as cursor:
        cursor.execute(sql, (INDEX_ID,))
        rows = cursor.fetchall()
        for row in rows:
            row_dict = dict(row)
            if row_dict.get('max_date') and hasattr(row_dict['max_date'], 'isoformat'):
                row_dict['max_date'] = row_dict['max_date'].isoformat()
            if row_dict.get('min_date') and hasattr(row_dict['min_date'], 'isoformat'):
                row_dict['min_date'] = row_dict['min_date'].isoformat()
            results.append(row_dict)
    
    return results


def get_monthly_stats(year: int, month: int) -> Optional[Dict[str, Any]]:
    """
    Get aggregated statistics for a specific month.
    
    Returns:
        Dict with avg, min, max, first, last values or None if no data
    """
    sql = """
    SELECT 
        AVG(value)::numeric(6,2) as avg_value,
        MIN(value) as min_value,
        MAX(value) as max_value,
        COUNT(*) as snapshot_count
    FROM intel_indices_daily
    WHERE index_id = %s
      AND EXTRACT(YEAR FROM date) = %s
      AND EXTRACT(MONTH FROM date) = %s
    """
    
    with get_cursor() as cursor:
        cursor.execute(sql, (INDEX_ID, year, month))
        row = cursor.fetchone()
        if row and row['snapshot_count'] > 0:
            return dict(row)
    
    return None


def get_adjacent_dates(current_date: str) -> Dict[str, Optional[str]]:
    """
    Get the previous and next snapshot dates for navigation.
    
    Args:
        current_date: Current date in YYYY-MM-DD format
    
    Returns:
        Dict with 'prev' and 'next' date strings or None
    """
    prev_sql = """
    SELECT date FROM intel_indices_daily
    WHERE index_id = %s AND date < %s
    ORDER BY date DESC LIMIT 1
    """
    
    next_sql = """
    SELECT date FROM intel_indices_daily
    WHERE index_id = %s AND date > %s
    ORDER BY date ASC LIMIT 1
    """
    
    result = {'prev': None, 'next': None}
    
    with get_cursor() as cursor:
        cursor.execute(prev_sql, (INDEX_ID, current_date))
        row = cursor.fetchone()
        if row:
            d = row['date']
            result['prev'] = d.isoformat() if hasattr(d, 'isoformat') else str(d)
        
        cursor.execute(next_sql, (INDEX_ID, current_date))
        row = cursor.fetchone()
        if row:
            d = row['date']
            result['next'] = d.isoformat() if hasattr(d, 'isoformat') else str(d)
    
    return result


def get_adjacent_months(year: int, month: int) -> Dict[str, Optional[Dict[str, int]]]:
    """
    Get the previous and next months that have snapshots.
    
    Returns:
        Dict with 'prev' and 'next' containing year/month or None
    """
    prev_sql = """
    SELECT DISTINCT 
        EXTRACT(YEAR FROM date)::int as year,
        EXTRACT(MONTH FROM date)::int as month
    FROM intel_indices_daily
    WHERE index_id = %s
      AND (EXTRACT(YEAR FROM date) < %s 
           OR (EXTRACT(YEAR FROM date) = %s AND EXTRACT(MONTH FROM date) < %s))
    ORDER BY year DESC, month DESC
    LIMIT 1
    """
    
    next_sql = """
    SELECT DISTINCT 
        EXTRACT(YEAR FROM date)::int as year,
        EXTRACT(MONTH FROM date)::int as month
    FROM intel_indices_daily
    WHERE index_id = %s
      AND (EXTRACT(YEAR FROM date) > %s 
           OR (EXTRACT(YEAR FROM date) = %s AND EXTRACT(MONTH FROM date) > %s))
    ORDER BY year ASC, month ASC
    LIMIT 1
    """
    
    result = {'prev': None, 'next': None}
    
    with get_cursor() as cursor:
        cursor.execute(prev_sql, (INDEX_ID, year, year, month))
        row = cursor.fetchone()
        if row:
            result['prev'] = {'year': row['year'], 'month': row['month']}
        
        cursor.execute(next_sql, (INDEX_ID, year, year, month))
        row = cursor.fetchone()
        if row:
            result['next'] = {'year': row['year'], 'month': row['month']}
    
    return result


def get_all_snapshot_dates() -> List[str]:
    """
    Get all snapshot dates for sitemap generation.
    
    Returns:
        List of date strings in YYYY-MM-DD format
    """
    sql = """
    SELECT date FROM intel_indices_daily
    WHERE index_id = %s
    ORDER BY date DESC
    """
    
    dates = []
    with get_cursor() as cursor:
        cursor.execute(sql, (INDEX_ID,))
        rows = cursor.fetchall()
        for row in rows:
            d = row['date']
            dates.append(d.isoformat() if hasattr(d, 'isoformat') else str(d))
    
    return dates
