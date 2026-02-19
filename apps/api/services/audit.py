import asyncio
import logging
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import or_
from sqlalchemy.future import select

from config import settings, require_youtube_api_key
from database import async_session_maker
from models.audit import Audit
from models.competitor import Competitor
from models.outcome_metric import OutcomeMetric
from models.profile import Profile
from models.research_item import ResearchItem
from models.video import Video
from models.video_metrics import VideoMetrics
from ingestion.youtube import create_youtube_client_with_api_key
from multimodal.audio import extract_audio, transcribe_audio
from multimodal.llm import analyze_content
from multimodal.video import download_video, extract_frames, get_video_duration_seconds

logger = logging.getLogger(__name__)

SHORT_FORM_MAX_SECONDS = 60
DETECTOR_ORDER = [
    "time_to_value",
    "open_loops",
    "dead_zones",
    "pattern_interrupts",
    "cta_style",
]
DETECTOR_LABELS = {
    "time_to_value": "Time to Value",
    "open_loops": "Open Loops",
    "dead_zones": "Dead Zones",
    "pattern_interrupts": "Pattern Interrupts",
    "cta_style": "CTA Style",
}
DETECTOR_TARGET_SCORES = {
    "time_to_value": 85.0,
    "open_loops": 78.0,
    "dead_zones": 82.0,
    "pattern_interrupts": 80.0,
    "cta_style": 76.0,
}
DETECTOR_WEIGHT_MAP = {
    "short_form": {
        "time_to_value": 0.32,
        "open_loops": 0.16,
        "dead_zones": 0.22,
        "pattern_interrupts": 0.20,
        "cta_style": 0.10,
    },
    "long_form": {
        "time_to_value": 0.24,
        "open_loops": 0.14,
        "dead_zones": 0.30,
        "pattern_interrupts": 0.18,
        "cta_style": 0.14,
    },
}


def _get_youtube_client():
    api_key = require_youtube_api_key()
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


