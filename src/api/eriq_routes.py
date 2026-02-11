import logging
import os
from datetime import date
from fastapi import APIRouter, Header, HTTPException
from typing import Optional, List
from pydantic import BaseModel

from src.api.user_routes import verify_user_session
from src.eriq.agent import ask_eriq
from src.eriq.context import get_user_plan, get_plan_config, get_questions_used_today
from src.eriq.knowledge_base import load_knowledge_base
from src.db.db import get_cursor, execute_query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/eriq", tags=["eriq"])

VALID_FEEDBACK_TAGS = [
    "helpful", "not_helpful", "inaccurate", "too_vague", "too_technical",
    "missing_context", "excellent_analysis", "wrong_data", "outdated",
    "needs_more_detail", "good_explanation", "confusing",
]


class EriqAskRequest(BaseModel):
    question: str
    conversation_history: Optional[List[dict]] = None


class EriqFeedbackRequest(BaseModel):
    conversation_id: int
    rating: int
    comment: Optional[str] = None
    tags: Optional[List[str]] = None


@router.on_event("startup")
async def eriq_startup():
    try:
        load_knowledge_base()
        logger.info("ERIQ knowledge base loaded on startup")
    except Exception as e:
        logger.warning(f"ERIQ knowledge base preload failed (will lazy-load): {e}")


@router.post("/ask")
def eriq_ask(body: EriqAskRequest, x_user_token: Optional[str] = Header(None)):
    session = verify_user_session(x_user_token)
    user_id = session["user_id"]
    question = body.question.strip()

    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    if len(question) > 2000:
        raise HTTPException(status_code=400, detail="Question is too long (max 2000 characters)")

    result = ask_eriq(
        user_id=user_id,
        question=question,
        conversation_history=body.conversation_history,
    )

    try:
        _log_conversation(
            user_id=user_id,
            question=question,
            response=result.get("response", result.get("message", "")),
            intent=result.get("intent", "unknown"),
            mode=result.get("mode", "explain"),
            plan=result.get("plan", "free"),
            tokens_used=result.get("tokens_used", 0),
            rating=None,
            success=result.get("success", False),
        )
    except Exception as e:
        logger.error(f"Failed to log ERIQ conversation: {e}")

    return result


@router.get("/status")
def eriq_status(x_user_token: Optional[str] = Header(None)):
    session = verify_user_session(x_user_token)
    user_id = session["user_id"]
    plan = get_user_plan(user_id)
    config = get_plan_config(plan)
    questions_used = get_questions_used_today(user_id)

    return {
        "plan": plan,
        "questions_used": questions_used,
        "questions_limit": config["max_questions_per_day"],
        "questions_remaining": max(0, config["max_questions_per_day"] - questions_used),
        "modes": config["modes"],
        "features": {
            "pillars": config["show_pillars"],
            "drivers": config["show_drivers"],
            "regime": config["show_regime"],
            "correlations": config["show_correlations"],
            "betas": config["show_betas"],
        },
    }


@router.post("/feedback")
def eriq_feedback(body: EriqFeedbackRequest, x_user_token: Optional[str] = Header(None)):
    session = verify_user_session(x_user_token)
    user_id = session["user_id"]

    if body.rating < 1 or body.rating > 5:
        raise HTTPException(status_code=400, detail="Rating must be between 1 and 5")

    validated_tags = []
    if body.tags:
        validated_tags = [t for t in body.tags if t in VALID_FEEDBACK_TAGS]

    try:
        with get_cursor() as cursor:
            cursor.execute("""
                UPDATE eriq_conversations
                SET rating = %s, feedback_comment = %s, feedback_tags = %s
                WHERE id = %s AND user_id = %s
            """, (body.rating, body.comment, validated_tags, body.conversation_id, user_id))
        return {"success": True, "message": "Thank you for your feedback"}
    except Exception as e:
        logger.error(f"Failed to save ERIQ feedback: {e}")
        raise HTTPException(status_code=500, detail="Failed to save feedback")


