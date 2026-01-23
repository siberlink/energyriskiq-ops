"""
GERI Interpretation Generator

Generates AI-powered, quote-ready interpretation sentences for each GERI index.
Uses structured prompting with governance rules for deterministic, safe outputs.
"""

import os
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# the newest OpenAI model is "gpt-4.1-mini" for cost-effective interpretation
# do not change this unless explicitly requested by the user
AI_INTEGRATIONS_OPENAI_API_KEY = os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY")
AI_INTEGRATIONS_OPENAI_BASE_URL = os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL")


def generate_interpretation(
    value: int,
    band: str,
    top_drivers: List[Dict[str, Any]],
    top_regions: List[str],
    index_date: str
) -> str:
    """
    Generate a structured, quote-ready interpretation for a GERI index.
    
    Args:
        value: GERI value (0-100)
        band: Risk band (LOW, MODERATE, ELEVATED, CRITICAL)
        top_drivers: List of driver dicts with headline, region, category
        top_regions: List of top region names
        index_date: Date string (YYYY-MM-DD)
    
    Returns:
        A single-sentence interpretation suitable for quoting.
    """
    if not AI_INTEGRATIONS_OPENAI_API_KEY or not AI_INTEGRATIONS_OPENAI_BASE_URL:
        logger.warning("OpenAI credentials not configured, using fallback interpretation")
        return _fallback_interpretation(value, band, top_regions)
    
    try:
        from openai import OpenAI
        
        client = OpenAI(
            api_key=AI_INTEGRATIONS_OPENAI_API_KEY,
            base_url=AI_INTEGRATIONS_OPENAI_BASE_URL
        )
        
        driver_summaries = []
        for i, d in enumerate(top_drivers[:5]):
            headline = d.get('headline', '')
            region = d.get('region', 'Unknown')
            category = d.get('category', 'unknown').replace('_', ' ')
            driver_summaries.append(f"{i+1}. [{region}/{category}] {headline}")
        
        drivers_text = "\n".join(driver_summaries) if driver_summaries else "No significant drivers"
        regions_text = ", ".join(top_regions[:3]) if top_regions else "global markets"
        
        band_descriptions = {
            'LOW': 'low structural stress with limited disruption risk',
            'MODERATE': 'moderate structural stress requiring monitoring',
            'ELEVATED': 'elevated structural stress with heightened disruption potential',
            'CRITICAL': 'critical structural stress with significant market disruption underway'
        }
        band_desc = band_descriptions.get(band, 'uncertain conditions')
        
        prompt = f"""You are an energy market analyst writing a daily risk briefing. Generate ONE sentence (max 40 words) summarizing today's Global Energy Risk Index.

INDEX DATA:
- Date: {index_date}
- GERI Value: {value}/100
- Risk Band: {band}
- Top Regions: {regions_text}

TOP DRIVERS:
{drivers_text}

REQUIREMENTS:
1. Start with "Current risk conditions indicate..." or "Today's index reflects..."
2. Reference the risk level ({band.lower()}) naturally
3. Mention 1-2 specific regions if relevant
4. If drivers show a theme (war, supply disruption, sanctions), reference it briefly
5. Be factual, not sensational
6. Suitable for journalists to quote
7. Do NOT mention the numerical value
8. Do NOT use jargon like "geopolitical risk vectors"

EXAMPLE OUTPUT:
"Current risk conditions indicate moderate structural stress in global energy markets, with supply-side pressure concentrated in Europe amid ongoing regional tensions."

Generate the interpretation:"""

        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": "You are a professional energy market analyst. Write concise, factual, quote-ready briefings."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=100,
            temperature=0.3
        )
        
        interpretation = response.choices[0].message.content.strip()
        
        interpretation = interpretation.strip('"\'')
        
        if len(interpretation) > 300:
            interpretation = interpretation[:300].rsplit(' ', 1)[0] + '.'
        
        if not interpretation.endswith('.'):
            interpretation += '.'
        
        logger.info(f"Generated interpretation for {index_date}: {interpretation[:50]}...")
        return interpretation
        
    except Exception as e:
        logger.error(f"Error generating AI interpretation: {e}")
        return _fallback_interpretation(value, band, top_regions)


def _fallback_interpretation(value: int, band: str, top_regions: List[str]) -> str:
    """Generate a deterministic fallback interpretation without AI."""
    regions_text = " and ".join(top_regions[:2]) if top_regions else "global markets"
    
    templates = {
        'LOW': f"Current risk conditions indicate low structural stress in global energy markets, with minimal disruption signals across major regions.",
        'MODERATE': f"Current risk conditions indicate moderate structural stress in global energy markets, with pressure concentrated in {regions_text}.",
        'ELEVATED': f"Current risk conditions indicate elevated structural stress in global energy markets, with significant pressure building across {regions_text}.",
        'CRITICAL': f"Current risk conditions indicate critical structural stress in global energy markets, with active disruption events affecting {regions_text}."
    }
    
    return templates.get(band, templates['MODERATE'])
