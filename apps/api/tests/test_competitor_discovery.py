import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from database import Base
from models.competitor import Competitor
from models.research_item import ResearchItem
from models.user import User
from services.competitor_discovery import discover_competitors_service


DISCOVERY_USER_ID = "discovery-user"
DISCOVERY_OTHER_USER_ID = "discovery-other-user"


@pytest_asyncio.fixture
async def discovery_session(tmp_path):
    db_path = tmp_path / "competitor_discovery.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_maker() as session:
        session.add_all(
            [
                User(id=DISCOVERY_USER_ID, email="discovery-user@example.com"),
                User(id=DISCOVERY_OTHER_USER_ID, email="discovery-other@example.com"),
            ]
        )
        await session.commit()

    async with session_maker() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_discover_service_merges_research_and_community_sources(discovery_session):
    discovery_session.add_all(
        [
            ResearchItem(
                id="ri-fusion-1",
                user_id=DISCOVERY_USER_ID,
                platform="instagram",
                source_type="capture",
                creator_handle="@ai_newslab",
                creator_display_name="AI News Lab",
                title="AI News recap",
                caption="ai_newslab weekly recap",
                external_id="ai_newslab",
                metrics_json={"views": 150000, "likes": 6200, "comments": 330, "shares": 260, "saves": 190},
                media_meta_json={"creator_id": "ai_newslab"},
            ),
            Competitor(
                id="comp-community-fusion",
                user_id=DISCOVERY_OTHER_USER_ID,
                platform="instagram",
                handle="@ai_newslab",
                external_id="ai_newslab",
                display_name="AI News Lab",
                subscriber_count="54000",
            ),
            Competitor(
                id="comp-tracked-fusion",
                user_id=DISCOVERY_USER_ID,
                platform="instagram",
                handle="@ai_newslab",
                external_id="ai_newslab",
                display_name="AI News Lab",
                subscriber_count="32000",
            ),
        ]
    )
    await discovery_session.commit()

    payload = await discover_competitors_service(
        db=discovery_session,
        user_id=DISCOVERY_USER_ID,
        platform="instagram",
        query="ai_newslab",
        page=1,
        limit=20,
    )

    assert payload["platform"] == "instagram"
    assert payload["total_count"] >= 1
    candidate = payload["candidates"][0]
    assert candidate["external_id"] == "ai_newslab"
    assert candidate["already_tracked"] is True
    assert int(candidate.get("source_count", 0)) >= 2
    source_labels = set(candidate.get("source_labels") or [])
    assert "research_corpus" in source_labels
    assert "community_graph" in source_labels
    assert candidate.get("confidence_tier") in {"medium", "high"}
    assert isinstance(candidate.get("evidence"), list)
    assert len(candidate["evidence"]) >= 1


@pytest.mark.asyncio
async def test_discover_service_pagination_is_deterministic(discovery_session):
    discovery_session.add_all(
        [
            ResearchItem(
                id="ri-page-alpha",
                user_id=DISCOVERY_USER_ID,
                platform="instagram",
                source_type="capture",
                creator_handle="@alpha_creator",
                creator_display_name="Alpha Creator",
                title="hooks alpha",
                caption="hooks alpha format",
                external_id="ig-alpha",
                metrics_json={"views": 100000, "likes": 4000, "comments": 150, "shares": 100, "saves": 60},
                media_meta_json={"creator_id": "alpha_creator"},
            ),
            ResearchItem(
                id="ri-page-beta",
                user_id=DISCOVERY_USER_ID,
                platform="instagram",
                source_type="capture",
                creator_handle="@beta_creator",
                creator_display_name="Beta Creator",
                title="hooks beta",
                caption="hooks beta format",
                external_id="ig-beta",
                metrics_json={"views": 100000, "likes": 4000, "comments": 150, "shares": 100, "saves": 60},
                media_meta_json={"creator_id": "beta_creator"},
            ),
            ResearchItem(
                id="ri-page-gamma",
                user_id=DISCOVERY_USER_ID,
                platform="instagram",
                source_type="capture",
                creator_handle="@gamma_creator",
                creator_display_name="Gamma Creator",
                title="hooks gamma",
                caption="hooks gamma format",
                external_id="ig-gamma",
                metrics_json={"views": 100000, "likes": 4000, "comments": 150, "shares": 100, "saves": 60},
                media_meta_json={"creator_id": "gamma_creator"},
            ),
        ]
    )
    await discovery_session.commit()

    page_1 = await discover_competitors_service(
        db=discovery_session,
        user_id=DISCOVERY_USER_ID,
        platform="instagram",
        query="hooks",
        page=1,
        limit=1,
    )
    page_2 = await discover_competitors_service(
        db=discovery_session,
        user_id=DISCOVERY_USER_ID,
        platform="instagram",
        query="hooks",
        page=2,
        limit=1,
    )
    page_1_repeat = await discover_competitors_service(
        db=discovery_session,
        user_id=DISCOVERY_USER_ID,
        platform="instagram",
        query="hooks",
        page=1,
        limit=1,
    )

    assert page_1["total_count"] == 3
    assert page_1["has_more"] is True
    assert page_2["total_count"] == page_1["total_count"]
    first_id = page_1["candidates"][0]["external_id"]
    second_id = page_2["candidates"][0]["external_id"]
    assert first_id != second_id
    assert page_1_repeat["candidates"][0]["external_id"] == first_id
    assert page_1["candidates"][0]["display_name"] == "Alpha Creator"


@pytest.mark.asyncio
async def test_discover_service_requires_query_for_youtube(discovery_session):
    with pytest.raises(ValueError, match="query is required"):
        await discover_competitors_service(
            db=discovery_session,
            user_id=DISCOVERY_USER_ID,
            platform="youtube",
            query="",
            page=1,
            limit=10,
            youtube_client=None,
        )
