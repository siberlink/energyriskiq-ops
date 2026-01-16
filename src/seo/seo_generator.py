"""
SEO Daily Page Generator for EnergyRiskIQ

Generates SEO-optimized daily alerts pages with 24-hour delay.
Uses only public alert data (no premium leakage).
"""

import logging
import json
from datetime import datetime, timezone, timedelta, date
from typing import Dict, List, Optional, Any
from collections import Counter

from src.db.db import get_cursor, execute_query, execute_one

logger = logging.getLogger(__name__)

CATEGORY_DISPLAY = {
    'GEOPOLITICAL': 'Geopolitical',
    'ENERGY': 'Energy',
    'SUPPLY_CHAIN': 'Supply Chain',
    'geopolitical': 'Geopolitical',
    'energy': 'Energy',
    'supply_chain': 'Supply Chain'
}

REGION_DISPLAY = {
    'Europe': 'Europe',
    'Middle East': 'Middle East',
    'Asia': 'Asia',
    'North America': 'North America',
    'South America': 'South America',
    'Africa': 'Africa',
    'Global': 'Global'
}

ALERT_TYPE_DISPLAY = {
    'HIGH_IMPACT_EVENT': 'High-Impact Event',
    'REGIONAL_RISK_SPIKE': 'Regional Risk Spike',
    'ASSET_RISK_SPIKE': 'Asset Risk Spike',
    'DAILY_DIGEST': 'Daily Digest'
}


def get_yesterday_date() -> date:
    """Get yesterday's date in UTC."""
    return (datetime.now(timezone.utc) - timedelta(days=1)).date()


def get_alerts_for_date(target_date: date) -> List[Dict]:
    """
    Fetch all alert_events for a specific date (24h window).
    Returns only public-safe fields.
    """
    start_dt = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=timezone.utc)
    end_dt = start_dt + timedelta(days=1)
    
    query = """
    SELECT 
        id,
        alert_type,
        scope_region,
        scope_assets,
        severity,
        headline,
        body,
        event_fingerprint,
        created_at
    FROM alert_events
    WHERE created_at >= %s AND created_at < %s
      AND headline IS NOT NULL
    ORDER BY severity DESC, created_at DESC
    """
    
    results = execute_query(query, (start_dt, end_dt))
    return results if results else []


def extract_source_domain(url: Optional[str]) -> Optional[str]:
    """Extract domain from URL (no link, just text)."""
    if not url:
        return None
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        domain = parsed.netloc
        if domain.startswith('www.'):
            domain = domain[4:]
        return domain
    except Exception:
        return None


def derive_category_from_alert_type(alert_type: str) -> str:
    """Derive a display category from alert_type."""
    if alert_type == 'HIGH_IMPACT_EVENT':
        return 'Geopolitical'
    elif alert_type == 'REGIONAL_RISK_SPIKE':
        return 'Energy'
    elif alert_type == 'ASSET_RISK_SPIKE':
        return 'Commodities'
    return 'Risk Event'


def sanitize_text_for_seo(text: str) -> str:
    """Remove URLs and sanitize text for SEO pages to avoid external linking."""
    if not text:
        return text
    import re
    url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
    sanitized = re.sub(url_pattern, '', text)
    sanitized = re.sub(r'\s+', ' ', sanitized).strip()
    return sanitized


def build_public_alert_card(alert: Dict) -> Dict:
    """
    Build a public-safe alert card for SEO pages.
    No premium fields exposed. URLs sanitized.
    """
    assets = alert.get('scope_assets') or []
    
    public_title = sanitize_text_for_seo(alert.get('headline', 'Risk Alert'))
    public_summary = sanitize_text_for_seo(alert.get('body', ''))
    if public_summary and len(public_summary) > 200:
        public_summary = public_summary[:197] + '...'
    
    alert_type = alert.get('alert_type', 'HIGH_IMPACT_EVENT')
    category = derive_category_from_alert_type(alert_type)
    
    return {
        'id': alert['id'],
        'public_title': public_title,
        'public_summary': public_summary,
        'severity': alert.get('severity', 3),
        'category': category,
        'region': alert.get('scope_region', 'Global'),
        'event_type': ALERT_TYPE_DISPLAY.get(alert_type, alert_type),
        'alert_type_raw': alert_type,
        'timestamp': alert['created_at'].isoformat() if alert.get('created_at') else None,
        'assets': assets[:3] if assets else [],
        'source_domain': None
    }


