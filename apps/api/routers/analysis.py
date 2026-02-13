"""
Analysis router.
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any

from ingestion.youtube import YouTubeClient, create_youtube_client_with_api_key
from config import settings
from analysis.metrics import ChannelAnalyzer
from analysis.models import DiagnosisResult

router = APIRouter()


def _get_youtube_client():
    """Get YouTube client."""
    # Reusing the helper from routers.youtube or instantiating directly
    api_key = settings.YOUTUBE_API_KEY if hasattr(settings, 'YOUTUBE_API_KEY') else settings.GOOGLE_CLIENT_SECRET
    if not api_key:
        raise HTTPException(
            status_code=500, 
            detail="YouTube API key not configured"
        )
    return create_youtube_client_with_api_key(api_key)


@router.get("/diagnose/channel/{channel_id}")
async def diagnose_channel(channel_id: str) -> DiagnosisResult:
    """
    Run a full diagnosis on a channel.
    Fetches latest 50 videos and runs the analyzer.
    """
    try:
        client = _get_youtube_client()
        
        # 1. Fetch channel info
        channel_info = client.get_channel_info(channel_id)
        if not channel_info:
            raise HTTPException(status_code=404, detail="Channel not found")
            
        # 2. Fetch recent videos (up to 50 for statistical significance)
        videos_data = client.get_channel_videos(channel_id, max_results=50)
        
        # 3. Get detailed stats for those videos
        if videos_data:
            video_ids = [v["id"] for v in videos_data]
            details = client.get_video_details(video_ids)
            
            # Merge details into video objects
            for vid in videos_data:
                vid_id = vid["id"]
                if vid_id in details:
                    vid.update({
                        "view_count": details[vid_id]["view_count"],
                        "like_count": details[vid_id]["like_count"],
                        "comment_count": details[vid_id]["comment_count"],
                        "duration_seconds": details[vid_id]["duration_seconds"]
                    })
        
        # 4. Run Analysis
        analyzer = ChannelAnalyzer(channel_info, videos_data)
        diagnosis = analyzer.analyze()
        
        return diagnosis
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
