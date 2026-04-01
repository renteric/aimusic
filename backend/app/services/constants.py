"""
constants.py - Shared constants for AI-Music.

Centralised definitions imported by the downloader, transcriber, and
Flask application to keep format/bitrate lists in a single place.
"""

#: Audio formats supported by yt-dlp extraction and the web UI.
SUPPORTED_FORMATS: list[str] = ["mp3", "flac", "m4a", "ogg", "opus", "wav"]
