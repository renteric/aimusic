#!/usr/bin/env python3
"""
metadata_cleaner.py - Audio metadata inspector and remover.

Supported formats:
    mp3, flac, m4a, ogg, opus, wav

Features:
- Inspect metadata with exiftool (``--show``).
- Remove ALL tags (``--clean``):
    - MP3: guaranteed ID3v1 (128-byte footer) + ID3v2 removal via mutagen.
    - WAV: direct RIFF chunk parser strips metadata chunks without re-encoding.
    - Others: exiftool preferred; mutagen as fallback.
- Batch-clean entire folders, optionally recursive.
- Optional ``.bak`` backup before any destructive operation.
- Optional removal of filesystem write-protection (chmod + chattr).

Requirements:
- Python 3.13+
- ``exiftool`` (recommended, install via ``apt install libimage-exiftool-perl``)
- ``mutagen`` (fallback, install via ``pip install mutagen``)

CLI usage examples::

    # Show metadata
    python3 metadata_cleaner.py -p song.mp3 --show

    # Remove all metadata with backup
    python3 metadata_cleaner.py -p song.mp3 --clean --backup

    # Clean entire folder recursively
    python3 metadata_cleaner.py -p ~/Music --clean --backup
"""

import shutil
import stat
import subprocess
from pathlib import Path
from typing import Iterable, Optional, Tuple

import click

# Optional mutagen fallback
try:
    from mutagen.id3 import ID3, ID3NoHeaderError
    from mutagen import File as MutagenFile
except Exception:
    ID3 = None
    ID3NoHeaderError = Exception
    MutagenFile = None


SUPPORTED_FORMATS = ["mp3", "flac", "m4a", "ogg", "opus", "wav"]


# ---------------------------------------------------------------------
# Utility Functions
# ---------------------------------------------------------------------


def which(cmd: str) -> Optional[str]:
    """Return the full path of a command if it is installed, otherwise None.

    Args:
        cmd: Executable name to look up (e.g. ``"exiftool"``).

    Returns:
        Absolute path string, or None if not found on PATH.
    """
    from shutil import which as _which

    return _which(cmd)


def run_cmd(cmd: list[str]) -> Tuple[int, str, str]:
    """Execute a shell command and return its result.

    Args:
        cmd: Command and argument list to run.

    Returns:
        Tuple of ``(returncode, stdout, stderr)``.
    """
    p = subprocess.run(cmd, capture_output=True, check=False)

    def decode(b: bytes) -> str:
        return b.decode("utf-8", errors="replace") if b else ""

    return p.returncode, decode(p.stdout), decode(p.stderr)


def iter_audio_targets(path: Path, recursive: bool) -> Iterable[Path]:
    """Yield supported audio files found at *path*.

    - If *path* is a file, yields it only if its extension is in
      :data:`SUPPORTED_FORMATS`.
    - If *path* is a directory, yields all matching files (recursively or not).

    Args:
        path: File or directory to search.
        recursive: When True and *path* is a directory, descend into
                   sub-directories.

    Yields:
        :class:`~pathlib.Path` objects for each supported audio file found.
    """
    if path.is_file():
        if path.suffix.lower().lstrip(".") in SUPPORTED_FORMATS:
            yield path
        return

    if recursive:
        for ext in SUPPORTED_FORMATS:
            yield from path.rglob(f"*.{ext}")
    else:
        for ext in SUPPORTED_FORMATS:
            yield from path.glob(f"*.{ext}")


def backup_file(file_path: Path) -> Path:
    """Create a ``.bak`` copy of *file_path* next to the original.

    Args:
        file_path: Path to the file to back up.

    Returns:
        Path of the newly created backup file.
    """
    backup_path = file_path.with_suffix(file_path.suffix + ".bak")
    shutil.copy2(file_path, backup_path)
    return backup_path


def remove_write_protection(file_path: Path) -> None:
    """Attempt to remove filesystem write protection from *file_path*.

    Two operations are performed:
    1. Add the owner write bit (``chmod u+w``).
    2. Remove the Linux immutable flag via ``chattr -i`` (no-op on non-Linux).

    Args:
        file_path: Path to the file whose protection should be lifted.
    """
    file_path.chmod(file_path.stat().st_mode | stat.S_IWUSR)

    if which("chattr"):
        subprocess.run(["chattr", "-i", str(file_path)], check=False)


# ---------------------------------------------------------------------
# Metadata Handling
# ---------------------------------------------------------------------


