"""
SEO Daily Page Generator for EnergyRiskIQ

Generates SEO-optimized daily alerts pages with 24-hour delay.
Uses only public alert data (no premium leakage).
"""

import logging
import json
import re
import os
from datetime import datetime, timezone, timedelta, date
from typing import Dict, List, Optional, Any
from collections import Counter

from openai import OpenAI
from src.db.db import get_cursor, execute_query, execute_one

logger = logging.getLogger(__name__)


def get_openai_client() -> Optional[OpenAI]:
    """Get OpenAI client using Replit AI Integrations."""
    # Use Replit AI Integrations (preferred) or fallback to standard OpenAI key
    ai_api_key = os.environ.get('AI_INTEGRATIONS_OPENAI_API_KEY')
    ai_base_url = os.environ.get('AI_INTEGRATIONS_OPENAI_BASE_URL')
    
    if ai_api_key and ai_base_url:
        return OpenAI(api_key=ai_api_key, base_url=ai_base_url)
    
    # Fallback to standard OpenAI key
    openai_key = os.environ.get('OPENAI_API_KEY')
    if openai_key:
        return OpenAI(api_key=openai_key)
    
    return None


def vary_duplicate_titles_with_ai(cards: List[Dict]) -> List[Dict]:
    """
    Use AI to generate unique titles for cards that have duplicate generic titles.
    Extracts specific event details from the body to create differentiated titles.
    """
    if not cards:
        return cards
    
    # Group cards by their public_title
    title_groups = {}
    for i, card in enumerate(cards):
        title = card.get('public_title', '')
        if title not in title_groups:
            title_groups[title] = []
        title_groups[title].append((i, card))
    
    # Find groups with duplicates (2+ cards with same title)
    duplicate_groups = {title: items for title, items in title_groups.items() if len(items) > 1}
    
    if not duplicate_groups:
        return cards  # No duplicates to fix
    
    client = get_openai_client()
    if not client:
        logger.warning("OpenAI client unavailable for title variation")
        return cards  # Return unchanged if no API key
    
    # Build cards list copy to modify
    result_cards = list(cards)
    
    for base_title, items in duplicate_groups.items():
        # Prepare batch request for AI
        summaries = []
        for idx, card in items:
            summary = card.get('public_summary', '')[:300]
            region = card.get('region', 'Global')
            summaries.append(f"Card {idx}: Region: {region}. Content: {summary}")
        
        prompt = f"""You are creating SEO-optimized titles for energy risk intelligence alerts.

The base title is: "{base_title}"

These {len(items)} alerts all have this same generic title, but they describe DIFFERENT events:

{chr(10).join(summaries)}

Generate a unique, specific title for EACH card that:
1. Keeps the risk-signal language style (e.g., "signals", "elevated risk", "disruption")
2. Adds specific details from the content (e.g., "Iran airspace closure", "US strike threat", "Lebanon attacks")
3. Is 8-15 words long
4. Does NOT start with the region name (avoid "Middle East...")

Return ONLY a JSON object like this:
{{"0": "Specific title for card 0", "1": "Specific title for card 1", ...}}

Use the original card indices as keys."""

        try:
            response = client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=500
            )
            
            content = response.choices[0].message.content
            if not content:
                continue
            content = content.strip()
            # Extract JSON from response (handle markdown code blocks)
            if '```' in content:
                match = re.search(r'\{[^}]+\}', content, re.DOTALL)
                if match:
                    content = match.group()
            
            new_titles = json.loads(content)
            
            # Apply new titles to cards
            for idx, card in items:
                str_idx = str(idx)
                if str_idx in new_titles:
                    result_cards[idx] = {**card, 'public_title': new_titles[str_idx]}
                    logger.info(f"Varied title for card {idx}: {new_titles[str_idx][:50]}...")
        
        except Exception as e:
            logger.error(f"AI title variation failed for '{base_title[:30]}...': {e}")
            # Continue with original titles on error
    
    return result_cards


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


