import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from datetime import datetime, timezone

from database import Base, get_db
from main import app
from models.audit import Audit
from models.competitor import Competitor
from models.connection import Connection
from models.draft_snapshot import DraftSnapshot
from models.outcome_metric import OutcomeMetric
from models.research_item import ResearchItem
from models.script_variant import ScriptVariant
from models.user import User
from services.session_token import create_session_token


FLOW_USER_ID = "flow-user"
FLOW_AUTH_HEADER = {"Authorization": f"Bearer {create_session_token(FLOW_USER_ID, 'flow@example.com')['token']}"}


@pytest_asyncio.fixture
async def flow_client(tmp_path):
    db_path = tmp_path / "ux_flow_state.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_maker() as session:
        session.add(User(id=FLOW_USER_ID, email="flow@example.com"))
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
async def test_flow_state_empty_account_points_to_connect(flow_client):
    client, _ = flow_client

    response = await client.get("/ux/flow_state", headers=FLOW_AUTH_HEADER)
    assert response.status_code == 200
    payload = response.json()

    assert payload["connected_platforms"] == {
        "youtube": False,
        "instagram": False,
        "tiktok": False,
    }
    assert payload["next_best_action"] == "connect_platform"
    assert payload["next_best_href"] == "/connect"
    assert payload["completion_percent"] == 0


@pytest.mark.asyncio
async def test_flow_state_populated_account_points_to_post_outcome(flow_client):
    client, session_maker = flow_client

    async with session_maker() as session:
        session.add(
            Connection(
                id="conn-1",
                user_id=FLOW_USER_ID,
                platform="instagram",
                platform_user_id="ig-user-1",
                platform_handle="@flowcreator",
                access_token_encrypted="enc-token",
            )
        )
        session.add(
            Competitor(
                id="comp-1",
                user_id=FLOW_USER_ID,
                platform="instagram",
                handle="@competitor",
                external_id="ig-comp-1",
                display_name="Competitor 1",
            )
        )
        session.add(
            ResearchItem(
                id="ri-1",
                user_id=FLOW_USER_ID,
                platform="instagram",
                source_type="capture",
                title="Hook teardown",
                caption="High-performing hook sample",
            )
        )
        session.add(
            ScriptVariant(
                id="sv-1",
                user_id=FLOW_USER_ID,
                source_item_id="ri-1",
                platform="instagram",
                topic="Hook teardown",
                variants_json=[{"id": "v1"}],
            )
        )
        session.add(
            DraftSnapshot(
                id="ds-1",
                user_id=FLOW_USER_ID,
                platform="instagram",
                source_item_id="ri-1",
                script_text="Draft script",
                rescored_score=81,
            )
        )
        session.add(
            Audit(
                id="audit-1",
                user_id=FLOW_USER_ID,
                status="completed",
                progress="100",
                output_json={"ok": True},
            )
        )
        await session.commit()

    response = await client.get("/ux/flow_state", headers=FLOW_AUTH_HEADER)
    assert response.status_code == 200
    payload = response.json()

    assert payload["connected_platforms"]["instagram"] is True
    assert payload["has_competitors_by_platform"]["instagram"] is True
    assert payload["has_research_items_by_platform"]["instagram"] is True
    assert payload["has_script_variants"] is True
    assert payload["has_completed_audit"] is True
    assert payload["has_report"] is True
    assert payload["has_outcomes"] is False
    assert payload["next_best_action"] == "post_outcome"
    assert payload["next_best_href"] == "/report/latest"
    assert payload["preferred_platform"] == "instagram"
    assert payload["completion_percent"] > 70

    async with session_maker() as session:
        session.add(
            OutcomeMetric(
                id="outcome-1",
                user_id=FLOW_USER_ID,
                platform="instagram",
                video_external_id="vid-1",
                posted_at=datetime(2026, 2, 21, 0, 0, tzinfo=timezone.utc),
                actual_metrics_json={"views": 1000},
            )
        )
        await session.commit()

    final_response = await client.get("/ux/flow_state", headers=FLOW_AUTH_HEADER)
    assert final_response.status_code == 200
    final_payload = final_response.json()
    assert final_payload["has_outcomes"] is True
    assert final_payload["next_best_action"] == "optimize_loop"
    assert final_payload["next_best_href"] == "/research?mode=optimizer"
    assert final_payload["completion_percent"] == 100
