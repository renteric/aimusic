#!/usr/bin/env python3
"""
extract_melody_cli.py - Transcribe a melody from an audio file and export MIDI + MusicXML.

Features:
- Harmonic-percussive source separation (HPSS) for cleaner pitch detection.
- Automatic BPM estimation via librosa beat tracker.
- Automatic key/mode detection via chroma-based Krumhansl-Schmuckler profiles.
- Melodic line extraction using pYIN (probabilistic YIN) pitch tracker.
- MIDI export: solo melody track + two-voice duet with diatonic/fixed harmony.
- MusicXML lead-sheet export (melody + harmony part).
- CSV export of raw onset/duration/pitch data.
- JSON summary written alongside all outputs.

CLI usage::

    python3 extract_melody_cli.py audio.mp3
    python3 extract_melody_cli.py audio.mp3 --out ./results --fmin C3 --fmax C7
    python3 extract_melody_cli.py audio.mp3 --bpm 120 --key D --mode minor --harmony fixed+3
"""

import csv
import json
from dataclasses import dataclass
from pathlib import Path

import click
import librosa
import mido
import numpy as np
from mido import Message, MidiFile, MidiTrack, bpm2tempo
from music21 import instrument, key as m21key, metadata
from music21 import meter, note as m21note, stream
from music21 import tempo as m21tempo
from tqdm import tqdm

# ── Constants ─────────────────────────────────────────────────────────────────

PITCH_CLASSES: list[str] = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Krumhansl-Schmuckler key-finding profiles
_MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

HARMONY_MODES: list[str] = ["diatonic", "fixed+3"]
VALID_MODES: list[str] = ["major", "minor"]

#: Smallest note duration used in MusicXML output.
#: A 32nd note (1/8 of a quarter) is always representable in standard notation
#: and remains valid after music21 splits notes at barlines.
_MIN_QL: float = 0.125  # 32nd note

#: Quantisation step for MusicXML durations — round to nearest 32nd note so
#: floating-point quarter-lengths never produce unmappable fractions.
_QL_STEP: float = 0.03125  # 128th note grid


def _quantise_ql(ql: float) -> float:
    """Round *ql* to the nearest 128th-note grid and enforce a 32nd-note minimum.

    music21's ``makeNotation()`` splits notes at barlines.  When the input
    quarter-length is an arbitrary float the split produces irrational
    fractions (e.g. 2048th notes) that MusicXML cannot represent.  Snapping
    to a 128th-note grid (``_QL_STEP = 1/32``) guarantees every sub-note
    after splitting is a standard duration.

    Args:
        ql: Raw quarter-length value (any positive float).

    Returns:
        Quantised quarter-length ≥ :data:`_MIN_QL`.
    """
    return max(_MIN_QL, round(ql / _QL_STEP) * _QL_STEP)


# ── Data classes ──────────────────────────────────────────────────────────────


@dataclass
class ExtractionConfig:
    """Immutable value object that carries all parameters for one melody extraction.

    Attributes:
        fmin_hz: Lowest expected pitch in Hz (passed to pYIN).
        fmax_hz: Highest expected pitch in Hz (passed to pYIN).
        min_note_sec: Minimum note duration in seconds; shorter events are discarded.
        use_hpss: When True, apply harmonic-percussive source separation before analysis.
        bpm_override: Force a specific BPM instead of auto-detecting. None = auto.
        key_override: Force a specific key tonic (e.g. ``"D"``, ``"F#"``). None = auto.
        mode_override: Force a specific mode (``"major"`` or ``"minor"``). None = auto.
        harmony_mode: Harmony strategy for the duet track (``"diatonic"`` or ``"fixed+3"``).
    """

    fmin_hz: float
    fmax_hz: float
    min_note_sec: float
    use_hpss: bool
    bpm_override: float | None
    key_override: str | None
    mode_override: str | None
    harmony_mode: str

    def __post_init__(self) -> None:
        """Validate field values at construction time.

        Raises:
            ValueError: If any field contains an invalid value.
        """
        if self.fmin_hz <= 0 or self.fmax_hz <= 0:
            raise ValueError("fmin_hz and fmax_hz must be positive.")
        if self.fmin_hz >= self.fmax_hz:
            raise ValueError(f"fmin_hz ({self.fmin_hz}) must be less than fmax_hz ({self.fmax_hz}).")
        if self.min_note_sec <= 0:
            raise ValueError("min_note_sec must be positive.")
        if self.harmony_mode not in HARMONY_MODES:
            raise ValueError(f"harmony_mode must be one of {HARMONY_MODES}, got '{self.harmony_mode}'.")
        if self.mode_override is not None and self.mode_override not in VALID_MODES:
            raise ValueError(f"mode_override must be one of {VALID_MODES}, got '{self.mode_override}'.")


