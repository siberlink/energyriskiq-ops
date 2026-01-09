import os
import sys
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.api.routes import router
from src.api.risk_routes import router as risk_router
from src.api.alert_routes import router as alert_router
from src.api.marketing_routes import router as marketing_router
from src.api.internal_routes import router as internal_router
from src.api.digest_routes import router as digest_router
from src.db.migrations import run_migrations

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

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")

@app.get("/", include_in_schema=False)
async def landing_page():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"), media_type="text/html")

@app.get("/privacy", include_in_schema=False)
async def privacy_page():
    return FileResponse(os.path.join(STATIC_DIR, "privacy.html"), media_type="text/html")

@app.get("/terms", include_in_schema=False)
async def terms_page():
    return FileResponse(os.path.join(STATIC_DIR, "terms.html"), media_type="text/html")

@app.get("/disclaimer", include_in_schema=False)
async def disclaimer_page():
    return FileResponse(os.path.join(STATIC_DIR, "disclaimer.html"), media_type="text/html")

app.include_router(router)
app.include_router(risk_router)
app.include_router(alert_router)
app.include_router(marketing_router)
app.include_router(internal_router)
app.include_router(digest_router)

@app.on_event("startup")
async def startup_event():
    logger.info("Starting EnergyRiskIQ API...")
    try:
        run_migrations()
        logger.info("Database migrations completed")
    except Exception as e:
        logger.error(f"Failed to run migrations: {e}")
        raise

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get('PORT', 5000))
    uvicorn.run(app, host="0.0.0.0", port=port)
