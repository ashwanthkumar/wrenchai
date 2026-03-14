"""FastAPI dependencies for request handling."""

from collections.abc import AsyncGenerator

from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db as _get_db
from app.services.firebase_auth import verify_token
from app.services.session_manager import SessionManager
from app.services.rag import RAGService


# Re-export get_db for use as a dependency
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session."""
    async for session in _get_db():
        yield session


# Global SessionManager instance
_session_manager: SessionManager | None = None

# Global RAGService instance
_rag_service: RAGService | None = None


def set_session_manager(sm: SessionManager) -> None:
    """Set the global SessionManager instance (called once at startup)."""
    global _session_manager
    _session_manager = sm


def get_session_manager() -> SessionManager:
    """Return the global SessionManager instance."""
    if _session_manager is None:
        raise RuntimeError("SessionManager not initialized")
    return _session_manager


def set_rag_service(rag: RAGService) -> None:
    """Set the global RAGService instance (called once at startup)."""
    global _rag_service
    _rag_service = rag


def get_rag_service() -> RAGService:
    """Return the global RAGService instance."""
    if _rag_service is None:
        raise RuntimeError("RAGService not initialized")
    return _rag_service


async def get_current_user(authorization: str = Header(...)) -> str:
    """Extract Bearer token from Authorization header and verify with Firebase.

    Returns the Firebase UID.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")

    token = authorization[len("Bearer "):]
    try:
        uid = await verify_token(token)
        return uid
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
