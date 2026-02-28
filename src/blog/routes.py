import logging
import bcrypt
import secrets
import re
import unicodedata
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Request, Header, Query
from fastapi.responses import HTMLResponse, JSONResponse

from src.blog import db as blog_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["blog"])


def _hash_password(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _verify_password(password, hashed):
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except Exception:
        return False


def _slugify(text):
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
    text = re.sub(r'[^\w\s-]', '', text.lower())
    text = re.sub(r'[-\s]+', '-', text).strip('-')
    return text[:200]


def _get_blog_user(request: Request):
    token = request.cookies.get('blog_token')
    if not token:
        return None
    session = blog_db.get_blog_session(token)
    if not session:
        return None
    if not session.get('is_active', True):
        return None
    return {
        'id': session['id'],
        'display_name': session['display_name'],
        'email': session['email'],
        'avatar_color': session['avatar_color']
    }


def _format_date(dt):
    if not dt:
        return ''
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt)
        except Exception:
            return dt
    return dt.strftime('%B %d, %Y')


def _format_date_short(dt):
    if not dt:
        return ''
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt)
        except Exception:
            return dt
    return dt.strftime('%b %d, %Y')


def _esc(text):
    if not text:
        return ''
    return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')


def _get_reading_time(content):
    words = len(re.findall(r'\w+', content or ''))
    minutes = max(1, round(words / 200))
    return f"{minutes} min read"


def _render_markdown_basic(text):
    if not text:
        return ''
    text = _esc(text)
    text = re.sub(r'^### (.+)$', r'<h3>\1</h3>', text, flags=re.MULTILINE)
    text = re.sub(r'^## (.+)$', r'<h2>\1</h2>', text, flags=re.MULTILINE)
    text = re.sub(r'^# (.+)$', r'<h1>\1</h1>', text, flags=re.MULTILINE)
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    text = re.sub(r'`(.+?)`', r'<code>\1</code>', text)
    def _safe_link(m):
        label = m.group(1)
        url = m.group(2)
        if url.lower().startswith(('http://', 'https://', '/')):
            return f'<a href="{url}" target="_blank" rel="noopener">{label}</a>'
        return label
    text = re.sub(r'\[(.+?)\]\((.+?)\)', _safe_link, text)
    paragraphs = text.split('\n\n')
    result = []
    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        if p.startswith('<h') or p.startswith('<ul') or p.startswith('<ol'):
            result.append(p)
        else:
            lines = p.split('\n')
            is_list = all(l.strip().startswith('- ') or l.strip().startswith('* ') or not l.strip() for l in lines if l.strip())
            if is_list and any(l.strip() for l in lines):
                items = [l.strip().lstrip('- ').lstrip('* ') for l in lines if l.strip()]
                result.append('<ul>' + ''.join(f'<li>{item}</li>' for item in items) + '</ul>')
            else:
                result.append(f'<p>{p}</p>')
    return '\n'.join(result)