# ── Music utilities ───────────────────────────────────────────────────────────


def detect_key_from_chroma(y: np.ndarray, sr: int) -> tuple[str, str]:
    """Detect the musical key and mode from a chroma representation.

    Uses the Krumhansl-Schmuckler key-finding algorithm: computes the
    normalised mean chroma vector and correlates it against major and minor
    templates for all 12 transpositions.

    Args:
        y: Audio time-series array.
        sr: Sampling rate of *y*.

    Returns:
        Tuple ``(key_str, mode)`` where *key_str* is a pitch-class name
        (e.g. ``"D"``) and *mode* is ``"major"`` or ``"minor"``.
    """
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    c = chroma.mean(axis=1)
    c = c / (np.linalg.norm(c) + 1e-9)

    best_corr = -1e9
    best_key = PITCH_CLASSES[0]
    best_mode = "major"

    for shift in range(12):
        maj_prof = np.roll(_MAJOR_PROFILE, shift)
        maj_prof = maj_prof / np.linalg.norm(maj_prof)
        min_prof = np.roll(_MINOR_PROFILE, shift)
        min_prof = min_prof / np.linalg.norm(min_prof)

        corr_maj = float(np.dot(c, maj_prof))
        corr_min = float(np.dot(c, min_prof))

        if corr_maj > best_corr:
            best_corr = corr_maj
            best_key = PITCH_CLASSES[shift]
            best_mode = "major"
        if corr_min > best_corr:
            best_corr = corr_min
            best_key = PITCH_CLASSES[shift]
            best_mode = "minor"

    return best_key, best_mode


def build_scale_pitch_classes(key_str: str, mode: str) -> set[int]:
    """Return the set of pitch-class integers for a given key and mode.

    Args:
        key_str: Tonic pitch class (e.g. ``"D"``, ``"F#"``).
        mode: Scale mode — ``"major"`` or ``"minor"``.

    Returns:
        Set of integers in ``0–11`` representing the scale degrees.
    """
    tonic_pc = PITCH_CLASSES.index(key_str)
    intervals = [0, 2, 4, 5, 7, 9, 11] if mode == "major" else [0, 2, 3, 5, 7, 8, 10]
    return {(tonic_pc + i) % 12 for i in intervals}


def diatonic_third_above(midi_pitch: int, key_str: str | None, mode: str | None) -> int:
    """Return the diatonic third above *midi_pitch* in the given key.

    Prefers a major third (4 semitones) when it stays in the scale, otherwise
    falls back to a minor third (3 semitones). When no key is provided, always
    returns a minor third.

    Args:
        midi_pitch: MIDI note number of the root note.
        key_str: Tonic pitch class (e.g. ``"D"``), or None for no key context.
        mode: ``"major"`` or ``"minor"``, or None for no key context.

    Returns:
        MIDI note number of the harmony note.
    """
    if key_str is None or mode is None:
        return midi_pitch + 3

    pcs = build_scale_pitch_classes(key_str, mode)
    m_pc = midi_pitch % 12
    cand_major = midi_pitch + 4
    cand_minor = midi_pitch + 3

    if (cand_major % 12) in pcs and (m_pc in pcs):
        return cand_major
    if (cand_minor % 12) in pcs and (m_pc in pcs):
        return cand_minor
    if (cand_major % 12) in pcs:
        return cand_major
    return cand_minor


# ── Core processor ────────────────────────────────────────────────────────────

# Type alias for a note tuple: (onset_sec, duration_sec, midi_pitch)
NoteList = list[tuple[float, float, int]]


