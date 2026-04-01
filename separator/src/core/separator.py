# core/separator.py
"""
Core audio separation engine using Demucs and open-unmix models.
Supports multiple stem separation approaches.
"""

import logging
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class SeparationError(Exception):
    pass


class AudioSeparator:
    """
    Wraps Demucs and open-unmix for multi-stem separation.
    Handles model selection, audio conversion, progress tracking, and output packaging.
    """

    SUPPORTED_FORMATS = {
        ".mp3",
        ".wav",
        ".flac",
        ".ogg",
        ".m4a",
        ".aac",
        ".wma",
        ".aiff",
    }

    def __init__(
        self,
        model: str = "htdemucs_6s",
        device: str = "cpu",
        jobs: int = 1,
        mp3_output: bool = True,
        mp3_bitrate: int = 320,
    ):
        self.model = model
        self.device = device
        self.jobs = jobs
        self.mp3_output = mp3_output
        self.mp3_bitrate = mp3_bitrate

        # Determine which separator to use
        if model.startswith("umx"):
            self.separator_type = "open_unmix"
            self._verify_open_unmix()
        else:
            self.separator_type = "demucs"
            self._verify_demucs()

    def _verify_demucs(self):
        """Check that demucs is installed and accessible."""
        result = subprocess.run(
            ["python", "-m", "demucs", "--help"], capture_output=True, text=True
        )
        if result.returncode != 0:
            raise SeparationError("Demucs is not installed. Run: pip install demucs")

    def _verify_open_unmix(self):
        """Check that open-unmix is installed and accessible."""
        try:
            import openunmix

            logger.info(f"Open-unmix version: {openunmix.__version__}")
        except ImportError:
            raise SeparationError(
                "Open-unmix is not installed. Run: pip install open-unmix"
            )

    def _verify_ffmpeg(self):
        """Check that ffmpeg is available for audio conversion."""
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True)
        return result.returncode == 0

    def _convert_to_wav(self, input_path: Path, output_dir: Path) -> Path:
        """Convert any audio format to WAV using ffmpeg."""
        output_path = output_dir / f"{input_path.stem}.wav"
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(input_path),
            "-ar",
            "44100",  # 44.1kHz sample rate
            "-ac",
            "2",  # stereo
            "-acodec",
            "pcm_s16le",
            str(output_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise SeparationError(f"Audio conversion failed: {result.stderr}")
        return output_path

    def get_audio_duration(self, audio_path: Path) -> float:
        """Get audio duration in seconds using ffprobe."""
        cmd = [
            "ffprobe",
            "-v",
            "quiet",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        try:
            return float(result.stdout.strip())
        except (ValueError, AttributeError):
            return 0.0

    def separate(
        self,
        input_path: Path,
        output_dir: Path,
        stems: Optional[List[str]] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> Dict[str, Path]:
        """
        Separate an audio file into stems.

        Args:
            input_path: Path to input audio file
            output_dir: Directory to save separated stems
            stems: List of stem names to extract (None = all available)
            progress_callback: Optional callback(percent, message) for progress updates

        Returns:
            Dict mapping stem names to output file paths
        """
        input_path = Path(input_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        if not input_path.exists():
            raise SeparationError(f"Input file not found: {input_path}")

        suffix = input_path.suffix.lower()
        if suffix not in self.SUPPORTED_FORMATS:
            raise SeparationError(
                f"Unsupported format: {suffix}. "
                f"Supported: {', '.join(self.SUPPORTED_FORMATS)}"
            )

        if progress_callback:
            progress_callback(5, "Preparing audio file...")

        # Use a temp dir for intermediate files
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            # Convert to WAV if needed for best compatibility
            if suffix != ".wav":
                if self._verify_ffmpeg():
                    audio_path = self._convert_to_wav(input_path, tmp_path)
                else:
                    audio_path = input_path  # Hope for the best
            else:
                audio_path = input_path

            if progress_callback:
                progress_callback(10, f"Running {self.model} model...")

            if self.separator_type == "demucs":
                return self._separate_demucs(
                    audio_path, output_dir, stems, progress_callback, tmp_path
                )
            elif self.separator_type == "open_unmix":
                return self._separate_open_unmix(
                    audio_path, output_dir, stems, progress_callback, tmp_path
                )
            else:
                raise SeparationError(f"Unknown separator type: {self.separator_type}")

    def _separate_demucs(
        self,
        audio_path: Path,
        output_dir: Path,
        stems: Optional[List[str]],
        progress_callback: Optional[Callable],
        tmp_path: Path,
    ) -> Dict[str, Path]:
        """Separate using Demucs."""
        # Build demucs command
        demucs_output = tmp_path / "demucs_out"
        cmd = [
            "python",
            "-m",
            "demucs",
            "--name",
            self.model,
            "--out",
            str(demucs_output),
            "--device",
            self.device,
            "-j",
            str(self.jobs),
        ]

        if self.mp3_output:
            cmd += ["--mp3", "--mp3-bitrate", str(self.mp3_bitrate)]

        # If only specific stems needed, use two-stems mode for efficiency
        # For full separation, just run the model on all stems
        cmd.append(str(audio_path))

        logger.info(f"Running: {' '.join(cmd)}")
        start_time = time.time()

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        # Stream output and parse progress
        output_lines = []
        for line in iter(process.stdout.readline, ""):
            line = line.strip()
            output_lines.append(line)
            logger.debug(f"Demucs: {line}")

            if progress_callback:
                if "Separated" in line or "Separating" in line:
                    progress_callback(50, "Separating stems...")
                elif "chunk" in line.lower():
                    progress_callback(70, "Processing audio chunks...")

        process.wait()

        if process.returncode != 0:
            error_output = "\n".join(output_lines[-20:])
            raise SeparationError(
                f"Demucs separation failed (exit code {process.returncode}).\n"
                f"Last output:\n{error_output}"
            )

        elapsed = time.time() - start_time
        logger.info(f"Demucs finished in {elapsed:.1f}s")

        if progress_callback:
            progress_callback(85, "Collecting output stems...")

        # Collect output files
        # Demucs outputs to: {out}/{model}/{track_name}/
        track_name = audio_path.stem
        stem_source_dir = demucs_output / self.model / track_name

        if not stem_source_dir.exists():
            # Try without track name (some versions differ)
            candidates = list(demucs_output.rglob("*.mp3")) + list(
                demucs_output.rglob("*.wav")
            )
            if not candidates:
                raise SeparationError(
                    f"No output files found. Expected dir: {stem_source_dir}"
                )
            stem_source_dir = candidates[0].parent

        # Move stems to final output dir
        result_stems = {}
        ext = ".mp3" if self.mp3_output else ".wav"

        for stem_file in stem_source_dir.iterdir():
            if stem_file.suffix in {".mp3", ".wav", ".flac"}:
                stem_name = stem_file.stem  # e.g. "vocals", "drums", etc.

                # Filter to requested stems if specified
                if stems and stem_name not in stems:
                    continue

                # Copy to output dir with clean name
                safe_track = "".join(
                    c for c in audio_path.stem if c.isalnum() or c in " -_"
                ).strip()
                output_filename = f"{safe_track}_{stem_name}{stem_file.suffix}"
                output_path = output_dir / output_filename

                shutil.copy2(stem_file, output_path)
                result_stems[stem_name] = output_path
                logger.info(f"  → {stem_name}: {output_path}")

        if not result_stems:
            raise SeparationError("No stems were produced. Check model compatibility.")

        # Check if all requested stems were produced
        if stems:
            missing_stems = [s for s in stems if s not in result_stems]
            if missing_stems:
                logger.warning(f"Requested stems not produced: {missing_stems}")
                # Don't fail, just log the warning

        if progress_callback:
            progress_callback(100, f"Done! {len(result_stems)} stems extracted.")

        return result_stems

    def _separate_open_unmix(
        self,
        audio_path: Path,
        output_dir: Path,
        stems: Optional[List[str]],
        progress_callback: Optional[Callable],
        tmp_path: Path,
    ) -> Dict[str, Path]:
        """Separate using open-unmix."""
        import librosa
        import openunmix
        import soundfile as sf
        import torch

        if progress_callback:
            progress_callback(20, "Loading open-unmix model...")

        # Load the appropriate open-unmix model
        if self.model == "umx":
            separator = openunmix.umx()
        elif self.model == "umxhq":
            separator = openunmix.umxhq()
        else:
            separator = openunmix.umx()  # default

        if progress_callback:
            progress_callback(40, "Loading audio...")

        # Load audio
        audio, rate = librosa.load(str(audio_path), sr=44100, mono=False)
        if audio.ndim == 1:
            audio = audio[None, :]  # Add channel dimension
        elif audio.shape[0] > 2:
            audio = audio[:2, :]  # Take first 2 channels

        if progress_callback:
            progress_callback(60, "Separating stems...")

        # Separate
        with torch.no_grad():
            estimates = separator(torch.tensor(audio).float())

        if progress_callback:
            progress_callback(80, "Saving stems...")

        # Save stems
        result_stems = {}
        stem_names = ["vocals", "drums", "bass", "guitar", "piano", "other"]

        for i, stem_name in enumerate(stem_names):
            if stems and stem_name not in stems:
                continue

            stem_audio = estimates[stem_name].numpy()

            # Convert to output format
            safe_track = "".join(
                c for c in audio_path.stem if c.isalnum() or c in " -_"
            ).strip()

            if self.mp3_output:
                # For MP3, we need to save as WAV first then convert
                wav_path = tmp_path / f"{stem_name}.wav"
                sf.write(str(wav_path), stem_audio.T, rate)

                # Convert to MP3
                output_filename = f"{safe_track}_{stem_name}.mp3"
                output_path = output_dir / output_filename

                cmd = [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(wav_path),
                    "-b:a",
                    f"{self.mp3_bitrate}k",
                    str(output_path),
                ]
                subprocess.run(cmd, check=True, capture_output=True)
            else:
                output_filename = f"{safe_track}_{stem_name}.wav"
                output_path = output_dir / output_filename
                sf.write(str(output_path), stem_audio.T, rate)

            result_stems[stem_name] = output_path
            logger.info(f"  → {stem_name}: {output_path}")

        if progress_callback:
            progress_callback(100, f"Done! {len(result_stems)} stems extracted.")

        return result_stems


def detect_device() -> str:
    """Auto-detect best available compute device."""
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"  # Apple Silicon
    except ImportError:
        pass
    return "cpu"
