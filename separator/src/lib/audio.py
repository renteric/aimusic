"""
Shared audio utilities used across all separator backends.

Provides file validation, safe path sanitisation, and byte formatting
helpers so every backend (Demucs, LALAI, AudioSep) behaves consistently.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Audio formats accepted at the API boundary
ALLOWED_EXTENSIONS: frozenset[str] = frozenset(
    {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".wma", ".aiff"}
)


def validate_extension(filename: str) -> str:
    """
    Return the lowercase file extension if it is an allowed audio format.

    Args:
        filename: Original filename from the upload (e.g. "song.mp3").

    Returns:
        Lowercase extension including the dot (e.g. ".mp3").

    Raises:
        ValueError: If the extension is not in ALLOWED_EXTENSIONS.
    """
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f"Unsupported audio format '{suffix}'. "
            f"Allowed: {sorted(ALLOWED_EXTENSIONS)}"
        )
    logger.debug("validate_extension: %s → %s", filename, suffix)
    return suffix


def safe_stem(name: str, fallback: str = "audio") -> str:
    """
    Sanitise a song/file name for use as a directory or file-name component.

    Keeps alphanumerics, spaces, hyphens, underscores, and dots.
    Strips leading/trailing whitespace. Falls back to `fallback` if the
    result would be empty.

    Args:
        name:     Raw name to sanitise (e.g. "Bésame Mucho [live].mp3").
        fallback: Returned when sanitisation produces an empty string.

    Returns:
        A filesystem-safe string.
    """
    sanitised = "".join(c for c in name if c.isalnum() or c in " -_.").strip()
    result = sanitised or fallback
    if result != name:
        logger.debug("safe_stem: %r → %r", name, result)
    return result


def format_bytes(num_bytes: int) -> str:
    """
    Return a human-readable file size string.

    Args:
        num_bytes: Size in bytes.

    Returns:
        Formatted string, e.g. "4.2 MB" or "320 KB".
    """
    if num_bytes < 1_024:
        return f"{num_bytes} B"
    if num_bytes < 1_024 ** 2:
        return f"{num_bytes / 1_024:.1f} KB"
    return f"{num_bytes / 1_024 ** 2:.1f} MB"
