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


AUDIT_QUEUE_NAME = "audit_jobs"
IN_PROGRESS_STATUSES = ("downloading", "processing_video", "processing_audio", "analyzing")


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
