"""
Service for generating Competitor Blueprints.
"""

import asyncio
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from config import settings
from ingestion.youtube import create_youtube_client_with_api_key
from models.competitor import Competitor
from models.connection import Connection
from models.profile import Profile


HOOK_TEMPLATE_MAP = {
    "Question Hook": "Why {pain_point} is hurting your growth (and what to do instead)",
    "Numbered Promise": "{number} ways to get {result} faster in {timeframe}",
    "Comparison Hook": "{option_a} vs {option_b}: which is better for {audience} in {year}",
    "Mistake/Warning Hook": "Stop making this {topic} mistake before it kills your {result}",
    "Secret Reveal Hook": "The {topic} secret most creators miss (but top channels use)",
    "Challenge/Experiment Hook": "I tried {tactic} for {duration} - here is what happened",
    "How-To Hook": "How to {outcome} without {common_obstacle}",
    "Direct Outcome Hook": "How I got {outcome} by changing just one thing",
}
SHORT_FORM_MAX_SECONDS = 60
HOOK_FORMAT_LABELS = {
    "short_form": f"Short-form (<= {SHORT_FORM_MAX_SECONDS}s)",
    "long_form": f"Long-form (> {SHORT_FORM_MAX_SECONDS}s)",
}
TOPIC_STOP_WORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "your",
    "you",
    "how",
    "why",
    "what",
    "when",
    "where",
    "into",
    "without",
    "about",
    "video",
    "videos",
    "creator",
    "creators",
    "channel",
}


def _get_youtube_client():
    api_key = settings.YOUTUBE_API_KEY if hasattr(settings, "YOUTUBE_API_KEY") else settings.GOOGLE_CLIENT_SECRET
    if not api_key:
        raise ValueError("YouTube API key not configured")
    return create_youtube_client_with_api_key(api_key)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _format_label(format_key: str) -> str:
    return HOOK_FORMAT_LABELS.get(format_key, "Unknown format")


def _classify_video_format(duration_seconds: int) -> str:
    if duration_seconds <= 0:
        return "unknown"
    if duration_seconds <= SHORT_FORM_MAX_SECONDS:
        return "short_form"
    return "long_form"


def _safe_list_of_strings(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _parse_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        text = str(value)
        if text.endswith("Z"):
            text = text.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return None


def _views_per_day(views: int, published_at: Any) -> float:
    published = _parse_datetime(published_at)
    if not published:
        return float(views)
    age_days = max((datetime.now(timezone.utc) - published).total_seconds() / 86400.0, 1.0)
    return float(views) / age_days


def _extract_topic_keywords(text: str) -> List[str]:
    tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9_+-]{2,}", text.lower())
    return [token for token in tokens if token not in TOPIC_STOP_WORDS]


def _extract_cta_style(text: str) -> str:
    lower = text.lower()
    if re.search(r"\bcomment\b|\bwhat do you think\b|\btell me\b", lower):
        return "comment_prompt"
    if re.search(r"\bshare\b|\bsend this\b|\brepost\b", lower):
        return "share_prompt"
    if re.search(r"\bsave\b|\bbookmark\b", lower):
        return "save_prompt"
    if re.search(r"\bsubscribe\b|\bfollow\b", lower):
        return "follow_prompt"
    if re.search(r"\blink in bio\b|\blink below\b|\bdescription\b", lower):
        return "link_prompt"
    return "none"


def _derive_framework_signals(video: Dict[str, Any]) -> Dict[str, Any]:
    title = str(video.get("title", "") or "")
    transcript = str(video.get("transcript", "") or "")
    body = f"{title}\n{transcript}".strip().lower()
    authority_hook = bool(
        re.search(r"\b\d+([kmb]|\+)?\b", title.lower())
        or re.search(r"\b(i|we)\s+(grew|scaled|gained|tested|hit)\b", body)
    )
    fast_proof = bool(
        re.search(r"\bproof\b|\bresults?\b|\breceipts?\b|\bscreenshot\b|\bdata\b", body)
    )
    framework_steps = bool(
        re.search(r"\bfirst\b|\bsecond\b|\bthird\b|\bstep\b|\bframework\b|\bformula\b", body)
    )
    open_loop = bool(
        re.search(r"\bcoming up\b|\bin a second\b|\bby the end\b|\blater in this video\b", body)
    )
    cta_style = _extract_cta_style(body)
    return {
        "authority_hook": authority_hook,
        "fast_proof": fast_proof,
        "framework_steps": framework_steps,
        "open_loop": open_loop,
        "cta_style": cta_style,
    }


def _pearson_correlation(xs: List[float], ys: List[float]) -> float:
    if len(xs) < 2 or len(xs) != len(ys):
        return 0.0
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    if var_x <= 0 or var_y <= 0:
        return 0.0
    return cov / ((var_x ** 0.5) * (var_y ** 0.5))


