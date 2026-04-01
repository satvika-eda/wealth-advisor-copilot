"""Shared test utilities — imported by test modules (not a test file itself)."""
from httpx import AsyncClient

ADVISOR_PASSWORD = "password123!"
ADMIN_PASSWORD = "adminpassword!"


async def get_auth_headers(client: AsyncClient, email: str, password: str) -> dict:
    """Log in and return an Authorization header dict."""
    resp = await client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
