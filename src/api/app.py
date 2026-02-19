import os
import sys
import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.api.routes import router
from src.api.risk_routes import router as risk_router
from src.api.alert_routes import router as alert_router
from src.api.marketing_routes import router as marketing_router
from src.api.internal_routes import router as internal_router
from src.api.digest_routes import router as digest_router
from src.api.daily_digest_routes import router as daily_digest_router
from src.api.contact_routes import router as contact_router
from src.api.admin_routes import router as admin_router
from src.api.user_routes import router as user_router
from src.api.ops_routes import router as ops_router
from src.api.telegram_routes import router as telegram_router
from src.api.seo_routes import router as seo_router
from src.billing.billing_routes import router as billing_router
from src.db.migrations import run_migrations, run_seo_tables_migration, run_sources_migration, run_geri_migration, run_pro_delivery_migration, run_fix_skipped_alerts, run_signal_quality_migration, _recalculate_stale_bands, run_eriq_migration, run_lng_price_migration, run_stripe_mode_migration
from src.geri import ENABLE_GERI
from src.geri.routes import router as geri_router
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
    return FileResponse(os.path.join(STATIC_DIR, "admin.html"), media_type="text/html")

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
app.include_router(contact_router)
app.include_router(admin_router)
app.include_router(user_router)
app.include_router(ops_router)
app.include_router(telegram_router)
app.include_router(seo_router)
app.include_router(billing_router)
app.include_router(signals_router)

if ENABLE_GERI:
    app.include_router(geri_router)
    logger.info("GERI module enabled - routes registered")

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
        run_signal_quality_migration()
        _recalculate_stale_bands()
        run_stripe_mode_migration()
        if ENABLE_ERIQ:
            run_eriq_migration()
            logger.info("ERIQ Expert Analyst module is ENABLED")
        logger.info("Database migrations completed")
        if ENABLE_GERI:
            logger.info("GERI module is ENABLED")
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
