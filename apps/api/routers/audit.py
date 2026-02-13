"""
Audit router for running full audits and retrieving reports.
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from pydantic import BaseModel
from typing import List, Optional, Literal
import uuid

from database import get_db
from models.audit import Audit
from models.user import User
from services.audit import process_video_audit

router = APIRouter()


class RetentionPoint(BaseModel):
    time: float
    retention: float


class CreateAuditRequest(BaseModel):
    source_mode: Literal["url", "upload"] = "url"
    video_url: Optional[str] = None
    retention_points: Optional[List[RetentionPoint]] = None
    user_id: str = "test-user"  # Optional for MVP

class AuditStatusResponse(BaseModel):
    audit_id: str
    status: str
    progress: str
    created_at: Optional[str] = None
    output: Optional[dict] = None
    error: Optional[str] = None

@router.post("/run_multimodal")
async def run_multimodal_audit(
    request: CreateAuditRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Start a new multimodal audit for a video."""
    if request.source_mode == "upload":
        raise HTTPException(
            status_code=501,
            detail="source_mode='upload' is not implemented yet. Use source_mode='url'.",
        )

    if not request.video_url:
        raise HTTPException(status_code=422, detail="video_url is required for source_mode='url'")

    # Ensure referenced user exists for FK integrity.
    user_result = await db.execute(select(User).where(User.id == request.user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        user = User(id=request.user_id, email=f"{request.user_id}@local.invalid")
        db.add(user)
        await db.flush()

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
            "retention_points": [p.model_dump() for p in (request.retention_points or [])],
        }
    )
    db.add(db_audit)
    await db.commit()
    await db.refresh(db_audit)
    
    # Trigger background task
    background_tasks.add_task(process_video_audit, audit_id, request.video_url)
    
    return {"audit_id": audit_id, "status": "pending"}


@router.get("/")
async def list_audits(
    user_id: str = Query(default="test-user"),
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
async def get_audit_status(audit_id: str, db: AsyncSession = Depends(get_db)):
    """Get status of an audit."""
    result = await db.execute(select(Audit).where(Audit.id == audit_id))
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
