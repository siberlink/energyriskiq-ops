"""Version context only: no changes to editorial instructions or scoring."""
INACTIVE_NOTE = (
    "Regional-spike (25%) and asset-risk (20%) components currently contribute little "
    "or nothing while the upstream risk pipeline is rebuilt. Describe them as inactive, "
    "not as active risk drivers. GERI currently reflects mainly high-impact events and concentration."
)


def interpretation_context(components, version="v1.2"):
    return {"methodology_version": version, "model_version": "geri_"+version,
            "inactive_component_note": INACTIVE_NOTE if version == "v1.2" else None,
            "components": components}
