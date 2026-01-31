"""
GERI Interpretation Generator

Generates AI-powered, professional interpretation for the GERI (Global Energy Risk Index).
Uses structured prompting with humanizing tone for 2-3 paragraph outputs.
"""

import os
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

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
    Generate a rich, 2-3 paragraph interpretation for a GERI index.
    
    Args:
        value: GERI value (0-100)
        band: Risk band (LOW, MODERATE, ELEVATED, CRITICAL)
        top_drivers: List of driver dicts with headline, region, category
        top_regions: List of top region names
        index_date: Date string (YYYY-MM-DD)
    
    Returns:
        A 2-3 paragraph interpretation with professional, humanizing tone.
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
        
        drivers_text = "\n".join(driver_summaries) if driver_summaries else "No significant drivers detected"
        regions_text = ", ".join(top_regions[:3]) if top_regions else "global markets"
        
        band_descriptions = {
            'LOW': 'conditions are stable with minimal risk signals across global energy markets',
            'MODERATE': 'moderate structural stress is present, requiring standard monitoring',
            'ELEVATED': 'elevated structural stress with heightened disruption potential across key regions',
            'CRITICAL': 'critical structural stress with significant market disruption underway or imminent'
        }
        band_desc = band_descriptions.get(band, 'conditions require monitoring')
        
        prompt = f"""You are a senior energy market analyst writing a detailed risk assessment for professional subscribers. Generate a 2-3 paragraph interpretation of today's Global Energy Risk Index.

INDEX DATA:
- Date: {index_date}
- GERI Value: {value}/100
- Risk Band: {band} ({band_desc})
- Top Affected Regions: {regions_text}

TOP DRIVERS:
{drivers_text}

WRITING REQUIREMENTS:
1. Write 2-3 substantive paragraphs (not bullet points)
2. First paragraph: Provide the headline assessment - what the index level means for global energy markets today
3. Second paragraph: Explain the key drivers and what's causing the current risk level (or lack thereof)
4. Third paragraph (optional): Offer forward-looking context or what market participants should watch

TONE REQUIREMENTS:
1. Professional but accessible - avoid excessive jargon
2. Humanizing - acknowledge the real-world implications for energy markets and economies
3. Balanced - neither alarmist nor dismissive
4. Authoritative - demonstrate expertise without being condescending
5. Do NOT use phrases like "current risk conditions indicate" - be more natural
6. Do NOT mention the exact numerical value repeatedly
7. Use varied sentence structure and avoid bullet points

EXAMPLE STYLE (for reference only, don't copy):
"Global energy markets are experiencing a period of relative stability today, with risk indicators reflecting manageable stress levels across major supply corridors. The overall picture suggests that energy infrastructure and supply chains are functioning within normal parameters, providing some reassurance to market participants and policymakers alike.

Several factors are contributing to this measured outlook. Supply flows from key producing regions remain consistent, while demand patterns across major consuming economies continue to track seasonal expectations. There are no acute disruption events currently affecting critical infrastructure, though localized concerns in certain regions warrant ongoing attention."

Generate the interpretation:"""

        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": "You are a senior energy market analyst at a respected global risk intelligence firm. Your writing is professional, insightful, and accessible to informed readers."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=500,
            temperature=0.4
        )
        
        interpretation = response.choices[0].message.content.strip()
        interpretation = interpretation.strip('"\'')
        
        if len(interpretation) > 1500:
            last_period = interpretation[:1500].rfind('.')
            if last_period > 0:
                interpretation = interpretation[:last_period + 1]
        
        logger.info(f"Generated GERI interpretation for {index_date}: {interpretation[:80]}...")
        return interpretation
        
    except Exception as e:
        logger.error(f"Error generating AI interpretation for GERI: {e}")
        return _fallback_interpretation(value, band, top_regions)


def _fallback_interpretation(value: int, band: str, top_regions: List[str]) -> str:
    """Generate a deterministic fallback interpretation without AI."""
    regions_text = " and ".join(top_regions[:2]) if top_regions else "global markets"
    
    templates = {
        'LOW': (
            "Global energy markets are operating under stable conditions, with risk indicators remaining well within normal parameters. "
            "Current infrastructure capacity and supply flows provide a comfortable operational buffer for market participants worldwide."
            "\n\n"
            "Supply from major producing regions continues without significant disruption, while demand patterns across key consuming economies track seasonal expectations. "
            "The overall market environment suggests limited near-term concern, though standard geopolitical and seasonal monitoring remains prudent."
        ),
        'MODERATE': (
            f"Global energy markets are experiencing moderate structural stress today, with risk indicators reflecting some pressure points across {regions_text}. "
            "While conditions remain manageable, the current environment warrants continued attention from market participants."
            "\n\n"
            "Several factors are contributing to the elevated stress signals, including regional supply dynamics and evolving geopolitical considerations. "
            "Market observers should monitor developments in affected regions, though no immediate disruption to global energy flows appears imminent."
        ),
        'ELEVATED': (
            f"Risk indicators in global energy markets have risen to elevated levels, signaling meaningful pressure across {regions_text}. "
            "Current conditions suggest emerging vulnerabilities that warrant heightened attention from market participants and policymakers."
            "\n\n"
            "The elevated stress level reflects a combination of factors affecting supply, transit, or demand dynamics in key regions. "
            "While conditions do not yet indicate critical disruption, the trajectory suggests prudent contingency awareness is advisable for energy-dependent operations."
        ),
        'CRITICAL': (
            f"Global energy markets are under significant stress, with risk indicators reflecting critical pressure affecting {regions_text}. "
            "Current conditions demand heightened attention from all market stakeholders, with potential implications for energy security and pricing."
            "\n\n"
            "Multiple stress factors are converging to create challenging market conditions, affecting supply availability, transit corridors, or critical infrastructure. "
            "The situation warrants active monitoring and consideration of contingency measures by relevant parties across the energy value chain."
        )
    }
    
    return templates.get(band, templates['MODERATE'])
