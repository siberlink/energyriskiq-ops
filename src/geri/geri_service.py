"""
GERI Service Layer - Shared functions for delayed vs real-time index access.

This module provides a unified interface for fetching GERI data,
used by both homepage card and /geri dedicated page.
"""

from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from datetime import date
import json

from .repo import get_latest_index, get_delayed_index


@dataclass
class DriverDetail:
    """Detailed driver info with region and category."""
    headline: str
    region: str
    category: str


@dataclass
class GeriViewModel:
    """View model for GERI data display."""
    value: int
    band: str
    date: str
    trend_1d: Optional[float]
    trend_7d: Optional[float]
    top_drivers: List[str]
    top_drivers_detailed: List[DriverDetail]
    top_regions: List[str]
    is_delayed: bool
    delay_hours: int = 0


def _parse_components(result: Dict[str, Any]) -> tuple:
    """Parse components from database result, handling JSON string or dict."""
    components = result.get('components', {})
    if isinstance(components, str):
        components = json.loads(components)
    
    top_drivers_raw = components.get('top_drivers', [])
    top_regions_raw = components.get('top_regions', [])
    
    seen = set()
    top_drivers = []
    top_drivers_detailed = []
    for d in top_drivers_raw:
        headline = d.get('headline', '')
        if headline and headline not in seen:
            seen.add(headline)
            top_drivers.append(headline)
            top_drivers_detailed.append(DriverDetail(
                headline=headline,
                region=d.get('region', ''),
                category=d.get('category', '')
            ))
    
    top_regions = [r.get('region', '') for r in top_regions_raw[:3] if r.get('region')]
    
    return top_drivers, top_drivers_detailed, top_regions


def _format_date(index_date) -> str:
    """Format date to ISO string."""
    if hasattr(index_date, 'isoformat'):
        return index_date.isoformat()
    return str(index_date) if index_date else ''


def get_geri_delayed() -> Optional[GeriViewModel]:
    """
    Get GERI data with 24h delay for public/unauthenticated access.
    
    Returns:
        GeriViewModel with delayed data, or None if no data available.
    """
    result = get_delayed_index(delay_days=1)
    
    if not result:
        return None
    
    top_drivers, top_drivers_detailed, top_regions = _parse_components(result)
    
    return GeriViewModel(
        value=result.get('value', 0),
        band=result.get('band', 'UNKNOWN'),
        date=_format_date(result.get('date')),
        trend_1d=result.get('trend_1d'),
        trend_7d=result.get('trend_7d'),
        top_drivers=top_drivers,
        top_drivers_detailed=top_drivers_detailed,
        top_regions=top_regions,
        is_delayed=True,
        delay_hours=24
    )


def get_geri_latest() -> Optional[GeriViewModel]:
    """
    Get the latest real-time GERI data for authenticated users.
    
    Returns:
        GeriViewModel with latest data, or None if no data available.
    """
    result = get_latest_index()
    
    if not result:
        return None
    
    top_drivers, top_drivers_detailed, top_regions = _parse_components(result)
    
    return GeriViewModel(
        value=result.get('value', 0),
        band=result.get('band', 'UNKNOWN'),
        date=_format_date(result.get('date')),
        trend_1d=result.get('trend_1d'),
        trend_7d=result.get('trend_7d'),
        top_drivers=top_drivers,
        top_drivers_detailed=top_drivers_detailed,
        top_regions=top_regions,
        is_delayed=False,
        delay_hours=0
    )


def get_geri_for_user(user_id: Optional[str] = None) -> Optional[GeriViewModel]:
    """
    Get GERI data appropriate for the user's authentication state.
    
    Args:
        user_id: User ID if authenticated, None if not.
    
    Returns:
        GeriViewModel with delayed data (if unauthenticated) or 
        real-time data (if authenticated), with fallback to delayed if real-time unavailable.
    """
    if user_id:
        realtime = get_geri_latest()
        if realtime:
            return realtime
        delayed = get_geri_delayed()
        if delayed:
            delayed.is_delayed = True
            delayed.delay_hours = 24
        return delayed
    else:
        return get_geri_delayed()
