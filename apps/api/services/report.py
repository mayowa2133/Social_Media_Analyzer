"""
Service for aggregating audit data into a unified report.
"""

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import Dict, Any, Optional, List

from models.audit import Audit
from models.blueprint_snapshot import BlueprintSnapshot
from models.competitor import Competitor
from models.outcome_metric import OutcomeMetric
from models.calibration_snapshot import CalibrationSnapshot
from models.draft_snapshot import DraftSnapshot
from models.research_item import ResearchItem
from services.blueprint import generate_blueprint_service
from services.outcomes import get_outcomes_summary_service
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


def _fallback_blueprint(reason: str = "", platform: str = "youtube") -> Dict[str, Any]:
    note = reason or "Blueprint fallback generated because live blueprint refresh failed."
    platform_key = str(platform or "youtube").strip().lower()
    if platform_key not in {"youtube", "instagram", "tiktok"}:
        platform_key = "youtube"
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
        "series_intelligence": {
            "summary": "No competitor series detected yet.",
            "sample_size": 0,
            "total_detected_series": 0,
            "series": [],
        },
        "dataset_summary": {
            "platform": platform_key,
            "research_items_scanned": 0,
            "mapped_competitor_items": 0,
            "mapped_user_items": 0,
            "data_quality_tier": "low",
        },
    }


def _confidence_bucket(sample_size: int, mean_abs_error: float) -> str:
    if sample_size >= 20 and mean_abs_error <= 10:
        return "high"
    if sample_size >= 8 and mean_abs_error <= 16:
        return "medium"
    return "low"


async def _prediction_outcome_context(
    user_id: str,
    db: AsyncSession,
    platform_hint: Optional[str] = None,
    audit_id: Optional[str] = None,
) -> Dict[str, Any]:
    preferred_platform = str(platform_hint or "youtube").strip().lower()
    if preferred_platform not in {"youtube", "instagram", "tiktok"}:
        preferred_platform = "youtube"

    linked_outcome = None
    if audit_id:
        linked_outcome_result = await db.execute(
            select(OutcomeMetric)
            .where(
                OutcomeMetric.user_id == user_id,
                OutcomeMetric.report_id == audit_id,
            )
            .order_by(OutcomeMetric.posted_at.desc(), OutcomeMetric.created_at.desc())
            .limit(1)
        )
        linked_outcome = linked_outcome_result.scalar_one_or_none()

    latest_outcome = linked_outcome
    if latest_outcome is None:
        latest_outcome_result = await db.execute(
            select(OutcomeMetric)
            .where(
                OutcomeMetric.user_id == user_id,
                OutcomeMetric.platform == preferred_platform,
            )
            .order_by(OutcomeMetric.posted_at.desc(), OutcomeMetric.created_at.desc())
            .limit(1)
        )
        latest_outcome = latest_outcome_result.scalar_one_or_none()

    if latest_outcome:
        prediction_vs_actual: Optional[Dict[str, Any]] = {
            "outcome_id": latest_outcome.id,
            "platform": latest_outcome.platform,
            "content_item_id": latest_outcome.content_item_id,
            "draft_snapshot_id": latest_outcome.draft_snapshot_id,
            "report_id": latest_outcome.report_id,
            "posted_at": latest_outcome.posted_at.isoformat() if latest_outcome.posted_at else None,
            "predicted_score": latest_outcome.predicted_score,
            "actual_score": latest_outcome.actual_score,
            "calibration_delta": latest_outcome.calibration_delta,
            "actual_metrics": (
                latest_outcome.actual_metrics_json if isinstance(latest_outcome.actual_metrics_json, dict) else {}
            ),
        }
        platform = latest_outcome.platform
    else:
        prediction_vs_actual = None
        platform = preferred_platform

    summary_data: Dict[str, Any] = {}
    try:
        summary_payload = await get_outcomes_summary_service(
            user_id=user_id,
            db=db,
            platform=platform,
        )
        if isinstance(summary_payload, dict):
            summary_data = summary_payload
    except Exception:
        summary_data = {}

    snapshot_result = await db.execute(
        select(CalibrationSnapshot)
        .where(
            CalibrationSnapshot.user_id == user_id,
            CalibrationSnapshot.platform == platform,
        )
        .order_by(CalibrationSnapshot.updated_at.desc(), CalibrationSnapshot.created_at.desc())
        .limit(1)
    )
    snapshot = snapshot_result.scalar_one_or_none()

    if snapshot:
        sample_size = int(snapshot.sample_size or 0)
        mean_abs_error = float(snapshot.mean_abs_error or 0.0)
        hit_rate = float(snapshot.hit_rate or 0.0)
        confidence = _confidence_bucket(sample_size, mean_abs_error)
        calibration_confidence = {
            "platform": snapshot.platform,
            "sample_size": sample_size,
            "mean_abs_error": round(mean_abs_error, 2),
            "hit_rate": round(hit_rate, 4),
            "trend": snapshot.trend or "flat",
            "confidence": confidence,
            "insufficient_data": sample_size < 5,
            "recommendations": snapshot.recommendations_json if isinstance(snapshot.recommendations_json, list) else [],
        }
    else:
        calibration_confidence = {
            "platform": platform,
            "sample_size": 0,
            "mean_abs_error": 0.0,
            "hit_rate": 0.0,
            "trend": "flat",
            "confidence": "low",
            "insufficient_data": True,
            "recommendations": [
                "No posted outcomes ingested yet. Add outcome metrics to calibrate prediction confidence.",
            ],
        }

    if summary_data:
        calibration_confidence["trend"] = summary_data.get("trend", calibration_confidence["trend"])
        calibration_confidence["confidence"] = summary_data.get("confidence", calibration_confidence["confidence"])
        calibration_confidence["insufficient_data"] = bool(summary_data.get("insufficient_data", calibration_confidence["insufficient_data"]))
        calibration_confidence["sample_size"] = int(summary_data.get("sample_size", calibration_confidence["sample_size"]))
        calibration_confidence["mean_abs_error"] = float(summary_data.get("avg_error", calibration_confidence["mean_abs_error"]))
        calibration_confidence["hit_rate"] = float(summary_data.get("hit_rate", calibration_confidence["hit_rate"]))
        summary_recommendations = summary_data.get("recommendations")
        if isinstance(summary_recommendations, list) and summary_recommendations:
            calibration_confidence["recommendations"] = summary_recommendations

    return {
        "prediction_vs_actual": prediction_vs_actual,
        "calibration_confidence": calibration_confidence,
        "outcome_drift": {
            "drift_windows": summary_data.get("drift_windows", {}),
            "next_actions": summary_data.get("next_actions", []),
            "recent_outcomes": summary_data.get("recent_outcomes", []),
        },
    }


