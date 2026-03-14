"""Session API endpoints."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.db.models import Manual, Session
from app.schemas.api import SessionCreate, SessionResponse

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("/", response_model=SessionResponse)
async def create_session(
    req: SessionCreate,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SessionResponse:
    """Create a new conversation session for the authenticated user."""
    # Verify manual exists
    result = await db.execute(select(Manual).where(Manual.id == req.manual_id))
    manual = result.scalar_one_or_none()
    if manual is None:
        raise HTTPException(status_code=404, detail="Manual not found")

    session = Session(
        id=str(uuid.uuid4()),
        user_id=user_id,
        manual_id=req.manual_id,
        title=req.title,
        created_at=datetime.now(timezone.utc),
    )
    db.add(session)
    await db.commit()

    return SessionResponse(
        id=session.id,
        manual_id=session.manual_id,
        title=session.title,
        created_at=session.created_at,
    )


@router.get("/", response_model=list[SessionResponse])
async def list_sessions(
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SessionResponse]:
    """List all sessions for the authenticated user."""
    result = await db.execute(
        select(Session).where(Session.user_id == user_id).order_by(Session.created_at)
    )
    sessions = result.scalars().all()
    return [
        SessionResponse(
            id=s.id,
            manual_id=s.manual_id,
            title=s.title,
            created_at=s.created_at,
        )
        for s in sessions
    ]
