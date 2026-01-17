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


def transform_headline_to_risk_signal(headline: str) -> str:
    """
    Transform news-like headlines into risk-signal language.
    Removes news patterns and reframes as risk intelligence.
    
    Examples:
    - "LIVE: Israel continues deadly Gaza attacks" → "Middle East conflict escalation signals elevated regional risk"
    - "Why is Iran's economy failing?" → "Iran economic instability signals rising civil unrest risk"
    - "Photos: Power outages in Kyiv" → "Ukraine infrastructure disruption signals energy supply risk"
    """
    if not headline:
        return "Risk event detected"
    
    import re
    
    # Remove news-like prefixes
    news_prefixes = [
        r'^LIVE:\s*',
        r'^BREAKING:\s*',
        r'^UPDATE:\s*',
        r'^WATCH:\s*',
        r'^VIDEO:\s*',
        r'^PHOTOS?:\s*',
        r'^ANALYSIS:\s*',
        r'^OPINION:\s*',
        r'^EXCLUSIVE:\s*',
        r'^DEVELOPING:\s*',
        r'^URGENT:\s*',
        r'^JUST IN:\s*',
    ]
    
    cleaned = headline
    for prefix in news_prefixes:
        cleaned = re.sub(prefix, '', cleaned, flags=re.IGNORECASE)
    
    # Remove question patterns at the start
    cleaned = re.sub(r'^Why is\s+', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'^What\s+', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'^How\s+', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'^Who\s+', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'^When\s+', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'^Where\s+', '', cleaned, flags=re.IGNORECASE)
    
    # Remove trailing question marks
    cleaned = re.sub(r'\?+$', '', cleaned)
    
    # Remove ellipsis and trailing dots
    cleaned = re.sub(r'\.{2,}$', '', cleaned)
    cleaned = re.sub(r'…$', '', cleaned)
    
    cleaned = cleaned.strip()
    
    # If headline is very short after cleaning, return a generic risk statement
    if len(cleaned) < 10:
        return "Risk event detected requiring monitoring"
    
    # Check if headline already contains risk-signal language
    risk_terms = ['risk', 'signal', 'disruption', 'escalation', 'pressure', 'instability', 'volatility', 'impact']
    has_risk_language = any(term in cleaned.lower() for term in risk_terms)
    
    if has_risk_language:
        # Already risk-framed, just clean and return
        return cleaned
    
    # Add risk-signal suffix if not present
    # Detect geographic/topic context for better framing
    regions = ['europe', 'middle east', 'asia', 'russia', 'ukraine', 'iran', 'israel', 'gaza', 'china']
    topics = ['oil', 'gas', 'energy', 'pipeline', 'lng', 'nuclear', 'supply', 'trade', 'economy']
    
    lower_cleaned = cleaned.lower()
    detected_region = None
    detected_topic = None
    
    for region in regions:
        if region in lower_cleaned:
            detected_region = region.title()
            break
    
    for topic in topics:
        if topic in lower_cleaned:
            detected_topic = topic
            break
    
    # Build risk-signal suffix
    if detected_region and detected_topic:
        suffix = f" - signals {detected_topic} market risk"
    elif detected_region:
        suffix = " - signals regional risk escalation"
    elif detected_topic:
        suffix = f" - signals {detected_topic} supply risk"
    else:
        suffix = " - risk signal detected"
    
    # Capitalize first letter
    if cleaned and cleaned[0].islower():
        cleaned = cleaned[0].upper() + cleaned[1:]
    
    return cleaned + suffix


def build_public_alert_card(alert: Dict) -> Dict:
    """
    Build a public-safe alert card for SEO pages.
    No premium fields exposed. URLs sanitized.
    Headlines transformed to risk-signal language.
    """
    assets = alert.get('scope_assets') or []
    
    # First sanitize, then transform to risk-signal language
    raw_title = sanitize_text_for_seo(alert.get('headline', 'Risk Alert'))
    public_title = transform_headline_to_risk_signal(raw_title)
    
    public_summary = sanitize_text_for_seo(alert.get('body', ''))
    if public_summary and len(public_summary) > 200:
        public_summary = public_summary[:197] + '...'
    
    alert_type = alert.get('alert_type', 'HIGH_IMPACT_EVENT')
    category = derive_category_from_alert_type(alert_type)
    severity = alert.get('severity', 3)
    
    # Derive severity label for consistent display
    if severity >= 5:
        severity_label = 'Critical'
    elif severity >= 4:
        severity_label = 'High'
    elif severity >= 3:
        severity_label = 'Moderate'
    else:
        severity_label = 'Low'
    
    return {
        'id': alert['id'],
        'public_title': public_title,
        'public_summary': public_summary,
        'severity': severity,
        'severity_label': severity_label,
        'category': category,
        'region': alert.get('scope_region', 'Global'),
        'event_type': ALERT_TYPE_DISPLAY.get(alert_type, alert_type),
        'alert_type_raw': alert_type,
        'timestamp': alert['created_at'].isoformat() if alert.get('created_at') else None,
        'assets': assets[:3] if assets else [],
        'source_domain': None
    }


