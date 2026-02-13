"""
Service for generating Competitor Blueprints.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import Dict, Any, Optional, Tuple
import asyncio
import json

from models.competitor import Competitor
from models.connection import Connection
from models.profile import Profile
from routers.youtube import _get_youtube_client
from config import settings


async def _resolve_user_channel(db: AsyncSession, user_id: str) -> Tuple[Optional[str], str]:
    """
    Resolve user's YouTube channel identity from profiles first, then connection metadata.
    """
    profile_result = await db.execute(
        select(Profile)
        .where(Profile.user_id == user_id, Profile.platform == "youtube")
        .order_by(Profile.created_at.desc())
        .limit(1)
    )
    profile = profile_result.scalar_one_or_none()
    if profile and profile.external_id:
        return profile.external_id, (profile.display_name or profile.handle or "User Channel")

    conn_result = await db.execute(
        select(Connection)
        .where(Connection.user_id == user_id, Connection.platform == "youtube")
        .order_by(Connection.created_at.desc())
        .limit(1)
    )
    connection = conn_result.scalar_one_or_none()
    if connection and connection.platform_user_id:
        return connection.platform_user_id, (connection.platform_handle or "User Channel")

    return None, "User Channel"


async def generate_blueprint_service(user_id: str, db: AsyncSession) -> Dict[str, Any]:
    """
    Generate a gap analysis and content strategy blueprint.
    """
    # 1. Resolve User Channel
    user_channel_id, user_channel_name = await _resolve_user_channel(db, user_id)
    
    # 2. Get Competitors
    result = await db.execute(select(Competitor).where(Competitor.user_id == user_id))
    competitors = result.scalars().all()
    
    if not competitors:
        # Return empty state or error
        return {
            "gap_analysis": ["Add competitors to generate a blueprint."],
            "content_pillars": [],
            "video_ideas": []
        }

    # 3. Fetch Data (Concurrent)
    # We want last 10 videos from everyone to see what's working NOW.
    
    client = _get_youtube_client()
    
    # Helper to fetch videos
    async def fetch_videos_safe(channel_id, label):
        try:
            vids = client.get_channel_videos(channel_id, max_results=10)
            vid_ids = [v["id"] for v in vids]
            details = client.get_video_details(vid_ids)
            
            # Enrich
            enriched = []
            for v in vids:
                d = details.get(v["id"], {})
                enriched.append({
                    "title": v["title"],
                    "views": d.get("view_count", 0),
                    "likes": d.get("like_count", 0),
                    "published": v.get("published_at"),
                    "channel": label
                })
            return enriched
        except Exception as e:
            print(f"Error fetching for {label}: {e}")
            return []

    tasks = []
    if user_channel_id:
        tasks.append(fetch_videos_safe(user_channel_id, "User"))
    for comp in competitors:
        tasks.append(fetch_videos_safe(comp.external_id, comp.display_name or "Competitor"))
        
    results = await asyncio.gather(*tasks)
    
    all_videos = []
    for r in results:
        all_videos.extend(r)
        
    # 4. LLM Analysis
    # Prepare prompt
    prompt = f"""
    Analyze these YouTube video performance stats to create a content blueprint.
    
    My Channel: {user_channel_name} (Videos: {[v for v in all_videos if v['channel'] == 'User']})
    
    Competitors:
    {json.dumps([v for v in all_videos if v['channel'] != 'User'], default=str)}
    
    Identify:
    1. Gaps: What high-performing topics/formats are competitors doing that I am missing?
    2. Pillars: Recommend 3 content pillars based on competitor wins.
    3. Ideas: Generate 3 specific video ideas (Title + Brief Concept) that steal their strategy but improve it.
    
    Return JSON:
    {{
        "gap_analysis": ["point 1", "point 2"],
        "content_pillars": ["pillar 1", "pillar 2"],
        "video_ideas": [
            {{"title": "...", "concept": "..."}}
        ]
    }}
    """
    
    from multimodal.llm import get_openai_client
    try:
        oa_client = get_openai_client(settings.OPENAI_API_KEY)
        if oa_client is None:
            raise ValueError("OpenAI API key missing; using deterministic fallback blueprint.")

        response = oa_client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        content = response.choices[0].message.content
        return json.loads(content)
    except Exception as e:
        print(f"LLM Error: {e}")
        # Deterministic fallback for local/dev mode
        return {
            "gap_analysis": [
                "Competitors publish more frequently on repeatable formats.",
                "Top competitor videos rely on clearer hook framing in the first 10 seconds.",
            ],
            "content_pillars": ["Behind the Scenes", "Tutorials", "Challenges"],
            "video_ideas": [
                {"title": "I Tried X for 7 Days", "concept": "Challenge format modeled after high-performing peers."},
                {"title": "Ultimate Guide to Y", "concept": "Deep dive tutorial targeting proven audience demand."},
                {"title": "My Studio Setup 2026", "concept": "Transparent breakdown format that drives comments and shares."}
            ]
        }
