import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import select

from main import app
from database import Base, get_db
from models.video_metrics import VideoMetrics


@pytest_asyncio.fixture
async def ingest_client(tmp_path):
    db_path = tmp_path / "ingest.db"
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


@pytest.mark.asyncio
async def test_ingest_platform_metrics_persists_true_shares_saves_retention(ingest_client):
    client, session_maker = ingest_client

    response = await client.post(
        "/analysis/ingest/platform_metrics",
        json={
            "user_id": "user-ingest",
            "platform": "youtube",
            "video_external_id": "abc123",
            "video_url": "https://www.youtube.com/watch?v=abc123",
            "title": "Test video",
            "views": 120000,
            "likes": 5200,
            "comments": 420,
            "shares": 310,
            "saves": 780,
            "retention_points": [
                {"time": 0, "retention": 100},
                {"time": 3, "retention": 86},
                {"time": 30, "retention": 64},
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ingested"] is True
    assert payload["metric_coverage"]["shares"] == "true"
    assert payload["metric_coverage"]["saves"] == "true"
    assert payload["metric_coverage"]["retention_curve"] == "true"

    async with session_maker() as db:
        result = await db.execute(select(VideoMetrics))
        metrics = result.scalar_one()
        assert metrics.shares == 310
        assert metrics.saves == 780
        assert isinstance(metrics.retention_points_json, list)
        assert len(metrics.retention_points_json) == 3
