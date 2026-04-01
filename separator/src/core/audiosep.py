"""
AudioSep wrapper for text-queried audio source separation.

AudioSep separates any sound from a mix given a natural-language description
(e.g. "flute playing", "brass instruments").  It is uniquely suited to
instruments that specialist models like Demucs do not isolate — woodwinds,
flute, brass, strings, synthesizer.

Prerequisites:
    pip install git+https://github.com/Audio-AGI/AudioSep.git
    pip install torch torchaudio  (already present in this project)

The first run downloads the checkpoint (~1 GB) from HuggingFace to
settings.audiosep_model_dir.  Subsequent runs load it from disk.

Reference paper:
    "Separate Anything You Please" — Liu et al., 2023
    https://arxiv.org/abs/2308.05037
"""

import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Default text prompts ───────────────────────────────────────────────────────
# These are the prompts passed to AudioSep for each stem ID.
# They can be overridden by callers — stem definitions in settings.py
# carry an authoritative copy used by the UI.
DEFAULT_PROMPTS: Dict[str, str] = {
    "woodwinds": "woodwind instruments playing",
    "flute": "flute playing",
    "brass": "brass instruments playing",
    "strings": "string instruments playing",
    "synthesizer": "synthesizer playing",
    "vocals": "human singing vocals",
    "drums": "drum kit playing",
    "bass": "bass guitar playing",
    "guitar": "electric guitar playing",
    "piano": "piano playing",
}


class AudioSepError(Exception):
    """Raised when AudioSep is unavailable or separation fails."""


