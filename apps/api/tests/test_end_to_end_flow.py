import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import select
from unittest.mock import MagicMock, patch

from main import app
from database import Base, get_db
from models.audit import Audit


@pytest_asyncio.fixture
async def integration_client(tmp_path):
    db_path = tmp_path / "integration.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def override_get_db():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, session_maker

    app.dependency_overrides.pop(get_db, None)
    await engine.dispose()


def _build_mock_youtube_client():
    client = MagicMock()

    client.get_my_channel_info.return_value = {
        "id": "UC_OWNER_CHANNEL",
        "title": "Owner Channel",
        "custom_url": "@owner",
        "thumbnail_url": "https://yt3.ggpht.com/owner.jpg",
        "subscriber_count": 12345,
    }

    def _resolve(identifier: str):
        if "competitor" in identifier:
            return "UC_COMPETITOR"
        return "UC_OWNER_CHANNEL"

    client.resolve_channel_identifier.side_effect = _resolve

    def _channel_info(channel_id: str):
        if channel_id == "UC_COMPETITOR":
            return {
                "id": "UC_COMPETITOR",
                "title": "Competitor Channel",
                "custom_url": "@competitor",
                "thumbnail_url": "https://yt3.ggpht.com/competitor.jpg",
                "subscriber_count": 54321,
                "video_count": 200,
                "view_count": 999999,
            }
        return {
            "id": "UC_OWNER_CHANNEL",
            "title": "Owner Channel",
            "custom_url": "@owner",
            "thumbnail_url": "https://yt3.ggpht.com/owner.jpg",
            "subscriber_count": 12345,
            "video_count": 100,
            "view_count": 500000,
        }

    client.get_channel_info.side_effect = _channel_info

    def _videos(channel_id: str, max_results: int = 10):
        return [
            {
                "id": f"{channel_id}_v1",
                "title": f"{channel_id} video one",
                "description": "desc",
                "published_at": "2026-01-01T00:00:00Z",
                "thumbnail_url": "https://i.ytimg.com/vi/sample/hqdefault.jpg",
            },
            {
                "id": f"{channel_id}_v2",
                "title": f"{channel_id} video two",
                "description": "desc",
                "published_at": "2026-01-03T00:00:00Z",
                "thumbnail_url": "https://i.ytimg.com/vi/sample2/hqdefault.jpg",
            },
        ][:max_results]

    client.get_channel_videos.side_effect = _videos

    def _details(video_ids):
        return {
            vid: {
                "view_count": 1000 + idx * 100,
                "like_count": 100 + idx * 10,
                "comment_count": 10 + idx,
                "duration_seconds": 120,
            }
            for idx, vid in enumerate(video_ids)
        }

    client.get_video_details.side_effect = _details
    return client


@pytest.mark.asyncio
async def test_connect_competitor_diagnose_blueprint_report(integration_client):
    client, session_maker = integration_client
    mock_youtube = _build_mock_youtube_client()

    with patch("routers.youtube._get_youtube_client", return_value=mock_youtube), \
         patch("routers.competitor._get_youtube_client", return_value=mock_youtube), \
         patch("routers.analysis._get_youtube_client", return_value=mock_youtube), \
         patch("services.blueprint._get_youtube_client", return_value=mock_youtube), \
         patch("routers.auth.create_youtube_client_with_oauth", return_value=mock_youtube):

        # 1) Connect / sync OAuth session into backend.
        sync_resp = await client.post(
            "/auth/sync/youtube",
            json={
                "access_token": "fake_access_token",
                "refresh_token": "fake_refresh_token",
                "expires_at": 1790000000,
                "email": "owner@example.com",
                "name": "Owner",
            },
        )
        assert sync_resp.status_code == 200
        sync_data = sync_resp.json()
        user_id = sync_data["user_id"]
        channel_id = sync_data["channel_id"]

        # 2) Add competitor.
        comp_resp = await client.post(
            "/competitors/",
            json={"channel_url": "https://youtube.com/@competitor", "user_id": user_id},
        )
        assert comp_resp.status_code == 200

        # 3) Run diagnosis.
        diagnosis_resp = await client.get(f"/analysis/diagnose/channel/{channel_id}")
        assert diagnosis_resp.status_code == 200
        diagnosis = diagnosis_resp.json()
        assert diagnosis["analyzed_video_count"] > 0
        assert diagnosis["primary_issue"] in {"PACKAGING", "RETENTION", "TOPIC_FIT", "CONSISTENCY", "UNDEFINED"}

        # 4) Seed a completed audit so consolidated report has all sections.
        async with session_maker() as db:
            audit = Audit(
                id="audit-e2e-1",
                user_id=user_id,
                status="completed",
                progress="100",
                output_json={
                    "diagnosis": diagnosis,
                    "video_analysis": {
                        "overall_score": 76,
                        "summary": "Video pacing is decent with room for stronger opening contrast.",
                        "sections": [{"name": "Intro", "score": 7, "feedback": ["Tighten first 5 seconds."]}],
                    },
                },
            )
            db.add(audit)
            await db.commit()

        # 5) Fetch consolidated report.
        report_resp = await client.get(f"/report/latest?user_id={user_id}")
        assert report_resp.status_code == 200
        report = report_resp.json()
        assert report["overall_score"] > 0
        assert isinstance(report["recommendations"], list)
        assert len(report["recommendations"]) > 0
        assert "blueprint" in report
