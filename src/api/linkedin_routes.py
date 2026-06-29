"""Admin API for the LinkedIn Posts Builder."""

import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from src.db.db import execute_query, execute_one
from src.api.admin_routes import verify_admin_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/linkedin", tags=["linkedin"])

VALID_STATUSES = {"draft", "approved", "published"}


class BodyUpdate(BaseModel):
    post_body: str


class StatusUpdate(BaseModel):
    status: str


@router.get("/posts")
def list_posts(x_admin_token: Optional[str] = Header(None)):
    verify_admin_token(x_admin_token)
    rows = execute_query(
        """
        SELECT id, post_date, report_date, selected_theme, selected_hook,
               selected_cta, post_body, char_count, status, source,
               created_at, updated_at
        FROM linkedin_posts
        ORDER BY post_date DESC, id DESC
        LIMIT 90
        """
    )
    return {"posts": rows or []}


@router.post("/generate")
def generate_post(x_admin_token: Optional[str] = Header(None)):
    verify_admin_token(x_admin_token)
    from src.linkedin.post_generator import generate_and_store_post

    result = generate_and_store_post(source="manual")
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "Generation failed"))
    return result


@router.post("/{post_id}/regenerate")
def regenerate_post(post_id: int, x_admin_token: Optional[str] = Header(None)):
    verify_admin_token(x_admin_token)
    post = execute_one("SELECT post_date FROM linkedin_posts WHERE id = %s", (post_id,))
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    pd = post["post_date"]
    if not isinstance(pd, date):
        pd = date.fromisoformat(str(pd)[:10])
    if pd != date.today():
        raise HTTPException(
            status_code=400,
            detail="Only today's post can be regenerated (it is rebuilt from today's report).",
        )

    from src.linkedin.post_generator import generate_and_store_post

    result = generate_and_store_post(source="manual", force_new_hook=True)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "Generation failed"))
    return result


@router.put("/{post_id}")
def update_post(post_id: int, body: BodyUpdate, x_admin_token: Optional[str] = Header(None)):
    verify_admin_token(x_admin_token)
    text = (body.post_body or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="post_body cannot be empty")
    rows = execute_query(
        """
        UPDATE linkedin_posts
        SET post_body = %s, char_count = %s, updated_at = NOW()
        WHERE id = %s
        RETURNING *
        """,
        (text, len(text), post_id),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Post not found")
    return {"ok": True, "post": rows[0]}


@router.post("/{post_id}/status")
def set_status(post_id: int, body: StatusUpdate, x_admin_token: Optional[str] = Header(None)):
    verify_admin_token(x_admin_token)
    status = (body.status or "").strip().lower()
    if status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")
    rows = execute_query(
        "UPDATE linkedin_posts SET status = %s, updated_at = NOW() WHERE id = %s RETURNING *",
        (status, post_id),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Post not found")
    return {"ok": True, "post": rows[0]}


@router.delete("/{post_id}")
def delete_post(post_id: int, x_admin_token: Optional[str] = Header(None)):
    verify_admin_token(x_admin_token)
    existing = execute_one("SELECT id FROM linkedin_posts WHERE id = %s", (post_id,))
    if not existing:
        raise HTTPException(status_code=404, detail="Post not found")
    execute_query("DELETE FROM linkedin_posts WHERE id = %s", (post_id,), fetch=False)
    return {"ok": True}
