"""Tests for messages API endpoints."""

import pytest
from httpx import AsyncClient

from app.db.models import Manual, ManualStatus, Session, Message


pytestmark = pytest.mark.asyncio


async def _setup_session(db, user_id: str = "test-uid-123") -> str:
    """Helper to create manual + session, returns session id."""
    from datetime import datetime, timezone

    manual = Manual(
        id="manual-1",
        filename="test.pdf",
        car_make="Toyota",
        car_model="Camry",
        car_year=2024,
        status=ManualStatus.completed,
        created_at=datetime.now(timezone.utc),
    )
    db.add(manual)

    session = Session(
        id="session-1",
        user_id=user_id,
        manual_id="manual-1",
        title="Test session",
        created_at=datetime.now(timezone.utc),
    )
    db.add(session)
    await db.commit()
    return "session-1"


async def test_send_message_returns_response(client: AsyncClient, db):
    """POST /api/sessions/{id}/message returns assistant message."""
    await _setup_session(db)
    resp = await client.post(
        "/api/sessions/session-1/message",
        json={"content": "How do I change the oil?"},
        headers={"Authorization": "Bearer valid-token"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["role"] == "assistant"
    assert len(data["content"]) > 0


async def test_send_message_saves_both_messages(client: AsyncClient, db):
    """After sending, DB contains both user and assistant messages."""
    await _setup_session(db)
    await client.post(
        "/api/sessions/session-1/message",
        json={"content": "How do I change the oil?"},
        headers={"Authorization": "Bearer valid-token"},
    )
    # Check messages in DB
    from sqlalchemy import select
    result = await db.execute(
        select(Message).where(Message.session_id == "session-1").order_by(Message.created_at)
    )
    messages = result.scalars().all()
    assert len(messages) == 2
    assert messages[0].role == "user"
    assert messages[0].content == "How do I change the oil?"
    assert messages[1].role == "assistant"


async def test_send_message_wrong_session(client: AsyncClient, db):
    """POST to session owned by different user returns 403."""
    await _setup_session(db, user_id="other-user")
    resp = await client.post(
        "/api/sessions/session-1/message",
        json={"content": "Hello"},
        headers={"Authorization": "Bearer valid-token"},
    )
    assert resp.status_code == 403


async def test_get_messages(client: AsyncClient, db):
    """GET /api/sessions/{id}/messages returns messages in order."""
    session_id = await _setup_session(db)
    # Send a message first to populate
    await client.post(
        f"/api/sessions/{session_id}/message",
        json={"content": "How do I change the oil?"},
        headers={"Authorization": "Bearer valid-token"},
    )
    resp = await client.get(
        f"/api/sessions/{session_id}/messages",
        headers={"Authorization": "Bearer valid-token"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["role"] == "user"
    assert data[1]["role"] == "assistant"


async def test_get_messages_empty_session(client: AsyncClient, db):
    """GET on new session returns empty list."""
    session_id = await _setup_session(db)
    resp = await client.get(
        f"/api/sessions/{session_id}/messages",
        headers={"Authorization": "Bearer valid-token"},
    )
    assert resp.status_code == 200
    assert resp.json() == []