def clean_alert_body_for_public(body: str) -> str:
    """
    Clean structured alert body to extract human-readable summary.
    Removes internal prefixes like 'ASSET RISK ALERT: FREIGHT Region: Europe Risk Score: 100/100...'
    Extracts just the KEY DRIVERS section if present.
    """
    import re
    if not body:
        return ""
    
    # Try to extract KEY DRIVERS section
    key_drivers_match = re.search(r'KEY DRIVERS?:\s*(.+)', body, re.IGNORECASE | re.DOTALL)
    if key_drivers_match:
        drivers_text = key_drivers_match.group(1).strip()
        # Clean up numbered list formatting
        drivers_text = re.sub(r'^\d+\.\s*', '', drivers_text)  # Remove leading number
        drivers_text = re.sub(r'\s+\d+\.\s+', '. ', drivers_text)  # Replace mid-text numbers with periods
        return drivers_text
    
    # Try to extract content after Direction/Confidence markers
    after_conf_match = re.search(r'Confidence:\s*\d+%\s*(.+)', body, re.IGNORECASE)
    if after_conf_match:
        return after_conf_match.group(1).strip()
    
    # Try to remove common structured prefixes
    cleaned = re.sub(
        r'^(ASSET RISK ALERT|REGIONAL RISK ALERT|HIGH[- ]IMPACT EVENT)[:\s]*',
        '', body, flags=re.IGNORECASE
    )
    cleaned = re.sub(
        r'^[A-Z]+\s+Region:\s*[A-Za-z\s]+Risk Score:\s*\d+/\d+\s*Direction:\s*[A-Z]+\s*Confidence:\s*\d+%\s*',
        '', cleaned, flags=re.IGNORECASE
    )
    
    if cleaned and cleaned != body:
        return cleaned.strip()
    
    # Fallback: return sanitized original
    return sanitize_text_for_seo(body)


