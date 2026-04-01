"""
conftest.py - Shared pytest fixtures for AI-Music tests.

Provides a pre-configured FastAPI test client and a temporary SQLite database
that is created fresh for each test session.
"""

import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Point the app at a temporary DB and use a fixed secret key so tests are
# deterministic across runs.
# Force-assign test values so they always override shell env and any loaded .env file.
os.environ["API_DEBUG"] = "true"
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production"
os.environ["ADMIN_USERNAME"] = "testadmin"
os.environ["ADMIN_PASSWORD"] = "testpassword123"


@pytest.fixture(scope="session")
def tmp_db(tmp_path_factory) -> Path:
    """Create a temporary directory for the test database.

    Yields:
        Path to the temporary database file.
    """
    db_dir = tmp_path_factory.mktemp("data")
    db_path = db_dir / "test.db"
    os.environ["DB_PATH"] = str(db_path)
    return db_path


@pytest.fixture(scope="session")
def app(tmp_db):
    """Create and configure a FastAPI application for testing.

    Args:
        tmp_db: Fixture that sets DB_PATH to an isolated test database.

    Yields:
        Configured :class:`~fastapi.FastAPI` application instance.
    """
    from app import create_app

    fastapi_app = create_app()
    yield fastapi_app


@pytest.fixture(scope="session")
def client(app):
    """Return a FastAPI TestClient (synchronous).

    Args:
        app: The test FastAPI application.

    Returns:
        :class:`~fastapi.testclient.TestClient` for making requests.
    """
    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture(scope="session")
def auth_client(client):
    """Return a TestClient that carries a valid auth cookie.

    Performs a login request and captures the ``access_token`` cookie so
    subsequent requests in the session are authenticated as the test admin.

    Args:
        client: Unauthenticated test client.

    Returns:
        The same client after a successful login POST.
    """
    resp = client.post(
        "/api/auth/login",
        json={"username": "testadmin", "password": "testpassword123"},
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return client
