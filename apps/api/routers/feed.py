"""Feed discovery/search router."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from database import get_db
from models.user import User
from routers.auth_scope import AuthContext, ensure_user_scope, get_auth_context
from routers.rate_limit import rate_limit
from services.feed_discovery import (
    assign_feed_items_to_collection_service,
    create_feed_repost_package_service,
    decode_feed_export_token,
    delete_feed_follow_service,
    discover_feed_items_service,
    export_feed_items_service,
    get_feed_bulk_download_status_service,
    get_feed_loop_summary_service,
    get_feed_telemetry_summary_service,
    get_feed_repost_package_service,
    list_feed_follows_service,
    list_feed_ingest_runs_service,
    list_feed_repost_packages_service,
    list_feed_telemetry_events_service,
    get_feed_transcript_jobs_status_service,
    resolve_feed_export_file,
    run_feed_follow_ingest_service,
    search_feed_items_service,
    start_feed_bulk_download_service,
    run_feed_loop_audit_service,
    run_feed_loop_variant_generate_service,
    start_feed_transcript_jobs_service,
    upsert_feed_follow_service,
    update_feed_repost_package_status_service,
    update_feed_favorite_service,
)

router = APIRouter()


class FeedItemResponse(BaseModel):
    item_id: str
    platform: str
    source_type: str
    url: Optional[str] = None
    external_id: Optional[str] = None
    creator_handle: Optional[str] = None
    creator_display_name: Optional[str] = None
    title: Optional[str] = None
    caption: Optional[str] = None
    metrics: Dict[str, int]
    published_at: Optional[str] = None
    created_at: Optional[str] = None
    engagement_rate: float
    views_per_hour: float
    trending_score: float


class FeedDiscoverRequest(BaseModel):
    platform: Literal["youtube", "instagram", "tiktok"]
    mode: Literal["profile", "hashtag", "keyword", "audio"] = "keyword"
    query: str = Field(min_length=1)
    timeframe: Literal["24h", "7d", "30d", "90d", "all"] = "7d"
    sort_by: Literal[
        "trending_score",
        "engagement_rate",
        "views_per_hour",
        "views",
        "likes",
        "comments",
        "shares",
        "saves",
        "posted_at",
        "created_at",
    ] = "trending_score"
    sort_direction: Literal["asc", "desc"] = "desc"
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=20, ge=1, le=100)
    user_id: Optional[str] = None


class FeedSearchRequest(BaseModel):
    platform: Optional[Literal["youtube", "instagram", "tiktok"]] = None
    mode: Optional[Literal["profile", "hashtag", "keyword", "audio"]] = None
    query: str = ""
    timeframe: Literal["24h", "7d", "30d", "90d", "all"] = "all"
    sort_by: Literal[
        "trending_score",
        "engagement_rate",
        "views_per_hour",
        "views",
        "likes",
        "comments",
        "shares",
        "saves",
        "posted_at",
        "created_at",
    ] = "trending_score"
    sort_direction: Literal["asc", "desc"] = "desc"
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=20, ge=1, le=100)
    user_id: Optional[str] = None


class FeedDiscoverResponse(BaseModel):
    run_id: str
    platform: str
    mode: str
    query: str
    timeframe: str
    ingestion_method: str
    source_health: Dict[str, Any]
    page: int
    limit: int
    total_count: int
    has_more: bool
    items: List[FeedItemResponse]


class FeedSearchResponse(BaseModel):
    platform: str
    mode: Optional[str] = None
    query: str
    timeframe: str
    page: int
    limit: int
    total_count: int
    has_more: bool
    items: List[FeedItemResponse]


class ToggleFeedFavoriteRequest(BaseModel):
    item_id: str
    favorite: bool = True
    user_id: Optional[str] = None


class ToggleFeedFavoriteResponse(BaseModel):
    item_id: str
    favorite: bool


class AssignFeedItemsToCollectionRequest(BaseModel):
    item_ids: List[str] = Field(min_length=1)
    collection_id: str
    user_id: Optional[str] = None


class AssignFeedItemsToCollectionResponse(BaseModel):
    collection_id: str
    assigned_count: int
    missing_count: int
    missing_item_ids: List[str]


class ExportFeedRequest(BaseModel):
    item_ids: Optional[List[str]] = None
    platform: Optional[Literal["youtube", "instagram", "tiktok"]] = None
    mode: Optional[Literal["profile", "hashtag", "keyword", "audio"]] = None
    query: Optional[str] = ""
    timeframe: Literal["24h", "7d", "30d", "90d", "all"] = "all"
    sort_by: Literal[
        "trending_score",
        "engagement_rate",
        "views_per_hour",
        "views",
        "likes",
        "comments",
        "shares",
        "saves",
        "posted_at",
        "created_at",
    ] = "trending_score"
    sort_direction: Literal["asc", "desc"] = "desc"
    limit: int = Field(default=100, ge=1, le=100)
    max_rows: int = Field(default=500, ge=1, le=5000)
    format: Literal["csv", "json"] = "csv"
    user_id: Optional[str] = None


class ExportFeedResponse(BaseModel):
    export_id: str
    status: str
    format: Literal["csv", "json"]
    item_count: int
    signed_url: str


class BulkFeedDownloadRequest(BaseModel):
    item_ids: List[str] = Field(min_length=1)
    user_id: Optional[str] = None


class BulkFeedDownloadJobItem(BaseModel):
    item_id: str
    job_id: Optional[str] = None
    status: str
    queue_job_id: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


class BulkFeedDownloadResponse(BaseModel):
    submitted_count: int
    queued_count: int
    failed_count: int
    skipped_count: int
    jobs: List[BulkFeedDownloadJobItem]


class BulkFeedDownloadStatusRequest(BaseModel):
    job_ids: List[str] = Field(min_length=1)
    user_id: Optional[str] = None


class BulkFeedDownloadStatusItem(BaseModel):
    job_id: str
    status: str
    progress: int
    queue_job_id: Optional[str] = None
    media_asset_id: Optional[str] = None
    upload_id: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


class BulkFeedDownloadStatusResponse(BaseModel):
    requested_count: int
    jobs: List[BulkFeedDownloadStatusItem]


class BulkFeedTranscriptRequest(BaseModel):
    item_ids: List[str] = Field(min_length=1)
    user_id: Optional[str] = None


class BulkFeedTranscriptResponse(BaseModel):
    submitted_count: int
    queued_count: int
    failed_count: int
    skipped_count: int
    jobs: List[BulkFeedDownloadJobItem]


class BulkFeedTranscriptStatusItem(BaseModel):
    job_id: str
    status: str
    progress: int
    queue_job_id: Optional[str] = None
    item_id: Optional[str] = None
    transcript_source: Optional[str] = None
    transcript_preview: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


class BulkFeedTranscriptStatusResponse(BaseModel):
    requested_count: int
    jobs: List[BulkFeedTranscriptStatusItem]


class UpsertFeedFollowRequest(BaseModel):
    platform: Literal["youtube", "instagram", "tiktok"]
    mode: Literal["profile", "hashtag", "keyword", "audio"] = "keyword"
    query: str = Field(min_length=1)
    timeframe: Literal["24h", "7d", "30d", "90d", "all"] = "7d"
    sort_by: Literal[
        "trending_score",
        "engagement_rate",
        "views_per_hour",
        "views",
        "likes",
        "comments",
        "shares",
        "saves",
        "posted_at",
        "created_at",
    ] = "trending_score"
    sort_direction: Literal["asc", "desc"] = "desc"
    limit: int = Field(default=20, ge=1, le=100)
    cadence: Optional[Literal["15m", "1h", "3h", "6h", "12h", "24h"]] = "6h"
    cadence_minutes: Optional[int] = Field(default=None, ge=15, le=1440)
    is_active: bool = True
    user_id: Optional[str] = None


class FeedFollowItem(BaseModel):
    id: str
    platform: str
    mode: str
    query: str
    timeframe: str
    sort_by: str
    sort_direction: str
    limit: int
    cadence_minutes: int
    is_active: bool
    last_run_at: Optional[str] = None
    next_run_at: Optional[str] = None
    last_error: Optional[str] = None
    created_at: Optional[str] = None


class UpsertFeedFollowResponse(BaseModel):
    created: bool
    follow: FeedFollowItem


class ListFeedFollowsResponse(BaseModel):
    count: int
    follows: List[FeedFollowItem]


class FeedIngestRunItem(BaseModel):
    run_id: str
    follow_id: str
    status: str
    item_count: int
    item_ids: List[str]
    error_message: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    created_at: Optional[str] = None


class RunFeedIngestRequest(BaseModel):
    follow_ids: Optional[List[str]] = None
    run_due_only: bool = False
    max_follows: int = Field(default=25, ge=1, le=100)
    user_id: Optional[str] = None


class RunFeedIngestResponse(BaseModel):
    scheduled_count: int
    completed_count: int
    failed_count: int
    runs: List[FeedIngestRunItem]


class ListFeedIngestRunsResponse(BaseModel):
    count: int
    runs: List[FeedIngestRunItem]


class CreateFeedRepostPackageRequest(BaseModel):
    source_item_id: str
    target_platforms: Optional[List[Literal["youtube", "instagram", "tiktok"]]] = None
    objective: Optional[str] = "maximize_reach"
    tone: Optional[str] = "direct"
    user_id: Optional[str] = None


class FeedRepostPackageItem(BaseModel):
    package_id: str
    source_item_id: str
    status: str
    target_platforms: List[str]
    package: Dict[str, Any]
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ListFeedRepostPackagesResponse(BaseModel):
    count: int
    packages: List[FeedRepostPackageItem]


class UpdateFeedRepostStatusRequest(BaseModel):
    status: Literal["draft", "scheduled", "published", "archived"]
    user_id: Optional[str] = None


class FeedLoopVariantRequest(BaseModel):
    source_item_id: str
    platform: Optional[Literal["youtube", "instagram", "tiktok"]] = None
    topic: Optional[str] = None
    audience: Optional[str] = None
    objective: Optional[str] = None
    tone: Optional[str] = "bold"
    duration_s: Optional[int] = Field(default=None, ge=15, le=900)
    generation_mode: str = "ai_first_fallback"
    constraints: Optional[Dict[str, Any]] = None
    user_id: Optional[str] = None


class FeedLoopVariantResponse(BaseModel):
    source_item_id: str
    platform: str
    topic: str
    audience: str
    objective: str
    optimizer: Dict[str, Any]
    credits: Dict[str, Any]


class FeedLoopAuditRequest(BaseModel):
    source_item_id: str
    platform: Optional[Literal["youtube", "instagram", "tiktok"]] = None
    retention_points: Optional[List[Dict[str, Any]]] = None
    platform_metrics: Optional[Dict[str, Any]] = None
    draft_snapshot_id: Optional[str] = None
    repost_package_id: Optional[str] = None
    user_id: Optional[str] = None


class FeedLoopAuditResponse(BaseModel):
    audit_id: str
    status: str
    source_item_id: str
    upload_id: str
    report_path: str
    credits: Dict[str, Any]


class FeedLoopSummaryResponse(BaseModel):
    source_item_id: str
    source_item: Dict[str, Any]
    latest_repost_package: Optional[Dict[str, Any]] = None
    latest_draft_snapshot: Optional[Dict[str, Any]] = None
    latest_audit: Optional[Dict[str, Any]] = None
    stage_completion: Dict[str, bool]
    next_step: str


class FeedTelemetrySummaryResponse(BaseModel):
    window_days: int
    event_volume: Dict[str, Any]
    funnel: Dict[str, Any]


class FeedTelemetryEventsResponse(BaseModel):
    window_days: int
    count: int
    events: List[Dict[str, Any]]


async def _ensure_user(db: AsyncSession, user_id: str) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user:
        return user
    user = User(id=user_id, email=f"{user_id}@local.invalid")
    db.add(user)
    await db.flush()
    return user


@router.post("/discover", response_model=FeedDiscoverResponse)
async def discover_feed_items(
    request: FeedDiscoverRequest,
    _rate_limit: None = Depends(rate_limit("feed_discover", limit=180, window_seconds=3600)),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    scoped_user_id = ensure_user_scope(auth.user_id, request.user_id)
    await _ensure_user(db, scoped_user_id)
    return await discover_feed_items_service(
        user_id=scoped_user_id,
        payload=request.model_dump(exclude_none=True),
        db=db,
    )


@router.post("/search", response_model=FeedSearchResponse)
async def search_feed_items(
    request: FeedSearchRequest,
    _rate_limit: None = Depends(rate_limit("feed_search", limit=260, window_seconds=3600)),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    scoped_user_id = ensure_user_scope(auth.user_id, request.user_id)
    await _ensure_user(db, scoped_user_id)
    return await search_feed_items_service(
        user_id=scoped_user_id,
        payload=request.model_dump(exclude_none=True),
        db=db,
    )


@router.post("/favorites/toggle", response_model=ToggleFeedFavoriteResponse)
async def toggle_feed_favorite(
    request: ToggleFeedFavoriteRequest,
    _rate_limit: None = Depends(rate_limit("feed_favorite_toggle", limit=300, window_seconds=3600)),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    scoped_user_id = ensure_user_scope(auth.user_id, request.user_id)
    await _ensure_user(db, scoped_user_id)
    return await update_feed_favorite_service(
        user_id=scoped_user_id,
        item_id=request.item_id,
        favorite=request.favorite,
        db=db,
    )


@router.post("/collections/assign", response_model=AssignFeedItemsToCollectionResponse)
async def assign_feed_items_to_collection(
    request: AssignFeedItemsToCollectionRequest,
    _rate_limit: None = Depends(rate_limit("feed_collection_assign", limit=200, window_seconds=3600)),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    scoped_user_id = ensure_user_scope(auth.user_id, request.user_id)
    await _ensure_user(db, scoped_user_id)
    return await assign_feed_items_to_collection_service(
        user_id=scoped_user_id,
        item_ids=request.item_ids,
        collection_id=request.collection_id,
        db=db,
    )


@router.post("/export", response_model=ExportFeedResponse)
async def export_feed(
    request: ExportFeedRequest,
    _rate_limit: None = Depends(rate_limit("feed_export", limit=80, window_seconds=3600)),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    scoped_user_id = ensure_user_scope(auth.user_id, request.user_id)
    await _ensure_user(db, scoped_user_id)
    return await export_feed_items_service(
        user_id=scoped_user_id,
        payload=request.model_dump(exclude_none=True),
        db=db,
    )


@router.get("/export/{export_id}/download")
async def download_feed_export(export_id: str, token: str):
    claims = decode_feed_export_token(token)
    token_user = str(claims.get("sub", ""))
    token_export = str(claims.get("export_id", ""))
    if token_export != export_id:
        raise HTTPException(status_code=401, detail="Feed export token does not match export id.")

    file_path = resolve_feed_export_file(token_user, export_id)
    ext = file_path.suffix.lower().lstrip(".")
    media_type = "text/csv" if ext == "csv" else "application/json"
    filename = f"feed_export_{export_id}.{ext}"
    return FileResponse(file_path, media_type=media_type, filename=filename)


@router.post("/download/bulk", response_model=BulkFeedDownloadResponse)
async def start_feed_bulk_download(
    request: BulkFeedDownloadRequest,
    _rate_limit: None = Depends(rate_limit("feed_download_bulk", limit=60, window_seconds=3600)),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    scoped_user_id = ensure_user_scope(auth.user_id, request.user_id)
    await _ensure_user(db, scoped_user_id)
    return await start_feed_bulk_download_service(
        user_id=scoped_user_id,
        item_ids=request.item_ids,
        db=db,
    )


@router.post("/download/status", response_model=BulkFeedDownloadStatusResponse)
async def get_feed_bulk_download_status(
    request: BulkFeedDownloadStatusRequest,
    _rate_limit: None = Depends(rate_limit("feed_download_status", limit=220, window_seconds=3600)),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    scoped_user_id = ensure_user_scope(auth.user_id, request.user_id)
    await _ensure_user(db, scoped_user_id)
    return await get_feed_bulk_download_status_service(
        user_id=scoped_user_id,
        job_ids=request.job_ids,
        db=db,
    )


@router.post("/transcripts/bulk", response_model=BulkFeedTranscriptResponse)
async def start_feed_transcript_bulk(
    request: BulkFeedTranscriptRequest,
    _rate_limit: None = Depends(rate_limit("feed_transcript_bulk", limit=80, window_seconds=3600)),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    scoped_user_id = ensure_user_scope(auth.user_id, request.user_id)
    await _ensure_user(db, scoped_user_id)
    return await start_feed_transcript_jobs_service(
        user_id=scoped_user_id,
        item_ids=request.item_ids,
        db=db,
    )


@router.post("/transcripts/status", response_model=BulkFeedTranscriptStatusResponse)
async def get_feed_transcript_status(
    request: BulkFeedDownloadStatusRequest,
    _rate_limit: None = Depends(rate_limit("feed_transcript_status", limit=220, window_seconds=3600)),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    scoped_user_id = ensure_user_scope(auth.user_id, request.user_id)
    await _ensure_user(db, scoped_user_id)
    return await get_feed_transcript_jobs_status_service(
        user_id=scoped_user_id,
        job_ids=request.job_ids,
        db=db,
    )


@router.post("/follows/upsert", response_model=UpsertFeedFollowResponse)
async def upsert_feed_follow(
    request: UpsertFeedFollowRequest,
    _rate_limit: None = Depends(rate_limit("feed_follow_upsert", limit=200, window_seconds=3600)),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    scoped_user_id = ensure_user_scope(auth.user_id, request.user_id)
    await _ensure_user(db, scoped_user_id)
    return await upsert_feed_follow_service(
        user_id=scoped_user_id,
        payload=request.model_dump(exclude_none=True),
        db=db,
    )


@router.get("/follows", response_model=ListFeedFollowsResponse)
async def list_feed_follows(
    platform: Optional[Literal["youtube", "instagram", "tiktok"]] = None,
    active_only: bool = True,
    user_id: Optional[str] = None,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    scoped_user_id = ensure_user_scope(auth.user_id, user_id)
    await _ensure_user(db, scoped_user_id)
    return await list_feed_follows_service(
        user_id=scoped_user_id,
        platform=platform,
        active_only=bool(active_only),
        db=db,
    )


@router.delete("/follows/{follow_id}")
async def delete_feed_follow(
    follow_id: str,
    user_id: Optional[str] = None,
    _rate_limit: None = Depends(rate_limit("feed_follow_delete", limit=120, window_seconds=3600)),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    scoped_user_id = ensure_user_scope(auth.user_id, user_id)
    await _ensure_user(db, scoped_user_id)
    return await delete_feed_follow_service(
        user_id=scoped_user_id,
        follow_id=follow_id,
        db=db,
    )


@router.post("/follows/ingest", response_model=RunFeedIngestResponse)
async def run_feed_follow_ingest(
    request: RunFeedIngestRequest,
    _rate_limit: None = Depends(rate_limit("feed_follow_ingest", limit=120, window_seconds=3600)),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    scoped_user_id = ensure_user_scope(auth.user_id, request.user_id)
    await _ensure_user(db, scoped_user_id)
    return await run_feed_follow_ingest_service(
        user_id=scoped_user_id,
        follow_ids=request.follow_ids,
        run_due_only=request.run_due_only,
        max_follows=request.max_follows,
        db=db,
    )


@router.get("/follows/runs", response_model=ListFeedIngestRunsResponse)
async def list_feed_ingest_runs(
    follow_id: Optional[str] = None,
    limit: int = 50,
    user_id: Optional[str] = None,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    scoped_user_id = ensure_user_scope(auth.user_id, user_id)
    await _ensure_user(db, scoped_user_id)
    return await list_feed_ingest_runs_service(
        user_id=scoped_user_id,
        follow_id=follow_id,
        limit=limit,
        db=db,
    )


@router.post("/repost/package", response_model=FeedRepostPackageItem)
async def create_feed_repost_package(
    request: CreateFeedRepostPackageRequest,
    _rate_limit: None = Depends(rate_limit("feed_repost_package_create", limit=120, window_seconds=3600)),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    scoped_user_id = ensure_user_scope(auth.user_id, request.user_id)
    await _ensure_user(db, scoped_user_id)
    return await create_feed_repost_package_service(
        user_id=scoped_user_id,
        payload=request.model_dump(exclude_none=True),
        db=db,
    )


@router.get("/repost/packages", response_model=ListFeedRepostPackagesResponse)
async def list_feed_repost_packages(
    source_item_id: Optional[str] = None,
    limit: int = 20,
    user_id: Optional[str] = None,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    scoped_user_id = ensure_user_scope(auth.user_id, user_id)
    await _ensure_user(db, scoped_user_id)
    return await list_feed_repost_packages_service(
        user_id=scoped_user_id,
        source_item_id=source_item_id,
        limit=limit,
        db=db,
    )


@router.get("/repost/packages/{package_id}", response_model=FeedRepostPackageItem)
async def get_feed_repost_package(
    package_id: str,
    user_id: Optional[str] = None,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    scoped_user_id = ensure_user_scope(auth.user_id, user_id)
    await _ensure_user(db, scoped_user_id)
    return await get_feed_repost_package_service(
        user_id=scoped_user_id,
        package_id=package_id,
        db=db,
    )


@router.post("/repost/packages/{package_id}/status", response_model=FeedRepostPackageItem)
async def update_feed_repost_package_status(
    package_id: str,
    request: UpdateFeedRepostStatusRequest,
    _rate_limit: None = Depends(rate_limit("feed_repost_package_status", limit=180, window_seconds=3600)),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    scoped_user_id = ensure_user_scope(auth.user_id, request.user_id)
    await _ensure_user(db, scoped_user_id)
    return await update_feed_repost_package_status_service(
        user_id=scoped_user_id,
        package_id=package_id,
        status=request.status,
        db=db,
    )


@router.post("/loop/variant_generate", response_model=FeedLoopVariantResponse)
async def run_feed_loop_variant_generate(
    request: FeedLoopVariantRequest,
    _rate_limit: None = Depends(rate_limit("feed_loop_variant_generate", limit=100, window_seconds=3600)),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    scoped_user_id = ensure_user_scope(auth.user_id, request.user_id)
    await _ensure_user(db, scoped_user_id)
    return await run_feed_loop_variant_generate_service(
        user_id=scoped_user_id,
        payload=request.model_dump(exclude_none=True),
        db=db,
    )


@router.post("/loop/audit", response_model=FeedLoopAuditResponse)
async def run_feed_loop_audit(
    request: FeedLoopAuditRequest,
    _rate_limit: None = Depends(rate_limit("feed_loop_audit", limit=80, window_seconds=3600)),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    scoped_user_id = ensure_user_scope(auth.user_id, request.user_id)
    await _ensure_user(db, scoped_user_id)
    return await run_feed_loop_audit_service(
        user_id=scoped_user_id,
        payload=request.model_dump(exclude_none=True),
        db=db,
    )


@router.get("/loop/summary", response_model=FeedLoopSummaryResponse)
async def get_feed_loop_summary(
    source_item_id: str,
    user_id: Optional[str] = None,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    scoped_user_id = ensure_user_scope(auth.user_id, user_id)
    await _ensure_user(db, scoped_user_id)
    return await get_feed_loop_summary_service(
        user_id=scoped_user_id,
        source_item_id=source_item_id,
        db=db,
    )


@router.get("/telemetry/summary", response_model=FeedTelemetrySummaryResponse)
async def get_feed_telemetry_summary(
    days: int = 7,
    user_id: Optional[str] = None,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    scoped_user_id = ensure_user_scope(auth.user_id, user_id)
    await _ensure_user(db, scoped_user_id)
    return await get_feed_telemetry_summary_service(
        user_id=scoped_user_id,
        days=days,
        db=db,
    )


@router.get("/telemetry/events", response_model=FeedTelemetryEventsResponse)
async def list_feed_telemetry_events(
    days: int = 7,
    limit: int = 50,
    event_name: Optional[str] = None,
    status: Optional[str] = None,
    user_id: Optional[str] = None,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    scoped_user_id = ensure_user_scope(auth.user_id, user_id)
    await _ensure_user(db, scoped_user_id)
    return await list_feed_telemetry_events_service(
        user_id=scoped_user_id,
        days=days,
        limit=limit,
        event_name=event_name,
        status=status,
        db=db,
    )
