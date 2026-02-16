import os
import json
import logging
from typing import Optional
from openai import OpenAI

from src.eriq.context import (
    build_context, format_context_for_prompt, get_user_plan,
    get_plan_config, get_questions_used_today
)
from src.eriq.knowledge_base import (
    load_knowledge_base, retrieve_relevant_docs, format_knowledge_for_prompt
)
from src.eriq.router import classify_intent, check_mode_access, get_upgrade_message
from src.eriq.tokens import check_can_use, deduct_tokens

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are ERIQ — the Expert Risk Intelligence Analyst for EnergyRiskIQ.

## Identity
You are a senior energy risk analyst with deep expertise in geopolitical risk, energy markets, and quantitative risk intelligence. You are the authoritative voice of the EnergyRiskIQ platform.

## Core Principles
1. **EnergyRiskIQ Expert First** — You are an expert on the EnergyRiskIQ platform, its indices (GERI, EERI, EGSI-M, EGSI-S), methodology, and intelligence outputs. Always explain within the EnergyRiskIQ framework.
2. **Energy & Geopolitical Intelligence Second** — You have deep knowledge of energy markets, geopolitics, and their risk implications.
3. **Evidence-Only Claims** — Every claim must be grounded in the provided context data or knowledge base documents. Never fabricate data points.
4. **No Financial Advice** — Never recommend specific trades, investments, or portfolio allocations. You provide risk intelligence, not financial advice.
5. **"I Don't Know" Policy** — If the data is missing or insufficient, say so clearly. Never guess or hallucinate values.

## Communication Style
- **Professional but accessible** — Write like a senior analyst briefing a sophisticated audience
- **Three-paragraph architecture** when explaining:
  1. Current state (what the data shows)
  2. Context (why it matters, what drove it)
  3. Forward-looking implications (what to watch for)
- **Use precise numbers** from the context data — cite actual index values, trends, asset prices
- **Use risk bands correctly**: GERI and EERI use LOW/MODERATE/ELEVATED/SEVERE/CRITICAL. EGSI uses LOW/NORMAL/ELEVATED/HIGH/CRITICAL.
- **Be concise** — respect the user's time. Quality over quantity.

## Analytical Concepts You Use
- **Spikes**: Sudden, sharp increases in index values
- **Divergences**: When indices or assets move in conflicting directions
- **Regime Classification**: Calm, Moderate, Elevated Uncertainty, Risk Build, Gas-Storage Stress, Shock
- **Momentum**: Direction and acceleration of risk trends
- **Contagion**: Risk spillover from one region/domain to another
- **Correlations**: Statistical relationships between risk indices and assets

## Index Descriptions
- **GERI (Global Energy Risk Index)**: Composite measure of global energy sector risk (0-100). Incorporates geopolitical events, supply disruptions, market stress, and asset volatility with regional weighting.
- **EERI (European Escalation Risk Index)**: Europe-specific energy risk focusing on gas supply security, infrastructure threats, and regional geopolitical tensions (0-100).
- **EGSI-M (Europe Gas Stress Index - Market)**: Measures gas market/transmission stress including TTF price volatility, flow disruptions, and LNG competition (0-100).
- **EGSI-S (Europe Gas Stress Index - System)**: Measures gas storage/refill/winter readiness stress incorporating EU storage levels, injection/withdrawal rates, and seasonal targets (0-100).

## Guardrails
- NEVER provide specific trade recommendations or investment advice
- NEVER fabricate or hallucinate data points — only cite what appears in the context
- NEVER reveal internal scoring formulas, weights, or proprietary algorithms
- NEVER discuss other users' data or preferences
- If asked about something outside your expertise, redirect to EnergyRiskIQ's coverage areas
- Always include a brief disclaimer when discussing market implications: risk intelligence is not financial advice

## Greeting Behavior
When greeted, introduce yourself warmly but professionally. Mention your capabilities relevant to the user's plan tier."""

MODE_PROMPTS = {
    "explain": """## Mode: EXPLAIN
You are in Explain mode. Focus on:
- Defining concepts, indices, and methodology
- Explaining what current readings mean
- Describing what alerts indicate
- Answering "what is" and "how does" questions
Keep explanations clear, educational, and grounded in the knowledge base.""",

    "interpret": """## Mode: INTERPRET
You are in Interpret mode. Focus on:
- Analyzing cross-index relationships and divergences
- Interpreting asset-risk dynamics
- Identifying patterns in historical data
- Explaining regime context and implications
- Providing deeper analytical insights
Ground all interpretations in the provided context data.""",

    "decide_support": """## Mode: DECIDE-SUPPORT
You are in Decision-Support mode. Focus on:
- Scenario analysis ("what if" questions)
- Forward-looking risk implications
- Probability-weighted outlooks
- Multi-factor risk assessment
- Strategic risk positioning insights
Always caveat: this is risk intelligence, not financial advice. Provide frameworks for thinking, not specific recommendations.""",
}

