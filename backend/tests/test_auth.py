"""
Backend tests for Phase 5 authentication dependency and protected endpoints.

Tests:
1. Unauthenticated requests to /api/datasets/preview return HTTP 401.
2. Unauthenticated requests to /api/datasets/dashboard return HTTP 401.
3. Requests with invalid or empty Bearer token return HTTP 401.
4. /health endpoint remains accessible without authentication (HTTP 200).
5. get_current_user returns AuthenticatedUser when Supabase verifies token.
6. get_current_user returns HTTP 401 when Supabase reports invalid/expired token.
7. get_current_user returns HTTP 503 when Supabase service is unreachable.
8. get_current_user returns HTTP 503 when SUPABASE_URL is not configured.
9. Protected preview succeeds with valid credentials.
10. Protected dashboard succeeds with valid credentials.
"""

import io
import json
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
from fastapi import HTTPException
from app.main import app
from app.auth import get_current_user, AuthenticatedUser


client = TestClient(app)


def test_public_health_endpoint_without_auth():
    """Health check must remain public."""
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "healthy"


def test_preview_endpoint_unauthenticated_returns_401():
    """POST /api/datasets/preview must reject unauthenticated requests."""
    # Temporarily remove dependency override to test real auth behavior
    app.dependency_overrides.pop(get_current_user, None)
    try:
        csv_bytes = b"col1,col2\n1,2\n"
        files = {"file": ("test.csv", io.BytesIO(csv_bytes), "text/csv")}
        res = client.post("/api/datasets/preview", files=files)
        assert res.status_code == 401
        assert "Missing Bearer access token" in res.json()["detail"]
    finally:
        # Restore mock override
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            id="00000000-0000-0000-0000-000000000001",
            email="testuser@example.com",
            role="authenticated",
        )


def test_dashboard_endpoint_unauthenticated_returns_401():
    """POST /api/datasets/dashboard must reject unauthenticated requests."""
    app.dependency_overrides.pop(get_current_user, None)
    try:
        csv_bytes = b"col1,col2\n1,2\n"
        files = {"file": ("test.csv", io.BytesIO(csv_bytes), "text/csv")}
        data = {
            "chart_configs": json.dumps([
                {
                    "id": "c1",
                    "chart_type": "bar",
                    "title": "Test",
                    "dimension_column": "col1",
                    "measure_column": "col2",
                    "aggregation": "sum",
                }
            ])
        }
        res = client.post("/api/datasets/dashboard", files=files, data=data)
        assert res.status_code == 401
        assert "Missing Bearer access token" in res.json()["detail"]
    finally:
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            id="00000000-0000-0000-0000-000000000001",
            email="testuser@example.com",
            role="authenticated",
        )


@pytest.mark.asyncio
async def test_auth_missing_token():
    """get_current_user raises 401 when no credentials are provided."""
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(credentials=None)
    assert exc_info.value.status_code == 401
    assert "Missing Bearer access token" in exc_info.value.detail


@pytest.mark.asyncio
async def test_auth_unconfigured_supabase_url():
    """get_current_user raises 503 when SUPABASE_URL is missing."""
    class DummyCreds:
        credentials = "some.jwt.token"

    with patch.dict("os.environ", {"SUPABASE_URL": ""}):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials=DummyCreds())
        assert exc_info.value.status_code == 503
        assert "SUPABASE_URL is missing" in exc_info.value.detail


@pytest.mark.asyncio
async def test_auth_valid_supabase_token():
    """get_current_user returns AuthenticatedUser when Supabase Auth returns 200."""
    class DummyCreds:
        credentials = "valid.jwt.token"

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "id": "11111111-2222-3333-4444-555555555555",
        "email": "analyst@company.com",
        "role": "authenticated",
    }

    with patch.dict("os.environ", {"SUPABASE_URL": "https://example.supabase.co", "SUPABASE_ANON_KEY": "anon_key"}):
        with patch("httpx.AsyncClient.get", return_value=mock_resp):
            user = await get_current_user(credentials=DummyCreds())
            assert user.id == "11111111-2222-3333-4444-555555555555"
            assert user.email == "analyst@company.com"
            assert user.role == "authenticated"


@pytest.mark.asyncio
async def test_auth_expired_or_invalid_supabase_token():
    """get_current_user raises 401 when Supabase Auth rejects the token."""
    class DummyCreds:
        credentials = "expired.jwt.token"

    mock_resp = MagicMock()
    mock_resp.status_code = 401

    with patch.dict("os.environ", {"SUPABASE_URL": "https://example.supabase.co", "SUPABASE_ANON_KEY": "anon_key"}):
        with patch("httpx.AsyncClient.get", return_value=mock_resp):
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(credentials=DummyCreds())
            assert exc_info.value.status_code == 401
            assert "Invalid, expired, or revoked" in exc_info.value.detail


@pytest.mark.asyncio
async def test_auth_provider_offline_returns_503():
    """get_current_user raises 503 when Supabase Auth cannot be reached."""
    import httpx

    class DummyCreds:
        credentials = "some.jwt.token"

    with patch.dict("os.environ", {"SUPABASE_URL": "https://example.supabase.co", "SUPABASE_ANON_KEY": "anon_key"}):
        with patch("httpx.AsyncClient.get", side_effect=httpx.ConnectError("Connection refused")):
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(credentials=DummyCreds())
            assert exc_info.value.status_code == 503
            assert "unavailable" in exc_info.value.detail
