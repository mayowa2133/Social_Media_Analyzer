"""Durable audit job queue helpers (Redis/RQ)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from redis import Redis
from rq import Queue, Retry
from rq.job import Job
from sqlalchemy import select

from config import settings
from database import async_session_maker
from models.audit import Audit
from models.media_download_job import MediaDownloadJob


AUDIT_QUEUE_NAME = "audit_jobs"
MEDIA_QUEUE_NAME = "media_jobs"
IN_PROGRESS_STATUSES = ("downloading", "processing_video", "processing_audio", "analyzing")
MEDIA_IN_PROGRESS_STATUSES = ("queued", "downloading", "processing")


def get_redis_connection() -> Redis:
    """Build Redis connection used by RQ."""
    return Redis.from_url(settings.REDIS_URL)


def get_audit_queue() -> Queue:
    """Return the configured audit queue."""
    return Queue(
        name=AUDIT_QUEUE_NAME,
        connection=get_redis_connection(),
        default_timeout=1800,
    )


def get_media_queue() -> Queue:
    """Return the configured media download queue."""
    return Queue(
        name=MEDIA_QUEUE_NAME,
        connection=get_redis_connection(),
        default_timeout=1800,
    )


def enqueue_audit_job(
    audit_id: str,
    video_url: Optional[str],
    upload_path: Optional[str],
    source_mode: str,
) -> Job:
    """Enqueue an audit job with retry/timeouts for durability."""
    queue = get_audit_queue()
    return queue.enqueue(
        "services.audit.process_video_audit_job",
        audit_id,
        video_url,
        upload_path,
        source_mode,
        job_id=f"audit:{audit_id}",
        retry=Retry(max=3, interval=[15, 60, 180]),
        job_timeout=1800,
        result_ttl=86400,
        failure_ttl=86400,
    )


def enqueue_media_download_job(job_id: str) -> Job:
    """Enqueue a media download job with retry/timeouts for durability."""
    queue = get_media_queue()
    return queue.enqueue(
        "services.media_download.process_media_download_job",
        job_id,
        job_id=f"media:{job_id}",
        retry=Retry(max=3, interval=[10, 30, 120]),
        job_timeout=1800,
        result_ttl=86400,
        failure_ttl=86400,
    )


async def recover_stalled_audits(max_age_minutes: int = 120) -> int:
    """Mark stale in-progress audits as failed after restarts/worker interruptions."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=max(max_age_minutes, 1))
    async with async_session_maker() as db:
        result = await db.execute(
            select(Audit).where(
                Audit.status.in_(IN_PROGRESS_STATUSES),
                Audit.created_at < cutoff,
            )
        )
        audits = result.scalars().all()
        for audit in audits:
            audit.status = "failed"
            audit.error_message = "Audit execution was interrupted. Re-run the audit from workspace."
        if audits:
            await db.commit()
        return len(audits)


async def recover_stalled_media_download_jobs(max_age_minutes: int = 120) -> int:
    """Mark stale in-progress media jobs as failed after restarts/worker interruptions."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=max(max_age_minutes, 1))
    async with async_session_maker() as db:
        result = await db.execute(
            select(MediaDownloadJob).where(
                MediaDownloadJob.status.in_(MEDIA_IN_PROGRESS_STATUSES),
                MediaDownloadJob.created_at < cutoff,
            )
        )
        jobs = result.scalars().all()
        for job in jobs:
            job.status = "failed"
            job.error_code = "stalled"
            job.error_message = "Media download was interrupted. Re-run download from workspace."
            job.completed_at = datetime.now(timezone.utc)
            job.progress = max(int(job.progress or 0), 5)
        if jobs:
            await db.commit()
        return len(jobs)