def transform_headline_to_risk_signal(headline: str) -> str:
    """
    Transform news-like headlines into risk-signal language.
    Completely rewrites headlines to sound like risk intelligence, not news.
    
    Examples:
    - "LIVE: Israel continues deadly Gaza attacks" → "Gaza conflict escalation signals elevated regional instability"
    - "Why is Iran's economy failing?" → "Iran economic instability signals elevated civil unrest risk"
    - "Photos: Power outages in Kyiv" → "Ukraine energy infrastructure disruption signals supply risk"
    - "What happened at UN Security Council" → "UN Security Council activity signals diplomatic escalation risk"
    """
    if not headline:
        return "Risk event detected requiring monitoring"
    
    import re
    
    lower = headline.lower()
    
    # Check if already properly risk-framed (has risk language AND doesn't start with news patterns)
    risk_terms = ['risk', 'signals', 'disruption', 'escalation', 'instability', 'volatility', 'elevated']
    news_starts = ['live:', 'breaking:', 'update:', 'watch:', 'video:', 'photo', 'why ', 'what ', 'how ', 'who ', 'when ', 'where ']
    
    has_risk_language = sum(1 for term in risk_terms if term in lower) >= 2
    starts_with_news = any(lower.startswith(p) for p in news_starts)
    
    if has_risk_language and not starts_with_news:
        return headline
    
    # === ENTITY EXTRACTION ===
    
    # Region/Country detection (order matters - more specific first)
    region_map = {
        'kyiv': 'Ukraine', 'kiev': 'Ukraine', 'ukraine': 'Ukraine', 'ukrainian': 'Ukraine',
        'russia': 'Russia', 'russian': 'Russia', 'moscow': 'Russia', 'kremlin': 'Russia',
        'gaza': 'Gaza', 'palestinian': 'Palestine', 'west bank': 'Palestine',
        'israel': 'Israel', 'israeli': 'Israel', 'tel aviv': 'Israel',
        'iran': 'Iran', 'iranian': 'Iran', 'tehran': 'Iran',
        'china': 'China', 'chinese': 'China', 'beijing': 'China',
        'saudi': 'Saudi Arabia', 'riyadh': 'Saudi Arabia',
        'iraq': 'Iraq', 'iraqi': 'Iraq', 'baghdad': 'Iraq',
        'syria': 'Syria', 'syrian': 'Syria', 'damascus': 'Syria',
        'yemen': 'Yemen', 'houthi': 'Yemen',
        'libya': 'Libya', 'libyan': 'Libya',
        'venezuela': 'Venezuela',
        'nigeria': 'Nigeria', 'niger': 'Niger',
        'europe': 'Europe', 'european': 'Europe', 'eu ': 'Europe',
        'middle east': 'Middle East',
        'asia': 'Asia', 'asian': 'Asia',
        'africa': 'Africa', 'african': 'Africa',
        'un ': 'UN', 'united nations': 'UN', 'security council': 'UN Security Council',
        'nato': 'NATO', 'opec': 'OPEC',
    }
    
    detected_region = None
    for pattern, region in region_map.items():
        if pattern in lower:
            detected_region = region
            break
    
    # Event type detection → risk category
    event_patterns = {
        # Conflict/Violence
        (r'attack|strike|bomb|shell|missile|drone|militar|combat|war|fight|kill|dead|death|casualt', 'conflict', 'escalation'),
        # Infrastructure
        (r'power outage|blackout|grid|electricity|infrastructure|pipeline|refiner|plant|facility', 'infrastructure', 'disruption'),
        # Civil unrest
        (r'protest|riot|demonstrat|unrest|uprising|civil|dissent|opposition', 'civil unrest', 'instability'),
        # Economic
        (r'econom|inflation|currency|sanction|trade|tariff|embargo|price|cost|market', 'economic', 'pressure'),
        # Energy supply
        (r'oil|gas|lng|fuel|energy|petrol|crude|barrel|opec|supply|export|import', 'energy supply', 'volatility'),
        # Diplomatic
        (r'diplomat|negotiat|talk|summit|council|treaty|agreement|alliance|relation', 'diplomatic', 'tension'),
        # Security
        (r'secur|terror|threat|intelligen|spy|cyber|hack', 'security', 'threat'),
        # Political
        (r'elect|vote|govern|regime|coup|leader|president|minister|parliament', 'political', 'uncertainty'),
        # Nuclear
        (r'nuclear|atomic|uranium|enrichment|weapon|warhead', 'nuclear', 'escalation'),
        # Shipping/Trade routes
        (r'ship|vessel|tanker|port|strait|canal|maritime|cargo|freight', 'maritime trade', 'disruption'),
    }
    
    detected_event_type = 'geopolitical'
    detected_risk_word = 'risk'
    
    for pattern, event_type, risk_word in event_patterns:
        if re.search(pattern, lower):
            detected_event_type = event_type
            detected_risk_word = risk_word
            break
    
    # === BUILD RISK-SIGNAL TITLE ===
    
    # Format: "[Region] [event type] [risk word] signals elevated [outcome] risk"
    
    if detected_region:
        if detected_event_type == 'conflict':
            return f"{detected_region} conflict {detected_risk_word} signals elevated regional instability"
        elif detected_event_type == 'infrastructure':
            return f"{detected_region} infrastructure {detected_risk_word} signals energy supply risk"
        elif detected_event_type == 'civil unrest':
            return f"{detected_region} civil {detected_risk_word} signals elevated political risk"
        elif detected_event_type == 'economic':
            return f"{detected_region} economic {detected_risk_word} signals market volatility risk"
        elif detected_event_type == 'energy supply':
            return f"{detected_region} energy {detected_risk_word} signals supply chain risk"
        elif detected_event_type == 'diplomatic':
            return f"{detected_region} diplomatic {detected_risk_word} signals geopolitical uncertainty"
        elif detected_event_type == 'security':
            return f"{detected_region} security {detected_risk_word} signals elevated threat level"
        elif detected_event_type == 'political':
            return f"{detected_region} political {detected_risk_word} signals governance instability"
        elif detected_event_type == 'nuclear':
            return f"{detected_region} nuclear {detected_risk_word} signals elevated proliferation risk"
        elif detected_event_type == 'maritime trade':
            return f"{detected_region} maritime {detected_risk_word} signals trade route vulnerability"
        else:
            return f"{detected_region} {detected_event_type} activity signals elevated regional risk"
    else:
        # No region detected - use generic but still risk-framed
        if detected_event_type != 'geopolitical':
            return f"Global {detected_event_type} {detected_risk_word} signals elevated market risk"
        else:
            # Fallback: extract key nouns and build generic risk title
            return f"Geopolitical development signals elevated market risk"


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
    
    # Clean the body to extract meaningful content (removes structured prefixes)
    raw_body = alert.get('body', '')
    public_summary = clean_alert_body_for_public(raw_body)
    public_summary = sanitize_text_for_seo(public_summary)
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
    all_cards = [build_public_alert_card(a) for a in alerts]
    
    # STEP 1: Deduplicate cards by summary to avoid near-identical content blocks
    seen_summaries = set()
    deduped_cards = []
    for card in all_cards:
        summary_key = card.get('public_summary', '')[:100].lower().strip()
        if summary_key not in seen_summaries:
            seen_summaries.add(summary_key)
            deduped_cards.append(card)
    
    # STEP 2: Use AI to vary duplicate titles (same title, different content)
    alert_cards = vary_duplicate_titles_with_ai(deduped_cards)
    
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
    """Get list of months that have daily pages with max date for lastmod."""
    query = """
    SELECT 
        EXTRACT(YEAR FROM page_date)::int as year,
        EXTRACT(MONTH FROM page_date)::int as month,
        COUNT(*) as page_count,
        SUM(alert_count) as total_alerts,
        MAX(page_date) as max_date
    FROM seo_daily_pages
    GROUP BY EXTRACT(YEAR FROM page_date), EXTRACT(MONTH FROM page_date)
    ORDER BY year DESC, month DESC
    """
    results = execute_query(query)
    return results if results else []


