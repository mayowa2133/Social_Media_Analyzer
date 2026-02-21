"""
Social Performance Coach - FastAPI Backend
Main application entry point with health check and API routing.
"""

import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import os

from config import settings, validate_security_settings
from database import engine, Base
import models  # noqa: F401
from routers import (
    health,
    auth,
    youtube,
    analysis,
    audit,
    competitor,
    feed,
    report,
    research,
    optimizer,
    outcomes,
    billing,
    media,
)
from services.audit_queue import (
    recover_stalled_audits,
    recover_stalled_feed_transcript_jobs,
    recover_stalled_media_download_jobs,
)
from services.feed_discovery import run_due_feed_auto_ingest_service
from services.outcomes import run_calibration_refresh_for_all_users_service


async def _periodic_outcome_recalibration() -> None:
    interval_minutes = max(int(settings.OUTCOME_RECALIBRATE_INTERVAL_MINUTES), 0)
    if interval_minutes <= 0:
        return
    while True:
        await asyncio.sleep(interval_minutes * 60)
        try:
            result = await run_calibration_refresh_for_all_users_service()
            print(
                f"📈 Outcome recalibration: refreshed={result.get('refreshed', 0)} "
                f"skipped={result.get('skipped', 0)}"
            )
        except Exception as exc:
            print(f"⚠️ Outcome recalibration tick failed: {exc}")


async def _periodic_feed_auto_ingest() -> None:
    interval_minutes = max(int(settings.FEED_AUTO_INGEST_INTERVAL_MINUTES), 0)
    if interval_minutes <= 0:
        return
    while True:
        await asyncio.sleep(interval_minutes * 60)
        try:
            result = await run_due_feed_auto_ingest_service()
            scheduled = int(result.get("scheduled_count", 0) or 0)
            completed = int(result.get("completed_count", 0) or 0)
            failed = int(result.get("failed_count", 0) or 0)
            if scheduled:
                print(
                    f"📰 Feed auto-ingest tick: scheduled={scheduled} "
                    f"completed={completed} failed={failed}"
                )
        except Exception as exc:
            print(f"⚠️ Feed auto-ingest tick failed: {exc}")


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
    try:
        recovered_media = await recover_stalled_media_download_jobs()
        if recovered_media:
            print(f"♻️ Recovered {recovered_media} stalled media download jobs after startup.")
    except Exception as exc:
        print(f"⚠️ Stalled media recovery skipped: {exc}")
    try:
        recovered_transcripts = await recover_stalled_feed_transcript_jobs()
        if recovered_transcripts:
            print(f"♻️ Recovered {recovered_transcripts} stalled feed transcript jobs after startup.")
    except Exception as exc:
        print(f"⚠️ Stalled feed transcript recovery skipped: {exc}")
    recalibration_task = None
    feed_auto_ingest_task = None
    if settings.OUTCOME_LEARNING_ENABLED and int(settings.OUTCOME_RECALIBRATE_INTERVAL_MINUTES) > 0:
        recalibration_task = asyncio.create_task(_periodic_outcome_recalibration())
        print(
            "📅 Outcome recalibration loop enabled "
            f"(every {int(settings.OUTCOME_RECALIBRATE_INTERVAL_MINUTES)} min)."
        )
    if settings.RESEARCH_ENABLED and settings.FEED_AUTO_INGEST_ENABLED and int(settings.FEED_AUTO_INGEST_INTERVAL_MINUTES) > 0:
        feed_auto_ingest_task = asyncio.create_task(_periodic_feed_auto_ingest())
        print(
            "📅 Feed auto-ingest loop enabled "
            f"(every {int(settings.FEED_AUTO_INGEST_INTERVAL_MINUTES)} min)."
        )
    yield
    # Shutdown
    if recalibration_task is not None:
        recalibration_task.cancel()
        try:
            await recalibration_task
        except asyncio.CancelledError:
            pass
    if feed_auto_ingest_task is not None:
        feed_auto_ingest_task.cancel()
        try:
            await feed_auto_ingest_task
        except asyncio.CancelledError:
            pass
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
app.include_router(feed.router, prefix="/feed", tags=["Feed"])
app.include_router(report.router, prefix="/report", tags=["Report"])
app.include_router(research.router, prefix="/research", tags=["Research"])
app.include_router(optimizer.router, prefix="/optimizer", tags=["Optimizer"])
app.include_router(outcomes.router, prefix="/outcomes", tags=["Outcomes"])
app.include_router(billing.router, prefix="/billing", tags=["Billing"])
app.include_router(media.router, prefix="/media", tags=["Media"])


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "Social Performance Coach API",
        "version": "0.1.0",
        "status": "running"
    }