def _blog_base_styles():
    return """
    <style>
        :root {
            --blog-bg: #0f172a;
            --blog-text: #f1f5f9;
            --blog-text-primary: #ffffff;
            --blog-text-secondary: #cbd5e1;
            --blog-text-muted: #94a3b8;
            --blog-text-faint: #64748b;
            --blog-nav-bg: rgba(15,23,42,0.95);
            --blog-nav-border: rgba(255,255,255,0.06);
            --blog-card-bg: rgba(255,255,255,0.03);
            --blog-card-border: rgba(255,255,255,0.06);
            --blog-card-hover-border: rgba(59,130,246,0.3);
            --blog-card-hover-shadow: 0 12px 40px rgba(0,0,0,0.3);
            --blog-card-cover-bg: linear-gradient(135deg, #1e293b, #0f172a);
            --blog-input-bg: rgba(255,255,255,0.04);
            --blog-input-border: rgba(255,255,255,0.1);
            --blog-input-text: #f1f5f9;
            --blog-hero-gradient: linear-gradient(135deg, #f1f5f9, #94a3b8);
            --blog-link: #60a5fa;
            --blog-link-hover: #93bbfc;
            --blog-modal-bg: #1e293b;
            --blog-modal-overlay: rgba(0,0,0,0.7);
            --blog-content-text: #e2e8f0;
            --blog-content-code-bg: rgba(59,130,246,0.1);
            --blog-content-code-color: #93bbfc;
            --blog-content-strong: #f1f5f9;
            --blog-tag-bg: rgba(139,92,246,0.1);
            --blog-tag-color: #a78bfa;
            --blog-cat-bg: rgba(59,130,246,0.12);
            --blog-cat-color: #60a5fa;
            --blog-footer-border: rgba(255,255,255,0.04);
            --blog-comment-border: rgba(255,255,255,0.04);
            --blog-nav-link-hover-bg: rgba(255,255,255,0.06);
            --blog-badge-user-bg: rgba(255,255,255,0.04);
            --blog-search-placeholder: #475569;
            --blog-filter-border: rgba(255,255,255,0.1);
            --blog-filter-bg: rgba(255,255,255,0.03);
            --blog-theme-toggle-bg: rgba(255,255,255,0.06);
            --blog-theme-toggle-color: #94a3b8;
            --blog-theme-toggle-hover: rgba(255,255,255,0.12);
            --blog-select-bg: rgba(255,255,255,0.04);
        }

        [data-theme="light"] {
            --blog-bg: #f8fafc;
            --blog-text: #0f172a;
            --blog-text-primary: #020617;
            --blog-text-secondary: #334155;
            --blog-text-muted: #475569;
            --blog-text-faint: #64748b;
            --blog-nav-bg: rgba(255,255,255,0.95);
            --blog-nav-border: rgba(0,0,0,0.08);
            --blog-card-bg: #ffffff;
            --blog-card-border: rgba(0,0,0,0.08);
            --blog-card-hover-border: rgba(59,130,246,0.4);
            --blog-card-hover-shadow: 0 12px 40px rgba(0,0,0,0.08);
            --blog-card-cover-bg: linear-gradient(135deg, #e2e8f0, #cbd5e1);
            --blog-input-bg: #ffffff;
            --blog-input-border: rgba(0,0,0,0.12);
            --blog-input-text: #1e293b;
            --blog-hero-gradient: linear-gradient(135deg, #0f172a, #334155);
            --blog-link: #2563eb;
            --blog-link-hover: #1d4ed8;
            --blog-modal-bg: #ffffff;
            --blog-modal-overlay: rgba(0,0,0,0.4);
            --blog-content-text: #1e293b;
            --blog-content-code-bg: rgba(59,130,246,0.08);
            --blog-content-code-color: #2563eb;
            --blog-content-strong: #0f172a;
            --blog-tag-bg: rgba(139,92,246,0.08);
            --blog-tag-color: #7c3aed;
            --blog-cat-bg: rgba(59,130,246,0.08);
            --blog-cat-color: #2563eb;
            --blog-footer-border: rgba(0,0,0,0.06);
            --blog-comment-border: rgba(0,0,0,0.06);
            --blog-nav-link-hover-bg: rgba(0,0,0,0.04);
            --blog-badge-user-bg: rgba(0,0,0,0.04);
            --blog-search-placeholder: #94a3b8;
            --blog-filter-border: rgba(0,0,0,0.1);
            --blog-filter-bg: rgba(0,0,0,0.02);
            --blog-theme-toggle-bg: rgba(0,0,0,0.05);
            --blog-theme-toggle-color: #475569;
            --blog-theme-toggle-hover: rgba(0,0,0,0.1);
            --blog-select-bg: #ffffff;
        }

        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: var(--blog-bg); color: var(--blog-text); line-height: 1.7; transition: background 0.3s, color 0.3s; }
        a { color: var(--blog-link); text-decoration: none; transition: color 0.2s; }
        a:hover { color: var(--blog-link-hover); }

        .blog-nav { background: var(--blog-nav-bg); border-bottom: 1px solid var(--blog-nav-border); padding: 0 24px; position: sticky; top: 0; z-index: 100; backdrop-filter: blur(20px); transition: background 0.3s, border-color 0.3s; }
        .blog-nav-inner { max-width: 1200px; margin: 0 auto; display: flex; align-items: center; justify-content: space-between; height: 64px; }
        .blog-logo { font-size: 18px; font-weight: 700; color: var(--blog-text-primary); display: flex; align-items: center; gap: 10px; }
        .blog-logo-icon { width: 32px; height: 32px; background: linear-gradient(135deg, #3b82f6, #8b5cf6); border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: 16px; }
        .blog-nav-links { display: flex; align-items: center; gap: 8px; }
        .blog-nav-links a, .blog-nav-links button { padding: 8px 16px; border-radius: 8px; font-size: 14px; font-weight: 500; cursor: pointer; border: none; background: none; color: var(--blog-text-secondary); transition: all 0.2s; }
        .blog-nav-links a:hover, .blog-nav-links button:hover { color: var(--blog-text-primary); background: var(--blog-nav-link-hover-bg); }
        .blog-nav-btn-primary { background: linear-gradient(135deg, #3b82f6, #8b5cf6) !important; color: #fff !important; }
        .blog-nav-btn-primary:hover { opacity: 0.9 !important; }
        .blog-user-badge { display: flex; align-items: center; gap: 8px; padding: 6px 12px; border-radius: 8px; background: var(--blog-badge-user-bg); font-size: 13px; color: var(--blog-text-secondary); }
        .blog-user-avatar { width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 600; font-size: 12px; color: #fff; }

        .blog-theme-toggle { display: flex; align-items: center; justify-content: center; gap: 6px; height: 36px; padding: 0 14px; border-radius: 20px; border: 1px solid var(--blog-filter-border); background: var(--blog-theme-toggle-bg); color: var(--blog-theme-toggle-color); font-size: 14px; cursor: pointer; transition: all 0.2s; flex-shrink: 0; font-weight: 500; font-family: inherit; }
        .blog-theme-toggle:hover { background: var(--blog-theme-toggle-hover); color: var(--blog-text-primary); border-color: #3b82f6; }
        .blog-theme-toggle-icon { font-size: 16px; line-height: 1; }

        .blog-container { max-width: 1200px; margin: 0 auto; padding: 40px 24px; }
        .blog-hero { text-align: center; padding: 60px 0 40px; }
        .blog-hero h1 { font-size: 42px; font-weight: 800; background: var(--blog-hero-gradient); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; margin-bottom: 12px; }
        .blog-hero p { font-size: 18px; color: var(--blog-text-muted); max-width: 600px; margin: 0 auto; }

        .blog-filters { display: flex; gap: 12px; margin-bottom: 32px; flex-wrap: wrap; align-items: center; }
        .blog-filter-btn { padding: 8px 18px; border-radius: 20px; border: 1px solid var(--blog-filter-border); background: var(--blog-filter-bg); color: var(--blog-text-secondary); font-size: 13px; cursor: pointer; transition: all 0.2s; }
        .blog-filter-btn:hover, .blog-filter-btn.active { background: rgba(59,130,246,0.15); border-color: #3b82f6; color: #60a5fa; }
        .blog-search { flex: 1; min-width: 200px; padding: 10px 16px; border-radius: 10px; border: 1px solid var(--blog-input-border); background: var(--blog-input-bg); color: var(--blog-input-text); font-size: 14px; outline: none; transition: background 0.3s, border-color 0.3s, color 0.3s; }
        .blog-search:focus { border-color: #3b82f6; }
        .blog-search::placeholder { color: var(--blog-search-placeholder); }

        .blog-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 28px; }
        .blog-card { background: var(--blog-card-bg); border: 1px solid var(--blog-card-border); border-radius: 16px; overflow: hidden; transition: all 0.3s; cursor: pointer; }
        .blog-card:hover { border-color: var(--blog-card-hover-border); transform: translateY(-4px); box-shadow: var(--blog-card-hover-shadow); }
        .blog-card-cover { width: 100%; height: 200px; background: var(--blog-card-cover-bg); display: flex; align-items: center; justify-content: center; overflow: hidden; }
        .blog-card-cover img { width: 100%; height: 100%; object-fit: cover; }
        .blog-card-cover-placeholder { font-size: 48px; opacity: 0.3; }
        .blog-card-body { padding: 24px; }
        .blog-card-category { display: inline-block; padding: 4px 12px; border-radius: 12px; background: var(--blog-cat-bg); color: var(--blog-cat-color); font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 12px; }
        .blog-card-title { font-size: 20px; font-weight: 700; color: var(--blog-text-primary); margin-bottom: 8px; line-height: 1.3; }
        .blog-card-excerpt { font-size: 14px; color: var(--blog-text-muted); line-height: 1.6; margin-bottom: 16px; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
        .blog-card-meta { display: flex; align-items: center; gap: 12px; font-size: 12px; color: var(--blog-text-faint); }
        .blog-card-author { display: flex; align-items: center; gap: 6px; }
        .blog-card-author-avatar { width: 24px; height: 24px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 10px; font-weight: 600; color: #fff; }
        .blog-card-dot { width: 3px; height: 3px; border-radius: 50%; background: var(--blog-text-faint); }

        .blog-pagination { display: flex; justify-content: center; gap: 8px; margin-top: 40px; }
        .blog-page-btn { padding: 10px 16px; border-radius: 10px; border: 1px solid var(--blog-filter-border); background: var(--blog-filter-bg); color: var(--blog-text-secondary); font-size: 14px; cursor: pointer; transition: all 0.2s; }
        .blog-page-btn:hover, .blog-page-btn.active { background: rgba(59,130,246,0.15); border-color: #3b82f6; color: #60a5fa; }
        .blog-page-btn:disabled { opacity: 0.4; cursor: not-allowed; }

        .blog-empty { text-align: center; padding: 80px 20px; }
        .blog-empty-icon { font-size: 64px; margin-bottom: 16px; opacity: 0.3; }
        .blog-empty h3 { font-size: 20px; color: var(--blog-text-secondary); margin-bottom: 8px; }
        .blog-empty p { font-size: 14px; color: var(--blog-text-faint); }

        .blog-article { max-width: 800px; margin: 0 auto; padding: 40px 24px; }
        .blog-article-back { display: inline-flex; align-items: center; gap: 6px; color: var(--blog-text-muted); font-size: 14px; margin-bottom: 32px; }
        .blog-article-back:hover { color: var(--blog-text-secondary); }
        .blog-article-category { display: inline-block; padding: 4px 14px; border-radius: 14px; background: var(--blog-cat-bg); color: var(--blog-cat-color); font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 16px; }
        .blog-article h1 { font-size: 36px; font-weight: 800; color: var(--blog-text-primary); line-height: 1.2; margin-bottom: 20px; }
        .blog-article-meta { display: flex; align-items: center; gap: 16px; padding-bottom: 24px; border-bottom: 1px solid var(--blog-card-border); margin-bottom: 32px; font-size: 14px; color: var(--blog-text-muted); flex-wrap: wrap; }
        .blog-article-author-card { display: flex; align-items: center; gap: 10px; }
        .blog-article-author-avatar { width: 40px; height: 40px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 16px; color: #fff; }
        .blog-article-author-info { display: flex; flex-direction: column; }
        .blog-article-author-name { font-weight: 600; color: var(--blog-text); font-size: 14px; }
        .blog-article-author-label { font-size: 12px; color: var(--blog-text-muted); }
        .blog-article-cover { width: 100%; max-height: 440px; border-radius: 16px; overflow: hidden; margin-bottom: 32px; }
        .blog-article-cover img { width: 100%; height: 100%; object-fit: cover; }
        .blog-article-content { font-size: 17px; line-height: 1.9; color: var(--blog-content-text); }
        .blog-article-content h1 { font-size: 28px; margin: 32px 0 16px; }
        .blog-article-content h2 { font-size: 24px; margin: 28px 0 14px; color: var(--blog-text-primary); }
        .blog-article-content h3 { font-size: 20px; margin: 24px 0 12px; color: var(--blog-text); }
        .blog-article-content p { margin-bottom: 18px; }
        .blog-article-content ul, .blog-article-content ol { margin: 16px 0; padding-left: 24px; }
        .blog-article-content li { margin-bottom: 8px; }
        .blog-article-content code { background: var(--blog-content-code-bg); padding: 2px 8px; border-radius: 6px; font-size: 14px; color: var(--blog-content-code-color); }
        .blog-article-content a { color: var(--blog-link); border-bottom: 1px solid rgba(96,165,250,0.3); }
        .blog-article-content strong { color: var(--blog-content-strong); }
        .blog-article-tags { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 32px; padding-top: 24px; border-top: 1px solid var(--blog-card-border); }
        .blog-article-tag { padding: 4px 12px; border-radius: 12px; background: var(--blog-tag-bg); color: var(--blog-tag-color); font-size: 12px; }

        .blog-comments { max-width: 800px; margin: 40px auto 0; padding: 0 24px 60px; }
        .blog-comments-header { font-size: 20px; font-weight: 700; color: var(--blog-text-primary); margin-bottom: 24px; display: flex; align-items: center; gap: 10px; }
        .blog-comments-count { background: var(--blog-cat-bg); color: var(--blog-cat-color); padding: 2px 10px; border-radius: 12px; font-size: 13px; }
        .blog-comment-form { margin-bottom: 32px; }
        .blog-comment-form textarea { width: 100%; min-height: 100px; padding: 16px; border-radius: 12px; border: 1px solid var(--blog-input-border); background: var(--blog-input-bg); color: var(--blog-input-text); font-size: 14px; font-family: inherit; resize: vertical; outline: none; transition: background 0.3s, border-color 0.3s, color 0.3s; }
        .blog-comment-form textarea:focus { border-color: #3b82f6; }
        .blog-comment-form-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 10px; align-items: center; }
        .blog-comment-submit { padding: 10px 24px; border-radius: 10px; border: none; background: linear-gradient(135deg, #3b82f6, #8b5cf6); color: #fff; font-size: 14px; font-weight: 600; cursor: pointer; transition: opacity 0.2s; }
        .blog-comment-submit:hover { opacity: 0.9; }
        .blog-comment-submit:disabled { opacity: 0.5; cursor: not-allowed; }
        .blog-comment-login-hint { font-size: 13px; color: var(--blog-text-muted); }
        .blog-comment { padding: 20px 0; border-bottom: 1px solid var(--blog-comment-border); }
        .blog-comment:last-child { border-bottom: none; }
        .blog-comment-header { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
        .blog-comment-avatar { width: 32px; height: 32px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 600; color: #fff; }
        .blog-comment-author { font-weight: 600; color: var(--blog-text); font-size: 14px; }
        .blog-comment-date { font-size: 12px; color: var(--blog-text-faint); }
        .blog-comment-text { font-size: 14px; color: var(--blog-text-secondary); line-height: 1.6; }

        .blog-modal-overlay { display: none; position: fixed; inset: 0; background: var(--blog-modal-overlay); z-index: 200; align-items: center; justify-content: center; backdrop-filter: blur(4px); }
        .blog-modal-overlay.active { display: flex; }
        .blog-modal { background: var(--blog-modal-bg); border: 1px solid var(--blog-card-border); border-radius: 20px; padding: 40px; width: 90%; max-width: 440px; }
        .blog-modal h2 { font-size: 22px; font-weight: 700; color: var(--blog-text-primary); margin-bottom: 6px; }
        .blog-modal p { font-size: 14px; color: var(--blog-text-muted); margin-bottom: 24px; }
        .blog-modal-tabs { display: flex; gap: 4px; margin-bottom: 24px; background: var(--blog-badge-user-bg); border-radius: 10px; padding: 4px; }
        .blog-modal-tab { flex: 1; padding: 10px; text-align: center; border-radius: 8px; font-size: 14px; font-weight: 500; cursor: pointer; color: var(--blog-text-muted); transition: all 0.2s; border: none; background: none; }
        .blog-modal-tab.active { background: rgba(59,130,246,0.15); color: #60a5fa; }
        .blog-modal-field { margin-bottom: 16px; }
        .blog-modal-field label { display: block; font-size: 13px; color: var(--blog-text-secondary); margin-bottom: 6px; font-weight: 500; }
        .blog-modal-field input { width: 100%; padding: 12px 16px; border-radius: 10px; border: 1px solid var(--blog-input-border); background: var(--blog-input-bg); color: var(--blog-input-text); font-size: 14px; outline: none; transition: background 0.3s, border-color 0.3s, color 0.3s; }
        .blog-modal-field input:focus { border-color: #3b82f6; }
        .blog-modal-submit { width: 100%; padding: 14px; border-radius: 12px; border: none; background: linear-gradient(135deg, #3b82f6, #8b5cf6); color: #fff; font-size: 15px; font-weight: 600; cursor: pointer; margin-top: 8px; transition: opacity 0.2s; }
        .blog-modal-submit:hover { opacity: 0.9; }
        .blog-modal-error { color: #f87171; font-size: 13px; margin-top: 8px; text-align: center; min-height: 18px; }

        .blog-write-page { max-width: 900px; margin: 0 auto; padding: 40px 24px; }
        .blog-write-page h1 { font-size: 28px; font-weight: 700; color: var(--blog-text-primary); margin-bottom: 24px; }
        .blog-write-form-group { margin-bottom: 20px; }
        .blog-write-form-group label { display: block; font-size: 13px; color: var(--blog-text-secondary); margin-bottom: 6px; font-weight: 500; }
        .blog-write-form-group input, .blog-write-form-group textarea, .blog-write-form-group select { width: 100%; padding: 12px 16px; border-radius: 10px; border: 1px solid var(--blog-input-border); background: var(--blog-input-bg); color: var(--blog-input-text); font-size: 14px; outline: none; font-family: inherit; transition: background 0.3s, border-color 0.3s, color 0.3s; }
        .blog-write-form-group input:focus, .blog-write-form-group textarea:focus { border-color: #3b82f6; }
        .blog-write-form-group textarea { min-height: 400px; resize: vertical; line-height: 1.7; }
        .blog-write-form-group select { appearance: auto; -webkit-appearance: auto; }
        .blog-write-form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
        .blog-write-actions { display: flex; gap: 12px; margin-top: 24px; }
        .blog-write-btn { padding: 14px 28px; border-radius: 12px; border: none; font-size: 15px; font-weight: 600; cursor: pointer; transition: all 0.2s; }
        .blog-write-btn-primary { background: linear-gradient(135deg, #3b82f6, #8b5cf6); color: #fff; }
        .blog-write-btn-secondary { background: var(--blog-filter-bg); color: var(--blog-text-secondary); border: 1px solid var(--blog-filter-border); }
        .blog-write-btn:hover { opacity: 0.9; }

        .blog-my-posts { max-width: 900px; margin: 0 auto; padding: 40px 24px; }
        .blog-my-posts h1 { font-size: 28px; font-weight: 700; color: var(--blog-text-primary); margin-bottom: 24px; }
        .blog-my-post-item { display: flex; align-items: center; justify-content: space-between; padding: 16px 20px; background: var(--blog-card-bg); border: 1px solid var(--blog-card-border); border-radius: 12px; margin-bottom: 12px; }
        .blog-my-post-title { font-weight: 600; color: var(--blog-text); font-size: 15px; }
        .blog-my-post-meta { font-size: 12px; color: var(--blog-text-faint); margin-top: 4px; }
        .blog-status-badge { display: inline-block; padding: 3px 10px; border-radius: 10px; font-size: 11px; font-weight: 600; text-transform: uppercase; }
        .blog-status-published { background: rgba(16,185,129,0.15); color: #34d399; }
        .blog-status-pending { background: rgba(245,158,11,0.15); color: #fbbf24; }
        .blog-status-rejected { background: rgba(239,68,68,0.15); color: #f87171; }
        .blog-status-draft { background: rgba(100,116,139,0.15); color: #94a3b8; }

        .blog-footer { border-top: 1px solid var(--blog-footer-border); padding: 32px 24px; text-align: center; margin-top: 40px; transition: border-color 0.3s; }
        .blog-footer p { font-size: 13px; color: var(--blog-text-faint); }
        .blog-footer a { color: var(--blog-link); }

        .blog-guest-name-input { width: 100%; padding: 10px 16px; border-radius: 10px; border: 1px solid var(--blog-input-border); background: var(--blog-input-bg); color: var(--blog-input-text); font-size: 14px; outline: none; margin-bottom: 8px; transition: background 0.3s, border-color 0.3s, color 0.3s; }
        .blog-guest-name-input:focus { border-color: #3b82f6; }

        @media (max-width: 768px) {
            .blog-hero h1 { font-size: 28px; }
            .blog-hero p { font-size: 15px; }
            .blog-grid { grid-template-columns: 1fr; }
            .blog-article h1 { font-size: 26px; }
            .blog-write-form-row { grid-template-columns: 1fr; }
            .blog-nav-links { gap: 4px; }
            .blog-nav-links a, .blog-nav-links button { padding: 6px 10px; font-size: 13px; }
            .blog-theme-toggle { height: 32px; padding: 0 10px; font-size: 12px; }
            .blog-theme-toggle-icon { font-size: 14px; }
        }
    </style>
    <script>
        (function() {
            var saved = localStorage.getItem('blog_theme');
            if (saved === 'light') document.documentElement.setAttribute('data-theme', 'light');
        })();
    </script>
    """