PLAN_DEPTH_PROMPTS = {
    "free": "Provide concise, accessible explanations. Keep responses brief and educational. Data shown is 24-hour delayed.",
    "personal": "Provide real-time analysis with trend context. Include index relationships where relevant.",
    "trader": "Provide detailed analysis with regime context, momentum assessment, and asset sensitivity insights. Include quantitative data points.",
    "pro": "Provide comprehensive institutional-quality analysis with full pillar decomposition, scenario pathways, and cross-index dynamics. Include AI narrative insights.",
    "enterprise": "Provide full institutional intelligence with complete decomposition, multi-scenario analysis, team-relevant framing, and strategic implications.",
}


def _get_direct_client() -> Optional[OpenAI]:
    direct_key = os.environ.get('OPENAI_API_KEY')
    if direct_key:
        return OpenAI(api_key=direct_key)
    return None


def _get_proxy_client() -> Optional[OpenAI]:
    api_key = os.environ.get('AI_INTEGRATIONS_OPENAI_API_KEY')
    base_url = os.environ.get('AI_INTEGRATIONS_OPENAI_BASE_URL')
    if api_key and base_url:
        return OpenAI(api_key=api_key, base_url=base_url)
    return None


def _call_model(messages: list, max_tokens: int):
    direct_client = _get_direct_client()
    if direct_client:
        try:
            response = direct_client.chat.completions.create(
                model="gpt-5.1",
                messages=messages,
                max_completion_tokens=max_tokens,
            )
            logger.info("ERIQ used GPT-5.1 via direct OpenAI key")
            return response
        except Exception as e:
            logger.warning(f"Direct OpenAI GPT-5.1 failed ({e}), falling back to proxy model")

    proxy_client = _get_proxy_client()
    if proxy_client:
        response = proxy_client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=messages,
            max_tokens=max_tokens,
        )
        logger.info("ERIQ used gpt-4.1-mini via platform proxy")
        return response

    raise RuntimeError("No OpenAI client available")


PAGE_CONTEXT_PROMPTS = {
    "geri": """## Page Context: GERI Dashboard
The user is currently viewing the GERI (Global Energy Risk Index) dashboard. They can see the current GERI value, band, trends, pillar breakdown, top drivers, regional distribution, and historical chart. Focus your answers on GERI-specific data, methodology, and what the current readings mean. Reference the specific values and drivers visible on their dashboard when possible.""",
    "eeri": """## Page Context: EERI Dashboard
The user is currently viewing the EERI (European Escalation Risk Index) dashboard. They can see the current EERI value, band, trends, pillar decomposition, weekly snapshots, and historical data. Focus your answers on European energy risk, EERI methodology, and what the current readings mean for European markets. Reference specific EERI values, components, and drivers visible on their dashboard.""",
    "egsi": """## Page Context: EGSI Dashboard
The user is currently viewing the EGSI (Europe Gas Stress Index) dashboard. They can see both EGSI-M (Market/Transmission) and EGSI-S (System/Storage) indices, stress bands, trend data, interpretations, and trader intelligence modules (if their plan allows). Focus your answers on European gas market stress, storage dynamics, TTF price relationships, and what the current EGSI readings indicate. Reference specific EGSI-M and EGSI-S values visible on their dashboard.""",
}


