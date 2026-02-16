import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from database import Base
from models.competitor import Competitor
from models.user import User
from services.blueprint import generate_blueprint_service


@pytest_asyncio.fixture
async def blueprint_db(tmp_path):
    db_path = tmp_path / "blueprint.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_maker() as session:
        user = User(id="user-blueprint", email="user-blueprint@local.invalid")
        session.add(user)
        session.add(
            Competitor(
                id="comp-1",
                user_id="user-blueprint",
                platform="youtube",
                handle="@comp",
                external_id="UC_COMP_1",
                display_name="Comp One",
            )
        )
        await session.commit()
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_generate_blueprint_includes_velocity_framework_and_repurpose(blueprint_db, monkeypatch):
    class MockClient:
        def __init__(self):
            self.max_results_args = []

        def get_channel_videos(self, channel_id, max_results=20):
            self.max_results_args.append(max_results)
            return [
                {
                    "id": "v1",
                    "title": "I grew 400k followers in 2 years",
                    "description": "Today I show the 3 steps and proof screenshots.",
                    "published_at": "2025-12-01T00:00:00Z",
                },
                {
                    "id": "v2",
                    "title": "Why your reels stop getting views",
                    "description": "By the end, you will have a framework you can repeat.",
                    "published_at": "2026-01-10T00:00:00Z",
                },
            ]

        def get_video_details(self, video_ids):
            return {
                "v1": {
                    "view_count": 350000,
                    "like_count": 18000,
                    "comment_count": 1200,
                    "duration_seconds": 46,
                },
                "v2": {
                    "view_count": 190000,
                    "like_count": 9200,
                    "comment_count": 740,
                    "duration_seconds": 420,
                },
            }

        def get_video_captions(self, video_id):
            return (
                "I tested this for 30 days. Here is the proof. "
                "Step one is packaging, step two is hook pacing, step three is CTA."
            )

    mock_client = MockClient()
    monkeypatch.setattr("services.blueprint._get_youtube_client", lambda: mock_client)

    blueprint = await generate_blueprint_service("user-blueprint", blueprint_db)

    assert any(arg == 50 for arg in mock_client.max_results_args)
    assert "winner_pattern_signals" in blueprint
    assert "framework_playbook" in blueprint
    assert "repurpose_plan" in blueprint
    assert blueprint["winner_pattern_signals"]["sample_size"] > 0
    assert isinstance(blueprint["winner_pattern_signals"]["top_topics_by_velocity"], list)
    assert isinstance(blueprint["framework_playbook"]["stage_adoption"], dict)
    assert "youtube_shorts" in blueprint["repurpose_plan"]
    assert "transcript_quality" in blueprint
    assert blueprint["transcript_quality"]["sample_size"] > 0
    assert isinstance(blueprint["transcript_quality"]["by_source"], dict)
    assert "velocity_actions" in blueprint
    assert isinstance(blueprint["velocity_actions"], list)
    assert len(blueprint["velocity_actions"]) > 0
