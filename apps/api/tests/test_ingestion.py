import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

from main import app
from database import get_db
from ingestion.youtube import YouTubeClient
from services.session_token import create_session_token

# Mock settings to use SQLite for testing
import os
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"


TEST_USER_ID = "test-user"
TEST_AUTH_HEADER = {"Authorization": f"Bearer {create_session_token(TEST_USER_ID)['token']}"}


@pytest.fixture
def mock_youtube_client():
    with patch("routers.youtube._get_youtube_client") as mock_youtube, \
         patch("routers.competitor._get_youtube_client") as mock_competitor:
        client = MagicMock(spec=YouTubeClient)
        
        # Mock resolve_channel_identifier
        client.resolve_channel_identifier.side_effect = lambda url: "UC_MOCK_CHANNEL_ID" if "valid" in url else None
        
        # Mock get_channel_info
        client.get_channel_info.return_value = {
            "id": "UC_MOCK_CHANNEL_ID",
            "title": "Mock Channel",
            "description": "A mock channel for testing",
            "custom_url": "@mockchannel",
            "published_at": "2020-01-01T00:00:00Z",
            "thumbnail_url": "http://example.com/thumb.jpg",
            "subscriber_count": 1000,
            "video_count": 50,
            "view_count": 100000,
            "uploads_playlist_id": "UU_MOCK_PLAYLIST_ID"
        }
        
        # Mock get_channel_videos
        client.get_channel_videos.return_value = [
            {
                "id": "video1",
                "title": "Test Video 1",
                "description": "Description 1",
                "published_at": "2023-01-01T00:00:00Z",
                "thumbnail_url": "http://example.com/v1.jpg",
                "channel_id": "UC_MOCK_CHANNEL_ID"
            },
            {
                "id": "video2",
                "title": "Test Video 2",
                "description": "Description 2",
                "published_at": "2023-01-02T00:00:00Z",
                "thumbnail_url": "http://example.com/v2.jpg",
                "channel_id": "UC_MOCK_CHANNEL_ID"
            }
        ]
        
        # Mock get_video_details
        client.get_video_details.return_value = {
            "video1": {
                "view_count": 100,
                "like_count": 10,
                "comment_count": 5,
                "duration": "PT1M",
                "duration_seconds": 60
            },
            "video2": {
                "view_count": 200,
                "like_count": 20,
                "comment_count": 10,
                "duration": "PT2M",
                "duration_seconds": 120
            }
        }

        # Mock search_channels for recommendation endpoint
        client.search_channels.return_value = [
            {
                "id": "UC_EXISTING_CHANNEL",
                "title": "Existing Tracked Channel",
                "custom_url": "@existing",
                "thumbnail_url": "http://example.com/existing.jpg",
                "subscriber_count": 500000,
                "video_count": 250,
                "view_count": 50000000,
            },
            {
                "id": "UC_SUGGESTED_CHANNEL",
                "title": "Suggested Channel",
                "custom_url": "@suggested",
                "thumbnail_url": "http://example.com/suggested.jpg",
                "subscriber_count": 250000,
                "video_count": 180,
                "view_count": 18000000,
            },
        ]
        
        mock_youtube.return_value = client
        mock_competitor.return_value = client
        yield client


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_resolve_channel(client, mock_youtube_client):
    """Test resolving a channel URL."""
    response = await client.post("/youtube/resolve", json={"url": "http://youtube.com/valid"})
    assert response.status_code == 200
    data = response.json()
    assert data["channel_id"] == "UC_MOCK_CHANNEL_ID"
    assert data["title"] == "Mock Channel"