async def _best_edited_variant_context(
    *,
    user_id: str,
    audit_id: Optional[str],
    db: AsyncSession,
) -> Optional[Dict[str, Any]]:
    linked_snapshot_id: Optional[str] = None
    if audit_id:
        linked_outcome_result = await db.execute(
            select(OutcomeMetric)
            .where(
                OutcomeMetric.user_id == user_id,
                OutcomeMetric.report_id == audit_id,
                OutcomeMetric.draft_snapshot_id.isnot(None),
            )
            .order_by(OutcomeMetric.posted_at.desc(), OutcomeMetric.created_at.desc())
            .limit(1)
        )
        linked_outcome = linked_outcome_result.scalar_one_or_none()
        if linked_outcome and linked_outcome.draft_snapshot_id:
            linked_snapshot_id = linked_outcome.draft_snapshot_id

    snapshot = None
    if linked_snapshot_id:
        snapshot_result = await db.execute(
            select(DraftSnapshot).where(
                DraftSnapshot.id == linked_snapshot_id,
                DraftSnapshot.user_id == user_id,
            )
        )
        snapshot = snapshot_result.scalar_one_or_none()

    if snapshot is None:
        latest_snapshot_result = await db.execute(
            select(DraftSnapshot)
            .where(DraftSnapshot.user_id == user_id)
            .order_by(DraftSnapshot.created_at.desc())
            .limit(1)
        )
        snapshot = latest_snapshot_result.scalar_one_or_none()

    if snapshot is None:
        return None

    script_preview = (snapshot.script_text or "").strip()
    if len(script_preview) > 340:
        script_preview = f"{script_preview[:337]}..."

    detector_rankings = (
        snapshot.detector_rankings_json
        if isinstance(snapshot.detector_rankings_json, list)
        else []
    )
    top_detectors: List[Dict[str, Any]] = []
    for row in detector_rankings[:3]:
        if not isinstance(row, dict):
            continue
        top_detectors.append(
            {
                "detector_key": row.get("detector_key"),
                "label": row.get("label"),
                "score": row.get("score"),
                "target_score": row.get("target_score"),
                "gap": row.get("gap"),
            }
        )

    return {
        "id": snapshot.id,
        "platform": snapshot.platform,
        "variant_id": snapshot.variant_id,
        "source_item_id": snapshot.source_item_id,
        "script_preview": script_preview,
        "baseline_score": snapshot.baseline_score,
        "rescored_score": snapshot.rescored_score,
        "delta_score": snapshot.delta_score,
        "created_at": snapshot.created_at.isoformat() if snapshot.created_at else None,
        "top_detector_improvements": top_detectors,
    }


def _build_optimizer_quick_actions(best_edited_variant: Optional[Dict[str, Any]]) -> List[Dict[str, str]]:
    href = "/research?mode=optimizer"
    if isinstance(best_edited_variant, dict):
        source_item_id = str(best_edited_variant.get("source_item_id") or "").strip()
        script_preview = str(best_edited_variant.get("script_preview") or "").strip()
        if source_item_id:
            href += f"&source_item_id={quote(source_item_id)}"
        if script_preview:
            topic_seed = script_preview.split(".")[0][:120].strip()
            if topic_seed:
                href += f"&topic={quote(topic_seed)}"

    return [
        {
            "type": "generate_improved_variants",
            "label": "Generate 3 improved variants now",
            "href": href,
        }
    ]