def _extract_youtube_video_id(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    text = str(url).strip()
    if not text:
        return None

    patterns = [
        r"(?:v=)([A-Za-z0-9_-]{11})",
        r"(?:youtu\.be/)([A-Za-z0-9_-]{11})",
        r"(?:shorts/)([A-Za-z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return None


def _infer_source_platform(video_url: Optional[str], requested_platform: Optional[str] = None) -> str:
    platform_hint = str(requested_platform or "").strip().lower()
    if platform_hint in {"youtube", "instagram", "tiktok"}:
        return platform_hint

    text = str(video_url or "").strip().lower()
    if "instagram.com" in text:
        return "instagram"
    if "tiktok.com" in text:
        return "tiktok"
    if "youtube.com" in text or "youtu.be" in text:
        return "youtube"
    return "youtube"


def _median(values: List[float]) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    mid = len(sorted_values) // 2
    if len(sorted_values) % 2:
        return float(sorted_values[mid])
    return float((sorted_values[mid - 1] + sorted_values[mid]) / 2.0)


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


def _detector_weights_for_format(format_type: str) -> Dict[str, float]:
    if format_type == "short_form":
        return DETECTOR_WEIGHT_MAP["short_form"]
    if format_type == "long_form":
        return DETECTOR_WEIGHT_MAP["long_form"]

    short = DETECTOR_WEIGHT_MAP["short_form"]
    long = DETECTOR_WEIGHT_MAP["long_form"]
    return {
        key: round((short[key] + long[key]) / 2.0, 3)
        for key in DETECTOR_ORDER
    }


def _detector_priority(impact: float) -> str:
    if impact >= 18.0:
        return "critical"
    if impact >= 12.0:
        return "high"
    if impact >= 7.0:
        return "medium"
    return "low"


def _detector_evidence_and_edits(
    detector_key: str,
    detector_payload: Dict[str, Any],
    format_type: str,
) -> Tuple[List[str], List[str]]:
    if detector_key == "time_to_value":
        seconds = _safe_float(detector_payload.get("seconds"), 0.0)
        return (
            [
                f"First value lands at {round(seconds, 2)}s.",
                f"Assessment is '{detector_payload.get('assessment', 'unknown')}'.",
                "Earlier payoff consistently improves hold in the first 3 seconds.",
            ],
            [
                "Rewrite the first spoken line as outcome + proof in one sentence.",
                "Place strongest visual/result in frame 1 and mirror it in on-screen text.",
                "Cut setup sentences until value lands before second 3 for short-form or second 5 for long-form.",
            ],
        )

    if detector_key == "open_loops":
        count = _safe_int(detector_payload.get("count"), 0)
        return (
            [
                f"Detected {count} open-loop teaser(s).",
                "Open loops increase completion when payoff is delivered quickly.",
            ],
            [
                "Add one teaser line in the first 5 seconds that promises a concrete payoff.",
                "Resolve each teaser before mid-video to avoid viewer frustration.",
                "Avoid stacking more than two loops in one clip.",
            ],
        )

    if detector_key == "dead_zones":
        count = _safe_int(detector_payload.get("count"), 0)
        total = _safe_float(detector_payload.get("total_seconds"), 0.0)
        pace_hint = "every 1-2 seconds" if format_type == "short_form" else "every 10-20 seconds"
        return (
            [
                f"Detected {count} dead-zone segment(s) totaling {round(total, 2)}s.",
                "Dead zones correlate with retention cliffs and lower rewatch signals.",
            ],
            [
                "Trim low-information pauses and filler phrases around detected dead zones.",
                f"Insert visual/pattern shifts {pace_hint} to reset attention.",
                "Overlay captions or proof visuals during slower spoken sections.",
            ],
        )

    if detector_key == "pattern_interrupts":
        per_minute = _safe_float(detector_payload.get("interrupts_per_minute"), 0.0)
        return (
            [
                f"Pattern interrupts are {round(per_minute, 2)} per minute.",
                f"Assessment is '{detector_payload.get('assessment', 'unknown')}'.",
            ],
            [
                "Insert planned interrupt beats (camera/angle/text/pace change) at fixed intervals.",
                "Move strongest proof element immediately before likely drop points.",
                "Alternate sentence length and shot framing to avoid monotony.",
            ],
        )

    if detector_key == "cta_style":
        style = str(detector_payload.get("style", "none") or "none").replace("_", " ")
        return (
            [
                f"Detected CTA style: {style}.",
                "Single-intent CTA generally outperforms stacked CTA asks.",
            ],
            [
                "Pick one CTA objective only (comment, save/share, follow, or link action).",
                "Phrase CTA as a concrete prompt tied to the promise of the video.",
                "Place CTA in final 10-15% with one-line framing and no extra asks.",
            ],
        )

    return (["No detector evidence available."], ["No suggested edits available."])


def _build_detector_rankings(
    detectors: Dict[str, Any],
    format_type: str,
) -> Tuple[List[Dict[str, Any]], float, float, Dict[str, float]]:
    weights = _detector_weights_for_format(format_type)

    weighted_score = 0.0
    average_scores: List[float] = []
    rankings: List[Dict[str, Any]] = []
    for detector_key in DETECTOR_ORDER:
        payload = detectors.get(detector_key, {}) if isinstance(detectors, dict) else {}
        score = _clamp(_safe_float(payload.get("score"), 0.0), 0.0, 100.0)
        target_score = _safe_float(DETECTOR_TARGET_SCORES.get(detector_key, 80.0), 80.0)
        gap = max(0.0, target_score - score)
        normalized_gap = gap / max(target_score, 1.0)
        weight = _safe_float(weights.get(detector_key), 0.0)
        impact = normalized_gap * weight * 100.0
        estimated_lift = min(12.0, normalized_gap * weight * 65.0)
        priority = _detector_priority(impact)
        evidence, edits = _detector_evidence_and_edits(detector_key, payload if isinstance(payload, dict) else {}, format_type)
        rankings.append(
            {
                "detector_key": detector_key,
                "label": DETECTOR_LABELS.get(detector_key, detector_key),
                "score": round(score, 1),
                "target_score": round(target_score, 1),
                "gap": round(gap, 1),
                "weight": round(weight, 3),
                "priority": priority,
                "estimated_lift_points": round(estimated_lift, 1),
                "evidence": evidence,
                "edits": edits,
                "_impact": impact,
            }
        )
        weighted_score += score * weight
        average_scores.append(score)

    rankings.sort(
        key=lambda row: (
            _safe_float(row["_impact"], 0.0),
            _safe_float(row.get("gap"), 0.0),
            _safe_float(row.get("weight"), 0.0),
        ),
        reverse=True,
    )

    for idx, row in enumerate(rankings):
        row["rank"] = idx + 1
        row.pop("_impact", None)

    explicit_detector_score = sum(average_scores) / max(len(average_scores), 1)
    return rankings, _clamp(weighted_score), round(explicit_detector_score, 1), weights


def _build_next_actions(
    detector_rankings: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    actions: List[Dict[str, Any]] = []
    for row in detector_rankings:
        gap = _safe_float(row.get("gap"), 0.0)
        if gap <= 0:
            continue
        execution_steps = [str(step) for step in row.get("edits", []) if str(step).strip()]
        evidence = [str(item) for item in row.get("evidence", []) if str(item).strip()]
        actions.append(
            {
                "title": f"Improve {row.get('label', 'detector signal')}",
                "detector_key": str(row.get("detector_key", "")),
                "priority": str(row.get("priority", "low")),
                "why": evidence[0] if evidence else "This detector is below the target benchmark.",
                "expected_lift_points": _safe_float(row.get("estimated_lift_points"), 0.0),
                "execution_steps": execution_steps,
                "evidence": evidence,
            }
        )
        if len(actions) >= 3:
            break
    return actions


def _build_platform_metrics(
    video_analysis: Dict[str, Any],
    detectors: Dict[str, Any],
    retention_points: List[Dict[str, Any]],
    platform_metrics: Dict[str, Any],
    format_type: str,
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

    detector_rankings, detector_weighted_score, explicit_detector_score, detector_weights = _build_detector_rankings(
        detectors=detectors,
        format_type=format_type,
    )
    score = _clamp((base_score * 0.75) + (detector_weighted_score * 0.25))

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
            "explicit_detector_score": explicit_detector_score,
            "detector_weighted_score": round(detector_weighted_score, 1),
            "detector_weight_breakdown": detector_weights,
            "hook_strength": round(hook_strength, 1),
            "pacing_strength": round(pacing_strength, 1),
            "timestamp_positive_signals": positives,
            "timestamp_negative_signals": negatives,
        },
        "detectors": detectors,
        "detector_rankings": detector_rankings,
        "metric_coverage": metric_coverage,
        "true_metrics": true_metrics if true_metrics else None,
        "true_metric_notes": true_signal_notes,
    }


async def _load_true_platform_metrics_for_video(
    user_id: str,
    video_url: Optional[str],
    platform: str = "youtube",
) -> Dict[str, Any]:
    """Load latest persisted platform metrics for a specific user video URL."""
    if platform != "youtube":
        return {}
    video_id = _extract_youtube_video_id(video_url)
    if not video_id:
        return {}

    async with async_session_maker() as db:
        result = await db.execute(
            select(
                VideoMetrics.views,
                VideoMetrics.likes,
                VideoMetrics.comments,
                VideoMetrics.shares,
                VideoMetrics.saves,
                VideoMetrics.watch_time_hours,
                VideoMetrics.avg_view_duration_s,
                VideoMetrics.ctr,
                VideoMetrics.retention_points_json,
            )
            .join(Video, Video.id == VideoMetrics.video_id)
            .outerjoin(Profile, Profile.id == Video.profile_id)
            .where(
                Video.external_id == video_id,
                Video.platform == "youtube",
                or_(Profile.user_id == user_id, Profile.user_id.is_(None)),
            )
            .order_by(VideoMetrics.fetched_at.desc())
            .limit(1)
        )
        row = result.first()

    if not row:
        return {}

    retention_points = row[8] if isinstance(row[8], list) else []
    return {
        "views": _safe_int(row[0], 0),
        "likes": _safe_int(row[1], 0),
        "comments": _safe_int(row[2], 0),
        "shares": _safe_int(row[3], 0),
        "saves": _safe_int(row[4], 0),
        "watch_time_hours": _safe_float(row[5], 0.0) if row[5] is not None else None,
        "avg_view_duration_s": _safe_float(row[6], 0.0) if row[6] is not None else None,
        "ctr": _safe_float(row[7], 0.0) if row[7] is not None else None,
        "retention_points": retention_points,
    }


async def _collect_historical_performance(
    user_id: str,
    format_type: str,
    platform: str = "youtube",
) -> Dict[str, Any]:
    """Build user historical baseline from persisted posted-video metrics."""
    if platform in {"instagram", "tiktok"}:
        async with async_session_maker() as db:
            result = await db.execute(
                select(
                    OutcomeMetric.actual_metrics_json,
                    OutcomeMetric.actual_score,
                    OutcomeMetric.retention_points_json,
                )
                .where(
                    OutcomeMetric.user_id == user_id,
                    OutcomeMetric.platform == platform,
                )
                .order_by(OutcomeMetric.created_at.desc())
                .limit(120)
            )
            rows = result.all()

        if not rows:
            return {
                "sample_size": 0,
                "format_sample_size": 0,
                "score": 0.0,
                "confidence": "low",
                "insufficient_data": True,
                "summary": f"No historical {platform} posted metrics found yet.",
                "signals": [],
            }

        weighted_rates: List[float] = []
        actual_scores: List[float] = []
        retention_coverage = 0
        for row in rows:
            metrics = row[0] if isinstance(row[0], dict) else {}
            views = _safe_float(metrics.get("views"), 0.0)
            likes = _safe_float(metrics.get("likes"), 0.0)
            comments = _safe_float(metrics.get("comments"), 0.0)
            shares = _safe_float(metrics.get("shares"), 0.0)
            saves = _safe_float(metrics.get("saves"), 0.0)
            weighted_rates.append((likes + (comments * 2.0) + (shares * 3.0) + (saves * 3.0)) / max(views, 1.0))
            actual_scores.append(_safe_float(row[1], 0.0))
            if isinstance(row[2], list) and row[2]:
                retention_coverage += 1

        sample_size = len(rows)
        avg_weighted_rate = sum(weighted_rates) / max(sample_size, 1)
        avg_actual_score = sum(actual_scores) / max(sample_size, 1)
        retention_ratio = retention_coverage / max(sample_size, 1)
        historical_score = _clamp(
            (avg_actual_score * 0.75)
            + min(avg_weighted_rate * 1200.0, 20.0)
            + (retention_ratio * 5.0)
        )
        confidence = "high" if sample_size >= 20 else "medium" if sample_size >= 8 else "low"
        insufficient_data = sample_size < 5
        return {
            "sample_size": sample_size,
            "format_sample_size": sample_size,
            "score": round(historical_score, 1),
            "confidence": confidence,
            "insufficient_data": insufficient_data,
            "summary": (
                f"Historical {platform} baseline calibrates prediction confidence from your posted outcomes."
                if not insufficient_data
                else f"Historical {platform} baseline has limited samples; confidence is reduced."
            ),
            "signals": [
                f"Historical sample size: {sample_size} {platform} posts",
                f"Average actual score: {round(avg_actual_score, 1)}",
                f"Weighted engagement rate: {round(avg_weighted_rate, 4)}",
                f"Retention-curve coverage: {round(retention_ratio * 100, 1)}%",
            ],
        }

    async with async_session_maker() as db:
        result = await db.execute(
            select(
                Video.duration_s,
                VideoMetrics.views,
                VideoMetrics.likes,
                VideoMetrics.comments,
                VideoMetrics.shares,
                VideoMetrics.saves,
                VideoMetrics.avg_view_duration_s,
                VideoMetrics.retention_points_json,
            )
            .join(VideoMetrics, VideoMetrics.video_id == Video.id)
            .join(Profile, Profile.id == Video.profile_id)
            .where(
                Profile.user_id == user_id,
                Video.platform == platform,
                VideoMetrics.views > 0,
            )
            .order_by(VideoMetrics.fetched_at.desc())
            .limit(120)
        )
        rows = result.all()

    if not rows:
        return {
            "sample_size": 0,
            "format_sample_size": 0,
            "score": 0.0,
            "confidence": "low",
            "insufficient_data": True,
            "summary": "No historical posted-video metrics found yet.",
            "signals": [],
        }

    records: List[Dict[str, Any]] = []
    for row in rows:
        duration_s = _safe_int(row[0], 0)
        row_format = _infer_format(duration_s)
        views = _safe_float(row[1], 0.0)
        likes = _safe_float(row[2], 0.0)
        comments = _safe_float(row[3], 0.0)
        shares = _safe_float(row[4], 0.0)
        saves = _safe_float(row[5], 0.0)
        avg_view_duration_s = _safe_float(row[6], 0.0)
        retention_points = row[7] if isinstance(row[7], list) else []
        weighted_rate = (likes + (comments * 2.0) + (shares * 3.0) + (saves * 3.0)) / max(views, 1.0)
        records.append(
            {
                "format_type": row_format,
                "views": views,
                "weighted_rate": weighted_rate,
                "avg_view_duration_s": avg_view_duration_s,
                "has_retention": bool(retention_points),
            }
        )

    filtered = records
    format_sample_size = len(records)
    if format_type in {"short_form", "long_form"}:
        format_filtered = [row for row in records if row["format_type"] == format_type]
        if format_filtered:
            filtered = format_filtered
            format_sample_size = len(format_filtered)

    median_views = _median([row["views"] for row in filtered])
    avg_weighted_rate = sum(row["weighted_rate"] for row in filtered) / max(len(filtered), 1)
    avg_view_duration = sum(row["avg_view_duration_s"] for row in filtered) / max(len(filtered), 1)
    retention_ratio = sum(1 for row in filtered if row["has_retention"]) / max(len(filtered), 1)

    historical_score = _clamp(
        min(median_views / 2500.0, 35.0)
        + min(avg_weighted_rate * 1400.0, 35.0)
        + min(avg_view_duration / 1.5, 20.0)
        + (retention_ratio * 10.0)
    )

    confidence = "high" if format_sample_size >= 18 else "medium" if format_sample_size >= 8 else "low"
    insufficient_data = format_sample_size < 5
    return {
        "sample_size": len(records),
        "format_sample_size": format_sample_size,
        "score": round(historical_score, 1),
        "confidence": confidence,
        "insufficient_data": insufficient_data,
        "summary": (
            "Historical baseline uses your posted video outcomes to calibrate prediction confidence."
            if not insufficient_data
            else "Historical baseline has limited samples; confidence is reduced until more posted data is ingested."
        ),
        "signals": [
            f"Historical sample size: {len(records)} videos (format-matched: {format_sample_size})",
            f"Median views: {round(median_views, 1)}",
            f"Weighted engagement rate: {round(avg_weighted_rate, 4)}",
            f"Retention-curve coverage: {round(retention_ratio * 100, 1)}%",
        ],
    }


async def _collect_competitor_benchmark(
    user_id: str,
    format_type: str,
    platform: str = "youtube",
) -> Dict[str, Any]:
    if platform in {"instagram", "tiktok"}:
        async with async_session_maker() as db:
            competitors_result = await db.execute(
                select(Competitor).where(
                    Competitor.user_id == user_id,
                    Competitor.platform == platform,
                )
            )
            competitors = competitors_result.scalars().all()
            competitor_ids = {str(c.external_id) for c in competitors if c.external_id}
            competitor_handles = {str(c.handle).lower() for c in competitors if c.handle}

            items_result = await db.execute(
                select(ResearchItem).where(
                    ResearchItem.user_id == user_id,
                    ResearchItem.platform == platform,
                )
            )
            research_items = items_result.scalars().all()

        samples: List[Dict[str, Any]] = []
        for item in research_items:
            metrics = item.metrics_json if isinstance(item.metrics_json, dict) else {}
            views = _safe_int(metrics.get("views"), 0)
            if views <= 0:
                continue
            creator_handle = str(item.creator_handle or "").strip().lower()
            external_id = str(item.external_id or item.creator_handle or "").strip()
            if competitor_ids or competitor_handles:
                if external_id not in competitor_ids and creator_handle not in competitor_handles:
                    continue
            likes = _safe_int(metrics.get("likes"), 0)
            comments = _safe_int(metrics.get("comments"), 0)
            shares = _safe_int(metrics.get("shares"), 0)
            saves = _safe_int(metrics.get("saves"), 0)
            engagement_rate = (likes + (comments * 2.0) + (shares * 3.0) + (saves * 3.0)) / max(views, 1)
            samples.append(
                {
                    "channel_id": external_id or creator_handle or "unknown",
                    "format_type": format_type,
                    "views": views,
                    "like_rate": likes / max(views, 1),
                    "comment_rate": comments / max(views, 1),
                    "engagement_rate": engagement_rate,
                }
            )

        if not samples:
            return {
                "has_data": False,
                "sample_size": 0,
                "competitor_count": len(competitors) if "competitors" in locals() else 0,
                "avg_views": 0.0,
                "avg_like_rate": 0.0,
                "avg_comment_rate": 0.0,
                "avg_engagement_rate": 0.0,
                "difficulty_score": 55.0,
                "used_format_filter": False,
                "format_type": format_type,
                "summary": f"No usable {platform} competitor research metrics found yet.",
            }

        avg_views = sum(s["views"] for s in samples) / len(samples)
        avg_like_rate = sum(s["like_rate"] for s in samples) / len(samples)
        avg_comment_rate = sum(s["comment_rate"] for s in samples) / len(samples)
        avg_engagement_rate = sum(s["engagement_rate"] for s in samples) / len(samples)
        difficulty_score = _clamp(
            43.0
            + min(avg_views / 18000.0, 22.0)
            + min(avg_engagement_rate * 950.0, 20.0)
            + min(avg_comment_rate * 2600.0, 10.0),
            43.0,
            95.0,
        )
        return {
            "has_data": True,
            "sample_size": len(samples),
            "competitor_count": len({s["channel_id"] for s in samples}),
            "avg_views": round(avg_views, 2),
            "avg_like_rate": round(avg_like_rate, 4),
            "avg_comment_rate": round(avg_comment_rate, 4),
            "avg_engagement_rate": round(avg_engagement_rate, 4),
            "difficulty_score": round(difficulty_score, 1),
            "used_format_filter": False,
            "format_type": format_type,
            "summary": f"{platform.capitalize()} benchmark built from imported competitor research metadata.",
        }

    async with async_session_maker() as db:
        result = await db.execute(
            select(Competitor).where(
                Competitor.user_id == user_id,
                Competitor.platform == platform,
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
    content_platform: str = "youtube",
) -> Dict[str, Any]:
    format_type = _infer_format(duration_seconds)
    platform_score = _build_platform_metrics(
        video_analysis,
        detectors,
        retention_points,
        platform_metrics,
        format_type=format_type,
    )
    next_actions = _build_next_actions(platform_score.get("detector_rankings", []))
    benchmark = await _collect_competitor_benchmark(user_id, format_type, platform=content_platform)
    competitor_metrics = _build_competitor_metrics(platform_score["score"], benchmark)
    historical_metrics = await _collect_historical_performance(user_id, format_type, platform=content_platform)

    has_historical = not historical_metrics.get("insufficient_data", True)
    if has_historical:
        weights = {
            "competitor_metrics": 0.45,
            "platform_metrics": 0.35,
            "historical_metrics": 0.20,
        }
    else:
        weights = {
            "competitor_metrics": 0.55,
            "platform_metrics": 0.45,
            "historical_metrics": 0.0,
        }

    combined_score = _clamp(
        (competitor_metrics["score"] * weights["competitor_metrics"])
        + (platform_score["score"] * weights["platform_metrics"])
        + (_safe_float(historical_metrics.get("score"), 0.0) * weights["historical_metrics"])
    )
    score_band = _score_band(combined_score)
    confidence_rank = {"low": 1, "medium": 2, "high": 3}
    competitor_conf = str(competitor_metrics.get("confidence", "low"))
    historical_conf = str(historical_metrics.get("confidence", "low"))
    combined_conf_score = min(confidence_rank.get(competitor_conf, 1), confidence_rank.get(historical_conf, 1))
    if not has_historical:
        combined_conf_score = min(combined_conf_score, 2)
    combined_confidence = "high" if combined_conf_score >= 3 else "medium" if combined_conf_score == 2 else "low"
    insufficient_data_reasons: List[str] = []
    if benchmark.get("sample_size", 0) < 8:
        insufficient_data_reasons.append("Competitor benchmark sample is below 8 videos.")
    if historical_metrics.get("insufficient_data"):
        insufficient_data_reasons.append("Historical posted-video sample is below 5 format-matched videos.")

    return {
        "platform": content_platform,
        "format_type": format_type,
        "duration_seconds": duration_seconds,
        "competitor_metrics": competitor_metrics,
        "platform_metrics": platform_score,
        "historical_metrics": historical_metrics,
        "combined_metrics": {
            "score": round(combined_score, 1),
            "confidence": combined_confidence,
            "likelihood_band": score_band,
            "summary": (
                "Combined prediction blends competitor benchmark score and platform quality score "
                "plus historical posted-video performance calibration to estimate near-term performance potential."
            ),
            "weights": weights,
            "insufficient_data": len(insufficient_data_reasons) > 0,
            "insufficient_data_reasons": insufficient_data_reasons,
        },
        "repurpose_plan": _build_repurpose_plan(video_analysis, detectors, format_type),
        "next_actions": next_actions,
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
            content_platform = _infer_source_platform(
                video_url if source_mode == "url" else None,
                requested_platform=input_payload.get("platform"),
            )
            retention_points = input_payload.get("retention_points", []) or []
            platform_metrics_input = input_payload.get("platform_metrics", {}) or {}
            persisted_true_metrics = await _load_true_platform_metrics_for_video(
                audit.user_id,
                video_url if source_mode == "url" else None,
                platform=content_platform,
            )
            if persisted_true_metrics:
                logger.info(
                    "Audit %s loaded persisted true metrics for URL video id",
                    audit_id,
                )
                if not retention_points and isinstance(persisted_true_metrics.get("retention_points"), list):
                    retention_points = persisted_true_metrics.get("retention_points", [])
                platform_metrics_input = {
                    **persisted_true_metrics,
                    **platform_metrics_input,
                }
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
                content_platform=content_platform,
            )
            detector_rankings = (
                performance_prediction.get("platform_metrics", {}).get("detector_rankings", [])
                if isinstance(performance_prediction, dict)
                else []
            )
            next_actions = (
                performance_prediction.get("next_actions", [])
                if isinstance(performance_prediction, dict)
                else []
            )
            logger.info(
                "Audit %s ranking summary: detector_rankings=%s next_actions=%s top_priority=%s",
                audit_id,
                len(detector_rankings) if isinstance(detector_rankings, list) else 0,
                len(next_actions) if isinstance(next_actions, list) else 0,
                detector_rankings[0].get("priority") if isinstance(detector_rankings, list) and detector_rankings else "n/a",
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
            if source_mode == "upload" and settings.DELETE_UPLOAD_AFTER_AUDIT and upload_path:
                try:
                    Path(upload_path).unlink(missing_ok=True)
                except Exception as exc:
                    logger.warning("Could not delete upload source file for audit %s: %s", audit_id, exc)
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


def process_video_audit_job(
    audit_id: str,
    video_url: Optional[str] = None,
    upload_path: Optional[str] = None,
    source_mode: str = "url",
):
    """RQ worker entrypoint for running the async audit pipeline."""
    asyncio.run(
        process_video_audit(
            audit_id=audit_id,
            video_url=video_url,
            upload_path=upload_path,
            source_mode=source_mode,
        )
    )
