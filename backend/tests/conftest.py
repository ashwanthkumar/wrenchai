"""Shared pytest fixtures for WrenchAI backend tests."""

from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.db.models import Base


@pytest_asyncio.fixture
async def db():
    """Provide an async database session backed by in-memory SQLite."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def client(db):
    """Provide an async HTTP client with dependency overrides for testing."""
    from app.main import app
    from app.api.deps import get_db, get_current_user, get_session_manager

    # Mock session manager
    mock_session_manager = AsyncMock()
    mock_session_manager.send_message = AsyncMock(
        return_value="This is a mock AI response about car repair."
    )

    # Mock Firebase auth — valid tokens return test UID, invalid raises
    async def mock_verify_token(token: str) -> str:
        if token == "invalid-token":
            raise ValueError("Invalid token")
        return "test-uid-123"

    # Patch verify_token in all modules that imported it by value
    import app.services.firebase_auth as fb_module
    import app.api.deps as deps_module
    import app.api.auth as auth_module

    original_fb = fb_module.verify_token
    original_deps = deps_module.verify_token
    original_auth = auth_module.verify_token

    fb_module.verify_token = mock_verify_token
    deps_module.verify_token = mock_verify_token
    auth_module.verify_token = mock_verify_token

    # Override dependencies
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_session_manager] = lambda: mock_session_manager

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    # Cleanup
    app.dependency_overrides.clear()
    fb_module.verify_token = original_fb
    deps_module.verify_token = original_deps
    auth_module.verify_token = original_auth
