"""Connector provider abstraction with feature-flagged stubs."""

from __future__ import annotations

import secrets
from abc import ABC, abstractmethod
from typing import Dict
from urllib.parse import quote_plus

from config import settings
from services.connectors.types import (
    ConnectorCallbackPayload,
    ConnectorProfile,
    ConnectorStartResult,
    ConnectorUnavailableError,
    PlatformKey,
)


class BaseConnectorProvider(ABC):
    platform: PlatformKey
    provider_name: str
    enabled: bool

    @abstractmethod
    def start(self, *, user_id: str) -> ConnectorStartResult:
        raise NotImplementedError

    @abstractmethod
    def callback(self, payload: ConnectorCallbackPayload) -> ConnectorProfile:
        raise NotImplementedError


class StubOAuthConnectorProvider(BaseConnectorProvider):
    """Feature-flag-ready provider that fails deterministically until configured."""

    def __init__(
        self,
        *,
        platform: PlatformKey,
        provider_name: str,
        enabled: bool,
        setup_url: str,
    ) -> None:
        self.platform = platform
        self.provider_name = provider_name
        self.enabled = enabled
        self.setup_url = setup_url

    def _setup_error(self) -> ConnectorUnavailableError:
        platform_title = self.platform.capitalize()
        message = (
            f"{platform_title} OAuth connector is not configured. "
            f"Enable provider settings and flags, then retry. Setup guide: {self.setup_url} "
            "You can continue with manual /auth/sync/social."
        )
        return ConnectorUnavailableError(message)

    def start(self, *, user_id: str) -> ConnectorStartResult:
        if not self.enabled:
            raise self._setup_error()
        state = secrets.token_urlsafe(24)
        connect_url = (
            f"/auth/connect/{self.platform}/callback?"
            f"state={quote_plus(state)}&code=stub_code&user_id={quote_plus(user_id)}"
        )
        return ConnectorStartResult(
            platform=self.platform,
            connect_url=connect_url,
            state=state,
            provider=self.provider_name,
        )

    def callback(self, payload: ConnectorCallbackPayload) -> ConnectorProfile:
        if not self.enabled:
            raise self._setup_error()
        handle_seed = payload.user_id or payload.email.split("@", 1)[0]
        normalized_handle = str(handle_seed or "creator").strip().lower().replace(" ", "_")
        handle = f"@{normalized_handle}"
        return ConnectorProfile(
            platform_user_id=f"{self.platform}:{normalized_handle}",
            handle=handle,
            display_name=payload.name or handle,
            follower_count=0,
            profile_picture_url=payload.picture,
            access_token=f"oauth_stub:{self.platform}:{payload.code}",
            refresh_token=None,
            expires_at=None,
            scope="basic",
            provider=self.provider_name,
            metadata={"connector_mode": "oauth_stub", "state": payload.state},
        )


def connector_capabilities() -> Dict[str, bool]:
    return {
        "instagram_oauth_available": bool(settings.ENABLE_INSTAGRAM_CONNECTORS),
        "tiktok_oauth_available": bool(settings.ENABLE_TIKTOK_CONNECTORS),
    }


def get_connector_provider(platform: PlatformKey) -> BaseConnectorProvider:
    if platform == "instagram":
        return StubOAuthConnectorProvider(
            platform="instagram",
            provider_name="instagram_stub_oauth",
            enabled=bool(settings.ENABLE_INSTAGRAM_CONNECTORS),
            setup_url="https://developers.facebook.com/docs/instagram-platform/",
        )
    return StubOAuthConnectorProvider(
        platform="tiktok",
        provider_name="tiktok_stub_oauth",
        enabled=bool(settings.ENABLE_TIKTOK_CONNECTORS),
        setup_url="https://developers.tiktok.com/doc/login-kit-web/",
    )

