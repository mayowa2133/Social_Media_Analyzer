"""Authentication dependencies for API user scoping."""

from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from services.session_token import decode_session_token


auth_scheme = HTTPBearer(auto_error=False)


@dataclass
class AuthContext:
    user_id: str
    email: Optional[str] = None


def ensure_user_scope(auth_user_id: str, supplied_user_id: Optional[str]) -> str:
    """Return authenticated user_id and reject cross-user attempts."""
    if supplied_user_id and supplied_user_id != auth_user_id:
        raise HTTPException(status_code=403, detail="user_id does not match authenticated session.")
    return auth_user_id


async def get_auth_context(
    credentials: HTTPAuthorizationCredentials = Depends(auth_scheme),
) -> AuthContext:
    """Resolve authenticated user from Bearer session token."""
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Missing Bearer session token.")

    try:
        payload = decode_session_token(credentials.credentials)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    return AuthContext(
        user_id=str(payload.get("sub", "")),
        email=str(payload.get("email", "")) or None,
    )
