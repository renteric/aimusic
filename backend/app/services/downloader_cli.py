#!/usr/bin/env python3
"""
downloader_cli.py - CLI tool to download audio from the web via yt-dlp.

Can be used as:
1. A standalone CLI script: ``python downloader_cli.py -s single -u "https://..."``
2. A subprocess invoked by the Flask API (with PYTHONPATH set to this directory).
3. A module: ``python -m app.services.downloader_cli`` (from backend/).

Output directory rules:
- Always writes into ``./media`` (relative to working directory).
- ``--output subfolder`` → ``./media/subfolder``.
- The name is sanitised: internal spaces removed, absolute paths and ``..`` rejected.

Examples::

    python downloader_cli.py -s single -u "https://youtu.be/xyz" --format mp3 --bitrate 320k
    python downloader_cli.py -s playlist -u "https://youtube.com/playlist?list=..." -o mixes
    python downloader_cli.py -s search_txt -q "Artist - Song Title"
"""

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import click

# Support both: imported as package (app.services.downloader_cli) and as a
# standalone script run with PYTHONPATH pointing at this directory.
try:
    from app.services.constants import SUPPORTED_FORMATS  # package context
except ImportError:
    from constants import SUPPORTED_FORMATS  # type: ignore  # standalone context

# ── Constants ──────────────────────────────────────────────────────────────────

MEDIA_OUTPUT_PATH = Path("./media")

SUPPORTED_BITRATES: list[str] = [
    "auto", "disable",
    "8k", "16k", "24k", "32k", "40k", "48k", "64k",
    "80k", "96k", "112k", "128k", "160k", "192k", "224k", "256k", "320k",
    "0", "1", "2", "3", "4", "5", "6", "7", "8", "9",
]


# ── Data classes ───────────────────────────────────────────────────────────────


@dataclass
class DownloadConfig:
    """Immutable value object for a single download operation.

    Attributes:
        audio_format: Target audio format, e.g. ``"mp3"``.
        bitrate: Target audio bitrate / quality, e.g. ``"320k"`` or ``"0"``.
        output_dir: Resolved filesystem path where files will be written.
        verbose: When True, print the yt-dlp command before executing.
        force: When True, pass ``--ignore-errors`` to yt-dlp and skip
               ffmpeg availability checks.
    """

    audio_format: str
    bitrate: str
    output_dir: Path
    verbose: bool = False
    force: bool = False

    def __post_init__(self) -> None:
        """Validate field values at construction time.

        Raises:
            ValueError: If *audio_format* or *bitrate* is not supported.
        """
        if self.audio_format not in SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported format '{self.audio_format}'. Choose from: {SUPPORTED_FORMATS}")
        if self.bitrate not in SUPPORTED_BITRATES:
            raise ValueError(f"Unsupported bitrate '{self.bitrate}'. Choose from: {SUPPORTED_BITRATES}")


# ── Click callbacks ────────────────────────────────────────────────────────────


def validate_source(ctx: click.Context, param: click.Parameter, value: str) -> str:
    """Validate the --source option.

    Args:
        ctx: Click context (unused).
        param: Click parameter object (unused).
        value: Raw value supplied by the user.

    Returns:
        The validated value unchanged.

    Raises:
        click.BadParameter: If *value* is not a known source type.
    """
    if value not in {"single", "playlist", "search_txt"}:
        raise click.BadParameter("Source must be 'single', 'playlist', or 'search_txt'.")
    return value


def validate_format(ctx: click.Context, param: click.Parameter, value: str) -> str:
    """Validate the --format option against :data:`SUPPORTED_FORMATS`.

    Args:
        ctx: Click context (unused).
        param: Click parameter object (unused).
        value: Raw format string.

    Returns:
        The validated value unchanged.

    Raises:
        click.BadParameter: If *value* is not in :data:`SUPPORTED_FORMATS`.
    """
    if value not in SUPPORTED_FORMATS:
        raise click.BadParameter(f"Unsupported format. Choose from: {', '.join(SUPPORTED_FORMATS)}")
    return value


def validate_bitrate(ctx: click.Context, param: click.Parameter, value: str) -> str:
    """Validate the --bitrate option against :data:`SUPPORTED_BITRATES`.

    Args:
        ctx: Click context (unused).
        param: Click parameter object (unused).
        value: Raw bitrate string.

    Returns:
        The validated value unchanged.

    Raises:
        click.BadParameter: If *value* is not in :data:`SUPPORTED_BITRATES`.
    """
    if value not in SUPPORTED_BITRATES:
        raise click.BadParameter(f"Unsupported bitrate. Choose from: {', '.join(SUPPORTED_BITRATES)}")
    return value


# ── Path resolution ────────────────────────────────────────────────────────────


def resolve_output_dir(output: str) -> Path:
    """Resolve a user-supplied folder name to a safe path inside ``./media``.

    Rules:
        - Empty / base variants (``""```, ``"."```, ``"media"`` etc.) → ``./media``
        - Any other string → ``./media/<sanitised_name>``
        - Absolute paths and ``..`` segments are rejected.
        - All spaces are stripped from the folder name.

    Args:
        output: Raw output folder name from the CLI or web UI.

    Returns:
        Resolved :class:`~pathlib.Path` guaranteed to be inside ``./media``.

    Raises:
        click.BadParameter: If *output* is absolute or contains ``..``.
    """
    out = (output or "").strip()

    if out in {"", ".", "media", "./media", "./media/"}:
        return MEDIA_OUTPUT_PATH

    out = out.replace(" ", "").strip("/")
    if not out:
        return MEDIA_OUTPUT_PATH

    rel = Path(out)
    if rel.is_absolute() or any(part == ".." for part in rel.parts):
        raise click.BadParameter("Output must be a subfolder inside ./media (no absolute paths, no '..').")

    return MEDIA_OUTPUT_PATH / rel


