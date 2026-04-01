"""
stem.py - Stem Extraction proxy router for AI-Music.

Proxies all stem-related API calls to the separator microservice running at
SEPARATOR_URL (default: http://separator:8000). All routes require the
``superadmin`` or ``admin`` role.

Routes registered under the ``/api/stem`` prefix:

    GET  /api/stem/health                     — separator health + device info
    GET  /api/stem/models                     — list Demucs models and stems
    POST /api/stem/separate                   — start a Demucs separation job
    POST /api/stem/lalai/separate             — start a LALAL.AI separation job
    POST /api/stem/audiosep/separate          — start an AudioSep separation job
    GET  /api/stem/jobs/{job_id}              — poll any job
    GET  /api/stem/jobs                       — list all jobs
    GET  /api/stem/download/{job_id}/{stem}   — download one stem file
    GET  /api/stem/download/{job_id}          — download all stems as ZIP
    DELETE /api/stem/jobs/{job_id}            — delete a job and its files
    GET  /api/stem/library                    — list stem output folders
    DELETE /api/stem/library/{folder}         — delete an output folder
"""

import io

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from ..core.config import AppConfig
from ..core.roles import require_roles
from ..models.user import User

router = APIRouter(prefix="/api/stem", tags=["stem"])

_admin_dep = Depends(require_roles("superadmin", "admin"))

# Default timeout for separation jobs (they can run for minutes)
_UPLOAD_TIMEOUT = httpx.Timeout(connect=10.0, read=600.0, write=300.0, pool=10.0)
_DEFAULT_TIMEOUT = httpx.Timeout(30.0)


def _sep_url(path: str) -> str:
    """Build a full separator service URL.

    Args:
        path: Path component to append (must start with ``/``).

    Returns:
        Absolute URL string for the separator microservice.
    """
    return f"{AppConfig.SEPARATOR_URL.rstrip('/')}{path}"


# The separator's TrustedHostMiddleware only allows "localhost". Override the
# Host header on every proxied request so container-to-container calls are accepted.
_PROXY_HEADERS = {"Host": "localhost"}


async def _proxy_json(method: str, path: str, **kwargs) -> dict:
    """Send a JSON request to the separator and return the parsed response.

    Args:
        method: HTTP method (``"GET"``, ``"POST"``, ``"DELETE"``).
        path: Separator API path (e.g. ``"/health"``).
        **kwargs: Extra arguments forwarded to :meth:`httpx.AsyncClient.request`.

    Returns:
        Parsed JSON dict from the separator.

    Raises:
        HTTPException: Mirrors the separator's HTTP error status.
    """
    headers = {**_PROXY_HEADERS, **kwargs.pop("headers", {})}
    async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
        resp = await client.request(method, _sep_url(path), headers=headers, **kwargs)
    if not resp.is_success:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


# ── Health & meta ─────────────────────────────────────────────────────────────


@router.get("/health")
async def stem_health(current_user: User = _admin_dep) -> dict:
    """Return separator health, device info, and feature flags.

    Args:
        current_user: Resolved by the admin role dependency.

    Returns:
        JSON from ``GET /health`` on the separator service.
    """
    return await _proxy_json("GET", "/health")


@router.get("/models")
async def stem_models(current_user: User = _admin_dep) -> dict:
    """List available Demucs models and stem definitions.

    Args:
        current_user: Resolved by the admin role dependency.

    Returns:
        JSON from ``GET /api/models`` on the separator service.
    """
    return await _proxy_json("GET", "/api/models")


# ── Demucs ────────────────────────────────────────────────────────────────────


@router.post("/separate")
async def stem_separate_demucs(
    file: UploadFile = File(...),
    model: str = Query(default="htdemucs"),
    stems: str | None = Query(default=None),
    current_user: User = _admin_dep,
) -> dict:
    """Upload audio and start a Demucs separation job.

    Args:
        file: Audio file upload.
        model: Demucs model name (default ``htdemucs``).
        stems: Comma-separated stem names to extract (default: all).
        current_user: Resolved by the admin role dependency.

    Returns:
        ``{"job_id": str, "status": "queued", "provider": "demucs"}``
    """
    content = await file.read()
    params: dict[str, str] = {"model": model}
    if stems:
        params["stems"] = stems

    async with httpx.AsyncClient(timeout=_UPLOAD_TIMEOUT) as client:
        resp = await client.post(
            _sep_url("/api/separate"),
            files={"file": (file.filename, content, file.content_type or "audio/mpeg")},
            params=params,
            headers=_PROXY_HEADERS,
        )
    if not resp.is_success:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


