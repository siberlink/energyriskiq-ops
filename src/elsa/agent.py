import os
import logging
from typing import Optional, List, Generator
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
3. **Past Conversations (Cross-Topic Memory)** — Your previous conversations from ALL topics, allowing you to build on past analyses, recall strategic decisions, and maintain continuity across different discussion threads
4. **App Pages** — Understanding of all public-facing pages, dashboards, and user-facing features
5. **Uploaded Images** — When the admin shares screenshots, charts, competitor pages, or marketing materials, you can analyze them visually

## Core Capabilities
1. **Marketing Strategy** — Campaign ideas, positioning, messaging, competitive analysis
2. **Content Strategy** — Blog topics, social media content, email campaigns, SEO content recommendations
3. **User Growth Analysis** — Signup trends, conversion funnel insights, churn indicators, retention strategies
4. **Revenue Intelligence** — Plan performance, upsell opportunities, pricing optimization suggestions
5. **SEO & Discoverability** — Sitemap analysis, keyword suggestions, content gap identification
6. **Product Insights** — Feature adoption analysis, user engagement patterns, feature prioritization input
7. **Competitive Positioning** — How to position EnergyRiskIQ's unique indices and intelligence capabilities
8. **Campaign Planning** — Email marketing, social media, partnerships, and outreach strategies
9. **Visual Analysis** — Analyze uploaded screenshots, charts, competitor pages, and marketing materials to provide data-driven insights
10. **Image Generation** — Generate custom marketing images, banners, and social media visuals using DALL-E 3, with platform-specific sizing for LinkedIn, Facebook, X/Twitter, and custom dimensions

## Cross-Topic Memory
You have access to conversations from ALL previous topics, not just the current one. Use this to:
- Reference past recommendations and check if they were followed up on
- Maintain consistency across different strategic discussions
- Connect insights from different areas (e.g., SEO insights informing content strategy)
- Build on previously discussed marketing channel setups when advising on other channels

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

PLATFORM_PRESETS = {
    "linkedin_post": {"name": "LinkedIn Post", "dalle_size": "1024x1024", "display": "1200×1200"},
    "linkedin_banner": {"name": "LinkedIn Banner", "dalle_size": "1792x1024", "display": "1584×396 (generated 1792×1024, crop to fit)"},
    "linkedin_cover": {"name": "LinkedIn Cover", "dalle_size": "1792x1024", "display": "1128×191 (generated 1792×1024, crop to fit)"},
    "facebook_post": {"name": "Facebook Post", "dalle_size": "1792x1024", "display": "1200×630"},
    "facebook_cover": {"name": "Facebook Cover", "dalle_size": "1792x1024", "display": "820×312 (generated 1792×1024, crop to fit)"},
    "twitter_post": {"name": "X/Twitter Post", "dalle_size": "1792x1024", "display": "1600×900"},
    "twitter_header": {"name": "X/Twitter Header", "dalle_size": "1792x1024", "display": "1500×500 (generated 1792×1024, crop to fit)"},
    "square": {"name": "Square (1:1)", "dalle_size": "1024x1024", "display": "1024×1024"},
    "landscape": {"name": "Landscape (16:9)", "dalle_size": "1792x1024", "display": "1792×1024"},
    "portrait": {"name": "Portrait (9:16)", "dalle_size": "1024x1792", "display": "1024×1792"},
    "banner_wide": {"name": "Wide Banner", "dalle_size": "1792x1024", "display": "1792×1024"},
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


def _call_model_stream(messages: list, max_tokens: int) -> Generator:
    direct_client = _get_direct_client()
    if direct_client:
        try:
            stream = direct_client.chat.completions.create(
                model="gpt-5.1",
                messages=messages,
                max_completion_tokens=max_tokens,
                stream=True,
            )
            logger.info("ELSA streaming GPT-5.1 via direct OpenAI key")
            return stream
        except Exception as e:
            logger.warning(f"Direct OpenAI GPT-5.1 streaming failed ({e}), falling back to proxy model")

    proxy_client = _get_proxy_client()
    if proxy_client:
        stream = proxy_client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=messages,
            max_tokens=max_tokens,
            stream=True,
        )
        logger.info("ELSA streaming gpt-4.1-mini via platform proxy")
        return stream

    raise RuntimeError("No OpenAI client available for ELSA")


def _build_messages(question: str, topic_id: int = None, conversation_history: List[dict] = None, image_data: str = None) -> list:
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

    if image_data:
        user_content = [
            {"type": "text", "text": question},
            {"type": "image_url", "image_url": {"url": image_data, "detail": "high"}}
        ]
        messages.append({"role": "user", "content": user_content})
    else:
        messages.append({"role": "user", "content": question})

    return messages


def ask_elsa_stream(question: str, topic_id: int = None, conversation_history: List[dict] = None, image_data: str = None) -> Generator:
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

    yield f"data: {_json_encode({'type': 'topic', 'topic_id': topic_id})}\n\n"

    messages = _build_messages(question, topic_id, conversation_history, image_data)

    try:
        stream = _call_model_stream(messages, MAX_RESPONSE_TOKENS)
        full_response = []

        for chunk in stream:
            if chunk.choices and len(chunk.choices) > 0:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    text = delta.content
                    full_response.append(text)
                    yield f"data: {_json_encode({'type': 'chunk', 'content': text})}\n\n"

        answer = "".join(full_response).strip()
        if not answer:
            answer = "I wasn't able to generate a response. Could you rephrase your question?"

        _save_conversation(topic_id, question, answer, 0)

        yield f"data: {_json_encode({'type': 'done', 'topic_id': topic_id})}\n\n"

    except Exception as e:
        logger.error(f"ELSA streaming failed: {e}")
        yield f"data: {_json_encode({'type': 'error', 'message': 'ELSA is experiencing a temporary issue. Please try again in a moment.'})}\n\n"


def _json_encode(obj: dict) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False)


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


def get_platform_presets() -> dict:
    return PLATFORM_PRESETS


def generate_elsa_image(prompt: str, platform: str = "square", quality: str = "standard", style: str = "vivid") -> dict:
    preset = PLATFORM_PRESETS.get(platform, PLATFORM_PRESETS["square"])
    dalle_size = preset["dalle_size"]

    client = _get_direct_client()
    if not client:
        raise RuntimeError("No OpenAI API key available for image generation. DALL-E requires a direct OpenAI key.")

    enhanced_prompt = (
        f"Professional marketing image for the energy risk intelligence industry. "
        f"Brand: EnergyRiskIQ. {prompt}. "
        f"The image should be clean, modern, professional, and suitable for {preset['name']} use. "
        f"Use a dark blue, purple, and teal color palette where appropriate."
    )

    logger.info(f"ELSA generating image: platform={platform}, size={dalle_size}, quality={quality}")

    try:
        response = client.images.generate(
            model="dall-e-3",
            prompt=enhanced_prompt,
            size=dalle_size,
            quality=quality,
            style=style,
            n=1,
            response_format="url",
        )

        image_url = response.data[0].url
        revised_prompt = response.data[0].revised_prompt

        logger.info(f"ELSA image generated successfully for {preset['name']}")

        return {
            "success": True,
            "image_url": image_url,
            "revised_prompt": revised_prompt,
            "platform": platform,
            "platform_name": preset["name"],
            "size": dalle_size,
            "display_size": preset["display"],
            "quality": quality,
            "style": style,
        }

    except Exception as e:
        logger.error(f"ELSA image generation failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "platform": platform,
            "platform_name": preset["name"],
        }
