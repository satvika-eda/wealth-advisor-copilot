"""Tests for authentication endpoints."""
import pytest
from httpx import AsyncClient

from tests.helpers import get_auth_headers, ADVISOR_PASSWORD, ADMIN_PASSWORD


@pytest.mark.asyncio
async def test_register_and_login(client: AsyncClient):
    """User can register and then log in."""
    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": "new@test.com", "password": "supersecure123", "full_name": "New User"},
    )
    assert reg.status_code == 201
    body = reg.json()
    assert "access_token" in body
    assert body["role"] == "advisor"

    login = await client.post(
        "/api/v1/auth/login",
        data={"username": "new@test.com", "password": "supersecure123"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert login.status_code == 200
    assert "access_token" in login.json()
    assert login.json()["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_password_too_short_rejected(client: AsyncClient):
    """Registration fails if password is under 12 characters."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "short@test.com", "password": "tooshort"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_role_escalation_blocked(client: AsyncClient):
    """Users cannot self-assign admin or compliance roles."""
    for role in ("admin", "compliance"):
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": f"{role}attempt@test.com", "password": "supersecure123", "role": role},
        )
        assert resp.status_code == 422, f"Expected 422 for role={role!r}"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    """Login fails with wrong password."""
    resp = await client.post(
        "/api/v1/auth/login",
        data={"username": "advisor@test.com", "password": "wrongpassword"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_unknown_user(client: AsyncClient):
    resp = await client.post(
        "/api/v1/auth/login",
        data={"username": "nobody@test.com", "password": "anything"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_returns_current_user(client: AsyncClient):
    headers = await get_auth_headers(client, "advisor@test.com", ADVISOR_PASSWORD)
    resp = await client.get("/api/v1/auth/me", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["email"] == "advisor@test.com"


@pytest.mark.asyncio
async def test_me_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_duplicate_email_rejected(client: AsyncClient):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "dup@test.com", "password": "supersecure123"},
    )
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "dup@test.com", "password": "anothersecure123"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_invalid_token_rejected(client: AsyncClient):
    resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer not.a.real.token"},
    )
    assert resp.status_code == 401
