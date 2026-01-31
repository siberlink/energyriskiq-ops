"""
Contextual Linking System

Smart linking system that concentrates SEO authority upward:
  Index Pages (GERI / EERI / EGSI)  <- SEO targets
           ↑
  Index History Pages
           ↑
  Alert History Pages

Rules:
- Alert History → Index Pages: 2-3 links MAX (Risk Context block)
- Index History → Index Pages: 1 link (breadcrumb) + 0-1 (alert history footer)
- Index Pages → Alert History: 1-2 links MAX (Recent Risk Drivers section)
- GLOBAL: No duplicate index links per page
"""

from datetime import date, datetime
from typing import List, Dict, Optional, Set
from calendar import month_name

BASE_URL = "https://energyriskiq.com"

INDEX_DEFINITIONS = {
    'geri': {
        'name': 'Global Energy Risk Index (GERI)',
        'short_name': 'GERI',
        'url': '/geri',
        'description': 'global energy market risk',
        'keywords': ['global', 'energy', 'oil', 'crude', 'opec', 'world', 'international'],
    },
    'eeri': {
        'name': 'Europe Energy Risk Index (EERI)',
        'short_name': 'EERI',
        'url': '/eeri',
        'description': 'European energy market risk',
        'keywords': ['europe', 'eu', 'european', 'germany', 'france', 'uk', 'poland', 'norway'],
        'regions': ['europe', 'eu', 'european union', 'western europe', 'eastern europe', 'nordic'],
    },
    'egsi': {
        'name': 'Europe Gas Stress Index (EGSI)',
        'short_name': 'EGSI',
        'url': '/egsi',
        'description': 'European gas market stress',
        'keywords': ['gas', 'lng', 'pipeline', 'transit', 'gazprom', 'nord stream', 'turkstream', 'storage', 'ttf'],
        'categories': ['gas_supply', 'lng_shipping', 'pipeline', 'gas_infrastructure'],
    },
}

BLACK_SEA_REGIONS = ['black sea', 'black-sea', 'ukraine', 'turkey', 'romania', 'bulgaria', 'georgia']


