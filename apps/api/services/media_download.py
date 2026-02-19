"""Durable media download and asset materialization service."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy.future import select

from config import settings
from database import async_session_maker
from models.media_asset import MediaAsset
from models.media_download_job import MediaDownloadJob
from models.upload import Upload
from multimodal.video import download_video, get_video_duration_seconds

logger = logging.getLogger(__name__)

VIDEO_MIME_BY_EXT = {
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".m4v": "video/x-m4v",
    ".webm": "video/webm",
    ".avi": "video/x-msvideo",
    ".mkv": "video/x-matroska",
}


def _safe_filename(name: str) -> str:
    base = os.path.basename(name or "download.mp4")
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in base)
    return cleaned or "download.mp4"


def _guess_mime(path: Path) -> str:
    return VIDEO_MIME_BY_EXT.get(path.suffix.lower(), "video/mp4")


async def _get_job(job_id: str) -> Optional[MediaDownloadJob]:
    async with async_session_maker() as db:
        result = await db.execute(select(MediaDownloadJob).where(MediaDownloadJob.id == job_id))
        return result.scalar_one_or_none()


async def _update_job(
    job_id: str,
    *,
    status: Optional[str] = None,
    progress: Optional[int] = None,
    error_code: Optional[str] = None,
    error_message: Optional[str] = None,
    queue_job_id: Optional[str] = None,
    media_asset_id: Optional[str] = None,
    upload_id: Optional[str] = None,
    increment_attempts: bool = False,
    completed: bool = False,
) -> None:
    async with async_session_maker() as db:
        result = await db.execute(select(MediaDownloadJob).where(MediaDownloadJob.id == job_id))
        job = result.scalar_one_or_none()
        if not job:
            return
        if status is not None:
            job.status = status
        if progress is not None:
            job.progress = max(0, min(int(progress), 100))
        if error_code is not None:
            job.error_code = error_code
        if error_message is not None:
            job.error_message = error_message[:1000]
        if queue_job_id is not None:
            job.queue_job_id = queue_job_id
        if media_asset_id is not None:
            job.media_asset_id = media_asset_id
        if upload_id is not None:
            job.upload_id = upload_id
        if increment_attempts:
            job.attempts = max(int(job.attempts or 0), 0) + 1
        if completed:
            job.completed_at = datetime.now(timezone.utc)
        await db.commit()


async def process_media_download_job_async(job_id: str) -> None:
    """Async media download pipeline executed by RQ worker wrapper."""
    job = await _get_job(job_id)
    if not job:
        logger.warning("Media download job %s not found", job_id)
        return

    temp_root = Path(settings.AUDIT_UPLOAD_DIR) / "_media_tmp" / job.user_id
    temp_root.mkdir(parents=True, exist_ok=True)
    temp_output = temp_root / f"{job_id}.mp4"

    final_path: Optional[Path] = None
    downloaded_path: Optional[Path] = None
    try:
        await _update_job(
            job_id,
            status="downloading",
            progress=20,
            error_code=None,
            error_message=None,
            increment_attempts=True,
        )

        downloaded_raw = await asyncio.to_thread(download_video, job.source_url, str(temp_output))
        downloaded_path = Path(downloaded_raw)
        if not downloaded_path.exists():
            raise FileNotFoundError("Downloaded media file missing after downloader completed.")

        await _update_job(job_id, status="processing", progress=65)

        duration_seconds = await asyncio.to_thread(get_video_duration_seconds, str(downloaded_path))
        file_size_bytes = downloaded_path.stat().st_size
        final_dir = Path(settings.AUDIT_UPLOAD_DIR) / job.user_id
        final_dir.mkdir(parents=True, exist_ok=True)
        final_name = _safe_filename(f"{job_id}{downloaded_path.suffix or '.mp4'}")
        final_path = final_dir / final_name
        shutil.move(str(downloaded_path), str(final_path))

        async with async_session_maker() as db:
            db_result = await db.execute(select(MediaDownloadJob).where(MediaDownloadJob.id == job_id))
            db_job = db_result.scalar_one_or_none()
            if not db_job:
                return

            upload_id = str(uuid.uuid4())
            upload = Upload(
                id=upload_id,
                user_id=db_job.user_id,
                file_url=str(final_path),
                file_type="video",
                original_filename=final_name,
                file_size_bytes=file_size_bytes,
                mime_type=_guess_mime(final_path),
            )
            db.add(upload)

            media_asset_id = str(uuid.uuid4())
            asset = MediaAsset(
                id=media_asset_id,
                user_id=db_job.user_id,
                platform=db_job.platform,
                source_url=db_job.source_url,
                file_path=str(final_path),
                file_name=final_name,
                file_size_bytes=file_size_bytes,
                mime_type=_guess_mime(final_path),
                duration_seconds=max(int(duration_seconds or 0), 0),
                transcript_status="pending",
                upload_id=upload_id,
            )
            db.add(asset)

            db_job.status = "completed"
            db_job.progress = 100
            db_job.error_code = None
            db_job.error_message = None
            db_job.media_asset_id = media_asset_id
            db_job.upload_id = upload_id
            db_job.completed_at = datetime.now(timezone.utc)
            await db.commit()
        logger.info("Media download job %s completed", job_id)
    except Exception as exc:
        logger.exception("Media download job %s failed: %s", job_id, exc)
        await _update_job(
            job_id,
            status="failed",
            progress=100,
            error_code="download_failed",
            error_message=str(exc),
            completed=True,
        )
        if final_path and final_path.exists():
            try:
                final_path.unlink(missing_ok=True)
            except Exception:
                logger.warning("Could not cleanup failed final media path %s", final_path)
    finally:
        if downloaded_path and downloaded_path.exists():
            try:
                downloaded_path.unlink(missing_ok=True)
            except Exception:
                logger.warning("Could not cleanup temporary downloaded media %s", downloaded_path)
        if temp_output.exists():
            try:
                temp_output.unlink(missing_ok=True)
            except Exception:
                logger.warning("Could not cleanup temp output %s", temp_output)


def process_media_download_job(job_id: str) -> None:
    """RQ worker entrypoint for media download jobs."""
    asyncio.run(process_media_download_job_async(job_id))
