"""Research ingestion/search/export services."""

from __future__ import annotations

import csv
import io
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import uuid

from fastapi import HTTPException, UploadFile
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from config import require_youtube_api_key, settings
from ingestion.youtube import create_youtube_client_with_api_key
from models.research_collection import ResearchCollection
from models.research_item import ResearchItem

logger = logging.getLogger(__name__)

ALLOWED_RESEARCH_PLATFORMS = {"youtube", "instagram", "tiktok"}
ALLOWED_SORT_KEYS = {"created_at", "posted_at", "views", "likes", "comments", "shares", "saves"}
ALLOWED_EXPORT_FORMATS = {"csv", "json"}
TIMEFRAME_WINDOWS = {
    "24h": timedelta(days=1),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "90d": timedelta(days=90),
    "all": None,
}
EXPORT_DIR = Path("/tmp/spc_exports")


def _assert_research_enabled() -> None:
    if not settings.RESEARCH_ENABLED:
        raise HTTPException(status_code=503, detail="Research module disabled by feature flag.")


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _parse_datetime(value: Any) -> Optional[datetime]:
    text = _normalize_text(value)
    if not text:
        return None
    try:
        normalized = text.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return None


def _infer_platform(platform: Optional[str], url: str) -> str:
    platform_hint = _normalize_text(platform).lower()
    if platform_hint in ALLOWED_RESEARCH_PLATFORMS:
        return platform_hint
    lower = _normalize_text(url).lower()
    if "instagram.com" in lower:
        return "instagram"
    if "tiktok.com" in lower:
        return "tiktok"
    if "youtube.com" in lower or "youtu.be" in lower:
        return "youtube"
    raise HTTPException(status_code=422, detail="Unable to infer platform. Provide platform explicitly.")


def _extract_external_id(platform: str, url: str) -> Optional[str]:
    text = _normalize_text(url)
    if platform == "youtube":
        patterns = [
            r"(?:v=)([A-Za-z0-9_-]{11})",
            r"(?:youtu\.be/)([A-Za-z0-9_-]{11})",
            r"(?:shorts/)([A-Za-z0-9_-]{11})",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
    if platform == "instagram":
        match = re.search(r"/(?:reel|p)/([A-Za-z0-9_-]+)", text)
        if match:
            return match.group(1)
    if platform == "tiktok":
        match = re.search(r"/video/([0-9]+)", text)
        if match:
            return match.group(1)
    return None


def _extract_creator_handle(platform: str, url: str) -> Optional[str]:
    text = _normalize_text(url)
    if platform == "instagram":
        match = re.search(r"instagram\.com/([A-Za-z0-9._]+)/", text)
        if match:
            return f"@{match.group(1)}"
    if platform == "tiktok":
        match = re.search(r"tiktok\.com/@([A-Za-z0-9._-]+)", text)
        if match:
            return f"@{match.group(1)}"
    if platform == "youtube":
        match = re.search(r"youtube\.com/@([A-Za-z0-9._-]+)", text)
        if match:
            return f"@{match.group(1)}"
    return None


async def _ensure_default_collection(user_id: str, db: AsyncSession) -> ResearchCollection:
    result = await db.execute(
        select(ResearchCollection)
        .where(
            ResearchCollection.user_id == user_id,
            ResearchCollection.is_system.is_(True),
            ResearchCollection.name == "Default Collection",
        )
        .limit(1)
    )
    collection = result.scalar_one_or_none()
    if collection:
        return collection
    collection = ResearchCollection(
        id=str(uuid.uuid4()),
        user_id=user_id,
        name="Default Collection",
        platform="mixed",
        description="Default collection for imported research items.",
        is_system=True,
    )
    db.add(collection)
    await db.flush()
    return collection


def _canonical_item_payload(item: ResearchItem) -> Dict[str, Any]:
    metrics = item.metrics_json if isinstance(item.metrics_json, dict) else {}
    media_meta = item.media_meta_json if isinstance(item.media_meta_json, dict) else {}
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
        "metrics": {
            "views": _safe_int(metrics.get("views"), 0),
            "likes": _safe_int(metrics.get("likes"), 0),
            "comments": _safe_int(metrics.get("comments"), 0),
            "shares": _safe_int(metrics.get("shares"), 0),
            "saves": _safe_int(metrics.get("saves"), 0),
        },
        "media_meta": media_meta,
        "published_at": item.published_at.isoformat() if item.published_at else None,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "collection_id": item.collection_id,
    }


def _metrics_from_row(row: Dict[str, Any]) -> Dict[str, int]:
    return {
        "views": _safe_int(row.get("views"), 0),
        "likes": _safe_int(row.get("likes"), 0),
        "comments": _safe_int(row.get("comments"), 0),
        "shares": _safe_int(row.get("shares"), 0),
        "saves": _safe_int(row.get("saves"), 0),
    }


