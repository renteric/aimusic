"""
user.py - SQLite-backed User model for AI-Music.

Provides database initialisation, connection management, and a User class.
No ORM is used — raw sqlite3 keeps the dependency surface minimal and the
schema trivially auditable. Flask-Login interface removed; authentication
is now handled via JWT cookies in core/auth.py.
"""

import os
import sqlite3
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash

from ..core.config import AppConfig

#: All valid role names.
VALID_ROLES: tuple[str, ...] = ("superadmin", "admin", "user", "viewer")

#: Roles that may be assigned via the admin API (superadmin is set only at bootstrap).
ASSIGNABLE_ROLES: tuple[str, ...] = ("admin", "user", "viewer")


# ── Database helpers ───────────────────────────────────────────────────────────


def get_connection() -> sqlite3.Connection:
    """Open a new SQLite connection to the application database.

    Reads ``DB_PATH`` from the environment at call time so that test code
    can override the path via ``os.environ`` after the module is imported.
    Creates the database file and its parent directory if they do not yet
    exist. Row factory is set to :class:`sqlite3.Row` for attribute-style
    column access. WAL mode and foreign-key enforcement are enabled per
    connection.

    Returns:
        Open :class:`sqlite3.Connection` ready for use.
    """
    _db_env = os.getenv("DB_PATH", "data/app.db")
    db_file = Path(_db_env) if Path(_db_env).is_absolute() else AppConfig.BASE_DIR / _db_env
    db_file.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_file), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db() -> None:
    """Create the database schema if it does not already exist.

    Safe to call on every startup — all DDL uses ``IF NOT EXISTS``.
    Applies an inline migration to add the ``role`` column to pre-existing
    installations.
    """
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT    UNIQUE NOT NULL COLLATE NOCASE,
                password_hash TEXT    NOT NULL,
                role          TEXT    NOT NULL DEFAULT 'user',
                is_active     INTEGER NOT NULL DEFAULT 1,
                created_at    DATETIME DEFAULT (datetime('now'))
            )
        """)
        # Migration: add role column to pre-existing tables that lack it.
        existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
        if "role" not in existing_cols:
            conn.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")
        conn.commit()


# ── User model ─────────────────────────────────────────────────────────────────


class User:
    """Lightweight user object for AI-Music.

    Wraps a :class:`sqlite3.Row` from the ``users`` table. Authentication
    state is managed via JWT cookies — this class carries no session state.

    Attributes:
        id: Integer primary key.
        username: Unique login name (case-insensitive in the database).
        password_hash: Werkzeug-hashed password.
        role: One of ``superadmin``, ``admin``, ``user``, ``viewer``.
        is_active: Whether the account is enabled.
        created_at: ISO datetime string of account creation.
    """

    def __init__(self, row: sqlite3.Row) -> None:
        """Construct a User from a database row.

        Args:
            row: A :class:`sqlite3.Row` from the ``users`` table.
        """
        self.id: int = row["id"]
        self.username: str = row["username"]
        self.password_hash: str = row["password_hash"]
        self.role: str = row["role"] if "role" in row.keys() else "user"
        self.is_active: bool = bool(row["is_active"])
        self.created_at: str = row["created_at"] or ""

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """Serialise the user to a JSON-safe dictionary.

        Returns:
            Dict with ``id``, ``username``, ``role``, ``is_active``, and ``created_at``.
        """
        return {
            "id": self.id,
            "username": self.username,
            "role": self.role,
            "is_active": self.is_active,
            "created_at": self.created_at,
        }

    # ── Password helpers ───────────────────────────────────────────────────────

    def check_password(self, password: str) -> bool:
        """Verify a plain-text password against the stored hash.

        Args:
            password: Plain-text candidate password.

        Returns:
            True if the password matches, False otherwise.
        """
        return check_password_hash(self.password_hash, password)

    def set_password(self, new_password: str) -> None:
        """Hash and persist a new password for this user.

        Args:
            new_password: Plain-text replacement password.
        """
        new_hash = generate_password_hash(new_password)
        with get_connection() as conn:
            conn.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (new_hash, self.id),
            )
            conn.commit()
        self.password_hash = new_hash

    # ── Instance mutations ─────────────────────────────────────────────────────

    def update(
        self,
        username: str | None = None,
        password: str | None = None,
        role: str | None = None,
        is_active: bool | None = None,
    ) -> None:
        """Update one or more fields for this user.

        Args:
            username: New login name (1–64 characters), or None to leave unchanged.
            password: New plain-text password (min 8 chars), or None to leave unchanged.
            role: New role (must be in :data:`VALID_ROLES`), or None to leave unchanged.
            is_active: New active flag, or None to leave unchanged.

        Raises:
            ValueError: If a field value is invalid or the username is taken.
        """
        updates: dict[str, object] = {}

        if username is not None:
            username = username.strip()
            if not username or len(username) > 64:
                raise ValueError("Username must be 1–64 characters.")
            updates["username"] = username

        if password is not None:
            if len(password) < 8:
                raise ValueError("Password must be at least 8 characters.")
            updates["password_hash"] = generate_password_hash(password)

        if role is not None:
            if role not in VALID_ROLES:
                raise ValueError(f"Invalid role '{role}'. Must be one of: {', '.join(VALID_ROLES)}.")
            updates["role"] = role

        if is_active is not None:
            updates["is_active"] = int(is_active)

        if not updates:
            return

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [self.id]
        try:
            with get_connection() as conn:
                conn.execute(f"UPDATE users SET {set_clause} WHERE id = ?", values)
                conn.commit()
        except sqlite3.IntegrityError:
            raise ValueError(f"Username '{username}' is already taken.")

        # Sync in-memory attributes.
        for k, v in updates.items():
            if k == "is_active":
                self.is_active = bool(v)
            elif k == "password_hash":
                self.password_hash = str(v)
            elif k == "username":
                self.username = str(v)
            elif k == "role":
                self.role = str(v)

    def delete(self) -> None:
        """Permanently delete this user from the database."""
        with get_connection() as conn:
            conn.execute("DELETE FROM users WHERE id = ?", (self.id,))
            conn.commit()

    # ── Class-level queries ────────────────────────────────────────────────────

    @classmethod
    def get_by_id(cls, user_id: int) -> "User | None":
        """Fetch a user by primary key.

        Args:
            user_id: Integer primary key.

        Returns:
            :class:`User` if found, otherwise ``None``.
        """
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return cls(row) if row else None

    @classmethod
    def get_by_username(cls, username: str) -> "User | None":
        """Fetch a user by username (case-insensitive).

        Args:
            username: Login name to look up.

        Returns:
            :class:`User` if found, otherwise ``None``.
        """
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE username = ? COLLATE NOCASE",
                (username,),
            ).fetchone()
        return cls(row) if row else None

    @classmethod
    def list_all(cls) -> list["User"]:
        """Return all users ordered by primary key.

        Returns:
            List of :class:`User` instances.
        """
        with get_connection() as conn:
            rows = conn.execute("SELECT * FROM users ORDER BY id").fetchall()
        return [cls(row) for row in rows]

    @classmethod
    def create(cls, username: str, password: str, role: str = "user") -> "User":
        """Insert a new user and return the created instance.

        Args:
            username: Unique login name (1–64 characters).
            password: Plain-text password (hashed before storage).
            role: Initial role (default ``'user'``).

        Returns:
            The newly created :class:`User`.

        Raises:
            ValueError: If the username is already taken, invalid, or the role is unknown.
        """
        username = username.strip()
        if not username or len(username) > 64:
            raise ValueError("Username must be 1–64 characters.")
        if role not in VALID_ROLES:
            raise ValueError(f"Invalid role '{role}'.")
        pw_hash = generate_password_hash(password)
        try:
            with get_connection() as conn:
                conn.execute(
                    "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                    (username, pw_hash, role),
                )
                conn.commit()
        except sqlite3.IntegrityError:
            raise ValueError(f"Username '{username}' is already taken.")
        return cls.get_by_username(username)  # type: ignore[return-value]

    @classmethod
    def count(cls) -> int:
        """Return the total number of user records.

        Returns:
            Integer row count from the ``users`` table.
        """
        with get_connection() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()
        return row["n"] if row else 0

    @classmethod
    def ensure_superadmin(cls) -> None:
        """Promote the lowest-id user to superadmin if no superadmin exists.

        Called on startup for existing installs that pre-date the role system.
        """
        with get_connection() as conn:
            row = conn.execute("SELECT id FROM users WHERE role = 'superadmin'").fetchone()
            if row:
                return
            conn.execute(
                "UPDATE users SET role = 'superadmin' WHERE id = (SELECT MIN(id) FROM users)"
            )
            conn.commit()
