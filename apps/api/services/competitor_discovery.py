"""Provider-based competitor discovery service."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from models.competitor import Competitor
from models.research_item import ResearchItem
from services.identity import identity_variants, normalize_handle


@dataclass
class DiscoveryCandidate:
    external_id: str
    handle: str
    display_name: str
    subscriber_count: int = 0
    video_count: int = 0
    view_count: int = 0
    avg_views_per_video: int = 0
    thumbnail_url: Optional[str] = None
    source: str = "unknown"
    quality_score: float = 0.0
    already_tracked: bool = False
    source_set: Set[str] = field(default_factory=set)
    source_count: int = 1
    source_labels: List[str] = field(default_factory=list)
    confidence_tier: str = "low"
    evidence: List[str] = field(default_factory=list)

    def as_response(self) -> Dict[str, Any]:
        return {
            "external_id": self.external_id,
            "handle": self.handle,
            "display_name": self.display_name,
            "subscriber_count": max(int(self.subscriber_count or 0), 0),
            "video_count": max(int(self.video_count or 0), 0),
            "view_count": max(int(self.view_count or 0), 0),
            "avg_views_per_video": max(int(self.avg_views_per_video or 0), 0),
            "thumbnail_url": self.thumbnail_url,
            "source": self.source,
            "quality_score": round(float(self.quality_score or 0.0), 2),
            "already_tracked": bool(self.already_tracked),
            "source_count": max(int(self.source_count or 0), 1),
            "source_labels": self.source_labels if isinstance(self.source_labels, list) else [],
            "confidence_tier": str(self.confidence_tier or "low"),
            "evidence": self.evidence if isinstance(self.evidence, list) else [],
        }


SOURCE_PRIORITY = {
    "official_api": 4,
    "youtube_search": 4,
    "research_corpus": 3,
    "community_graph": 2,
    "provider_search": 2,
    "manual_url_seed": 1,
}

URL_PATTERN = re.compile(r"https?://[^\s]+", flags=re.IGNORECASE)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _parse_int_string(value: Any) -> int:
    text = str(value or "").strip()
    if not text:
        return 0
    digits = "".join(ch for ch in text if ch.isdigit() or ch in {"-", "."})
    if not digits:
        return 0
    return _safe_int(digits, 0)


def _format_count(value: int) -> str:
    return f"{max(int(value or 0), 0):,}"


def _source_label(source: str) -> str:
    mapping = {
        "official_api": "official_api",
        "youtube_search": "youtube_search",
        "research_corpus": "research_corpus",
        "community_graph": "community_graph",
        "provider_search": "provider_search",
        "manual_url_seed": "manual_url_seed",
    }
    return mapping.get(str(source or "").strip().lower(), "unknown")


def _score_discovery_quality(
    *,
    subscriber_count: int,
    video_count: int,
    view_count: int,
    avg_views_per_video: int,
    source: str,
) -> float:
    source_bonus = {
        "official_api": 12.0,
        "youtube_search": 12.0,
        "research_corpus": 8.0,
        "community_graph": 6.0,
        "provider_search": 6.0,
        "manual_url_seed": 4.0,
    }.get(source, 7.0)
    return round(
        source_bonus
        + (min(max(subscriber_count, 0), 2_000_000) / 80_000.0)
        + (min(max(view_count, 0), 100_000_000) / 2_000_000.0)
        + (min(max(avg_views_per_video, 0), 1_000_000) / 25_000.0)
        + (min(max(video_count, 0), 1000) / 80.0),
        2,
    )


def _discover_key(*values: Any) -> str:
    tokens = identity_variants(*values)
    if not tokens:
        return ""
    return sorted(tokens, key=lambda item: (len(item), item), reverse=True)[0]


def _query_urls(query: str) -> List[str]:
    rows = URL_PATTERN.findall(str(query or ""))
    seen: Set[str] = set()
    ordered: List[str] = []
    for row in rows:
        clean = row.rstrip(").,;")
        if not clean or clean in seen:
            continue
        seen.add(clean)
        ordered.append(clean)
    return ordered


def _platform_from_url(url: str) -> Optional[str]:
    lowered = str(url or "").lower()
    if "instagram.com" in lowered:
        return "instagram"
    if "tiktok.com" in lowered:
        return "tiktok"
    if "youtube.com" in lowered or "youtu.be" in lowered:
        return "youtube"
    return None


def _preferred_source(source_set: Set[str]) -> str:
    if not source_set:
        return "unknown"
    return sorted(source_set, key=lambda source: (SOURCE_PRIORITY.get(source, 0), source), reverse=True)[0]


def _confidence_tier(candidate: DiscoveryCandidate) -> str:
    source_count = max(len(candidate.source_set), 1)
    quality = float(candidate.quality_score or 0.0)
    has_volume = int(candidate.video_count or 0) >= 3 or int(candidate.view_count or 0) >= 50_000
    if source_count >= 2 and quality >= 14 and has_volume:
        return "high"
    if source_count >= 2 or quality >= 9 or int(candidate.video_count or 0) >= 2:
        return "medium"
    return "low"


def _build_evidence(candidate: DiscoveryCandidate) -> List[str]:
    evidence: List[str] = []
    source_labels = sorted({_source_label(source) for source in candidate.source_set if source})
    if source_labels:
        evidence.append(
            f"Matched across {len(source_labels)} source(s): {', '.join(source_labels)}."
        )
    if int(candidate.video_count or 0) > 0:
        evidence.append(f"Observed across {_format_count(candidate.video_count)} post(s) in mapped data.")
    if int(candidate.avg_views_per_video or 0) > 0:
        evidence.append(f"Avg views/video proxy: {_format_count(candidate.avg_views_per_video)}.")
    if int(candidate.subscriber_count or 0) > 0:
        evidence.append(f"Audience/engagement proxy: {_format_count(candidate.subscriber_count)}.")
    if not evidence:
        evidence.append("Seeded from query hints with limited metric coverage.")
    return evidence[:4]


def _candidate_tokens(candidate: DiscoveryCandidate) -> Set[str]:
    return identity_variants(candidate.external_id, candidate.handle, candidate.display_name)


def _merge_candidate(existing: DiscoveryCandidate, incoming: DiscoveryCandidate) -> None:
    existing.subscriber_count = max(existing.subscriber_count, incoming.subscriber_count)
    existing.video_count = max(existing.video_count, incoming.video_count)
    existing.view_count = max(existing.view_count, incoming.view_count)
    existing.avg_views_per_video = max(existing.avg_views_per_video, incoming.avg_views_per_video)
    if not existing.thumbnail_url and incoming.thumbnail_url:
        existing.thumbnail_url = incoming.thumbnail_url
    if len(incoming.display_name or "") > len(existing.display_name or ""):
        existing.display_name = incoming.display_name
    if len(incoming.handle or "") > len(existing.handle or ""):
        existing.handle = incoming.handle

    existing.source_set.add(incoming.source)
    existing.source = _preferred_source(existing.source_set)
    existing.source_count = max(len(existing.source_set), 1)
    existing.source_labels = sorted({_source_label(source) for source in existing.source_set if source})

    existing.quality_score = round(max(existing.quality_score, incoming.quality_score), 2)


def _finalize_candidate(candidate: DiscoveryCandidate) -> None:
    candidate.source_set = {source for source in candidate.source_set if source}
    if not candidate.source_set and candidate.source:
        candidate.source_set = {candidate.source}
    candidate.source = _preferred_source(candidate.source_set)
    candidate.source_count = max(len(candidate.source_set), 1)
    candidate.source_labels = sorted({_source_label(source) for source in candidate.source_set if source})

    fusion_bonus = max(candidate.source_count - 1, 0) * 1.2
    coverage_bonus = 1.0 if int(candidate.video_count or 0) >= 3 else 0.0
    candidate.quality_score = round(float(candidate.quality_score or 0.0) + fusion_bonus + coverage_bonus, 2)
    candidate.confidence_tier = _confidence_tier(candidate)
    candidate.evidence = _build_evidence(candidate)


def _rank_candidates(candidates: Sequence[DiscoveryCandidate]) -> List[DiscoveryCandidate]:
    ranked = list(candidates)
    ranked.sort(key=lambda item: item.display_name.lower())
    ranked.sort(key=lambda item: item.quality_score, reverse=True)
    return ranked


async def _provider_official_api(
    *,
    platform: str,
    query: str,
    limit: int,
    youtube_client: Any = None,
) -> List[DiscoveryCandidate]:
    if platform != "youtube":
        return []
    if not query:
        return []
    if youtube_client is None:
        return []

    search_limit = min(max(limit * 5, 20), 60)
    channels = youtube_client.search_channels(query, max_results=search_limit)

    candidates: List[DiscoveryCandidate] = []
    for channel in channels:
        external_id = str(channel.get("id") or "").strip()
        if not external_id:
            continue
        subscriber_count = _safe_int(channel.get("subscriber_count"), 0)
        video_count = _safe_int(channel.get("video_count"), 0)
        view_count = _safe_int(channel.get("view_count"), 0)
        avg_views = int(view_count / max(video_count, 1))
        source = "official_api"
        quality = _score_discovery_quality(
            subscriber_count=subscriber_count,
            video_count=video_count,
            view_count=view_count,
            avg_views_per_video=avg_views,
            source=source,
        )
        handle = normalize_handle(channel.get("custom_url") or channel.get("title") or external_id)
        candidate = DiscoveryCandidate(
            external_id=external_id,
            handle=handle or f"@{external_id}",
            display_name=str(channel.get("title") or handle or external_id),
            subscriber_count=subscriber_count,
            video_count=video_count,
            view_count=view_count,
            avg_views_per_video=avg_views,
            thumbnail_url=channel.get("thumbnail_url"),
            source=source,
            quality_score=quality,
            source_set={source},
        )
        candidates.append(candidate)
    return candidates


async def _provider_research_corpus(
    *,
    db: AsyncSession,
    user_id: str,
    platform: str,
    query: str,
) -> List[DiscoveryCandidate]:
    result = await db.execute(
        select(ResearchItem)
        .where(
            ResearchItem.user_id == user_id,
            ResearchItem.platform == platform,
        )
        .order_by(ResearchItem.published_at.desc(), ResearchItem.created_at.desc())
        .limit(2000)
    )
    items = result.scalars().all()
    query_lower = str(query or "").strip().lower()

    grouped: Dict[str, Dict[str, Any]] = {}
    for item in items:
        text_blob = " ".join(
            [
                str(item.title or ""),
                str(item.caption or ""),
                str(item.creator_handle or ""),
                str(item.creator_display_name or ""),
            ]
        ).lower()
        if query_lower and query_lower not in text_blob:
            continue

        media_meta = item.media_meta_json if isinstance(item.media_meta_json, dict) else {}
        key = _discover_key(
            item.creator_handle,
            media_meta.get("creator_id"),
            item.creator_display_name,
            item.external_id,
        )
        if not key:
            continue
        metrics = item.metrics_json if isinstance(item.metrics_json, dict) else {}
        views = _safe_int(metrics.get("views"), 0)
        likes = _safe_int(metrics.get("likes"), 0)
        comments = _safe_int(metrics.get("comments"), 0)
        shares = _safe_int(metrics.get("shares"), 0)
        saves = _safe_int(metrics.get("saves"), 0)
        row = grouped.setdefault(
            key,
            {
                "external_id": key,
                "handle": normalize_handle(item.creator_handle or key),
                "display_name": str(item.creator_display_name or item.creator_handle or key),
                "subscriber_count": 0,
                "video_count": 0,
                "view_count": 0,
                "avg_views_per_video": 0,
                "thumbnail_url": None,
                "engagement_proxy": 0,
            },
        )
        row["video_count"] += 1
        row["view_count"] += max(views, 0)
        row["engagement_proxy"] += max(likes, 0) + (max(comments, 0) * 2) + (max(shares, 0) * 3) + (max(saves, 0) * 3)
        thumbnail = media_meta.get("thumbnail_url")
        if thumbnail and not row["thumbnail_url"]:
            row["thumbnail_url"] = thumbnail

    source = "research_corpus"
    candidates: List[DiscoveryCandidate] = []
    for key in sorted(grouped.keys()):
        row = grouped[key]
        video_count = max(_safe_int(row.get("video_count"), 0), 1)
        view_count = _safe_int(row.get("view_count"), 0)
        avg_views = int(view_count / video_count)
        subscriber_proxy = _safe_int(row.get("engagement_proxy"), 0)
        quality = _score_discovery_quality(
            subscriber_count=subscriber_proxy,
            video_count=_safe_int(row.get("video_count"), 0),
            view_count=view_count,
            avg_views_per_video=avg_views,
            source=source,
        )
        candidates.append(
            DiscoveryCandidate(
                external_id=str(row.get("external_id") or key),
                handle=str(row.get("handle") or f"@{key}"),
                display_name=str(row.get("display_name") or row.get("handle") or key),
                subscriber_count=subscriber_proxy,
                video_count=_safe_int(row.get("video_count"), 0),
                view_count=view_count,
                avg_views_per_video=avg_views,
                thumbnail_url=row.get("thumbnail_url"),
                source=source,
                quality_score=quality,
                source_set={source},
            )
        )
    return candidates


async def _provider_community_graph(
    *,
    db: AsyncSession,
    platform: str,
    query: str,
) -> List[DiscoveryCandidate]:
    query_lower = str(query or "").strip().lower()
    result = await db.execute(
        select(Competitor)
        .where(Competitor.platform == platform)
        .order_by(Competitor.created_at.desc())
        .limit(3000)
    )
    rows = result.scalars().all()

    grouped: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        text_blob = " ".join(
            [
                str(row.handle or ""),
                str(row.display_name or ""),
                str(row.external_id or ""),
            ]
        ).lower()
        if query_lower and query_lower not in text_blob:
            continue

        key = _discover_key(row.external_id, row.handle, row.display_name)
        if not key:
            continue

        bucket = grouped.setdefault(
            key,
            {
                "external_id": str(row.external_id or key),
                "handle": normalize_handle(row.handle or key),
                "display_name": str(row.display_name or row.handle or key),
                "subscriber_count": 0,
                "mentions": 0,
                "thumbnail_url": None,
            },
        )
        bucket["mentions"] += 1
        bucket["subscriber_count"] = max(bucket["subscriber_count"], _parse_int_string(row.subscriber_count))
        if not bucket["thumbnail_url"] and row.profile_picture_url:
            bucket["thumbnail_url"] = row.profile_picture_url

    source = "community_graph"
    candidates: List[DiscoveryCandidate] = []
    for key in sorted(grouped.keys()):
        bucket = grouped[key]
        mentions = _safe_int(bucket.get("mentions"), 0)
        subscriber_count = _safe_int(bucket.get("subscriber_count"), 0)
        quality = _score_discovery_quality(
            subscriber_count=subscriber_count,
            video_count=mentions,
            view_count=0,
            avg_views_per_video=0,
            source=source,
        )
        candidates.append(
            DiscoveryCandidate(
                external_id=str(bucket.get("external_id") or key),
                handle=str(bucket.get("handle") or f"@{key}"),
                display_name=str(bucket.get("display_name") or bucket.get("handle") or key),
                subscriber_count=subscriber_count,
                video_count=mentions,
                view_count=0,
                avg_views_per_video=0,
                thumbnail_url=bucket.get("thumbnail_url"),
                source=source,
                quality_score=quality,
                source_set={source},
            )
        )
    return candidates


async def _provider_manual_url_seed(
    *,
    platform: str,
    query: str,
) -> List[DiscoveryCandidate]:
    candidates: List[DiscoveryCandidate] = []
    source = "manual_url_seed"
    for url in _query_urls(query):
        url_platform = _platform_from_url(url)
        if url_platform and url_platform != platform:
            continue
        token = _discover_key(url)
        if not token:
            continue
        handle = normalize_handle(token)
        display = token.replace("_", " ").replace(".", " ").strip().title() or handle or token
        quality = _score_discovery_quality(
            subscriber_count=0,
            video_count=0,
            view_count=0,
            avg_views_per_video=0,
            source=source,
        )
        candidates.append(
            DiscoveryCandidate(
                external_id=token,
                handle=handle or f"@{token}",
                display_name=display,
                source=source,
                quality_score=quality,
                source_set={source},
            )
        )
    return candidates


async def discover_competitors_service(
    *,
    db: AsyncSession,
    user_id: str,
    platform: str,
    query: str,
    page: int,
    limit: int,
    youtube_client: Any = None,
) -> Dict[str, Any]:
    platform_key = str(platform or "youtube").strip().lower()
    query_value = str(query or "").strip()
    if platform_key == "youtube" and not query_value:
        raise ValueError("query is required for YouTube discover")

    tracked_result = await db.execute(
        select(Competitor).where(
            Competitor.user_id == user_id,
            Competitor.platform == platform_key,
        )
    )
    tracked_rows = tracked_result.scalars().all()
    tracked_tokens: Set[str] = set()
    for row in tracked_rows:
        tracked_tokens |= identity_variants(row.external_id, row.handle, row.display_name)

    provider_rows: List[DiscoveryCandidate] = []
    provider_rows.extend(
        await _provider_official_api(
            platform=platform_key,
            query=query_value,
            limit=limit,
            youtube_client=youtube_client,
        )
    )
    provider_rows.extend(
        await _provider_research_corpus(
            db=db,
            user_id=user_id,
            platform=platform_key,
            query=query_value,
        )
    )
    provider_rows.extend(
        await _provider_community_graph(
            db=db,
            platform=platform_key,
            query=query_value,
        )
    )
    provider_rows.extend(
        await _provider_manual_url_seed(
            platform=platform_key,
            query=query_value,
        )
    )

    merged: Dict[str, DiscoveryCandidate] = {}
    for candidate in provider_rows:
        key = _discover_key(candidate.external_id, candidate.handle, candidate.display_name)
        if not key:
            continue
        existing = merged.get(key)
        if existing is None:
            if candidate.source and not candidate.source_set:
                candidate.source_set = {candidate.source}
            merged[key] = candidate
            continue
        _merge_candidate(existing, candidate)

    finalized: List[DiscoveryCandidate] = []
    for candidate in merged.values():
        _finalize_candidate(candidate)
        finalized.append(candidate)

    ranked = _rank_candidates(finalized)
    for candidate in ranked:
        row_tokens = _candidate_tokens(candidate)
        candidate.already_tracked = bool(tracked_tokens.intersection(row_tokens))

    start = max(page - 1, 0) * limit
    end = start + limit
    return {
        "platform": platform_key,
        "query": query_value,
        "page": page,
        "limit": limit,
        "total_count": len(ranked),
        "has_more": end < len(ranked),
        "candidates": [candidate.as_response() for candidate in ranked[start:end]],
    }