async def import_research_url_service(
    *,
    user_id: str,
    platform: Optional[str],
    url: str,
    db: AsyncSession,
) -> Dict[str, Any]:
    _assert_research_enabled()
    canonical_url = _normalize_text(url)
    if not canonical_url:
        raise HTTPException(status_code=422, detail="url is required")
    resolved_platform = _infer_platform(platform, canonical_url)
    collection = await _ensure_default_collection(user_id, db)

    external_id = _extract_external_id(resolved_platform, canonical_url)
    creator_handle = _extract_creator_handle(resolved_platform, canonical_url)
    title = None
    caption = None
    metrics = {"views": 0, "likes": 0, "comments": 0, "shares": 0, "saves": 0}
    media_meta: Dict[str, Any] = {
        "import_mode": "manual_url",
        "download_enabled": bool(settings.ALLOW_EXTERNAL_MEDIA_DOWNLOAD),
    }

    if resolved_platform == "youtube" and external_id:
        try:
            client = create_youtube_client_with_api_key(require_youtube_api_key())
            details = client.get_video_details([external_id]).get(external_id, {})
            title = _normalize_text(details.get("title"))
            caption = _normalize_text(details.get("description"))
            metrics.update(
                {
                    "views": _safe_int(details.get("view_count"), 0),
                    "likes": _safe_int(details.get("like_count"), 0),
                    "comments": _safe_int(details.get("comment_count"), 0),
                }
            )
            media_meta.update(
                {
                    "thumbnail_url": details.get("thumbnail_url"),
                    "duration_seconds": _safe_int(details.get("duration_seconds"), 0),
                }
            )
        except Exception as exc:
            logger.warning("YouTube enrichment failed for research import url=%s: %s", canonical_url, exc)

    item = ResearchItem(
        id=str(uuid.uuid4()),
        user_id=user_id,
        collection_id=collection.id,
        platform=resolved_platform,
        source_type="manual_url",
        url=canonical_url,
        external_id=external_id,
        creator_handle=creator_handle,
        creator_display_name=creator_handle,
        title=title,
        caption=caption,
        metrics_json=metrics,
        media_meta_json=media_meta,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    logger.info("research_import_url user=%s platform=%s item=%s", user_id, resolved_platform, item.id)
    return _canonical_item_payload(item)


async def capture_research_item_service(
    *,
    user_id: str,
    payload: Dict[str, Any],
    db: AsyncSession,
) -> Dict[str, Any]:
    _assert_research_enabled()
    resolved_platform = _infer_platform(payload.get("platform"), _normalize_text(payload.get("url")))
    collection = await _ensure_default_collection(user_id, db)
    url = _normalize_text(payload.get("url"))
    external_id = _normalize_text(payload.get("external_id")) or _extract_external_id(resolved_platform, url)
    creator_handle = _normalize_text(payload.get("creator_handle")) or _extract_creator_handle(resolved_platform, url)
    published_at = _parse_datetime(payload.get("published_at"))
    metrics = _metrics_from_row(payload if isinstance(payload, dict) else {})
    media_meta = payload.get("media_meta") if isinstance(payload.get("media_meta"), dict) else {}
    item = ResearchItem(
        id=str(uuid.uuid4()),
        user_id=user_id,
        collection_id=collection.id,
        platform=resolved_platform,
        source_type="browser_capture",
        url=url or None,
        external_id=external_id or None,
        creator_handle=creator_handle or None,
        creator_display_name=_normalize_text(payload.get("creator_display_name")) or creator_handle or None,
        title=_normalize_text(payload.get("title")) or None,
        caption=_normalize_text(payload.get("caption")) or None,
        metrics_json=metrics,
        media_meta_json=media_meta,
        published_at=published_at,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    logger.info("research_capture user=%s platform=%s item=%s", user_id, resolved_platform, item.id)
    return _canonical_item_payload(item)


async def import_research_csv_service(
    *,
    user_id: str,
    platform: Optional[str],
    file: UploadFile,
    db: AsyncSession,
) -> Dict[str, Any]:
    _assert_research_enabled()
    try:
        content = await file.read()
        if len(content) > 5 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="CSV file too large. Max 5MB.")
        text = content.decode("utf-8-sig")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not read CSV file: {exc}") from exc
    finally:
        await file.close()

    try:
        reader = csv.DictReader(io.StringIO(text))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid CSV: {exc}") from exc

    collection = ResearchCollection(
        id=str(uuid.uuid4()),
        user_id=user_id,
        name=f"CSV Import {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}",
        platform=(platform or "mixed"),
        description="Bulk imported collection.",
        is_system=False,
    )
    db.add(collection)
    await db.flush()

    imported_count = 0
    failures: List[Dict[str, Any]] = []
    for row_idx, row in enumerate(reader, start=2):
        row_url = _normalize_text(row.get("url") or row.get("video_url"))
        row_platform = None
        try:
            row_platform = _infer_platform(platform or row.get("platform"), row_url)
        except HTTPException:
            if platform in ALLOWED_RESEARCH_PLATFORMS:
                row_platform = str(platform)
            else:
                failures.append({"row": row_idx, "error": "Could not infer platform"})
                continue

        item = ResearchItem(
            id=str(uuid.uuid4()),
            user_id=user_id,
            collection_id=collection.id,
            platform=row_platform,
            source_type="csv_import",
            url=row_url or None,
            external_id=_normalize_text(row.get("external_id") or row.get("video_external_id")) or _extract_external_id(row_platform, row_url),
            creator_handle=_normalize_text(row.get("creator_handle")) or _extract_creator_handle(row_platform, row_url),
            creator_display_name=_normalize_text(row.get("creator_display_name")) or None,
            title=_normalize_text(row.get("title")) or None,
            caption=_normalize_text(row.get("caption") or row.get("description")) or None,
            metrics_json=_metrics_from_row(row),
            media_meta_json={
                "thumbnail_url": _normalize_text(row.get("thumbnail_url")) or None,
                "duration_seconds": _safe_int(row.get("duration_seconds"), 0) or None,
            },
            published_at=_parse_datetime(row.get("published_at")),
        )
        db.add(item)
        imported_count += 1

    await db.commit()
    logger.info(
        "research_import_csv user=%s collection=%s imported=%s failures=%s",
        user_id,
        collection.id,
        imported_count,
        len(failures),
    )
    return {
        "imported_count": imported_count,
        "failed_rows": failures,
        "collection_id": collection.id,
    }


def _timeframe_cutoff(timeframe: str) -> Optional[datetime]:
    key = str(timeframe or "all").strip().lower()
    delta = TIMEFRAME_WINDOWS.get(key)
    if delta is None:
        return None
    return datetime.now(timezone.utc) - delta


def _row_metric(item: ResearchItem, key: str) -> int:
    metrics = item.metrics_json if isinstance(item.metrics_json, dict) else {}
    return _safe_int(metrics.get(key), 0)


def _search_text(item: ResearchItem) -> str:
    return " ".join(
        [
            _normalize_text(item.title),
            _normalize_text(item.caption),
            _normalize_text(item.creator_handle),
            _normalize_text(item.creator_display_name),
        ]
    ).lower()


def _sort_items(items: List[ResearchItem], sort_by: str, sort_direction: str) -> List[ResearchItem]:
    resolved_sort = sort_by if sort_by in ALLOWED_SORT_KEYS else "created_at"
    reverse = str(sort_direction).lower() != "asc"

    def _key(item: ResearchItem) -> Any:
        if resolved_sort in {"views", "likes", "comments", "shares", "saves"}:
            return _row_metric(item, resolved_sort)
        if resolved_sort == "posted_at":
            return item.published_at or datetime.fromtimestamp(0, tz=timezone.utc)
        return item.created_at or datetime.fromtimestamp(0, tz=timezone.utc)

    return sorted(items, key=_key, reverse=reverse)


async def search_research_items_service(
    *,
    user_id: str,
    payload: Dict[str, Any],
    db: AsyncSession,
) -> Dict[str, Any]:
    _assert_research_enabled()
    result = await db.execute(
        select(ResearchItem).where(ResearchItem.user_id == user_id)
    )
    items = result.scalars().all()
    platform = _normalize_text(payload.get("platform")).lower()
    if platform in ALLOWED_RESEARCH_PLATFORMS:
        items = [item for item in items if item.platform == platform]

    cutoff = _timeframe_cutoff(_normalize_text(payload.get("timeframe") or "all"))
    if cutoff:
        items = [
            item for item in items
            if (item.published_at and item.published_at >= cutoff)
            or (item.created_at and item.created_at >= cutoff)
        ]

    query = _normalize_text(payload.get("query")).lower()
    if query:
        items = [item for item in items if query in _search_text(item)]

    sorted_items = _sort_items(
        items=items,
        sort_by=_normalize_text(payload.get("sort_by") or "created_at"),
        sort_direction=_normalize_text(payload.get("sort_direction") or "desc"),
    )
    page = max(_safe_int(payload.get("page"), 1), 1)
    limit = max(1, min(_safe_int(payload.get("limit"), 20), 100))
    start = (page - 1) * limit
    end = start + limit
    page_rows = sorted_items[start:end]
    has_more = end < len(sorted_items)

    logger.info(
        "research_search_run user=%s platform=%s query=%s page=%s limit=%s total=%s",
        user_id,
        platform or "all",
        query,
        page,
        limit,
        len(sorted_items),
    )
    return {
        "page": page,
        "limit": limit,
        "total_count": len(sorted_items),
        "has_more": has_more,
        "items": [_canonical_item_payload(item) for item in page_rows],
    }


async def list_research_collections_service(user_id: str, db: AsyncSession) -> List[Dict[str, Any]]:
    _assert_research_enabled()
    result = await db.execute(
        select(ResearchCollection).where(ResearchCollection.user_id == user_id).order_by(ResearchCollection.created_at.desc())
    )
    rows = result.scalars().all()
    return [
        {
            "id": row.id,
            "name": row.name,
            "platform": row.platform,
            "description": row.description,
            "is_system": bool(row.is_system),
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


async def get_research_item_service(user_id: str, item_id: str, db: AsyncSession) -> Dict[str, Any]:
    _assert_research_enabled()
    result = await db.execute(
        select(ResearchItem).where(
            ResearchItem.id == item_id,
            ResearchItem.user_id == user_id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Research item not found")
    return _canonical_item_payload(item)


def _export_token(user_id: str, export_id: str, ttl_minutes: int = 30) -> str:
    now = datetime.now(timezone.utc)
    claims = {
        "sub": user_id,
        "export_id": export_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ttl_minutes)).timestamp()),
        "purpose": "research_export",
    }
    return jwt.encode(claims, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_export_token(token: str) -> Dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid export token.") from exc
    if payload.get("purpose") != "research_export":
        raise HTTPException(status_code=401, detail="Invalid export token purpose.")
    return payload


def _collection_items_to_rows(collection: ResearchCollection, items: List[ResearchItem]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in items:
        payload = _canonical_item_payload(item)
        rows.append(
            {
                "collection_id": collection.id,
                "collection_name": collection.name,
                "item_id": payload["item_id"],
                "platform": payload["platform"],
                "url": payload.get("url"),
                "external_id": payload.get("external_id"),
                "creator_handle": payload.get("creator_handle"),
                "title": payload.get("title"),
                "caption": payload.get("caption"),
                "views": payload["metrics"]["views"],
                "likes": payload["metrics"]["likes"],
                "comments": payload["metrics"]["comments"],
                "shares": payload["metrics"]["shares"],
                "saves": payload["metrics"]["saves"],
                "published_at": payload.get("published_at"),
                "created_at": payload.get("created_at"),
            }
        )
    return rows


async def export_research_collection_service(
    *,
    user_id: str,
    collection_id: str,
    export_format: str,
    db: AsyncSession,
) -> Dict[str, Any]:
    _assert_research_enabled()
    fmt = _normalize_text(export_format).lower()
    if fmt not in ALLOWED_EXPORT_FORMATS:
        raise HTTPException(status_code=422, detail="format must be 'csv' or 'json'")

    collection_result = await db.execute(
        select(ResearchCollection).where(
            ResearchCollection.id == collection_id,
            ResearchCollection.user_id == user_id,
        )
    )
    collection = collection_result.scalar_one_or_none()
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    items_result = await db.execute(
        select(ResearchItem).where(
            ResearchItem.user_id == user_id,
            ResearchItem.collection_id == collection_id,
        )
    )
    items = items_result.scalars().all()
    rows = _collection_items_to_rows(collection, items)

    export_id = str(uuid.uuid4())
    user_dir = EXPORT_DIR / user_id
    user_dir.mkdir(parents=True, exist_ok=True)
    file_path = user_dir / f"{export_id}.{fmt}"
    if fmt == "json":
        file_path.write_text(json.dumps(rows, indent=2, ensure_ascii=True), encoding="utf-8")
    else:
        buffer = io.StringIO()
        fieldnames = [
            "collection_id",
            "collection_name",
            "item_id",
            "platform",
            "url",
            "external_id",
            "creator_handle",
            "title",
            "caption",
            "views",
            "likes",
            "comments",
            "shares",
            "saves",
            "published_at",
            "created_at",
        ]
        writer = csv.DictWriter(buffer, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
        file_path.write_text(buffer.getvalue(), encoding="utf-8")

    token = _export_token(user_id, export_id)
    return {
        "export_id": export_id,
        "status": "completed",
        "signed_url": f"/research/export/{export_id}/download?token={token}",
        "format": fmt,
        "item_count": len(rows),
    }


def resolve_export_file(user_id: str, export_id: str) -> Tuple[Path, str]:
    for ext in ("csv", "json"):
        path = EXPORT_DIR / user_id / f"{export_id}.{ext}"
        if path.exists():
            return path, ext
    raise HTTPException(status_code=404, detail="Export file not found")
