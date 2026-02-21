"""Feed transcript job processing service."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from sqlalchemy.future import select

from config import settings
from database import async_session_maker
from models.feed_transcript_job import FeedTranscriptJob
from models.media_asset import MediaAsset
from models.media_download_job import MediaDownloadJob
from models.research_item import ResearchItem
from multimodal.audio import extract_audio, transcribe_audio

logger = logging.getLogger(__name__)


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _transcript_text_from_payload(payload: Any) -> str:
    if isinstance(payload, dict):
        text = _safe_text(payload.get("text"))
        if text:
            return text
        segments = payload.get("segments")
        if isinstance(segments, list):
            chunked = []
            for segment in segments:
                if isinstance(segment, dict):
                    chunk = _safe_text(segment.get("text"))
                else:
                    chunk = _safe_text(getattr(segment, "text", ""))
                if chunk:
                    chunked.append(chunk)
            return " ".join(chunked).strip()
        return ""
    text = _safe_text(getattr(payload, "text", ""))
    if text:
        return text
    segments = getattr(payload, "segments", []) or []
    chunked = [_safe_text(getattr(segment, "text", "")) for segment in segments]
    return " ".join([row for row in chunked if row]).strip()


async def _update_job(
    job_id: str,
    *,
    status: Optional[str] = None,
    progress: Optional[int] = None,
    queue_job_id: Optional[str] = None,
    error_code: Optional[str] = None,
    error_message: Optional[str] = None,
    transcript_source: Optional[str] = None,
    transcript_text: Optional[str] = None,
    increment_attempts: bool = False,
    completed: bool = False,
) -> None:
    async with async_session_maker() as db:
        result = await db.execute(select(FeedTranscriptJob).where(FeedTranscriptJob.id == job_id))
        job = result.scalar_one_or_none()
        if not job:
            return
        if status is not None:
            job.status = status
        if progress is not None:
            job.progress = max(0, min(int(progress), 100))
        if queue_job_id is not None:
            job.queue_job_id = queue_job_id
        if error_code is not None:
            job.error_code = error_code
        if error_message is not None:
            job.error_message = _safe_text(error_message)[:1000]
        if transcript_source is not None:
            job.transcript_source = transcript_source
        if transcript_text is not None:
            job.transcript_text = transcript_text[:20000]
        if increment_attempts:
            job.attempts = max(int(job.attempts or 0), 0) + 1
        if completed:
            job.completed_at = datetime.now(timezone.utc)
        await db.commit()


async def _resolve_media_asset(
    *,
    user_id: str,
    item: ResearchItem,
    db: Any,
) -> Optional[MediaAsset]:
    media_meta = item.media_meta_json if isinstance(item.media_meta_json, dict) else {}
    download_job_id = _safe_text(media_meta.get("feed_download_job_id"))
    if not download_job_id:
        return None

    job_result = await db.execute(
        select(MediaDownloadJob).where(
            MediaDownloadJob.id == download_job_id,
            MediaDownloadJob.user_id == user_id,
            MediaDownloadJob.status == "completed",
        )
    )
    download_job = job_result.scalar_one_or_none()
    if not download_job or not download_job.media_asset_id:
        return None

    asset_result = await db.execute(
        select(MediaAsset).where(
            MediaAsset.id == download_job.media_asset_id,
            MediaAsset.user_id == user_id,
        )
    )
    return asset_result.scalar_one_or_none()


async def process_feed_transcript_job_async(job_id: str) -> None:
    """Async processor for feed transcript extraction jobs."""
    async with async_session_maker() as db:
        result = await db.execute(select(FeedTranscriptJob).where(FeedTranscriptJob.id == job_id))
        job = result.scalar_one_or_none()
        if not job:
            logger.warning("Feed transcript job %s not found", job_id)
            return

    try:
        await _update_job(
            job_id,
            status="processing",
            progress=20,
            error_code=None,
            error_message=None,
            increment_attempts=True,
        )

        async with async_session_maker() as db:
            item_result = await db.execute(
                select(ResearchItem).where(
                    ResearchItem.id == job.research_item_id,
                    ResearchItem.user_id == job.user_id,
                )
            )
            item = item_result.scalar_one_or_none()
            if not item:
                raise RuntimeError("Research item not found for transcript job.")

            transcript_source = ""
            transcript_text = ""
            media_asset: Optional[MediaAsset] = None
            if settings.ENABLE_WHISPER_TRANSCRIPTION:
                media_asset = await _resolve_media_asset(user_id=job.user_id, item=item, db=db)

            if media_asset and media_asset.file_path and Path(media_asset.file_path).exists():
                await _update_job(job_id, progress=55)
                transcript_dir = Path(settings.AUDIT_UPLOAD_DIR) / "_feed_transcripts" / job.user_id
                transcript_dir.mkdir(parents=True, exist_ok=True)
                audio_path = transcript_dir / f"{job_id}.mp3"
                try:
                    await asyncio.to_thread(extract_audio, media_asset.file_path, str(audio_path))
                    transcript_payload = await asyncio.to_thread(transcribe_audio, str(audio_path), settings.OPENAI_API_KEY)
                    transcript_text = _transcript_text_from_payload(transcript_payload)
                    transcript_source = "whisper_audio"
                finally:
                    if audio_path.exists():
                        audio_path.unlink(missing_ok=True)

            if not transcript_text:
                caption = _safe_text(item.caption)
                title = _safe_text(item.title)
                if caption:
                    transcript_text = caption
                    transcript_source = "caption_fallback"
                elif title:
                    transcript_text = title
                    transcript_source = "title_fallback"

            if not transcript_text:
                raise RuntimeError("No transcript source available for this feed item.")

            media_meta = item.media_meta_json if isinstance(item.media_meta_json, dict) else {}
            next_meta = {
                **media_meta,
                "transcript_job_id": job.id,
                "transcript_source": transcript_source,
                "transcript_text": transcript_text[:12000],
                "transcript_updated_at": datetime.now(timezone.utc).isoformat(),
            }
            item.media_meta_json = next_meta

            job_update = await db.execute(select(FeedTranscriptJob).where(FeedTranscriptJob.id == job_id))
            db_job = job_update.scalar_one_or_none()
            if db_job:
                db_job.status = "completed"
                db_job.progress = 100
                db_job.error_code = None
                db_job.error_message = None
                db_job.transcript_source = transcript_source
                db_job.transcript_text = transcript_text[:20000]
                db_job.completed_at = datetime.now(timezone.utc)
            await db.commit()
    except Exception as exc:
        logger.exception("Feed transcript job %s failed: %s", job_id, exc)
        await _update_job(
            job_id,
            status="failed",
            progress=100,
            error_code="transcript_failed",
            error_message=str(exc),
            completed=True,
        )


def process_feed_transcript_job(job_id: str) -> None:
    """RQ worker entrypoint for feed transcript jobs."""
    asyncio.run(process_feed_transcript_job_async(job_id))
