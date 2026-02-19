import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from database import Base, get_db
from main import app
from models.research_item import ResearchItem
from models.user import User
from services.session_token import create_session_token


PARITY_USER_ID = "parity-user"
PARITY_AUTH_HEADER = {"Authorization": f"Bearer {create_session_token(PARITY_USER_ID, 'parity@example.com')['token']}"}


@pytest_asyncio.fixture
async def parity_client(tmp_path):
    db_path = tmp_path / "parity_hardening.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_maker() as session:
        session.add(User(id=PARITY_USER_ID, email="parity@example.com"))
        await session.commit()

    async def override_get_db():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, session_maker

    app.dependency_overrides.pop(get_db, None)
    await engine.dispose()


@pytest.mark.asyncio
async def test_auth_me_exposes_connector_capabilities(parity_client):
    client, _ = parity_client
    response = await client.get("/auth/me", headers=PARITY_AUTH_HEADER)
    assert response.status_code == 200
    payload = response.json()
    capabilities = payload.get("connector_capabilities")
    assert isinstance(capabilities, dict)
    assert "instagram_oauth_available" in capabilities
    assert "tiktok_oauth_available" in capabilities
    assert isinstance(capabilities["instagram_oauth_available"], bool)
    assert isinstance(capabilities["tiktok_oauth_available"], bool)


@pytest.mark.asyncio
async def test_connect_platform_start_returns_deterministic_fallback_when_disabled(parity_client):
    client, _ = parity_client
    response = await client.post("/auth/connect/instagram/start", headers=PARITY_AUTH_HEADER)
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["platform"] == "instagram"
    assert detail["manual_sync_endpoint"] == "/auth/sync/social"
    assert "OAuth connector is not configured" in detail["message"]


@pytest.mark.asyncio
async def test_competitor_discover_dedupes_identity_for_instagram(parity_client):
    client, session_maker = parity_client

    async with session_maker() as session:
        session.add_all(
            [
                ResearchItem(
                    id="ri-1",
                    user_id=PARITY_USER_ID,
                    platform="instagram",
                    source_type="capture",
                    creator_handle="@AI_NewsLab",
                    creator_display_name="AI News Lab",
                    title="AI News recap",
                    caption="AI News weekly recap and hooks",
                    external_id="ig-1",
                    metrics_json={"views": 90000, "likes": 4400, "comments": 210, "shares": 180, "saves": 120},
                    media_meta_json={"creator_id": "creator_abc"},
                ),
                ResearchItem(
                    id="ri-2",
                    user_id=PARITY_USER_ID,
                    platform="instagram",
                    source_type="capture",
                    creator_handle="ainewslab",
                    creator_display_name="AI News Lab",
                    title="AI News hook test",
                    caption="AI News hook formulas",
                    external_id="ig-2",
                    metrics_json={"views": 120000, "likes": 5100, "comments": 260, "shares": 230, "saves": 160},
                    media_meta_json={"creator_id": "creator_abc"},
                ),
            ]
        )
        await session.commit()

    response = await client.post(
        "/competitors/discover",
        json={
            "platform": "instagram",
            "query": "ai news",
            "page": 1,
            "limit": 20,
            "user_id": PARITY_USER_ID,
        },
        headers=PARITY_AUTH_HEADER,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["platform"] == "instagram"
    assert payload["total_count"] == 1
    candidate = payload["candidates"][0]
    assert candidate["display_name"] == "AI News Lab"
    assert candidate["handle"].startswith("@")
    assert candidate["quality_score"] > 0

    repeat = await client.post(
        "/competitors/discover",
        json={
            "platform": "instagram",
            "query": "ai news",
            "page": 1,
            "limit": 20,
            "user_id": PARITY_USER_ID,
        },
        headers=PARITY_AUTH_HEADER,
    )
    assert repeat.status_code == 200
    assert repeat.json()["candidates"][0]["external_id"] == candidate["external_id"]

