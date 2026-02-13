import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

from main import app
from database import get_db
from ingestion.youtube import YouTubeClient

# Mock settings to use SQLite for testing
import os
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"


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
        response = await client.post("/competitors/", json={"channel_url": "http://youtube.com/valid"})
        assert response.status_code == 200
        data = response.json()
        assert data["channel_id"] == "UC_MOCK_CHANNEL_ID"
        assert data["title"] == "Mock Channel"

        # Duplicate competitor should be rejected.
        response = await client.post("/competitors/", json={"channel_url": "http://youtube.com/valid"})
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
