import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.future import select

from database import Base, get_db
from main import app
from models.media_download_job import MediaDownloadJob
from services.media_download import process_media_download_job_async
from services.session_token import create_session_token


MEDIA_USER_ID = "media-user"
OTHER_USER_ID = "media-user-other"
MEDIA_AUTH_HEADER = {"Authorization": f"Bearer {create_session_token(MEDIA_USER_ID)['token']}"}
OTHER_AUTH_HEADER = {"Authorization": f"Bearer {create_session_token(OTHER_USER_ID)['token']}"}


class _FakeJob:
    def __init__(self, job_id: str):
        self.id = job_id
        self.origin = "media_jobs"


class _FakeAuditJob:
    def __init__(self, job_id: str):
        self.id = job_id
        self.origin = "audit_jobs"


def _enqueue_media_noop(job_id: str):
    return _FakeJob(f"media:{job_id}")


def _enqueue_media_async(job_id: str):
    asyncio.create_task(process_media_download_job_async(job_id))
    return _FakeJob(f"media:{job_id}")


def _enqueue_audit_noop(audit_id: str, video_url: str | None, upload_path: str | None, source_mode: str):
    return _FakeAuditJob(f"audit:{audit_id}")


def _fake_download_video(url: str, output_path: str) -> str:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"fake-video")
    return str(target)


@pytest_asyncio.fixture
async def media_client(tmp_path):
    db_path = tmp_path / "media_download.db"
    upload_root = tmp_path / "uploads"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def override_get_db():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with (
        patch("routers.media.settings.AUDIT_UPLOAD_DIR", str(upload_root)),
        patch("services.media_download.settings.AUDIT_UPLOAD_DIR", str(upload_root)),
        patch("services.media_download.async_session_maker", session_maker),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client, session_maker

    app.dependency_overrides.pop(get_db, None)
    await engine.dispose()


@pytest.mark.asyncio
async def test_media_download_job_completes_and_can_run_upload_audit(media_client):
    client, _ = media_client
    with (
        patch("routers.media.settings.ALLOW_EXTERNAL_MEDIA_DOWNLOAD", True),
        patch("routers.media.enqueue_media_download_job", side_effect=_enqueue_media_async),
        patch("services.media_download.download_video", side_effect=_fake_download_video),
        patch("services.media_download.get_video_duration_seconds", return_value=42),
        patch("routers.audit.enqueue_audit_job", side_effect=_enqueue_audit_noop),
    ):
        create_resp = await client.post(
            "/media/download",
            json={
                "platform": "instagram",
                "source_url": "https://instagram.com/reel/abc123",
                "user_id": MEDIA_USER_ID,
            },
            headers=MEDIA_AUTH_HEADER,
        )
        assert create_resp.status_code == 200
        payload = create_resp.json()
        job_id = payload["job_id"]
        assert payload["status"] == "queued"
        assert payload["platform"] == "instagram"

        status_payload = payload
        for _ in range(20):
            status_resp = await client.get(
                f"/media/download/{job_id}?user_id={MEDIA_USER_ID}",
                headers=MEDIA_AUTH_HEADER,
            )
            assert status_resp.status_code == 200
            status_payload = status_resp.json()
            if status_payload["status"] == "completed":
                break
            await asyncio.sleep(0.05)

        assert status_payload["status"] == "completed"
        assert status_payload["upload_id"]
        assert status_payload["media_asset_id"]
        assert status_payload["progress"] == 100

        audit_resp = await client.post(
            "/audit/run_multimodal",
            json={
                "source_mode": "upload",
                "upload_id": status_payload["upload_id"],
                "user_id": MEDIA_USER_ID,
            },
            headers=MEDIA_AUTH_HEADER,
        )
        assert audit_resp.status_code == 200
        assert audit_resp.json()["status"] == "pending"


@pytest.mark.asyncio
async def test_media_download_queue_unavailable_marks_job_failed(media_client):
    client, session_maker = media_client
    with (
        patch("routers.media.settings.ALLOW_EXTERNAL_MEDIA_DOWNLOAD", True),
        patch("routers.media.enqueue_media_download_job", side_effect=RuntimeError("redis offline")),
    ):
        create_resp = await client.post(
            "/media/download",
            json={
                "platform": "tiktok",
                "source_url": "https://www.tiktok.com/@test/video/123",
                "user_id": MEDIA_USER_ID,
            },
            headers=MEDIA_AUTH_HEADER,
        )
        assert create_resp.status_code == 503

    async with session_maker() as session:
        result = await session.execute(
            select(MediaDownloadJob).where(MediaDownloadJob.user_id == MEDIA_USER_ID)
        )
        jobs = result.scalars().all()
        assert len(jobs) == 1
        assert jobs[0].status == "failed"
        assert jobs[0].error_code == "queue_unavailable"


@pytest.mark.asyncio
async def test_media_download_job_scoped_by_authenticated_user(media_client):
    client, _ = media_client
    with (
        patch("routers.media.settings.ALLOW_EXTERNAL_MEDIA_DOWNLOAD", True),
        patch("routers.media.enqueue_media_download_job", side_effect=_enqueue_media_noop),
    ):
        create_resp = await client.post(
            "/media/download",
            json={
                "platform": "instagram",
                "source_url": "https://instagram.com/reel/private-test",
                "user_id": MEDIA_USER_ID,
            },
            headers=MEDIA_AUTH_HEADER,
        )
        assert create_resp.status_code == 200
        job_id = create_resp.json()["job_id"]

    forbidden_resp = await client.get(
        f"/media/download/{job_id}?user_id={OTHER_USER_ID}",
        headers=OTHER_AUTH_HEADER,
    )
    assert forbidden_resp.status_code == 404
