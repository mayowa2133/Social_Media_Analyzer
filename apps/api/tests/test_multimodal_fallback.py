from multimodal.llm import analyze_content


def test_multimodal_fallback_without_openai_key_returns_valid_audit_result():
    result = analyze_content(
        frames=[],
        transcript={"text": "Quick test transcript for local deterministic fallback."},
        video_metadata={"id": "video-local-1", "title": "Local Fallback Video"},
        api_key="test-key",
    )

    assert result.video_id == "video-local-1"
    assert result.overall_score > 0
    assert len(result.sections) > 0
    assert len(result.timestamp_feedback) > 0
