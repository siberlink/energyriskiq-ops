"""Narrative evidence only. Never changes scoring or selectors."""
INACTIVE_NOTE = (
    "Methodology constraint: the regional-spike and asset-risk components are inactive "
    "methodology components, not observations of low or absent market risk. Do not describe "
    "them as muted, quiet, low, contributing little, temporarily inactive, or capable of "
    "reactivation because market events change. Their inactive status is not evidence of "
    "stable markets, resilient infrastructure, absent spillover, or low asset exposure. "
    "Discuss the selected index's contributing signals and the supplied event evidence only. "
    "Any future activation requires an explicit methodology/pipeline change; do not predict "
    "it or imply that headlines can activate these components. Do not request or invent a "
    "component breakdown. Regional names in event headlines identify event geography and "
    "do not establish an active regional-spike component."
)


def interpretation_context(components, version="v1.2"):
    if version == "v1.2":
        evidence = {k: components[k] for k in (
            "high_impact_score", "region_concentration_score_raw", "high_impact_events",
            "total_alerts", "top_drivers", "top_regions") if k in components}
        return {
            "methodology_version": version, "model_version": "geri_v1.2",
            "inactive_component_note": INACTIVE_NOTE,
            "component_status": {
                "regional_spike": "inactive_methodology_component",
                "asset_risk": "inactive_methodology_component"},
            "narrative_rules": {
                "inactive_status_is_market_evidence": False,
                "market_events_can_reactivate_components": False,
                "request_component_breakdown": False},
            "components": evidence}
    return {"methodology_version": version, "model_version": "geri_"+version,
            "inactive_component_note": INACTIVE_NOTE if version == "v1.2" else None,
            "components": components}
