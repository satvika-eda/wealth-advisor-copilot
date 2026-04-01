"""Database connection and session management."""
import uuid
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text, select
from typing import AsyncGenerator

from app.config import get_settings
from app.logging_config import get_logger

settings = get_settings()
logger = get_logger(__name__)

DATABASE_URL = settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")

engine = create_async_engine(
    DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=20,
    max_overflow=10,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency to get database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """Initialize database, create tables and enable pgvector."""
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        from app.db import models  # noqa: F401 — registers models against Base
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        from app.db.models import Tenant, User

        default_tenant_id = "00000000-0000-0000-0000-000000000001"
        default_user_id = "00000000-0000-0000-0000-000000000001"

        result = await session.execute(
            select(Tenant).where(Tenant.id == uuid.UUID(default_tenant_id))
        )
        if not result.scalar_one_or_none():
            session.add(Tenant(id=uuid.UUID(default_tenant_id), name="Default Tenant"))
            await session.commit()
            logger.info("Created default tenant", extra={"tenant_id": default_tenant_id})

        # Password is set from ADMIN_SEED_PASSWORD in settings; leave empty to skip seeding.
        seed_password = settings.ADMIN_SEED_PASSWORD
        if seed_password:
            result = await session.execute(
                select(User).where(User.id == uuid.UUID(default_user_id))
            )
            if not result.scalar_one_or_none():
                from app.auth.jwt import hash_password
                session.add(User(
                    id=uuid.UUID(default_user_id),
                    tenant_id=uuid.UUID(default_tenant_id),
                    email="admin@wealthadvisor.local",
                    hashed_password=hash_password(seed_password),
                    full_name="Default Admin",
                    role="admin",
                ))
                await session.commit()
                logger.info("Created default admin user", extra={"user_id": default_user_id})
