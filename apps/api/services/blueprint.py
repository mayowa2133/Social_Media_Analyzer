"""
Service for generating Competitor Blueprints.
"""

import asyncio
import json
import logging
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from config import settings, require_youtube_api_key
from ingestion.youtube import create_youtube_client_with_api_key
from models.competitor import Competitor
from models.connection import Connection
from models.profile import Profile

logger = logging.getLogger(__name__)

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
SERIES_ANCHOR_STOP_WORDS = TOPIC_STOP_WORDS | {
    "part",
    "episode",
    "ep",
    "pt",
    "season",
    "series",
    "update",
    "news",
}
TRANSCRIPT_FETCH_TIMEOUT_SECONDS = 6.0
TRANSCRIPT_FETCH_CONCURRENCY = 6
TRUE_TRANSCRIPT_SOURCES = {"youtube_transcript_api", "youtube_captions"}
TRANSCRIPT_CACHE_KEY_PREFIX = "spc:transcript:"
SHORT_PLATFORMS = {"youtube_shorts", "instagram_reels", "tiktok"}
SCRIPT_PLATFORM_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "youtube_shorts": {
        "duration_target_s": 45,
        "hook_deadline_s": 2,
        "cta": "comment_prompt",
        "cadence": "high",
        "supports_short_form": True,
    },
    "instagram_reels": {
        "duration_target_s": 35,
        "hook_deadline_s": 2,
        "cta": "save_prompt",
        "cadence": "high",
        "supports_short_form": True,
    },
    "tiktok": {
        "duration_target_s": 28,
        "hook_deadline_s": 1,
        "cta": "follow_prompt",
        "cadence": "very_high",
        "supports_short_form": True,
    },
    "youtube_long": {
        "duration_target_s": 420,
        "hook_deadline_s": 12,
        "cta": "comment_prompt",
        "cadence": "moderate",
        "supports_short_form": False,
    },
}


def _get_youtube_client():
    api_key = require_youtube_api_key()
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


def _series_anchor_from_title(title: str) -> str:
    normalized = re.sub(r"\s+", " ", str(title or "").strip().lower())
    if not normalized:
        return ""

    normalized = re.sub(
        r"\b(part|episode|ep|pt|season|day)\s*#?\s*\d+\b",
        " ",
        normalized,
        flags=re.IGNORECASE,
    )
    split_candidates = re.split(r"[:|–—-]", normalized)
    candidate = split_candidates[0] if split_candidates else normalized
    tokens = [
        token
        for token in re.findall(r"[a-z0-9][a-z0-9']*", candidate)
        if token not in SERIES_ANCHOR_STOP_WORDS
    ]
    if len(tokens) < 2:
        tokens = [
            token
            for token in re.findall(r"[a-z0-9][a-z0-9']*", normalized)
            if token not in SERIES_ANCHOR_STOP_WORDS
        ]
    if len(tokens) < 2:
        return ""
    return " ".join(tokens[:5])


def _humanize_anchor(anchor: str) -> str:
    words = [word for word in str(anchor or "").split(" ") if word]
    if not words:
        return "Series"
    return " ".join(words).title()


def _empty_series_intelligence(summary: str = "Not enough competitor data to detect recurring series.") -> Dict[str, Any]:
    return {
        "summary": summary,
        "sample_size": 0,
        "total_detected_series": 0,
        "series": [],
    }


