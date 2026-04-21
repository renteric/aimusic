"""
melody.py - Melody extraction API router for AI-Music.

Runs :class:`~app.services.extract_melody_cli.MelodyExtractor` in a background
thread so long-running pYIN analysis never blocks the Uvicorn event loop.

Routes registered under the ``/api/melody`` prefix:

    POST   /api/melody/extract              — start an extraction job
    GET    /api/melody/jobs                 — list recent jobs (newest first)
    GET    /api/melody/jobs/{job_id}        — poll a job for status + results
    DELETE /api/melody/jobs/{job_id}        — delete a job and its output files
    GET    /api/melody/download/{job_id}/{filename} — download one output file
    GET    /api/melody/download/{job_id}            — download all output files as ZIP
"""

import io
import json
import re
import shutil
import threading
import time
import uuid
import zipfile
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from ..core.config import AppConfig
from ..core.roles import require_roles
from ..models.user import User
from ..utils.files import safe_media_path

router = APIRouter(prefix="/api/melody", tags=["melody"])

# ── Optional ML dep guard ──────────────────────────────────────────────────────
# librosa / music21 / mido are heavy; guard the import so the backend starts
# cleanly even when the packages are absent, and raises 503 at request time.

try:
    import click as _click  # already a dep (used by CLI)

    from ..services.extract_melody_cli import (
        ExtractionConfig,
        MelodyExtractor,
    )

    _MELODY_AVAILABLE = True
except ImportError:
    _MELODY_AVAILABLE = False
    _click = None  # type: ignore[assignment]

# ── Constants ──────────────────────────────────────────────────────────────────

#: Output files the download endpoint will serve.
_ALLOWED_FILES: frozenset[str] = frozenset({
    "melody.mid",
    "duet.mid",
    "lead_sheet.musicxml",
    "notes.csv",
    "summary.json",
})

#: Root directory for all melody extraction outputs (inside MEDIA_DIR).
_MELODY_DIR: Path = AppConfig.MEDIA_DIR / "melody"

# ── Job tracking ───────────────────────────────────────────────────────────────

MELODY_JOBS: dict[str, "MelodyJob"] = {}
MELODY_JOBS_LOCK = threading.Lock()

JobStatus = Literal["pending", "processing", "done", "failed"]


class MelodyJob:
    """Tracks a single asynchronous melody extraction job.

    Attributes:
        job_id: Unique hex identifier.
        audio_path: rel_path of the source audio file inside MEDIA_DIR.
        audio_name: Bare filename (no directory prefix).
        out_dir: Absolute path where output files are written.
        status: Current job state.
        summary: Extraction summary dict; populated when ``status == "done"``.
        error: Human-readable error message; populated when ``status == "failed"``.
        started_at: Unix timestamp of job creation.
    """

    def __init__(self, job_id: str, audio_path: str, out_dir: Path) -> None:
        """Initialise a new melody extraction job.

        Args:
            job_id: Unique identifier string.
            audio_path: Relative path to the audio file inside MEDIA_DIR.
            out_dir: Absolute output directory for this job's files.
        """
        self.job_id = job_id
        self.audio_path = audio_path
        self.audio_name = Path(audio_path).name
        self.out_dir = out_dir
        self.status: JobStatus = "pending"
        self.summary: dict | None = None
        self.error: str = ""
        self.started_at: float = time.time()

    def to_dict(self) -> dict:
        """Serialise the job to a JSON-safe dict.

        Returns:
            Dict suitable for use as an API response body.
        """
        result: dict = {
            "job_id": self.job_id,
            "status": self.status,
            "audio_path": self.audio_path,
            "audio_name": self.audio_name,
            "started_at": self.started_at,
            "error": self.error,
            "outputs": [],
        }
        if self.summary:
            result["summary"] = self.summary
            result["outputs"] = [
                f for f in _ALLOWED_FILES if (self.out_dir / f).exists()
            ]
        return result


def _song_stem(audio_path: str) -> str:
    """Return a filesystem-safe stem derived from the audio filename.

    Strips the file extension and replaces any characters that are unsafe in
    filenames (anything that is not alphanumeric, hyphen, underscore, dot, or
    space) with an underscore, then strips leading/trailing whitespace.

    Args:
        audio_path: Relative or absolute path to the audio file.

    Returns:
        A non-empty safe stem string (falls back to ``"melody"`` when the
        result would otherwise be empty).
    """
    stem = Path(audio_path).stem
    safe = re.sub(r"[^\w\s\-.]", "_", stem).strip()
    return safe or "melody"


