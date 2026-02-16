"""Session token helpers for backend-authenticated user scope."""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from jose import JWTError, jwt

from config import settings


SESSION_TOKEN_TYPE = "spc_session"


def create_session_token(
    user_id: str,
    email: Optional[str] = None,
    expires_hours: Optional[int] = None,
) -> Dict[str, Any]:
    """Create a signed session token payload for API authentication."""
    now = datetime.now(timezone.utc)
    ttl_hours = int(expires_hours or settings.JWT_EXPIRATION_HOURS or 24)
    expires_at = now + timedelta(hours=max(ttl_hours, 1))
    claims: Dict[str, Any] = {
        "sub": user_id,
        "type": SESSION_TOKEN_TYPE,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    if email:
        claims["email"] = email

    token = jwt.encode(claims, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return {
        "token": token,
        "expires_at": int(expires_at.timestamp()),
    }


def decode_session_token(token: str) -> Dict[str, Any]:
    """Decode and validate a signed session token."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except JWTError as exc:
        raise ValueError("Invalid or expired session token.") from exc

    token_type = str(payload.get("type", "")).strip()
    if token_type != SESSION_TOKEN_TYPE:
        raise ValueError("Invalid session token type.")

    subject = str(payload.get("sub", "")).strip()
    if not subject:
        raise ValueError("Session token missing subject.")

    return payload
