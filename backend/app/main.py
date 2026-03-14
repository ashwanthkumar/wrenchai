"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db.database import init_db, async_session
from app.db.seed import seed_admin


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""
    # Initialize database tables
    await init_db()

    # Seed default admin user
    async with async_session() as db:
        await seed_admin(db)

    yield


app = FastAPI(title="WrenchAI", lifespan=lifespan)


def main():
    """Run the application with uvicorn."""
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
