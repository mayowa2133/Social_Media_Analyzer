import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from database import Base, get_db
from main import app
from services.session_token import create_session_token


TEST_USER_ID = "research-optimizer-user"
TEST_AUTH_HEADER = {"Authorization": f"Bearer {create_session_token(TEST_USER_ID)['token']}"}


@pytest_asyncio.fixture
async def integration_client(tmp_path):
    db_path = tmp_path / "research_optimizer.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def override_get_db():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    app.dependency_overrides.pop(get_db, None)
    await engine.dispose()


@pytest.mark.asyncio
async def test_research_import_and_search_with_credit_charge(integration_client):
    import_resp = await integration_client.post(
        "/research/import_url",
        json={
            "platform": "instagram",
            "url": "https://www.instagram.com/reel/C1234567890/",
            "user_id": TEST_USER_ID,
        },
        headers=TEST_AUTH_HEADER,
    )
    assert import_resp.status_code == 200
    imported = import_resp.json()
    assert imported["platform"] == "instagram"

    search_resp = await integration_client.post(
        "/research/search",
        json={
            "platform": "instagram",
            "query": "",
            "sort_by": "created_at",
            "sort_direction": "desc",
            "timeframe": "all",
            "page": 1,
            "limit": 20,
            "user_id": TEST_USER_ID,
        },
        headers=TEST_AUTH_HEADER,
    )
    assert search_resp.status_code == 200
    payload = search_resp.json()
    assert payload["total_count"] >= 1
    assert isinstance(payload["items"], list)
    assert payload["items"][0]["platform"] == "instagram"
    assert payload["credits"]["charged"] >= 0

    credits_resp = await integration_client.get(
        f"/billing/credits?user_id={TEST_USER_ID}",
        headers=TEST_AUTH_HEADER,
    )
    assert credits_resp.status_code == 200
    credits_payload = credits_resp.json()
    assert "balance" in credits_payload
    assert credits_payload["balance"] <= credits_payload["free_monthly_credits"]


@pytest.mark.asyncio
async def test_optimizer_variant_generation_and_rescore(integration_client):
    variants_resp = await integration_client.post(
        "/optimizer/variant_generate",
        json={
            "platform": "youtube",
            "topic": "AI News hooks",
            "audience": "creators",
            "objective": "higher retention",
            "tone": "bold",
            "duration_s": 40,
            "generation_mode": "ai_first_fallback",
            "constraints": {
                "platform": "youtube",
                "duration_s": 40,
                "tone": "bold",
            },
            "user_id": TEST_USER_ID,
        },
        headers=TEST_AUTH_HEADER,
    )
    assert variants_resp.status_code == 200
    variants_payload = variants_resp.json()
    assert variants_payload["generation"]["mode"] == "ai_first_fallback"
    assert "used_fallback" in variants_payload["generation"]
    assert len(variants_payload["variants"]) == 3
    assert all(isinstance(item.get("script_text"), str) and item["script_text"] for item in variants_payload["variants"])

    first_variant = variants_payload["variants"][0]
    rescore_resp = await integration_client.post(
        "/optimizer/rescore",
        json={
            "platform": "youtube",
            "script_text": first_variant["script_text"] + "\nComment your niche and follow for part two.",
            "duration_s": 40,
            "baseline_score": first_variant["score_breakdown"]["combined"],
            "baseline_detector_rankings": first_variant.get("detector_rankings", []),
            "user_id": TEST_USER_ID,
        },
        headers=TEST_AUTH_HEADER,
    )
    assert rescore_resp.status_code == 200
    rescore_payload = rescore_resp.json()
    assert "score_breakdown" in rescore_payload
    assert isinstance(rescore_payload.get("detector_rankings"), list)
    assert isinstance(rescore_payload.get("next_actions"), list)
    assert isinstance(rescore_payload.get("line_level_edits"), list)
    assert "improvement_diff" in rescore_payload

    snapshot_resp = await integration_client.post(
        "/optimizer/draft_snapshot",
        json={
            "platform": "youtube",
            "variant_id": first_variant["id"],
            "script_text": first_variant["script_text"],
            "baseline_score": first_variant["score_breakdown"]["combined"],
            "rescore_output": rescore_payload,
            "user_id": TEST_USER_ID,
        },
        headers=TEST_AUTH_HEADER,
    )
    assert snapshot_resp.status_code == 200
    snapshot_payload = snapshot_resp.json()
    assert snapshot_payload["id"]
    assert snapshot_payload["script_text"]
    assert isinstance(snapshot_payload.get("line_level_edits"), list)

    get_snapshot_resp = await integration_client.get(
        f"/optimizer/draft_snapshot/{snapshot_payload['id']}?user_id={TEST_USER_ID}",
        headers=TEST_AUTH_HEADER,
    )
    assert get_snapshot_resp.status_code == 200
    assert get_snapshot_resp.json()["id"] == snapshot_payload["id"]

    list_snapshot_resp = await integration_client.get(
        f"/optimizer/draft_snapshot?platform=youtube&user_id={TEST_USER_ID}",
        headers=TEST_AUTH_HEADER,
    )
    assert list_snapshot_resp.status_code == 200
    listed = list_snapshot_resp.json()
    assert listed["count"] >= 1
    assert isinstance(listed["items"], list)


@pytest.mark.asyncio
async def test_outcomes_ingest_and_summary(integration_client):
    ingest_resp = await integration_client.post(
        "/outcomes/ingest",
        json={
            "platform": "youtube",
            "video_external_id": "video-001",
            "actual_metrics": {
                "views": 12000,
                "likes": 800,
                "comments": 90,
                "shares": 45,
                "saves": 38,
                "avg_view_duration_s": 28,
            },
            "retention_points": [
                {"time": 3, "retention": 81},
                {"time": 20, "retention": 54},
            ],
            "posted_at": "2026-02-18T12:00:00Z",
            "predicted_score": 72,
            "user_id": TEST_USER_ID,
        },
        headers=TEST_AUTH_HEADER,
    )
    assert ingest_resp.status_code == 200
    ingest_payload = ingest_resp.json()
    assert "outcome_id" in ingest_payload
    assert "confidence_update" in ingest_payload

    summary_resp = await integration_client.get(
        f"/outcomes/summary?platform=youtube&user_id={TEST_USER_ID}",
        headers=TEST_AUTH_HEADER,
    )
    assert summary_resp.status_code == 200
    summary = summary_resp.json()
    assert summary["platform"] == "youtube"
    assert summary["sample_size"] >= 1
    assert "recommendations" in summary