@pytest.mark.asyncio
async def test_add_competitor(client, mock_youtube_client):
    """Test adding a competitor."""
    class _Result:
        def __init__(self, value):
            self._value = value

        def scalar_one_or_none(self):
            return self._value

    mock_db = MagicMock()
    mock_db.execute = AsyncMock(side_effect=[
        _Result(None),      # user lookup (first request)
        _Result(None),      # competitor duplicate check (first request)
        _Result(object()),  # user lookup (second request)
        _Result(object()),  # competitor duplicate check (second request)
    ])
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        response = await client.post(
            "/competitors/",
            json={"channel_url": "http://youtube.com/valid", "user_id": "test-user"},
            headers=TEST_AUTH_HEADER,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["channel_id"] == "UC_MOCK_CHANNEL_ID"
        assert data["title"] == "Mock Channel"

        # Duplicate competitor should be rejected.
        response = await client.post(
            "/competitors/",
            json={"channel_url": "http://youtube.com/valid", "user_id": "test-user"},
            headers=TEST_AUTH_HEADER,
        )
        assert response.status_code == 400
        assert "already added" in response.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_get_channel_videos(client, mock_youtube_client):
    """Test fetching videos."""
    response = await client.get("/youtube/channel/UC_MOCK_CHANNEL_ID/videos")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["title"] == "Test Video 1"
    assert data[0]["view_count"] == 100


@pytest.mark.asyncio
async def test_recommend_competitors(client, mock_youtube_client):
    """Test recommending competitors from niche search."""
    class _Scalars:
        def __init__(self, values):
            self._values = values

        def all(self):
            return self._values

    class _Result:
        def __init__(self, scalar_value=None, scalar_values=None):
            self._scalar_value = scalar_value
            self._scalar_values = scalar_values or []

        def scalar_one_or_none(self):
            return self._scalar_value

        def scalars(self):
            return _Scalars(self._scalar_values)

    mock_db = MagicMock()
    mock_db.execute = AsyncMock(return_value=_Result(scalar_values=["UC_EXISTING_CHANNEL"]))

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        response = await client.post(
            "/competitors/recommend",
            json={
                "niche": "AI News",
                "user_id": "test-user",
                "limit": 1,
                "page": 1,
                "sort_by": "avg_views_per_video",
                "sort_direction": "asc",
            },
            headers=TEST_AUTH_HEADER,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["niche"] == "AI News"
        assert data["page"] == 1
        assert data["limit"] == 1
        assert data["total_count"] == 2
        assert data["has_more"] is True
        assert len(data["recommendations"]) == 1
        assert data["recommendations"][0]["channel_id"] == "UC_SUGGESTED_CHANNEL"
        assert data["recommendations"][0]["already_tracked"] is False

        response = await client.post(
            "/competitors/recommend",
            json={
                "niche": "AI News",
                "user_id": "test-user",
                "limit": 1,
                "page": 2,
                "sort_by": "avg_views_per_video",
                "sort_direction": "asc",
            },
            headers=TEST_AUTH_HEADER,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 2
        assert data["limit"] == 1
        assert data["total_count"] == 2
        assert data["has_more"] is False
        assert len(data["recommendations"]) == 1
        assert data["recommendations"][0]["channel_id"] == "UC_EXISTING_CHANNEL"
        assert data["recommendations"][0]["already_tracked"] is True
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_remove_competitor_requires_user_scope(client):
    """Delete competitor endpoint requires auth token."""
    response = await client.delete("/competitors/comp-123")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_remove_competitor_with_user_scope(client):
    """Delete competitor removes only when scoped by user_id."""

    class _Result:
        def __init__(self, value):
            self._value = value

        def scalar_one_or_none(self):
            return self._value

    competitor = MagicMock()
    mock_db = MagicMock()
    mock_db.execute = AsyncMock(return_value=_Result(competitor))
    mock_db.delete = AsyncMock()
    mock_db.commit = AsyncMock()

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        response = await client.delete(
            "/competitors/comp-123?user_id=test-user",
            headers=TEST_AUTH_HEADER,
        )
        assert response.status_code == 200
        assert response.json()["message"] == "Competitor removed"
        mock_db.delete.assert_awaited_once_with(competitor)
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_remove_competitor_rejects_cross_user_scope(client):
    """Delete competitor rejects mismatched query user_id."""
    response = await client.delete(
        "/competitors/comp-123?user_id=other-user",
        headers=TEST_AUTH_HEADER,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_competitor_videos_requires_user_scope(client):
    """Competitor videos endpoint requires auth token."""
    response = await client.get("/competitors/comp-123/videos")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_competitor_videos_with_user_scope(client, mock_youtube_client):
    """Competitor videos endpoint returns videos when scoped by user_id."""

    class _Result:
        def __init__(self, value):
            self._value = value

        def scalar_one_or_none(self):
            return self._value

    competitor = MagicMock()
    competitor.external_id = "UC_MOCK_CHANNEL_ID"

    mock_db = MagicMock()
    mock_db.execute = AsyncMock(return_value=_Result(competitor))

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        response = await client.get(
            "/competitors/comp-123/videos?user_id=test-user&limit=2",
            headers=TEST_AUTH_HEADER,
        )
        assert response.status_code == 200
        videos = response.json()
        assert len(videos) == 2
        assert videos[0]["video_id"] == "video1"
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_get_competitor_videos_rejects_cross_user_scope(client):
    """Competitor videos endpoint rejects mismatched query user_id."""
    response = await client.get(
        "/competitors/comp-123/videos?user_id=other-user",
        headers=TEST_AUTH_HEADER,
    )
    assert response.status_code == 403
