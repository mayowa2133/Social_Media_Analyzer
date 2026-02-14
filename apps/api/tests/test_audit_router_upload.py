import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from unittest.mock import AsyncMock, patch

from database import Base, get_db
from main import app


@pytest_asyncio.fixture
async def integration_client(tmp_path):
    db_path = tmp_path / "audit_upload.db"
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
async def test_upload_video_and_start_upload_mode_audit(integration_client):
    with patch("routers.audit.process_video_audit", new=AsyncMock(return_value=None)):
        upload_resp = await integration_client.post(
            "/audit/upload",
            files={"file": ("sample.mp4", b"fake-video-binary", "video/mp4")},
            data={"user_id": "upload-user"},
        )
        assert upload_resp.status_code == 200
        upload_data = upload_resp.json()
        assert upload_data["status"] == "uploaded"
        assert upload_data["upload_id"]

        run_resp = await integration_client.post(
            "/audit/run_multimodal",
            json={
                "source_mode": "upload",
                "upload_id": upload_data["upload_id"],
                "user_id": "upload-user",
            },
        )
        assert run_resp.status_code == 200
        run_data = run_resp.json()
        assert run_data["status"] == "pending"
        assert run_data["audit_id"]