def _blog_nav_html(user=None):
    user_section = ""
    if user:
        initial = (user.get('display_name') or 'U')[0].upper()
        color = user.get('avatar_color', '#3b82f6')
        user_section = f"""
            <div class="blog-user-badge">
                <div class="blog-user-avatar" style="background:{_esc(color)}">{_esc(initial)}</div>
                <span>{_esc(user.get('display_name',''))}</span>
            </div>
            <a href="/blog/my-posts">My Posts</a>
            <a href="/blog/write">Write</a>
            <button onclick="blogLogout()">Logout</button>
        """
    else:
        user_section = """
            <button onclick="openBlogAuth()" class="blog-nav-btn-primary">Sign In</button>
        """

    return f"""
    <nav class="blog-nav">
        <div class="blog-nav-inner">
            <a href="/blog" class="blog-logo">
                <img src="/static/logo.png" alt="EnergyRiskIQ" width="32" height="32" style="border-radius:8px;" />
                EnergyRiskIQ
            </a>
            <div class="blog-nav-links">
                <a href="/blog">Articles</a>
                <a href="/">EnergyRiskIQ</a>
                {user_section}
                <button class="blog-theme-toggle" onclick="toggleBlogTheme()" id="blogThemeBtn" title="Toggle theme"><span class="blog-theme-toggle-icon" id="blogThemeIcon">&#9790;</span><span id="blogThemeLabel">Light</span></button>
            </div>
        </div>
    </nav>
    """


