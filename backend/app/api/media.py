"""
media.py - Media files API router for AI-Music.

Routes registered under the ``/api/media`` prefix:

    GET  /api/media/files[/<path>]  — list a media directory as JSON
    GET  /api/media/stream/<path>   — stream an audio file (range requests)
    GET  /api/media/download/<path> — serve a file as an attachment
    POST /api/media/delete          — delete files/folders (JSON body)
    POST /api/media/clean           — run the metadata cleaner (JSON body)
    GET  /api/media/read/<path>     — return raw text of a .md file (JSON)
    POST /api/media/transcribe      — transcribe audio via Whisper (JSON body)
"""

import json
import mimetypes
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..core.auth import get_current_user
from ..core.config import AppConfig
from ..core.roles import require_roles
from ..models.user import User
from ..utils.files import human_size, safe_media_path

router = APIRouter(prefix="/api/media", tags=["media"])

_SERVICES_DIR = Path(__file__).resolve().parent.parent / "services"
_CLEANER_SCRIPT = _SERVICES_DIR / "metadata_cleaner.py"


@router.get("/files")
@router.get("/files/{req_path:path}")
def list_files(
    req_path: str = "",
    current_user: User = Depends(get_current_user),
) -> dict:
    """List the contents of a media directory.

    Args:
        req_path: Optional sub-path inside the media directory.
        current_user: Resolved by :func:`get_current_user`.

    Returns:
        JSON with ``entries`` list (sorted folders-first), ``current_path``,
        and ``parent_path`` (``null`` at the root).

    Raises:
        HTTPException: 404 if the target path does not exist.
    """
    if not AppConfig.MEDIA_DIR.exists():
        return {"entries": [], "current_path": "media", "parent_path": None, "req_path": req_path}

    target = safe_media_path(req_path)
    if not target.exists() or not target.is_dir():
        raise HTTPException(404, "Path not found.")

    rel_parts = [p for p in (req_path or "").split("/") if p]
    parent_path: str | None = None
    if rel_parts:
        parent_path = "/".join(rel_parts[:-1]) if len(rel_parts) > 1 else ""

    entries = []
    for child in target.iterdir():
        stat = child.stat()
        is_dir = child.is_dir()
        rel_child = child.relative_to(AppConfig.MEDIA_DIR).as_posix()
        mime, _ = mimetypes.guess_type(child.name)
        mime = mime or ("directory" if is_dir else "application/octet-stream")

        entries.append({
            "name": child.name,
            "rel_path": rel_child,
            "is_dir": is_dir,
            "size": stat.st_size,
            "size_human": human_size(stat.st_size),
            "mime": mime,
            "mtime": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
        })

    entries.sort(key=lambda e: (not e["is_dir"], e["name"].casefold()))
    current = f"media/{req_path.strip('/')}" if req_path else "media"
    return {
        "entries": entries,
        "current_path": current,
        "parent_path": parent_path,
        "req_path": req_path,
    }


