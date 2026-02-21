"""Feed discovery/search services built on canonical research items."""

from __future__ import annotations

import csv
import io
import json
import logging
import math
import uuid
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import HTTPException
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from config import settings
from database import async_session_maker
from models.audit import Audit
from models.draft_snapshot import DraftSnapshot
from models.feed_auto_ingest_run import FeedAutoIngestRun
from models.feed_repost_package import FeedRepostPackage
from models.feed_source_follow import FeedSourceFollow
from models.feed_telemetry_event import FeedTelemetryEvent
from models.feed_transcript_job import FeedTranscriptJob
from models.media_download_job import MediaDownloadJob
from models.research_collection import ResearchCollection
from models.research_item import ResearchItem
from models.upload import Upload
from services.audit_queue import enqueue_audit_job, enqueue_feed_transcript_job, enqueue_media_download_job
from services.credits import add_credit_purchase, consume_credits
from services.optimizer import generate_variants_service

logger = logging.getLogger(__name__)


ALLOWED_PLATFORMS = {"youtube", "instagram", "tiktok"}
ALLOWED_DISCOVERY_MODES = {"profile", "hashtag", "keyword", "audio"}
ALLOWED_EXPORT_FORMATS = {"csv", "json"}
ALLOWED_SORT_KEYS = {
    "trending_score",
    "engagement_rate",
    "views_per_hour",
    "views",
    "likes",
    "comments",
    "shares",
    "saves",
    "posted_at",
    "created_at",
}
TIMEFRAME_WINDOWS = {
    "24h": timedelta(days=1),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "90d": timedelta(days=90),
    "all": None,
}
FEED_EXPORT_DIR = Path("/tmp/spc_exports")
FOLLOW_CADENCE_MINUTES = {
    "15m": 15,
    "1h": 60,
    "3h": 180,
    "6h": 360,
    "12h": 720,
    "24h": 1440,
}
REPOST_ALLOWED_STATUSES = {"draft", "scheduled", "published", "archived"}
REPOST_DEFAULT_TARGETS = ["youtube", "instagram", "tiktok"]
REPOST_DURATION_TARGETS = {
    "youtube": 34,
    "instagram": 28,
    "tiktok": 24,
}
REPOST_HOOK_DEADLINES = {
    "youtube": 3,
    "instagram": 2,
    "tiktok": 2,
}
TOPIC_STOPWORDS = {
    "the",
    "and",
    "with",
    "from",
    "that",
    "this",
    "your",
    "for",
    "are",
    "you",
    "how",
    "why",
    "what",
    "when",
    "into",
    "about",
    "news",
    "video",
}


def _clean_item_ids(item_ids: List[str]) -> List[str]:
    return [row for row in dict.fromkeys([str(item_id).strip() for item_id in item_ids if str(item_id).strip()])]


def _safe_media_meta(item: ResearchItem) -> Dict[str, Any]:
    return item.media_meta_json if isinstance(item.media_meta_json, dict) else {}


