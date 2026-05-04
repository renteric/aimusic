"""FastAPI application for Music Source Separator — API only.

All HTML UI is served by the Vue.js frontend. This service exposes a pure
REST API consumed by the main backend proxy (``/api/stem/*``).

Endpoints
---------
GET  /health                        Service health probe
GET  /api/models                    List available Demucs models and stem groups

POST /api/separate                  Start a Demucs/open-unmix separation job
POST /api/lalai/separate            Start a LALAL.AI cloud separation job
POST /api/audiosep/separate         Start an AudioSep text-query separation job

GET  /api/jobs/{job_id}             Poll a job (status, progress, produced stems)
GET  /api/jobs                      List all jobs, newest first
DELETE /api/jobs/{job_id}           Delete a job and its output files

GET  /api/download/{job_id}/{stem}  Stream a single stem file
GET  /api/download/{job_id}         Download all stems as a ZIP archive

GET  /api/library                   List output folders (song library)
GET  /api/library/{folder}          List stems inside a folder
DELETE /api/folders/{folder_name}   Delete an output folder
"""

import asyncio
import io
import shutil
import sys
import time
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.requests import Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

# ── Project imports ───────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))

from config.settings import (
    AUDIOSEP_STEMS,
    AVAILABLE_MODELS,
    DEFAULT_MODEL,
    LALAI_STEMS,
    STEM_GROUPS,
    settings,
)
from core.audiosep import AudioSepError, AudioSepSeparator
from core.lalai import LalaiError, LalaiSeparator
from core.separator import AudioSeparator, SeparationError, detect_device
from lib.audio import safe_stem, validate_extension
from lib.logging import configure_logging, get_logger

# ── Logging ───────────────────────────────────────────────────────────────────
configure_logging()
logger = get_logger(__name__)

# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="Music Source Separator API",
    description="AI-powered audio stem separation — Demucs · LALAL.AI · AudioSep",
    version="2.0.0",
)

# ── Middleware ────────────────────────────────────────────────────────────────

_cors_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
_allowed_hosts = [h.strip() for h in settings.allowed_hosts.split(",") if h.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
    allow_credentials=True,
    max_age=86400,
)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=_allowed_hosts,
)

