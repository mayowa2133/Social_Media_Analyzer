"""Optimizer v2 services for script variant generation and draft re-scoring."""

from __future__ import annotations

import json
import logging
import math
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from config import settings
from models.draft_snapshot import DraftSnapshot
from models.research_item import ResearchItem
from models.script_variant import ScriptVariant
from services.audit import (
    _build_competitor_metrics,
    _build_next_actions,
    _build_platform_metrics,
    _collect_competitor_benchmark,
    _collect_historical_performance,
    _extract_explicit_detectors,
    _infer_format,
    _safe_float,
)

logger = logging.getLogger(__name__)

ALLOWED_PLATFORMS = {"youtube", "instagram", "tiktok"}
DEFAULT_DURATION_SECONDS = {
    "youtube": 45,
    "instagram": 35,
    "tiktok": 30,
}
DEFAULT_GENERATION_MODE = "ai_first_fallback"
AI_MODEL_NAME = "gpt-4o"

VARIANT_STYLES = [
    ("variant_a", "Outcome + Proof"),
    ("variant_b", "Curiosity Gap"),
    ("variant_c", "Contrarian Take"),
]


def _assert_optimizer_enabled() -> None:
    if not settings.OPTIMIZER_V2_ENABLED:
        raise HTTPException(status_code=503, detail="Optimizer v2 disabled by feature flag.")


def _normalize_platform(value: Optional[str]) -> str:
    text = str(value or "youtube").strip().lower()
    if text in ALLOWED_PLATFORMS:
        return text
    aliases = {
        "youtube_shorts": "youtube",
        "youtube_long": "youtube",
        "instagram_reels": "instagram",
        "reels": "instagram",
        "shorts": "youtube",
    }
    resolved = aliases.get(text)
    if resolved:
        return resolved
    raise HTTPException(status_code=422, detail="platform must be youtube, instagram, or tiktok")