def _blog_auth_modal_html():
    return """
    <div class="blog-modal-overlay" id="blogAuthModal">
        <div class="blog-modal">
            <h2 id="blogAuthTitle">Welcome</h2>
            <p>Sign in or create an account to comment and write articles</p>
            <div class="blog-modal-tabs">
                <button class="blog-modal-tab active" onclick="switchBlogAuthTab('login')">Sign In</button>
                <button class="blog-modal-tab" onclick="switchBlogAuthTab('register')">Create Account</button>
            </div>
            <div id="blogAuthLoginForm">
                <div class="blog-modal-field">
                    <label>Email</label>
                    <input type="email" id="blogLoginEmail" placeholder="you@example.com" />
                </div>
                <div class="blog-modal-field">
                    <label>Password</label>
                    <input type="password" id="blogLoginPassword" placeholder="Your password" />
                </div>
                <button class="blog-modal-submit" onclick="blogLogin()">Sign In</button>
            </div>
            <div id="blogAuthRegisterForm" style="display:none;">
                <div class="blog-modal-field">
                    <label>Display Name</label>
                    <input type="text" id="blogRegName" placeholder="Your name" />
                </div>
                <div class="blog-modal-field">
                    <label>Email</label>
                    <input type="email" id="blogRegEmail" placeholder="you@example.com" />
                </div>
                <div class="blog-modal-field">
                    <label>Password</label>
                    <input type="password" id="blogRegPassword" placeholder="Min 6 characters" />
                </div>
                <button class="blog-modal-submit" onclick="blogRegister()">Create Account</button>
            </div>
            <div class="blog-modal-error" id="blogAuthError"></div>
        </div>
    </div>
    """