def ui_resolve_output_dir(base_dir: "str | Path", output_subfolder: str) -> str:
    """Resolve the final download directory for use from the Flask API.

    Combines *base_dir* with the sanitised *output_subfolder* so that the
    API layer never replicates path-sanitisation logic.

    Args:
        base_dir: Project root directory.
        output_subfolder: Raw user input like ``"toto"`` or ``""``.

    Returns:
        Absolute path string to the resolved output directory (created if needed).
    """
    base = Path(base_dir)
    resolved = resolve_output_dir(output_subfolder)
    final_path = base / resolved
    final_path.mkdir(parents=True, exist_ok=True)
    return str(final_path)


# ── Core download helper ───────────────────────────────────────────────────────


def _download_media(input_source: str, config: DownloadConfig) -> None:
    """Execute yt-dlp for a single input source using the given configuration.

    Streams yt-dlp stdout/stderr to the terminal line-by-line so callers
    (and the Flask SSE stream) see progress in real time.

    Args:
        input_source: A direct URL or a ``ytsearch1:`` query string.
        config: :class:`DownloadConfig` with format, bitrate, and output path.
    """
    click.echo(f"\n--- Processing: {input_source} ---")

    command = [
        "yt-dlp", "-x",
        "--audio-format", config.audio_format,
        "--add-metadata",
        "--embed-thumbnail",
        "--no-check-certificates",
        "--restrict-filenames",
        "--paths", str(config.output_dir),
        "-o", "%(title)s.%(ext)s",
        input_source,
    ]
    if config.bitrate != "disable":
        command.extend(["--audio-quality", config.bitrate])
    if config.force:
        command.append("--ignore-errors")
    if config.verbose:
        click.echo(f"Executing command: {' '.join(command)}")

    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        assert process.stdout is not None
        for line in process.stdout:
            click.echo(line, nl=False)
        process.wait()

        if process.returncode == 0:
            click.echo(f"Successfully processed: {input_source}")
        else:
            click.echo(f"Failed to process {input_source}", err=True)
    except FileNotFoundError:
        click.echo("Error: yt-dlp not found. Install it or add it to PATH.", err=True)
    except Exception as exc:
        click.echo(f"An unexpected error occurred: {exc}", err=True)


# ── CLI entry point ────────────────────────────────────────────────────────────


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option("-s", "--source", required=True, callback=validate_source,
              help="Source type: 'single', 'playlist', or 'search_txt'.")
@click.option("-q", "--query", type=str,
              help="Song query, path to a list file, or multi-line queries.")
@click.option("-u", "--url", type=str,
              help="Direct URL for a single song or playlist.")
@click.option("-o", "--output", default="",
              help="Subfolder inside ./media. Empty → ./media.")
@click.option("--format", "fmt", default="mp3", callback=validate_format,
              help=f"Audio format: {', '.join(SUPPORTED_FORMATS)}")
@click.option("--bitrate", default="320k", callback=validate_bitrate,
              help="Audio bitrate / quality.")
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose output.")
@click.option("-f", "--force", is_flag=True,
              help="Skip ffmpeg check and enable --ignore-errors.")
def main(
    source: str,
    query: str,
    url: str,
    output: str,
    fmt: str,
    bitrate: str,
    verbose: bool,
    force: bool,
) -> None:
    """Download audio from YouTube and other sources using yt-dlp.

    Examples::

        python downloader_cli.py -s single -u "https://youtu.be/xyz" --format mp3
        python downloader_cli.py -s playlist -u "https://youtube.com/playlist?list=..." -o mixes
        python downloader_cli.py -s search_txt -q "Artist - Song Title"
    """
    if query and url:
        raise click.BadParameter("Cannot use both --query and --url simultaneously.")
    if not query and not url:
        raise click.BadParameter("Either --query or --url must be provided.")

    output_dir = resolve_output_dir(output)
    output_dir.mkdir(parents=True, exist_ok=True)

    config = DownloadConfig(
        audio_format=fmt, bitrate=bitrate, output_dir=output_dir, verbose=verbose, force=force,
    )

    if url:
        _download_media(url, config)
        return

    if source == "single":
        _download_media(f"ytsearch1:{query}", config)
        return

    if source == "search_txt":
        for q in [ln.strip() for ln in (query or "").splitlines() if ln.strip()]:
            _download_media(f"ytsearch1:{q}", config)
        return

    # Playlist mode
    if source == "playlist":
        if query and os.path.isfile(query):
            try:
                with open(query, encoding="utf-8") as f:
                    queries = [ln.strip() for ln in f if ln.strip()]
            except Exception as exc:
                click.echo(f"Error reading file: {exc}", err=True)
                sys.exit(1)
        else:
            queries = [ln.strip() for ln in (query or "").splitlines() if ln.strip()]

        for q in queries:
            if q.startswith(("http://", "https://")):
                _download_media(q, config)
            else:
                _download_media(f"ytsearch1:{q}", config)


if __name__ == "__main__":
    main()
