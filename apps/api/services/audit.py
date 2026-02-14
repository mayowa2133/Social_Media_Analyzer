import asyncio
import logging
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.future import select

from config import settings
from database import async_session_maker
from models.audit import Audit
from models.competitor import Competitor
from ingestion.youtube import create_youtube_client_with_api_key
from multimodal.audio import extract_audio, transcribe_audio
from multimodal.llm import analyze_content
from multimodal.video import download_video, extract_frames, get_video_duration_seconds

logger = logging.getLogger(__name__)

SHORT_FORM_MAX_SECONDS = 60


def _get_youtube_client():
    api_key = settings.YOUTUBE_API_KEY or settings.GOOGLE_CLIENT_SECRET
    if not api_key:
        raise ValueError("YouTube API key not configured")
    return create_youtube_client_with_api_key(api_key)


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


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _to_100_scale(score: Any) -> float:
    raw = _safe_float(score, 0.0)
    return raw * 10.0 if raw <= 10.0 else raw


def _infer_format(duration_seconds: int) -> str:
    if duration_seconds <= 0:
        return "unknown"
    if duration_seconds <= SHORT_FORM_MAX_SECONDS:
        return "short_form"
    return "long_form"


def _score_band(score: float) -> str:
    if score >= 80:
        return "high"
    if score >= 60:
        return "medium"
    return "low"


def _format_label(format_type: str) -> str:
    if format_type == "short_form":
        return f"short-form (<= {SHORT_FORM_MAX_SECONDS}s)"
    if format_type == "long_form":
        return f"long-form (> {SHORT_FORM_MAX_SECONDS}s)"
    return "mixed-format"


def _segment_field(segment: Any, field: str, default: Any) -> Any:
    if isinstance(segment, dict):
        return segment.get(field, default)
    return getattr(segment, field, default)


def _normalize_transcript(
    transcript: Any,
    duration_seconds: int,
) -> tuple[str, List[Dict[str, Any]]]:
    segments_raw: List[Any] = []
    if isinstance(transcript, dict):
        segments_raw = transcript.get("segments", []) or []
        full_text = str(transcript.get("text", "") or "").strip()
    else:
        segments_raw = getattr(transcript, "segments", []) or []
        full_text = str(getattr(transcript, "text", "") or "").strip()

    segments: List[Dict[str, Any]] = []
    for seg in segments_raw:
        start = _safe_float(_segment_field(seg, "start", 0.0), 0.0)
        end = _safe_float(_segment_field(seg, "end", start + 3.0), start + 3.0)
        text = str(_segment_field(seg, "text", "") or "").strip()
        if not text:
            continue
        if end < start:
            end = start + 3.0
        segments.append({"start": start, "end": end, "text": text})

    segments.sort(key=lambda s: _safe_float(s.get("start", 0.0)))
    if segments:
        for i in range(len(segments)):
            current = segments[i]
            next_start = _safe_float(segments[i + 1]["start"], current["end"]) if i + 1 < len(segments) else None
            guessed_end = current["end"]
            if next_start is not None:
                guessed_end = min(guessed_end, next_start)
                if guessed_end <= current["start"]:
                    guessed_end = current["start"] + 2.5
            elif duration_seconds > 0:
                guessed_end = min(guessed_end, float(duration_seconds))
                if guessed_end <= current["start"]:
                    guessed_end = min(float(duration_seconds), current["start"] + 2.5)
            current["end"] = guessed_end
    elif full_text:
        default_end = min(max(float(duration_seconds), 6.0), 12.0) if duration_seconds > 0 else 8.0
        segments = [{"start": 0.0, "end": default_end, "text": full_text}]

    if not full_text and segments:
        full_text = " ".join(seg["text"] for seg in segments)

    return full_text, segments


