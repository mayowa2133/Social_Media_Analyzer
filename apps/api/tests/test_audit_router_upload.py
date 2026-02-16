import asyncio
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from unittest.mock import AsyncMock, MagicMock, patch

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
    with patch("services.audit.async_session_maker", session_maker):
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


@pytest.mark.asyncio
async def test_upload_mode_audit_outputs_next_actions(integration_client):
    mock_analysis_result = MagicMock()
    mock_analysis_result.model_dump.return_value = {
        "overall_score": 7.2,
        "summary": "Mock analysis summary",
        "sections": [
            {"name": "Hook", "score": 7.8},
            {"name": "Pacing", "score": 6.9},
        ],
        "timestamp_feedback": [{"impact": "negative"}],
    }
    mock_transcript = {
        "text": "In a second I will show the proof. Here are the 3 steps. Comment below.",
        "segments": [
            {"start": 0.0, "end": 3.0, "text": "In a second I will show the proof."},
            {"start": 3.2, "end": 7.0, "text": "Here are the 3 steps."},
            {"start": 18.0, "end": 24.0, "text": "Comment below."},
        ],
    }

    with patch("services.audit.extract_frames", return_value=["/tmp/frame.jpg"]), \
         patch("services.audit.extract_audio", return_value=None), \
         patch("services.audit.transcribe_audio", return_value=mock_transcript), \
         patch("services.audit.analyze_content", return_value=mock_analysis_result), \
         patch("services.audit.get_video_duration_seconds", return_value=36), \
         patch("services.audit.shutil.rmtree"):
        upload_resp = await integration_client.post(
            "/audit/upload",
            files={"file": ("sample.mp4", b"fake-video-binary", "video/mp4")},
            data={"user_id": "upload-user"},
        )
        assert upload_resp.status_code == 200
        upload_data = upload_resp.json()

        run_resp = await integration_client.post(
            "/audit/run_multimodal",
            json={
                "source_mode": "upload",
                "upload_id": upload_data["upload_id"],
                "user_id": "upload-user",
                "platform_metrics": {"views": 12000, "likes": 640, "comments": 54},
            },
        )
        assert run_resp.status_code == 200
        audit_id = run_resp.json()["audit_id"]

        status_payload = {}
        for _ in range(15):
            status_resp = await integration_client.get(f"/audit/{audit_id}?user_id=upload-user")
            assert status_resp.status_code == 200
            status_payload = status_resp.json()
            if status_payload.get("status") == "completed":
                break
            await asyncio.sleep(0.05)

        assert status_payload.get("status") == "completed"
        output = status_payload.get("output", {})
        prediction = output.get("performance_prediction", {})
        assert isinstance(prediction.get("next_actions"), list)
        assert len(prediction.get("next_actions", [])) > 0
