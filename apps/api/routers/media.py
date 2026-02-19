"""Media download job router."""

from __future__ import annotations

import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from config import settings
from database import get_db
from models.media_download_job import MediaDownloadJob
from models.user import User
from routers.auth_scope import AuthContext, ensure_user_scope, get_auth_context
from routers.rate_limit import rate_limit
from services.audit_queue import enqueue_media_download_job

router = APIRouter()


class CreateMediaDownloadRequest(BaseModel):
    platform: Literal["youtube", "instagram", "tiktok"] = "instagram"
    source_url: str = Field(min_length=8, max_length=2000)
    user_id: Optional[str] = None


class MediaDownloadJobResponse(BaseModel):
    job_id: str
    platform: str
    source_url: str
    status: str
    progress: int
    attempts: int
    max_attempts: int
    queue_job_id: Optional[str] = None
    media_asset_id: Optional[str] = None
    upload_id: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    created_at: Optional[str] = None
    completed_at: Optional[str] = None


async def _ensure_user(db: AsyncSession, user_id: str) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user:
        return user
    user = User(id=user_id, email=f"{user_id}@local.invalid")
    db.add(user)
    await db.flush()
    return user


def _serialize_job(job: MediaDownloadJob) -> MediaDownloadJobResponse:
    return MediaDownloadJobResponse(
        job_id=job.id,
        platform=job.platform,
        source_url=job.source_url,
        status=job.status,
        progress=int(job.progress or 0),
        attempts=int(job.attempts or 0),
        max_attempts=int(job.max_attempts or 3),
        queue_job_id=job.queue_job_id,
        media_asset_id=job.media_asset_id,
        upload_id=job.upload_id,
        error_code=job.error_code,
        error_message=job.error_message,
        created_at=job.created_at.isoformat() if job.created_at else None,
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
    )


@router.post("/download", response_model=MediaDownloadJobResponse)
async def create_media_download_job(
    request: CreateMediaDownloadRequest,
    _rate_limit: None = Depends(rate_limit("media_download_create", limit=60, window_seconds=3600)),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """Create and enqueue a media download job."""
    if not settings.ALLOW_EXTERNAL_MEDIA_DOWNLOAD:
        raise HTTPException(
            status_code=503,
            detail=(
                "External media download is disabled. Set ALLOW_EXTERNAL_MEDIA_DOWNLOAD=true "
                "or use upload mode in /audit/new."
            ),
        )

    scoped_user_id = ensure_user_scope(auth.user_id, request.user_id)
    await _ensure_user(db, scoped_user_id)
    source_url = str(request.source_url or "").strip()
    if not source_url.startswith("http://") and not source_url.startswith("https://"):
        raise HTTPException(status_code=422, detail="source_url must be an absolute http(s) URL")

    job = MediaDownloadJob(
        id=str(uuid.uuid4()),
        user_id=scoped_user_id,
        platform=request.platform,
        source_url=source_url,
        status="queued",
        progress=0,
        attempts=0,
        max_attempts=3,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    try:
        queue_job = enqueue_media_download_job(job.id)
        job.queue_job_id = queue_job.id
        await db.commit()
        await db.refresh(job)
    except Exception as exc:
        job.status = "failed"
        job.error_code = "queue_unavailable"
        job.error_message = str(exc)
        await db.commit()
        raise HTTPException(
            status_code=503,
            detail="Media queue unavailable. Check Redis/worker availability and retry.",
        ) from exc

    return _serialize_job(job)


@router.get("/download/{job_id}", response_model=MediaDownloadJobResponse)
async def get_media_download_job(
    job_id: str,
    user_id: Optional[str] = None,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """Get media download job status for the current user."""
    scoped_user_id = ensure_user_scope(auth.user_id, user_id)
    result = await db.execute(
        select(MediaDownloadJob).where(
            MediaDownloadJob.id == job_id,
            MediaDownloadJob.user_id == scoped_user_id,
        )
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Media download job not found")
    return _serialize_job(job)
