"""
docs.py - Docs API router for AI-Music.

Routes registered under the ``/api/docs`` prefix:

    GET  /api/docs/files[/<path>]  — list a docs directory as JSON
    GET  /api/docs/file/<path>     — get a file's raw text content
    GET  /api/docs/search          — full-text + filename search across all docs
    POST /api/docs/files           — create a file or folder
    PUT  /api/docs/file/<path>     — update a file's text content
    POST /api/docs/rename          — rename a file or folder
    POST /api/docs/delete          — delete files/folders (JSON body)
"""

import html
import re
import shutil
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..core.auth import get_current_user
from ..core.config import AppConfig
from ..core.roles import require_roles
from ..models.user import User
from ..utils.files import human_size, safe_docs_path

router = APIRouter(prefix="/api/docs", tags=["docs"])

_TEXT_SUFFIXES = {".md", ".txt", ".rst", ".csv", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg"}
_MAX_RESULTS = 50
_MAX_SNIPPETS_PER_FILE = 3


@router.get("/files")
@router.get("/files/{req_path:path}")
def list_files(
    req_path: str = "",
    current_user: User = Depends(get_current_user),
) -> dict:
    """List the contents of a docs directory.

    Args:
        req_path: Optional sub-path inside the docs directory.
        current_user: Resolved by :func:`get_current_user`.

    Returns:
        JSON with ``entries`` list (sorted folders-first), ``current_path``,
        ``parent_path`` (``null`` at the root), and ``req_path``.

    Raises:
        HTTPException: 404 if the target path does not exist.
    """
    AppConfig.DOCS_DIR.mkdir(parents=True, exist_ok=True)

    target = safe_docs_path(req_path)
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
        rel_child = child.relative_to(AppConfig.DOCS_DIR).as_posix()
        entries.append({
            "name": child.name,
            "rel_path": rel_child,
            "is_dir": is_dir,
            "size": stat.st_size,
            "size_human": human_size(stat.st_size),
            "mtime": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
        })

    entries.sort(key=lambda e: (not e["is_dir"], e["name"].casefold()))
    current = f"docs/{req_path.strip('/')}" if req_path else "docs"
    return {
        "entries": entries,
        "current_path": current,
        "parent_path": parent_path,
        "req_path": req_path,
    }


@router.get("/file/{req_path:path}")
def get_file(
    req_path: str,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Return the raw text content of a docs file.

    Args:
        req_path: Sub-path to the file inside the docs directory.
        current_user: Resolved by :func:`get_current_user`.

    Returns:
        JSON with ``content`` string.

    Raises:
        HTTPException: 404 if the path does not resolve to a file.
    """
    target = safe_docs_path(req_path)
    if not target.exists() or not target.is_file():
        raise HTTPException(404, "File not found.")
    try:
        content = target.read_text(encoding="utf-8")
    except Exception as exc:
        raise HTTPException(500, str(exc))
    return {"content": content}


def _highlight(text: str, query: str, window: int = 180) -> str:
    """HTML-escape a line of text and wrap every query occurrence in ``<mark>``.

    Args:
        text: Raw text line from a document.
        query: The search term to highlight (case-insensitive).
        window: Maximum characters to show; excess is replaced with ``…``.

    Returns:
        HTML-safe string with matches wrapped in ``<mark>…</mark>`` tags.
    """
    text = text.strip()
    if len(text) > window:
        idx = text.lower().find(query.lower())
        start = max(0, idx - window // 3)
        end = min(len(text), start + window)
        text = ("…" if start > 0 else "") + text[start:end] + ("…" if end < len(text) else "")
    safe = html.escape(text)
    return re.sub(f"({re.escape(html.escape(query))})", r"<mark>\1</mark>", safe, flags=re.IGNORECASE)


@router.get("/search")
def search_docs(
    q: str = "",
    current_user: User = Depends(get_current_user),
) -> dict:
    """Search docs by filename and file content.

    Args:
        q: Search term (case-insensitive).
        current_user: Resolved by :func:`get_current_user`.

    Returns:
        JSON ``{"results": list}`` where each result has ``rel_path``,
        ``name``, ``name_match`` (bool), and ``snippets`` (list[str]).
    """
    query = q.strip()
    if not query:
        return {"results": []}

    AppConfig.DOCS_DIR.mkdir(parents=True, exist_ok=True)
    query_lower = query.lower()
    results = []

    for path in sorted(AppConfig.DOCS_DIR.rglob("*")):
        if path.is_dir():
            continue

        rel = path.relative_to(AppConfig.DOCS_DIR).as_posix()
        name_match = query_lower in path.name.lower()
        snippets: list[str] = []

        if path.suffix.lower() in _TEXT_SUFFIXES:
            try:
                for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                    if query_lower in line.lower():
                        snippets.append(_highlight(line, query))
                        if len(snippets) >= _MAX_SNIPPETS_PER_FILE:
                            break
            except Exception:
                pass

        if name_match or snippets:
            results.append({
                "rel_path": rel,
                "name": path.name,
                "name_match": name_match,
                "snippets": snippets,
            })

        if len(results) >= _MAX_RESULTS:
            break

    results.sort(key=lambda r: (not r["name_match"], r["rel_path"]))
    return {"results": results}


class CreateEntryBody(BaseModel):
    """Request body for POST /api/docs/files."""

    path: str
    type: str = "file"
    content: str = ""


@router.post("/files")
def create_entry(
    body: CreateEntryBody,
    current_user: User = Depends(require_roles("superadmin", "admin", "user")),
) -> dict:
    """Create a new file or folder inside the docs directory.

    Args:
        body: JSON body with ``path``, ``type``, and optional ``content``.
        current_user: Resolved by the role dependency.

    Returns:
        ``{"success": bool}``

    Raises:
        HTTPException: 400 if path is missing, 409 if already exists.
    """
    path = body.path.strip()
    if not path:
        raise HTTPException(400, "Path is required.")

    target = safe_docs_path(path)
    if target.exists():
        raise HTTPException(409, "Already exists.")

    try:
        if body.type == "folder":
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body.content, encoding="utf-8")
    except Exception as exc:
        raise HTTPException(500, str(exc))

    return {"success": True}


class UpdateFileBody(BaseModel):
    """Request body for PUT /api/docs/file/:path."""

    content: str = ""


@router.put("/file/{req_path:path}")
def update_file(
    req_path: str,
    body: UpdateFileBody,
    current_user: User = Depends(require_roles("superadmin", "admin", "user")),
) -> dict:
    """Overwrite the content of an existing docs file.

    Args:
        req_path: Sub-path to the file inside the docs directory.
        body: JSON body with ``content``.
        current_user: Resolved by the role dependency.

    Returns:
        ``{"success": bool}``

    Raises:
        HTTPException: 404 if the file does not exist.
    """
    target = safe_docs_path(req_path)
    if not target.exists() or not target.is_file():
        raise HTTPException(404, "File not found.")
    try:
        target.write_text(body.content, encoding="utf-8")
    except Exception as exc:
        raise HTTPException(500, str(exc))
    return {"success": True}


class RenameBody(BaseModel):
    """Request body for POST /api/docs/rename."""

    from_path: str
    to_path: str

    model_config = {"populate_by_name": True}

    # Support both snake_case and the original "from"/"to" key names
    @classmethod
    def model_validate(cls, obj, *args, **kwargs):  # type: ignore[override]
        if isinstance(obj, dict):
            obj = {
                "from_path": obj.get("from") or obj.get("from_path", ""),
                "to_path": obj.get("to") or obj.get("to_path", ""),
            }
        return super().model_validate(obj, *args, **kwargs)


@router.post("/rename")
def rename_entry(
    body: RenameBody,
    current_user: User = Depends(require_roles("superadmin", "admin", "user")),
) -> dict:
    """Rename or move a docs file or folder.

    Args:
        body: JSON body with ``from`` and ``to`` paths.
        current_user: Resolved by the role dependency.

    Returns:
        ``{"success": bool, "new_path": str}``
    """
    old_path = body.from_path.strip()
    new_path = body.to_path.strip()

    if not old_path or not new_path:
        raise HTTPException(400, "Both 'from' and 'to' are required.")

    old_target = safe_docs_path(old_path)
    new_target = safe_docs_path(new_path)

    if not old_target.exists():
        raise HTTPException(404, "Source not found.")
    if new_target.exists():
        raise HTTPException(409, "Destination already exists.")

    try:
        new_target.parent.mkdir(parents=True, exist_ok=True)
        old_target.rename(new_target)
    except Exception as exc:
        raise HTTPException(500, str(exc))

    return {"success": True, "new_path": new_path}


class DeleteBody(BaseModel):
    """Request body for POST /api/docs/delete."""

    paths: list[str]


@router.post("/delete")
def delete_files(
    body: DeleteBody,
    current_user: User = Depends(require_roles("superadmin", "admin", "user")),
) -> dict:
    """Delete one or more docs files or directories.

    Args:
        body: JSON body with ``paths`` list.
        current_user: Resolved by the role dependency.

    Returns:
        ``{"deleted": list[str], "errors": list[str]}``
    """
    deleted: list[str] = []
    errors: list[str] = []

    for p in body.paths:
        try:
            target = safe_docs_path(p)
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
