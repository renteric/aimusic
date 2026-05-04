"""
LALAL.AI API v1 client for cloud-based stem separation.

LALAL.AI v1 API (current):
  - Upload:  POST /api/v1/upload/          raw binary, X-License-Key auth
  - Split:   POST /api/v1/split/stem_separator/  one task per stem
  - Check:   POST /api/v1/check/           batch poll by task_id list
  - Result:  tracks[].url  where tracks[].type == "stem"

Prerequisites:
    pip install requests
    Set MUSEP_LALALAI_API_KEY in your environment or .env file.
"""

import logging
import subprocess
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

import requests as _requests

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
_API = "https://www.lalal.ai/api/v1"
LALAI_POLL_INTERVAL_S = 5
LALAI_MAX_WAIT_S = 600

# Maps our internal stem IDs → LALAL.AI v1 stem parameter values.
STEM_TO_LALAI: Dict[str, str] = {
    "vocals":          "vocals",
    "drums":           "drum",
    "bass":            "bass",
    "piano":           "piano",
    "electric_guitar": "electric_guitar",
    "acoustic_guitar": "acoustic_guitar",
    "guitar":          "electric_guitar",
    "synthesizer":     "synthesizer",
    "strings":         "strings",
    "wind":            "wind",
    "woodwinds":       "wind",
    "flute":           "wind",
    "brass":           "wind",
}


class LalaiError(Exception):
    """Raised when LALAL.AI returns an error or a request times out."""


