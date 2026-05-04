"""
download.py - Download API router for AI-Music.

Routes registered under the ``/api/download`` prefix:

    POST   /api/download              — start an audio download job
    GET    /api/download/logs/<id>    — stream real-time logs via SSE
    GET    /api/download/jobs         — list all in-memory download jobs
    DELETE /api/download/jobs/<id>    — remove a completed job record

The downloader is executed as a subprocess (downloader_cli.py) to isolate
it from the Uvicorn worker and support long-running playlist downloads.
Verbose downloads run asynchronously with log output streamed to the
browser using Server-Sent Events (SSE) via an async generator.

When ``auto_transcribe`` or ``auto_stem`` is enabled the job is always run
in verbose/async mode so post-processing results appear in the SSE stream.
"""

import asyncio
import json
import os
import queue
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..core.auth import get_current_user
from ..core.config import AppConfig
from ..models.user import User
from ..services.downloader_cli import ui_resolve_output_dir
from ..utils.sse import SSE_JOB_DONE, sse_pack

router = APIRouter(prefix="/api/download", tags=["download"])

# ── Services path ──────────────────────────────────────────────────────────────

_SERVICES_DIR = Path(__file__).resolve().parent.parent / "services"

# ── Audio file extensions recognised for post-processing ──────────────────────

_AUDIO_EXTENSIONS: frozenset[str] = frozenset({".mp3", ".flac", ".wav", ".m4a", ".ogg", ".opus"})

# ── Job tracking ───────────────────────────────────────────────────────────────

JOBS: dict[str, "DownloadJob"] = {}
JOBS_LOCK = threading.Lock()


class DownloadJob:
    """Represents a single asynchronous download job.

    Attributes:
        job_id: Unique hex identifier.
        cmd: Subprocess command list.
        output_dir: Destination directory for downloaded files.
        q: Thread-safe queue of log lines for the SSE stream.
        done: True once the subprocess has exited.
        success: True on exit code 0; False on failure; None while running.
        message: Human-readable completion message.
        error: Human-readable error message on failure.
        started_at: Unix timestamp of job creation.
        auto_transcribe: Fire Whisper transcription on each downloaded file.
        transcribe_language: Language hint forwarded to Whisper.
        transcribe_model: Whisper model size.
        auto_stem: Fire Demucs separation on each downloaded file.
        stem_model: Demucs model name.
        proc: Live subprocess handle; set once the download starts, None otherwise.
    """

    def __init__(
        self,
        job_id: str,
        cmd: list[str],
        output_dir: Path,
        auto_transcribe: bool = False,
        transcribe_language: str = "Spanish",
        transcribe_model: str = "base",
        auto_stem: bool = False,
        stem_model: str = "htdemucs_6s",
    ) -> None:
        """Initialise a new download job.

        Args:
            job_id: Unique identifier string.
            cmd: Full subprocess command to run.
            output_dir: Target directory for downloaded files.
            auto_transcribe: Transcribe each downloaded audio file after download.
            transcribe_language: Language hint for Whisper.
            transcribe_model: Whisper model size (e.g. ``"base"``, ``"small"``).
            auto_stem: Separate each downloaded audio file into stems after download.
            stem_model: Demucs model name (e.g. ``"htdemucs_6s"``).
        """
        self.job_id = job_id
        self.cmd = cmd
        self.output_dir = output_dir
        self.q: "queue.Queue[str]" = queue.Queue()
        self.done = False
        self.success: bool | None = None
        self.message: str = ""
        self.error: str = ""
        self.started_at = time.time()
        self.auto_transcribe = auto_transcribe
        self.transcribe_language = transcribe_language
        self.transcribe_model = transcribe_model
        self.auto_stem = auto_stem
        self.stem_model = stem_model
        self.proc: subprocess.Popen | None = None


def _jobs_cleanup(max_age: int = AppConfig.JOB_MAX_AGE_SECONDS) -> None:
    """Remove completed jobs older than *max_age* seconds.

    Args:
        max_age: Maximum job age in seconds before eviction.
    """
    now = time.time()
    with JOBS_LOCK:
        old = [jid for jid, j in JOBS.items() if (now - j.started_at) > max_age]
        for jid in old:
            JOBS.pop(jid, None)


