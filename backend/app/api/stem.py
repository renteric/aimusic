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
    POST /api/stem/bounce                     — mix stems at given volumes → new MP3
"""

import io
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

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


# ── Bounce / export ───────────────────────────────────────────────────────────


class BounceBody(BaseModel):
    """Request body for POST /api/stem/bounce."""

    folder: str
    """Stem library folder name (inside ``media/stems/``)."""

    volumes: dict[str, float]
    """Mapping of stem filename (e.g. ``vocals.mp3``) to linear volume 0.0–1.0.
    Omit a stem or set its volume to 0.0 to exclude it from the mix."""

    output_name: str = ""
    """Optional output filename (without extension).  Defaults to
    ``<folder>_bounce``."""

    format: str = "mp3"
    """Output audio format: ``mp3``, ``flac``, ``wav``, ``ogg``, or ``opus``."""

    bitrate: str = "320k"
    """Bitrate for lossy formats (e.g. ``"192k"``, ``"320k"``).
    Ignored for lossless formats (``flac``, ``wav``)."""


@router.post("/bounce")
async def bounce_stems(
    body: BounceBody,
    current_user: User = _admin_dep,
) -> dict:
    """Mix stem files at the given volumes and export a new MP3.

    Uses ``ffmpeg``'s ``amix`` + ``volume`` filters to blend each stem at the
    requested level, then writes the result to ``media/`` as a new MP3 file.
    Stems with volume ``0.0`` (or absent from *volumes*) are excluded from the
    mix entirely.

    Args:
        body: JSON body with ``folder``, ``volumes`` mapping, optional
              ``output_name``, and ``bitrate``.
        current_user: Resolved by the admin role dependency.

    Returns:
        ``{"success": True, "path": str, "filename": str}`` where ``path``
        is the rel_path inside MEDIA_DIR for the new file.

    Raises:
        HTTPException: 400 if no active stems, 404 if folder not found,
            500 on ffmpeg failure.
    """
    # Validate folder name — no path traversal.
    if not re.match(r"^[\w\-. ]+$", body.folder):
        raise HTTPException(400, "Invalid folder name.")

    stems_dir = AppConfig.STEMS_DIR
    folder_path = stems_dir / body.folder
    try:
        folder_path.resolve().relative_to(stems_dir.resolve())
    except ValueError:
        raise HTTPException(404, "Folder not found.")

    if not folder_path.is_dir():
        raise HTTPException(404, f"Stem folder '{body.folder}' not found.")

    # Collect stem files that have a non-zero volume.
    audio_extensions = {".mp3", ".wav", ".flac"}
    all_stems = [
        p for p in sorted(folder_path.iterdir())
        if p.is_file() and p.suffix.lower() in audio_extensions
    ]
    if not all_stems:
        raise HTTPException(400, "No audio files found in this stem folder.")

    active: list[tuple[Path, float]] = []
    for stem_path in all_stems:
        vol = body.volumes.get(stem_path.name, 1.0)
        if vol > 0.0:
            active.append((stem_path, min(vol, 2.0)))  # cap at 200 %

    if not active:
        raise HTTPException(400, "All stems are muted — nothing to bounce.")

    # Sanitise output name.
    raw_name = body.output_name.strip() or f"{body.folder}_bounce"
    safe_name = re.sub(r"[^\w\s\-.]", "_", raw_name).strip()
    if not safe_name:
        safe_name = "bounce"

    # Build ffmpeg command.
    # Each active stem gets its own -i input and a volume filter.
    # amix blends them; normalize=0 preserves the individual levels.
    cmd: list[str] = ["ffmpeg", "-y"]
    for stem_path, _ in active:
        cmd += ["-i", str(stem_path)]

    n = len(active)
    if n == 1:
        # Single stem — just apply volume directly, no amix needed.
        stem_path, vol = active[0]
        filter_graph = f"[0:a]volume={vol:.4f}[out]"
        cmd += ["-filter_complex", filter_graph, "-map", "[out]"]
    else:
        # Build: [0:a]volume=V[a0]; [1:a]volume=V[a1]; ... ; [a0][a1]...amix=inputs=N:normalize=0[out]
        vol_filters = ";".join(
            f"[{i}:a]volume={vol:.4f}[a{i}]" for i, (_, vol) in enumerate(active)
        )
        mix_inputs = "".join(f"[a{i}]" for i in range(n))
        filter_graph = f"{vol_filters};{mix_inputs}amix=inputs={n}:normalize=0[out]"
        cmd += ["-filter_complex", filter_graph, "-map", "[out]"]

    _FORMAT_SETTINGS: dict[str, dict] = {
        "mp3":  {"codec": "libmp3lame", "ext": "mp3",  "lossy": True},
        "flac": {"codec": "flac",       "ext": "flac", "lossy": False},
        "wav":  {"codec": "pcm_s16le",  "ext": "wav",  "lossy": False},
        "ogg":  {"codec": "libvorbis",  "ext": "ogg",  "lossy": True},
        "opus": {"codec": "libopus",    "ext": "opus", "lossy": True},
    }
    fmt = body.format.lower() if body.format.lower() in _FORMAT_SETTINGS else "mp3"
    fmt_cfg = _FORMAT_SETTINGS[fmt]

    output_filename = f"{safe_name}.{fmt_cfg['ext']}"
    output_path = AppConfig.MEDIA_DIR / output_filename

    cmd += ["-codec:a", fmt_cfg["codec"]]
    if fmt_cfg["lossy"]:
        bitrate = body.bitrate if re.match(r"^\d+k$", body.bitrate) else "320k"
        cmd += ["-b:a", bitrate]
    cmd.append(str(output_path))

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(500, "ffmpeg timed out during bounce.")
    except FileNotFoundError:
        raise HTTPException(500, "ffmpeg is not installed or not on PATH.")

    if result.returncode != 0:
        raise HTTPException(500, f"ffmpeg error: {result.stderr[-500:]}")

    rel_path = output_path.relative_to(AppConfig.MEDIA_DIR).as_posix()
    return {
        "success": True,
        "path": rel_path,
        "filename": output_filename,
    }
