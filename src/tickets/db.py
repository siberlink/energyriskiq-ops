import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict
from src.db.db import get_cursor, execute_one

logger = logging.getLogger(__name__)


def run_tickets_migration():
    logger.info("Running tickets migration...")
    with get_cursor() as cursor:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                category VARCHAR(50) NOT NULL,
                other_category VARCHAR(100),
                subject VARCHAR(200) NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'open',
                priority VARCHAR(20) NOT NULL DEFAULT 'normal',
                user_unread BOOLEAN NOT NULL DEFAULT FALSE,
                admin_unread BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ticket_messages (
                id SERIAL PRIMARY KEY,
                ticket_id INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
                sender_type VARCHAR(10) NOT NULL,
                sender_id INTEGER,
                message TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_tickets_user_id ON tickets(user_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_ticket_messages_ticket_id ON ticket_messages(ticket_id)
        """)
    logger.info("Tickets migration complete.")


def create_ticket(user_id: int, category: str, subject: str, message: str,
                  other_category: Optional[str] = None) -> Dict:
    with get_cursor() as cursor:
        cursor.execute("""
            INSERT INTO tickets (user_id, category, other_category, subject, status, admin_unread, user_unread)
            VALUES (%s, %s, %s, %s, 'open', TRUE, FALSE)
            RETURNING id, user_id, category, other_category, subject, status, priority,
                      created_at, updated_at
        """, (user_id, category, other_category, subject))
        ticket = dict(cursor.fetchone())

        cursor.execute("""
            INSERT INTO ticket_messages (ticket_id, sender_type, sender_id, message)
            VALUES (%s, 'user', %s, %s)
            RETURNING id, ticket_id, sender_type, sender_id, message, created_at
        """, (ticket['id'], user_id, message))

    ticket['created_at'] = ticket['created_at'].isoformat()
    ticket['updated_at'] = ticket['updated_at'].isoformat()
    return ticket


def get_tickets_for_user(user_id: int, status_filter: Optional[str] = None) -> List[Dict]:
    query = """
        SELECT t.id, t.category, t.other_category, t.subject, t.status, t.priority,
               t.user_unread, t.created_at, t.updated_at,
               (SELECT COUNT(*) FROM ticket_messages WHERE ticket_id = t.id) as message_count,
               (SELECT message FROM ticket_messages WHERE ticket_id = t.id ORDER BY created_at DESC LIMIT 1) as last_message
        FROM tickets t
        WHERE t.user_id = %s
    """
    params = [user_id]
    if status_filter:
        query += " AND t.status = %s"
        params.append(status_filter)
    query += " ORDER BY t.updated_at DESC"

    with get_cursor(commit=False) as cursor:
        cursor.execute(query, params)
        rows = cursor.fetchall()

    result = []
    for row in rows:
        d = dict(row)
        d['created_at'] = d['created_at'].isoformat()
        d['updated_at'] = d['updated_at'].isoformat()
        if d.get('last_message') and len(d['last_message']) > 100:
            d['last_message'] = d['last_message'][:100] + '...'
        result.append(d)
    return result


def get_ticket_detail(ticket_id: int, user_id: Optional[int] = None, admin: bool = False) -> Optional[Dict]:
    if admin:
        ticket = execute_one("""
            SELECT t.*, u.email as user_email
            FROM tickets t
            JOIN users u ON t.user_id = u.id
            WHERE t.id = %s
        """, (ticket_id,))
    else:
        ticket = execute_one("""
            SELECT t.*
            FROM tickets t
            WHERE t.id = %s AND t.user_id = %s
        """, (ticket_id, user_id))

    if not ticket:
        return None

    ticket = dict(ticket)
    ticket['created_at'] = ticket['created_at'].isoformat()
    ticket['updated_at'] = ticket['updated_at'].isoformat()

    with get_cursor(commit=False) as cursor:
        cursor.execute("""
            SELECT id, ticket_id, sender_type, sender_id, message, created_at
            FROM ticket_messages
            WHERE ticket_id = %s
            ORDER BY created_at ASC
        """, (ticket_id,))
        messages = cursor.fetchall()

    ticket['messages'] = []
    for msg in messages:
        m = dict(msg)
        m['created_at'] = m['created_at'].isoformat()
        ticket['messages'].append(m)

    return ticket


def add_ticket_message(ticket_id: int, sender_type: str, sender_id: Optional[int],
                       message: str) -> Dict:
    with get_cursor() as cursor:
        cursor.execute("""
            INSERT INTO ticket_messages (ticket_id, sender_type, sender_id, message)
            VALUES (%s, %s, %s, %s)
            RETURNING id, ticket_id, sender_type, sender_id, message, created_at
        """, (ticket_id, sender_type, sender_id, message))
        msg = dict(cursor.fetchone())

        if sender_type == 'admin':
            cursor.execute("""
                UPDATE tickets SET user_unread = TRUE, admin_unread = FALSE, updated_at = NOW()
                WHERE id = %s
            """, (ticket_id,))
        else:
            cursor.execute("""
                UPDATE tickets SET admin_unread = TRUE, user_unread = FALSE, updated_at = NOW()
                WHERE id = %s
            """, (ticket_id,))

    msg['created_at'] = msg['created_at'].isoformat()
    return msg


def update_ticket_status(ticket_id: int, status: str):
    with get_cursor() as cursor:
        cursor.execute("""
            UPDATE tickets SET status = %s, updated_at = NOW() WHERE id = %s
        """, (status, ticket_id))


def get_all_tickets_admin(status_filter: Optional[str] = None,
                          category_filter: Optional[str] = None) -> List[Dict]:
    query = """
        SELECT t.id, t.category, t.other_category, t.subject, t.status, t.priority,
               t.admin_unread, t.created_at, t.updated_at,
               u.email as user_email,
               (SELECT COUNT(*) FROM ticket_messages WHERE ticket_id = t.id) as message_count,
               (SELECT message FROM ticket_messages WHERE ticket_id = t.id ORDER BY created_at DESC LIMIT 1) as last_message
        FROM tickets t
        JOIN users u ON t.user_id = u.id
        WHERE 1=1
    """
    params = []
    if status_filter:
        query += " AND t.status = %s"
        params.append(status_filter)
    if category_filter:
        query += " AND t.category = %s"
        params.append(category_filter)
    query += " ORDER BY t.admin_unread DESC, t.updated_at DESC"

    with get_cursor(commit=False) as cursor:
        cursor.execute(query, params)
        rows = cursor.fetchall()

    result = []
    for row in rows:
        d = dict(row)
        d['created_at'] = d['created_at'].isoformat()
        d['updated_at'] = d['updated_at'].isoformat()
        if d.get('last_message') and len(d['last_message']) > 100:
            d['last_message'] = d['last_message'][:100] + '...'
        result.append(d)
    return result


def get_unread_count_user(user_id: int) -> int:
    row = execute_one("""
        SELECT COUNT(*) as cnt FROM tickets
        WHERE user_id = %s AND user_unread = TRUE
    """, (user_id,))
    return row['cnt'] if row else 0


def get_unread_count_admin() -> int:
    row = execute_one("SELECT COUNT(*) as cnt FROM tickets WHERE admin_unread = TRUE")
    return row['cnt'] if row else 0


def mark_ticket_read_by_user(ticket_id: int, user_id: int):
    with get_cursor() as cursor:
        cursor.execute("""
            UPDATE tickets SET user_unread = FALSE WHERE id = %s AND user_id = %s
        """, (ticket_id, user_id))


def mark_ticket_read_by_admin(ticket_id: int):
    with get_cursor() as cursor:
        cursor.execute("""
            UPDATE tickets SET admin_unread = FALSE WHERE id = %s
        """, (ticket_id,))


def get_ticket_stats_admin() -> Dict:
    with get_cursor(commit=False) as cursor:
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE status = 'open') as open_count,
                COUNT(*) FILTER (WHERE status = 'in_progress') as in_progress_count,
                COUNT(*) FILTER (WHERE status = 'resolved') as resolved_count,
                COUNT(*) FILTER (WHERE status = 'closed') as closed_count,
                COUNT(*) FILTER (WHERE admin_unread = TRUE) as unread_count
            FROM tickets
        """)
        row = dict(cursor.fetchone())
    return row