@router.get("/history")
def eriq_history(x_user_token: Optional[str] = Header(None), limit: int = 20):
    session = verify_user_session(x_user_token)
    user_id = session["user_id"]

    rows = execute_query("""
        SELECT id, question, response, intent, mode, created_at, rating, feedback_tags
        FROM eriq_conversations
        WHERE user_id = %s AND success = true
        ORDER BY created_at DESC
        LIMIT %s
    """, (user_id, min(limit, 50)))

    if not rows:
        return {"conversations": []}

    return {
        "conversations": [
            {
                "id": r["id"],
                "question": r["question"],
                "response": r["response"],
                "intent": r["intent"],
                "mode": r["mode"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "rating": r["rating"],
                "feedback_tags": r.get("feedback_tags", []),
            }
            for r in rows
        ]
    }


@router.get("/analytics")
def eriq_analytics(x_internal_token: Optional[str] = Header(None)):
    expected_token = os.environ.get("INTERNAL_RUNNER_TOKEN", "")
    if not expected_token or x_internal_token != expected_token:
        raise HTTPException(status_code=403, detail="Unauthorized")

    analytics = {}

    top_questions = execute_query("""
        SELECT question, intent, COUNT(*) as ask_count
        FROM eriq_conversations
        WHERE success = true AND created_at > NOW() - INTERVAL '30 days'
        GROUP BY question, intent
        ORDER BY ask_count DESC
        LIMIT 20
    """)
    analytics["top_questions"] = [
        {"question": r["question"], "intent": r["intent"], "count": r["ask_count"]}
        for r in (top_questions or [])
    ]

    low_satisfaction = execute_query("""
        SELECT id, question, response, intent, mode, plan, rating,
               feedback_comment, feedback_tags, created_at
        FROM eriq_conversations
        WHERE rating IS NOT NULL AND rating <= 2
              AND created_at > NOW() - INTERVAL '30 days'
        ORDER BY created_at DESC
        LIMIT 20
    """)
    analytics["low_satisfaction_responses"] = [
        {
            "id": r["id"],
            "question": r["question"],
            "intent": r["intent"],
            "mode": r["mode"],
            "plan": r["plan"],
            "rating": r["rating"],
            "comment": r.get("feedback_comment"),
            "tags": r.get("feedback_tags", []),
            "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
        }
        for r in (low_satisfaction or [])
    ]

    intent_distribution = execute_query("""
        SELECT intent, mode, COUNT(*) as count,
               ROUND(AVG(CASE WHEN rating IS NOT NULL THEN rating END)::numeric, 2) as avg_rating,
               COUNT(CASE WHEN rating IS NOT NULL THEN 1 END) as rated_count,
               COUNT(CASE WHEN success = false THEN 1 END) as fail_count
        FROM eriq_conversations
        WHERE created_at > NOW() - INTERVAL '30 days'
        GROUP BY intent, mode
        ORDER BY count DESC
    """)
    analytics["intent_distribution"] = [
        {
            "intent": r["intent"],
            "mode": r["mode"],
            "count": r["count"],
            "avg_rating": float(r["avg_rating"]) if r.get("avg_rating") else None,
            "rated_count": r["rated_count"],
            "fail_count": r["fail_count"],
        }
        for r in (intent_distribution or [])
    ]

    plan_usage = execute_query("""
        SELECT plan, COUNT(*) as total_questions,
               COUNT(DISTINCT user_id) as unique_users,
               ROUND(AVG(tokens_used)::numeric, 0) as avg_tokens,
               ROUND(AVG(CASE WHEN rating IS NOT NULL THEN rating END)::numeric, 2) as avg_rating,
               COUNT(CASE WHEN success = false THEN 1 END) as failures
        FROM eriq_conversations
        WHERE created_at > NOW() - INTERVAL '30 days'
        GROUP BY plan
        ORDER BY total_questions DESC
    """)
    analytics["plan_usage"] = [
        {
            "plan": r["plan"],
            "total_questions": r["total_questions"],
            "unique_users": r["unique_users"],
            "avg_tokens": int(r["avg_tokens"]) if r.get("avg_tokens") else 0,
            "avg_rating": float(r["avg_rating"]) if r.get("avg_rating") else None,
            "failures": r["failures"],
        }
        for r in (plan_usage or [])
    ]

    tag_distribution = execute_query("""
        SELECT unnest(feedback_tags) as tag, COUNT(*) as count
        FROM eriq_conversations
        WHERE feedback_tags IS NOT NULL AND feedback_tags != '{}'
              AND created_at > NOW() - INTERVAL '30 days'
        GROUP BY tag
        ORDER BY count DESC
    """)
    analytics["feedback_tag_distribution"] = [
        {"tag": r["tag"], "count": r["count"]}
        for r in (tag_distribution or [])
    ]

    daily_volume = execute_query("""
        SELECT DATE(created_at) as day, COUNT(*) as questions,
               COUNT(DISTINCT user_id) as users,
               COUNT(CASE WHEN success = false THEN 1 END) as failures
        FROM eriq_conversations
        WHERE created_at > NOW() - INTERVAL '14 days'
        GROUP BY DATE(created_at)
        ORDER BY day DESC
    """)
    analytics["daily_volume"] = [
        {
            "date": str(r["day"]),
            "questions": r["questions"],
            "users": r["users"],
            "failures": r["failures"],
        }
        for r in (daily_volume or [])
    ]

    summary = execute_query("""
        SELECT
            COUNT(*) as total_conversations,
            COUNT(DISTINCT user_id) as total_users,
            COUNT(CASE WHEN rating IS NOT NULL THEN 1 END) as total_rated,
            ROUND(AVG(CASE WHEN rating IS NOT NULL THEN rating END)::numeric, 2) as overall_avg_rating,
            COUNT(CASE WHEN rating <= 2 THEN 1 END) as low_satisfaction_count,
            COUNT(CASE WHEN rating >= 4 THEN 1 END) as high_satisfaction_count,
            COUNT(CASE WHEN success = false THEN 1 END) as total_failures,
            SUM(tokens_used) as total_tokens_used
        FROM eriq_conversations
        WHERE created_at > NOW() - INTERVAL '30 days'
    """)
    if summary:
        s = summary[0]
        analytics["summary_30d"] = {
            "total_conversations": s["total_conversations"],
            "total_users": s["total_users"],
            "total_rated": s["total_rated"],
            "overall_avg_rating": float(s["overall_avg_rating"]) if s.get("overall_avg_rating") else None,
            "low_satisfaction_count": s["low_satisfaction_count"],
            "high_satisfaction_count": s["high_satisfaction_count"],
            "satisfaction_rate": round(s["high_satisfaction_count"] / max(s["total_rated"], 1) * 100, 1),
            "total_failures": s["total_failures"],
            "failure_rate": round(s["total_failures"] / max(s["total_conversations"], 1) * 100, 1),
            "total_tokens_used": s["total_tokens_used"] or 0,
        }

    return analytics


def _log_conversation(user_id: int, question: str, response: str, intent: str,
                      mode: str, plan: str, tokens_used: int, rating: Optional[int],
                      success: bool):
    with get_cursor() as cursor:
        cursor.execute("""
            INSERT INTO eriq_conversations
            (user_id, question, response, intent, mode, plan, tokens_used, rating, success, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        """, (user_id, question, response, intent, mode, plan, tokens_used, rating, success))