def _read_meta(out_dir: Path) -> dict:
    """Read the ``_meta.json`` file written by :func:`_run_melody_job`.

    Args:
        out_dir: Absolute path to the job output directory.

    Returns:
        Parsed meta dict, or an empty dict when the file is absent.
    """
    meta_file = out_dir / "_meta.json"
    if meta_file.exists():
        try:
            return json.loads(meta_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _jobs_cleanup() -> None:
    """Evict in-memory job records older than ``JOB_MAX_AGE_SECONDS``.

    Does NOT delete output files from disk — the user may still want them.
    """
    now = time.time()
    with MELODY_JOBS_LOCK:
        stale = [jid for jid, j in MELODY_JOBS.items() if (now - j.started_at) > AppConfig.JOB_MAX_AGE_SECONDS]
        for jid in stale:
            MELODY_JOBS.pop(jid, None)


def _run_melody_job(job: MelodyJob, config: "ExtractionConfig") -> None:
    """Execute melody extraction in a background thread.

    Drives :meth:`MelodyExtractor.run`, captures any error, and updates the
    job status.  ``click.echo`` output goes to stdout (Docker logs).

    Args:
        job: The :class:`MelodyJob` to execute.
        config: :class:`ExtractionConfig` built from the request body.
    """
    job.status = "processing"

    # Persist job metadata to disk immediately so save/ZIP endpoints work even
    # after the in-memory job record has been evicted.
    meta = {"audio_path": job.audio_path, "song_stem": _song_stem(job.audio_path)}
    (job.out_dir / "_meta.json").write_text(json.dumps(meta), encoding="utf-8")

    try:
        audio_abs = safe_media_path(job.audio_path)
        extractor = MelodyExtractor(
            audio_path=audio_abs,
            out_dir=job.out_dir,
            config=config,
        )
        summary = extractor.run()

        # Replace absolute output paths with bare filenames — clients download
        # via the /api/melody/download/{job_id}/{filename} endpoint.
        if "outputs" in summary:
            summary["outputs"] = {
                k: Path(v).name for k, v in summary["outputs"].items()
            }

        job.summary = summary
        job.status = "done"
    except Exception as exc:
        # click.ClickException carries the formatted message; others use str().
        if hasattr(exc, "format_message"):
            job.error = exc.format_message()  # type: ignore[attr-defined]
        else:
            job.error = str(exc)
        job.status = "failed"
    finally:
        _jobs_cleanup()


# ── Request body ───────────────────────────────────────────────────────────────


class ExtractBody(BaseModel):
    """Request body for POST /api/melody/extract."""

    path: str
    fmin: str = "C4"
    fmax: str = "A6"
    min_note_ms: float = 60.0
    use_hpss: bool = True
    bpm: float | None = None
    key: str | None = None
    mode: str | None = None
    harmony_mode: str = "diatonic"


# ── Helpers ────────────────────────────────────────────────────────────────────


def _require_melody_deps() -> None:
    """Raise 503 when the ML dependencies are not installed.

    Raises:
        HTTPException: 503 when librosa / mido / music21 are unavailable.
    """
    if not _MELODY_AVAILABLE:
        raise HTTPException(
            503,
            "Melody extraction dependencies are not installed. "
            "Ensure librosa, mido, music21, and soundfile are in requirements.txt "
            "and the backend image has been rebuilt.",
        )


def _parse_pitch(value: str, param: str) -> float:
    """Convert a note name (e.g. ``"C4"``) or numeric string to Hz.

    Args:
        value: Note name or plain float string.
        param: Parameter name used in error messages.

    Returns:
        Frequency in Hz.

    Raises:
        HTTPException: 422 when *value* cannot be parsed.
    """
    import librosa  # only called when _MELODY_AVAILABLE is True

    try:
        return float(librosa.note_to_hz(value))
    except Exception:
        pass
    try:
        return float(value)
    except ValueError:
        raise HTTPException(422, f"'{value}' is not a valid note name (e.g. C4) or Hz value for {param}.")


# ── Endpoints ──────────────────────────────────────────────────────────────────


@router.post("/extract")
def start_extraction(
    body: ExtractBody,
    current_user: User = Depends(require_roles("superadmin", "admin", "user")),
) -> dict:
    """Start a melody extraction job for an audio file.

    Validates the request, builds an :class:`ExtractionConfig`, creates a
    :class:`MelodyJob`, and launches the extractor in a daemon thread.

    Args:
        body: JSON body with ``path`` and optional extraction parameters.
        current_user: Resolved by the role dependency.

    Returns:
        ``{"job_id": str, "status": "pending"}``.

    Raises:
        HTTPException: 503 if ML deps are missing, 404 if the file is not
            found, 422 on invalid parameter values.
    """
    _require_melody_deps()

    target = safe_media_path(body.path)
    if not target.exists() or not target.is_file():
        raise HTTPException(404, "Audio file not found.")

    mime_suffix = target.suffix.lower().lstrip(".")
    if mime_suffix not in {"mp3", "flac", "wav", "m4a", "ogg", "opus"}:
        raise HTTPException(422, "File does not appear to be a supported audio format.")

    if body.key is not None and body.mode is None:
        raise HTTPException(422, "key and mode must be provided together.")
    if body.mode is not None and body.key is None:
        raise HTTPException(422, "key and mode must be provided together.")

    fmin_hz = _parse_pitch(body.fmin, "fmin")
    fmax_hz = _parse_pitch(body.fmax, "fmax")

    try:
        config = ExtractionConfig(
            fmin_hz=fmin_hz,
            fmax_hz=fmax_hz,
            min_note_sec=max(0.02, body.min_note_ms / 1000.0),
            use_hpss=body.use_hpss,
            bpm_override=body.bpm,
            key_override=body.key,
            mode_override=body.mode,
            harmony_mode=body.harmony_mode,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    job_id = uuid.uuid4().hex
    out_dir = _MELODY_DIR / job_id
    out_dir.mkdir(parents=True, exist_ok=True)

    job = MelodyJob(job_id=job_id, audio_path=body.path, out_dir=out_dir)
    with MELODY_JOBS_LOCK:
        MELODY_JOBS[job_id] = job

    threading.Thread(
        target=_run_melody_job,
        args=(job, config),
        daemon=True,
        name=f"melody-{job_id[:8]}",
    ).start()

    return {"job_id": job_id, "status": "pending"}


@router.get("/jobs")
def list_jobs(
    current_user: User = Depends(require_roles("superadmin", "admin", "user")),
) -> list[dict]:
    """Return all in-memory melody jobs, newest first.

    Args:
        current_user: Resolved by the role dependency.

    Returns:
        List of job dicts sorted by ``started_at`` descending.
    """
    with MELODY_JOBS_LOCK:
        jobs = list(MELODY_JOBS.values())
    return [j.to_dict() for j in sorted(jobs, key=lambda j: j.started_at, reverse=True)]


@router.get("/jobs/{job_id}")
def get_job(
    job_id: str,
    current_user: User = Depends(require_roles("superadmin", "admin", "user")),
) -> dict:
    """Return the current state of a melody extraction job.

    Args:
        job_id: Hex job identifier returned by ``POST /api/melody/extract``.
        current_user: Resolved by the role dependency.

    Returns:
        Full job dict including ``summary`` and ``outputs`` when complete.

    Raises:
        HTTPException: 404 if *job_id* is unknown.
    """
    with MELODY_JOBS_LOCK:
        job = MELODY_JOBS.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found.")
    return job.to_dict()


@router.delete("/jobs/{job_id}")
def delete_job(
    job_id: str,
    current_user: User = Depends(require_roles("superadmin", "admin", "user")),
) -> dict:
    """Delete a melody job record and its output files from disk.

    Args:
        job_id: Hex job identifier.
        current_user: Resolved by the role dependency.

    Returns:
        ``{"success": True}``.

    Raises:
        HTTPException: 404 if *job_id* is unknown, 409 if still processing.
    """
    with MELODY_JOBS_LOCK:
        job = MELODY_JOBS.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found.")
    if job.status == "processing":
        raise HTTPException(409, "Cannot delete a job that is still processing.")

    if job.out_dir.exists():
        shutil.rmtree(job.out_dir, ignore_errors=True)

    with MELODY_JOBS_LOCK:
        MELODY_JOBS.pop(job_id, None)

    return {"success": True}


@router.get("/download/{job_id}/{filename}")
def download_output(
    job_id: str,
    filename: str,
    current_user: User = Depends(require_roles("superadmin", "admin", "user")),
) -> FileResponse:
    """Serve one output file from a completed melody extraction job.

    Only files in the allowed set (``melody.mid``, ``duet.mid``,
    ``lead_sheet.musicxml``, ``notes.csv``, ``summary.json``) may be
    downloaded.

    Args:
        job_id: Hex job identifier.
        filename: One of the allowed output filenames.
        current_user: Resolved by the role dependency.

    Returns:
        :class:`~fastapi.responses.FileResponse` for the requested file.

    Raises:
        HTTPException: 400 for disallowed filenames, 404 if job or file is not found.
    """
    if filename not in _ALLOWED_FILES:
        raise HTTPException(400, f"'{filename}' is not an allowed output file.")

    # Allow downloading even after job is evicted from memory (file persists on disk).
    out_dir = _MELODY_DIR / job_id
    file_path = out_dir / filename

    if not file_path.exists():
        raise HTTPException(404, "Output file not found. The job may have been deleted.")

    # Derive stem from meta (disk) then in-memory job, then job_id fallback.
    meta = _read_meta(out_dir)
    stem = meta.get("song_stem")
    if not stem:
        with MELODY_JOBS_LOCK:
            mem_job = MELODY_JOBS.get(job_id)
        stem = _song_stem(mem_job.audio_path) if mem_job else f"melody_{job_id[:8]}"

    download_name = f"{stem}_{filename}"

    _mime_map: dict[str, str] = {
        ".mid": "audio/midi",
        ".musicxml": "application/vnd.recordare.musicxml+xml",
        ".csv": "text/csv",
        ".json": "application/json",
    }
    mime = _mime_map.get(file_path.suffix.lower(), "application/octet-stream")

    return FileResponse(
        path=str(file_path),
        filename=download_name,
        media_type=mime,
    )


@router.get("/download/{job_id}")
def download_all_outputs(
    job_id: str,
    current_user: User = Depends(require_roles("superadmin", "admin", "user")),
) -> StreamingResponse:
    """Stream all output files for a melody extraction job as a ZIP archive.

    The archive contains every file present in the job output directory that
    belongs to the allowed set.  The archive is built in memory so no temp
    file is left on disk.

    Args:
        job_id: Hex job identifier.
        current_user: Resolved by the role dependency.

    Returns:
        :class:`~fastapi.responses.StreamingResponse` serving a ZIP file.

    Raises:
        HTTPException: 404 if the job output directory does not exist or
            contains no downloadable files.
    """
    out_dir = _MELODY_DIR / job_id
    if not out_dir.is_dir():
        raise HTTPException(404, "Job output not found. The job may have been deleted.")

    files_to_zip = [out_dir / f for f in _ALLOWED_FILES if (out_dir / f).exists()]
    if not files_to_zip:
        raise HTTPException(404, "No output files found for this job.")

    meta = _read_meta(out_dir)
    stem = meta.get("song_stem") or f"melody_{job_id[:8]}"

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for f in files_to_zip:
            zf.write(f, arcname=f"{stem}_{f.name}")
    buf.seek(0)

    zip_name = f"{stem}.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zip_name}"'},
    )


@router.post("/jobs/{job_id}/save")
def save_outputs_to_library(
    job_id: str,
    current_user: User = Depends(require_roles("superadmin", "admin", "user")),
) -> dict:
    """Copy all output files into the source audio file's media directory.

    Files are named ``<song_stem>_<original_filename>`` and placed alongside
    the source audio file.  Existing files with the same name are overwritten.

    Args:
        job_id: Hex job identifier.
        current_user: Resolved by the role dependency.

    Returns:
        ``{"saved": [list of rel_paths written]}``.

    Raises:
        HTTPException: 404 if the output directory or metadata is missing.
    """
    out_dir = _MELODY_DIR / job_id
    if not out_dir.is_dir():
        raise HTTPException(404, "Job output not found. The job may have been deleted.")

    meta = _read_meta(out_dir)
    if not meta.get("audio_path"):
        raise HTTPException(404, "Job metadata not found.")

    audio_abs = safe_media_path(meta["audio_path"])
    target_dir = audio_abs.parent
    stem = meta.get("song_stem") or _song_stem(meta["audio_path"])

    saved: list[str] = []
    for fname in _ALLOWED_FILES:
        src = out_dir / fname
        if src.exists():
            dst = target_dir / f"{stem}_{fname}"
            shutil.copy2(src, dst)
            saved.append(dst.relative_to(AppConfig.MEDIA_DIR).as_posix())

    return {"saved": saved}


@router.post("/jobs/{job_id}/save/{filename}")
def save_output_file_to_library(
    job_id: str,
    filename: str,
    current_user: User = Depends(require_roles("superadmin", "admin", "user")),
) -> dict:
    """Copy a single output file into the source audio file's media directory.

    The file is named ``<song_stem>_<original_filename>`` and placed alongside
    the source audio.  An existing file with the same name is overwritten.

    Args:
        job_id: Hex job identifier.
        filename: One of the allowed output filenames.
        current_user: Resolved by the role dependency.

    Returns:
        ``{"saved": rel_path, "filename": dest_filename}``.

    Raises:
        HTTPException: 400 for disallowed filenames, 404 if job output or
            metadata is not found.
    """
    if filename not in _ALLOWED_FILES:
        raise HTTPException(400, f"'{filename}' is not an allowed output file.")

    out_dir = _MELODY_DIR / job_id
    src = out_dir / filename
    if not src.exists():
        raise HTTPException(404, "Output file not found. The job may have been deleted.")

    meta = _read_meta(out_dir)
    if not meta.get("audio_path"):
        raise HTTPException(404, "Job metadata not found.")

    audio_abs = safe_media_path(meta["audio_path"])
    target_dir = audio_abs.parent
    stem = meta.get("song_stem") or _song_stem(meta["audio_path"])

    dest_filename = f"{stem}_{filename}"
    dst = target_dir / dest_filename
    shutil.copy2(src, dst)
    saved_path = dst.relative_to(AppConfig.MEDIA_DIR).as_posix()

    return {"saved": saved_path, "filename": dest_filename}
