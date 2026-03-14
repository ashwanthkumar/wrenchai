"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.deps import set_rag_service, set_session_manager
from app.api.router import api_router
from app.config import settings
from app.db.database import init_db, async_session
from app.db.seed import seed_admin
from app.services.rag import RAGService
from app.services.session_manager import SessionManager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""
    # Initialize database tables
    await init_db()

    # Seed default admin user
    async with async_session() as db:
        await seed_admin(db)

    # Initialize services
    rag_service = RAGService(settings.chromadb_path)
    set_rag_service(rag_service)

    session_manager = SessionManager(
        rag_service=rag_service,
        sessions_dir=settings.sessions_dir,
        model=settings.claude_model,
        idle_timeout_minutes=settings.session_idle_timeout_minutes,
        cleanup_interval_minutes=settings.session_cleanup_interval_minutes,
    )
    await session_manager.start_cleanup_task()
    set_session_manager(session_manager)

    yield

    await session_manager.close_all()


app = FastAPI(title="WrenchAI", lifespan=lifespan)
app.include_router(api_router)


def main():
    """Run the application with uvicorn."""
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
