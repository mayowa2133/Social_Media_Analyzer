"""Connector provider contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Literal, Optional


PlatformKey = Literal["instagram", "tiktok"]


class ConnectorUnavailableError(RuntimeError):
    """Raised when OAuth connector is not configured or disabled."""


@dataclass(frozen=True)
class ConnectorStartResult:
    platform: PlatformKey
    connect_url: str
    state: str
    provider: str


@dataclass(frozen=True)
class ConnectorCallbackPayload:
    platform: PlatformKey
    code: str
    state: str
    user_id: Optional[str]
    email: str
    name: Optional[str]
    picture: Optional[str]
    redirect_uri: Optional[str]


@dataclass(frozen=True)
class ConnectorProfile:
    platform_user_id: str
    handle: str
    display_name: str
    follower_count: int
    profile_picture_url: Optional[str]
    access_token: str
    refresh_token: Optional[str]
    expires_at: Optional[int]
    scope: Optional[str]
    provider: str
    metadata: Dict[str, Any]