def _extract_explicit_detectors(
    transcript: Any,
    video_analysis: Dict[str, Any],
    duration_seconds: int,
) -> Dict[str, Any]:
    text, segments = _normalize_transcript(transcript, duration_seconds)
    lower_text = text.lower()
    safe_duration = max(float(duration_seconds), 1.0)

    value_patterns = [
        r"\bhere('?s| is) (the|what|how)\b",
        r"\bthe (\d+|three|four|five) (things|steps|rules|mistakes)\b",
        r"\bhow to\b",
        r"\bthis is why\b",
        r"\bframework\b",
    ]
    value_ts = None
    for seg in segments:
        seg_text = str(seg.get("text", "")).lower()
        if any(re.search(pattern, seg_text) for pattern in value_patterns):
            value_ts = _safe_float(seg.get("start", 0.0), 0.0)
            break
    if value_ts is None:
        value_ts = min(safe_duration * 0.25, 20.0)
    time_to_value_score = _clamp(100.0 - (value_ts * 9.0), 0.0, 100.0)

    open_loop_patterns = [
        r"\bin a second\b",
        r"\bby the end\b",
        r"\bstick around\b",
        r"\bcoming up\b",
        r"\bbefore we get to\b",
        r"\blater in this video\b",
        r"\bdon't skip\b",
    ]
    open_loop_matches: List[str] = []
    for pattern in open_loop_patterns:
        open_loop_matches.extend(re.findall(pattern, lower_text))
    open_loops_count = len(open_loop_matches)
    open_loops_score = _clamp(45.0 + (open_loops_count * 14.0), 0.0, 100.0)

    dead_zones: List[Dict[str, float]] = []
    previous_end = 0.0
    for seg in segments:
        start = _safe_float(seg.get("start", 0.0), 0.0)
        end = _safe_float(seg.get("end", start), start)
        gap = start - previous_end
        if gap >= 4.5:
            dead_zones.append({"start": round(previous_end, 2), "end": round(start, 2), "duration": round(gap, 2)})

        words = re.findall(r"\w+", str(seg.get("text", "")))
        seg_duration = max(0.0, end - start)
        if seg_duration >= 7.0 and len(words) <= 6:
            dead_zones.append({"start": round(start, 2), "end": round(end, 2), "duration": round(seg_duration, 2)})
        previous_end = max(previous_end, end)

    tail_gap = safe_duration - previous_end
    if tail_gap >= 5.0:
        dead_zones.append(
            {"start": round(previous_end, 2), "end": round(safe_duration, 2), "duration": round(tail_gap, 2)}
        )
    dead_zone_seconds = sum(zone["duration"] for zone in dead_zones)
    dead_zone_score = _clamp(100.0 - ((dead_zone_seconds / safe_duration) * 120.0) - (len(dead_zones) * 4.0), 0.0, 100.0)

    timestamp_feedback = video_analysis.get("timestamp_feedback", [])
    timestamp_events = len(timestamp_feedback) if isinstance(timestamp_feedback, list) else 0
    long_segments = sum(
        1 for seg in segments if (_safe_float(seg.get("end", 0.0)) - _safe_float(seg.get("start", 0.0))) >= 8.0
    )
    estimated_interrupts = max(0, len(segments) - long_segments) + timestamp_events
    interrupts_per_minute = estimated_interrupts / max(safe_duration / 60.0, 1.0)
    pattern_interrupt_score = _clamp(42.0 + (interrupts_per_minute * 18.0) - (long_segments * 8.0), 0.0, 100.0)

    cta_window_text = lower_text
    if segments:
        cta_start = safe_duration * 0.75
        tail_segments = [seg for seg in segments if _safe_float(seg.get("start", 0.0), 0.0) >= cta_start]
        if tail_segments:
            cta_window_text = " ".join(str(seg.get("text", "")).lower() for seg in tail_segments)
    cta_patterns = {
        "comment_prompt": [r"\bcomment\b", r"\btell me\b", r"\bwhat do you think\b"],
        "subscribe_follow": [r"\bsubscribe\b", r"\bfollow\b"],
        "save_share": [r"\bsave\b", r"\bshare\b", r"\bsend this\b"],
        "link_bio": [r"\blink in bio\b", r"\blink below\b", r"\bdescription\b"],
    }
    cta_style = "none"
    cta_hits = 0
    for style, patterns in cta_patterns.items():
        hits = sum(1 for pattern in patterns if re.search(pattern, cta_window_text))
        if hits > cta_hits:
            cta_hits = hits
            cta_style = style
    cta_score = 20.0 if cta_style == "none" else _clamp(58.0 + (cta_hits * 14.0), 0.0, 100.0)

    return {
        "time_to_value": {
            "seconds": round(value_ts, 2),
            "target_seconds": 5.0,
            "score": round(time_to_value_score, 1),
            "assessment": "fast" if value_ts <= 3 else "moderate" if value_ts <= 8 else "slow",
        },
        "open_loops": {
            "count": open_loops_count,
            "score": round(open_loops_score, 1),
            "examples": open_loop_matches[:3],
        },
        "dead_zones": {
            "count": len(dead_zones),
            "total_seconds": round(dead_zone_seconds, 2),
            "score": round(dead_zone_score, 1),
            "zones": dead_zones[:5],
        },
        "pattern_interrupts": {
            "interrupts_per_minute": round(interrupts_per_minute, 2),
            "score": round(pattern_interrupt_score, 1),
            "assessment": (
                "high"
                if interrupts_per_minute >= 5.0
                else "healthy"
                if interrupts_per_minute >= 3.0
                else "low"
            ),
        },
        "cta_style": {
            "style": cta_style,
            "score": round(cta_score, 1),
            "window": "last_25_percent",
        },
    }


