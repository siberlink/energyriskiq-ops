import os
import sys
import asyncio
import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.api.routes import router
from src.api.risk_routes import router as risk_router
from src.api.alert_routes import router as alert_router
from src.api.marketing_routes import router as marketing_router
from src.api.internal_routes import router as internal_router
from src.api.digest_routes import router as digest_router
from src.api.daily_digest_routes import router as daily_digest_router
from src.api.linkedin_routes import router as linkedin_router
from src.api.contact_routes import router as contact_router
from src.api.admin_routes import router as admin_router
from src.api.user_routes import router as user_router
from src.api.ops_routes import router as ops_router
from src.api.telegram_routes import router as telegram_router
from src.api.seo_routes import router as seo_router
from src.billing.billing_routes import router as billing_router, stripe_webhook
from src.db.migrations import run_migrations, run_seo_tables_migration, run_sources_migration, run_geri_migration, run_pro_delivery_migration, run_fix_skipped_alerts, run_signal_quality_migration, _recalculate_stale_bands, run_eriq_migration, run_lng_price_migration, run_stripe_mode_migration, run_lng_import_sources_migration, run_gas_storage_country_migration
from src.geri import ENABLE_GERI
from src.geri.routes import router as geri_router
from src.geri.live_routes import router as geri_live_router
from src.reri import ENABLE_EERI
from src.reri.routes import router as eeri_router
from src.reri.seo_routes import router as eeri_seo_router
from src.reri.pro_routes import router as eeri_pro_router
from src.egsi.types import ENABLE_EGSI
from src.egsi.routes import router as egsi_router
from src.egsi.egsi_seo_routes import router as egsi_seo_router
from src.eriq import ENABLE_ERIQ
from src.api.eriq_routes import router as eriq_router
from src.elsa.routes import router as elsa_router
from src.api.signals_routes import router as signals_router
from src.tickets.routes import router as tickets_router
from src.blog.routes import router as blog_router
from src.api.snapshot_routes import router as snapshot_router
from src.api.forecast_routes import router as forecast_router
from src.api.gas_storage_routes import router as gas_storage_router
from src.api.gas_storage_germany_routes import router as gas_storage_germany_router
from src.api.lng_routes import router as lng_router
from src.api.jkm_routes import router as jkm_router
from src.api.ttf_routes import router as ttf_router
from src.api.brent_routes import router as brent_router
from src.api.jkm_chart_routes import router as jkm_chart_router
from src.api.lng_drivers_routes import router as lng_drivers_router
from src.api.natgas_routes import router as natgas_router
from src.api.wti_routes import router as wti_router
from src.api.wti_widget_routes import router as wti_widget_router
from src.api.gas_storage_widget_routes import router as gas_storage_widget_router
from src.api.lng_widget_routes import router as lng_widget_router

