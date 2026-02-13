"""
Router for competitor management and analysis.
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from pydantic import BaseModel
from typing import List, Optional
import uuid
from datetime import datetime

from database import get_db
from models.competitor import Competitor
from models.user import User
from routers.youtube import _get_youtube_client, ChannelInfo, VideoInfo, get_channel_videos

router = APIRouter()

# ==================== Pydantic Models ====================

class AddCompetitorRequest(BaseModel):
    channel_url: str
    user_id: str = "test-user" # Optional for MVP

class CompetitorResponse(BaseModel):
    id: str
    channel_id: str
    title: str
    custom_url: Optional[str] = None
    subscriber_count: Optional[str] = None # Strings in YouTube API sometimes
    video_count: Optional[int] = None
    thumbnail_url: Optional[str] = None
    created_at: str
    platform: str

class BlueprintRequest(BaseModel):
    user_id: str = "test-user"

class BlueprintResponse(BaseModel):
    gap_analysis: List[str]
    content_pillars: List[str]
    video_ideas: List[dict]


# ==================== Endpoints ====================

@router.post("/", response_model=CompetitorResponse)
async def add_competitor(
    request: AddCompetitorRequest, 
    db: AsyncSession = Depends(get_db)
):
    """Add a competitor channel to track."""
    try:
        client = _get_youtube_client()
        
        # Resolve channel
        channel_id = client.resolve_channel_identifier(request.channel_url)
        if not channel_id:
            raise HTTPException(status_code=400, detail="Could not resolve channel URL")

        # Ensure user exists for FK integrity in MVP mode.
        user_result = await db.execute(select(User).where(User.id == request.user_id))
        user = user_result.scalar_one_or_none()
        if not user:
            user = User(id=request.user_id, email=f"{request.user_id}@local.invalid")
            db.add(user)
            await db.flush()
        
        # Check if already added for this user
        result = await db.execute(
            select(Competitor).where(
                Competitor.user_id == request.user_id,
                Competitor.external_id == channel_id
            )
        )
        if result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Competitor already added")

        # Get channel info
        info = client.get_channel_info(channel_id)
        if not info:
             raise HTTPException(status_code=404, detail="Channel not found")

        # Create
        new_comp = Competitor(
            id=str(uuid.uuid4()),
            user_id=request.user_id,
            platform="youtube",
            handle=info.get("custom_url", "") or info["title"],
            external_id=channel_id,
            display_name=info["title"],
            profile_picture_url=info.get("thumbnail_url"),
            subscriber_count=str(info.get("subscriber_count", 0)),
            # video_count is not in model? Check model again.
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
            video_count=info.get("video_count") # Return live data
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/", response_model=List[CompetitorResponse])
async def list_competitors(
    user_id: str = "test-user",
    db: AsyncSession = Depends(get_db)
):
    """List all competitors for a user."""
    result = await db.execute(select(Competitor).where(Competitor.user_id == user_id))
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
            platform=c.platform
        ) for c in competitors
    ]

@router.delete("/{competitor_id}")
async def remove_competitor(competitor_id: str, db: AsyncSession = Depends(get_db)):
    """Remove a competitor."""
    result = await db.execute(select(Competitor).where(Competitor.id == competitor_id))
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
    db: AsyncSession = Depends(get_db)
):
    """Get videos for a competitor."""
    result = await db.execute(select(Competitor).where(Competitor.id == competitor_id))
    comp = result.scalar_one_or_none()
    
    if not comp:
        raise HTTPException(status_code=404, detail="Competitor not found")
        
    return await get_channel_videos(comp.external_id, limit)

@router.post("/blueprint")
async def generate_competitor_blueprint(
    request: BlueprintRequest,
    db: AsyncSession = Depends(get_db)
):
    """Generate a strategy blueprint based on competitors."""
    from services.blueprint import generate_blueprint_service
    return await generate_blueprint_service(request.user_id, db)
