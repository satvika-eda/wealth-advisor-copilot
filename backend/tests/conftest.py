"""Shared pytest fixtures for the wealth advisor copilot test suite."""
import uuid
from typing import AsyncGenerator

import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import NullPool

from app.main import app
from app.db.database import Base, get_db
from app.db.models import Tenant, User
from app.auth.jwt import hash_password
from tests.helpers import ADVISOR_PASSWORD, ADMIN_PASSWORD

TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/wealth_advisor_test"

# NullPool avoids asyncpg connections being reused across event loop contexts
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False, poolclass=NullPool)
TestSessionLocal = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

DEFAULT_TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
DEFAULT_USER_ID   = uuid.UUID("00000000-0000-0000-0000-000000000002")
ADMIN_USER_ID     = uuid.UUID("00000000-0000-0000-0000-000000000003")


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_db():
    """Create schema once per session."""
    async with test_engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(autouse=True)
async def clean_and_seed(setup_db):
    """Truncate and re-seed before each test."""
    async with test_engine.begin() as conn:
        await conn.execute(text(
            "TRUNCATE audit_logs, conversations, chunks, documents, users, tenants"
            " RESTART IDENTITY CASCADE"
        ))

    async with TestSessionLocal() as session:
        tenant = Tenant(id=DEFAULT_TENANT_ID, name="Test Tenant")
        advisor = User(
            id=DEFAULT_USER_ID,
            tenant_id=DEFAULT_TENANT_ID,
            email="advisor@test.com",
            hashed_password=hash_password(ADVISOR_PASSWORD),
            full_name="Test Advisor",
            role="advisor",
        )
        admin = User(
            id=ADMIN_USER_ID,
            tenant_id=DEFAULT_TENANT_ID,
            email="admin@test.com",
            hashed_password=hash_password(ADMIN_PASSWORD),
            full_name="Test Admin",
            role="admin",
        )
        session.add_all([tenant, advisor, admin])
        await session.commit()
    yield


@pytest_asyncio.fixture
async def client(clean_and_seed) -> AsyncGenerator[AsyncClient, None]:
    """HTTP test client — each request gets its own DB session via NullPool."""
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with TestSessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
