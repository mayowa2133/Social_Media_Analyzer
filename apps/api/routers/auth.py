"""
Authentication router for OAuth session sync and user profile retrieval.
"""

from datetime import datetime, timezone
import uuid
from typing import Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from database import get_db
from ingestion.youtube import create_youtube_client_with_oauth
from models.connection import Connection
from models.profile import Profile
from models.user import User
from routers.auth_scope import AuthContext, get_auth_context
from services.crypto import encrypt_token
from services.session_token import create_session_token

router = APIRouter()


class SyncYouTubeSessionRequest(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    expires_at: Optional[int] = None  # Unix timestamp (seconds)
    scope: Optional[str] = None
    user_id: Optional[str] = None
    email: str
    name: Optional[str] = None
    picture: Optional[str] = None


class SyncYouTubeSessionResponse(BaseModel):
    user_id: str
    email: str
    youtube_connected: bool
    session_token: str
    session_expires_at: int
    channel_id: Optional[str] = None
    channel_title: Optional[str] = None
    channel_handle: Optional[str] = None
    subscriber_count: Optional[str] = None
    thumbnail_url: Optional[str] = None


class CurrentUserResponse(BaseModel):
    user_id: str
    email: str
    name: Optional[str] = None
    picture: Optional[str] = None
    youtube_connected: bool = False
    channel_id: Optional[str] = None
    channel_title: Optional[str] = None
    channel_handle: Optional[str] = None
    subscriber_count: Optional[str] = None
    thumbnail_url: Optional[str] = None
    instagram_connected: bool = False
    tiktok_connected: bool = False
    connected_platforms: Dict[str, bool] = {}
    profiles: List[Dict[str, Optional[str]]] = []


class SyncSocialConnectionRequest(BaseModel):
    platform: Literal["instagram", "tiktok"]
    handle: str
    external_id: Optional[str] = None
    display_name: Optional[str] = None
    follower_count: Optional[str] = None
    profile_picture_url: Optional[str] = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    expires_at: Optional[int] = None
    scope: Optional[str] = None
    user_id: Optional[str] = None
    email: str
    name: Optional[str] = None
    picture: Optional[str] = None


class SyncSocialConnectionResponse(BaseModel):
    user_id: str
    email: str
    platform: str
    connected: bool
    session_token: str
    session_expires_at: int
    profile: Dict[str, Optional[str]]


def _to_datetime(value: Optional[int]) -> Optional[datetime]:
    if not value:
        return None
    return datetime.fromtimestamp(value, tz=timezone.utc)


@router.get("/me", response_model=CurrentUserResponse)
async def get_current_user(
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """Get current user profile and platform connection status."""
    result = await db.execute(select(User).where(User.id == auth.user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    conn_result = await db.execute(
        select(Connection)
        .where(Connection.user_id == user.id, Connection.platform.in_(["youtube", "instagram", "tiktok"]))
        .order_by(desc(Connection.created_at))
    )
    connections = conn_result.scalars().all()
    connected_platforms = {
        "youtube": False,
        "instagram": False,
        "tiktok": False,
    }
    for row in connections:
        platform_key = str(row.platform or "").lower()
        if platform_key in connected_platforms:
            connected_platforms[platform_key] = True

    profile_result = await db.execute(
        select(Profile)
        .where(Profile.user_id == user.id, Profile.platform.in_(["youtube", "instagram", "tiktok"]))
        .order_by(desc(Profile.created_at))
    )
    profile_rows = profile_result.scalars().all()
    profile_by_platform: Dict[str, Profile] = {}
    for row in profile_rows:
        platform_key = str(row.platform or "").lower()
        if platform_key not in profile_by_platform:
            profile_by_platform[platform_key] = row

    youtube_profile = profile_by_platform.get("youtube")
    profiles_payload: List[Dict[str, Optional[str]]] = []
    for platform_key in ("youtube", "instagram", "tiktok"):
        row = profile_by_platform.get(platform_key)
        if not row:
            continue
        profiles_payload.append(
            {
                "platform": platform_key,
                "external_id": row.external_id,
                "handle": row.handle,
                "display_name": row.display_name,
                "subscriber_count": row.subscriber_count,
                "profile_picture_url": row.profile_picture_url,
            }
        )

    return CurrentUserResponse(
        user_id=user.id,
        email=user.email,
        name=user.name,
        picture=user.picture,
        youtube_connected=connected_platforms["youtube"],
        channel_id=youtube_profile.external_id if youtube_profile else None,
        channel_title=youtube_profile.display_name if youtube_profile else None,
        channel_handle=youtube_profile.handle if youtube_profile else None,
        subscriber_count=youtube_profile.subscriber_count if youtube_profile else None,
        thumbnail_url=youtube_profile.profile_picture_url if youtube_profile else None,
        instagram_connected=connected_platforms["instagram"],
        tiktok_connected=connected_platforms["tiktok"],
        connected_platforms=connected_platforms,
        profiles=profiles_payload,
    )


@router.post("/sync/youtube", response_model=SyncYouTubeSessionResponse)
async def sync_youtube_session(
    request: SyncYouTubeSessionRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Persist a frontend OAuth session into backend tables and hydrate channel identity.
    """
    # 1. Resolve authenticated channel using OAuth access token.
    try:
        youtube = create_youtube_client_with_oauth(request.access_token)
        channel_info = youtube.get_my_channel_info()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid YouTube OAuth token: {e}")

    if not channel_info:
        raise HTTPException(status_code=400, detail="Could not load authenticated YouTube channel")

    # 2. Upsert user.
    user: Optional[User] = None
    if request.user_id:
        user_result = await db.execute(select(User).where(User.id == request.user_id))
        user = user_result.scalar_one_or_none()
    if not user:
        user_result = await db.execute(select(User).where(User.email == str(request.email)))
        user = user_result.scalar_one_or_none()

    if not user:
        user = User(
            id=request.user_id or str(uuid.uuid4()),
            email=str(request.email),
            name=request.name,
            picture=request.picture,
        )
        db.add(user)
        await db.flush()
    else:
        user.email = str(request.email)
        if request.name:
            user.name = request.name
        if request.picture:
            user.picture = request.picture

    # 3. Upsert encrypted connection.
    conn_result = await db.execute(
        select(Connection).where(
            Connection.user_id == user.id,
            Connection.platform == "youtube",
        )
    )
    connection = conn_result.scalar_one_or_none()

    encrypted_access = encrypt_token(request.access_token)
    encrypted_refresh = encrypt_token(request.refresh_token) if request.refresh_token else None

    if connection:
        connection.access_token_encrypted = encrypted_access
        connection.refresh_token_encrypted = encrypted_refresh
        connection.expires_at = _to_datetime(request.expires_at)
        connection.scope = request.scope
        connection.platform_user_id = channel_info.get("id")
        connection.platform_handle = channel_info.get("custom_url") or channel_info.get("title")
    else:
        connection = Connection(
            id=str(uuid.uuid4()),
            user_id=user.id,
            platform="youtube",
            platform_user_id=channel_info.get("id"),
            platform_handle=channel_info.get("custom_url") or channel_info.get("title"),
            access_token_encrypted=encrypted_access,
            refresh_token_encrypted=encrypted_refresh,
            expires_at=_to_datetime(request.expires_at),
            scope=request.scope,
        )
        db.add(connection)

    # 4. Upsert profile for channel identity.
    profile_result = await db.execute(
        select(Profile).where(
            Profile.user_id == user.id,
            Profile.platform == "youtube",
            Profile.external_id == channel_info.get("id", ""),
        )
    )
    profile = profile_result.scalar_one_or_none()

    if profile:
        profile.handle = channel_info.get("custom_url") or channel_info.get("title") or profile.handle
        profile.display_name = channel_info.get("title") or profile.display_name
        profile.profile_picture_url = channel_info.get("thumbnail_url") or profile.profile_picture_url
        profile.subscriber_count = str(channel_info.get("subscriber_count", 0))
    else:
        profile = Profile(
            id=str(uuid.uuid4()),
            user_id=user.id,
            platform="youtube",
            handle=channel_info.get("custom_url") or channel_info.get("title") or "youtube-channel",
            external_id=channel_info.get("id", ""),
            display_name=channel_info.get("title"),
            profile_picture_url=channel_info.get("thumbnail_url"),
            subscriber_count=str(channel_info.get("subscriber_count", 0)),
        )
        db.add(profile)

    await db.commit()
    await db.refresh(user)
    session = create_session_token(user.id, user.email)

    return SyncYouTubeSessionResponse(
        user_id=user.id,
        email=user.email,
        youtube_connected=True,
        session_token=session["token"],
        session_expires_at=session["expires_at"],
        channel_id=channel_info.get("id"),
        channel_title=channel_info.get("title"),
        channel_handle=channel_info.get("custom_url") or channel_info.get("title"),
        subscriber_count=str(channel_info.get("subscriber_count", 0)),
        thumbnail_url=channel_info.get("thumbnail_url"),
    )


@router.post("/sync/social", response_model=SyncSocialConnectionResponse)
async def sync_social_connection(
    request: SyncSocialConnectionRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Persist Instagram/TikTok connection metadata and issue backend session token.

    This supports manual parity workflows where OAuth provider integration is not available.
    """
    handle = str(request.handle or "").strip()
    if not handle:
        raise HTTPException(status_code=422, detail="handle is required")
    normalized_handle = handle if handle.startswith("@") else f"@{handle}"

    user: Optional[User] = None
    if request.user_id:
        user_result = await db.execute(select(User).where(User.id == request.user_id))
        user = user_result.scalar_one_or_none()
    if not user:
        user_result = await db.execute(select(User).where(User.email == str(request.email)))
        user = user_result.scalar_one_or_none()

    if not user:
        user = User(
            id=request.user_id or str(uuid.uuid4()),
            email=str(request.email),
            name=request.name,
            picture=request.picture,
        )
        db.add(user)
        await db.flush()
    else:
        user.email = str(request.email)
        if request.name:
            user.name = request.name
        if request.picture:
            user.picture = request.picture

    connection_result = await db.execute(
        select(Connection).where(
            Connection.user_id == user.id,
            Connection.platform == request.platform,
        )
    )
    connection = connection_result.scalar_one_or_none()
    opaque_access_token = str(request.access_token or f"manual:{request.platform}:{normalized_handle}")
    encrypted_access = encrypt_token(opaque_access_token)
    encrypted_refresh = encrypt_token(request.refresh_token) if request.refresh_token else None
    platform_user_id = str(request.external_id or normalized_handle).strip()

    if connection:
        connection.platform_user_id = platform_user_id
        connection.platform_handle = normalized_handle
        connection.access_token_encrypted = encrypted_access
        connection.refresh_token_encrypted = encrypted_refresh
        connection.expires_at = _to_datetime(request.expires_at)
        connection.scope = request.scope
    else:
        connection = Connection(
            id=str(uuid.uuid4()),
            user_id=user.id,
            platform=request.platform,
            platform_user_id=platform_user_id,
            platform_handle=normalized_handle,
            access_token_encrypted=encrypted_access,
            refresh_token_encrypted=encrypted_refresh,
            expires_at=_to_datetime(request.expires_at),
            scope=request.scope,
        )
        db.add(connection)

    profile_result = await db.execute(
        select(Profile).where(
            Profile.user_id == user.id,
            Profile.platform == request.platform,
            Profile.external_id == platform_user_id,
        )
    )
    profile = profile_result.scalar_one_or_none()
    display_name = str(request.display_name or normalized_handle).strip()
    subscriber_count = str(request.follower_count or "0")
    if profile:
        profile.handle = normalized_handle
        profile.display_name = display_name
        profile.profile_picture_url = request.profile_picture_url or profile.profile_picture_url
        profile.subscriber_count = subscriber_count
    else:
        profile = Profile(
            id=str(uuid.uuid4()),
            user_id=user.id,
            platform=request.platform,
            handle=normalized_handle,
            external_id=platform_user_id,
            display_name=display_name,
            profile_picture_url=request.profile_picture_url,
            subscriber_count=subscriber_count,
        )
        db.add(profile)

    await db.commit()
    await db.refresh(user)
    session = create_session_token(user.id, user.email)
    return SyncSocialConnectionResponse(
        user_id=user.id,
        email=user.email,
        platform=request.platform,
        connected=True,
        session_token=session["token"],
        session_expires_at=session["expires_at"],
        profile={
            "platform": request.platform,
            "external_id": platform_user_id,
            "handle": normalized_handle,
            "display_name": display_name,
            "subscriber_count": subscriber_count,
            "profile_picture_url": request.profile_picture_url,
        },
    )


@router.post("/logout")
async def logout(_auth: AuthContext = Depends(get_auth_context)):
    """Frontend-managed logout acknowledgment endpoint."""
    return {"message": "Logged out successfully"}