def generate_sitemap_entries() -> List[Dict]:
    """Generate sitemap entries for all SEO pages with lastmod dates."""
    from datetime import date
    entries = []
    
    today = date.today().isoformat()
    
    entries.append({
        'loc': '/',
        'priority': '1.0',
        'changefreq': 'daily',
        'lastmod': today
    })
    
    entries.append({
        'loc': '/alerts',
        'priority': '0.9',
        'changefreq': 'daily',
        'lastmod': today
    })
    
    static_lastmod = '2025-01-15'
    
    entries.append({
        'loc': '/privacy',
        'priority': '0.4',
        'changefreq': 'monthly',
        'lastmod': static_lastmod
    })
    
    entries.append({
        'loc': '/terms',
        'priority': '0.4',
        'changefreq': 'monthly',
        'lastmod': static_lastmod
    })
    
    entries.append({
        'loc': '/disclaimer',
        'priority': '0.4',
        'changefreq': 'monthly',
        'lastmod': static_lastmod
    })
    
    entries.append({
        'loc': '/marketing/samples',
        'priority': '0.5',
        'changefreq': 'monthly',
        'lastmod': static_lastmod
    })
    
    entries.append({
        'loc': '/geri',
        'priority': '0.9',
        'changefreq': 'daily',
        'lastmod': today
    })
    
    entries.append({
        'loc': '/geri/methodology',
        'priority': '0.8',
        'changefreq': 'monthly',
        'lastmod': today
    })
    
    entries.append({
        'loc': '/why-geri',
        'priority': '0.8',
        'changefreq': 'weekly',
        'lastmod': today
    })
    
    try:
        from src.geri.geri_history_service import get_all_snapshot_dates, get_available_months as get_geri_months
        
        geri_dates = get_all_snapshot_dates()
        geri_months = get_geri_months()
        
        latest_geri_date = geri_dates[0] if geri_dates else today
        entries.append({
            'loc': '/geri/history',
            'priority': '0.8',
            'changefreq': 'daily',
            'lastmod': latest_geri_date
        })
        
        for m in geri_months:
            max_date = m.get('max_date', f"{m['year']}-{m['month']:02d}-01")
            entries.append({
                'loc': f"/geri/{m['year']}/{m['month']:02d}",
                'priority': '0.7',
                'changefreq': 'weekly',
                'lastmod': max_date if isinstance(max_date, str) else max_date
            })
        
        for geri_date in geri_dates:
            entries.append({
                'loc': f"/geri/{geri_date}",
                'priority': '0.8',
                'changefreq': 'never',
                'lastmod': geri_date
            })
    except Exception:
        pass
    
    try:
        from src.reri.eeri_history_service import get_all_eeri_dates, get_eeri_available_months
        
        entries.append({
            'loc': '/eeri',
            'priority': '0.9',
            'changefreq': 'daily',
            'lastmod': today
        })
        
        entries.append({
            'loc': '/eeri/methodology',
            'priority': '0.8',
            'changefreq': 'monthly',
            'lastmod': today
        })
        
        eeri_dates = get_all_eeri_dates()
        eeri_months = get_eeri_available_months()
        
        latest_eeri_date = eeri_dates[0] if eeri_dates else today
        entries.append({
            'loc': '/eeri/history',
            'priority': '0.8',
            'changefreq': 'daily',
            'lastmod': latest_eeri_date
        })
        
        for m in eeri_months:
            max_date = m.get('max_date', f"{m['year']}-{m['month']:02d}-01")
            entries.append({
                'loc': f"/eeri/{m['year']}/{m['month']:02d}",
                'priority': '0.7',
                'changefreq': 'weekly',
                'lastmod': max_date if isinstance(max_date, str) else max_date
            })
        
        for eeri_date in eeri_dates:
            entries.append({
                'loc': f"/eeri/{eeri_date}",
                'priority': '0.8',
                'changefreq': 'never',
                'lastmod': eeri_date
            })
    except Exception:
        pass
    
    try:
        from src.egsi.egsi_history_service import get_all_egsi_m_dates, get_egsi_m_available_months
        
        entries.append({
            'loc': '/egsi',
            'priority': '0.9',
            'changefreq': 'daily',
            'lastmod': today
        })
        
        entries.append({
            'loc': '/egsi/methodology',
            'priority': '0.8',
            'changefreq': 'monthly',
            'lastmod': today
        })
        
        egsi_dates = get_all_egsi_m_dates()
        egsi_months = get_egsi_m_available_months()
        
        latest_egsi_date = egsi_dates[0] if egsi_dates else today
        entries.append({
            'loc': '/egsi/history',
            'priority': '0.8',
            'changefreq': 'daily',
            'lastmod': latest_egsi_date
        })
        
        for m in egsi_months:
            max_date = m.get('max_date', f"{m['year']}-{m['month']:02d}-01")
            entries.append({
                'loc': f"/egsi/{m['year']}/{m['month']:02d}",
                'priority': '0.7',
                'changefreq': 'weekly',
                'lastmod': max_date if isinstance(max_date, str) else max_date
            })
        
        for egsi_date in egsi_dates:
            entries.append({
                'loc': f"/egsi/{egsi_date}",
                'priority': '0.8',
                'changefreq': 'never',
                'lastmod': egsi_date
            })
    except Exception:
        pass
    
    months = get_available_months()
    for m in months:
        max_date = m.get('max_date')
        if max_date:
            if isinstance(max_date, str):
                lastmod = max_date[:10]
            else:
                lastmod = max_date.isoformat() if hasattr(max_date, 'isoformat') else str(max_date)[:10]
        else:
            lastmod = f"{m['year']}-{m['month']:02d}-01"
        entries.append({
            'loc': f"/alerts/{m['year']}/{m['month']:02d}",
            'priority': '0.7',
            'changefreq': 'weekly',
            'lastmod': lastmod
        })
    
    pages = get_recent_daily_pages(limit=90)
    for p in pages:
        page_date = p['page_date']
        if isinstance(page_date, str):
            page_date_obj = datetime.fromisoformat(page_date).date()
            lastmod = page_date[:10]
        else:
            page_date_obj = page_date
            lastmod = page_date.isoformat()
        entries.append({
            'loc': f"/alerts/daily/{page_date_obj.isoformat()}",
            'priority': '0.8',
            'changefreq': 'never',
            'lastmod': lastmod
        })
    
    return entries


