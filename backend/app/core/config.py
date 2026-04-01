"""
config.py - Centralised application configuration for AI-Music.

All settings are read from environment variables (loaded from .env by the
caller). Safe defaults let the app start without any env configuration,
but SECRET_KEY and ADMIN_PASSWORD must be overridden in production.
"""

import os
from pathlib import Path


class AppConfig:
    """Central configuration object populated from environment variables.

    Every public attribute maps 1-to-1 to an env var of the same name.
    Relative paths (MEDIA_DIR, DB_PATH) are resolved against BASE_DIR.

    Attributes:
        HOST: Bind address for Uvicorn.
        PORT: TCP port for the web server.
        DEBUG: Enable debug mode — always False in production.
        SECRET_KEY: JWT signing key — change in production.
        BASE_DIR: Project root directory (parent of the ``app/`` package).
        MEDIA_DIR: Directory where downloaded media files are stored.
        STEMS_DIR: Sub-directory inside MEDIA_DIR for stem extraction outputs.
        DOCS_DIR: Directory for user markdown documents.
        DB_PATH: Path to the SQLite database file.
        JOB_MAX_AGE_SECONDS: Age limit for in-memory download job records.
        TRANSCRIBE_SERVICE_URL: URL of the external Whisper transcription service.
        SEPARATOR_URL: URL of the separator microservice (internal Docker network).
        CORS_ORIGINS: Allowed CORS origins (Vite dev server in development).
        ADMIN_USERNAME: Login name for the auto-created admin account.
        ADMIN_PASSWORD: Password for the auto-created admin account.
        ACCESS_TOKEN_EXPIRE_MINUTES: JWT token lifetime in minutes.
    """

    HOST: str = os.getenv("API_HOST", "0.0.0.0")
    PORT: int = int(os.getenv("API_PORT", "5000"))
    DEBUG: bool = os.getenv("API_DEBUG", "false").lower() in ("1", "true", "yes")
    SECRET_KEY: str = os.getenv("SECRET_KEY", os.urandom(32).hex())

    #: Container/backend root: parent of the ``app/`` package (= /app in Docker, backend/ locally).
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent

    _media_env: str = os.getenv("MEDIA_DIR", "media")
    MEDIA_DIR: Path = (
        Path(_media_env) if Path(_media_env).is_absolute() else BASE_DIR / _media_env
    )

    #: Stem extraction outputs live here (inside MEDIA_DIR).
    STEMS_DIR: Path = MEDIA_DIR / "stems"

    _docs_env: str = os.getenv("DOCS_DIR", "docs")
    DOCS_DIR: Path = (
        Path(_docs_env) if Path(_docs_env).is_absolute() else BASE_DIR / _docs_env
    )

    _db_env: str = os.getenv("DB_PATH", "data/app.db")
    DB_PATH: Path = (
        Path(_db_env) if Path(_db_env).is_absolute() else BASE_DIR / _db_env
    )

    JOB_MAX_AGE_SECONDS: int = int(os.getenv("JOB_MAX_AGE_SECONDS", "3600"))
    TRANSCRIBE_SERVICE_URL: str = os.getenv("TRANSCRIBE_SERVICE_URL", "http://transcribe:9000")
    SEPARATOR_URL: str = os.getenv("SEPARATOR_URL", "http://separator:8000")

    CORS_ORIGINS: list[str] = [
        o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()
    ]

    ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "")

    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))
