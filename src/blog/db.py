import logging
from src.db.db import execute_query, execute_one, get_cursor

logger = logging.getLogger(__name__)


def run_blog_migrations():
    try:
        with get_cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS blog_users (
                    id SERIAL PRIMARY KEY,
                    display_name VARCHAR(100) NOT NULL,
                    email VARCHAR(255) NOT NULL UNIQUE,
                    password_hash VARCHAR(255) NOT NULL,
                    avatar_color VARCHAR(7) DEFAULT '#3b82f6',
                    bio TEXT DEFAULT '',
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS blog_sessions (
                    token VARCHAR(64) PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES blog_users(id) ON DELETE CASCADE,
                    expires_at TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS blog_posts (
                    id SERIAL PRIMARY KEY,
                    title VARCHAR(500) NOT NULL,
                    slug VARCHAR(600) NOT NULL UNIQUE,
                    excerpt TEXT DEFAULT '',
                    content TEXT NOT NULL,
                    cover_image TEXT DEFAULT '',
                    category VARCHAR(100) DEFAULT 'General',
                    tags TEXT DEFAULT '',
                    author_id INTEGER,
                    author_name VARCHAR(100) NOT NULL DEFAULT 'Admin',
                    author_type VARCHAR(20) NOT NULL DEFAULT 'admin',
                    status VARCHAR(20) NOT NULL DEFAULT 'pending',
                    rejection_reason TEXT DEFAULT '',
                    view_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW(),
                    published_at TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS blog_comments (
                    id SERIAL PRIMARY KEY,
                    post_id INTEGER NOT NULL REFERENCES blog_posts(id) ON DELETE CASCADE,
                    user_id INTEGER REFERENCES blog_users(id) ON DELETE SET NULL,
                    guest_name VARCHAR(100),
                    content TEXT NOT NULL,
                    is_approved BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS idx_blog_posts_slug ON blog_posts(slug);
                CREATE INDEX IF NOT EXISTS idx_blog_posts_status ON blog_posts(status);
                CREATE INDEX IF NOT EXISTS idx_blog_posts_created ON blog_posts(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_blog_comments_post ON blog_comments(post_id);
                CREATE INDEX IF NOT EXISTS idx_blog_users_email ON blog_users(email);
            """)
        logger.info("Blog migrations completed")
    except Exception as e:
        logger.error(f"Blog migration error: {e}")


def get_published_posts(page=1, per_page=10, category=None, search=None):
    offset = (page - 1) * per_page
    conditions = ["status = 'published'"]
    params = []

    if category and category != 'all':
        conditions.append("category = %s")
        params.append(category)
    if search:
        conditions.append("(title ILIKE %s OR excerpt ILIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])

    where = " AND ".join(conditions)
    params.extend([per_page, offset])

    posts = execute_query(
        f"SELECT * FROM blog_posts WHERE {where} ORDER BY published_at DESC NULLS LAST, created_at DESC LIMIT %s OFFSET %s",
        tuple(params), fetch=True
    )

    count_params = params[:-2]
    count_row = execute_one(
        f"SELECT COUNT(*) as total FROM blog_posts WHERE {where}",
        tuple(count_params) if count_params else None
    )
    total = count_row['total'] if count_row else 0

    return posts or [], total


def get_post_by_slug(slug):
    return execute_one("SELECT * FROM blog_posts WHERE slug = %s AND status = 'published'", (slug,))


def get_post_by_id(post_id):
    return execute_one("SELECT * FROM blog_posts WHERE id = %s", (post_id,))


def increment_view_count(post_id):
    try:
        execute_query("UPDATE blog_posts SET view_count = view_count + 1 WHERE id = %s", (post_id,))
    except Exception:
        pass


def create_post(title, slug, excerpt, content, cover_image, category, tags, author_id, author_name, author_type, status='pending'):
    published_at = "NOW()" if status == 'published' else "NULL"
    return execute_one(
        f"""INSERT INTO blog_posts (title, slug, excerpt, content, cover_image, category, tags, author_id, author_name, author_type, status, published_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, {published_at})
            RETURNING *""",
        (title, slug, excerpt, content, cover_image, category, tags, author_id, author_name, author_type, status)
    )


def update_post(post_id, title, slug, excerpt, content, cover_image, category, tags):
    return execute_one(
        """UPDATE blog_posts SET title=%s, slug=%s, excerpt=%s, content=%s, cover_image=%s, category=%s, tags=%s, updated_at=NOW()
           WHERE id=%s RETURNING *""",
        (title, slug, excerpt, content, cover_image, category, tags, post_id)
    )


def update_post_status(post_id, status, rejection_reason=''):
    published_at_clause = ", published_at=NOW()" if status == 'published' else ""
    return execute_one(
        f"UPDATE blog_posts SET status=%s, rejection_reason=%s{published_at_clause}, updated_at=NOW() WHERE id=%s RETURNING *",
        (status, rejection_reason, post_id)
    )


def delete_post(post_id):
    execute_query("DELETE FROM blog_posts WHERE id=%s", (post_id,), fetch=False)


def get_all_posts_admin(status_filter=None):
    if status_filter and status_filter != 'all':
        return execute_query(
            "SELECT * FROM blog_posts WHERE status=%s ORDER BY created_at DESC", (status_filter,), fetch=True
        ) or []
    return execute_query("SELECT * FROM blog_posts ORDER BY created_at DESC", fetch=True) or []


def get_posts_by_author(author_id):
    return execute_query(
        "SELECT * FROM blog_posts WHERE author_id=%s ORDER BY created_at DESC", (author_id,), fetch=True
    ) or []


def get_comments_for_post(post_id):
    return execute_query(
        """SELECT c.*, bu.display_name as user_display_name, bu.avatar_color
           FROM blog_comments c
           LEFT JOIN blog_users bu ON c.user_id = bu.id
           WHERE c.post_id = %s AND c.is_approved = TRUE
           ORDER BY c.created_at ASC""",
        (post_id,), fetch=True
    ) or []


def add_comment(post_id, content, user_id=None, guest_name=None):
    return execute_one(
        "INSERT INTO blog_comments (post_id, user_id, guest_name, content) VALUES (%s, %s, %s, %s) RETURNING *",
        (post_id, user_id, guest_name, content)
    )


def get_blog_user_by_email(email):
    return execute_one("SELECT * FROM blog_users WHERE email = %s", (email,))


def get_blog_user_by_id(user_id):
    return execute_one("SELECT * FROM blog_users WHERE id = %s", (user_id,))


def create_blog_user(display_name, email, password_hash):
    import random
    colors = ['#3b82f6', '#ef4444', '#10b981', '#f59e0b', '#8b5cf6', '#ec4899', '#06b6d4', '#f97316']
    color = random.choice(colors)
    return execute_one(
        "INSERT INTO blog_users (display_name, email, password_hash, avatar_color) VALUES (%s, %s, %s, %s) RETURNING *",
        (display_name, email, password_hash, color)
    )


def get_blog_categories():
    rows = execute_query(
        "SELECT DISTINCT category FROM blog_posts WHERE status='published' ORDER BY category", fetch=True
    ) or []
    return [r['category'] for r in rows]


def get_blog_stats():
    return execute_one("""
        SELECT 
            COUNT(*) FILTER (WHERE status='published') as published,
            COUNT(*) FILTER (WHERE status='pending') as pending,
            COUNT(*) FILTER (WHERE status='rejected') as rejected,
            COUNT(*) FILTER (WHERE status='draft') as draft,
            COUNT(*) as total
        FROM blog_posts
    """)


def create_blog_session(token, user_id, expires_at):
    return execute_one(
        "INSERT INTO blog_sessions (token, user_id, expires_at) VALUES (%s, %s, %s) RETURNING *",
        (token, user_id, expires_at)
    )


def get_blog_session(token):
    return execute_one(
        """SELECT bs.token, bs.expires_at, bu.id, bu.display_name, bu.email, bu.avatar_color, bu.is_active
           FROM blog_sessions bs
           JOIN blog_users bu ON bs.user_id = bu.id
           WHERE bs.token = %s AND bs.expires_at > NOW()""",
        (token,)
    )


def delete_blog_session(token):
    execute_query("DELETE FROM blog_sessions WHERE token = %s", (token,), fetch=False)


def cleanup_expired_blog_sessions():
    execute_query("DELETE FROM blog_sessions WHERE expires_at < NOW()", fetch=False)