def _build_winner_pattern_signals(competitor_videos: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not competitor_videos:
        return {
            "summary": "Not enough competitor videos to build velocity playbook.",
            "sample_size": 0,
            "top_topics_by_velocity": [],
            "hook_velocity_correlation": 0.0,
            "top_videos_by_velocity": [],
        }

    topic_stats: Dict[str, Dict[str, float]] = {}
    hook_scores: List[float] = []
    velocity_scores: List[float] = []
    ranked_videos: List[Dict[str, Any]] = []

    for video in competitor_videos:
        title = str(video.get("title", "") or "")
        transcript = str(video.get("transcript", "") or "")
        combined_text = f"{title} {transcript}"
        views = _safe_int(video.get("views", 0))
        velocity = float(video.get("views_per_day", 0.0) or 0.0)
        pattern = _detect_hook_pattern(title)
        hook_score = 1.0
        if pattern in {"Question Hook", "How-To Hook"}:
            hook_score = 2.0
        elif pattern in {"Numbered Promise", "Challenge/Experiment Hook"}:
            hook_score = 1.6

        hook_scores.append(hook_score)
        velocity_scores.append(velocity)

        ranked_videos.append(
            {
                "channel": video.get("channel"),
                "title": title,
                "views": views,
                "views_per_day": round(velocity, 2),
                "hook_pattern": pattern,
            }
        )

        for keyword in _extract_topic_keywords(combined_text):
            if keyword not in topic_stats:
                topic_stats[keyword] = {"count": 0.0, "velocity_sum": 0.0}
            topic_stats[keyword]["count"] += 1
            topic_stats[keyword]["velocity_sum"] += velocity

    top_topics = []
    for topic, stats in topic_stats.items():
        avg_velocity = stats["velocity_sum"] / max(stats["count"], 1.0)
        top_topics.append(
            {
                "topic": topic,
                "count": int(stats["count"]),
                "avg_views_per_day": round(avg_velocity, 2),
            }
        )
    top_topics.sort(key=lambda row: (row["avg_views_per_day"], row["count"]), reverse=True)

    correlation = _pearson_correlation(hook_scores, velocity_scores)
    ranked_videos.sort(key=lambda row: row["views_per_day"], reverse=True)

    return {
        "summary": (
            "Velocity playbook built from competitor views/day and hook style correlation."
        ),
        "sample_size": len(competitor_videos),
        "top_topics_by_velocity": top_topics[:5],
        "hook_velocity_correlation": round(correlation, 3),
        "top_videos_by_velocity": ranked_videos[:5],
    }


def _build_framework_playbook(competitor_videos: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not competitor_videos:
        return {
            "summary": "No competitor framework data yet.",
            "stage_adoption": {},
            "cta_distribution": {},
            "dominant_sequence": [],
            "execution_notes": [],
        }

    totals = {
        "authority_hook": 0,
        "fast_proof": 0,
        "framework_steps": 0,
        "open_loop": 0,
    }
    cta_distribution: Dict[str, int] = defaultdict(int)

    for video in competitor_videos:
        signals = video.get("framework_signals", {})
        for key in totals:
            if bool(signals.get(key, False)):
                totals[key] += 1
        cta_distribution[str(signals.get("cta_style", "none"))] += 1

    sample = max(len(competitor_videos), 1)
    stage_adoption = {key: round(value / sample, 3) for key, value in totals.items()}
    ordered_ctas = sorted(cta_distribution.items(), key=lambda item: item[1], reverse=True)
    dominant_sequence = [
        "authority_hook",
        "fast_proof",
        "framework_steps",
        "cta",
    ]

    return {
        "summary": "Transcript-first framework extraction across competitor winners.",
        "stage_adoption": stage_adoption,
        "cta_distribution": {key: value for key, value in ordered_ctas},
        "dominant_sequence": dominant_sequence,
        "execution_notes": [
            "Lead with authority/result claim in first line.",
            "Deliver proof quickly before deep explanation.",
            "Use explicit step framework and finish with one CTA style.",
        ],
    }


def _build_repurpose_plan(
    hook_intelligence: Dict[str, Any],
    winner_signals: Dict[str, Any],
    framework_playbook: Dict[str, Any],
) -> Dict[str, Any]:
    top_pattern = "Direct Outcome Hook"
    common_patterns = hook_intelligence.get("common_patterns", [])
    if isinstance(common_patterns, list) and common_patterns:
        top_pattern = str(common_patterns[0].get("pattern", top_pattern))

    top_topic = "your niche"
    topics = winner_signals.get("top_topics_by_velocity", [])
    if isinstance(topics, list) and topics:
        top_topic = str(topics[0].get("topic", top_topic))

    cta_distribution = framework_playbook.get("cta_distribution", {})
    primary_cta = "comment_prompt"
    if isinstance(cta_distribution, dict) and cta_distribution:
        primary_cta = max(cta_distribution, key=lambda key: cta_distribution[key])

    return {
        "summary": "One concept, three platform-native cuts with packaging adjustments.",
        "core_angle": f"Use {top_pattern} around '{top_topic}' with fast proof and {primary_cta}.",
        "youtube_shorts": {
            "duration_target_s": 45,
            "hook_template": top_pattern,
            "edit_directives": [
                "Open with bold claim text on frame 1.",
                "Show proof by second 5.",
                "Use one comment CTA in final 3 seconds.",
            ],
        },
        "instagram_reels": {
            "duration_target_s": 35,
            "hook_template": top_pattern,
            "edit_directives": [
                "Front-load the strongest visual and caption.",
                "Keep pace dense with no dead air.",
                "End with save/share CTA card.",
            ],
        },
        "tiktok": {
            "duration_target_s": 28,
            "hook_template": top_pattern,
            "edit_directives": [
                "Lead with conflict question in first second.",
                "Add two pattern interrupts in first 10 seconds.",
                "Close with follow + comment prompt.",
            ],
        },
    }


def _safe_transcript_text(client: Any, video_id: str, fallback_text: str) -> str:
    text = ""
    try:
        caption_data = client.get_video_captions(video_id)
        if isinstance(caption_data, str) and caption_data and not caption_data.lower().startswith("captions available"):
            text = caption_data
    except Exception:
        text = ""

    if not text:
        # Optional runtime integration if library is available.
        try:
            from youtube_transcript_api import YouTubeTranscriptApi  # type: ignore

            transcript_items = YouTubeTranscriptApi.get_transcript(video_id, languages=["en"])
            chunks = [item.get("text", "").strip() for item in transcript_items[:80] if item.get("text")]
            text = " ".join(chunks).strip()
        except Exception:
            text = ""

    if text:
        return text[:6000]
    return fallback_text[:3000]


def _detect_hook_pattern(title: str) -> str:
    lower = title.lower().strip()

    if not lower:
        return "Direct Outcome Hook"

    if (
        "?" in title
        or lower.startswith("why ")
        or lower.startswith("how ")
        or lower.startswith("what ")
        or lower.startswith("can ")
        or lower.startswith("should ")
        or lower.startswith("is ")
        or lower.startswith("are ")
        or lower.startswith("will ")
    ):
        return "Question Hook"

    if re.search(r"\b\d+\b", lower):
        return "Numbered Promise"

    if re.search(r"\b(vs|versus|compare|comparison)\b", lower):
        return "Comparison Hook"

    if re.search(r"\b(mistake|warning|avoid|stop\s+doing|wrong)\b", lower):
        return "Mistake/Warning Hook"

    if re.search(r"\b(secret|truth|nobody\s+tells|no\s+one\s+tells)\b", lower):
        return "Secret Reveal Hook"

    if re.search(r"\b(i\s+tried|we\s+tried|for\s+\d+\s+days|challenge|experiment)\b", lower):
        return "Challenge/Experiment Hook"

    if lower.startswith("how to "):
        return "How-To Hook"

    return "Direct Outcome Hook"


def _template_for_pattern(pattern: str) -> str:
    return HOOK_TEMPLATE_MAP.get(pattern, HOOK_TEMPLATE_MAP["Direct Outcome Hook"])


def _empty_format_hook_profile(format_key: str, summary: Optional[str] = None) -> Dict[str, Any]:
    label = _format_label(format_key)
    return {
        "format": format_key,
        "label": label,
        "video_count": 0,
        "summary": summary or f"Not enough {label.lower()} competitor videos for reliable hook extraction.",
        "common_patterns": [],
        "recommended_hooks": [],
        "competitor_examples": [],
    }


def _build_hook_pattern_payload(
    competitor_videos: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[str], List[Dict[str, Any]]]:
    pattern_stats: Dict[str, Dict[str, Any]] = {}
    competitor_examples: Dict[str, List[Tuple[int, str]]] = defaultdict(list)

    for video in competitor_videos:
        title = str(video.get("title", "")).strip()
        channel = str(video.get("channel", "Competitor")).strip() or "Competitor"
        views = _safe_int(video.get("views", 0))
        if not title:
            continue

        pattern = _detect_hook_pattern(title)
        if pattern not in pattern_stats:
            pattern_stats[pattern] = {
                "pattern": pattern,
                "frequency": 0,
                "channels": set(),
                "total_views": 0,
                "examples": [],
            }

        pattern_stats[pattern]["frequency"] += 1
        pattern_stats[pattern]["channels"].add(channel)
        pattern_stats[pattern]["total_views"] += views
        pattern_stats[pattern]["examples"].append((views, title))
        competitor_examples[channel].append((views, title))

    if not pattern_stats:
        return [], [], []

    ranked_patterns = sorted(
        pattern_stats.values(),
        key=lambda item: (
            len(item["channels"]),
            item["frequency"],
            item["total_views"],
        ),
        reverse=True,
    )

    common_patterns: List[Dict[str, Any]] = []
    for item in ranked_patterns[:5]:
        examples = [
            title
            for _, title in sorted(item["examples"], key=lambda x: x[0], reverse=True)[:3]
        ]
        common_patterns.append(
            {
                "pattern": item["pattern"],
                "frequency": _safe_int(item["frequency"]),
                "competitor_count": _safe_int(len(item["channels"])),
                "avg_views": _safe_int(item["total_views"] / max(item["frequency"], 1)),
                "examples": examples,
                "template": _template_for_pattern(item["pattern"]),
            }
        )

    recommended_hooks: List[str] = []
    for pattern in common_patterns:
        template = str(pattern.get("template", "")).strip()
        if template and template not in recommended_hooks:
            recommended_hooks.append(template)

    competitor_examples_payload: List[Dict[str, Any]] = []
    for competitor, hooks in sorted(competitor_examples.items(), key=lambda x: x[0].lower()):
        top_titles = [
            title
            for _, title in sorted(hooks, key=lambda x: x[0], reverse=True)[:3]
        ]
        competitor_examples_payload.append(
            {
                "competitor": competitor,
                "hooks": top_titles,
            }
        )

    return common_patterns, recommended_hooks, competitor_examples_payload


def _build_format_hook_profile(format_key: str, competitor_videos: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not competitor_videos:
        return _empty_format_hook_profile(format_key)

    common_patterns, recommended_hooks, competitor_examples = _build_hook_pattern_payload(competitor_videos)
    if not common_patterns:
        return _empty_format_hook_profile(
            format_key,
            summary=f"{_format_label(format_key)} videos exist, but titles were too sparse for hook extraction.",
        )

    top_pattern = common_patterns[0]["pattern"]
    return {
        "format": format_key,
        "label": _format_label(format_key),
        "video_count": len(competitor_videos),
        "summary": (
            f"{_format_label(format_key)} winner pattern: {top_pattern}. "
            "Prioritize this structure for this video length."
        ),
        "common_patterns": common_patterns,
        "recommended_hooks": recommended_hooks,
        "competitor_examples": competitor_examples,
    }


def _empty_hook_intelligence(summary: str = "Not enough competitor data to extract hook patterns.") -> Dict[str, Any]:
    return {
        "summary": summary,
        "format_definition": (
            f"short_form <= {SHORT_FORM_MAX_SECONDS}s, "
            f"long_form > {SHORT_FORM_MAX_SECONDS}s"
        ),
        "common_patterns": [],
        "recommended_hooks": [],
        "competitor_examples": [],
        "format_breakdown": {
            "short_form": _empty_format_hook_profile("short_form"),
            "long_form": _empty_format_hook_profile("long_form"),
        },
    }


def _build_hook_intelligence(competitor_videos: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not competitor_videos:
        return _empty_hook_intelligence()

    common_patterns, recommended_hooks, competitor_examples = _build_hook_pattern_payload(competitor_videos)
    if not common_patterns:
        return _empty_hook_intelligence(
            "Competitor videos were found, but titles were too sparse for hook extraction."
        )

    short_form_videos = [
        v
        for v in competitor_videos
        if _classify_video_format(_safe_int(v.get("duration_seconds", 0))) == "short_form"
    ]
    long_form_videos = [
        v
        for v in competitor_videos
        if _classify_video_format(_safe_int(v.get("duration_seconds", 0))) == "long_form"
    ]

    short_profile = _build_format_hook_profile("short_form", short_form_videos)
    long_profile = _build_format_hook_profile("long_form", long_form_videos)

    top_pattern = common_patterns[0]["pattern"]
    format_summary = ""
    if short_profile["common_patterns"] and long_profile["common_patterns"]:
        short_top = short_profile["common_patterns"][0]["pattern"]
        long_top = long_profile["common_patterns"][0]["pattern"]
        format_summary = f" Shorts winner: {short_top}. Long-form winner: {long_top}."
    elif short_profile["common_patterns"]:
        short_top = short_profile["common_patterns"][0]["pattern"]
        format_summary = f" Shorts winner: {short_top}."
    elif long_profile["common_patterns"]:
        long_top = long_profile["common_patterns"][0]["pattern"]
        format_summary = f" Long-form winner: {long_top}."

    summary = (
        f"Most repeated competitor hook pattern: {top_pattern}.{format_summary} "
        "Use the format-specific templates below and adapt them to your niche promise."
    )

    return {
        "summary": summary,
        "format_definition": (
            f"short_form <= {SHORT_FORM_MAX_SECONDS}s, "
            f"long_form > {SHORT_FORM_MAX_SECONDS}s"
        ),
        "common_patterns": common_patterns,
        "recommended_hooks": recommended_hooks,
        "competitor_examples": competitor_examples,
        "format_breakdown": {
            "short_form": short_profile,
            "long_form": long_profile,
        },
    }


def _normalize_pattern_payload(raw: Any, fallback: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    common_patterns: List[Dict[str, Any]] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                pattern = str(item.get("pattern", "Direct Outcome Hook")).strip() or "Direct Outcome Hook"
                common_patterns.append(
                    {
                        "pattern": pattern,
                        "frequency": _safe_int(item.get("frequency", 0)),
                        "competitor_count": _safe_int(item.get("competitor_count", 0)),
                        "avg_views": _safe_int(item.get("avg_views", 0)),
                        "examples": _safe_list_of_strings(item.get("examples", []))[:3],
                        "template": str(item.get("template", _template_for_pattern(pattern))).strip(),
                    }
                )
            elif isinstance(item, str):
                pattern = item.strip() or "Direct Outcome Hook"
                common_patterns.append(
                    {
                        "pattern": pattern,
                        "frequency": 0,
                        "competitor_count": 0,
                        "avg_views": 0,
                        "examples": [],
                        "template": _template_for_pattern(pattern),
                    }
                )
    return common_patterns or fallback


def _normalize_competitor_examples(raw: Any, fallback: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    competitor_examples: List[Dict[str, Any]] = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            competitor = str(item.get("competitor", "Competitor")).strip() or "Competitor"
            hooks = _safe_list_of_strings(item.get("hooks", []))[:3]
            competitor_examples.append({"competitor": competitor, "hooks": hooks})
    return competitor_examples or fallback


def _normalize_format_hook_profile(raw: Any, fallback: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return fallback

    format_key = str(raw.get("format", fallback.get("format", "unknown"))).strip() or "unknown"
    common_patterns = _normalize_pattern_payload(raw.get("common_patterns"), fallback.get("common_patterns", []))
    recommended_hooks = _safe_list_of_strings(raw.get("recommended_hooks", []))
    if not recommended_hooks:
        recommended_hooks = fallback.get("recommended_hooks", [])

    competitor_examples = _normalize_competitor_examples(
        raw.get("competitor_examples"),
        fallback.get("competitor_examples", []),
    )
    summary = str(raw.get("summary", "")).strip() or str(fallback.get("summary", ""))

    return {
        "format": format_key,
        "label": str(raw.get("label", fallback.get("label", _format_label(format_key)))).strip()
        or _format_label(format_key),
        "video_count": _safe_int(raw.get("video_count", fallback.get("video_count", 0))),
        "summary": summary,
        "common_patterns": common_patterns,
        "recommended_hooks": recommended_hooks,
        "competitor_examples": competitor_examples,
    }


def _normalize_hook_intelligence(raw: Any, fallback: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return fallback

    common_patterns = _normalize_pattern_payload(
        raw.get("common_patterns"),
        fallback.get("common_patterns", []),
    )
    recommended_hooks = _safe_list_of_strings(raw.get("recommended_hooks", []))
    if not recommended_hooks:
        recommended_hooks = fallback.get("recommended_hooks", [])

    competitor_examples = _normalize_competitor_examples(
        raw.get("competitor_examples"),
        fallback.get("competitor_examples", []),
    )
    summary = str(raw.get("summary", "")).strip() or str(fallback.get("summary", ""))

    fallback_breakdown = fallback.get("format_breakdown", {})
    raw_breakdown = raw.get("format_breakdown", {})
    if not isinstance(raw_breakdown, dict):
        raw_breakdown = {}

    short_fallback = fallback_breakdown.get("short_form", _empty_format_hook_profile("short_form"))
    long_fallback = fallback_breakdown.get("long_form", _empty_format_hook_profile("long_form"))

    return {
        "summary": summary,
        "format_definition": str(
            raw.get(
                "format_definition",
                fallback.get(
                    "format_definition",
                    f"short_form <= {SHORT_FORM_MAX_SECONDS}s, long_form > {SHORT_FORM_MAX_SECONDS}s",
                ),
            )
        ).strip(),
        "common_patterns": common_patterns,
        "recommended_hooks": recommended_hooks,
        "competitor_examples": competitor_examples,
        "format_breakdown": {
            "short_form": _normalize_format_hook_profile(raw_breakdown.get("short_form"), short_fallback),
            "long_form": _normalize_format_hook_profile(raw_breakdown.get("long_form"), long_fallback),
        },
    }


def _normalize_winner_pattern_signals(raw: Any, fallback: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return fallback

    top_topics: List[Dict[str, Any]] = []
    raw_topics = raw.get("top_topics_by_velocity", [])
    if isinstance(raw_topics, list):
        for topic in raw_topics:
            if not isinstance(topic, dict):
                continue
            name = str(topic.get("topic", "")).strip()
            if not name:
                continue
            top_topics.append(
                {
                    "topic": name,
                    "count": _safe_int(topic.get("count", 0)),
                    "avg_views_per_day": float(topic.get("avg_views_per_day", 0.0) or 0.0),
                }
            )
    if not top_topics:
        top_topics = fallback.get("top_topics_by_velocity", [])

    top_videos: List[Dict[str, Any]] = []
    raw_videos = raw.get("top_videos_by_velocity", [])
    if isinstance(raw_videos, list):
        for video in raw_videos:
            if not isinstance(video, dict):
                continue
            title = str(video.get("title", "")).strip()
            if not title:
                continue
            top_videos.append(
                {
                    "channel": str(video.get("channel", "Competitor")).strip() or "Competitor",
                    "title": title,
                    "views": _safe_int(video.get("views", 0)),
                    "views_per_day": float(video.get("views_per_day", 0.0) or 0.0),
                    "hook_pattern": str(video.get("hook_pattern", "Direct Outcome Hook")).strip() or "Direct Outcome Hook",
                }
            )
    if not top_videos:
        top_videos = fallback.get("top_videos_by_velocity", [])

    return {
        "summary": str(raw.get("summary", fallback.get("summary", ""))).strip() or fallback.get("summary", ""),
        "sample_size": _safe_int(raw.get("sample_size", fallback.get("sample_size", 0))),
        "top_topics_by_velocity": top_topics,
        "hook_velocity_correlation": float(
            raw.get("hook_velocity_correlation", fallback.get("hook_velocity_correlation", 0.0)) or 0.0
        ),
        "top_videos_by_velocity": top_videos,
    }


def _normalize_framework_playbook(raw: Any, fallback: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return fallback

    stage_adoption: Dict[str, float] = {}
    raw_stage = raw.get("stage_adoption", {})
    if isinstance(raw_stage, dict):
        for key in ("authority_hook", "fast_proof", "framework_steps", "open_loop"):
            stage_adoption[key] = float(raw_stage.get(key, fallback.get("stage_adoption", {}).get(key, 0.0)) or 0.0)
    else:
        stage_adoption = fallback.get("stage_adoption", {})

    cta_distribution: Dict[str, int] = {}
    raw_cta = raw.get("cta_distribution", {})
    if isinstance(raw_cta, dict):
        for key, value in raw_cta.items():
            label = str(key).strip()
            if label:
                cta_distribution[label] = _safe_int(value, 0)
    if not cta_distribution:
        cta_distribution = fallback.get("cta_distribution", {})

    dominant_sequence = _safe_list_of_strings(raw.get("dominant_sequence", []))
    if not dominant_sequence:
        dominant_sequence = fallback.get("dominant_sequence", [])

    execution_notes = _safe_list_of_strings(raw.get("execution_notes", []))
    if not execution_notes:
        execution_notes = fallback.get("execution_notes", [])

    return {
        "summary": str(raw.get("summary", fallback.get("summary", ""))).strip() or fallback.get("summary", ""),
        "stage_adoption": stage_adoption,
        "cta_distribution": cta_distribution,
        "dominant_sequence": dominant_sequence,
        "execution_notes": execution_notes,
    }


def _normalize_repurpose_plan(raw: Any, fallback: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return fallback

    def _normalize_platform(name: str, fb: Dict[str, Any]) -> Dict[str, Any]:
        data = raw.get(name, {})
        if not isinstance(data, dict):
            return fb
        return {
            "duration_target_s": _safe_int(data.get("duration_target_s", fb.get("duration_target_s", 30)), 30),
            "hook_template": str(data.get("hook_template", fb.get("hook_template", "Direct Outcome Hook"))).strip()
            or str(fb.get("hook_template", "Direct Outcome Hook")),
            "edit_directives": _safe_list_of_strings(data.get("edit_directives", [])) or fb.get("edit_directives", []),
        }

    return {
        "summary": str(raw.get("summary", fallback.get("summary", ""))).strip() or fallback.get("summary", ""),
        "core_angle": str(raw.get("core_angle", fallback.get("core_angle", ""))).strip() or fallback.get("core_angle", ""),
        "youtube_shorts": _normalize_platform("youtube_shorts", fallback.get("youtube_shorts", {})),
        "instagram_reels": _normalize_platform("instagram_reels", fallback.get("instagram_reels", {})),
        "tiktok": _normalize_platform("tiktok", fallback.get("tiktok", {})),
    }


def _normalize_blueprint_payload(payload: Any, fallback: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return fallback

    gap_analysis = _safe_list_of_strings(payload.get("gap_analysis", []))
    if not gap_analysis:
        gap_analysis = fallback["gap_analysis"]

    content_pillars = _safe_list_of_strings(payload.get("content_pillars", []))
    if not content_pillars:
        content_pillars = fallback["content_pillars"]

    video_ideas: List[Dict[str, str]] = []
    raw_ideas = payload.get("video_ideas", [])
    if isinstance(raw_ideas, list):
        for item in raw_ideas:
            if isinstance(item, dict):
                title = str(item.get("title", "")).strip()
                concept = str(item.get("concept", "")).strip()
                if title and concept:
                    video_ideas.append({"title": title, "concept": concept})

    if not video_ideas:
        video_ideas = fallback["video_ideas"]

    hook_intelligence = _normalize_hook_intelligence(
        payload.get("hook_intelligence"),
        fallback["hook_intelligence"],
    )
    winner_pattern_signals = _normalize_winner_pattern_signals(
        payload.get("winner_pattern_signals"),
        fallback["winner_pattern_signals"],
    )
    framework_playbook = _normalize_framework_playbook(
        payload.get("framework_playbook"),
        fallback["framework_playbook"],
    )
    repurpose_plan = _normalize_repurpose_plan(
        payload.get("repurpose_plan"),
        fallback["repurpose_plan"],
    )

    return {
        "gap_analysis": gap_analysis,
        "content_pillars": content_pillars,
        "video_ideas": video_ideas,
        "hook_intelligence": hook_intelligence,
        "winner_pattern_signals": winner_pattern_signals,
        "framework_playbook": framework_playbook,
        "repurpose_plan": repurpose_plan,
    }


async def _resolve_user_channel(db: AsyncSession, user_id: str) -> Tuple[Optional[str], str]:
    """
    Resolve user's YouTube channel identity from profiles first, then connection metadata.
    """
    profile_result = await db.execute(
        select(Profile)
        .where(Profile.user_id == user_id, Profile.platform == "youtube")
        .order_by(Profile.created_at.desc())
        .limit(1)
    )
    profile = profile_result.scalar_one_or_none()
    if profile and profile.external_id:
        return profile.external_id, (profile.display_name or profile.handle or "User Channel")

    conn_result = await db.execute(
        select(Connection)
        .where(Connection.user_id == user_id, Connection.platform == "youtube")
        .order_by(Connection.created_at.desc())
        .limit(1)
    )
    connection = conn_result.scalar_one_or_none()
    if connection and connection.platform_user_id:
        return connection.platform_user_id, (connection.platform_handle or "User Channel")

    return None, "User Channel"


async def generate_blueprint_service(user_id: str, db: AsyncSession) -> Dict[str, Any]:
    """
    Generate a gap analysis and content strategy blueprint.
    """
    user_channel_id, user_channel_name = await _resolve_user_channel(db, user_id)

    result = await db.execute(select(Competitor).where(Competitor.user_id == user_id))
    competitors = result.scalars().all()

    if not competitors:
        return {
            "gap_analysis": ["Add competitors to generate a blueprint."],
            "content_pillars": [],
            "video_ideas": [],
            "hook_intelligence": _empty_hook_intelligence(),
            "winner_pattern_signals": _build_winner_pattern_signals([]),
            "framework_playbook": _build_framework_playbook([]),
            "repurpose_plan": _build_repurpose_plan(_empty_hook_intelligence(), _build_winner_pattern_signals([]), _build_framework_playbook([])),
        }

    client = _get_youtube_client()

    async def fetch_videos_safe(channel_id: str, label: str) -> List[Dict[str, Any]]:
        try:
            vids = client.get_channel_videos(channel_id, max_results=50)
            vid_ids = [v["id"] for v in vids if v.get("id")]
            details = client.get_video_details(vid_ids)

            enriched = []
            for video in vids:
                video_id = video.get("id")
                if not video_id:
                    continue
                detail = details.get(video_id, {})
                description = str(video.get("description", "") or "")
                transcript = _safe_transcript_text(client, video_id, description)
                views = _safe_int(detail.get("view_count", 0))
                enriched.append(
                    {
                        "title": video.get("title", ""),
                        "description": description,
                        "transcript": transcript,
                        "views": views,
                        "likes": _safe_int(detail.get("like_count", 0)),
                        "comment_count": _safe_int(detail.get("comment_count", 0)),
                        "duration_seconds": _safe_int(detail.get("duration_seconds", 0)),
                        "published": video.get("published_at"),
                        "views_per_day": round(_views_per_day(views, video.get("published_at")), 2),
                        "framework_signals": _derive_framework_signals(
                            {
                                "title": video.get("title", ""),
                                "transcript": transcript,
                            }
                        ),
                        "channel": label,
                    }
                )
            return enriched
        except Exception as e:
            print(f"Error fetching for {label}: {e}")
            return []

    tasks = []
    if user_channel_id:
        tasks.append(fetch_videos_safe(user_channel_id, "User"))
    for comp in competitors:
        tasks.append(fetch_videos_safe(comp.external_id, comp.display_name or "Competitor"))

    results = await asyncio.gather(*tasks)

    all_videos: List[Dict[str, Any]] = []
    for rows in results:
        all_videos.extend(rows)

    competitor_videos = [v for v in all_videos if v.get("channel") != "User"]
    hook_intelligence = _build_hook_intelligence(competitor_videos)
    winner_pattern_signals = _build_winner_pattern_signals(competitor_videos)
    framework_playbook = _build_framework_playbook(competitor_videos)
    repurpose_plan = _build_repurpose_plan(hook_intelligence, winner_pattern_signals, framework_playbook)

    top_topics = winner_pattern_signals.get("top_topics_by_velocity", [])
    derived_content_pillars = [row.get("topic", "") for row in top_topics[:3] if row.get("topic")]
    if not derived_content_pillars:
        derived_content_pillars = ["Audience Pain Points", "How-To Experiments", "Workflow Breakdowns"]

    deterministic_blueprint = {
        "gap_analysis": [
            "Competitors are compounding on specific topics with stronger views/day velocity.",
            "Top competitor videos deliver proof quickly, then move into framework steps.",
            "Winning channels reuse hook structures and CTA styles with minimal variation.",
        ],
        "content_pillars": derived_content_pillars,
        "video_ideas": [
            {
                "title": "Why Most Creators Miss This Growth Lever",
                "concept": "Authority hook + quick proof + 3-step framework mapped from top-velocity competitor videos.",
            },
            {
                "title": "I Tested 3 Content Systems for 30 Days",
                "concept": "Experiment format with clear receipts, then reusable workflow checklist.",
            },
            {
                "title": "The Framework We Use to Keep Retention High",
                "concept": "Teach the framework directly, then close with a comment prompt CTA.",
            },
        ],
        "hook_intelligence": hook_intelligence,
        "winner_pattern_signals": winner_pattern_signals,
        "framework_playbook": framework_playbook,
        "repurpose_plan": repurpose_plan,
    }

    prompt = f"""
    Analyze these YouTube video performance stats to create a content blueprint.

    My Channel: {user_channel_name} (Videos: {[v for v in all_videos if v['channel'] == 'User']})

    Competitors:
    {json.dumps(competitor_videos, default=str)}

    Identify:
    1. Gaps: What high-performing topics/formats are competitors doing that I am missing?
    2. Pillars: Recommend 3 content pillars based on competitor wins.
    3. Ideas: Generate 3 specific video ideas (Title + Brief Concept) that steal their strategy but improve it.
    4. Hook Intelligence:
       - Extract common hook patterns repeated across competitors.
       - Provide concrete hook templates the user can adapt.
       - Provide specific competitor hook title examples.
       - Split hook rankings and templates by short-form vs long-form based on duration.
       - Use format definition: short_form <= {SHORT_FORM_MAX_SECONDS}s, long_form > {SHORT_FORM_MAX_SECONDS}s.
    5. Winner Pattern Signals:
       - Rank top topics by views/day velocity.
       - Estimate correlation between hook style strength and velocity.
       - Return top 5 videos by views/day.
    6. Framework Playbook:
       - Infer sequence adoption rates: authority_hook -> fast_proof -> framework_steps -> CTA.
       - Return CTA distribution.
    7. Repurpose Plan:
       - Output one core angle with YouTube Shorts, Instagram Reels, and TikTok edit directives.

    Return JSON:
    {{
        "gap_analysis": ["point 1", "point 2"],
        "content_pillars": ["pillar 1", "pillar 2"],
        "video_ideas": [
            {{"title": "...", "concept": "..."}}
        ],
        "hook_intelligence": {{
            "summary": "...",
            "format_definition": "short_form <= {SHORT_FORM_MAX_SECONDS}s, long_form > {SHORT_FORM_MAX_SECONDS}s",
            "common_patterns": [
                {{
                    "pattern": "Question Hook",
                    "frequency": 4,
                    "competitor_count": 2,
                    "avg_views": 120000,
                    "examples": ["..."],
                    "template": "..."
                }}
            ],
            "recommended_hooks": ["..."],
            "competitor_examples": [
                {{"competitor": "...", "hooks": ["..."]}}
            ],
            "format_breakdown": {{
                "short_form": {{
                    "format": "short_form",
                    "label": "Short-form (<= {SHORT_FORM_MAX_SECONDS}s)",
                    "video_count": 6,
                    "summary": "...",
                    "common_patterns": [
                        {{
                            "pattern": "Question Hook",
                            "frequency": 3,
                            "competitor_count": 2,
                            "avg_views": 90000,
                            "examples": ["..."],
                            "template": "..."
                        }}
                    ],
                    "recommended_hooks": ["..."],
                    "competitor_examples": [{{"competitor": "...", "hooks": ["..."]}}]
                }},
                "long_form": {{
                    "format": "long_form",
                    "label": "Long-form (> {SHORT_FORM_MAX_SECONDS}s)",
                    "video_count": 4,
                    "summary": "...",
                    "common_patterns": [
                        {{
                            "pattern": "How-To Hook",
                            "frequency": 2,
                            "competitor_count": 2,
                            "avg_views": 120000,
                            "examples": ["..."],
                            "template": "..."
                        }}
                    ],
                    "recommended_hooks": ["..."],
                    "competitor_examples": [{{"competitor": "...", "hooks": ["..."]}}]
                }}
            }}
        }},
        "winner_pattern_signals": {{
            "summary": "...",
            "sample_size": 80,
            "top_topics_by_velocity": [{{"topic": "...", "count": 10, "avg_views_per_day": 4200.5}}],
            "hook_velocity_correlation": 0.42,
            "top_videos_by_velocity": [{{"channel": "...", "title": "...", "views": 120000, "views_per_day": 3500.2, "hook_pattern": "Question Hook"}}]
        }},
        "framework_playbook": {{
            "summary": "...",
            "stage_adoption": {{"authority_hook": 0.76, "fast_proof": 0.64, "framework_steps": 0.58, "open_loop": 0.41}},
            "cta_distribution": {{"comment_prompt": 15, "follow_prompt": 8}},
            "dominant_sequence": ["authority_hook", "fast_proof", "framework_steps", "cta"],
            "execution_notes": ["...", "..."]
        }},
        "repurpose_plan": {{
            "summary": "...",
            "core_angle": "...",
            "youtube_shorts": {{"duration_target_s": 45, "hook_template": "...", "edit_directives": ["..."]}},
            "instagram_reels": {{"duration_target_s": 35, "hook_template": "...", "edit_directives": ["..."]}},
            "tiktok": {{"duration_target_s": 28, "hook_template": "...", "edit_directives": ["..."]}}
        }}
    }}
    """

    from multimodal.llm import get_openai_client

    try:
        oa_client = get_openai_client(settings.OPENAI_API_KEY)
        if oa_client is None:
            raise ValueError("OpenAI API key missing; using deterministic fallback blueprint.")

        response = oa_client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        parsed = json.loads(content)
        return _normalize_blueprint_payload(parsed, deterministic_blueprint)
    except Exception as e:
        print(f"LLM Error: {e}")
        return deterministic_blueprint