def _clip(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_duration(duration_s: Optional[int], platform: str) -> int:
    default_value = DEFAULT_DURATION_SECONDS.get(platform, 45)
    if duration_s is None:
        return default_value
    duration = int(duration_s)
    return max(15, min(duration, 900))


def _split_lines(script_text: str) -> List[str]:
    rows = [line.strip() for line in script_text.splitlines() if line.strip()]
    if rows:
        return rows
    # Fallback for single-line scripts.
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", script_text) if part.strip()]


def _build_transcript_segments(script_text: str, duration_s: int) -> Dict[str, Any]:
    lines = _split_lines(script_text)
    if not lines:
        lines = ["Start with your strongest claim.", "Deliver one proof point.", "Close with one CTA."]

    weighted_lengths = [max(1, len(re.findall(r"\w+", line))) for line in lines]
    total_weight = float(sum(weighted_lengths) or 1)

    segments: List[Dict[str, Any]] = []
    cursor = 0.0
    for idx, line in enumerate(lines):
        weight = weighted_lengths[idx] / total_weight
        if idx == len(lines) - 1:
            end = float(duration_s)
        else:
            end = min(float(duration_s), cursor + max(1.5, round(duration_s * weight, 2)))
        if end <= cursor:
            end = min(float(duration_s), cursor + 1.5)
        segments.append({"start": round(cursor, 2), "end": round(end, 2), "text": line})
        cursor = end

    if segments:
        segments[-1]["end"] = float(duration_s)

    return {
        "text": " ".join(lines),
        "segments": segments,
    }


def _score_hook_quality(first_line: str) -> float:
    line = first_line.lower()
    score = 58.0
    if any(token in line for token in ("how", "why", "secret", "mistake", "stop", "boost", "grow")):
        score += 12.0
    if any(token in line for token in ("i tested", "i grew", "we tried", "proof", "results")):
        score += 14.0
    if len(re.findall(r"\d+", line)) > 0:
        score += 6.0
    return _clip(score)


def _score_body_quality(lines: List[str], duration_s: int) -> float:
    info_density = sum(len(re.findall(r"\w+", line)) for line in lines) / max(len(lines), 1)
    cadence = len(lines) / max(duration_s / 15.0, 1.0)
    score = 50.0 + min(info_density / 2.5, 22.0) + min(cadence * 8.0, 18.0)
    return _clip(score)


def _score_cta_quality(script_text: str) -> float:
    lower = script_text.lower()
    if any(token in lower for token in ("comment", "save", "share", "follow", "subscribe")):
        return 82.0
    if any(token in lower for token in ("link", "bio", "description")):
        return 74.0
    return 42.0


def _build_video_analysis(script_text: str, duration_s: int, platform: str) -> Dict[str, Any]:
    lines = _split_lines(script_text)
    first_line = lines[0] if lines else script_text
    hook_score = _score_hook_quality(first_line)
    body_score = _score_body_quality(lines, duration_s)
    cta_score = _score_cta_quality(script_text)

    overall_score_100 = (hook_score * 0.45) + (body_score * 0.35) + (cta_score * 0.20)
    overall_score_10 = round(overall_score_100 / 10.0, 2)

    return {
        "overall_score": overall_score_10,
        "summary": (
            f"Script-only simulation for {platform}. "
            "Rescore improves as hook clarity, pacing cadence, and CTA specificity improve."
        ),
        "sections": [
            {"name": "Hook", "score": round(hook_score / 10.0, 2)},
            {"name": "Body/Pacing", "score": round(body_score / 10.0, 2)},
            {"name": "CTA", "score": round(cta_score / 10.0, 2)},
        ],
        "timestamp_feedback": [],
    }


def _combined_score(
    competitor_score: float,
    platform_score: float,
    historical_score: float,
    historical_ready: bool,
) -> Tuple[float, Dict[str, float]]:
    if historical_ready:
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

    combined = (
        competitor_score * weights["competitor_metrics"]
        + platform_score * weights["platform_metrics"]
        + historical_score * weights["historical_metrics"]
    )
    return _clip(combined), weights


def _confidence_label(benchmark_samples: int, historical_confidence: str, historical_ready: bool) -> str:
    benchmark_conf = "high" if benchmark_samples >= 20 else "medium" if benchmark_samples >= 8 else "low"
    ranking = {"low": 1, "medium": 2, "high": 3}
    conf = min(ranking.get(benchmark_conf, 1), ranking.get(historical_confidence, 1))
    if not historical_ready:
        conf = min(conf, 2)
    return "high" if conf >= 3 else "medium" if conf == 2 else "low"


def _script_payload_for_style(
    *,
    style_key: str,
    topic: str,
    audience: str,
    objective: str,
    tone: str,
    duration_s: int,
    platform: str,
) -> Dict[str, Any]:
    platform_cta = {
        "youtube": "Comment 'PLAN' and I will post the exact template.",
        "instagram": "Save this and send it to one creator who needs it.",
        "tiktok": "Follow for part two and comment your niche.",
    }.get(platform, "Comment if you want the template.")

    tone_prefix = {
        "bold": "Straight truth:",
        "expert": "Data-backed insight:",
        "conversational": "Quick take:",
    }.get(str(tone).strip().lower(), "Quick take:")

    if style_key == "variant_a":
        hook = f"{tone_prefix} I used this {topic} play and saw measurable lift."
        setup = f"In {duration_s} seconds, I will show the 3-step framework for {audience}."
        value_lines = [
            "Step 1: Lead with outcome + proof in the first sentence.",
            "Step 2: Cut dead space and add a pattern interrupt before every likely drop.",
            f"Step 3: Close with one CTA tied to {objective}.",
        ]
        cta = platform_cta
        rationale = "Best for direct authority and fast proof."
    elif style_key == "variant_b":
        hook = f"Most creators miss this {topic} signal and lose reach in the first 3 seconds."
        setup = "Stay to the end because I will show the exact fix and where to place it."
        value_lines = [
            "Open loop: call out the hidden mistake before giving the fix.",
            "Deliver one concrete proof point and one copyable line.",
            f"Then use a single CTA that supports {objective}.",
        ]
        cta = platform_cta
        rationale = "Best for curiosity-driven retention and completion."
    else:
        hook = f"Stop copying viral formats blindly; your {topic} strategy needs this switch."
        setup = "Contrarian claim: shorter setup, earlier payoff, and fewer CTA asks outperform more editing tricks."
        value_lines = [
            f"For {audience}, run this sequence: claim -> proof -> 2 steps -> CTA.",
            "Use one strong visual interrupt where most viewers drop.",
            f"Measure success by {objective}, not by vanity spikes.",
        ]
        cta = platform_cta
        rationale = "Best for differentiated positioning and share triggers."

    script_text = "\n".join([hook, setup, *value_lines, cta])
    return {
        "style_key": style_key,
        "label": dict(VARIANT_STYLES).get(style_key, style_key),
        "script": script_text,
        "script_text": script_text,
        "structure": {
            "hook": hook,
            "setup": setup,
            "value": " ".join(value_lines),
            "cta": cta,
        },
        "rationale": rationale,
    }


def _normalize_generation_mode(value: Any) -> str:
    mode = _safe_text(value).lower() or DEFAULT_GENERATION_MODE
    if mode != DEFAULT_GENERATION_MODE:
        raise HTTPException(status_code=422, detail="generation_mode must be ai_first_fallback")
    return mode


def _normalize_constraints(payload: Dict[str, Any]) -> Dict[str, Any]:
    constraints = payload.get("constraints") if isinstance(payload.get("constraints"), dict) else {}
    platform = _normalize_platform(constraints.get("platform") or payload.get("platform"))
    duration_s = _normalize_duration(constraints.get("duration_s") or payload.get("duration_s"), platform)
    tone = _safe_text(constraints.get("tone") or payload.get("tone")) or "bold"
    return {
        "platform": platform,
        "duration_s": duration_s,
        "tone": tone,
        "hook_style": _safe_text(constraints.get("hook_style")) or None,
        "cta_style": _safe_text(constraints.get("cta_style")) or None,
        "pacing_density": _safe_text(constraints.get("pacing_density")) or None,
    }


def _variant_style_instructions() -> Dict[str, str]:
    return {
        "variant_a": "Outcome+Proof: lead with concrete claim + evidence quickly.",
        "variant_b": "Curiosity Gap: open loop in first 2 lines, then close the loop with proof.",
        "variant_c": "Contrarian Take: challenge common advice and present a clear alternative.",
    }


def _safe_script_payload_from_ai(
    *,
    style_key: str,
    raw_variant: Dict[str, Any],
    fallback: Dict[str, Any],
) -> Dict[str, Any]:
    hook = _safe_text(raw_variant.get("hook")) or fallback["structure"]["hook"]
    setup = _safe_text(raw_variant.get("setup")) or fallback["structure"]["setup"]
    value = _safe_text(raw_variant.get("value")) or fallback["structure"]["value"]
    cta = _safe_text(raw_variant.get("cta")) or fallback["structure"]["cta"]
    script_text = _safe_text(raw_variant.get("script_text")) or "\n".join([hook, setup, value, cta])
    if len(script_text) < 20:
        script_text = fallback["script_text"]
    return {
        "style_key": style_key,
        "label": fallback["label"],
        "rationale": _safe_text(raw_variant.get("rationale")) or fallback["rationale"],
        "script": script_text,
        "script_text": script_text,
        "structure": {
            "hook": hook,
            "setup": setup,
            "value": value,
            "cta": cta,
        },
    }


async def _load_source_context(
    *,
    user_id: str,
    source_item_id: Optional[str],
    db: AsyncSession,
) -> Optional[Dict[str, Any]]:
    if not source_item_id:
        return None
    result = await db.execute(
        select(ResearchItem).where(
            ResearchItem.id == source_item_id,
            ResearchItem.user_id == user_id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        return None
    metrics = item.metrics_json if isinstance(item.metrics_json, dict) else {}
    return {
        "title": item.title,
        "caption": item.caption,
        "creator_handle": item.creator_handle,
        "platform": item.platform,
        "views": metrics.get("views"),
        "likes": metrics.get("likes"),
        "comments": metrics.get("comments"),
        "shares": metrics.get("shares"),
        "saves": metrics.get("saves"),
    }


def _ai_variant_prompt(
    *,
    topic: str,
    audience: str,
    objective: str,
    constraints: Dict[str, Any],
    source_context: Optional[Dict[str, Any]],
) -> str:
    style_rules = _variant_style_instructions()
    return (
        "Generate EXACTLY 3 social video scripts in JSON only.\n"
        f"Topic: {topic}\n"
        f"Audience: {audience}\n"
        f"Objective: {objective}\n"
        f"Platform: {constraints['platform']}\n"
        f"Duration seconds: {constraints['duration_s']}\n"
        f"Tone: {constraints['tone']}\n"
        f"Hook style override: {constraints.get('hook_style') or 'none'}\n"
        f"CTA style override: {constraints.get('cta_style') or 'none'}\n"
        f"Pacing density override: {constraints.get('pacing_density') or 'none'}\n"
        f"Source context: {json.dumps(source_context or {}, ensure_ascii=True)}\n"
        "Variant strategy constraints:\n"
        f"- variant_a: {style_rules['variant_a']}\n"
        f"- variant_b: {style_rules['variant_b']}\n"
        f"- variant_c: {style_rules['variant_c']}\n"
        "Return schema:\n"
        "{\n"
        '  "variants": [\n'
        "    {\n"
        '      "style_key": "variant_a|variant_b|variant_c",\n'
        '      "hook": "string",\n'
        '      "setup": "string",\n'
        '      "value": "string",\n'
        '      "cta": "string",\n'
        '      "script_text": "string",\n'
        '      "rationale": "string"\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "Rules: distinct strategies, no markdown, no extra keys outside schema."
    )


async def _generate_ai_or_fallback_variants(
    *,
    topic: str,
    audience: str,
    objective: str,
    constraints: Dict[str, Any],
    source_context: Optional[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    fallbacks_by_style = {
        style_key: _script_payload_for_style(
            style_key=style_key,
            topic=topic,
            audience=audience,
            objective=objective,
            tone=constraints["tone"],
            duration_s=constraints["duration_s"],
            platform=constraints["platform"],
        )
        for style_key, _label in VARIANT_STYLES
    }

    from multimodal.llm import get_openai_client

    generation = {
        "mode": DEFAULT_GENERATION_MODE,
        "provider": "deterministic",
        "model": "deterministic-v1",
        "used_fallback": True,
        "fallback_reason": "OpenAI API key missing or unavailable",
    }

    client = get_openai_client(settings.OPENAI_API_KEY)
    if client is None:
        variants = [fallbacks_by_style[style_key] for style_key, _ in VARIANT_STYLES]
        return variants, generation

    try:
        response = client.chat.completions.create(
            model=AI_MODEL_NAME,
            messages=[{"role": "user", "content": _ai_variant_prompt(
                topic=topic,
                audience=audience,
                objective=objective,
                constraints=constraints,
                source_context=source_context,
            )}],
            response_format={"type": "json_object"},
        )
        raw_content = response.choices[0].message.content
        parsed = json.loads(raw_content or "{}")
        variants_raw = parsed.get("variants") if isinstance(parsed, dict) else None
        variants_by_style: Dict[str, Dict[str, Any]] = {}
        if isinstance(variants_raw, list):
            for item in variants_raw:
                if not isinstance(item, dict):
                    continue
                style_key = _safe_text(item.get("style_key")).lower()
                if style_key not in {"variant_a", "variant_b", "variant_c"}:
                    continue
                variants_by_style[style_key] = _safe_script_payload_from_ai(
                    style_key=style_key,
                    raw_variant=item,
                    fallback=fallbacks_by_style[style_key],
                )

        variants: List[Dict[str, Any]] = []
        used_fallback = False
        fallback_reasons: List[str] = []
        for style_key, _ in VARIANT_STYLES:
            variant = variants_by_style.get(style_key)
            if variant is None:
                used_fallback = True
                fallback_reasons.append(f"missing_{style_key}")
                variant = fallbacks_by_style[style_key]
            variants.append(variant)

        generation = {
            "mode": DEFAULT_GENERATION_MODE,
            "provider": "openai",
            "model": AI_MODEL_NAME,
            "used_fallback": used_fallback,
            "fallback_reason": ", ".join(fallback_reasons) if fallback_reasons else None,
        }
        return variants, generation
    except Exception as exc:
        logger.warning("Optimizer AI generation fallback: %s", exc)
        variants = [fallbacks_by_style[style_key] for style_key, _ in VARIANT_STYLES]
        generation = {
            "mode": DEFAULT_GENERATION_MODE,
            "provider": "deterministic",
            "model": "deterministic-v1",
            "used_fallback": True,
            "fallback_reason": f"openai_error: {exc}",
        }
        return variants, generation


def _normalize_baseline_detector_map(payload: Dict[str, Any]) -> Dict[str, float]:
    rows = payload.get("baseline_detector_rankings")
    if not isinstance(rows, list):
        return {}
    result: Dict[str, float] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = _safe_text(row.get("detector_key"))
        if not key:
            continue
        result[key] = _safe_float(row.get("score"), math.nan)
    return {key: value for key, value in result.items() if not math.isnan(value)}


def _build_improvement_diff(
    *,
    baseline_score: float,
    baseline_detector_map: Dict[str, float],
    combined_score: float,
    detector_rankings: List[Dict[str, Any]],
) -> Dict[str, Any]:
    combined_before: Optional[float] = None
    combined_delta: Optional[float] = None
    if not math.isnan(baseline_score):
        combined_before = round(baseline_score, 1)
        combined_delta = round(combined_score - baseline_score, 1)

    detector_deltas: List[Dict[str, Any]] = []
    for detector in detector_rankings:
        key = _safe_text(detector.get("detector_key"))
        after_score = round(_safe_float(detector.get("score"), 0.0), 1)
        before_score = baseline_detector_map.get(key)
        delta = round(after_score - before_score, 1) if before_score is not None else None
        detector_deltas.append(
            {
                "detector_key": key,
                "before_score": round(before_score, 1) if before_score is not None else None,
                "after_score": after_score,
                "delta": delta,
            }
        )

    return {
        "combined": {
            "before": combined_before,
            "after": round(combined_score, 1),
            "delta": combined_delta,
        },
        "detectors": detector_deltas,
    }


def _build_line_level_edits(
    *,
    script_text: str,
    detector_rankings: List[Dict[str, Any]],
    format_type: str,
) -> List[Dict[str, Any]]:
    lines = _split_lines(script_text)
    if not lines:
        return []

    last_idx = len(lines) - 1
    longest_idx = max(range(len(lines)), key=lambda idx: len(re.findall(r"\w+", lines[idx])))
    cadence_target = "every 6-10 seconds" if format_type == "short_form" else "every 20-35 seconds"

    edits: List[Dict[str, Any]] = []
    for item in detector_rankings[:5]:
        key = _safe_text(item.get("detector_key"))
        priority = _safe_text(item.get("priority")) or "medium"
        evidence = item.get("evidence")
        reason = ""
        if isinstance(evidence, list) and evidence:
            reason = _safe_text(evidence[0])
        elif isinstance(evidence, str):
            reason = _safe_text(evidence)
        if key == "time_to_value":
            line_no = 1
            original = lines[0]
            suggestion = f"Within one line: the outcome is {original.lower().rstrip('.')} with proof in the same sentence."
        elif key == "open_loops":
            line_no = min(2, len(lines))
            original = lines[line_no - 1]
            suggestion = "Add a teaser: 'In a few seconds, I will show the exact before/after line that changed results.'"
        elif key == "dead_zones":
            line_no = longest_idx + 1
            original = lines[longest_idx]
            suggestion = "Split this into two shorter lines and attach one concrete visual cue for each line."
        elif key == "pattern_interrupts":
            line_no = min(max(2, len(lines) // 2), len(lines))
            original = lines[line_no - 1]
            suggestion = f"Insert a pattern interrupt here (caption shift, zoom, or cut) {cadence_target}."
        elif key == "cta_style":
            line_no = last_idx + 1
            original = lines[last_idx]
            suggestion = "Use one CTA only: 'Comment \"PLAN\" and I will send the exact framework.'"
        else:
            line_no = 1
            original = lines[0]
            suggestion = "Rewrite this line to make the payoff clearer and more specific."

        edits.append(
            {
                "detector_key": key,
                "detector_label": _safe_text(item.get("label")) or key,
                "priority": priority,
                "line_number": line_no,
                "original_line": original,
                "suggested_line": suggestion,
                "reason": reason,
            }
        )
    return edits


def _serialize_draft_snapshot(row: DraftSnapshot) -> Dict[str, Any]:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "platform": row.platform,
        "source_item_id": row.source_item_id,
        "variant_id": row.variant_id,
        "script_text": row.script_text,
        "baseline_score": row.baseline_score,
        "rescored_score": row.rescored_score,
        "delta_score": row.delta_score,
        "detector_rankings": row.detector_rankings_json if isinstance(row.detector_rankings_json, list) else [],
        "next_actions": row.next_actions_json if isinstance(row.next_actions_json, list) else [],
        "line_level_edits": row.line_level_edits_json if isinstance(row.line_level_edits_json, list) else [],
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


async def _evaluate_script(
    *,
    user_id: str,
    platform: str,
    script_text: str,
    duration_s: int,
    optional_metrics: Optional[Dict[str, Any]] = None,
    retention_points: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    transcript = _build_transcript_segments(script_text, duration_s)
    video_analysis = _build_video_analysis(script_text, duration_s, platform)
    detectors = _extract_explicit_detectors(transcript, video_analysis, duration_s)
    format_type = _infer_format(duration_s)

    platform_metrics = _build_platform_metrics(
        video_analysis=video_analysis,
        detectors=detectors,
        retention_points=retention_points or [],
        platform_metrics=optional_metrics or {},
        format_type=format_type,
    )

    try:
        benchmark = await _collect_competitor_benchmark(user_id, format_type)
    except Exception:
        benchmark = {
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
        }
    competitor_metrics = _build_competitor_metrics(platform_metrics["score"], benchmark)
    try:
        historical_metrics = await _collect_historical_performance(user_id, format_type)
    except Exception:
        historical_metrics = {
            "sample_size": 0,
            "format_sample_size": 0,
            "score": 0.0,
            "confidence": "low",
            "insufficient_data": True,
            "summary": "Historical baseline unavailable.",
            "signals": [],
        }

    historical_ready = not bool(historical_metrics.get("insufficient_data", True))
    combined_score, weights = _combined_score(
        competitor_score=_safe_float(competitor_metrics.get("score"), 0.0),
        platform_score=_safe_float(platform_metrics.get("score"), 0.0),
        historical_score=_safe_float(historical_metrics.get("score"), 0.0),
        historical_ready=historical_ready,
    )
    confidence = _confidence_label(
        benchmark_samples=int(benchmark.get("sample_size", 0) or 0),
        historical_confidence=str(historical_metrics.get("confidence", "low")),
        historical_ready=historical_ready,
    )

    next_actions = _build_next_actions(platform_metrics.get("detector_rankings", []))

    return {
        "format_type": format_type,
        "duration_seconds": duration_s,
        "video_analysis": video_analysis,
        "detectors": detectors,
        "platform_metrics": platform_metrics,
        "competitor_metrics": competitor_metrics,
        "historical_metrics": historical_metrics,
        "combined_score": round(combined_score, 1),
        "combined_confidence": confidence,
        "weights": weights,
        "next_actions": next_actions,
    }


async def generate_variants_service(
    *,
    user_id: str,
    payload: Dict[str, Any],
    db: AsyncSession,
) -> Dict[str, Any]:
    _assert_optimizer_enabled()

    topic = _safe_text(payload.get("topic"))
    if len(topic) < 2:
        raise HTTPException(status_code=422, detail="topic is required")

    generation_mode = _normalize_generation_mode(payload.get("generation_mode"))
    constraints = _normalize_constraints(payload)
    platform = constraints["platform"]
    audience = _safe_text(payload.get("audience")) or "solo creators"
    objective = _safe_text(payload.get("objective")) or "higher retention and shares"
    tone = constraints["tone"]
    duration_s = constraints["duration_s"]
    source_item_id = _safe_text(payload.get("source_item_id")) or None
    payload_source_context = _safe_text(payload.get("source_context")) or None
    source_context = await _load_source_context(
        user_id=user_id,
        source_item_id=source_item_id,
        db=db,
    )
    if payload_source_context:
        if source_context is None:
            source_context = {"context_note": payload_source_context}
        else:
            source_context["context_note"] = payload_source_context

    raw_variants, generation = await _generate_ai_or_fallback_variants(
        topic=topic,
        audience=audience,
        objective=objective,
        constraints=constraints,
        source_context=source_context,
    )

    evaluations: List[Dict[str, Any]] = []
    for variant_payload in raw_variants:
        style_key = _safe_text(variant_payload.get("style_key"))
        evaluated = await _evaluate_script(
            user_id=user_id,
            platform=platform,
            script_text=variant_payload["script_text"],
            duration_s=duration_s,
        )
        evaluations.append(
            {
                "id": str(uuid.uuid4()),
                "style_key": style_key,
                "label": variant_payload["label"],
                "rationale": variant_payload["rationale"],
                "script": variant_payload["script"],
                "script_text": variant_payload["script_text"],
                "structure": variant_payload.get("structure", {}),
                "score_breakdown": {
                    "platform_metrics": round(_safe_float(evaluated["platform_metrics"].get("score"), 0.0), 1),
                    "competitor_metrics": round(_safe_float(evaluated["competitor_metrics"].get("score"), 0.0), 1),
                    "historical_metrics": round(_safe_float(evaluated["historical_metrics"].get("score"), 0.0), 1),
                    "combined": evaluated["combined_score"],
                    "detector_weighted_score": round(
                        _safe_float(
                            evaluated["platform_metrics"].get("signals", {}).get("detector_weighted_score"),
                            0.0,
                        ),
                        1,
                    ),
                    "confidence": evaluated["combined_confidence"],
                },
                "detector_rankings": evaluated["platform_metrics"].get("detector_rankings", []),
                "next_actions": evaluated["next_actions"],
            }
        )

    evaluations.sort(key=lambda row: _safe_float(row["score_breakdown"].get("combined"), 0.0), reverse=True)
    median_score = sorted(_safe_float(v["score_breakdown"].get("combined"), 0.0) for v in evaluations)[1]
    for idx, variant in enumerate(evaluations):
        combined = _safe_float(variant["score_breakdown"].get("combined"), 0.0)
        variant["rank"] = idx + 1
        variant["expected_lift_points"] = round(max(0.0, combined - median_score), 1)

    batch_id = str(uuid.uuid4())
    row = ScriptVariant(
        id=batch_id,
        user_id=user_id,
        source_item_id=source_item_id,
        platform=platform,
        topic=topic,
        request_json={
            "platform": platform,
            "topic": topic,
            "audience": audience,
            "objective": objective,
            "tone": tone,
            "duration_s": duration_s,
            "generation_mode": generation_mode,
            "constraints": constraints,
            "template_series_key": payload.get("template_series_key"),
            "source_item_id": source_item_id,
            "source_context": source_context,
            "generation": generation,
        },
        variants_json=evaluations,
        selected_variant_id=evaluations[0]["id"] if evaluations else None,
    )
    db.add(row)
    await db.commit()

    return {
        "batch_id": batch_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generation": generation,
        "variants": evaluations,
    }


async def rescore_script_service(
    *,
    user_id: str,
    payload: Dict[str, Any],
    db: AsyncSession,
) -> Dict[str, Any]:
    _assert_optimizer_enabled()

    script_text = _safe_text(payload.get("script_text"))
    if len(script_text) < 20:
        raise HTTPException(status_code=422, detail="script_text must be at least 20 characters")

    platform = _normalize_platform(payload.get("platform"))
    duration_s = _normalize_duration(payload.get("duration_s"), platform)

    optional_metrics = payload.get("optional_metrics") if isinstance(payload.get("optional_metrics"), dict) else {}
    retention_points_raw = payload.get("retention_points") if isinstance(payload.get("retention_points"), list) else []
    retention_points: List[Dict[str, Any]] = []
    for point in retention_points_raw:
        if not isinstance(point, dict):
            continue
        t = _safe_float(point.get("time"), -1.0)
        r = _safe_float(point.get("retention"), -1.0)
        if t < 0 or r < 0:
            continue
        retention_points.append({"time": t, "retention": r})

    evaluated = await _evaluate_script(
        user_id=user_id,
        platform=platform,
        script_text=script_text,
        duration_s=duration_s,
        optional_metrics=optional_metrics,
        retention_points=retention_points,
    )

    baseline_score = _safe_float(payload.get("baseline_score"), math.nan)
    baseline_detector_map = _normalize_baseline_detector_map(payload)
    combined_score = _safe_float(evaluated.get("combined_score"), 0.0)
    score_delta = None
    if not math.isnan(baseline_score):
        score_delta = round(combined_score - baseline_score, 1)

    detector_rankings = evaluated["platform_metrics"].get("detector_rankings", [])
    line_level_edits = _build_line_level_edits(
        script_text=script_text,
        detector_rankings=detector_rankings,
        format_type=str(evaluated.get("format_type") or "unknown"),
    )
    improvement_diff = _build_improvement_diff(
        baseline_score=baseline_score,
        baseline_detector_map=baseline_detector_map,
        combined_score=combined_score,
        detector_rankings=detector_rankings,
    )

    return {
        "score_breakdown": {
            "platform_metrics": round(_safe_float(evaluated["platform_metrics"].get("score"), 0.0), 1),
            "competitor_metrics": round(_safe_float(evaluated["competitor_metrics"].get("score"), 0.0), 1),
            "historical_metrics": round(_safe_float(evaluated["historical_metrics"].get("score"), 0.0), 1),
            "combined": round(combined_score, 1),
            "confidence": evaluated.get("combined_confidence", "low"),
            "weights": evaluated.get("weights", {}),
            "delta_from_baseline": score_delta,
        },
        "detector_rankings": detector_rankings,
        "next_actions": evaluated.get("next_actions", []),
        "line_level_edits": line_level_edits,
        "improvement_diff": improvement_diff,
        "signals": evaluated["platform_metrics"].get("signals", {}),
        "format_type": evaluated.get("format_type"),
        "duration_seconds": evaluated.get("duration_seconds"),
    }


async def create_draft_snapshot_service(
    *,
    user_id: str,
    payload: Dict[str, Any],
    db: AsyncSession,
) -> Dict[str, Any]:
    _assert_optimizer_enabled()

    script_text = _safe_text(payload.get("script_text"))
    if len(script_text) < 20:
        raise HTTPException(status_code=422, detail="script_text must be at least 20 characters")

    platform = _normalize_platform(payload.get("platform"))
    source_item_id = _safe_text(payload.get("source_item_id")) or None
    variant_id = _safe_text(payload.get("variant_id")) or None
    baseline_score = _safe_float(payload.get("baseline_score"), math.nan)
    rescored_score = _safe_float(payload.get("rescored_score"), math.nan)
    delta_score = _safe_float(payload.get("delta_score"), math.nan)

    rescore_output = payload.get("rescore_output") if isinstance(payload.get("rescore_output"), dict) else {}
    if math.isnan(rescored_score):
        rescored_score = _safe_float(
            payload.get("score_breakdown", {}).get("combined")
            if isinstance(payload.get("score_breakdown"), dict)
            else rescore_output.get("score_breakdown", {}).get("combined"),
            math.nan,
        )
    if math.isnan(rescored_score):
        raise HTTPException(status_code=422, detail="rescored_score or score_breakdown.combined is required")

    if math.isnan(delta_score) and not math.isnan(baseline_score):
        delta_score = round(rescored_score - baseline_score, 1)

    detector_rankings = payload.get("detector_rankings")
    if not isinstance(detector_rankings, list):
        detector_rankings = rescore_output.get("detector_rankings", [])
    next_actions = payload.get("next_actions")
    if not isinstance(next_actions, list):
        next_actions = rescore_output.get("next_actions", [])
    line_level_edits = payload.get("line_level_edits")
    if not isinstance(line_level_edits, list):
        line_level_edits = rescore_output.get("line_level_edits", [])

    row = DraftSnapshot(
        id=str(uuid.uuid4()),
        user_id=user_id,
        platform=platform,
        source_item_id=source_item_id,
        variant_id=variant_id,
        script_text=script_text,
        baseline_score=None if math.isnan(baseline_score) else round(baseline_score, 1),
        rescored_score=round(rescored_score, 1),
        delta_score=None if math.isnan(delta_score) else round(delta_score, 1),
        detector_rankings_json=detector_rankings if isinstance(detector_rankings, list) else [],
        next_actions_json=next_actions if isinstance(next_actions, list) else [],
        line_level_edits_json=line_level_edits if isinstance(line_level_edits, list) else [],
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _serialize_draft_snapshot(row)


async def get_draft_snapshot_service(
    *,
    user_id: str,
    snapshot_id: str,
    db: AsyncSession,
) -> Dict[str, Any]:
    _assert_optimizer_enabled()
    result = await db.execute(
        select(DraftSnapshot).where(
            DraftSnapshot.id == snapshot_id,
            DraftSnapshot.user_id == user_id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Draft snapshot not found")
    return _serialize_draft_snapshot(row)


async def list_draft_snapshots_service(
    *,
    user_id: str,
    db: AsyncSession,
    platform: Optional[str] = None,
    limit: int = 20,
) -> Dict[str, Any]:
    _assert_optimizer_enabled()
    query = select(DraftSnapshot).where(DraftSnapshot.user_id == user_id)
    if platform:
        query = query.where(DraftSnapshot.platform == _normalize_platform(platform))
    query = query.order_by(DraftSnapshot.created_at.desc()).limit(max(1, min(int(limit), 100)))
    result = await db.execute(query)
    rows = result.scalars().all()
    return {
        "items": [_serialize_draft_snapshot(row) for row in rows],
        "count": len(rows),
    }
