"""
Health check endpoints.
"""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as redis

from config import settings

router = APIRouter()


@router.get("/health")
async def health_check():
    """
    Health check endpoint.
    Returns overall system health status.
    """
    health_status = {
        "status": "healthy",
        "api": "up",
        "database": "unknown",
        "redis": "unknown",
        "youtube_api_key": "configured" if settings.YOUTUBE_API_KEY else "missing",
    }
    
    # Check database connection
    try:
        from database import engine
        from sqlalchemy import text
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        health_status["database"] = "up"
    except Exception as e:
        health_status["database"] = f"down: {str(e)}"
        health_status["status"] = "degraded"
    
    # Check Redis connection
    try:
        r = redis.from_url(settings.REDIS_URL)
        await r.ping()
        await r.close()
        health_status["redis"] = "up"
    except Exception as e:
        health_status["redis"] = f"down: {str(e)}"
        health_status["status"] = "degraded"
    
    return health_status


@router.get("/health/ready")
async def readiness_check():
    """Kubernetes-style readiness probe."""
    missing = []
    if not settings.YOUTUBE_API_KEY:
        missing.append("YOUTUBE_API_KEY")

    if missing:
        return JSONResponse(
            status_code=503,
            content={"ready": False, "missing": missing},
        )
    return {"ready": True}


@router.get("/health/live")
async def liveness_check():
    """Kubernetes-style liveness probe."""
    return {"alive": True}
