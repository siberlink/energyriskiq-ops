import logging
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


class EriqAskRequest(BaseModel):
    question: str
    conversation_history: Optional[List[dict]] = None


class EriqFeedbackRequest(BaseModel):
    conversation_id: int
    rating: int
    comment: Optional[str] = None


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

    try:
        with get_cursor() as cursor:
            cursor.execute("""
                UPDATE eriq_conversations
                SET rating = %s, feedback_comment = %s
                WHERE id = %s AND user_id = %s
            """, (body.rating, body.comment, body.conversation_id, user_id))
        return {"success": True, "message": "Thank you for your feedback"}
    except Exception as e:
        logger.error(f"Failed to save ERIQ feedback: {e}")
        raise HTTPException(status_code=500, detail="Failed to save feedback")


@router.get("/history")
def eriq_history(x_user_token: Optional[str] = Header(None), limit: int = 20):
    session = verify_user_session(x_user_token)
    user_id = session["user_id"]

    rows = execute_query("""
        SELECT id, question, response, intent, mode, created_at, rating
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
            }
            for r in rows
        ]
    }


def _log_conversation(user_id: int, question: str, response: str, intent: str,
                      mode: str, plan: str, tokens_used: int, rating: Optional[int],
                      success: bool):
    with get_cursor() as cursor:
        cursor.execute("""
            INSERT INTO eriq_conversations
            (user_id, question, response, intent, mode, plan, tokens_used, rating, success, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        """, (user_id, question, response, intent, mode, plan, tokens_used, rating, success))
