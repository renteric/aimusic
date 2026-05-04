"""
app.py - Minimal FastAPI wrapper around ACEStepPipeline.

Exposes two endpoints:
  GET  /health    — liveness probe
  POST /generate  — run text-to-music generation and return the saved file path

The pipeline is loaded once at startup from the checkpoint directory set via
ACESTEP_CHECKPOINT_PATH (empty string triggers automatic Hugging Face download).
Generated audio is written directly to the save_path supplied in the request
body (defaults to /app/media/ai_composed so it lands on the shared volume).
"""

import os
import logging
import time

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from pydantic import BaseModel

# ── Logging setup ──────────────────────────────────────────────────────────────
# DEBUG level captures everything: our logs, uvicorn, ACE-Step internals, torch.
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# Pull third-party loggers down to DEBUG so their output flows through.
for _name in ("uvicorn", "uvicorn.access", "uvicorn.error", "fastapi", "acestep", "torch"):
    logging.getLogger(_name).setLevel(logging.DEBUG)

logger = logging.getLogger("acestep-server")

_pipeline = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load ACEStepPipeline once at startup."""
    global _pipeline

    logger.debug("Lifespan start — importing ACEStepPipeline")
    from acestep.pipeline_ace_step import ACEStepPipeline

    checkpoint = os.environ.get("ACESTEP_CHECKPOINT_PATH", "")
    dtype = os.environ.get("ACESTEP_DTYPE", "float32")

    logger.debug("Env — ACESTEP_CHECKPOINT_PATH=%r  ACESTEP_DTYPE=%r", checkpoint, dtype)
    logger.info("Loading ACEStepPipeline (checkpoint=%r, dtype=%s)…", checkpoint or "auto", dtype)

    t0 = time.perf_counter()
    _pipeline = ACEStepPipeline(
        checkpoint_dir=checkpoint,
        dtype=dtype,
        torch_compile=False,
        cpu_offload=True,
        overlapped_decode=False,
    )
    elapsed = time.perf_counter() - t0

    logger.info("ACEStepPipeline ready (loaded in %.1fs).", elapsed)
    logger.debug("Pipeline object: %r", _pipeline)
    yield
    logger.debug("Lifespan shutdown.")


app = FastAPI(title="ACE-Step 1.5 | AI-Music", lifespan=lifespan)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log every incoming request and its response status + duration."""
    t0 = time.perf_counter()
    logger.debug("→ %s %s  body_size=%s", request.method, request.url.path,
                 request.headers.get("content-length", "?"))
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    logger.debug("← %s %s  status=%d  %.1fms",
                 request.method, request.url.path, response.status_code, elapsed_ms)
    return response


@app.get("/health")
def health() -> dict:
    """Liveness probe — returns ok once the pipeline is loaded."""
    loaded = _pipeline is not None
    logger.debug("Health check — pipeline_loaded=%s", loaded)
    return {"status": "ok", "pipeline_loaded": loaded}


class GenerateRequest(BaseModel):
    """Request body for POST /generate."""

    prompt: str
    lyrics: str = ""
    audio_duration: float = 60.0
    infer_step: int = 60
    guidance_scale: float = 15.0
    save_path: str = "/app/media/ai_composed"
    format: str = "wav"


@app.post("/generate")
def generate(req: GenerateRequest) -> dict:
    """Run ACE-Step text-to-music generation.

    Saves the generated audio to *req.save_path* (treated as a directory if it
    has no extension) and returns the absolute path of the first audio file.

    Returns:
        JSON with ``success``, ``output_path`` (str), and ``error`` (str).
    """
    logger.debug("generate() called — params: prompt=%r  lyrics=%r  duration=%.1f  "
                 "infer_step=%d  guidance_scale=%.1f  save_path=%r  format=%r",
                 req.prompt, req.lyrics, req.audio_duration,
                 req.infer_step, req.guidance_scale, req.save_path, req.format)

    if _pipeline is None:
        logger.error("generate() called before pipeline is ready")
        return {"success": False, "output_path": "", "error": "Pipeline not loaded yet."}

    try:
        os.makedirs(req.save_path, exist_ok=True)
        logger.debug("save_path %r ensured", req.save_path)

        logger.info("Starting generation — prompt=%r  duration=%.1fs  steps=%d",
                    req.prompt, req.audio_duration, req.infer_step)
        t0 = time.perf_counter()

        outputs = _pipeline(
            prompt=req.prompt,
            lyrics=req.lyrics or None,
            audio_duration=req.audio_duration,
            infer_step=req.infer_step,
            guidance_scale=req.guidance_scale,
            save_path=req.save_path,
            format=req.format,
            task="text2music",
        )

        elapsed = time.perf_counter() - t0
        logger.info("Pipeline finished in %.1fs", elapsed)
        logger.debug("Raw pipeline outputs: %r", outputs)

        # outputs is [audio_path_0, ..., params_json_path]
        # The last element is always a JSON metadata file.
        audio_extensions = {".wav", ".mp3", ".flac", ".ogg"}
        audio_paths = [
            p for p in outputs
            if isinstance(p, str) and os.path.splitext(p)[1].lower() in audio_extensions
        ]

        logger.debug("Detected audio files: %r", audio_paths)

        if not audio_paths:
            logger.warning("Pipeline returned no audio file — outputs=%r", outputs)
            return {"success": False, "output_path": "", "error": "Pipeline returned no audio file."}

        logger.info("Generation complete — output=%r", audio_paths[0])
        return {"success": True, "output_path": audio_paths[0], "error": ""}

    except Exception as exc:
        logger.exception("Generation failed: %s", exc)
        return {"success": False, "output_path": "", "error": str(exc)}
