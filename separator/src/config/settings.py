# config/settings.py
from pathlib import Path

from pydantic_settings import BaseSettings

BASE_DIR = Path("/app")


class Settings(BaseSettings):
    """
    Application-wide configuration loaded from environment variables.

    All settings can be overridden via environment variables prefixed
    with ``MUSEP_``, e.g. ``MUSEP_MAX_UPLOAD_SIZE_MB=500``.

    In Docker, all variables are injected by docker-compose from the root
    ``.env`` file — no separate separator ``.env`` is needed.
    """

    # ── Paths ─────────────────────────────────────────────────────────────────
    models_dir: Path = BASE_DIR / "models"
    uploads_dir: Path = BASE_DIR / "uploads"
    outputs_dir: Path = BASE_DIR / "outputs"

    # ── Audio ─────────────────────────────────────────────────────────────────
    sample_rate: int = 44100
    audio_channels: int = 2

    # ── Processing ────────────────────────────────────────────────────────────
    device: str = "cpu"       # "cpu" or "cuda" — auto-detected at runtime
    jobs: int = 1             # parallel jobs for CPU separation
    mp3_bitrate: int = 320    # output MP3 quality

    # ── API ───────────────────────────────────────────────────────────────────
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    max_upload_size_mb: int = 200
    max_file_duration_minutes: int = 20

    # ── CORS / security ───────────────────────────────────────────────────────
    # Comma-separated list of allowed CORS origins.
    # In Docker the main backend proxies all requests, so CORS is only needed
    # during local development (Vite dev server, direct API access).
    cors_origins: str = "http://localhost:8000,http://localhost:3000"

    # Comma-separated list of trusted Host header values.
    # Add your Docker bridge gateway IP if container-to-container calls fail.
    allowed_hosts: str = "localhost,127.0.0.1,*.localhost"

    # ── LALAL.AI ──────────────────────────────────────────────────────────────
    lalalai_api_key: str = ""
    """LALAL.AI license key. Set MUSEP_LALALAI_API_KEY to enable LALAL.AI separation."""

    # ── AudioSep ──────────────────────────────────────────────────────────────
    audiosep_model_dir: Path = BASE_DIR / "models" / "audiosep"
    """Directory where AudioSep checkpoint files are cached."""
    audiosep_checkpoint: str = "audiosep_base_4M_steps.ckpt"
    """Filename of the AudioSep checkpoint inside audiosep_model_dir.
    Download from https://huggingface.co/spaces/Audio-AGI/AudioSep"""

    class Config:
        env_prefix = "MUSEP_"


settings = Settings()

# ── Stem definitions ──────────────────────────────────────────────────────────
# Maps user-facing stem names to Demucs model outputs.
#
# Verified stem support per model (as of demucs v4, archived Jan 2025):
#   htdemucs        → vocals, drums, bass, other
#   htdemucs_ft     → vocals, drums, bass, other
#   htdemucs_6s     → vocals, drums, bass, guitar, piano, other  (best multi-stem)
#   mdx             → vocals, drums, bass, other
#   mdx_extra       → vocals, drums, bass, other
#   mdx_extra_q     → vocals, drums, bass, other  (quantized, lower RAM)
#   umx             → vocals, drums, bass, other
#   umxhq           → vocals, drums, bass, other
#
# NOTE: synthesizer, strings, woodwinds, brass, flute, percussion are defined
# in STEM_GROUPS for UI display only. No currently available open-source model
# separates these as distinct stems — they all fall into the "other" bucket.
# Separating them would require a custom model trained on MoisesDB's wind/strings
# taxonomy. Do not pass these stem names to any model — they will produce silence.

STEM_GROUPS = {
    "vocals": {"label": "🎤 Vocals", "model_stem": "vocals", "color": "#E74C3C"},
    "drums": {"label": "🥁 Drums", "model_stem": "drums", "color": "#E67E22"},
    "bass": {"label": "🎸 Bass", "model_stem": "bass", "color": "#8E44AD"},
    "guitar": {"label": "🎸 Guitar", "model_stem": "guitar", "color": "#2ECC71"},
    "piano": {"label": "🎹 Piano / Keys", "model_stem": "piano", "color": "#3498DB"},
    # ── NOT supported by any current model ────────────────────────────────────
    # These stems fall into the "other" bucket on all available models.
    # They are kept here for UI display and future custom-model support.
    # Do NOT pass them as --two-stems or stem filter arguments to demucs/umx.
    "synthesizer": {
        "label": "🎹 Synthesizer",
        "model_stem": "other",  # maps to "other" — no dedicated model exists
        "color": "#9B59B6",
        "unsupported": True,
    },
    "strings": {
        "label": "🎻 Strings",
        "model_stem": "other",  # maps to "other" — no dedicated model exists
        "color": "#1ABC9C",
        "unsupported": True,
    },
    "woodwinds": {
        "label": "🎷 Woodwinds",
        "model_stem": "other",  # maps to "other" — no dedicated model exists
        "color": "#F39C12",
        "unsupported": True,
    },
    "brass": {
        "label": "🎺 Brass",
        "model_stem": "other",  # maps to "other" — no dedicated model exists
        "color": "#E74C3C",
        "unsupported": True,
    },
    "flute": {
        "label": "🪈 Flute",
        "model_stem": "other",  # maps to "other" — no dedicated model exists
        "color": "#27AE60",
        "unsupported": True,
    },
    "percussion": {
        "label": "🥁 Percussion",
        "model_stem": "other",  # maps to "other" — no dedicated model exists
        "color": "#8E44AD",
        "unsupported": True,
    },
    "other": {"label": "🎵 Other", "model_stem": "other", "color": "#95A5A6"},
}

