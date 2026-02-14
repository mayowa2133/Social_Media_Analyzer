"""
Service for aggregating audit data into a unified report.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import Dict, Any, Optional, List

from models.audit import Audit
from services.blueprint import generate_blueprint_service


def _safe_score_100(value: Any, default: float = 70.0) -> float:
    try:
        raw = float(value)
    except (TypeError, ValueError):
        return default
    if raw <= 10.0:
        return max(0.0, min(100.0, raw * 10.0))
    return max(0.0, min(100.0, raw))


def _normalize_recommendations(
    diagnosis: Dict[str, Any],
    video_analysis: Dict[str, Any],
    performance_prediction: Optional[Dict[str, Any]],
) -> List[str]:
    """
    Normalize mixed recommendation payloads into display-ready strings.
    """
    result: List[str] = []

    for rec in diagnosis.get("recommendations", [])[:2]:
        if isinstance(rec, str):
            result.append(rec)
        elif isinstance(rec, dict):
            title = rec.get("title")
            description = rec.get("description")
            if title and description:
                result.append(f"{title}: {description}")
            elif title:
                result.append(str(title))

    for sec in video_analysis.get("sections", [])[:1]:
        if isinstance(sec, dict):
            for feedback in sec.get("feedback", [])[:1]:
                if isinstance(feedback, str):
                    result.append(feedback)

    combined = (
        performance_prediction.get("combined_metrics", {})
        if isinstance(performance_prediction, dict)
        else {}
    )
    combined_score = _safe_score_100(combined.get("score"), default=-1)
    if combined_score >= 0:
        if combined_score < 60:
            result.append("Combined performance likelihood is currently low; tighten the first 3-5 seconds and clarity of the payoff.")
        elif combined_score < 80:
            result.append("Combined performance likelihood is medium; improve hook specificity and pacing to lift breakout odds.")
        else:
            result.append("Combined performance likelihood is high; keep this structure and iterate variations for repeatable winners.")

    result.append("Focus on the next 3 pillar topics identified in your Competitor Blueprint.")
    return result


async def get_consolidated_report(user_id: str, audit_id: Optional[str], db: AsyncSession) -> Dict[str, Any]:
    """
    Consolidate metrics, multimodal results, and competitor blueprint.
    """
    # 1. Fetch Audit Data (Phase C/D)
    if audit_id:
        result = await db.execute(select(Audit).where(Audit.id == audit_id))
        audit = result.scalar_one_or_none()
    else:
        # Get latest
        result = await db.execute(
            select(Audit)
            .where(Audit.user_id == user_id)
            .order_by(Audit.created_at.desc())
            .limit(1)
        )
        audit = result.scalar_one_or_none()

    # 2. Extract Diagnosis (Phase C) and Video Analysis (Phase D)
    diagnosis = {}
    video_analysis = {}
    performance_prediction: Optional[Dict[str, Any]] = None
    
    if audit and audit.output_json:
        # Depending on how it's stored, might be JSON already or a bundle
        data = audit.output_json
        diagnosis = data.get("diagnosis", {})
        if isinstance(data.get("video_analysis"), dict):
            video_analysis = data.get("video_analysis", {})
        elif isinstance(data, dict) and "overall_score" in data and "sections" in data:
            # Backward compatibility for early multimodal payloads that stored analysis at top-level.
            video_analysis = data
        raw_prediction = data.get("performance_prediction")
        if isinstance(raw_prediction, dict) and raw_prediction:
            performance_prediction = raw_prediction

    # 3. Fetch Competitor Blueprint (Phase E)
    blueprint = await generate_blueprint_service(user_id, db)

    # 4. Calculate Overall Score (Weighted)
    # Weights: 30% Stats Metrics, 40% Video Hook/Retention, 30% Strategy/Blueprint
    stats_score = _safe_score_100(diagnosis.get("metrics", {}).get("overall_score", 70), default=70)
    predicted_combined = performance_prediction.get("combined_metrics", {}).get("score") if performance_prediction else None
    if predicted_combined is not None:
        video_score = _safe_score_100(predicted_combined, default=70)
    else:
        video_score = _safe_score_100(video_analysis.get("overall_score", 70), default=70)
    strategy_score = 80

    overall_score = (stats_score * 0.3) + (video_score * 0.4) + (strategy_score * 0.3)

    return {
        "audit_id": audit.id if audit else "new",
        "created_at": audit.created_at.isoformat() if audit else None,
        "overall_score": round(overall_score),
        "diagnosis": diagnosis,
        "video_analysis": video_analysis,
        "performance_prediction": performance_prediction,
        "blueprint": blueprint,
        "recommendations": _normalize_recommendations(diagnosis, video_analysis, performance_prediction),
    }
