import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from database import Base, get_db
from main import app
from models.competitor import Competitor
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
    assert candidate["confidence_tier"] in {"low", "medium", "high"}
    assert isinstance(candidate.get("evidence"), list)
    assert len(candidate["evidence"]) >= 1
    assert int(candidate.get("source_count", 0)) >= 1
    assert isinstance(candidate.get("source_labels"), list)

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


@pytest.mark.asyncio
async def test_competitor_discover_manual_url_seed_for_tiktok(parity_client):
    client, _ = parity_client

    query = (
        "https://www.tiktok.com/@ai.daily.breakdown/video/7371111111111111111 "
        "https://www.tiktok.com/@ai.daily.breakdown/video/7372222222222222222"
    )
    response = await client.post(
        "/competitors/discover",
        json={
            "platform": "tiktok",
            "query": query,
            "page": 1,
            "limit": 20,
            "user_id": PARITY_USER_ID,
        },
        headers=PARITY_AUTH_HEADER,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["platform"] == "tiktok"
    assert payload["total_count"] >= 1
    candidate = payload["candidates"][0]
    assert candidate["source"] in {"manual_url_seed", "research_corpus", "official_api"}
    assert candidate["handle"].startswith("@")
    assert candidate["quality_score"] > 0

    repeat = await client.post(
        "/competitors/discover",
        json={
            "platform": "tiktok",
            "query": query,
            "page": 1,
            "limit": 20,
            "user_id": PARITY_USER_ID,
        },
        headers=PARITY_AUTH_HEADER,
    )
    assert repeat.status_code == 200
    assert repeat.json()["candidates"][0]["external_id"] == candidate["external_id"]


@pytest.mark.asyncio
async def test_competitor_discover_pagination_stable_order(parity_client):
    client, session_maker = parity_client

    async with session_maker() as session:
        session.add_all(
            [
                ResearchItem(
                    id="ri-page-1",
                    user_id=PARITY_USER_ID,
                    platform="instagram",
                    source_type="capture",
                    creator_handle="@growthalpha",
                    creator_display_name="Growth Alpha",
                    title="hooks 1",
                    caption="hooks alpha",
                    external_id="ig-page-1",
                    metrics_json={"views": 120000, "likes": 5100, "comments": 200, "shares": 180, "saves": 90},
                    media_meta_json={"creator_id": "creator_p1"},
                ),
                ResearchItem(
                    id="ri-page-2",
                    user_id=PARITY_USER_ID,
                    platform="instagram",
                    source_type="capture",
                    creator_handle="@growthbeta",
                    creator_display_name="Growth Beta",
                    title="hooks 2",
                    caption="hooks beta",
                    external_id="ig-page-2",
                    metrics_json={"views": 60000, "likes": 2200, "comments": 90, "shares": 80, "saves": 40},
                    media_meta_json={"creator_id": "creator_p2"},
                ),
            ]
        )
        await session.commit()

    page_1 = await client.post(
        "/competitors/discover",
        json={
            "platform": "instagram",
            "query": "hooks",
            "page": 1,
            "limit": 1,
            "user_id": PARITY_USER_ID,
        },
        headers=PARITY_AUTH_HEADER,
    )
    assert page_1.status_code == 200
    payload_1 = page_1.json()
    assert payload_1["total_count"] >= 2
    assert payload_1["has_more"] is True
    first_id = payload_1["candidates"][0]["external_id"]

    page_2 = await client.post(
        "/competitors/discover",
        json={
            "platform": "instagram",
            "query": "hooks",
            "page": 2,
            "limit": 1,
            "user_id": PARITY_USER_ID,
        },
        headers=PARITY_AUTH_HEADER,
    )
    assert page_2.status_code == 200
    payload_2 = page_2.json()
    assert payload_2["total_count"] == payload_1["total_count"]
    second_id = payload_2["candidates"][0]["external_id"]
    assert second_id != first_id

    repeat = await client.post(
        "/competitors/discover",
        json={
            "platform": "instagram",
            "query": "hooks",
            "page": 1,
            "limit": 1,
            "user_id": PARITY_USER_ID,
        },
        headers=PARITY_AUTH_HEADER,
    )
    assert repeat.status_code == 200
    assert repeat.json()["candidates"][0]["external_id"] == first_id


@pytest.mark.asyncio
async def test_competitor_discover_community_graph_source_for_tiktok(parity_client):
    client, session_maker = parity_client
    other_user_id = "parity-other-user"

    async with session_maker() as session:
        session.add(User(id=other_user_id, email="other@example.com"))
        session.add(
            Competitor(
                id="comp-community-1",
                user_id=other_user_id,
                platform="tiktok",
                handle="@aipatternlab",
                external_id="aipatternlab",
                display_name="AI Pattern Lab",
                subscriber_count="128900",
            )
        )
        await session.commit()

    response = await client.post(
        "/competitors/discover",
        json={
            "platform": "tiktok",
            "query": "pattern",
            "page": 1,
            "limit": 10,
            "user_id": PARITY_USER_ID,
        },
        headers=PARITY_AUTH_HEADER,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_count"] >= 1
    candidate = payload["candidates"][0]
    assert candidate["source"] in {"community_graph", "research_corpus", "manual_url_seed", "official_api"}
    assert candidate["confidence_tier"] in {"low", "medium", "high"}
    assert isinstance(candidate.get("evidence"), list)


@pytest.mark.asyncio
async def test_competitor_discover_merges_sources_and_marks_tracked(parity_client):
    client, session_maker = parity_client
    other_user_id = "parity-fusion-user"

    async with session_maker() as session:
        session.add(User(id=other_user_id, email="fusion@example.com"))
        session.add_all(
            [
                ResearchItem(
                    id="ri-fusion-ig",
                    user_id=PARITY_USER_ID,
                    platform="instagram",
                    source_type="capture",
                    creator_handle="@ai_newslab",
                    creator_display_name="AI News Lab",
                    title="AI hooks breakdown",
                    caption="ai_newslab retention test",
                    external_id="ai_newslab",
                    metrics_json={"views": 110000, "likes": 5200, "comments": 220, "shares": 180, "saves": 130},
                    media_meta_json={"creator_id": "ai_newslab"},
                ),
                Competitor(
                    id="comp-fusion-other",
                    user_id=other_user_id,
                    platform="instagram",
                    handle="@ai_newslab",
                    external_id="ai_newslab",
                    display_name="AI News Lab",
                    subscriber_count="49000",
                ),
                Competitor(
                    id="comp-fusion-tracked",
                    user_id=PARITY_USER_ID,
                    platform="instagram",
                    handle="@ai_newslab",
                    external_id="ai_newslab",
                    display_name="AI News Lab",
                    subscriber_count="33000",
                ),
            ]
        )
        await session.commit()

    response = await client.post(
        "/competitors/discover",
        json={
            "platform": "instagram",
            "query": "ai_newslab",
            "page": 1,
            "limit": 10,
            "user_id": PARITY_USER_ID,
        },
        headers=PARITY_AUTH_HEADER,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_count"] >= 1

    candidate = payload["candidates"][0]
    assert candidate["external_id"] == "ai_newslab"
    assert candidate["already_tracked"] is True
    assert int(candidate.get("source_count", 0)) >= 2
    source_labels = set(candidate.get("source_labels") or [])
    assert "research_corpus" in source_labels
    assert "community_graph" in source_labels
