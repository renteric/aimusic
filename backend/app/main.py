"""
main.py - Uvicorn entry point for AI-Music.

Usage (Uvicorn from backend/ directory)::

    uvicorn app.main:app --host 0.0.0.0 --port 5000 --workers 1

Usage (direct, development only)::

    python -m app.main
"""

from . import create_app
from .core.config import AppConfig

app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=AppConfig.HOST,
        port=AppConfig.PORT,
        reload=AppConfig.DEBUG,
    )
