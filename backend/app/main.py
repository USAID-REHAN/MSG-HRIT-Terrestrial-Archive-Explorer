"""FastAPI entrypoint — MSG HRIT Terrestrial Archive Explorer backend."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import browse, discovery, final_globes, globe, jobs
from app.api.schemas import HealthResponse
from app.config import get_settings
from app.db.session import get_session_factory, init_db
from app.demo_bootstrap import install_demo_bundle_if_needed
from app.jobs.manager import job_manager
from app.reference.product_reference import seed_product_reference

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    settings.ensure_data_dirs()
    if install_demo_bundle_if_needed(settings):
        logger.info("Bundled demo catalog ready for %s", settings.data_root)
    init_db()
    factory = get_session_factory()
    db = factory()
    try:
        n = seed_product_reference(db)
        logger.info("DB ready. Seeded %s product_reference row(s).", n)
    finally:
        db.close()
    interrupted = job_manager.reconcile_interrupted_jobs()
    if interrupted:
        logger.warning("Marked %s interrupted job(s) as paused.", interrupted)
    yield


app = FastAPI(
    title="MSG HRIT Terrestrial Archive Explorer",
    description="Discovery, sample download, satpy processing, and browse API",
    version="1.0.0",
    lifespan=lifespan,
)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.frontend_origin,
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(discovery.router, prefix="/api")
app.include_router(jobs.router, prefix="/api")
app.include_router(browse.router, prefix="/api")
app.include_router(final_globes.router, prefix="/api")
app.include_router(globe.router, prefix="/api")


@app.get("/api/health", response_model=HealthResponse)
def health():
    settings = get_settings()
    db_ok = False
    try:
        init_db()
        factory = get_session_factory()
        db = factory()
        try:
            db.execute(__import__("sqlalchemy").text("SELECT 1"))
            db_ok = True
        finally:
            db.close()
    except Exception:  # noqa: BLE001
        db_ok = False
    return HealthResponse(
        status="ok" if db_ok else "degraded",
        service="msg-hrit-backend",
        db_ok=db_ok,
        data_root=str(settings.data_root),
        archive_url=settings.archive_url,
    )


@app.get("/")
def root():
    return {
        "service": "MSG HRIT Terrestrial Archive Explorer API",
        "docs": "/docs",
        "health": "/api/health",
    }
