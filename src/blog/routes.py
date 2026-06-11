import logging
import json
import bcrypt
import secrets
import re
import os
import uuid
import unicodedata
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Request, Header, Query, UploadFile, File
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
        'avatar_color': session['avatar_color'],
        'bio': session.get('bio') or '',
        'website': session.get('website') or '',
        'avatar_image': session.get('avatar_image') or ''
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


def _strip_user_links(text):
    """Remove hyperlinks from user-authored article content.
    Converts markdown links [label](url) -> label (leaving ![alt](url) images intact)
    and neutralises raw <a> tags. Bare URLs are left as plain (non-clickable) text."""
    if not text:
        return text
    text = re.sub(r'(?<!!)\[([^\]]*)\]\(([^)]+)\)', r'\1', text)
    text = re.sub(r'</?a\b[^>]*>', '', text, flags=re.IGNORECASE)
    return text


def _linkify_bio(text):
    """Escape bio text, then turn bare http(s) URLs into safe clickable links.
    Used for the author bio box where links ARE allowed."""
    if not text:
        return ''
    escaped = _esc(text)
    def _repl(m):
        url = m.group(0)
        trail = ''
        while url and url[-1] in '.,;:)]}\'"':
            trail = url[-1] + trail
            url = url[:-1]
        return f'<a href="{url}" target="_blank" rel="noopener nofollow">{url}</a>{trail}'
    escaped = re.sub(r'https?://[^\s<]+', _repl, escaped)
    return escaped.replace('\n', '<br/>')


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
    def _safe_image(m):
        alt = m.group(1)
        url = m.group(2)
        if url.lower().startswith(('http://', 'https://', '/')):
            return f'<img src="{url}" alt="{alt}" style="max-width:100%;height:auto;border-radius:8px;margin:12px 0;" loading="lazy" />'
        return alt
    text = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', _safe_image, text)
    def _safe_link(m):
        label = m.group(1)
        url = m.group(2)
        if url.lower().startswith(('http://', 'https://', '/')):
            return f'<a href="{url}" target="_blank" rel="noopener">{label}</a>'
        return label
    text = re.sub(r'\[(.+?)\]\((.+?)\)', _safe_link, text)
    _hr_re = re.compile(r'^\s*(?:-\s*){3,}$|^\s*(?:\*\s*){3,}$|^\s*(?:_\s*){3,}$')
    paragraphs = text.split('\n\n')
    result = []
    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        if _hr_re.match(p):
            result.append('<hr style="border:0;border-top:1px solid var(--blog-card-border);margin:32px 0;" />')
            continue
        if p.startswith('<h') or p.startswith('<ul') or p.startswith('<ol') or p.startswith('<img'):
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
        .blog-logo { font-size: 18px; font-weight: 700; color: var(--blog-text-primary); display: flex; align-items: center; gap: 10px; white-space: nowrap; }
        .blog-logo-icon { width: 32px; height: 32px; background: linear-gradient(135deg, #3b82f6, #8b5cf6); border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: 16px; }
        .blog-nav-links { display: flex; align-items: center; gap: 8px; }
        .blog-nav-links a, .blog-nav-links button { padding: 8px 16px; border-radius: 8px; font-size: 14px; font-weight: 500; cursor: pointer; border: none; background: none; color: var(--blog-text-secondary); transition: all 0.2s; }
        .blog-nav-links a:hover, .blog-nav-links button:hover { color: var(--blog-text-primary); background: var(--blog-nav-link-hover-bg); }
        .blog-nav-btn-primary { background: linear-gradient(135deg, #3b82f6, #8b5cf6) !important; color: #fff !important; }
        .blog-nav-btn-primary:hover { opacity: 0.9 !important; }
        .blog-user-badge { display: flex; align-items: center; gap: 8px; padding: 6px 12px; border-radius: 8px; background: var(--blog-badge-user-bg); font-size: 13px; color: var(--blog-text-secondary); }
        .blog-user-avatar { width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 600; font-size: 12px; color: #fff; }

        .blog-hamburger { display: none; align-items: center; justify-content: center; width: 40px; height: 40px; border: none; background: none; cursor: pointer; padding: 0; z-index: 110; }
        .blog-hamburger-icon { display: flex; flex-direction: column; gap: 5px; width: 22px; }
        .blog-hamburger-icon span { display: block; height: 2px; background: var(--blog-text-secondary); border-radius: 2px; transition: all 0.3s; }
        .blog-hamburger.active .blog-hamburger-icon span:nth-child(1) { transform: rotate(45deg) translate(5px, 5px); }
        .blog-hamburger.active .blog-hamburger-icon span:nth-child(2) { opacity: 0; }
        .blog-hamburger.active .blog-hamburger-icon span:nth-child(3) { transform: rotate(-45deg) translate(5px, -5px); }

        .blog-mobile-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.5); z-index: 99; }
        .blog-mobile-overlay.active { display: block; }

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

        .blog-search-bar { margin-bottom: 16px; display: flex; justify-content: center; }
        .blog-search { min-width: 400px; max-width: 600px; width: 100%; }
        .blog-cat-links-row { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 28px; align-items: center; justify-content: center; }
        .blog-cat-link { display: inline-flex; align-items: center; gap: 6px; padding: 6px 14px; border-radius: 20px; font-size: 13px; font-weight: 500; color: var(--blog-text-secondary); background: var(--blog-filter-bg); border: 1px solid var(--blog-filter-border); transition: all 0.2s; text-decoration: none; white-space: nowrap; }
        .blog-cat-link:hover { border-color: #3b82f6; color: var(--blog-text-primary); background: rgba(59,130,246,0.08); }
        .blog-cat-link.active { background: rgba(59,130,246,0.15); border-color: #3b82f6; color: #60a5fa; }
        .blog-cat-link-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
        .blog-cat-link-count { font-size: 11px; background: rgba(255,255,255,0.08); padding: 1px 6px; border-radius: 10px; color: var(--blog-text-muted); }
        [data-theme="light"] .blog-cat-link-count { background: rgba(0,0,0,0.06); }
        .blog-cat-hero-badge { display: inline-block; padding: 6px 18px; border-radius: 20px; font-size: 13px; font-weight: 600; margin-bottom: 12px; letter-spacing: 0.5px; text-transform: uppercase; }

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
        .blog-author-bio { display: flex; gap: 18px; align-items: flex-start; margin-top: 40px; padding: 24px; border-radius: 16px; background: var(--blog-card-bg); border: 1px solid var(--blog-card-border); }
        .blog-author-bio-img { width: 72px; height: 72px; border-radius: 50%; object-fit: cover; flex-shrink: 0; border: 2px solid var(--blog-card-border); }
        .blog-author-bio-initial { width: 72px; height: 72px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 28px; font-weight: 700; color: #fff; flex-shrink: 0; }
        .blog-author-bio-body { flex: 1; min-width: 0; }
        .blog-author-bio-label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--blog-text-faint); font-weight: 600; margin-bottom: 4px; }
        .blog-author-bio-name { font-size: 18px; font-weight: 700; color: var(--blog-text-primary); margin-bottom: 8px; }
        .blog-author-bio-text { font-size: 14px; color: var(--blog-text-secondary); line-height: 1.6; margin: 0 0 10px 0; word-break: break-word; }
        .blog-author-bio-link { display: inline-flex; align-items: center; gap: 6px; font-size: 14px; font-weight: 600; color: #60a5fa; text-decoration: none; }
        .blog-author-bio-link:hover { text-decoration: underline; }

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
        .bp-avatar-row { display: flex; gap: 20px; align-items: center; margin-bottom: 24px; }
        .bp-avatar-wrap { position: relative; width: 88px; height: 88px; flex-shrink: 0; }
        .bp-avatar-initial { width: 88px; height: 88px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 34px; font-weight: 700; color: #fff; }
        .bp-avatar-preview { position: absolute; inset: 0; width: 88px; height: 88px; border-radius: 50%; object-fit: cover; border: 2px solid var(--blog-card-border); }
        .bw-toolbar { display: flex; flex-wrap: wrap; gap: 2px; padding: 6px 8px; background: var(--blog-filter-bg); border: 1px solid var(--blog-input-border); border-bottom: none; border-radius: 10px 10px 0 0; }
        .bw-tbtn { padding: 6px 11px; border: none; border-radius: 5px; background: var(--blog-theme-toggle-bg); color: var(--blog-text-secondary); font-size: 13px; cursor: pointer; line-height: 1; transition: background .15s, color .15s; }
        .bw-tbtn:hover { background: var(--blog-nav-link-hover-bg); color: var(--blog-text-primary); }
        .bw-tbtn-disabled, .bw-tbtn-disabled:hover { opacity: 0.35; cursor: not-allowed; background: var(--blog-theme-toggle-bg); color: var(--blog-text-secondary); }
        .bw-tsep { width: 1px; background: var(--blog-input-border); margin: 2px 4px; }
        .bw-content { border-radius: 0 0 10px 10px !important; font-family: ui-monospace, SFMono-Regular, Menlo, monospace !important; min-height: 360px !important; }
        .bw-toolbar-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; }
        .bw-preview-btn { padding: 5px 14px; border-radius: 6px; border: 1px solid rgba(59,130,246,0.3); background: rgba(59,130,246,0.1); color: #60a5fa; font-size: 12px; font-weight: 500; cursor: pointer; }
        .bw-upload-label { padding: 8px 16px; border-radius: 8px; border: 1px dashed rgba(139,92,246,0.45); background: rgba(139,92,246,0.08); color: #a78bfa; font-size: 13px; cursor: pointer; display: inline-flex; align-items: center; gap: 6px; }
        .bw-img-label { padding: 8px 16px; border-radius: 8px; border: 1px dashed rgba(59,130,246,0.45); background: rgba(59,130,246,0.08); color: #60a5fa; font-size: 13px; cursor: pointer; display: inline-flex; align-items: center; gap: 6px; }
        .bw-hint { font-size: 11px; color: var(--blog-text-faint); }
        .bw-cover-preview { display: none; margin-bottom: 8px; position: relative; width: 220px; border: 1px solid var(--blog-input-border); border-radius: 10px; overflow: hidden; }
        .bw-cover-preview img { display: block; width: 100%; height: auto; }
        .bw-x { position: absolute; top: 6px; right: 6px; width: 26px; height: 26px; border-radius: 6px; border: none; background: rgba(15,23,42,0.85); color: #f87171; font-size: 15px; line-height: 1; cursor: pointer; }
        .bw-section { margin-bottom: 20px; padding: 16px; background: var(--blog-filter-bg); border: 1px solid var(--blog-input-border); border-radius: 12px; }
        .bw-row { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
        .bw-emoji-panel { display: none; padding: 8px; background: var(--blog-card-bg); border: 1px solid var(--blog-input-border); border-top: none; max-height: 180px; overflow-y: auto; }
        .bw-emoji-tab { padding: 3px 8px; border: none; border-radius: 4px; font-size: 11px; cursor: pointer; background: var(--blog-theme-toggle-bg); color: var(--blog-text-secondary); }
        .bw-emoji-tab.active { background: rgba(59,130,246,0.2); color: #60a5fa; font-weight: 600; }
        .bw-emoji-btn { padding: 4px; border: none; background: none; font-size: 20px; cursor: pointer; border-radius: 4px; line-height: 1; }
        .bw-modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); z-index: 9999; overflow-y: auto; }
        .bw-modal-inner { max-width: 800px; margin: 40px auto; background: var(--blog-bg); border: 1px solid var(--blog-card-border); border-radius: 16px; padding: 32px; position: relative; }

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
            .blog-hamburger { display: flex; }
            .blog-nav { padding: 0 16px; }
            .blog-nav-inner { height: 56px; }
            .blog-nav-links { position: fixed; top: 0; right: -280px; width: 280px; height: 100vh; background: var(--blog-nav-bg); backdrop-filter: blur(20px); flex-direction: column; align-items: stretch; gap: 0; padding: 72px 16px 24px; z-index: 105; transition: right 0.3s ease; border-left: 1px solid var(--blog-nav-border); overflow-y: auto; }
            .blog-nav-links.open { right: 0; }
            .blog-nav-links a, .blog-nav-links button { padding: 14px 16px; font-size: 15px; border-radius: 10px; text-align: left; width: 100%; }
            .blog-nav-btn-primary { margin-top: 8px; text-align: center !important; border-radius: 10px !important; padding: 14px 16px !important; }
            .blog-user-badge { margin-bottom: 8px; padding: 12px 16px; border-radius: 10px; }
            .blog-theme-toggle { margin-top: 8px; height: 44px; padding: 0 16px; font-size: 14px; border-radius: 10px; justify-content: center; width: 100%; }
            .blog-theme-toggle-icon { font-size: 16px; }

            .blog-hero { padding: 40px 0 24px; }
            .blog-hero h1 { font-size: 28px; }
            .blog-hero p { font-size: 15px; }
            .blog-container { padding: 24px 16px; }
            .blog-grid { grid-template-columns: 1fr; gap: 20px; }
            .blog-card-body { padding: 20px; }
            .blog-filters { gap: 8px; margin-bottom: 24px; }
            .blog-filter-btn { padding: 6px 14px; font-size: 12px; }
            .blog-search { min-width: 100%; max-width: 100%; padding: 10px 14px; font-size: 14px; }
            .blog-cat-links-row { gap: 6px; margin-bottom: 20px; }
            .blog-cat-link { padding: 5px 10px; font-size: 12px; }
            .blog-cat-hero-badge { font-size: 11px; padding: 4px 14px; }
            .blog-pagination { gap: 6px; margin-top: 32px; }
            .blog-page-btn { padding: 8px 12px; font-size: 13px; }

            .blog-article { padding: 24px 16px; }
            .blog-article h1 { font-size: 24px; }
            .blog-article-meta { gap: 10px; font-size: 13px; }
            .blog-article-content { font-size: 16px; line-height: 1.8; }
            .blog-article-cover { border-radius: 12px; }
            .blog-article-tags { gap: 6px; }

            .blog-comments { padding: 0 16px 40px; }
            .blog-comment-form textarea { min-height: 80px; padding: 12px; }

            .blog-write-page { padding: 24px 16px; }
            .blog-write-page h1 { font-size: 22px; }
            .blog-write-form-row { grid-template-columns: 1fr; }
            .blog-write-form-group textarea { min-height: 300px; }
            .blog-write-actions { flex-direction: column; }
            .blog-write-btn { width: 100%; text-align: center; }

            .blog-my-posts { padding: 24px 16px; }
            .blog-my-posts h1 { font-size: 22px; }
            .blog-my-post-item { flex-direction: column; align-items: flex-start; gap: 10px; padding: 14px 16px; }

            .blog-modal { padding: 28px 24px; width: 95%; }
            .blog-modal h2 { font-size: 20px; }

            .blog-footer { padding: 24px 16px; }
            .blog-logo { font-size: 16px; }
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
            <a href="/blog/account">Profile</a>
            <button onclick="blogLogout()">Logout</button>
        """
    else:
        user_section = """
            <button onclick="openBlogAuth()" class="blog-nav-btn-primary">Sign In</button>
        """

    return f"""
    <div class="blog-mobile-overlay" id="blogMobileOverlay" onclick="closeBlogMenu()"></div>
    <nav class="blog-nav">
        <div class="blog-nav-inner">
            <a href="/blog" class="blog-logo">
                <img src="/static/logo.png" alt="EnergyRiskIQ" width="32" height="32" style="border-radius:8px;" />
                EnergyRiskIQ
            </a>
            <div class="blog-nav-links" id="blogNavLinks">
                <a href="/blog" onclick="closeBlogMenu()">Articles</a>
                <a href="/" onclick="closeBlogMenu()">EnergyRiskIQ</a>
                {user_section}
                <button class="blog-theme-toggle" onclick="toggleBlogTheme()" id="blogThemeBtn" title="Toggle theme"><span class="blog-theme-toggle-icon" id="blogThemeIcon">&#9790;</span><span id="blogThemeLabel">Light</span></button>
            </div>
            <button class="blog-hamburger" id="blogHamburger" onclick="toggleBlogMenu()" aria-label="Menu">
                <div class="blog-hamburger-icon"><span></span><span></span><span></span></div>
            </button>
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

        function toggleBlogMenu() {
            var nav = document.getElementById('blogNavLinks');
            var hamburger = document.getElementById('blogHamburger');
            var overlay = document.getElementById('blogMobileOverlay');
            if (nav) nav.classList.toggle('open');
            if (hamburger) hamburger.classList.toggle('active');
            if (overlay) overlay.classList.toggle('active');
            document.body.style.overflow = nav && nav.classList.contains('open') ? 'hidden' : '';
        }
        function closeBlogMenu() {
            var nav = document.getElementById('blogNavLinks');
            var hamburger = document.getElementById('blogHamburger');
            var overlay = document.getElementById('blogMobileOverlay');
            if (nav) nav.classList.remove('open');
            if (hamburger) hamburger.classList.remove('active');
            if (overlay) overlay.classList.remove('active');
            document.body.style.overflow = '';
        }

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


def _render_category_links(categories, active_slug=None):
    links = f'<a href="/blog" class="blog-cat-link{" active" if not active_slug else ""}">'
    links += '<span class="blog-cat-link-dot" style="background:#94a3b8;"></span>All</a>'
    for cat in categories:
        is_active = ' active' if active_slug == cat.get('slug') else ''
        color = _esc(cat.get('color', '#3b82f6'))
        slug = _esc(cat.get('slug', ''))
        name = _esc(cat.get('name', ''))
        count = cat.get('post_count', 0)
        count_badge = f' <span class="blog-cat-link-count">{count}</span>' if count > 0 else ''
        links += f'<a href="/blog/{slug}" class="blog-cat-link{is_active}">'
        links += f'<span class="blog-cat-link-dot" style="background:{color};"></span>{name}{count_badge}</a>'
    return links


def _get_cat_slug_for_post(post, cat_slug_map=None):
    cat_name = post.get('category', 'General')
    if cat_slug_map and cat_name in cat_slug_map:
        return cat_slug_map[cat_name]
    import re
    return re.sub(r'[^a-z0-9]+', '-', cat_name.lower()).strip('-') or 'general'


def _render_blog_cards(posts, cat_slug_map=None):
    if cat_slug_map is None:
        cat_slug_map = blog_db.get_category_slug_map()
    cards = ""
    for p in posts:
        cover = ""
        if p.get('cover_image'):
            cover = f'<img src="{_esc(p["cover_image"])}" alt="" />'
        else:
            cover = '<div class="blog-card-cover-placeholder">&#x1f4f0;</div>'

        author_initial = (p.get('author_name') or 'A')[0].upper()
        c_slug = _get_cat_slug_for_post(p, cat_slug_map)

        cards += f"""
        <article class="blog-card" onclick="location.href='/blog/{_esc(c_slug)}/{_esc(p['slug'])}'">
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
    return cards


def _render_pagination(page, total_pages, base_url="/blog"):
    if total_pages <= 1:
        return ""
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
    return pagination


@router.get("/blog/uploads/{filename}")
async def serve_blog_image(filename: str):
    try:
        row = blog_db.execute_one(
            "SELECT image_data, content_type FROM blog_images WHERE filename = %s", (filename,)
        )
        if not row:
            return JSONResponse({"error": "Image not found"}, status_code=404)
        from fastapi.responses import Response
        return Response(
            content=bytes(row['image_data']),
            media_type=row['content_type'],
            headers={"Cache-Control": "public, max-age=31536000, immutable"}
        )
    except Exception as e:
        logger.error(f"Blog image serve error: {e}")
        return JSONResponse({"error": "Image not found"}, status_code=404)


@router.get("/blog", response_class=HTMLResponse)
async def blog_home(request: Request, page: int = Query(1, ge=1), category: str = Query(None), search: str = Query(None)):
    blog_db.refresh_category_post_counts()
    posts, total = blog_db.get_published_posts(page=page, per_page=9, category=category, search=search)
    categories = blog_db.get_blog_categories()
    total_pages = max(1, (total + 8) // 9)

    category_links = _render_category_links(categories)
    cards = _render_blog_cards(posts)

    if not cards:
        cards = """
        <div class="blog-empty" style="grid-column:1/-1;">
            <div class="blog-empty-icon">&#x1f4dd;</div>
            <h3>No articles yet</h3>
            <p>Check back soon for educational content on energy risk and geopolitics.</p>
        </div>
        """

    search_val = _esc(search) if search else ''
    pagination = _render_pagination(page, total_pages)

    body = f"""
    <div class="blog-container">
        <div class="blog-hero">
            <h1>Energy Intelligence Blog</h1>
            <p>Expert analysis, educational articles, and insights on geopolitical energy risk</p>
        </div>
        <div class="blog-search-bar">
            <input class="blog-search" type="text" placeholder="Search articles..." value="{search_val}" onkeydown="if(event.key==='Enter')searchBlog(this.value)" />
        </div>
        <div class="blog-cat-links-row">
            {category_links}
        </div>
        <div class="blog-grid">
            {cards}
        </div>
        {pagination}
    </div>
    <script>
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




_BLOG_WRITE_SCRIPT = r"""
<script>
var _bwImages = [];
var _bwReplaceIdx = null;
var _bwEmojiCat = 'Smileys';
var _bwEmoji = {
    'Smileys': ['\u{1F600}','\u{1F603}','\u{1F604}','\u{1F601}','\u{1F606}','\u{1F605}','\u{1F602}','\u{1F923}','\u{1F60A}','\u{1F607}','\u{1F642}','\u{1F643}','\u{1F609}','\u{1F60C}','\u{1F60D}','\u{1F618}','\u{1F617}','\u{1F61A}','\u{1F60B}','\u{1F61B}','\u{1F914}','\u{1F928}','\u{1F610}','\u{1F611}','\u{1F636}','\u{1F60F}','\u{1F612}','\u{1F644}','\u{1F62E}','\u{1F627}','\u{1F622}','\u{1F62D}','\u{1F624}','\u{1F620}','\u{1F621}'],
    'Gestures': ['\u{1F44D}','\u{1F44E}','\u{1F44C}','\u{270C}\u{FE0F}','\u{1F91E}','\u{1F44A}','\u{270A}','\u{1F91B}','\u{1F91C}','\u{1F44F}','\u{1F64C}','\u{1F450}','\u{1F932}','\u{1F91D}','\u{1F64F}','\u{270D}\u{FE0F}','\u{1F4AA}','\u{1F44B}','\u{1F590}\u{FE0F}','\u{270B}','\u{1F596}','\u{1F44E}','\u{1F446}','\u{1F447}','\u{1F448}','\u{1F449}','\u{261D}\u{FE0F}'],
    'Objects': ['\u{1F4A1}','\u{1F4D6}','\u{1F4DD}','\u{1F4CA}','\u{1F4C8}','\u{1F4C9}','\u{1F4B0}','\u{1F4B5}','\u{1F4B3}','\u{1F4B8}','\u{26A1}','\u{1F525}','\u{1F4A7}','\u{1F30A}','\u{2699}\u{FE0F}','\u{1F527}','\u{1F528}','\u{1F6E0}\u{FE0F}','\u{1F4CC}','\u{1F4CE}','\u{1F517}','\u{1F4C5}','\u{23F0}','\u{231B}','\u{1F50B}','\u{1F4F1}','\u{1F4BB}','\u{1F5A5}\u{FE0F}','\u{2709}\u{FE0F}','\u{1F4E7}'],
    'Energy': ['\u{26FD}','\u{1F6E2}\u{FE0F}','\u{1F3ED}','\u{26A1}','\u{1F50C}','\u{1F50B}','\u{2600}\u{FE0F}','\u{1F30D}','\u{1F30E}','\u{1F30F}','\u{1F4A8}','\u{1F525}','\u{2744}\u{FE0F}','\u{1F321}\u{FE0F}','\u{2693}','\u{1F6A2}','\u{2708}\u{FE0F}','\u{1F69B}','\u{1F3D7}\u{FE0F}','\u{1F4E6}'],
    'Symbols': ['\u{2705}','\u{274C}','\u{26A0}\u{FE0F}','\u{2757}','\u{2753}','\u{1F4AF}','\u{1F53A}','\u{1F53B}','\u{2B06}\u{FE0F}','\u{2B07}\u{FE0F}','\u{27A1}\u{FE0F}','\u{2B05}\u{FE0F}','\u{1F504}','\u{267B}\u{FE0F}','\u{2728}','\u{2B50}','\u{1F31F}','\u{1F4A5}','\u{1F3AF}','\u{1F6A8}','\u{2696}\u{FE0F}','\u{1F536}','\u{1F537}'],
    'Flags': ['\u{1F1FA}\u{1F1F8}','\u{1F1EA}\u{1F1FA}','\u{1F1EC}\u{1F1E7}','\u{1F1F7}\u{1F1FA}','\u{1F1E8}\u{1F1F3}','\u{1F1F8}\u{1F1E6}','\u{1F1EF}\u{1F1F5}','\u{1F1E9}\u{1F1EA}','\u{1F1EB}\u{1F1F7}','\u{1F3F3}\u{FE0F}','\u{1F3F4}','\u{1F6A9}']
};

function bwEsc(s) {
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function bwMdInsert(type) {
    var ta = document.getElementById('writeContent');
    var start = ta.selectionStart, end = ta.selectionEnd;
    var text = ta.value;
    var sel = text.substring(start, end);
    var before = text.substring(0, start);
    var after = text.substring(end);
    var insert = '', cursorOffset = 0;
    switch(type) {
        case 'bold': insert = '**' + (sel || 'bold text') + '**'; cursorOffset = sel ? insert.length : 2; break;
        case 'italic': insert = '*' + (sel || 'italic text') + '*'; cursorOffset = sel ? insert.length : 1; break;
        case 'underline': insert = '<u>' + (sel || 'underlined text') + '</u>'; cursorOffset = sel ? insert.length : 3; break;
        case 'h1': insert = '\n# ' + (sel || 'Heading 1') + '\n'; cursorOffset = insert.length; break;
        case 'h2': insert = '\n## ' + (sel || 'Heading 2') + '\n'; cursorOffset = insert.length; break;
        case 'h3': insert = '\n### ' + (sel || 'Heading 3') + '\n'; cursorOffset = insert.length; break;
        case 'ul': insert = '\n- ' + (sel || 'List item') + '\n'; cursorOffset = insert.length; break;
        case 'ol': insert = '\n1. ' + (sel || 'List item') + '\n'; cursorOffset = insert.length; break;
        case 'indent': insert = '    ' + (sel || ''); cursorOffset = insert.length; break;
        case 'link': return;
        case 'quote': insert = '\n> ' + (sel || 'Quote') + '\n'; cursorOffset = insert.length; break;
        case 'code': insert = '\n```\n' + (sel || 'code') + '\n```\n'; cursorOffset = insert.length; break;
        case 'hr': insert = '\n\n---\n\n'; cursorOffset = insert.length; break;
    }
    ta.value = before + insert + after;
    ta.focus();
    ta.selectionStart = ta.selectionEnd = start + cursorOffset;
}

function bwSyncCover() {
    var url = document.getElementById('writeCover').value.trim();
    var wrap = document.getElementById('writeCoverPreview');
    var img = document.getElementById('writeCoverPreviewImg');
    if (url) {
        img.onerror = function() { bwCoverStatus('Could not load image from that URL', true); };
        img.src = url;
        wrap.style.display = 'block';
    } else {
        img.onerror = null; img.src = ''; wrap.style.display = 'none';
    }
}
function bwRemoveCover() {
    document.getElementById('writeCover').value = '';
    bwSyncCover();
    var inp = document.getElementById('writeCoverFile'); if (inp) inp.value = '';
}
function bwCoverStatus(msg, isErr) {
    var el = document.getElementById('writeCoverStatus');
    el.style.display = 'inline'; el.style.color = isErr ? '#f87171' : '#34d399'; el.textContent = msg;
    if (!isErr) setTimeout(function(){ el.style.display='none'; }, 3000);
}
async function bwHandleCoverSelect(input) {
    if (!input.files || !input.files[0]) return;
    var file = input.files[0];
    if (file.size > 1572864) { bwCoverStatus('Image must be under 1.5 MB', true); input.value=''; return; }
    if (['image/jpeg','image/png','image/gif','image/webp'].indexOf(file.type) === -1) { bwCoverStatus('Only JPEG, PNG, GIF, WebP allowed', true); input.value=''; return; }
    bwCoverStatus('Uploading...', false);
    var fd = new FormData(); fd.append('file', file);
    try {
        var resp = await fetch('/api/blog/upload-image', { method:'POST', body: fd });
        var data = await resp.json();
        if (data.success) { document.getElementById('writeCover').value = data.url; bwSyncCover(); bwCoverStatus('Cover image uploaded!', false); }
        else { bwCoverStatus(data.error || 'Upload failed', true); }
    } catch(e) { bwCoverStatus('Upload failed - connection error', true); }
    input.value = '';
}

function bwToggleImageUpload() {
    var s = document.getElementById('writeImageSection');
    s.style.display = (s.style.display === 'none' || !s.style.display) ? 'block' : 'none';
}
function bwImageStatus(msg, isErr) {
    var el = document.getElementById('writeImageStatus');
    el.style.display='block'; el.style.color = isErr ? '#f87171' : '#34d399'; el.textContent = msg;
    if (!isErr) setTimeout(function(){ el.style.display='none'; }, 3000);
}
async function bwHandleImageSelect(input) {
    if (!input.files || !input.files[0]) return;
    var file = input.files[0];
    if (_bwReplaceIdx === null && _bwImages.length >= 3) { bwImageStatus('Maximum 3 images per article', true); input.value=''; return; }
    if (file.size > 1572864) { bwImageStatus('Image must be under 1.5 MB', true); input.value=''; return; }
    if (['image/jpeg','image/png','image/gif','image/webp'].indexOf(file.type) === -1) { bwImageStatus('Only JPEG, PNG, GIF, WebP allowed', true); input.value=''; return; }
    bwImageStatus('Uploading...', false);
    var fd = new FormData(); fd.append('file', file);
    try {
        var resp = await fetch('/api/blog/upload-image', { method:'POST', body: fd });
        var data = await resp.json();
        if (data.success) {
            if (_bwReplaceIdx !== null && _bwReplaceIdx < _bwImages.length) {
                var old = _bwImages[_bwReplaceIdx];
                var ta = document.getElementById('writeContent');
                ta.value = ta.value.split('![image](' + old.url + ')').join('![image](' + data.url + ')');
                _bwImages[_bwReplaceIdx] = { url: data.url, filename: data.filename };
                _bwReplaceIdx = null;
                bwImageStatus('Image replaced!', false);
            } else {
                _bwImages.push({ url: data.url, filename: data.filename });
                bwImageStatus('Uploaded! Click "Insert" to add it to your article.', false);
            }
            bwRenderImages();
        } else { bwImageStatus(data.error || 'Upload failed', true); }
    } catch(e) { bwImageStatus('Upload failed - connection error', true); }
    input.value = '';
}
function bwRenderImages() {
    var c = document.getElementById('writeImageList');
    document.getElementById('writeImageCount').textContent = _bwImages.length + ' / 3 images';
    var html = '';
    _bwImages.forEach(function(img, idx) {
        html += '<div style="position:relative;border:1px solid var(--blog-input-border);border-radius:8px;overflow:hidden;width:120px;">';
        html += '<img src="' + img.url + '" style="width:120px;height:80px;object-fit:cover;display:block;" />';
        html += '<div style="display:flex;gap:2px;padding:4px;">';
        html += '<button type="button" onclick="bwInsertImage(' + idx + ')" style="flex:1;padding:3px;border:none;border-radius:4px;background:rgba(59,130,246,0.2);color:#60a5fa;font-size:10px;cursor:pointer;">Insert</button>';
        html += '<button type="button" onclick="bwReplaceImage(' + idx + ')" style="padding:3px 6px;border:none;border-radius:4px;background:rgba(234,179,8,0.2);color:#eab308;font-size:10px;cursor:pointer;">Replace</button>';
        html += '<button type="button" onclick="bwRemoveImage(' + idx + ')" style="padding:3px 6px;border:none;border-radius:4px;background:rgba(239,68,68,0.2);color:#f87171;font-size:10px;cursor:pointer;">&times;</button>';
        html += '</div></div>';
    });
    c.innerHTML = html;
}
function bwInsertImage(idx) {
    var img = _bwImages[idx]; if (!img) return;
    var ta = document.getElementById('writeContent');
    var pos = ta.selectionStart; var text = ta.value;
    var insert = '\n![image](' + img.url + ')\n';
    ta.value = text.substring(0,pos) + insert + text.substring(pos);
    ta.focus(); ta.selectionStart = ta.selectionEnd = pos + insert.length;
    bwImageStatus('Image inserted into article.', false);
}
function bwReplaceImage(idx) {
    _bwReplaceIdx = idx;
    document.getElementById('writeImageFile').click();
}
function bwRemoveImage(idx) {
    var img = _bwImages[idx];
    if (img) {
        var ta = document.getElementById('writeContent');
        ta.value = ta.value.split('![image](' + img.url + ')').join('');
        while (ta.value.indexOf('\n\n\n') !== -1) { ta.value = ta.value.split('\n\n\n').join('\n\n'); }
    }
    _bwImages.splice(idx,1); bwRenderImages();
}

function bwToggleEmoji() {
    var p = document.getElementById('writeEmojiPanel');
    if (p.style.display === 'none' || !p.style.display) { p.style.display='block'; bwRenderEmoji(); }
    else { p.style.display='none'; }
}
function bwRenderEmoji() {
    var tabsEl = document.getElementById('writeEmojiTabs');
    var gridEl = document.getElementById('writeEmojiGrid');
    var cats = Object.keys(_bwEmoji);
    var th = '';
    cats.forEach(function(cat){ var a = cat===_bwEmojiCat; th += '<button type="button" class="bw-emoji-tab' + (a?' active':'') + '" onclick="_bwEmojiCat=\'' + cat + '\';bwRenderEmoji();">' + cat + '</button>'; });
    tabsEl.innerHTML = th;
    var ems = _bwEmoji[_bwEmojiCat] || [];
    var gh = '';
    ems.forEach(function(em){ gh += '<button type="button" class="bw-emoji-btn" onclick="bwInsertEmoji(\'' + em + '\')">' + em + '</button>'; });
    gridEl.innerHTML = gh;
}
function bwInsertEmoji(em) {
    var ta = document.getElementById('writeContent');
    var pos = ta.selectionStart; var text = ta.value;
    ta.value = text.substring(0,pos) + em + text.substring(pos);
    ta.focus(); ta.selectionStart = ta.selectionEnd = pos + em.length;
}

function bwRenderMd(md) {
    var html = bwEsc(md);
    html = html.replace(/```([\s\S]*?)```/g, function(m, code){ return '<pre style="background:var(--blog-content-code-bg,rgba(0,0,0,0.3));padding:12px;border-radius:8px;overflow-x:auto;"><code>' + code.trim() + '</code></pre>'; });
    html = html.replace(/!\[image\]\((.*?)\)/g, '<img src="$1" style="max-width:100%;border-radius:10px;margin:12px 0;" />');
    html = html.replace(/^######\s+(.*)$/gm, '<h6 style="color:var(--blog-text-primary);">$1</h6>');
    html = html.replace(/^#####\s+(.*)$/gm, '<h5 style="color:var(--blog-text-primary);">$1</h5>');
    html = html.replace(/^####\s+(.*)$/gm, '<h4 style="color:var(--blog-text-primary);">$1</h4>');
    html = html.replace(/^###\s+(.*)$/gm, '<h3 style="color:var(--blog-text-primary);">$1</h3>');
    html = html.replace(/^##\s+(.*)$/gm, '<h2 style="color:var(--blog-text-primary);">$1</h2>');
    html = html.replace(/^#\s+(.*)$/gm, '<h1 style="color:var(--blog-text-primary);">$1</h1>');
    html = html.replace(/^---$/gm, '<hr style="border:none;border-top:1px solid var(--blog-card-border);margin:20px 0;" />');
    html = html.replace(/^&gt;\s+(.*)$/gm, '<blockquote style="border-left:3px solid #3b82f6;padding-left:14px;color:var(--blog-text-muted);margin:12px 0;">$1</blockquote>');
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
    html = html.replace(/`([^`]+?)`/g, '<code style="background:var(--blog-content-code-bg,rgba(0,0,0,0.3));padding:2px 6px;border-radius:4px;">$1</code>');
    html = html.replace(/\[(.+?)\]\((.+?)\)/g, '<a href="$2" style="color:#60a5fa;">$1</a>');
    html = html.replace(/^\s*[-*]\s+(.*)$/gm, '<li>$1</li>');
    html = html.replace(/^\s*\d+\.\s+(.*)$/gm, '<li>$1</li>');
    html = html.replace(/(<li>[\s\S]*?<\/li>)/g, '<ul style="padding-left:22px;margin:12px 0;">$1</ul>');
    html = html.replace(/\n{2,}/g, '</p><p style="margin:12px 0;">');
    html = html.replace(/\n/g, '<br>');
    return '<p style="margin:12px 0;">' + html + '</p>';
}
function bwPreview() {
    var content = document.getElementById('writeContent').value;
    var title = document.getElementById('writeTitle').value.trim();
    var cover = document.getElementById('writeCover').value.trim();
    var html = '';
    if (title) html += '<h1 style="color:var(--blog-text-primary);font-size:30px;margin-bottom:16px;">' + bwEsc(title) + '</h1>';
    if (cover) html += '<img src="' + bwEsc(cover) + '" style="max-width:100%;border-radius:12px;margin-bottom:20px;" />';
    html += bwRenderMd(content);
    document.getElementById('writePreviewBody').innerHTML = html;
    document.getElementById('writePreviewModal').style.display = 'block';
}
function bwClosePreview() {
    document.getElementById('writePreviewModal').style.display = 'none';
}

async function submitArticle() {
    var title = document.getElementById('writeTitle').value.trim();
    var content = document.getElementById('writeContent').value.trim();
    var excerpt = document.getElementById('writeExcerpt').value.trim();
    var category = document.getElementById('writeCategory').value;
    var tags = document.getElementById('writeTags').value.trim();
    var cover = document.getElementById('writeCover').value.trim();

    if (!title || !content) {
        document.getElementById('writeError').textContent = 'Title and content are required';
        return;
    }
    if (content.length < 100) {
        document.getElementById('writeError').textContent = 'Content must be at least 100 characters';
        return;
    }

    try {
        var resp = await fetch('/api/blog/posts', {
            method: 'POST',
            headers: {'Content-Type':'application/json'},
            body: JSON.stringify({title:title, content:content, excerpt:excerpt, category:category, tags:tags, cover_image:cover})
        });
        var data = await resp.json();
        if (data.success) {
            document.getElementById('writeError').textContent = '';
            document.getElementById('writeSuccess').style.display = 'block';
            document.getElementById('writeSuccess').textContent = 'Article submitted for review! Redirecting...';
            setTimeout(function() { location.href = '/blog/my-posts'; }, 2000);
        } else {
            document.getElementById('writeError').textContent = data.error || 'Failed to submit';
        }
    } catch(e) {
        document.getElementById('writeError').textContent = 'Connection error';
    }
}
</script>
"""


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

    categories = blog_db.get_blog_category_names()
    cat_options = ''.join(f'<option>{_esc(c)}</option>' for c in categories) if categories else '<option>General</option>'

    body_html = f"""
    <div class="blog-write-page">
        <h1>Write a New Article</h1>
        <p style="color:var(--blog-text-faint);margin-bottom:24px;font-size:14px;">Your article will be reviewed by our editors before publishing.</p>
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
                    {cat_options}
                </select>
            </div>
            <div class="blog-write-form-group">
                <label>Tags (comma separated)</label>
                <input type="text" id="writeTags" placeholder="e.g. OPEC, crude oil, sanctions" />
            </div>
        </div>
        <div class="blog-write-form-group">
            <label>Cover Image (optional)</label>
            <div class="bw-row" style="margin-bottom:8px;">
                <label class="bw-upload-label">
                    &#128247; Upload Cover Image
                    <input type="file" id="writeCoverFile" accept="image/jpeg,image/png,image/gif,image/webp" style="display:none;" onchange="bwHandleCoverSelect(this)" />
                </label>
                <span class="bw-hint">Max 1.5 MB &middot; JPEG, PNG, GIF, WebP</span>
                <span id="writeCoverStatus" style="font-size:12px;display:none;"></span>
            </div>
            <div id="writeCoverPreview" class="bw-cover-preview">
                <img id="writeCoverPreviewImg" src="" alt="Cover preview" />
                <button type="button" class="bw-x" onclick="bwRemoveCover()" title="Remove cover image">&times;</button>
            </div>
            <input type="text" id="writeCover" placeholder="…or paste an image URL (https://...)" oninput="bwSyncCover()" />
        </div>
        <div class="blog-write-form-group">
            <div class="bw-toolbar-head">
                <label style="margin:0;">Content (Markdown supported)</label>
                <button type="button" class="bw-preview-btn" onclick="bwPreview()">Preview</button>
            </div>
            <div class="bw-toolbar">
                <button type="button" class="bw-tbtn" onclick="bwMdInsert('bold')" title="Bold" style="font-weight:700;">B</button>
                <button type="button" class="bw-tbtn" onclick="bwMdInsert('italic')" title="Italic" style="font-style:italic;">I</button>
                <button type="button" class="bw-tbtn" onclick="bwMdInsert('underline')" title="Underline" style="text-decoration:underline;">U</button>
                <span class="bw-tsep"></span>
                <button type="button" class="bw-tbtn" onclick="bwMdInsert('h1')" title="Heading 1" style="font-weight:700;">H1</button>
                <button type="button" class="bw-tbtn" onclick="bwMdInsert('h2')" title="Heading 2" style="font-weight:700;">H2</button>
                <button type="button" class="bw-tbtn" onclick="bwMdInsert('h3')" title="Heading 3" style="font-weight:700;">H3</button>
                <span class="bw-tsep"></span>
                <button type="button" class="bw-tbtn" onclick="bwMdInsert('ul')" title="Bullet List">&#8226; List</button>
                <button type="button" class="bw-tbtn" onclick="bwMdInsert('ol')" title="Numbered List">1. List</button>
                <button type="button" class="bw-tbtn" onclick="bwMdInsert('indent')" title="Indent">&#8677; Indent</button>
                <span class="bw-tsep"></span>
                <button type="button" class="bw-tbtn bw-tbtn-disabled" disabled title="Links are not allowed in articles. Add your website link in your Profile bio instead.">&#128279;</button>
                <button type="button" class="bw-tbtn" onclick="bwMdInsert('quote')" title="Blockquote">&#10077;</button>
                <button type="button" class="bw-tbtn" onclick="bwMdInsert('code')" title="Code Block" style="font-family:monospace;">&lt;/&gt;</button>
                <button type="button" class="bw-tbtn" onclick="bwMdInsert('hr')" title="Horizontal Rule">&#8213;</button>
                <span class="bw-tsep"></span>
                <button type="button" class="bw-tbtn" onclick="bwToggleImageUpload()" title="Insert Image">&#128247;</button>
                <button type="button" class="bw-tbtn" onclick="bwToggleEmoji()" title="Insert Emoji">&#128522;</button>
            </div>
            <div id="writeEmojiPanel" class="bw-emoji-panel">
                <div style="display:flex;gap:4px;margin-bottom:6px;flex-wrap:wrap;" id="writeEmojiTabs"></div>
                <div style="display:flex;flex-wrap:wrap;gap:2px;" id="writeEmojiGrid"></div>
            </div>
            <textarea id="writeContent" class="bw-content" placeholder="Write your article here. You can use Markdown formatting: **bold**, *italic*, ## headings, - lists, [links](url)"></textarea>
        </div>
        <div id="writeImageSection" class="bw-section" style="display:none;">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
                <span style="font-size:13px;color:var(--blog-text-secondary);font-weight:500;">Upload Image</span>
                <span style="font-size:11px;color:var(--blog-text-faint);" id="writeImageCount">0 / 3 images</span>
            </div>
            <div class="bw-row" style="margin-bottom:10px;">
                <label class="bw-img-label">
                    &#128193; Choose File
                    <input type="file" id="writeImageFile" accept="image/jpeg,image/png,image/gif,image/webp" style="display:none;" onchange="bwHandleImageSelect(this)" />
                </label>
                <span class="bw-hint">Max 1.5 MB &middot; up to 3 images</span>
                <button type="button" onclick="bwToggleImageUpload()" style="margin-left:auto;padding:5px 12px;border-radius:6px;border:1px solid var(--blog-input-border);background:var(--blog-theme-toggle-bg);color:var(--blog-text-secondary);font-size:12px;cursor:pointer;">Close</button>
            </div>
            <div id="writeImageStatus" style="font-size:12px;margin-bottom:8px;display:none;"></div>
            <div id="writeImageList" style="display:flex;gap:8px;flex-wrap:wrap;"></div>
        </div>
        <div class="blog-write-actions">
            <button class="blog-write-btn blog-write-btn-primary" onclick="submitArticle()">Submit for Review</button>
            <button class="blog-write-btn blog-write-btn-secondary" onclick="location.href='/blog'">Cancel</button>
        </div>
        <div id="writeError" style="color:#f87171;font-size:14px;margin-top:12px;"></div>
        <div id="writeSuccess" style="color:#34d399;font-size:14px;margin-top:12px;display:none;"></div>
    </div>
    <div id="writePreviewModal" class="bw-modal">
        <div class="bw-modal-inner">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:24px;border-bottom:1px solid var(--blog-card-border);padding-bottom:16px;">
                <h3 style="color:var(--blog-text-primary);font-size:18px;margin:0;">Article Preview</h3>
                <button style="padding:6px 14px;border-radius:6px;border:1px solid var(--blog-input-border);background:var(--blog-theme-toggle-bg);color:var(--blog-text-secondary);font-size:13px;cursor:pointer;" onclick="bwClosePreview()">Close</button>
            </div>
            <div id="writePreviewBody" style="color:var(--blog-content-text);font-size:15px;line-height:1.8;"></div>
        </div>
    </div>
    """
    body = body_html + _BLOG_WRITE_SCRIPT
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


@router.get("/blog/account", response_class=HTMLResponse)
async def blog_account_page(request: Request):
    user = _get_blog_user(request)
    if not user:
        return HTMLResponse(_blog_page("My Profile", """
        <div class="blog-container blog-empty">
            <div class="blog-empty-icon">&#x1f512;</div>
            <h3>Sign in to edit your profile</h3>
            <p><a href="#" onclick="openBlogAuth(); return false;">Sign in or create an account</a></p>
        </div>
        """, request))

    bio = user.get('bio') or ''
    website = user.get('website') or ''
    avatar_image = user.get('avatar_image') or ''
    initial = (user.get('display_name') or 'U')[0].upper()
    color = user.get('avatar_color', '#3b82f6')

    if avatar_image:
        preview = f'<img id="bpAvatarImg" src="{_esc(avatar_image)}" alt="" class="bp-avatar-preview" />'
        preview_initial_style = 'display:none;'
    else:
        preview = ''
        preview_initial_style = ''

    body = f"""
    <div class="blog-write-page">
        <h1 style="margin-bottom:6px;">My Profile</h1>
        <p style="color:var(--blog-text-muted);font-size:14px;margin-bottom:24px;">Add a photo and a short bio. These appear at the bottom of every article you publish. You may include a link to your website or business below.</p>

        <div class="bp-avatar-row">
            <div class="bp-avatar-wrap">
                <div class="bp-avatar-initial" id="bpAvatarInitial" style="background:{_esc(color)};{preview_initial_style}">{_esc(initial)}</div>
                {preview}
            </div>
            <div>
                <input type="file" id="bpAvatarFile" accept="image/*" style="display:none;" onchange="bpUploadAvatar(this)" />
                <button type="button" class="blog-write-btn blog-write-btn-secondary" onclick="document.getElementById('bpAvatarFile').click()">Upload Photo</button>
                <button type="button" class="blog-write-btn blog-write-btn-secondary" id="bpRemoveBtn" onclick="bpRemoveAvatar()" style="{'' if avatar_image else 'display:none;'}">Remove</button>
                <div id="bpAvatarStatus" style="font-size:12px;color:var(--blog-text-muted);margin-top:8px;">JPG, PNG, GIF or WebP. Square images look best.</div>
            </div>
        </div>

        <div class="blog-write-form-group">
            <label>Bio</label>
            <textarea id="bpBio" maxlength="600" placeholder="Tell readers a little about yourself..." style="min-height:120px;">{_esc(bio)}</textarea>
            <div style="font-size:12px;color:var(--blog-text-muted);margin-top:4px;">Up to 600 characters.</div>
        </div>

        <div class="blog-write-form-group">
            <label>Website / Business Link</label>
            <input type="url" id="bpWebsite" placeholder="https://your-website.com" value="{_esc(website)}" />
            <div style="font-size:12px;color:var(--blog-text-muted);margin-top:4px;">Shown as a clickable link in your author box.</div>
        </div>

        <div style="display:flex;gap:10px;align-items:center;margin-top:8px;">
            <button type="button" class="blog-write-btn blog-write-btn-primary" id="bpSaveBtn" onclick="bpSaveProfile()">Save Profile</button>
            <span id="bpSaveMsg" style="font-size:14px;"></span>
        </div>
    </div>
    <script>
        var bpAvatarUrl = {json.dumps(avatar_image)};
        async function bpUploadAvatar(input) {{
            var file = input.files[0];
            if (!file) return;
            var status = document.getElementById('bpAvatarStatus');
            status.textContent = 'Uploading...';
            var fd = new FormData();
            fd.append('file', file);
            try {{
                var resp = await fetch('/api/blog/upload-image', {{ method: 'POST', body: fd }});
                var data = await resp.json();
                if (data.success && data.url) {{
                    bpAvatarUrl = data.url;
                    var wrap = document.querySelector('.bp-avatar-wrap');
                    var img = document.getElementById('bpAvatarImg');
                    if (!img) {{
                        img = document.createElement('img');
                        img.id = 'bpAvatarImg';
                        img.className = 'bp-avatar-preview';
                        wrap.appendChild(img);
                    }}
                    img.src = data.url;
                    document.getElementById('bpAvatarInitial').style.display = 'none';
                    document.getElementById('bpRemoveBtn').style.display = '';
                    status.textContent = 'Photo ready. Click Save Profile to apply.';
                }} else {{
                    status.textContent = data.error || 'Upload failed';
                }}
            }} catch(e) {{ status.textContent = 'Upload failed'; }}
            input.value = '';
        }}
        function bpRemoveAvatar() {{
            bpAvatarUrl = '';
            var img = document.getElementById('bpAvatarImg');
            if (img) img.remove();
            document.getElementById('bpAvatarInitial').style.display = '';
            document.getElementById('bpRemoveBtn').style.display = 'none';
            document.getElementById('bpAvatarStatus').textContent = 'Photo removed. Click Save Profile to apply.';
        }}
        async function bpSaveProfile() {{
            var btn = document.getElementById('bpSaveBtn');
            var msg = document.getElementById('bpSaveMsg');
            btn.disabled = true;
            msg.style.color = 'var(--blog-text-muted)';
            msg.textContent = 'Saving...';
            try {{
                var resp = await fetch('/api/blog/profile', {{
                    method: 'POST',
                    headers: {{'Content-Type':'application/json'}},
                    body: JSON.stringify({{
                        bio: document.getElementById('bpBio').value,
                        website: document.getElementById('bpWebsite').value,
                        avatar_image: bpAvatarUrl
                    }})
                }});
                var data = await resp.json();
                if (data.success) {{
                    msg.style.color = '#34d399';
                    msg.textContent = 'Profile saved!';
                }} else {{
                    msg.style.color = '#f87171';
                    msg.textContent = data.error || 'Failed to save';
                }}
            }} catch(e) {{
                msg.style.color = '#f87171';
                msg.textContent = 'Failed to save';
            }}
            btn.disabled = false;
        }}
    </script>
    """
    return HTMLResponse(_blog_page("My Profile", body, request))


@router.get("/blog/{cat_slug}/{article_slug}", response_class=HTMLResponse)
async def blog_article_page(cat_slug: str, article_slug: str, request: Request):
    post = blog_db.get_post_by_slug(article_slug)
    if not post:
        return HTMLResponse(_blog_page("Not Found", """
        <div class="blog-container blog-empty">
            <div class="blog-empty-icon">&#x1f50d;</div>
            <h3>Article not found</h3>
            <p><a href="/blog">Back to all articles</a></p>
        </div>
        """, request), status_code=404)

    cat_slug_map = blog_db.get_category_slug_map()
    expected_cat_slug = _get_cat_slug_for_post(post, cat_slug_map)
    if cat_slug != expected_cat_slug:
        from starlette.responses import RedirectResponse
        return RedirectResponse(url=f"/blog/{expected_cat_slug}/{article_slug}", status_code=301)

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

    author_bio_html = ""
    if post.get('author_type') == 'user' and post.get('author_id'):
        author = blog_db.get_blog_user_by_id(post['author_id'])
        if author:
            a_bio = (author.get('bio') or '').strip()
            a_website = (author.get('website') or '').strip()
            a_image = (author.get('avatar_image') or '').strip()
            if a_bio or a_website or a_image:
                a_name = author.get('display_name') or post.get('author_name') or 'Author'
                a_color = author.get('avatar_color') or '#3b82f6'
                if a_image:
                    avatar_block = f'<img class="blog-author-bio-img" src="{_esc(a_image)}" alt="{_esc(a_name)}" loading="lazy" />'
                else:
                    avatar_block = f'<div class="blog-author-bio-initial" style="background:{_esc(a_color)}">{_esc(a_name[0].upper())}</div>'
                bio_para = f'<p class="blog-author-bio-text">{_linkify_bio(a_bio)}</p>' if a_bio else ''
                website_link = ""
                if a_website:
                    href = a_website if a_website.lower().startswith(('http://', 'https://')) else 'https://' + a_website
                    label = re.sub(r'^https?://', '', a_website).rstrip('/')
                    website_link = f'<a class="blog-author-bio-link" href="{_esc(href)}" target="_blank" rel="noopener nofollow">&#128279; {_esc(label)}</a>'
                author_bio_html = f"""
                <div class="blog-author-bio">
                    {avatar_block}
                    <div class="blog-author-bio-body">
                        <div class="blog-author-bio-label">About the author</div>
                        <div class="blog-author-bio-name">{_esc(a_name)}</div>
                        {bio_para}
                        {website_link}
                    </div>
                </div>
                """

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

    back_url = f"/blog/{_esc(cat_slug)}"
    cat_display = _esc(post.get('category', 'General'))

    body = f"""
    <article class="blog-article">
        <a href="{back_url}" class="blog-article-back">&larr; Back to {cat_display}</a>
        <a href="{back_url}" class="blog-article-category" style="text-decoration:none;">{cat_display}</a>
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
        {author_bio_html}
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


@router.get("/blog/{cat_slug}", response_class=HTMLResponse)
async def blog_category_page(cat_slug: str, request: Request, page: int = Query(1, ge=1)):
    blog_db.refresh_category_post_counts()
    category = blog_db.get_blog_category_by_slug(cat_slug)
    if not category:
        return HTMLResponse(_blog_page("Category Not Found", """
        <div class="blog-container blog-empty">
            <div class="blog-empty-icon">&#x1f50d;</div>
            <h3>Category not found</h3>
            <p><a href="/blog">Back to all articles</a></p>
        </div>
        """, request), status_code=404)

    cat_name = category['name']
    cat_desc = category.get('description', '')
    cat_color = category.get('color', '#3b82f6')
    posts, total = blog_db.get_published_posts(page=page, per_page=9, category=cat_name)
    total_pages = max(1, (total + 8) // 9)
    all_categories = blog_db.get_blog_categories()

    category_links = _render_category_links(all_categories, active_slug=cat_slug)
    cards = _render_blog_cards(posts)

    if not cards:
        cards = f"""
        <div class="blog-empty" style="grid-column:1/-1;">
            <div class="blog-empty-icon">&#x1f4dd;</div>
            <h3>No articles in {_esc(cat_name)}</h3>
            <p>Check back soon or <a href="/blog">browse all articles</a>.</p>
        </div>
        """

    pagination = _render_pagination(page, total_pages, base_url=f"/blog/{cat_slug}")

    body = f"""
    <div class="blog-container">
        <div class="blog-hero">
            <div class="blog-cat-hero-badge" style="background:{_esc(cat_color)}22;color:{_esc(cat_color)};border:1px solid {_esc(cat_color)}44;">
                {_esc(cat_name)}
            </div>
            <h1>{_esc(cat_name)}</h1>
            <p>{_esc(cat_desc) if cat_desc else f'Articles about {_esc(cat_name).lower()}'}</p>
        </div>
        <div class="blog-cat-links-row">
            {category_links}
        </div>
        <div class="blog-grid">
            {cards}
        </div>
        {pagination}
    </div>
    <script>
        function goPage(p) {{
            var url = new URL(location.href);
            url.searchParams.set('page', p);
            location.href = url.toString();
        }}
    </script>
    """

    return HTMLResponse(_blog_page(f"{cat_name} - Blog", body, request))


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
        content = _strip_user_links(content)
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


@router.post("/api/blog/profile")
async def blog_update_profile(request: Request):
    user = _get_blog_user(request)
    if not user:
        return JSONResponse({"success": False, "error": "Sign in required"}, status_code=401)
    try:
        body = await request.json()
        bio = (body.get('bio') or '').strip()[:600]
        website = (body.get('website') or '').strip()[:500]
        avatar_image = (body.get('avatar_image') or '').strip()[:1000]

        if website and not website.lower().startswith(('http://', 'https://')):
            website = 'https://' + website
        if avatar_image and not avatar_image.startswith(('http://', 'https://', '/')):
            return JSONResponse({"success": False, "error": "Invalid image URL"})

        blog_db.update_blog_profile(user['id'], bio, website, avatar_image)
        return JSONResponse({"success": True})
    except Exception as e:
        logger.error(f"Blog update profile error: {e}")
        return JSONResponse({"success": False, "error": "Failed to save profile"})


@router.post("/api/blog/upload-image")
async def blog_user_upload_image(request: Request, file: UploadFile = File(...)):
    user = _get_blog_user(request)
    if not user:
        return JSONResponse({"success": False, "error": "Sign in required"}, status_code=401)
    try:
        if not _check_upload_rate(f"user:{user['id']}"):
            return JSONResponse({"success": False, "error": "Upload rate limit reached (max 15 images per hour)"})

        if file.content_type not in ALLOWED_IMAGE_TYPES:
            return JSONResponse({"success": False, "error": "Only JPEG, PNG, GIF, and WebP images are allowed"})

        contents = await file.read()
        if len(contents) > MAX_IMAGE_SIZE:
            return JSONResponse({"success": False, "error": "Image size must be under 1.5 MB"})

        if not _validate_image_magic(contents):
            return JSONResponse({"success": False, "error": "File does not appear to be a valid image"})

        ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else 'jpg'
        if ext not in ('jpg', 'jpeg', 'png', 'gif', 'webp'):
            ext = 'jpg'
        filename = f"{uuid.uuid4().hex[:12]}.{ext}"
        content_type = CONTENT_TYPE_MAP.get(ext, 'image/png')

        blog_db.execute_one(
            "INSERT INTO blog_images (filename, content_type, image_data) VALUES (%s, %s, %s) RETURNING id",
            (filename, content_type, contents)
        )

        url = f"/blog/uploads/{filename}"
        return JSONResponse({"success": True, "url": url, "filename": filename})
    except Exception as e:
        logger.error(f"Blog user image upload error: {e}")
        return JSONResponse({"success": False, "error": "Upload failed"})


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

        status = (body.get('status') or 'published').strip()
        if status not in ('published', 'draft'):
            status = 'published'

        if not title:
            return JSONResponse({"success": False, "error": "Title is required"})
        if status == 'published' and not content:
            return JSONResponse({"success": False, "error": "Content is required to publish"})

        slug = _slugify(title)
        existing = blog_db.get_post_by_slug(slug)
        if existing:
            slug = slug + '-' + secrets.token_hex(3)

        if not excerpt and content:
            excerpt = content[:200].rsplit(' ', 1)[0] + '...' if len(content) > 200 else content

        post = blog_db.create_post(
            title=title, slug=slug, excerpt=excerpt, content=content,
            cover_image=cover_image, category=category, tags=tags,
            author_id=None, author_name='EnergyRiskIQ',
            author_type='admin', status=status
        )
        return JSONResponse({"success": True, "post_id": post['id']})
    except Exception as e:
        logger.error(f"Admin blog create error: {e}")
        return JSONResponse({"success": False, "error": "Failed to create post"})


@router.put("/api/blog/admin/posts/{post_id}")
async def admin_blog_update_post(post_id: int, request: Request, x_admin_token: Optional[str] = Header(None)):
    from src.api.admin_routes import verify_admin_token
    verify_admin_token(x_admin_token)
    try:
        existing_post = blog_db.get_post_by_id(post_id)
        if not existing_post:
            return JSONResponse({"success": False, "error": "Post not found"})

        body = await request.json()
        title = (body.get('title') or '').strip()
        content = (body.get('content') or '').strip()
        excerpt = (body.get('excerpt') or '').strip()
        category = (body.get('category') or 'General').strip()
        tags = (body.get('tags') or '').strip()
        cover_image = (body.get('cover_image') or '').strip()
        status = (body.get('status') or '').strip()
        if status not in ('published', 'draft'):
            status = existing_post.get('status', 'draft')

        if not title:
            return JSONResponse({"success": False, "error": "Title is required"})
        if status == 'published' and not content:
            return JSONResponse({"success": False, "error": "Content is required to publish"})

        if title == existing_post.get('title', ''):
            slug = existing_post.get('slug', _slugify(title))
        else:
            slug = _slugify(title)
            slug_check = blog_db.get_post_by_slug(slug)
            if slug_check and slug_check['id'] != post_id:
                slug = slug + '-' + secrets.token_hex(3)

        if not excerpt and content:
            excerpt = content[:200].rsplit(' ', 1)[0] + '...' if len(content) > 200 else content

        post = blog_db.update_post(post_id, title, slug, excerpt, content, cover_image, category, tags)
        if post:
            post = blog_db.update_post_status(post_id, status)
        return JSONResponse({"success": True, "post_id": post['id'] if post else post_id})
    except Exception as e:
        logger.error(f"Admin blog update error: {e}")
        return JSONResponse({"success": False, "error": "Failed to update post"})


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


@router.get("/api/blog/categories")
async def public_blog_categories():
    cats = blog_db.get_blog_categories()
    result = []
    for c in cats:
        d = dict(c)
        for k, v in d.items():
            if isinstance(v, datetime):
                d[k] = v.isoformat()
        result.append(d)
    return JSONResponse({"success": True, "categories": result})


@router.get("/api/blog/admin/categories")
async def admin_blog_list_categories(x_admin_token: Optional[str] = Header(None)):
    from src.api.admin_routes import verify_admin_token
    verify_admin_token(x_admin_token)
    blog_db.refresh_category_post_counts()
    cats = blog_db.get_all_blog_categories_admin()
    result = []
    for c in cats:
        d = dict(c)
        for k, v in d.items():
            if isinstance(v, datetime):
                d[k] = v.isoformat()
        result.append(d)
    return JSONResponse({"success": True, "categories": result})


@router.post("/api/blog/admin/categories")
async def admin_blog_create_category(request: Request, x_admin_token: Optional[str] = Header(None)):
    from src.api.admin_routes import verify_admin_token
    verify_admin_token(x_admin_token)
    try:
        body = await request.json()
        name = (body.get('name') or '').strip()
        slug = (body.get('slug') or '').strip()
        description = (body.get('description') or '').strip()
        color = (body.get('color') or '#3b82f6').strip()
        sort_order = int(body.get('sort_order', 0))
        if not name:
            return JSONResponse({"success": False, "error": "Name is required"})
        if not slug:
            slug = _slugify(name)
        cat = blog_db.create_blog_category(name, slug, description, color, sort_order)
        return JSONResponse({"success": True, "category_id": cat['id']})
    except Exception as e:
        logger.error(f"Admin create category error: {e}")
        return JSONResponse({"success": False, "error": str(e)})


@router.put("/api/blog/admin/categories/{cat_id}")
async def admin_blog_update_category(cat_id: int, request: Request, x_admin_token: Optional[str] = Header(None)):
    from src.api.admin_routes import verify_admin_token
    verify_admin_token(x_admin_token)
    try:
        body = await request.json()
        name = (body.get('name') or '').strip()
        slug = (body.get('slug') or '').strip()
        description = (body.get('description') or '').strip()
        color = (body.get('color') or '#3b82f6').strip()
        sort_order = int(body.get('sort_order', 0))
        is_active = body.get('is_active', True)
        if not name:
            return JSONResponse({"success": False, "error": "Name is required"})
        if not slug:
            slug = _slugify(name)
        cat = blog_db.update_blog_category(cat_id, name, slug, description, color, sort_order, is_active)
        return JSONResponse({"success": True, "category_id": cat['id'] if cat else None})
    except Exception as e:
        logger.error(f"Admin update category error: {e}")
        return JSONResponse({"success": False, "error": str(e)})


@router.delete("/api/blog/admin/categories/{cat_id}")
async def admin_blog_delete_category(cat_id: int, x_admin_token: Optional[str] = Header(None)):
    from src.api.admin_routes import verify_admin_token
    verify_admin_token(x_admin_token)
    try:
        blog_db.delete_blog_category(cat_id)
        return JSONResponse({"success": True})
    except Exception as e:
        logger.error(f"Admin delete category error: {e}")
        return JSONResponse({"success": False, "error": str(e)})


@router.get("/api/blog/admin/users")
async def admin_blog_list_users(x_admin_token: Optional[str] = Header(None)):
    from src.api.admin_routes import verify_admin_token
    verify_admin_token(x_admin_token)
    users = blog_db.get_all_blog_users_admin()
    result = []
    for u in users:
        d = dict(u)
        for k, v in d.items():
            if isinstance(v, datetime):
                d[k] = v.isoformat()
        result.append(d)
    return JSONResponse({"success": True, "users": result})


@router.put("/api/blog/admin/users/{user_id}/status")
async def admin_blog_update_user_status(user_id: int, request: Request, x_admin_token: Optional[str] = Header(None)):
    from src.api.admin_routes import verify_admin_token
    verify_admin_token(x_admin_token)
    try:
        body = await request.json()
        is_active = body.get('is_active', True)
        user = blog_db.update_blog_user_status(user_id, is_active)
        return JSONResponse({"success": True, "user_id": user['id'] if user else None})
    except Exception as e:
        logger.error(f"Admin update blog user error: {e}")
        return JSONResponse({"success": False, "error": str(e)})


@router.delete("/api/blog/admin/users/{user_id}")
async def admin_blog_delete_user(user_id: int, x_admin_token: Optional[str] = Header(None)):
    from src.api.admin_routes import verify_admin_token
    verify_admin_token(x_admin_token)
    try:
        blog_db.delete_blog_user(user_id)
        return JSONResponse({"success": True})
    except Exception as e:
        logger.error(f"Admin delete blog user error: {e}")
        return JSONResponse({"success": False, "error": str(e)})


ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
MAX_IMAGE_SIZE = 1_572_864
MAX_IMAGES_PER_HOUR = 15

IMAGE_MAGIC_BYTES = {
    b'\xff\xd8\xff': 'jpg',
    b'\x89PNG': 'png',
    b'GIF87a': 'gif',
    b'GIF89a': 'gif',
    b'RIFF': 'webp',
}

CONTENT_TYPE_MAP = {
    'jpg': 'image/jpeg', 'jpeg': 'image/jpeg',
    'png': 'image/png', 'gif': 'image/gif', 'webp': 'image/webp'
}

_upload_tracker = {}


def _check_upload_rate(key='admin'):
    import time
    now = time.time()
    if key not in _upload_tracker:
        _upload_tracker[key] = []
    _upload_tracker[key] = [t for t in _upload_tracker[key] if now - t < 3600]
    if len(_upload_tracker[key]) >= MAX_IMAGES_PER_HOUR:
        return False
    _upload_tracker[key].append(now)
    return True


def _validate_image_magic(data: bytes) -> bool:
    for magic, _ in IMAGE_MAGIC_BYTES.items():
        if data[:len(magic)] == magic:
            return True
    return False




@router.post("/api/blog/admin/upload-image")
async def admin_blog_upload_image(
    file: UploadFile = File(...),
    x_admin_token: Optional[str] = Header(None),
):
    from src.api.admin_routes import verify_admin_token
    verify_admin_token(x_admin_token)
    try:
        if not _check_upload_rate():
            return JSONResponse({"success": False, "error": "Upload rate limit reached (max 15 images per hour)"})

        if file.content_type not in ALLOWED_IMAGE_TYPES:
            return JSONResponse({"success": False, "error": "Only JPEG, PNG, GIF, and WebP images are allowed"})

        contents = await file.read()
        if len(contents) > MAX_IMAGE_SIZE:
            return JSONResponse({"success": False, "error": "Image size must be under 1.5 MB"})

        if not _validate_image_magic(contents):
            return JSONResponse({"success": False, "error": "File does not appear to be a valid image"})

        ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else 'jpg'
        if ext not in ('jpg', 'jpeg', 'png', 'gif', 'webp'):
            ext = 'jpg'
        filename = f"{uuid.uuid4().hex[:12]}.{ext}"
        content_type = CONTENT_TYPE_MAP.get(ext, 'image/png')

        blog_db.execute_one(
            "INSERT INTO blog_images (filename, content_type, image_data) VALUES (%s, %s, %s) RETURNING id",
            (filename, content_type, contents)
        )

        url = f"/blog/uploads/{filename}"
        return JSONResponse({"success": True, "url": url, "filename": filename})
    except Exception as e:
        logger.error(f"Blog image upload error: {e}")
        return JSONResponse({"success": False, "error": "Upload failed"})
