"""
Shared pytest fixtures for the Akari Scout AI Agent test suite.

Provides:
- An async HTTPX client wired to the FastAPI app (no real server needed).
- Pre-created sessions for chat tests.
- Mocked agent / router responses so tests don't hit the Anthropic API.
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
import httpx

from app.config import settings


# ── Base URL & auth header ─────────────────────────────────────────────────

BASE_URL = "http://test"
HEADERS = {"X-API-Key": settings.API_KEY}
TENANT_ID = "test-tenant"


# ── Async client fixture ──────────────────────────────────────────────────

@pytest_asyncio.fixture
async def client():
    """Yield an async HTTPX client backed by the FastAPI ASGI app.

    Patches the database connection so we don't need a live Azure SQL
    instance during tests.
    """
    from app.database import db

    # Prevent real DB connection during lifespan startup
    with patch.object(db, "connect"), patch.object(db, "close"):
        from app.main import app

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as ac:
            yield ac


# ── Helper to create a session ────────────────────────────────────────────

@pytest_asyncio.fixture
async def session_id(client: httpx.AsyncClient) -> str:
    """Create a fresh session and return its ID."""
    resp = await client.put(
        "/sessions",
        json={"tenantId": TENANT_ID, "label": "Test Session"},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    return resp.json()["id"]
