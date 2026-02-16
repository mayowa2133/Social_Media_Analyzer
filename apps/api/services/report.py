"""
Service for aggregating audit data into a unified report.
"""

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import Dict, Any, Optional, List

from models.audit import Audit
from models.blueprint_snapshot import BlueprintSnapshot
from models.competitor import Competitor
from services.blueprint import generate_blueprint_service
from config import settings

logger = logging.getLogger(__name__)


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
    blueprint: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """
    Normalize mixed recommendation payloads into display-ready strings.
    """
    result: List[str] = []

    if isinstance(performance_prediction, dict):
        next_actions = performance_prediction.get("next_actions", [])
        if isinstance(next_actions, list):
            for action in next_actions[:3]:
                if not isinstance(action, dict):
                    continue
                title = str(action.get("title", "")).strip()
                why = str(action.get("why", "")).strip()
                if title and why:
                    result.append(f"{title}: {why}")
                elif title:
                    result.append(title)

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

    if isinstance(blueprint, dict):
        velocity_actions = blueprint.get("velocity_actions", [])
        if isinstance(velocity_actions, list):
            for action in velocity_actions[:2]:
                if not isinstance(action, dict):
                    continue
                title = str(action.get("title", "")).strip()
                why = str(action.get("why", "")).strip()
                if title and why:
                    result.append(f"{title}: {why}")

    result.append("Focus on the next 3 pillar topics identified in your Competitor Blueprint.")

    deduped: List[str] = []
    seen = set()
    for item in result:
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)

    return deduped[:8]


def _fallback_blueprint(reason: str = "") -> Dict[str, Any]:
    note = reason or "Blueprint fallback generated because live blueprint refresh failed."
    return {
        "gap_analysis": [note],
        "content_pillars": ["Audience Pain Points", "Execution Frameworks", "Retention Tweaks"],
        "video_ideas": [
            {"title": "Fix Your First 3 Seconds", "concept": "Open with direct payoff and proof."},
            {"title": "How We Keep Retention High", "concept": "Use framework steps and faster pattern interrupts."},
            {"title": "The CTA That Converts", "concept": "Use one clear CTA tied to the promise."},
        ],
        "hook_intelligence": {
            "summary": "Fallback hook profile. Connect competitors for richer hook extraction.",
            "format_definition": "short_form <= 60s, long_form > 60s",
            "common_patterns": [],
            "recommended_hooks": [],
            "competitor_examples": [],
            "format_breakdown": {
                "short_form": {
                    "format": "short_form",
                    "label": "Short-form (<= 60s)",
                    "video_count": 0,
                    "summary": "No short-form benchmark yet.",
                    "common_patterns": [],
                    "recommended_hooks": [],
                    "competitor_examples": [],
                },
                "long_form": {
                    "format": "long_form",
                    "label": "Long-form (> 60s)",
                    "video_count": 0,
                    "summary": "No long-form benchmark yet.",
                    "common_patterns": [],
                    "recommended_hooks": [],
                    "competitor_examples": [],
                },
            },
        },
        "winner_pattern_signals": {
            "summary": "No velocity benchmark available yet.",
            "sample_size": 0,
            "top_topics_by_velocity": [],
            "hook_velocity_correlation": 0.0,
            "top_videos_by_velocity": [],
        },
        "framework_playbook": {
            "summary": "No framework benchmark available yet.",
            "stage_adoption": {
                "authority_hook": 0.0,
                "fast_proof": 0.0,
                "framework_steps": 0.0,
                "open_loop": 0.0,
            },
            "cta_distribution": {},
            "dominant_sequence": ["authority_hook", "fast_proof", "framework_steps", "cta"],
            "execution_notes": ["Connect competitors to generate framework-specific recommendations."],
        },
        "repurpose_plan": {
            "summary": "Fallback repurpose plan.",
            "core_angle": "Use one core message and adapt pacing by platform.",
            "youtube_shorts": {"duration_target_s": 45, "hook_template": "Question Hook", "edit_directives": ["Lead with payoff in frame 1."]},
            "instagram_reels": {"duration_target_s": 35, "hook_template": "Question Hook", "edit_directives": ["Use clean pacing and one save CTA."]},
            "tiktok": {"duration_target_s": 28, "hook_template": "Question Hook", "edit_directives": ["Use fast cuts and one comment CTA."]},
        },
        "transcript_quality": {
            "sample_size": 0,
            "by_source": {},
            "transcript_coverage_ratio": 0.0,
            "fallback_ratio": 1.0,
            "notes": [note],
        },
        "velocity_actions": [],
    }


