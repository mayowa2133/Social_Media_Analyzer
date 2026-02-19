"""
Router for competitor management and analysis.
"""

import uuid
import logging
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from database import get_db
from models.competitor import Competitor
from models.research_item import ResearchItem
from models.user import User
from routers.auth_scope import AuthContext, ensure_user_scope, get_auth_context
from routers.rate_limit import rate_limit
from routers.youtube import _get_youtube_client, get_channel_videos
from services.competitor_discovery import discover_competitors_service
from services.identity import identity_variants, normalize_handle, normalize_identity_token

router = APIRouter()
logger = logging.getLogger(__name__)


# ==================== Pydantic Models ====================

class AddCompetitorRequest(BaseModel):
    channel_url: str
    user_id: Optional[str] = None


class AddManualCompetitorRequest(BaseModel):
    platform: Literal["youtube", "instagram", "tiktok"]
    handle: str
    display_name: Optional[str] = None
    external_id: Optional[str] = None
    subscriber_count: Optional[int] = 0
    thumbnail_url: Optional[str] = None
    user_id: Optional[str] = None


class CompetitorResponse(BaseModel):
    id: str
    channel_id: str
    title: str
    custom_url: Optional[str] = None
    subscriber_count: Optional[str] = None  # Kept as string for compatibility
    video_count: Optional[int] = None
    thumbnail_url: Optional[str] = None
    created_at: str
    platform: str


class BlueprintRequest(BaseModel):
    user_id: Optional[str] = None
    platform: Literal["youtube", "instagram", "tiktok"] = "youtube"


class RecommendCompetitorsRequest(BaseModel):
    niche: str
    platform: Literal["youtube", "instagram", "tiktok"] = "youtube"
    user_id: Optional[str] = None
    limit: int = Field(default=8, ge=1, le=20)
    page: int = Field(default=1, ge=1)
    sort_by: Literal["subscriber_count", "avg_views_per_video", "view_count"] = "subscriber_count"
    sort_direction: Literal["desc", "asc"] = "desc"


class RecommendedCompetitor(BaseModel):
    channel_id: str
    title: str
    custom_url: Optional[str] = None
    subscriber_count: int = 0
    video_count: int = 0
    view_count: int = 0
    avg_views_per_video: int = 0
    thumbnail_url: Optional[str] = None
    already_tracked: bool = False


class RecommendCompetitorsResponse(BaseModel):
    niche: str
    page: int
    limit: int
    total_count: int
    has_more: bool
    recommendations: List[RecommendedCompetitor]


class DiscoverCompetitorsRequest(BaseModel):
    platform: Literal["youtube", "instagram", "tiktok"] = "youtube"
    query: str = ""
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=12, ge=1, le=50)
    user_id: Optional[str] = None


class DiscoverCompetitorCandidate(BaseModel):
    external_id: str
    handle: str
    display_name: str
    subscriber_count: int = 0
    video_count: int = 0
    view_count: int = 0
    avg_views_per_video: int = 0
    thumbnail_url: Optional[str] = None
    source: str
    quality_score: float
    already_tracked: bool = False
    source_count: int = 1
    source_labels: List[str] = Field(default_factory=list)
    confidence_tier: Literal["low", "medium", "high"] = "low"
    evidence: List[str] = Field(default_factory=list)


class DiscoverCompetitorsResponse(BaseModel):
    platform: str
    query: str
    page: int
    limit: int
    total_count: int
    has_more: bool
    candidates: List[DiscoverCompetitorCandidate]


class SeriesInsightsRequest(BaseModel):
    user_id: Optional[str] = None
    platform: Literal["youtube", "instagram", "tiktok"] = "youtube"


class ImportCompetitorsFromResearchRequest(BaseModel):
    platform: Literal["instagram", "tiktok"]
    niche: Optional[str] = None
    min_items_per_creator: int = Field(default=2, ge=1, le=20)
    top_n: int = Field(default=25, ge=1, le=100)
    user_id: Optional[str] = None


