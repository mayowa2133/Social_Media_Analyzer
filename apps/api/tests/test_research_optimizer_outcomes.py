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


@pytest.mark.asyncio
async def test_research_collection_move_meta_and_filtered_search(integration_client):
    capture_resp = await integration_client.post(
        "/research/capture",
        json={
            "platform": "tiktok",
            "url": "https://www.tiktok.com/@growthlab/video/101",
            "external_id": "tt-101",
            "creator_handle": "@growthlab",
            "creator_display_name": "Growth Lab",
            "title": "AI News pacing teardown",
            "caption": "AI News pacing teardown with hook examples.",
            "views": 98000,
            "likes": 5400,
            "comments": 420,
            "shares": 390,
            "saves": 220,
            "user_id": TEST_USER_ID,
        },
        headers=TEST_AUTH_HEADER,
    )
    assert capture_resp.status_code == 200
    item_id = capture_resp.json()["item_id"]

    collection_resp = await integration_client.post(
        "/research/collections",
        json={
            "name": "TikTok Hooks",
            "platform": "tiktok",
            "description": "High-performing hook references",
            "user_id": TEST_USER_ID,
        },
        headers=TEST_AUTH_HEADER,
    )
    assert collection_resp.status_code == 200
    collection_id = collection_resp.json()["id"]

    move_resp = await integration_client.post(
        f"/research/items/{item_id}/move",
        json={"collection_id": collection_id, "user_id": TEST_USER_ID},
        headers=TEST_AUTH_HEADER,
    )
    assert move_resp.status_code == 200
    assert move_resp.json()["collection_id"] == collection_id

    meta_resp = await integration_client.post(
        f"/research/items/{item_id}/meta",
        json={"tags": ["ai", "hooks"], "pinned": True, "archived": True, "user_id": TEST_USER_ID},
        headers=TEST_AUTH_HEADER,
    )
    assert meta_resp.status_code == 200
    payload = meta_resp.json()
    assert payload["pinned"] is True
    assert payload["archived"] is True
    assert sorted(payload["tags"]) == ["ai", "hooks"]

    hidden_search_resp = await integration_client.post(
        "/research/search",
        json={
            "platform": "tiktok",
            "query": "AI News",
            "collection_id": collection_id,
            "include_archived": False,
            "pinned_only": True,
            "tags": ["ai"],
            "sort_by": "views",
            "sort_direction": "desc",
            "timeframe": "all",
            "page": 1,
            "limit": 20,
            "user_id": TEST_USER_ID,
        },
        headers=TEST_AUTH_HEADER,
    )
    assert hidden_search_resp.status_code == 200
    assert hidden_search_resp.json()["total_count"] == 0

    visible_search_resp = await integration_client.post(
        "/research/search",
        json={
            "platform": "tiktok",
            "query": "AI News",
            "collection_id": collection_id,
            "include_archived": True,
            "pinned_only": True,
            "tags": ["ai"],
            "sort_by": "views",
            "sort_direction": "desc",
            "timeframe": "all",
            "page": 1,
            "limit": 20,
            "user_id": TEST_USER_ID,
        },
        headers=TEST_AUTH_HEADER,
    )
    assert visible_search_resp.status_code == 200
    visible_payload = visible_search_resp.json()
    assert visible_payload["total_count"] >= 1
    assert visible_payload["items"][0]["item_id"] == item_id