def exiftool_dump(file_path: Path) -> str:
    """Return full exiftool metadata output for a file."""
    if not which("exiftool"):
        raise FileNotFoundError("exiftool not installed")
    rc, out, err = run_cmd(["exiftool", str(file_path)])
    return (out or err).strip()


def exiftool_clean(file_path: Path) -> None:
    """
    Remove ALL metadata using exiftool (best-effort).

    - For MP3, also clears ID3v1 and ID3v2 groups explicitly.
    - For other formats, uses -all= only (avoids non-applicable groups).
    """
    if not which("exiftool"):
        raise FileNotFoundError("exiftool not installed")

    ext = file_path.suffix.lower().lstrip(".")

    cmd = [
        "exiftool",
        "-overwrite_original",
        "-all=",
    ]

    if ext == "mp3":
        cmd += ["-id3v1:all=", "-id3v2:all="]

    cmd.append(str(file_path))

    rc, out, err = run_cmd(cmd)
    if rc != 0:
        raise RuntimeError((err or out).strip())


def mutagen_clean(file_path: Path) -> None:
    """
    Remove ID3v2 using mutagen and remove ID3v1 by stripping the 128-byte TAG footer.
    This guarantees both ID3v2 and ID3v1 are removed.
    """
    if ID3 is None:
        raise RuntimeError("Mutagen not installed. Install: pip install mutagen")

    # Remove ID3v2
    try:
        id3 = ID3(str(file_path))
        id3.delete(str(file_path))
    except ID3NoHeaderError:
        pass

    # Remove ID3v1 (128-byte footer starting with b'TAG')
    data = file_path.read_bytes()
    if len(data) >= 128 and data[-128:-125] == b"TAG":
        file_path.write_bytes(data[:-128])


def wav_strip_metadata(file_path: Path) -> None:
    """
    Strip metadata from a WAV file by parsing the RIFF structure and
    rebuilding without metadata chunks.

    Removes: LIST INFO, id3, ID3, bext, XMP, iXML, cart, afsp chunks.
    Keeps: fmt, data, fact, cue, smpl, and any other non-metadata chunks.
    """
    METADATA_CHUNK_IDS = {b"id3 ", b"ID3 ", b"bext", b"XMP ", b"iXML", b"_PMX", b"cart", b"afsp"}

    data = file_path.read_bytes()

    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise RuntimeError(f"Not a valid RIFF WAV file: {file_path}")

    kept_chunks = bytearray()
    pos = 12  # Skip 'RIFF' + size (4) + 'WAVE' (4)

    while pos + 8 <= len(data):
        chunk_id = data[pos : pos + 4]
        chunk_size = int.from_bytes(data[pos + 4 : pos + 8], "little")
        padded_size = chunk_size + (chunk_size % 2)
        chunk_total = 8 + padded_size

        skip = chunk_id in METADATA_CHUNK_IDS
        if not skip and chunk_id == b"LIST":
            # Only skip LIST INFO (metadata); keep other LIST types (e.g. adtl)
            if pos + 12 <= len(data) and data[pos + 8 : pos + 12] == b"INFO":
                skip = True

        if not skip:
            kept_chunks += data[pos : pos + chunk_total]

        pos += chunk_total

    wave_content = b"WAVE" + bytes(kept_chunks)
    new_file = b"RIFF" + len(wave_content).to_bytes(4, "little") + wave_content
    file_path.write_bytes(new_file)


def mutagen_clean_generic(file_path: Path) -> None:
    """Remove tags for non-MP3 formats using mutagen."""
    if MutagenFile is None:
        raise RuntimeError("Mutagen not installed. Install: pip install mutagen")

    audio = MutagenFile(str(file_path))
    if audio is None:
        raise RuntimeError(f"Unsupported or unreadable audio file: {file_path}")

    # Most mutagen file types implement a .delete() method, but signatures vary.
    if hasattr(audio, "delete"):
        try:
            audio.delete()  # type: ignore[attr-defined]
        except TypeError:
            audio.delete(str(file_path))  # type: ignore[attr-defined]

    # Ensure tags are cleared even when .delete() is absent/no-op.
    if getattr(audio, "tags", None):
        try:
            audio.tags.clear()  # type: ignore[union-attr]
        except Exception:
            audio.tags = None  # type: ignore[assignment]

    if hasattr(audio, "save"):
        audio.save()  # type: ignore[attr-defined]


def verify_no_tags(file_path: Path) -> bool:
    """Best-effort verification that common tags are absent (non-MP3 formats)."""
    if MutagenFile is None:
        return False
    audio = MutagenFile(str(file_path))
    if audio is None:
        return False
    tags = getattr(audio, "tags", None)
    return not tags


