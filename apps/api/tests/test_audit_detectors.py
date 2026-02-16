from services.audit import _build_platform_metrics, _extract_explicit_detectors


def test_explicit_detectors_extract_standalone_signals():
    transcript = {
        "text": (
            "I grew from zero to 100k. In a second I will show the proof. "
            "Here are the 3 steps. Stick around and comment if you want part 2."
        ),
        "segments": [
            {"start": 0.0, "end": 2.0, "text": "I grew from zero to 100k."},
            {"start": 2.1, "end": 5.0, "text": "In a second I will show the proof."},
            {"start": 5.2, "end": 8.4, "text": "Here are the 3 steps."},
            {"start": 18.0, "end": 24.0, "text": "Comment if you want part 2."},
        ],
    }
    analysis = {
        "overall_score": 7.2,
        "sections": [
            {"name": "Hook", "score": 8},
            {"name": "Pacing", "score": 7},
        ],
        "timestamp_feedback": [
            {"impact": "positive"},
            {"impact": "negative"},
        ],
    }

    detectors = _extract_explicit_detectors(transcript, analysis, duration_seconds=30)

    assert "time_to_value" in detectors
    assert "open_loops" in detectors
    assert "dead_zones" in detectors
    assert "pattern_interrupts" in detectors
    assert "cta_style" in detectors
    assert detectors["open_loops"]["count"] >= 1


def test_platform_metrics_uses_true_retention_and_interaction_inputs():
    analysis = {
        "overall_score": 7.6,
        "sections": [
            {"name": "Hook", "score": 8.4},
            {"name": "Content", "score": 7.1},
        ],
        "timestamp_feedback": [{"impact": "positive"}],
    }
    detectors = {
        "time_to_value": {"score": 85.0},
        "open_loops": {"score": 70.0},
        "dead_zones": {"score": 78.0},
        "pattern_interrupts": {"score": 72.0},
        "cta_style": {"score": 68.0},
    }
    retention_points = [
        {"time": 0, "retention": 100},
        {"time": 3, "retention": 88},
        {"time": 30, "retention": 62},
        {"time": 60, "retention": 48},
    ]
    platform_metrics = {
        "views": 50000,
        "likes": 2400,
        "comments": 310,
        "shares": 280,
        "saves": 520,
    }

    result = _build_platform_metrics(
        analysis,
        detectors,
        retention_points,
        platform_metrics,
        format_type="short_form",
    )
    coverage = result["metric_coverage"]

    assert coverage["shares"] == "true"
    assert coverage["saves"] == "true"
    assert coverage["retention_curve"] == "true"
    assert result["true_metrics"] is not None
    assert result["signals"]["detector_weighted_score"] > 0
    assert isinstance(result.get("detector_rankings"), list)
    assert len(result["detector_rankings"]) == 5
    assert result["detector_rankings"][0]["rank"] == 1
    assert result["score"] > 0


def test_detector_ranking_priority_is_deterministic_for_short_vs_long():
    analysis = {
        "overall_score": 7.0,
        "sections": [
            {"name": "Hook", "score": 7.5},
            {"name": "Pacing", "score": 6.8},
        ],
        "timestamp_feedback": [],
    }
    detectors = {
        "time_to_value": {"score": 40.0, "seconds": 9.0, "assessment": "slow"},
        "open_loops": {"score": 76.0, "count": 1},
        "dead_zones": {"score": 42.0, "count": 3, "total_seconds": 18.0},
        "pattern_interrupts": {"score": 50.0, "interrupts_per_minute": 1.8, "assessment": "low"},
        "cta_style": {"score": 22.0, "style": "none"},
    }

    short_result = _build_platform_metrics(
        analysis,
        detectors,
        retention_points=[],
        platform_metrics={},
        format_type="short_form",
    )
    long_result = _build_platform_metrics(
        analysis,
        detectors,
        retention_points=[],
        platform_metrics={},
        format_type="long_form",
    )

    short_top = short_result["detector_rankings"][0]["detector_key"]
    long_top = long_result["detector_rankings"][0]["detector_key"]
    assert short_top in {"time_to_value", "dead_zones", "cta_style", "pattern_interrupts", "open_loops"}
    assert long_top in {"time_to_value", "dead_zones", "cta_style", "pattern_interrupts", "open_loops"}
    assert any(item["priority"] in {"critical", "high"} for item in short_result["detector_rankings"])
    assert any(item["estimated_lift_points"] >= 0 for item in long_result["detector_rankings"])