def _blog_scripts():
    return """
    <script>
        function openBlogAuth() {
            document.getElementById('blogAuthModal').classList.add('active');
        }
        function closeBlogAuth() {
            document.getElementById('blogAuthModal').classList.remove('active');
            document.getElementById('blogAuthError').textContent = '';
        }
        document.addEventListener('click', function(e) {
            var modal = document.getElementById('blogAuthModal');
            if (modal && e.target === modal) closeBlogAuth();
        });

        function switchBlogAuthTab(tab) {
            var tabs = document.querySelectorAll('.blog-modal-tab');
            tabs.forEach(function(t, i) { t.classList.toggle('active', (tab === 'login' && i === 0) || (tab === 'register' && i === 1)); });
            document.getElementById('blogAuthLoginForm').style.display = tab === 'login' ? 'block' : 'none';
            document.getElementById('blogAuthRegisterForm').style.display = tab === 'register' ? 'block' : 'none';
            document.getElementById('blogAuthError').textContent = '';
        }

        async function blogLogin() {
            var email = document.getElementById('blogLoginEmail').value.trim();
            var password = document.getElementById('blogLoginPassword').value;
            if (!email || !password) { document.getElementById('blogAuthError').textContent = 'Please fill all fields'; return; }
            try {
                var resp = await fetch('/api/blog/auth/login', {
                    method: 'POST', headers: {'Content-Type':'application/json'},
                    body: JSON.stringify({email: email, password: password})
                });
                var data = await resp.json();
                if (data.success) { location.reload(); }
                else { document.getElementById('blogAuthError').textContent = data.error || 'Login failed'; }
            } catch(e) { document.getElementById('blogAuthError').textContent = 'Connection error'; }
        }

        async function blogRegister() {
            var name = document.getElementById('blogRegName').value.trim();
            var email = document.getElementById('blogRegEmail').value.trim();
            var password = document.getElementById('blogRegPassword').value;
            if (!name || !email || !password) { document.getElementById('blogAuthError').textContent = 'Please fill all fields'; return; }
            if (password.length < 6) { document.getElementById('blogAuthError').textContent = 'Password must be at least 6 characters'; return; }
            try {
                var resp = await fetch('/api/blog/auth/register', {
                    method: 'POST', headers: {'Content-Type':'application/json'},
                    body: JSON.stringify({display_name: name, email: email, password: password})
                });
                var data = await resp.json();
                if (data.success) { location.reload(); }
                else { document.getElementById('blogAuthError').textContent = data.error || 'Registration failed'; }
            } catch(e) { document.getElementById('blogAuthError').textContent = 'Connection error'; }
        }

        async function blogLogout() {
            await fetch('/api/blog/auth/logout', {method:'POST'});
            location.href = '/blog';
        }

        document.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') {
                var modal = document.getElementById('blogAuthModal');
                if (modal && modal.classList.contains('active')) {
                    var loginVisible = document.getElementById('blogAuthLoginForm').style.display !== 'none';
                    if (loginVisible) blogLogin();
                    else blogRegister();
                }
            }
        });

        function toggleBlogTheme() {
            var html = document.documentElement;
            var current = html.getAttribute('data-theme');
            var icon = document.getElementById('blogThemeIcon');
            var label = document.getElementById('blogThemeLabel');
            if (current === 'light') {
                html.removeAttribute('data-theme');
                localStorage.setItem('blog_theme', 'dark');
                if (icon) icon.innerHTML = '\u263E';
                if (label) label.textContent = 'Light';
            } else {
                html.setAttribute('data-theme', 'light');
                localStorage.setItem('blog_theme', 'light');
                if (icon) icon.innerHTML = '\u2600';
                if (label) label.textContent = 'Dark';
            }
        }
        (function() {
            var saved = localStorage.getItem('blog_theme');
            var icon = document.getElementById('blogThemeIcon');
            var label = document.getElementById('blogThemeLabel');
            if (saved === 'light') {
                if (icon) icon.innerHTML = '\u2600';
                if (label) label.textContent = 'Dark';
            }
        })();
    </script>
    """


def _blog_page(title, body_html, request: Request):
    user = _get_blog_user(request)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
    <title>{_esc(title)} - EnergyRiskIQ Blog</title>
    <meta name="description" content="Educational articles on energy risk, geopolitics, and market intelligence from EnergyRiskIQ."/>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet"/>
    {_blog_base_styles()}
</head>
<body>
    {_blog_nav_html(user)}
    {body_html}
    <footer class="blog-footer">
        <p>&copy; 2026 <a href="/">EnergyRiskIQ</a>. All rights reserved.</p>
    </footer>
    {_blog_auth_modal_html()}
    {_blog_scripts()}