def clean_audio_metadata(file_path: Path) -> None:
    """Remove metadata for supported audio files."""
    ext = file_path.suffix.lower().lstrip(".")
    if ext not in SUPPORTED_FORMATS:
        raise click.ClickException(
            f"Unsupported format: .{ext}. Supported: {', '.join(SUPPORTED_FORMATS)}"
        )

    # MP3: always use mutagen + manual ID3v1 stripping for guaranteed removal.
    if ext == "mp3":
        mutagen_clean(file_path)
        id3v2_absent, id3v1_absent = verify_no_id3(file_path)
        click.echo(
            f"Verify: ID3v2={'OK' if id3v2_absent else 'FAIL'} | ID3v1={'OK' if id3v1_absent else 'FAIL'}"
        )
        return

    # WAV: exiftool cannot write RIFF WAVE on most systems; use direct RIFF parser.
    if ext == "wav":
        wav_strip_metadata(file_path)
        click.echo("Verify: RIFF metadata chunks removed")
        return

    # Other formats: prefer exiftool (broad support), fallback to mutagen on failure.
    if which("exiftool"):
        try:
            exiftool_clean(file_path)
            ok = verify_no_tags(file_path) if MutagenFile is not None else True
            click.echo(f"Verify: TAGS={'OK' if ok else 'UNKNOWN'}")
            return
        except RuntimeError as e:
            click.echo(f"exiftool clean failed, falling back to mutagen: {e}")

    mutagen_clean_generic(file_path)
    ok = verify_no_tags(file_path)
    click.echo(f"Verify: TAGS={'OK' if ok else 'UNKNOWN'}")


def verify_no_id3(file_path: Path) -> tuple[bool, bool]:
    """Verify that ID3v2 and ID3v1 tags are absent from an MP3 file.

    Uses mutagen to check for an ID3v2 header, and reads the last 128 bytes
    directly to check for an ID3v1 ``TAG`` footer.

    Args:
        file_path: Path to the MP3 file to inspect.

    Returns:
        Tuple ``(id3v2_absent, id3v1_absent)`` where each element is True
        when the corresponding tag type is not present.
    """
    id3v2_absent = True
    if ID3 is not None:
        try:
            ID3(str(file_path))
            id3v2_absent = False
        except ID3NoHeaderError:
            id3v2_absent = True

    data = file_path.read_bytes()
    id3v1_absent = not (len(data) >= 128 and data[-128:-125] == b"TAG")
    return id3v2_absent, id3v1_absent


# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------


@click.command()
@click.option(
    "--path",
    "-p",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Audio file or folder path",
)
@click.option(
    "--recursive/--no-recursive",
    default=True,
    help="Search folders recursively (default: recursive)",
)
@click.option("--show", is_flag=True, help="Show metadata using exiftool")
@click.option(
    "--clean",
    is_flag=True,
    help="Remove ALL metadata (MP3: ID3v1 + ID3v2 guaranteed; others: best-effort)",
)
@click.option("--backup", is_flag=True, help="Create .bak backup before cleaning")
@click.option(
    "--remove-protection",
    is_flag=True,
    help="Remove filesystem write protection before cleaning",
)
def main(
    path: Path,
    recursive: bool,
    show: bool,
    clean: bool,
    backup: bool,
    remove_protection: bool,
) -> None:
    """
    Audio Metadata Inspector and Cleaner.

    Examples:

        Show metadata:
            python3 run.py -p song.mp3 --show

        Clean one file with backup:
            python3 run.py -p song.mp3 --clean --backup

        Clean entire folder:
            python3 run.py -p ~/Music --clean --backup
    """

    targets = list(iter_audio_targets(path, recursive))
    if not targets:
        raise click.ClickException(
            f"No supported audio files found. Supported: {', '.join(SUPPORTED_FORMATS)}"
        )

    click.echo(f"Found {len(targets)} file(s).")
    click.echo(f"Backend: {'exiftool' if which('exiftool') else 'mutagen fallback'}\n")

    for file_path in targets:
        click.echo(f"=== {file_path} ===")

        if show:
            if which("exiftool"):
                click.echo(exiftool_dump(file_path) or "(no metadata found)")
            else:
                click.echo("Install exiftool for detailed metadata output.")

        if clean:
            if backup:
                backup_path = backup_file(file_path)
                click.echo(f"Backup created: {backup_path}")

            if remove_protection:
                remove_write_protection(file_path)

            clean_audio_metadata(file_path)
            click.echo("Metadata removed.")

        click.echo()

    click.echo("Done.")


if __name__ == "__main__":
    main()