class ContextualLinkBuilder:
    """
    Builds contextual links with deduplication and budget enforcement.
    
    Usage:
        builder = ContextualLinkBuilder()
        links = builder.get_alert_history_index_links(alerts_data)
        html = builder.render_risk_context_block(links)
    """
    
    def __init__(self):
        self._used_links: Set[str] = set()
    
    def reset(self):
        """Reset link tracking for a new page."""
        self._used_links = set()
    
    def _can_use_link(self, index_id: str) -> bool:
        """Check if this link can be used (not already on page)."""
        return index_id not in self._used_links
    
    def _mark_link_used(self, index_id: str):
        """Mark a link as used on this page."""
        self._used_links.add(index_id)
    
    def determine_relevant_indices(
        self,
        regions: Optional[List[str]] = None,
        categories: Optional[List[str]] = None,
        keywords: Optional[List[str]] = None,
        max_links: int = 3
    ) -> List[str]:
        """
        Determine which indices are relevant based on content.
        
        Returns list of index IDs in priority order: ['geri', 'eeri', 'egsi']
        GERI is always included (global baseline).
        """
        relevant = ['geri']
        
        regions = [r.lower() for r in (regions or [])]
        categories = [c.lower() for c in (categories or [])]
        keywords = [k.lower() for k in (keywords or [])]
        
        all_text = ' '.join(regions + categories + keywords)
        
        eeri_match = False
        for region in regions:
            if any(eu_region in region for eu_region in INDEX_DEFINITIONS['eeri'].get('regions', [])):
                eeri_match = True
                break
        
        for kw in INDEX_DEFINITIONS['eeri']['keywords']:
            if kw in all_text:
                eeri_match = True
                break
        
        is_black_sea = any(bs in all_text for bs in BLACK_SEA_REGIONS)
        if is_black_sea:
            eeri_match = True
        
        egsi_match = False
        for cat in categories:
            if any(gc in cat for gc in INDEX_DEFINITIONS['egsi'].get('categories', [])):
                egsi_match = True
                break
        
        for kw in INDEX_DEFINITIONS['egsi']['keywords']:
            if kw in all_text:
                egsi_match = True
                break
        
        if eeri_match and len(relevant) < max_links:
            relevant.append('eeri')
        
        if egsi_match and len(relevant) < max_links:
            relevant.append('egsi')
        
        return relevant[:max_links]
    
    def get_index_link_data(self, index_id: str) -> Optional[Dict]:
        """Get link data for an index if not already used."""
        if not self._can_use_link(index_id):
            return None
        
        defn = INDEX_DEFINITIONS.get(index_id)
        if not defn:
            return None
        
        self._mark_link_used(index_id)
        return {
            'id': index_id,
            'name': defn['name'],
            'short_name': defn['short_name'],
            'url': defn['url'],
            'description': defn['description'],
        }
    
    def render_risk_context_block(
        self,
        index_ids: List[str],
        period_text: str = "this period"
    ) -> str:
        """
        Render the Risk Context block for Alert History pages.
        
        Args:
            index_ids: List of index IDs to link (e.g., ['geri', 'eeri'])
            period_text: Description of the time period (e.g., "January 2026")
        
        Returns:
            HTML string for the Risk Context block
        """
        if not index_ids:
            return ""
        
        links_html = ""
        for idx_id in index_ids:
            link_data = self.get_index_link_data(idx_id)
            if link_data:
                links_html += f'<li><a href="{link_data["url"]}">{link_data["name"]}</a></li>'
        
        if not links_html:
            return ""
        
        return f"""
        <div class="risk-context-block">
            <h3>Risk Context</h3>
            <p>The alerts from {period_text} contributed to readings in:</p>
            <ul class="index-links">
                {links_html}
            </ul>
            <p class="context-note">reflecting energy market and geopolitical stress during this period.</p>
        </div>
        """
    
    def render_recent_drivers_block(
        self,
        drivers: List[str],
        alert_history_url: Optional[str] = None,
        alert_history_label: str = "View recent alerts"
    ) -> str:
        """
        Render the Recent Risk Drivers block for Index pages.
        
        Args:
            drivers: List of driver descriptions (max 5)
            alert_history_url: Optional link to alert history page
            alert_history_label: Label for the alert history link
        
        Returns:
            HTML string for the Recent Risk Drivers block
        """
        if not drivers:
            return ""
        
        drivers_html = ""
        for driver in drivers[:5]:
            drivers_html += f'<li>{driver}</li>'
        
        link_html = ""
        if alert_history_url:
            link_html = f'<a href="{alert_history_url}" class="drivers-link">{alert_history_label} →</a>'
        
        return f"""
        <div class="recent-drivers-block">
            <h3>Recent Risk Drivers</h3>
            <ul class="drivers-list">
                {drivers_html}
            </ul>
            <p class="drivers-source">(Based on recent EnergyRiskIQ alerts)</p>
            {link_html}
        </div>
        """
    
    def render_index_history_footer(
        self,
        main_index_url: str,
        main_index_name: str,
        alert_history_url: Optional[str] = None,
        alert_history_label: Optional[str] = None
    ) -> str:
        """
        Render the footer links for Index History pages.
        
        Args:
            main_index_url: URL to main index page (required)
            main_index_name: Name of the main index
            alert_history_url: Optional URL to related alert history
            alert_history_label: Label for alert history link
        
        Returns:
            HTML string for the footer section
        """
        alert_link_html = ""
        if alert_history_url and alert_history_label:
            alert_link_html = f"""
            <div class="data-sources">
                <h4>Data Sources</h4>
                <p><a href="{alert_history_url}">{alert_history_label}</a></p>
            </div>
            """
        
        return f"""
        <div class="index-history-footer">
            <div class="back-to-index">
                <a href="{main_index_url}">← Back to {main_index_name}</a>
            </div>
            {alert_link_html}
        </div>
        """


