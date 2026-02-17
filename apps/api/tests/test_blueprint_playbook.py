import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from database import Base
from models.competitor import Competitor
from models.user import User
from services.blueprint import (
    generate_blueprint_service,
    generate_series_plan_service,
    generate_viral_script_service,
    get_competitor_series_service,
)


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
    assert "series_intelligence" in blueprint
    assert isinstance(blueprint["series_intelligence"], dict)
    assert "series" in blueprint["series_intelligence"]


@pytest.mark.asyncio
async def test_series_and_script_services_return_structured_outputs(blueprint_db, monkeypatch):
    class MockClient:
        def get_channel_videos(self, channel_id, max_results=20):
            return [
                {
                    "id": "s1",
                    "title": "AI News Breakdown Part 1",
                    "description": "Hooks and velocity analysis",
                    "published_at": "2026-01-10T00:00:00Z",
                },
                {
                    "id": "s2",
                    "title": "AI News Breakdown Part 2",
                    "description": "Retention fixes with proof",
                    "published_at": "2026-01-11T00:00:00Z",
                },
            ]

        def get_video_details(self, video_ids):
            return {
                "s1": {"view_count": 220000, "like_count": 12000, "comment_count": 800, "duration_seconds": 34},
                "s2": {"view_count": 250000, "like_count": 13000, "comment_count": 900, "duration_seconds": 32},
            }

        def get_video_captions(self, video_id):
            return "In this episode I share three AI news hooks and one CTA."

    monkeypatch.setattr("services.blueprint._get_youtube_client", lambda: MockClient())

    series = await get_competitor_series_service("user-blueprint", blueprint_db)
    assert "series" in series
    assert isinstance(series["series"], list)

    series_plan = await generate_series_plan_service(
        "user-blueprint",
        {
            "mode": "competitor_template",
            "niche": "AI News",
            "audience": "AI creators",
            "objective": "higher retention",
            "platform": "youtube_shorts",
            "episodes": 4,
            "template_series_key": "ai_news_breakdown",
        },
        blueprint_db,
    )
    assert series_plan["mode"] in {"scratch", "competitor_template"}
    assert series_plan["episodes_count"] == 4
    assert isinstance(series_plan["episodes"], list)
    assert len(series_plan["episodes"]) == 4

    script = await generate_viral_script_service(
        "user-blueprint",
        {
            "platform": "tiktok",
            "topic": "AI News hooks",
            "audience": "new creators",
            "objective": "more shares",
            "tone": "bold",
            "desired_duration_s": 30,
        },
        blueprint_db,
    )
    assert script["platform"] == "tiktok"
    assert script["duration_target_s"] == 30
    assert isinstance(script["script_sections"], list)
    assert len(script["script_sections"]) > 0
    assert "score_breakdown" in script
