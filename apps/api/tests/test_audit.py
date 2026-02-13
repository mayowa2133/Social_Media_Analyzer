import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from services.audit import process_video_audit
from models.audit import Audit

@pytest.mark.asyncio
async def test_process_video_audit_success():
    # Mock Audit record
    mock_audit = MagicMock(spec=Audit)
    mock_audit.id = "audit-123"
    mock_audit.status = "pending"

    # Mock DB Session
    mock_db = AsyncMock()
    # Mock select result
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_audit
    mock_db.execute.return_value = mock_result
    
    # Mock Context Manager for Session
    mock_session_ctx = AsyncMock()
    mock_session_ctx.__aenter__.return_value = mock_db
    mock_session_ctx.__aexit__.return_value = None
    
    # Mock SessionMaker
    mock_session_maker = MagicMock(return_value=mock_session_ctx)

    with patch("services.audit.async_session_maker", mock_session_maker), \
         patch("services.audit.download_video", return_value="/tmp/test_vid.mp4") as mock_download, \
         patch("services.audit.extract_frames", return_value=["/tmp/f1.jpg"]) as mock_frames, \
         patch("services.audit.extract_audio", return_value="/tmp/test_aud.mp3") as mock_extract_audio, \
         patch("services.audit.transcribe_audio", return_value={"text": "test transcript"}) as mock_transcribe, \
         patch("services.audit.analyze_content") as mock_analyze, \
         patch("services.audit.os.makedirs"), \
         patch("services.audit.shutil.rmtree"):
         
         # Mock LLM result
         mock_analyze_result = MagicMock()
         mock_analyze_result.model_dump.return_value = {"overall_score": 10, "summary": "Great"}
         mock_analyze.return_value = mock_analyze_result
         
         # Run Service
         await process_video_audit("audit-123", "http://test.url")
         
         # Assertions
         assert mock_download.called
         assert mock_frames.called
         assert mock_extract_audio.called
         assert mock_transcribe.called
         assert mock_analyze.called
         
         # Check final status
         assert mock_audit.status == "completed"
         assert mock_audit.progress == "100"
         assert mock_audit.output_json == {"overall_score": 10, "summary": "Great"}
         assert mock_db.commit.call_count >= 1

@pytest.mark.asyncio
async def test_process_video_audit_failure():
    # Mock failure in download
    mock_audit = MagicMock(spec=Audit)
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_audit
    mock_db.execute.return_value = mock_result
    
    mock_session_ctx = AsyncMock()
    mock_session_ctx.__aenter__.return_value = mock_db
    mock_session_ctx.__aexit__.return_value = None
    mock_session_maker = MagicMock(return_value=mock_session_ctx)

    with patch("services.audit.async_session_maker", mock_session_maker), \
         patch("services.audit.download_video", side_effect=Exception("Download failed")):
         
         await process_video_audit("audit-fail", "http://bad.url")
         
         assert mock_audit.status == "failed"
         assert "Download failed" in mock_audit.error_message