</body>
</html>"""


@router.get("/blog", response_class=HTMLResponse)
async def blog_home(request: Request, page: int = Query(1, ge=1), category: str = Query(None), search: str = Query(None)):
    posts, total = blog_db.get_published_posts(page=page, per_page=9, category=category, search=search)
    categories = blog_db.get_blog_categories()
    total_pages = max(1, (total + 8) // 9)

    cat_buttons = '<button class="blog-filter-btn' + (' active' if not category or category == 'all' else '') + '" onclick="filterBlog(\'all\')">All</button>'
    for cat in categories:
        active = ' active' if category == cat else ''
        cat_buttons += f'<button class="blog-filter-btn{active}" onclick="filterBlog(\'{_esc(cat)}\')">{_esc(cat)}</button>'

    cards = ""
    for p in posts:
        cover = ""
        if p.get('cover_image'):
            cover = f'<img src="{_esc(p["cover_image"])}" alt="" />'
        else:
            cover = '<div class="blog-card-cover-placeholder">&#x1f4f0;</div>'

        author_initial = (p.get('author_name') or 'A')[0].upper()
        tags_list = [t.strip() for t in (p.get('tags') or '').split(',') if t.strip()]

        cards += f"""
        <article class="blog-card" onclick="location.href='/blog/{_esc(p['slug'])}'">
            <div class="blog-card-cover">{cover}</div>
            <div class="blog-card-body">
                <span class="blog-card-category">{_esc(p.get('category','General'))}</span>
                <h2 class="blog-card-title">{_esc(p['title'])}</h2>
                <p class="blog-card-excerpt">{_esc(p.get('excerpt',''))}</p>
                <div class="blog-card-meta">
                    <div class="blog-card-author">
                        <div class="blog-card-author-avatar" style="background:#3b82f6">{author_initial}</div>
                        {_esc(p.get('author_name','Admin'))}
                    </div>
                    <div class="blog-card-dot"></div>
                    <span>{_format_date_short(p.get('published_at') or p.get('created_at'))}</span>
                    <div class="blog-card-dot"></div>
                    <span>{_get_reading_time(p.get('content',''))}</span>
                </div>
            </div>
        </article>
        """

    if not cards:
        cards = """
        <div class="blog-empty" style="grid-column:1/-1;">
            <div class="blog-empty-icon">&#x1f4dd;</div>
            <h3>No articles yet</h3>
            <p>Check back soon for educational content on energy risk and geopolitics.</p>
        </div>
        """

    search_val = _esc(search) if search else ''
    pagination = ""
    if total_pages > 1:
        pagination = '<div class="blog-pagination">'
        if page > 1:
            pagination += f'<button class="blog-page-btn" onclick="goPage({page - 1})">&larr; Previous</button>'
        for pg in range(1, total_pages + 1):
            if pg == page:
                pagination += f'<button class="blog-page-btn active">{pg}</button>'
            elif abs(pg - page) < 3 or pg == 1 or pg == total_pages:
                pagination += f'<button class="blog-page-btn" onclick="goPage({pg})">{pg}</button>'
        if page < total_pages:
            pagination += f'<button class="blog-page-btn" onclick="goPage({page + 1})">Next &rarr;</button>'
        pagination += '</div>'

    body = f"""
    <div class="blog-container">
        <div class="blog-hero">
            <h1>Energy Intelligence Blog</h1>
            <p>Expert analysis, educational articles, and insights on geopolitical energy risk</p>
        </div>
        <div class="blog-filters">
            {cat_buttons}
            <input class="blog-search" type="text" placeholder="Search articles..." value="{search_val}" onkeydown="if(event.key==='Enter')searchBlog(this.value)" />
        </div>
        <div class="blog-grid">
            {cards}
        </div>
        {pagination}
    </div>
    <script>
        function filterBlog(cat) {{
            var url = '/blog?category=' + encodeURIComponent(cat);
            location.href = url;
        }}
        function searchBlog(q) {{
            var url = '/blog?search=' + encodeURIComponent(q);
            location.href = url;
        }}
        function goPage(p) {{
            var url = new URL(location.href);
            url.searchParams.set('page', p);
            location.href = url.toString();
        }}
    </script>
    """

    return HTMLResponse(_blog_page("Blog", body, request))


@router.get("/blog/write", response_class=HTMLResponse)
async def blog_write_page(request: Request):
    user = _get_blog_user(request)
    if not user:
        return HTMLResponse(_blog_page("Write", """
        <div class="blog-container blog-empty">
            <div class="blog-empty-icon">&#x1f512;</div>
            <h3>Sign in to write articles</h3>
            <p>You need a blog account to submit articles. <a href="#" onclick="openBlogAuth(); return false;">Sign in or create an account</a>.</p>
        </div>
        """, request))

    body = f"""
    <div class="blog-write-page">
        <h1>Write a New Article</h1>
        <p style="color:#64748b;margin-bottom:24px;font-size:14px;">Your article will be reviewed by our editors before publishing.</p>
        <div class="blog-write-form-group">
            <label>Title</label>
            <input type="text" id="writeTitle" placeholder="Enter article title" />
        </div>
        <div class="blog-write-form-group">
            <label>Excerpt / Summary</label>
            <input type="text" id="writeExcerpt" placeholder="A brief summary (shown on cards)" />
        </div>
        <div class="blog-write-form-row">
            <div class="blog-write-form-group">
                <label>Category</label>
                <select id="writeCategory">
                    <option>Energy Markets</option>
                    <option>Geopolitics</option>
                    <option>Risk Management</option>
                    <option>Oil & Gas</option>
                    <option>Renewables</option>
                    <option>Climate & ESG</option>
                    <option>Trading Strategies</option>
                    <option>Industry Analysis</option>
                    <option>General</option>
                </select>
            </div>
            <div class="blog-write-form-group">
                <label>Tags (comma separated)</label>
                <input type="text" id="writeTags" placeholder="e.g. OPEC, crude oil, sanctions" />
            </div>
        </div>
        <div class="blog-write-form-group">
            <label>Cover Image URL (optional)</label>
            <input type="text" id="writeCover" placeholder="https://..." />
        </div>
        <div class="blog-write-form-group">
            <label>Content (Markdown supported)</label>
            <textarea id="writeContent" placeholder="Write your article here. You can use Markdown formatting: **bold**, *italic*, ## headings, - lists, [links](url), \`code\`"></textarea>
        </div>
        <div class="blog-write-actions">
            <button class="blog-write-btn blog-write-btn-primary" onclick="submitArticle()">Submit for Review</button>
            <button class="blog-write-btn blog-write-btn-secondary" onclick="location.href='/blog'">Cancel</button>
        </div>
        <div id="writeError" style="color:#f87171;font-size:14px;margin-top:12px;"></div>
        <div id="writeSuccess" style="color:#34d399;font-size:14px;margin-top:12px;display:none;"></div>
    </div>
    <script>
        async function submitArticle() {{
            var title = document.getElementById('writeTitle').value.trim();
            var content = document.getElementById('writeContent').value.trim();
            var excerpt = document.getElementById('writeExcerpt').value.trim();
            var category = document.getElementById('writeCategory').value;
            var tags = document.getElementById('writeTags').value.trim();
            var cover = document.getElementById('writeCover').value.trim();

            if (!title || !content) {{
                document.getElementById('writeError').textContent = 'Title and content are required';
                return;
            }}
            if (content.length < 100) {{
                document.getElementById('writeError').textContent = 'Content must be at least 100 characters';
                return;
            }}

            try {{
                var resp = await fetch('/api/blog/posts', {{
                    method: 'POST',
                    headers: {{'Content-Type':'application/json'}},
                    body: JSON.stringify({{title:title, content:content, excerpt:excerpt, category:category, tags:tags, cover_image:cover}})
                }});
                var data = await resp.json();
                if (data.success) {{
                    document.getElementById('writeError').textContent = '';
                    document.getElementById('writeSuccess').style.display = 'block';
                    document.getElementById('writeSuccess').textContent = 'Article submitted for review! Redirecting...';
                    setTimeout(function() {{ location.href = '/blog/my-posts'; }}, 2000);
                }} else {{
                    document.getElementById('writeError').textContent = data.error || 'Failed to submit';
                }}
            }} catch(e) {{
                document.getElementById('writeError').textContent = 'Connection error';
            }}
        }}
    </script>
    """
    return HTMLResponse(_blog_page("Write Article", body, request))


@router.get("/blog/my-posts", response_class=HTMLResponse)
async def blog_my_posts_page(request: Request):
    user = _get_blog_user(request)
    if not user:
        return HTMLResponse(_blog_page("My Posts", """
        <div class="blog-container blog-empty">
            <div class="blog-empty-icon">&#x1f512;</div>
            <h3>Sign in to see your posts</h3>
            <p><a href="#" onclick="openBlogAuth(); return false;">Sign in or create an account</a></p>
        </div>
        """, request))

    posts = blog_db.get_posts_by_author(user['id'])
    rows = ""
    for p in posts:
        status_cls = f"blog-status-{p['status']}"
        rejection = ""
        if p['status'] == 'rejected' and p.get('rejection_reason'):
            rejection = f'<div style="font-size:12px;color:#f87171;margin-top:4px;">Reason: {_esc(p["rejection_reason"])}</div>'
        rows += f"""
        <div class="blog-my-post-item">
            <div>
                <div class="blog-my-post-title">{_esc(p['title'])}</div>
                <div class="blog-my-post-meta">{_format_date_short(p['created_at'])} &middot; {p.get('view_count',0)} views</div>
                {rejection}
            </div>
            <span class="blog-status-badge {status_cls}">{p['status']}</span>
        </div>
        """

    if not rows:
        rows = """
        <div class="blog-empty">
            <div class="blog-empty-icon">&#x1f4dd;</div>
            <h3>No articles yet</h3>
            <p><a href="/blog/write">Write your first article</a></p>
        </div>
        """

    body = f"""
    <div class="blog-my-posts">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:24px;">
            <h1>My Articles</h1>
            <a href="/blog/write" class="blog-write-btn blog-write-btn-primary" style="text-decoration:none;display:inline-block;">Write New</a>
        </div>
        {rows}
    </div>
    """
    return HTMLResponse(_blog_page("My Posts", body, request))


@router.get("/blog/{slug}", response_class=HTMLResponse)
async def blog_article_page(slug: str, request: Request):
    post = blog_db.get_post_by_slug(slug)
    if not post:
        return HTMLResponse(_blog_page("Not Found", """
        <div class="blog-container blog-empty">
            <div class="blog-empty-icon">&#x1f50d;</div>
            <h3>Article not found</h3>
            <p><a href="/blog">Back to all articles</a></p>
        </div>
        """, request), status_code=404)

    blog_db.increment_view_count(post['id'])
    comments = blog_db.get_comments_for_post(post['id'])
    user = _get_blog_user(request)

    author_initial = (post.get('author_name') or 'A')[0].upper()
    author_label = 'Admin' if post.get('author_type') == 'admin' else 'Contributor'

    cover_html = ""
    if post.get('cover_image'):
        cover_html = f'<div class="blog-article-cover"><img src="{_esc(post["cover_image"])}" alt="" /></div>'

    tags_html = ""
    tags_list = [t.strip() for t in (post.get('tags') or '').split(',') if t.strip()]
    if tags_list:
        tags_html = '<div class="blog-article-tags">' + ''.join(f'<span class="blog-article-tag">{_esc(t)}</span>' for t in tags_list) + '</div>'

    content_html = _render_markdown_basic(post.get('content', ''))

    comments_html = ""
    for c in comments:
        name = c.get('user_display_name') or c.get('guest_name') or 'Anonymous'
        color = c.get('avatar_color') or '#64748b'
        initial = name[0].upper()
        comments_html += f"""
        <div class="blog-comment">
            <div class="blog-comment-header">
                <div class="blog-comment-avatar" style="background:{_esc(color)}">{_esc(initial)}</div>
                <span class="blog-comment-author">{_esc(name)}</span>
                <span class="blog-comment-date">{_format_date_short(c.get('created_at'))}</span>
            </div>
            <div class="blog-comment-text">{_esc(c.get('content',''))}</div>
        </div>
        """

    comment_form = ""
    if user:
        comment_form = f"""
        <div class="blog-comment-form">
            <textarea id="commentText" placeholder="Share your thoughts..."></textarea>
            <div class="blog-comment-form-actions">
                <button class="blog-comment-submit" onclick="postComment({post['id']})">Post Comment</button>
            </div>
        </div>
        """
    else:
        comment_form = """
        <div class="blog-comment-form">
            <textarea id="commentText" placeholder="Share your thoughts..."></textarea>
            <div style="display:flex;gap:8px;margin-top:8px;">
                <input type="text" id="commentGuestName" placeholder="Your name" style="flex:1;padding:10px 14px;border-radius:10px;border:1px solid rgba(255,255,255,0.1);background:rgba(255,255,255,0.04);color:#e2e8f0;font-size:14px;outline:none;" />
            </div>
            <div class="blog-comment-form-actions">
                <span class="blog-comment-login-hint"><a href="#" onclick="openBlogAuth();return false;">Sign in</a> for a richer experience</span>
                <button class="blog-comment-submit" onclick="postCommentGuest(""" + str(post['id']) + """)">Post Comment</button>
            </div>
        </div>
        """

    body = f"""
    <article class="blog-article">
        <a href="/blog" class="blog-article-back">&larr; Back to articles</a>
        <span class="blog-article-category">{_esc(post.get('category','General'))}</span>
        <h1>{_esc(post['title'])}</h1>
        <div class="blog-article-meta">
            <div class="blog-article-author-card">
                <div class="blog-article-author-avatar" style="background:#3b82f6">{author_initial}</div>
                <div class="blog-article-author-info">
                    <span class="blog-article-author-name">{_esc(post.get('author_name','Admin'))}</span>
                    <span class="blog-article-author-label">{author_label}</span>
                </div>
            </div>
            <span>{_format_date(post.get('published_at') or post.get('created_at'))}</span>
            <span>{_get_reading_time(post.get('content',''))}</span>
            <span>{post.get('view_count',0)} views</span>
        </div>
        {cover_html}
        <div class="blog-article-content">
            {content_html}
        </div>
        {tags_html}
    </article>
    <section class="blog-comments">
        <div class="blog-comments-header">
            Comments <span class="blog-comments-count">{len(comments)}</span>
        </div>
        {comment_form}
        <div id="commentsList">
            {comments_html}
        </div>
    </section>
    <script>
        async function postComment(postId) {{
            var text = document.getElementById('commentText').value.trim();
            if (!text) return;
            try {{
                var resp = await fetch('/api/blog/posts/' + postId + '/comments', {{
                    method: 'POST',
                    headers: {{'Content-Type':'application/json'}},
                    body: JSON.stringify({{content: text}})
                }});
                var data = await resp.json();
                if (data.success) location.reload();
            }} catch(e) {{}}
        }}
        async function postCommentGuest(postId) {{
            var text = document.getElementById('commentText').value.trim();
            var name = document.getElementById('commentGuestName').value.trim();
            if (!text) return;
            if (!name) {{ alert('Please enter your name'); return; }}
            try {{
                var resp = await fetch('/api/blog/posts/' + postId + '/comments', {{
                    method: 'POST',
                    headers: {{'Content-Type':'application/json'}},
                    body: JSON.stringify({{content: text, guest_name: name}})
                }});
                var data = await resp.json();
                if (data.success) location.reload();
            }} catch(e) {{}}
        }}
    </script>
    """

    return HTMLResponse(_blog_page(post['title'], body, request))


