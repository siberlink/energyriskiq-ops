import logging
from src.db.db import execute_query, execute_one, get_cursor

logger = logging.getLogger(__name__)

DEFAULT_BLOG_CATEGORIES = [
    ('Energy Markets', 'energy-markets', 'Analysis of global energy commodity markets, pricing trends, and supply-demand dynamics', '#3b82f6', 1),
    ('Geopolitics', 'geopolitics', 'Geopolitical developments affecting energy security and trade flows', '#ef4444', 2),
    ('Risk Management', 'risk-management', 'Strategies and frameworks for managing energy market risk', '#8b5cf6', 3),
    ('Oil & Gas', 'oil-gas', 'Upstream, midstream, and downstream oil and gas industry coverage', '#f59e0b', 4),
    ('Renewables', 'renewables', 'Renewable energy developments, policy, and market integration', '#10b981', 5),
    ('Climate & ESG', 'climate-esg', 'Climate policy, ESG frameworks, and energy transition analysis', '#06b6d4', 6),
    ('Trading Strategies', 'trading-strategies', 'Energy trading methodologies, hedging, and market positioning', '#ec4899', 7),
    ('Industry Analysis', 'industry-analysis', 'Deep dives into energy industry segments and corporate strategy', '#f97316', 8),
    ('Regulation & Policy', 'regulation-policy', 'Energy regulation, sanctions, and government policy analysis', '#6366f1', 9),
    ('LNG & Natural Gas', 'lng-natural-gas', 'LNG markets, natural gas infrastructure, and pricing dynamics', '#14b8a6', 10),
    ('Nuclear Energy', 'nuclear-energy', 'Nuclear power developments, policy, and market outlook', '#a855f7', 11),
    ('General', 'general', 'General energy intelligence and cross-cutting topics', '#64748b', 12),
]


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

                CREATE TABLE IF NOT EXISTS blog_categories (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL UNIQUE,
                    slug VARCHAR(120) NOT NULL UNIQUE,
                    description TEXT DEFAULT '',
                    color VARCHAR(7) DEFAULT '#3b82f6',
                    sort_order INTEGER DEFAULT 0,
                    is_active BOOLEAN DEFAULT TRUE,
                    post_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS idx_blog_posts_slug ON blog_posts(slug);
                CREATE INDEX IF NOT EXISTS idx_blog_posts_status ON blog_posts(status);
                CREATE INDEX IF NOT EXISTS idx_blog_posts_created ON blog_posts(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_blog_comments_post ON blog_comments(post_id);
                CREATE INDEX IF NOT EXISTS idx_blog_users_email ON blog_users(email);
                CREATE INDEX IF NOT EXISTS idx_blog_categories_slug ON blog_categories(slug);
                CREATE INDEX IF NOT EXISTS idx_blog_categories_sort ON blog_categories(sort_order);

                CREATE TABLE IF NOT EXISTS blog_images (
                    id SERIAL PRIMARY KEY,
                    filename VARCHAR(255) NOT NULL UNIQUE,
                    content_type VARCHAR(50) NOT NULL DEFAULT 'image/png',
                    image_data BYTEA NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_blog_images_filename ON blog_images(filename);
            """)
        _seed_default_categories()
        logger.info("Blog migrations completed")
    except Exception as e:
        logger.error(f"Blog migration error: {e}")


def _seed_default_categories():
    existing = execute_one("SELECT COUNT(*) as cnt FROM blog_categories")
    if existing and existing['cnt'] > 0:
        return
    try:
        with get_cursor() as cur:
            for name, slug, description, color, sort_order in DEFAULT_BLOG_CATEGORIES:
                cur.execute(
                    """INSERT INTO blog_categories (name, slug, description, color, sort_order)
                       VALUES (%s, %s, %s, %s, %s) ON CONFLICT (name) DO NOTHING""",
                    (name, slug, description, color, sort_order)
                )
        logger.info(f"Seeded {len(DEFAULT_BLOG_CATEGORIES)} default blog categories")
    except Exception as e:
        logger.error(f"Blog category seed error: {e}")


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
        "SELECT id, name, slug, description, color, sort_order, is_active, post_count FROM blog_categories WHERE is_active = TRUE ORDER BY sort_order, name",
        fetch=True
    ) or []
    return rows


def get_blog_category_names():
    rows = get_blog_categories()
    return [r['name'] for r in rows]


def get_blog_category_by_slug(slug):
    return execute_one(
        "SELECT * FROM blog_categories WHERE slug = %s AND is_active = TRUE", (slug,)
    )


def get_category_slug_map():
    rows = get_blog_categories()
    return {r['name']: r['slug'] for r in rows}


def get_all_blog_categories_admin():
    return execute_query(
        "SELECT * FROM blog_categories ORDER BY sort_order, name", fetch=True
    ) or []


def create_blog_category(name, slug, description='', color='#3b82f6', sort_order=0):
    return execute_one(
        """INSERT INTO blog_categories (name, slug, description, color, sort_order)
           VALUES (%s, %s, %s, %s, %s) RETURNING *""",
        (name, slug, description, color, sort_order)
    )


def update_blog_category(cat_id, name, slug, description, color, sort_order, is_active):
    return execute_one(
        """UPDATE blog_categories SET name=%s, slug=%s, description=%s, color=%s, sort_order=%s, is_active=%s
           WHERE id=%s RETURNING *""",
        (name, slug, description, color, sort_order, is_active, cat_id)
    )


def delete_blog_category(cat_id):
    execute_query("DELETE FROM blog_categories WHERE id=%s", (cat_id,), fetch=False)


def refresh_category_post_counts():
    try:
        execute_query("""
            UPDATE blog_categories bc SET post_count = (
                SELECT COUNT(*) FROM blog_posts bp
                WHERE bp.category = bc.name AND bp.status = 'published'
            )
        """, fetch=False)
    except Exception as e:
        logger.error(f"Category post count refresh error: {e}")


def get_all_blog_users_admin():
    return execute_query(
        """SELECT id, display_name, email, avatar_color, bio, is_active, created_at,
                  (SELECT COUNT(*) FROM blog_posts WHERE author_id = blog_users.id) as post_count,
                  (SELECT COUNT(*) FROM blog_comments WHERE user_id = blog_users.id) as comment_count
           FROM blog_users ORDER BY created_at DESC""",
        fetch=True
    ) or []


def update_blog_user_status(user_id, is_active):
    return execute_one(
        "UPDATE blog_users SET is_active=%s WHERE id=%s RETURNING *",
        (is_active, user_id)
    )


def delete_blog_user(user_id):
    execute_query("DELETE FROM blog_sessions WHERE user_id=%s", (user_id,), fetch=False)
    execute_query("DELETE FROM blog_users WHERE id=%s", (user_id,), fetch=False)


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
