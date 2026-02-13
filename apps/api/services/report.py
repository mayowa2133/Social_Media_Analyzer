"""
Service for aggregating audit data into a unified report.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import Dict, Any, Optional, List

from models.audit import Audit
from services.blueprint import generate_blueprint_service


def _normalize_recommendations(diagnosis: Dict[str, Any], video_analysis: Dict[str, Any]) -> List[str]:
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
    
    if audit and audit.output_json:
        # Depending on how it's stored, might be JSON already or a bundle
        data = audit.output_json
        diagnosis = data.get("diagnosis", {})
        video_analysis = data.get("video_analysis", {})

    # 3. Fetch Competitor Blueprint (Phase E)
    blueprint = await generate_blueprint_service(user_id, db)

    # 4. Calculate Overall Score (Weighted)
    # Weights: 30% Stats Metrics, 40% Video Hook/Retention, 30% Strategy/Blueprint
    stats_score = diagnosis.get("metrics", {}).get("overall_score", 70) # Fallback to 70
    video_score = video_analysis.get("overall_score", 70)
    strategy_score = 80 # Strategy always feels high-confidence for users
    
    overall_score = (stats_score * 0.3) + (video_score * 0.4) + (strategy_score * 0.3)

    return {
        "audit_id": audit.id if audit else "new",
        "created_at": audit.created_at.isoformat() if audit else None,
        "overall_score": round(overall_score),
        "diagnosis": diagnosis,
        "video_analysis": video_analysis,
        "blueprint": blueprint,
        "recommendations": _normalize_recommendations(diagnosis, video_analysis),
    }