def compute_risk_posture(alerts: List[Dict]) -> str:
    """
    Generate a 2-4 sentence daily risk posture summary.
    Based on severity distribution and alert types.
    """
    if not alerts:
        return "No significant risk events were detected for this day. Markets and supply chains operated within normal parameters."
    
    total = len(alerts)
    critical_count = sum(1 for a in alerts if a.get('severity', 0) >= 4)
    high_count = sum(1 for a in alerts if a.get('severity', 0) == 3)
    
    regions = Counter(a.get('scope_region', 'Global') for a in alerts)
    top_regions = [r for r, _ in regions.most_common(2)]
    
    categories = Counter(derive_category_from_alert_type(a.get('alert_type', 'HIGH_IMPACT_EVENT')) for a in alerts)
    top_category = categories.most_common(1)[0][0] if categories else 'Geopolitical'
    
    if critical_count >= 3:
        posture_text = f"Risk posture for this period was ELEVATED with {critical_count} critical-severity alerts detected."
    elif critical_count >= 1 or high_count >= 3:
        posture_text = f"Risk posture was MODERATE with {total} total alerts, including {critical_count} critical events."
    else:
        posture_text = f"Risk posture remained STABLE with {total} alerts, predominantly low-to-moderate severity."
    
    region_text = f"Primary activity concentrated in {', '.join(top_regions)}." if top_regions else ""
    
    driver_text = f"{top_category} factors were the dominant risk drivers."
    
    return f"{posture_text} {region_text} {driver_text}"


def compute_top_drivers(alerts: List[Dict]) -> List[str]:
    """
    Compute top 3 risk drivers based on frequency and severity.
    Returns bullet-point strings.
    """
    if not alerts:
        return ["No significant risk drivers detected for this period."]
    
    driver_scores = Counter()
    
    for alert in alerts:
        region = alert.get('scope_region', 'Global')
        category = derive_category_from_alert_type(alert.get('alert_type', 'HIGH_IMPACT_EVENT'))
        severity = alert.get('severity', 3)
        
        key = f"{region} - {category}"
        driver_scores[key] += severity
    
    top_drivers = []
    for driver, score in driver_scores.most_common(3):
        parts = driver.split(' - ')
        region = parts[0] if parts else 'Unknown'
        category = parts[1] if len(parts) > 1 else 'Unknown'
        
        count = sum(1 for a in alerts 
                   if a.get('scope_region') == region and 
                   derive_category_from_alert_type(a.get('alert_type', 'HIGH_IMPACT_EVENT')) == category)
        
        top_drivers.append(f"{region}: {count} {category.lower()} event(s) with aggregate severity score {score}")
    
    return top_drivers if top_drivers else ["No significant risk drivers detected."]


