"""Simple Redis-backed rate limiting dependency."""

from __future__ import annotations

import asyncio
import time
from typing import Callable, Dict, Tuple

from fastapi import Depends, HTTPException, Request
import redis.asyncio as redis

from config import settings


_local_counters: Dict[str, Tuple[int, float]] = {}
_local_lock = asyncio.Lock()


def _client_identifier(request: Request) -> str:
    if request.client and request.client.host:
        return request.client.host
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return "unknown"


async def _consume_local_quota(key: str, limit: int, window_seconds: int) -> bool:
    now = time.time()
    async with _local_lock:
        count, reset_at = _local_counters.get(key, (0, now + window_seconds))
        if now >= reset_at:
            count = 0
            reset_at = now + window_seconds
        count += 1
        _local_counters[key] = (count, reset_at)
        return count <= limit


def rate_limit(prefix: str, limit: int, window_seconds: int) -> Callable[[], None]:
    """Return a FastAPI dependency that enforces per-client request quotas."""

    async def _dependency(request: Request):
        if getattr(request.app.state, "disable_rate_limits", False):
            return

        client_id = _client_identifier(request)
        key = f"spc:rate:{prefix}:{client_id}"

        try:
            redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
            try:
                current = await redis_client.incr(key)
                if current == 1:
                    await redis_client.expire(key, window_seconds)
            finally:
                await redis_client.aclose()
            allowed = current <= limit
        except Exception:
            allowed = await _consume_local_quota(key, limit, window_seconds)

        if not allowed:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded for {prefix}. Try again later.",
            )

    return _dependency
