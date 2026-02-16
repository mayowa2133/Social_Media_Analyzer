"""
Analysis router.
"""

import csv
from datetime import datetime, timezone
import io
import json
import uuid
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Depends, File, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from ingestion.youtube import create_youtube_client_with_api_key
from config import require_youtube_api_key
from analysis.metrics import ChannelAnalyzer
from analysis.models import DiagnosisResult
from database import get_db
from models.profile import Profile
from models.user import User
from models.video import Video
from models.video_metrics import VideoMetrics
from routers.auth_scope import AuthContext, ensure_user_scope, get_auth_context
from routers.rate_limit import rate_limit

router = APIRouter()
logger = logging.getLogger(__name__)


def _get_youtube_client():
    """Get YouTube client."""
    try:
        api_key = require_youtube_api_key()
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
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
    user_id: Optional[str] = None
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


class PlatformMetricsCsvIngestResponse(BaseModel):
    ingested: bool
    processed_rows: int
    successful_rows: int
    failed_rows: int
    failures: List[Dict[str, Any]]


def _coerce_int(value: Any, default: int = 0) -> int:
    if value in (None, ""):
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _coerce_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_retention_points_raw(raw: Any) -> List[Dict[str, float]]:
    if raw in (None, ""):
        return []
    parsed = raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except Exception:
            return []
    if not isinstance(parsed, list):
        return []
    result: List[Dict[str, float]] = []
    for point in parsed:
        if not isinstance(point, dict):
            continue
        time_val = _coerce_float(point.get("time"), None)
        retention_val = _coerce_float(point.get("retention"), None)
        if time_val is None or retention_val is None:
            continue
        result.append({"time": float(time_val), "retention": float(retention_val)})
    return result


async def _ingest_platform_metrics_record(
    scoped_user_id: str,
    request: PlatformMetricsIngestRequest,
    db: AsyncSession,
) -> PlatformMetricsIngestResponse:
    user_result = await db.execute(select(User).where(User.id == scoped_user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        user = User(id=scoped_user_id, email=f"{scoped_user_id}@local.invalid")
        db.add(user)
        await db.flush()

    profile_result = await db.execute(
        select(Profile)
        .where(Profile.user_id == scoped_user_id, Profile.platform == request.platform)
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
    except Exception:
        logger.exception("Failed to generate channel diagnosis for channel_id=%s", channel_id)
        raise HTTPException(status_code=500, detail="Failed to generate diagnosis.")


@router.post("/ingest/platform_metrics", response_model=PlatformMetricsIngestResponse)
async def ingest_platform_metrics(
    request: PlatformMetricsIngestRequest,
    _rate_limit: None = Depends(rate_limit("metrics_ingest", limit=240, window_seconds=3600)),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """
    Ingest true platform analytics for a video (owner-side export).

    This endpoint stores shares/saves/retention points and other metrics so
    diagnosis can use true signals instead of only proxies where available.
    """
    try:
        scoped_user_id = ensure_user_scope(auth.user_id, request.user_id)
        return await _ingest_platform_metrics_record(scoped_user_id, request, db)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to ingest platform metrics for user %s", request.user_id)
        raise HTTPException(status_code=500, detail="Failed to ingest platform metrics.")


@router.post("/ingest/platform_metrics_csv", response_model=PlatformMetricsCsvIngestResponse)
async def ingest_platform_metrics_csv(
    file: UploadFile = File(...),
    platform: str = "youtube",
    user_id: Optional[str] = None,
    _rate_limit: None = Depends(rate_limit("metrics_ingest_csv", limit=30, window_seconds=3600)),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """Bulk ingest true metrics from CSV export rows."""
    scoped_user_id = ensure_user_scope(auth.user_id, user_id)
    failures: List[Dict[str, Any]] = []
    processed_rows = 0
    successful_rows = 0

    try:
        content = await file.read()
        if len(content) > 5 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="CSV file too large. Max 5MB.")
        text = content.decode("utf-8-sig")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not read CSV file: {exc}") from exc
    finally:
        await file.close()

    try:
        reader = csv.DictReader(io.StringIO(text))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid CSV: {exc}") from exc

    for row_idx, row in enumerate(reader, start=2):
        processed_rows += 1
        external_id = str(row.get("video_external_id", "") or "").strip()
        if not external_id:
            failures.append({"row": row_idx, "error": "Missing video_external_id"})
            continue

        try:
            request_payload = PlatformMetricsIngestRequest(
                user_id=scoped_user_id,
                platform=platform,
                video_external_id=external_id,
                video_url=str(row.get("video_url", "") or "").strip() or None,
                title=str(row.get("title", "") or "").strip() or None,
                published_at=str(row.get("published_at", "") or "").strip() or None,
                duration_seconds=_coerce_int(row.get("duration_seconds"), 0) or None,
                views=_coerce_int(row.get("views"), 0),
                likes=_coerce_int(row.get("likes"), 0),
                comments=_coerce_int(row.get("comments"), 0),
                shares=_coerce_int(row.get("shares"), 0),
                saves=_coerce_int(row.get("saves"), 0),
                watch_time_hours=_coerce_float(row.get("watch_time_hours"), None),
                avg_view_duration_s=_coerce_float(row.get("avg_view_duration_s"), None),
                ctr=_coerce_float(row.get("ctr"), None),
                retention_points=[
                    RetentionPoint(time=item["time"], retention=item["retention"])
                    for item in _parse_retention_points_raw(row.get("retention_points_json"))
                ] or None,
            )
            await _ingest_platform_metrics_record(scoped_user_id, request_payload, db)
            successful_rows += 1
        except Exception as exc:
            await db.rollback()
            failures.append({"row": row_idx, "video_external_id": external_id, "error": str(exc)})

    return PlatformMetricsCsvIngestResponse(
        ingested=True,
        processed_rows=processed_rows,
        successful_rows=successful_rows,
        failed_rows=len(failures),
        failures=failures[:50],
    )
