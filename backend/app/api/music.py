"""
music.py - AI Composer API router for AI-Music.

Proxies music generation requests to the ACE-Step 1.5 microservice and
streams real-time progress updates to the browser via Server-Sent Events,
using the same job/queue/SSE pattern as ``download.py``.

Generated audio is saved to ``MEDIA_DIR/ai_composed/`` and immediately
browsable via the existing ``/api/media`` routes.

Routes registered under the ``/api/music`` prefix:

    POST   /api/music/generate           — start a generation job
    GET    /api/music/jobs/{id}/stream   — SSE progress stream
    GET    /api/music/jobs               — list all in-memory jobs
    DELETE /api/music/jobs/{id}          — remove a completed job record
    POST   /api/music/jobs/{id}/cancel   — cancel a running job

ACE-Step 1.5 API contract (verify against its Swagger UI at :8001/docs):
    POST {ACESTEP_URL}/generate
    Content-Type: application/json
    {
        "prompt":         str,    # style / genre description
        "lyrics":         str,    # optional lyrics; empty string = instrumental
        "audio_duration": float,  # seconds
        "infer_step":     int,    # diffusion steps (singular — ACE-Step param name)
        "guidance_scale": float,  # classifier-free guidance scale
        "save_path":      str,    # directory where the audio file is written
        "format":         str,    # "wav" or "mp3"
    }
    Response: JSON {"success": bool, "output_path": str, "error": str}
    The audio file is written directly to save_path on the shared media volume.
"""

import asyncio
import json
import queue
import re
import threading
import time
import uuid
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..core.auth import get_current_user
from ..core.config import AppConfig
from ..core.roles import require_roles
from ..models.user import User
from ..utils.sse import SSE_JOB_DONE, sse_pack

router = APIRouter(prefix="/api/music", tags=["music"])

# ── Output directory ───────────────────────────────────────────────────────────

#: All generated tracks land here (inside MEDIA_DIR → visible in the media browser).
_AI_COMPOSED_DIR: Path = AppConfig.MEDIA_DIR / "ai_composed"

# ── Job tracking ───────────────────────────────────────────────────────────────

MUSIC_JOBS: dict[str, "MusicJob"] = {}
MUSIC_JOBS_LOCK = threading.Lock()


class MusicJob:
    """Represents a single asynchronous music generation job.

    Attributes:
        job_id: Unique hex identifier.
        prompt: Style / genre description forwarded to ACE-Step as ``tags``.
        lyrics: Optional lyrics string; empty string requests instrumental.
        duration: Requested audio duration in seconds.
        infer_steps: Number of diffusion steps for ACE-Step.
        guidance_scale: Classifier-free guidance scale for ACE-Step.
        title: Optional human-readable filename stem.
        q: Thread-safe queue of log lines for the SSE stream.
        done: True once the job has finished (success or failure).
        success: True on success, False on failure, None while running.
        message: Human-readable completion message.
        error: Human-readable error message on failure.
        output_rel_path: Media-relative path of the saved file (empty until done).
        started_at: Unix timestamp of job creation.
        cancelled: Event set by :func:`cancel_job` to abort saving the output.
    """

    def __init__(
        self,
        job_id: str,
        prompt: str,
        lyrics: str,
        duration: float,
        infer_steps: int,
        guidance_scale: float,
        title: str,
    ) -> None:
        """Initialise a new music generation job.

        Args:
            job_id: Unique identifier string.
            prompt: Style / genre description for ACE-Step ``tags``.
            lyrics: Song lyrics (empty string for instrumental).
            duration: Audio duration in seconds.
            infer_steps: Diffusion steps for ACE-Step.
            guidance_scale: CFG scale for ACE-Step.
            title: Optional filename stem for the saved audio file.
        """
        self.job_id = job_id
        self.prompt = prompt
        self.lyrics = lyrics
        self.duration = duration
        self.infer_steps = infer_steps
        self.guidance_scale = guidance_scale
        self.title = title
        self.q: "queue.Queue[str]" = queue.Queue()
        self.done = False
        self.success: bool | None = None
        self.message: str = ""
        self.error: str = ""
        self.output_rel_path: str = ""
        self.started_at: float = time.time()
        self.cancelled: threading.Event = threading.Event()


