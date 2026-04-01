"""
auth.py - JWT cookie-based authentication helpers for AI-Music.

Uses python-jose to issue and verify HS256 JWT tokens stored as HttpOnly
cookies. Two FastAPI Dependencies are provided:

  get_current_user         — raises HTTP 401 if token is missing or invalid
  get_optional_user        — returns None instead of raising (used by /me)

Token payload: {"sub": str(user_id), "username": str, "role": str, "exp": int}
Cookie name  : access_token (HttpOnly, SameSite=Lax)
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, Request, status
from jose import JWTError, jwt

from .config import AppConfig
from ..models.user import User

_ALGORITHM = "HS256"
_COOKIE_NAME = "access_token"


# ── Token helpers ─────────────────────────────────────────────────────────────


def create_access_token(user: User) -> str:
    """Create a signed JWT for *user*.

    Args:
        user: The authenticated user to embed in the token.

    Returns:
        Encoded JWT string.
    """
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=AppConfig.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload: dict[str, Any] = {
        "sub": str(user.id),
        "username": user.username,
        "role": user.role,
        "exp": expire,
    }
    return jwt.encode(payload, AppConfig.SECRET_KEY, algorithm=_ALGORITHM)


def _decode_token(token: str) -> dict[str, Any] | None:
    """Decode and verify *token*, returning the payload or None on failure.

    Args:
        token: Encoded JWT string from the cookie.

    Returns:
        Decoded payload dict if valid, otherwise ``None``.
    """
    try:
        return jwt.decode(token, AppConfig.SECRET_KEY, algorithms=[_ALGORITHM])
    except JWTError:
        return None


def _user_from_payload(payload: dict[str, Any]) -> User | None:
    """Load and return a User from a decoded JWT payload.

    Args:
        payload: Decoded JWT dict with at least a ``"sub"`` key.

    Returns:
        :class:`~app.models.user.User` if found and active, otherwise ``None``.
    """
    try:
        user_id = int(payload["sub"])
    except (KeyError, ValueError, TypeError):
        return None
    user = User.get_by_id(user_id)
    if user is None or not user.is_active:
        return None
    return user


# ── Cookie helpers ────────────────────────────────────────────────────────────


def set_auth_cookie(response: Any, token: str) -> None:
    """Attach the JWT access-token as an HttpOnly cookie to *response*.

    Args:
        response: FastAPI ``Response`` object to modify.
        token: JWT string to store.
    """
    response.set_cookie(
        key=_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,          # set True behind HTTPS proxy
        max_age=AppConfig.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )


def clear_auth_cookie(response: Any) -> None:
    """Remove the access-token cookie from *response*.

    Args:
        response: FastAPI ``Response`` object to modify.
    """
    response.delete_cookie(key=_COOKIE_NAME, path="/")


# ── FastAPI Dependencies ──────────────────────────────────────────────────────


def get_current_user(request: Request) -> User:
    """FastAPI dependency — return the authenticated user or raise HTTP 401.

    Reads the ``access_token`` cookie, verifies the JWT, and loads the user
    from the database. Raises HTTP 401 if any step fails.

    Args:
        request: Incoming FastAPI request.

    Returns:
        Authenticated and active :class:`~app.models.user.User`.

    Raises:
        HTTPException: 401 if the token is absent, invalid, or the user is
            disabled.
    """
    token: str | None = request.cookies.get(_COOKIE_NAME)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    payload = _decode_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
        )
    user = _user_from_payload(payload)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or account disabled.",
        )
    return user


def get_optional_user(request: Request) -> User | None:
    """FastAPI dependency — return the authenticated user or None (no 401).

    Used by the ``/api/auth/me`` endpoint which should always return 200.

    Args:
        request: Incoming FastAPI request.

    Returns:
        :class:`~app.models.user.User` if authenticated, otherwise ``None``.
    """
    token: str | None = request.cookies.get(_COOKIE_NAME)
    if not token:
        return None
    payload = _decode_token(token)
    if payload is None:
        return None
    return _user_from_payload(payload)
