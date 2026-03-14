"""Tests for auth API endpoints."""

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app


pytestmark = pytest.mark.asyncio


async def test_verify_valid_token(client: AsyncClient):
    """POST /api/auth/verify with valid token returns user_id."""
    resp = await client.post("/api/auth/verify", json={"firebase_token": "valid-token"})
    assert resp.status_code == 200
    data = resp.json()
    assert "user_id" in data
    assert data["user_id"] == "test-uid-123"


async def test_verify_invalid_token(client: AsyncClient):
    """POST /api/auth/verify with invalid token returns 401."""
    resp = await client.post("/api/auth/verify", json={"firebase_token": "invalid-token"})
    assert resp.status_code == 401
