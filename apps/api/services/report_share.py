"""Share-link helpers for consolidated reports."""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from models.audit import Audit
from models.report_share_link import ReportShareLink


async def create_report_share_link(
    *,
    user_id: str,
    audit_id: str,
    db: AsyncSession,
    expires_hours: int = 168,
) -> Dict[str, Any]:
    audit_result = await db.execute(
        select(Audit).where(
            Audit.id == audit_id,
            Audit.user_id == user_id,
        )
    )
    audit = audit_result.scalar_one_or_none()
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")

    now = datetime.now(timezone.utc)
    max_hours = 24 * 30
    ttl_hours = max(1, min(int(expires_hours), max_hours))
    expires_at = now + timedelta(hours=ttl_hours)

    token = secrets.token_urlsafe(24)
    row = ReportShareLink(
        id=str(uuid.uuid4()),
        user_id=user_id,
        audit_id=audit_id,
        share_token=token,
        expires_at=expires_at,
    )
    db.add(row)
    await db.commit()

    return {
        "share_id": row.id,
        "audit_id": audit_id,
        "share_token": token,
        "expires_at": expires_at.isoformat(),
    }


async def resolve_shared_report(*, share_token: str, db: AsyncSession) -> Dict[str, Any]:
    token = str(share_token or "").strip()
    if not token:
        raise HTTPException(status_code=422, detail="share_token is required")

    result = await db.execute(
        select(ReportShareLink).where(ReportShareLink.share_token == token)
    )
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="Share link not found")

    now = datetime.now(timezone.utc)
    expires_at = link.expires_at
    if expires_at is None:
        raise HTTPException(status_code=410, detail="Share link expired")
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= now:
        raise HTTPException(status_code=410, detail="Share link expired")

    link.last_accessed_at = now
    await db.commit()

    from services.report import get_consolidated_report

    payload = await get_consolidated_report(link.user_id, link.audit_id, db)
    payload["shared_report"] = {
        "share_token": token,
        "expires_at": expires_at.isoformat(),
    }
    return payload
