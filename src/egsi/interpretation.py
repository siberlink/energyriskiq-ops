"""
EGSI Interpretation Generator

Generates AI-powered, professional interpretation for the EGSI (Europe Gas Stress Index).
Uses structured prompting with humanizing tone for 2-3 paragraph outputs.
"""

import os
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

AI_INTEGRATIONS_OPENAI_API_KEY = os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY")
AI_INTEGRATIONS_OPENAI_BASE_URL = os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL")


def generate_egsi_interpretation(
    value: int,
    band: str,
    drivers: List[Dict[str, Any]],
    components: Dict[str, Any],
    index_date: str,
    index_type: str = "EGSI-M"
) -> str:
    """
    Generate a rich, 2-3 paragraph interpretation for an EGSI index.
    
    Args:
        value: EGSI value (0-100)
        band: Risk band (LOW, NORMAL, ELEVATED, HIGH, CRITICAL)
        drivers: List of driver dicts with headline, region, category
        components: Dict of component scores
        index_date: Date string (YYYY-MM-DD)
        index_type: Either "EGSI-M" (Market) or "EGSI-S" (System)
    
    Returns:
        A 2-3 paragraph interpretation with professional, humanizing tone.
    """
    if not AI_INTEGRATIONS_OPENAI_API_KEY or not AI_INTEGRATIONS_OPENAI_BASE_URL:
        logger.warning("OpenAI credentials not configured, using fallback interpretation")
        return _fallback_interpretation(value, band, index_type, components)
    
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
                category = d.get('category', 'gas supply').replace('_', ' ')
                driver_summaries.append(f"{i+1}. [{region}/{category}] {headline}")
            else:
                driver_summaries.append(f"{i+1}. {str(d)}")
        
        drivers_text = "\n".join(driver_summaries) if driver_summaries else "No significant drivers detected"
        
        component_summary = []
        if index_type == "EGSI-M":
            component_summary = [
                f"RERI-EU contribution: {components.get('reri_eu', 'N/A')}",
                f"Theme Pressure: {components.get('theme_pressure', 'N/A')}",
                f"Asset Transmission: {components.get('asset_transmission', 'N/A')}",
                f"Chokepoint Factor: {components.get('chokepoint_factor', 'N/A')}"
            ]
        else:
            component_summary = [
                f"Supply Pressure: {components.get('supply_pressure', 'N/A')}",
                f"Transit Stress: {components.get('transit_stress', 'N/A')}",
                f"Storage Stress: {components.get('storage_stress', 'N/A')}",
                f"Price Volatility: {components.get('price_volatility', 'N/A')}",
                f"Policy Risk: {components.get('policy_risk', 'N/A')}"
            ]
        
        components_text = ", ".join(component_summary)
        
        band_context = {
            'LOW': 'conditions are stable with minimal stress signals',
            'NORMAL': 'markets are functioning normally with routine operational considerations',
            'ELEVATED': 'there are early warning signs requiring increased monitoring',
            'HIGH': 'significant stress indicators are present and markets require close attention',
            'CRITICAL': 'severe market stress is evident with potential for supply disruptions'
        }
        band_desc = band_context.get(band, 'conditions require monitoring')
        
        index_desc = "Market/Transmission signal measuring gas market stress" if index_type == "EGSI-M" else "System stress index tracking storage, refill, and winter preparedness"
        
        prompt = f"""You are a senior energy market analyst writing a detailed risk assessment for professional subscribers. Generate a 2-3 paragraph interpretation of today's Europe Gas Stress Index.

INDEX DATA:
- Date: {index_date}
- Index Type: {index_type} ({index_desc})
- EGSI Value: {value}/100
- Risk Band: {band} ({band_desc})
- Components: {components_text}

TOP DRIVERS:
{drivers_text}

WRITING REQUIREMENTS:
1. Write 2-3 substantive paragraphs (not bullet points)
2. First paragraph: Provide the headline assessment - what the index level means for European gas markets today
3. Second paragraph: Explain the key drivers and what's causing the current stress level (or lack thereof)
4. Third paragraph (optional): Offer forward-looking context or what market participants should watch

TONE REQUIREMENTS:
1. Professional but accessible - avoid excessive jargon
2. Humanizing - acknowledge the real-world implications for energy markets and consumers
3. Balanced - neither alarmist nor dismissive
4. Authoritative - demonstrate expertise without being condescending
5. Do NOT use phrases like "current risk conditions indicate" - be more natural
6. Do NOT mention the exact numerical value repeatedly
7. Use varied sentence structure and avoid bullet points

EXAMPLE STYLE (for reference only, don't copy):
"Europe's gas markets are operating under stable conditions today, with stress indicators remaining well within normal parameters. The continent's storage infrastructure continues to perform as expected, providing a comfortable buffer against seasonal demand fluctuations.

Recent weeks have seen consistent supply flows through established transit routes, with no significant disruptions affecting major pipelines. Market participants can take measured confidence from the current operational stability, though the approaching winter season warrants continued vigilance around storage drawdown patterns."

Generate the interpretation:"""

        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": "You are a senior energy market analyst at a respected risk intelligence firm. Your writing is professional, insightful, and accessible to informed readers."},
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
        
        logger.info(f"Generated EGSI interpretation for {index_date}: {interpretation[:80]}...")
        return interpretation
        
    except Exception as e:
        logger.error(f"Error generating AI interpretation for EGSI: {e}")
        return _fallback_interpretation(value, band, index_type, components)


