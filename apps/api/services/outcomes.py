"""Outcome ingestion and calibration summary services."""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from config import settings
from database import async_session_maker
from models.calibration_snapshot import CalibrationSnapshot
from models.outcome_metric import OutcomeMetric
from models.research_item import ResearchItem


def _assert_outcome_learning_enabled() -> None:
    if not settings.OUTCOME_LEARNING_ENABLED:
        raise HTTPException(status_code=503, detail="Outcome learning disabled by feature flag.")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _clip(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)

    text = str(value or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="posted_at is required")
    try:
        normalized = text.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="posted_at must be a valid ISO datetime") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _compute_actual_score(actual_metrics: Dict[str, Any], retention_points: List[Dict[str, Any]]) -> float:
    views = max(_safe_float(actual_metrics.get("views"), 0.0), 0.0)
    likes = max(_safe_float(actual_metrics.get("likes"), 0.0), 0.0)
    comments = max(_safe_float(actual_metrics.get("comments"), 0.0), 0.0)
    shares = max(_safe_float(actual_metrics.get("shares"), 0.0), 0.0)
    saves = max(_safe_float(actual_metrics.get("saves"), 0.0), 0.0)
    avg_watch_time = max(_safe_float(actual_metrics.get("avg_watch_time"), 0.0), 0.0)
    avg_view_duration_s = max(_safe_float(actual_metrics.get("avg_view_duration_s"), 0.0), 0.0)

    # Use log-scaled reach + weighted engagement + watch depth + retention curve quality.
    reach_component = min(30.0, math.log10(views + 1.0) * 7.5)

    weighted_interactions = likes + (comments * 2.0) + (shares * 3.0) + (saves * 3.0)
    engagement_rate = weighted_interactions / max(views, 1.0)
    engagement_component = min(42.0, engagement_rate * 900.0)

    watch_component = min(18.0, max(avg_watch_time, avg_view_duration_s) / 3.5)

    retention_component = 0.0
    normalized_retention: List[float] = []
    for point in retention_points:
        if not isinstance(point, dict):
            continue
        retention = _safe_float(point.get("retention"), -1.0)
        if retention < 0:
            continue
        normalized_retention.append(_clip(retention, 0.0, 100.0))
    if normalized_retention:
        avg_retention = sum(normalized_retention) / len(normalized_retention)
        retention_component = min(10.0, avg_retention * 0.12)

    return round(_clip(reach_component + engagement_component + watch_component + retention_component), 1)


def _trend_from_deltas(deltas: List[float]) -> str:
    if len(deltas) < 4:
        return "flat"
    midpoint = len(deltas) // 2
    older = deltas[midpoint:]
    newer = deltas[:midpoint]
    older_mean = sum(older) / max(len(older), 1)
    newer_mean = sum(newer) / max(len(newer), 1)
    if newer_mean < older_mean - 1.5:
        return "improving"
    if newer_mean > older_mean + 1.5:
        return "drifting"
    return "flat"


def _recommendations(sample_size: int, mean_abs_error: float, trend: str) -> List[str]:
    notes: List[str] = []
    if sample_size < 5:
        notes.append("Insufficient data: ingest at least 5 posted outcomes for stronger confidence.")
    if mean_abs_error > 18:
        notes.append("Prediction error is high. Prioritize scripts with explicit detector gaps fixed before posting.")
    elif mean_abs_error > 10:
        notes.append("Prediction error is moderate. Re-score edited drafts and compare deltas before publishing.")
    else:
        notes.append("Calibration error is healthy. Keep using the same score -> edit -> re-score loop.")

    if trend == "drifting":
        notes.append("Recent posts are drifting from predictions. Revisit hook and pacing assumptions.")
    elif trend == "improving":
        notes.append("Prediction accuracy is improving. Scale what is working in your latest formats.")

    return notes[:4]


def _confidence_bucket(sample_size: int, mean_abs_error: float) -> str:
    if sample_size >= 20 and mean_abs_error <= 10:
        return "high"
    if sample_size >= 8 and mean_abs_error <= 16:
        return "medium"
    return "low"