def ask_eriq(user_id: int, question: str, conversation_history: Optional[list] = None, page_context: Optional[str] = None) -> dict:
    plan = get_user_plan(user_id)
    config = get_plan_config(plan)

    questions_used = get_questions_used_today(user_id)
    max_questions = config["max_questions_per_day"]

    if questions_used >= max_questions:
        return {
            "success": False,
            "error": "daily_limit",
            "message": f"You've reached your daily limit of {max_questions} questions. Your quota resets at midnight UTC.",
            "questions_used": questions_used,
            "questions_limit": max_questions,
            "plan": plan,
        }

    can_use, token_status = check_can_use(user_id, plan)
    if not can_use:
        return {
            "success": False,
            "error": "token_limit",
            "message": "You've used all your ERIQ tokens for this month. Purchase additional tokens to continue using ERIQ.",
            "token_status": token_status,
            "plan": plan,
        }

    intent, required_mode, confidence = classify_intent(question)

    if intent == "disallowed":
        return {
            "success": True,
            "response": "I appreciate your interest, but I'm not able to provide specific trade recommendations or investment advice. As a risk intelligence analyst, I can help you understand the current risk environment, explain index movements, and analyze scenarios — but the decision to act is always yours. How can I help you understand the risk landscape instead?",
            "intent": "disallowed",
            "mode": "explain",
            "plan": plan,
            "questions_used": questions_used + 1,
            "questions_limit": max_questions,
            "grounded": True,
        }

    if not check_mode_access(required_mode, config["modes"]):
        upgrade_msg = get_upgrade_message(required_mode, plan)
        effective_mode = config["modes"][-1]
    else:
        upgrade_msg = None
        effective_mode = required_mode

    try:
        ctx = build_context(user_id, plan, question)
    except Exception as e:
        logger.error(f"Failed to build context for user {user_id}: {e}")
        ctx = {
            "timestamp": "",
            "plan": plan,
            "indices": {},
            "alerts": [],
            "assets": {},
            "regime": None,
            "risk_tone": None,
            "correlations": None,
            "betas": None,
            "data_quality": {"overall": "degraded", "issues": ["Context assembly failed"]},
        }

    relevant_docs = retrieve_relevant_docs(question, top_k=4)
    knowledge_text = format_knowledge_for_prompt(relevant_docs)
    context_text = format_context_for_prompt(ctx)

    messages = _build_messages(
        question=question,
        plan=plan,
        mode=effective_mode,
        context_text=context_text,
        knowledge_text=knowledge_text,
        conversation_history=conversation_history,
        page_context=page_context,
    )

    try:
        response = _call_model(messages, config["max_response_tokens"])

        choice = response.choices[0]
        finish_reason = choice.finish_reason
        refusal = getattr(choice.message, 'refusal', None)
        answer = (choice.message.content or "").strip()
        tokens_used = response.usage.total_tokens if response.usage else 0

        if refusal:
            logger.warning(f"ERIQ model refusal: {refusal}")
        if not answer:
            logger.warning(f"ERIQ empty response - finish_reason={finish_reason}, refusal={refusal}, tokens={tokens_used}")
            if refusal:
                answer = "I understand your question, but I need to clarify: I provide risk intelligence and analysis, not specific trading advice. Let me help you understand how our indices can inform your risk awareness instead. Could you rephrase your question in terms of understanding risk?"
            elif finish_reason == "length":
                answer = "My response was too long to complete. Could you ask a more specific question so I can give you a focused answer?"
            else:
                answer = "I wasn't able to generate a response for that question. Could you try rephrasing it? For example, ask about what a specific index measures or what current readings indicate."

        if upgrade_msg:
            answer += f"\n\n---\n*{upgrade_msg}*"

        try:
            deduct_tokens(user_id, tokens_used)
        except Exception as te:
            logger.error(f"Token deduction failed for user {user_id}: {te}")

        updated_token_status = None
        try:
            _, updated_token_status = check_can_use(user_id, plan)
        except Exception:
            pass

        return {
            "success": True,
            "response": answer,
            "intent": intent,
            "mode": effective_mode,
            "plan": plan,
            "questions_used": questions_used + 1,
            "questions_limit": max_questions,
            "tokens_used": tokens_used,
            "token_status": updated_token_status,
            "data_quality": ctx.get("data_quality", {}).get("overall", "unknown"),
            "grounded": True,
            "confidence": confidence,
        }

    except Exception as e:
        logger.error(f"OpenAI call failed for ERIQ: {e}")
        return {
            "success": False,
            "error": "ai_error",
            "message": "I'm experiencing a temporary issue processing your question. Please try again in a moment.",
            "plan": plan,
            "questions_used": questions_used,
            "questions_limit": max_questions,
        }


def _build_messages(question: str, plan: str, mode: str, context_text: str,
                    knowledge_text: str, conversation_history: Optional[list] = None,
                    page_context: Optional[str] = None) -> list:
    system_parts = [SYSTEM_PROMPT]

    if page_context and page_context in PAGE_CONTEXT_PROMPTS:
        system_parts.append(PAGE_CONTEXT_PROMPTS[page_context])

    mode_prompt = MODE_PROMPTS.get(mode, MODE_PROMPTS["explain"])
    system_parts.append(mode_prompt)

    depth_prompt = PLAN_DEPTH_PROMPTS.get(plan, PLAN_DEPTH_PROMPTS["free"])
    system_parts.append(f"\n## Response Depth\n{depth_prompt}")

    system_content = "\n\n".join(system_parts)

    messages = [{"role": "system", "content": system_content}]

    if knowledge_text:
        messages.append({
            "role": "system",
            "content": knowledge_text,
        })

    messages.append({
        "role": "system",
        "content": context_text,
    })

    if conversation_history:
        for msg in conversation_history[-6:]:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": question})

    return messages