# ── LALAL.AI ──────────────────────────────────────────────────────────────────


@router.post("/lalai/separate")
async def stem_separate_lalai(
    file: UploadFile = File(...),
    stems: str | None = Query(default=None),
    current_user: User = _admin_dep,
) -> dict:
    """Upload audio and start a LALAL.AI cloud separation job.

    Args:
        file: Audio file upload.
        stems: Comma-separated stem names to extract (default: all).
        current_user: Resolved by the admin role dependency.

    Returns:
        ``{"job_id": str, "status": "queued", "provider": "lalai"}``
    """
    content = await file.read()
    params: dict[str, str] = {}
    if stems:
        params["stems"] = stems

    async with httpx.AsyncClient(timeout=_UPLOAD_TIMEOUT) as client:
        resp = await client.post(
            _sep_url("/api/lalai/separate"),
            files={"file": (file.filename, content, file.content_type or "audio/mpeg")},
            params=params,
            headers=_PROXY_HEADERS,
        )
    if not resp.is_success:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


# ── AudioSep ──────────────────────────────────────────────────────────────────


@router.post("/audiosep/separate")
async def stem_separate_audiosep(
    file: UploadFile = File(...),
    stems: str | None = Query(default=None),
    current_user: User = _admin_dep,
) -> dict:
    """Upload audio and start an AudioSep text-query separation job.

    Args:
        file: Audio file upload.
        stems: Comma-separated stem names (text prompts) to extract.
        current_user: Resolved by the admin role dependency.

    Returns:
        ``{"job_id": str, "status": "queued", "provider": "audiosep"}``
    """
    content = await file.read()
    params: dict[str, str] = {}
    if stems:
        params["stems"] = stems

    async with httpx.AsyncClient(timeout=_UPLOAD_TIMEOUT) as client:
        resp = await client.post(
            _sep_url("/api/audiosep/separate"),
            files={"file": (file.filename, content, file.content_type or "audio/mpeg")},
            params=params,
            headers=_PROXY_HEADERS,
        )
    if not resp.is_success:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


# ── Job management ────────────────────────────────────────────────────────────


@router.get("/jobs")
async def stem_list_jobs(current_user: User = _admin_dep) -> list:
    """List all separation jobs (newest first).

    Args:
        current_user: Resolved by the admin role dependency.

    Returns:
        JSON list from ``GET /api/jobs`` on the separator service.
    """
    return await _proxy_json("GET", "/api/jobs")


@router.get("/jobs/{job_id}")
async def stem_get_job(job_id: str, current_user: User = _admin_dep) -> dict:
    """Poll a separation job for status and results.

    Args:
        job_id: Job UUID returned when the job was started.
        current_user: Resolved by the admin role dependency.

    Returns:
        JSON from ``GET /api/jobs/{job_id}`` on the separator service.
    """
    return await _proxy_json("GET", f"/api/jobs/{job_id}")


@router.delete("/jobs/{job_id}")
async def stem_delete_job(job_id: str, current_user: User = _admin_dep) -> dict:
    """Delete a separation job and its output files.

    Args:
        job_id: Job UUID to delete.
        current_user: Resolved by the admin role dependency.

    Returns:
        ``{"message": str}`` from the separator service.
    """
    return await _proxy_json("DELETE", f"/api/jobs/{job_id}")


# ── Downloads ─────────────────────────────────────────────────────────────────


@router.get("/download/{job_id}/{stem_name}")
async def stem_download_one(
    job_id: str,
    stem_name: str,
    current_user: User = _admin_dep,
) -> StreamingResponse:
    """Download a single stem file from a completed job.

    Args:
        job_id: Job UUID.
        stem_name: Stem identifier (e.g. ``vocals``, ``drums``).
        current_user: Resolved by the admin role dependency.

    Returns:
        Audio file streamed from the separator service.
    """
    async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
        resp = await client.get(_sep_url(f"/api/download/{job_id}/{stem_name}"), headers=_PROXY_HEADERS)
    if not resp.is_success:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)

    media_type = resp.headers.get("content-type", "audio/mpeg")
    cd = resp.headers.get("content-disposition", f'attachment; filename="{stem_name}.mp3"')
    return StreamingResponse(
        io.BytesIO(resp.content),
        media_type=media_type,
        headers={"Content-Disposition": cd},
    )


