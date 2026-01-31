"""
EERI Interpretation Generator

Generates AI-powered, professional interpretation for the EERI (European Energy Risk Index).
Uses structured prompting with humanizing tone for 2-3 paragraph outputs.
"""

import os
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

AI_INTEGRATIONS_OPENAI_API_KEY = os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY")
AI_INTEGRATIONS_OPENAI_BASE_URL = os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL")


def generate_eeri_interpretation(
    value: int,
    band: str,
    drivers: List[Dict[str, Any]],
    components: Dict[str, Any],
    index_date: str
) -> str:
    """
    Generate a rich, 2-3 paragraph interpretation for an EERI index.
    
    Args:
        value: EERI value (0-100)
        band: Risk band (LOW, MODERATE, ELEVATED, CRITICAL)
        drivers: List of driver dicts with headline, region, category
        components: Dict of component scores (reri_eu, theme_pressure, asset_transmission, contagion)
        index_date: Date string (YYYY-MM-DD)
    
    Returns:
        A 2-3 paragraph interpretation with professional, humanizing tone.
    """
    if not AI_INTEGRATIONS_OPENAI_API_KEY or not AI_INTEGRATIONS_OPENAI_BASE_URL:
        logger.warning("OpenAI credentials not configured, using fallback interpretation")
        return _fallback_interpretation(value, band, components)
    
    try:
        from openai import OpenAI
        
        client = OpenAI(
            api_key=AI_INTEGRATIONS_OPENAI_API_KEY,
            base_url=AI_INTEGRATIONS_OPENAI_BASE_URL
        )
        
        driver_summaries = []
        for i, d in enumerate(drivers[:5]):
            if isinstance(d, dict):
                headline = d.get('headline', d.get('title', ''))
                region = d.get('region', 'Europe')
                category = d.get('category', 'energy').replace('_', ' ')
                driver_summaries.append(f"{i+1}. [{region}/{category}] {headline}")
            else:
                driver_summaries.append(f"{i+1}. {str(d)}")
        
        drivers_text = "\n".join(driver_summaries) if driver_summaries else "No significant drivers detected"
        
        component_summary = [
            f"RERI-EU (Regional): {components.get('reri_eu', 'N/A')}",
            f"Theme Pressure: {components.get('theme_pressure', 'N/A')}",
            f"Asset Transmission: {components.get('asset_transmission', 'N/A')}",
            f"Contagion Factor: {components.get('contagion', 'N/A')}"
        ]
        components_text = ", ".join(component_summary)
        
        band_context = {
            'LOW': 'conditions are stable with minimal stress signals across European energy infrastructure',
            'MODERATE': 'moderate structural stress is present in European markets, requiring standard monitoring',
            'ELEVATED': 'elevated structural stress with heightened disruption potential in European energy systems',
            'CRITICAL': 'critical structural stress with significant disruption risk to European energy security'
        }
        band_desc = band_context.get(band, 'conditions require monitoring')
        
        prompt = f"""You are a senior energy market analyst writing a detailed risk assessment for professional subscribers. Generate a 2-3 paragraph interpretation of today's European Energy Risk Index (EERI).

INDEX DATA:
- Date: {index_date}
- EERI Value: {value}/100
- Risk Band: {band} ({band_desc})
- Components: {components_text}

TOP DRIVERS:
{drivers_text}

CONTEXT:
The EERI measures structural risk across European energy markets, incorporating regional risk signals, thematic pressures (e.g., supply disruption, geopolitical tension), asset-level transmission stress, and contagion effects from neighboring regions.

WRITING REQUIREMENTS:
1. Write 2-3 substantive paragraphs (not bullet points)
2. First paragraph: Provide the headline assessment - what the index level means for European energy markets today
3. Second paragraph: Explain the key drivers and what's causing the current risk level (or lack thereof)
4. Third paragraph (optional): Offer forward-looking context or what market participants should watch

TONE REQUIREMENTS:
1. Professional but accessible - avoid excessive jargon
2. Humanizing - acknowledge the real-world implications for European energy consumers and industries
3. Balanced - neither alarmist nor dismissive
4. Authoritative - demonstrate expertise without being condescending
5. Do NOT use phrases like "current risk conditions indicate" - be more natural
6. Do NOT mention the exact numerical value repeatedly
7. Use varied sentence structure and avoid bullet points

EXAMPLE STYLE (for reference only, don't copy):
"European energy markets are navigating a period of measured stability today, with structural risk indicators reflecting manageable conditions across the continent's key supply corridors. The overall assessment suggests that Europe's energy infrastructure is functioning within expected parameters, though ongoing vigilance remains essential given the region's complex supply dynamics.

The current risk profile is shaped by relatively stable flows through major transit routes and adequate storage levels heading into seasonal demand shifts. While localized pressure points persist in certain sub-regions, broader systemic stress remains contained for now."

Generate the interpretation:"""

        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": "You are a senior energy market analyst at a respected European risk intelligence firm. Your writing is professional, insightful, and accessible to informed readers."},
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
        
        logger.info(f"Generated EERI interpretation for {index_date}: {interpretation[:80]}...")
        return interpretation
        
    except Exception as e:
        logger.error(f"Error generating AI interpretation for EERI: {e}")
        return _fallback_interpretation(value, band, components)


def _fallback_interpretation(value: int, band: str, components: Dict[str, Any]) -> str:
    """Generate a deterministic fallback interpretation without AI."""
    
    band_templates = {
        'LOW': (
            "European energy markets are operating under stable conditions, with structural risk indicators remaining well within normal parameters. "
            "The continent's energy infrastructure continues to perform as expected, providing a comfortable buffer against potential disruptions."
            "\n\n"
            "Supply flows through established transit routes remain consistent, and storage levels across major European hubs are tracking seasonal expectations. "
            "The overall market environment suggests limited near-term concern, though standard monitoring of geopolitical developments remains prudent."
        ),
        'MODERATE': (
            "European energy markets are experiencing moderate structural stress today, with risk indicators reflecting some pressure points across key regions. "
            "While conditions remain manageable, the current environment warrants continued attention from market participants and policymakers."
            "\n\n"
            "Several factors are contributing to the elevated stress signals, including regional supply dynamics and evolving geopolitical considerations affecting European energy security. "
            "Market observers should monitor developments in affected corridors, though no immediate disruption to European energy flows appears imminent."
        ),
        'ELEVATED': (
            "Risk indicators in European energy markets have risen to elevated levels, signaling meaningful pressure across key supply corridors. "
            "Current conditions suggest emerging vulnerabilities that warrant heightened attention from market participants and European energy stakeholders."
            "\n\n"
            "The elevated stress level reflects a combination of factors affecting transit, storage, or supply dynamics in critical European regions. "
            "While conditions do not yet indicate critical disruption, the trajectory suggests prudent contingency awareness is advisable for energy-dependent industries."
        ),
        'CRITICAL': (
            "European energy markets are under significant structural stress, with risk indicators reflecting critical pressure on supply infrastructure and market stability. "
            "Current conditions demand heightened attention from all market stakeholders, with potential implications for European energy security."
            "\n\n"
            "Multiple stress factors are converging to create challenging conditions across European energy markets, affecting transit corridors, storage dynamics, or supply availability. "
            "The situation warrants active monitoring and consideration of contingency measures by relevant parties across the European energy landscape."
        )
    }
    
    return band_templates.get(band, band_templates['MODERATE'])