@router.get("/stream/{req_path:path}")
def stream_file(
    req_path: str,
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    """Stream an audio file for in-browser playback with HTTP range support.

    Only serves files with an ``audio/*`` MIME type.

    Args:
        req_path: Sub-path to the audio file inside the media directory.
        current_user: Resolved by :func:`get_current_user`.

    Returns:
        Streaming :class:`FileResponse` with range support.

    Raises:
        HTTPException: 404 if the path is not a valid audio file.
    """
    if not AppConfig.MEDIA_DIR.exists():
        raise HTTPException(404, "Media directory not found.")
    target = safe_media_path(req_path)
    if not target.exists() or not target.is_file():
        raise HTTPException(404, "File not found.")

    mime, _ = mimetypes.guess_type(target.name)
    mime = mime or "application/octet-stream"
    if not mime.startswith("audio/"):
        raise HTTPException(404, "Not an audio file.")

    return FileResponse(path=str(target), media_type=mime)


@router.get("/read/{req_path:path}")
def read_markdown(
    req_path: str,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Return the text content of a Markdown file inside the media directory.

    Only ``.md`` files are served by this endpoint.

    Args:
        req_path: Sub-path to the ``.md`` file inside the media directory.
        current_user: Resolved by :func:`get_current_user`.

    Returns:
        ``{"content": str}`` with the raw Markdown text.

    Raises:
        HTTPException: 404 if the path is not found or is not a ``.md`` file.
    """
    target = safe_media_path(req_path)
    if not target.exists() or not target.is_file():
        raise HTTPException(404, "File not found.")
    if target.suffix.lower() != ".md":
        raise HTTPException(404, "Not a Markdown file.")
    return {"content": target.read_text(encoding="utf-8")}


@router.get("/download/{req_path:path}")
def download_file(
    req_path: str,
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    """Serve a media file as a browser download (attachment).

    Args:
        req_path: Sub-path to the file inside the media directory.
        current_user: Resolved by :func:`get_current_user`.

    Returns:
        :class:`FileResponse` with ``Content-Disposition: attachment``.

    Raises:
        HTTPException: 404 if the path does not resolve to a file.
    """
    if not AppConfig.MEDIA_DIR.exists():
        raise HTTPException(404, "Media directory not found.")
    target = safe_media_path(req_path)
    if not target.exists() or not target.is_file():
        raise HTTPException(404, "File not found.")
    return FileResponse(
        path=str(target),
        filename=target.name,
        media_type="application/octet-stream",
    )


class DeleteBody(BaseModel):
    """Request body for POST /api/media/delete."""

    paths: list[str]


@router.post("/delete")
def delete_files(
    body: DeleteBody,
    current_user: User = Depends(require_roles("superadmin", "admin", "user")),
) -> dict:
    """Delete one or more media files or directories.

    Args:
        body: JSON body with ``paths`` list of sub-paths to delete.
        current_user: Resolved by the role dependency.

    Returns:
        ``{"deleted": list[str], "errors": list[str]}``.
    """
    deleted: list[str] = []
    errors: list[str] = []

    for p in body.paths:
        try:
            target = safe_media_path(p)
            if not target.exists():
                errors.append(f"{p}: not found")
                continue
            shutil.rmtree(target) if target.is_dir() else target.unlink()
            deleted.append(p)
        except HTTPException:
            errors.append(f"{p}: path not allowed")
        except Exception as exc:
            errors.append(f"{p}: {exc}")

    return {"deleted": deleted, "errors": errors}


class CleanBody(BaseModel):
    """Request body for POST /api/media/clean."""

    path: str
    show: bool = False
    clean: bool = False
    backup: bool = False
    recursive: bool = True
    remove_protection: bool = False


@router.post("/clean")
def clean_metadata(
    body: CleanBody,
    current_user: User = Depends(require_roles("superadmin", "admin", "user")),
) -> dict:
    """Run the metadata cleaner on a path inside the media directory.

    Args:
        body: JSON body with ``path`` and optional cleaner flags.
        current_user: Resolved by the role dependency.

    Returns:
        ``{"success": bool, "output": str}``.

    Raises:
        HTTPException: 404 if path not found, 504 on timeout.
    """
    target = safe_media_path(body.path)
    if not target.exists():
        raise HTTPException(404, "Path not found.")

    cmd = [sys.executable, str(_CLEANER_SCRIPT), "-p", str(target)]
    if not body.recursive:
        cmd.append("--no-recursive")
    if body.show:
        cmd.append("--show")
    if body.clean:
        cmd.append("--clean")
    if body.backup:
        cmd.append("--backup")
    if body.remove_protection:
        cmd.append("--remove-protection")

    env = {**os.environ, "PYTHONPATH": str(_SERVICES_DIR)}
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=300, env=env)
        out = result.stdout + ("\n" + result.stderr if result.stderr.strip() else "")
        return {"success": result.returncode == 0, "output": out.strip()}
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "Cleaner timed out after 300 s.")
    except Exception as exc:
        raise HTTPException(500, str(exc))


class TranscribeBody(BaseModel):
    """Request body for POST /api/media/transcribe."""

    path: str
    language: str = "Spanish"
    model: str = "base"


@router.post("/transcribe")
def transcribe_audio(
    body: TranscribeBody,
    current_user: User = Depends(require_roles("superadmin", "admin", "user")),
) -> dict:
    """Transcribe an audio file using the external Whisper service.

    Args:
        body: JSON body with ``path``, optional ``language`` and ``model``.
        current_user: Resolved by the role dependency.

    Returns:
        ``{"success": bool, "output": str}`` forwarded from the transcribe service.

    Raises:
        HTTPException: 404 if file not found, 503 if service unavailable.
    """
    target = safe_media_path(body.path)
    if not target.exists() or not target.is_file():
        raise HTTPException(404, "File not found.")

    payload = json.dumps({
        "path": str(target),
        "language": body.language.strip(),
        "model": body.model.strip(),
    }).encode()
    req = urllib.request.Request(
        f"{AppConfig.TRANSCRIBE_SERVICE_URL}/transcribe",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            return json.loads(resp.read())
    except urllib.error.URLError as exc:
        raise HTTPException(503, f"Transcribe service unavailable: {exc.reason}")
    except Exception as exc:
        raise HTTPException(500, str(exc))
