"""transcribe_service.py — Lightweight FastAPI service for Whisper transcription.

Runs inside the ``music-transcribe`` Docker container and exposes a minimal
REST API that the main backend calls when a user clicks the "Transcribe" button
in the media browser UI.

The Whisper model is loaded once per model-size on first use and cached in
memory for the lifetime of the process, avoiding re-load overhead on every
request.

Endpoints:
    GET  /health      — Liveness probe for Docker healthcheck.
    POST /transcribe  — Transcribe an audio file and write a ``.md`` beside it.
"""

import os
import sys
from pathlib import Path

import uvicorn
import whisper  # type: ignore
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# transcribe_cli lives alongside this file in src/lib/
sys.path.insert(0, str(Path(__file__).resolve().parent))

from transcribe_cli import build_transcript_markdown, pick_device_and_precision  # noqa: E402

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Whisper Transcription Service",
    description="Internal microservice — transcribes audio files via OpenAI Whisper.",
    version="1.0.0",
)

# ── Model cache — one entry per model-size, loaded on first request ───────────
_model_cache: dict[str, whisper.Whisper] = {}


def _get_model(model_size: str) -> whisper.Whisper:
    """Return a cached Whisper model, loading from disk on the first call.

    The model weights directory defaults to ``~/.cache/whisper`` but can be
    overridden by setting the ``WHISPER_CACHE_DIR`` environment variable —
    useful in Docker where the home directory may not be writable.

    Args:
        model_size: Whisper model identifier (e.g. ``"base"``, ``"small"``).

    Returns:
        Loaded :class:`whisper.Whisper` model instance.
    """
    if model_size not in _model_cache:
        device, _ = pick_device_and_precision()
        cache_dir: str | None = os.getenv("WHISPER_CACHE_DIR")
        _model_cache[model_size] = whisper.load_model(
            model_size, device=device, download_root=cache_dir
        )
    return _model_cache[model_size]


# ── Request / response schemas ────────────────────────────────────────────────

class TranscribeRequest(BaseModel):
    """Body schema for the ``POST /transcribe`` endpoint.

    Attributes:
        path: Absolute path to the audio file inside the container.
        language: Language hint for Whisper (e.g. ``"Spanish"``).
            Pass ``"auto"`` to let Whisper detect the language automatically.
        model: Whisper model size identifier (default ``"base"``).
        pause_threshold: Silence gap in seconds that inserts a blank line between
            transcript paragraphs (default ``1.2``).
    """

    path: str = Field(..., description="Absolute path to the audio file in the container")
    language: str = Field(default="Spanish", description="Language hint or 'auto' for detection")
    model: str = Field(default="base", description="Whisper model size")
    pause_threshold: float = Field(default=1.2, ge=0.0, description="Pause gap in seconds for paragraph breaks")


class TranscribeResponse(BaseModel):
    """Response schema for the ``POST /transcribe`` endpoint.

    Attributes:
        success: Whether transcription completed without error.
        output: Human-readable summary of the output file (on success).
        error: Error description (on failure).
    """

    success: bool
    output: str | None = None
    error: str | None = None


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health() -> dict:
    """Liveness probe endpoint.

    Returns:
        JSON ``{"status": "ok"}`` with HTTP 200.
    """
    return {"status": "ok"}


@app.post("/transcribe", response_model=TranscribeResponse)
def transcribe_endpoint(body: TranscribeRequest) -> TranscribeResponse:
    """Transcribe an audio file and save the result as a ``.md`` file.

    Runs Whisper inference on the requested audio file and writes a Markdown
    transcript (with metadata header and timestamped paragraphs) to a file with
    the same base name but a ``.md`` extension in the same directory.

    Args:
        body: Validated request body (see :class:`TranscribeRequest`).

    Returns:
        :class:`TranscribeResponse` with ``success=True`` and an ``output``
        summary on success, or ``success=False`` and an ``error`` message on
        failure.

    Raises:
        HTTPException: 400 if the audio file does not exist at the given path.
    """
    audio_path = body.path.strip()
    if not audio_path or not Path(audio_path).is_file():
        raise HTTPException(status_code=400, detail=f"File not found: {audio_path}")

    language: str | None = (
        None if body.language.strip().lower() == "auto" else body.language.strip()
    )

    try:
        model = _get_model(body.model)
        _, auto_fp16 = pick_device_and_precision()

        result = model.transcribe(audio_path, language=language, fp16=auto_fp16)

        markdown = build_transcript_markdown(
            result, audio_path, language, body.model, body.pause_threshold
        )

        md_out = Path(audio_path + ".md")
        md_out.write_text(markdown, encoding="utf-8")

        return TranscribeResponse(
            success=True,
            output=f"Transcribed → {md_out.name}",
        )

    except Exception as exc:
        return TranscribeResponse(success=False, error=str(exc))


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("TRANSCRIBE_PORT", "9000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
