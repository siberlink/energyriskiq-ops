from typing import Dict, List, Optional
from datetime import datetime

def format_regional_risk_spike(
    region: str,
    risk_7d: float,
    prev_risk_7d: Optional[float],
    trend: str,
    driver_events: List[Dict],
    assets: Dict
) -> tuple:
    title = f"Europe Geo-Energy Risk Spike"
    
    change_text = ""
    if prev_risk_7d is not None and prev_risk_7d > 0:
        change_pct = ((risk_7d - prev_risk_7d) / prev_risk_7d) * 100
        if change_pct > 0:
            change_text = f" (+{change_pct:.0f}% vs 24h ago)"
        elif change_pct < 0:
            change_text = f" ({change_pct:.0f}% vs 24h ago)"
    
    message = f"""REGIONAL RISK ALERT: {region}

Current Risk Level: {risk_7d:.0f}/100{change_text}
Trend: {trend.upper()}

KEY DRIVERS:
"""
    
    for i, event in enumerate(driver_events[:3], 1):
        message += f"{i}. {event.get('title', 'Unknown event')[:80]}\n"
        message += f"   Region: {event.get('region', 'Unknown')} | Category: {event.get('category', 'Unknown')}\n"
    
    message += f"\nASSETS LIKELY AFFECTED:\n"
    for asset, data in assets.items():
        direction = data.get('direction', 'unclear')
        risk = data.get('risk', 0)
        arrow = "up" if direction in ['up', 'risk_off'] else ("down" if direction == 'down' else "~")
        message += f"  {asset.upper()}: {risk:.0f}/100 ({arrow})\n"
    
    message += "\n---\nInformational only. Not financial advice."
    
    return title, message


def format_asset_risk_spike(
    asset: str,
    region: str,
    risk_score: float,
    direction: str,
    confidence: float,
    driver_events: List[Dict]
) -> tuple:
    title = f"{asset.upper()} Risk Rising in {region}"
    
    direction_text = direction.upper()
    if asset == 'fx':
        if direction in ['risk_off', 'down']:
            direction_text = "RISK-OFF (bearish)"
        elif direction in ['risk_on', 'up']:
            direction_text = "RISK-ON (bullish)"
    
    message = f"""ASSET RISK ALERT: {asset.upper()}

Region: {region}
Risk Score: {risk_score:.0f}/100
Direction: {direction_text}
Confidence: {confidence:.0%}

KEY DRIVERS:
"""
    
    for i, event in enumerate(driver_events[:2], 1):
        message += f"{i}. {event.get('title', 'Unknown event')[:80]}\n"
    
    message += "\n---\nInformational only. Not financial advice."
    
    return title, message


def format_high_impact_event(
    event: Dict,
    region: str
) -> tuple:
    title = f"High-Impact Event Detected ({region})"
    
    severity = event.get('severity_score', 0)
    event_title = event.get('title', 'Unknown event')
    ai_summary = event.get('ai_summary', '')
    source_url = event.get('source_url', '')
    category = event.get('category', 'Unknown')
    
    message = f"""HIGH-IMPACT EVENT ALERT

Event: {event_title}
Severity: {severity}/5
Category: {category.upper()}
Region: {region}
"""
    
    if ai_summary:
        message += f"\nAI Analysis:\n{ai_summary[:300]}"
    
    if source_url:
        message += f"\n\nSource: {source_url}"
    
    message += "\n\n---\nInformational only. Not financial advice."
    
    return title, message


def format_daily_digest(
    region: str,
    risk_7d: float,
    risk_30d: float,
    trend: str,
    assets: Dict,
    top_events: List[Dict],
    date_str: str
) -> tuple:
    title = f"Daily Risk Digest - {region} ({date_str})"
    
    message = f"""DAILY RISK DIGEST: {region}
{date_str}

RISK OVERVIEW
7-Day Risk: {risk_7d:.0f}/100 ({trend})
30-Day Risk: {risk_30d:.0f}/100

ASSET RISK SUMMARY
"""
    
    for asset, data in assets.items():
        direction = data.get('direction', 'unclear')
        risk = data.get('risk', 0)
        message += f"  {asset.upper()}: {risk:.0f}/100 ({direction})\n"
    
    message += f"\nTOP EVENTS TODAY\n"
    for i, event in enumerate(top_events[:5], 1):
        message += f"{i}. {event.get('title', 'Unknown')[:70]}...\n"
    
    message += "\n---\nInformational only. Not financial advice."
    
    return title, message


def generate_sample_alerts() -> List[Dict]:
    samples = []
    
    title, msg = format_regional_risk_spike(
        region="Europe",
        risk_7d=78,
        prev_risk_7d=62,
        trend="rising",
        driver_events=[
            {"title": "OPEC+ announces surprise production cuts", "region": "Middle East", "category": "energy"},
            {"title": "Baltic Sea shipping disrupted by naval exercises", "region": "Europe", "category": "supply_chain"},
            {"title": "Natural gas storage levels drop below seasonal average", "region": "Europe", "category": "energy"}
        ],
        assets={
            "oil": {"risk": 82, "direction": "up"},
            "gas": {"risk": 85, "direction": "up"},
            "fx": {"risk": 65, "direction": "risk_off"},
            "freight": {"risk": 70, "direction": "up"}
        }
    )
    samples.append({"type": "REGIONAL_RISK_SPIKE", "title": title, "message": msg})
    
    title, msg = format_asset_risk_spike(
        asset="gas",
        region="Europe",
        risk_score=85,
        direction="up",
        confidence=0.78,
        driver_events=[
            {"title": "LNG terminal maintenance extends through winter"},
            {"title": "Cold snap forecast across Northern Europe"}
        ]
    )
    samples.append({"type": "ASSET_RISK_SPIKE", "title": title, "message": msg})
    
    title, msg = format_high_impact_event(
        event={
            "title": "Major pipeline explosion disrupts gas flows to Central Europe",
            "severity_score": 5,
            "category": "energy",
            "ai_summary": "A significant explosion has occurred on a major natural gas pipeline serving Central European markets. Initial reports indicate substantial damage that may take weeks to repair. This represents a critical supply disruption with potential for price spikes.",
            "source_url": "https://example.com/breaking-news"
        },
        region="Europe"
    )
    samples.append({"type": "HIGH_IMPACT_EVENT", "title": title, "message": msg})
    
    return samples


LANDING_COPY = {
    "hero": "Real-Time Energy Risk Intelligence for Traders & Operators",
    "subhero": "AI-powered alerts that tell you when Europe's energy markets are about to move. Before they move.",
    "bullets": [
        "Get instant alerts when regional risk levels spike above your thresholds",
        "Track oil, gas, FX, and freight risk signals in real-time",
        "AI-enriched event analysis with market impact predictions"
    ],
    "example_alerts": [
        "Europe Geo-Energy Risk Spike: Risk at 78/100 (+26% in 24h). OPEC+ cuts + Baltic disruption driving oil & gas higher.",
        "GAS Risk Rising in Europe: 85/100 (UP). LNG maintenance + cold snap forecast.",
        "High-Impact Event: Major pipeline explosion disrupts gas flows to Central Europe (Severity 5/5)"
    ],
    "cta": "Start Free - Get Europe Risk Alerts Now",
    "cta_upgrade": "Upgrade to Trader for Real-Time Asset Alerts",
    "disclaimer": "EnergyRiskIQ provides informational risk indicators only. This is not investment advice. Always conduct your own research and consult qualified professionals before making trading or business decisions."
}