def _retention_curve_score(retention_points: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    normalized: List[Dict[str, float]] = []
    for point in retention_points:
        if not isinstance(point, dict):
            continue
        t = _safe_float(point.get("time"), -1.0)
        r = _safe_float(point.get("retention"), -1.0)
        if t < 0 or r < 0:
            continue
        normalized.append({"time": t, "retention": _clamp(r, 0.0, 100.0)})

    if not normalized:
        return None

    normalized.sort(key=lambda p: p["time"])

    def _nearest(target: float) -> float:
        return min(normalized, key=lambda p: abs(p["time"] - target))["retention"]

    total_span = max(normalized[-1]["time"], 1.0)
    early = _nearest(min(3.0, total_span))
    mid = _nearest(min(30.0, total_span * 0.5))
    end = normalized[-1]["retention"]
    curve_score = _clamp((early * 0.45) + (mid * 0.35) + (end * 0.20), 0.0, 100.0)

    return {
        "score": round(curve_score, 1),
        "early_retention": round(early, 1),
        "mid_retention": round(mid, 1),
        "end_retention": round(end, 1),
        "point_count": len(normalized),
    }


def _build_repurpose_plan(
    video_analysis: Dict[str, Any],
    detectors: Dict[str, Any],
    format_type: str,
) -> Dict[str, Any]:
    summary = str(video_analysis.get("summary", "") or "").strip() or "Keep the same core idea and tighten the opening."
    cta_style = (
        detectors.get("cta_style", {}).get("style", "comment_prompt")
        if isinstance(detectors, dict)
        else "comment_prompt"
    )
    hook_speed = detectors.get("time_to_value", {}).get("seconds", 6.0) if isinstance(detectors, dict) else 6.0
    pacing_target = "high-cut density (1 visual shift every 1-2s)" if format_type == "short_form" else "pattern interrupt every 10-20s"

    return {
        "core_thesis": summary,
        "source_format": format_type,
        "youtube_shorts": {
            "target_duration_s": 45 if format_type != "long_form" else 55,
            "hook_deadline_s": min(3.0, _safe_float(hook_speed, 6.0)),
            "editing_style": "faster jumps + kinetic captions",
            "cta": "Ask one concrete comment question in final 3 seconds.",
        },
        "instagram_reels": {
            "target_duration_s": 35 if format_type != "long_form" else 50,
            "hook_deadline_s": 2.5,
            "editing_style": "strong first frame text + cleaner aesthetic pacing",
            "cta": "Prompt save/share with one practical takeaway card.",
        },
        "tiktok": {
            "target_duration_s": 28 if format_type != "long_form" else 45,
            "hook_deadline_s": 1.8,
            "editing_style": pacing_target,
            "cta": (
                "Close with follow + comment prompt."
                if cta_style in {"none", "subscribe_follow"}
                else "Close with the same CTA style that already performs."
            ),
        },
    }


def _build_platform_metrics(
    video_analysis: Dict[str, Any],
    detectors: Dict[str, Any],
    retention_points: List[Dict[str, Any]],
    platform_metrics: Dict[str, Any],
) -> Dict[str, Any]:
    overall_100 = _clamp(_to_100_scale(video_analysis.get("overall_score", 0)))
    sections = video_analysis.get("sections", [])
    section_scores: List[float] = []
    hook_candidates: List[float] = []
    pacing_candidates: List[float] = []

    if isinstance(sections, list):
        for sec in sections:
            if not isinstance(sec, dict):
                continue
            sec_name = str(sec.get("name", "")).lower()
            sec_score_100 = _clamp(_to_100_scale(sec.get("score", 0)))
            section_scores.append(sec_score_100)
            if "intro" in sec_name or "hook" in sec_name:
                hook_candidates.append(sec_score_100)
            if "body" in sec_name or "content" in sec_name or "pacing" in sec_name:
                pacing_candidates.append(sec_score_100)

    section_mean = sum(section_scores) / len(section_scores) if section_scores else overall_100
    hook_strength = sum(hook_candidates) / len(hook_candidates) if hook_candidates else section_mean
    pacing_strength = sum(pacing_candidates) / len(pacing_candidates) if pacing_candidates else section_mean

    negatives = 0
    positives = 0
    timestamp_feedback = video_analysis.get("timestamp_feedback", [])
    if isinstance(timestamp_feedback, list):
        for item in timestamp_feedback:
            if not isinstance(item, dict):
                continue
            impact = str(item.get("impact", "")).lower()
            if impact == "negative":
                negatives += 1
            elif impact == "positive":
                positives += 1

    risk_penalty = min(15.0, negatives * 3.0)
    positive_boost = min(8.0, positives * 1.5)

    base_score = _clamp(
        (overall_100 * 0.55)
        + (hook_strength * 0.25)
        + (pacing_strength * 0.20)
        + positive_boost
        - risk_penalty
    )

    detector_scores = [
        _safe_float(detectors.get("time_to_value", {}).get("score", 0.0), 0.0),
        _safe_float(detectors.get("open_loops", {}).get("score", 0.0), 0.0),
        _safe_float(detectors.get("dead_zones", {}).get("score", 0.0), 0.0),
        _safe_float(detectors.get("pattern_interrupts", {}).get("score", 0.0), 0.0),
        _safe_float(detectors.get("cta_style", {}).get("score", 0.0), 0.0),
    ]
    detector_composite = sum(detector_scores) / max(len(detector_scores), 1)
    score = _clamp((base_score * 0.75) + (detector_composite * 0.25))

    metric_coverage = {
        "likes": "available",
        "comments": "available",
        "shares": "proxy",
        "saves": "proxy",
        "retention_curve": "proxy",
    }
    true_signal_notes: List[str] = []
    true_metrics: Dict[str, Any] = {}

    retention_curve = _retention_curve_score(retention_points)
    if retention_curve:
        score = _clamp((score * 0.8) + (_safe_float(retention_curve.get("score", 0.0), 0.0) * 0.2))
        metric_coverage["retention_curve"] = "true"
        true_metrics["retention_curve"] = retention_curve
        true_signal_notes.append("Used provided retention curve points from platform analytics.")

    views = _safe_float(platform_metrics.get("views"), 0.0)
    likes = _safe_float(platform_metrics.get("likes"), 0.0)
    comments = _safe_float(platform_metrics.get("comments"), 0.0)
    shares = _safe_float(platform_metrics.get("shares"), 0.0)
    saves = _safe_float(platform_metrics.get("saves"), 0.0)
    if shares > 0:
        metric_coverage["shares"] = "true"
    if saves > 0:
        metric_coverage["saves"] = "true"
    if views > 0 and (likes > 0 or comments > 0 or shares > 0 or saves > 0):
        weighted_interactions = likes + (comments * 2.0) + (shares * 3.0) + (saves * 3.0)
        true_engagement_rate = weighted_interactions / max(views, 1.0)
        true_engagement_score = _clamp(true_engagement_rate * 1200.0, 0.0, 100.0)
        score = _clamp((score * 0.85) + (true_engagement_score * 0.15))
        true_metrics["engagement"] = {
            "views": int(views),
            "likes": int(likes),
            "comments": int(comments),
            "shares": int(shares),
            "saves": int(saves),
            "weighted_rate": round(true_engagement_rate, 4),
            "score": round(true_engagement_score, 1),
        }
        true_signal_notes.append("Used true interaction metrics (views/likes/comments/shares/saves).")

    return {
        "score": round(score, 1),
        "summary": (
            "Platform quality score derived from hook clarity, pacing, explicit structure detectors, "
            "and true analytics metrics when provided."
        ),
        "signals": {
            "overall_multimodal_score": round(overall_100, 1),
            "base_multimodal_score": round(base_score, 1),
            "explicit_detector_score": round(detector_composite, 1),
            "hook_strength": round(hook_strength, 1),
            "pacing_strength": round(pacing_strength, 1),
            "timestamp_positive_signals": positives,
            "timestamp_negative_signals": negatives,
        },
        "detectors": detectors,
        "metric_coverage": metric_coverage,
        "true_metrics": true_metrics if true_metrics else None,
        "true_metric_notes": true_signal_notes,
    }


async def _collect_competitor_benchmark(user_id: str, format_type: str) -> Dict[str, Any]:
    async with async_session_maker() as db:
        result = await db.execute(
            select(Competitor).where(
                Competitor.user_id == user_id,
                Competitor.platform == "youtube",
            )
        )
        competitors = result.scalars().all()

    if not competitors:
        return {
            "has_data": False,
            "sample_size": 0,
            "competitor_count": 0,
            "avg_views": 0.0,
            "avg_like_rate": 0.0,
            "avg_comment_rate": 0.0,
            "avg_engagement_rate": 0.0,
            "difficulty_score": 55.0,
            "used_format_filter": False,
            "format_type": format_type,
            "summary": "No competitors connected yet; baseline difficulty fallback used.",
        }

    try:
        client = _get_youtube_client()
    except Exception as exc:
        logger.warning(f"Could not initialize YouTube client for competitor benchmark: {exc}")
        return {
            "has_data": False,
            "sample_size": 0,
            "competitor_count": len(competitors),
            "avg_views": 0.0,
            "avg_like_rate": 0.0,
            "avg_comment_rate": 0.0,
            "avg_engagement_rate": 0.0,
            "difficulty_score": 55.0,
            "used_format_filter": False,
            "format_type": format_type,
            "summary": "Competitors found, but benchmark fetch failed. Using fallback difficulty.",
        }

    samples: List[Dict[str, Any]] = []
    for competitor in competitors[:12]:
        channel_id = competitor.external_id
        if not channel_id:
            continue
        try:
            videos = client.get_channel_videos(channel_id, max_results=12)
            video_ids = [v.get("id") for v in videos if v.get("id")]
            if not video_ids:
                continue
            details = client.get_video_details(video_ids)
            for video in videos:
                video_id = video.get("id")
                if not video_id:
                    continue
                detail = details.get(video_id, {})
                views = _safe_int(detail.get("view_count", 0))
                if views <= 0:
                    continue
                likes = _safe_int(detail.get("like_count", 0))
                comments = _safe_int(detail.get("comment_count", 0))
                duration_seconds = _safe_int(detail.get("duration_seconds", 0))
                row_format = _infer_format(duration_seconds)
                like_rate = likes / max(views, 1)
                comment_rate = comments / max(views, 1)
                engagement_rate = (likes + (comments * 2.0)) / max(views, 1)
                samples.append(
                    {
                        "channel_id": channel_id,
                        "format_type": row_format,
                        "views": views,
                        "like_rate": like_rate,
                        "comment_rate": comment_rate,
                        "engagement_rate": engagement_rate,
                    }
                )
        except Exception as exc:
            logger.warning(f"Error fetching benchmark data for competitor {channel_id}: {exc}")

    if not samples:
        return {
            "has_data": False,
            "sample_size": 0,
            "competitor_count": len(competitors),
            "avg_views": 0.0,
            "avg_like_rate": 0.0,
            "avg_comment_rate": 0.0,
            "avg_engagement_rate": 0.0,
            "difficulty_score": 55.0,
            "used_format_filter": False,
            "format_type": format_type,
            "summary": "Competitors connected, but no usable public video metrics were found.",
        }

    filtered = samples
    used_format_filter = False
    if format_type in {"short_form", "long_form"}:
        format_filtered = [s for s in samples if s["format_type"] == format_type]
        if format_filtered:
            filtered = format_filtered
            used_format_filter = True

    avg_views = sum(s["views"] for s in filtered) / len(filtered)
    avg_like_rate = sum(s["like_rate"] for s in filtered) / len(filtered)
    avg_comment_rate = sum(s["comment_rate"] for s in filtered) / len(filtered)
    avg_engagement_rate = sum(s["engagement_rate"] for s in filtered) / len(filtered)
    difficulty_score = _clamp(
        45.0
        + min(avg_views / 15000.0, 25.0)
        + min(avg_engagement_rate * 900.0, 18.0)
        + min(avg_comment_rate * 2500.0, 12.0),
        45.0,
        95.0,
    )

    return {
        "has_data": True,
        "sample_size": len(filtered),
        "competitor_count": len({s["channel_id"] for s in filtered}),
        "avg_views": round(avg_views, 2),
        "avg_like_rate": round(avg_like_rate, 4),
        "avg_comment_rate": round(avg_comment_rate, 4),
        "avg_engagement_rate": round(avg_engagement_rate, 4),
        "difficulty_score": round(difficulty_score, 1),
        "used_format_filter": used_format_filter,
        "format_type": format_type,
        "summary": (
            f"Benchmark built from {len(filtered)} competitor videos"
            f"{' matching this format' if used_format_filter else ''}."
        ),
    }


def _build_competitor_metrics(platform_score: float, benchmark: Dict[str, Any]) -> Dict[str, Any]:
    difficulty_score = _safe_float(benchmark.get("difficulty_score", 55.0), 55.0)
    adjusted_score = _clamp(platform_score + (70.0 - difficulty_score))
    band = _score_band(adjusted_score)

    summary = (
        "Competitor-aligned score estimates how likely this video can compete against currently tracked channel baselines."
    )
    if not benchmark.get("has_data"):
        summary = (
            "Competitor score is using fallback baseline because competitor data was unavailable; "
            "connect competitors for higher-confidence predictions."
        )

    return {
        "score": round(adjusted_score, 1),
        "confidence": "high" if benchmark.get("sample_size", 0) >= 20 else "medium" if benchmark.get("sample_size", 0) >= 8 else "low",
        "summary": summary,
        "benchmark": {
            "sample_size": benchmark.get("sample_size", 0),
            "competitor_count": benchmark.get("competitor_count", 0),
            "avg_views": benchmark.get("avg_views", 0.0),
            "avg_like_rate": benchmark.get("avg_like_rate", 0.0),
            "avg_comment_rate": benchmark.get("avg_comment_rate", 0.0),
            "avg_engagement_rate": benchmark.get("avg_engagement_rate", 0.0),
            "difficulty_score": difficulty_score,
            "used_format_filter": benchmark.get("used_format_filter", False),
        },
        "signals": [
            f"Target format benchmark: {_format_label(str(benchmark.get('format_type', 'unknown')))}",
            f"Competitive difficulty: {round(difficulty_score, 1)}/100 ({band})",
        ],
    }


async def _build_performance_prediction(
    user_id: str,
    video_analysis: Dict[str, Any],
    duration_seconds: int,
    detectors: Dict[str, Any],
    retention_points: List[Dict[str, Any]],
    platform_metrics: Dict[str, Any],
) -> Dict[str, Any]:
    format_type = _infer_format(duration_seconds)
    platform_score = _build_platform_metrics(video_analysis, detectors, retention_points, platform_metrics)
    benchmark = await _collect_competitor_benchmark(user_id, format_type)
    competitor_metrics = _build_competitor_metrics(platform_score["score"], benchmark)

    combined_score = _clamp((competitor_metrics["score"] * 0.55) + (platform_score["score"] * 0.45))
    score_band = _score_band(combined_score)

    return {
        "format_type": format_type,
        "duration_seconds": duration_seconds,
        "competitor_metrics": competitor_metrics,
        "platform_metrics": platform_score,
        "combined_metrics": {
            "score": round(combined_score, 1),
            "confidence": (
                "high"
                if benchmark.get("sample_size", 0) >= 20
                else "medium"
                if benchmark.get("sample_size", 0) >= 8
                else "low"
            ),
            "likelihood_band": score_band,
            "summary": (
                "Combined prediction blends competitor benchmark score and platform quality score "
                "to estimate near-term performance potential."
            ),
            "weights": {
                "competitor_metrics": 0.55,
                "platform_metrics": 0.45,
            },
        },
        "repurpose_plan": _build_repurpose_plan(video_analysis, detectors, format_type),
    }


async def process_video_audit(
    audit_id: str,
    video_url: Optional[str] = None,
    upload_path: Optional[str] = None,
    source_mode: str = "url",
):
    """
    Background task to process a multimodal audit from URL or uploaded file.
    """
    async with async_session_maker() as db:
        temp_dir = f"/tmp/spc_audit_{audit_id}"
        frames_dir = os.path.join(temp_dir, "frames")
        audio_path = os.path.join(temp_dir, "audio.mp3")

        try:
            result_audit = await db.execute(select(Audit).where(Audit.id == audit_id))
            audit = result_audit.scalar_one_or_none()
            if not audit:
                logger.error(f"Audit record {audit_id} not found; aborting background task")
                return

            logger.info(
                f"Starting audit {audit_id} source_mode={source_mode} video_url={video_url or 'n/a'} upload_path={upload_path or 'n/a'}"
            )
            await _update_status(db, audit_id, "downloading", 10)

            if not os.path.exists(temp_dir):
                os.makedirs(temp_dir)

            if source_mode == "upload":
                if not upload_path or not os.path.exists(upload_path):
                    raise FileNotFoundError("Uploaded file not found for this audit")
                suffix = Path(upload_path).suffix or ".mp4"
                working_video_path = os.path.join(temp_dir, f"video{suffix}")
                await asyncio.to_thread(shutil.copy2, upload_path, working_video_path)
            else:
                if not video_url:
                    raise ValueError("video_url is required for URL audits")
                working_video_path = os.path.join(temp_dir, "video.mp4")
                working_video_path = await asyncio.to_thread(download_video, video_url, working_video_path)

            duration_seconds = await asyncio.to_thread(get_video_duration_seconds, working_video_path)

            await _update_status(db, audit_id, "processing_video", 30)
            frames = await asyncio.to_thread(extract_frames, working_video_path, frames_dir, 5)
            logger.info(f"Extracted {len(frames)} frames for audit {audit_id}")

            await _update_status(db, audit_id, "processing_audio", 50)
            await asyncio.to_thread(extract_audio, working_video_path, audio_path)

            api_key = settings.OPENAI_API_KEY
            transcript = await asyncio.to_thread(transcribe_audio, audio_path, api_key)
            logger.info(f"Audio transcription complete for audit {audit_id}")

            await _update_status(db, audit_id, "analyzing", 70)
            title_hint = "Uploaded Video" if source_mode == "upload" else "Unknown Video"
            if isinstance(audit.input_json, dict):
                title_hint = audit.input_json.get("upload_file_name") or title_hint
            metadata = {
                "title": title_hint,
                "url": video_url,
                "id": audit_id,
                "source_mode": source_mode,
            }

            result = await asyncio.to_thread(analyze_content, frames, transcript, metadata, api_key)
            video_analysis = result.model_dump()
            input_payload = audit.input_json if isinstance(audit.input_json, dict) else {}
            retention_points = input_payload.get("retention_points", []) or []
            platform_metrics_input = input_payload.get("platform_metrics", {}) or {}
            explicit_detectors = _extract_explicit_detectors(
                transcript=transcript,
                video_analysis=video_analysis,
                duration_seconds=duration_seconds,
            )
            performance_prediction = await _build_performance_prediction(
                user_id=audit.user_id,
                video_analysis=video_analysis,
                duration_seconds=duration_seconds,
                detectors=explicit_detectors,
                retention_points=retention_points,
                platform_metrics=platform_metrics_input,
            )

            audit.status = "completed"
            audit.progress = "100"
            audit.output_json = {
                **video_analysis,
                "video_analysis": video_analysis,
                "explicit_detectors": explicit_detectors,
                "performance_prediction": performance_prediction,
            }
            audit.completed_at = datetime.now(timezone.utc)
            await db.commit()

            logger.info(f"Audit {audit_id} completed successfully")

        except Exception as e:
            logger.error(f"Audit {audit_id} failed: {e}")
            result_audit = await db.execute(select(Audit).where(Audit.id == audit_id))
            audit = result_audit.scalar_one_or_none()
            if audit:
                audit.status = "failed"
                audit.error_message = str(e)
                await db.commit()

        finally:
            if os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                except Exception as e:
                    logger.error(f"Error cleaning up temp dir: {e}")


async def _update_status(db, audit_id: str, status: str, progress: int):
    result = await db.execute(select(Audit).where(Audit.id == audit_id))
    audit = result.scalar_one_or_none()
    if audit:
        audit.status = status
        audit.progress = str(progress)
        await db.commit()