def _scan_audio_files(directory: Path) -> set[Path]:
    """Return the set of audio files currently in *directory* (non-recursive).

    Args:
        directory: Directory to scan.

    Returns:
        Set of absolute :class:`~pathlib.Path` objects for audio files found.
    """
    if not directory.is_dir():
        return set()
    return {p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in _AUDIO_EXTENSIONS}


def _call_transcribe_service(audio: Path, language: str, model: str) -> str:
    """Send one audio file to the Whisper transcription service.

    Args:
        audio: Absolute path to the audio file.
        language: Language hint (e.g. ``"Spanish"``).
        model: Whisper model size (e.g. ``"base"``).

    Returns:
        Human-readable result string for SSE logging.
    """
    payload = json.dumps({"path": str(audio), "language": language, "model": model}).encode()
    req = urllib.request.Request(
        f"{AppConfig.TRANSCRIBE_SERVICE_URL}/transcribe",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            result = json.loads(resp.read())
            if result.get("success"):
                return f"✓ Transcription complete → {audio.name}.md"
            return f"✗ Transcription failed: {result.get('error', 'unknown error')}"
    except urllib.error.URLError as exc:
        return f"✗ Transcription service unavailable: {exc.reason}"
    except Exception as exc:
        return f"✗ Transcription error: {exc}"


_STEM_MIME: dict[str, str] = {
    ".mp3": "audio/mpeg",
    ".flac": "audio/flac",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".ogg": "audio/ogg",
    ".opus": "audio/ogg",
}


def _call_stem_service(audio: Path, model: str) -> str:
    """Upload one audio file to the Demucs separator microservice.

    Posts the file directly to the separator's ``/api/separate`` endpoint with
    the ``Host: localhost`` header required by its TrustedHostMiddleware.

    Args:
        audio: Absolute path to the audio file.
        model: Demucs model name (e.g. ``"htdemucs_6s"``).

    Returns:
        Human-readable result string for SSE logging.
    """
    try:
        import httpx  # already a project dep via stem.py

        sep_url = f"{AppConfig.SEPARATOR_URL.rstrip('/')}/api/separate"
        timeout = httpx.Timeout(connect=10.0, read=600.0, write=300.0, pool=10.0)
        mime = _STEM_MIME.get(audio.suffix.lower(), "audio/mpeg")

        with open(audio, "rb") as fh:
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(
                    sep_url,
                    params={"model": model},
                    files={"file": (audio.name, fh, mime)},
                    headers={"Host": "localhost"},
                )
        if resp.is_success:
            job_id = resp.json().get("job_id", "")
            return f"✓ Stem separation started (job {job_id[:8]}) — check Stem Library"
        return f"✗ Stem separation failed ({resp.status_code}): {resp.text[:200]}"
    except Exception as exc:
        return f"✗ Stem separation error: {exc}"


def _post_process(job: DownloadJob, new_files: set[Path]) -> None:
    """Run auto-transcribe and/or auto-stem on newly downloaded audio files.

    Logs each step to *job.q* so results appear in the SSE stream.

    Args:
        job: The completed :class:`DownloadJob` whose flags control processing.
        new_files: Set of new audio file paths found after download.
    """
    if not new_files:
        job.q.put("[post] No new audio files found for post-processing.\n")
        return

    for audio in sorted(new_files):
        if job.auto_transcribe:
            job.q.put(f"[transcribe] {audio.name}…\n")
            msg = _call_transcribe_service(audio, job.transcribe_language, job.transcribe_model)
            job.q.put(f"[transcribe] {msg}\n")

        if job.auto_stem:
            job.q.put(f"[stem] {audio.name}…\n")
            msg = _call_stem_service(audio, job.stem_model)
            job.q.put(f"[stem] {msg}\n")


def _run_job(job: DownloadJob) -> None:
    """Execute a download command in a background thread.

    Streams stdout/stderr lines into *job.q* for SSE delivery.  When the
    download succeeds and post-processing flags are set, calls
    :func:`_post_process` on every newly downloaded audio file before
    enqueuing the :data:`~app.utils.sse.SSE_JOB_DONE` sentinel.

    Args:
        job: The :class:`DownloadJob` to execute.
    """
    env = {**os.environ, "PYTHONPATH": str(_SERVICES_DIR)}
    try:
        # Snapshot existing audio files so we can find only the new ones.
        pre_files = _scan_audio_files(job.output_dir)

        job.q.put(f"Running: {' '.join(job.cmd)}\n")
        proc = job.proc = subprocess.Popen(
            job.cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            job.q.put(line)

        rc = proc.wait()
        if rc == 0:
            job.success = True
            job.message = f"Download completed. Files saved to: {job.output_dir}"

            # Run post-processing on newly downloaded files.
            if job.auto_transcribe or job.auto_stem:
                post_files = _scan_audio_files(job.output_dir)
                new_files = post_files - pre_files
                _post_process(job, new_files)
        else:
            job.success = False
            job.error = f"Downloader exited with code {rc}."
    except Exception as exc:
        job.success = False
        job.error = str(exc)
    finally:
        job.done = True
        job.q.put(SSE_JOB_DONE)
        _jobs_cleanup()


# ── Pydantic bodies ────────────────────────────────────────────────────────────

class DownloadBody(BaseModel):
    """Request body for POST /api/download."""

    source: str = "single"
    format: str = "mp3"
    bitrate: str = "320k"
    url: str = ""
    search_txt: str = ""
    output: str = ""
    verbose: bool = False
    auto_transcribe: bool = False
    transcribe_language: str = "Spanish"
    transcribe_model: str = "base"
    auto_stem: bool = False
    stem_model: str = "htdemucs_6s"


# ── Routes ─────────────────────────────────────────────────────────────────────


@router.post("")
def start_download(
    body: DownloadBody,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Start an audio download job.

    Args:
        body: JSON body with download parameters.
        current_user: Resolved by :func:`get_current_user`.

    Returns:
        Verbose: ``{"success": true, "job_id": str}``.
        Non-verbose: ``{"success": true, "message": str, "output": str}`` or
        raises HTTP 400 / 500 on failure.
    """
    source = body.source
    fmt = body.format
    bitrate = body.bitrate
    url = body.url.strip()
    search_txt = body.search_txt.strip()
    custom_output = body.output.strip()
    # Force async/verbose mode when post-processing is requested so the user
    # receives SSE progress updates for transcription and stem separation.
    verbose = body.verbose or body.auto_transcribe or body.auto_stem

    output_dir = ui_resolve_output_dir(AppConfig.BASE_DIR, custom_output)
    _downloader = _SERVICES_DIR / "downloader_cli.py"
    cmd = [
        sys.executable, str(_downloader),
        "-s", source,
        "--format", fmt,
        "--bitrate", bitrate,
        "-o", custom_output,
        "-v",  # always verbose in async path; non-verbose handled below
    ]

    if source == "search_txt":
        if not search_txt:
            raise HTTPException(400, "Search text is required.")
        cmd.extend(["-q", search_txt])
    else:
        if not url:
            raise HTTPException(400, "URL is required.")
        cmd.extend(["-u", url])

    if verbose:
        job_id = uuid.uuid4().hex
        job = DownloadJob(
            job_id=job_id,
            cmd=cmd,
            output_dir=Path(output_dir),
            auto_transcribe=body.auto_transcribe,
            transcribe_language=body.transcribe_language.strip() or "Spanish",
            transcribe_model=body.transcribe_model.strip() or "base",
            auto_stem=body.auto_stem,
            stem_model=body.stem_model.strip() or "htdemucs_6s",
        )
        with JOBS_LOCK:
            JOBS[job_id] = job
        threading.Thread(target=_run_job, args=(job,), daemon=True).start()
        return {"success": True, "job_id": job_id}

    # Non-verbose synchronous path (no post-processing flags).
    non_verbose_cmd = [c for c in cmd if c != "-v"]
    env = {**os.environ, "PYTHONPATH": str(_SERVICES_DIR)}
    try:
        result = subprocess.run(non_verbose_cmd, capture_output=True, text=True, check=True, env=env)
        return {
            "success": True,
            "output": result.stdout,
            "message": f"Download completed. Files saved to: {output_dir}",
        }
    except subprocess.CalledProcessError as exc:
        raise HTTPException(500, exc.stderr or exc.stdout or str(exc))
    except Exception as exc:
        raise HTTPException(500, str(exc))


@router.get("/logs/{job_id}")
async def stream_logs(
    job_id: str,
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """Stream download job logs using Server-Sent Events (SSE).

    Delivers log lines as ``data:`` events. Closes with a ``done`` event
    containing a JSON summary of the job result.

    Args:
        job_id: Hex job identifier returned by ``POST /api/download``.
        current_user: Resolved by :func:`get_current_user`.

    Returns:
        A ``text/event-stream`` response that remains open until the job exits.

    Raises:
        HTTPException: 404 if *job_id* is unknown.
    """
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found.")

    async def generate():
        """Yield SSE chunks until the job completes."""
        yield "data: connected\n\n"
        loop = asyncio.get_event_loop()
        while True:
            try:
                line: str = await asyncio.wait_for(
                    loop.run_in_executor(None, job.q.get),
                    timeout=1.5,
                )
            except asyncio.TimeoutError:
                if job.done:
                    break
                yield ": keep-alive\n\n"
                continue
            if line == SSE_JOB_DONE:
                break
            yield sse_pack(line.rstrip("\n"))

        yield sse_pack(
            json.dumps({
                "success": bool(job.success),
                "message": job.message,
                "error": job.error,
                "job_id": job.job_id,
            }),
            event="done",
        )

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/jobs")
def list_jobs(
    current_user: User = Depends(get_current_user),
) -> list:
    """List all in-memory download jobs, newest first.

    Args:
        current_user: Resolved by :func:`get_current_user`.

    Returns:
        List of job summary dicts ordered by ``started_at`` descending.
    """
    with JOBS_LOCK:
        jobs = list(JOBS.values())

    jobs.sort(key=lambda j: j.started_at, reverse=True)
    return [
        {
            "job_id": j.job_id,
            "done": j.done,
            "success": j.success,
            "message": j.message,
            "error": j.error,
            "started_at": j.started_at,
            "output_dir": str(j.output_dir),
            "auto_transcribe": j.auto_transcribe,
            "auto_stem": j.auto_stem,
        }
        for j in jobs
    ]


@router.delete("/jobs/{job_id}")
def remove_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Remove a download job record from memory.

    Only completed (done) jobs may be removed.  Running jobs must be
    allowed to finish naturally since the subprocess cannot be killed
    without risking partial downloads.

    Args:
        job_id: Hex job identifier.
        current_user: Resolved by :func:`get_current_user`.

    Returns:
        ``{"success": True}``.

    Raises:
        HTTPException: 404 if job not found, 409 if still running.
    """
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found.")
    if not job.done:
        raise HTTPException(409, "Cannot remove a job that is still running.")
    with JOBS_LOCK:
        JOBS.pop(job_id, None)
    return {"success": True}


@router.post("/jobs/{job_id}/cancel")
def cancel_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Terminate a running download job by killing its subprocess.

    Sends SIGTERM to the subprocess; if it does not exit within two seconds,
    SIGKILL is sent.  The job is marked as done with a failure result so it
    can be dismissed from the queue normally.

    Args:
        job_id: Hex job identifier.
        current_user: Resolved by :func:`get_current_user`.

    Returns:
        ``{"success": True}``.

    Raises:
        HTTPException: 404 if job not found, 409 if the job is already done.
    """
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found.")
    if job.done:
        raise HTTPException(409, "Job is already finished.")
    if job.proc is not None:
        job.proc.terminate()
        try:
            job.proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            job.proc.kill()
    # Mark the job as done so the SSE stream drains and the UI can dismiss it.
    job.success = False
    job.error = "Cancelled by user."
    job.done = True
    job.q.put("__JOB_DONE__")
    return {"success": True}