def _jobs_cleanup() -> None:
    """Remove completed music jobs older than ``JOB_MAX_AGE_SECONDS``."""
    now = time.time()
    with MUSIC_JOBS_LOCK:
        stale = [jid for jid, j in MUSIC_JOBS.items() if j.done and (now - j.started_at) > AppConfig.JOB_MAX_AGE_SECONDS]
        for jid in stale:
            MUSIC_JOBS.pop(jid, None)


def _safe_filename(title: str, prompt: str, job_id: str) -> str:
    """Derive a filesystem-safe filename stem from the job parameters.

    Args:
        title: User-supplied title (may be empty).
        prompt: Style prompt used as fallback.
        job_id: Job identifier used as final fallback.

    Returns:
        A non-empty, filesystem-safe string (no spaces, no special chars).
    """
    raw = title.strip() or prompt.strip() or job_id[:8]
    safe = re.sub(r"[^\w\s\-]", "", raw)
    safe = re.sub(r"\s+", "_", safe).strip("_")
    return (safe[:60] or job_id[:8])


def _run_music_job(job: MusicJob) -> None:
    """Execute music generation in a background thread.

    Calls the ACE-Step ``/generate`` endpoint (blocking HTTP, long timeout),
    saves the returned audio to ``MEDIA_DIR/ai_composed/``, and signals the
    SSE stream via ``job.q``.

    Args:
        job: The :class:`MusicJob` to execute.
    """
    job.q.put("Starting ACE-Step 1.5 music generation…\n")
    job.q.put(f"Prompt: {job.prompt}\n")
    job.q.put(f"Duration: {job.duration}s  |  Steps: {job.infer_steps}  |  CFG: {job.guidance_scale}\n")
    job.q.put("On CPU, generation may take 10–30 minutes. This window can be safely minimised.\n")

    payload: dict = {
        "prompt": job.prompt,
        "lyrics": job.lyrics,
        "audio_duration": job.duration,
        "infer_step": job.infer_steps,    # ACE-Step uses singular "infer_step"
        "guidance_scale": job.guidance_scale,
        "save_path": str(AppConfig.MEDIA_DIR / "ai_composed"),
        "format": "wav",
    }

    try:
        # ACE-Step generation can take many minutes on CPU; timeout is generous.
        timeout = httpx.Timeout(connect=30.0, read=7200.0, write=60.0, pool=10.0)
        generate_url = f"{AppConfig.ACESTEP_URL.rstrip('/')}/generate"

        job.q.put(f"Calling ACE-Step at {generate_url}…\n")

        with httpx.Client(timeout=timeout) as client:
            resp = client.post(generate_url, json=payload)

        if not resp.is_success:
            raise RuntimeError(f"ACE-Step returned HTTP {resp.status_code}: {resp.text[:300]}")

        # Our ACE-Step wrapper (acestep/app.py) returns JSON:
        # {"success": bool, "output_path": str, "error": str}
        data = resp.json()
        if not data.get("success"):
            raise RuntimeError(f"ACE-Step generation failed: {data.get('error', 'unknown error')}")

        if job.cancelled.is_set():
            job.q.put("Generation complete but job was cancelled — output discarded.\n")
            return

        out_path = Path(data["output_path"])
        try:
            file_kb = out_path.stat().st_size // 1024
        except FileNotFoundError:
            raise RuntimeError(f"ACE-Step reported output path {out_path} but file was not found.")

        rel_path = out_path.relative_to(AppConfig.MEDIA_DIR).as_posix()

        job.success = True
        job.output_rel_path = rel_path
        job.message = f"Generated: {rel_path}"
        job.q.put(f"✓ Generation complete → {rel_path} ({file_kb} KB)\n")

    except Exception as exc:
        if not job.cancelled.is_set():
            job.success = False
            job.error = str(exc)
            job.q.put(f"✗ Generation failed: {exc}\n")
    finally:
        job.done = True
        job.q.put(SSE_JOB_DONE)
        _jobs_cleanup()


# ── Pydantic request body ──────────────────────────────────────────────────────


class MusicGenerateBody(BaseModel):
    """Request body for POST /api/music/generate."""

    prompt: str
    lyrics: str = ""
    duration: float = 60.0
    infer_steps: int = 60
    guidance_scale: float = 15.0
    title: str = ""


# ── Routes ─────────────────────────────────────────────────────────────────────