def _windowed_drift(rows_with_prediction: List[OutcomeMetric], days: int) -> Dict[str, Any]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(int(days), 1))
    scoped: List[OutcomeMetric] = []
    for row in rows_with_prediction:
        posted_at = _as_utc(row.posted_at)
        if posted_at is not None and posted_at >= cutoff:
            scoped.append(row)
    if not scoped:
        return {
            "days": int(days),
            "count": 0,
            "mean_delta": 0.0,
            "mean_abs_error": 0.0,
            "bias": "neutral",
        }

    deltas = [float(row.calibration_delta or 0.0) for row in scoped if row.calibration_delta is not None]
    if not deltas:
        return {
            "days": int(days),
            "count": len(scoped),
            "mean_delta": 0.0,
            "mean_abs_error": 0.0,
            "bias": "neutral",
        }

    mean_delta = sum(deltas) / len(deltas)
    mean_abs_error = sum(abs(delta) for delta in deltas) / len(deltas)
    if mean_delta >= 2.0:
        bias = "underpredicting"
    elif mean_delta <= -2.0:
        bias = "overpredicting"
    else:
        bias = "neutral"

    return {
        "days": int(days),
        "count": len(deltas),
        "mean_delta": round(mean_delta, 2),
        "mean_abs_error": round(mean_abs_error, 2),
        "bias": bias,
    }


def _drift_actions(
    *,
    platform: str,
    sample_size: int,
    mean_abs_error: float,
    drift_7d: Dict[str, Any],
    drift_30d: Dict[str, Any],
) -> List[str]:
    actions: List[str] = []
    platform_label = str(platform or "youtube").capitalize()

    if sample_size < 5:
        actions.append(f"Capture at least 5 {platform_label} post outcomes to improve confidence.")

    bias_7d = str(drift_7d.get("bias", "neutral"))
    if bias_7d == "underpredicting":
        actions.append("Recent actuals are above predictions. Raise targets and test stronger hook ambition.")
    elif bias_7d == "overpredicting":
        actions.append("Recent actuals are below predictions. Tighten hooks and reduce dead zones before posting.")

    if mean_abs_error > 16:
        actions.append("Re-score every edited draft and execute top 2 detector actions before publishing.")
    elif mean_abs_error > 10:
        actions.append("Use A/B script variants and keep only drafts with positive re-score deltas.")
    else:
        actions.append("Calibration is healthy. Scale the current format and topic mix.")

    bias_30d = str(drift_30d.get("bias", "neutral"))
    if bias_30d != "neutral" and bias_30d != bias_7d:
        actions.append("7d vs 30d drift differs. Re-check posting cadence and topic consistency.")

    deduped: List[str] = []
    seen = set()
    for action in actions:
        key = action.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(key)
    return deduped[:4]


def _serialize_recent_outcomes(rows: List[OutcomeMetric], limit: int = 12) -> List[Dict[str, Any]]:
    payload: List[Dict[str, Any]] = []
    for row in rows[: max(int(limit), 1)]:
        payload.append(
            {
                "outcome_id": row.id,
                "platform": row.platform,
                "draft_snapshot_id": row.draft_snapshot_id,
                "report_id": row.report_id,
                "content_item_id": row.content_item_id,
                "posted_at": row.posted_at.isoformat() if row.posted_at else None,
                "predicted_score": row.predicted_score,
                "actual_score": row.actual_score,
                "calibration_delta": row.calibration_delta,
            }
        )
    return payload


