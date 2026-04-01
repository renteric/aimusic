"""
test_presets.py - Tests for DownloadConfig validation and preset logic.

Verifies that :class:`~app.services.downloader_cli.DownloadConfig` correctly
accepts valid combinations and rejects unsupported formats / bitrates.
"""

import pytest
from pathlib import Path

from app.services.downloader_cli import DownloadConfig, resolve_output_dir, SUPPORTED_BITRATES
from app.services.constants import SUPPORTED_FORMATS


class TestDownloadConfig:
    """Unit tests for DownloadConfig dataclass validation."""

    def test_valid_mp3_320k(self, tmp_path):
        """A valid mp3/320k configuration should construct without error."""
        cfg = DownloadConfig(audio_format="mp3", bitrate="320k", output_dir=tmp_path)
        assert cfg.audio_format == "mp3"
        assert cfg.bitrate == "320k"

    def test_all_supported_formats_accepted(self, tmp_path):
        """Every format in SUPPORTED_FORMATS should be accepted."""
        for fmt in SUPPORTED_FORMATS:
            cfg = DownloadConfig(audio_format=fmt, bitrate="320k", output_dir=tmp_path)
            assert cfg.audio_format == fmt

    def test_unsupported_format_raises(self, tmp_path):
        """An unsupported format should raise ValueError."""
        with pytest.raises(ValueError, match="Unsupported format"):
            DownloadConfig(audio_format="mp4", bitrate="320k", output_dir=tmp_path)

    def test_unsupported_bitrate_raises(self, tmp_path):
        """An unsupported bitrate should raise ValueError."""
        with pytest.raises(ValueError, match="Unsupported bitrate"):
            DownloadConfig(audio_format="mp3", bitrate="999k", output_dir=tmp_path)

    def test_verbose_flag_defaults_false(self, tmp_path):
        """verbose should default to False."""
        cfg = DownloadConfig(audio_format="mp3", bitrate="320k", output_dir=tmp_path)
        assert cfg.verbose is False

    def test_force_flag_can_be_set(self, tmp_path):
        """force flag should be settable to True."""
        cfg = DownloadConfig(audio_format="flac", bitrate="auto", output_dir=tmp_path, force=True)
        assert cfg.force is True


class TestResolveOutputDir:
    """Unit tests for the resolve_output_dir path helper."""

    def test_empty_string_returns_media(self):
        """Empty output string should resolve to ./media."""
        result = resolve_output_dir("")
        assert result.name == "media"

    def test_named_subfolder(self):
        """A named subfolder should be appended to ./media."""
        result = resolve_output_dir("Quena")
        assert result.parts[-1] == "Quena"
        assert "media" in result.parts

    def test_spaces_stripped(self):
        """Internal spaces in the folder name should be stripped."""
        result = resolve_output_dir("My Music")
        assert " " not in str(result)

    def test_dotdot_raises(self):
        """Path with .. should raise BadParameter."""
        import click
        with pytest.raises(click.BadParameter):
            resolve_output_dir("../escape")
