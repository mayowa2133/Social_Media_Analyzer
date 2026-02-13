"""
YouTube API router for channel data and video ingestion.
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel, HttpUrl
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
import re

from config import settings
from database import get_db

router = APIRouter()


# ==================== Pydantic Models ====================

class ChannelInfo(BaseModel):
    """YouTube channel information."""
    channel_id: str
    title: str
    description: Optional[str] = None
    custom_url: Optional[str] = None
    subscriber_count: Optional[int] = None
    video_count: Optional[int] = None
    view_count: Optional[int] = None
    thumbnail_url: Optional[str] = None


class VideoInfo(BaseModel):
    """YouTube video information."""
    video_id: str
    title: str
    description: Optional[str] = None
    published_at: str
    duration_seconds: int = 0
    thumbnail_url: Optional[str] = None
    view_count: int = 0
    like_count: int = 0
    comment_count: int = 0


class AddCompetitorRequest(BaseModel):
    """Request to add a competitor channel."""
    channel_url: str


class CompetitorResponse(BaseModel):
    """Response for a competitor channel."""
    id: str
    channel_id: str
    title: str
    custom_url: Optional[str] = None
    subscriber_count: Optional[int] = None
    video_count: Optional[int] = None
    thumbnail_url: Optional[str] = None
    created_at: str


class ResolveChannelRequest(BaseModel):
    """Request to resolve a channel URL to channel ID."""
    url: str


class ResolveChannelResponse(BaseModel):
    """Response with resolved channel ID."""
    channel_id: Optional[str] = None
    title: Optional[str] = None
    error: Optional[str] = None


# ==================== Helpers ====================

def _get_youtube_client():
    """Get YouTube client using API key."""
    from ingestion.youtube import create_youtube_client_with_api_key
    
    api_key = settings.YOUTUBE_API_KEY if hasattr(settings, 'YOUTUBE_API_KEY') else settings.GOOGLE_CLIENT_SECRET
    if not api_key:
        raise HTTPException(
            status_code=500, 
            detail="YouTube API key not configured"
        )
    return create_youtube_client_with_api_key(api_key)


# ==================== Endpoints ====================

@router.post("/resolve")
async def resolve_channel(request: ResolveChannelRequest) -> ResolveChannelResponse:
    """
    Resolve a YouTube channel URL or handle to a channel ID.
    
    Supports:
    - youtube.com/channel/UC...
    - youtube.com/@handle
    - youtube.com/c/customurl
    - @handle
    """
    try:
        client = _get_youtube_client()
        channel_id = client.resolve_channel_identifier(request.url)
        
        if not channel_id:
            return ResolveChannelResponse(error="Could not resolve channel")
        
        # Get channel title
        channel_info = client.get_channel_info(channel_id)
        title = channel_info.get("title") if channel_info else None
        
        return ResolveChannelResponse(channel_id=channel_id, title=title)
    except Exception as e:
        return ResolveChannelResponse(error=str(e))


@router.get("/channel/{channel_id}")
async def get_channel_info(channel_id: str) -> ChannelInfo:
    """Get channel information by channel ID."""
    try:
        client = _get_youtube_client()
        info = client.get_channel_info(channel_id)
        
        if not info:
            raise HTTPException(status_code=404, detail="Channel not found")
        
        return ChannelInfo(
            channel_id=info["id"],
            title=info["title"],
            description=info.get("description"),
            custom_url=info.get("custom_url"),
            subscriber_count=info.get("subscriber_count"),
            video_count=info.get("video_count"),
            view_count=info.get("view_count"),
            thumbnail_url=info.get("thumbnail_url"),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/channel/{channel_id}/videos")
async def get_channel_videos(
    channel_id: str,
    limit: int = Query(default=20, le=50)
) -> List[VideoInfo]:
    """Get recent videos from a channel."""
    try:
        client = _get_youtube_client()
        videos = client.get_channel_videos(channel_id, max_results=limit)
        
        if not videos:
            return []
        
        # Get video details (views, likes, duration)
        video_ids = [v["id"] for v in videos if v.get("id")]
        details = client.get_video_details(video_ids)
        
        result = []
        for video in videos:
            video_id = video.get("id")
            if not video_id:
                continue
            
            video_details = details.get(video_id, {})
            result.append(VideoInfo(
                video_id=video_id,
                title=video["title"],
                description=video.get("description"),
                published_at=video.get("published_at", ""),
                duration_seconds=video_details.get("duration_seconds", 0),
                thumbnail_url=video.get("thumbnail_url"),
                view_count=video_details.get("view_count", 0),
                like_count=video_details.get("like_count", 0),
                comment_count=video_details.get("comment_count", 0),
            ))
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Competitor Management moved to routers/competitor.py