def compute_risk_posture(alerts: List[Dict]) -> Dict:
    """
    Generate a humanized daily risk posture summary.
    Returns dict with posture level, summary text, and structured data.
    """
    if not alerts:
        return {
            'level': 'STABLE',
            'summary': "No significant risk events were detected for this period. Energy markets and supply chains operated within normal parameters, with no major geopolitical escalations requiring attention.",
            'critical_count': 0,
            'high_count': 0,
            'total': 0
        }
    
    total = len(alerts)
    critical_count = sum(1 for a in alerts if a.get('severity', 0) >= 5)
    high_count = sum(1 for a in alerts if a.get('severity', 0) == 4)
    moderate_count = sum(1 for a in alerts if a.get('severity', 0) == 3)
    
    regions = Counter(a.get('scope_region', 'Global') for a in alerts)
    top_regions = [r for r, _ in regions.most_common(2)]
    
    categories = Counter(derive_category_from_alert_type(a.get('alert_type', 'HIGH_IMPACT_EVENT')) for a in alerts)
    top_cats = [c for c, _ in categories.most_common(2)]
    
    # Determine posture level
    if critical_count >= 3:
        level = 'ELEVATED'
    elif critical_count >= 1 or high_count >= 3:
        level = 'MODERATE'
    else:
        level = 'STABLE'
    
    # Build humanized summary
    region_phrase = ' and '.join(top_regions) if top_regions else 'global markets'
    category_phrase = ' and '.join([c.lower() for c in top_cats]) if top_cats else 'geopolitical'
    
    if level == 'ELEVATED':
        summary = f"Risk conditions were elevated, driven by intensified {category_phrase} pressure across {region_phrase}, with {critical_count} critical-severity escalation signals detected. Market participants should monitor developments closely for potential supply disruption or price volatility."
    elif level == 'MODERATE':
        summary = f"Risk conditions were moderate, with {total} alerts detected across {region_phrase}. {category_phrase.capitalize()} factors were the primary drivers, with {high_count} high-severity and {critical_count} critical events requiring attention."
    else:
        summary = f"Risk conditions remained stable with {total} alerts of predominantly moderate severity. Activity was concentrated in {region_phrase}, with {category_phrase} factors as the main theme. No immediate supply chain or market disruption signals detected."
    
    return {
        'level': level,
        'summary': summary,
        'critical_count': critical_count,
        'high_count': high_count,
        'moderate_count': moderate_count,
        'total': total
    }


def compute_top_drivers(alerts: List[Dict]) -> List[Dict]:
    """
    Compute top 3 risk drivers based on frequency and severity.
    Returns list of dicts with text, region, category, and link info for internal linking.
    """
    if not alerts:
        return [{
            'text': "No significant risk drivers detected for this period.",
            'region': None,
            'category': None,
            'region_slug': None,
            'category_slug': None
        }]
    
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
        
        # Create slugs for internal linking
        region_slug = region.lower().replace(' ', '-') if region else None
        category_slug = category.lower().replace(' ', '-') if category else None
        
        top_drivers.append({
            'text': f"{region}: {count} {category.lower()} event(s) detected",
            'region': region,
            'category': category,
            'count': count,
            'score': score,
            'region_slug': region_slug,
            'category_slug': category_slug
        })
    
    return top_drivers if top_drivers else [{
        'text': "No significant risk drivers detected.",
        'region': None,
        'category': None,
        'region_slug': None,
        'category_slug': None
    }]


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
    Uses consistent severity buckets: Critical (5/5), High (4/5), Moderate (3/5).
    """
    date_str = target_date.strftime("%B %d, %Y")
    
    if not alerts:
        return f"No significant geopolitical or energy risk alerts detected on {date_str}. Monitor daily risk intelligence with EnergyRiskIQ."
    
    total = len(alerts)
    # Consistent severity buckets: Critical=5, High=4, Moderate=3
    critical_count = sum(1 for a in alerts if a.get('severity', 0) >= 5)
    high_count = sum(1 for a in alerts if a.get('severity', 0) == 4)
    
    regions = Counter(a.get('scope_region', 'Global') for a in alerts)
    top_regions = [r for r, _ in regions.most_common(2)]
    
    categories = Counter(derive_category_from_alert_type(a.get('alert_type', 'HIGH_IMPACT_EVENT')) for a in alerts)
    top_cats = [c for c, _ in categories.most_common(2)]
    
    region_str = ' and '.join(top_regions) if top_regions else 'global markets'
    cat_str = ' and '.join(top_cats).lower() if top_cats else 'risk'
    
    if critical_count > 0:
        severity_str = f"{critical_count} critical-severity"
    elif high_count > 0:
        severity_str = f"{high_count} high-severity"
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
    
    # Consistent severity buckets: Critical (5/5), High (4/5), Moderate (3/5)
    critical_count = sum(1 for c in alert_cards if c['severity'] >= 5)
    high_count = sum(1 for c in alert_cards if c['severity'] == 4)
    moderate_count = sum(1 for c in alert_cards if c['severity'] == 3)
    low_count = sum(1 for c in alert_cards if c['severity'] <= 2)
    
    regions = Counter(c['region'] for c in alert_cards)
    categories = Counter(c['category'] for c in alert_cards)
    alert_types = Counter(c['alert_type_raw'] for c in alert_cards if c.get('alert_type_raw'))
    
    risk_posture = compute_risk_posture(alerts)
    
    model = {
        'date': target_date.isoformat(),
        'date_display': format_date_display(target_date),
        'h1_title': f"Geopolitical and Energy Risk Alerts for {format_date_display(target_date)}",
        'seo_title': generate_seo_title(target_date, alerts),
        'seo_description': generate_seo_description(target_date, alerts),
        'risk_posture': risk_posture,
        'top_drivers': compute_top_drivers(alerts),
        'stats': {
            'total_alerts': len(alert_cards),
            'critical_count': critical_count,
            'high_count': high_count,
            'moderate_count': moderate_count,
            'low_count': low_count,
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
        page_json = result['page_json']
        if page_json:
            if isinstance(page_json, str):
                model = json.loads(page_json)
            else:
                model = page_json
        else:
            model = None
        return {
            'id': result['id'],
            'page_date': result['page_date'],
            'seo_title': result['seo_title'],
            'seo_description': result['seo_description'],
            'model': model,
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