@router.post("/generate")
def start_generation(
    body: MusicGenerateBody,
    current_user: User = Depends(require_roles("superadmin", "admin", "user")),
) -> dict:
    """Start an AI music generation job.

    Validates the request, creates a :class:`MusicJob`, launches the
    ACE-Step call in a daemon thread, and returns the job ID for SSE
    streaming.

    Args:
        body: JSON body with generation parameters.
        current_user: Resolved by the role dependency.

    Returns:
        ``{"success": True, "job_id": str}``.

    Raises:
        HTTPException: 422 on invalid parameter ranges.
    """
    prompt = body.prompt.strip()
    if not prompt:
        raise HTTPException(422, "prompt is required.")

    # Ensure the output directory exists before starting the job.
    _AI_COMPOSED_DIR.mkdir(parents=True, exist_ok=True)

    duration = round(max(10.0, min(240.0, body.duration)), 1)
    infer_steps = max(20, min(150, body.infer_steps))
    guidance_scale = round(max(1.0, min(20.0, body.guidance_scale)), 1)

    job_id = uuid.uuid4().hex
    job = MusicJob(
        job_id=job_id,
        prompt=prompt,
        lyrics=body.lyrics.strip(),
        duration=duration,
        infer_steps=infer_steps,
        guidance_scale=guidance_scale,
        title=body.title.strip(),
    )

    with MUSIC_JOBS_LOCK:
        MUSIC_JOBS[job_id] = job

    threading.Thread(
        target=_run_music_job,
        args=(job,),
        daemon=True,
        name=f"music-{job_id[:8]}",
    ).start()

    return {"success": True, "job_id": job_id}


@router.get("/jobs/{job_id}/stream")
async def stream_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """Stream music generation progress via Server-Sent Events.

    Delivers log lines as ``data:`` events and closes with a ``done`` event
    containing a JSON summary including ``rel_path`` of the generated file.

    Args:
        job_id: Hex job identifier returned by ``POST /api/music/generate``.
        current_user: Resolved by :func:`get_current_user`.

    Returns:
        A ``text/event-stream`` response that remains open until generation ends.

    Raises:
        HTTPException: 404 if *job_id* is unknown.
    """
    with MUSIC_JOBS_LOCK:
        job = MUSIC_JOBS.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found.")

    async def generate():
        """Yield SSE chunks until the generation job completes."""
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
                "rel_path": job.output_rel_path,
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
    """List all in-memory music generation jobs, newest first.

    Args:
        current_user: Resolved by :func:`get_current_user`.

    Returns:
        List of job summary dicts ordered by ``started_at`` descending.
    """
    with MUSIC_JOBS_LOCK:
        jobs = list(MUSIC_JOBS.values())
    jobs.sort(key=lambda j: j.started_at, reverse=True)
    return [
        {
            "job_id": j.job_id,
            "done": j.done,
            "success": j.success,
            "message": j.message,
            "error": j.error,
            "started_at": j.started_at,
            "prompt": j.prompt,
            "duration": j.duration,
            "output_rel_path": j.output_rel_path,
        }
        for j in jobs
    ]


@router.delete("/jobs/{job_id}")
def remove_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Remove a completed music generation job record from memory.

    Args:
        job_id: Hex job identifier.
        current_user: Resolved by :func:`get_current_user`.

    Returns:
        ``{"success": True}``.

    Raises:
        HTTPException: 404 if job not found, 409 if still running.
    """
    with MUSIC_JOBS_LOCK:
        job = MUSIC_JOBS.get(job_id)
        if job is None:
            raise HTTPException(404, "Job not found.")
        if not job.done:
            raise HTTPException(409, "Cannot remove a job that is still running.")
        MUSIC_JOBS.pop(job_id, None)
    return {"success": True}


@router.post("/jobs/{job_id}/cancel")
def cancel_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Cancel a running music generation job.

    Sets the cancellation flag so the background thread discards any result
    once the ACE-Step HTTP call completes.  The SSE stream is drained
    immediately by injecting the sentinel.

    Note:
        ACE-Step does not support mid-generation interruption; the underlying
        HTTP call continues until ACE-Step finishes or times out.  The output
        file is simply not saved.

    Args:
        job_id: Hex job identifier.
        current_user: Resolved by :func:`get_current_user`.

    Returns:
        ``{"success": True}``.

    Raises:
        HTTPException: 404 if job not found, 409 if already finished.
    """
    with MUSIC_JOBS_LOCK:
        job = MUSIC_JOBS.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found.")
    if job.done:
        raise HTTPException(409, "Job is already finished.")
    job.cancelled.set()
    job.success = False
    job.error = "Cancelled by user."
    job.done = True
    job.q.put("__JOB_DONE__")
    return {"success": True}
