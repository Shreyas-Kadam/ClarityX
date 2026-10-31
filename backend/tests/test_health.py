import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app


@pytest.mark.anyio
async def test_root_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert data["message"] == "Welcome to ClarityX API"
        assert data["project"] == "ClarityX"


@pytest.mark.anyio
async def test_health_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["project"] == "ClarityX"
        # Confirm health endpoint reports only backend application status, not untested database health
        assert "database" not in data


@pytest.mark.anyio
async def test_validation_error_sanitization():
    from app.core.exceptions import sanitize_validation_errors

    # Raw Pydantic error dictionary containing a sensitive input value
    raw_errors = [
        {
            "type": "string_too_short",
            "loc": ("body", "password"),
            "msg": "String should have at least 8 characters",
            "input": "super_secret_password_123",
            "ctx": {"min_length": 8},
        }
    ]

    sanitized = sanitize_validation_errors(raw_errors)
    assert len(sanitized) == 1
    # Verify raw input and context were stripped
    assert "input" not in sanitized[0]
    assert "ctx" not in sanitized[0]
    assert sanitized[0]["loc"] == ("body", "password")
    assert sanitized[0]["msg"] == "String should have at least 8 characters"


@pytest.mark.anyio
async def test_cors_headers():
    transport = ASGITransport(app=app)
    headers = {
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "GET",
    }
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.options("/health", headers=headers)
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"


@pytest.mark.anyio
async def test_not_found_standard_envelope():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/nonexistent-endpoint")
        assert response.status_code == 404
        data = response.json()
        assert data["success"] is False
        assert "message" in data
        assert "detail" in data

