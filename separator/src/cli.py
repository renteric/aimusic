#!/usr/bin/env python3
# cli.py — Command-line interface for Music Source Separator
"""
Usage examples:
  python cli.py separate song.mp3
  python cli.py separate song.mp3 --stems vocals,drums,bass
  python cli.py separate song.mp3 --model htdemucs_6s --output ./my_stems
  python cli.py batch ./my_music_folder --stems vocals,guitar
  python cli.py models
  python cli.py info song.mp3
"""

import sys
import time
import click
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from rich.panel import Panel
from rich.text import Text
from rich import box

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from core.separator import AudioSeparator, SeparationError, detect_device
from config.settings import AVAILABLE_MODELS, STEM_GROUPS, DEFAULT_MODEL

console = Console()

BANNER = """
╔══════════════════════════════════════════════════╗
║   🎵  Music Source Separator  v1.0              ║
║   Powered by Demucs (Meta AI)                   ║
╚══════════════════════════════════════════════════╝
"""


@click.group()
def cli():
    """🎵 AI-powered music source separation tool."""
    pass


@cli.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--stems", "-s", default=None,
              help="Comma-separated stems: vocals,drums,bass,guitar,piano,other")
@click.option("--model", "-m", default=DEFAULT_MODEL,
              type=click.Choice(list(AVAILABLE_MODELS.keys())),
              help=f"Model to use (default: {DEFAULT_MODEL})")
@click.option("--output", "-o", default=None,
              help="Output directory (default: ./outputs/<track_name>)")
@click.option("--format", "-f", default="mp3",
              type=click.Choice(["mp3", "wav"]),
              help="Output format (default: mp3)")
@click.option("--bitrate", "-b", default=320, type=int,
              help="MP3 bitrate in kbps (default: 320)")
@click.option("--device", "-d", default=None,
              help="Compute device: cpu or cuda (auto-detected by default)")
def separate(input_file, stems, model, output, format, bitrate, device):
    """Separate a single audio file into instrument stems."""
    console.print(BANNER, style="bold cyan")

    input_path = Path(input_file)
    device = device or detect_device()

    # Parse stems
    stem_list = [s.strip() for s in stems.split(",")] if stems else None

    # Set output directory
    if output:
        output_dir = Path(output)
    else:
        output_dir = Path("outputs") / input_path.stem
    output_dir.mkdir(parents=True, exist_ok=True)

    # Show job summary
    model_info = AVAILABLE_MODELS[model]
    table = Table(box=box.ROUNDED, show_header=False, border_style="dim")
    table.add_column("Key", style="bold cyan", width=16)
    table.add_column("Value", style="white")
    table.add_row("File", str(input_path.name))
    table.add_row("Model", f"{model} — {model_info['description']}")
    table.add_row("Stems", ", ".join(stem_list) if stem_list else "all available")
    table.add_row("Output", str(output_dir))
    table.add_row("Format", format.upper())
    table.add_row("Device", device.upper())
    if device == "cpu":
        table.add_row("⚠️  Note", "CPU mode — expect 5–15 min per song")
    console.print(table)
    console.print()

    # Run separation with progress
    separator = AudioSeparator(
        model=model,
        device=device,
        mp3_output=(format == "mp3"),
        mp3_bitrate=bitrate,
    )

    result_stems = {}
    start_time = time.time()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Separating...", total=100)

        def update_progress(pct, msg):
            progress.update(task, completed=pct, description=f"[cyan]{msg}")

        try:
            result_stems = separator.separate(
                input_path=input_path,
                output_dir=output_dir,
                stems=stem_list,
                progress_callback=update_progress,
            )
        except SeparationError as e:
            console.print(f"\n[bold red]❌ Separation failed:[/bold red] {e}")
            sys.exit(1)

    elapsed = time.time() - start_time

    # Results table
    console.print(f"\n[bold green]✅ Done in {elapsed:.1f}s[/bold green]\n")
    results_table = Table(title="Separated Stems", box=box.ROUNDED, border_style="green")
    results_table.add_column("Stem", style="bold")
    results_table.add_column("File", style="dim")
    results_table.add_column("Size", justify="right")

    for stem_name, stem_path in sorted(result_stems.items()):
        size_mb = stem_path.stat().st_size / 1024 / 1024
        label = STEM_GROUPS.get(stem_name, {}).get("label", stem_name)
        results_table.add_row(label, stem_path.name, f"{size_mb:.1f} MB")

    console.print(results_table)
    console.print(f"\n[dim]Output directory: {output_dir.resolve()}[/dim]")


@cli.command()
@click.argument("input_dir", type=click.Path(exists=True))
@click.option("--stems", "-s", default=None,
              help="Comma-separated stems to extract")