# =============================================================================
# REGIONAL DAILY PAGES
# =============================================================================

REGION_DISPLAY_NAMES = {
    'middle-east': 'Middle East',
    'europe': 'Europe',
    'asia': 'Asia',
    'americas': 'Americas',
    'africa': 'Africa',
    'global': 'Global',
}

REGION_SCOPE_MAPPINGS = {
    'middle-east': ['Middle East', 'middle-east', 'middle east', 'MIDDLE EAST'],
    'europe': ['Europe', 'europe', 'EUROPE', 'EU', 'European Union'],
    'asia': ['Asia', 'asia', 'ASIA', 'Asia-Pacific', 'APAC'],
    'americas': ['Americas', 'americas', 'AMERICAS', 'North America', 'South America', 'Latin America'],
    'africa': ['Africa', 'africa', 'AFRICA', 'Sub-Saharan Africa'],
}


def get_alerts_for_date_and_region(target_date: date, region_slug: str) -> List[Dict]:
    """
    Fetch all alert_events for a specific date and region.
    Returns only public-safe fields.
    """
    start_dt = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=timezone.utc)
    end_dt = start_dt + timedelta(days=1)
    
    region_variants = REGION_SCOPE_MAPPINGS.get(region_slug, [region_slug])
    
    placeholders = ', '.join(['%s'] * len(region_variants))
    query = f"""
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
      AND scope_region IN ({placeholders})
    ORDER BY severity DESC, created_at DESC
    """
    
    params = [start_dt, end_dt] + region_variants
    results = execute_query(query, tuple(params))
    return results if results else []


