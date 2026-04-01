"""Tests for document management endpoints."""
import pytest
from httpx import AsyncClient

from tests.helpers import get_auth_headers, ADVISOR_PASSWORD, ADMIN_PASSWORD


@pytest.mark.asyncio
async def test_create_document_requires_auth(client: AsyncClient):
    resp = await client.post("/api/v1/documents/", json={
        "title": "Test Doc",
        "content": "Hello world",
        "sensitivity_level": "internal",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_advisor_can_create_internal_document(client: AsyncClient):
    headers = await get_auth_headers(client, "advisor@test.com", ADVISOR_PASSWORD)
    resp = await client.post("/api/v1/documents/", json={
        "title": "Internal Report",
        "content": "This is an internal document with sufficient content for ingestion testing.",
        "sensitivity_level": "internal",
        "source_type": "manual",
    }, headers=headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "Internal Report"
    assert body["sensitivity_level"] == "internal"
    assert body["is_approved"] is False
    assert body["ingestion_status"] == "pending"


@pytest.mark.asyncio
async def test_advisor_cannot_create_confidential_document(client: AsyncClient):
    headers = await get_auth_headers(client, "advisor@test.com", ADVISOR_PASSWORD)
    resp = await client.post("/api/v1/documents/", json={
        "title": "Secret Report",
        "content": "Confidential content.",
        "sensitivity_level": "confidential",
    }, headers=headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_create_confidential_document(client: AsyncClient):
    headers = await get_auth_headers(client, "admin@test.com", ADMIN_PASSWORD)
    resp = await client.post("/api/v1/documents/", json={
        "title": "Confidential Report",
        "content": "This is a confidential document with sufficient content.",
        "sensitivity_level": "confidential",
        "source_type": "manual",
    }, headers=headers)
    assert resp.status_code == 201
    assert resp.json()["sensitivity_level"] == "confidential"


@pytest.mark.asyncio
async def test_list_documents_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/documents/")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_documents_returns_accessible_only(client: AsyncClient):
    admin_headers = await get_auth_headers(client, "admin@test.com", ADMIN_PASSWORD)
    advisor_headers = await get_auth_headers(client, "advisor@test.com", ADVISOR_PASSWORD)

    # Admin creates a confidential document
    await client.post("/api/v1/documents/", json={
        "title": "Confidential Only",
        "content": "Confidential document that advisors cannot see.",
        "sensitivity_level": "confidential",
        "source_type": "manual",
    }, headers=admin_headers)

    # Advisor lists — should NOT see confidential
    advisor_resp = await client.get("/api/v1/documents/", headers=advisor_headers)
    assert advisor_resp.status_code == 200
    titles = [d["title"] for d in advisor_resp.json()["documents"]]
    assert "Confidential Only" not in titles

    # Admin lists — should see confidential
    admin_resp = await client.get("/api/v1/documents/", headers=admin_headers)
    assert admin_resp.status_code == 200
    titles = [d["title"] for d in admin_resp.json()["documents"]]
    assert "Confidential Only" in titles


@pytest.mark.asyncio
async def test_approve_document_requires_admin(client: AsyncClient):
    # Create a document as admin
    admin_headers = await get_auth_headers(client, "admin@test.com", ADMIN_PASSWORD)
    create = await client.post("/api/v1/documents/", json={
        "title": "To Approve",
        "content": "Document pending approval.",
        "sensitivity_level": "internal",
    }, headers=admin_headers)
    doc_id = create.json()["id"]

    # Advisor cannot approve
    advisor_headers = await get_auth_headers(client, "advisor@test.com", ADVISOR_PASSWORD)
    resp = await client.post(f"/api/v1/documents/{doc_id}/approve", headers=advisor_headers)
    assert resp.status_code == 403

    # Admin can approve
    resp = await client.post(f"/api/v1/documents/{doc_id}/approve", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["is_approved"] is True


@pytest.mark.asyncio
async def test_delete_document_requires_admin(client: AsyncClient):
    admin_headers = await get_auth_headers(client, "admin@test.com", ADMIN_PASSWORD)
    create = await client.post("/api/v1/documents/", json={
        "title": "To Delete",
        "content": "This document will be deleted.",
        "sensitivity_level": "internal",
    }, headers=admin_headers)
    doc_id = create.json()["id"]

    advisor_headers = await get_auth_headers(client, "advisor@test.com", ADVISOR_PASSWORD)
    resp = await client.delete(f"/api/v1/documents/{doc_id}", headers=advisor_headers)
    assert resp.status_code == 403

    resp = await client.delete(f"/api/v1/documents/{doc_id}", headers=admin_headers)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_create_document_without_content_or_url_fails(client: AsyncClient):
    headers = await get_auth_headers(client, "advisor@test.com", ADVISOR_PASSWORD)
    resp = await client.post("/api/v1/documents/", json={
        "title": "No Content",
        "sensitivity_level": "internal",
    }, headers=headers)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_duplicate_document_rejected(client: AsyncClient):
    headers = await get_auth_headers(client, "advisor@test.com", ADVISOR_PASSWORD)
    payload = {
        "title": "Duplicate Test",
        "content": "Unique content for deduplication testing purposes.",
        "sensitivity_level": "internal",
    }
    first = await client.post("/api/v1/documents/", json=payload, headers=headers)
    assert first.status_code == 201

    second = await client.post("/api/v1/documents/", json=payload, headers=headers)
    assert second.status_code == 409
