"""
__init__.py - AI-Music FastAPI Application Package.

Exposes :func:`create_app` as the single entry point for constructing the
FastAPI application with all middleware, routers, and startup logic wired
together. Use ``app.main:app`` as the Uvicorn target.
"""

import sys

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Load .env before reading AppConfig (which reads os.getenv at import time).
load_dotenv()

from .core.config import AppConfig  # noqa: E402
from .core.security import SecurityHeadersMiddleware  # noqa: E402
from .models.user import User, init_db  # noqa: E402


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Initialises CORS and security middleware, registers all API routers,
    bootstraps the SQLite database, and seeds a default admin user if no
    users exist.

    Returns:
        Configured and ready-to-serve :class:`~fastapi.FastAPI` instance.
    """
    app = FastAPI(
        title="AI-Music",
        description="Full-stack music downloader and stem extractor.",
        version="2.0.0",
        # Disable automatic /docs in production; keep in debug mode
        docs_url="/api/docs-ui" if AppConfig.DEBUG else None,
        redoc_url=None,
    )

    # ── CORS ───────────────────────────────────────────────────────────────────
    # Only enabled when CORS_ORIGINS is set (Vite dev server in development).
    if AppConfig.CORS_ORIGINS:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=AppConfig.CORS_ORIGINS,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            allow_headers=["Content-Type"],
        )

    # ── Security headers ───────────────────────────────────────────────────────
    app.add_middleware(SecurityHeadersMiddleware)

    # ── Routers ────────────────────────────────────────────────────────────────
    from .api.admin import router as admin_router
    from .api.ai import router as ai_router
    from .api.auth import router as auth_router
    from .api.docs import router as docs_router
    from .api.download import router as download_router
    from .api.media import router as media_router
    from .api.melody import router as melody_router
    from .api.stem import router as stem_router

    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(download_router)
    app.include_router(media_router)
    app.include_router(docs_router)
    app.include_router(stem_router)
    app.include_router(ai_router)
    app.include_router(melody_router)

    # ── Config endpoint ────────────────────────────────────────────────────────
    from .services.constants import SUPPORTED_FORMATS
    from .services.downloader_cli import SUPPORTED_BITRATES

    @app.get("/api/config", tags=["config"])
    def api_config() -> dict:
        """Return application configuration for the Vue.js frontend.

        Returns:
            JSON with ``formats`` and ``bitrates`` arrays.
        """
        return {"formats": SUPPORTED_FORMATS, "bitrates": SUPPORTED_BITRATES}

    # ── Database bootstrap ─────────────────────────────────────────────────────
    _bootstrap_db()

    return app


def _bootstrap_db() -> None:
    """Initialise the SQLite database and seed the default admin user.

    Creates tables if they do not exist, then:
    - On a fresh install: creates the admin account with role ``superadmin``.
    - On an existing install: promotes the first user to ``superadmin`` if no
      superadmin account exists yet (migration from pre-role schema).
    """
    init_db()

    if User.count() == 0:
        password = AppConfig.ADMIN_PASSWORD
        if not password:
            password = "changeme123"
            print(
                "[WARNING] No ADMIN_PASSWORD set — default admin password is 'changeme123'. "
                "Change it immediately via the UI.",
                file=sys.stderr,
            )
        User.create(AppConfig.ADMIN_USERNAME, password, role="superadmin")
        print(f"[INFO] Created superadmin user '{AppConfig.ADMIN_USERNAME}'.", file=sys.stderr)
    else:
        User.ensure_superadmin()