async def _record_feed_event(
    *,
    db: AsyncSession,
    user_id: str,
    event_name: str,
    status: str = "ok",
    platform: Optional[str] = None,
    source_item_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """Best-effort telemetry write; never breaks primary workflow."""
    try:
        event = FeedTelemetryEvent(
            id=str(uuid.uuid4()),
            user_id=user_id,
            event_name=_normalize_text(event_name)[:80],
            status=_normalize_text(status)[:32] or "ok",
            platform=_normalize_text(platform)[:32] or None,
            source_item_id=_normalize_text(source_item_id) or None,
            details_json=details if isinstance(details, dict) else None,
        )
        db.add(event)
        await db.flush()
        logger.info(
            "Feed telemetry user=%s event=%s status=%s platform=%s source_item_id=%s details=%s",
            user_id,
            event.event_name,
            event.status,
            event.platform,
            event.source_item_id,
            event.details_json or {},
        )
    except Exception as exc:
        logger.warning("Feed telemetry write skipped for user=%s event=%s: %s", user_id, event_name, exc)


def _assert_research_enabled() -> None:
    if not settings.RESEARCH_ENABLED:
        raise HTTPException(status_code=503, detail="Feed discovery unavailable because RESEARCH_ENABLED=false.")


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _normalized_platform(value: Any, *, required: bool = True) -> Optional[str]:
    text = _normalize_text(value).lower()
    if not text and not required:
        return None
    if text not in ALLOWED_PLATFORMS:
        if required:
            raise HTTPException(status_code=422, detail="platform must be youtube, instagram, or tiktok.")
        return None
    return text


def _normalized_mode(value: Any) -> str:
    text = _normalize_text(value).lower()
    if text not in ALLOWED_DISCOVERY_MODES:
        raise HTTPException(status_code=422, detail="mode must be profile, hashtag, keyword, or audio.")
    return text


def _timeframe_cutoff(value: Any) -> Optional[datetime]:
    key = _normalize_text(value or "all").lower()
    delta = TIMEFRAME_WINDOWS.get(key)
    if delta is None:
        return None
    return datetime.now(timezone.utc) - delta


def _as_utc(value: Optional[datetime]) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _published_reference(item: ResearchItem) -> datetime:
    return _as_utc(item.published_at or item.created_at)


def _search_blob(item: ResearchItem) -> str:
    return " ".join(
        [
            _normalize_text(item.url),
            _normalize_text(item.title),
            _normalize_text(item.caption),
            _normalize_text(item.creator_handle),
            _normalize_text(item.creator_display_name),
        ]
    ).lower()


def _extract_hashtags(text: str) -> List[str]:
    return re.findall(r"#([a-zA-Z0-9_]+)", text.lower())


def _extract_topic_keywords(text: str, limit: int = 3) -> List[str]:
    raw_tokens = re.findall(r"[a-zA-Z0-9]{3,}", text.lower())
    tokens = [token for token in raw_tokens if token not in TOPIC_STOPWORDS]
    deduped = list(dict.fromkeys(tokens))
    return deduped[:limit]


def _normalize_target_platforms(value: Any) -> List[str]:
    if not isinstance(value, list):
        return REPOST_DEFAULT_TARGETS[:]
    normalized: List[str] = []
    for row in value:
        platform = _normalized_platform(row, required=False)
        if platform:
            normalized.append(platform)
    deduped = list(dict.fromkeys(normalized))
    return deduped or REPOST_DEFAULT_TARGETS[:]


def _engagement_rate(metrics: Dict[str, int]) -> float:
    views = max(int(metrics.get("views", 0)), 1)
    numerator = (
        int(metrics.get("likes", 0))
        + int(metrics.get("comments", 0))
        + int(metrics.get("shares", 0))
        + int(metrics.get("saves", 0))
    )
    return numerator / views


def _views_per_hour(views: int, reference_ts: datetime) -> float:
    age_hours = max((datetime.now(timezone.utc) - _as_utc(reference_ts)).total_seconds() / 3600.0, 1.0)
    return float(views) / age_hours


def _recency_decay(reference_ts: datetime) -> float:
    age_hours = max((datetime.now(timezone.utc) - _as_utc(reference_ts)).total_seconds() / 3600.0, 0.0)
    return math.exp(-age_hours / 120.0)


def _trending_score(
    *,
    metrics: Dict[str, int],
    views_per_hour: float,
    engagement_rate: float,
    reference_ts: datetime,
) -> float:
    velocity_signal = min(max(views_per_hour / 10000.0, 0.0), 1.0)
    engagement_signal = min(max(engagement_rate * 4.0, 0.0), 1.0)
    shares_saves = int(metrics.get("shares", 0)) + int(metrics.get("saves", 0))
    views = max(int(metrics.get("views", 0)), 1)
    share_save_signal = min(max((shares_saves / views) * 8.0, 0.0), 1.0)
    recency_signal = min(max(_recency_decay(reference_ts), 0.0), 1.0)
    score = (
        (0.35 * velocity_signal)
        + (0.25 * engagement_signal)
        + (0.20 * share_save_signal)
        + (0.20 * recency_signal)
    ) * 100.0
    return round(score, 2)


def _item_payload(item: ResearchItem) -> Dict[str, Any]:
    metrics = item.metrics_json if isinstance(item.metrics_json, dict) else {}
    normalized_metrics = {
        "views": _safe_int(metrics.get("views"), 0),
        "likes": _safe_int(metrics.get("likes"), 0),
        "comments": _safe_int(metrics.get("comments"), 0),
        "shares": _safe_int(metrics.get("shares"), 0),
        "saves": _safe_int(metrics.get("saves"), 0),
    }
    ref_ts = _published_reference(item)
    rate = _engagement_rate(normalized_metrics)
    velocity = _views_per_hour(normalized_metrics["views"], ref_ts)
    return {
        "item_id": item.id,
        "platform": item.platform,
        "source_type": item.source_type,
        "url": item.url,
        "external_id": item.external_id,
        "creator_handle": item.creator_handle,
        "creator_display_name": item.creator_display_name,
        "title": item.title,
        "caption": item.caption,
        "metrics": normalized_metrics,
        "published_at": item.published_at.isoformat() if item.published_at else None,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "engagement_rate": round(rate, 4),
        "views_per_hour": round(velocity, 2),
        "trending_score": _trending_score(
            metrics=normalized_metrics,
            views_per_hour=velocity,
            engagement_rate=rate,
            reference_ts=ref_ts,
        ),
    }


def _mode_match(item: ResearchItem, *, mode: str, query: str) -> bool:
    blob = _search_blob(item)
    if mode == "profile":
        return query in _normalize_text(item.creator_handle).lower() or query in _normalize_text(item.creator_display_name).lower()
    if mode == "hashtag":
        hashtags = set(_extract_hashtags(blob))
        normalized = query[1:] if query.startswith("#") else query
        return normalized in hashtags
    if mode == "audio":
        media_meta = item.media_meta_json if isinstance(item.media_meta_json, dict) else {}
        audio_blob = " ".join(
            [
                _normalize_text(media_meta.get("audio_id")),
                _normalize_text(media_meta.get("audio_title")),
                _normalize_text(media_meta.get("sound_id")),
                _normalize_text(media_meta.get("sound_title")),
                _normalize_text(media_meta.get("music")),
                blob,
            ]
        ).lower()
        return query in audio_blob
    # keyword
    return query in blob


def _sort_rows(rows: List[Dict[str, Any]], *, sort_by: str, sort_direction: str) -> List[Dict[str, Any]]:
    resolved_sort = sort_by if sort_by in ALLOWED_SORT_KEYS else "trending_score"
    reverse = str(sort_direction).lower() != "asc"

    def _key(row: Dict[str, Any]) -> Any:
        if resolved_sort in {"views", "likes", "comments", "shares", "saves"}:
            metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
            return _safe_int(metrics.get(resolved_sort), 0)
        if resolved_sort in {"trending_score", "engagement_rate", "views_per_hour"}:
            return float(row.get(resolved_sort) or 0.0)
        if resolved_sort == "posted_at":
            return row.get("published_at") or ""
        return row.get("created_at") or ""

    # Stable tie-break: oldest lexical item_id last for desc sorting.
    ordered = sorted(rows, key=lambda row: str(row.get("item_id") or ""))
    ordered.sort(key=_key, reverse=reverse)
    return ordered


async def _base_rows(
    *,
    db: AsyncSession,
    user_id: str,
    platform: Optional[str],
    timeframe: Any,
) -> List[ResearchItem]:
    query = select(ResearchItem).where(ResearchItem.user_id == user_id)
    if platform:
        query = query.where(ResearchItem.platform == platform)
    result = await db.execute(query)
    rows = result.scalars().all()
    cutoff = _timeframe_cutoff(timeframe)
    if cutoff is None:
        return rows
    return [
        row
        for row in rows
        if (_published_reference(row) >= cutoff)
    ]


def _paginate(rows: List[Dict[str, Any]], *, page: int, limit: int) -> Dict[str, Any]:
    p = max(_safe_int(page, 1), 1)
    l = max(1, min(_safe_int(limit, 20), 100))
    start = (p - 1) * l
    end = start + l
    return {
        "page": p,
        "limit": l,
        "total_count": len(rows),
        "has_more": end < len(rows),
        "items": rows[start:end],
    }


def _source_health(total_count: int) -> Dict[str, Any]:
    return {
        "research_corpus": "healthy" if total_count > 0 else "empty",
        "official_provider": "not_configured",
        "collector": "not_enabled",
    }


async def discover_feed_items_service(
    *,
    user_id: str,
    payload: Dict[str, Any],
    db: AsyncSession,
) -> Dict[str, Any]:
    _assert_research_enabled()
    platform = _normalized_platform(payload.get("platform"), required=True)
    mode = _normalized_mode(payload.get("mode"))
    query = _normalize_text(payload.get("query")).lower()
    if not query:
        raise HTTPException(status_code=422, detail="query is required for feed discovery.")

    base = await _base_rows(
        db=db,
        user_id=user_id,
        platform=platform,
        timeframe=payload.get("timeframe") or "7d",
    )
    filtered = [row for row in base if _mode_match(row, mode=mode, query=query)]
    projected = [_item_payload(row) for row in filtered]
    sorted_rows = _sort_rows(
        projected,
        sort_by=_normalize_text(payload.get("sort_by") or "trending_score"),
        sort_direction=_normalize_text(payload.get("sort_direction") or "desc"),
    )
    paged = _paginate(
        sorted_rows,
        page=payload.get("page"),
        limit=payload.get("limit"),
    )
    response = {
        "run_id": str(uuid.uuid4()),
        "platform": platform,
        "mode": mode,
        "query": _normalize_text(payload.get("query")),
        "timeframe": _normalize_text(payload.get("timeframe") or "7d"),
        "ingestion_method": "research_corpus",
        "source_health": _source_health(paged["total_count"]),
        **paged,
    }
    await _record_feed_event(
        db=db,
        user_id=user_id,
        event_name="feed_discover",
        status="ok",
        platform=platform,
        details={
            "mode": mode,
            "query": query[:80],
            "result_count": int(response.get("total_count", 0)),
        },
    )
    await db.commit()
    return response


async def search_feed_items_service(
    *,
    user_id: str,
    payload: Dict[str, Any],
    db: AsyncSession,
) -> Dict[str, Any]:
    _assert_research_enabled()
    platform = _normalized_platform(payload.get("platform"), required=False)
    mode_raw = _normalize_text(payload.get("mode") or "")
    mode: Optional[Literal["profile", "hashtag", "keyword", "audio"]] = None
    if mode_raw:
        mode = _normalized_mode(mode_raw)  # type: ignore[assignment]

    query = _normalize_text(payload.get("query")).lower()
    base = await _base_rows(
        db=db,
        user_id=user_id,
        platform=platform,
        timeframe=payload.get("timeframe") or "all",
    )

    filtered = base
    if query and mode:
        filtered = [row for row in filtered if _mode_match(row, mode=mode, query=query)]
    elif query:
        filtered = [row for row in filtered if query in _search_blob(row)]

    projected = [_item_payload(row) for row in filtered]
    sorted_rows = _sort_rows(
        projected,
        sort_by=_normalize_text(payload.get("sort_by") or "trending_score"),
        sort_direction=_normalize_text(payload.get("sort_direction") or "desc"),
    )
    paged = _paginate(
        sorted_rows,
        page=payload.get("page"),
        limit=payload.get("limit"),
    )
    response = {
        "platform": platform or "all",
        "mode": mode,
        "query": _normalize_text(payload.get("query")),
        "timeframe": _normalize_text(payload.get("timeframe") or "all"),
        **paged,
    }
    await _record_feed_event(
        db=db,
        user_id=user_id,
        event_name="feed_search",
        status="ok",
        platform=platform,
        details={
            "mode": mode,
            "query": query[:80],
            "result_count": int(response.get("total_count", 0)),
        },
    )
    await db.commit()
    return response


async def update_feed_favorite_service(
    *,
    user_id: str,
    item_id: str,
    favorite: bool,
    db: AsyncSession,
) -> Dict[str, Any]:
    _assert_research_enabled()
    result = await db.execute(
        select(ResearchItem).where(
            ResearchItem.id == item_id,
            ResearchItem.user_id == user_id,
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Feed item not found.")

    media_meta = item.media_meta_json if isinstance(item.media_meta_json, dict) else {}
    next_meta = {**media_meta, "favorite": bool(favorite)}
    item.media_meta_json = next_meta
    await _record_feed_event(
        db=db,
        user_id=user_id,
        event_name="feed_favorite_toggle",
        status="ok",
        platform=item.platform,
        source_item_id=item.id,
        details={"favorite": bool(favorite)},
    )
    await db.commit()
    return {"item_id": item.id, "favorite": bool(next_meta["favorite"])}


async def assign_feed_items_to_collection_service(
    *,
    user_id: str,
    item_ids: List[str],
    collection_id: str,
    db: AsyncSession,
) -> Dict[str, Any]:
    _assert_research_enabled()
    unique_item_ids = [row for row in dict.fromkeys([str(item_id).strip() for item_id in item_ids if str(item_id).strip()])]
    if not unique_item_ids:
        raise HTTPException(status_code=422, detail="item_ids must include at least one id.")

    collection_result = await db.execute(
        select(ResearchCollection).where(
            ResearchCollection.id == collection_id,
            ResearchCollection.user_id == user_id,
        )
    )
    collection = collection_result.scalar_one_or_none()
    if collection is None:
        raise HTTPException(status_code=404, detail="Collection not found.")

    items_result = await db.execute(
        select(ResearchItem).where(
            ResearchItem.user_id == user_id,
            ResearchItem.id.in_(unique_item_ids),
        )
    )
    items = items_result.scalars().all()
    found_ids = {row.id for row in items}
    for row in items:
        row.collection_id = collection.id
        await _record_feed_event(
            db=db,
            user_id=user_id,
            event_name="feed_collection_assign",
            status="ok",
            platform=row.platform,
            source_item_id=row.id,
            details={"collection_id": collection.id},
        )
    await db.commit()

    missing_ids = [row for row in unique_item_ids if row not in found_ids]
    return {
        "collection_id": collection.id,
        "assigned_count": len(items),
        "missing_count": len(missing_ids),
        "missing_item_ids": missing_ids[:25],
    }


def _feed_export_token(user_id: str, export_id: str, ttl_minutes: int = 30) -> str:
    now = datetime.now(timezone.utc)
    claims = {
        "sub": user_id,
        "export_id": export_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ttl_minutes)).timestamp()),
        "purpose": "feed_export",
    }
    return jwt.encode(claims, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_feed_export_token(token: str) -> Dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid feed export token.") from exc
    if payload.get("purpose") != "feed_export":
        raise HTTPException(status_code=401, detail="Invalid feed export token purpose.")
    return payload


def resolve_feed_export_file(user_id: str, export_id: str) -> Path:
    for ext in ("csv", "json"):
        path = FEED_EXPORT_DIR / user_id / f"feed_{export_id}.{ext}"
        if path.exists():
            return path
    raise HTTPException(status_code=404, detail="Feed export file not found.")


def _export_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    export_rows: List[Dict[str, Any]] = []
    for row in rows:
        metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
        export_rows.append(
            {
                "item_id": row.get("item_id"),
                "platform": row.get("platform"),
                "source_type": row.get("source_type"),
                "url": row.get("url"),
                "external_id": row.get("external_id"),
                "creator_handle": row.get("creator_handle"),
                "creator_display_name": row.get("creator_display_name"),
                "title": row.get("title"),
                "caption": row.get("caption"),
                "views": _safe_int(metrics.get("views"), 0),
                "likes": _safe_int(metrics.get("likes"), 0),
                "comments": _safe_int(metrics.get("comments"), 0),
                "shares": _safe_int(metrics.get("shares"), 0),
                "saves": _safe_int(metrics.get("saves"), 0),
                "engagement_rate": float(row.get("engagement_rate") or 0.0),
                "views_per_hour": float(row.get("views_per_hour") or 0.0),
                "trending_score": float(row.get("trending_score") or 0.0),
                "published_at": row.get("published_at"),
                "created_at": row.get("created_at"),
            }
        )
    return export_rows


async def export_feed_items_service(
    *,
    user_id: str,
    payload: Dict[str, Any],
    db: AsyncSession,
) -> Dict[str, Any]:
    _assert_research_enabled()
    export_format = _normalize_text(payload.get("format")).lower()
    if export_format not in ALLOWED_EXPORT_FORMATS:
        raise HTTPException(status_code=422, detail="format must be csv or json.")

    item_ids = payload.get("item_ids")
    rows: List[Dict[str, Any]] = []
    if isinstance(item_ids, list) and item_ids:
        normalized_ids = [str(item_id).strip() for item_id in item_ids if str(item_id).strip()]
        if not normalized_ids:
            raise HTTPException(status_code=422, detail="item_ids must include at least one id.")
        result = await db.execute(
            select(ResearchItem).where(
                ResearchItem.user_id == user_id,
                ResearchItem.id.in_(normalized_ids),
            )
        )
        items = result.scalars().all()
        item_map = {item.id: _item_payload(item) for item in items}
        rows = [item_map[item_id] for item_id in normalized_ids if item_id in item_map]
    else:
        max_rows = max(1, min(_safe_int(payload.get("max_rows"), 500), 5000))
        page = 1
        limit = max(1, min(_safe_int(payload.get("limit"), 100), 100))
        while True:
            result = await search_feed_items_service(
                user_id=user_id,
                payload={
                    "platform": payload.get("platform"),
                    "mode": payload.get("mode"),
                    "query": payload.get("query"),
                    "timeframe": payload.get("timeframe") or "all",
                    "sort_by": payload.get("sort_by") or "trending_score",
                    "sort_direction": payload.get("sort_direction") or "desc",
                    "page": page,
                    "limit": limit,
                },
                db=db,
            )
            rows.extend(result.get("items", []))
            if not result.get("has_more") or len(rows) >= max_rows:
                break
            page += 1
        rows = rows[:max_rows]

    export_rows = _export_rows(rows)
    export_id = str(uuid.uuid4())
    user_dir = FEED_EXPORT_DIR / user_id
    user_dir.mkdir(parents=True, exist_ok=True)
    file_path = user_dir / f"feed_{export_id}.{export_format}"

    if export_format == "json":
        file_path.write_text(json.dumps(export_rows, ensure_ascii=True, indent=2), encoding="utf-8")
    else:
        buffer = io.StringIO()
        fieldnames = [
            "item_id",
            "platform",
            "source_type",
            "url",
            "external_id",
            "creator_handle",
            "creator_display_name",
            "title",
            "caption",
            "views",
            "likes",
            "comments",
            "shares",
            "saves",
            "engagement_rate",
            "views_per_hour",
            "trending_score",
            "published_at",
            "created_at",
        ]
        writer = csv.DictWriter(buffer, fieldnames=fieldnames)
        writer.writeheader()
        for row in export_rows:
            writer.writerow(row)
        file_path.write_text(buffer.getvalue(), encoding="utf-8")

    token = _feed_export_token(user_id, export_id)
    await _record_feed_event(
        db=db,
        user_id=user_id,
        event_name="feed_export",
        status="ok",
        platform=_normalize_text(payload.get("platform")) or None,
        details={
            "format": export_format,
            "item_count": len(export_rows),
            "max_rows": _safe_int(payload.get("max_rows"), 500),
        },
    )
    await db.commit()
    return {
        "export_id": export_id,
        "status": "completed",
        "format": export_format,
        "item_count": len(export_rows),
        "signed_url": f"/feed/export/{export_id}/download?token={token}",
    }


async def start_feed_bulk_download_service(
    *,
    user_id: str,
    item_ids: List[str],
    db: AsyncSession,
) -> Dict[str, Any]:
    _assert_research_enabled()
    if not settings.ALLOW_EXTERNAL_MEDIA_DOWNLOAD:
        raise HTTPException(
            status_code=503,
            detail=(
                "External media download is disabled. Set ALLOW_EXTERNAL_MEDIA_DOWNLOAD=true "
                "or use upload mode in /audit/new."
            ),
        )

    unique_item_ids = _clean_item_ids(item_ids)
    if not unique_item_ids:
        raise HTTPException(status_code=422, detail="item_ids must include at least one id.")

    result = await db.execute(
        select(ResearchItem).where(
            ResearchItem.user_id == user_id,
            ResearchItem.id.in_(unique_item_ids),
        )
    )
    items = result.scalars().all()
    item_map = {row.id: row for row in items}

    responses: List[Dict[str, Any]] = []
    for item_id in unique_item_ids:
        item = item_map.get(item_id)
        if item is None:
            responses.append(
                {
                    "item_id": item_id,
                    "job_id": None,
                    "status": "skipped",
                    "queue_job_id": None,
                    "error_code": "item_not_found",
                    "error_message": "Feed item not found.",
                }
            )
            continue

        source_url = _normalize_text(item.url)
        if not source_url.startswith("http://") and not source_url.startswith("https://"):
            responses.append(
                {
                    "item_id": item.id,
                    "job_id": None,
                    "status": "skipped",
                    "queue_job_id": None,
                    "error_code": "missing_source_url",
                    "error_message": "Feed item must include an absolute source URL to download.",
                }
            )
            continue

        job = MediaDownloadJob(
            id=str(uuid.uuid4()),
            user_id=user_id,
            platform=item.platform,
            source_url=source_url,
            status="queued",
            progress=0,
            attempts=0,
            max_attempts=3,
        )
        db.add(job)
        await db.flush()

        queue_job_id: Optional[str] = None
        error_code: Optional[str] = None
        error_message: Optional[str] = None
        try:
            queue_job = enqueue_media_download_job(job.id)
            queue_job_id = getattr(queue_job, "id", None)
            job.queue_job_id = queue_job_id
        except Exception as exc:
            job.status = "failed"
            job.error_code = "queue_unavailable"
            job.error_message = str(exc)[:1000]
            error_code = "queue_unavailable"
            error_message = str(exc)

        media_meta = _safe_media_meta(item)
        history = media_meta.get("feed_download_job_ids")
        history_list = history if isinstance(history, list) else []
        merged_history = [*history_list, job.id][-20:]
        item.media_meta_json = {
            **media_meta,
            "feed_download_job_id": job.id,
            "feed_download_job_ids": merged_history,
            "feed_download_updated_at": datetime.now(timezone.utc).isoformat(),
        }

        responses.append(
            {
                "item_id": item.id,
                "job_id": job.id,
                "status": job.status,
                "queue_job_id": queue_job_id,
                "error_code": error_code,
                "error_message": error_message,
            }
        )

    await db.commit()
    queued_count = sum(1 for row in responses if row.get("status") == "queued")
    failed_count = sum(1 for row in responses if row.get("status") == "failed")
    skipped_count = sum(1 for row in responses if row.get("status") == "skipped")
    await _record_feed_event(
        db=db,
        user_id=user_id,
        event_name="feed_download_bulk_start",
        status="ok" if failed_count == 0 else "partial",
        details={
            "submitted_count": len(unique_item_ids),
            "queued_count": queued_count,
            "failed_count": failed_count,
            "skipped_count": skipped_count,
        },
    )
    await db.commit()
    return {
        "submitted_count": len(unique_item_ids),
        "queued_count": queued_count,
        "failed_count": failed_count,
        "skipped_count": skipped_count,
        "jobs": responses,
    }


async def get_feed_bulk_download_status_service(
    *,
    user_id: str,
    job_ids: List[str],
    db: AsyncSession,
) -> Dict[str, Any]:
    _assert_research_enabled()
    unique_job_ids = [row for row in dict.fromkeys([str(job_id).strip() for job_id in job_ids if str(job_id).strip()])]
    if not unique_job_ids:
        raise HTTPException(status_code=422, detail="job_ids must include at least one id.")

    result = await db.execute(
        select(MediaDownloadJob).where(
            MediaDownloadJob.user_id == user_id,
            MediaDownloadJob.id.in_(unique_job_ids),
        )
    )
    rows = result.scalars().all()
    row_map = {row.id: row for row in rows}

    payload_jobs: List[Dict[str, Any]] = []
    for job_id in unique_job_ids:
        row = row_map.get(job_id)
        if row is None:
            payload_jobs.append(
                {
                    "job_id": job_id,
                    "status": "missing",
                    "progress": 0,
                    "queue_job_id": None,
                    "media_asset_id": None,
                    "upload_id": None,
                    "error_code": "not_found",
                    "error_message": "Job not found.",
                }
            )
            continue
        payload_jobs.append(
            {
                "job_id": row.id,
                "status": row.status,
                "progress": int(row.progress or 0),
                "queue_job_id": row.queue_job_id,
                "media_asset_id": row.media_asset_id,
                "upload_id": row.upload_id,
                "error_code": row.error_code,
                "error_message": row.error_message,
            }
        )

    response = {
        "requested_count": len(unique_job_ids),
        "jobs": payload_jobs,
    }
    failed_count = sum(1 for row in payload_jobs if row.get("status") == "failed")
    await _record_feed_event(
        db=db,
        user_id=user_id,
        event_name="feed_download_status_poll",
        status="ok" if failed_count == 0 else "partial",
        details={
            "requested_count": len(unique_job_ids),
            "failed_count": failed_count,
        },
    )
    await db.commit()
    return response


async def start_feed_transcript_jobs_service(
    *,
    user_id: str,
    item_ids: List[str],
    db: AsyncSession,
) -> Dict[str, Any]:
    _assert_research_enabled()
    unique_item_ids = _clean_item_ids(item_ids)
    if not unique_item_ids:
        raise HTTPException(status_code=422, detail="item_ids must include at least one id.")

    result = await db.execute(
        select(ResearchItem).where(
            ResearchItem.user_id == user_id,
            ResearchItem.id.in_(unique_item_ids),
        )
    )
    items = result.scalars().all()
    item_map = {row.id: row for row in items}
    responses: List[Dict[str, Any]] = []

    for item_id in unique_item_ids:
        item = item_map.get(item_id)
        if item is None:
            responses.append(
                {
                    "item_id": item_id,
                    "job_id": None,
                    "status": "skipped",
                    "queue_job_id": None,
                    "error_code": "item_not_found",
                    "error_message": "Feed item not found.",
                }
            )
            continue

        job = FeedTranscriptJob(
            id=str(uuid.uuid4()),
            user_id=user_id,
            research_item_id=item.id,
            status="queued",
            progress=0,
            attempts=0,
            max_attempts=3,
        )
        db.add(job)
        await db.flush()

        queue_job_id: Optional[str] = None
        error_code: Optional[str] = None
        error_message: Optional[str] = None
        try:
            queue_job = enqueue_feed_transcript_job(job.id)
            queue_job_id = getattr(queue_job, "id", None)
            job.queue_job_id = queue_job_id
        except Exception as exc:
            job.status = "failed"
            job.error_code = "queue_unavailable"
            job.error_message = str(exc)[:1000]
            error_code = "queue_unavailable"
            error_message = str(exc)

        media_meta = _safe_media_meta(item)
        item.media_meta_json = {
            **media_meta,
            "transcript_job_id": job.id,
            "transcript_job_updated_at": datetime.now(timezone.utc).isoformat(),
        }
        responses.append(
            {
                "item_id": item.id,
                "job_id": job.id,
                "status": job.status,
                "queue_job_id": queue_job_id,
                "error_code": error_code,
                "error_message": error_message,
            }
        )

    await db.commit()
    queued_count = sum(1 for row in responses if row.get("status") == "queued")
    failed_count = sum(1 for row in responses if row.get("status") == "failed")
    skipped_count = sum(1 for row in responses if row.get("status") == "skipped")
    await _record_feed_event(
        db=db,
        user_id=user_id,
        event_name="feed_transcript_bulk_start",
        status="ok" if failed_count == 0 else "partial",
        details={
            "submitted_count": len(unique_item_ids),
            "queued_count": queued_count,
            "failed_count": failed_count,
            "skipped_count": skipped_count,
        },
    )
    await db.commit()
    return {
        "submitted_count": len(unique_item_ids),
        "queued_count": queued_count,
        "failed_count": failed_count,
        "skipped_count": skipped_count,
        "jobs": responses,
    }


async def get_feed_transcript_jobs_status_service(
    *,
    user_id: str,
    job_ids: List[str],
    db: AsyncSession,
) -> Dict[str, Any]:
    _assert_research_enabled()
    unique_job_ids = [row for row in dict.fromkeys([str(job_id).strip() for job_id in job_ids if str(job_id).strip()])]
    if not unique_job_ids:
        raise HTTPException(status_code=422, detail="job_ids must include at least one id.")

    result = await db.execute(
        select(FeedTranscriptJob).where(
            FeedTranscriptJob.user_id == user_id,
            FeedTranscriptJob.id.in_(unique_job_ids),
        )
    )
    jobs = result.scalars().all()
    job_map = {row.id: row for row in jobs}
    payload_jobs: List[Dict[str, Any]] = []
    for job_id in unique_job_ids:
        row = job_map.get(job_id)
        if row is None:
            payload_jobs.append(
                {
                    "job_id": job_id,
                    "status": "missing",
                    "progress": 0,
                    "queue_job_id": None,
                    "item_id": None,
                    "transcript_source": None,
                    "transcript_preview": None,
                    "error_code": "not_found",
                    "error_message": "Job not found.",
                }
            )
            continue
        payload_jobs.append(
            {
                "job_id": row.id,
                "status": row.status,
                "progress": int(row.progress or 0),
                "queue_job_id": row.queue_job_id,
                "item_id": row.research_item_id,
                "transcript_source": row.transcript_source,
                "transcript_preview": str(row.transcript_text or "")[:180] or None,
                "error_code": row.error_code,
                "error_message": row.error_message,
            }
        )
    response = {
        "requested_count": len(unique_job_ids),
        "jobs": payload_jobs,
    }
    failed_count = sum(1 for row in payload_jobs if row.get("status") == "failed")
    await _record_feed_event(
        db=db,
        user_id=user_id,
        event_name="feed_transcript_status_poll",
        status="ok" if failed_count == 0 else "partial",
        details={
            "requested_count": len(unique_job_ids),
            "failed_count": failed_count,
        },
    )
    await db.commit()
    return response


def _normalized_follow_limit(value: Any) -> int:
    return max(1, min(_safe_int(value, 20), 100))


def _normalized_cadence_minutes(*, cadence: Optional[str] = None, cadence_minutes: Optional[int] = None) -> int:
    if cadence_minutes is not None:
        return max(15, min(int(cadence_minutes), 24 * 60))
    key = _normalize_text(cadence).lower()
    if key and key in FOLLOW_CADENCE_MINUTES:
        return FOLLOW_CADENCE_MINUTES[key]
    return FOLLOW_CADENCE_MINUTES["6h"]


def _serialize_follow(row: FeedSourceFollow) -> Dict[str, Any]:
    return {
        "id": row.id,
        "platform": row.platform,
        "mode": row.mode,
        "query": row.query,
        "timeframe": row.timeframe,
        "sort_by": row.sort_by,
        "sort_direction": row.sort_direction,
        "limit": int(row.limit or 20),
        "cadence_minutes": int(row.cadence_minutes or 360),
        "is_active": bool(row.is_active),
        "last_run_at": row.last_run_at.isoformat() if row.last_run_at else None,
        "next_run_at": row.next_run_at.isoformat() if row.next_run_at else None,
        "last_error": row.last_error,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _serialize_ingest_run(row: FeedAutoIngestRun) -> Dict[str, Any]:
    item_ids = row.item_ids_json if isinstance(row.item_ids_json, list) else []
    return {
        "run_id": row.id,
        "follow_id": row.follow_id,
        "status": row.status,
        "item_count": int(row.item_count or 0),
        "item_ids": [str(item_id) for item_id in item_ids[:50]],
        "error_message": row.error_message,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


async def upsert_feed_follow_service(
    *,
    user_id: str,
    payload: Dict[str, Any],
    db: AsyncSession,
) -> Dict[str, Any]:
    _assert_research_enabled()
    platform = _normalized_platform(payload.get("platform"), required=True)
    mode = _normalized_mode(payload.get("mode"))
    query = _normalize_text(payload.get("query")).lower()
    if not query:
        raise HTTPException(status_code=422, detail="query is required.")
    timeframe = _normalize_text(payload.get("timeframe") or "7d").lower()
    if timeframe not in TIMEFRAME_WINDOWS:
        raise HTTPException(status_code=422, detail="timeframe must be one of 24h, 7d, 30d, 90d, all.")

    sort_by = _normalize_text(payload.get("sort_by") or "trending_score")
    if sort_by not in ALLOWED_SORT_KEYS:
        raise HTTPException(status_code=422, detail="sort_by is invalid.")
    sort_direction = _normalize_text(payload.get("sort_direction") or "desc").lower()
    if sort_direction not in {"asc", "desc"}:
        raise HTTPException(status_code=422, detail="sort_direction must be asc or desc.")
    cadence_minutes = _normalized_cadence_minutes(
        cadence=_normalize_text(payload.get("cadence") or ""),
        cadence_minutes=payload.get("cadence_minutes"),
    )
    limit = _normalized_follow_limit(payload.get("limit"))
    is_active = bool(payload.get("is_active", True))
    now = datetime.now(timezone.utc)

    existing_result = await db.execute(
        select(FeedSourceFollow).where(
            FeedSourceFollow.user_id == user_id,
            FeedSourceFollow.platform == platform,
            FeedSourceFollow.mode == mode,
            FeedSourceFollow.query == query,
        )
    )
    row = existing_result.scalar_one_or_none()
    created = False
    if row is None:
        created = True
        row = FeedSourceFollow(
            id=str(uuid.uuid4()),
            user_id=user_id,
            platform=platform,
            mode=mode,
            query=query,
            timeframe=timeframe,
            sort_by=sort_by,
            sort_direction=sort_direction,
            limit=limit,
            cadence_minutes=cadence_minutes,
            is_active=is_active,
            next_run_at=(now + timedelta(minutes=cadence_minutes)) if is_active else None,
        )
        db.add(row)
    else:
        row.timeframe = timeframe
        row.sort_by = sort_by
        row.sort_direction = sort_direction
        row.limit = limit
        row.cadence_minutes = cadence_minutes
        row.is_active = is_active
        if is_active and row.next_run_at is None:
            row.next_run_at = now + timedelta(minutes=cadence_minutes)
        if not is_active:
            row.next_run_at = None

    await db.commit()
    await db.refresh(row)
    await _record_feed_event(
        db=db,
        user_id=user_id,
        event_name="feed_follow_upsert",
        status="created" if created else "updated",
        platform=platform,
        details={
            "mode": mode,
            "query": query[:80],
            "cadence_minutes": cadence_minutes,
            "is_active": is_active,
        },
    )
    await db.commit()
    return {
        "created": created,
        "follow": _serialize_follow(row),
    }


async def list_feed_follows_service(
    *,
    user_id: str,
    platform: Optional[str],
    active_only: bool,
    db: AsyncSession,
) -> Dict[str, Any]:
    _assert_research_enabled()
    normalized_platform = _normalized_platform(platform, required=False)
    query = select(FeedSourceFollow).where(FeedSourceFollow.user_id == user_id)
    if normalized_platform:
        query = query.where(FeedSourceFollow.platform == normalized_platform)
    if active_only:
        query = query.where(FeedSourceFollow.is_active.is_(True))

    result = await db.execute(query)
    rows = result.scalars().all()
    rows.sort(
        key=lambda row: (
            0 if row.next_run_at else 1,
            _as_utc(row.next_run_at) if row.next_run_at else datetime.max.replace(tzinfo=timezone.utc),
            str(row.query),
        )
    )
    payload = [_serialize_follow(row) for row in rows]
    return {"count": len(payload), "follows": payload}


async def delete_feed_follow_service(
    *,
    user_id: str,
    follow_id: str,
    db: AsyncSession,
) -> Dict[str, Any]:
    _assert_research_enabled()
    result = await db.execute(
        select(FeedSourceFollow).where(
            FeedSourceFollow.id == follow_id,
            FeedSourceFollow.user_id == user_id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Feed follow not found.")
    platform = row.platform
    await db.delete(row)
    await _record_feed_event(
        db=db,
        user_id=user_id,
        event_name="feed_follow_delete",
        status="ok",
        platform=platform,
        details={"follow_id": follow_id},
    )
    await db.commit()
    return {"deleted": True, "follow_id": follow_id}


async def _run_follow_ingest(
    *,
    follow: FeedSourceFollow,
    db: AsyncSession,
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    run = FeedAutoIngestRun(
        id=str(uuid.uuid4()),
        follow_id=follow.id,
        user_id=follow.user_id,
        status="running",
        item_count=0,
        item_ids_json=[],
        started_at=now,
    )
    db.add(run)
    await db.flush()

    try:
        result = await discover_feed_items_service(
            user_id=follow.user_id,
            payload={
                "platform": follow.platform,
                "mode": follow.mode,
                "query": follow.query,
                "timeframe": follow.timeframe,
                "sort_by": follow.sort_by,
                "sort_direction": follow.sort_direction,
                "page": 1,
                "limit": int(follow.limit or 20),
            },
            db=db,
        )
        items = result.get("items", []) if isinstance(result, dict) else []
        item_ids = [str(item.get("item_id")) for item in items if isinstance(item, dict) and item.get("item_id")]
        run.status = "completed"
        run.item_count = len(item_ids)
        run.item_ids_json = item_ids[:100]
        run.completed_at = datetime.now(timezone.utc)

        follow.last_run_at = now
        follow.next_run_at = now + timedelta(minutes=max(int(follow.cadence_minutes or 360), 15))
        follow.last_error = None
    except Exception as exc:
        run.status = "failed"
        run.error_message = str(exc)[:1000]
        run.completed_at = datetime.now(timezone.utc)
        follow.last_run_at = now
        follow.next_run_at = now + timedelta(minutes=max(int(follow.cadence_minutes or 360), 15))
        follow.last_error = str(exc)[:500]
    return _serialize_ingest_run(run)


async def run_feed_follow_ingest_service(
    *,
    user_id: str,
    follow_ids: Optional[List[str]],
    run_due_only: bool,
    max_follows: int,
    db: AsyncSession,
) -> Dict[str, Any]:
    _assert_research_enabled()
    now = datetime.now(timezone.utc)
    query = select(FeedSourceFollow).where(
        FeedSourceFollow.user_id == user_id,
        FeedSourceFollow.is_active.is_(True),
    )
    normalized_follow_ids = _clean_item_ids(follow_ids or [])
    if normalized_follow_ids:
        query = query.where(FeedSourceFollow.id.in_(normalized_follow_ids))
    result = await db.execute(query)
    follows = result.scalars().all()
    follows.sort(key=lambda row: (_as_utc(row.next_run_at) if row.next_run_at else now, row.created_at or now))

    if run_due_only:
        follows = [row for row in follows if row.next_run_at and _as_utc(row.next_run_at) <= now]

    limited = follows[: max(1, min(int(max_follows), 100))]
    runs: List[Dict[str, Any]] = []
    for follow in limited:
        runs.append(await _run_follow_ingest(follow=follow, db=db))

    await db.commit()
    completed = sum(1 for row in runs if row.get("status") == "completed")
    failed = sum(1 for row in runs if row.get("status") == "failed")
    await _record_feed_event(
        db=db,
        user_id=user_id,
        event_name="feed_follow_ingest_manual",
        status="ok" if failed == 0 else "partial",
        details={
            "scheduled_count": len(limited),
            "completed_count": completed,
            "failed_count": failed,
            "run_due_only": bool(run_due_only),
        },
    )
    await db.commit()
    return {
        "scheduled_count": len(limited),
        "completed_count": completed,
        "failed_count": failed,
        "runs": runs,
    }


async def list_feed_ingest_runs_service(
    *,
    user_id: str,
    follow_id: Optional[str],
    limit: int,
    db: AsyncSession,
) -> Dict[str, Any]:
    _assert_research_enabled()
    max_limit = max(1, min(int(limit), 200))
    query = select(FeedAutoIngestRun).where(FeedAutoIngestRun.user_id == user_id)
    if follow_id:
        query = query.where(FeedAutoIngestRun.follow_id == follow_id)
    result = await db.execute(query)
    rows = result.scalars().all()
    rows.sort(
        key=lambda row: _as_utc(row.created_at) if row.created_at else datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    payload = [_serialize_ingest_run(row) for row in rows[:max_limit]]
    return {"count": len(payload), "runs": payload}


async def run_due_feed_auto_ingest_service(max_follows: int = 25) -> Dict[str, Any]:
    """Run due follow ingests across all users (periodic scheduler entrypoint)."""
    if not settings.RESEARCH_ENABLED or not settings.FEED_AUTO_INGEST_ENABLED:
        return {"scheduled_count": 0, "completed_count": 0, "failed_count": 0, "runs": []}
    async with async_session_maker() as db:
        now = datetime.now(timezone.utc)
        query = select(FeedSourceFollow).where(
            FeedSourceFollow.is_active.is_(True),
            FeedSourceFollow.next_run_at.is_not(None),
        )
        result = await db.execute(query)
        follows = [
            row
            for row in result.scalars().all()
            if row.next_run_at and _as_utc(row.next_run_at) <= now
        ]
        follows.sort(key=lambda row: (_as_utc(row.next_run_at) if row.next_run_at else now, row.created_at or now))
        limited = follows[: max(1, min(int(max_follows), 200))]
        runs: List[Dict[str, Any]] = []
        for follow in limited:
            runs.append(await _run_follow_ingest(follow=follow, db=db))
        await db.commit()
        if limited:
            await _record_feed_event(
                db=db,
                user_id=limited[0].user_id,
                event_name="feed_follow_ingest_due_tick",
                status="ok",
                platform=limited[0].platform,
                details={
                    "scheduled_count": len(limited),
                    "completed_count": sum(1 for row in runs if row.get("status") == "completed"),
                    "failed_count": sum(1 for row in runs if row.get("status") == "failed"),
                },
            )
            await db.commit()
        return {
            "scheduled_count": len(limited),
            "completed_count": sum(1 for row in runs if row.get("status") == "completed"),
            "failed_count": sum(1 for row in runs if row.get("status") == "failed"),
            "runs": runs,
        }


def _build_repost_package_payload(
    *,
    item: ResearchItem,
    target_platforms: List[str],
    objective: str,
    tone: str,
) -> Dict[str, Any]:
    payload = _item_payload(item)
    metrics = payload.get("metrics", {}) if isinstance(payload.get("metrics"), dict) else {}
    views = _safe_int(metrics.get("views"), 0)
    likes = _safe_int(metrics.get("likes"), 0)
    comments = _safe_int(metrics.get("comments"), 0)
    shares = _safe_int(metrics.get("shares"), 0)
    saves = _safe_int(metrics.get("saves"), 0)
    media_meta = _safe_media_meta(item)
    transcript_text = _normalize_text(media_meta.get("transcript_text"))
    source_text = " ".join(
        [
            _normalize_text(item.title),
            _normalize_text(item.caption),
            transcript_text,
        ]
    ).strip()
    keywords = _extract_topic_keywords(source_text, limit=4)
    primary_topic = keywords[0] if keywords else "content growth"
    proof_phrase = f"{max(views, 1000):,} views"
    engagement_rate = float(payload.get("engagement_rate", 0.0) or 0.0)

    hooks = [
        {
            "style": "outcome_proof",
            "line": f"I tested this {primary_topic} structure and it drove {proof_phrase}.",
        },
        {
            "style": "curiosity_gap",
            "line": f"Most creators miss this {primary_topic} move, and it quietly kills retention.",
        },
        {
            "style": "contrarian_take",
            "line": f"Stop over-editing {primary_topic} videos. This simpler format performs better.",
        },
    ]

    caption_hashtags = _extract_hashtags(_normalize_text(item.caption))
    default_hashtags_by_platform = {
        "youtube": ["shorts", "creatorgrowth", "contentstrategy"],
        "instagram": ["reels", "contenttips", "creatorbusiness"],
        "tiktok": ["tiktoktips", "viralhooks", "creatorjourney"],
    }

    platform_packages: Dict[str, Any] = {}
    for platform in target_platforms:
        default_hashtags = default_hashtags_by_platform.get(platform, ["creatorgrowth"])
        hashtags = list(dict.fromkeys((caption_hashtags + default_hashtags)[:6]))
        hashtag_line = " ".join([f"#{tag}" for tag in hashtags if tag])
        cta = {
            "youtube": "Comment 'PLAN' and I'll share the exact checklist.",
            "instagram": "Save this Reel and share it with your content partner.",
            "tiktok": "Follow for part 2 where I break down the full posting workflow.",
        }.get(platform, "Follow for the next breakdown.")
        platform_packages[platform] = {
            "duration_target_s": REPOST_DURATION_TARGETS.get(platform, 28),
            "hook_deadline_s": REPOST_HOOK_DEADLINES.get(platform, 2),
            "first_frame_text": hooks[0]["line"][:80],
            "caption": (
                f"{hooks[0]['line']} "
                f"Step 1: Start with the proof. Step 2: Show one tactical move. Step 3: End with a single CTA. "
                f"{cta} {hashtag_line}"
            ).strip(),
            "cta_line": cta,
            "hashtags": [f"#{tag}" for tag in hashtags if tag],
            "edit_directives": [
                "Open with motion + headline text in the first second.",
                "Add one pattern interrupt every 2-3 seconds.",
                "Place strongest proof visual before the halfway point.",
            ],
        }

    checklist = [
        "Use one hook line only; avoid stacking multiple intros.",
        "Show a measurable proof moment within first 3 seconds.",
        "Keep body to 2-3 concrete steps with no filler.",
        "Use one CTA intent (save/share/comment/follow), not multiple.",
        "Export platform-native aspect ratio and verify subtitles.",
    ]
    if transcript_text:
        checklist.append("Keep top transcript phrase as on-screen text anchor.")

    score_estimate = round(
        min(
            100.0,
            max(
                0.0,
                (float(payload.get("trending_score", 0.0) or 0.0) * 0.6)
                + (engagement_rate * 100.0 * 0.4),
            ),
        ),
        1,
    )

    return {
        "objective": objective,
        "tone": tone,
        "source_snapshot": {
            "item_id": item.id,
            "platform": item.platform,
            "title": item.title,
            "caption": item.caption,
            "creator_handle": item.creator_handle,
            "metrics": {
                "views": views,
                "likes": likes,
                "comments": comments,
                "shares": shares,
                "saves": saves,
            },
            "engagement_rate": round(engagement_rate, 4),
        },
        "topic_keywords": keywords,
        "core_angle": f"Reuse the winning {primary_topic} proof-first structure with tighter pacing and one CTA.",
        "hook_variants": hooks,
        "platform_packages": platform_packages,
        "execution_checklist": checklist,
        "estimated_score": score_estimate,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _serialize_feed_repost_package(row: FeedRepostPackage) -> Dict[str, Any]:
    targets = row.target_platforms_json if isinstance(row.target_platforms_json, list) else []
    package = row.package_json if isinstance(row.package_json, dict) else {}
    return {
        "package_id": row.id,
        "source_item_id": row.source_item_id,
        "status": row.status,
        "target_platforms": [str(item) for item in targets],
        "package": package,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


async def create_feed_repost_package_service(
    *,
    user_id: str,
    payload: Dict[str, Any],
    db: AsyncSession,
) -> Dict[str, Any]:
    _assert_research_enabled()
    source_item_id = _normalize_text(payload.get("source_item_id"))
    if not source_item_id:
        raise HTTPException(status_code=422, detail="source_item_id is required.")
    result = await db.execute(
        select(ResearchItem).where(
            ResearchItem.id == source_item_id,
            ResearchItem.user_id == user_id,
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Feed source item not found.")

    targets = _normalize_target_platforms(payload.get("target_platforms"))
    objective = _normalize_text(payload.get("objective") or "maximize_reach")
    tone = _normalize_text(payload.get("tone") or "direct")
    package_payload = _build_repost_package_payload(
        item=item,
        target_platforms=targets,
        objective=objective,
        tone=tone,
    )
    row = FeedRepostPackage(
        id=str(uuid.uuid4()),
        user_id=user_id,
        source_item_id=item.id,
        status="draft",
        target_platforms_json=targets,
        package_json=package_payload,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    await _record_feed_event(
        db=db,
        user_id=user_id,
        event_name="feed_repost_package_created",
        status="ok",
        platform=item.platform,
        source_item_id=item.id,
        details={
            "target_platform_count": len(targets),
            "objective": objective[:80],
        },
    )
    await db.commit()
    return _serialize_feed_repost_package(row)


async def list_feed_repost_packages_service(
    *,
    user_id: str,
    source_item_id: Optional[str],
    limit: int,
    db: AsyncSession,
) -> Dict[str, Any]:
    _assert_research_enabled()
    query = select(FeedRepostPackage).where(FeedRepostPackage.user_id == user_id)
    normalized_item_id = _normalize_text(source_item_id)
    if normalized_item_id:
        query = query.where(FeedRepostPackage.source_item_id == normalized_item_id)
    result = await db.execute(query)
    rows = result.scalars().all()
    rows.sort(
        key=lambda row: _as_utc(row.created_at) if row.created_at else datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    max_limit = max(1, min(int(limit), 100))
    payload = [_serialize_feed_repost_package(row) for row in rows[:max_limit]]
    return {"count": len(payload), "packages": payload}


async def get_feed_repost_package_service(
    *,
    user_id: str,
    package_id: str,
    db: AsyncSession,
) -> Dict[str, Any]:
    _assert_research_enabled()
    result = await db.execute(
        select(FeedRepostPackage).where(
            FeedRepostPackage.id == package_id,
            FeedRepostPackage.user_id == user_id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Feed repost package not found.")
    return _serialize_feed_repost_package(row)


async def update_feed_repost_package_status_service(
    *,
    user_id: str,
    package_id: str,
    status: str,
    db: AsyncSession,
) -> Dict[str, Any]:
    _assert_research_enabled()
    next_status = _normalize_text(status).lower()
    if next_status not in REPOST_ALLOWED_STATUSES:
        raise HTTPException(status_code=422, detail="status must be one of draft, scheduled, published, archived.")
    result = await db.execute(
        select(FeedRepostPackage).where(
            FeedRepostPackage.id == package_id,
            FeedRepostPackage.user_id == user_id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Feed repost package not found.")
    row.status = next_status
    package_payload = row.package_json if isinstance(row.package_json, dict) else {}
    row.package_json = {
        **package_payload,
        "status_updated_at": datetime.now(timezone.utc).isoformat(),
        "status": next_status,
    }
    await _record_feed_event(
        db=db,
        user_id=user_id,
        event_name="feed_repost_package_status",
        status=next_status,
        source_item_id=row.source_item_id,
        details={"package_id": row.id},
    )
    await db.commit()
    await db.refresh(row)
    return _serialize_feed_repost_package(row)


def _source_text_blob(item: ResearchItem) -> str:
    media_meta = _safe_media_meta(item)
    return " ".join(
        [
            _normalize_text(item.title),
            _normalize_text(item.caption),
            _normalize_text(media_meta.get("transcript_text")),
        ]
    ).strip()


async def _resolve_source_item(user_id: str, source_item_id: str, db: AsyncSession) -> ResearchItem:
    result = await db.execute(
        select(ResearchItem).where(
            ResearchItem.id == source_item_id,
            ResearchItem.user_id == user_id,
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Feed source item not found.")
    return item


def _infer_loop_topic(item: ResearchItem) -> str:
    blob = _source_text_blob(item)
    tokens = _extract_topic_keywords(blob, limit=5)
    if tokens:
        return " ".join(tokens[:3])
    if item.title:
        return _normalize_text(item.title)[:90]
    return "content strategy"


def _infer_loop_audience(item: ResearchItem) -> str:
    handle = _normalize_text(item.creator_handle).lstrip("@")
    if handle:
        return f"creators similar to {handle}"
    return "solo creators"


def _infer_loop_objective(item: ResearchItem) -> str:
    metrics = item.metrics_json if isinstance(item.metrics_json, dict) else {}
    shares = _safe_int(metrics.get("shares"), 0)
    saves = _safe_int(metrics.get("saves"), 0)
    comments = _safe_int(metrics.get("comments"), 0)
    if shares + saves > comments:
        return "increase shares and saves"
    return "increase watch retention and comments"


async def run_feed_loop_variant_generate_service(
    *,
    user_id: str,
    payload: Dict[str, Any],
    db: AsyncSession,
) -> Dict[str, Any]:
    _assert_research_enabled()
    source_item_id = _normalize_text(payload.get("source_item_id"))
    if not source_item_id:
        raise HTTPException(status_code=422, detail="source_item_id is required.")
    item = await _resolve_source_item(user_id, source_item_id, db)

    platform = _normalized_platform(payload.get("platform"), required=False) or item.platform
    topic = _normalize_text(payload.get("topic")) or _infer_loop_topic(item)
    audience = _normalize_text(payload.get("audience")) or _infer_loop_audience(item)
    objective = _normalize_text(payload.get("objective")) or _infer_loop_objective(item)
    tone = _normalize_text(payload.get("tone") or "bold")
    duration_s = _safe_int(payload.get("duration_s"), 0) or None
    generation_mode = _normalize_text(payload.get("generation_mode") or "ai_first_fallback")
    constraints = payload.get("constraints") if isinstance(payload.get("constraints"), dict) else {}
    constraints = {
        "platform": platform,
        "duration_s": duration_s,
        "tone": tone,
        **constraints,
    }

    credit_charge = await consume_credits(
        user_id,
        db,
        cost=max(int(settings.CREDIT_COST_OPTIMIZER_VARIANTS), 0),
        reason="Feed loop variant generation",
        reference_type="feed_loop_variant_generate",
        reference_id=source_item_id,
    )

    result = await generate_variants_service(
        user_id=user_id,
        payload={
            "platform": platform,
            "topic": topic,
            "audience": audience,
            "objective": objective,
            "tone": tone,
            "duration_s": duration_s,
            "source_item_id": source_item_id,
            "generation_mode": generation_mode,
            "constraints": constraints,
        },
        db=db,
    )
    media_meta = _safe_media_meta(item)
    item.media_meta_json = {
        **media_meta,
        "loop_last_variant_batch_at": datetime.now(timezone.utc).isoformat(),
        "loop_last_variant_count": len(result.get("variants", [])),
    }
    await _record_feed_event(
        db=db,
        user_id=user_id,
        event_name="feed_loop_variant_generate",
        status="ok",
        platform=platform,
        source_item_id=source_item_id,
        details={
            "variant_count": len(result.get("variants", [])),
            "used_fallback": bool(result.get("generation", {}).get("used_fallback")),
            "charged": int(credit_charge.get("charged", 0)),
        },
    )
    await db.commit()
    return {
        "source_item_id": source_item_id,
        "platform": platform,
        "topic": topic,
        "audience": audience,
        "objective": objective,
        "optimizer": result,
        "credits": credit_charge,
    }


async def _resolve_source_upload_for_audit(
    *,
    user_id: str,
    item: ResearchItem,
    db: AsyncSession,
) -> Dict[str, Any]:
    media_meta = _safe_media_meta(item)
    download_job_id = _normalize_text(media_meta.get("feed_download_job_id"))
    candidate_jobs: List[MediaDownloadJob] = []

    if download_job_id:
        result = await db.execute(
            select(MediaDownloadJob).where(
                MediaDownloadJob.id == download_job_id,
                MediaDownloadJob.user_id == user_id,
            )
        )
        row = result.scalar_one_or_none()
        if row:
            candidate_jobs.append(row)

    if not candidate_jobs and item.url:
        result = await db.execute(
            select(MediaDownloadJob).where(
                MediaDownloadJob.user_id == user_id,
                MediaDownloadJob.source_url == item.url,
            )
        )
        rows = result.scalars().all()
        candidate_jobs.extend(rows)

    candidate_jobs.sort(
        key=lambda row: _as_utc(row.created_at) if row.created_at else datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    selected = next(
        (row for row in candidate_jobs if row.status == "completed" and row.upload_id),
        None,
    )
    if selected is None:
        raise HTTPException(
            status_code=409,
            detail=(
                "No completed feed download found for this item. "
                "Run /feed/download/bulk and wait for completion before starting audit."
            ),
        )
    upload_result = await db.execute(
        select(Upload).where(
            Upload.id == selected.upload_id,
            Upload.user_id == user_id,
            Upload.file_type == "video",
        )
    )
    upload = upload_result.scalar_one_or_none()
    if upload is None or not upload.file_url:
        raise HTTPException(status_code=404, detail="Upload for feed download is missing.")
    if not Path(upload.file_url).exists():
        raise HTTPException(status_code=404, detail="Downloaded upload file is missing on disk.")
    return {
        "upload_id": upload.id,
        "upload_path": upload.file_url,
        "download_job_id": selected.id,
    }


async def run_feed_loop_audit_service(
    *,
    user_id: str,
    payload: Dict[str, Any],
    db: AsyncSession,
) -> Dict[str, Any]:
    _assert_research_enabled()
    source_item_id = _normalize_text(payload.get("source_item_id"))
    if not source_item_id:
        raise HTTPException(status_code=422, detail="source_item_id is required.")
    item = await _resolve_source_item(user_id, source_item_id, db)
    source_upload = await _resolve_source_upload_for_audit(user_id=user_id, item=item, db=db)

    platform = _normalized_platform(payload.get("platform"), required=False) or item.platform
    retention_points = payload.get("retention_points") if isinstance(payload.get("retention_points"), list) else []
    platform_metrics = payload.get("platform_metrics") if isinstance(payload.get("platform_metrics"), dict) else None
    draft_snapshot_id = _normalize_text(payload.get("draft_snapshot_id")) or None
    repost_package_id = _normalize_text(payload.get("repost_package_id")) or None

    audit_id = str(uuid.uuid4())
    credit_charge = await consume_credits(
        user_id,
        db,
        cost=max(int(settings.CREDIT_COST_AUDIT_RUN), 0),
        reason="Feed loop audit run",
        reference_type="feed_loop_audit",
        reference_id=audit_id,
    )

    db_audit = Audit(
        id=audit_id,
        user_id=user_id,
        status="pending",
        progress="0",
        input_json={
            "source_mode": "upload",
            "platform": platform,
            "video_url": None,
            "upload_id": source_upload["upload_id"],
            "source_item_id": source_item_id,
            "feed_download_job_id": source_upload["download_job_id"],
            "draft_snapshot_id": draft_snapshot_id,
            "repost_package_id": repost_package_id,
            "retention_points": retention_points,
            "platform_metrics": platform_metrics,
        },
    )
    db.add(db_audit)
    await db.commit()
    await db.refresh(db_audit)

    try:
        job = enqueue_audit_job(
            audit_id=audit_id,
            video_url=None,
            upload_path=source_upload["upload_path"],
            source_mode="upload",
        )
        if isinstance(db_audit.input_json, dict):
            db_audit.input_json = {
                **db_audit.input_json,
                "queue_job_id": job.id,
                "queue_name": job.origin,
            }
        media_meta = _safe_media_meta(item)
        item.media_meta_json = {
            **media_meta,
            "loop_last_audit_id": audit_id,
            "loop_last_audit_at": datetime.now(timezone.utc).isoformat(),
        }
        await _record_feed_event(
            db=db,
            user_id=user_id,
            event_name="feed_loop_audit_start",
            status="ok",
            platform=platform,
            source_item_id=source_item_id,
            details={
                "audit_id": audit_id,
                "upload_id": source_upload["upload_id"],
                "charged": int(credit_charge.get("charged", 0)),
            },
        )
        await db.commit()
    except Exception as exc:
        if int(credit_charge.get("charged", 0)) > 0:
            try:
                await add_credit_purchase(
                    user_id,
                    db,
                    credits=int(credit_charge.get("charged", 0)),
                    provider="system_refund",
                    billing_reference=f"feed_loop_audit_refund:{audit_id}",
                    reason="Refund for failed feed loop audit queue enqueue",
                )
            except Exception:
                pass
        db_audit.status = "failed"
        db_audit.error_message = "Could not enqueue audit job. Check Redis/worker availability."
        await db.commit()
        raise HTTPException(status_code=503, detail="Audit queue unavailable. Try again shortly.") from exc

    return {
        "audit_id": audit_id,
        "status": "pending",
        "source_item_id": source_item_id,
        "upload_id": source_upload["upload_id"],
        "report_path": f"/report/{audit_id}",
        "credits": credit_charge,
    }


def _audit_matches_source_item(audit: Audit, source_item_id: str) -> bool:
    payload = audit.input_json if isinstance(audit.input_json, dict) else {}
    return _normalize_text(payload.get("source_item_id")) == source_item_id


def _serialize_audit_summary(audit: Audit) -> Dict[str, Any]:
    return {
        "audit_id": audit.id,
        "status": audit.status,
        "progress": audit.progress,
        "created_at": audit.created_at.isoformat() if audit.created_at else None,
        "completed_at": audit.completed_at.isoformat() if audit.completed_at else None,
        "report_path": f"/report/{audit.id}",
    }


def _serialize_draft_summary(row: DraftSnapshot) -> Dict[str, Any]:
    return {
        "snapshot_id": row.id,
        "platform": row.platform,
        "rescored_score": round(float(row.rescored_score or 0.0), 1),
        "delta_score": round(float(row.delta_score or 0.0), 1) if row.delta_score is not None else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


async def get_feed_loop_summary_service(
    *,
    user_id: str,
    source_item_id: str,
    db: AsyncSession,
) -> Dict[str, Any]:
    _assert_research_enabled()
    item = await _resolve_source_item(user_id, source_item_id, db)

    package_result = await db.execute(
        select(FeedRepostPackage).where(
            FeedRepostPackage.user_id == user_id,
            FeedRepostPackage.source_item_id == source_item_id,
        )
    )
    packages = package_result.scalars().all()
    packages.sort(
        key=lambda row: _as_utc(row.created_at) if row.created_at else datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    latest_package = _serialize_feed_repost_package(packages[0]) if packages else None

    snapshot_result = await db.execute(
        select(DraftSnapshot).where(
            DraftSnapshot.user_id == user_id,
            DraftSnapshot.source_item_id == source_item_id,
        )
    )
    snapshots = snapshot_result.scalars().all()
    snapshots.sort(
        key=lambda row: _as_utc(row.created_at) if row.created_at else datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    latest_snapshot = _serialize_draft_summary(snapshots[0]) if snapshots else None

    audit_result = await db.execute(
        select(Audit).where(Audit.user_id == user_id)
    )
    audits = [row for row in audit_result.scalars().all() if _audit_matches_source_item(row, source_item_id)]
    audits.sort(
        key=lambda row: _as_utc(row.created_at) if row.created_at else datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    latest_audit = _serialize_audit_summary(audits[0]) if audits else None

    stage_completion = {
        "discovered": True,
        "packaged": latest_package is not None,
        "scripted": latest_snapshot is not None,
        "audited": latest_audit is not None,
        "reported": bool(latest_audit and latest_audit.get("status") == "completed"),
    }
    if not stage_completion["packaged"]:
        next_step = "Generate a repost package."
    elif not stage_completion["scripted"]:
        next_step = "Generate AI variants and save a draft snapshot."
    elif not stage_completion["audited"]:
        next_step = "Run feed loop audit from downloaded upload."
    elif not stage_completion["reported"]:
        next_step = "Wait for audit completion and open report."
    else:
        next_step = "Log post outcomes to continue calibration."

    response = {
        "source_item_id": source_item_id,
        "source_item": _item_payload(item),
        "latest_repost_package": latest_package,
        "latest_draft_snapshot": latest_snapshot,
        "latest_audit": latest_audit,
        "stage_completion": stage_completion,
        "next_step": next_step,
    }
    await _record_feed_event(
        db=db,
        user_id=user_id,
        event_name="feed_loop_summary_view",
        status="ok",
        platform=item.platform,
        source_item_id=source_item_id,
        details={
            "packaged": stage_completion["packaged"],
            "scripted": stage_completion["scripted"],
            "audited": stage_completion["audited"],
            "reported": stage_completion["reported"],
        },
    )
    await db.commit()
    return response


def _audit_source_item_id(audit: Audit) -> Optional[str]:
    payload = audit.input_json if isinstance(audit.input_json, dict) else {}
    source_item_id = _normalize_text(payload.get("source_item_id"))
    return source_item_id or None


async def get_feed_telemetry_summary_service(
    *,
    user_id: str,
    days: int,
    db: AsyncSession,
) -> Dict[str, Any]:
    _assert_research_enabled()
    lookback_days = max(1, min(int(days), 90))
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)

    event_result = await db.execute(
        select(FeedTelemetryEvent).where(
            FeedTelemetryEvent.user_id == user_id,
            FeedTelemetryEvent.created_at >= cutoff,
        )
    )
    events = event_result.scalars().all()
    by_event: Dict[str, int] = {}
    by_status: Dict[str, int] = {}
    for event in events:
        by_event[event.event_name] = by_event.get(event.event_name, 0) + 1
        by_status[event.status] = by_status.get(event.status, 0) + 1

    item_result = await db.execute(
        select(ResearchItem).where(ResearchItem.user_id == user_id)
    )
    items = item_result.scalars().all()
    discovered_ids = {row.id for row in items}

    package_result = await db.execute(
        select(FeedRepostPackage).where(FeedRepostPackage.user_id == user_id)
    )
    packaged_ids = {row.source_item_id for row in package_result.scalars().all() if row.source_item_id}

    snapshot_result = await db.execute(
        select(DraftSnapshot).where(DraftSnapshot.user_id == user_id)
    )
    scripted_ids = {row.source_item_id for row in snapshot_result.scalars().all() if row.source_item_id}

    audit_result = await db.execute(
        select(Audit).where(Audit.user_id == user_id)
    )
    audits = audit_result.scalars().all()
    audited_ids: set[str] = set()
    reported_ids: set[str] = set()
    for row in audits:
        source_item_id = _audit_source_item_id(row)
        if not source_item_id:
            continue
        audited_ids.add(source_item_id)
        if row.status == "completed":
            reported_ids.add(source_item_id)

    discovered_count = len(discovered_ids)
    packaged_count = len(packaged_ids)
    scripted_count = len(scripted_ids)
    audited_count = len(audited_ids)
    reported_count = len(reported_ids)

    def _ratio(numerator: int, denominator: int) -> float:
        if denominator <= 0:
            return 0.0
        return round((numerator / denominator) * 100.0, 1)

    return {
        "window_days": lookback_days,
        "event_volume": {
            "total_events": len(events),
            "by_event": by_event,
            "by_status": by_status,
            "error_count": sum(1 for event in events if event.status in {"error", "failed"}),
        },
        "funnel": {
            "discovered_count": discovered_count,
            "packaged_count": packaged_count,
            "scripted_count": scripted_count,
            "audited_count": audited_count,
            "reported_count": reported_count,
            "discover_to_package_pct": _ratio(packaged_count, discovered_count),
            "package_to_script_pct": _ratio(scripted_count, packaged_count),
            "script_to_audit_pct": _ratio(audited_count, scripted_count),
            "audit_to_report_pct": _ratio(reported_count, audited_count),
        },
    }


async def list_feed_telemetry_events_service(
    *,
    user_id: str,
    days: int,
    limit: int,
    event_name: Optional[str],
    status: Optional[str],
    db: AsyncSession,
) -> Dict[str, Any]:
    _assert_research_enabled()
    lookback_days = max(1, min(int(days), 90))
    max_limit = max(1, min(int(limit), 200))
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)

    result = await db.execute(
        select(FeedTelemetryEvent).where(
            FeedTelemetryEvent.user_id == user_id,
            FeedTelemetryEvent.created_at >= cutoff,
        )
    )
    rows = result.scalars().all()
    normalized_event = _normalize_text(event_name)
    normalized_status = _normalize_text(status)
    if normalized_event:
        rows = [row for row in rows if row.event_name == normalized_event]
    if normalized_status:
        rows = [row for row in rows if row.status == normalized_status]
    rows.sort(
        key=lambda row: _as_utc(row.created_at) if row.created_at else datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )

    events_payload = [
        {
            "event_id": row.id,
            "event_name": row.event_name,
            "status": row.status,
            "platform": row.platform,
            "source_item_id": row.source_item_id,
            "details": row.details_json if isinstance(row.details_json, dict) else {},
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows[:max_limit]
    ]
    return {
        "window_days": lookback_days,
        "count": len(events_payload),
        "events": events_payload,
    }
