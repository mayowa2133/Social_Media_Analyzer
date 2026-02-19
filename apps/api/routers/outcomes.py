"""Outcome learning router for prediction-vs-actual calibration."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from database import get_db
from models.user import User
from routers.auth_scope import AuthContext, ensure_user_scope, get_auth_context
from routers.rate_limit import rate_limit
from services.outcomes import (
    get_outcomes_summary_service,
    ingest_outcome_service,
    run_calibration_refresh_for_all_users_service,
)

router = APIRouter()
logger = logging.getLogger(__name__)


class RetentionPoint(BaseModel):
    time: float
    retention: float


class OutcomesIngestRequest(BaseModel):
    platform: str = "youtube"
    content_item_id: Optional[str] = None
    draft_snapshot_id: Optional[str] = None
    report_id: Optional[str] = None
    video_external_id: Optional[str] = None
    actual_metrics: Dict[str, Any]
    retention_points: Optional[List[RetentionPoint]] = None
    posted_at: str
    predicted_score: Optional[float] = Field(default=None, ge=0, le=100)
    user_id: Optional[str] = None


async def _ensure_user(db: AsyncSession, user_id: str) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user:
        return user

    user = User(id=user_id, email=f"{user_id}@local.invalid")
    db.add(user)
    await db.flush()
    return user


@router.post("/ingest")
async def ingest_outcome_metrics(
    request: OutcomesIngestRequest,
    _rate_limit: None = Depends(rate_limit("outcome_ingest", limit=120, window_seconds=3600)),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    scoped_user_id = ensure_user_scope(auth.user_id, request.user_id)
    await _ensure_user(db, scoped_user_id)

    payload = request.model_dump(exclude_none=True)
    if request.retention_points:
        payload["retention_points"] = [point.model_dump() for point in request.retention_points]

    return await ingest_outcome_service(user_id=scoped_user_id, payload=payload, db=db)


@router.get("/summary")
async def outcomes_summary(
    user_id: Optional[str] = Query(default=None),
    platform: Optional[str] = Query(default=None),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    scoped_user_id = ensure_user_scope(auth.user_id, user_id)
    await _ensure_user(db, scoped_user_id)
    return await get_outcomes_summary_service(
        user_id=scoped_user_id,
        db=db,
        platform=platform,
    )


@router.post("/recalibrate")
async def recalibrate_outcomes(
    _rate_limit: None = Depends(rate_limit("outcomes_recalibrate", limit=12, window_seconds=3600)),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    # Requires authenticated session but does not trust user input.
    if not auth.user_id:
        return {"refreshed": 0, "skipped": 0, "errors": ["unauthorized"]}
    return await run_calibration_refresh_for_all_users_service(db=db)
