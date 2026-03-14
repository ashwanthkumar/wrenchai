"""Message API endpoints — core conversation flow."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_session_manager
from app.db.models import Message, Session
from app.schemas.api import MessageCreate, MessageResponse
from app.services.session_manager import SessionManager

router = APIRouter(prefix="/sessions/{session_id}", tags=["messages"])


async def _verify_session_ownership(
    session_id: str, user_id: str, db: AsyncSession
) -> Session:
    """Verify the session exists and belongs to the user. Returns the session."""
    result = await db.execute(select(Session).where(Session.id == session_id))
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to access this session")
    return session


@router.post("/message", response_model=MessageResponse)
async def send_message(
    session_id: str,
    req: MessageCreate,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    session_manager: SessionManager = Depends(get_session_manager),
) -> MessageResponse:
    """Send a user message and get an AI assistant response."""
    session = await _verify_session_ownership(session_id, user_id, db)

    # Save user message
    user_msg = Message(
        id=str(uuid.uuid4()),
        session_id=session_id,
        role="user",
        content=req.content,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user_msg)
    await db.commit()

    # Get AI response via session manager
    response_text = await session_manager.send_message(
        session_id=session_id,
        user_message=req.content,
        manual_id=session.manual_id,
    )

    # Save assistant message
    assistant_msg = Message(
        id=str(uuid.uuid4()),
        session_id=session_id,
        role="assistant",
        content=response_text,
        created_at=datetime.now(timezone.utc),
    )
    db.add(assistant_msg)
    await db.commit()

    return MessageResponse(
        id=assistant_msg.id,
        role=assistant_msg.role,
        content=assistant_msg.content,
        created_at=assistant_msg.created_at,
    )


@router.get("/messages", response_model=list[MessageResponse])
async def get_messages(
    session_id: str,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MessageResponse]:
    """Get all messages for a session in chronological order."""
    await _verify_session_ownership(session_id, user_id, db)

    result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at)
    )
    messages = result.scalars().all()
    return [
        MessageResponse(
            id=m.id,
            role=m.role,
            content=m.content,
            created_at=m.created_at,
        )
        for m in messages
    ]
