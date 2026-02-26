"""Database connection and session management."""
import uuid
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text, select
from typing import AsyncGenerator

from app.config import get_settings

settings = get_settings()

# Convert sync URL to async
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
        # Enable pgvector extension
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        
        # Import models to register them
        from app.db import models  # noqa: F401
        
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)
    
    # Seed default tenant and user
    async with AsyncSessionLocal() as session:
        from app.db.models import Tenant, User
        
        default_tenant_id = "00000000-0000-0000-0000-000000000001"
        default_user_id = "00000000-0000-0000-0000-000000000001"
        
        # Create default tenant if not exists
        result = await session.execute(
            select(Tenant).where(Tenant.id == uuid.UUID(default_tenant_id))
        )
        if not result.scalar_one_or_none():
            tenant = Tenant(
                id=uuid.UUID(default_tenant_id),
                name="Default Tenant",
            )
            session.add(tenant)
            await session.commit()
            print("Created default tenant")
        
        # Create default user if not exists
        result = await session.execute(
            select(User).where(User.id == uuid.UUID(default_user_id))
        )
        if not result.scalar_one_or_none():
            user = User(
                id=uuid.UUID(default_user_id),
                tenant_id=uuid.UUID(default_tenant_id),
                email="admin@wealthadvisor.local",
                hashed_password="not-a-real-password",  # Demo only
                full_name="Default Admin",
                role="admin",
            )
            session.add(user)
            await session.commit()
            print("Created default user")
