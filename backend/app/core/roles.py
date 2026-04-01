"""
roles.py - Role-based access control helpers for AI-Music.

Provides :func:`require_roles`, a factory that returns a FastAPI Dependency
restricting routes to users whose role is in a specified set.

Usage::

    @router.get("/admin/users")
    def list_users(current_user: User = Depends(require_roles("superadmin", "admin"))):
        ...
"""

from collections.abc import Callable

from fastapi import Depends, HTTPException, status

from .auth import get_current_user
from ..models.user import User


def require_roles(*roles: str) -> Callable:
    """Return a FastAPI dependency that requires the current user to have one of *roles*.

    The returned dependency first resolves authentication via
    :func:`~app.core.auth.get_current_user`, then checks that
    ``user.role`` is in the allowed set.

    Args:
        *roles: One or more role names permitted to call the endpoint
                (e.g. ``"superadmin"``, ``"admin"``).

    Returns:
        A FastAPI dependency callable that yields the authenticated
        :class:`~app.models.user.User` or raises HTTP 403.

    Raises:
        HTTPException: 403 when the user's role is not in *roles*.
    """
    def dependency(current_user: User = Depends(get_current_user)) -> User:
        """Inner dependency — check role and return user.

        Args:
            current_user: Resolved by :func:`get_current_user`.

        Returns:
            The authenticated user if their role is permitted.

        Raises:
            HTTPException: 403 if the role is not in the allowed set.
        """
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions.",
            )
        return current_user

    return dependency