def _fallback_interpretation(value: int, band: str, index_type: str, components: Dict[str, Any]) -> str:
    """Generate a deterministic fallback interpretation without AI."""
    
    band_templates = {
        'LOW': (
            "Europe's gas markets are operating under stable conditions, with stress indicators remaining well within normal parameters. "
            "Current infrastructure capacity and storage levels provide a comfortable operational buffer for market participants."
            "\n\n"
            "Supply flows through established transit routes continue without significant disruption, and storage facilities are performing as expected. "
            "The overall market environment suggests limited near-term concern, though standard seasonal monitoring remains prudent."
        ),
        'NORMAL': (
            "European gas markets are functioning within normal parameters today, with stress indicators showing typical operational patterns. "
            "Market fundamentals remain balanced, with supply adequately meeting current demand requirements."
            "\n\n"
            "Transit flows and storage dynamics are performing as expected for this period. While no immediate concerns are evident, "
            "market participants should maintain awareness of evolving supply-demand dynamics as seasonal factors develop."
        ),
        'ELEVATED': (
            "Stress indicators in European gas markets have risen to elevated levels, signaling the need for increased monitoring. "
            "Current conditions suggest emerging pressure points that warrant attention from market participants and policy observers."
            "\n\n"
            "Several contributing factors are creating upward pressure on the stress index, including supply-side developments and regional demand dynamics. "
            "While conditions do not yet indicate critical disruption, the trajectory suggests prudent contingency awareness is advisable."
        ),
        'HIGH': (
            "European gas markets are experiencing significant stress, with indicators reflecting meaningful pressure across multiple dimensions. "
            "Current conditions require close attention from market participants, with supply security considerations becoming more prominent."
            "\n\n"
            "The elevated stress level reflects a combination of factors affecting transit, storage, or supply dynamics. "
            "Market observers should monitor developments closely, as conditions may evolve and impact both pricing and availability."
        ),
        'CRITICAL': (
            "Europe's gas markets are under severe stress, with indicators reflecting critical pressure on supply infrastructure and market stability. "
            "Current conditions demand heightened attention from all market stakeholders, with potential implications for energy security."
            "\n\n"
            "Multiple stress factors are converging to create challenging market conditions, affecting transit corridors, storage dynamics, or supply availability. "
            "The situation warrants active monitoring and consideration of contingency measures by relevant parties."
        )
    }
    
    return band_templates.get(band, band_templates['NORMAL'])
