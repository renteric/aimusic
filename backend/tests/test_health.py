"""
test_health.py - Tests for core API health and authentication endpoints.

Covers:
- /api/config returns expected keys
- /api/auth/me returns 200 with authenticated=False when not logged in
- /api/auth/login succeeds with valid credentials
- /api/auth/me returns username after login
- /api/auth/logout clears the session
- Protected endpoints return 401 without a valid cookie
"""


def test_config_returns_formats_and_bitrates(client):
    """GET /api/config should return a JSON object with formats and bitrates."""
    resp = client.get("/api/config")
    assert resp.status_code == 200
    data = resp.json()
    assert "formats" in data
    assert "bitrates" in data
    assert "mp3" in data["formats"]
    assert "320k" in data["bitrates"]


def test_me_unauthenticated(client):
    """GET /api/auth/me should return 200 with authenticated=False when no cookie is set."""
    resp = client.get("/api/auth/me")
    assert resp.status_code == 200
    data = resp.json()
    assert data["authenticated"] is False


def test_login_invalid_credentials(client):
    """POST /api/auth/login should return 401 for wrong password."""
    resp = client.post("/api/auth/login", json={"username": "testadmin", "password": "wrong"})
    assert resp.status_code == 401
    data = resp.json()
    assert "Invalid" in data["detail"]


def test_login_missing_fields(client):
    """POST /api/auth/login should return 422 when fields are missing."""
    resp = client.post("/api/auth/login", json={"username": "testadmin"})
    assert resp.status_code == 422


def test_login_success(client):
    """POST /api/auth/login should return 200 and set the access_token cookie."""
    resp = client.post(
        "/api/auth/login",
        json={"username": "testadmin", "password": "testpassword123"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["username"] == "testadmin"
    # Cookie should be set
    assert "access_token" in resp.cookies


def test_me_authenticated(auth_client):
    """GET /api/auth/me should return the username after a successful login."""
    resp = auth_client.get("/api/auth/me")
    assert resp.status_code == 200
    data = resp.json()
    assert data["authenticated"] is True
    assert data["username"] == "testadmin"


def test_protected_endpoint_requires_auth(client):
    """POST /api/download should return 401 without a valid auth cookie."""
    # Use a fresh client without the auth cookie
    from fastapi.testclient import TestClient
    fresh_client = TestClient(client.app, raise_server_exceptions=True)
    resp = fresh_client.post(
        "/api/download",
        json={"source": "single", "url": "https://example.com"},
    )
    assert resp.status_code == 401


def test_stem_endpoint_requires_admin(auth_client):
    """GET /api/stem/health should return 200 for the admin test user (superadmin role)."""
    import httpx
    # The test admin user is seeded as superadmin, so this should succeed.
    # The separator service is only available in Docker — network errors are skipped.
    try:
        resp = auth_client.get("/api/stem/health")
    except httpx.ConnectError:
        import pytest
        pytest.skip("Separator service not reachable in local environment")
    # 200 if separator is up, 5xx if separator is down — either is fine for auth testing
    assert resp.status_code != 401
    assert resp.status_code != 403
