"""Research ingestion/search/export router."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from config import settings
from database import get_db
from models.user import User
from routers.auth_scope import AuthContext, ensure_user_scope, get_auth_context
from routers.rate_limit import rate_limit
from services.credits import consume_credits
from services.research import (
    capture_research_item_service,
    decode_export_token,
    export_research_collection_service,
    get_research_item_service,
    import_research_csv_service,
    import_research_url_service,
    list_research_collections_service,
    resolve_export_file,
    search_research_items_service,
)

router = APIRouter()
logger = logging.getLogger(__name__)


class ImportResearchUrlRequest(BaseModel):
    platform: Optional[str] = None
    url: str
    user_id: Optional[str] = None


class CaptureResearchItemRequest(BaseModel):
    platform: Optional[str] = None
    url: Optional[str] = None
    external_id: Optional[str] = None
    creator_handle: Optional[str] = None
    creator_display_name: Optional[str] = None
    title: Optional[str] = None
    caption: Optional[str] = None
    views: Optional[int] = 0
    likes: Optional[int] = 0
    comments: Optional[int] = 0
    shares: Optional[int] = 0
    saves: Optional[int] = 0
    published_at: Optional[str] = None
    media_meta: Optional[Dict[str, Any]] = None
    user_id: Optional[str] = None


class SearchResearchRequest(BaseModel):
    platform: Optional[str] = None
    query: Optional[str] = ""
    sort_by: Literal["created_at", "posted_at", "views", "likes", "comments", "shares", "saves"] = "created_at"
    sort_direction: Literal["asc", "desc"] = "desc"
    timeframe: Literal["24h", "7d", "30d", "90d", "all"] = "all"
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=20, ge=1, le=100)
    user_id: Optional[str] = None


class ExportResearchRequest(BaseModel):
    collection_id: str
    format: Literal["csv", "json"] = "csv"
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


@router.post("/import_url")
async def import_research_url(
    request: ImportResearchUrlRequest,
    _rate_limit: None = Depends(rate_limit("research_import_url", limit=100, window_seconds=3600)),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    scoped_user_id = ensure_user_scope(auth.user_id, request.user_id)
    await _ensure_user(db, scoped_user_id)
    return await import_research_url_service(
        user_id=scoped_user_id,
        platform=request.platform,
        url=request.url,
        db=db,
    )


@router.post("/capture")
async def capture_research_item(
    request: CaptureResearchItemRequest,
    _rate_limit: None = Depends(rate_limit("research_capture", limit=180, window_seconds=3600)),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    scoped_user_id = ensure_user_scope(auth.user_id, request.user_id)
    await _ensure_user(db, scoped_user_id)
    return await capture_research_item_service(
        user_id=scoped_user_id,
        payload=request.model_dump(exclude_none=True),
        db=db,
    )


@router.post("/import_csv")
async def import_research_csv(
    file: UploadFile = File(...),
    platform: Optional[str] = Form(default=None),
    user_id: Optional[str] = Form(default=None),
    _rate_limit: None = Depends(rate_limit("research_import_csv", limit=30, window_seconds=3600)),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    scoped_user_id = ensure_user_scope(auth.user_id, user_id)
    await _ensure_user(db, scoped_user_id)
    return await import_research_csv_service(
        user_id=scoped_user_id,
        platform=platform,
        file=file,
        db=db,
    )


@router.post("/search")
async def search_research_items(
    request: SearchResearchRequest,
    _rate_limit: None = Depends(rate_limit("research_search", limit=160, window_seconds=3600)),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    scoped_user_id = ensure_user_scope(auth.user_id, request.user_id)
    await _ensure_user(db, scoped_user_id)

    charge = await consume_credits(
        scoped_user_id,
        db,
        cost=max(int(settings.CREDIT_COST_RESEARCH_SEARCH), 0),
        reason="Research search batch",
        reference_type="research_search",
    )

    result = await search_research_items_service(
        user_id=scoped_user_id,
        payload=request.model_dump(exclude_none=True),
        db=db,
    )
    result["credits"] = charge
    return result


@router.get("/collections")
async def list_research_collections(
    user_id: Optional[str] = Query(default=None),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    scoped_user_id = ensure_user_scope(auth.user_id, user_id)
    await _ensure_user(db, scoped_user_id)
    return {"collections": await list_research_collections_service(scoped_user_id, db)}


@router.get("/items/{item_id}")
async def get_research_item(
    item_id: str,
    user_id: Optional[str] = Query(default=None),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    scoped_user_id = ensure_user_scope(auth.user_id, user_id)
    await _ensure_user(db, scoped_user_id)
    return await get_research_item_service(scoped_user_id, item_id, db)


@router.post("/export")
async def export_research_collection(
    request: ExportResearchRequest,
    _rate_limit: None = Depends(rate_limit("research_export", limit=50, window_seconds=3600)),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    scoped_user_id = ensure_user_scope(auth.user_id, request.user_id)
    await _ensure_user(db, scoped_user_id)
    return await export_research_collection_service(
        user_id=scoped_user_id,
        collection_id=request.collection_id,
        export_format=request.format,
        db=db,
    )


@router.get("/export/{export_id}/download")
async def download_research_export(
    export_id: str,
    token: str,
):
    claims = decode_export_token(token)
    token_user = str(claims.get("sub", ""))
    token_export = str(claims.get("export_id", ""))
    if token_export != export_id:
        raise HTTPException(status_code=401, detail="Export token does not match export id.")

    file_path, ext = resolve_export_file(token_user, export_id)
    media_type = "text/csv" if ext == "csv" else "application/json"
    filename = f"research_export_{export_id}.{ext}"
    return FileResponse(file_path, media_type=media_type, filename=filename)
