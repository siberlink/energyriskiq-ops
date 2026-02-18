import os
import logging
from typing import Optional, List
from openai import OpenAI

from src.elsa.knowledge_base import (
    load_elsa_knowledge_base, retrieve_relevant_elsa_docs, format_elsa_knowledge
)
from src.elsa.context import build_elsa_context, get_past_elsa_conversations
from src.db.db import get_cursor, execute_one

logger = logging.getLogger(__name__)

ELSA_SYSTEM_PROMPT = """You are ELSA — the Energy Leadership & Strategic Advisor for EnergyRiskIQ.

## Identity
You are a senior marketing strategist, business intelligence expert, and growth advisor for the EnergyRiskIQ platform. You have deep knowledge of SaaS marketing, subscription business models, content strategy, SEO, user acquisition, retention, and energy market positioning.

## Your Knowledge Sources
You have access to:
1. **Product Documentation** — All documents from /docs and /ERIQ directories describing the platform's indices (GERI, EERI, EGSI), features, methodology, and architecture
2. **Production Database** — Live business metrics including user counts, plan distribution, revenue, content metrics, alert volumes, ERIQ bot usage, and SEO data
3. **Past Conversations** — Your previous conversations and insights, allowing you to build on past analyses and track recommendations over time
4. **App Pages** — Understanding of all public-facing pages, dashboards, and user-facing features

## Core Capabilities
1. **Marketing Strategy** — Campaign ideas, positioning, messaging, competitive analysis
2. **Content Strategy** — Blog topics, social media content, email campaigns, SEO content recommendations
3. **User Growth Analysis** — Signup trends, conversion funnel insights, churn indicators, retention strategies
4. **Revenue Intelligence** — Plan performance, upsell opportunities, pricing optimization suggestions
5. **SEO & Discoverability** — Sitemap analysis, keyword suggestions, content gap identification
6. **Product Insights** — Feature adoption analysis, user engagement patterns, feature prioritization input
7. **Competitive Positioning** — How to position EnergyRiskIQ's unique indices and intelligence capabilities
8. **Campaign Planning** — Email marketing, social media, partnerships, and outreach strategies

## Communication Style
- **Strategic and actionable** — Every insight should come with clear next steps
- **Data-driven** — Ground recommendations in the actual business metrics you can see
- **Concise but thorough** — Respect the admin's time while providing sufficient depth
- **Creative** — Bring fresh marketing ideas specific to the energy risk intelligence niche
- **Honest** — If data is insufficient or a strategy is risky, say so clearly

## Response Structure
When analyzing or recommending:
1. **Current State** — What the data shows right now
2. **Opportunity/Challenge** — What this means for growth
3. **Recommendation** — Specific, actionable steps to take
4. **Expected Impact** — What results to expect

## Product Knowledge
- EnergyRiskIQ provides proprietary risk indices: GERI (Global Energy Risk Index), EERI (European Escalation Risk Index), EGSI-M (Market Gas Stress), EGSI-S (System Gas Stress)
- 5 subscription tiers: Free, Personal (€9.90), Trader (€29), Pro (€49), Enterprise (€129)
- Features include AI-powered daily digest, ERIQ analyst bot, real-time dashboards, and automated alerts
- Target audience: Energy traders, risk managers, analysts, hedge funds, utilities, institutional investors

## Guardrails
- Focus on marketing, growth, and business strategy — leave energy risk analysis to ERIQ
- Base recommendations on actual platform data and capabilities
- Be realistic about what the platform can achieve given its current state
- Never expose sensitive user data (names, emails) — only aggregate metrics"""

MAX_RESPONSE_TOKENS = 6000


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
            logger.info("ELSA used GPT-5.1 via direct OpenAI key")
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
        logger.info("ELSA used gpt-4.1-mini via platform proxy")
        return response

    raise RuntimeError("No OpenAI client available for ELSA")