def generate_seo_title(target_date: date, alerts: List[Dict]) -> str:
    """
    Generate dynamic SEO title.
    Enriched with top regions and themes if enough signal.
    """
    date_str = target_date.strftime("%b %d, %Y")
    
    if not alerts:
        return f"Geopolitical & Energy Risk Alerts - {date_str} | EnergyRiskIQ"
    
    regions = Counter(a.get('scope_region', 'Global') for a in alerts)
    top_regions = [r for r, _ in regions.most_common(2)]
    
    categories = Counter(derive_category_from_alert_type(a.get('alert_type', 'HIGH_IMPACT_EVENT')) for a in alerts)
    top_cat = categories.most_common(1)
    top_category = top_cat[0][0] if top_cat else ''
    
    if len(alerts) >= 3 and top_regions:
        region_str = ', '.join(top_regions[:2])
        if top_category:
            return f"Geopolitical & Energy Risk Alerts: {region_str}, {top_category} - {date_str} | EnergyRiskIQ"
        return f"Geopolitical & Energy Risk Alerts: {region_str} - {date_str} | EnergyRiskIQ"
    
    return f"Geopolitical & Energy Risk Alerts - {date_str} | EnergyRiskIQ"


def generate_seo_description(target_date: date, alerts: List[Dict]) -> str:
    """
    Generate dynamic SEO meta description.
    Sounds like risk intelligence, not news aggregation.
    """
    date_str = target_date.strftime("%B %d, %Y")
    
    if not alerts:
        return f"No significant geopolitical or energy risk alerts detected on {date_str}. Monitor daily risk intelligence with EnergyRiskIQ."
    
    total = len(alerts)
    critical_count = sum(1 for a in alerts if a.get('severity', 0) >= 4)
    
    regions = Counter(a.get('scope_region', 'Global') for a in alerts)
    top_regions = [r for r, _ in regions.most_common(2)]
    
    categories = Counter(derive_category_from_alert_type(a.get('alert_type', 'HIGH_IMPACT_EVENT')) for a in alerts)
    top_cats = [c for c, _ in categories.most_common(2)]
    
    region_str = ' and '.join(top_regions) if top_regions else 'global markets'
    cat_str = ' and '.join(top_cats).lower() if top_cats else 'risk'
    
    if critical_count > 0:
        severity_str = f"{critical_count} critical-severity"
    else:
        severity_str = f"{total}"
    
    return f"{severity_str} risk alert(s) for {region_str} on {date_str}. {cat_str.capitalize()} risk signals affecting energy markets and supply chains. EnergyRiskIQ daily intelligence."


def format_date_display(target_date: date) -> str:
    """Format date for display: January 15, 2026"""
    return target_date.strftime("%B %d, %Y")


def generate_daily_page_model(target_date: date) -> Dict:
    """
    Generate the complete page model for a daily SEO page.
    """
    alerts = get_alerts_for_date(target_date)
    alert_cards = [build_public_alert_card(a) for a in alerts]
    
    critical_count = sum(1 for c in alert_cards if c['severity'] >= 4)
    high_count = sum(1 for c in alert_cards if c['severity'] == 3)
    
    regions = Counter(c['region'] for c in alert_cards)
    categories = Counter(c['category'] for c in alert_cards)
    alert_types = Counter(c['alert_type_raw'] for c in alert_cards if c.get('alert_type_raw'))
    
    model = {
        'date': target_date.isoformat(),
        'date_display': format_date_display(target_date),
        'h1_title': f"Geopolitical and Energy Risk Alerts for {format_date_display(target_date)}",
        'seo_title': generate_seo_title(target_date, alerts),
        'seo_description': generate_seo_description(target_date, alerts),
        'risk_posture': compute_risk_posture(alerts),
        'top_drivers': compute_top_drivers(alerts),
        'stats': {
            'total_alerts': len(alert_cards),
            'critical_count': critical_count,
            'high_count': high_count,
            'regions': dict(regions),
            'categories': dict(categories),
            'alert_types': dict(alert_types)
        },
        'alert_cards': alert_cards,
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'prev_date': (target_date - timedelta(days=1)).isoformat(),
        'next_date': (target_date + timedelta(days=1)).isoformat() if target_date < get_yesterday_date() else None
    }
    
    return model