def generate_regional_seo_title(target_date: date, region_name: str, alerts: List[Dict]) -> str:
    """Generate SEO-optimized title for a regional daily page."""
    date_display = format_date_display(target_date)
    count = len(alerts)
    
    if count == 0:
        return f"{region_name} Risk Alerts for {date_display} | EnergyRiskIQ"
    
    severity_max = max((a.get('severity', 0) for a in alerts), default=0)
    if severity_max >= 5:
        return f"Critical {region_name} Risk Alerts for {date_display} | EnergyRiskIQ"
    elif severity_max >= 4:
        return f"High-Priority {region_name} Risk Alerts for {date_display} | EnergyRiskIQ"
    else:
        return f"{region_name} Risk Alerts for {date_display} | EnergyRiskIQ"


def generate_regional_seo_description(target_date: date, region_name: str, alerts: List[Dict]) -> str:
    """Generate SEO meta description for a regional daily page."""
    date_display = format_date_display(target_date)
    count = len(alerts)
    
    if count == 0:
        return f"No significant {region_name} risk alerts detected on {date_display}. Monitor daily {region_name} risk intelligence with EnergyRiskIQ."
    
    critical = sum(1 for a in alerts if a.get('severity', 0) >= 5)
    high = sum(1 for a in alerts if a.get('severity', 0) == 4)
    
    parts = []
    if critical > 0:
        parts.append(f"{critical} critical")
    if high > 0:
        parts.append(f"{high} high-priority")
    
    if parts:
        severity_text = " and ".join(parts)
        return f"{count} {region_name} risk alerts for {date_display}, including {severity_text} events. Track geopolitical and energy supply disruptions."
    
    return f"{count} {region_name} risk alerts for {date_display}. Track geopolitical and energy supply disruptions affecting {region_name}."


