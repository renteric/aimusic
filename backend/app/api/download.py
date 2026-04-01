"""
download.py - Download API router for AI-Music.

Routes registered under the ``/api/download`` prefix:

    POST /api/download              — start an audio download job
    GET  /api/download/logs/<id>    — stream real-time logs via SSE

The downloader is executed as a subprocess (downloader_cli.py) to isolate
it from the Uvicorn worker and support long-running playlist downloads.
Verbose downloads run asynchronously with log output streamed to the
browser using Server-Sent Events (SSE) via an async generator.
"""

import asyncio
import json
import os
import queue
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..core.auth import get_current_user
from ..core.config import AppConfig
from ..models.user import User
from ..services.downloader_cli import ui_resolve_output_dir

router = APIRouter(prefix="/api/download", tags=["download"])

# ── Services path ──────────────────────────────────────────────────────────────

_SERVICES_DIR = Path(__file__).resolve().parent.parent / "services"

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
    """

    def __init__(self, job_id: str, cmd: list[str], output_dir: Path) -> None:
        """Initialise a new download job.

        Args:
            job_id: Unique identifier string.
            cmd: Full subprocess command to run.
            output_dir: Target directory for downloaded files.
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


def _run_job(job: DownloadJob) -> None:
    """Execute a download command in a background thread.

    Streams stdout/stderr lines into *job.q* for SSE delivery. Enqueues
    the sentinel ``"__JOB_DONE__"`` when the process exits.

    Args:
        job: The :class:`DownloadJob` to execute.
    """
    env = {**os.environ, "PYTHONPATH": str(_SERVICES_DIR)}
    try:
        job.q.put(f"Running: {' '.join(job.cmd)}\n")
        proc = subprocess.Popen(
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
        else:
            job.success = False
            job.error = f"Downloader exited with code {rc}."
    except Exception as exc:
        job.success = False
        job.error = str(exc)
    finally:
        job.done = True
        job.q.put("__JOB_DONE__")
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
    verbose = body.verbose

    output_dir = ui_resolve_output_dir(AppConfig.BASE_DIR, custom_output)
    _downloader = _SERVICES_DIR / "downloader_cli.py"
    cmd = [
        sys.executable, str(_downloader),
        "-s", source,
        "--format", fmt,
        "--bitrate", bitrate,
        "-o", custom_output,
    ]
    if verbose:
        cmd.append("-v")

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
        job = DownloadJob(job_id=job_id, cmd=cmd, output_dir=Path(output_dir))
        with JOBS_LOCK:
            JOBS[job_id] = job
        threading.Thread(target=_run_job, args=(job,), daemon=True).start()
        return {"success": True, "job_id": job_id}

    env = {**os.environ, "PYTHONPATH": str(_SERVICES_DIR)}
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, env=env)
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

    def sse_pack(data: str, event: str | None = None) -> str:
        """Format *data* as an SSE message block."""
        payload = "".join(f"data: {line}\n" for line in data.splitlines()) or "data: \n"
        prefix = f"event: {event}\n" if event else ""
        return prefix + payload + "\n"

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
            if line == "__JOB_DONE__":
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
