import re
import logging
from typing import Tuple

logger = logging.getLogger(__name__)

INTENT_PATTERNS = {
    "methodology": [
        r"\b(what is|how does|how is|explain|define|meaning of|methodology|formula|calculated|computed)\b.*\b(geri|eeri|egsi|index|pillar|component|band|score|risk score)\b",
        r"\b(geri|eeri|egsi)\b.*\b(work|mean|stand for|measure|methodology|formula)\b",
        r"\b(what|how).*\b(band|pillar|component|weight|classification)\b",
    ],
    "explain_today_move": [
        r"\b(why|what happened|what caused|what drove|explain)\b.*\b(today|move|change|spike|drop|jump|fell|rose|increased|decreased)\b",
        r"\b(geri|eeri|egsi)\b.*\b(up|down|rose|fell|spike|drop|move|change)\b",
        r"\b(today|latest|current|now)\b.*\b(reading|value|level|score)\b",
    ],
    "cross_index_compare": [
        r"\b(compare|versus|vs|relationship|between|differ|difference)\b.*\b(geri|eeri|egsi|index|indices)\b",
        r"\b(geri|eeri|egsi)\b.*\b(and|vs|versus|compared to)\b.*\b(geri|eeri|egsi)\b",
        r"\b(diverge|divergence|disconnect|gap)\b.*\b(index|indices|geri|eeri|egsi)\b",
    ],
    "divergence_explain": [
        r"\b(diverge|divergence|disconnect|decouple|mismatch)\b",
        r"\b(risk|index)\b.*\b(disagree|disconnect|opposite|conflict)\b.*\b(asset|market|price)\b",
        r"\b(brent|ttf|vix|storage)\b.*\b(disagree|diverge|opposite)\b.*\b(geri|eeri|egsi)\b",
    ],
    "scenario_explain": [
        r"\b(what if|scenario|hypothetical|suppose|imagine|if.*happens|could.*lead)\b",
        r"\b(escalat|worsen|improve|resolve)\b.*\b(what|how|impact)\b",
        r"\b(forecast|predict|expect|outlook|probability)\b",
    ],
    "asset_impact": [
        r"\b(impact|affect|effect|implication|mean for)\b.*\b(brent|oil|gas|ttf|vix|eurusd|eur\/usd|storage|market|portfolio|trade)\b",
        r"\b(brent|oil|gas|ttf|vix|eurusd|storage)\b.*\b(price|level|outlook|direction)\b",
        r"\b(should i|trade|position|hedge|exposure)\b",
    ],
    "alert_explain": [
        r"\b(alert|event|headline|news)\b.*\b(explain|mean|significant|important|impact)\b",
        r"\b(why|what).*\b(alert|event)\b.*\b(severity|critical|high|important)\b",
        r"\b(latest|recent|top)\b.*\b(alert|event|headline)\b",
    ],
    "regime_explain": [
        r"\b(regime|phase|state|environment|condition)\b.*\b(current|now|today|market)\b",
        r"\b(calm|moderate|elevated|shock|stress)\b.*\b(regime|phase|state)\b",
        r"\b(what regime|which regime|current regime)\b",
    ],
    "greeting": [
        r"^(hi|hello|hey|good morning|good afternoon|good evening|howdy|greetings)\b",
        r"^(who are you|what can you do|help|what are you)\b",
    ],
}

DISALLOWED_PATTERNS = [
    r"\b(buy|sell|long|short|trade recommendation|investment advice|financial advice)\b",
    r"\b(should i invest|recommend.*stock|portfolio allocation|specific trade)\b",
    r"\b(guarantee|promise|certain|definitely will|100%)\b.*\b(price|market|return)\b",
]

MODE_REQUIREMENTS = {
    "explain": ["methodology", "explain_today_move", "alert_explain", "greeting"],
    "interpret": ["cross_index_compare", "divergence_explain", "asset_impact", "regime_explain"],
    "decide_support": ["scenario_explain"],
}


def classify_intent(question: str) -> Tuple[str, str, float]:
    q_lower = question.lower().strip()

    for pattern in DISALLOWED_PATTERNS:
        if re.search(pattern, q_lower):
            return "disallowed", "explain", 0.9

    best_intent = "general"
    best_confidence = 0.0

    for intent, patterns in INTENT_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, q_lower):
                confidence = 0.85
                if intent == "greeting":
                    confidence = 0.95
                if confidence > best_confidence:
                    best_intent = intent
                    best_confidence = confidence

    if best_confidence < 0.5:
        best_intent = "general"
        best_confidence = 0.5

    required_mode = _get_required_mode(best_intent)

    return best_intent, required_mode, best_confidence


def _get_required_mode(intent: str) -> str:
    for mode, intents in MODE_REQUIREMENTS.items():
        if intent in intents:
            return mode
    return "explain"


def check_mode_access(required_mode: str, allowed_modes: list) -> bool:
    return required_mode in allowed_modes


def get_upgrade_message(required_mode: str, current_plan: str) -> str:
    plan_suggestions = {
        "free": {
            "interpret": "Upgrade to Personal to unlock interpretation and cross-index analysis.",
            "decide_support": "Upgrade to Trader to unlock decision-support scenarios and forecasts.",
        },
        "personal": {
            "decide_support": "Upgrade to Trader to unlock decision-support scenarios and forecasts.",
        },
    }
    return plan_suggestions.get(current_plan, {}).get(
        required_mode,
        f"This question requires {required_mode} mode, which is available on higher plan tiers."
    )