def generate_regional_daily_page_model(target_date: date, region_slug: str) -> Dict:
    """
    Generate the complete page model for a regional daily SEO page.
    """
    region_name = REGION_DISPLAY_NAMES.get(region_slug, region_slug.replace('-', ' ').title())
    
    alerts = get_alerts_for_date_and_region(target_date, region_slug)
    all_cards = [build_public_alert_card(a) for a in alerts]
    
    seen_summaries = set()
    deduped_cards = []
    for card in all_cards:
        summary_key = card.get('public_summary', '')[:100].lower().strip()
        if summary_key not in seen_summaries:
            seen_summaries.add(summary_key)
            deduped_cards.append(card)
    
    alert_cards = vary_duplicate_titles_with_ai(deduped_cards)
    
    critical_count = sum(1 for c in alert_cards if c['severity'] >= 5)
    high_count = sum(1 for c in alert_cards if c['severity'] == 4)
    moderate_count = sum(1 for c in alert_cards if c['severity'] == 3)
    low_count = sum(1 for c in alert_cards if c['severity'] <= 2)
    
    categories = Counter(c['category'] for c in alert_cards)
    alert_types = Counter(c['alert_type_raw'] for c in alert_cards if c.get('alert_type_raw'))
    
    risk_posture = compute_risk_posture(alerts)
    
    model = {
        'date': target_date.isoformat(),
        'date_display': format_date_display(target_date),
        'region_slug': region_slug,
        'region_name': region_name,
        'h1_title': f"{region_name} Risk Alerts for {format_date_display(target_date)}",
        'seo_title': generate_regional_seo_title(target_date, region_name, alerts),
        'seo_description': generate_regional_seo_description(target_date, region_name, alerts),
        'risk_posture': risk_posture,
        'top_drivers': compute_top_drivers(alerts),
        'stats': {
            'total_alerts': len(alert_cards),
            'critical_count': critical_count,
            'high_count': high_count,
            'moderate_count': moderate_count,
            'low_count': low_count,
            'categories': dict(categories),
            'alert_types': dict(alert_types)
        },
        'alert_cards': alert_cards,
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'prev_date': (target_date - timedelta(days=1)).isoformat(),
        'next_date': (target_date + timedelta(days=1)).isoformat() if target_date < get_yesterday_date() else None
    }
    
    return model


def save_regional_daily_page(target_date: date, region_slug: str, model: Dict) -> int:
    """
    Save/update the regional daily page model to the database.
    Returns the page ID.
    """
    with get_cursor() as cursor:
        cursor.execute("""
            INSERT INTO seo_regional_daily_pages (
                region_slug, page_date, seo_title, seo_description, page_json, 
                alert_count, generated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (region_slug, page_date) DO UPDATE SET
                seo_title = EXCLUDED.seo_title,
                seo_description = EXCLUDED.seo_description,
                page_json = EXCLUDED.page_json,
                alert_count = EXCLUDED.alert_count,
                generated_at = NOW(),
                updated_at = NOW()
            RETURNING id
        """, (
            region_slug,
            target_date,
            model['seo_title'],
            model['seo_description'],
            json.dumps(model),
            model['stats']['total_alerts']
        ))
        result = cursor.fetchone()
        return result['id'] if result else None


def get_regional_daily_page(target_date: date, region_slug: str) -> Optional[Dict]:
    """Retrieve a saved regional daily page model."""
    query = """
    SELECT id, region_slug, page_date, seo_title, seo_description, page_json, 
           alert_count, generated_at, updated_at
    FROM seo_regional_daily_pages
    WHERE page_date = %s AND region_slug = %s
    """
    result = execute_one(query, (target_date, region_slug))
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
            'region_slug': result['region_slug'],
            'page_date': result['page_date'],
            'seo_title': result['seo_title'],
            'seo_description': result['seo_description'],
            'alert_count': result['alert_count'],
            'generated_at': result['generated_at'],
            'model': model
        }
    return None


def get_regional_available_dates(region_slug: str, limit: int = 90) -> List[Dict]:
    """Get list of available dates for a region with alert counts."""
    query = """
    SELECT page_date, alert_count, generated_at
    FROM seo_regional_daily_pages
    WHERE region_slug = %s
    ORDER BY page_date DESC
    LIMIT %s
    """
    results = execute_query(query, (region_slug, limit))
    return results if results else []


def generate_and_save_regional_daily_page(target_date: date, region_slug: str) -> Dict:
    """Generate and save a regional daily page. Returns the model."""
    model = generate_regional_daily_page_model(target_date, region_slug)
    save_regional_daily_page(target_date, region_slug, model)
    logger.info(f"Generated regional daily page for {region_slug} on {target_date}: {model['stats']['total_alerts']} alerts")
    return model
