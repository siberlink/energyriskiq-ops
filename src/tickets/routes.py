import logging
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Header, Query
from pydantic import BaseModel, Field
from src.tickets.db import (
    create_ticket, get_tickets_for_user, get_ticket_detail,
    add_ticket_message, update_ticket_status, get_all_tickets_admin,
    get_unread_count_user, get_unread_count_admin, mark_ticket_read_by_user,
    mark_ticket_read_by_admin, get_ticket_stats_admin
)
from src.api.user_routes import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/tickets", tags=["tickets"])


class CreateTicketRequest(BaseModel):
    category: str = Field(..., pattern="^(support|billing|feature_suggestion|other)$")
    subject: str = Field(..., min_length=3, max_length=200)
    message: str = Field(..., min_length=10, max_length=5000)
    other_category: Optional[str] = Field(None, max_length=100)


class TicketReplyRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=5000)


class UpdateStatusRequest(BaseModel):
    status: str = Field(..., pattern="^(open|in_progress|resolved|closed)$")


def _get_user_from_session(authorization: Optional[str]) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization.replace("Bearer ", "")
    user = get_current_user(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid session")
    return user


def _validate_admin(x_admin_token: Optional[str]):
    from src.api.admin_routes import verify_admin_token
    verify_admin_token(x_admin_token)


@router.post("")
def create_new_ticket(
    req: CreateTicketRequest,
    authorization: Optional[str] = Header(None)
):
    user = _get_user_from_session(authorization)
    ticket = create_ticket(
        user_id=user['id'],
        category=req.category,
        subject=req.subject,
        message=req.message,
        other_category=req.other_category
    )
    return {"success": True, "ticket": ticket}


@router.get("")
def list_user_tickets(
    status: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None)
):
    user = _get_user_from_session(authorization)
    tickets = get_tickets_for_user(user['id'], status_filter=status)
    return {"tickets": tickets}


@router.get("/unread")
def user_unread_count(authorization: Optional[str] = Header(None)):
    user = _get_user_from_session(authorization)
    count = get_unread_count_user(user['id'])
    return {"unread": count}


@router.get("/{ticket_id}")
def get_ticket(ticket_id: int, authorization: Optional[str] = Header(None)):
    user = _get_user_from_session(authorization)
    ticket = get_ticket_detail(ticket_id, user_id=user['id'])
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    mark_ticket_read_by_user(ticket_id, user['id'])
    return {"ticket": ticket}


@router.post("/{ticket_id}/reply")
def reply_to_ticket(
    ticket_id: int,
    req: TicketReplyRequest,
    authorization: Optional[str] = Header(None)
):
    user = _get_user_from_session(authorization)
    ticket = get_ticket_detail(ticket_id, user_id=user['id'])
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if ticket['status'] == 'closed':
        raise HTTPException(status_code=400, detail="Cannot reply to a closed ticket")
    msg = add_ticket_message(
        ticket_id=ticket_id,
        sender_type='user',
        sender_id=user['id'],
        message=req.message
    )
    return {"success": True, "message": msg}


@router.get("/admin/all")
def admin_list_tickets(
    status: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    x_admin_token: Optional[str] = Header(None)
):
    _validate_admin(x_admin_token)
    tickets = get_all_tickets_admin(status_filter=status, category_filter=category)
    return {"tickets": tickets}


@router.get("/admin/stats")
def admin_ticket_stats(x_admin_token: Optional[str] = Header(None)):
    _validate_admin(x_admin_token)
    stats = get_ticket_stats_admin()
    return stats


@router.get("/admin/unread")
def admin_unread_count(x_admin_token: Optional[str] = Header(None)):
    _validate_admin(x_admin_token)
    count = get_unread_count_admin()
    return {"unread": count}


@router.get("/admin/{ticket_id}")
def admin_get_ticket(ticket_id: int, x_admin_token: Optional[str] = Header(None)):
    _validate_admin(x_admin_token)
    ticket = get_ticket_detail(ticket_id, admin=True)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    mark_ticket_read_by_admin(ticket_id)
    return {"ticket": ticket}


@router.post("/admin/{ticket_id}/reply")
def admin_reply_to_ticket(
    ticket_id: int,
    req: TicketReplyRequest,
    x_admin_token: Optional[str] = Header(None)
):
    _validate_admin(x_admin_token)
    ticket = get_ticket_detail(ticket_id, admin=True)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    msg = add_ticket_message(
        ticket_id=ticket_id,
        sender_type='admin',
        sender_id=None,
        message=req.message
    )
    return {"success": True, "message": msg}


@router.put("/admin/{ticket_id}/status")
def admin_update_status(
    ticket_id: int,
    req: UpdateStatusRequest,
    x_admin_token: Optional[str] = Header(None)
):
    _validate_admin(x_admin_token)
    update_ticket_status(ticket_id, req.status)
    return {"success": True, "status": req.status}
