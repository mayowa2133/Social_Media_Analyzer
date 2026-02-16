"""
Audit router for running full audits and retrieving reports.
"""

import os
import uuid
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Literal

from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends, Query, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from pydantic import BaseModel

from config import settings
from database import get_db
from models.audit import Audit
from models.upload import Upload
from models.user import User
from services.audit import process_video_audit

router = APIRouter()
logger = logging.getLogger(__name__)

MAX_VIDEO_UPLOAD_BYTES = 300 * 1024 * 1024  # 300 MB
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".avi", ".mkv"}
ALLOWED_VIDEO_MIME_PREFIXES = ("video/",)


class RetentionPoint(BaseModel):
    time: float
    retention: float


class PlatformMetricsInput(BaseModel):
    views: Optional[int] = None
    likes: Optional[int] = None
    comments: Optional[int] = None
    shares: Optional[int] = None
    saves: Optional[int] = None
    watch_time_hours: Optional[float] = None
    avg_view_duration_s: Optional[float] = None
    ctr: Optional[float] = None


class CreateAuditRequest(BaseModel):
    source_mode: Literal["url", "upload"] = "url"
    video_url: Optional[str] = None
    upload_id: Optional[str] = None
    retention_points: Optional[List[RetentionPoint]] = None
    platform_metrics: Optional[PlatformMetricsInput] = None
    user_id: str


class AuditStatusResponse(BaseModel):
    audit_id: str
    status: str
    progress: str
    created_at: Optional[str] = None
    output: Optional[dict] = None
    error: Optional[str] = None


class UploadVideoResponse(BaseModel):
    upload_id: str
    file_name: str
    mime_type: Optional[str] = None
    file_size_bytes: int
    status: str


def _sanitize_filename(filename: str) -> str:
    base = os.path.basename(filename or "upload.mp4")
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in base)
    return safe or "upload.mp4"


async def _ensure_user(db: AsyncSession, user_id: str) -> User:
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        user = User(id=user_id, email=f"{user_id}@local.invalid")
        db.add(user)
        await db.flush()
    return user


def _cleanup_stale_upload_files() -> None:
    """Best-effort cleanup of old uploaded files to limit disk growth."""
    retention_hours = max(int(settings.AUDIT_UPLOAD_RETENTION_HOURS), 1)
    root = Path(settings.AUDIT_UPLOAD_DIR)
    if not root.exists():
        return

    cutoff = datetime.now(timezone.utc) - timedelta(hours=retention_hours)
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            if mtime < cutoff:
                path.unlink(missing_ok=True)
        except Exception as exc:
            logger.warning("Could not cleanup stale upload file %s: %s", path, exc)


@router.post("/upload", response_model=UploadVideoResponse)
async def upload_audit_video(
    file: UploadFile = File(...),
    user_id: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload a local video file for audit processing."""
    await _ensure_user(db, user_id)

    original_filename = _sanitize_filename(file.filename or "upload.mp4")
    suffix = Path(original_filename).suffix.lower()
    content_type = (file.content_type or "").lower()

    if suffix not in ALLOWED_VIDEO_EXTENSIONS and not content_type.startswith(ALLOWED_VIDEO_MIME_PREFIXES):
        raise HTTPException(
            status_code=422,
            detail="Unsupported file type. Upload a video file (mp4, mov, m4v, webm, avi, mkv).",
        )

    upload_id = str(uuid.uuid4())
    user_dir = Path(settings.AUDIT_UPLOAD_DIR) / user_id
    user_dir.mkdir(parents=True, exist_ok=True)
    stored_filename = f"{upload_id}_{original_filename}"
    destination = user_dir / stored_filename

    total_size = 0
    try:
        with destination.open("wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > MAX_VIDEO_UPLOAD_BYTES:
                    out.close()
                    destination.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413,
                        detail=f"File too large. Max upload size is {MAX_VIDEO_UPLOAD_BYTES // (1024 * 1024)}MB.",
                    )
                out.write(chunk)
    finally:
        await file.close()

    upload = Upload(
        id=upload_id,
        user_id=user_id,
        file_url=str(destination),
        file_type="video",
        original_filename=original_filename,
        file_size_bytes=total_size,
        mime_type=content_type or None,
    )
    db.add(upload)
    await db.commit()
    _cleanup_stale_upload_files()

    return UploadVideoResponse(
        upload_id=upload_id,
        file_name=original_filename,
        mime_type=content_type or None,
        file_size_bytes=total_size,
        status="uploaded",
    )


@router.post("/run_multimodal")
async def run_multimodal_audit(
    request: CreateAuditRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Start a new multimodal audit for a video."""
    if request.source_mode == "url" and not request.video_url:
        raise HTTPException(status_code=422, detail="video_url is required for source_mode='url'")
    if request.source_mode == "upload" and not request.upload_id:
        raise HTTPException(status_code=422, detail="upload_id is required for source_mode='upload'")

    await _ensure_user(db, request.user_id)

    upload_record: Optional[Upload] = None
    upload_path: Optional[str] = None
    if request.source_mode == "upload":
        upload_result = await db.execute(
            select(Upload).where(
                Upload.id == request.upload_id,
                Upload.user_id == request.user_id,
                Upload.file_type == "video",
            )
        )
        upload_record = upload_result.scalar_one_or_none()
        if not upload_record:
            raise HTTPException(status_code=404, detail="Upload not found for this user")
        upload_path = upload_record.file_url
        if not upload_path or not Path(upload_path).exists():
            raise HTTPException(status_code=404, detail="Uploaded file is missing on disk")

    audit_id = str(uuid.uuid4())

    # Create Audit record
    db_audit = Audit(
        id=audit_id,
        user_id=request.user_id,
        status="pending",
        progress="0",
        input_json={
            "source_mode": request.source_mode,
            "video_url": request.video_url,
            "upload_id": request.upload_id,
            "upload_file_name": upload_record.original_filename if upload_record else None,
            "retention_points": [p.model_dump() for p in (request.retention_points or [])],
            "platform_metrics": request.platform_metrics.model_dump(exclude_none=True) if request.platform_metrics else None,
        }
    )
    db.add(db_audit)
    await db.commit()
    await db.refresh(db_audit)

    # Trigger background task
    background_tasks.add_task(
        process_video_audit,
        audit_id,
        request.video_url,
        upload_path,
        request.source_mode,
    )

    return {"audit_id": audit_id, "status": "pending"}


@router.get("/")
async def list_audits(
    user_id: str = Query(...),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List recent audits for a user."""
    result = await db.execute(
        select(Audit)
        .where(Audit.user_id == user_id)
        .order_by(Audit.created_at.desc())
        .limit(limit)
    )
    audits = result.scalars().all()
    return [
        {
            "audit_id": audit.id,
            "status": audit.status,
            "progress": audit.progress,
            "created_at": audit.created_at.isoformat() if audit.created_at else None,
            "completed_at": audit.completed_at.isoformat() if audit.completed_at else None,
        }
        for audit in audits
    ]

@router.get("/{audit_id}")
async def get_audit_status(
    audit_id: str,
    user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Get status of an audit."""
    result = await db.execute(
        select(Audit).where(
            Audit.id == audit_id,
            Audit.user_id == user_id,
        )
    )
    audit = result.scalar_one_or_none()
    
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")
        
    return {
        "audit_id": audit.id,
        "status": audit.status,
        "progress": audit.progress,
        "created_at": str(audit.created_at),
        "output": audit.output_json,
        "error": audit.error_message
    }