@router.get("/download/{job_id}")
async def stem_download_all(
    job_id: str,
    current_user: User = _admin_dep,
) -> StreamingResponse:
    """Download all stems for a job as a ZIP archive.

    Args:
        job_id: Job UUID.
        current_user: Resolved by the admin role dependency.

    Returns:
        ZIP file streamed from the separator service.
    """
    async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
        resp = await client.get(_sep_url(f"/api/download/{job_id}"), headers=_PROXY_HEADERS)
    if not resp.is_success:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)

    cd = resp.headers.get("content-disposition", f'attachment; filename="{job_id}_stems.zip"')
    return StreamingResponse(
        io.BytesIO(resp.content),
        media_type="application/zip",
        headers={"Content-Disposition": cd},
    )


# ── Library ───────────────────────────────────────────────────────────────────


@router.get("/library")
async def stem_library(current_user: User = _admin_dep) -> dict:
    """List all stem output folders in media/stems/.

    Reads the STEMS_DIR directly rather than proxying the separator's
    /list route, so the data always reflects the shared volume state.

    Args:
        current_user: Resolved by the admin role dependency.

    Returns:
        ``{"folders": list[dict]}`` where each dict has ``name``,
        ``display_name``, and ``audio_count``.
    """
    stems_dir = AppConfig.STEMS_DIR
    folders: list[dict] = []

    if stems_dir.exists():
        for folder_path in sorted(stems_dir.iterdir()):
            if not folder_path.is_dir():
                continue
            audio_files = (
                list(folder_path.glob("*.mp3"))
                + list(folder_path.glob("*.wav"))
                + list(folder_path.glob("*.flac"))
            )
            folders.append({
                "name": folder_path.name,
                "display_name": folder_path.name.replace("_", " ").title(),
                "audio_count": len(audio_files),
            })

    return {"folders": folders}


@router.get("/library/{folder_name}")
async def stem_library_folder(folder_name: str, current_user: User = _admin_dep) -> dict:
    """List audio files inside a stem output folder.

    Args:
        folder_name: Folder name inside media/stems/.
        current_user: Resolved by the admin role dependency.

    Returns:
        ``{"folder": str, "files": list[dict]}`` where each file dict has
        ``filename``, ``stem_name``, ``rel_path``, and ``size_mb``.

    Raises:
        HTTPException: 404 if the folder does not exist.
    """
    stems_dir = AppConfig.STEMS_DIR
    folder_path = stems_dir / folder_name

    # Path-traversal guard
    try:
        folder_path.resolve().relative_to(stems_dir.resolve())
    except ValueError:
        raise HTTPException(404, "Folder not found.")

    if not folder_path.exists() or not folder_path.is_dir():
        raise HTTPException(404, f"Folder '{folder_name}' not found.")

    audio_files: list[dict] = []
    for fp in sorted(
        list(folder_path.glob("*.mp3"))
        + list(folder_path.glob("*.wav"))
        + list(folder_path.glob("*.flac"))
    ):
        stem_name = fp.stem
        # Strip UUID prefix if present (e.g. "abc123_vocals" → "vocals")
        if "_" in stem_name:
            prefix, _, remainder = stem_name.partition("_")
            if "-" in prefix:
                stem_name = remainder

        rel = fp.relative_to(AppConfig.MEDIA_DIR).as_posix()
        audio_files.append({
            "filename": fp.name,
            "stem_name": stem_name,
            "rel_path": rel,          # usable with /api/media/stream/<rel_path>
            "size_mb": round(fp.stat().st_size / 1_048_576, 1),
        })

    audio_files.sort(key=lambda x: x["stem_name"])
    return {"folder": folder_name, "files": audio_files}


@router.delete("/library/{folder_name}")
async def stem_delete_folder(folder_name: str, current_user: User = _admin_dep) -> dict:
    """Delete a stem output folder from media/stems/.

    Args:
        folder_name: Folder name inside media/stems/ to delete.
        current_user: Resolved by the admin role dependency.

    Returns:
        ``{"message": str}`` on success.

    Raises:
        HTTPException: 404 if folder not found, 500 on deletion error.
    """
    import shutil

    stems_dir = AppConfig.STEMS_DIR
    folder_path = stems_dir / folder_name

    try:
        folder_path.resolve().relative_to(stems_dir.resolve())
    except ValueError:
        raise HTTPException(404, "Folder not found.")

    if not folder_path.exists() or not folder_path.is_dir():
        raise HTTPException(404, f"Folder '{folder_name}' not found.")

    try:
        shutil.rmtree(folder_path)
        return {"message": f"Folder '{folder_name}' deleted."}
    except OSError as exc:
        raise HTTPException(500, f"Failed to delete folder: {exc}")
