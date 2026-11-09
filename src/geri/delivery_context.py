"""Read/prompt policy for standalone delivery workers; no sends or DB writes."""
import json

from src.geri.model_selection import published_model, read_sql
from src.geri.narrative_context import interpretation_context, INACTIVE_NOTE


def selected_query(query):
    """Ops uses ordinary cursors, so explicitly select at the delivery boundary."""
    return read_sql(query)


def delivery_context(observation=None):
    observation = observation or {}
    context = interpretation_context({}, version=published_model())
    context.update(value=observation.get("value"),
                   observation_date=str(observation.get("date") or "unavailable"))
    return context


def prompt_context(observation=None):
    return (
        "\nGERI METHODOLOGY CONTEXT: "
        + json.dumps(delivery_context(observation), default=str)
        + "\nDiscuss the observed index level, direction and supplied events only. "
        "Do not invent or provide a breakdown into components, pillar attribution "
        "or contribution percentages. Regional and asset market context is not "
        "evidence of an active GERI component. Respect the inactive-component note."
    )


def methodology_note():
    version = published_model()
    note = f"GERI methodology {version}."
    # Keep the approved meaning without displaying an instruction to the LLM.
    public_note = INACTIVE_NOTE.replace(
        "Describe them as inactive, not as active risk drivers.",
        "These components are currently inactive, not active risk drivers.")
    return note + (" " + public_note if version == "v1.2" else "")


def narrative_cache_key(key):
    # Match the website namespace without importing its admin-preview machinery.
    return key if published_model() == "v1.1" else key + ":geri_v1.2"
