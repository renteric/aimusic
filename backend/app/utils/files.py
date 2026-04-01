"""
files.py - File-system helpers for AI-Music.

Provides path-safety validation and human-readable size formatting used by
the media and docs API routes. Uses FastAPI HTTPException instead of Flask abort.
"""

from pathlib import Path

from fastapi import HTTPException, status

from ..core.config import AppConfig


def safe_media_path(req_path: str) -> Path:
    """Resolve a user-supplied sub-path safely within MEDIA_DIR.

    Prevents path-traversal attacks by ensuring the resolved candidate path
    always lives inside :attr:`~app.core.config.AppConfig.MEDIA_DIR`.

    Args:
        req_path: Raw sub-path string from a URL segment (may include slashes).

    Returns:
        Resolved absolute :class:`~pathlib.Path` guaranteed to be inside MEDIA_DIR.

    Raises:
        HTTPException: 404 if the resolved path escapes MEDIA_DIR.
    """
    rel = (req_path or "").lstrip("/")
    candidate = (AppConfig.MEDIA_DIR / rel).resolve()
    media_root = AppConfig.MEDIA_DIR.resolve()

    if media_root != candidate and media_root not in candidate.parents:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Path not found.")

    return candidate


def safe_docs_path(req_path: str) -> Path:
    """Resolve a user-supplied sub-path safely within DOCS_DIR.

    Prevents path-traversal attacks by ensuring the resolved candidate path
    always lives inside :attr:`~app.core.config.AppConfig.DOCS_DIR`.

    Args:
        req_path: Raw sub-path string from a URL segment (may include slashes).

    Returns:
        Resolved absolute :class:`~pathlib.Path` guaranteed to be inside DOCS_DIR.

    Raises:
        HTTPException: 404 if the resolved path escapes DOCS_DIR.
    """
    rel = (req_path or "").lstrip("/")
    candidate = (AppConfig.DOCS_DIR / rel).resolve()
    docs_root = AppConfig.DOCS_DIR.resolve()

    if docs_root != candidate and docs_root not in candidate.parents:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Path not found.")

    return candidate


def human_size(num_bytes: int) -> str:
    """Convert a byte count to a human-readable string (e.g. ``"4.2 MB"``).

    Args:
        num_bytes: File size in bytes.

    Returns:
        Formatted string with the appropriate unit suffix.
    """
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    size = float(num_bytes)
    for unit in units:
        if size < 1024.0 or unit == units[-1]:
            return f"{int(size)} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{num_bytes} B"