async def _compute_competitor_signature(user_id: str, db: AsyncSession) -> str:
    result = await db.execute(
        select(Competitor.external_id)
        .where(Competitor.user_id == user_id, Competitor.platform == "youtube")
        .order_by(Competitor.external_id.asc())
    )
    channel_ids = [str(value) for value in result.scalars().all() if value]
    if not channel_ids:
        return "none"
    payload = json.dumps(channel_ids, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


async def _get_or_refresh_blueprint(user_id: str, db: AsyncSession) -> Dict[str, Any]:
    snapshot_result = await db.execute(select(BlueprintSnapshot).where(BlueprintSnapshot.user_id == user_id))
    snapshot = snapshot_result.scalar_one_or_none()
    competitor_signature = await _compute_competitor_signature(user_id, db)
    ttl = timedelta(minutes=max(int(settings.BLUEPRINT_CACHE_TTL_MINUTES), 1))
    now = datetime.now(timezone.utc)

    cached_payload = snapshot.payload_json if snapshot and isinstance(snapshot.payload_json, dict) else None
    generated_at = snapshot.generated_at if snapshot else None
    is_stale = True
    if cached_payload and isinstance(generated_at, datetime):
        generated_at_utc = (
            generated_at
            if generated_at.tzinfo is not None
            else generated_at.replace(tzinfo=timezone.utc)
        )
        is_stale = (now - generated_at_utc) > ttl
    if snapshot and snapshot.competitor_signature != competitor_signature:
        is_stale = True

    if cached_payload and not is_stale:
        return cached_payload

    try:
        fresh_blueprint = await generate_blueprint_service(user_id, db)
        if not isinstance(fresh_blueprint, dict):
            raise ValueError("Blueprint service returned invalid payload.")

        if snapshot is None:
            snapshot = BlueprintSnapshot(
                user_id=user_id,
                payload_json=fresh_blueprint,
                competitor_signature=competitor_signature,
                generated_at=now,
                last_error=None,
            )
            db.add(snapshot)
        else:
            snapshot.payload_json = fresh_blueprint
            snapshot.competitor_signature = competitor_signature
            snapshot.generated_at = now
            snapshot.last_error = None
        await db.commit()
        return fresh_blueprint
    except Exception as exc:
        logger.warning("Blueprint refresh failed for user %s: %s", user_id, exc)
        if snapshot is not None:
            snapshot.last_error = str(exc)
            try:
                await db.commit()
            except Exception:
                await db.rollback()
        if cached_payload:
            return cached_payload

        fallback = _fallback_blueprint("Blueprint live refresh failed; using deterministic fallback.")
        if snapshot is None:
            snapshot = BlueprintSnapshot(
                user_id=user_id,
                payload_json=fallback,
                competitor_signature=competitor_signature,
                generated_at=now,
                last_error=str(exc),
            )
            db.add(snapshot)
            try:
                await db.commit()
            except Exception:
                await db.rollback()
        return fallback


async def get_consolidated_report(user_id: str, audit_id: Optional[str], db: AsyncSession) -> Dict[str, Any]:
    """
    Consolidate metrics, multimodal results, and competitor blueprint.
    """
    # 1. Fetch Audit Data (Phase C/D)
    if audit_id:
        result = await db.execute(
            select(Audit).where(
                Audit.id == audit_id,
                Audit.user_id == user_id,
            )
        )
        audit = result.scalar_one_or_none()
        if not audit:
            raise LookupError("Audit not found for this user.")
    else:
        # Get latest
        result = await db.execute(
            select(Audit)
            .where(
                Audit.user_id == user_id,
                Audit.status == "completed",
            )
            .order_by(Audit.created_at.desc())
            .limit(1)
        )
        audit = result.scalar_one_or_none()
        if not audit:
            raise LookupError("No completed audit found for this user.")

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
    blueprint = await _get_or_refresh_blueprint(user_id, db)

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
        "recommendations": _normalize_recommendations(diagnosis, video_analysis, performance_prediction, blueprint),
    }