class ImportCompetitorsFromResearchResponse(BaseModel):
    platform: str
    scanned_items: int
    candidate_creators: int
    imported_count: int
    skipped_existing: int
    skipped_low_volume: int
    competitors: List[CompetitorResponse]


class SeriesPlanRequest(BaseModel):
    user_id: Optional[str] = None
    mode: Literal["scratch", "competitor_template"] = "scratch"
    niche: str = Field(default="creator growth")
    audience: str = Field(default="creators in your niche")
    objective: str = Field(default="increase views, retention, and shares")
    platform: Literal["youtube_shorts", "instagram_reels", "tiktok", "youtube_long"] = "youtube_shorts"
    episodes: int = Field(default=5, ge=3, le=12)
    template_series_key: Optional[str] = None


class SeriesCalendarRequest(BaseModel):
    user_id: Optional[str] = None
    series_title: str
    platform: Literal["youtube_shorts", "instagram_reels", "tiktok", "youtube_long"] = "youtube_shorts"
    start_date: str
    cadence_days: int = Field(default=2, ge=1, le=14)
    episodes: List[Dict[str, Any]]


class SeriesNextEpisodeRequest(BaseModel):
    user_id: Optional[str] = None
    series_title: str
    platform: Literal["youtube_shorts", "instagram_reels", "tiktok", "youtube_long"] = "youtube_shorts"
    completed_episodes: int = Field(default=0, ge=0, le=200)
    objective: str = "increase retention and shares"
    audience: str = "creators in your niche"


class ViralScriptRequest(BaseModel):
    user_id: Optional[str] = None
    platform: Literal["youtube_shorts", "instagram_reels", "tiktok", "youtube_long"] = "youtube_shorts"
    topic: str = Field(min_length=2, max_length=180)
    audience: str = Field(default="creators")
    objective: str = Field(default="increase watch time and shares")
    tone: Literal["bold", "expert", "conversational"] = "bold"
    template_series_key: Optional[str] = None
    desired_duration_s: Optional[int] = Field(default=None, ge=15, le=900)


def _discover_key(*values: Any) -> str:
    tokens = identity_variants(*values)
    if not tokens:
        return ""
    return sorted(tokens, key=len, reverse=True)[0]


# ==================== Endpoints ====================

