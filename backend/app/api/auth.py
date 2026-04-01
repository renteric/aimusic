"""
auth.py - Authentication API router for AI-Music.

Routes registered under the ``/api/auth`` prefix:

    POST /api/auth/login            — validate credentials, issue JWT cookie
    POST /api/auth/logout           — clear the JWT cookie
    GET  /api/auth/me               — return current user info (always 200)
    POST /api/auth/change-password  — update the logged-in user's password

All responses are JSON. Authentication uses HttpOnly JWT cookies issued by
:mod:`app.core.auth`. State-changing endpoints accept JSON bodies only.
"""

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

from ..core.auth import clear_auth_cookie, create_access_token, get_current_user, get_optional_user
from ..models.user import User

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginBody(BaseModel):
    """Request body for POST /api/auth/login."""

    username: str
    password: str


class ChangePasswordBody(BaseModel):
    """Request body for POST /api/auth/change-password."""

    current_password: str
    new_password: str


# ── Routes ─────────────────────────────────────────────────────────────────────


@router.post("/login")
def login(body: LoginBody, response: Response) -> dict:
    """Authenticate a user and set a JWT access-token cookie.

    Args:
        body: JSON body with ``username`` and ``password``.
        response: FastAPI response object used to set the cookie.

    Returns:
        ``{"success": true, "username": str, "role": str}`` on success, or
        ``{"success": false, "error": str}`` with HTTP 400 / 401 / 403.
    """
    from fastapi import HTTPException

    username = body.username.strip()
    password = body.password

    if not username or not password:
        raise HTTPException(400, "Username and password are required.")

    user = User.get_by_username(username)
    if user is None or not user.check_password(password):
        raise HTTPException(401, "Invalid username or password.")

    if not user.is_active:
        raise HTTPException(403, "This account has been disabled.")

    token = create_access_token(user)
    from ..core.auth import set_auth_cookie
    set_auth_cookie(response, token)

    return {"success": True, "username": user.username, "role": user.role}


@router.post("/logout")
def logout(
    response: Response,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Clear the JWT access-token cookie.

    Args:
        response: FastAPI response object used to delete the cookie.
        current_user: Resolved by :func:`get_current_user`.

    Returns:
        ``{"success": true}``
    """
    clear_auth_cookie(response)
    return {"success": True}


@router.get("/me")
def me(current_user: User | None = Depends(get_optional_user)) -> dict:
    """Return the currently authenticated user's profile.

    Always returns HTTP 200. Callers check the ``authenticated`` field.

    Args:
        current_user: Resolved by :func:`get_optional_user` — may be None.

    Returns:
        ``{"authenticated": true, "username": str, "role": str}`` if logged in,
        or ``{"authenticated": false}`` otherwise.
    """
    if current_user is not None:
        return {
            "authenticated": True,
            "username": current_user.username,
            "role": current_user.role,
        }
    return {"authenticated": False}


@router.post("/change-password")
def change_password(
    body: ChangePasswordBody,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Change the current user's password.

    Args:
        body: JSON body with ``current_password`` and ``new_password``.
        current_user: Resolved by :func:`get_current_user`.

    Returns:
        ``{"success": true}`` on success, or raises HTTP 400 / 403.
    """
    from fastapi import HTTPException

    if current_user.role == "viewer":
        raise HTTPException(403, "Viewers cannot change their password.")

    if len(body.new_password) < 8:
        raise HTTPException(400, "New password must be at least 8 characters.")

    if not current_user.check_password(body.current_password):
        raise HTTPException(403, "Current password is incorrect.")

    current_user.set_password(body.new_password)
    return {"success": True}