logging.basicConfig(
    level=os.environ.get('LOG_LEVEL', 'INFO'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="EnergyRiskIQ API",
    description="Event Ingestion, Classification, Risk Intelligence, and Alerts Pipeline",
    version="0.4.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Redirect all 404 Not Found responses to the main landing page,
    except admin API paths which need real JSON errors."""
    if exc.status_code == 404:
        if request.url.path.startswith("/admin/"):
            return JSONResponse(status_code=404, content={"detail": str(exc.detail)})
        return RedirectResponse(url="/", status_code=302)
    return JSONResponse(status_code=exc.status_code, content={"detail": str(exc.detail)})


class TrailingSlashRedirectMiddleware(BaseHTTPMiddleware):
    """Redirect trailing slash URLs to non-trailing slash for SEO canonicalization."""
    
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path != "/" and path.endswith("/"):
            new_path = path.rstrip("/")
            if request.url.query:
                new_url = f"{new_path}?{request.url.query}"
            else:
                new_url = new_path
            return RedirectResponse(url=new_url, status_code=301)
        return await call_next(request)


app.add_middleware(TrailingSlashRedirectMiddleware)


_FRAME_PROTECTED_PREFIXES = (
    "/admin",
    "/dashboard",
    "/settings",
    "/users",
    "/tokens",
    "/billing",
)

# Sensitive HTML served directly from the public /static mount must be protected
# too, otherwise framing protection is bypassed by hitting the static URL directly.
_FRAME_PROTECTED_STATIC = (
    "/static/admin.html",
    "/static/users.html",
    "/static/users-account.html",
)


class ClickjackingProtectionMiddleware(BaseHTTPMiddleware):
    """Block third-party framing of sensitive authenticated pages (admin, account,
    dashboard, settings, token/payment flows) to prevent clickjacking. Public
    embeddable widgets under /embed/* are intentionally left framable."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        protected = (
            any(path == p or path.startswith(p + "/") for p in _FRAME_PROTECTED_PREFIXES)
            or path in _FRAME_PROTECTED_STATIC
        )
        if protected:
            response.headers["X-Frame-Options"] = "SAMEORIGIN"
            response.headers["Content-Security-Policy"] = "frame-ancestors 'self';"
        return response


app.add_middleware(ClickjackingProtectionMiddleware)

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/", include_in_schema=False)
async def landing_page():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"), media_type="text/html")

@app.get("/favicon.png", include_in_schema=False)
async def favicon():
    return FileResponse(os.path.join(STATIC_DIR, "favicon.png"), media_type="image/png")

@app.get("/privacy", include_in_schema=False)
async def privacy_page():
    return FileResponse(os.path.join(STATIC_DIR, "privacy.html"), media_type="text/html")

@app.get("/terms", include_in_schema=False)
async def terms_page():
    return FileResponse(os.path.join(STATIC_DIR, "terms.html"), media_type="text/html")

@app.get("/disclaimer", include_in_schema=False)
async def disclaimer_page():
    return FileResponse(os.path.join(STATIC_DIR, "disclaimer.html"), media_type="text/html")

@app.get("/marketing/samples", include_in_schema=False)
async def samples_page():
    return FileResponse(os.path.join(STATIC_DIR, "samples.html"), media_type="text/html")

@app.get("/why-geri", include_in_schema=False)
async def why_geri_page():
    return FileResponse(os.path.join(STATIC_DIR, "why-geri.html"), media_type="text/html")

@app.get("/admin", include_in_schema=False)
async def admin_page():
    response = FileResponse(os.path.join(STATIC_DIR, "admin.html"), media_type="text/html")
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.get("/users", include_in_schema=False)
async def users_auth_page():
    return FileResponse(os.path.join(STATIC_DIR, "users.html"), media_type="text/html")

@app.get("/users/verify", include_in_schema=False)
async def users_verify_page():
    return FileResponse(os.path.join(STATIC_DIR, "users.html"), media_type="text/html")

@app.get("/users/account", include_in_schema=False)
async def users_account_page():
    response = FileResponse(os.path.join(STATIC_DIR, "users-account.html"), media_type="text/html")
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.get("/users/account.html", include_in_schema=False)
async def users_account_page_html():
    """Redirect to canonical URL for SEO."""
    return RedirectResponse(url="/users/account", status_code=301)

@app.get("/users/email-login", include_in_schema=False)
async def users_email_login_page():
    """Magic-login landing page from newsletter emails: exchanges the token for
    a session, stores it the same way the sign-in page does, then forwards to
    the account page. Falls back to /users on failure."""
    html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="robots" content="noindex, nofollow">
  <title>Signing you in… | EnergyRiskIQ</title>
</head>
<body style="margin:0;background:#0f172a;color:#e2e8f0;font-family:Arial,Helvetica,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;">
  <div style="text-align:center;">
    <p style="color:#d4a017;font-size:20px;font-weight:bold;margin:0 0 10px;">EnergyRiskIQ</p>
    <p id="msg" style="color:#94a3b8;font-size:14px;">Signing you in…</p>
  </div>
  <script>
  (async function() {
    var params = new URLSearchParams(window.location.search);
    var t = params.get('t');
    try { history.replaceState(null, '', '/users/email-login'); } catch (e) {}
    if (!t) { window.location.replace('/users'); return; }
    try {
      var res = await fetch('/users/email-login/exchange', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: t })
      });
      var data = await res.json();
      if (res.ok && data.success && data.token) {
        localStorage.setItem('userSession', JSON.stringify({
          token: data.token,
          user: data.user,
          expires: Date.now() + (7 * 24 * 60 * 60 * 1000)
        }));
        window.location.replace('/users/account');
      } else {
        document.getElementById('msg').textContent = 'This login link has expired. Redirecting to sign in…';
        setTimeout(function() { window.location.replace('/users'); }, 1800);
      }
    } catch (e) {
      window.location.replace('/users');
    }
  })();
  </script>
</body>
</html>"""
    return HTMLResponse(content=html, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})

@app.get("/energy-risk-intelligence-signals", include_in_schema=False)
async def signals_landing_page():
    response = FileResponse(os.path.join(STATIC_DIR, "energy-risk-intelligence-signals.html"), media_type="text/html")
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response

app.include_router(router)
app.include_router(risk_router)
app.include_router(alert_router)
app.include_router(marketing_router)
app.include_router(internal_router)
app.include_router(digest_router)
app.include_router(daily_digest_router)
app.include_router(linkedin_router)
app.include_router(contact_router)
app.include_router(admin_router)
app.include_router(user_router)
app.include_router(ops_router)
app.include_router(telegram_router)
app.include_router(seo_router)
app.include_router(billing_router)
app.add_api_route("/api/v1/billing/webhook", stripe_webhook, methods=["POST"])
app.include_router(signals_router)

if ENABLE_GERI:
    app.include_router(geri_router)
    app.include_router(geri_live_router)
    logger.info("GERI module enabled - routes registered (including Live endpoints)")

if ENABLE_EERI:
    app.include_router(eeri_router)
    app.include_router(eeri_seo_router)
    app.include_router(eeri_pro_router)
    logger.info("EERI module enabled - routes registered (including Pro endpoints)")

if ENABLE_EGSI:
    app.include_router(egsi_router)
    app.include_router(egsi_seo_router)
    logger.info("EGSI module enabled - routes registered")

if ENABLE_ERIQ:
    app.include_router(eriq_router)
    logger.info("ERIQ Expert Analyst module enabled - routes registered")

app.include_router(elsa_router)
logger.info("ELSA Marketing Bot module enabled - routes registered")

app.include_router(tickets_router)
app.include_router(blog_router)
app.include_router(snapshot_router)
app.include_router(forecast_router)
app.include_router(gas_storage_router)
app.include_router(gas_storage_germany_router)
app.include_router(lng_router)
app.include_router(jkm_router)
app.include_router(ttf_router)
app.include_router(brent_router)
app.include_router(jkm_chart_router)
app.include_router(lng_drivers_router)
app.include_router(natgas_router)
app.include_router(wti_router)
app.include_router(wti_widget_router)
app.include_router(gas_storage_widget_router)
app.include_router(lng_widget_router)
from src.api.contact_routes import run_contact_confirmation_migration
try:
    run_contact_confirmation_migration()
except Exception as _e:
    logger.error(f"contact confirmation migration error: {_e}")

from src.api.brent_forecast_routes import router as brent_forecast_router, run_brent_forecast_migration
app.include_router(brent_forecast_router)
try:
    run_brent_forecast_migration()
except Exception as _e:
    logger.error(f"brent_forecast migration error: {_e}")
from src.api.wti_pro_widget_routes import router as wti_pro_widget_router, run_wti_pro_widget_migration
app.include_router(wti_pro_widget_router)
try:
    run_wti_pro_widget_migration()
except Exception as _e:
    logger.error(f"wti_pro_widget migration error: {_e}")
from src.api.lng_pro_widget_routes import router as lng_pro_widget_router, run_lng_pro_widget_migration
app.include_router(lng_pro_widget_router)
try:
    run_lng_pro_widget_migration()
except Exception as _e:
    logger.error(f"lng_pro_widget migration error: {_e}")
from src.api.gas_storage_pro_widget_routes import router as gas_storage_pro_widget_router, run_gas_storage_pro_widget_migration
app.include_router(gas_storage_pro_widget_router)
try:
    run_gas_storage_pro_widget_migration()
except Exception as _e:
    logger.error(f"gas_storage_pro_widget migration error: {_e}")
from src.api.indices_history_routes import router as indices_history_router, run_indices_history_migration
app.include_router(indices_history_router)
try:
    run_indices_history_migration()
except Exception as _e:
    logger.error(f"indices_history migration error: {_e}")
from src.api.daily_report_routes import router as daily_report_router, run_daily_report_migration
app.include_router(daily_report_router)
try:
    run_daily_report_migration()
except Exception as _e:
    logger.error(f"daily_report migration error: {_e}")
from src.api.alerts_access_routes import router as alerts_access_router, run_alerts_access_migration
app.include_router(alerts_access_router)
try:
    run_alerts_access_migration()
except Exception as _e:
    logger.error(f"alerts_access migration error: {_e}")
from src.api.geri_live_sub_routes import router as geri_live_sub_router, run_geri_live_sub_migration
app.include_router(geri_live_sub_router)
try:
    run_geri_live_sub_migration()
except Exception as _e:
    logger.error(f"geri_live_sub migration error: {_e}")
from src.api.widget_embed_tracking_routes import router as widget_embed_tracking_router, run_widget_embed_tracking_migration
app.include_router(widget_embed_tracking_router)
try:
    run_widget_embed_tracking_migration()
except Exception as _e:
    logger.error(f"widget_embed_tracking migration error: {_e}")
from src.api.user_activity_tracking_routes import router as user_activity_tracking_router, run_user_activity_migration
app.include_router(user_activity_tracking_router)
try:
    run_user_activity_migration()
except Exception as _e:
    logger.error(f"user_activity migration error: {_e}")
logger.info("Tickets module enabled - routes registered")

@app.on_event("startup")
async def startup_event():
    logger.info("Starting EnergyRiskIQ API...")
    try:
        run_migrations()
        run_seo_tables_migration()
        run_sources_migration()
        run_geri_migration()
        run_pro_delivery_migration()
        run_fix_skipped_alerts()
        run_lng_price_migration()
        run_lng_import_sources_migration()
        run_gas_storage_country_migration()
        run_signal_quality_migration()
        _recalculate_stale_bands()
        run_stripe_mode_migration()
        if ENABLE_ERIQ:
            run_eriq_migration()
            logger.info("ERIQ Expert Analyst module is ENABLED")
        from src.tickets.db import run_tickets_migration, auto_close_stale_tickets, auto_archive_closed_tickets
        run_tickets_migration()
        from src.blog.db import run_blog_migrations
        run_blog_migrations()
        try:
            closed = auto_close_stale_tickets()
            archived = auto_archive_closed_tickets()
            if closed or archived:
                logger.info(f"Ticket maintenance: {closed} auto-closed, {archived} auto-archived")
        except Exception as e:
            logger.warning(f"Ticket auto-maintenance skipped: {e}")
        from src.api.admin_routes import _init_admin_sessions_table, _init_bulk_email_table
        _init_admin_sessions_table()
        _init_bulk_email_table()
        from src.api.user_routes import _init_email_login_tokens_table, _init_password_reset_tokens_table, _init_last_login_column
        _init_email_login_tokens_table()
        _init_password_reset_tokens_table()
        _init_last_login_column()
        logger.info("Database migrations completed")
        app_url = os.environ.get("APP_URL", "")
        if app_url and os.environ.get("TELEGRAM_BOT_TOKEN"):
            from src.api.telegram_routes import setup_webhook
            setup_webhook(app_url.rstrip("/"))
        from src.ingest.intraday_prices import run_intraday_migration
        run_intraday_migration()
        if ENABLE_GERI:
            from src.geri.live import run_geri_live_migration, run_geri_live_history_migration, periodic_geri_live_recompute
            run_geri_live_migration()
            run_geri_live_history_migration()
            asyncio.create_task(periodic_geri_live_recompute())
            logger.info("GERI module is ENABLED (including Live + periodic recompute)")
        else:
            logger.info("GERI module is DISABLED (set ENABLE_GERI=true to enable)")
    except Exception as e:
        logger.error(f"Failed to run migrations: {e}")
        raise

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get('PORT', 5000))
    uvicorn.run(app, host="0.0.0.0", port=port)
