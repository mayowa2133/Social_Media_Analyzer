import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from database import Base
from models.audit import Audit
from models.calibration_snapshot import CalibrationSnapshot
from models.user import User
from services.report import get_consolidated_report


@pytest_asyncio.fixture
async def report_db(tmp_path):
    db_path = tmp_path / "report_contract.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_maker() as session:
        user = User(id="report-user", email="report-user@local.invalid")
        session.add(user)
        audit = Audit(
            id="audit-report-1",
            user_id="report-user",
            status="completed",
            progress="100",
            output_json={
                "diagnosis": {"recommendations": []},
                "video_analysis": {"overall_score": 7.0, "summary": "test", "sections": []},
                "performance_prediction": {
                    "platform": "instagram",
                    "format_type": "short_form",
                    "duration_seconds": 40,
                    "platform_metrics": {
                        "score": 74.0,
                        "signals": {
                            "overall_multimodal_score": 70.0,
                            "base_multimodal_score": 69.0,
                            "explicit_detector_score": 68.0,
                            "detector_weighted_score": 71.0,
                            "detector_weight_breakdown": {
                                "time_to_value": 0.32,
                                "open_loops": 0.16,
                                "dead_zones": 0.22,
                                "pattern_interrupts": 0.20,
                                "cta_style": 0.10,
                            },
                            "hook_strength": 72.0,
                            "pacing_strength": 68.0,
                            "timestamp_positive_signals": 1,
                            "timestamp_negative_signals": 0,
                        },
                        "detector_rankings": [
                            {
                                "detector_key": "time_to_value",
                                "label": "Time to Value",
                                "score": 64.0,
                                "target_score": 85.0,
                                "gap": 21.0,
                                "weight": 0.32,
                                "priority": "high",
                                "rank": 1,
                                "estimated_lift_points": 5.2,
                                "evidence": ["First value lands late."],
                                "edits": ["Lead with payoff in first line."],
                            }
                        ],
                    },
                    "competitor_metrics": {"score": 70.0, "benchmark": {"sample_size": 0}},
                    "combined_metrics": {"score": 73.0},
                    "next_actions": [
                        {
                            "title": "Improve Time to Value",
                            "detector_key": "time_to_value",
                            "priority": "high",
                            "why": "First value lands late.",
                            "expected_lift_points": 5.2,
                            "execution_steps": ["Lead with payoff in first line."],
                            "evidence": ["First value lands late."],
                        }
                    ],
                },
            },
        )
        session.add(
            CalibrationSnapshot(
                id="cal-ig-1",
                user_id="report-user",
                platform="instagram",
                sample_size=12,
                mean_abs_error=9.5,
                hit_rate=0.66,
                trend="flat",
                recommendations_json=["Keep refining hooks and pacing."],
            )
        )
        session.add(audit)
        await session.commit()
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_report_contract_preserves_new_prediction_fields(report_db):
    report = await get_consolidated_report("report-user", "audit-report-1", report_db)

    prediction = report.get("performance_prediction")
    assert isinstance(prediction, dict)
    assert "next_actions" in prediction
    assert isinstance(prediction["next_actions"], list)
    assert len(prediction["next_actions"]) > 0
    assert "detector_rankings" in prediction["platform_metrics"]
    assert isinstance(prediction["platform_metrics"]["detector_rankings"], list)
    assert prediction["platform_metrics"]["signals"]["detector_weighted_score"] > 0

    recommendations = report.get("recommendations", [])
    assert isinstance(recommendations, list)
    assert any("Improve Time to Value" in item for item in recommendations)
    assert "calibration_confidence" in report
    assert isinstance(report["calibration_confidence"], dict)
    assert report["calibration_confidence"]["platform"] == "instagram"
    assert report["report_platform"] == "instagram"
    assert report["report_platform"] == report["calibration_confidence"]["platform"]
    assert "prediction_vs_actual" in report
    assert "quick_actions" in report
    assert "best_edited_variant" in report
    assert "outcome_drift" in report
    assert "drift_windows" in report["outcome_drift"]
    assert "next_actions" in report["outcome_drift"]