# ===== API ENDPOINTS =====

@router.post("/api/blog/auth/register")
async def blog_auth_register(request: Request):
    try:
        body = await request.json()
        display_name = (body.get('display_name') or '').strip()
        email = (body.get('email') or '').strip().lower()
        password = body.get('password') or ''

        if not display_name or not email or not password:
            return JSONResponse({"success": False, "error": "All fields are required"})
        if len(password) < 6:
            return JSONResponse({"success": False, "error": "Password must be at least 6 characters"})
        if len(display_name) > 100:
            return JSONResponse({"success": False, "error": "Display name too long"})

        existing = blog_db.get_blog_user_by_email(email)
        if existing:
            return JSONResponse({"success": False, "error": "Email already registered"})

        user = blog_db.create_blog_user(display_name, email, _hash_password(password))
        token = secrets.token_hex(32)
        expires_at = datetime.utcnow() + timedelta(days=30)
        blog_db.create_blog_session(token, user['id'], expires_at)
        resp = JSONResponse({"success": True})
        resp.set_cookie('blog_token', token, max_age=30*86400, httponly=True, samesite='lax', secure=True)
        return resp
    except Exception as e:
        logger.error(f"Blog register error: {e}")
        return JSONResponse({"success": False, "error": "Registration failed"})


@router.post("/api/blog/auth/login")
async def blog_auth_login(request: Request):
    try:
        body = await request.json()
        email = (body.get('email') or '').strip().lower()
        password = body.get('password') or ''

        user = blog_db.get_blog_user_by_email(email)
        if not user or not _verify_password(password, user['password_hash']):
            return JSONResponse({"success": False, "error": "Invalid email or password"})
        if not user.get('is_active', True):
            return JSONResponse({"success": False, "error": "Account is deactivated"})

        token = secrets.token_hex(32)
        expires_at = datetime.utcnow() + timedelta(days=30)
        blog_db.create_blog_session(token, user['id'], expires_at)
        resp = JSONResponse({"success": True})
        resp.set_cookie('blog_token', token, max_age=30*86400, httponly=True, samesite='lax', secure=True)
        return resp
    except Exception as e:
        logger.error(f"Blog login error: {e}")
        return JSONResponse({"success": False, "error": "Login failed"})


