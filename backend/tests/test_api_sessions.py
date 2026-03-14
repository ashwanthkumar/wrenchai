"""Tests for sessions API endpoints."""

import pytest
from httpx import AsyncClient

from app.db.models import Manual, ManualStatus


pytestmark = pytest.mark.asyncio


async def _create_manual(db, manual_id: str = "manual-1") -> Manual:
    """Helper to create a manual in the database."""
    from datetime import datetime, timezone

    manual = Manual(
        id=manual_id,
        filename="test.pdf",
        car_make="Toyota",
        car_model="Camry",
        car_year=2024,
        status=ManualStatus.completed,
        created_at=datetime.now(timezone.utc),
    )
    db.add(manual)
    await db.commit()
    return manual


async def test_create_session(client: AsyncClient, db):
    """POST /api/sessions/ with valid body creates session, returns 200 with id."""
    await _create_manual(db)
    resp = await client.post(
        "/api/sessions/",
        json={"manual_id": "manual-1", "title": "Help with brakes"},
        headers={"Authorization": "Bearer valid-token"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert data["manual_id"] == "manual-1"
    assert data["title"] == "Help with brakes"


async def test_create_session_invalid_manual(client: AsyncClient, db):
    """POST with non-existent manual_id returns 404."""
    resp = await client.post(
        "/api/sessions/",
        json={"manual_id": "nonexistent", "title": "Test"},
        headers={"Authorization": "Bearer valid-token"},
    )
    assert resp.status_code == 404


async def test_list_sessions(client: AsyncClient, db):
    """GET /api/sessions/ returns only sessions owned by the authenticated user."""
    await _create_manual(db)
    # Create two sessions
    await client.post(
        "/api/sessions/",
        json={"manual_id": "manual-1", "title": "Session 1"},
        headers={"Authorization": "Bearer valid-token"},
    )
    await client.post(
        "/api/sessions/",
        json={"manual_id": "manual-1", "title": "Session 2"},
        headers={"Authorization": "Bearer valid-token"},
    )
    resp = await client.get(
        "/api/sessions/",
        headers={"Authorization": "Bearer valid-token"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2


async def test_list_sessions_empty(client: AsyncClient, db):
    """GET returns empty list for user with no sessions."""
    resp = await client.get(
        "/api/sessions/",
        headers={"Authorization": "Bearer valid-token"},
    )
    assert resp.status_code == 200
    assert resp.json() == []
