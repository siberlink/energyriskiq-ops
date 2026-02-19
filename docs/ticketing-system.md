# Ticketing System — Support & Communication Module

**Last Updated:** February 2026

---

## 1. Overview

The Ticketing System provides a structured communication channel between EnergyRiskIQ users and the admin team. Users can create support tickets from their account dashboard, and admins manage them from the admin portal. Both sides receive live unread notifications with 30-second polling.

The module is fully encapsulated in `src/tickets/` with its own database layer (`db.py`) and API routes (`routes.py`), keeping it isolated from other system components.

---

## 2. Architecture

### Module Structure

```
src/tickets/
├── __init__.py
├── db.py          # Database schema, migrations, and all query functions
└── routes.py      # FastAPI API endpoints (user + admin)
```

### Database Tables

#### `tickets`
| Column          | Type         | Description                                       |
|-----------------|--------------|---------------------------------------------------|
| id              | SERIAL PK    | Auto-incrementing ticket ID                       |
| user_id         | INTEGER FK   | References `users(id)` — the ticket creator       |
| category        | VARCHAR(50)  | One of: support, billing, feature_suggestion, other |
| other_category  | VARCHAR(100) | Custom label when category is "other"             |
| subject         | VARCHAR(200) | Ticket subject line (3–200 chars)                 |
| status          | VARCHAR(20)  | One of: open, in_progress, resolved, closed       |
| priority        | VARCHAR(20)  | Default: normal                                   |
| user_unread     | BOOLEAN      | TRUE when admin has replied and user hasn't viewed |
| admin_unread    | BOOLEAN      | TRUE when user creates/replies and admin hasn't viewed |
| created_at      | TIMESTAMPTZ  | Ticket creation timestamp                         |
| updated_at      | TIMESTAMPTZ  | Last update timestamp                             |

#### `ticket_messages`
| Column      | Type        | Description                                    |
|-------------|-------------|------------------------------------------------|
| id          | SERIAL PK   | Auto-incrementing message ID                   |
| ticket_id   | INTEGER FK  | References `tickets(id)` with CASCADE delete   |
| sender_type | VARCHAR(10) | Either "user" or "admin"                       |
| sender_id   | INTEGER     | User ID (for user messages), NULL for admin    |
| message     | TEXT        | Message content (1–5000 chars)                 |
| created_at  | TIMESTAMPTZ | Message timestamp                              |

### Indexes

- `idx_tickets_user_id` on `tickets(user_id)` — fast lookup of user's tickets
- `idx_tickets_status` on `tickets(status)` — status filtering
- `idx_ticket_messages_ticket_id` on `ticket_messages(ticket_id)` — message retrieval

---

## 3. Ticket Categories

| Category            | Label              | Use Case                                |
|---------------------|--------------------|-----------------------------------------|
| support             | Support            | General platform help and questions     |
| billing             | Billing            | Payment, subscription, and invoice issues |
| feature_suggestion  | Feature Suggestion | User ideas for new features             |
| other               | (Custom label)     | User-defined category with custom text  |

---

## 4. Ticket Statuses & Lifecycle

| Status      | Meaning                                              |
|-------------|------------------------------------------------------|
| open        | New ticket, awaiting admin attention (default)       |
| in_progress | Admin is actively working on the issue               |
| resolved    | Issue has been addressed, awaiting user confirmation |
| closed      | Ticket is finalized — no further replies allowed     |

**Lifecycle Flow:**
```
User creates ticket → [open]
  → Admin reviews → [in_progress]
  → Admin resolves → [resolved]
  → Admin or natural close → [closed]
```

Users cannot reply to tickets with status "closed". Admins can change status at any time.

---

## 5. API Endpoints

All endpoints are under `/api/v1/tickets`.

### User Endpoints (Bearer token auth)

| Method | Path                          | Description                    |
|--------|-------------------------------|--------------------------------|
| POST   | `/api/v1/tickets`             | Create a new ticket            |
| GET    | `/api/v1/tickets`             | List user's tickets (with optional `?status=` filter) |
| GET    | `/api/v1/tickets/unread`      | Get user's unread ticket count |
| GET    | `/api/v1/tickets/{id}`        | Get ticket detail with messages (marks as read) |
| POST   | `/api/v1/tickets/{id}/reply`  | Reply to a ticket              |

### Admin Endpoints (X-Admin-Token header auth)

