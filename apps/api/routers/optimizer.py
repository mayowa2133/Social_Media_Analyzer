"""Optimizer v2 router: variant generation and draft re-score."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from config import settings
from database import get_db
from models.user import User
from routers.auth_scope import AuthContext, ensure_user_scope, get_auth_context
from routers.rate_limit import rate_limit
from services.credits import consume_credits
from services.optimizer import (
    create_draft_snapshot_service,
    generate_variants_service,
    get_draft_snapshot_service,
    list_draft_snapshots_service,
    rescore_script_service,
)

router = APIRouter()
logger = logging.getLogger(__name__)


class VariantGenerateRequest(BaseModel):
    platform: str = "youtube"
    topic: str
    audience: str
    objective: str
    tone: str = "bold"
    duration_s: Optional[int] = Field(default=None, ge=15, le=900)
    template_series_key: Optional[str] = None
    source_item_id: Optional[str] = None
    generation_mode: str = "ai_first_fallback"
    constraints: Optional[Dict[str, Any]] = None
    user_id: Optional[str] = None


class RetentionPoint(BaseModel):
    time: float
    retention: float


class RescoreRequest(BaseModel):
    platform: str = "youtube"
    script_text: str
    duration_s: Optional[int] = Field(default=None, ge=15, le=900)
    optional_metrics: Optional[Dict[str, Any]] = None
    retention_points: Optional[List[RetentionPoint]] = None
    baseline_score: Optional[float] = None
    baseline_detector_rankings: Optional[List[Dict[str, Any]]] = None
    user_id: Optional[str] = None


class DraftSnapshotCreateRequest(BaseModel):
    platform: str = "youtube"
    source_item_id: Optional[str] = None
    variant_id: Optional[str] = None
    script_text: str
    baseline_score: Optional[float] = None
    rescored_score: Optional[float] = None
    delta_score: Optional[float] = None
    detector_rankings: Optional[List[Dict[str, Any]]] = None
    next_actions: Optional[List[Dict[str, Any]]] = None
    line_level_edits: Optional[List[Dict[str, Any]]] = None
    score_breakdown: Optional[Dict[str, Any]] = None
    rescore_output: Optional[Dict[str, Any]] = None
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


@router.post("/variant_generate")
async def generate_variants(
    request: VariantGenerateRequest,
    _rate_limit: None = Depends(rate_limit("optimizer_variants", limit=80, window_seconds=3600)),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    scoped_user_id = ensure_user_scope(auth.user_id, request.user_id)
    await _ensure_user(db, scoped_user_id)

    charge = await consume_credits(
        scoped_user_id,
        db,
        cost=max(int(settings.CREDIT_COST_OPTIMIZER_VARIANTS), 0),
        reason="Optimizer script generation batch",
        reference_type="optimizer_variant_generate",
    )

    payload = await generate_variants_service(
        user_id=scoped_user_id,
        payload=request.model_dump(exclude_none=True),
        db=db,
    )
    payload["credits"] = charge
    return payload


@router.post("/rescore")
async def rescore_script(
    request: RescoreRequest,
    _rate_limit: None = Depends(rate_limit("optimizer_rescore", limit=180, window_seconds=3600)),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    scoped_user_id = ensure_user_scope(auth.user_id, request.user_id)
    await _ensure_user(db, scoped_user_id)

    payload = request.model_dump(exclude_none=True)
    if request.retention_points:
        payload["retention_points"] = [point.model_dump() for point in request.retention_points]

    return await rescore_script_service(
        user_id=scoped_user_id,
        payload=payload,
        db=db,
    )


@router.post("/draft_snapshot")
async def create_draft_snapshot(
    request: DraftSnapshotCreateRequest,
    _rate_limit: None = Depends(rate_limit("optimizer_snapshot_create", limit=240, window_seconds=3600)),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    scoped_user_id = ensure_user_scope(auth.user_id, request.user_id)
    await _ensure_user(db, scoped_user_id)
    return await create_draft_snapshot_service(
        user_id=scoped_user_id,
        payload=request.model_dump(exclude_none=True),
        db=db,
    )


@router.get("/draft_snapshot")
async def list_draft_snapshots(
    user_id: Optional[str] = Query(default=None),
    platform: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    scoped_user_id = ensure_user_scope(auth.user_id, user_id)
    await _ensure_user(db, scoped_user_id)
    return await list_draft_snapshots_service(
        user_id=scoped_user_id,
        platform=platform,
        limit=limit,
        db=db,
    )


@router.get("/draft_snapshot/{snapshot_id}")
async def get_draft_snapshot(
    snapshot_id: str,
    user_id: Optional[str] = Query(default=None),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    scoped_user_id = ensure_user_scope(auth.user_id, user_id)
    await _ensure_user(db, scoped_user_id)
    return await get_draft_snapshot_service(
        user_id=scoped_user_id,
        snapshot_id=snapshot_id,
        db=db,
    )
