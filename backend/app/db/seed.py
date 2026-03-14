"""Seed the database with default data."""

import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Admin


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against a bcrypt hash."""
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


async def seed_admin(db: AsyncSession) -> None:
    """Create the default admin user if it doesn't already exist."""
    result = await db.execute(
        select(Admin).where(Admin.username == settings.admin_username)
    )
    existing = result.scalar_one_or_none()

    if existing is None:
        admin = Admin(
            username=settings.admin_username,
            password_hash=hash_password(settings.admin_password),
        )
        db.add(admin)
        await db.commit()
