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

    def _preprocess_input(self, audio_path: Path, dest: Path) -> Path:
        """
        Convert *audio_path* to 32 kHz mono WAV for AudioSep.

        AudioSep's native sample rate is 32 kHz mono.  When the input is
        any other format or rate, AudioSep resamples internally using
        torchaudio's default algorithm, which introduces more artifacts than
        ffmpeg's high-quality SoX resampler.  Pre-converting here gives the
        model the cleanest possible input.

        If the input is already a 32 kHz mono WAV the file is copied as-is
        to avoid an unnecessary re-encode.

        Args:
            audio_path: Original uploaded audio file.
            dest:       Destination path for the pre-processed WAV.

        Returns:
            Path to the pre-processed file (always *dest*).

        Raises:
            AudioSepError: If ffmpeg is not on PATH or conversion fails.
        """
        import shutil
        import torchaudio as _ta

        try:
            info = _ta.info(str(audio_path))
            already_ok = (
                audio_path.suffix.lower() == ".wav"
                and info.sample_rate == 32000
                and info.num_channels == 1
            )
        except Exception:
            already_ok = False

        if already_ok:
            shutil.copy2(str(audio_path), str(dest))
            return dest

        cmd = [
            "ffmpeg", "-y",
            "-i", str(audio_path),
            "-ar", "32000",
            "-ac", "1",
            "-sample_fmt", "s16",
            str(dest),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise AudioSepError(
                f"Input pre-processing failed: {result.stderr[-300:]}"
            )
        logger.debug(
            "Pre-processed input → 32 kHz mono WAV: %s (%.1f MB)",
            dest.name,
            dest.stat().st_size / 1_024 / 1_024,
        )
        return dest

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
            import torchaudio as _ta

            # use_chunk=True splits audio into overlapping windows — necessary
            # for long tracks but adds ~30% overhead on short clips.
            # Disable for files under 3 minutes to avoid the chunking penalty.
            info = _ta.info(str(audio_path))
            duration_s = info.num_frames / info.sample_rate
            use_chunk = duration_s > 180

            separate_audio(
                self._pipeline,
                str(audio_path),
                text_prompt,
                str(output_path),
                self._device,
                use_chunk=use_chunk,
            )
            logger.debug("separate_audio() succeeded (use_chunk=%s, duration=%.1fs)", use_chunk, duration_s)
        except Exception as exc:
            logger.error("AudioSep inference failed: %s", exc)
            raise AudioSepError(f"AudioSep inference failed: {exc}") from exc

    def _convert_audio(
        self,
        wav_path: Path,
        output_path: Path,
        output_format: str,
        mp3_bitrate: int,
    ) -> None:
        """
        Convert a WAV file to the requested output format using FFmpeg.

        For WAV output the source file is moved directly (no re-encoding).
        For FLAC and MP3 FFmpeg resamples to 44100 Hz stereo to avoid
        sample-rate mismatch artifacts (AudioSep outputs at 32 kHz).

        Args:
            wav_path:      Source WAV produced by AudioSep (32 kHz).
            output_path:   Destination file path (extension determines format).
            output_format: One of ``"wav"``, ``"flac"``, or ``"mp3"``.
            mp3_bitrate:   Target MP3 bitrate in kbps (used only for ``"mp3"``).

        Raises:
            AudioSepError: If FFmpeg is not on PATH or conversion fails.
        """
        import shutil

        if output_format == "wav":
            shutil.move(str(wav_path), str(output_path))
            logger.debug("WAV move complete: %s", output_path.name)
            return

        logger.debug("Converting %s → %s", wav_path.name, output_path.name)

        if output_format == "flac":
            cmd = [
                "ffmpeg", "-y",
                "-i", str(wav_path),
                "-ar", "44100",
                "-ac", "2",
                str(output_path),
            ]
        else:  # mp3
            cmd = [
                "ffmpeg", "-y",
                "-i", str(wav_path),
                "-ar", "44100",
                "-ac", "2",
                "-b:a", f"{mp3_bitrate}k",
                str(output_path),
            ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error("FFmpeg conversion failed:\n%s", result.stderr)
            raise AudioSepError(
                f"FFmpeg conversion to {output_format.upper()} failed: {result.stderr[-300:]}"
            )
        logger.debug("%s conversion complete: %s", output_format.upper(), output_path.name)

    # ── Public API ────────────────────────────────────────────────────────────

    def separate(
        self,
        input_path: Path,
        output_dir: Path,
        stems: List[str],
        prompts: Optional[Dict[str, str]] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        output_format: str = "wav",
        mp3_bitrate: int = 320,
    ) -> Dict[str, Path]:
        """
        Separate *input_path* into the requested stems using AudioSep.

        Each stem is processed independently with its own text prompt.
        Results are saved in *output_dir* using the requested format.

        Args:
            input_path:        Path to the source audio file.
            output_dir:        Directory where stem files will be written.
            stems:             List of stem IDs to extract.
            prompts:           Optional mapping of stem_id → text prompt.
                               Defaults to :data:`DEFAULT_PROMPTS`.
            progress_callback: Optional ``(pct: int, msg: str)`` callback.
            output_format:     Output container: ``"wav"``, ``"flac"``, or ``"mp3"``.
                               Defaults to ``"wav"`` for lossless quality.
            mp3_bitrate:       Target bitrate in kbps when *output_format* is ``"mp3"``.

        Returns:
            Mapping of ``stem_id → Path`` for every extracted stem.

        Raises:
            AudioSepError: If AudioSep is not installed, the checkpoint is
                           missing, or inference fails.
        """
        fmt = output_format if output_format in {"wav", "flac", "mp3"} else "wav"
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

            # Pre-process input once — avoids torchaudio resampling artifacts
            if progress_callback:
                progress_callback(5, "🔧 Pre-processing audio…")
            try:
                clean_input = self._preprocess_input(input_path, tmp_path / "input_32k.wav")
            except AudioSepError as exc:
                logger.warning("Input pre-processing failed (%s) — using original", exc)
                clean_input = input_path

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
                final_out = output_dir / f"{stem_id}.{fmt}"

                try:
                    self._run_inference(clean_input, prompt, wav_out)
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
                    self._convert_audio(wav_out, final_out, fmt, mp3_bitrate)
                except AudioSepError as exc:
                    logger.error(
                        "Audio conversion failed for '%s': %s", stem_id, exc
                    )
                    continue

                results[stem_id] = final_out
                done_pct = int(10 + ((idx + 1) / total) * 80)
                if progress_callback:
                    progress_callback(done_pct, f"✅ '{stem_id}' extracted")

                logger.info(
                    "Stem '%s' saved → %s (%.1f MB)",
                    stem_id,
                    final_out.name,
                    final_out.stat().st_size / 1_024 / 1_024,
                )

        logger.info(
            "separate() complete — %d/%d stems extracted", len(results), total
        )

        if progress_callback:
            progress_callback(95, f"✅ {len(results)}/{total} stems extracted")

        return results
