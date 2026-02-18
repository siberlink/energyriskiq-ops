import logging
from fastapi import APIRouter, HTTPException, Header
from fastapi.responses import StreamingResponse
from typing import Optional, List
from pydantic import BaseModel

from src.api.admin_routes import verify_admin_token
from src.elsa.agent import ask_elsa_stream, create_topic, get_topics, get_topic_history
from src.elsa.knowledge_base import load_elsa_knowledge_base

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/elsa", tags=["elsa"])


class ElsaAskRequest(BaseModel):
    question: str
    topic_id: Optional[int] = None
    conversation_history: Optional[List[dict]] = None
    image_data: Optional[str] = None


class ElsaTopicRequest(BaseModel):
    title: str


@router.on_event("startup")
async def elsa_startup():
    try:
        load_elsa_knowledge_base()
        logger.info("ELSA knowledge base loaded on startup")
    except Exception as e:
        logger.warning(f"ELSA knowledge base preload failed (will lazy-load): {e}")


@router.post("/ask")
def elsa_ask(body: ElsaAskRequest, x_admin_token: Optional[str] = Header(None)):
    verify_admin_token(x_admin_token)

    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty")
    if len(question) > 5000:
        raise HTTPException(status_code=400, detail="Question is too long (max 5000 characters)")

    image_data = body.image_data
    if image_data and len(image_data) > 20_000_000:
        raise HTTPException(status_code=400, detail="Image is too large (max ~15MB)")

    def generate():
        yield from ask_elsa_stream(
            question=question,
            topic_id=body.topic_id,
            conversation_history=body.conversation_history,
            image_data=image_data,
        )

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.post("/topics")
def elsa_create_topic(body: ElsaTopicRequest, x_admin_token: Optional[str] = Header(None)):
    verify_admin_token(x_admin_token)

    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Topic title cannot be empty")

    try:
        topic = create_topic(title)
        return {"success": True, "topic": topic}
    except Exception as e:
        logger.error(f"Failed to create ELSA topic: {e}")
        raise HTTPException(status_code=500, detail="Failed to create topic")


@router.get("/topics")
def elsa_list_topics(x_admin_token: Optional[str] = Header(None)):
    verify_admin_token(x_admin_token)
    topics = get_topics(limit=50)
    return {"topics": topics}


@router.get("/topics/{topic_id}/history")
def elsa_topic_history(topic_id: int, x_admin_token: Optional[str] = Header(None)):
    verify_admin_token(x_admin_token)
    history = get_topic_history(topic_id, limit=100)
    return {"messages": history}