@pytest.mark.asyncio
async def test_instagram_recommendations_and_manual_competitor_add(integration_client):
    for idx, handle in enumerate(["@aibreakdowns", "@growthinsights", "@aibreakdowns"], start=1):
        capture_resp = await integration_client.post(
            "/research/capture",
            json={
                "platform": "instagram",
                "url": f"https://www.instagram.com/reel/C{idx}12345/",
                "external_id": f"ig-{idx}",
                "creator_handle": handle,
                "creator_display_name": handle.replace("@", "").title(),
                "title": "AI News breakdown",
                "caption": "AI News growth strategy with hooks and pacing.",
                "views": 50000 * idx,
                "likes": 3000 * idx,
                "comments": 200 * idx,
                "shares": 150 * idx,
                "saves": 120 * idx,
                "user_id": TEST_USER_ID,
            },
            headers=TEST_AUTH_HEADER,
        )
        assert capture_resp.status_code == 200

    recommend_resp = await integration_client.post(
        "/competitors/recommend",
        json={
            "platform": "instagram",
            "niche": "AI News",
            "sort_by": "avg_views_per_video",
            "sort_direction": "desc",
            "limit": 5,
            "page": 1,
            "user_id": TEST_USER_ID,
        },
        headers=TEST_AUTH_HEADER,
    )
    assert recommend_resp.status_code == 200
    recommend_payload = recommend_resp.json()
    assert recommend_payload["total_count"] >= 1
    first = recommend_payload["recommendations"][0]
    assert first["avg_views_per_video"] > 0
    assert first["channel_id"]

    manual_resp = await integration_client.post(
        "/competitors/manual",
        json={
            "platform": "instagram",
            "handle": first["custom_url"] or first["channel_id"],
            "display_name": first["title"],
            "external_id": first["channel_id"],
            "subscriber_count": first["subscriber_count"],
            "user_id": TEST_USER_ID,
        },
        headers=TEST_AUTH_HEADER,
    )
    assert manual_resp.status_code == 200
    created = manual_resp.json()
    assert created["platform"] == "instagram"


@pytest.mark.asyncio
async def test_import_competitors_from_research_creates_ig_competitors(integration_client):
    seed_rows = [
        ("@aibreakdowns", "AI Breakdowns", 125000),
        ("@aibreakdowns", "AI Breakdowns", 98000),
        ("@growthinsights", "Growth Insights", 88000),
        ("@growthinsights", "Growth Insights", 76000),
    ]
    for idx, (handle, display_name, views) in enumerate(seed_rows, start=1):
        capture_resp = await integration_client.post(
            "/research/capture",
            json={
                "platform": "instagram",
                "url": f"https://www.instagram.com/reel/CIMPORT{idx}/",
                "external_id": f"ig-import-{idx}",
                "creator_handle": handle,
                "creator_display_name": display_name,
                "title": "AI News growth teardown",
                "caption": "AI News growth teardown with hooks and proof.",
                "views": views,
                "likes": int(views * 0.06),
                "comments": int(views * 0.004),
                "shares": int(views * 0.003),
                "saves": int(views * 0.002),
                "user_id": TEST_USER_ID,
            },
            headers=TEST_AUTH_HEADER,
        )
        assert capture_resp.status_code == 200

    import_resp = await integration_client.post(
        "/competitors/import_from_research",
        json={
            "platform": "instagram",
            "min_items_per_creator": 2,
            "top_n": 10,
            "user_id": TEST_USER_ID,
        },
        headers=TEST_AUTH_HEADER,
    )
    assert import_resp.status_code == 200
    payload = import_resp.json()
    assert payload["platform"] == "instagram"
    assert payload["imported_count"] >= 2
    assert payload["candidate_creators"] >= 2


@pytest.mark.asyncio
async def test_outcomes_recalibrate_endpoint(integration_client):
    ingest_resp = await integration_client.post(
        "/outcomes/ingest",
        json={
            "platform": "tiktok",
            "video_external_id": "tt-001",
            "actual_metrics": {"views": 5000, "likes": 400, "comments": 40, "shares": 30, "saves": 20},
            "posted_at": "2026-02-18T12:00:00Z",
            "predicted_score": 65,
            "user_id": TEST_USER_ID,
        },
        headers=TEST_AUTH_HEADER,
    )
    assert ingest_resp.status_code == 200

    recalibrate_resp = await integration_client.post(
        "/outcomes/recalibrate",
        headers=TEST_AUTH_HEADER,
    )
    assert recalibrate_resp.status_code == 200
    payload = recalibrate_resp.json()
    assert "refreshed" in payload
    assert "skipped" in payload
    assert "errors" in payload
