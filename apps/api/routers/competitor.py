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
from models.user import User
from routers.auth_scope import AuthContext, ensure_user_scope, get_auth_context
from routers.rate_limit import rate_limit
from routers.youtube import _get_youtube_client, get_channel_videos

router = APIRouter()
logger = logging.getLogger(__name__)


# ==================== Pydantic Models ====================

class AddCompetitorRequest(BaseModel):
    channel_url: str
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


class RecommendCompetitorsRequest(BaseModel):
    niche: str
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


class SeriesInsightsRequest(BaseModel):
    user_id: Optional[str] = None


class SeriesPlanRequest(BaseModel):
    user_id: Optional[str] = None
    mode: Literal["scratch", "competitor_template"] = "scratch"
    niche: str = Field(default="creator growth")
    audience: str = Field(default="creators in your niche")
    objective: str = Field(default="increase views, retention, and shares")
    platform: Literal["youtube_shorts", "instagram_reels", "tiktok", "youtube_long"] = "youtube_shorts"
    episodes: int = Field(default=5, ge=3, le=12)
    template_series_key: Optional[str] = None


class ViralScriptRequest(BaseModel):
    user_id: Optional[str] = None
    platform: Literal["youtube_shorts", "instagram_reels", "tiktok", "youtube_long"] = "youtube_shorts"
    topic: str = Field(min_length=2, max_length=180)
    audience: str = Field(default="creators")
    objective: str = Field(default="increase watch time and shares")
    tone: Literal["bold", "expert", "conversational"] = "bold"
    template_series_key: Optional[str] = None
    desired_duration_s: Optional[int] = Field(default=None, ge=15, le=900)


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
    return await generate_blueprint_service(scoped_user_id, db)


@router.post("/series")
async def get_competitor_series(
    request: SeriesInsightsRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Get recurring competitor series detected from tracked channels."""
    from services.blueprint import get_competitor_series_service

    scoped_user_id = ensure_user_scope(auth.user_id, request.user_id)
    return await get_competitor_series_service(scoped_user_id, db)


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