def _resolve_report_platform(
    *,
    performance_prediction: Optional[Dict[str, Any]],
    audit_input: Optional[Dict[str, Any]],
) -> str:
    if isinstance(performance_prediction, dict):
        candidate = str(performance_prediction.get("platform") or "").strip().lower()
        if candidate in {"youtube", "instagram", "tiktok"}:
            return candidate
    if isinstance(audit_input, dict):
        candidate = str(audit_input.get("platform") or "").strip().lower()
        if candidate in {"youtube", "instagram", "tiktok"}:
            return candidate
    return "youtube"


async def _compute_competitor_signature(
    user_id: str,
    db: AsyncSession,
    platform: str = "youtube",
) -> str:
    platform_key = str(platform or "youtube").strip().lower()
    if platform_key not in {"youtube", "instagram", "tiktok"}:
        platform_key = "youtube"

    result = await db.execute(
        select(Competitor.external_id)
        .where(Competitor.user_id == user_id, Competitor.platform == platform_key)
        .order_by(Competitor.external_id.asc())
    )
    competitor_ids = [str(value) for value in result.scalars().all() if value]

    dataset_bits: Dict[str, Any] = {
        "platform": platform_key,
        "competitors": competitor_ids,
    }
    if platform_key in {"instagram", "tiktok"}:
        item_result = await db.execute(
            select(ResearchItem.id)
            .where(
                ResearchItem.user_id == user_id,
                ResearchItem.platform == platform_key,
            )
            .order_by(ResearchItem.id.asc())
        )
        dataset_bits["research_item_ids"] = [str(value) for value in item_result.scalars().all() if value]

    payload = json.dumps(dataset_bits, separators=(",", ":"), ensure_ascii=True)
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()
    return f"{platform_key}:{digest}"


async def _get_or_refresh_blueprint(
    user_id: str,
    db: AsyncSession,
    platform: str = "youtube",
) -> Dict[str, Any]:
    platform_key = str(platform or "youtube").strip().lower()
    if platform_key not in {"youtube", "instagram", "tiktok"}:
        platform_key = "youtube"

    snapshot_result = await db.execute(select(BlueprintSnapshot).where(BlueprintSnapshot.user_id == user_id))
    snapshot = snapshot_result.scalar_one_or_none()
    competitor_signature = await _compute_competitor_signature(user_id, db, platform=platform_key)
    ttl = timedelta(minutes=max(int(settings.BLUEPRINT_CACHE_TTL_MINUTES), 1))
    now = datetime.now(timezone.utc)

    cached_payload = snapshot.payload_json if snapshot and isinstance(snapshot.payload_json, dict) else None
    cached_platform = str(cached_payload.get("dataset_summary", {}).get("platform", "")).strip().lower() if cached_payload else ""
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
    if cached_platform and cached_platform != platform_key:
        is_stale = True

    if cached_payload and not is_stale:
        return cached_payload

    try:
        fresh_blueprint = await generate_blueprint_service(user_id, db, platform=platform_key)
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

        fallback = _fallback_blueprint(
            "Blueprint live refresh failed; using deterministic fallback.",
            platform=platform_key,
        )
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

    report_platform = _resolve_report_platform(
        performance_prediction=performance_prediction,
        audit_input=audit.input_json if audit and isinstance(audit.input_json, dict) else None,
    )

    # 3. Fetch Competitor Blueprint (Phase E)
    blueprint = await _get_or_refresh_blueprint(user_id, db, platform=report_platform)
    outcome_context = await _prediction_outcome_context(
        user_id,
        db,
        platform_hint=report_platform,
        audit_id=audit.id if audit else audit_id,
    )
    best_edited_variant = await _best_edited_variant_context(
        user_id=user_id,
        audit_id=audit.id if audit else audit_id,
        db=db,
    )

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
        "report_platform": report_platform,
        "created_at": audit.created_at.isoformat() if audit else None,
        "overall_score": round(overall_score),
        "diagnosis": diagnosis,
        "video_analysis": video_analysis,
        "performance_prediction": performance_prediction,
        "blueprint": blueprint,
        "prediction_vs_actual": outcome_context.get("prediction_vs_actual"),
        "calibration_confidence": outcome_context.get("calibration_confidence"),
        "outcome_drift": outcome_context.get("outcome_drift"),
        "best_edited_variant": best_edited_variant,
        "quick_actions": _build_optimizer_quick_actions(best_edited_variant),
        "recommendations": _normalize_recommendations(diagnosis, video_analysis, performance_prediction, blueprint),
    }