def ask_elsa(question: str, topic_id: int = None, conversation_history: List[dict] = None) -> dict:
    try:
        relevant_docs = retrieve_relevant_elsa_docs(question, top_k=6)
        knowledge_text = format_elsa_knowledge(relevant_docs)
    except Exception as e:
        logger.error(f"ELSA knowledge retrieval failed: {e}")
        knowledge_text = ""

    try:
        context_text = build_elsa_context(question)
    except Exception as e:
        logger.error(f"ELSA context assembly failed: {e}")
        context_text = "Business context unavailable."

    try:
        past_convos = get_past_elsa_conversations(topic_id=topic_id, limit=10)
    except Exception as e:
        logger.error(f"ELSA past conversations failed: {e}")
        past_convos = ""

    if not topic_id:
        try:
            auto_title = question[:60].strip()
            if len(question) > 60:
                auto_title += "..."
            topic = create_topic(auto_title)
            topic_id = topic["id"]
            logger.info(f"ELSA auto-created topic '{auto_title}' (id={topic_id})")
        except Exception as e:
            logger.warning(f"ELSA auto-topic creation failed: {e}")

    messages = [{"role": "system", "content": ELSA_SYSTEM_PROMPT}]

    if knowledge_text:
        messages.append({"role": "system", "content": knowledge_text})

    messages.append({"role": "system", "content": context_text})

    if past_convos:
        messages.append({"role": "system", "content": past_convos})

    if conversation_history:
        for msg in conversation_history[-8:]:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": question})

    try:
        response = _call_model(messages, MAX_RESPONSE_TOKENS)
        choice = response.choices[0]
        answer = (choice.message.content or "").strip()
        tokens_used = response.usage.total_tokens if response.usage else 0

        if not answer:
            answer = "I wasn't able to generate a response. Could you rephrase your question?"

        _save_conversation(topic_id, question, answer, tokens_used)

        return {
            "success": True,
            "response": answer,
            "tokens_used": tokens_used,
            "topic_id": topic_id,
        }

    except Exception as e:
        logger.error(f"ELSA OpenAI call failed: {e}")
        return {
            "success": False,
            "error": "ai_error",
            "message": "ELSA is experiencing a temporary issue. Please try again in a moment.",
        }


def _save_conversation(topic_id: int, question: str, response: str, tokens_used: int):
    try:
        with get_cursor() as cursor:
            cursor.execute("""
                INSERT INTO elsa_conversations (topic_id, question, response, tokens_used)
                VALUES (%s, %s, %s, %s)
            """, (topic_id, question, response, tokens_used))

            if topic_id:
                cursor.execute("""
                    UPDATE elsa_topics SET message_count = message_count + 1, updated_at = NOW()
                    WHERE id = %s
                """, (topic_id,))
    except Exception as e:
        logger.error(f"Failed to save ELSA conversation: {e}")


def create_topic(title: str) -> dict:
    try:
        with get_cursor() as cursor:
            cursor.execute("""
                INSERT INTO elsa_topics (title) VALUES (%s) RETURNING id, title, created_at
            """, (title,))
            row = cursor.fetchone()
            return {"id": row["id"], "title": row["title"], "created_at": row["created_at"].isoformat()}
    except Exception as e:
        logger.error(f"Failed to create ELSA topic: {e}")
        raise


def get_topics(limit: int = 50) -> list:
    from src.db.db import execute_query
    rows = execute_query("""
        SELECT id, title, summary, message_count, created_at, updated_at
        FROM elsa_topics ORDER BY updated_at DESC LIMIT %s
    """, (limit,)) or []
    return [{
        "id": r["id"],
        "title": r["title"],
        "summary": r.get("summary"),
        "message_count": r["message_count"],
        "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
    } for r in rows]


def get_topic_history(topic_id: int, limit: int = 50) -> list:
    from src.db.db import execute_query
    rows = execute_query("""
        SELECT id, question, response, tokens_used, created_at
        FROM elsa_conversations WHERE topic_id = %s ORDER BY created_at ASC LIMIT %s
    """, (topic_id, limit)) or []
    return [{
        "id": r["id"],
        "question": r["question"],
        "response": r["response"],
        "tokens_used": r["tokens_used"],
        "created_at": r["created_at"].isoformat() if r["created_at"] else None,
    } for r in rows]
