import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.future import select

from database import Base, get_db
from main import app
from models.audit import Audit
from models.feed_source_follow import FeedSourceFollow
from models.media_download_job import MediaDownloadJob
from models.research_item import ResearchItem
from models.upload import Upload
from services.feed_transcript import process_feed_transcript_job_async
from services.session_token import create_session_token


TEST_USER_ID = "feed-user"
TEST_AUTH_HEADER = {"Authorization": f"Bearer {create_session_token(TEST_USER_ID)['token']}"}


class _FakeQueueJob:
    def __init__(self, job_id: str):
        self.id = job_id


class _FakeAuditQueueJob:
    def __init__(self, audit_id: str):
        self.id = audit_id
        self.origin = "audit_jobs"


@pytest_asyncio.fixture
async def feed_client(tmp_path):
    db_path = tmp_path / "feed_discovery.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def override_get_db():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with patch("services.feed_transcript.async_session_maker", session_maker):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            setattr(client, "_session_maker", session_maker)
            yield client

    app.dependency_overrides.pop(get_db, None)
    await engine.dispose()


async def _capture_item(
    client: AsyncClient,
    *,
    platform: str,
    external_id: str,
    handle: str,
    title: str,
    caption: str,
    views: int,
    likes: int,
    comments: int,
    shares: int,
    saves: int,
    published_at: datetime,
    url: str | None = None,
    media_meta: dict | None = None,
):
    response = await client.post(
        "/research/capture",
        json={
            "platform": platform,
            "external_id": external_id,
            "creator_handle": handle,
            "creator_display_name": handle.strip("@").replace("_", " ").title(),
            "title": title,
            "caption": caption,
            "url": url,
            "media_meta": media_meta,
            "views": views,
            "likes": likes,
            "comments": comments,
            "shares": shares,
            "saves": saves,
            "published_at": published_at.isoformat(),
            "user_id": TEST_USER_ID,
        },
        headers=TEST_AUTH_HEADER,
    )
    assert response.status_code == 200
    return response.json()["item_id"]