async def _resolve_predicted_score(
    *,
    user_id: str,
    content_item_id: Optional[str],
    payload_predicted_score: Optional[float],
    db: AsyncSession,
) -> Optional[float]:
    if payload_predicted_score is not None:
        return round(_clip(_safe_float(payload_predicted_score, 0.0)), 1)

    if not content_item_id:
        return None

    result = await db.execute(
        select(ResearchItem).where(
            ResearchItem.id == content_item_id,
            ResearchItem.user_id == user_id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        return None

    media_meta = item.media_meta_json if isinstance(item.media_meta_json, dict) else {}
    score = media_meta.get("predicted_score")
    if score is None:
        return None
    return round(_clip(_safe_float(score, 0.0)), 1)


async def _refresh_snapshot(*, user_id: str, platform: str, db: AsyncSession) -> Dict[str, Any]:
    rows_result = await db.execute(
        select(OutcomeMetric)
        .where(OutcomeMetric.user_id == user_id, OutcomeMetric.platform == platform)
        .order_by(OutcomeMetric.created_at.desc())
        .limit(250)
    )
    rows = rows_result.scalars().all()

    sample_size = len(rows)
    deltas = [abs(_safe_float(row.calibration_delta, 0.0)) for row in rows]
    rows_with_prediction = [row for row in rows if row.predicted_score is not None]

    if rows_with_prediction:
        mean_abs_error = sum(abs(_safe_float(row.calibration_delta, 0.0)) for row in rows_with_prediction) / len(rows_with_prediction)
        hit_rate = (
            sum(1 for row in rows_with_prediction if abs(_safe_float(row.calibration_delta, 0.0)) <= 10.0)
            / max(len(rows_with_prediction), 1)
        )
    else:
        mean_abs_error = 0.0
        hit_rate = 0.0

    trend = _trend_from_deltas(deltas)
    recommendations = _recommendations(sample_size, mean_abs_error, trend)

    snapshot_result = await db.execute(
        select(CalibrationSnapshot).where(
            CalibrationSnapshot.user_id == user_id,
            CalibrationSnapshot.platform == platform,
        )
    )
    snapshot = snapshot_result.scalar_one_or_none()
    if snapshot is None:
        snapshot = CalibrationSnapshot(
            id=str(uuid.uuid4()),
            user_id=user_id,
            platform=platform,
            sample_size=sample_size,
            mean_abs_error=round(mean_abs_error, 2),
            hit_rate=round(hit_rate, 4),
            trend=trend,
            recommendations_json=recommendations,
        )
        db.add(snapshot)
    else:
        snapshot.sample_size = sample_size
        snapshot.mean_abs_error = round(mean_abs_error, 2)
        snapshot.hit_rate = round(hit_rate, 4)
        snapshot.trend = trend
        snapshot.recommendations_json = recommendations

    await db.commit()

    confidence = _confidence_bucket(sample_size, mean_abs_error)
    return {
        "platform": platform,
        "sample_size": sample_size,
        "avg_error": round(mean_abs_error, 2),
        "hit_rate": round(hit_rate, 4),
        "trend": trend,
        "confidence": confidence,
        "insufficient_data": sample_size < 5,
        "recommendations": recommendations,
    }


async def ingest_outcome_service(*, user_id: str, payload: Dict[str, Any], db: AsyncSession) -> Dict[str, Any]:
    _assert_outcome_learning_enabled()

    platform = str(payload.get("platform") or "youtube").strip().lower()
    if platform not in {"youtube", "instagram", "tiktok"}:
        raise HTTPException(status_code=422, detail="platform must be youtube, instagram, or tiktok")

    content_item_id = str(payload.get("content_item_id") or "").strip() or None
    draft_snapshot_id = str(payload.get("draft_snapshot_id") or "").strip() or None
    report_id = str(payload.get("report_id") or "").strip() or None
    actual_metrics = payload.get("actual_metrics") if isinstance(payload.get("actual_metrics"), dict) else None
    if not actual_metrics:
        raise HTTPException(status_code=422, detail="actual_metrics is required")

    retention_points = payload.get("retention_points") if isinstance(payload.get("retention_points"), list) else []
    posted_at = _parse_datetime(payload.get("posted_at"))

    predicted_score = await _resolve_predicted_score(
        user_id=user_id,
        content_item_id=content_item_id,
        payload_predicted_score=(
            _safe_float(payload.get("predicted_score"), 0.0)
            if payload.get("predicted_score") is not None
            else None
        ),
        db=db,
    )
    actual_score = _compute_actual_score(actual_metrics, retention_points)
    calibration_delta = None
    if predicted_score is not None:
        calibration_delta = round(actual_score - predicted_score, 2)

    video_external_id = str(payload.get("video_external_id") or "").strip()
    if not video_external_id:
        video_external_id = str(content_item_id or str(uuid.uuid4()))

    row = OutcomeMetric(
        id=str(uuid.uuid4()),
        user_id=user_id,
        content_item_id=content_item_id,
        draft_snapshot_id=draft_snapshot_id,
        report_id=report_id,
        platform=platform,
        video_external_id=video_external_id,
        posted_at=posted_at,
        actual_metrics_json=actual_metrics,
        retention_points_json=retention_points or None,
        predicted_score=predicted_score,
        actual_score=actual_score,
        calibration_delta=calibration_delta,
    )
    db.add(row)
    await db.commit()

    snapshot = await _refresh_snapshot(user_id=user_id, platform=platform, db=db)
    return {
        "outcome_id": row.id,
        "calibration_delta": calibration_delta,
        "actual_score": actual_score,
        "predicted_score": predicted_score,
        "confidence_update": snapshot,
    }


async def get_outcomes_summary_service(
    *,
    user_id: str,
    db: AsyncSession,
    platform: Optional[str] = None,
) -> Dict[str, Any]:
    _assert_outcome_learning_enabled()

    if platform:
        platform_key = str(platform).strip().lower()
        if platform_key not in {"youtube", "instagram", "tiktok"}:
            raise HTTPException(status_code=422, detail="platform must be youtube, instagram, or tiktok")
        snapshot = await _refresh_snapshot(user_id=user_id, platform=platform_key, db=db)

        rows_result = await db.execute(
            select(OutcomeMetric)
            .where(OutcomeMetric.user_id == user_id, OutcomeMetric.platform == platform_key)
            .order_by(OutcomeMetric.posted_at.desc(), OutcomeMetric.created_at.desc())
            .limit(120)
        )
        rows = rows_result.scalars().all()
        rows_with_prediction = [row for row in rows if row.predicted_score is not None and row.calibration_delta is not None]
        drift_7d = _windowed_drift(rows_with_prediction, 7)
        drift_30d = _windowed_drift(rows_with_prediction, 30)
        next_actions = _drift_actions(
            platform=platform_key,
            sample_size=int(snapshot.get("sample_size", 0) or 0),
            mean_abs_error=float(snapshot.get("avg_error", 0.0) or 0.0),
            drift_7d=drift_7d,
            drift_30d=drift_30d,
        )
        return {
            **snapshot,
            "drift_windows": {
                "d7": drift_7d,
                "d30": drift_30d,
            },
            "recent_outcomes": _serialize_recent_outcomes(rows, limit=12),
            "next_actions": next_actions,
        }

    rows_result = await db.execute(
        select(CalibrationSnapshot)
        .where(CalibrationSnapshot.user_id == user_id)
        .order_by(CalibrationSnapshot.updated_at.desc(), CalibrationSnapshot.created_at.desc())
    )
    rows = rows_result.scalars().all()

    if not rows:
        return {
            "hit_rate": 0.0,
            "avg_error": 0.0,
            "trend": "flat",
            "confidence": "low",
            "insufficient_data": True,
            "recommendations": [
                "No outcomes captured yet. Ingest posted results to unlock calibration confidence.",
            ],
            "platforms": [],
        }

    platforms: List[Dict[str, Any]] = []
    for row in rows:
        sample_size = int(row.sample_size or 0)
        avg_error = float(row.mean_abs_error or 0.0)
        hit_rate = float(row.hit_rate or 0.0)
        confidence = _confidence_bucket(sample_size, avg_error)
        platforms.append(
            {
                "platform": row.platform,
                "sample_size": sample_size,
                "avg_error": round(avg_error, 2),
                "hit_rate": round(hit_rate, 4),
                "trend": row.trend,
                "confidence": confidence,
                "insufficient_data": sample_size < 5,
                "recommendations": row.recommendations_json if isinstance(row.recommendations_json, list) else [],
            }
        )

    avg_error_all = sum(item["avg_error"] for item in platforms) / max(len(platforms), 1)
    hit_rate_all = sum(item["hit_rate"] for item in platforms) / max(len(platforms), 1)
    sample_size_all = sum(item["sample_size"] for item in platforms)

    dominant = sorted(platforms, key=lambda item: item["sample_size"], reverse=True)[0]
    return {
        "hit_rate": round(hit_rate_all, 4),
        "avg_error": round(avg_error_all, 2),
        "trend": dominant.get("trend", "flat"),
        "confidence": _confidence_bucket(sample_size_all, avg_error_all),
        "insufficient_data": sample_size_all < 5,
        "recommendations": dominant.get("recommendations", []),
        "platforms": platforms,
    }


async def run_calibration_refresh_for_all_users_service(db: Optional[AsyncSession] = None) -> Dict[str, Any]:
    """Refresh calibration snapshots for every user/platform with captured outcomes."""
    _assert_outcome_learning_enabled()
    refreshed = 0
    skipped = 0
    errors: List[str] = []

    async def _run_with_session(session: AsyncSession) -> None:
        nonlocal refreshed, skipped, errors
        result = await session.execute(
            select(OutcomeMetric.user_id, OutcomeMetric.platform).distinct()
        )
        pairs = result.all()

        for user_id, platform in pairs:
            if not user_id or not platform:
                skipped += 1
                continue
            try:
                await _refresh_snapshot(user_id=str(user_id), platform=str(platform), db=session)
                refreshed += 1
            except Exception as exc:
                skipped += 1
                errors.append(f"{user_id}:{platform}:{exc}")

    if db is not None:
        await _run_with_session(db)
    else:
        async with async_session_maker() as session:
            await _run_with_session(session)

    return {
        "refreshed": refreshed,
        "skipped": skipped,
        "errors": errors[:20],
    }