app.add_middleware(GZipMiddleware, minimum_size=1000)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach security-related HTTP response headers to every response."""

    async def dispatch(self, request: Request, call_next):
        """Add security headers then forward to the next handler.

        Args:
            request: Incoming HTTP request.
            call_next: Next middleware or route handler.

        Returns:
            Response with security headers applied.
        """
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=()"
        )
        return response


app.add_middleware(SecurityHeadersMiddleware)

# ── Outputs served as static files ───────────────────────────────────────────
# Stem audio files are served directly from the outputs directory so the
# frontend can stream them without going through a Python handler.
from fastapi.staticfiles import StaticFiles  # noqa: E402

if settings.outputs_dir.exists():
    app.mount(
        "/outputs",
        StaticFiles(directory=str(settings.outputs_dir)),
        name="outputs",
    )

# ── Shared state ──────────────────────────────────────────────────────────────
executor = ThreadPoolExecutor(max_workers=2)
device = detect_device()
logger.info("Compute device: %s", device.upper())


# ── Job models ────────────────────────────────────────────────────────────────

class JobStatus(str, Enum):
    """Lifecycle states for a separation job."""

    QUEUED = "queued"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


class Provider(str, Enum):
    """Separation engine / provider identifier."""

    DEMUCS = "demucs"
    LALAI = "lalai"
    AUDIOSEP = "audiosep"


class Job(BaseModel):
    """In-memory representation of a separation job."""

    id: str
    status: JobStatus
    provider: Provider = Provider.DEMUCS
    progress: int = 0
    message: str = ""
    filename: str = ""
    model: str = DEFAULT_MODEL
    stems_requested: List[str] = []
    stems_produced: Dict[str, str] = {}   # stem_name → filename
    error: Optional[str] = None
    created_at: float = 0.0
    finished_at: Optional[float] = None
    duration_s: Optional[float] = None


jobs: Dict[str, Job] = {}


# ── Private helpers ───────────────────────────────────────────────────────────

def _check_size(content: bytes, filename: str) -> None:
    """Raise HTTP 413 if the upload exceeds the configured size limit.

    Args:
        content: Raw file bytes to validate.
        filename: Original filename used in the error message.

    Raises:
        HTTPException: 413 if the file exceeds ``settings.max_upload_size_mb``.
    """
    max_bytes = settings.max_upload_size_mb * 1_048_576
    if len(content) > max_bytes:
        raise HTTPException(
            413,
            f"File '{filename}' too large (max {settings.max_upload_size_mb} MB)",
        )


def _parse_stems(raw: Optional[str], valid: List[str]) -> List[str]:
    """Parse a comma-separated stem query parameter.

    Falls back to all *valid* stems when *raw* is ``None``.

    Args:
        raw: Comma-separated stem names from the query string, or ``None``.
        valid: Complete list of valid stem identifiers for the current context.

    Returns:
        List of validated stem names.

    Raises:
        HTTPException: 400 if any requested stem is not in *valid*.
    """
    if not raw:
        return valid

    requested = [s.strip() for s in raw.split(",") if s.strip()]
    invalid = [s for s in requested if s not in valid]
    if invalid:
        raise HTTPException(
            400, f"Unknown stems: {invalid}. Valid options: {valid}"
        )
    return requested


def _get_done_job(job_id: str) -> Job:
    """Return a completed Job or raise an appropriate HTTP error.

    Args:
        job_id: UUID string identifying the job.

    Returns:
        The completed :class:`Job` instance.

    Raises:
        HTTPException: 404 if the job does not exist.
        HTTPException: 400 if the job is not yet complete.
    """
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, f"Job '{job_id}' not found")
    if job.status != JobStatus.DONE:
        raise HTTPException(400, f"Job is not complete (status: {job.status})")
    return job


def _song_dir(job: Job) -> Path:
    """Return (and create) the song-named output directory for a job.

    The directory name is the sanitised filename stem, e.g.
    ``outputs/Besame_mucho/``.

    Args:
        job: The :class:`Job` whose output directory is required.

    Returns:
        Path to the output directory (created if it does not yet exist).
    """
    name = safe_stem(Path(job.filename).stem, fallback=f"song_{job.id[:8]}")
    path = settings.outputs_dir / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def _save_upload(content: bytes, filename: str) -> tuple[str, Path]:
    """Persist uploaded bytes to the uploads directory.

    Args:
        content: Raw file bytes received from the client.
        filename: Original filename — used to determine the file extension.

    Returns:
        ``(job_id, upload_path)`` tuple where *job_id* is a fresh UUID string
        and *upload_path* is the absolute path to the saved file.
    """
    suffix = validate_extension(filename)
    job_id = str(uuid.uuid4())
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    path = settings.uploads_dir / f"{job_id}{suffix}"
    path.write_bytes(content)
    logger.debug("Saved upload: %s (%d bytes)", path.name, len(content))
    return job_id, path


def _create_job(
    job_id: str,
    filename: str,
    provider: Provider,
    model: str,
    stems: List[str],
) -> Job:
    """Construct and register a new Job in the in-memory store.

    Args:
        job_id: Pre-generated UUID string (from :func:`_save_upload`).
        filename: Original uploaded filename.
        provider: Which separation engine will handle the job.
        model: Model identifier (Demucs model name or ``"lalai"``/``"audiosep"``).
        stems: List of stem names requested by the client.

    Returns:
        The newly registered :class:`Job` instance.
    """
    job = Job(
        id=job_id,
        status=JobStatus.QUEUED,
        provider=provider,
        filename=filename,
        model=model,
        stems_requested=stems,
        created_at=time.time(),
        message="Queued for processing…",
    )
    jobs[job_id] = job
    return job


def _finalise_job(job: Job, result: Dict[str, Path], output_dir: Path) -> None:
    """Move stem files to the song-named directory and mark the job done.

    Args:
        job: The :class:`Job` to finalise.
        result: Mapping of stem name → temporary stem file path.
        output_dir: Temporary per-job directory to clean up after moving files.
    """
    song_dir = _song_dir(job)

    for stem_name, stem_path in result.items():
        dest = song_dir / stem_path.name
        stem_path.rename(dest)
        logger.info("Moved %s → %s", stem_path.name, dest)

    job.stems_produced = {s: p.name for s, p in result.items()}
    job.status = JobStatus.DONE
    job.progress = 100
    job.message = f"{len(result)} stems extracted"
    job.finished_at = time.time()
    job.duration_s = round(job.finished_at - job.created_at, 1)
    logger.info(
        "[%s] Done in %.1fs via %s → %s",
        job.id[:8], job.duration_s, job.provider, list(result.keys()),
    )

    if output_dir.exists():
        shutil.rmtree(output_dir)
        logger.debug("Cleaned up temp dir: %s", output_dir)


def _fail_job(job: Job, error: str, output_dir: Path) -> None:
    """Mark a job failed and clean up the temporary output directory.

    Args:
        job: The :class:`Job` to mark as failed.
        error: Human-readable error description.
        output_dir: Temporary directory to remove.
    """
    job.status = JobStatus.FAILED
    job.error = error
    job.message = f"Failed: {error}"
    logger.error("[%s] Failed: %s", job.id[:8], error)
    if output_dir.exists():
        shutil.rmtree(output_dir)


def _cleanup_upload(path: Path) -> None:
    """Remove the uploaded source file after processing completes.

    Args:
        path: Path to the temporary upload file to delete.
    """
    if path.exists():
        path.unlink(missing_ok=True)
        logger.debug("Removed upload: %s", path.name)


# ── Job runners ───────────────────────────────────────────────────────────────

def _run_demucs(
    job_id: str, audio_path: Path, model: str, stems: Optional[List[str]]
) -> None:
    """Thread-pool worker: separate using local Demucs / open-unmix.

    Args:
        job_id: ID of the registered :class:`Job`.
        audio_path: Path to the uploaded audio file.
        model: Demucs model identifier (e.g. ``"htdemucs_6s"``).
        stems: Specific stems to extract, or ``None`` for all model stems.
    """
    job = jobs[job_id]
    job.status = JobStatus.PROCESSING
    output_dir = settings.outputs_dir / job_id

    try:
        separator = AudioSeparator(
            model=model,
            device=device,
            mp3_output=True,
            mp3_bitrate=settings.mp3_bitrate,
        )

        def _progress(pct: int, msg: str) -> None:
            job.progress = pct
            job.message = msg
            logger.debug("[%s] %d%% — %s", job_id[:8], pct, msg)

        result = separator.separate(
            input_path=audio_path,
            output_dir=output_dir,
            stems=stems,
            progress_callback=_progress,
        )
        _finalise_job(job, result, output_dir)

    except SeparationError as exc:
        _fail_job(job, str(exc), output_dir)
    except Exception as exc:
        _fail_job(job, f"Unexpected error: {exc}", output_dir)
        logger.exception("[%s] Unexpected error in Demucs runner", job_id[:8])
    finally:
        _cleanup_upload(audio_path)


def _run_lalai(job_id: str, audio_path: Path, stems: List[str], output_format: str = "mp3") -> None:
    """Thread-pool worker: separate using the LALAL.AI cloud API.

    Args:
        job_id: ID of the registered :class:`Job`.
        audio_path: Path to the uploaded audio file.
        stems: List of stem names to request from LALAL.AI.
        output_format: Output container — ``"mp3"`` (default) or ``"wav"``.
    """
    job = jobs[job_id]
    job.status = JobStatus.PROCESSING
    output_dir = settings.outputs_dir / job_id

    try:
        separator = LalaiSeparator(api_key=settings.lalalai_api_key)

        def _progress(pct: int, msg: str) -> None:
            job.progress = pct
            job.message = msg
            logger.debug("[%s] %d%% — %s", job_id[:8], pct, msg)

        result = separator.separate(
            input_path=audio_path,
            output_dir=output_dir,
            stems=stems,
            progress_callback=_progress,
            output_format=output_format,
        )
        _finalise_job(job, result, output_dir)

    except LalaiError as exc:
        _fail_job(job, str(exc), output_dir)
    except Exception as exc:
        _fail_job(job, f"Unexpected error: {exc}", output_dir)
        logger.exception("[%s] Unexpected error in LALAI runner", job_id[:8])
    finally:
        _cleanup_upload(audio_path)


def _run_audiosep(
    job_id: str,
    audio_path: Path,
    stems: List[str],
    prompts: Dict[str, str],
    output_format: str = "wav",
    mp3_bitrate: int = 320,
) -> None:
    """Thread-pool worker: separate using local AudioSep model.

    Args:
        job_id: ID of the registered :class:`Job`.
        audio_path: Path to the uploaded audio file.
        stems: List of stem names to extract.
        prompts: Mapping of stem name → text prompt for AudioSep.
        output_format: Output container — ``"wav"``, ``"flac"``, or ``"mp3"``.
        mp3_bitrate: Target MP3 bitrate in kbps (ignored unless output_format is ``"mp3"``).
    """
    job = jobs[job_id]
    job.status = JobStatus.PROCESSING
    output_dir = settings.outputs_dir / job_id

    try:
        separator = AudioSepSeparator(
            model_dir=settings.audiosep_model_dir,
            checkpoint=settings.audiosep_checkpoint,
            device=device,
        )

        def _progress(pct: int, msg: str) -> None:
            job.progress = pct
            job.message = msg
            logger.debug("[%s] %d%% — %s", job_id[:8], pct, msg)

        result = separator.separate(
            input_path=audio_path,
            output_dir=output_dir,
            stems=stems,
            prompts=prompts,
            progress_callback=_progress,
            output_format=output_format,
            mp3_bitrate=mp3_bitrate,
        )
        _finalise_job(job, result, output_dir)

    except AudioSepError as exc:
        _fail_job(job, str(exc), output_dir)
    except Exception as exc:
        _fail_job(job, f"Unexpected error: {exc}", output_dir)
        logger.exception("[%s] Unexpected error in AudioSep runner", job_id[:8])
    finally:
        _cleanup_upload(audio_path)


# ── Health & meta ─────────────────────────────────────────────────────────────

@app.get("/health")
async def health() -> dict:
    """Service health probe.

    Returns:
        JSON with status, compute device, job counts, and feature flags.
    """
    return {
        "status": "ok",
        "device": device,
        "active_jobs": sum(1 for j in jobs.values() if j.status == JobStatus.PROCESSING),
        "total_jobs": len(jobs),
        "audiosep_available": AudioSepSeparator.is_available(),
        "lalai_configured": bool(settings.lalalai_api_key),
    }


@app.get("/api/models")
async def list_models() -> dict:
    """List all Demucs models and stem definitions.

    Returns:
        JSON with available model names, the default model, and the full
        stem group configuration.
    """
    return {
        "models": AVAILABLE_MODELS,
        "default": DEFAULT_MODEL,
        "stems": STEM_GROUPS,
    }


# ── Demucs ────────────────────────────────────────────────────────────────────

@app.post("/api/separate")
async def start_demucs(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    model: str = Query(default=DEFAULT_MODEL),
    stems: Optional[str] = Query(default=None),
) -> dict:
    """Upload an audio file and start a Demucs/open-unmix separation job.

    Args:
        background_tasks: FastAPI background task runner (unused; separation
            runs in the thread-pool executor).
        file: Multipart audio file upload.
        model: Demucs model name (default: ``htdemucs_6s``).
        stems: Optional comma-separated list of stems to extract.

    Returns:
        JSON ``{job_id, status, provider}`` for polling via
        ``GET /api/jobs/{job_id}``.

    Raises:
        HTTPException: 400 for unknown model or unsupported file type.
        HTTPException: 413 if the upload exceeds the size limit.
    """
    if model not in AVAILABLE_MODELS:
        raise HTTPException(
            400, f"Unknown model '{model}'. Options: {list(AVAILABLE_MODELS)}"
        )

    content = await file.read()
    _check_size(content, file.filename or "audio")

    filename = file.filename or "audio.mp3"
    try:
        validate_extension(filename)
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    stem_list: Optional[List[str]] = None
    if stems:
        stem_list = [s.strip() for s in stems.split(",") if s.strip()]
        model_stems = AVAILABLE_MODELS[model]["stems"]
        invalid = [s for s in stem_list if s not in model_stems]
        if invalid:
            raise HTTPException(
                400,
                f"Stems {invalid} not available for model '{model}'. "
                f"Available: {model_stems}",
            )

    job_id, upload_path = _save_upload(content, filename)
    _create_job(
        job_id,
        filename,
        Provider.DEMUCS,
        model,
        stem_list or AVAILABLE_MODELS[model]["stems"],
    )

    loop = asyncio.get_event_loop()
    loop.run_in_executor(executor, _run_demucs, job_id, upload_path, model, stem_list)

    logger.info("[%s] Demucs job queued — file=%s model=%s", job_id[:8], filename, model)
    return {"job_id": job_id, "status": "queued", "provider": "demucs"}


# ── LALAL.AI ──────────────────────────────────────────────────────────────────

_VALID_LALAI_FORMATS = {"mp3", "wav"}


@app.post("/api/lalai/separate")
async def start_lalai(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    stems: Optional[str] = Query(default=None),
    output_format: str = Query(default="mp3"),
) -> dict:
    """Upload an audio file and start a LALAL.AI cloud separation job.

    Args:
        background_tasks: FastAPI background task runner (unused).
        file: Multipart audio file upload.
        stems: Optional comma-separated list of LALAL.AI stem identifiers.
        output_format: Output container — ``"mp3"`` (default) or ``"wav"``.

    Returns:
        JSON ``{job_id, status, provider}`` for polling.

    Raises:
        HTTPException: 400 for unsupported file type, invalid stems, or bad format.
        HTTPException: 413 if the upload exceeds the size limit.
        HTTPException: 503 if ``MUSEP_LALALAI_API_KEY`` is not configured.
    """
    if not settings.lalalai_api_key:
        raise HTTPException(
            503,
            "LALAL.AI is not configured. "
            "Set the MUSEP_LALALAI_API_KEY environment variable.",
        )

    fmt = output_format.lower()
    if fmt not in _VALID_LALAI_FORMATS:
        raise HTTPException(400, f"output_format must be one of: {', '.join(sorted(_VALID_LALAI_FORMATS))}")

    content = await file.read()
    _check_size(content, file.filename or "audio")

    filename = file.filename or "audio.mp3"
    try:
        validate_extension(filename)
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    stem_list = _parse_stems(stems, list(LALAI_STEMS.keys()))

    job_id, upload_path = _save_upload(content, filename)
    _create_job(job_id, filename, Provider.LALAI, "lalai", stem_list)

    loop = asyncio.get_event_loop()
    loop.run_in_executor(executor, _run_lalai, job_id, upload_path, stem_list, fmt)

    logger.info("[%s] LALAI job queued — file=%s stems=%s format=%s", job_id[:8], filename, stem_list, fmt)
    return {"job_id": job_id, "status": "queued", "provider": "lalai"}


# ── AudioSep ──────────────────────────────────────────────────────────────────

_VALID_FORMATS = {"wav", "flac", "mp3"}
_VALID_BITRATES = {128, 192, 256, 320}


@app.post("/api/audiosep/separate")
async def start_audiosep(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    stems: Optional[str] = Query(default=None),
    output_format: str = Query(default="wav"),
    bitrate: int = Query(default=320),
) -> dict:
    """Upload an audio file and start an AudioSep text-query separation job.

    AudioSep must be installed::

        pip install git+https://github.com/Audio-AGI/AudioSep.git

    Args:
        background_tasks: FastAPI background task runner (unused).
        file: Multipart audio file upload.
        stems: Optional comma-separated list of AudioSep stem identifiers.
        output_format: Output container — ``"wav"`` (default), ``"flac"``, or ``"mp3"``.
        bitrate: MP3 bitrate in kbps (128 / 192 / 256 / 320). Ignored for WAV/FLAC.

    Returns:
        JSON ``{job_id, status, provider}`` for polling.

    Raises:
        HTTPException: 400 for unsupported file type, invalid stems, or bad format.
        HTTPException: 413 if the upload exceeds the size limit.
        HTTPException: 503 if AudioSep is not installed.
    """
    if not AudioSepSeparator.is_available():
        raise HTTPException(
            503,
            "AudioSep is not installed. "
            "Run: pip install git+https://github.com/Audio-AGI/AudioSep.git",
        )

    fmt = output_format.lower()
    if fmt not in _VALID_FORMATS:
        raise HTTPException(400, f"output_format must be one of: {', '.join(sorted(_VALID_FORMATS))}")
    if bitrate not in _VALID_BITRATES:
        raise HTTPException(400, f"bitrate must be one of: {', '.join(str(b) for b in sorted(_VALID_BITRATES))}")

    content = await file.read()
    _check_size(content, file.filename or "audio")

    filename = file.filename or "audio.mp3"
    try:
        validate_extension(filename)
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    stem_list = _parse_stems(stems, list(AUDIOSEP_STEMS.keys()))
    prompts = {
        s: AUDIOSEP_STEMS[s]["prompt"]
        for s in stem_list
        if s in AUDIOSEP_STEMS
    }

    job_id, upload_path = _save_upload(content, filename)
    _create_job(job_id, filename, Provider.AUDIOSEP, "audiosep", stem_list)

    loop = asyncio.get_event_loop()
    loop.run_in_executor(executor, _run_audiosep, job_id, upload_path, stem_list, prompts, fmt, bitrate)

    logger.info(
        "[%s] AudioSep job queued — file=%s stems=%s format=%s bitrate=%d",
        job_id[:8], filename, stem_list, fmt, bitrate,
    )
    return {"job_id": job_id, "status": "queued", "provider": "audiosep"}


# ── Job management ────────────────────────────────────────────────────────────

@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str) -> dict:
    """Poll a job for current status and results (all providers).

    Args:
        job_id: UUID identifying the job.

    Returns:
        JSON job detail including status, progress, produced stems, and errors.

    Raises:
        HTTPException: 404 if the job does not exist.
    """
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, f"Job '{job_id}' not found")

    return {
        "job_id": job.id,
        "status": job.status,
        "provider": job.provider,
        "progress": job.progress,
        "message": job.message,
        "filename": job.filename,
        "model": job.model,
        "stems_requested": job.stems_requested,
        "stems_produced": job.stems_produced,
        "error": job.error,
        "duration_s": job.duration_s,
    }


@app.get("/api/jobs")
async def list_jobs() -> list:
    """List all jobs, newest first.

    Returns:
        JSON array of job summaries (id, status, provider, filename, progress,
        stems count).
    """
    return [
        {
            "job_id": j.id,
            "status": j.status,
            "provider": j.provider,
            "filename": j.filename,
            "progress": j.progress,
            "stems_count": len(j.stems_produced),
        }
        for j in sorted(jobs.values(), key=lambda x: x.created_at, reverse=True)
    ]


@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: str) -> dict:
    """Delete a job and clean up its output files.

    Args:
        job_id: UUID identifying the job to delete.

    Returns:
        JSON confirmation message.

    Raises:
        HTTPException: 404 if the job does not exist.
        HTTPException: 400 if the job is still processing.
    """
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job.status == JobStatus.PROCESSING:
        raise HTTPException(400, "Cannot delete a running job")

    if job.status == JobStatus.DONE:
        song_dir = _song_dir(job)
        if song_dir.exists():
            shutil.rmtree(song_dir)
            logger.info("Deleted output dir: %s", song_dir)

    del jobs[job_id]
    return {"message": f"Job {job_id} deleted"}


# ── Downloads ─────────────────────────────────────────────────────────────────

@app.get("/api/download/{job_id}/{stem_name}")
async def download_stem(job_id: str, stem_name: str) -> FileResponse:
    """Stream a single stem file from a completed job.

    Args:
        job_id: UUID of the completed job.
        stem_name: Name of the stem to download (e.g. ``"vocals"``).

    Returns:
        :class:`~fastapi.responses.FileResponse` for the stem audio file.

    Raises:
        HTTPException: 400 if the job is not complete.
        HTTPException: 404 if the job or stem does not exist on disk.
    """
    job = _get_done_job(job_id)

    if stem_name not in job.stems_produced:
        raise HTTPException(
            404,
            f"Stem '{stem_name}' not found. Available: {list(job.stems_produced)}",
        )

    stem_filename = job.stems_produced[stem_name]
    stem_path = _song_dir(job) / stem_filename

    if not stem_path.exists():
        raise HTTPException(404, "Stem file missing from disk")

    media_type = "audio/mpeg" if stem_filename.endswith(".mp3") else "audio/wav"
    return FileResponse(
        path=str(stem_path), filename=stem_filename, media_type=media_type
    )


@app.get("/api/download/{job_id}")
async def download_all_stems(job_id: str) -> StreamingResponse:
    """Download all stems for a job as a ZIP archive.

    Args:
        job_id: UUID of the completed job.

    Returns:
        :class:`~fastapi.responses.StreamingResponse` containing a ZIP archive
        of all produced stem files.

    Raises:
        HTTPException: 400 if the job is not complete.
        HTTPException: 404 if the job does not exist.
    """
    job = _get_done_job(job_id)
    song_dir = _song_dir(job)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for stem_name, stem_filename in job.stems_produced.items():
            stem_path = song_dir / stem_filename
            if stem_path.exists():
                zf.write(stem_path, stem_filename)
                logger.debug("ZIP: added %s", stem_filename)

    buffer.seek(0)
    safe_name = safe_stem(Path(job.filename).stem, fallback="stems")
    zip_name = f"{safe_name}_stems.zip"

    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={zip_name}"},
    )


# ── Library ───────────────────────────────────────────────────────────────────

@app.get("/api/library")
async def list_library() -> dict:
    """List all output folders in the song library.

    Returns:
        JSON ``{folders: [...]}`` where each entry contains the folder name,
        display name, and audio file count.
    """
    folders = []
    if settings.outputs_dir.exists():
        for folder_path in sorted(settings.outputs_dir.iterdir()):
            if not folder_path.is_dir():
                continue
            audio_count = len(
                list(folder_path.glob("*.mp3")) + list(folder_path.glob("*.wav"))
            )
            folders.append(
                {
                    "name": folder_path.name,
                    "display_name": folder_path.name.replace("_", " ").title(),
                    "audio_count": audio_count,
                }
            )
    return {"folders": folders}


@app.get("/api/library/{folder}")
async def get_library_folder(folder: str) -> dict:
    """List stems inside a named output folder.

    Args:
        folder: Folder name within the outputs directory.

    Returns:
        JSON ``{folder, stems: [...]}`` where each stem entry contains the
        filename, stem name, size in MB, and streaming URL.

    Raises:
        HTTPException: 404 if the folder does not exist.
    """
    folder_path = settings.outputs_dir / folder
    if not folder_path.exists() or not folder_path.is_dir():
        raise HTTPException(404, f"Folder '{folder}' not found")

    audio_files = []
    for file_path in sorted(
        list(folder_path.glob("*.mp3")) + list(folder_path.glob("*.wav"))
    ):
        filename = file_path.name
        stem = file_path.stem
        # UUID-prefixed filenames: "3fa8-..._vocals.mp3" → stem_name = "vocals"
        if "_" in stem:
            prefix, _, remainder = stem.partition("_")
            stem_name = remainder if "-" in prefix else stem
        else:
            stem_name = stem

        audio_files.append(
            {
                "filename": filename,
                "stem_name": stem_name,
                "stream_url": f"/outputs/{folder}/{filename}",
                "size_mb": round(file_path.stat().st_size / 1_048_576, 1),
            }
        )

    audio_files.sort(key=lambda x: x["stem_name"])
    return {"folder": folder, "stems": audio_files}


@app.delete("/api/folders/{folder_name}")
async def delete_folder(folder_name: str) -> dict:
    """Delete an output folder and all its stems.

    Args:
        folder_name: Name of the folder inside the outputs directory.

    Returns:
        JSON confirmation message.

    Raises:
        HTTPException: 404 if the folder does not exist.
        HTTPException: 400 if the path is not a directory.
        HTTPException: 500 if deletion fails due to an OS error.
    """
    folder_path = settings.outputs_dir / folder_name

    if not folder_path.exists():
        raise HTTPException(404, f"Folder '{folder_name}' not found")
    if not folder_path.is_dir():
        raise HTTPException(400, f"'{folder_name}' is not a directory")

    try:
        shutil.rmtree(folder_path)
        logger.info("Deleted folder: %s", folder_path)
        return {"message": f"Folder '{folder_name}' deleted"}
    except OSError as exc:
        logger.error("Failed to delete folder %s: %s", folder_name, exc)
        raise HTTPException(500, f"Failed to delete folder: {exc}")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
    )