@click.option("--model", "-m", default=DEFAULT_MODEL,
              type=click.Choice(list(AVAILABLE_MODELS.keys())))
@click.option("--output", "-o", default="outputs",
              help="Root output directory (default: ./outputs)")
@click.option("--format", "-f", default="mp3",
              type=click.Choice(["mp3", "wav"]))
@click.option("--device", "-d", default=None)
def batch(input_dir, stems, model, output, format, device):
    """Process all audio files in a directory."""
    console.print(BANNER, style="bold cyan")

    input_path = Path(input_dir)
    output_root = Path(output)
    device = device or detect_device()
    stem_list = [s.strip() for s in stems.split(",")] if stems else None

    # Find all audio files
    audio_extensions = {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac"}
    audio_files = [
        f for f in input_path.iterdir()
        if f.suffix.lower() in audio_extensions
    ]

    if not audio_files:
        console.print(f"[yellow]No audio files found in {input_dir}[/yellow]")
        sys.exit(0)

    console.print(f"[cyan]Found {len(audio_files)} audio file(s) to process[/cyan]\n")

    separator = AudioSeparator(
        model=model,
        device=device,
        mp3_output=(format == "mp3"),
    )

    success, failed = 0, 0

    for i, audio_file in enumerate(audio_files, 1):
        console.print(f"[bold]({i}/{len(audio_files)}) {audio_file.name}[/bold]")
        output_dir = output_root / audio_file.stem
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("{task.percentage:>3.0f}%"),
                console=console,
                transient=True,
            ) as progress:
                task = progress.add_task("Processing...", total=100)
                result = separator.separate(
                    input_path=audio_file,
                    output_dir=output_dir,
                    stems=stem_list,
                    progress_callback=lambda p, m: progress.update(task, completed=p, description=m),
                )
            console.print(f"  [green]✓ {len(result)} stems → {output_dir}[/green]")
            success += 1
        except SeparationError as e:
            console.print(f"  [red]✗ Failed: {e}[/red]")
            failed += 1

    console.print(f"\n[bold]Batch complete:[/bold] {success} succeeded, {failed} failed")


@cli.command()
def models():
    """List all available separation models."""
    console.print(BANNER, style="bold cyan")
    table = Table(title="Available Models", box=box.ROUNDED, border_style="cyan")
    table.add_column("Model Name", style="bold cyan")
    table.add_column("Quality", justify="center")
    table.add_column("Stems", style="dim")
    table.add_column("Size", justify="right")
    table.add_column("Description")

    for name, info in AVAILABLE_MODELS.items():
        marker = " ← default" if name == DEFAULT_MODEL else ""
        quality_color = {
            "Very High": "green",
            "High": "yellow",
            "Good": "white"
        }.get(info["quality"], "white")
        table.add_row(
            f"{name}{marker}",
            f"[{quality_color}]{info['quality']}[/{quality_color}]",
            ", ".join(info["stems"]),
            f"{info['size_mb']} MB",
            info["description"],
        )

    console.print(table)
    console.print("\n[dim]Models are downloaded automatically on first use (~100MB)[/dim]")


@cli.command()
@click.argument("input_file", type=click.Path(exists=True))
def info(input_file):
    """Show information about an audio file."""
    import subprocess, json

    input_path = Path(input_file)
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", str(input_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        console.print("[red]ffprobe not found. Install ffmpeg to use this command.[/red]")
        sys.exit(1)

    data = json.loads(result.stdout)
    fmt = data.get("format", {})

    duration = float(fmt.get("duration", 0))
    minutes = int(duration // 60)
    seconds = int(duration % 60)
    size_mb = int(fmt.get("size", 0)) / 1024 / 1024

    table = Table(title=f"📄 {input_path.name}", box=box.ROUNDED, show_header=False)
    table.add_column("Key", style="bold cyan", width=16)
    table.add_column("Value")
    table.add_row("Format", fmt.get("format_long_name", "Unknown"))
    table.add_row("Duration", f"{minutes}m {seconds}s")
    table.add_row("File Size", f"{size_mb:.1f} MB")
    table.add_row("Bit Rate", f"{int(fmt.get('bit_rate', 0)) // 1000} kbps")

    for stream in data.get("streams", []):
        if stream.get("codec_type") == "audio":
            table.add_row("Sample Rate", f"{stream.get('sample_rate', '?')} Hz")
            table.add_row("Channels", str(stream.get("channels", "?")))
            table.add_row("Codec", stream.get("codec_name", "?").upper())

    console.print(table)

    est_cpu_min = max(1, int(duration / 60) * 3)
    console.print(f"\n[dim]Estimated CPU processing time: ~{est_cpu_min}–{est_cpu_min*3} minutes[/dim]")


if __name__ == "__main__":
    cli()