@router.post("/api/blog/auth/logout")
async def blog_auth_logout(request: Request):
    token = request.cookies.get('blog_token')
    if token:
        blog_db.delete_blog_session(token)
    resp = JSONResponse({"success": True})
    resp.delete_cookie('blog_token')
    return resp


@router.post("/api/blog/posts")
async def blog_create_post(request: Request):
    user = _get_blog_user(request)
    if not user:
        return JSONResponse({"success": False, "error": "Sign in required"}, status_code=401)

    try:
        body = await request.json()
        title = (body.get('title') or '').strip()
        content = (body.get('content') or '').strip()
        excerpt = (body.get('excerpt') or '').strip()
        category = (body.get('category') or 'General').strip()
        tags = (body.get('tags') or '').strip()
        cover_image = (body.get('cover_image') or '').strip()

        if not title or not content:
            return JSONResponse({"success": False, "error": "Title and content are required"})
        if len(content) < 100:
            return JSONResponse({"success": False, "error": "Content must be at least 100 characters"})

        slug = _slugify(title)
        existing = blog_db.get_post_by_slug(slug)
        if existing:
            slug = slug + '-' + secrets.token_hex(3)

        if not excerpt:
            excerpt = content[:200].rsplit(' ', 1)[0] + '...' if len(content) > 200 else content

        post = blog_db.create_post(
            title=title, slug=slug, excerpt=excerpt, content=content,
            cover_image=cover_image, category=category, tags=tags,
            author_id=user['id'], author_name=user['display_name'],
            author_type='user', status='pending'
        )
        return JSONResponse({"success": True, "post_id": post['id']})
    except Exception as e:
        logger.error(f"Blog create post error: {e}")
        return JSONResponse({"success": False, "error": "Failed to create post"})


@router.post("/api/blog/posts/{post_id}/comments")
async def blog_add_comment(post_id: int, request: Request):
    try:
        body = await request.json()
        content = (body.get('content') or '').strip()
        guest_name = (body.get('guest_name') or '').strip()

        if not content:
            return JSONResponse({"success": False, "error": "Comment cannot be empty"})
        if len(content) > 2000:
            return JSONResponse({"success": False, "error": "Comment too long (max 2000 characters)"})

        user = _get_blog_user(request)
        user_id = user['id'] if user else None

        if not user_id and not guest_name:
            return JSONResponse({"success": False, "error": "Name is required for guest comments"})

        comment = blog_db.add_comment(post_id, content, user_id=user_id, guest_name=guest_name if not user_id else None)
        return JSONResponse({"success": True, "comment_id": comment['id']})
    except Exception as e:
        logger.error(f"Blog comment error: {e}")
        return JSONResponse({"success": False, "error": "Failed to post comment"})


# ===== ADMIN API ENDPOINTS =====

@router.get("/api/blog/admin/posts")
async def admin_blog_list_posts(request: Request, status: str = Query(None), x_admin_token: Optional[str] = Header(None)):
    from src.api.admin_routes import verify_admin_token
    verify_admin_token(x_admin_token)
    posts = blog_db.get_all_posts_admin(status_filter=status)
    result = []
    for p in posts:
        d = dict(p)
        for k, v in d.items():
            if isinstance(v, datetime):
                d[k] = v.isoformat()
        result.append(d)
    return JSONResponse({"success": True, "posts": result})


@router.get("/api/blog/admin/stats")
async def admin_blog_stats(request: Request, x_admin_token: Optional[str] = Header(None)):
    from src.api.admin_routes import verify_admin_token
    verify_admin_token(x_admin_token)
    stats = blog_db.get_blog_stats()
    return JSONResponse({"success": True, "stats": dict(stats) if stats else {}})


@router.post("/api/blog/admin/posts")
async def admin_blog_create_post(request: Request, x_admin_token: Optional[str] = Header(None)):
    from src.api.admin_routes import verify_admin_token
    verify_admin_token(x_admin_token)
    try:
        body = await request.json()
        title = (body.get('title') or '').strip()
        content = (body.get('content') or '').strip()
        excerpt = (body.get('excerpt') or '').strip()
        category = (body.get('category') or 'General').strip()
        tags = (body.get('tags') or '').strip()
        cover_image = (body.get('cover_image') or '').strip()

        if not title or not content:
            return JSONResponse({"success": False, "error": "Title and content are required"})

        slug = _slugify(title)
        existing = blog_db.get_post_by_slug(slug)
        if existing:
            slug = slug + '-' + secrets.token_hex(3)

        if not excerpt:
            excerpt = content[:200].rsplit(' ', 1)[0] + '...' if len(content) > 200 else content

        post = blog_db.create_post(
            title=title, slug=slug, excerpt=excerpt, content=content,
            cover_image=cover_image, category=category, tags=tags,
            author_id=None, author_name='EnergyRiskIQ',
            author_type='admin', status='published'
        )
        return JSONResponse({"success": True, "post_id": post['id']})
    except Exception as e:
        logger.error(f"Admin blog create error: {e}")
        return JSONResponse({"success": False, "error": "Failed to create post"})


@router.put("/api/blog/admin/posts/{post_id}/status")
async def admin_blog_update_status(post_id: int, request: Request, x_admin_token: Optional[str] = Header(None)):
    from src.api.admin_routes import verify_admin_token
    verify_admin_token(x_admin_token)
    try:
        body = await request.json()
        status = body.get('status')
        rejection_reason = body.get('rejection_reason', '')
        if status not in ('published', 'rejected', 'pending', 'draft'):
            return JSONResponse({"success": False, "error": "Invalid status"})
        post = blog_db.update_post_status(post_id, status, rejection_reason)
        return JSONResponse({"success": True, "post_id": post['id'] if post else None})
    except Exception as e:
        logger.error(f"Admin blog status error: {e}")
        return JSONResponse({"success": False, "error": "Failed to update post status"})


@router.delete("/api/blog/admin/posts/{post_id}")
async def admin_blog_delete_post(post_id: int, request: Request, x_admin_token: Optional[str] = Header(None)):
    from src.api.admin_routes import verify_admin_token
    verify_admin_token(x_admin_token)
    try:
        blog_db.delete_post(post_id)
        return JSONResponse({"success": True})
    except Exception as e:
        logger.error(f"Admin blog delete error: {e}")
        return JSONResponse({"success": False, "error": "Failed to delete post"})


@router.get("/api/blog/admin/posts/{post_id}")
async def admin_blog_get_post(post_id: int, request: Request, x_admin_token: Optional[str] = Header(None)):
    from src.api.admin_routes import verify_admin_token
    verify_admin_token(x_admin_token)
    post = blog_db.get_post_by_id(post_id)
    if not post:
        return JSONResponse({"success": False, "error": "Post not found"}, status_code=404)
    post_dict = dict(post)
    for k, v in post_dict.items():
        if isinstance(v, datetime):
            post_dict[k] = v.isoformat()
    return JSONResponse({"success": True, "post": post_dict})
