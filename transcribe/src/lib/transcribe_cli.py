"""transcribe_cli.py - CLI tool to transcribe audio files using OpenAI Whisper.

Supports single-file and folder-batch transcription. Output is saved as a
Markdown ``.md`` file beside the original audio file, with a metadata header
and timestamped paragraph breaks inserted at natural pauses.

Typical usage::

    python3 transcribe_cli.py audio.mp3 --language Spanish
    python3 transcribe_cli.py ./my-folder/ --model small
"""

import glob as _glob
import os
from datetime import datetime

import click
import torch
import whisper

from constants import SUPPORTED_FORMATS


def pick_device_and_precision() -> tuple[str, bool]:
    """Detect the best available compute device and whether fp16 is safe.

    Returns:
        A tuple of (device_string, use_fp16) where *device_string* is one of
        ``"cuda"``, ``"mps"``, or ``"cpu"``, and *use_fp16* is True only when
        CUDA is available.
    """
    if torch.cuda.is_available():
        return "cuda", True
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps", False
    return "cpu", False



def build_transcript_markdown(
    result: dict,
    audio_path: str,
    language: str | None,
    model_size: str,
    pause_threshold: float = 1.2,
) -> str:
    """Build a Markdown-formatted transcript from a Whisper result dict.

    The output includes a metadata header (filename, language, model, date) and
    the transcript body split into paragraphs wherever consecutive segments are
    separated by a gap >= *pause_threshold* seconds.

    Args:
        result: Raw dict returned by :func:`whisper.Whisper.transcribe`.
        audio_path: Path to the source audio file (used for the header title).
        language: Language name passed to Whisper, or ``None`` for auto-detect.
        model_size: Whisper model identifier used (e.g. ``"base"``).
        pause_threshold: Silence gap in seconds that starts a new paragraph.

    Returns:
        Complete Markdown string ready to be written to a ``.md`` file.
    """
    filename = os.path.basename(audio_path)
    detected_lang = (result.get("language") or language or "auto").capitalize()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    header = "\n".join([
        f"# {filename}",
        "",
        f"**Language:** {detected_lang}  ",
        f"**Model:** {model_size}  ",
        f"**Transcribed:** {now}  ",
        "",
        "---",
        "",
    ])

    paragraphs: list[str] = []
    current_tokens: list[str] = []
    prev_end: float | None = None

    for seg in result["segments"]:
        seg_text: str = seg["text"].strip()
        if not seg_text:
            continue

        if prev_end is not None and (seg["start"] - prev_end) >= pause_threshold:
            if current_tokens:
                paragraphs.append(" ".join(current_tokens))
            current_tokens = []

        current_tokens.append(seg_text)
        prev_end = seg["end"]

    if current_tokens:
        paragraphs.append(" ".join(current_tokens))

    return header + "\n\n".join(paragraphs) + "\n"


def transcribe_file(
    model: whisper.Whisper,
    audio_path: str,
    language: str | None,
    model_size: str,
    use_fp16: bool,
    pause_threshold: float = 1.2,
) -> None:
    """Transcribe one audio file and save the result to a ``.md`` file.

    The transcript is formatted as Markdown with a metadata header and
    timestamped paragraph breaks wherever consecutive segments are separated
    by more than *pause_threshold* seconds of silence.

    Args:
        model: A loaded :class:`whisper.Whisper` model instance.
        audio_path: Absolute or relative path to the audio file.
        language: ISO language name (e.g. ``"Spanish"``) or ``None`` for
            automatic detection.
        model_size: Whisper model identifier (e.g. ``"base"``), included in
            the output header.
        use_fp16: When True, run inference in 16-bit floating point (requires
            CUDA). Ignored on CPU.
        pause_threshold: Minimum silence gap in seconds between segments that
            triggers a new paragraph in the output.
    """
    result = model.transcribe(audio_path, language=language, fp16=use_fp16)

    markdown = build_transcript_markdown(result, audio_path, language, model_size, pause_threshold)

    md_out = audio_path + ".md"
    with open(md_out, "w", encoding="utf-8") as fh:
        fh.write(markdown)

    click.echo(f"[ok] Transcribed {os.path.basename(audio_path)} → {os.path.basename(md_out)}")


@click.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--model", "model_size", default="base", show_default=True,
              help="Whisper model size: tiny|base|small|medium|large")
@click.option(
    "--language",
    default="Spanish",
    show_default=True,
    help="Force language (e.g. 'Spanish'). Pass 'auto' to auto-detect.",
)
@click.option("--pause-threshold", default=1.2, show_default=True,
              help="Silence gap in seconds that starts a new paragraph.")
@click.option("--fp16/--no-fp16", default=True, help="Use fp16 when available (ignored on CPU).")
def main(path: str, model_size: str, language: str, pause_threshold: float, fp16: bool) -> None:
    """Transcribe audio with Whisper and save as Markdown.

    PATH can be a single audio file or a folder. When a folder is given every
    supported audio file inside is processed in alphabetical order.

    Supported formats: mp3, flac, m4a, ogg, opus, wav.
    """
    lang: str | None = None if (not language or language.lower() == "auto") else language

    device, auto_fp16 = pick_device_and_precision()
    use_fp16 = fp16 and auto_fp16
    click.echo(f"[info] device={device}, fp16={use_fp16}")

    model = whisper.load_model(model_size, device=device)

    if os.path.isdir(path):
        audio_files: list[str] = []
        for fmt in SUPPORTED_FORMATS:
            audio_files.extend(_glob.glob(os.path.join(path, f"*.{fmt}")))
        audio_files = sorted(audio_files, key=lambda x: os.path.basename(x).lower())

        if not audio_files:
            click.echo(f"[warn] No supported audio files found in folder. ({', '.join(SUPPORTED_FORMATS)})")
            return

        click.echo(f"[info] Found {len(audio_files)} audio files:")
        for f in audio_files:
            click.echo(" - " + os.path.basename(f))

        for audio_file in audio_files:
            transcribe_file(model, audio_file, lang, model_size, use_fp16, pause_threshold)
    else:
        transcribe_file(model, path, lang, model_size, use_fp16, pause_threshold)


if __name__ == "__main__":
    main()