def get_risk_context_styles() -> str:
    """Return CSS styles for the Risk Context block."""
    return """
    <style>
        .risk-context-block {
            background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%);
            border-left: 4px solid #0066FF;
            border-radius: 8px;
            padding: 20px 24px;
            margin: 24px 0;
        }
        .risk-context-block h3 {
            font-size: 16px;
            font-weight: 600;
            color: #0f172a;
            margin-bottom: 12px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .risk-context-block h3::before {
            content: "📊";
        }
        .risk-context-block p {
            color: #475569;
            font-size: 14px;
            margin-bottom: 12px;
        }
        .risk-context-block .index-links {
            list-style: none;
            padding: 0;
            margin: 0 0 12px 0;
        }
        .risk-context-block .index-links li {
            padding: 6px 0;
        }
        .risk-context-block .index-links a {
            color: #0066FF;
            text-decoration: none;
            font-weight: 500;
        }
        .risk-context-block .index-links a:hover {
            text-decoration: underline;
        }
        .risk-context-block .context-note {
            font-size: 13px;
            color: #64748b;
            font-style: italic;
            margin-bottom: 0;
        }
        
        .recent-drivers-block {
            background: #f8fafc;
            border-radius: 8px;
            padding: 20px 24px;
            margin: 24px 0;
            border: 1px solid #e2e8f0;
        }
        .recent-drivers-block h3 {
            font-size: 16px;
            font-weight: 600;
            color: #0f172a;
            margin-bottom: 12px;
        }
        .recent-drivers-block .drivers-list {
            list-style: disc;
            padding-left: 20px;
            margin: 0 0 12px 0;
        }
        .recent-drivers-block .drivers-list li {
            color: #334155;
            font-size: 14px;
            padding: 4px 0;
        }
        .recent-drivers-block .drivers-source {
            font-size: 13px;
            color: #64748b;
            font-style: italic;
            margin-bottom: 8px;
        }
        .recent-drivers-block .drivers-link {
            color: #0066FF;
            text-decoration: none;
            font-weight: 500;
            font-size: 14px;
        }
        .recent-drivers-block .drivers-link:hover {
            text-decoration: underline;
        }
        
        .index-history-footer {
            margin-top: 40px;
            padding-top: 24px;
            border-top: 1px solid #e2e8f0;
        }
        .index-history-footer .back-to-index a {
            color: #0066FF;
            text-decoration: none;
            font-weight: 500;
        }
        .index-history-footer .back-to-index a:hover {
            text-decoration: underline;
        }
        .index-history-footer .data-sources {
            margin-top: 16px;
        }
        .index-history-footer .data-sources h4 {
            font-size: 14px;
            font-weight: 600;
            color: #64748b;
            margin-bottom: 8px;
        }
        .index-history-footer .data-sources a {
            color: #0066FF;
            text-decoration: none;
        }
        .index-history-footer .data-sources a:hover {
            text-decoration: underline;
        }
    </style>
    """


def get_alert_month_url(target_date: date) -> str:
    """Get the URL for the alert history month page."""
    return f"/alerts/{target_date.year}/{target_date.month:02d}"


def get_alert_month_label(target_date: date) -> str:
    """Get a human-readable label for an alert history month."""
    return f"{month_name[target_date.month]} {target_date.year} alerts"


def extract_regions_from_alerts(alerts: List[Dict]) -> List[str]:
    """Extract unique regions from a list of alerts."""
    regions = set()
    for alert in alerts:
        region = alert.get('region') or alert.get('primary_region', '')
        if region:
            regions.add(region.lower())
    return list(regions)


def extract_categories_from_alerts(alerts: List[Dict]) -> List[str]:
    """Extract unique categories from a list of alerts."""
    categories = set()
    for alert in alerts:
        category = alert.get('category') or alert.get('event_type', '')
        if category:
            categories.add(category.lower())
    return list(categories)


EGSI_KEYWORDS = ['gas', 'lng', 'pipeline', 'transit', 'gazprom', 'nord stream', 'turkstream', 'storage', 'ttf']
EERI_KEYWORDS = ['europe', 'eu', 'european', 'germany', 'france', 'uk', 'poland', 'norway', 'ukraine', 'russia', 'georgia']


def extract_keywords_from_alerts(alerts: List[Dict]) -> List[str]:
    """Extract relevant keywords from alert titles and content for index matching."""
    keywords = set()
    for alert in alerts:
        text_sources = [
            alert.get('title', ''),
            alert.get('headline', ''),
            alert.get('description', ''),
            alert.get('ai_analysis', ''),
            alert.get('summary', ''),
        ]
        combined_text = ' '.join(str(t) for t in text_sources if t).lower()
        
        for kw in EGSI_KEYWORDS + EERI_KEYWORDS:
            if kw in combined_text:
                keywords.add(kw)
    
    return list(keywords)