@pytest.mark.asyncio
async def test_feed_discover_profile_mode_returns_ranked_items(feed_client):
    now = datetime.now(timezone.utc)
    await _capture_item(
        feed_client,
        platform="instagram",
        external_id="ig-profile-1",
        handle="@ai_news_lab",
        title="AI News hooks 1",
        caption="retention hooks",
        views=140000,
        likes=6800,
        comments=330,
        shares=920,
        saves=780,
        published_at=now - timedelta(hours=3),
    )
    await _capture_item(
        feed_client,
        platform="instagram",
        external_id="ig-profile-2",
        handle="@ai_news_lab",
        title="AI News hooks 2",
        caption="audience format test",
        views=62000,
        likes=2100,
        comments=140,
        shares=210,
        saves=160,
        published_at=now - timedelta(hours=12),
    )
    await _capture_item(
        feed_client,
        platform="instagram",
        external_id="ig-profile-3",
        handle="@other_handle",
        title="Other niche",
        caption="not matching",
        views=200000,
        likes=12000,
        comments=600,
        shares=1500,
        saves=1400,
        published_at=now - timedelta(hours=2),
    )

    response = await feed_client.post(
        "/feed/discover",
        json={
            "platform": "instagram",
            "mode": "profile",
            "query": "ai_news_lab",
            "timeframe": "7d",
            "sort_by": "trending_score",
            "sort_direction": "desc",
            "page": 1,
            "limit": 10,
            "user_id": TEST_USER_ID,
        },
        headers=TEST_AUTH_HEADER,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"]
    assert payload["ingestion_method"] == "research_corpus"
    assert payload["source_health"]["research_corpus"] == "healthy"
    assert payload["total_count"] == 2
    scores = [row["trending_score"] for row in payload["items"]]
    assert scores == sorted(scores, reverse=True)
    assert all("engagement_rate" in row for row in payload["items"])
    assert all("views_per_hour" in row for row in payload["items"])


@pytest.mark.asyncio
async def test_feed_discover_hashtag_respects_timeframe(feed_client):
    now = datetime.now(timezone.utc)
    recent_id = await _capture_item(
        feed_client,
        platform="instagram",
        external_id="ig-hash-1",
        handle="@trend_lab",
        title="Daily market recap",
        caption="Best recap #ainews #ai",
        views=38000,
        likes=1600,
        comments=80,
        shares=120,
        saves=90,
        published_at=now - timedelta(hours=5),
    )
    await _capture_item(
        feed_client,
        platform="instagram",
        external_id="ig-hash-2",
        handle="@trend_lab",
        title="Weekly market recap",
        caption="Best recap #ainews",
        views=120000,
        likes=5200,
        comments=260,
        shares=550,
        saves=430,
        published_at=now - timedelta(days=10),
    )

    response = await feed_client.post(
        "/feed/discover",
        json={
            "platform": "instagram",
            "mode": "hashtag",
            "query": "ainews",
            "timeframe": "24h",
            "sort_by": "trending_score",
            "sort_direction": "desc",
            "page": 1,
            "limit": 20,
            "user_id": TEST_USER_ID,
        },
        headers=TEST_AUTH_HEADER,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_count"] == 1
    assert payload["items"][0]["item_id"] == recent_id


@pytest.mark.asyncio
async def test_feed_search_views_per_hour_sort_and_pagination_is_deterministic(feed_client):
    now = datetime.now(timezone.utc)
    first_expected = await _capture_item(
        feed_client,
        platform="tiktok",
        external_id="tt-speed-1",
        handle="@growth_lab",
        title="Growth play 1",
        caption="growth acceleration",
        views=30000,
        likes=1200,
        comments=80,
        shares=140,
        saves=100,
        published_at=now - timedelta(hours=2),
    )  # 15k/hour
    second_expected = await _capture_item(
        feed_client,
        platform="tiktok",
        external_id="tt-speed-2",
        handle="@growth_lab",
        title="Growth play 2",
        caption="growth acceleration",
        views=100000,
        likes=3800,
        comments=220,
        shares=410,
        saves=300,
        published_at=now - timedelta(hours=10),
    )  # 10k/hour
    third_expected = await _capture_item(
        feed_client,
        platform="tiktok",
        external_id="tt-speed-3",
        handle="@growth_lab",
        title="Growth play 3",
        caption="growth acceleration",
        views=150000,
        likes=5000,
        comments=280,
        shares=520,
        saves=430,
        published_at=now - timedelta(hours=50),
    )  # 3k/hour

    page_1 = await feed_client.post(
        "/feed/search",
        json={
            "platform": "tiktok",
            "mode": "keyword",
            "query": "growth",
            "timeframe": "all",
            "sort_by": "views_per_hour",
            "sort_direction": "desc",
            "page": 1,
            "limit": 2,
            "user_id": TEST_USER_ID,
        },
        headers=TEST_AUTH_HEADER,
    )
    assert page_1.status_code == 200
    payload_1 = page_1.json()
    assert payload_1["total_count"] == 3
    assert payload_1["has_more"] is True
    assert payload_1["items"][0]["item_id"] == first_expected
    assert payload_1["items"][1]["item_id"] == second_expected

    page_2 = await feed_client.post(
        "/feed/search",
        json={
            "platform": "tiktok",
            "mode": "keyword",
            "query": "growth",
            "timeframe": "all",
            "sort_by": "views_per_hour",
            "sort_direction": "desc",
            "page": 2,
            "limit": 2,
            "user_id": TEST_USER_ID,
        },
        headers=TEST_AUTH_HEADER,
    )
    assert page_2.status_code == 200
    payload_2 = page_2.json()
    assert payload_2["has_more"] is False
    assert payload_2["items"][0]["item_id"] == third_expected

    repeat_page_1 = await feed_client.post(
        "/feed/search",
        json={
            "platform": "tiktok",
            "mode": "keyword",
            "query": "growth",
            "timeframe": "all",
            "sort_by": "views_per_hour",
            "sort_direction": "desc",
            "page": 1,
            "limit": 2,
            "user_id": TEST_USER_ID,
        },
        headers=TEST_AUTH_HEADER,
    )
    assert repeat_page_1.status_code == 200
    assert repeat_page_1.json()["items"][0]["item_id"] == first_expected


@pytest.mark.asyncio
async def test_feed_favorite_toggle_persists_on_research_item(feed_client):
    now = datetime.now(timezone.utc)
    item_id = await _capture_item(
        feed_client,
        platform="instagram",
        external_id="ig-fav-1",
        handle="@favorites_lab",
        title="Favorite me",
        caption="favorite toggle validation",
        views=18000,
        likes=900,
        comments=60,
        shares=90,
        saves=70,
        published_at=now - timedelta(hours=6),
    )

    mark_response = await feed_client.post(
        "/feed/favorites/toggle",
        json={"item_id": item_id, "favorite": True, "user_id": TEST_USER_ID},
        headers=TEST_AUTH_HEADER,
    )
    assert mark_response.status_code == 200
    assert mark_response.json() == {"item_id": item_id, "favorite": True}

    item_response = await feed_client.get(
        f"/research/items/{item_id}",
        params={"user_id": TEST_USER_ID},
        headers=TEST_AUTH_HEADER,
    )
    assert item_response.status_code == 200
    assert item_response.json()["media_meta"].get("favorite") is True

    clear_response = await feed_client.post(
        "/feed/favorites/toggle",
        json={"item_id": item_id, "favorite": False, "user_id": TEST_USER_ID},
        headers=TEST_AUTH_HEADER,
    )
    assert clear_response.status_code == 200
    assert clear_response.json() == {"item_id": item_id, "favorite": False}

    item_after_clear = await feed_client.get(
        f"/research/items/{item_id}",
        params={"user_id": TEST_USER_ID},
        headers=TEST_AUTH_HEADER,
    )
    assert item_after_clear.status_code == 200
    assert item_after_clear.json()["media_meta"].get("favorite") is False


@pytest.mark.asyncio
async def test_feed_assign_collection_bulk_assigns_and_reports_missing_items(feed_client):
    now = datetime.now(timezone.utc)
    first_item = await _capture_item(
        feed_client,
        platform="tiktok",
        external_id="tt-assign-1",
        handle="@collection_lab",
        title="Collection target 1",
        caption="collection move candidate",
        views=24000,
        likes=1300,
        comments=70,
        shares=120,
        saves=95,
        published_at=now - timedelta(hours=4),
    )
    second_item = await _capture_item(
        feed_client,
        platform="tiktok",
        external_id="tt-assign-2",
        handle="@collection_lab",
        title="Collection target 2",
        caption="collection move candidate",
        views=29000,
        likes=1500,
        comments=95,
        shares=140,
        saves=110,
        published_at=now - timedelta(hours=3),
    )

    collection_response = await feed_client.post(
        "/research/collections",
        json={
            "name": "Feed Winners",
            "platform": "tiktok",
            "description": "Top feed candidates",
            "user_id": TEST_USER_ID,
        },
        headers=TEST_AUTH_HEADER,
    )
    assert collection_response.status_code == 200
    collection_id = collection_response.json()["id"]

    assign_response = await feed_client.post(
        "/feed/collections/assign",
        json={
            "item_ids": [first_item, second_item, "missing-item-id"],
            "collection_id": collection_id,
            "user_id": TEST_USER_ID,
        },
        headers=TEST_AUTH_HEADER,
    )
    assert assign_response.status_code == 200
    assign_payload = assign_response.json()
    assert assign_payload["collection_id"] == collection_id
    assert assign_payload["assigned_count"] == 2
    assert assign_payload["missing_count"] == 1
    assert assign_payload["missing_item_ids"] == ["missing-item-id"]

    first_check = await feed_client.get(
        f"/research/items/{first_item}",
        params={"user_id": TEST_USER_ID},
        headers=TEST_AUTH_HEADER,
    )
    second_check = await feed_client.get(
        f"/research/items/{second_item}",
        params={"user_id": TEST_USER_ID},
        headers=TEST_AUTH_HEADER,
    )
    assert first_check.status_code == 200
    assert second_check.status_code == 200
    assert first_check.json()["collection_id"] == collection_id
    assert second_check.json()["collection_id"] == collection_id


@pytest.mark.asyncio
async def test_feed_export_generates_signed_download_and_enforces_token(feed_client):
    now = datetime.now(timezone.utc)
    first_item = await _capture_item(
        feed_client,
        platform="instagram",
        external_id="ig-export-1",
        handle="@export_lab",
        title="Export target 1",
        caption="csv export",
        views=33000,
        likes=1700,
        comments=85,
        shares=160,
        saves=130,
        published_at=now - timedelta(hours=8),
    )
    second_item = await _capture_item(
        feed_client,
        platform="instagram",
        external_id="ig-export-2",
        handle="@export_lab",
        title="Export target 2",
        caption="csv export",
        views=36000,
        likes=1800,
        comments=90,
        shares=180,
        saves=150,
        published_at=now - timedelta(hours=6),
    )

    export_response = await feed_client.post(
        "/feed/export",
        json={
            "item_ids": [first_item, second_item],
            "format": "csv",
            "user_id": TEST_USER_ID,
        },
        headers=TEST_AUTH_HEADER,
    )
    assert export_response.status_code == 200
    export_payload = export_response.json()
    assert export_payload["status"] == "completed"
    assert export_payload["format"] == "csv"
    assert export_payload["item_count"] == 2
    assert export_payload["signed_url"].startswith(f"/feed/export/{export_payload['export_id']}/download?")

    signed_url = export_payload["signed_url"]
    parsed = urlparse(signed_url)
    token = parse_qs(parsed.query)["token"][0]

    download_response = await feed_client.get(signed_url)
    assert download_response.status_code == 200
    content = download_response.text
    assert "item_id,platform,source_type,url,external_id" in content
    assert first_item in content
    assert second_item in content

    wrong_id_response = await feed_client.get(f"/feed/export/not-the-export/download?token={token}")
    assert wrong_id_response.status_code == 401
    assert "does not match export id" in wrong_id_response.json()["detail"]

    invalid_token_response = await feed_client.get(f"/feed/export/{export_payload['export_id']}/download?token=bad-token")
    assert invalid_token_response.status_code == 401


@pytest.mark.asyncio
async def test_feed_bulk_download_queues_jobs_and_status_endpoint(feed_client):
    now = datetime.now(timezone.utc)
    downloadable_item = await _capture_item(
        feed_client,
        platform="instagram",
        external_id="ig-download-1",
        handle="@download_lab",
        title="Download candidate",
        caption="has url",
        url="https://instagram.com/reel/abc123",
        views=41000,
        likes=1900,
        comments=95,
        shares=210,
        saves=160,
        published_at=now - timedelta(hours=4),
    )
    missing_url_item = await _capture_item(
        feed_client,
        platform="instagram",
        external_id="ig-download-2",
        handle="@download_lab",
        title="Missing URL candidate",
        caption="no url",
        url=None,
        views=26000,
        likes=1200,
        comments=60,
        shares=120,
        saves=100,
        published_at=now - timedelta(hours=5),
    )

    def _enqueue_noop(job_id: str):
        return _FakeQueueJob(f"media:{job_id}")

    with (
        patch("services.feed_discovery.settings.ALLOW_EXTERNAL_MEDIA_DOWNLOAD", True),
        patch("services.feed_discovery.enqueue_media_download_job", side_effect=_enqueue_noop),
    ):
        create_response = await feed_client.post(
            "/feed/download/bulk",
            json={
                "item_ids": [downloadable_item, missing_url_item, "missing-item"],
                "user_id": TEST_USER_ID,
            },
            headers=TEST_AUTH_HEADER,
        )
    assert create_response.status_code == 200
    payload = create_response.json()
    assert payload["submitted_count"] == 3
    assert payload["queued_count"] == 1
    assert payload["skipped_count"] == 2
    queued_jobs = [row for row in payload["jobs"] if row["status"] == "queued"]
    assert len(queued_jobs) == 1
    queued_job_id = queued_jobs[0]["job_id"]
    assert queued_job_id

    status_response = await feed_client.post(
        "/feed/download/status",
        json={"job_ids": [queued_job_id], "user_id": TEST_USER_ID},
        headers=TEST_AUTH_HEADER,
    )
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["requested_count"] == 1
    assert status_payload["jobs"][0]["job_id"] == queued_job_id
    assert status_payload["jobs"][0]["status"] in {"queued", "downloading", "processing", "completed", "failed"}


@pytest.mark.asyncio
async def test_feed_transcript_bulk_completes_with_caption_fallback(feed_client):
    now = datetime.now(timezone.utc)
    transcript_item = await _capture_item(
        feed_client,
        platform="tiktok",
        external_id="tt-transcript-1",
        handle="@transcript_lab",
        title="Transcript candidate",
        caption="This is a deterministic caption transcript fallback for testing.",
        url="https://www.tiktok.com/@transcript/video/123",
        views=50000,
        likes=2200,
        comments=120,
        shares=260,
        saves=190,
        published_at=now - timedelta(hours=2),
    )

    def _enqueue_transcript_async(job_id: str):
        asyncio.create_task(process_feed_transcript_job_async(job_id))
        return _FakeQueueJob(f"feed_transcript:{job_id}")

    with patch("services.feed_discovery.enqueue_feed_transcript_job", side_effect=_enqueue_transcript_async):
        create_response = await feed_client.post(
            "/feed/transcripts/bulk",
            json={"item_ids": [transcript_item], "user_id": TEST_USER_ID},
            headers=TEST_AUTH_HEADER,
        )
    assert create_response.status_code == 200
    create_payload = create_response.json()
    assert create_payload["queued_count"] == 1
    job_id = create_payload["jobs"][0]["job_id"]
    assert job_id

    status_payload = None
    for _ in range(20):
        status_response = await feed_client.post(
            "/feed/transcripts/status",
            json={"job_ids": [job_id], "user_id": TEST_USER_ID},
            headers=TEST_AUTH_HEADER,
        )
        assert status_response.status_code == 200
        status_payload = status_response.json()["jobs"][0]
        if status_payload["status"] == "completed":
            break
        await asyncio.sleep(0.05)

    assert status_payload is not None
    assert status_payload["status"] == "completed"
    assert status_payload["transcript_source"] in {"caption_fallback", "title_fallback", "whisper_audio"}
    assert isinstance(status_payload["transcript_preview"], str)
    assert len(status_payload["transcript_preview"]) > 5


@pytest.mark.asyncio
async def test_feed_follow_upsert_list_and_delete(feed_client):
    create_response = await feed_client.post(
        "/feed/follows/upsert",
        json={
            "platform": "instagram",
            "mode": "profile",
            "query": "ai_news_lab",
            "timeframe": "7d",
            "cadence": "6h",
            "limit": 25,
            "user_id": TEST_USER_ID,
        },
        headers=TEST_AUTH_HEADER,
    )
    assert create_response.status_code == 200
    create_payload = create_response.json()
    assert create_payload["created"] is True
    follow_id = create_payload["follow"]["id"]

    upsert_response = await feed_client.post(
        "/feed/follows/upsert",
        json={
            "platform": "instagram",
            "mode": "profile",
            "query": "ai_news_lab",
            "timeframe": "30d",
            "cadence": "12h",
            "limit": 40,
            "user_id": TEST_USER_ID,
        },
        headers=TEST_AUTH_HEADER,
    )
    assert upsert_response.status_code == 200
    upsert_payload = upsert_response.json()
    assert upsert_payload["created"] is False
    assert upsert_payload["follow"]["id"] == follow_id
    assert upsert_payload["follow"]["limit"] == 40
    assert upsert_payload["follow"]["cadence_minutes"] == 720

    list_response = await feed_client.get(
        "/feed/follows",
        params={"platform": "instagram", "active_only": "true", "user_id": TEST_USER_ID},
        headers=TEST_AUTH_HEADER,
    )
    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert list_payload["count"] >= 1
    assert any(row["id"] == follow_id for row in list_payload["follows"])

    delete_response = await feed_client.delete(
        f"/feed/follows/{follow_id}",
        params={"user_id": TEST_USER_ID},
        headers=TEST_AUTH_HEADER,
    )
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] is True


@pytest.mark.asyncio
async def test_feed_follow_ingest_creates_runs_and_respects_due_filter(feed_client):
    now = datetime.now(timezone.utc)
    await _capture_item(
        feed_client,
        platform="instagram",
        external_id="ig-follow-ingest-1",
        handle="@ai_news_lab",
        title="AI news winners",
        caption="ai growth playbook",
        url="https://instagram.com/reel/ingest1",
        views=60000,
        likes=2800,
        comments=130,
        shares=320,
        saves=250,
        published_at=now - timedelta(hours=3),
    )

    follow_resp = await feed_client.post(
        "/feed/follows/upsert",
        json={
            "platform": "instagram",
            "mode": "keyword",
            "query": "ai growth",
            "timeframe": "7d",
            "cadence": "6h",
            "limit": 20,
            "user_id": TEST_USER_ID,
        },
        headers=TEST_AUTH_HEADER,
    )
    assert follow_resp.status_code == 200
    follow_id = follow_resp.json()["follow"]["id"]

    due_only_initial = await feed_client.post(
        "/feed/follows/ingest",
        json={
            "follow_ids": [follow_id],
            "run_due_only": True,
            "max_follows": 10,
            "user_id": TEST_USER_ID,
        },
        headers=TEST_AUTH_HEADER,
    )
    assert due_only_initial.status_code == 200
    assert due_only_initial.json()["scheduled_count"] == 0

    session_maker = getattr(feed_client, "_session_maker")
    async with session_maker() as session:
        result = await session.execute(
            select(FeedSourceFollow).where(
                FeedSourceFollow.id == follow_id,
                FeedSourceFollow.user_id == TEST_USER_ID,
            )
        )
        row = result.scalar_one()
        row.next_run_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        await session.commit()

    due_only_run = await feed_client.post(
        "/feed/follows/ingest",
        json={
            "follow_ids": [follow_id],
            "run_due_only": True,
            "max_follows": 10,
            "user_id": TEST_USER_ID,
        },
        headers=TEST_AUTH_HEADER,
    )
    assert due_only_run.status_code == 200
    due_payload = due_only_run.json()
    assert due_payload["scheduled_count"] == 1
    assert due_payload["completed_count"] == 1
    assert due_payload["runs"][0]["follow_id"] == follow_id
    assert due_payload["runs"][0]["item_count"] >= 1

    runs_response = await feed_client.get(
        "/feed/follows/runs",
        params={"follow_id": follow_id, "limit": 10, "user_id": TEST_USER_ID},
        headers=TEST_AUTH_HEADER,
    )
    assert runs_response.status_code == 200
    runs_payload = runs_response.json()
    assert runs_payload["count"] >= 1
    assert runs_payload["runs"][0]["follow_id"] == follow_id


@pytest.mark.asyncio
async def test_feed_repost_package_create_list_get_and_status_update(feed_client):
    now = datetime.now(timezone.utc)
    source_item_id = await _capture_item(
        feed_client,
        platform="instagram",
        external_id="ig-repost-1",
        handle="@repost_lab",
        title="3 hook styles that doubled retention",
        caption="Most creators miss this opening line. #creator #hooks",
        url="https://instagram.com/reel/repost-1",
        views=120000,
        likes=5200,
        comments=360,
        shares=740,
        saves=610,
        published_at=now - timedelta(hours=9),
        media_meta={"transcript_text": "Most creators bury proof too late. Start with the outcome and show receipts."},
    )

    create_response = await feed_client.post(
        "/feed/repost/package",
        json={
            "source_item_id": source_item_id,
            "target_platforms": ["instagram", "tiktok"],
            "objective": "maximize_reach",
            "tone": "direct",
            "user_id": TEST_USER_ID,
        },
        headers=TEST_AUTH_HEADER,
    )
    assert create_response.status_code == 200
    create_payload = create_response.json()
    package_id = create_payload["package_id"]
    assert create_payload["status"] == "draft"
    assert create_payload["source_item_id"] == source_item_id
    assert set(create_payload["target_platforms"]) == {"instagram", "tiktok"}
    assert len(create_payload["package"]["hook_variants"]) == 3
    assert "instagram" in create_payload["package"]["platform_packages"]
    assert "tiktok" in create_payload["package"]["platform_packages"]

    list_response = await feed_client.get(
        "/feed/repost/packages",
        params={"source_item_id": source_item_id, "limit": 10, "user_id": TEST_USER_ID},
        headers=TEST_AUTH_HEADER,
    )
    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert list_payload["count"] >= 1
    assert any(row["package_id"] == package_id for row in list_payload["packages"])

    get_response = await feed_client.get(
        f"/feed/repost/packages/{package_id}",
        params={"user_id": TEST_USER_ID},
        headers=TEST_AUTH_HEADER,
    )
    assert get_response.status_code == 200
    get_payload = get_response.json()
    assert get_payload["package_id"] == package_id
    assert isinstance(get_payload["package"]["execution_checklist"], list)

    status_response = await feed_client.post(
        f"/feed/repost/packages/{package_id}/status",
        json={"status": "scheduled", "user_id": TEST_USER_ID},
        headers=TEST_AUTH_HEADER,
    )
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["status"] == "scheduled"
    assert status_payload["package"]["status"] == "scheduled"


@pytest.mark.asyncio
async def test_feed_repost_package_status_validation_and_missing_item(feed_client):
    now = datetime.now(timezone.utc)
    source_item_id = await _capture_item(
        feed_client,
        platform="tiktok",
        external_id="tt-repost-1",
        handle="@repost_lab",
        title="Retention checklist",
        caption="Quick retention checklist",
        url="https://www.tiktok.com/@repost/video/1",
        views=42000,
        likes=1900,
        comments=110,
        shares=260,
        saves=180,
        published_at=now - timedelta(hours=6),
    )

    create_response = await feed_client.post(
        "/feed/repost/package",
        json={"source_item_id": source_item_id, "user_id": TEST_USER_ID},
        headers=TEST_AUTH_HEADER,
    )
    assert create_response.status_code == 200
    package_id = create_response.json()["package_id"]

    invalid_status_response = await feed_client.post(
        f"/feed/repost/packages/{package_id}/status",
        json={"status": "invalid_status", "user_id": TEST_USER_ID},
        headers=TEST_AUTH_HEADER,
    )
    assert invalid_status_response.status_code == 422

    missing_item_response = await feed_client.post(
        "/feed/repost/package",
        json={"source_item_id": "missing-source-item", "user_id": TEST_USER_ID},
        headers=TEST_AUTH_HEADER,
    )
    assert missing_item_response.status_code == 404


@pytest.mark.asyncio
async def test_feed_loop_variant_generate_from_source_item(feed_client):
    now = datetime.now(timezone.utc)
    source_item_id = await _capture_item(
        feed_client,
        platform="youtube",
        external_id="yt-loop-variants-1",
        handle="@loop_lab",
        title="How to keep retention for short videos",
        caption="Proof-first hooks keep people watching longer.",
        url="https://youtube.com/watch?v=loopvariants",
        views=90000,
        likes=4100,
        comments=280,
        shares=350,
        saves=0,
        published_at=now - timedelta(hours=10),
    )

    response = await feed_client.post(
        "/feed/loop/variant_generate",
        json={
            "source_item_id": source_item_id,
            "tone": "bold",
            "user_id": TEST_USER_ID,
        },
        headers=TEST_AUTH_HEADER,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["source_item_id"] == source_item_id
    assert payload["optimizer"]["generation"]["mode"] == "ai_first_fallback"
    assert len(payload["optimizer"]["variants"]) == 3
    assert payload["credits"]["charged"] >= 0


@pytest.mark.asyncio
async def test_feed_loop_audit_uses_completed_feed_download_upload(feed_client):
    now = datetime.now(timezone.utc)
    source_item_id = await _capture_item(
        feed_client,
        platform="instagram",
        external_id="ig-loop-audit-1",
        handle="@loop_lab",
        title="Loop audit source",
        caption="This one has a completed download",
        url="https://instagram.com/reel/loop-audit-1",
        views=47000,
        likes=2100,
        comments=140,
        shares=260,
        saves=190,
        published_at=now - timedelta(hours=8),
    )

    session_maker = getattr(feed_client, "_session_maker")
    upload_id = str(uuid.uuid4())
    download_job_id = str(uuid.uuid4())
    upload_path = Path("/tmp") / f"{upload_id}.mp4"
    upload_path.write_bytes(b"loop-audit-video")

    async with session_maker() as session:
        upload = Upload(
            id=upload_id,
            user_id=TEST_USER_ID,
            file_url=str(upload_path),
            file_type="video",
            original_filename="loop_audit.mp4",
            file_size_bytes=upload_path.stat().st_size,
            mime_type="video/mp4",
        )
        session.add(upload)
        download_job = MediaDownloadJob(
            id=download_job_id,
            user_id=TEST_USER_ID,
            platform="instagram",
            source_url="https://instagram.com/reel/loop-audit-1",
            status="completed",
            progress=100,
            attempts=1,
            max_attempts=3,
            upload_id=upload_id,
        )
        session.add(download_job)
        research_result = await session.execute(
            select(ResearchItem).where(
                ResearchItem.id == source_item_id,
                ResearchItem.user_id == TEST_USER_ID,
            )
        )
        item_row = research_result.scalar_one()
        media_meta = item_row.media_meta_json if isinstance(item_row.media_meta_json, dict) else {}
        item_row.media_meta_json = {**media_meta, "feed_download_job_id": download_job_id}
        await session.commit()

    def _enqueue_audit_stub(audit_id: str, video_url: str | None, upload_path: str | None, source_mode: str):
        return _FakeAuditQueueJob(f"audit:{audit_id}")

    with patch("services.feed_discovery.enqueue_audit_job", side_effect=_enqueue_audit_stub):
        response = await feed_client.post(
            "/feed/loop/audit",
            json={"source_item_id": source_item_id, "user_id": TEST_USER_ID},
            headers=TEST_AUTH_HEADER,
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["source_item_id"] == source_item_id
    assert payload["status"] == "pending"
    assert payload["upload_id"] == upload_id
    assert payload["report_path"].startswith("/report/")

    summary = await feed_client.get(
        "/feed/loop/summary",
        params={"source_item_id": source_item_id, "user_id": TEST_USER_ID},
        headers=TEST_AUTH_HEADER,
    )
    assert summary.status_code == 200
    summary_payload = summary.json()
    assert summary_payload["latest_audit"] is not None
    assert summary_payload["stage_completion"]["audited"] is True

    upload_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_feed_loop_summary_shows_package_and_snapshot_progress(feed_client):
    now = datetime.now(timezone.utc)
    source_item_id = await _capture_item(
        feed_client,
        platform="tiktok",
        external_id="tt-loop-summary-1",
        handle="@loop_summary",
        title="Loop summary source",
        caption="build the loop",
        url="https://www.tiktok.com/@loop/video/summary",
        views=38000,
        likes=1700,
        comments=95,
        shares=210,
        saves=140,
        published_at=now - timedelta(hours=7),
    )

    repost_response = await feed_client.post(
        "/feed/repost/package",
        json={"source_item_id": source_item_id, "user_id": TEST_USER_ID},
        headers=TEST_AUTH_HEADER,
    )
    assert repost_response.status_code == 200

    snapshot_response = await feed_client.post(
        "/optimizer/draft_snapshot",
        json={
            "platform": "tiktok",
            "source_item_id": source_item_id,
            "script_text": "Hook with proof immediately. Then show one step, then CTA to follow for part two.",
            "rescored_score": 78.4,
            "user_id": TEST_USER_ID,
        },
        headers=TEST_AUTH_HEADER,
    )
    assert snapshot_response.status_code == 200

    summary_response = await feed_client.get(
        "/feed/loop/summary",
        params={"source_item_id": source_item_id, "user_id": TEST_USER_ID},
        headers=TEST_AUTH_HEADER,
    )
    assert summary_response.status_code == 200
    payload = summary_response.json()
    assert payload["latest_repost_package"] is not None
    assert payload["latest_draft_snapshot"] is not None
    assert payload["stage_completion"]["packaged"] is True
    assert payload["stage_completion"]["scripted"] is True


@pytest.mark.asyncio
async def test_feed_telemetry_summary_and_events_reflect_loop_funnel(feed_client):
    now = datetime.now(timezone.utc)
    source_item_id = await _capture_item(
        feed_client,
        platform="youtube",
        external_id="yt-telemetry-1",
        handle="@telemetry_lab",
        title="Telemetry source item",
        caption="Testing telemetry funnel coverage",
        url="https://youtube.com/watch?v=telemetry1",
        views=54000,
        likes=2600,
        comments=170,
        shares=220,
        saves=0,
        published_at=now - timedelta(hours=5),
    )

    repost_response = await feed_client.post(
        "/feed/repost/package",
        json={"source_item_id": source_item_id, "user_id": TEST_USER_ID},
        headers=TEST_AUTH_HEADER,
    )
    assert repost_response.status_code == 200

    snapshot_response = await feed_client.post(
        "/optimizer/draft_snapshot",
        json={
            "platform": "youtube",
            "source_item_id": source_item_id,
            "script_text": "Start with proof, give two steps, close with one CTA focused on comments.",
            "rescored_score": 82.1,
            "user_id": TEST_USER_ID,
        },
        headers=TEST_AUTH_HEADER,
    )
    assert snapshot_response.status_code == 200

    session_maker = getattr(feed_client, "_session_maker")
    async with session_maker() as session:
        audit_row = Audit(
            id=str(uuid.uuid4()),
            user_id=TEST_USER_ID,
            status="completed",
            progress="100",
            input_json={"source_item_id": source_item_id, "platform": "youtube", "source_mode": "upload"},
            output_json={"diagnosis": {}, "video_analysis": {}},
            completed_at=datetime.now(timezone.utc),
        )
        session.add(audit_row)
        await session.commit()

    loop_summary_response = await feed_client.get(
        "/feed/loop/summary",
        params={"source_item_id": source_item_id, "user_id": TEST_USER_ID},
        headers=TEST_AUTH_HEADER,
    )
    assert loop_summary_response.status_code == 200

    telemetry_summary = await feed_client.get(
        "/feed/telemetry/summary",
        params={"days": 7, "user_id": TEST_USER_ID},
        headers=TEST_AUTH_HEADER,
    )
    assert telemetry_summary.status_code == 200
    summary_payload = telemetry_summary.json()
    assert summary_payload["funnel"]["discovered_count"] >= 1
    assert summary_payload["funnel"]["packaged_count"] >= 1
    assert summary_payload["funnel"]["scripted_count"] >= 1
    assert summary_payload["funnel"]["audited_count"] >= 1
    assert summary_payload["funnel"]["reported_count"] >= 1
    assert summary_payload["event_volume"]["by_event"].get("feed_repost_package_created", 0) >= 1
    assert summary_payload["event_volume"]["by_event"].get("feed_loop_summary_view", 0) >= 1

    telemetry_events = await feed_client.get(
        "/feed/telemetry/events",
        params={"days": 7, "limit": 20, "event_name": "feed_repost_package_created", "user_id": TEST_USER_ID},
        headers=TEST_AUTH_HEADER,
    )
    assert telemetry_events.status_code == 200
    events_payload = telemetry_events.json()
    assert events_payload["count"] >= 1
    assert all(row["event_name"] == "feed_repost_package_created" for row in events_payload["events"])
