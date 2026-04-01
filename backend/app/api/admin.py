"""
admin.py - User Management API router for AI-Music.

Routes registered under the ``/api/admin`` prefix:

    GET    /api/admin/users          — list all users
    POST   /api/admin/users          — create a user
    PUT    /api/admin/users/<id>     — update a user
    DELETE /api/admin/users/<id>     — delete a user

All routes require ``superadmin`` or ``admin`` role.
The superadmin account (role='superadmin') cannot be deleted and its role
cannot be changed via the API.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..core.roles import require_roles
from ..models.user import ASSIGNABLE_ROLES, User

router = APIRouter(prefix="/api/admin", tags=["admin"])

_admin_dep = Depends(require_roles("superadmin", "admin"))


class CreateUserBody(BaseModel):
    """Request body for POST /api/admin/users."""

    username: str
    password: str
    role: str = "user"


class UpdateUserBody(BaseModel):
    """Request body for PUT /api/admin/users/:id."""

    username: str | None = None
    password: str | None = None
    role: str | None = None
    is_active: bool | None = None


# ── Routes ─────────────────────────────────────────────────────────────────────


@router.get("/users")
def list_users(current_user: User = _admin_dep) -> dict:
    """Return a list of all user accounts.

    Args:
        current_user: Resolved by the admin role dependency.

    Returns:
        JSON with ``users`` array of user dicts.
    """
    users = User.list_all()
    return {"users": [u.to_dict() for u in users]}


@router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(body: CreateUserBody, current_user: User = _admin_dep) -> dict:
    """Create a new user account.

    Args:
        body: JSON body with ``username``, ``password``, and optional ``role``.
        current_user: Resolved by the admin role dependency.

    Returns:
        ``{"success": true, "user": dict}`` with HTTP 201 on success.

    Raises:
        HTTPException: 400 for validation errors, 409 for duplicate username.
    """
    username = body.username.strip()
    password = body.password
    role = body.role.strip()

    if not username or not password:
        raise HTTPException(400, "Username and password are required.")
    if len(password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters.")
    if role not in ASSIGNABLE_ROLES:
        raise HTTPException(400, f"Invalid role. Must be one of: {', '.join(ASSIGNABLE_ROLES)}.")

    try:
        user = User.create(username, password, role=role)
        return {"success": True, "user": user.to_dict()}
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@router.put("/users/{user_id}")
def update_user(user_id: int, body: UpdateUserBody, current_user: User = _admin_dep) -> dict:
    """Update a user account.

    Args:
        user_id: Primary key of the user to update.
        body: JSON body with optional ``username``, ``password``, ``role``, ``is_active``.
        current_user: Resolved by the admin role dependency.

    Returns:
        ``{"success": true, "user": dict}`` on success.

    Raises:
        HTTPException: 403 for permission violations, 404 if not found, 400 for invalid data.
    """
    target = User.get_by_id(user_id)
    if not target:
        raise HTTPException(404, "User not found.")

    # Only superadmin may modify the superadmin account.
    if target.role == "superadmin" and current_user.role != "superadmin":
        raise HTTPException(403, "Only superadmin can modify the superadmin account.")

    # Superadmin role is immutable via the API.
    if target.role == "superadmin" and body.role is not None and body.role != "superadmin":
        raise HTTPException(403, "The superadmin role cannot be changed.")

    # Prevent escalation to superadmin.
    if body.role == "superadmin" and target.role != "superadmin":
        raise HTTPException(403, "Cannot assign the superadmin role.")

    if body.role is not None and body.role not in ASSIGNABLE_ROLES:
        raise HTTPException(400, f"Invalid role. Must be one of: {', '.join(ASSIGNABLE_ROLES)}.")

    try:
        target.update(
            username=body.username,
            password=body.password,
            role=body.role if target.role != "superadmin" else None,
            is_active=body.is_active,
        )
        return {"success": True, "user": target.to_dict()}
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.delete("/users/{user_id}")
def delete_user(user_id: int, current_user: User = _admin_dep) -> dict:
    """Delete a user account.

    The superadmin account and the caller's own account cannot be deleted.

    Args:
        user_id: Primary key of the user to delete.
        current_user: Resolved by the admin role dependency.

    Returns:
        ``{"success": true}`` on success.

    Raises:
        HTTPException: 403 for protected accounts, 404 if not found.
    """
    target = User.get_by_id(user_id)
    if not target:
        raise HTTPException(404, "User not found.")

    if target.role == "superadmin":
        raise HTTPException(403, "The superadmin account cannot be deleted.")

    if target.id == current_user.id:
        raise HTTPException(403, "You cannot delete your own account.")

    target.delete()
    return {"success": True}
