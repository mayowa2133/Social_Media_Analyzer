"""
Social Performance Coach - FastAPI Backend
Main application entry point with health check and API routing.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import os

from config import settings, validate_security_settings
from database import engine, Base
import models  # noqa: F401
from routers import health, auth, youtube, analysis, audit, competitor, report
from services.audit_queue import recover_stalled_audits


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown."""
    # Startup
    print("🚀 Starting Social Performance Coach API...")
    validate_security_settings()
    if settings.AUTO_CREATE_DB_SCHEMA:
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            print("🗄️ Database schema verified.")
        except Exception as e:
            print(f"⚠️ Database bootstrap skipped: {e}")
    try:
        recovered = await recover_stalled_audits()
        if recovered:
            print(f"♻️ Recovered {recovered} stalled audits after startup.")
    except Exception as exc:
        print(f"⚠️ Stalled audit recovery skipped: {exc}")
    yield
    # Shutdown
    print("👋 Shutting down API...")


app = FastAPI(
    title="Social Performance Coach API",
    description="Audit social media performance and get actionable recommendations",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router, tags=["Health"])
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(youtube.router, prefix="/youtube", tags=["YouTube"])
app.include_router(analysis.router, prefix="/analysis", tags=["Analysis"])
app.include_router(audit.router, prefix="/audit", tags=["Audit"])
app.include_router(competitor.router, prefix="/competitors", tags=["Competitor"])
app.include_router(report.router, prefix="/report", tags=["Report"])


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "Social Performance Coach API",
        "version": "0.1.0",
        "status": "running"
    }
