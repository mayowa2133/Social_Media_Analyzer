import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from unittest.mock import MagicMock, patch
from main import app
from ingestion.youtube import YouTubeClient

@pytest.fixture
def mock_youtube_client_analysis():
    with patch("routers.analysis._get_youtube_client") as mock:
        client = MagicMock(spec=YouTubeClient)
        
        # Mock get_channel_info
        client.get_channel_info.return_value = {
            "id": "UC_MOCK_CHANNEL_ID",
            "title": "Mock Channel"
        }
        
        client.get_channel_videos.return_value = [
            {
                "id": "video1",
                "title": "Test Video 1",
                "published_at": "2023-01-01T00:00:00Z", 
                "view_count": 100
            },
            {
                "id": "video2",
                "title": "Test Video 2",
                "published_at": "2023-01-02T00:00:00Z",
                "view_count": 100
            },
            {
                "id": "video3",
                "title": "Test Video 3",
                "published_at": "2023-01-03T00:00:00Z",
                "view_count": 100
            },
            {
                "id": "video4",
                "title": "Test Video 4",
                "published_at": "2023-01-04T00:00:00Z",
                "view_count": 120
            }
        ]
        
        # Mock get_video_details
        client.get_video_details.return_value = {
            "video1": {"view_count": 100, "like_count": 10, "comment_count": 5, "duration_seconds": 60},
            "video2": {"view_count": 100, "like_count": 10, "comment_count": 5, "duration_seconds": 60},
            "video3": {"view_count": 100, "like_count": 10, "comment_count": 5, "duration_seconds": 60},
            "video4": {"view_count": 120, "like_count": 12, "comment_count": 6, "duration_seconds": 60}
        }
        
        mock.return_value = client
        yield client

@pytest.mark.asyncio
async def test_full_diagnosis_flow(mock_youtube_client_analysis):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/analysis/diagnose/channel/UC_MOCK_CHANNEL_ID")
        
    assert response.status_code == 200
    data = response.json()
    
    assert data["channel_id"] == "UC_MOCK_CHANNEL_ID"
    # Should be PACKAGING because max(200) < 1.5 * median(150)
    assert data["primary_issue"] == "PACKAGING" 
    assert len(data["evidence"]) > 0
    assert len(data["recommendations"]) > 0