class MelodyExtractor:
    """Orchestrates melody extraction and multi-format export for a single audio file.

    Attributes:
        audio_path: Path to the input audio file.
        out_dir: Directory where all output files are written.
        config: Extraction parameters.
    """

    def __init__(self, audio_path: Path, out_dir: Path, config: ExtractionConfig) -> None:
        """Initialise the extractor.

        Args:
            audio_path: Path to the input audio file.
            out_dir: Directory where all output files will be written.
            config: :class:`ExtractionConfig` with extraction parameters.
        """
        self.audio_path = audio_path
        self.out_dir = out_dir
        self.config = config

        # Populated during run()
        self._y: np.ndarray | None = None
        self._sr: int | None = None
        self._bpm: float | None = None
        self._key: str | None = None
        self._mode: str | None = None
        self._notes: NoteList = []

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _load_audio(self) -> tuple[np.ndarray, int]:
        """Load the audio file as a mono time-series.

        Returns:
            Tuple ``(y, sr)`` — the audio array and its sampling rate.

        Raises:
            click.ClickException: If the file cannot be read by librosa.
        """
        click.echo(f"Loading audio: {self.audio_path}")
        try:
            y, sr = librosa.load(str(self.audio_path), mono=True)
        except Exception as exc:
            raise click.ClickException(f"Failed to load audio file: {exc}") from exc
        click.echo(f"  Duration: {librosa.get_duration(y=y, sr=sr):.1f}s | Sample rate: {sr} Hz")
        return y, sr

    def _estimate_bpm(self, y: np.ndarray, sr: int) -> float:
        """Estimate the tempo in BPM, respecting any manual override.

        Args:
            y: Audio time-series.
            sr: Sampling rate.

        Returns:
            Beats per minute as a float.
        """
        if self.config.bpm_override is not None:
            click.echo(f"  BPM (override): {self.config.bpm_override:.1f}")
            return float(self.config.bpm_override)

        tempo = librosa.beat.tempo(y=y, sr=sr, aggregate=np.median)
        bpm = float(tempo[0]) if np.ndim(tempo) > 0 else float(tempo)
        click.echo(f"  BPM (detected): {bpm:.1f}")
        return bpm

    def _detect_key(self, y: np.ndarray, sr: int) -> tuple[str, str]:
        """Detect or apply the key and mode, respecting manual overrides.

        Args:
            y: Audio time-series.
            sr: Sampling rate.

        Returns:
            Tuple ``(key_str, mode)``.
        """
        if self.config.key_override and self.config.mode_override:
            click.echo(f"  Key (override): {self.config.key_override} {self.config.mode_override}")
            return self.config.key_override, self.config.mode_override

        key_str, mode = detect_key_from_chroma(y, sr)
        click.echo(f"  Key (detected): {key_str} {mode}")
        return key_str, mode

    def _extract_notes(self, y: np.ndarray, sr: int) -> NoteList:
        """Run pYIN pitch tracking and convert to a list of discrete notes.

        Applies HPSS first when enabled in the config. Frames shorter than
        ``config.min_note_sec`` are discarded.

        Args:
            y: Audio time-series.
            sr: Sampling rate.

        Returns:
            List of ``(onset_sec, duration_sec, midi_pitch)`` tuples.
        """
        click.echo("Extracting melody (pYIN)...")
        y_use = y
        if self.config.use_hpss:
            click.echo("  Applying HPSS...")
            y_harm, _ = librosa.effects.hpss(y, margin=(1.0, 1.2))
            y_use = y_harm

        f0, *_ = librosa.pyin(
            y_use, fmin=self.config.fmin_hz, fmax=self.config.fmax_hz, sr=sr
        )
        times = librosa.times_like(f0, sr=sr)

        midi = np.full_like(f0, fill_value=np.nan, dtype=float)
        idx = ~np.isnan(f0)
        midi[idx] = librosa.hz_to_midi(f0[idx])
        midi_q = np.round(midi)

        notes: NoteList = []
        last_pitch: float | None = None
        start_time: float | None = None

        for i, m in enumerate(tqdm(midi_q, desc="  Quantising frames", unit="frame", leave=False)):
            if np.isnan(m):
                if last_pitch is not None and start_time is not None:
                    duration = times[i] - start_time
                    if duration >= self.config.min_note_sec:
                        notes.append((start_time, duration, int(last_pitch)))
                    last_pitch = None
                    start_time = None
                continue

            if last_pitch is None:
                last_pitch = m
                start_time = times[i]
            elif m != last_pitch:
                if start_time is not None:
                    duration = times[i] - start_time
                    if duration >= self.config.min_note_sec:
                        notes.append((start_time, duration, int(last_pitch)))
                last_pitch = m
                start_time = times[i]

        # Flush the last note
        if last_pitch is not None and start_time is not None:
            duration = float(times[-1]) - start_time
            if duration >= self.config.min_note_sec:
                notes.append((start_time, duration, int(last_pitch)))

        click.echo(f"  Notes found: {len(notes)}")
        return notes

    # ── Export methods ────────────────────────────────────────────────────────

    def save_csv(self, notes: NoteList, csv_path: Path) -> None:
        """Write note events to a CSV file.

        Columns: ``onset_sec``, ``duration_sec``, ``midi_pitch``.

        Args:
            notes: List of ``(onset_sec, duration_sec, midi_pitch)`` tuples.
            csv_path: Destination file path.
        """
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["onset_sec", "duration_sec", "midi_pitch"])
            for onset, dur, pitch in notes:
                w.writerow([f"{onset:.6f}", f"{dur:.6f}", pitch])
        click.echo(f"  CSV  -> {csv_path}")

    def write_midi(
        self,
        notes: NoteList,
        bpm: float,
        key_str: str | None,
        mode: str | None,
        melody_path: Path,
        duet_path: Path,
    ) -> None:
        """Write solo melody and two-voice duet MIDI files.

        The duet file contains the original melody on track 1 and a harmony
        voice on track 2. The harmony pitch is computed per
        :func:`diatonic_third_above` using the detected key.

        Args:
            notes: List of ``(onset_sec, duration_sec, midi_pitch)`` tuples.
            bpm: Tempo in beats per minute.
            key_str: Tonic pitch class for diatonic harmony (``None`` = fixed+3).
            mode: Scale mode for diatonic harmony (``None`` = fixed+3).
            melody_path: Output path for the solo melody MIDI file.
            duet_path: Output path for the two-voice duet MIDI file.
        """
        tpb = 480
        quarter_dur = 60.0 / bpm

        # --- Solo melody ---
        mid = MidiFile(ticks_per_beat=tpb)
        tr = MidiTrack()
        mid.tracks.append(tr)
        tr.append(mido.MetaMessage("set_tempo", tempo=bpm2tempo(bpm), time=0))

        cur_time = 0.0
        for onset, dur, pitch in notes:
            delta = max(0, int(round((onset - cur_time) / quarter_dur * tpb)))
            tr.append(Message("note_on", note=pitch, velocity=96, time=delta))
            tr.append(Message("note_off", note=pitch, velocity=64, time=int(round(dur / quarter_dur * tpb))))
            cur_time = onset + dur

        mid.save(melody_path)
        click.echo(f"  MIDI melody -> {melody_path}")

        # --- Two-voice duet ---
        mid2 = MidiFile(ticks_per_beat=tpb)
        t1 = MidiTrack()
        t2 = MidiTrack()
        mid2.tracks += [t1, t2]

        for track in (t1, t2):
            track.append(mido.MetaMessage("set_tempo", tempo=bpm2tempo(bpm), time=0))

        use_diatonic = self.config.harmony_mode == "diatonic" and key_str and mode
        cur_time = 0.0

        for onset, dur, pitch in notes:
            delta = max(0, int(round((onset - cur_time) / quarter_dur * tpb)))
            dur_ticks = int(round(dur / quarter_dur * tpb))

            t1.append(Message("note_on", note=pitch, velocity=100, time=delta))
            t1.append(Message("note_off", note=pitch, velocity=64, time=dur_ticks))

            hp = diatonic_third_above(pitch, key_str, mode) if use_diatonic else pitch + 3
            t2.append(Message("note_on", note=hp, velocity=85, time=delta))
            t2.append(Message("note_off", note=hp, velocity=64, time=dur_ticks))

            cur_time = onset + dur

        mid2.save(duet_path)
        click.echo(f"  MIDI duet   -> {duet_path}")

    def write_musicxml(
        self,
        notes: NoteList,
        bpm: float,
        key_str: str | None,
        mode: str | None,
        out_path: Path,
    ) -> None:
        """Write a two-part MusicXML lead sheet (melody + harmony).

        The melody part uses a Flute instrument; the harmony part uses a
        Pan Flute. Gaps between notes are filled with rests.

        Args:
            notes: List of ``(onset_sec, duration_sec, midi_pitch)`` tuples.
            bpm: Tempo in beats per minute.
            key_str: Tonic pitch class (e.g. ``"D"``), or None.
            mode: Scale mode (``"major"`` or ``"minor"``), or None.
            out_path: Destination path for the ``.musicxml`` file.
        """
        quarter_dur = 60.0 / bpm

        sc = stream.Score()
        sc.insert(0, metadata.Metadata())
        sc.metadata.title = "Lead Sheet (Auto Transcription)"
        sc.metadata.composer = "Auto"

        def _make_part(inst: object, with_notes: bool) -> stream.Part:
            """Build one Part and optionally populate it with notes/rests.

            Args:
                inst: A music21 instrument object.
                with_notes: When True, populate the part with the note list.

            Returns:
                A fully configured :class:`music21.stream.Part`.
            """
            part = stream.Part()
            part.insert(0, inst)
            part.insert(0, meter.TimeSignature("2/4"))
            part.insert(0, m21tempo.MetronomeMark(number=bpm))
            if key_str and mode:
                try:
                    part.insert(0, m21key.Key(key_str, mode))
                except Exception:
                    pass

            if not with_notes:
                return part

            last_time_q = 0.0
            for onset, dur, pitch in notes:
                onset_q = onset / quarter_dur
                gap_q = onset_q - last_time_q
                if gap_q >= _MIN_QL:
                    part.append(m21note.Rest(quarterLength=_quantise_ql(gap_q)))
                n = m21note.Note(pitch)
                n.quarterLength = _quantise_ql(dur / quarter_dur)
                part.append(n)
                last_time_q = onset_q + n.quarterLength

            return part

        part_mel = _make_part(instrument.Flute(), with_notes=True)

        # Build harmony by mirroring melody structure
        part_harm = _make_part(instrument.PanFlute(), with_notes=False)
        for n in part_mel.recurse().notesAndRests:
            ql = _quantise_ql(n.quarterLength)
            if isinstance(n, m21note.Note):
                hp = diatonic_third_above(n.pitch.midi, key_str, mode)
                hn = m21note.Note(hp)
                hn.quarterLength = ql
                part_harm.append(hn)
            else:
                part_harm.append(m21note.Rest(quarterLength=ql))

        sc.append(part_mel)
        sc.append(part_harm)
        sc.write("musicxml", fp=out_path)
        click.echo(f"  MusicXML    -> {out_path}")

    # ── Orchestrator ──────────────────────────────────────────────────────────

    def run(self) -> dict:
        """Run the full melody extraction pipeline and write all outputs.

        Steps:
        1. Load audio.
        2. Estimate BPM.
        3. Detect key and mode.
        4. Extract melody notes via pYIN.
        5. Export CSV, MIDI (melody + duet), and MusicXML.
        6. Write a JSON summary and return it.

        Returns:
            Dictionary with extraction metadata and output file paths.

        Raises:
            click.ClickException: On any unrecoverable processing error.
        """
        self.out_dir.mkdir(parents=True, exist_ok=True)

        y, sr = self._load_audio()
        duration = librosa.get_duration(y=y, sr=sr)

        click.echo("\nAnalysing audio...")
        bpm = self._estimate_bpm(y, sr)
        key_str, mode = self._detect_key(y, sr)
        notes = self._extract_notes(y, sr)

        if not notes:
            raise click.ClickException("No notes were detected. Try adjusting --fmin/--fmax or --min-note-ms.")

        click.echo("\nWriting outputs...")

        csv_path = self.out_dir / "notes.csv"
        midi_melody_path = self.out_dir / "melody.mid"
        midi_duet_path = self.out_dir / "duet.mid"
        musicxml_path = self.out_dir / "lead_sheet.musicxml"

        self.save_csv(notes, csv_path)
        self.write_midi(notes, bpm, key_str, mode, midi_melody_path, midi_duet_path)
        self.write_musicxml(notes, bpm, key_str, mode, musicxml_path)

        summary = {
            "audio": str(self.audio_path),
            "duration_sec": round(float(duration), 3),
            "sr": int(sr),
            "bpm": round(float(bpm), 2),
            "key": key_str,
            "mode": mode,
            "notes_count": len(notes),
            "outputs": {
                "csv": str(csv_path),
                "melody_midi": str(midi_melody_path),
                "duet_midi": str(midi_duet_path),
                "musicxml": str(musicxml_path),
            },
        }

        summary_path = self.out_dir / "summary.json"
        summary_path.write_text(json.dumps(summary, indent=2))
        click.echo(f"  Summary     -> {summary_path}")

        return summary