class AudioSepSeparator:
    """
    Local stem separator backed by the AudioSep text-query model.

    AudioSep must be installed and the checkpoint available before this
    class can be used.  Instantiation lazily imports the library so that
    the rest of the application starts normally even when AudioSep is not
    installed — only the AudioSep page will surface the error.

    Args:
        model_dir:   Directory containing (or where to download) the
                     AudioSep checkpoint file.
        checkpoint:  Filename of the checkpoint inside *model_dir*.
        device:      PyTorch device string ("cpu", "cuda", "mps").
    """

    def __init__(
        self,
        model_dir: Path,
        checkpoint: str = "checkpoint.ckpt",
        device: str = "cpu",
    ) -> None:
        self._model_dir = Path(model_dir)
        self._checkpoint = checkpoint
        self._device = device
        self._pipeline = None  # lazy-loaded on first separate() call
        logger.info(
            "AudioSepSeparator configured (model_dir=%s device=%s)",
            model_dir,
            device,
        )

    # ── Availability check ────────────────────────────────────────────────────

    @staticmethod
    def is_available() -> bool:
        """
        Return True if the AudioSep pipeline module is on PYTHONPATH.

        Uses importlib.util.find_spec instead of actually importing the module
        to avoid triggering the CLAP_Encoder default-argument instantiation
        that happens at class-definition time inside models/audiosep.py —
        which would require the CLAP checkpoint to already be on disk.
        """
        try:
            import importlib.util

            spec = importlib.util.find_spec("pipeline")
            return spec is not None and spec.origin is not None
        except Exception:
            return False

    def _checkpoint_path(self) -> Path:
        """Return the full path to the checkpoint file."""
        return self._model_dir / self._checkpoint

    # ── Model loading ─────────────────────────────────────────────────────────

    def _load_pipeline(self):
        """
        Import AudioSep and load the model into memory (lazy, once).

        Uses ``pipeline.build_audiosep(config_yaml, checkpoint_path, device)``
        from the cloned AudioSep repository (PYTHONPATH=/opt/audiosep).
        The config YAML is resolved relative to the pipeline module's location.

        Raises:
            AudioSepError: If the package is not installed, the checkpoint
                           is missing, or the config YAML is not found.
        """
        if self._pipeline is not None:
            return  # already loaded

        ckpt = self._checkpoint_path()
        logger.info("Loading AudioSep model from %s (device=%s)", ckpt, self._device)

        if not ckpt.exists():
            raise AudioSepError(
                f"AudioSep checkpoint not found: {ckpt}\n"
                f"Download it from https://huggingface.co/audio-agi/AudioSep and "
                f"place it at {ckpt}"
            )

        try:
            import importlib.util

            spec = importlib.util.find_spec("pipeline")
            if spec is None or spec.origin is None:
                raise AudioSepError(
                    "AudioSep pipeline module not found. "
                    "Ensure PYTHONPATH includes the AudioSep repo root."
                )
            audiosep_dir = Path(spec.origin).parent
            config_yaml = audiosep_dir / "config" / "audiosep_base.yaml"
            if not config_yaml.exists():
                raise AudioSepError(
                    f"AudioSep config YAML not found: {config_yaml}"
                )
            # AudioSep's CLAP_Encoder uses a relative path
            # "checkpoint/music_speech_audioset_epoch_15_esc_89.98.pt".
            # IMPORTANT: chdir BEFORE importing pipeline, because the import
            # evaluates CLAP_Encoder() as a class-level default argument,
            # which immediately calls create_model() and checks os.path.exists()
            # on that relative path. If CWD is wrong at import time it fails.
            # PyTorch 2.6 changed torch.load default to weights_only=True,
            # which blocks numpy types embedded in the CLAP checkpoint.
            # Patch torch.load to use weights_only=False (checkpoint is trusted).
            try:
                import torch as _torch
                import functools as _functools
                _orig_load = _torch.load
                @_functools.wraps(_orig_load)
                def _patched_load(*args, **kwargs):
                    kwargs.setdefault("weights_only", False)
                    return _orig_load(*args, **kwargs)
                _torch.load = _patched_load
                logger.debug("Patched torch.load to weights_only=False for CLAP")
            except Exception as _e:
                logger.warning("Could not patch torch.load: %s", _e)

            logger.debug("Config: %s, CWD → %s", config_yaml, audiosep_dir)
            old_cwd = os.getcwd()
            try:
                os.chdir(audiosep_dir)
                from pipeline import build_audiosep  # type: ignore  # noqa: PLC0415
                self._pipeline = build_audiosep(
                    str(config_yaml), str(ckpt), self._device
                )
            finally:
                os.chdir(old_cwd)
            logger.info("AudioSep model loaded successfully")

        except AudioSepError:
            raise
        except Exception as exc:
            raise AudioSepError(f"Failed to load AudioSep model: {exc}") from exc

    # ── Separation ────────────────────────────────────────────────────────────

    def _run_inference(
        self,
        audio_path: Path,
        text_prompt: str,
        output_path: Path,
    ) -> None:
        """
        Run AudioSep inference for a single text prompt.

        Tries the Python API first; falls back to the CLI script if the
        Python API is unavailable in the installed version.

        Args:
            audio_path:  Input audio file (WAV preferred).
            text_prompt: Natural-language description of the target sound.
            output_path: Where to write the separated WAV.

        Raises:
            AudioSepError: On inference failure.
        """
        logger.info(
            "AudioSep inference: prompt=%r input=%s output=%s",
            text_prompt,
            audio_path.name,
            output_path.name,
        )

        try:
            self._load_pipeline()
        except AudioSepError:
            raise

        try:
            from pipeline import separate_audio  # type: ignore

            separate_audio(
                self._pipeline,
                str(audio_path),
                text_prompt,
                str(output_path),
                self._device,
                use_chunk=True,
            )
            logger.debug("separate_audio() succeeded")
        except Exception as exc:
            logger.error("AudioSep inference failed: %s", exc)
            raise AudioSepError(f"AudioSep inference failed: {exc}") from exc

    def _convert_to_mp3(self, wav_path: Path, mp3_path: Path) -> None:
        """
        Convert a WAV file to MP3 using FFmpeg.

        Args:
            wav_path: Source WAV file.
            mp3_path: Destination MP3 path.

        Raises:
            AudioSepError: If FFmpeg is not on PATH or conversion fails.
        """
        logger.debug("Converting %s → %s", wav_path.name, mp3_path.name)
        cmd = [
            "ffmpeg", "-y",
            "-i", str(wav_path),
            "-b:a", "320k",
            str(mp3_path),
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.error("FFmpeg conversion failed:\n%s", result.stderr)
            raise AudioSepError(
                f"FFmpeg conversion to MP3 failed: {result.stderr[-300:]}"
            )
        logger.debug("MP3 conversion complete: %s", mp3_path.name)

    # ── Public API ────────────────────────────────────────────────────────────

    def separate(
        self,
        input_path: Path,
        output_dir: Path,
        stems: List[str],
        prompts: Optional[Dict[str, str]] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> Dict[str, Path]:
        """
        Separate *input_path* into the requested stems using AudioSep.

        Each stem is processed independently with its own text prompt.
        Results are saved as MP3 files in *output_dir*.

        Args:
            input_path:        Path to the source audio file.
            output_dir:        Directory where stem files will be written.
            stems:             List of stem IDs to extract.
            prompts:           Optional mapping of stem_id → text prompt.
                               Defaults to :data:`DEFAULT_PROMPTS`.
            progress_callback: Optional ``(pct: int, msg: str)`` callback.

        Returns:
            Mapping of ``stem_id → Path`` for every extracted stem.

        Raises:
            AudioSepError: If AudioSep is not installed, the checkpoint is
                           missing, or inference fails.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        effective_prompts = {**DEFAULT_PROMPTS, **(prompts or {})}
        results: Dict[str, Path] = {}
        total = len(stems)

        logger.info(
            "separate() → stems=%s input=%s", stems, input_path.name
        )

        if progress_callback:
            progress_callback(2, "🔊 Initialising AudioSep model…")

        # Load model once before the loop (lazy)
        try:
            self._load_pipeline()
        except AudioSepError as exc:
            logger.error("AudioSep model load failed: %s", exc)
            raise

        with tempfile.TemporaryDirectory(prefix="audiosep_") as tmp:
            tmp_path = Path(tmp)

            for idx, stem_id in enumerate(stems):
                prompt = effective_prompts.get(stem_id)
                if prompt is None:
                    logger.warning(
                        "No prompt for stem '%s' — skipping", stem_id
                    )
                    continue

                base_pct = int(10 + (idx / total) * 80)
                if progress_callback:
                    progress_callback(
                        base_pct,
                        f"🔊 Separating '{stem_id}' — \"{prompt}\"…",
                    )

                wav_out = tmp_path / f"{stem_id}.wav"
                mp3_out = output_dir / f"{stem_id}.mp3"

                try:
                    self._run_inference(input_path, prompt, wav_out)
                except AudioSepError as exc:
                    logger.error(
                        "Inference failed for stem '%s': %s", stem_id, exc
                    )
                    continue

                if not wav_out.exists():
                    logger.warning(
                        "AudioSep produced no output for '%s'", stem_id
                    )
                    continue

                try:
                    self._convert_to_mp3(wav_out, mp3_out)
                except AudioSepError as exc:
                    logger.error(
                        "MP3 conversion failed for '%s': %s", stem_id, exc
                    )
                    # Keep the WAV as fallback
                    import shutil
                    wav_fallback = output_dir / f"{stem_id}.wav"
                    shutil.copy(wav_out, wav_fallback)
                    results[stem_id] = wav_fallback
                    continue

                results[stem_id] = mp3_out
                done_pct = int(10 + ((idx + 1) / total) * 80)
                if progress_callback:
                    progress_callback(done_pct, f"✅ '{stem_id}' extracted")

                logger.info(
                    "Stem '%s' saved → %s (%.1f MB)",
                    stem_id,
                    mp3_out.name,
                    mp3_out.stat().st_size / 1_024 / 1_024,
                )

        logger.info(
            "separate() complete — %d/%d stems extracted", len(results), total
        )

        if progress_callback:
            progress_callback(95, f"✅ {len(results)}/{total} stems extracted")

        return results
