"""E2E tests for authentication flow."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    """Test health check endpoint."""
    response = await client.get("/health")
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_root_endpoint(client: AsyncClient):
    """Test root endpoint."""
    response = await client.get("/")
    
    assert response.status_code == 200
    data = response.json()
    assert "name" in data
    assert data["name"] == "Professor MVP"


@pytest.mark.asyncio
async def test_unauthorized_access(client: AsyncClient):
    """Test that protected endpoints require authentication."""
    response = await client.get("/api/auth/me")
    
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_invalid_token(client: AsyncClient):
    """Test that invalid tokens are rejected."""
    response = await client.get(
        "/api/auth/me",
        headers={"Authorization": "Bearer invalid_token"}
    )
    
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token_invalid(client: AsyncClient):
    """Test refresh with invalid token."""
    response = await client.post(
        "/api/auth/refresh",
        json={"refresh_token": "invalid_refresh_token"}
    )
    
    assert response.status_code == 401
