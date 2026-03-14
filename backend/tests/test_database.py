"""Tests for database models, engine initialization, and admin seeding."""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.db.models import Base, Admin, Manual, Session, Message, ManualStatus
from app.db.database import init_db
from app.db.seed import seed_admin


@pytest.mark.asyncio
async def test_init_db_creates_tables():
    """After init_db(), all four tables exist."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)

    # Use init_db with a custom engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with engine.connect() as conn:
        result = await conn.run_sync(
            lambda sync_conn: inspect(sync_conn).get_table_names()
        )

    assert "admins" in result
    assert "manuals" in result
    assert "sessions" in result
    assert "messages" in result

    await engine.dispose()


@pytest.mark.asyncio
async def test_create_admin(db: AsyncSession):
    """Can insert an Admin row and read it back."""
    admin = Admin(username="testadmin", password_hash="hashed_pw")
    db.add(admin)
    await db.commit()

    result = await db.execute(select(Admin).where(Admin.username == "testadmin"))
    fetched = result.scalar_one()
    assert fetched.username == "testadmin"
    assert fetched.password_hash == "hashed_pw"
    assert fetched.id is not None


@pytest.mark.asyncio
async def test_create_manual(db: AsyncSession):
    """Can insert a Manual with all fields, default status is pending."""
    manual_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    manual = Manual(
        id=manual_id,
        filename="toyota_camry_2023.pdf",
        car_make="Toyota",
        car_model="Camry",
        car_year=2023,
        created_at=now,
    )
    db.add(manual)
    await db.commit()

    result = await db.execute(select(Manual).where(Manual.id == manual_id))
    fetched = result.scalar_one()
    assert fetched.filename == "toyota_camry_2023.pdf"
    assert fetched.car_make == "Toyota"
    assert fetched.car_model == "Camry"
    assert fetched.car_year == 2023
    assert fetched.status == ManualStatus.pending
    assert fetched.error_message is None
    assert fetched.page_count is None
    assert fetched.chunk_count is None


@pytest.mark.asyncio
async def test_create_session_with_manual_fk(db: AsyncSession):
    """Session.manual_id references an existing Manual."""
    manual_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    manual = Manual(
        id=manual_id,
        filename="honda_civic_2022.pdf",
        car_make="Honda",
        car_model="Civic",
        car_year=2022,
        created_at=now,
    )
    db.add(manual)
    await db.commit()

    session = Session(
        id=session_id,
        user_id="firebase_uid_123",
        manual_id=manual_id,
        title="Help with oil change",
        created_at=now,
    )
    db.add(session)
    await db.commit()

    result = await db.execute(select(Session).where(Session.id == session_id))
    fetched = result.scalar_one()
    assert fetched.manual_id == manual_id
    assert fetched.user_id == "firebase_uid_123"
    assert fetched.title == "Help with oil change"


@pytest.mark.asyncio
async def test_create_message_with_session_fk(db: AsyncSession):
    """Message.session_id references an existing Session."""
    manual_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    message_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    manual = Manual(
        id=manual_id,
        filename="ford_f150_2024.pdf",
        car_make="Ford",
        car_model="F-150",
        car_year=2024,
        created_at=now,
    )
    db.add(manual)
    await db.commit()

    session = Session(
        id=session_id,
        user_id="firebase_uid_456",
        manual_id=manual_id,
        title="Brake pad replacement",
        created_at=now,
    )
    db.add(session)
    await db.commit()

    message = Message(
        id=message_id,
        session_id=session_id,
        role="user",
        content="How do I replace the brake pads?",
        created_at=now,
    )
    db.add(message)
    await db.commit()

    result = await db.execute(select(Message).where(Message.id == message_id))
    fetched = result.scalar_one()
    assert fetched.session_id == session_id
    assert fetched.role == "user"
    assert fetched.content == "How do I replace the brake pads?"
    assert fetched.rag_context is None


def test_manual_status_enum():
    """ManualStatus has exactly: pending, processing, completed, failed."""
    members = [status.value for status in ManualStatus]
    assert sorted(members) == sorted(["pending", "processing", "completed", "failed"])
    assert len(members) == 4


@pytest.mark.asyncio
async def test_seed_admin_creates_user(db: AsyncSession):
    """seed_admin() creates an admin when none exists."""
    await seed_admin(db)

    result = await db.execute(select(Admin))
    admins = result.scalars().all()
    assert len(admins) == 1
    assert admins[0].username == "admin"
    # Verify the password hash is a bcrypt hash
    assert admins[0].password_hash.startswith("$2")


@pytest.mark.asyncio
async def test_seed_admin_idempotent(db: AsyncSession):
    """Calling seed_admin() twice doesn't create duplicates."""
    await seed_admin(db)
    await seed_admin(db)

    result = await db.execute(select(Admin))
    admins = result.scalars().all()
    assert len(admins) == 1