class LalaiSeparator:
    """
    Cloud-based stem separator backed by the LALAL.AI REST API v1.

    Uploads the source file once; processes each requested stem sequentially
    via /api/v1/split/stem_separator/; polls /api/v1/check/ until done.

    Args:
        api_key: LALAL.AI license key (X-License-Key header).
    """

    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise LalaiError(
                "LALAL.AI API key is missing. "
                "Set the MUSEP_LALALAI_API_KEY environment variable."
            )
        self._api_key = api_key
        self._auth = {"X-License-Key": api_key}
        logger.info("LalaiSeparator ready (key=...%s)", api_key[-4:])

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _check_response(self, resp: _requests.Response) -> dict:
        """Raise LalaiError on non-2xx or API-level error field."""
        if resp.status_code not in (200, 201):
            raise LalaiError(
                f"LALAL.AI HTTP {resp.status_code}: {resp.text[:300]}"
            )
        data: dict = resp.json()
        if "detail" in data and isinstance(data["detail"], str):
            raise LalaiError(f"LALAL.AI error: {data['detail']}")
        if data.get("status") == "error":
            raise LalaiError(f"LALAL.AI error: {data.get('error', data)}")
        return data

    # ── Upload ────────────────────────────────────────────────────────────────

    def _upload(self, audio_path: Path) -> str:
        """
        Upload an audio file as raw binary to /api/v1/upload/.

        Args:
            audio_path: Local path to the source audio file.

        Returns:
            source_id (str): File identifier for subsequent split calls.
        """
        size_mb = audio_path.stat().st_size / 1_024 / 1_024
        logger.info("Uploading %s (%.1f MB) to LALAL.AI", audio_path.name, size_mb)

        headers = {
            **self._auth,
            "Content-Type": "application/octet-stream",
            "Content-Disposition": f"attachment; filename={audio_path.name}",
        }

        with open(audio_path, "rb") as fh:
            resp = _requests.post(
                f"{_API}/upload/",
                headers=headers,
                data=fh,
                timeout=300.0,
            )

        data = self._check_response(resp)
        source_id = data.get("id")
        if not source_id:
            raise LalaiError(f"LALAL.AI upload: no id in response — {data}")

        logger.info("Upload complete, source_id=%s duration=%ss", source_id, data.get("duration"))
        return str(source_id)

    # ── Split ─────────────────────────────────────────────────────────────────

    def _start_split(self, source_id: str, lalai_stem: str) -> str:
        """
        Start a stem separation task via /api/v1/split/stem_separator/.

        Args:
            source_id:  ID returned by :meth:`_upload`.
            lalai_stem: LALAL.AI stem name (e.g. "vocals", "drum").

        Returns:
            task_id (str): Identifier for polling via /api/v1/check/.
        """
        logger.info("Starting split: source_id=%s stem=%s", source_id, lalai_stem)

        resp = _requests.post(
            f"{_API}/split/stem_separator/",
            headers={**self._auth, "Content-Type": "application/json"},
            json={"source_id": source_id, "presets": {"stem": lalai_stem}},
            timeout=60.0,
        )

        data = self._check_response(resp)
        task_id = data.get("task_id")
        if not task_id:
            raise LalaiError(f"LALAL.AI split: no task_id in response — {data}")

        logger.info("Split task started, task_id=%s", task_id)
        return str(task_id)

    # ── Poll ──────────────────────────────────────────────────────────────────

    def _poll_until_done(
        self,
        task_id: str,
        stem_label: str = "stem",
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> dict:
        """
        Block until the LALAL.AI task finishes via /api/v1/check/.

        Args:
            task_id:           Task ID from :meth:`_start_split`.
            stem_label:        Human-readable name for log messages.
            progress_callback: Optional ``(pct: int, msg: str)`` callback.

        Returns:
            Result dict containing a ``tracks`` list with download URLs.
        """
        elapsed = 0

        while elapsed < LALAI_MAX_WAIT_S:
            time.sleep(LALAI_POLL_INTERVAL_S)
            elapsed += LALAI_POLL_INTERVAL_S

            resp = _requests.post(
                f"{_API}/check/",
                headers={**self._auth, "Content-Type": "application/json"},
                json={"task_ids": [task_id]},
                timeout=30.0,
            )
            data = self._check_response(resp)

            task_result = data.get("result", {}).get(task_id, {})
            status = task_result.get("status", "unknown")

            logger.debug("Poll: task=%s stem=%s status=%s elapsed=%ds",
                         task_id, stem_label, status, elapsed)

            if status == "success":
                result = task_result.get("result", {})
                if not result:
                    raise LalaiError(
                        f"LALAL.AI success but result missing: {task_result}"
                    )
                logger.info("Stem '%s' ready after %ds", stem_label, elapsed)
                return result

            if status in ("error", "cancelled", "server_error"):
                raise LalaiError(
                    f"LALAL.AI task failed for '{stem_label}': {task_result}"
                )

            if progress_callback:
                pct = min(85, int(elapsed / LALAI_MAX_WAIT_S * 85))
                progress_callback(
                    pct,
                    f"⏳ LALAL.AI processing '{stem_label}'… ({elapsed}s)",
                )

        raise LalaiError(
            f"LALAL.AI timed out after {LALAI_MAX_WAIT_S}s for '{stem_label}'"
        )

    # ── Download ──────────────────────────────────────────────────────────────

    def _download(self, url: str, dest: Path) -> None:
        """
        Download a stem track from the LALAL.AI CDN.

        Args:
            url:  URL from tracks[].url where tracks[].type == "stem".
            dest: Local path to write the downloaded file.
        """
        logger.info("Downloading '%s' → %s", url, dest.name)

        resp = _requests.get(url, timeout=120.0)
        if resp.status_code != 200:
            raise LalaiError(
                f"Failed to download stem from LALAL.AI: HTTP {resp.status_code}"
            )

        dest.write_bytes(resp.content)
        logger.info("Downloaded %s (%.1f MB)", dest.name,
                    dest.stat().st_size / 1_024 / 1_024)

    # ── Public API ────────────────────────────────────────────────────────────

    def _convert_to_wav(self, mp3_path: Path, wav_path: Path) -> None:
        """
        Convert an MP3 file to WAV using FFmpeg.

        Args:
            mp3_path: Source MP3 file downloaded from LALAL.AI CDN.
            wav_path: Destination WAV path.

        Raises:
            LalaiError: If FFmpeg is not on PATH or conversion fails.
        """
        logger.debug("Converting %s → %s", mp3_path.name, wav_path.name)
        cmd = [
            "ffmpeg", "-y",
            "-i", str(mp3_path),
            "-ar", "44100",
            "-ac", "2",
            str(wav_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error("FFmpeg WAV conversion failed:\n%s", result.stderr)
            raise LalaiError(f"FFmpeg conversion to WAV failed: {result.stderr[-300:]}")
        mp3_path.unlink(missing_ok=True)
        logger.debug("WAV conversion complete: %s", wav_path.name)

    def separate(
        self,
        input_path: Path,
        output_dir: Path,
        stems: List[str],
        progress_callback: Optional[Callable[[int, str], None]] = None,
        output_format: str = "mp3",
    ) -> Dict[str, Path]:
        """
        Separate *input_path* into the requested stems using LALAL.AI v1.

        LALAL.AI always returns MP3 from its CDN.  When *output_format* is
        ``"wav"`` the downloaded MP3 is converted to WAV via FFmpeg and the
        intermediate MP3 is deleted.

        Args:
            input_path:        Source audio file.
            output_dir:        Directory for downloaded stem files.
            stems:             Stem IDs to extract (must be in STEM_TO_LALAI).
            progress_callback: Optional ``(pct: int, msg: str)`` callback.
            output_format:     ``"mp3"`` (default) or ``"wav"``.

        Returns:
            Mapping of stem_id → Path for every successfully downloaded stem.
        """
        fmt = output_format if output_format in {"mp3", "wav"} else "mp3"
        output_dir.mkdir(parents=True, exist_ok=True)
        results: Dict[str, Path] = {}

        logger.info("separate() stems=%s input=%s format=%s", stems, input_path.name, fmt)

        if progress_callback:
            progress_callback(2, "📤 Uploading to LALAL.AI…")

        source_id = self._upload(input_path)
        total = len(stems)

        for idx, stem_id in enumerate(stems):
            lalai_stem = STEM_TO_LALAI.get(stem_id)
            if lalai_stem is None:
                logger.warning("No LALAL.AI mapping for stem '%s' — skipping", stem_id)
                continue

            base_pct = int(10 + (idx / total) * 80)
            if progress_callback:
                progress_callback(base_pct, f"⚙️ Processing '{stem_id}' via LALAL.AI…")

            try:
                task_id = self._start_split(source_id, lalai_stem)
                task_result = self._poll_until_done(
                    task_id,
                    stem_label=stem_id,
                    progress_callback=progress_callback,
                )
            except LalaiError as exc:
                logger.error("Failed to process stem '%s': %s", stem_id, exc)
                continue

            stem_url = next(
                (t["url"] for t in task_result.get("tracks", []) if t.get("type") == "stem"),
                None,
            )
            if not stem_url:
                logger.warning("No stem track URL for '%s': %s", stem_id, task_result)
                continue

            # Always download as MP3 (LALAL.AI CDN only serves MP3)
            mp3_dest = output_dir / f"{stem_id}.mp3"
            try:
                self._download(stem_url, mp3_dest)
            except LalaiError as exc:
                logger.error("Download failed for '%s': %s", stem_id, exc)
                continue

            if fmt == "wav":
                wav_dest = output_dir / f"{stem_id}.wav"
                try:
                    self._convert_to_wav(mp3_dest, wav_dest)
                    results[stem_id] = wav_dest
                except LalaiError as exc:
                    logger.error("WAV conversion failed for '%s': %s", stem_id, exc)
                    results[stem_id] = mp3_dest  # fall back to MP3
            else:
                results[stem_id] = mp3_dest

            done_pct = int(10 + ((idx + 1) / total) * 80)
            if progress_callback:
                progress_callback(done_pct, f"✅ '{stem_id}' extracted")

        logger.info("separate() complete — %d/%d stems extracted", len(results), total)
        if progress_callback:
            progress_callback(95, f"✅ {len(results)}/{total} stems extracted")

        return results
