import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import select

from main import app
from database import Base, get_db
from models.video_metrics import VideoMetrics
from services.session_token import create_session_token


INGEST_USER_ID = "user-ingest"
INGEST_AUTH_HEADER = {"Authorization": f"Bearer {create_session_token(INGEST_USER_ID)['token']}"}


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
            "user_id": INGEST_USER_ID,
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
        headers=INGEST_AUTH_HEADER,
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


@pytest.mark.asyncio
async def test_ingest_platform_metrics_csv_bulk_upload(ingest_client):
    client, session_maker = ingest_client
    csv_payload = """video_external_id,video_url,title,views,likes,comments,shares,saves,avg_view_duration_s,ctr,retention_points_json
abc123,https://www.youtube.com/watch?v=abc123,Video A,150000,6200,410,280,760,28.4,0.067,"[{""time"":0,""retention"":100},{""time"":5,""retention"":82}]"
xyz789,https://www.youtube.com/watch?v=xyz789,Video B,98000,4100,290,190,520,22.1,0.054,"[{""time"":0,""retention"":100},{""time"":5,""retention"":74}]"
"""
    response = await client.post(
        "/analysis/ingest/platform_metrics_csv",
        params={"user_id": INGEST_USER_ID, "platform": "youtube"},
        files={"file": ("metrics.csv", csv_payload.encode("utf-8"), "text/csv")},
        headers=INGEST_AUTH_HEADER,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ingested"] is True
    assert payload["processed_rows"] == 2
    assert payload["successful_rows"] == 2
    assert payload["failed_rows"] == 0
    assert payload["normalized_fields"]["views"] == "mapped"
    assert payload["normalized_fields"]["likes"] == "mapped"
    assert payload["normalized_fields"]["comments"] == "mapped"
    assert payload["normalized_fields"]["shares"] == "mapped"
    assert payload["normalized_fields"]["saves"] == "mapped"
    assert payload["normalized_fields"]["retention_points"] == "mapped"
    assert payload["normalized_fields"]["avg_view_duration_s"] == "mapped"
    assert payload["normalized_fields"]["ctr"] == "mapped"

    async with session_maker() as db:
        result = await db.execute(select(VideoMetrics))
        metrics = result.scalars().all()
        assert len(metrics) == 2