@router.post("/", response_model=CompetitorResponse)
async def add_competitor(
    request: AddCompetitorRequest,
    _rate_limit: None = Depends(rate_limit("competitor_add", limit=40, window_seconds=3600)),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """Add a competitor channel to track."""
    try:
        client = _get_youtube_client()
        scoped_user_id = ensure_user_scope(auth.user_id, request.user_id)

        channel_id = client.resolve_channel_identifier(request.channel_url)
        if not channel_id:
            raise HTTPException(status_code=400, detail="Could not resolve channel URL")

        # Ensure user exists for FK integrity in MVP mode.
        user_result = await db.execute(select(User).where(User.id == scoped_user_id))
        user = user_result.scalar_one_or_none()
        if not user:
            user = User(id=scoped_user_id, email=f"{scoped_user_id}@local.invalid")
            db.add(user)
            await db.flush()

        # Check if already added for this user.
        result = await db.execute(
            select(Competitor).where(
                Competitor.user_id == scoped_user_id,
                Competitor.external_id == channel_id,
            )
        )
        if result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Competitor already added")

        info = client.get_channel_info(channel_id)
        if not info:
            raise HTTPException(status_code=404, detail="Channel not found")

        new_comp = Competitor(
            id=str(uuid.uuid4()),
            user_id=scoped_user_id,
            platform="youtube",
            handle=info.get("custom_url", "") or info["title"],
            external_id=channel_id,
            display_name=info["title"],
            profile_picture_url=info.get("thumbnail_url"),
            subscriber_count=str(info.get("subscriber_count", 0)),
        )

        db.add(new_comp)
        await db.commit()
        await db.refresh(new_comp)

        return CompetitorResponse(
            id=new_comp.id,
            channel_id=new_comp.external_id,
            title=new_comp.display_name,
            custom_url=new_comp.handle,
            subscriber_count=new_comp.subscriber_count,
            thumbnail_url=new_comp.profile_picture_url,
            created_at=str(new_comp.created_at),
            platform=new_comp.platform,
            video_count=info.get("video_count"),  # Return live data.
        )

    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to add competitor for user %s", auth.user_id)
        raise HTTPException(status_code=500, detail="Failed to add competitor.")


@router.post("/manual", response_model=CompetitorResponse)
async def add_manual_competitor(
    request: AddManualCompetitorRequest,
    _rate_limit: None = Depends(rate_limit("competitor_add_manual", limit=120, window_seconds=3600)),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """Add a manual competitor handle for Instagram/TikTok/YouTube parity research."""
    scoped_user_id = ensure_user_scope(auth.user_id, request.user_id)
    normalized_handle = normalize_handle(request.handle)
    if not normalized_handle:
        raise HTTPException(status_code=422, detail="handle is required")
    external_id = normalize_identity_token(request.external_id) or normalized_handle.lstrip("@")
    display_name = (request.display_name or normalized_handle).strip()

    user_result = await db.execute(select(User).where(User.id == scoped_user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        user = User(id=scoped_user_id, email=f"{scoped_user_id}@local.invalid")
        db.add(user)
        await db.flush()

    existing_result = await db.execute(
        select(Competitor).where(
            Competitor.user_id == scoped_user_id,
            Competitor.platform == request.platform,
            Competitor.external_id == external_id,
        )
    )
    if existing_result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Competitor already added")

    row = Competitor(
        id=str(uuid.uuid4()),
        user_id=scoped_user_id,
        platform=request.platform,
        handle=normalized_handle,
        external_id=external_id,
        display_name=display_name,
        profile_picture_url=request.thumbnail_url,
        subscriber_count=str(max(int(request.subscriber_count or 0), 0)),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return CompetitorResponse(
        id=row.id,
        channel_id=row.external_id,
        title=row.display_name,
        custom_url=row.handle,
        subscriber_count=row.subscriber_count,
        thumbnail_url=row.profile_picture_url,
        created_at=str(row.created_at),
        platform=row.platform,
        video_count=None,
    )


@router.post("/import_from_research", response_model=ImportCompetitorsFromResearchResponse)
async def import_competitors_from_research(
    request: ImportCompetitorsFromResearchRequest,
    _rate_limit: None = Depends(rate_limit("competitor_import_research", limit=40, window_seconds=3600)),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """Auto-create IG/TikTok competitors from imported research items."""
    scoped_user_id = ensure_user_scope(auth.user_id, request.user_id)
    niche_text = str(request.niche or "").strip().lower()

    existing_result = await db.execute(
        select(Competitor).where(
            Competitor.user_id == scoped_user_id,
            Competitor.platform == request.platform,
        )
    )
    existing_competitors = existing_result.scalars().all()
    existing_ids = {
        normalize_identity_token(row.external_id) or str(row.external_id)
        for row in existing_competitors
        if row.external_id
    }

    items_result = await db.execute(
        select(ResearchItem).where(
            ResearchItem.user_id == scoped_user_id,
            ResearchItem.platform == request.platform,
        )
    )
    items = items_result.scalars().all()
    scanned_items = len(items)

    grouped: Dict[str, Dict[str, Any]] = {}
    for item in items:
        text_blob = " ".join(
            [
                str(item.title or ""),
                str(item.caption or ""),
                str(item.creator_handle or ""),
                str(item.creator_display_name or ""),
            ]
        ).lower()
        if niche_text and niche_text not in text_blob:
            continue
        media_meta = item.media_meta_json if isinstance(item.media_meta_json, dict) else {}
        creator_key = _discover_key(
            item.creator_handle,
            media_meta.get("creator_id"),
            item.creator_display_name,
            item.external_id,
        )
        if not creator_key:
            continue
        metrics = item.metrics_json if isinstance(item.metrics_json, dict) else {}
        views = int(metrics.get("views", 0) or 0)
        likes = int(metrics.get("likes", 0) or 0)
        comments = int(metrics.get("comments", 0) or 0)
        shares = int(metrics.get("shares", 0) or 0)
        saves = int(metrics.get("saves", 0) or 0)
        normalized_handle = normalize_handle(item.creator_handle or creator_key)
        bucket = grouped.setdefault(
            creator_key,
            {
                "handle": normalized_handle,
                "display_name": str(item.creator_display_name or item.creator_handle or creator_key).strip(),
                "external_id": creator_key,
                "thumbnail_url": None,
                "items": 0,
                "views_total": 0,
                "engagement_proxy": 0,
            },
        )
        bucket["items"] += 1
        bucket["views_total"] += max(views, 0)
        bucket["engagement_proxy"] += max(likes, 0) + (max(comments, 0) * 2) + (max(shares, 0) * 3) + (max(saves, 0) * 3)
        thumb = media_meta.get("thumbnail_url")
        if thumb and not bucket["thumbnail_url"]:
            bucket["thumbnail_url"] = thumb

    ranked = sorted(
        grouped.values(),
        key=lambda row: (int(row["views_total"]), int(row["items"]), int(row["engagement_proxy"])),
        reverse=True,
    )[:request.top_n]

    imported_rows: List[CompetitorResponse] = []
    skipped_existing = 0
    skipped_low_volume = 0
    for row in ranked:
        if int(row["items"]) < request.min_items_per_creator:
            skipped_low_volume += 1
            continue
        external_id = normalize_identity_token(row["external_id"]) or str(row["external_id"])
        if external_id in existing_ids:
            skipped_existing += 1
            continue
        normalized_handle = normalize_handle(row["handle"] or external_id)
        comp = Competitor(
            id=str(uuid.uuid4()),
            user_id=scoped_user_id,
            platform=request.platform,
            handle=normalized_handle,
            external_id=external_id,
            display_name=str(row["display_name"] or normalized_handle),
            profile_picture_url=row.get("thumbnail_url"),
            subscriber_count=str(max(int(row.get("engagement_proxy", 0)), 0)),
        )
        db.add(comp)
        await db.flush()
        existing_ids.add(external_id)
        imported_rows.append(
            CompetitorResponse(
                id=comp.id,
                channel_id=comp.external_id,
                title=comp.display_name,
                custom_url=comp.handle,
                subscriber_count=comp.subscriber_count,
                thumbnail_url=comp.profile_picture_url,
                created_at=str(comp.created_at),
                platform=comp.platform,
                video_count=int(row["items"]),
            )
        )

    await db.commit()
    return ImportCompetitorsFromResearchResponse(
        platform=request.platform,
        scanned_items=scanned_items,
        candidate_creators=len(ranked),
        imported_count=len(imported_rows),
        skipped_existing=skipped_existing,
        skipped_low_volume=skipped_low_volume,
        competitors=imported_rows,
    )


@router.get("/", response_model=List[CompetitorResponse])
async def list_competitors(
    user_id: Optional[str] = Query(default=None),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """List all competitors for a user."""
    scoped_user_id = ensure_user_scope(auth.user_id, user_id)
    result = await db.execute(select(Competitor).where(Competitor.user_id == scoped_user_id))
    competitors = result.scalars().all()

    return [
        CompetitorResponse(
            id=c.id,
            channel_id=c.external_id,
            title=c.display_name,
            custom_url=c.handle,
            subscriber_count=c.subscriber_count,
            thumbnail_url=c.profile_picture_url,
            created_at=str(c.created_at),
            platform=c.platform,
        )
        for c in competitors
    ]


@router.post("/recommend", response_model=RecommendCompetitorsResponse)
async def recommend_competitors(
    request: RecommendCompetitorsRequest,
    _rate_limit: None = Depends(rate_limit("competitor_recommend", limit=80, window_seconds=3600)),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """
    Recommend top-performing channels for a niche with core performance metrics.
    """
    niche = (request.niche or "").strip()
    if not niche:
        raise HTTPException(status_code=422, detail="niche is required")

    try:
        if request.platform in {"instagram", "tiktok"}:
            scoped_user_id = ensure_user_scope(auth.user_id, request.user_id)
            tracked_result = await db.execute(
                select(Competitor.external_id).where(
                    Competitor.user_id == scoped_user_id,
                    Competitor.platform == request.platform,
                )
            )
            tracked_ids = {str(value) for value in tracked_result.scalars().all() if value}

            items_result = await db.execute(
                select(ResearchItem).where(
                    ResearchItem.user_id == scoped_user_id,
                    ResearchItem.platform == request.platform,
                )
            )
            items = items_result.scalars().all()
            niche_lower = niche.lower()
            grouped: Dict[str, Dict[str, Any]] = {}
            for item in items:
                text_blob = " ".join(
                    [
                        str(item.title or ""),
                        str(item.caption or ""),
                        str(item.creator_handle or ""),
                        str(item.creator_display_name or ""),
                    ]
                ).lower()
                if niche_lower not in text_blob:
                    continue
                media_meta = item.media_meta_json if isinstance(item.media_meta_json, dict) else {}
                dedupe_key = _discover_key(
                    item.creator_handle,
                    media_meta.get("creator_id"),
                    item.creator_display_name,
                    item.external_id,
                )
                if not dedupe_key:
                    continue
                normalized_handle = normalize_handle(item.creator_handle or dedupe_key)
                external_id = dedupe_key
                metrics = item.metrics_json if isinstance(item.metrics_json, dict) else {}
                views = int(metrics.get("views", 0) or 0)
                likes = int(metrics.get("likes", 0) or 0)
                comments = int(metrics.get("comments", 0) or 0)
                shares = int(metrics.get("shares", 0) or 0)
                saves = int(metrics.get("saves", 0) or 0)
                row = grouped.setdefault(
                    external_id,
                    {
                        "title": str(item.creator_display_name or normalized_handle),
                        "custom_url": normalized_handle,
                        "subscriber_count": 0,
                        "video_count": 0,
                        "view_count": 0,
                        "engagement_points": 0,
                        "thumbnail_url": None,
                        "channel_id": external_id,
                    },
                )
                row["video_count"] += 1
                row["view_count"] += max(views, 0)
                row["engagement_points"] += max(likes, 0) + (max(comments, 0) * 2) + (max(shares, 0) * 3) + (max(saves, 0) * 3)
                thumb = media_meta.get("thumbnail_url")
                if thumb and not row["thumbnail_url"]:
                    row["thumbnail_url"] = thumb

            recommendations: List[RecommendedCompetitor] = []
            for external_id, data in grouped.items():
                video_count = max(int(data["video_count"]), 1)
                avg_views = int(int(data["view_count"]) / video_count)
                # follower count not available from metadata-only ingest; use engagement proxy
                subscriber_proxy = int(data.get("engagement_points", 0))
                recommendations.append(
                    RecommendedCompetitor(
                        channel_id=external_id,
                        title=str(data["title"]),
                        custom_url=str(data.get("custom_url") or ""),
                        subscriber_count=subscriber_proxy,
                        video_count=int(data["video_count"]),
                        view_count=int(data["view_count"]),
                        avg_views_per_video=avg_views,
                        thumbnail_url=data.get("thumbnail_url"),
                        already_tracked=external_id in tracked_ids,
                    )
                )

            recommendations.sort(key=lambda r: r.title.lower())
            recommendations.sort(
                key=lambda r: getattr(r, request.sort_by),
                reverse=request.sort_direction == "desc",
            )
            start = (request.page - 1) * request.limit
            end = start + request.limit
            return RecommendCompetitorsResponse(
                niche=niche,
                page=request.page,
                limit=request.limit,
                total_count=len(recommendations),
                has_more=end < len(recommendations),
                recommendations=recommendations[start:end],
            )

        client = _get_youtube_client()
        scoped_user_id = ensure_user_scope(auth.user_id, request.user_id)
        requested_window = request.page * request.limit
        search_limit = min(max(requested_window * 5, requested_window), 50)
        channels = client.search_channels(niche, max_results=search_limit)

        tracked_result = await db.execute(
            select(Competitor.external_id).where(
                Competitor.user_id == scoped_user_id,
                Competitor.platform == "youtube",
            )
        )
        tracked_ids = set(tracked_result.scalars().all())

        recommendations: List[RecommendedCompetitor] = []
        for channel in channels:
            channel_id = channel.get("id")
            if not channel_id:
                continue

            subscriber_count = int(channel.get("subscriber_count", 0) or 0)
            video_count = int(channel.get("video_count", 0) or 0)
            view_count = int(channel.get("view_count", 0) or 0)
            avg_views_per_video = int(view_count / max(video_count, 1))

            recommendations.append(
                RecommendedCompetitor(
                    channel_id=channel_id,
                    title=channel.get("title", "Unknown Channel"),
                    custom_url=channel.get("custom_url"),
                    subscriber_count=subscriber_count,
                    video_count=video_count,
                    view_count=view_count,
                    avg_views_per_video=avg_views_per_video,
                    thumbnail_url=channel.get("thumbnail_url"),
                    already_tracked=channel_id in tracked_ids,
                )
            )

        # Stable two-pass sort keeps alphabetical tie-break regardless of direction.
        recommendations.sort(key=lambda r: r.title.lower())
        recommendations.sort(
            key=lambda r: getattr(r, request.sort_by),
            reverse=request.sort_direction == "desc",
        )
        start = (request.page - 1) * request.limit
        end = start + request.limit
        paged_recommendations = recommendations[start:end]

        return RecommendCompetitorsResponse(
            niche=niche,
            page=request.page,
            limit=request.limit,
            total_count=len(recommendations),
            has_more=end < len(recommendations),
            recommendations=paged_recommendations,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to recommend competitors for user %s", auth.user_id)
        raise HTTPException(status_code=500, detail="Failed to recommend competitors.")


@router.post("/discover", response_model=DiscoverCompetitorsResponse)
async def discover_competitors(
    request: DiscoverCompetitorsRequest,
    _rate_limit: None = Depends(rate_limit("competitor_discover", limit=120, window_seconds=3600)),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """Hybrid-safe competitor discovery with deterministic ranking and identity dedupe."""
    scoped_user_id = ensure_user_scope(auth.user_id, request.user_id)
    try:
        payload = await discover_competitors_service(
            db=db,
            user_id=scoped_user_id,
            platform=request.platform,
            query=request.query,
            page=request.page,
            limit=request.limit,
            youtube_client=_get_youtube_client() if request.platform == "youtube" else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to discover competitors for user %s", auth.user_id)
        raise HTTPException(status_code=500, detail="Failed to discover competitors.")

    return DiscoverCompetitorsResponse(
        platform=str(payload.get("platform") or request.platform),
        query=str(payload.get("query") or ""),
        page=int(payload.get("page") or request.page),
        limit=int(payload.get("limit") or request.limit),
        total_count=int(payload.get("total_count") or 0),
        has_more=bool(payload.get("has_more")),
        candidates=[
            DiscoverCompetitorCandidate(**candidate)
            for candidate in (payload.get("candidates") or [])
        ],
    )


@router.delete("/{competitor_id}")
async def remove_competitor(
    competitor_id: str,
    user_id: Optional[str] = Query(default=None),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """Remove a competitor."""
    scoped_user_id = ensure_user_scope(auth.user_id, user_id)
    result = await db.execute(
        select(Competitor).where(
            Competitor.id == competitor_id,
            Competitor.user_id == scoped_user_id,
        )
    )
    comp = result.scalar_one_or_none()

    if not comp:
        raise HTTPException(status_code=404, detail="Competitor not found")

    await db.delete(comp)
    await db.commit()
    return {"message": "Competitor removed"}


@router.get("/{competitor_id}/videos")
async def get_competitor_videos_endpoint(
    competitor_id: str,
    limit: int = 10,
    user_id: Optional[str] = Query(default=None),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """Get videos for a competitor."""
    scoped_user_id = ensure_user_scope(auth.user_id, user_id)
    result = await db.execute(
        select(Competitor).where(
            Competitor.id == competitor_id,
            Competitor.user_id == scoped_user_id,
        )
    )
    comp = result.scalar_one_or_none()

    if not comp:
        raise HTTPException(status_code=404, detail="Competitor not found")

    return await get_channel_videos(comp.external_id, limit)


@router.post("/blueprint")
async def generate_competitor_blueprint(
    request: BlueprintRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """Generate a strategy blueprint based on competitors."""
    from services.blueprint import generate_blueprint_service

    scoped_user_id = ensure_user_scope(auth.user_id, request.user_id)
    return await generate_blueprint_service(scoped_user_id, db, platform=request.platform)


@router.post("/series")
async def get_competitor_series(
    request: SeriesInsightsRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Get recurring competitor series detected from tracked channels."""
    from services.blueprint import get_competitor_series_service

    scoped_user_id = ensure_user_scope(auth.user_id, request.user_id)
    return await get_competitor_series_service(scoped_user_id, db, platform=request.platform)


@router.post("/series/plan")
async def generate_series_plan(
    request: SeriesPlanRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Generate a repeatable content series plan from scratch or competitor template."""
    from services.blueprint import generate_series_plan_service

    scoped_user_id = ensure_user_scope(auth.user_id, request.user_id)
    return await generate_series_plan_service(scoped_user_id, request.model_dump(), db)


@router.post("/script/generate")
async def generate_viral_script(
    request: ViralScriptRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Generate a high-performing short/reel/tiktok/long-form script scaffold."""
    from services.blueprint import generate_viral_script_service

    scoped_user_id = ensure_user_scope(auth.user_id, request.user_id)
    return await generate_viral_script_service(scoped_user_id, request.model_dump(), db)


@router.post("/series/calendar")
async def build_series_calendar(
    request: SeriesCalendarRequest,
    auth: AuthContext = Depends(get_auth_context),
) -> Dict[str, Any]:
    """Build a publish calendar from a generated series plan."""
    from datetime import datetime, timedelta

    ensure_user_scope(auth.user_id, request.user_id)
    try:
        start_date = datetime.fromisoformat(request.start_date).date()
    except Exception as exc:
        raise HTTPException(status_code=422, detail="start_date must be ISO date (YYYY-MM-DD)") from exc

    scheduled: List[Dict[str, Any]] = []
    for idx, episode in enumerate(request.episodes):
        publish_date = start_date + timedelta(days=idx * request.cadence_days)
        working_title = str(episode.get("working_title") or f"Episode {idx + 1}")
        scheduled.append(
            {
                "episode_number": int(episode.get("episode_number") or (idx + 1)),
                "working_title": working_title,
                "publish_date": publish_date.isoformat(),
                "status": "planned",
                "checklist": [
                    "Finalize hook line",
                    "Record and edit draft",
                    "Run re-score before publishing",
                ],
            }
        )

    return {
        "series_title": request.series_title,
        "platform": request.platform,
        "cadence_days": request.cadence_days,
        "episodes": scheduled,
    }


@router.post("/series/next_episode")
async def next_series_episode(
    request: SeriesNextEpisodeRequest,
    auth: AuthContext = Depends(get_auth_context),
) -> Dict[str, Any]:
    """Generate the next episode brief so creators can continue a series consistently."""
    ensure_user_scope(auth.user_id, request.user_id)
    episode_number = int(request.completed_episodes) + 1
    hook = (
        f"Episode {episode_number}: the one mistake blocking {request.objective} "
        f"for {request.audience}."
    )
    return {
        "series_title": request.series_title,
        "platform": request.platform,
        "episode_number": episode_number,
        "working_title": f"{request.series_title} - Episode {episode_number}",
        "hook_line": hook,
        "outline": [
            "Hook with a concrete outcome claim",
            "Show one proof point from your previous episode comments/results",
            "Deliver 2 tactical steps",
            "End with a single CTA tied to next episode",
        ],
        "cta": "Comment the next blocker you want solved in the next episode.",
    }