def save_daily_page(target_date: date, model: Dict) -> int:
    """
    Save/update the daily page model to the database.
    Returns the page ID.
    """
    with get_cursor() as cursor:
        cursor.execute("""
            INSERT INTO seo_daily_pages (
                page_date, seo_title, seo_description, page_json, 
                alert_count, generated_at
            ) VALUES (%s, %s, %s, %s, %s, NOW())
            ON CONFLICT (page_date) DO UPDATE SET
                seo_title = EXCLUDED.seo_title,
                seo_description = EXCLUDED.seo_description,
                page_json = EXCLUDED.page_json,
                alert_count = EXCLUDED.alert_count,
                generated_at = NOW(),
                updated_at = NOW()
            RETURNING id
        """, (
            target_date,
            model['seo_title'],
            model['seo_description'],
            json.dumps(model),
            model['stats']['total_alerts']
        ))
        result = cursor.fetchone()
        return result['id'] if result else None


def get_daily_page(target_date: date) -> Optional[Dict]:
    """Retrieve a saved daily page model."""
    query = """
    SELECT id, page_date, seo_title, seo_description, page_json, 
           alert_count, generated_at, updated_at
    FROM seo_daily_pages
    WHERE page_date = %s
    """
    result = execute_one(query, (target_date,))
    if result:
        return {
            'id': result['id'],
            'page_date': result['page_date'],
            'seo_title': result['seo_title'],
            'seo_description': result['seo_description'],
            'model': json.loads(result['page_json']) if result['page_json'] else None,
            'alert_count': result['alert_count'],
            'generated_at': result['generated_at'],
            'updated_at': result['updated_at']
        }
    return None


def get_recent_daily_pages(limit: int = 30) -> List[Dict]:
    """Get recent daily pages for archive/hub display."""
    query = """
    SELECT page_date, seo_title, alert_count, generated_at
    FROM seo_daily_pages
    ORDER BY page_date DESC
    LIMIT %s
    """
    results = execute_query(query, (limit,))
    return results if results else []


def get_monthly_pages(year: int, month: int) -> List[Dict]:
    """Get all daily pages for a specific month."""
    from calendar import monthrange
    
    start_date = date(year, month, 1)
    _, last_day = monthrange(year, month)
    end_date = date(year, month, last_day)
    
    query = """
    SELECT page_date, seo_title, alert_count, generated_at
    FROM seo_daily_pages
    WHERE page_date >= %s AND page_date <= %s
    ORDER BY page_date DESC
    """
    results = execute_query(query, (start_date, end_date))
    return results if results else []


def get_available_months() -> List[Dict]:
    """Get list of months that have daily pages."""
    query = """
    SELECT 
        EXTRACT(YEAR FROM page_date)::int as year,
        EXTRACT(MONTH FROM page_date)::int as month,
        COUNT(*) as page_count,
        SUM(alert_count) as total_alerts
    FROM seo_daily_pages
    GROUP BY EXTRACT(YEAR FROM page_date), EXTRACT(MONTH FROM page_date)
    ORDER BY year DESC, month DESC
    """
    results = execute_query(query)
    return results if results else []


def generate_sitemap_entries() -> List[Dict]:
    """Generate sitemap entries for all SEO pages."""
    entries = []
    
    entries.append({
        'loc': '/',
        'priority': '1.0',
        'changefreq': 'daily'
    })
    
    entries.append({
        'loc': '/alerts',
        'priority': '0.9',
        'changefreq': 'daily'
    })
    
    months = get_available_months()
    for m in months:
        entries.append({
            'loc': f"/alerts/{m['year']}/{m['month']:02d}",
            'priority': '0.7',
            'changefreq': 'weekly'
        })
    
    pages = get_recent_daily_pages(limit=90)
    for p in pages:
        page_date = p['page_date']
        if isinstance(page_date, str):
            page_date = datetime.fromisoformat(page_date).date()
        entries.append({
            'loc': f"/alerts/daily/{page_date.isoformat()}",
            'priority': '0.8',
            'changefreq': 'never'
        })
    
    return entries
