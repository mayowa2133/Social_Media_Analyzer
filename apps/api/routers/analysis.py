"""
Analysis router.
"""

from datetime import datetime, timezone
import uuid
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from ingestion.youtube import create_youtube_client_with_api_key
from config import settings
from analysis.metrics import ChannelAnalyzer
from analysis.models import DiagnosisResult
from database import get_db
from models.profile import Profile
from models.user import User
from models.video import Video
from models.video_metrics import VideoMetrics

router = APIRouter()
logger = logging.getLogger(__name__)


def _get_youtube_client():
    """Get YouTube client."""
    api_key = settings.YOUTUBE_API_KEY if hasattr(settings, "YOUTUBE_API_KEY") else settings.GOOGLE_CLIENT_SECRET
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="YouTube API key not configured"
        )
    return create_youtube_client_with_api_key(api_key)


def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        text = str(value)
        if text.endswith("Z"):
            text = text.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return None


class RetentionPoint(BaseModel):
    time: float
    retention: float


class PlatformMetricsIngestRequest(BaseModel):
    user_id: str = "test-user"
    platform: str = "youtube"
    video_external_id: str
    video_url: Optional[str] = None
    title: Optional[str] = None
    published_at: Optional[str] = None
    duration_seconds: Optional[int] = None
    views: int = Field(default=0, ge=0)
    likes: int = Field(default=0, ge=0)
    comments: int = Field(default=0, ge=0)
    shares: int = Field(default=0, ge=0)
    saves: int = Field(default=0, ge=0)
    watch_time_hours: Optional[float] = None
    avg_view_duration_s: Optional[float] = None
    ctr: Optional[float] = None
    retention_points: Optional[List[RetentionPoint]] = None


class PlatformMetricsIngestResponse(BaseModel):
    ingested: bool
    video_id: str
    metrics_id: str
    metric_coverage: Dict[str, str]


@router.get("/diagnose/channel/{channel_id}")
async def diagnose_channel(
    channel_id: str,
    db: AsyncSession = Depends(get_db),
) -> DiagnosisResult:
    """
    Run a full diagnosis on a channel.
    Fetches latest 50 videos and runs the analyzer.

    If true platform metrics are available in DB for these videos,
    they are merged into video objects before analysis.
    """
    try:
        client = _get_youtube_client()

        channel_info = client.get_channel_info(channel_id)
        if not channel_info:
            raise HTTPException(status_code=404, detail="Channel not found")

        videos_data = client.get_channel_videos(channel_id, max_results=50)

        if videos_data:
            video_ids = [v["id"] for v in videos_data]
            details = client.get_video_details(video_ids)

            latest_metrics_by_video: Dict[str, Dict[str, Any]] = {}
            try:
                metrics_result = await db.execute(
                    select(
                        Video.external_id,
                        VideoMetrics.shares,
                        VideoMetrics.saves,
                        VideoMetrics.retention_points_json,
                        VideoMetrics.watch_time_hours,
                        VideoMetrics.avg_view_duration_s,
                        VideoMetrics.ctr,
                    )
                    .join(VideoMetrics, VideoMetrics.video_id == Video.id)
                    .where(Video.external_id.in_(video_ids))
                    .order_by(VideoMetrics.fetched_at.desc())
                )
                metrics_rows = metrics_result.all()
                for row in metrics_rows:
                    external_id = str(row[0])
                    if external_id in latest_metrics_by_video:
                        continue
                    retention_payload = row[3]
                    retention_points = retention_payload if isinstance(retention_payload, list) else []
                    latest_metrics_by_video[external_id] = {
                        "shares": row[1],
                        "saves": row[2],
                        "retention_points": retention_points,
                        "watch_time_hours": row[4],
                        "avg_view_duration_s": row[5],
                        "ctr": row[6],
                    }
            except Exception as metrics_error:
                logger.warning("Could not load true platform metrics for diagnosis: %s", metrics_error)

            for vid in videos_data:
                vid_id = vid["id"]
                if vid_id in details:
                    vid.update({
                        "view_count": details[vid_id]["view_count"],
                        "like_count": details[vid_id]["like_count"],
                        "comment_count": details[vid_id]["comment_count"],
                        "duration_seconds": details[vid_id]["duration_seconds"],
                    })
                if vid_id in latest_metrics_by_video:
                    vid.update(latest_metrics_by_video[vid_id])

        analyzer = ChannelAnalyzer(channel_info, videos_data)
        diagnosis = analyzer.analyze()

        return diagnosis

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ingest/platform_metrics", response_model=PlatformMetricsIngestResponse)
async def ingest_platform_metrics(
    request: PlatformMetricsIngestRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Ingest true platform analytics for a video (owner-side export).

    This endpoint stores shares/saves/retention points and other metrics so
    diagnosis can use true signals instead of only proxies where available.
    """
    try:
        user_result = await db.execute(select(User).where(User.id == request.user_id))
        user = user_result.scalar_one_or_none()
        if not user:
            user = User(id=request.user_id, email=f"{request.user_id}@local.invalid")
            db.add(user)
            await db.flush()

        profile_result = await db.execute(
            select(Profile)
            .where(Profile.user_id == request.user_id, Profile.platform == request.platform)
            .order_by(Profile.created_at.desc())
            .limit(1)
        )
        profile = profile_result.scalar_one_or_none()

        video_result = await db.execute(
            select(Video).where(
                Video.external_id == request.video_external_id,
                Video.platform == request.platform,
                Video.profile_id == (profile.id if profile else None),
            )
        )
        video = video_result.scalar_one_or_none()

        if not video:
            default_url = request.video_url or f"https://www.youtube.com/watch?v={request.video_external_id}"
            video = Video(
                id=str(uuid.uuid4()),
                profile_id=profile.id if profile else None,
                competitor_id=None,
                platform=request.platform,
                external_id=request.video_external_id,
                url=default_url,
                title=request.title or request.video_external_id,
                description=None,
                published_at=_parse_datetime(request.published_at),
                duration_s=request.duration_seconds,
                thumbnail_url=None,
            )
            db.add(video)
            await db.flush()
        else:
            if request.video_url:
                video.url = request.video_url
            if request.title:
                video.title = request.title
            if request.duration_seconds is not None:
                video.duration_s = request.duration_seconds
            if request.published_at:
                parsed = _parse_datetime(request.published_at)
                if parsed:
                    video.published_at = parsed

        retention_points = [p.model_dump() for p in (request.retention_points or [])]

        metrics = VideoMetrics(
            id=str(uuid.uuid4()),
            video_id=video.id,
            views=request.views,
            likes=request.likes,
            comments=request.comments,
            shares=request.shares,
            saves=request.saves,
            watch_time_hours=request.watch_time_hours,
            avg_view_duration_s=request.avg_view_duration_s,
            ctr=request.ctr,
            retention_points_json=retention_points if retention_points else None,
        )
        db.add(metrics)
        await db.commit()

        return PlatformMetricsIngestResponse(
            ingested=True,
            video_id=video.id,
            metrics_id=metrics.id,
            metric_coverage={
                "shares": "true",
                "saves": "true",
                "retention_curve": "true" if retention_points else "missing",
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
