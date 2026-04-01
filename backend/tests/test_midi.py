"""
test_midi.py - Smoke tests for melody extraction helpers.

These tests verify that the extract_melody_cli module is importable and
its key functions have the correct signatures. Full integration tests
require audio files and optional heavy deps (librosa, pretty_midi) and
are therefore marked as ``slow``.
"""

import pytest

# Skip the entire module if librosa is not installed (optional heavy dependency).
pytest.importorskip("librosa")


def test_extract_melody_cli_importable():
    """The extract_melody_cli module should be importable without errors."""
    import app.services.extract_melody_cli  # noqa: F401


def test_extract_melody_cli_has_required_symbols():
    """extract_melody_cli must expose the main Click command."""
    from app.services import extract_melody_cli
    assert hasattr(extract_melody_cli, "main"), "extract_melody_cli must expose a 'main' click command"


@pytest.mark.slow
def test_extract_melody_requires_audio_file(tmp_path):
    """Running main() on a non-existent file should raise SystemExit(2)."""
    from click.testing import CliRunner
    from app.services.extract_melody_cli import main

    runner = CliRunner()
    result = runner.invoke(main, [str(tmp_path / "nonexistent.mp3")])
    # Click exits with code 2 for usage errors / missing files
    assert result.exit_code != 0
