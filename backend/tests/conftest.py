"""Shared pytest fixtures for the wealth advisor copilot test suite."""
import asyncio
import uuid
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.main import app
from app.db.database import Base, get_db
from app.db.models import Tenant, User
from app.auth.jwt import hash_password
from tests.helpers import ADVISOR_PASSWORD, ADMIN_PASSWORD

# ── In-memory SQLite for tests (no real Postgres required) ────────────────────
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestSessionLocal = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

DEFAULT_TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
DEFAULT_USER_ID   = uuid.UUID("00000000-0000-0000-0000-000000000002")
ADMIN_USER_ID     = uuid.UUID("00000000-0000-0000-0000-000000000003")


@pytest.fixture(scope="session")
def event_loop():
    """Single event loop for the entire test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_db():
    """Create all tables once per session; drop after."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    """Per-test DB session, rolled back after each test."""
    async with TestSessionLocal() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def seed_tenant_and_users(db: AsyncSession):
    """Seed a tenant plus advisor and admin users."""
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
    db.add_all([tenant, advisor, admin])
    await db.commit()
    return {"tenant": tenant, "advisor": advisor, "admin": admin}


@pytest_asyncio.fixture
async def client(db: AsyncSession, seed_tenant_and_users) -> AsyncGenerator[AsyncClient, None]:
    """HTTP test client wired to the test DB session."""
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