# Model options available
AVAILABLE_MODELS = {
    "htdemucs_6s": {
        "description": "6 stems: vocals, drums, bass, guitar, piano, other (recommended)",
        "stems": ["vocals", "drums", "bass", "guitar", "piano", "other"],
        "size_mb": 85,
        "quality": "High",
    },
    "mdx_extra": {
        "description": "4 stems: vocals, drums, bass, other — extra training data, ranked 2nd MDX challenge",
        "stems": ["vocals", "drums", "bass", "other"],
        "size_mb": 350,
        "quality": "Very High",
    },
    "htdemucs_ft": {
        "description": "4 stems fine-tuned: vocals, drums, bass, other (best quality for 4 stems)",
        "stems": ["vocals", "drums", "bass", "other"],
        "size_mb": 280,
        "quality": "Very High",
    },
    "htdemucs": {
        "description": "4 stems standard: vocals, drums, bass, other (fastest)",
        "stems": ["vocals", "drums", "bass", "other"],
        "size_mb": 80,
        "quality": "Good",
    },
    "mdx_extra_q": {
        "description": "4 stems: vocals, drums, bass, other — quantized mdx_extra, lower RAM, same quality",
        "stems": ["vocals", "drums", "bass", "other"],
        "size_mb": 90,
        "quality": "Very High",
    },
    "umx": {
        "description": "4 stems with open-unmix: vocals, drums, bass, other — lightweight",
        "stems": ["vocals", "drums", "bass", "other"],
        "size_mb": 50,
        "quality": "Good",
    },
    "umxhq": {
        "description": "4 stems high-quality open-unmix: vocals, drums, bass, other — best open-unmix quality",
        "stems": ["vocals", "drums", "bass", "other"],
        "size_mb": 100,
        "quality": "Very High",
    },
}

DEFAULT_MODEL = "htdemucs_6s"

# ── LALAL.AI stem definitions ─────────────────────────────────────────────────
# Maps our stem IDs → LALAL.AI API stem parameter names.
#
# LALAL.AI processes one stem at a time (target vs. backing track).
# The API filter=2 uses the "Phoenix" neural network — highest available quality.
# Supported stems: vocals, drum, bass, piano, electric_guitar, acoustic_guitar,
#                  synthesizer, strings, wind (covers woodwinds + brass + flute).
#
# Reference: https://www.lalal.ai/api/

LALAI_STEMS = {
    "vocals": {
        "label": "🎤 Vocals",
        "lalai_stem": "vocals",
        "color": "#E74C3C",
    },
    "drums": {
        "label": "🥁 Drums",
        "lalai_stem": "drum",
        "color": "#E67E22",
    },
    "bass": {
        "label": "🎸 Bass",
        "lalai_stem": "bass",
        "color": "#8E44AD",
    },
    "piano": {
        "label": "🎹 Piano / Keys",
        "lalai_stem": "piano",
        "color": "#3498DB",
    },
    "electric_guitar": {
        "label": "🎸 Electric Guitar",
        "lalai_stem": "electric_guitar",
        "color": "#2ECC71",
    },
    "acoustic_guitar": {
        "label": "🎸 Acoustic Guitar",
        "lalai_stem": "acoustic_guitar",
        "color": "#27AE60",
    },
    "synthesizer": {
        "label": "🎹 Synthesizer",
        "lalai_stem": "synthesizer",
        "color": "#9B59B6",
    },
    "strings": {
        "label": "🎻 Strings",
        "lalai_stem": "strings",
        "color": "#1ABC9C",
    },
    "wind": {
        "label": "🎷 Wind (Woodwinds + Brass + Flute)",
        "lalai_stem": "wind",
        "color": "#F39C12",
    },
}

# ── AudioSep stem definitions ─────────────────────────────────────────────────
# AudioSep separates audio based on a natural-language text prompt.
# Any instrument can be targeted — quality depends on how prominent it is
# in the mix. Works best with clear solo or lead instruments.
#
# Each stem maps to a text prompt passed directly to the AudioSep pipeline.
# Install AudioSep: pip install git+https://github.com/Audio-AGI/AudioSep.git
# Model checkpoint: ~1 GB, auto-downloaded to settings.audiosep_model_dir.

AUDIOSEP_STEMS = {
    "woodwinds": {
        "label": "🎷 Woodwinds",
        "prompt": "woodwind instruments playing",
        "color": "#F39C12",
    },
    "flute": {
        "label": "🪈 Flute",
        "prompt": "flute playing",
        "color": "#27AE60",
    },
    "brass": {
        "label": "🎺 Brass",
        "prompt": "brass instruments playing",
        "color": "#E74C3C",
    },
    "strings": {
        "label": "🎻 Strings",
        "prompt": "string instruments playing",
        "color": "#1ABC9C",
    },
    "synthesizer": {
        "label": "🎹 Synthesizer",
        "prompt": "synthesizer playing",
        "color": "#9B59B6",
    },
    "vocals": {
        "label": "🎤 Vocals",
        "prompt": "human singing vocals",
        "color": "#E74C3C",
    },
    "drums": {
        "label": "🥁 Drums",
        "prompt": "drum kit playing",
        "color": "#E67E22",
    },
    "bass": {
        "label": "🎸 Bass",
        "prompt": "bass guitar playing",
        "color": "#8E44AD",
    },
    "guitar": {
        "label": "🎸 Guitar",
        "prompt": "electric guitar playing",
        "color": "#2ECC71",
    },
    "piano": {
        "label": "🎹 Piano",
        "prompt": "piano playing",
        "color": "#3498DB",
    },
}