# ── Click callbacks ───────────────────────────────────────────────────────────


def _parse_note_or_hz(value: str, param_name: str) -> float:
    """Convert a note name (e.g. ``"C4"``) or numeric string to Hz.

    Args:
        value: Note name accepted by librosa (e.g. ``"A4"``) or a plain float string.
        param_name: CLI parameter name, used in error messages.

    Returns:
        Frequency in Hz as a float.

    Raises:
        click.BadParameter: If *value* cannot be parsed as a note or number.
    """
    try:
        return float(librosa.note_to_hz(value))
    except Exception:
        pass
    try:
        return float(value)
    except ValueError:
        raise click.BadParameter(
            f"'{value}' is not a valid note name (e.g. C4) or Hz value.", param_hint=param_name
        )


# ── CLI entry point ───────────────────────────────────────────────────────────


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.argument("audio", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--out", "-o",
    default="out",
    show_default=True,
    help="Output directory for all generated files.",
)
@click.option(
    "--fmin",
    default="C4",
    show_default=True,
    help="Lowest expected pitch as a note name (e.g. C3) or Hz value.",
)
@click.option(
    "--fmax",
    default="A6",
    show_default=True,
    help="Highest expected pitch as a note name (e.g. C7) or Hz value.",
)
@click.option(
    "--min-note-ms",
    default=60.0,
    show_default=True,
    type=float,
    help="Discard notes shorter than this duration (milliseconds).",
)
@click.option(
    "--no-hpss",
    is_flag=True,
    default=False,
    help="Disable harmonic-percussive source separation.",
)
@click.option(
    "--bpm",
    default=None,
    type=float,
    help="Override tempo instead of auto-detecting it.",
)
@click.option(
    "--key",
    default=None,
    type=str,
    help="Override key tonic (e.g. D, F#). Requires --mode.",
)
@click.option(
    "--mode",
    default=None,
    type=click.Choice(VALID_MODES),
    help="Override scale mode. Requires --key.",
)
@click.option(
    "--harmony",
    "harmony_mode",
    default="diatonic",
    show_default=True,
    type=click.Choice(HARMONY_MODES),
    help="Harmony strategy for the duet track.",
)
def main(
    audio: Path,
    out: str,
    fmin: str,
    fmax: str,
    min_note_ms: float,
    no_hpss: bool,
    bpm: float | None,
    key: str | None,
    mode: str | None,
    harmony_mode: str,
) -> None:
    """Transcribe a melody from AUDIO and export MIDI + MusicXML.

    AUDIO is the path to any audio file supported by librosa (mp3, wav, flac, …).

    \b
    Examples:
        python3 extract_melody_cli.py song.mp3
        python3 extract_melody_cli.py song.mp3 --out ./results --fmin C3 --fmax C7
        python3 extract_melody_cli.py song.mp3 --bpm 120 --key D --mode minor
        python3 extract_melody_cli.py song.mp3 --harmony fixed+3 --no-hpss
    """
    # Validate key/mode: both must be provided together or not at all
    if bool(key) != bool(mode):
        raise click.UsageError("--key and --mode must be used together.")

    try:
        fmin_hz = _parse_note_or_hz(fmin, "--fmin")
        fmax_hz = _parse_note_or_hz(fmax, "--fmax")
        config = ExtractionConfig(
            fmin_hz=fmin_hz,
            fmax_hz=fmax_hz,
            min_note_sec=max(0.02, min_note_ms / 1000.0),
            use_hpss=not no_hpss,
            bpm_override=bpm,
            key_override=key,
            mode_override=mode,
            harmony_mode=harmony_mode,
        )
    except ValueError as exc:
        raise click.UsageError(str(exc)) from exc

    extractor = MelodyExtractor(
        audio_path=audio,
        out_dir=Path(out),
        config=config,
    )

    summary = extractor.run()

    click.echo("\n" + json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
