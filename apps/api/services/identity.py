"""Shared creator identity normalization helpers."""

from __future__ import annotations

import re
from typing import Any, Set


def normalize_identity_token(value: Any) -> str:
    """Normalize handle/external-id/display-name tokens for matching and dedupe."""
    text = str(value or "").strip().lower()
    if not text:
        return ""

    text = re.sub(r"^https?://", "", text)
    text = text.split("?", 1)[0].split("#", 1)[0].strip("/")
    if "/" in text and ("instagram.com" in text or "tiktok.com" in text or "youtube.com" in text):
        text = text.rsplit("/", 1)[-1]
    if text.startswith("@"):
        text = text[1:]
    text = re.sub(r"[^a-z0-9._-]+", "", text)
    return text


def normalize_handle(value: Any) -> str:
    """Normalize a handle to @prefix format for storage/display."""
    token = normalize_identity_token(value)
    if not token:
        return ""
    return token if token.startswith("@") else f"@{token}"


def identity_variants(*values: Any) -> Set[str]:
    """Return canonical and condensed token variants for robust matching."""
    tokens: Set[str] = set()
    for value in values:
        token = normalize_identity_token(value)
        if not token:
            continue
        tokens.add(token)
        condensed = re.sub(r"[^a-z0-9]+", "", token)
        if condensed:
            tokens.add(condensed)
    return tokens