| Method | Path                                  | Description                        |
|--------|---------------------------------------|------------------------------------|
| GET    | `/api/v1/tickets/admin/all`           | List all tickets (with `?status=` and `?category=` filters) |
| GET    | `/api/v1/tickets/admin/stats`         | Get ticket statistics (open, in_progress, resolved, unread counts) |
| GET    | `/api/v1/tickets/admin/unread`        | Get admin unread count             |
| GET    | `/api/v1/tickets/admin/{id}`          | Get ticket detail (marks as read by admin) |
| POST   | `/api/v1/tickets/admin/{id}/reply`    | Admin reply to ticket              |
| PUT    | `/api/v1/tickets/admin/{id}/status`   | Update ticket status               |

---

## 6. Authentication

- **User side:** Standard Bearer token in `Authorization` header, validated through `get_current_user()` from user_routes
- **Admin side:** `X-Admin-Token` header, validated through the shared `verify_admin_token()` function from admin_routes (same auth used across entire admin portal)

---

## 7. Unread Notification System

The ticketing system uses a dual-sided unread tracking mechanism:

### How It Works

1. **User creates a ticket** → `admin_unread = TRUE` (admin sees unread indicator)
2. **Admin opens the ticket** → `mark_ticket_read_by_admin()` sets `admin_unread = FALSE`
3. **Admin replies** → `user_unread = TRUE` (user sees unread indicator)
4. **User opens the ticket** → `mark_ticket_read_by_user()` sets `user_unread = FALSE`
5. **User replies** → `admin_unread = TRUE` again

### Live Badge Notifications

Both the user dashboard and admin portal display unread ticket counts in their navigation:
- **User side:** Red badge on "Tickets" nav item in account sidebar
- **Admin side:** Red badge on "Tickets" nav item in admin sidebar

Both poll the `/unread` endpoint every 30 seconds for live updates.

---

## 8. User Interface

### User Dashboard (users-account.html)

Located in the account sidebar under the "Tickets" navigation item. Provides:

- **Ticket List View:** Shows all user tickets with subject, category, status badge, last message preview, message count, and unread indicator
- **Create Ticket Form:** Category selector (with custom label for "Other"), subject field, and message textarea
- **Ticket Detail View:** Full message thread with user/admin bubbles, reply textarea, and back navigation
- **Status Filter:** Dropdown to filter by Open, In Progress, Resolved, or Closed

### Admin Portal (admin.html)

Located in the admin sidebar under the "Support" section. Provides:

- **Stats Dashboard:** Quick-view cards showing Open, In Progress, Resolved, and Unread ticket counts
- **Filter Controls:** Status and category filter dropdowns
- **Ticket List:** Shows subject, user email, category, date, message count, status badge, and unread dot indicator
- **Ticket Detail View:** Full message thread, reply textarea, status management dropdown, and back button
- **Reply Box:** Automatically hidden when a ticket is closed

---

## 9. Data Constraints & Validation

| Field               | Constraint                                           |
|---------------------|------------------------------------------------------|
| subject             | 3–200 characters                                     |
| message (create)    | 10–5000 characters                                   |
| message (reply)     | 1–5000 characters                                    |
| category            | Must be: support, billing, feature_suggestion, other |
| status              | Must be: open, in_progress, resolved, closed         |
| other_category      | Max 100 characters (only when category = "other")    |
| Closed ticket reply | Blocked — returns HTTP 400                           |

---

## 10. Admin Statistics

The `/admin/stats` endpoint returns:

```json
{
  "total_count": 42,
  "open_count": 12,
  "in_progress_count": 5,
  "resolved_count": 20,
  "closed_count": 5,
  "unread_count": 8,
  "categories": {
    "support": 18,
    "billing": 10,
    "feature_suggestion": 8,
    "other": 6
  }
}
```

---

## 11. Integration Points

- **User Authentication:** Uses the existing session/Bearer token system from `src/api/user_routes.py`
- **Admin Authentication:** Uses the shared `verify_admin_token` from `src/api/admin_routes.py`
- **Database:** PostgreSQL via `src/db/db.py` connection pool
- **Migrations:** Runs automatically on API startup via `run_tickets_migration()` called from `src/api/app.py`

The ticketing module does not depend on or interfere with any other system modules (GERI, EERI, EGSI, delivery, alerts, etc.).