def _build_series_intelligence(competitor_videos: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not competitor_videos:
        return _empty_series_intelligence()

    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for video in competitor_videos:
        title = str(video.get("title", "") or "")
        anchor = _series_anchor_from_title(title)
        if not anchor:
            continue
        grouped[anchor].append(video)

    series_rows: List[Dict[str, Any]] = []
    for anchor, rows in grouped.items():
        if len(rows) < 2:
            continue
        channels = sorted(
            {
                str(row.get("channel", "Competitor")).strip() or "Competitor"
                for row in rows
            }
        )
        views = [_safe_int(row.get("views", 0)) for row in rows]
        velocities = [float(row.get("views_per_day", 0.0) or 0.0) for row in rows]
        top_titles = [
            str(row.get("title", "")).strip()
            for row in sorted(rows, key=lambda item: _safe_int(item.get("views", 0)), reverse=True)
            if str(row.get("title", "")).strip()
        ][:4]
        top_hook = _detect_hook_pattern(top_titles[0]) if top_titles else "Direct Outcome Hook"
        display_key = _humanize_anchor(anchor)
        series_rows.append(
            {
                "series_key": display_key,
                "series_key_slug": anchor.replace(" ", "_"),
                "video_count": len(rows),
                "competitor_count": len(channels),
                "avg_views": _safe_int(sum(views) / max(len(views), 1)),
                "avg_views_per_day": round(sum(velocities) / max(len(velocities), 1), 2),
                "top_titles": top_titles,
                "channels": channels[:5],
                "recommended_angle": (
                    f"Use '{display_key}' as a repeatable arc and open with {top_hook} "
                    "to keep each episode instantly recognizable."
                ),
            }
        )

    series_rows.sort(
        key=lambda row: (
            float(row.get("avg_views_per_day", 0.0) or 0.0),
            _safe_int(row.get("video_count", 0)),
            _safe_int(row.get("avg_views", 0)),
        ),
        reverse=True,
    )

    if not series_rows:
        return _empty_series_intelligence(
            "Competitor videos were analyzed, but no recurring multi-episode series pattern was detected."
        )

    return {
        "summary": (
            "Recurring competitor series extracted from repeated title anchors and ranked by velocity."
        ),
        "sample_size": len(competitor_videos),
        "total_detected_series": len(series_rows),
        "series": series_rows[:8],
    }


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
            "stage_adoption": {
                "authority_hook": 0.0,
                "fast_proof": 0.0,
                "framework_steps": 0.0,
                "open_loop": 0.0,
            },
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


def _extract_transcript_payload_sync(
    client: Any,
    video_id: str,
    description_fallback: str,
    title_fallback: str,
) -> Dict[str, Any]:
    # 1) Transcript API first.
    try:
        from youtube_transcript_api import YouTubeTranscriptApi  # type: ignore

        transcript_items = YouTubeTranscriptApi.get_transcript(video_id, languages=["en"])
        chunks = [item.get("text", "").strip() for item in transcript_items[:120] if item.get("text")]
        transcript_text = " ".join(chunks).strip()
        if transcript_text:
            return {
                "text": transcript_text[:9000],
                "source": "youtube_transcript_api",
                "char_count": len(transcript_text[:9000]),
                "segment_count": len(chunks),
            }
    except Exception:
        pass

    # 2) YouTube captions if actual text is available.
    try:
        caption_data = client.get_video_captions(video_id)
        if isinstance(caption_data, str):
            caption_text = caption_data.strip()
            if caption_text and not caption_text.lower().startswith("captions available"):
                caption_segments = [s for s in re.split(r"[.!?\n]+", caption_text) if s.strip()]
                return {
                    "text": caption_text[:9000],
                    "source": "youtube_captions",
                    "char_count": len(caption_text[:9000]),
                    "segment_count": len(caption_segments),
                }
    except Exception:
        pass

    # 3) Description fallback.
    description_text = str(description_fallback or "").strip()
    if description_text:
        return {
            "text": description_text[:3000],
            "source": "description_fallback",
            "char_count": len(description_text[:3000]),
            "segment_count": 0,
        }

    # 4) Title fallback.
    title_text = str(title_fallback or "").strip() or "Untitled video"
    return {
        "text": title_text[:300],
        "source": "title_fallback",
        "char_count": len(title_text[:300]),
        "segment_count": 0,
    }


async def _extract_transcript_payload(
    client: Any,
    video_id: str,
    description_fallback: str,
    title_fallback: str,
    semaphore: asyncio.Semaphore,
) -> Dict[str, Any]:
    async with semaphore:
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(
                    _extract_transcript_payload_sync,
                    client,
                    video_id,
                    description_fallback,
                    title_fallback,
                ),
                timeout=TRANSCRIPT_FETCH_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            logger.warning("Transcript extraction timeout/failure for %s: %s", video_id, exc)
            description_text = str(description_fallback or "").strip()
            if description_text:
                return {
                    "text": description_text[:3000],
                    "source": "description_fallback",
                    "char_count": len(description_text[:3000]),
                    "segment_count": 0,
                }
            title_text = str(title_fallback or "").strip() or "Untitled video"
            return {
                "text": title_text[:300],
                "source": "title_fallback",
                "char_count": len(title_text[:300]),
                "segment_count": 0,
            }


def _transcript_cache_key(video_id: str) -> str:
    return f"{TRANSCRIPT_CACHE_KEY_PREFIX}{video_id}"


def _is_valid_transcript_payload(payload: Any) -> bool:
    return (
        isinstance(payload, dict)
        and isinstance(payload.get("text"), str)
        and isinstance(payload.get("source"), str)
    )


async def _load_cached_transcript_payloads(video_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    if not video_ids:
        return {}

    ttl = max(int(settings.TRANSCRIPT_CACHE_TTL_SECONDS), 1)
    if ttl <= 0:
        return {}

    client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        keys = [_transcript_cache_key(video_id) for video_id in video_ids]
        raw_payloads = await client.mget(keys)
        cached: Dict[str, Dict[str, Any]] = {}
        for idx, raw in enumerate(raw_payloads):
            if not raw:
                continue
            try:
                parsed = json.loads(raw)
            except Exception:
                continue
            if _is_valid_transcript_payload(parsed):
                cached[video_ids[idx]] = parsed
        return cached
    except Exception as exc:
        logger.warning("Transcript cache read failed: %s", exc)
        return {}
    finally:
        await client.aclose()


async def _store_cached_transcript_payloads(payload_by_video_id: Dict[str, Dict[str, Any]]) -> None:
    if not payload_by_video_id:
        return

    ttl = max(int(settings.TRANSCRIPT_CACHE_TTL_SECONDS), 1)
    if ttl <= 0:
        return

    client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        pipe = client.pipeline()
        for video_id, payload in payload_by_video_id.items():
            if not _is_valid_transcript_payload(payload):
                continue
            pipe.setex(_transcript_cache_key(video_id), ttl, json.dumps(payload, separators=(",", ":"), ensure_ascii=True))
        await pipe.execute()
    except Exception as exc:
        logger.warning("Transcript cache write failed: %s", exc)
    finally:
        await client.aclose()


def _build_transcript_quality(videos: List[Dict[str, Any]]) -> Dict[str, Any]:
    sample_size = len(videos)
    by_source: Dict[str, int] = defaultdict(int)
    true_count = 0
    for video in videos:
        source = str(video.get("transcript_source", "unknown") or "unknown")
        by_source[source] += 1
        if source in TRUE_TRANSCRIPT_SOURCES:
            true_count += 1

    coverage = (true_count / sample_size) if sample_size else 0.0
    fallback_ratio = (1.0 - coverage) if sample_size else 1.0
    dominant_source = max(by_source, key=lambda key: by_source[key]) if by_source else "none"

    notes = [
        f"Transcript coverage ratio is {round(coverage, 3)} based on {sample_size} competitor videos.",
        f"Dominant transcript source: {dominant_source}.",
    ]
    if fallback_ratio > 0.5:
        notes.append("More than half of videos used fallback text; expect lower precision in framework extraction.")
    else:
        notes.append("Most videos used transcript/caption text, improving reliability of hook and framework signals.")

    return {
        "sample_size": sample_size,
        "by_source": dict(sorted(by_source.items(), key=lambda item: item[1], reverse=True)),
        "transcript_coverage_ratio": round(coverage, 3),
        "fallback_ratio": round(fallback_ratio, 3),
        "notes": notes,
    }


def _build_velocity_actions(
    winner_signals: Dict[str, Any],
    competitor_framework: Dict[str, Any],
    user_framework: Dict[str, Any],
    hook_intelligence: Dict[str, Any],
) -> List[Dict[str, Any]]:
    actions: List[Dict[str, Any]] = []

    topics = winner_signals.get("top_topics_by_velocity", [])
    if isinstance(topics, list) and topics:
        top_topic = topics[0]
        topic_name = str(top_topic.get("topic", "high-velocity topic"))
        actions.append(
            {
                "title": f"Double down on '{topic_name}' velocity topic",
                "why": "Highest velocity competitor topics are compounding the fastest in this niche.",
                "evidence": [
                    f"Top topic: {topic_name}",
                    f"Avg views/day: {top_topic.get('avg_views_per_day', 0)}",
                    f"Topic sample count: {top_topic.get('count', 0)} videos",
                ],
                "execution_steps": [
                    f"Publish 2-3 videos around '{topic_name}' in the next cycle.",
                    "Reuse proven structure from top competitor titles while changing examples/proof.",
                    "Measure views/day after 72 hours and keep only winning angle variants.",
                ],
                "target_metric": "views_per_day",
                "expected_effect": "Higher content velocity and faster discovery in recommendations.",
            }
        )

    correlation = float(winner_signals.get("hook_velocity_correlation", 0.0) or 0.0)
    common_patterns = hook_intelligence.get("common_patterns", [])
    top_pattern = "Direct Outcome Hook"
    if isinstance(common_patterns, list) and common_patterns:
        top_pattern = str(common_patterns[0].get("pattern", top_pattern))
    actions.append(
        {
            "title": f"Adopt '{top_pattern}' hook format consistently",
            "why": "Hook style consistency is linked to velocity in the competitor set.",
            "evidence": [
                f"Hook/velocity correlation: {round(correlation, 3)}",
                f"Top repeated pattern: {top_pattern}",
            ],
            "execution_steps": [
                "Use one hook template family for the next 5 uploads to improve pattern learning.",
                "Lead with concrete outcome and tighten first line to one breath.",
                "A/B test title line variants while preserving the same opening structure.",
            ],
            "target_metric": "opening_retention",
            "expected_effect": "Higher early hold and improved click-to-watch conversion.",
        }
    )

    competitor_stage = competitor_framework.get("stage_adoption", {}) if isinstance(competitor_framework, dict) else {}
    user_stage = user_framework.get("stage_adoption", {}) if isinstance(user_framework, dict) else {}
    stage_keys = ("authority_hook", "fast_proof", "framework_steps", "open_loop")
    largest_key = "fast_proof"
    largest_gap = 0.0
    for key in stage_keys:
        gap = float(competitor_stage.get(key, 0.0) or 0.0) - float(user_stage.get(key, 0.0) or 0.0)
        if gap > largest_gap:
            largest_gap = gap
            largest_key = key

    stage_label = largest_key.replace("_", " ")
    actions.append(
        {
            "title": f"Close the '{stage_label}' framework gap",
            "why": "Competitors execute this stage more often in winning videos.",
            "evidence": [
                f"Competitor adoption: {round(float(competitor_stage.get(largest_key, 0.0) or 0.0) * 100, 1)}%",
                f"Your adoption: {round(float(user_stage.get(largest_key, 0.0) or 0.0) * 100, 1)}%",
                f"Gap: {round(largest_gap * 100, 1)} points",
            ],
            "execution_steps": [
                "Script this stage explicitly before recording and keep it in every draft.",
                "Place proof earlier and collapse setup to avoid delayed payoff.",
                "Track retention at each major segment to verify gap closure.",
            ],
            "target_metric": "mid_video_retention",
            "expected_effect": "Improved continuation through the body and better completion rates.",
        }
    )

    return actions[:3]


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


def _normalize_transcript_quality(raw: Any, fallback: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return fallback

    by_source: Dict[str, int] = {}
    raw_by_source = raw.get("by_source", {})
    if isinstance(raw_by_source, dict):
        for key, value in raw_by_source.items():
            source = str(key).strip()
            if source:
                by_source[source] = _safe_int(value, 0)
    if not by_source:
        by_source = fallback.get("by_source", {})

    notes = _safe_list_of_strings(raw.get("notes", []))
    if not notes:
        notes = fallback.get("notes", [])

    return {
        "sample_size": _safe_int(raw.get("sample_size", fallback.get("sample_size", 0))),
        "by_source": by_source,
        "transcript_coverage_ratio": float(
            raw.get("transcript_coverage_ratio", fallback.get("transcript_coverage_ratio", 0.0)) or 0.0
        ),
        "fallback_ratio": float(raw.get("fallback_ratio", fallback.get("fallback_ratio", 1.0)) or 0.0),
        "notes": notes,
    }


def _normalize_velocity_actions(raw: Any, fallback: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    actions: List[Dict[str, Any]] = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", "")).strip()
            why = str(item.get("why", "")).strip()
            if not title or not why:
                continue
            evidence = _safe_list_of_strings(item.get("evidence", []))
            execution_steps = _safe_list_of_strings(item.get("execution_steps", []))
            actions.append(
                {
                    "title": title,
                    "why": why,
                    "evidence": evidence,
                    "execution_steps": execution_steps,
                    "target_metric": str(item.get("target_metric", "")).strip() or "views_per_day",
                    "expected_effect": str(item.get("expected_effect", "")).strip() or "Improve performance consistency.",
                }
            )
    return actions or fallback


def _normalize_series_intelligence(raw: Any, fallback: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return fallback

    series_rows: List[Dict[str, Any]] = []
    raw_series = raw.get("series", [])
    if isinstance(raw_series, list):
        for item in raw_series:
            if not isinstance(item, dict):
                continue
            series_key = str(item.get("series_key", "")).strip()
            if not series_key:
                continue
            series_rows.append(
                {
                    "series_key": series_key,
                    "series_key_slug": str(item.get("series_key_slug", "")).strip()
                    or series_key.lower().replace(" ", "_"),
                    "video_count": _safe_int(item.get("video_count", 0)),
                    "competitor_count": _safe_int(item.get("competitor_count", 0)),
                    "avg_views": _safe_int(item.get("avg_views", 0)),
                    "avg_views_per_day": float(item.get("avg_views_per_day", 0.0) or 0.0),
                    "top_titles": _safe_list_of_strings(item.get("top_titles", []))[:4],
                    "channels": _safe_list_of_strings(item.get("channels", []))[:5],
                    "recommended_angle": str(item.get("recommended_angle", "")).strip(),
                }
            )

    if not series_rows:
        series_rows = fallback.get("series", [])

    return {
        "summary": str(raw.get("summary", fallback.get("summary", ""))).strip() or fallback.get("summary", ""),
        "sample_size": _safe_int(raw.get("sample_size", fallback.get("sample_size", 0))),
        "total_detected_series": _safe_int(
            raw.get("total_detected_series", fallback.get("total_detected_series", len(series_rows)))
        ),
        "series": series_rows,
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
    transcript_quality = _normalize_transcript_quality(
        payload.get("transcript_quality"),
        fallback["transcript_quality"],
    )
    velocity_actions = _normalize_velocity_actions(
        payload.get("velocity_actions"),
        fallback["velocity_actions"],
    )
    series_intelligence = _normalize_series_intelligence(
        payload.get("series_intelligence"),
        fallback["series_intelligence"],
    )

    return {
        "gap_analysis": gap_analysis,
        "content_pillars": content_pillars,
        "video_ideas": video_ideas,
        "hook_intelligence": hook_intelligence,
        "winner_pattern_signals": winner_pattern_signals,
        "framework_playbook": framework_playbook,
        "repurpose_plan": repurpose_plan,
        "transcript_quality": transcript_quality,
        "velocity_actions": velocity_actions,
        "series_intelligence": series_intelligence,
    }


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _resolve_platform(platform: Any) -> Tuple[str, Dict[str, Any]]:
    key = str(platform or "youtube_shorts").strip().lower()
    if key not in SCRIPT_PLATFORM_DEFAULTS:
        key = "youtube_shorts"
    return key, SCRIPT_PLATFORM_DEFAULTS[key]


def _resolve_series_template(series_intelligence: Dict[str, Any], template_series_key: str) -> Optional[Dict[str, Any]]:
    rows = series_intelligence.get("series", []) if isinstance(series_intelligence, dict) else []
    if not isinstance(rows, list) or not rows:
        return None

    requested = str(template_series_key or "").strip().lower()
    if requested:
        for row in rows:
            if not isinstance(row, dict):
                continue
            key_value = str(row.get("series_key", "")).strip().lower()
            slug_value = str(row.get("series_key_slug", "")).strip().lower()
            if requested in {key_value, slug_value}:
                return row
    first = rows[0]
    return first if isinstance(first, dict) else None


def _resolve_hook_template(blueprint: Dict[str, Any], platform_key: str) -> str:
    hook_data = blueprint.get("hook_intelligence", {}) if isinstance(blueprint, dict) else {}
    if not isinstance(hook_data, dict):
        return HOOK_TEMPLATE_MAP["Direct Outcome Hook"]

    format_key = "short_form" if platform_key in SHORT_PLATFORMS else "long_form"
    format_breakdown = hook_data.get("format_breakdown", {})
    if isinstance(format_breakdown, dict):
        profile = format_breakdown.get(format_key, {})
        if isinstance(profile, dict):
            recommended = profile.get("recommended_hooks", [])
            if isinstance(recommended, list):
                for template in recommended:
                    value = str(template).strip()
                    if value:
                        return value
            common = profile.get("common_patterns", [])
            if isinstance(common, list):
                for pattern in common:
                    if isinstance(pattern, dict):
                        template = str(pattern.get("template", "")).strip()
                        if template:
                            return template

    recommended_hooks = hook_data.get("recommended_hooks", [])
    if isinstance(recommended_hooks, list):
        for template in recommended_hooks:
            value = str(template).strip()
            if value:
                return value

    return HOOK_TEMPLATE_MAP["Direct Outcome Hook"]


class _SafeTemplateDict(dict):
    def __missing__(self, key: str) -> str:
        return f"{{{key}}}"


def _render_hook_template(template: str, topic: str, audience: str, objective: str) -> str:
    template_text = str(template or HOOK_TEMPLATE_MAP["Direct Outcome Hook"]).strip()
    objective_text = str(objective or "more views and stronger retention").strip()
    topic_text = str(topic or "your niche").strip()
    audience_text = str(audience or "your audience").strip()

    token_values = _SafeTemplateDict(
        pain_point=f"{topic_text} content underperforming",
        result=objective_text,
        timeframe="30 days",
        number="3",
        option_a=f"{topic_text} quick tips",
        option_b=f"{topic_text} deep dives",
        audience=audience_text,
        year=str(datetime.now(timezone.utc).year),
        topic=topic_text,
        tactic=f"{topic_text} posting framework",
        duration="14 days",
        outcome=objective_text,
        common_obstacle="guesswork",
    )
    try:
        rendered = template_text.format_map(token_values)
    except Exception:
        rendered = template_text
    return re.sub(r"\s+", " ", rendered).strip()


def _series_title(mode: str, niche: str, topic_seed: str, template: Optional[Dict[str, Any]]) -> str:
    if mode == "competitor_template" and template:
        return f"{template.get('series_key', 'Competitor Series')} Remix"
    base = str(niche or topic_seed or "Growth").strip()
    return f"{base.title()} Sprint Series"


def _series_plan_episode_outline(index: int) -> Tuple[str, str, str]:
    blueprints = [
        ("Myth Breakdown", "Expose a common wrong assumption with fast proof.", "Show one before/after screenshot or stat."),
        ("Proof Stack", "Show one tactic and immediate measurable outcome.", "Use one concrete metric within first 6 seconds."),
        ("Framework", "Teach a repeatable 3-step process viewers can copy today.", "Add numbered on-screen steps."),
        ("Case Study", "Walk through a single example and explain why it worked.", "Use timestamps or chapter cards."),
        ("Mistakes", "List mistakes causing weak retention and how to fix them.", "Contrast weak vs strong execution."),
        ("Optimization", "Improve packaging, pacing, and CTA in one pass.", "Show edits side-by-side."),
        ("Trend Adaptation", "Apply the framework to a timely topic in your niche.", "Tie the trend to a concrete user pain point."),
        ("Audience Q&A", "Answer one recurring question and convert it into a framework.", "Use a comment screenshot as the opener."),
        ("Challenge", "Run a short experiment and report outcome honestly.", "Commit to a deadline and show final numbers."),
        ("Checklist", "Deliver a final checklist episode to lock in consistency.", "Provide a downloadable or save-friendly summary."),
    ]
    selected = blueprints[(max(index, 1) - 1) % len(blueprints)]
    return selected[0], selected[1], selected[2]


def _build_series_plan(blueprint: Dict[str, Any], request: Dict[str, Any]) -> Dict[str, Any]:
    mode = str(request.get("mode", "scratch")).strip()
    if mode not in {"scratch", "competitor_template"}:
        mode = "scratch"

    platform_key, platform_defaults = _resolve_platform(request.get("platform"))
    episodes_count = _safe_int(request.get("episodes", 5), 5)
    episodes_count = min(max(episodes_count, 3), 12)

    niche = str(request.get("niche", "")).strip()
    audience = str(request.get("audience", "")).strip() or "creators in your niche"
    objective = str(request.get("objective", "")).strip() or "increase watch time, shares, and follower growth"

    winner_signals = blueprint.get("winner_pattern_signals", {}) if isinstance(blueprint, dict) else {}
    top_topics = winner_signals.get("top_topics_by_velocity", []) if isinstance(winner_signals, dict) else []
    top_topic = "creator growth"
    if isinstance(top_topics, list) and top_topics:
        top_topic = str(top_topics[0].get("topic", top_topic)).strip() or top_topic
    topic_seed = niche or top_topic

    series_intelligence = blueprint.get("series_intelligence", {}) if isinstance(blueprint, dict) else {}
    template_series = _resolve_series_template(
        series_intelligence if isinstance(series_intelligence, dict) else {},
        str(request.get("template_series_key", "")),
    )
    if mode == "competitor_template" and not template_series:
        mode = "scratch"

    title = _series_title(mode, niche, topic_seed, template_series)
    hook_template = _resolve_hook_template(blueprint, platform_key)
    cadence = "3 posts/week" if platform_key in SHORT_PLATFORMS else "2 posts/week"

    episodes: List[Dict[str, Any]] = []
    for idx in range(1, episodes_count + 1):
        outline_title, goal, proof_idea = _series_plan_episode_outline(idx)
        working_title = f"{title} Ep {idx}: {outline_title} for {topic_seed.title()}"
        episodes.append(
            {
                "episode_number": idx,
                "working_title": working_title,
                "hook_template": hook_template,
                "content_goal": goal,
                "proof_idea": proof_idea,
                "duration_target_s": _safe_int(platform_defaults.get("duration_target_s", 45), 45),
                "cta": str(platform_defaults.get("cta", "comment_prompt")),
            }
        )

    why_items = [
        "The plan reuses competitor-winning hook structures but keeps your own angle and examples.",
        "Episodes are sequenced to maximize repeat viewing and follow-through across the series.",
        f"Cadence and duration are optimized for {platform_key.replace('_', ' ')} behavior patterns.",
    ]
    if template_series:
        why_items.append(
            f"Template source '{template_series.get('series_key', 'Competitor Series')}' already shows repeated velocity in the tracked competitor set."
        )

    response: Dict[str, Any] = {
        "mode": mode,
        "series_title": title,
        "series_thesis": (
            f"Create a repeatable {episodes_count}-episode arc around '{topic_seed}' for {audience}, "
            f"with each episode pushing toward {objective}."
        ),
        "platform": platform_key,
        "episodes_count": episodes_count,
        "publishing_cadence": cadence,
        "success_metrics": [
            "3-second hold rate",
            "average view duration",
            "shares + saves per 1,000 views",
            "comments per 1,000 views",
        ],
        "why_this_will_work": why_items,
        "episodes": episodes,
    }
    if template_series:
        response["source_template"] = {
            "series_key": str(template_series.get("series_key", "")),
            "video_count": _safe_int(template_series.get("video_count", 0)),
            "competitor_count": _safe_int(template_series.get("competitor_count", 0)),
            "channels": _safe_list_of_strings(template_series.get("channels", [])),
            "top_titles": _safe_list_of_strings(template_series.get("top_titles", [])),
        }
    return response


def _build_script_sections(
    platform_key: str,
    topic: str,
    objective: str,
    audience: str,
    hook_line: str,
    duration_target_s: int,
) -> List[Dict[str, str]]:
    if platform_key in SHORT_PLATFORMS:
        return [
            {"section": "Hook", "time_window": "0-2s", "text": hook_line},
            {
                "section": "Proof",
                "time_window": "2-6s",
                "text": f"Show one concrete result tied to {topic} so viewers trust the claim instantly.",
            },
            {
                "section": "Value Stack",
                "time_window": "6-18s",
                "text": f"Deliver 2-3 fast steps your {audience} can apply today to achieve {objective}.",
            },
            {
                "section": "Pattern Interrupt",
                "time_window": "18-22s",
                "text": "Switch camera angle or visual format and restate the biggest insight in one line.",
            },
            {
                "section": "CTA",
                "time_window": f"22-{duration_target_s}s",
                "text": "Ask for one action only: comment a keyword to get the checklist.",
            },
        ]

    return [
        {"section": "Hook + Promise", "time_window": "0-12s", "text": hook_line},
        {
            "section": "Proof + Context",
            "time_window": "12-45s",
            "text": f"Show receipts and explain why this matters for {audience}.",
        },
        {
            "section": "Framework",
            "time_window": "45-210s",
            "text": f"Break the method into 3 steps and tie each step directly to {objective}.",
        },
        {
            "section": "Case Example",
            "time_window": "210-330s",
            "text": f"Walk through one practical example in {topic} and highlight the decision points.",
        },
        {
            "section": "CTA",
            "time_window": f"330-{duration_target_s}s",
            "text": "Ask one clear CTA: comment your niche for a custom follow-up framework.",
        },
    ]


def _build_viral_script(blueprint: Dict[str, Any], request: Dict[str, Any]) -> Dict[str, Any]:
    platform_key, platform_defaults = _resolve_platform(request.get("platform"))
    topic = str(request.get("topic", "")).strip() or "content growth"
    audience = str(request.get("audience", "")).strip() or "creators"
    objective = str(request.get("objective", "")).strip() or "higher watch time and shares"
    tone = str(request.get("tone", "bold")).strip().lower()

    desired_duration = _safe_int(request.get("desired_duration_s"), 0)
    default_duration = _safe_int(platform_defaults.get("duration_target_s", 45), 45)
    duration_target_s = desired_duration if desired_duration > 0 else default_duration
    duration_target_s = min(max(duration_target_s, 15), 900)

    hook_template = _resolve_hook_template(blueprint, platform_key)
    hook_line = _render_hook_template(hook_template, topic=topic, audience=audience, objective=objective)
    if tone == "conversational":
        hook_line = f"Quick one: {hook_line}"
    elif tone == "expert":
        hook_line = f"Data-backed take: {hook_line}"

    sections = _build_script_sections(
        platform_key=platform_key,
        topic=topic,
        objective=objective,
        audience=audience,
        hook_line=hook_line,
        duration_target_s=duration_target_s,
    )

    on_screen_text = [
        hook_line,
        f"{topic.title()} Framework: 3 steps",
        f"Comment 'PLAYBOOK' for the checklist",
    ]
    shot_list = [
        "Frame 1: bold hook text + direct eye contact.",
        "Frame 2: proof visual (analytics screenshot or before/after).",
        "Frame 3: fast step list with numbered overlays.",
        "Final frame: single CTA card with high contrast text.",
    ]
    caption_options = [
        f"{topic.title()} is not random. Here is the exact playbook I use for {objective}.",
        f"If your {topic} videos stall, run this sequence and track retention after 72 hours.",
        f"Steal this {topic} framework and comment PLAYBOOK if you want the checklist version.",
    ]

    hashtags = []
    for token in _extract_topic_keywords(topic):
        normalized = re.sub(r"[^a-zA-Z0-9]", "", token)
        if not normalized:
            continue
        hashtags.append(f"#{normalized[:24]}")
    for default_tag in ["#creatorgrowth", "#contentstrategy", "#viralvideo"]:
        if default_tag not in hashtags:
            hashtags.append(default_tag)
    hashtags = hashtags[:8]

    hook_strength = 72
    if re.search(r"\b\d+\b", hook_line):
        hook_strength += 10
    if "?" in hook_line:
        hook_strength += 6
    if any(keyword in hook_line.lower() for keyword in ("how", "why", "secret", "mistake", "stop")):
        hook_strength += 8
    hook_strength = min(hook_strength, 98)

    retention_design = 70
    if platform_key in SHORT_PLATFORMS:
        retention_design += 12
    if len(sections) >= 5:
        retention_design += 8
    retention_design = min(retention_design, 96)

    shareability = 68
    if "checklist" in " ".join(caption_options).lower():
        shareability += 10
    if "comment" in sections[-1]["text"].lower():
        shareability += 8
    shareability = min(shareability, 95)

    overall = round((hook_strength * 0.4) + (retention_design * 0.35) + (shareability * 0.25), 1)

    velocity_actions = blueprint.get("velocity_actions", []) if isinstance(blueprint, dict) else []
    improvement_notes = []
    if isinstance(velocity_actions, list):
        for action in velocity_actions[:2]:
            if isinstance(action, dict):
                title = str(action.get("title", "")).strip()
                if title:
                    improvement_notes.append(title)
    if not improvement_notes:
        improvement_notes = [
            "Test two hook-line variants against the same edit structure.",
            "Cut any setup that delays payoff beyond the hook deadline.",
            "Keep one CTA objective to avoid dilution.",
        ]

    response: Dict[str, Any] = {
        "platform": platform_key,
        "topic": topic,
        "audience": audience,
        "objective": objective,
        "tone": tone,
        "duration_target_s": duration_target_s,
        "hook_deadline_s": _safe_int(platform_defaults.get("hook_deadline_s", 2), 2),
        "hook_template": hook_template,
        "hook_line": hook_line,
        "script_sections": sections,
        "on_screen_text": on_screen_text,
        "shot_list": shot_list,
        "caption_options": caption_options,
        "hashtags": hashtags,
        "cta_line": sections[-1]["text"],
        "score_breakdown": {
            "hook_strength": hook_strength,
            "retention_design": retention_design,
            "shareability": shareability,
            "overall": overall,
        },
        "improvement_notes": improvement_notes,
    }

    template_series = _resolve_series_template(
        blueprint.get("series_intelligence", {}) if isinstance(blueprint, dict) else {},
        str(request.get("template_series_key", "")),
    )
    if template_series:
        response["competitor_template"] = {
            "series_key": str(template_series.get("series_key", "")),
            "channels": _safe_list_of_strings(template_series.get("channels", [])),
            "top_titles": _safe_list_of_strings(template_series.get("top_titles", [])),
        }

    return response


async def get_competitor_series_service(user_id: str, db: AsyncSession) -> Dict[str, Any]:
    blueprint = await generate_blueprint_service(user_id, db, use_llm=False)
    series_intelligence = blueprint.get("series_intelligence", {})
    if isinstance(series_intelligence, dict):
        return series_intelligence
    return _empty_series_intelligence()


async def generate_series_plan_service(user_id: str, request: Dict[str, Any], db: AsyncSession) -> Dict[str, Any]:
    blueprint = await generate_blueprint_service(user_id, db, use_llm=False)
    return _build_series_plan(blueprint, request)


async def generate_viral_script_service(user_id: str, request: Dict[str, Any], db: AsyncSession) -> Dict[str, Any]:
    blueprint = await generate_blueprint_service(user_id, db, use_llm=False)
    return _build_viral_script(blueprint, request)


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


async def generate_blueprint_service(user_id: str, db: AsyncSession, use_llm: bool = True) -> Dict[str, Any]:
    """
    Generate a gap analysis and content strategy blueprint.
    """
    user_channel_id, user_channel_name = await _resolve_user_channel(db, user_id)

    result = await db.execute(select(Competitor).where(Competitor.user_id == user_id))
    competitors = result.scalars().all()

    if not competitors:
        empty_winner_signals = _build_winner_pattern_signals([])
        empty_framework = _build_framework_playbook([])
        empty_hooks = _empty_hook_intelligence()
        empty_series = _empty_series_intelligence()
        return {
            "gap_analysis": ["Add competitors to generate a blueprint."],
            "content_pillars": [],
            "video_ideas": [],
            "hook_intelligence": empty_hooks,
            "winner_pattern_signals": empty_winner_signals,
            "framework_playbook": empty_framework,
            "repurpose_plan": _build_repurpose_plan(empty_hooks, empty_winner_signals, empty_framework),
            "transcript_quality": _build_transcript_quality([]),
            "velocity_actions": [],
            "series_intelligence": empty_series,
        }

    client = _get_youtube_client()
    transcript_semaphore = asyncio.Semaphore(TRANSCRIPT_FETCH_CONCURRENCY)

    async def fetch_videos_safe(channel_id: str, label: str) -> List[Dict[str, Any]]:
        try:
            vids = client.get_channel_videos(channel_id, max_results=50)
            vid_ids = [v["id"] for v in vids if v.get("id")]
            details = client.get_video_details(vid_ids)

            ordered_video_ids: List[str] = []
            for video in vids:
                video_id = str(video.get("id", "")).strip()
                if video_id:
                    ordered_video_ids.append(video_id)

            transcript_map: Dict[str, Dict[str, Any]] = await _load_cached_transcript_payloads(ordered_video_ids)
            missing_video_ids = [video_id for video_id in ordered_video_ids if video_id not in transcript_map]

            transcript_tasks: List[asyncio.Task] = []
            for video in vids:
                video_id = str(video.get("id", "")).strip()
                if not video_id or video_id not in missing_video_ids:
                    continue
                transcript_tasks.append(
                    asyncio.create_task(
                        _extract_transcript_payload(
                            client=client,
                            video_id=video_id,
                            description_fallback=str(video.get("description", "") or ""),
                            title_fallback=str(video.get("title", "") or ""),
                            semaphore=transcript_semaphore,
                        )
                    )
                )

            transcript_payloads = await asyncio.gather(*transcript_tasks) if transcript_tasks else []
            fresh_payloads: Dict[str, Dict[str, Any]] = {}
            for idx, video_id in enumerate(missing_video_ids):
                if idx < len(transcript_payloads) and _is_valid_transcript_payload(transcript_payloads[idx]):
                    payload = transcript_payloads[idx]
                    transcript_map[video_id] = payload
                    fresh_payloads[video_id] = payload
            await _store_cached_transcript_payloads(fresh_payloads)

            enriched = []
            for video in vids:
                video_id = video.get("id")
                if not video_id:
                    continue
                detail = details.get(video_id, {})
                description = str(video.get("description", "") or "")
                transcript_payload = transcript_map.get(
                    video_id,
                    {
                        "text": description[:3000],
                        "source": "description_fallback" if description else "title_fallback",
                        "char_count": len(description[:3000]) if description else len(str(video.get("title", "") or "")[:300]),
                        "segment_count": 0,
                    },
                )
                transcript = str(transcript_payload.get("text", "") or "")
                views = _safe_int(detail.get("view_count", 0))
                enriched.append(
                    {
                        "title": video.get("title", ""),
                        "description": description,
                        "transcript": transcript,
                        "transcript_source": str(transcript_payload.get("source", "unknown")),
                        "transcript_char_count": _safe_int(transcript_payload.get("char_count", 0)),
                        "transcript_segment_count": _safe_int(transcript_payload.get("segment_count", 0)),
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
            logger.warning("Error fetching blueprint videos for %s (%s): %s", label, channel_id, e)
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

    user_videos = [v for v in all_videos if v.get("channel") == "User"]
    competitor_videos = [v for v in all_videos if v.get("channel") != "User"]
    hook_intelligence = _build_hook_intelligence(competitor_videos)
    winner_pattern_signals = _build_winner_pattern_signals(competitor_videos)
    framework_playbook = _build_framework_playbook(competitor_videos)
    repurpose_plan = _build_repurpose_plan(hook_intelligence, winner_pattern_signals, framework_playbook)
    transcript_quality = _build_transcript_quality(competitor_videos)
    series_intelligence = _build_series_intelligence(competitor_videos)
    user_framework_playbook = _build_framework_playbook(user_videos)
    velocity_actions = _build_velocity_actions(
        winner_signals=winner_pattern_signals,
        competitor_framework=framework_playbook,
        user_framework=user_framework_playbook,
        hook_intelligence=hook_intelligence,
    )
    logger.info(
        "Blueprint transcript coverage user=%s sample=%s coverage=%s by_source=%s",
        user_id,
        transcript_quality.get("sample_size", 0),
        transcript_quality.get("transcript_coverage_ratio", 0.0),
        transcript_quality.get("by_source", {}),
    )
    logger.info(
        "Blueprint velocity actions user=%s actions=%s",
        user_id,
        len(velocity_actions),
    )

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
        "transcript_quality": transcript_quality,
        "velocity_actions": velocity_actions,
        "series_intelligence": series_intelligence,
    }

    if not use_llm:
        return deterministic_blueprint

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
    8. Transcript Quality:
       - Summarize transcript source coverage and fallback ratio.
    9. Velocity Actions:
       - Output exactly 3 "do this next" actions with evidence + concrete steps.
    10. Series Intelligence:
       - Detect recurring competitor series from repeated title anchors.
       - Rank detected series by average views/day.
       - Include top episode titles and channel examples.

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
        }},
        "transcript_quality": {{
            "sample_size": 80,
            "by_source": {{"youtube_transcript_api": 40, "youtube_captions": 12, "description_fallback": 28}},
            "transcript_coverage_ratio": 0.65,
            "fallback_ratio": 0.35,
            "notes": ["..."]
        }},
        "velocity_actions": [
            {{
                "title": "...",
                "why": "...",
                "evidence": ["..."],
                "execution_steps": ["..."],
                "target_metric": "...",
                "expected_effect": "..."
            }}
        ],
        "series_intelligence": {{
            "summary": "...",
            "sample_size": 60,
            "total_detected_series": 4,
            "series": [
                {{
                    "series_key": "...",
                    "series_key_slug": "...",
                    "video_count": 5,
                    "competitor_count": 2,
                    "avg_views": 120000,
                    "avg_views_per_day": 4200.2,
                    "top_titles": ["..."],
                    "channels": ["..."],
                    "recommended_angle": "..."
                }}
            ]
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
        logger.warning("Blueprint LLM fallback for user %s: %s", user_id, e)
        return deterministic_blueprint
